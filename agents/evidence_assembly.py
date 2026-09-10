from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any, Callable, Optional

from agents.open_targets import OpenTargetsAgent
from agents.rag import RAGAgent
from agents.semantic_scholar import (
    PRIMARY_PHENOTYPE,
    S2_GENERAL_LIMIT,
    S2_PRIMARY_LIMIT,
    SemanticScholarAgent,
)
from config import (
    RERANKER_CANDIDATE_K,
    S2_CACHE_DIR,
    S2_RUNTIME_RATE_LIMIT_COOLDOWN_BASE_SECONDS,
    S2_RUNTIME_RATE_LIMIT_COOLDOWN_MAX_SECONDS,
)
from phenotype_utils import infer_phenotypes_from_text, normalize_phenotype_values
from reference_utils import build_reference_hit, extract_s2_paper_id
from text_utils import emit_progress, emit_timing, is_cancer_phenotype, unique_preserving_order

logger = logging.getLogger(__name__)

PRIMARY_INTENT = "primary_disease"
OTHER_INTENT = "other_disease"
NEUTRAL_INTENT = "disease_neutral"
VALID_DISEASE_INTENTS = {PRIMARY_INTENT, OTHER_INTENT, NEUTRAL_INTENT}
NAMED_PHENOTYPE_LIMIT = 15

