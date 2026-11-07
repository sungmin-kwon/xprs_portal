from __future__ import annotations

import logging
import os
import queue
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator


logger = logging.getLogger(__name__)

S2_ENRICHMENT_PAGE_SIZE = min(
    10,
    max(1, int(os.getenv("S2_ENRICHMENT_PAGE_SIZE", "10"))),
)
# One successful Semantic Scholar fallback request is the complete search for
# a gene/pool. Keep the cap equal to the page size so neither the background
# worker nor the admin page can paginate beyond ten raw papers.
S2_ENRICHMENT_MAX_RAW_RESULTS = S2_ENRICHMENT_PAGE_SIZE
S2_ENRICHMENT_GENERAL_TARGET = max(
    1, int(os.getenv("S2_ENRICHMENT_GENERAL_TARGET", "30"))
)
S2_ENRICHMENT_PRIMARY_TARGET = max(
    1, int(os.getenv("S2_ENRICHMENT_PRIMARY_TARGET", "20"))
)
S2_ENRICHMENT_NAMED_TARGET = max(
    1, int(os.getenv("S2_ENRICHMENT_NAMED_TARGET", "15"))
)
S2_ENRICHMENT_START_DELAY_SECONDS = max(
    0.0, float(os.getenv("S2_ENRICHMENT_START_DELAY_SECONDS", "30"))
)
S2_ENRICHMENT_API_KEY_MIN_INTERVAL_SECONDS = max(
    0.0,
    float(os.getenv("S2_ENRICHMENT_API_KEY_MIN_INTERVAL_SECONDS", "60")),
)


@dataclass(frozen=True)
class EnrichmentJob:
    gene: str
    pool_type: str
    phenotype: str | None
    target_eligible: int
    ready_at: float

    @property
    def key(self) -> tuple[str, str, str]:
        return self.gene, self.pool_type, self.phenotype or ""


