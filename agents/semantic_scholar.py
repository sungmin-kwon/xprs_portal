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
    GENE_IDENTITY_POLICY_VERSION,
    GENE_SEARCH_STRATEGY_VERSION,
    ReferenceMetadataExtractor,
    extract_journal_name,
    extract_s2_paper_id,
    gene_search_query,
    gene_search_strategies,
    has_zero_citation_count,
    infer_phenotypes_from_text,
    paper_gene_identity_is_valid,
    parse_metadata_list,
)
from text_utils import (
    emit_progress,
    emit_timing,
    unique_preserving_order,
)

logger = logging.getLogger(__name__)

PRIMARY_PHENOTYPE = "breast cancer"
# Keep interactive response pages small to reduce the cost of abstract-rich
# searches. Retrieval quality comes from the general + phenotype pool union and
# reranker rather than one oversized upstream response.
S2_GENERAL_LIMIT = max(1, int(os.getenv("S2_GENERAL_LIMIT", "10")))
S2_PRIMARY_LIMIT = max(1, int(os.getenv("S2_PRIMARY_LIMIT", "10")))
S2_PUBLIC_MIN_INTERVAL_SECONDS = float(os.getenv("S2_PUBLIC_MIN_INTERVAL_SECONDS", "2.0"))
S2_API_KEY_MIN_INTERVAL_SECONDS = float(os.getenv("S2_API_KEY_MIN_INTERVAL_SECONDS", "15.0"))
S2_REQUEST_JITTER_SECONDS = max(0.0, float(os.getenv("S2_REQUEST_JITTER_SECONDS", "0.25")))
S2_DEFAULT_MAX_RETRIES = max(1, int(os.getenv("S2_DEFAULT_MAX_RETRIES", "3")))
S2_SEARCH_RAW_RESULT_CAP = max(
    1, int(os.getenv("S2_ENRICHMENT_MAX_RAW_RESULTS", "50"))
)

STATUS_UNSET = object()


