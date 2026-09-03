from __future__ import annotations

import json
import logging
import os
import random
import re
import threading
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import requests

from reference_utils import (
    ReferenceMetadataExtractor,
    extract_journal_name,
    extract_s2_paper_id,
    has_zero_citation_count,
    infer_phenotypes_from_text,
    parse_metadata_list,
    text_has_usable_abstract,
    text_mentions_gene,
)
from text_utils import (
    emit_progress,
    emit_timing,
    format_duration,
    normalize_output_language,
    unique_preserving_order,
)

logger = logging.getLogger(__name__)

PRIMARY_PHENOTYPE = "breast cancer"
S2_GENERAL_LIMIT = 50
S2_PRIMARY_LIMIT = 15
S2_PUBLIC_MIN_INTERVAL_SECONDS = float(os.getenv("S2_PUBLIC_MIN_INTERVAL_SECONDS", "2.0"))
S2_API_KEY_MIN_INTERVAL_SECONDS = float(os.getenv("S2_API_KEY_MIN_INTERVAL_SECONDS", "2.0"))
S2_REQUEST_JITTER_SECONDS = max(0.0, float(os.getenv("S2_REQUEST_JITTER_SECONDS", "0.25")))
S2_DEFAULT_MAX_RETRIES = max(1, int(os.getenv("S2_DEFAULT_MAX_RETRIES", "3")))

STATUS_UNSET = object()
NON_ARTICLE_NOTICE_RE = re.compile(
    r"^\s*(correction|erratum|retraction|expression\s+of\s+concern)\s*:",
    flags=re.IGNORECASE,
)


def is_non_article_notice_title(title: str) -> bool:
    return bool(NON_ARTICLE_NOTICE_RE.search(title or ""))


