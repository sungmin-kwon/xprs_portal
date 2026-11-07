from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents.semantic_scholar import S2_SEARCH_RAW_RESULT_CAP
from config import (
    LITERATURE_MINIMUM_INTERACTIVE_ELIGIBLE_DOCUMENTS,
    LITERATURE_MINIMUM_PRIMARY_ELIGIBLE_DOCUMENTS,
)
from disease_registry import DISEASE_REGISTRY
from reference_utils import (
    GENE_SEARCH_STRATEGY_VERSION,
    gene_search_strategies,
    literature_paper_is_eligible,
    publication_dedup_key,
)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _semantic_scholar_cache(payload: dict[str, Any]) -> dict[str, Any]:
    gene = str(payload.get("gene") or "").strip().upper()
    phenotype = str(payload.get("phenotype") or "").strip().lower()
    papers = [row for row in payload.get("data", []) if isinstance(row, dict)]
    raw_examined = int(payload.get("raw_examined") or len(papers))
    # Semantic Scholar is a one-shot fallback: only the canonical query is
    # expected, with a strict ten-paper cap and no alternate-query sweep.
    expected = gene_search_strategies(gene, phenotype or None)[:1]
    stored = {
        str(row.get("query") or "").strip(): row
        for row in payload.get("search_strategies") or []
        if isinstance(row, dict) and str(row.get("query") or "").strip()
    }
    legacy_query = str(payload.get("query") or "").strip()
    strategy_states: list[bool] = []
    for index, strategy in enumerate(expected):
        prior = stored.get(strategy["query"])
        if prior is None and index == 0 and legacy_query == strategy["query"]:
            prior = {
                "raw_examined": raw_examined,
                "complete": bool(payload.get("pagination_complete")),
                "fetch_ok": payload.get("fetch_ok") is True,
            }
        prior = prior or {}
        examined = max(0, int(prior.get("raw_examined") or 0))
        strategy_states.append(
            bool(prior.get("complete"))
            or prior.get("fetch_ok") is True
            or examined >= S2_SEARCH_RAW_RESULT_CAP
        )
    strategies_complete = sum(strategy_states)
    pagination_complete = bool(expected) and strategies_complete == len(expected)
    current_strategy = int(payload.get("search_strategy_version") or 0) == GENE_SEARCH_STRATEGY_VERSION
    enrichment_complete = bool(payload.get("enrichment_complete")) and (
        current_strategy or len(expected) == 1
    )
    eligible_keys = {
        publication_dedup_key(paper)
        for paper in papers
        if literature_paper_is_eligible(paper, gene)
    }
    eligible_keys.discard("")
    terminal = bool(
        payload.get("fetch_ok") is True
        and (enrichment_complete or pagination_complete)
    )
    return {
        "source": "semanticscholar", "gene": gene, "phenotype": phenotype,
        "fetch_ok": payload.get("fetch_ok") is True,
        "paper_count": len(papers), "raw_examined": raw_examined,
        "pagination_complete": pagination_complete,
        "enrichment_complete": enrichment_complete,
        "terminal": terminal,
        "enrichment_stop_reason": payload.get("enrichment_stop_reason") if enrichment_complete else None,
        "search_strategy_count": len(expected),
        "search_strategies_complete": strategies_complete,
        "eligible_count": len(eligible_keys),
        "eligible_keys": sorted(eligible_keys),
        "retrieved_at": payload.get("retrieved_at"),
    }


def _europe_pmc_cache(payload: dict[str, Any]) -> dict[str, Any]:
    papers = [row for row in payload.get("data", []) if isinstance(row, dict)]
    gene = str(payload.get("gene") or "").strip().upper()
    fetch_ok = payload.get("fetch_ok") is True
    pagination_complete = bool(payload.get("pagination_complete", True))
    eligible_keys = {
        publication_dedup_key(paper)
        for paper in papers
        if literature_paper_is_eligible(paper, gene)
    }
    eligible_keys.discard("")
    return {
        "source": "europe_pmc",
        "gene": gene,
        "phenotype": str(payload.get("phenotype") or "").strip().lower(),
        "fetch_ok": fetch_ok,
        "paper_count": len(papers),
        "raw_examined": int(payload.get("raw_examined") or len(papers)),
        "pagination_complete": pagination_complete,
        "enrichment_complete": fetch_ok and pagination_complete,
        "terminal": fetch_ok and pagination_complete,
        "enrichment_stop_reason": "provider_page_complete",
        "search_strategy_count": 0, "search_strategies_complete": 0,
        "eligible_count": len(eligible_keys),
        "eligible_keys": sorted(eligible_keys),
        "retrieved_at": payload.get("retrieved_at"),
    }