class CacheQueryStrategyChanged(ValueError):
    """A cached page belongs to an older gene-disambiguation query."""


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
        self._cache_locks_guard = threading.Lock()
        self._cache_locks: dict[str, threading.Lock] = {}

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

    def _respect_api_key_rate_limit(
        self,
        minimum_interval_seconds: float | None = None,
    ) -> None:
        with self._api_key_request_lock:
            target_interval = max(
                S2_API_KEY_MIN_INTERVAL_SECONDS,
                float(minimum_interval_seconds or 0.0),
            ) + random.uniform(0.0, S2_REQUEST_JITTER_SECONDS)
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
        offset: int = 0,
        api_key_min_interval_seconds: float | None = None,
    ) -> tuple[Optional[List[Dict[str, Any]]], str, int | None, str | None]:
        url = "https://api.semanticscholar.org/graph/v1/paper/search"
        headers = {"x-api-key": self.api_key} if (use_api_key and self.api_key) else {}
        params = {
            "query": query,
            "limit": limit,
            "offset": max(0, int(offset)),
            "fields": "paperId,title,year,abstract,url,authors,citationCount,venue,journal,publicationVenue,openAccessPdf,externalIds",
        }
        mode = "api_key" if headers else "public"
        request_timeout = (5.0, float(timeout))

        last_status_code: int | None = None
        last_error: str | None = None
        for attempt in range(1, max_retries + 1):
            try:
                if headers:
                    if api_key_min_interval_seconds is None:
                        self._respect_api_key_rate_limit()
                    else:
                        self._respect_api_key_rate_limit(api_key_min_interval_seconds)
                else:
                    self._respect_public_rate_limit()
                logger.info(
                    "[S2] sending request query=%r offset=%d limit=%d mode=%s attempt=%d",
                    query,
                    offset,
                    limit,
                    mode,
                    attempt,
                )
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
                # can extend a rolling rate-limit window. Maintenance callers'
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

    def probe_api_key(self, timeout: int = 10) -> dict[str, Any]:
        """Run one keyed request and report validity without public fallback."""
        query = f"{PRIMARY_PHENOTYPE} genomics"
        checked_at = datetime.now(timezone.utc).isoformat()
        if not self.api_key:
            self._update_status(api_key_status="missing")
            return {
                "status": "missing",
                "checked_at": checked_at,
                "query": query,
                **self._snapshot_status(),
            }

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
            status = "ok"
        elif outcome == "auth_failed":
            self._update_status(
                api_key_status="forbidden",
                public_fallback_active=False,
                last_error=error_text or "API key rejected",
                last_status_code=status_code,
                last_mode="api_key",
            )
            status = "invalid"
        else:
            self._update_status(
                api_key_status="rate_limited" if outcome == "rate_limited" else "error",
                public_fallback_active=False,
                last_error=error_text or "Keyed request failed",
                last_status_code=status_code,
                last_mode="api_key",
            )
            status = "rate_limited" if outcome == "rate_limited" else "unavailable"
        return {
            "status": status,
            "checked_at": checked_at,
            "query": query,
            "http_status": status_code,
            "hit_count": len(data or []),
            **self._snapshot_status(),
        }

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
            f'Validating gene identity and metadata for "{query}" '
            f'(deterministic checks first; {label} for ambiguous symbols)',
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

    def _cache_lock(self, cache_path: Path) -> threading.Lock:
        key = str(cache_path)
        with self._cache_locks_guard:
            return self._cache_locks.setdefault(key, threading.Lock())

    @staticmethod
    def _read_cache_payload(cache_path: Path) -> dict[str, Any]:
        with cache_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _write_cache_payload(cache_path: Path, payload: dict[str, Any]) -> None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache_path.with_name(
            f".{cache_path.name}.{threading.get_ident()}.tmp"
        )
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(temporary, cache_path)

    def cached_papers(
        self,
        gene: str,
        phenotype: str | None = None,
    ) -> list[dict[str, Any]]:
        cache_path = self.cache_path_for_gene(gene, phenotype)
        if not cache_path or not cache_path.exists():
            return []
        try:
            payload = self._read_cache_payload(cache_path)
            return [paper for paper in payload.get("data", []) if isinstance(paper, dict)]
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return []

    def find_cached_paper(
        self,
        paper_id: str,
        genes: list[str] | tuple[str, ...],
    ) -> dict[str, Any] | None:
        """Find one paper in provider caches without making a request."""
        if self.cache_dir is None:
            return None
        wanted = str(paper_id or "").strip().casefold()
        if not wanted:
            return None

        preferred_paths: list[Path] = []
        for gene in genes:
            safe_gene = "".join(character for character in gene if character.isalnum())
            preferred_paths.extend(self.cache_dir.glob(f"{safe_gene}_*_s2.json"))
        seen_paths: set[Path] = set()
        for path in [*preferred_paths, *self.cache_dir.glob("*_s2.json")]:
            if path in seen_paths:
                continue
            seen_paths.add(path)
            try:
                payload = self._read_cache_payload(path)
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
            for paper in payload.get("data", []):
                if not isinstance(paper, dict):
                    continue
                external_ids = (
                    paper.get("externalIds")
                    if isinstance(paper.get("externalIds"), dict)
                    else {}
                )
                pmid = str(external_ids.get("PubMed") or paper.get("pmid") or "").strip()
                pmcid = str(
                    external_ids.get("PubMedCentral") or paper.get("pmcid") or ""
                ).strip()
                doi = str(external_ids.get("DOI") or paper.get("doi") or "").strip()
                identifiers = {
                    extract_s2_paper_id(paper),
                    pmid,
                    f"PMID:{pmid}" if pmid else "",
                    pmcid,
                    f"PMCID:{pmcid}" if pmcid else "",
                    doi,
                    f"DOI:{doi}" if doi else "",
                }
                if wanted in {identifier.casefold() for identifier in identifiers if identifier}:
                    return paper
        return None

    @staticmethod
    def _strategy_states(
        payload: dict[str, Any],
        gene: str,
        phenotype: str | None,
        *,
        page_size: int,
        max_raw_results: int,
    ) -> list[dict[str, Any]]:
        """Normalize current and legacy cache pagination into query states."""
        expected = gene_search_strategies(gene, phenotype)
        stored = payload.get("search_strategies")
        stored_by_query = {
            str(item.get("query") or "").strip(): item
            for item in stored or []
            if isinstance(item, dict) and str(item.get("query") or "").strip()
        }
        legacy_query = str(payload.get("query") or "").strip()
        states: list[dict[str, Any]] = []
        for index, strategy in enumerate(expected):
            prior = stored_by_query.get(strategy["query"])
            if prior is None and index == 0 and legacy_query == strategy["query"]:
                raw_examined = int(
                    payload.get("raw_examined")
                    or len([p for p in payload.get("data", []) if isinstance(p, dict)])
                )
                prior = {
                    "raw_examined": raw_examined,
                    "next_offset": int(payload.get("next_offset") or raw_examined),
                    "complete": bool(payload.get("pagination_complete")),
                    "fetch_ok": payload.get("fetch_ok") is True,
                }
            prior = prior or {}
            raw_examined = max(0, int(prior.get("raw_examined") or 0))
            states.append({
                "name": strategy["name"],
                "query": strategy["query"],
                "fetch_ok": prior.get("fetch_ok") is True,
                "raw_examined": raw_examined,
                "next_offset": max(0, int(prior.get("next_offset") or raw_examined)),
                "complete": bool(prior.get("complete")) or raw_examined >= max_raw_results,
                "page_size": max(1, int(prior.get("page_size") or page_size)),
            })
        return states

    @staticmethod
    def _active_strategy_index(states: list[dict[str, Any]]) -> int | None:
        return next(
            (index for index, state in enumerate(states) if not state.get("complete")),
            None,
        )

    def pagination_status(
        self,
        gene: str,
        phenotype: str | None = None,
        *,
        page_size: int = 10,
        max_raw_results: int = 50,
    ) -> dict[str, Any]:
        cache_path = self.cache_path_for_gene(gene, phenotype)
        if not cache_path or not cache_path.exists():
            return {
                "fetch_ok": False,
                "raw_examined": 0,
                "next_offset": 0,
                "pagination_complete": False,
            }
        try:
            payload = self._read_cache_payload(cache_path)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return {
                "fetch_ok": False,
                "raw_examined": 0,
                "next_offset": 0,
                "pagination_complete": False,
            }
        papers = [paper for paper in payload.get("data", []) if isinstance(paper, dict)]
        states = self._strategy_states(
            payload,
            gene,
            phenotype,
            page_size=page_size,
            max_raw_results=max_raw_results,
        )
        active_index = self._active_strategy_index(states)
        active = states[active_index] if active_index is not None else None
        raw_examined = sum(int(state.get("raw_examined") or 0) for state in states)
        complete = active is None
        next_offset = int(active.get("next_offset") or 0) if active else 0
        try:
            stored_strategy_version = int(payload.get("search_strategy_version") or 0)
        except (TypeError, ValueError):
            stored_strategy_version = 0
        enrichment_complete = bool(payload.get("enrichment_complete")) and (
            stored_strategy_version == GENE_SEARCH_STRATEGY_VERSION
            or len(states) <= 1
        )
        return {
            "fetch_ok": payload.get("fetch_ok") is True,
            "raw_examined": raw_examined,
            "next_offset": next_offset,
            "pagination_complete": complete,
            "paper_count": len(papers),
            "enrichment_complete": enrichment_complete,
            "enrichment_stop_reason": (
                payload.get("enrichment_stop_reason") if enrichment_complete else None
            ),
            "eligible_count": int(payload.get("eligible_count") or 0),
            "zero_yield_pages": int(payload.get("zero_yield_pages") or 0),
            "search_strategy_version": GENE_SEARCH_STRATEGY_VERSION,
            "search_strategy_count": len(states),
            "search_strategies_complete": sum(bool(state.get("complete")) for state in states),
            "active_search_strategy": active.get("name") if active else None,
            "active_search_query": active.get("query") if active else None,
        }

    def advance_to_next_search_strategy(
        self,
        gene: str,
        phenotype: str | None = None,
        *,
        page_size: int = 10,
        max_raw_results: int = 50,
    ) -> bool:
        """Stop a low-yield strategy and expose the next fallback, if any."""
        cache_path = self.cache_path_for_gene(gene, phenotype)
        if not cache_path or not cache_path.exists():
            return False
        with self._cache_lock(cache_path):
            payload = self._read_cache_payload(cache_path)
            states = self._strategy_states(
                payload,
                gene,
                phenotype,
                page_size=page_size,
                max_raw_results=max_raw_results,
            )
            active_index = self._active_strategy_index(states)
            if active_index is None:
                return False
            states[active_index]["complete"] = True
            states[active_index]["stop_reason"] = "low_yield"
            has_next = self._active_strategy_index(states) is not None
            payload.update({
                "search_strategy_version": GENE_SEARCH_STRATEGY_VERSION,
                "search_strategies": states,
                "pagination_complete": not has_next,
                "enrichment_complete": False,
                "enrichment_stop_reason": None,
                "zero_yield_pages": 0,
            })
            self._write_cache_payload(cache_path, payload)
            return has_next

    def record_enrichment_status(
        self,
        gene: str,
        phenotype: str | None,
        *,
        eligible_count: int,
        zero_yield_pages: int,
        complete: bool,
        stop_reason: str | None = None,
    ) -> None:
        cache_path = self.cache_path_for_gene(gene, phenotype)
        if not cache_path or not cache_path.exists():
            return
        with self._cache_lock(cache_path):
            payload = self._read_cache_payload(cache_path)
            page_size = max(1, int(payload.get("page_size") or 10))
            states = self._strategy_states(
                payload,
                gene,
                phenotype,
                page_size=page_size,
                max_raw_results=S2_SEARCH_RAW_RESULT_CAP,
            )
            if complete:
                for state in states:
                    state["complete"] = True
            payload.update({
                "eligible_count": max(0, int(eligible_count)),
                "zero_yield_pages": max(0, int(zero_yield_pages)),
                "enrichment_complete": bool(complete),
                "enrichment_stop_reason": stop_reason if complete else None,
                "search_strategy_version": GENE_SEARCH_STRATEGY_VERSION,
                "search_strategies": states,
                "pagination_complete": all(
                    bool(state.get("complete")) for state in states
                ),
            })
            self._write_cache_payload(cache_path, payload)

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
            expected_query = gene_search_query(gene, phenotype)
            return (
                payload.get("fetch_ok") is True
                and str(payload.get("query") or "").strip() == expected_query
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return False

    def search(
        self,
        query: str,
        limit: int = 5,
        max_retries: int = S2_DEFAULT_MAX_RETRIES,
        timeout: int = 15,
        progress_callback: Optional[Callable[[str], None]] = None,
        offset: int = 0,
        api_key_min_interval_seconds: float | None = None,
    ) -> Optional[List[Dict[str, Any]]]:
        started_at = time.perf_counter()
        used_public_fallback = not bool(self.api_key)
        if used_public_fallback:
            self._maybe_emit_public_fallback_notice(progress_callback)
        request_mode = "API key" if self.api_key else "public endpoint"
        page_label = f", offset {offset}" if offset else ""
        emit_progress(
            progress_callback,
            f'Sending query to Semantic Scholar: "{query}" '
            f'({request_mode}{page_label})',
        )
        data, outcome, status_code, error_text = self._search_request(
            query=query,
            limit=limit,
            max_retries=max_retries,
            timeout=timeout,
            use_api_key=bool(self.api_key),
            offset=offset,
            api_key_min_interval_seconds=api_key_min_interval_seconds,
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
                offset=offset,
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
        query = gene_search_query(gene, phenotype)

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
                cached_query = str(raw.get("query") or "").strip()
                if cached_query != query:
                    logger.info(
                        "[S2] cache query strategy changed for gene=%s phenotype=%s; refreshing with query=%r",
                        gene,
                        phenotype,
                        query,
                    )
                    raise CacheQueryStrategyChanged
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
                    or int(paper.get("gene_identity_policy_version") or 0)
                    != GENE_IDENTITY_POLICY_VERSION
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
                        self._write_cache_payload(cache_path, raw)
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
            except CacheQueryStrategyChanged:
                pass
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
        for paper in papers:
            if isinstance(paper, dict):
                paper.setdefault("search_strategy", "identity")
                paper.setdefault("search_query", query)
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
            "page_size": limit,
            "raw_examined": len(papers),
            "next_offset": len(papers),
            "pagination_complete": False,
            "search_strategy_version": GENE_SEARCH_STRATEGY_VERSION,
            "search_strategies": [
                {
                    "name": strategy["name"],
                    "query": strategy["query"],
                    "fetch_ok": index == 0,
                    "raw_examined": len(papers) if index == 0 else 0,
                    "next_offset": len(papers) if index == 0 else 0,
                    "complete": (len(papers) < limit) if index == 0 else False,
                    "page_size": limit,
                }
                for index, strategy in enumerate(gene_search_strategies(gene, phenotype))
            ],
            "data": papers,
        }
        payload["pagination_complete"] = all(
            bool(strategy.get("complete"))
            for strategy in payload["search_strategies"]
        )

        self._write_cache_payload(cache_path, payload)

        emit_timing(
            progress_callback,
            f'Semantic Scholar retrieval total for "{query}"',
            time.perf_counter() - started_at,
            source="api",
            live=False,
            papers=len(papers),
        )

        return papers

    def fetch_next_cached_page(
        self,
        gene: str,
        *,
        phenotype: str | None = None,
        page_size: int = 10,
        max_raw_results: int = 50,
        progress_callback: Optional[Callable[[str], None]] = None,
        request_timeout: int = 15,
        max_retries: int = S2_DEFAULT_MAX_RETRIES,
        api_key_min_interval_seconds: float | None = None,
    ) -> dict[str, Any]:
        """Fetch and atomically append one relevance-ranked cache page."""
        cache_path = self.cache_path_for_gene(gene, phenotype)
        if cache_path is None:
            return {"ok": False, "reason": "cache_disabled", "new_papers": []}

        with self._cache_lock(cache_path):
            payload = self._read_cache_payload(cache_path)
            if payload.get("fetch_ok") is not True:
                return {"ok": False, "reason": "initial_page_missing", "new_papers": []}
            states = self._strategy_states(
                payload,
                gene,
                phenotype,
                page_size=page_size,
                max_raw_results=max_raw_results,
            )
            active_index = self._active_strategy_index(states)
            if active_index is None:
                return {
                    "ok": True,
                    "reason": "complete",
                    "new_papers": [],
                    "all_papers": self.cached_papers(gene, phenotype),
                    "pagination_complete": True,
                }
            active = states[active_index]
            query = str(active["query"])
            offset = int(active.get("next_offset") or 0)
            remaining = max(0, int(max_raw_results) - offset)
            if remaining <= 0:
                active["complete"] = True
                payload["search_strategies"] = states
                has_next = self._active_strategy_index(states) is not None
                payload["pagination_complete"] = not has_next
                self._write_cache_payload(cache_path, payload)
                return {
                    "ok": True,
                    "reason": "strategy_raw_cap",
                    "new_papers": [],
                    "all_papers": [
                        paper for paper in payload.get("data", [])
                        if isinstance(paper, dict)
                    ],
                    "pagination_complete": not has_next,
                }
            requested = min(max(1, int(page_size)), remaining)
            page = self.search(
                query,
                limit=requested,
                max_retries=max_retries,
                timeout=request_timeout,
                progress_callback=progress_callback,
                offset=offset,
                api_key_min_interval_seconds=api_key_min_interval_seconds,
            )
            if page is None:
                return {
                    "ok": False,
                    "reason": "api_failed",
                    "new_papers": [],
                    "active_search_strategy": active.get("name"),
                    "active_search_query": query,
                }

            if self.metadata_extractor and page:
                self._emit_extraction_progress(
                    query=query,
                    progress_callback=progress_callback,
                )
                page, _ = self.metadata_extractor.enrich_papers(page, seed_gene=gene)

            for paper in page:
                if isinstance(paper, dict):
                    paper.setdefault("search_strategy", active.get("name"))
                    paper.setdefault("search_query", query)

            existing = [
                paper for paper in payload.get("data", []) if isinstance(paper, dict)
            ]
            seen: set[str] = set()
            merged: list[dict[str, Any]] = []
            for paper in existing + list(page):
                paper_id = extract_s2_paper_id(paper)
                identity = paper_id or f"title::{paper.get('title', '')}"
                if identity in seen:
                    continue
                seen.add(identity)
                merged.append(paper)

            strategy_raw_examined = offset + len(page)
            active.update({
                "fetch_ok": True,
                "raw_examined": strategy_raw_examined,
                "next_offset": strategy_raw_examined,
                "complete": len(page) < requested or strategy_raw_examined >= max_raw_results,
                "page_size": page_size,
            })
            active_index_after = self._active_strategy_index(states)
            complete = active_index_after is None
            raw_examined = sum(int(state.get("raw_examined") or 0) for state in states)
            next_offset = (
                int(states[active_index_after].get("next_offset") or 0)
                if active_index_after is not None
                else 0
            )
            payload.update({
                "gene": gene,
                "phenotype": phenotype,
                "query": gene_search_query(gene, phenotype),
                "retrieved_at": datetime.utcnow().isoformat(),
                "fetch_ok": True,
                "result_count": len(merged),
                "page_size": page_size,
                "raw_examined": raw_examined,
                "next_offset": next_offset,
                "pagination_complete": complete,
                "search_strategy_version": GENE_SEARCH_STRATEGY_VERSION,
                "search_strategies": states,
                "enrichment_complete": False,
                "enrichment_stop_reason": None,
                "data": merged,
            })
            self._write_cache_payload(cache_path, payload)
            return {
                "ok": True,
                "reason": "page_fetched",
                "new_papers": list(page),
                "all_papers": merged,
                "raw_examined": raw_examined,
                "next_offset": next_offset,
                "pagination_complete": complete,
                "paper_count": len(merged),
                "active_search_strategy": (
                    states[active_index_after].get("name")
                    if active_index_after is not None
                    else None
                ),
                "search_strategy": active.get("name"),
                "search_query": query,
            }

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
        else:
            # Maintenance/tests may construct the S2 agent without an LLM
            # extractor. Deterministic identity rules still apply, and
            # ambiguous acronym-only matches fail closed.
            papers, _ = ReferenceMetadataExtractor(use_llm=False).enrich_papers(
                papers,
                seed_gene=gene,
            )

        for p in papers:
            paper_id = extract_s2_paper_id(p)
            if not paper_id:
                continue 
            if has_zero_citation_count(p):
                continue

            title = p.get("title", "")
            abstract = p.get("abstract", "")
            url = p.get("url", "")
            external_ids = p.get("externalIds") if isinstance(p.get("externalIds"), dict) else {}
            pmid = str(external_ids.get("PubMed") or "").strip() or None
            pmcid = str(external_ids.get("PubMedCentral") or "").strip() or None
            doi = str(external_ids.get("DOI") or "").strip() or None

            if is_non_article_notice_title(str(title)):
                logger.info("[S2] Skipping non-article notice: %s", title)
                continue

            if not abstract or not str(abstract).strip():
                continue

            text = f"{title}\n\n{abstract}"
            if not paper_gene_identity_is_valid(p, gene):
                continue
            extracted = {
                "genes": parse_metadata_list(p.get("extracted_genes")),
                "phenotypes": parse_metadata_list(p.get("extracted_phenotypes")) or infer_phenotypes_from_text(text),
            }
            extracted_genes = unique_preserving_order(
                [g for g in extracted.get("genes", []) if isinstance(g, str) and g.strip()]
            )
            extracted_phenotypes = unique_preserving_order(
                [p for p in extracted.get("phenotypes", []) if isinstance(p, str) and p.strip()]
            )
            raw_authors = p.get("authors")
            if isinstance(raw_authors, list):
                authors = ", ".join(
                    str(author.get("name") or "").strip()
                    for author in raw_authors
                    if isinstance(author, dict) and str(author.get("name") or "").strip()
                )
            else:
                authors = str(raw_authors or "").strip()

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
                        "publication_id": paper_id,
                        "pmid": pmid,
                        "pmcid": pmcid,
                        "doi": doi,
                        "title": title,
                        "url": url,
                        "journal": extract_journal_name(p),
                        "citationCount": p.get("citationCount"),
                        "year": p.get("year"),
                        "authors": authors,
                        "extracted_genes": ", ".join(extracted_genes) or None,
                        "extracted_phenotypes": ", ".join(extracted_phenotypes) or None,
                        "gene_identity_validated": True,
                        "gene_identity_method": p.get("gene_identity_method") or "validated",
                        "gene_identity_policy_version": GENE_IDENTITY_POLICY_VERSION,
                        "search_strategy": p.get("search_strategy") or "identity",
                        "search_query": p.get("search_query") or gene_search_query(gene, phenotype),
                    },
                }
            )

        return docs

# ============================================================
# 4. Gene Importance Agent
# ============================================================