def parse_retry_after_seconds(
    value: str | None,
    *,
    now: datetime | None = None,
) -> float | None:
    """Parse Retry-After as delta seconds or an HTTP date."""
    if not value or not str(value).strip():
        return None
    raw = str(value).strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        pass
    try:
        retry_at = parsedate_to_datetime(raw)
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        current = now or datetime.now(timezone.utc)
        return max(0.0, (retry_at - current).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return None


class SemanticScholarAgent:
    def __init__(
        self,
        api_key: str,
        cache_dir: Path | None = None,
        metadata_extractor: ReferenceMetadataExtractor | None = None,
    ):
        self.api_key = api_key
        self.cache_dir = cache_dir
        self.metadata_extractor = metadata_extractor
        self._public_request_lock = threading.Lock()
        self._api_key_request_lock = threading.Lock()
        self._status_lock = threading.Lock()
        self._last_public_request_at = 0.0
        self._last_api_key_request_at = 0.0
        self._api_key_status = "unknown" if api_key else "missing"
        self._public_fallback_active = not bool(api_key)
        self._public_fallback_announced = False
        self._last_error: str | None = None
        self._last_status_code: int | None = None
        self._last_retry_after_seconds: float | None = None
        self._last_mode = "public" if not api_key else "api_key"

    def _snapshot_status(self) -> dict[str, Any]:
        with self._status_lock:
            effective_mode = "public" if self._public_fallback_active or not self.api_key else "api_key"
            return {
                "api_key_present": bool(self.api_key),
                "api_key_status": self._api_key_status,
                "public_fallback_enabled": True,
                "public_fallback_active": self._public_fallback_active,
                "effective_mode": effective_mode,
                "last_mode": self._last_mode,
                "last_status_code": self._last_status_code,
                "last_error": self._last_error,
                "last_retry_after_seconds": self._last_retry_after_seconds,
                "public_min_interval_seconds": S2_PUBLIC_MIN_INTERVAL_SECONDS,
                "api_key_min_interval_seconds": S2_API_KEY_MIN_INTERVAL_SECONDS,
                "request_jitter_seconds": S2_REQUEST_JITTER_SECONDS,
            }

    def get_health_status(self) -> dict[str, Any]:
        return self._snapshot_status()

    def _update_status(
        self,
        *,
        api_key_status: Any = STATUS_UNSET,
        public_fallback_active: Any = STATUS_UNSET,
        last_error: Any = STATUS_UNSET,
        last_status_code: Any = STATUS_UNSET,
        last_retry_after_seconds: Any = STATUS_UNSET,
        last_mode: Any = STATUS_UNSET,
    ) -> None:
        with self._status_lock:
            if api_key_status is not STATUS_UNSET:
                self._api_key_status = api_key_status
            if public_fallback_active is not STATUS_UNSET:
                self._public_fallback_active = public_fallback_active
            if last_error is not STATUS_UNSET:
                self._last_error = last_error
            if last_status_code is not STATUS_UNSET:
                self._last_status_code = last_status_code
            if last_retry_after_seconds is not STATUS_UNSET:
                self._last_retry_after_seconds = last_retry_after_seconds
            if last_mode is not STATUS_UNSET:
                self._last_mode = last_mode

    def _maybe_emit_public_fallback_notice(
        self,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        with self._status_lock:
            if self._public_fallback_announced:
                return
            self._public_fallback_announced = True
        emit_progress(
            progress_callback,
            "Semantic Scholar API key is unavailable; falling back to public rate-limited search"
            if self.api_key
            else "Using public, rate-limited Semantic Scholar search",
        )

    def _respect_public_rate_limit(self) -> None:
        with self._public_request_lock:
            target_interval = S2_PUBLIC_MIN_INTERVAL_SECONDS + random.uniform(0.0, S2_REQUEST_JITTER_SECONDS)
            wait_seconds = target_interval - (time.monotonic() - self._last_public_request_at)
            if wait_seconds > 0:
                time.sleep(wait_seconds)
            self._last_public_request_at = time.monotonic()

    def _respect_api_key_rate_limit(self) -> None:
        with self._api_key_request_lock:
            target_interval = S2_API_KEY_MIN_INTERVAL_SECONDS + random.uniform(0.0, S2_REQUEST_JITTER_SECONDS)
            wait_seconds = target_interval - (
                time.monotonic() - self._last_api_key_request_at
            )
            if wait_seconds > 0:
                time.sleep(wait_seconds)
            self._last_api_key_request_at = time.monotonic()

    def _search_request(
        self,
        *,
        query: str,
        limit: int,
        max_retries: int,
        timeout: int | float,
        use_api_key: bool,
    ) -> tuple[Optional[List[Dict[str, Any]]], str, int | None, str | None]:
        url = "https://api.semanticscholar.org/graph/v1/paper/search"
        headers = {"x-api-key": self.api_key} if (use_api_key and self.api_key) else {}
        params = {
            "query": query,
            "limit": limit,
            "fields": "paperId,title,year,abstract,url,authors,citationCount,venue,journal,publicationVenue,openAccessPdf",
        }
        mode = "api_key" if headers else "public"
        request_timeout = (5.0, float(timeout))

        logger.info(
            "[S2] search(query=%r, limit=%d, mode=%s)",
            query,
            limit,
            mode,
        )

        last_status_code: int | None = None
        last_error: str | None = None
        for attempt in range(1, max_retries + 1):
            try:
                if headers:
                    self._respect_api_key_rate_limit()
                else:
                    self._respect_public_rate_limit()
                resp = requests.get(url, headers=headers, params=params, timeout=request_timeout)
            except requests.ReadTimeout as e:
                last_status_code = None
                last_error = str(e)
                logger.warning(
                    "[S2] read timeout for query=%r attempt=%d mode=%s; not retrying: %s",
                    query,
                    attempt,
                    mode,
                    e,
                )
                # The upstream service may still be processing a request after
                # the client stops waiting. Retrying it immediately can create
                # duplicate expensive searches and trigger automated throttles.
                return None, "read_timeout", None, last_error
            except requests.RequestException as e:
                last_status_code = None
                last_error = str(e)
                logger.warning("[S2] request error for query=%r attempt=%d mode=%s: %s", query, attempt, mode, e)
                if attempt < max_retries:
                    time.sleep(min(10, 5 * attempt))
                continue

            last_status_code = resp.status_code
            last_error = resp.text[:500]
            if resp.status_code == 200:
                return resp.json().get("data", []), "ok", 200, None

            if resp.status_code == 429:
                retry_after = parse_retry_after_seconds(resp.headers.get("Retry-After"))
                self._update_status(last_retry_after_seconds=retry_after)
                logger.warning(
                    "[S2] rate limited for query=%r attempt=%d mode=%s retry_after=%s; not retrying",
                    query,
                    attempt,
                    mode,
                    retry_after,
                )
                # Retrying an explicit throttle response inside the same query
                # can extend a rolling rate-limit window. The pre-index sweep's
                # persistent circuit breaker decides when to probe again.
                return None, "rate_limited", 429, last_error

            if resp.status_code in {401, 403} and headers:
                logger.error(
                    "[S2] auth failure for query=%r status=%s body=%s",
                    query,
                    resp.status_code,
                    resp.text[:500],
                )
                return None, "auth_failed", resp.status_code, resp.text[:500]

            if 500 <= resp.status_code <= 599:
                logger.warning(
                    "[S2] upstream server error for query=%r attempt=%d mode=%s status=%s",
                    query,
                    attempt,
                    mode,
                    resp.status_code,
                )
                if attempt < max_retries:
                    time.sleep(min(30, 2 ** attempt))
                continue

            logger.warning(
                "[S2] non-success response for query=%r mode=%s status=%s body=%s",
                query,
                mode,
                resp.status_code,
                resp.text[:500],
            )
            return None, "failed", resp.status_code, resp.text[:500]

        return (
            None,
            "failed",
            last_status_code,
            last_error or "retry budget exhausted",
        )

    def probe_health(self, timeout: int = 10) -> dict[str, Any]:
        query = f"{PRIMARY_PHENOTYPE} genomics"
        result: dict[str, Any] = {
            "status": "unknown",
            "query": query,
        }

        if self.api_key:
            data, outcome, status_code, error_text = self._search_request(
                query=query,
                limit=1,
                max_retries=1,
                timeout=timeout,
                use_api_key=True,
            )
            if outcome == "ok":
                self._update_status(
                    api_key_status="ok",
                    public_fallback_active=False,
                    last_error=None,
                    last_status_code=status_code,
                    last_retry_after_seconds=None,
                    last_mode="api_key",
                )
                result.update({
                    "status": "ok",
                    "api_key_check": "ok",
                    "public_check": None,
                    "hit_count": len(data or []),
                })
                result.update(self._snapshot_status())
                return result
            if outcome == "auth_failed":
                self._update_status(
                    api_key_status="forbidden",
                    public_fallback_active=True,
                    last_error=error_text or "Forbidden",
                    last_status_code=status_code,
                    last_mode="api_key",
                )
                public_data, public_outcome, public_status, public_error = self._search_request(
                    query=query,
                    limit=1,
                    max_retries=1,
                    timeout=timeout,
                    use_api_key=False,
                )
                result.update({
                    "api_key_check": "forbidden",
                    "api_key_status_code": status_code,
                    "public_check": public_outcome,
                    "public_status_code": public_status,
                    "hit_count": len(public_data or []),
                })
                if public_outcome == "ok":
                    self._update_status(
                        public_fallback_active=True,
                        last_error=None,
                        last_status_code=public_status,
                        last_mode="public",
                    )
                    result["status"] = "degraded"
                else:
                    self._update_status(
                        public_fallback_active=True,
                        last_error=public_error or error_text or "Semantic Scholar unavailable",
                        last_status_code=public_status or status_code,
                        last_mode="public",
                    )
                    result["status"] = "unavailable"
                result.update(self._snapshot_status())
                return result

            self._update_status(
                api_key_status="rate_limited" if outcome == "rate_limited" else "error",
                public_fallback_active=False,
                last_error=error_text or "Keyed request failed",
                last_status_code=status_code,
                last_mode="api_key",
            )
            result.update({
                "status": "unavailable",
                "api_key_check": outcome,
                "api_key_status_code": status_code,
                "public_check": None,
            })
            result.update(self._snapshot_status())
            return result

        public_data, public_outcome, public_status, public_error = self._search_request(
            query=query,
            limit=1,
            max_retries=1,
            timeout=timeout,
            use_api_key=False,
        )
        self._update_status(
            api_key_status="missing",
            public_fallback_active=True,
            last_error=None if public_outcome == "ok" else (public_error or "Public Semantic Scholar access unavailable"),
            last_status_code=public_status,
            last_mode="public",
        )
        result.update({
            "status": "ok" if public_outcome == "ok" else "unavailable",
            "api_key_check": "missing",
            "public_check": public_outcome,
            "public_status_code": public_status,
            "hit_count": len(public_data or []),
        })
        result.update(self._snapshot_status())
        return result

    def _emit_extraction_progress(
        self,
        *,
        query: str,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        if not self.metadata_extractor or not self.metadata_extractor.use_llm:
            return
        label = getattr(self.metadata_extractor, "label", "LLM")
        emit_progress(
            progress_callback,
            f'Extracting metadata for "{query}" (heuristics first; {label} only if needed)',
        )

    @staticmethod
    def _safe_cache_token(text: str) -> str:
        token = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower()
        return token or "query"

    def cache_path_for_gene(
        self,
        gene: str,
        phenotype: str | None = None,
    ) -> Path | None:
        """Return the canonical cache path used for a gene query."""
        if not self.cache_dir:
            return None
        safe_gene = "".join(x for x in gene if x.isalnum())
        if phenotype:
            safe_phenotype = self._safe_cache_token(phenotype)
            cache_name = f"{safe_gene}_{safe_phenotype}_s2.json"
        else:
            cache_name = f"{safe_gene}_general_s2.json"
        return self.cache_dir / cache_name

    def cached_query_succeeded(
        self,
        gene: str,
        phenotype: str | None = None,
    ) -> bool:
        """Whether a cache file records a completed Semantic Scholar request."""
        cache_path = self.cache_path_for_gene(gene, phenotype)
        if not cache_path or not cache_path.exists():
            return False
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            return payload.get("fetch_ok") is True
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return False

    def search(
        self,
        query: str,
        limit: int = 5,
        max_retries: int = S2_DEFAULT_MAX_RETRIES,
        timeout: int = 15,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        started_at = time.perf_counter()
        used_public_fallback = not bool(self.api_key)
        if used_public_fallback:
            self._maybe_emit_public_fallback_notice(progress_callback)
        request_mode = "API key" if self.api_key else "public endpoint"
        emit_progress(
            progress_callback,
            f'Sending query to Semantic Scholar: "{query}" ({request_mode})',
        )
        data, outcome, status_code, error_text = self._search_request(
            query=query,
            limit=limit,
            max_retries=max_retries,
            timeout=timeout,
            use_api_key=bool(self.api_key),
        )

        if outcome == "auth_failed":
            used_public_fallback = True
            self._update_status(
                api_key_status="forbidden",
                public_fallback_active=True,
                last_error=error_text or "Forbidden",
                last_status_code=status_code,
                last_mode="api_key",
            )
            self._maybe_emit_public_fallback_notice(progress_callback)
            emit_progress(
                progress_callback,
                f'Retrying Semantic Scholar query via public endpoint: "{query}"',
            )
            data, outcome, status_code, error_text = self._search_request(
                query=query,
                limit=limit,
                max_retries=max_retries,
                timeout=timeout,
                use_api_key=False,
            )

        if outcome == "ok":
            self._update_status(
                api_key_status=("ok" if self.api_key and not used_public_fallback else self._snapshot_status().get("api_key_status")),
                public_fallback_active=used_public_fallback,
                last_error=None,
                last_status_code=status_code,
                last_retry_after_seconds=None,
                last_mode="public" if used_public_fallback else "api_key",
            )
            emit_timing(
                progress_callback,
                f'Semantic Scholar search for "{query}"',
                time.perf_counter() - started_at,
                live=False,
                hits=len(data or []),
                mode="public" if used_public_fallback else "api_key",
            )
            emit_progress(
                progress_callback,
                f'Semantic Scholar returned {len(data or [])} papers for "{query}"',
            )
            return data or []

        self._update_status(
            api_key_status=(
                "missing"
                if not self.api_key
                else ("rate_limited" if outcome == "rate_limited" else self._snapshot_status().get("api_key_status"))
            ),
            public_fallback_active=used_public_fallback,
            last_error=error_text or "Semantic Scholar request failed",
            last_status_code=status_code,
            last_mode="public" if used_public_fallback else "api_key",
        )
        emit_progress(
            progress_callback,
            f'Semantic Scholar search unavailable for "{query}"'
            + (f" (status {status_code})" if status_code else ""),
        )
        emit_timing(
            progress_callback,
            f'Semantic Scholar search for "{query}"',
            time.perf_counter() - started_at,
            status=status_code or outcome,
            live=False,
            hits=0,
        )
        return None

    def cached_for_gene(
        self,
        gene: str,
        limit: int = S2_GENERAL_LIMIT,
        phenotype: str | None = None,
        progress_callback: Optional[Callable[[str], None]] = None,
        request_timeout: int = 15,
        max_retries: int = S2_DEFAULT_MAX_RETRIES,
    ) -> List[Dict[str, Any]]:
        started_at = time.perf_counter()
        query = f"{gene} {phenotype}".strip() if phenotype else gene

        if not self.cache_dir:
            return self.search(
                query,
                limit=limit,
                max_retries=max_retries,
                timeout=request_timeout,
                progress_callback=progress_callback,
            ) or []

        cache_path = self.cache_path_for_gene(gene, phenotype)
        if cache_path is None:
            return self.search(
                query,
                limit=limit,
                max_retries=max_retries,
                timeout=request_timeout,
                progress_callback=progress_callback,
            ) or []

        if cache_path.exists():
            try:
                cache_started_at = time.perf_counter()
                with open(cache_path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                papers = raw.get("data", [])
                fetch_ok = raw.get("fetch_ok")
                if not papers and fetch_ok is not True:
                    logger.info(
                        '[S2] ignoring stale/ambiguous empty cache for query=%r path=%s',
                        query,
                        cache_path,
                    )
                    raise ValueError("stale empty cache without fetch_ok=true")
                emit_progress(
                    progress_callback,
                    f'Using cached Semantic Scholar results for "{query}" ({len(papers)} papers)',
                )
                needs_metadata = any(
                    paper.get("entity_extraction_complete") is not True
                    for paper in papers
                    if isinstance(paper, dict)
                )
                if self.metadata_extractor and papers and needs_metadata:
                    self._emit_extraction_progress(query=query, progress_callback=progress_callback)
                    enrich_started_at = time.perf_counter()
                    papers, changed = self.metadata_extractor.enrich_papers(papers, seed_gene=gene)
                    emit_timing(
                        progress_callback,
                        f'Phenotype extraction for "{query}"',
                        time.perf_counter() - enrich_started_at,
                        live=False,
                        mode="cached",
                        papers=len(papers),
                    )
                    if changed:
                        raw["data"] = papers
                        with open(cache_path, "w", encoding="utf-8") as f:
                            json.dump(raw, f, ensure_ascii=False, indent=2)
                emit_timing(
                    progress_callback,
                    f'Loaded cached Semantic Scholar results for "{query}"',
                    time.perf_counter() - cache_started_at,
                    live=False,
                    papers=len(papers),
                )
                emit_timing(
                    progress_callback,
                    f'Semantic Scholar retrieval total for "{query}"',
                    time.perf_counter() - started_at,
                    source="cache",
                    live=False,
                    papers=len(papers),
                )
                return papers
            except Exception as e:
                logger.warning(f"[S2] Cache read error for {gene}: {e}")

        fetch_started_at = time.perf_counter()
        searched_papers = self.search(
            query,
            limit=limit,
            max_retries=max_retries,
            timeout=request_timeout,
            progress_callback=progress_callback,
        )
        if searched_papers is None:
            emit_timing(
                progress_callback,
                f'Semantic Scholar retrieval total for "{query}"',
                time.perf_counter() - started_at,
                source="api_failed",
                live=False,
                papers=0,
            )
            return []
        papers = searched_papers
        emit_timing(
            progress_callback,
            f'Fetched Semantic Scholar results for "{query}"',
            time.perf_counter() - fetch_started_at,
            live=False,
            papers=len(papers),
        )
        if self.metadata_extractor and papers:
            self._emit_extraction_progress(query=query, progress_callback=progress_callback)
            enrich_started_at = time.perf_counter()
            papers, _ = self.metadata_extractor.enrich_papers(papers, seed_gene=gene)
            emit_timing(
                progress_callback,
                f'Phenotype extraction for "{query}"',
                time.perf_counter() - enrich_started_at,
                live=False,
                mode="fresh",
                papers=len(papers),
            )

        payload = {
            "gene": gene,
            "phenotype": phenotype,
            "query": query,
            "retrieved_at": datetime.utcnow().isoformat(),
            "fetch_ok": True,
            "result_count": len(papers),
            "data": papers,
        }

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        emit_timing(
            progress_callback,
            f'Semantic Scholar retrieval total for "{query}"',
            time.perf_counter() - started_at,
            source="api",
            live=False,
            papers=len(papers),
        )

        return papers

    def papers_to_docs(
        self,
        gene: str,
        papers: List[Dict[str, Any]],
        pool_type: str = "general",
        phenotype: str | None = None,
    ) -> List[Dict[str, Any]]:
        docs: List[Dict[str, Any]] = []
        phenotype_slug = re.sub(r"[^A-Za-z0-9]+", "_", (phenotype or "general")).strip("_").lower() or "general"
        if self.metadata_extractor:
            papers, _ = self.metadata_extractor.enrich_papers(papers, seed_gene=gene)

        for p in papers:
            paper_id = extract_s2_paper_id(p)
            if not paper_id:
                continue 
            if has_zero_citation_count(p):
                continue

            title = p.get("title", "")
            abstract = p.get("abstract", "")
            url = p.get("url", "")

            if is_non_article_notice_title(str(title)):
                logger.info("[S2] Skipping non-article notice: %s", title)
                continue

            if not abstract or not str(abstract).strip():
                continue

            text = f"{title}\n\n{abstract}"
            if not text_mentions_gene(text, gene):
                continue
            extracted = {
                "genes": parse_metadata_list(p.get("extracted_genes")) or ([gene] if text_mentions_gene(text, gene) else []),
                "phenotypes": parse_metadata_list(p.get("extracted_phenotypes")) or infer_phenotypes_from_text(text),
            }
            extracted_genes = unique_preserving_order(
                [g for g in extracted.get("genes", []) if isinstance(g, str) and g.strip()]
            )
            extracted_phenotypes = unique_preserving_order(
                [p for p in extracted.get("phenotypes", []) if isinstance(p, str) and p.strip()]
            )

            docs.append(
                {
                    "id": f"s2::{pool_type}::{phenotype_slug}::{gene}::{paper_id}",
                    "text": text,
                    "meta": {
                        "source": "semanticscholar",
                        "gene": gene,
                        "pool_type": pool_type,
                        "phenotype": phenotype,
                        "paperId": paper_id,
                        "title": title,
                        "url": url,
                        "journal": extract_journal_name(p),
                        "citationCount": p.get("citationCount"),
                        "extracted_genes": ", ".join(extracted_genes) or None,
                        "extracted_phenotypes": ", ".join(extracted_phenotypes) or None,
                    },
                }
            )

        return docs

# ============================================================
# 4. Gene Importance Agent
# ============================================================
