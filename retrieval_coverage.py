from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from reference_utils import GENE_SEARCH_STRATEGY_VERSION, gene_search_strategies


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
    page_size = int(payload.get("page_size") or 10)
    expected = gene_search_strategies(gene, phenotype or None)
    stored = {
        str(row.get("query") or "").strip(): row
        for row in payload.get("search_strategies") or []
        if isinstance(row, dict) and str(row.get("query") or "").strip()
    }
    if stored:
        strategies_complete = sum(
            bool((stored.get(item["query"]) or {}).get("complete")) for item in expected
        )
        pagination_complete = strategies_complete == len(expected)
    else:
        primary_complete = bool(payload.get("pagination_complete")) if "pagination_complete" in payload else (
            len(papers) < page_size or raw_examined >= 50
        )
        strategies_complete = int(primary_complete)
        pagination_complete = primary_complete and len(expected) == 1
    current_strategy = int(payload.get("search_strategy_version") or 0) == GENE_SEARCH_STRATEGY_VERSION
    enrichment_complete = bool(payload.get("enrichment_complete")) and (
        current_strategy or len(expected) == 1
    )
    return {
        "source": "semanticscholar", "gene": gene, "phenotype": phenotype,
        "fetch_ok": payload.get("fetch_ok") is True,
        "paper_count": len(papers), "raw_examined": raw_examined,
        "pagination_complete": pagination_complete,
        "enrichment_complete": enrichment_complete,
        "enrichment_stop_reason": payload.get("enrichment_stop_reason") if enrichment_complete else None,
        "search_strategy_count": len(expected),
        "search_strategies_complete": strategies_complete,
        "eligible_count": int(payload.get("eligible_count") or 0),
        "retrieved_at": payload.get("retrieved_at"),
    }


def _europe_pmc_cache(payload: dict[str, Any]) -> dict[str, Any]:
    papers = [row for row in payload.get("data", []) if isinstance(row, dict)]
    return {
        "source": "europe_pmc",
        "gene": str(payload.get("gene") or "").strip().upper(),
        "phenotype": str(payload.get("phenotype") or "").strip().lower(),
        "fetch_ok": payload.get("fetch_ok") is True,
        "paper_count": len(papers),
        "raw_examined": int(payload.get("raw_examined") or len(papers)),
        "pagination_complete": bool(payload.get("pagination_complete", True)),
        "enrichment_complete": True,
        "enrichment_stop_reason": "provider_page_complete",
        "search_strategy_count": 1, "search_strategies_complete": 1,
        "eligible_count": int(payload.get("eligible_count") or 0),
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


def _pool_status(documents: int, sources: list[dict[str, Any]]) -> str:
    finished = any(
        row.get("fetch_ok") and (row.get("enrichment_complete") or row.get("pagination_complete"))
        for row in sources
    )
    if documents > 0:
        return "complete" if finished else "indexed"
    if not sources:
        return "missing"
    if finished and all(int(row.get("eligible_count") or 0) == 0 for row in sources):
        return "empty"
    if any(row.get("fetch_ok") and int(row.get("paper_count") or 0) > 0 for row in sources):
        return "cache_only"
    return "partial"


def _pool_record(*, phenotype: str, documents: int, sources: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "pool": "phenotype" if phenotype else "general",
        "phenotype": phenotype or None,
        "documents": documents,
        "status": _pool_status(documents, sources),
        "cache_present": bool(sources),
        "fetch_ok": any(row.get("fetch_ok") for row in sources),
        "paper_count": sum(int(row.get("paper_count") or 0) for row in sources),
        "raw_examined": sum(int(row.get("raw_examined") or 0) for row in sources),
        "pagination_complete": any(row.get("pagination_complete") for row in sources),
        "enrichment_complete": any(row.get("enrichment_complete") for row in sources),
        "enrichment_stop_reason": next((row.get("enrichment_stop_reason") for row in sources if row.get("enrichment_stop_reason")), None),
        "eligible_count": sum(int(row.get("eligible_count") or 0) for row in sources),
        "retrieved_at": max((str(row.get("retrieved_at") or "") for row in sources), default="") or None,
        "search_strategy_count": sum(int(row.get("search_strategy_count") or 0) for row in sources),
        "search_strategies_complete": sum(int(row.get("search_strategies_complete") or 0) for row in sources),
        "sources": sources,
    }


def build_retrieval_coverage(
    *, inventory: dict[str, Any], cache_dirs: dict[str, Path],
    semantic_scholar: dict[str, Any] | None = None,
    queue_status: dict[str, Any] | None = None,
    runtime_status: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Combine observed provider-cache and shared-index state."""
    caches = _cache_queries(cache_dirs)
    indexed = {
        str(row.get("gene") or "").upper(): row
        for row in inventory.get("genes", []) if row.get("gene")
    }
    genes = sorted(set(indexed) | {key[0] for key in caches})
    result_genes: list[dict[str, Any]] = []
    for gene in genes:
        indexed_row = indexed.get(gene, {})
        indexed_phenotypes = {
            str(key).strip().lower(): int(value or 0)
            for key, value in (indexed_row.get("phenotypes") or {}).items()
        }
        discovered = {key[1] for key in caches if key[0] == gene} | set(indexed_phenotypes)
        if int((indexed_row.get("pools") or {}).get("general") or 0) > 0:
            discovered.add("")
        pools = []
        for phenotype in sorted(discovered, key=lambda value: (bool(value), value)):
            documents = int((indexed_row.get("pools") or {}).get("general") or 0) if not phenotype else indexed_phenotypes.get(phenotype, 0)
            pools.append(_pool_record(
                phenotype=phenotype, documents=documents,
                sources=caches.get((gene, phenotype), []),
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
        result_genes.append({
            "gene": gene, "documents": int(indexed_row.get("total") or 0),
            "sources": indexed_row.get("sources") or {},
            "coverage_state": state, "pools": pools,
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