def _cache_queries(cache_dirs: dict[str, Path]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    queries: dict[tuple[str, str], list[dict[str, Any]]] = {}
    loaders = {
        "semanticscholar": ("*_s2.json", _semantic_scholar_cache),
        "europe_pmc": ("*_epmc.json", _europe_pmc_cache),
    }
    for source, directory in cache_dirs.items():
        pattern, loader = loaders[source]
        if not directory.exists():
            continue
        for path in directory.glob(pattern):
            record = loader(_read_json(path))
            if record["gene"]:
                queries.setdefault((record["gene"], record["phenotype"]), []).append(record)
    return queries


def _pool_status(
    documents: int,
    sources: list[dict[str, Any]],
    *,
    target_reached: bool,
    all_providers_terminal: bool,
    attempted: bool = False,
) -> str:
    finished = target_reached or all_providers_terminal
    if documents > 0:
        return "complete" if finished else "indexed"
    if not sources and not attempted:
        return "missing"
    if finished and all(int(row.get("eligible_count") or 0) == 0 for row in sources):
        return "empty"
    if any(int(row.get("eligible_count") or 0) > 0 for row in sources):
        return "cache_only"
    if any(row.get("fetch_ok") and int(row.get("paper_count") or 0) > 0 for row in sources):
        return "partial"
    return "partial"


def _provider_statuses(
    *,
    sources: list[dict[str, Any]],
    expected_providers: set[str],
    attempts: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    cached_by_source = {
        str(source.get("source")): source
        for source in sources
        if source.get("source")
    }
    statuses: list[dict[str, Any]] = []
    for provider in sorted(expected_providers):
        cached = cached_by_source.get(provider) or {}
        attempt = attempts.get(provider)
        outcome = str((attempt or {}).get("outcome") or "")
        if outcome in {"rate_limited", "auth_failed", "unavailable", "deferred"}:
            state = outcome
        elif cached.get("terminal"):
            state = "complete"
        elif cached.get("fetch_ok"):
            state = "incomplete"
        elif outcome == "success":
            state = "retrieved"
        else:
            state = "not_searched"
        statuses.append({
            "source": provider,
            "state": state,
            "cache_present": bool(cached),
            "terminal": bool(cached.get("terminal")),
            "paper_count": int(cached.get("paper_count") or 0),
            "eligible_count": int(cached.get("eligible_count") or 0),
            "retrieved_at": cached.get("retrieved_at"),
            "last_attempt": attempt,
        })
    return statuses


def _pool_record(
    *,
    phenotype: str,
    documents: int,
    sources: list[dict[str, Any]],
    expected_providers: set[str],
    attempts: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    eligible_keys = {
        key
        for source in sources
        for key in source.get("eligible_keys") or []
        if key
    }
    terminal_providers = {
        str(source.get("source")) for source in sources if source.get("terminal")
    }
    target = LITERATURE_MINIMUM_INTERACTIVE_ELIGIBLE_DOCUMENTS
    target_reached = len(eligible_keys) >= target
    all_providers_terminal = bool(expected_providers) and expected_providers.issubset(
        terminal_providers
    )
    complete = target_reached or all_providers_terminal
    completion_reason = (
        "evidence_target"
        if target_reached
        else "all_providers_exhausted" if all_providers_terminal else None
    )
    public_sources = [
        {key: value for key, value in source.items() if key != "eligible_keys"}
        for source in sources
    ]
    return {
        "pool": "phenotype" if phenotype else "general",
        "phenotype": phenotype or None,
        "documents": documents,
        "status": _pool_status(
            documents,
            sources,
            target_reached=target_reached,
            all_providers_terminal=all_providers_terminal,
            attempted=bool(attempts),
        ),
        "cache_present": bool(sources),
        "fetch_ok": any(row.get("fetch_ok") for row in sources),
        "paper_count": sum(int(row.get("paper_count") or 0) for row in sources),
        "raw_examined": sum(int(row.get("raw_examined") or 0) for row in sources),
        "pagination_complete": all_providers_terminal,
        "enrichment_complete": complete,
        "enrichment_stop_reason": completion_reason,
        "completion_reason": completion_reason,
        "evidence_target": target,
        "target_reached": target_reached,
        "all_providers_terminal": all_providers_terminal,
        "terminal_providers": sorted(terminal_providers),
        "incomplete_providers": sorted(expected_providers - terminal_providers),
        "eligible_count": len(eligible_keys),
        "retrieved_at": max((str(row.get("retrieved_at") or "") for row in sources), default="") or None,
        "search_strategy_count": sum(int(row.get("search_strategy_count") or 0) for row in sources),
        "search_strategies_complete": sum(int(row.get("search_strategies_complete") or 0) for row in sources),
        "sources": public_sources,
        "provider_statuses": _provider_statuses(
            sources=sources,
            expected_providers=expected_providers,
            attempts=attempts,
        ),
    }


def build_retrieval_coverage(
    *, inventory: dict[str, Any], cache_dirs: dict[str, Path],
    semantic_scholar: dict[str, Any] | None = None,
    provider_attempts: list[dict[str, Any]] | None = None,
    queue_status: dict[str, Any] | None = None,
    runtime_status: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Combine observed provider-cache and shared-index state."""
    caches = _cache_queries(cache_dirs)
    expected_providers = set(cache_dirs)
    attempts: dict[tuple[str, str, str], dict[str, Any]] = {}
    for raw_attempt in provider_attempts or []:
        source = str(raw_attempt.get("source") or "").strip()
        gene = str(raw_attempt.get("gene") or "").strip().upper()
        phenotype = str(raw_attempt.get("phenotype") or "").strip().lower()
        if not source or not gene:
            continue
        key = (source, gene, phenotype)
        previous = attempts.get(key)
        if previous is None or str(raw_attempt.get("attempted_at") or "") >= str(previous.get("attempted_at") or ""):
            attempts[key] = {
                "outcome": raw_attempt.get("outcome"),
                "http_status": raw_attempt.get("http_status"),
                "detail": str(raw_attempt.get("detail") or "")[:300] or None,
                "retry_after_seconds": raw_attempt.get("retry_after_seconds"),
                "attempted_at": raw_attempt.get("attempted_at"),
            }
    indexed = {
        str(row.get("gene") or "").upper(): row
        for row in inventory.get("genes", []) if row.get("gene")
    }
    genes = sorted(
        set(indexed)
        | {key[0] for key in caches}
        | {key[1] for key in attempts}
    )
    result_genes: list[dict[str, Any]] = []
    portal_phenotypes = {
        config.primary_phenotype for config in DISEASE_REGISTRY.values()
    }
    for gene in genes:
        indexed_row = indexed.get(gene, {})
        indexed_phenotypes = {
            str(key).strip().lower(): int(value or 0)
            for key, value in (indexed_row.get("phenotypes") or {}).items()
        }
        discovered = (
            {key[1] for key in caches if key[0] == gene}
            | {key[2] for key in attempts if key[1] == gene}
            | set(indexed_phenotypes)
        )
        if int((indexed_row.get("pools") or {}).get("general") or 0) > 0:
            discovered.add("")
        pools = []
        for phenotype in sorted(discovered, key=lambda value: (bool(value), value)):
            documents = int((indexed_row.get("pools") or {}).get("general") or 0) if not phenotype else indexed_phenotypes.get(phenotype, 0)
            pools.append(_pool_record(
                phenotype=phenotype, documents=documents,
                sources=caches.get((gene, phenotype), []),
                expected_providers=expected_providers,
                attempts={
                    provider: attempts[(provider, gene, phenotype)]
                    for provider in expected_providers
                    if (provider, gene, phenotype) in attempts
                },
            ))
        if any(pool["status"] in {"indexed", "complete"} for pool in pools):
            state = "indexed"
        elif any(pool["status"] == "cache_only" for pool in pools):
            state = "cache_only"
        elif any(pool["status"] == "partial" for pool in pools):
            state = "partial"
        elif pools and all(pool["status"] == "empty" for pool in pools):
            state = "empty"
        else:
            state = "missing"
        general_documents = int(
            (indexed_row.get("pools") or {}).get("general") or 0
        )
        general_phenotypes = {
            str(key).strip().lower(): int(value or 0)
            for key, value in (indexed_row.get("general_phenotypes") or {}).items()
        }
        covered_by_general = [
            {"phenotype": phenotype, "documents": count}
            for phenotype, count in sorted(general_phenotypes.items())
            if phenotype in portal_phenotypes
            and phenotype not in discovered
            and general_documents >= LITERATURE_MINIMUM_INTERACTIVE_ELIGIBLE_DOCUMENTS
            and count >= LITERATURE_MINIMUM_PRIMARY_ELIGIBLE_DOCUMENTS
        ]
        result_genes.append({
            "gene": gene, "documents": int(indexed_row.get("total") or 0),
            "sources": indexed_row.get("sources") or {},
            "coverage_state": state, "pools": pools,
            "covered_by_general": covered_by_general,
        })

    tracked = [pool for row in result_genes for pool in row["pools"]]
    cached = [pool for pool in tracked if pool["cache_present"]]
    health = dict(semantic_scholar or {})
    health.pop("last_error", None)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "indexed_documents": int(inventory.get("document_count") or 0),
            "indexed_genes": int(inventory.get("gene_count") or 0),
            "cached_query_pools": len(cached),
            "tracked_query_pools": len(tracked),
            "tracked_indexed_pools": sum(pool["documents"] > 0 for pool in tracked),
            "tracked_terminal_pools": sum(pool["status"] in {"complete", "empty"} for pool in tracked),
            "providers": sorted(cache_dirs),
        },
        "inventory": inventory, "semantic_scholar": health,
        "queue": queue_status or {}, "runtime_cooldowns": runtime_status or [],
        "genes": result_genes,
    }
