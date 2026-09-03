from __future__ import annotations

import csv
import hashlib
import json
import re
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from agents.semantic_scholar import PRIMARY_PHENOTYPE, S2_GENERAL_LIMIT, S2_PRIMARY_LIMIT


MANIFEST_FIELDS = (
    "rank",
    "gene",
    "occurrences",
    "risk_increasing_occurrences",
    "risk_lowering_occurrences",
    "individual_coverage",
    "slot_coverage",
    "cumulative_slot_coverage",
    "queryable",
    "exclusion_reason",
)
GENE_SYMBOL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9-]{1,39}$")
PLACEHOLDER_GENE_RE = re.compile(r"^NA(?:_\d+)?$", re.IGNORECASE)
TEMPORARY_FAILURE_EXIT_CODE = 75


class SemanticScholarPoolError(RuntimeError):
    def __init__(
        self,
        *,
        query: str,
        status_code: int | None,
        detail: str | None,
        retry_after_seconds: float | None = None,
    ):
        self.query = query
        self.status_code = status_code
        self.detail = detail or "Semantic Scholar request failed"
        self.retry_after_seconds = retry_after_seconds
        self.transient = (
            status_code is None
            or status_code == 429
            or (isinstance(status_code, int) and 500 <= status_code <= 599)
        )
        status_text = f"status {status_code}" if status_code is not None else "network error"
        super().__init__(
            f'Semantic Scholar query did not complete successfully: "{query}" ({status_text})'
        )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify_gene_symbol(gene: str) -> tuple[bool, str]:
    symbol = str(gene or "").strip()
    if not symbol:
        return False, "empty"
    if PLACEHOLDER_GENE_RE.fullmatch(symbol):
        return False, "placeholder"
    if not GENE_SYMBOL_RE.fullmatch(symbol):
        return False, "unsupported_symbol_format"
    return True, ""