OTHER_DISEASE_PATTERNS = (
    re.compile(r"\bother cancers?\b", re.I),
    re.compile(r"\bother diseases?\b", re.I),
    re.compile(r"\bbeyond\s+breast\s+cancer\b", re.I),
    re.compile(r"\bother than breast cancer\b", re.I),
    re.compile(r"\bcancers?\s+other than\b", re.I),
    re.compile(r"(다른|기타).*(암|질환|질병)"),
    re.compile(r"(암|질환|질병).*(외|이외)"),
)
CANCER_ONLY_PATTERNS = (
    re.compile(r"\bother cancers?\b", re.I),
    re.compile(r"\bbeyond\s+breast\s+cancer\b", re.I),
    re.compile(r"\bother than breast cancer\b", re.I),
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
    ):
        self.rag = rag_agent
        self.ot = ot_agent
        self.s2 = s2_agent
        # Interactive requests share this agent. Serialize uncached S2 fetches so
        # one 429 can open the cooldown before another summary sends more queries.
        self._s2_fetch_lock = threading.Lock()
        self._s2_cooldown_until = 0.0
        self._s2_rate_limit_streak = 0

    @staticmethod
    def _pool_where(gene: str, pool_type: str, phenotype: str | None = None) -> dict[str, Any]:
        clauses: list[dict[str, Any]] = [{"gene": gene}, {"pool_type": pool_type}]
        if phenotype:
            clauses.append({"phenotype": phenotype})
        return {"$and": clauses}

    @staticmethod
    def _is_broad_other_disease_query(question: str) -> bool:
        return any(pattern.search(question or "") for pattern in OTHER_DISEASE_PATTERNS)

    @staticmethod
    def _resolve_disease_intent(
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
        broad_other = EvidenceAssemblyAgent._is_broad_other_disease_query(question)
        broad_cancers_only = any(pattern.search(question or "") for pattern in CANCER_ONLY_PATTERNS)

        if disease_intent not in VALID_DISEASE_INTENTS:
            if broad_other and not phenotypes:
                disease_intent = OTHER_INTENT
            elif any(p != PRIMARY_PHENOTYPE for p in phenotypes):
                disease_intent = OTHER_INTENT
            elif PRIMARY_PHENOTYPE in phenotypes:
                disease_intent = PRIMARY_INTENT
            else:
                disease_intent = NEUTRAL_INTENT

        if disease_intent == PRIMARY_INTENT:
            targets = [PRIMARY_PHENOTYPE]
        elif disease_intent == OTHER_INTENT:
            non_primary = [p for p in phenotypes if p != PRIMARY_PHENOTYPE]
            targets = non_primary or ([] if broad_other else phenotypes)
        else:
            targets = []
        return disease_intent, targets, broad_other, broad_cancers_only

    def _fetch_and_index_pool(
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
                f'Vector store: "{gene}" is missing its {pool_label}; '
                f'loading cached Semantic Scholar results for "{query_label}"'
            )
        else:
            message = (
                f'Vector store: "{gene}" is missing its {pool_label}; '
                "a Semantic Scholar query is required"
            )
        logger.info("[EVIDENCE_INDEX] %s", message)
        emit_progress(progress_callback, message)

        with self._s2_fetch_lock:
            # A different request may have populated the cache while this one
            # waited for the serialized fetch slot.
            cache_ready_now = self.s2.cached_query_succeeded(gene, phenotype)
            if not cache_ready_now and self._s2_cooldown_until > time.monotonic():
                remaining = max(1, int(self._s2_cooldown_until - time.monotonic() + 0.999))
                message = (
                    f'Semantic Scholar query skipped for "{query_label}": '
                    f"rate-limit cooldown active ({remaining}s remaining)"
                )
                logger.warning("[EVIDENCE_INDEX] %s", message)
                emit_progress(progress_callback, message)
                return False

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
            if not completed and hasattr(self.s2, "get_health_status"):
                health = self.s2.get_health_status() or {}
                if health.get("last_status_code") == 429:
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

    def _ensure_indexed_for_gene(
        self,
        gene: str,
        general_limit: int = S2_GENERAL_LIMIT,
        primary_limit: int = S2_PRIMARY_LIMIT,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        started_at = time.perf_counter()
        S2_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        general_where = self._pool_where(gene, "general")
        primary_where = self._pool_where(gene, "phenotype", PRIMARY_PHENOTYPE)
        general_indexed = self.rag.has_documents(general_where)
        primary_indexed = self.rag.has_documents(primary_where)

        if general_indexed and primary_indexed:
            message = (
                f'Vector store: "{gene}" is indexed '
                f"(general query and {PRIMARY_PHENOTYPE} query pools)"
            )
            logger.info("[EVIDENCE_INDEX] %s", message)
            emit_progress(progress_callback, message)
        else:
            if general_indexed:
                message = f'Vector store: "{gene}" general query pool is indexed'
                logger.info("[EVIDENCE_INDEX] %s", message)
                emit_progress(progress_callback, message)
            if primary_indexed:
                message = (
                    f'Vector store: "{gene}" {PRIMARY_PHENOTYPE} query pool is indexed'
                )
                logger.info("[EVIDENCE_INDEX] %s", message)
                emit_progress(progress_callback, message)

        general_available = general_indexed
        if not general_indexed:
            general_available = self._fetch_and_index_pool(
                gene,
                pool_type="general",
                phenotype=None,
                limit=general_limit,
                progress_callback=progress_callback,
            )
        if not primary_indexed and general_available:
            self._fetch_and_index_pool(
                gene,
                pool_type="phenotype",
                phenotype=PRIMARY_PHENOTYPE,
                limit=primary_limit,
                progress_callback=progress_callback,
            )
        elif not primary_indexed:
            message = (
                f'Skipping the {PRIMARY_PHENOTYPE} query for "{gene}" because '
                "the general Semantic Scholar query did not complete"
            )
            logger.warning("[EVIDENCE_INDEX] %s", message)
            emit_progress(progress_callback, message)

        ot_where = {"$and": [{"gene": gene}, {"source": "opentargets"}]}
        if not self.rag.has_documents(ot_where):
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
        if self.rag.has_documents(where):
            message = f'Vector store: "{gene}" {phenotype} query pool is indexed'
            logger.info("[EVIDENCE_INDEX] %s", message)
            emit_progress(progress_callback, message)
        else:
            self._fetch_and_index_pool(
                gene,
                pool_type="phenotype",
                phenotype=phenotype,
                limit=NAMED_PHENOTYPE_LIMIT,
                progress_callback=progress_callback,
            )

    @staticmethod
    def _candidate_identity(text: str, meta: dict[str, Any]) -> tuple[str, str]:
        paper_id = extract_s2_paper_id(meta)
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
                (self._pool_where(gene, "phenotype", PRIMARY_PHENOTYPE), 20),
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
                (self._pool_where(gene, "phenotype", PRIMARY_PHENOTYPE), 5),
            ])
        elif intent == OTHER_INTENT and broad_other:
            plan.extend([
                (self._pool_where(gene, "general"), 25),
                (self._pool_where(gene, "phenotype", PRIMARY_PHENOTYPE), 5),
            ])
        else:
            plan.extend([
                (self._pool_where(gene, "general"), 20),
                (self._pool_where(gene, "phenotype", PRIMARY_PHENOTYPE), 10),
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
                self._pool_where(gene, "phenotype", PRIMARY_PHENOTYPE),
                candidate_k,
            )
        return candidates[:candidate_k]

    @staticmethod
    def _disease_match(
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
                if phenotype != PRIMARY_PHENOTYPE
                and (not broad_cancers_only or is_cancer_phenotype(phenotype))
            ]
            if non_primary:
                return "direct"
            return "general" if not phenotype_set else "related"
        if not phenotype_set:
            return "general"
        if PRIMARY_PHENOTYPE in phenotype_set:
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
            if phenotype != PRIMARY_PHENOTYPE:
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
        return self._retrieve(
            gene=gene,
            question="role, mechanisms, prognosis, and pathways in breast cancer",
            intent=PRIMARY_INTENT,
            targets=[PRIMARY_PHENOTYPE],
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
