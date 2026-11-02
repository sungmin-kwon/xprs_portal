from __future__ import annotations

import logging
import os
import re
import threading
import time
from contextlib import contextmanager, nullcontext
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from agents.open_targets import OpenTargetsAgent
from agents.rag import RAGAgent
from agents.europe_pmc import EuropePMCAgent
from agents.literature_enrichment import (
    S2_ENRICHMENT_MAX_RAW_RESULTS,
    S2_ENRICHMENT_PAGE_SIZE,
)
from agents.literature_sources import LiteratureSource
from agents.semantic_scholar import (
    PRIMARY_PHENOTYPE,
    S2_GENERAL_LIMIT,
    SemanticScholarAgent,
)
from config import (
    EUROPE_PMC_GENERAL_LIMIT,
    EUROPE_PMC_NAMED_PHENOTYPE_LIMIT,
    EUROPE_PMC_PRIMARY_LIMIT,
    LITERATURE_MINIMUM_PRIMARY_ELIGIBLE_DOCUMENTS,
    LITERATURE_MINIMUM_INTERACTIVE_ELIGIBLE_DOCUMENTS,
    RERANKER_CANDIDATE_K,
    S2_CACHE_DIR,
    S2_RUNTIME_RATE_LIMIT_COOLDOWN_BASE_SECONDS,
    S2_RUNTIME_RATE_LIMIT_COOLDOWN_MAX_SECONDS,
)
from phenotype_utils import infer_phenotypes_from_text, normalize_phenotype_values
from reference_utils import (
    GENE_IDENTITY_POLICY_VERSION,
    build_reference_hit,
    parse_metadata_list,
    publication_dedup_key,
)
from text_utils import emit_progress, emit_timing, is_cancer_phenotype, unique_preserving_order

logger = logging.getLogger(__name__)

PRIMARY_INTENT = "primary_disease"
OTHER_INTENT = "other_disease"
NEUTRAL_INTENT = "disease_neutral"
VALID_DISEASE_INTENTS = {PRIMARY_INTENT, OTHER_INTENT, NEUTRAL_INTENT}
NAMED_PHENOTYPE_LIMIT = max(1, int(os.getenv("S2_NAMED_PHENOTYPE_LIMIT", "10")))
MINIMUM_INTERACTIVE_ELIGIBLE_DOCUMENTS = (
    LITERATURE_MINIMUM_INTERACTIVE_ELIGIBLE_DOCUMENTS
)

OTHER_DISEASE_PATTERNS = (
    re.compile(r"\bother cancers?\b", re.I),
    re.compile(r"\bother diseases?\b", re.I),
    re.compile(r"\bcancers?\s+other than\b", re.I),
    re.compile(r"(다른|기타).*(암|질환|질병)"),
    re.compile(r"(암|질환|질병).*(외|이외)"),
)
CANCER_ONLY_PATTERNS = (
    re.compile(r"\bother cancers?\b", re.I),
    re.compile(r"\bcancers?\s+other than\b", re.I),
    re.compile(r"(다른|기타).*암"),
    re.compile(r"암.*(외|이외)"),
)