def build_frequency_manifest(
    csv_path: Path,
    *,
    sweep_n: int = 10,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Rank genes appearing in each individual's strongest positive/negative slots.

    Positive and negative occurrences have identical weight. Pandas' stable
    ``keep='first'`` behavior makes ties reproduce the portal's current
    ``nlargest``/``nsmallest`` selection semantics.
    """
    if sweep_n < 1:
        raise ValueError("sweep_n must be at least 1")

    data = pd.read_csv(csv_path)
    if "Gene" not in data.columns:
        raise ValueError(f"{csv_path} does not contain a Gene column")
    individual_columns = [str(column) for column in data.columns if column != "Gene"]
    if not individual_columns:
        raise ValueError(f"{csv_path} does not contain individual columns")

    genes = data["Gene"].astype(str)
    increasing: Counter[str] = Counter()
    lowering: Counter[str] = Counter()

    for iid in individual_columns:
        values = pd.to_numeric(data[iid], errors="coerce")
        for index in values.nlargest(sweep_n, keep="first").index:
            increasing[genes.at[index]] += 1
        for index in values.nsmallest(sweep_n, keep="first").index:
            lowering[genes.at[index]] += 1

    ranked_genes = sorted(
        set(increasing) | set(lowering),
        key=lambda gene: (-(increasing[gene] + lowering[gene]), gene),
    )
    total_slots = sum(increasing.values()) + sum(lowering.values())
    cumulative_slots = 0
    rows: list[dict[str, Any]] = []
    for rank, gene in enumerate(ranked_genes, start=1):
        positive_count = increasing[gene]
        negative_count = lowering[gene]
        occurrences = positive_count + negative_count
        cumulative_slots += occurrences
        queryable, exclusion_reason = classify_gene_symbol(gene)
        rows.append({
            "rank": rank,
            "gene": gene,
            "occurrences": occurrences,
            "risk_increasing_occurrences": positive_count,
            "risk_lowering_occurrences": negative_count,
            "individual_coverage": occurrences / len(individual_columns),
            "slot_coverage": occurrences / total_slots if total_slots else 0.0,
            "cumulative_slot_coverage": cumulative_slots / total_slots if total_slots else 0.0,
            "queryable": queryable,
            "exclusion_reason": exclusion_reason,
        })

    metadata = {
        "source_csv": str(csv_path.resolve()),
        "source_sha256": sha256_file(csv_path),
        "generated_at": utc_now(),
        "sweep_n_per_direction": sweep_n,
        "individual_count": len(individual_columns),
        "source_gene_count": int(data["Gene"].nunique()),
        "ranked_gene_count": len(rows),
        "queryable_gene_count": sum(bool(row["queryable"]) for row in rows),
        "total_slots": total_slots,
        "risk_increasing_slots": sum(increasing.values()),
        "risk_lowering_slots": sum(lowering.values()),
    }
    return rows, metadata


def select_frequent_genes(
    rows: Iterable[dict[str, Any]],
    *,
    max_genes: int | None = 200,
    min_occurrences: int = 1,
) -> list[dict[str, Any]]:
    if max_genes is not None and max_genes < 1:
        raise ValueError("max_genes must be at least 1 or None")
    if min_occurrences < 1:
        raise ValueError("min_occurrences must be at least 1")
    selected = [
        row
        for row in rows
        if bool(row.get("queryable"))
        and int(row.get("occurrences") or 0) >= min_occurrences
    ]
    return selected if max_genes is None else selected[:max_genes]


def write_manifest(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary_path = Path(handle.name)
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        for row in rows:
            serialized = dict(row)
            for field in ("individual_coverage", "slot_coverage", "cumulative_slot_coverage"):
                serialized[field] = f"{float(serialized[field]):.8f}"
            serialized["queryable"] = "true" if serialized["queryable"] else "false"
            writer.writerow({field: serialized.get(field, "") for field in MANIFEST_FIELDS})
    temporary_path.replace(path)
    path.chmod(0o644)


def load_checkpoint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": 1, "genes": {}}
    try:
        with path.open("r", encoding="utf-8") as handle:
            state = json.load(handle)
        if not isinstance(state, dict) or not isinstance(state.get("genes", {}), dict):
            raise ValueError("invalid checkpoint structure")
        state.setdefault("schema_version", 1)
        state.setdefault("genes", {})
        return state
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read pre-index checkpoint {path}: {exc}") from exc


def save_checkpoint(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = utc_now()
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary_path = Path(handle.name)
        json.dump(state, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    temporary_path.replace(path)


def _pool_where(gene: str, pool_type: str, phenotype: str | None) -> dict[str, Any]:
    clauses: list[dict[str, Any]] = [{"gene": gene}, {"pool_type": pool_type}]
    if phenotype:
        clauses.append({"phenotype": phenotype})
    return {"$and": clauses}


def index_semantic_scholar_pool(
    *,
    gene: str,
    phenotype: str | None,
    limit: int,
    s2_agent: Any,
    rag_agent: Any,
    progress_callback: Any = None,
    request_timeout_seconds: int = 45,
    max_attempts: int = 2,
) -> dict[str, Any]:
    pool_type = "phenotype" if phenotype else "general"
    where = _pool_where(gene, pool_type, phenotype)
    if rag_agent.has_documents(where):
        return {
            "status": "already_indexed",
            "paper_count": None,
            "document_count": None,
        }

    cache_was_ready = bool(
        cache_dir := getattr(s2_agent, "cache_dir", None)
    ) and s2_agent.cached_query_succeeded(gene, phenotype)
    papers = s2_agent.cached_for_gene(
        gene,
        limit=limit,
        phenotype=phenotype,
        progress_callback=progress_callback,
        request_timeout=request_timeout_seconds,
        max_retries=max_attempts,
    )
    if cache_dir and not s2_agent.cached_query_succeeded(gene, phenotype):
        query = f"{gene} {phenotype}".strip() if phenotype else gene
        health = (
            s2_agent.get_health_status()
            if hasattr(s2_agent, "get_health_status")
            else {}
        )
        status_code = health.get("last_status_code")
        if not isinstance(status_code, int):
            status_code = None
        raise SemanticScholarPoolError(
            query=query,
            status_code=status_code,
            detail=health.get("last_error"),
            retry_after_seconds=health.get("last_retry_after_seconds"),
        )

    documents = s2_agent.papers_to_docs(
        gene,
        papers,
        pool_type=pool_type,
        phenotype=phenotype,
    )
    if documents:
        rag_agent.upsert_docs(documents)
    return {
        "status": "indexed",
        "source": "cache" if cache_was_ready else "api",
        "paper_count": len(papers),
        "document_count": len(documents),
    }


def preindex_gene(
    *,
    gene: str,
    s2_agent: Any,
    rag_agent: Any,
    progress_callback: Any = None,
    query_delay_seconds: float = 0.0,
    request_timeout_seconds: int = 45,
    max_attempts: int = 2,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "gene": gene,
        "status": "completed",
        "started_at": utc_now(),
        "pools": {},
        "errors": [],
        "halt_sweep": False,
    }
    pools = (
        ("general", None, S2_GENERAL_LIMIT),
        ("primary", PRIMARY_PHENOTYPE, S2_PRIMARY_LIMIT),
    )
    for label, phenotype, limit in pools:
        try:
            pool_result = index_semantic_scholar_pool(
                gene=gene,
                phenotype=phenotype,
                limit=limit,
                s2_agent=s2_agent,
                rag_agent=rag_agent,
                progress_callback=progress_callback,
                request_timeout_seconds=request_timeout_seconds,
                max_attempts=max_attempts,
            )
            result["pools"][label] = pool_result
            if pool_result.get("source") == "api" and query_delay_seconds > 0:
                time.sleep(query_delay_seconds)
        except SemanticScholarPoolError as exc:
            result["status"] = "failed"
            result["errors"].append(f"{label}: {exc}")
            result["pools"][label] = {
                "status": "failed",
                "error": str(exc),
                "status_code": exc.status_code,
                "retry_after_seconds": exc.retry_after_seconds,
                "transient": exc.transient,
            }
            if exc.transient:
                result["halt_sweep"] = True
                result["circuit_breaker_reason"] = {
                    "gene": gene,
                    "pool": label,
                    "query": exc.query,
                    "status_code": exc.status_code,
                    "detail": exc.detail,
                    "retry_after_seconds": exc.retry_after_seconds,
                }
                break
        except Exception as exc:
            result["status"] = "failed"
            result["errors"].append(f"{label}: {exc}")
            result["pools"][label] = {
                "status": "failed",
                "error": str(exc),
                "status_code": None,
                "transient": False,
            }
    result["finished_at"] = utc_now()
    return result