class LiteratureEnrichmentQueue:
    """Single background worker for one-shot Semantic Scholar fallbacks."""

    def __init__(self, *, s2_agent: Any, rag_agent: Any):
        self.s2 = s2_agent
        self.rag = rag_agent
        self._jobs: queue.Queue[EnrichmentJob] = queue.Queue()
        self._pending: set[tuple[str, str, str]] = set()
        self._job_details: dict[tuple[str, str, str], EnrichmentJob] = {}
        self._current_job_key: tuple[str, str, str] | None = None
        self._current_job_state: str | None = None
        self._pending_lock = threading.Lock()
        self._activity = threading.Condition()
        self._interactive_retrievals = 0
        self._worker = threading.Thread(
            target=self._run,
            name="s2-literature-enrichment",
            daemon=True,
        )
        self._worker.start()

    @contextmanager
    def interactive_retrieval(self) -> Iterator[None]:
        with self._activity:
            self._interactive_retrievals += 1
        try:
            yield
        finally:
            with self._activity:
                self._interactive_retrievals = max(
                    0, self._interactive_retrievals - 1
                )
                self._activity.notify_all()

    def target_for_pool(self, pool_type: str, phenotype: str | None, primary: str) -> int:
        if pool_type == "general":
            return S2_ENRICHMENT_GENERAL_TARGET
        if phenotype and phenotype.strip().lower() == primary.strip().lower():
            return S2_ENRICHMENT_PRIMARY_TARGET
        return S2_ENRICHMENT_NAMED_TARGET

    def get_status(self) -> dict[str, Any]:
        """Return a non-mutating operational snapshot for the admin viewer."""
        now = time.monotonic()
        with self._pending_lock:
            pending = len(self._pending)
            current_key = self._current_job_key
            jobs: list[dict[str, Any]] = []
            if current_key and current_key in self._job_details:
                jobs.append(self._job_snapshot(
                    self._job_details[current_key],
                    state=self._current_job_state or "active",
                    now=now,
                ))
            for key, job in self._job_details.items():
                if key == current_key:
                    continue
                jobs.append(self._job_snapshot(job, state="queued", now=now))
        with self._activity:
            interactive = self._interactive_retrievals
        return {
            "pending_jobs": pending,
            "queued_jobs": sum(job["state"] == "queued" for job in jobs),
            "jobs": jobs,
            "interactive_retrievals": interactive,
            "worker_alive": self._worker.is_alive(),
            "targets": {
                "general": S2_ENRICHMENT_GENERAL_TARGET,
                "primary_phenotype": S2_ENRICHMENT_PRIMARY_TARGET,
                "named_phenotype": S2_ENRICHMENT_NAMED_TARGET,
                "raw_result_cap": S2_ENRICHMENT_MAX_RAW_RESULTS,
                "api_key_min_interval_seconds": S2_ENRICHMENT_API_KEY_MIN_INTERVAL_SECONDS,
            },
        }

    @staticmethod
    def _job_snapshot(
        job: EnrichmentJob,
        *,
        state: str,
        now: float,
    ) -> dict[str, Any]:
        return {
            "gene": job.gene,
            "pool_type": job.pool_type,
            "phenotype": job.phenotype,
            "query": f"{job.gene} {job.phenotype or ''}".strip(),
            "state": state,
            "ready_in_seconds": max(0, int(job.ready_at - now + 0.999)),
            "target_eligible": job.target_eligible,
        }

    def schedule(
        self,
        *,
        gene: str,
        pool_type: str,
        phenotype: str | None,
        primary_phenotype: str,
    ) -> bool:
        status = self.s2.pagination_status(
            gene,
            phenotype,
            page_size=S2_ENRICHMENT_PAGE_SIZE,
            max_raw_results=S2_ENRICHMENT_MAX_RAW_RESULTS,
        )
        if status.get("pagination_complete") or status.get("enrichment_complete"):
            return False
        target = self.target_for_pool(pool_type, phenotype, primary_phenotype)
        papers = self.s2.cached_papers(gene, phenotype)
        docs = self.s2.papers_to_docs(
            gene,
            papers,
            pool_type=pool_type,
            phenotype=phenotype,
        )
        if len({doc["id"] for doc in docs}) >= target:
            self.s2.record_enrichment_status(
                gene,
                phenotype,
                eligible_count=len({doc["id"] for doc in docs}),
                zero_yield_pages=int(status.get("zero_yield_pages") or 0),
                complete=True,
                stop_reason="eligible_target",
            )
            return False

        job = EnrichmentJob(
            gene=gene,
            pool_type=pool_type,
            phenotype=phenotype,
            target_eligible=target,
            ready_at=time.monotonic() + S2_ENRICHMENT_START_DELAY_SECONDS,
        )
        with self._pending_lock:
            if job.key in self._pending:
                return False
            self._pending.add(job.key)
            self._job_details[job.key] = job
            self._jobs.put(job)
        logger.info(
            "[S2_ENRICH] queued gene=%s pool=%s phenotype=%s target=%d raw=%d initial=%s",
            gene,
            pool_type,
            phenotype,
            target,
            int(status.get("raw_examined") or 0),
            not bool(status.get("fetch_ok")),
        )
        return True

    def _wait_until_available(self, ready_at: float) -> None:
        with self._activity:
            while True:
                remaining = max(0.0, ready_at - time.monotonic())
                if self._interactive_retrievals == 0 and remaining <= 0:
                    return
                timeout = remaining if remaining > 0 else 1.0
                self._activity.wait(timeout=min(timeout, 5.0))

    def _run(self) -> None:
        while True:
            job = self._jobs.get()
            with self._pending_lock:
                self._current_job_key = job.key
                self._current_job_state = "waiting"
            try:
                self._wait_until_available(job.ready_at)
                with self._pending_lock:
                    self._current_job_state = "running"
                self._enrich(job)
            except Exception:
                logger.exception(
                    "[S2_ENRICH] background enrichment failed gene=%s pool=%s phenotype=%s",
                    job.gene,
                    job.pool_type,
                    job.phenotype,
                )
            finally:
                with self._pending_lock:
                    self._pending.discard(job.key)
                    self._job_details.pop(job.key, None)
                    if self._current_job_key == job.key:
                        self._current_job_key = None
                        self._current_job_state = None
                self._jobs.task_done()

    def _enrich(self, job: EnrichmentJob) -> None:
        papers = self.s2.cached_papers(job.gene, job.phenotype)
        docs = self.s2.papers_to_docs(
            job.gene,
            papers,
            pool_type=job.pool_type,
            phenotype=job.phenotype,
        )
        eligible_ids = {doc["id"] for doc in docs}
        status = self.s2.pagination_status(
            job.gene,
            job.phenotype,
            page_size=S2_ENRICHMENT_PAGE_SIZE,
            max_raw_results=S2_ENRICHMENT_MAX_RAW_RESULTS,
        )
        # A chatbot miss reaches the queue before a Semantic Scholar cache
        # exists. Make the one permitted provider request here so answer
        # generation never waits for Semantic Scholar or its cooldown.
        if not status.get("fetch_ok"):
            papers = self.s2.cached_for_gene(
                job.gene,
                limit=S2_ENRICHMENT_PAGE_SIZE,
                phenotype=job.phenotype,
                max_retries=1,
                api_key_min_interval_seconds=S2_ENRICHMENT_API_KEY_MIN_INTERVAL_SECONDS,
            )
            status = self.s2.pagination_status(
                job.gene,
                job.phenotype,
                page_size=S2_ENRICHMENT_PAGE_SIZE,
                max_raw_results=S2_ENRICHMENT_MAX_RAW_RESULTS,
            )
            if not status.get("fetch_ok"):
                logger.warning(
                    "[S2_ENRICH] initial fallback failed gene=%s pool=%s phenotype=%s",
                    job.gene,
                    job.pool_type,
                    job.phenotype,
                )
                return
            docs = self.s2.papers_to_docs(
                job.gene,
                papers,
                pool_type=job.pool_type,
                phenotype=job.phenotype,
            )
            if docs:
                self.rag.upsert_docs(docs)
                eligible_ids.update(doc["id"] for doc in docs)
        stop_reason = (
            "eligible_target"
            if len(eligible_ids) >= job.target_eligible
            else "one_shot_fallback_complete"
        )
        self.s2.record_enrichment_status(
            job.gene,
            job.phenotype,
            eligible_count=len(eligible_ids),
            zero_yield_pages=0 if eligible_ids else 1,
            complete=True,
            stop_reason=stop_reason,
        )

        logger.info(
            "[S2_ENRICH] finished gene=%s pool=%s phenotype=%s eligible=%d target=%d",
            job.gene,
            job.pool_type,
            job.phenotype,
            len(eligible_ids),
            job.target_eligible,
        )