class EvidenceAssemblyAgent:
    """Build disease-aware literature candidates and rerank them with MedCPT."""

    def __init__(
        self,
        rag_agent: RAGAgent,
        ot_agent: OpenTargetsAgent,
        s2_agent: SemanticScholarAgent,
        europe_pmc_agent: EuropePMCAgent | None = None,
        primary_phenotype: str = PRIMARY_PHENOTYPE,
        enrichment_queue: Any | None = None,
    ):
        self.rag = rag_agent
        self.ot = ot_agent
        self.s2 = s2_agent
        self.europe_pmc = europe_pmc_agent
        self.literature_sources: tuple[LiteratureSource, ...] = tuple(
            source for source in (europe_pmc_agent, s2_agent) if source is not None
        )
        self.primary_phenotype = (primary_phenotype or PRIMARY_PHENOTYPE).strip().lower()
        self.enrichment_queue = enrichment_queue
        # Interactive requests share this agent. Serialize uncached S2 fetches so
        # one 429 can open the cooldown before another summary sends more queries.
        self._s2_fetch_lock = threading.Lock()
        self._s2_cooldown_until = 0.0
        self._s2_rate_limit_streak = 0
        self._s2_last_query_label: str | None = None
        self._s2_last_query_at: str | None = None

    def _pool_has_current_documents(self, where: dict[str, Any]) -> bool:
        if not self.rag.has_documents(where):
            return False
        checker = getattr(self.rag, "documents_use_gene_identity_policy", None)
        if checker is None or checker(where, GENE_IDENTITY_POLICY_VERSION):
            return True
        logger.warning(
            "[EVIDENCE_INDEX] Removing a stale literature pool created before gene-identity policy v%s",
            GENE_IDENTITY_POLICY_VERSION,
        )
        deleter = getattr(self.rag, "delete_documents", None)
        if deleter is not None:
            deleter(where)
        return False

    def get_runtime_status(self) -> dict[str, Any]:
        remaining = max(0, int(self._s2_cooldown_until - time.monotonic() + 0.999))
        return {
            "scope": "semantic_scholar_fallback",
            "cooldown_active": remaining > 0,
            "cooldown_remaining_seconds": remaining,
            "cooldown_expires_at": (
                datetime.now(timezone.utc) + timedelta(seconds=remaining)
            ).isoformat() if remaining else None,
            "rate_limit_streak": self._s2_rate_limit_streak,
            "last_query": self._s2_last_query_label,
            "last_attempted_at": self._s2_last_query_at,
        }

    @contextmanager
    def interactive_request_batch(
        self,
        progress_callback: Optional[Callable[[str], None]] = None,
    ):
        """Give one user request priority over background S2 pagination.

        Europe PMC is queried first, so an existing Semantic Scholar cooldown
        must never delay the primary literature request.
        """
        activity = (
            self.enrichment_queue.interactive_retrieval()
            if self.enrichment_queue is not None
            else nullcontext()
        )
        with activity:
            yield

    def _cached_eligible_docs(
        self,
        gene: str,
        *,
        pool_type: str,
        phenotype: str | None,
    ) -> list[dict[str, Any]]:
        docs: list[dict[str, Any]] = []
        for provider in self.literature_sources:
            if not hasattr(provider, "cached_papers"):
                continue
            papers = provider.cached_papers(gene, phenotype)
            docs.extend(provider.papers_to_docs(
                gene,
                papers,
                pool_type=pool_type,
                phenotype=phenotype,
            ))
        return docs

    def _eligible_union_count(self, gene: str) -> int:
        docs = self._cached_eligible_docs(
            gene,
            pool_type="general",
            phenotype=None,
        ) + self._cached_eligible_docs(
            gene,
            pool_type="phenotype",
            phenotype=self.primary_phenotype,
        )
        paper_ids = set()
        for doc in docs:
            meta = doc.get("meta", {})
            identity = (
                f"PMID:{meta.get('pmid')}" if meta.get("pmid") else None
            ) or (
                f"PMCID:{meta.get('pmcid')}" if meta.get("pmcid") else None
            ) or (
                f"DOI:{str(meta.get('doi')).lower()}" if meta.get("doi") else None
            ) or str(meta.get("paperId") or doc.get("id") or "")
            if identity:
                paper_ids.add(identity)
        return len({paper_id for paper_id in paper_ids if paper_id})

    def _pool_eligible_union_count(
        self,
        gene: str,
        *,
        pool_type: str,
        phenotype: str | None,
    ) -> int:
        docs = self._cached_eligible_docs(
            gene,
            pool_type=pool_type,
            phenotype=phenotype,
        )
        identities = {
            publication_dedup_key(doc.get("meta", {}))
            or str(doc.get("id") or "")
            for doc in docs
        }
        return len({identity for identity in identities if identity})

    def _pool_completion_state(
        self,
        gene: str,
        *,
        pool_type: str,
        phenotype: str | None,
    ) -> dict[str, Any]:
        eligible_count = self._pool_eligible_union_count(
            gene,
            pool_type=pool_type,
            phenotype=phenotype,
        )
        s2_cached = self.s2.cached_query_succeeded(gene, phenotype)
        s2_status = (
            self.s2.pagination_status(
                gene,
                phenotype,
                page_size=S2_ENRICHMENT_PAGE_SIZE,
                max_raw_results=S2_ENRICHMENT_MAX_RAW_RESULTS,
            )
            if s2_cached and hasattr(self.s2, "pagination_status")
            else {}
        )
        s2_terminal = bool(
            s2_cached
            and (
                s2_status.get("enrichment_complete")
                or s2_status.get("pagination_complete")
            )
        )
        epmc_terminal = bool(
            self.europe_pmc
            and self.europe_pmc.cached_query_succeeded(gene, phenotype)
        )
        target_reached = (
            eligible_count >= MINIMUM_INTERACTIVE_ELIGIBLE_DOCUMENTS
        )
        all_providers_terminal = s2_terminal and (
            epmc_terminal if self.europe_pmc is not None else True
        )
        return {
            "eligible_count": eligible_count,
            "target_reached": target_reached,
            "all_providers_terminal": all_providers_terminal,
            "complete": target_reached or all_providers_terminal,
            "s2_cached": s2_cached,
            "s2_status": s2_status,
            "s2_terminal": s2_terminal,
            "epmc_terminal": epmc_terminal,
        }

    def _schedule_enrichment(
        self,
        gene: str,
        *,
        pool_type: str,
        phenotype: str | None,
    ) -> bool:
        if self.enrichment_queue is None:
            return False
        return bool(self.enrichment_queue.schedule(
            gene=gene,
            pool_type=pool_type,
            phenotype=phenotype,
            primary_phenotype=self.primary_phenotype,
        ))

    def _general_pool_covers_primary(self, gene: str) -> bool:
        """Whether broad evidence is already sufficient for a disease summary.

        This prevents an unconditional second Europe PMC request when the
        general query already returned both enough usable papers and enough
        papers that explicitly mention the active disease.
        """
        docs = self._cached_eligible_docs(
            gene,
            pool_type="general",
            phenotype=None,
        )
        all_ids: set[str] = set()
        primary_ids: set[str] = set()
        for doc in docs:
            meta = doc.get("meta", {})
            identity = publication_dedup_key(meta) or str(doc.get("id") or "")
            if not identity:
                continue
            all_ids.add(identity)
            phenotypes = normalize_phenotype_values(
                parse_metadata_list(meta.get("extracted_phenotypes"))
            )
            if not phenotypes:
                phenotypes = infer_phenotypes_from_text(doc.get("text") or "")
            if self.primary_phenotype in phenotypes:
                primary_ids.add(identity)
        return (
            len(all_ids) >= MINIMUM_INTERACTIVE_ELIGIBLE_DOCUMENTS
            and len(primary_ids) >= LITERATURE_MINIMUM_PRIMARY_ELIGIBLE_DOCUMENTS
        )

    def _open_runtime_cooldown_if_rate_limited(
        self,
        progress_callback: Optional[Callable[[str], None]],
    ) -> bool:
        if not hasattr(self.s2, "get_health_status"):
            return False
        health = self.s2.get_health_status() or {}
        if health.get("last_status_code") != 429:
            return False
        retry_after = health.get("last_retry_after_seconds")
        self._s2_rate_limit_streak += 1
        exponential_cooldown = min(
            S2_RUNTIME_RATE_LIMIT_COOLDOWN_MAX_SECONDS,
            S2_RUNTIME_RATE_LIMIT_COOLDOWN_BASE_SECONDS
            * (2 ** (self._s2_rate_limit_streak - 1)),
        )
        cooldown = max(float(retry_after or 0), float(exponential_cooldown))
        self._s2_cooldown_until = max(
            self._s2_cooldown_until,
            time.monotonic() + cooldown,
        )
        cooldown_message = (
            "Semantic Scholar rate-limit cooldown opened for "
            f"{int(cooldown)}s (consecutive 429s: {self._s2_rate_limit_streak})"
        )
        logger.warning("[EVIDENCE_INDEX] %s", cooldown_message)
        emit_progress(progress_callback, cooldown_message)
        return True

    @staticmethod
    def _pool_where(gene: str, pool_type: str, phenotype: str | None = None) -> dict[str, Any]:
        clauses: list[dict[str, Any]] = [{"gene": gene}, {"pool_type": pool_type}]
        if phenotype:
            clauses.append({"phenotype": phenotype})
        return {"$and": clauses}

    def _is_broad_other_disease_query(self, question: str) -> bool:
        text = question or ""
        dynamic_primary = re.escape(self.primary_phenotype)
        return (
            any(pattern.search(text) for pattern in OTHER_DISEASE_PATTERNS)
            or bool(re.search(rf"\b(?:beyond|other\s+than)\s+{dynamic_primary}\b", text, re.I))
        )

    def _resolve_disease_intent(
        self,
        question: str,
        requested_phenotypes: list[str] | None,
        disease_intent: str | None,
    ) -> tuple[str, list[str], bool, bool]:
        explicit: list[str] = []
        for phenotype in requested_phenotypes or []:
            canonical = normalize_phenotype_values([phenotype])
            explicit.extend(canonical or [str(phenotype).strip().lower()])
        explicit = [phenotype for phenotype in explicit if phenotype]
        inferred = infer_phenotypes_from_text(question)
        phenotypes = unique_preserving_order(explicit + inferred)
        broad_other = self._is_broad_other_disease_query(question)
        dynamic_primary = re.escape(self.primary_phenotype)
        broad_cancers_only = (
            any(pattern.search(question or "") for pattern in CANCER_ONLY_PATTERNS)
            or bool(
                re.search(
                    rf"\b(?:beyond|other\s+than)\s+{dynamic_primary}\b",
                    question or "",
                    re.I,
                )
            )
        )

        if disease_intent not in VALID_DISEASE_INTENTS:
            if broad_other and not phenotypes:
                disease_intent = OTHER_INTENT
            elif any(p != self.primary_phenotype for p in phenotypes):
                disease_intent = OTHER_INTENT
            elif self.primary_phenotype in phenotypes:
                disease_intent = PRIMARY_INTENT
            else:
                disease_intent = NEUTRAL_INTENT

        if disease_intent == PRIMARY_INTENT:
            targets = [self.primary_phenotype]
        elif disease_intent == OTHER_INTENT:
            non_primary = [p for p in phenotypes if p != self.primary_phenotype]
            targets = non_primary or ([] if broad_other else phenotypes)
        else:
            targets = []
        return disease_intent, targets, broad_other, broad_cancers_only

    def _fetch_semantic_scholar_pool(
        self,
        gene: str,
        *,
        pool_type: str,
        phenotype: str | None,
        limit: int,
        progress_callback: Optional[Callable[[str], None]],
    ) -> bool:
        query_label = f"{gene} {phenotype}".strip() if phenotype else gene
        pool_label = (
            f'{phenotype} query pool'
            if phenotype
            else "general query pool"
        )
        cache_ready_before = self.s2.cached_query_succeeded(gene, phenotype)
        if cache_ready_before:
            message = (
                f'Vector store miss: "{gene}" has no indexed {pool_label}. '
                f'A successful local Semantic Scholar cache exists for "{query_label}"; '
                "it will be indexed without a new upstream request"
            )
        else:
            message = (
                f'Vector store miss: "{gene}" has no indexed {pool_label}. '
                f'No successful local Semantic Scholar cache exists for "{query_label}"'
            )
        logger.info("[EVIDENCE_INDEX] %s", message)
        emit_progress(progress_callback, message)

        with self._s2_fetch_lock:
            # A different request may have populated the cache while this one
            # waited for the serialized fetch slot.
            cache_ready_now = self.s2.cached_query_succeeded(gene, phenotype)
            if not cache_ready_now and self._s2_cooldown_until > time.monotonic():
                remaining = max(1, int(self._s2_cooldown_until - time.monotonic() + 0.999))
                if hasattr(self.s2, "record_query_attempt"):
                    self.s2.record_query_attempt(
                        gene,
                        phenotype,
                        outcome="deferred",
                        detail=f"Runtime rate-limit cooldown active ({remaining}s remaining)",
                    )
                message = (
                    f'No Semantic Scholar request was sent for "{query_label}": '
                    f"rate-limit cooldown active ({remaining}s remaining)"
                )
                logger.warning("[EVIDENCE_INDEX] %s", message)
                emit_progress(progress_callback, message)
                return False

            if not cache_ready_now:
                self._s2_last_query_label = query_label
                self._s2_last_query_at = datetime.now(timezone.utc).isoformat()
            papers = self.s2.cached_for_gene(
                gene,
                limit=limit,
                phenotype=phenotype,
                progress_callback=progress_callback,
            )
            docs = self.s2.papers_to_docs(
                gene,
                papers,
                pool_type=pool_type,
                phenotype=phenotype,
            )
            completed = self.s2.cached_query_succeeded(gene, phenotype)
            if not completed:
                self._open_runtime_cooldown_if_rate_limited(progress_callback)

            # A completed uncached request proves that the upstream endpoint has
            # recovered, so the next future 429 starts again at one minute.
            if completed and not cache_ready_now:
                self._s2_rate_limit_streak = 0
                self._s2_cooldown_until = 0.0

            if docs:
                source = "cached results" if cache_ready_before or cache_ready_now else "newly retrieved results"
                message = (
                    f'Indexing {len(docs)} eligible documents for "{query_label}" '
                    f"from {source}"
                )
                logger.info("[EVIDENCE_INDEX] %s", message)
                emit_progress(progress_callback, message)
                self.rag.upsert_docs(docs)
                return True
            if completed:
                message = (
                    f'No eligible documents were available to index for "{query_label}"; '
                    "the completed Semantic Scholar cache was retained"
                )
                logger.info("[EVIDENCE_INDEX] %s", message)
                emit_progress(progress_callback, message)
                return True

            message = (
                f'Semantic Scholar retrieval did not complete for "{query_label}"; '
                "no documents were added to the vector store"
            )
            logger.warning("[EVIDENCE_INDEX] %s", message)
            emit_progress(progress_callback, message)
            return False

    def _fetch_europe_pmc_pool(
        self,
        gene: str,
        *,
        pool_type: str,
        phenotype: str | None,
        limit: int,
        progress_callback: Optional[Callable[[str], None]],
    ) -> tuple[bool, int]:
        if self.europe_pmc is None:
            return False, 0
        query_label = f"{gene} {phenotype}".strip() if phenotype else gene
        cache_ready = self.europe_pmc.cached_query_succeeded(gene, phenotype)
        if cache_ready:
            emit_progress(
                progress_callback,
                f'A successful local Europe PMC cache exists for "{query_label}"; '
                "it will be indexed without a new upstream request",
            )
        papers = self.europe_pmc.cached_for_gene(
            gene,
            limit=max(limit, 25),
            phenotype=phenotype,
            progress_callback=progress_callback,
        )
        completed = self.europe_pmc.cached_query_succeeded(gene, phenotype)
        docs = self.europe_pmc.papers_to_docs(
            gene,
            papers,
            pool_type=pool_type,
            phenotype=phenotype,
        )
        if docs:
            emit_progress(
                progress_callback,
                f'Indexing {len(docs)} eligible Europe PMC documents for "{query_label}"',
            )
            self.rag.upsert_docs(docs)
            return True, len(docs)
        if completed:
            emit_progress(
                progress_callback,
                f'No eligible Europe PMC documents were available for "{query_label}"',
            )
        return completed, 0

    def _fetch_and_index_pool(
        self,
        gene: str,
        *,
        pool_type: str,
        phenotype: str | None,
        limit: int,
        progress_callback: Optional[Callable[[str], None]],
        allow_semantic_scholar_fallback: bool = True,
        force_semantic_scholar_fallback: bool = False,
    ) -> bool:
        """Fill a pool from Europe PMC, using S2 only as an emergency fallback.

        Automatic retrieval treats any eligible Europe PMC document as usable
        evidence. Semantic Scholar is contacted only when Europe PMC yields no
        eligible document at all. An explicit admin action may force one S2
        page so coverage can still be inspected or extended deliberately.
        """
        europe_pmc_completed, europe_pmc_eligible = self._fetch_europe_pmc_pool(
            gene,
            pool_type=pool_type,
            phenotype=phenotype,
            limit=limit,
            progress_callback=progress_callback,
        )
        if europe_pmc_eligible and not force_semantic_scholar_fallback:
            emit_progress(
                progress_callback,
                f'Europe PMC supplied {europe_pmc_eligible} eligible documents; '
                "the emergency Semantic Scholar fallback is not needed",
            )
            return True

        if not allow_semantic_scholar_fallback and not force_semantic_scholar_fallback:
            if self.s2.cached_query_succeeded(gene, phenotype):
                semantic_scholar_completed = self._fetch_semantic_scholar_pool(
                    gene,
                    pool_type=pool_type,
                    phenotype=phenotype,
                    limit=limit,
                    progress_callback=progress_callback,
                )
                return semantic_scholar_completed or europe_pmc_completed
            emit_progress(
                progress_callback,
                "Semantic Scholar was not queried because automatic disease-pool "
                "augmentation is disabled",
            )
            return europe_pmc_completed

        if europe_pmc_eligible:
            reason = (
                f"Europe PMC supplied {europe_pmc_eligible} eligible document"
                f"{'s' if europe_pmc_eligible != 1 else ''}"
            )
        elif europe_pmc_completed:
            reason = "Europe PMC supplied no eligible documents"
        else:
            reason = "Europe PMC was unavailable"
        emit_progress(
            progress_callback,
            f"{reason}; requesting one Semantic Scholar fallback page",
        )
        semantic_scholar_completed = self._fetch_semantic_scholar_pool(
            gene,
            pool_type=pool_type,
            phenotype=phenotype,
            limit=limit,
            progress_callback=progress_callback,
        )
        return semantic_scholar_completed or europe_pmc_completed

    def manually_index_pool(
        self,
        gene: str,
        *,
        phenotype: str | None = None,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> dict[str, Any]:
        """Populate one missing query pool from cache or a literature provider.

        This is the narrow mutation exposed by the protected retrieval admin
        page. It reuses the interactive Semantic Scholar lock/cooldown and the
        same eligibility/indexing rules for every provider.
        """
        pool_type = "phenotype" if phenotype else "general"
        where = self._pool_where(gene, pool_type, phenotype)
        indexed_before = self._pool_has_current_documents(where)
        completion_before = self._pool_completion_state(
            gene,
            pool_type=pool_type,
            phenotype=phenotype,
        )
        s2_cached_before = completion_before["s2_cached"]
        if indexed_before:
            if completion_before["complete"]:
                return {
                    "ok": True,
                    "status": "already_complete",
                    "scheduled": False,
                    "documents_present": True,
                }

            if not completion_before["s2_cached"]:
                self._fetch_and_index_pool(
                    gene,
                    pool_type=pool_type,
                    phenotype=phenotype,
                    limit=NAMED_PHENOTYPE_LIMIT if phenotype else S2_GENERAL_LIMIT,
                    progress_callback=progress_callback,
                    force_semantic_scholar_fallback=True,
                )

            completion_after_fetch = self._pool_completion_state(
                gene,
                pool_type=pool_type,
                phenotype=phenotype,
            )
            scheduled = False
            if (
                s2_cached_before
                and completion_after_fetch["s2_cached"]
                and not completion_after_fetch["complete"]
                and self.enrichment_queue is not None
            ):
                scheduled = bool(self.enrichment_queue.schedule(
                    gene=gene,
                    pool_type=pool_type,
                    phenotype=phenotype,
                    primary_phenotype=phenotype or self.primary_phenotype,
                ))
            completion_after = self._pool_completion_state(
                gene,
                pool_type=pool_type,
                phenotype=phenotype,
            )
            if scheduled:
                status = "enrichment_queued"
            elif completion_after["complete"]:
                status = "already_complete"
            elif completion_after["s2_cached"] and self.enrichment_queue is not None:
                status = "enrichment_pending"
            else:
                status = "already_indexed"
            return {
                "ok": True,
                "status": status,
                "scheduled": scheduled,
                "documents_present": True,
            }

        completed = self._fetch_and_index_pool(
            gene,
            pool_type=pool_type,
            phenotype=phenotype,
            limit=NAMED_PHENOTYPE_LIMIT if phenotype else S2_GENERAL_LIMIT,
            progress_callback=progress_callback,
            force_semantic_scholar_fallback=True,
        )
        indexed = self._pool_has_current_documents(where)
        completion = self._pool_completion_state(
            gene,
            pool_type=pool_type,
            phenotype=phenotype,
        )
        s2_cached = completion["s2_cached"]
        cached = s2_cached or completion["epmc_terminal"]
        scheduled = False
        if s2_cached_before and s2_cached and not completion["complete"]:
            scheduled = bool(self.enrichment_queue and self.enrichment_queue.schedule(
                gene=gene,
                pool_type=pool_type,
                phenotype=phenotype,
                primary_phenotype=phenotype or self.primary_phenotype,
            ))
        if (
            completed
            and cached
            and s2_cached
            and not indexed
            and not scheduled
            and completion["complete"]
            and hasattr(self.s2, "record_enrichment_status")
        ):
            self.s2.record_enrichment_status(
                gene,
                phenotype,
                eligible_count=0,
                zero_yield_pages=int(
                    completion["s2_status"].get("zero_yield_pages") or 0
                ),
                complete=True,
                stop_reason=(
                    completion["s2_status"].get("enrichment_stop_reason")
                    or "source_exhausted_or_raw_cap"
                ),
            )
        if indexed:
            status = "indexed"
        elif scheduled:
            status = "enrichment_queued"
        elif completed and cached and completion["complete"]:
            status = "no_eligible_documents"
        elif completed and cached:
            status = "enrichment_pending"
        else:
            status = "unavailable"
        return {
            "ok": bool(completed),
            "status": status,
            "scheduled": scheduled,
            "documents_present": indexed,
        }

    def manually_probe_semantic_scholar(self) -> dict[str, Any]:
        """Serialize an admin key check without changing retrieval cooldowns."""
        activity = (
            self.enrichment_queue.interactive_retrieval()
            if self.enrichment_queue is not None
            else nullcontext()
        )
        with activity, self._s2_fetch_lock:
            return self.s2.probe_api_key()

    def _ensure_indexed_for_gene(
        self,
        gene: str,
        general_limit: int = EUROPE_PMC_GENERAL_LIMIT,
        primary_limit: int = EUROPE_PMC_PRIMARY_LIMIT,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        started_at = time.perf_counter()
        S2_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        general_where = self._pool_where(gene, "general")
        primary_where = self._pool_where(gene, "phenotype", self.primary_phenotype)
        general_indexed = self._pool_has_current_documents(general_where)
        primary_indexed = self._pool_has_current_documents(primary_where)

        if general_indexed and primary_indexed:
            message = (
                f'Vector store reuse: "{gene}" has indexed general and '
                f'{self.primary_phenotype} query pools; no upstream literature request '
                "is needed for either pool"
            )
            logger.info("[EVIDENCE_INDEX] %s", message)
            emit_progress(progress_callback, message)
        else:
            if general_indexed:
                message = (
                    f'Vector store reuse: "{gene}" general query pool is indexed; '
                    "no upstream literature request is needed for this pool"
                )
                logger.info("[EVIDENCE_INDEX] %s", message)
                emit_progress(progress_callback, message)
            if primary_indexed:
                message = (
                    f'Vector store reuse: "{gene}" {self.primary_phenotype} query pool '
                    "is indexed; no upstream literature request is needed for this pool"
                )
                logger.info("[EVIDENCE_INDEX] %s", message)
                emit_progress(progress_callback, message)

        # Search the reusable general pool first. Only make a second Europe PMC
        # request when that broad pool does not already contain enough usable,
        # disease-relevant evidence.
        if not general_indexed:
            self._fetch_and_index_pool(
                gene,
                pool_type="general",
                phenotype=None,
                limit=general_limit,
                progress_callback=progress_callback,
                allow_semantic_scholar_fallback=False,
            )
        if not primary_indexed:
            if self._general_pool_covers_primary(gene):
                emit_progress(
                    progress_callback,
                    f'General Europe PMC evidence for "{gene}" already includes '
                    f'sufficient {self.primary_phenotype} coverage; the separate '
                    "disease query was skipped",
                )
            else:
                self._fetch_and_index_pool(
                    gene,
                    pool_type="phenotype",
                    phenotype=self.primary_phenotype,
                    limit=primary_limit,
                    progress_callback=progress_callback,
                    allow_semantic_scholar_fallback=False,
                )

        has_local_literature = (
            self._pool_has_current_documents(general_where)
            or self._pool_has_current_documents(primary_where)
        )
        if not has_local_literature:
            scheduled = self._schedule_enrichment(
                gene,
                pool_type="general",
                phenotype=None,
            )
            message = (
                f'No usable Europe PMC literature was found for "{gene}"; '
                "a Semantic Scholar fallback was queued in the background"
                if scheduled
                else f'No usable Europe PMC literature was found for "{gene}"; '
                "the chatbot will continue without waiting for Semantic Scholar"
            )
            emit_progress(progress_callback, message)

        ot_where = {"$and": [{"gene": gene}, {"source": "opentargets"}]}
        if self.ot is not None and not self.rag.has_documents(ot_where):
            ot_doc = self.ot.doc_for_gene(gene)
            if ot_doc:
                self.rag.upsert_docs([ot_doc])

        emit_timing(
            progress_callback,
            f'Literature index prep for "{gene}"',
            time.perf_counter() - started_at,
        )

    def _ensure_named_phenotype_indexed(
        self,
        gene: str,
        phenotype: str,
        progress_callback: Optional[Callable[[str], None]],
    ) -> None:
        where = self._pool_where(gene, "phenotype", phenotype)
        if self._pool_has_current_documents(where):
            message = (
                f'Vector store reuse: "{gene}" {phenotype} query pool is indexed; '
                "no upstream literature request is needed for this pool"
            )
            logger.info("[EVIDENCE_INDEX] %s", message)
            emit_progress(progress_callback, message)
        else:
            self._fetch_and_index_pool(
                gene,
                pool_type="phenotype",
                phenotype=phenotype,
                limit=EUROPE_PMC_NAMED_PHENOTYPE_LIMIT,
                progress_callback=progress_callback,
                allow_semantic_scholar_fallback=False,
            )
            has_local_literature = (
                self._pool_has_current_documents(where)
                or self._pool_has_current_documents(self._pool_where(gene, "general"))
                or self._pool_has_current_documents(
                    self._pool_where(gene, "phenotype", self.primary_phenotype)
                )
            )
            if not has_local_literature:
                scheduled = self._schedule_enrichment(
                    gene,
                    pool_type="phenotype",
                    phenotype=phenotype,
                )
                message = (
                    f'No usable Europe PMC literature was found for "{gene} {phenotype}"; '
                    "a Semantic Scholar fallback was queued in the background"
                    if scheduled
                    else f'No usable Europe PMC literature was found for "{gene} {phenotype}"; '
                    "the chatbot will continue without waiting for Semantic Scholar"
                )
                emit_progress(progress_callback, message)

    @staticmethod
    def _candidate_identity(text: str, meta: dict[str, Any]) -> tuple[str, str]:
        paper_id = publication_dedup_key(meta)
        if paper_id:
            return "paper", paper_id
        return "text", f"{meta.get('source', '')}::{meta.get('title', '')}::{text[:120]}"

    def _collect_candidates(
        self,
        *,
        gene: str,
        query: str,
        intent: str,
        targets: list[str],
        broad_other: bool,
    ) -> list[tuple[str, dict[str, Any]]]:
        candidate_k = RERANKER_CANDIDATE_K
        plan: list[tuple[dict[str, Any], int]] = []
        if intent == PRIMARY_INTENT:
            plan.extend([
                (self._pool_where(gene, "phenotype", self.primary_phenotype), 20),
                (self._pool_where(gene, "general"), 10),
            ])
        elif intent == OTHER_INTENT and targets:
            target_budget = 15
            per_target = max(5, target_budget // len(targets))
            plan.extend(
                (self._pool_where(gene, "phenotype", phenotype), per_target)
                for phenotype in targets
            )
            plan.extend([
                (self._pool_where(gene, "general"), 10),
                (self._pool_where(gene, "phenotype", self.primary_phenotype), 5),
            ])
        elif intent == OTHER_INTENT and broad_other:
            plan.extend([
                (self._pool_where(gene, "general"), 25),
                (self._pool_where(gene, "phenotype", self.primary_phenotype), 5),
            ])
        else:
            plan.extend([
                (self._pool_where(gene, "general"), 20),
                (self._pool_where(gene, "phenotype", self.primary_phenotype), 10),
            ])

        candidates: list[tuple[str, dict[str, Any]]] = []
        seen: set[tuple[str, str]] = set()

        def add_from_pool(where: dict[str, Any], limit: int) -> None:
            if limit <= 0:
                return
            for text, meta in self.rag.query(query=query, top_k=limit, where=where):
                identity = self._candidate_identity(text, meta)
                if identity in seen:
                    continue
                seen.add(identity)
                candidates.append((text, meta))
                if len(candidates) >= candidate_k:
                    return

        for where, limit in plan:
            add_from_pool(where, min(limit, candidate_k - len(candidates)))
            if len(candidates) >= candidate_k:
                break

        # Sparse phenotype pools should not reduce candidate recall.
        if len(candidates) < candidate_k:
            add_from_pool(self._pool_where(gene, "general"), candidate_k)
        if len(candidates) < candidate_k:
            add_from_pool(
                self._pool_where(gene, "phenotype", self.primary_phenotype),
                candidate_k,
            )
        return candidates[:candidate_k]

    def _disease_match(
        self,
        phenotypes: list[str],
        *,
        intent: str,
        targets: list[str],
        broad_other: bool,
        broad_cancers_only: bool,
    ) -> str:
        phenotype_set = set(phenotypes)
        if intent in {PRIMARY_INTENT, OTHER_INTENT} and targets:
            if phenotype_set.intersection(targets):
                return "direct"
            return "general" if not phenotype_set else "related"
        if intent == OTHER_INTENT and broad_other:
            non_primary = [
                phenotype
                for phenotype in phenotypes
                if phenotype != self.primary_phenotype
                and (not broad_cancers_only or is_cancer_phenotype(phenotype))
            ]
            if non_primary:
                return "direct"
            return "general" if not phenotype_set else "related"
        if not phenotype_set:
            return "general"
        if self.primary_phenotype in phenotype_set:
            return "primary_context"
        return "related"

    @staticmethod
    def _policy_adjustment(intent: str, disease_match: str) -> float:
        if intent in {PRIMARY_INTENT, OTHER_INTENT}:
            if disease_match == "direct":
                return 0.15
            if disease_match == "general":
                return 0.03
            if intent == OTHER_INTENT and disease_match == "related":
                return -0.05
            return 0.0
        if disease_match == "general":
            return 0.05
        if disease_match == "primary_context":
            return 0.02
        return 0.0

    def _rank_candidates(
        self,
        *,
        gene: str,
        query: str,
        candidates: list[tuple[str, dict[str, Any]]],
        intent: str,
        targets: list[str],
        broad_other: bool,
        broad_cancers_only: bool,
        top_k: int,
    ) -> tuple[list[str], list[dict[str, Any]], str]:
        reranked = self.rag.rerank(query, candidates)
        ranked_hits: list[tuple[float, str, dict[str, Any]]] = []
        for text, meta in reranked:
            built = build_reference_hit(text, meta, gene=gene)
            if not built:
                continue
            chunk, ref = built
            phenotypes = list(ref.get("inferred_phenotypes") or [])
            pool_phenotype = str(meta.get("phenotype") or "").strip().lower()
            if pool_phenotype and pool_phenotype in text.lower():
                phenotypes = unique_preserving_order(phenotypes + [pool_phenotype])
            disease_match = self._disease_match(
                phenotypes,
                intent=intent,
                targets=targets,
                broad_other=broad_other,
                broad_cancers_only=broad_cancers_only,
            )
            reranker_score = meta.get("reranker_score")
            if reranker_score is None:
                reranker_score = 1.0 - float(meta.get("dense_distance") or 0.0)
            adjusted_score = float(reranker_score) + self._policy_adjustment(
                intent, disease_match
            )
            ref.update({
                "disease_match": disease_match,
                "source_pool": (
                    f"phenotype:{meta.get('phenotype')}"
                    if meta.get("pool_type") == "phenotype" and meta.get("phenotype")
                    else (meta.get("pool_type") or "general")
                ),
                "reranker_score": round(float(reranker_score), 6),
                "policy_score": round(adjusted_score, 6),
                "target_phenotypes": list(targets),
            })
            ranked_hits.append((adjusted_score, chunk, ref))

        ranked_hits.sort(
            key=lambda item: (
                item[0],
                int(item[2].get("citationCount") or 0),
            ),
            reverse=True,
        )
        selected = ranked_hits[:top_k]
        ranker = "MEDCPT" if any(
            meta.get("reranker_score") is not None for _, meta in reranked
        ) else "DENSE"
        return (
            [chunk for _, chunk, _ in selected],
            [ref for _, _, ref in selected],
            f"RAG_{ranker}_{intent.upper()}",
        )

    def _retrieve(
        self,
        *,
        gene: str,
        question: str,
        intent: str,
        targets: list[str],
        broad_other: bool,
        broad_cancers_only: bool,
        top_k: int,
        progress_callback: Optional[Callable[[str], None]],
    ) -> tuple[list[str], list[dict[str, Any]], str]:
        started_at = time.perf_counter()
        self._ensure_indexed_for_gene(gene, progress_callback=progress_callback)
        for phenotype in targets:
            if phenotype != self.primary_phenotype:
                self._ensure_named_phenotype_indexed(
                    gene, phenotype, progress_callback
                )

        target_text = " ".join(targets)
        query = f"{gene} {question} {target_text}".strip()
        candidates = self._collect_candidates(
            gene=gene,
            query=query,
            intent=intent,
            targets=targets,
            broad_other=broad_other,
        )
        chunks, refs, source = self._rank_candidates(
            gene=gene,
            query=query,
            candidates=candidates,
            intent=intent,
            targets=targets,
            broad_other=broad_other,
            broad_cancers_only=broad_cancers_only,
            top_k=top_k,
        )
        emit_timing(
            progress_callback,
            f'Disease-aware literature retrieval for "{gene}"',
            time.perf_counter() - started_at,
            source=source,
            intent=intent,
            candidates=len(candidates),
            chunks=len(chunks),
        )
        return chunks, refs, source

    def retrieve_gene_context(
        self,
        gene: str,
        top_k: int = 10,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> tuple[list[str], list[dict[str, Any]], str]:
        emit_progress(progress_callback, f'Gathering literature context for "{gene}"')
        context = (
            self.enrichment_queue.interactive_retrieval()
            if self.enrichment_queue is not None
            else nullcontext()
        )
        with context:
            return self._retrieve(
                gene=gene,
                question=f"role, mechanisms, prognosis, and pathways in {self.primary_phenotype}",
                intent=PRIMARY_INTENT,
                targets=[self.primary_phenotype],
                broad_other=False,
                broad_cancers_only=False,
                top_k=top_k,
                progress_callback=progress_callback,
            )

    def retrieve_gene_context_for_question(
        self,
        gene: str,
        question: str,
        top_k: int = 6,
        requested_phenotypes: list[str] | None = None,
        disease_intent: str | None = None,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> tuple[list[str], list[dict[str, Any]], str]:
        emit_progress(progress_callback, f'Retrieving question-specific evidence for "{gene}"')
        intent, targets, broad_other, broad_cancers_only = self._resolve_disease_intent(
            question,
            requested_phenotypes,
            disease_intent,
        )
        context = (
            self.enrichment_queue.interactive_retrieval()
            if self.enrichment_queue is not None
            else nullcontext()
        )
        with context:
            return self._retrieve(
                gene=gene,
                question=question,
                intent=intent,
                targets=targets,
                broad_other=broad_other,
                broad_cancers_only=broad_cancers_only,
                top_k=top_k,
                progress_callback=progress_callback,
            )
