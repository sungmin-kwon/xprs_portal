from __future__ import annotations

import fcntl
import logging
import threading
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

EMB_MODEL_NAME = "BAAI/bge-m3"
CHROMA_COLLECTION = "xprs_pmc_lit"
logger = logging.getLogger(__name__)


def acquire_chroma_process_lock(chroma_dir: str):
    """Hold an exclusive advisory lock for an embedded Chroma directory."""
    chroma_path = Path(chroma_dir)
    chroma_path.mkdir(parents=True, exist_ok=True)
    lock_path = chroma_path / ".xprs_process.lock"
    handle = lock_path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise RuntimeError(
            f"Chroma store is already open by another XPRS process: {chroma_path}"
        ) from exc
    return handle


class RAGAgent:
    def __init__(
        self,
        emb_model_name: str,
        chroma_dir: str,
        collection_name: str,
        *,
        reranker_model_name: str | None = None,
        reranker_enabled: bool = True,
        reranker_batch_size: int = 8,
        reranker_max_length: int = 512,
    ):
        from chromadb import Client
        from chromadb.config import Settings
        from sentence_transformers import SentenceTransformer

        logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)
        # Embedded Chroma is a single-process store. Hold an advisory lock for
        # this agent's lifetime so a maintenance sweep cannot write the same
        # database while the web server is running (or vice versa).
        self._store_lock_handle = acquire_chroma_process_lock(chroma_dir)
        self._emb_model = SentenceTransformer(emb_model_name)
        self._chroma = Client(
            Settings(
                is_persistent=True,
                persist_directory=chroma_dir,
                anonymized_telemetry=False,
            )
        )
        self._collection = self._chroma.get_or_create_collection(name=collection_name)
        self._reranker_model_name = reranker_model_name
        self._reranker_enabled = bool(reranker_enabled and reranker_model_name)
        self._reranker_batch_size = reranker_batch_size
        self._reranker_max_length = reranker_max_length
        self._reranker = None
        self._reranker_error: str | None = None
        self._reranker_lock = threading.Lock()

    def embed(self, texts: List[str]) -> List[List[float]]:
        return self._emb_model.encode(texts, normalize_embeddings=True).tolist()

    def upsert_docs(self, docs: List[Dict[str, Any]]) -> None:
        if not docs:
            return
        ids = [d["id"] for d in docs]
        texts = [d["text"] for d in docs]
        metas = [d.get("meta", {}) for d in docs]
        embs = self.embed(texts)
        self._collection.upsert(
            ids=ids,
            embeddings=embs,
            documents=texts,
            metadatas=metas,
        )

    def gene_is_indexed(self, gene: str) -> bool:
        existing = self._collection.get(
            where={"gene": gene},
            limit=1,
            include=[],
        )
        return len(existing["ids"]) > 0

    def has_documents(self, where: Dict[str, Any]) -> bool:
        existing = self._collection.get(where=where, limit=1, include=[])
        return len(existing["ids"]) > 0

    @staticmethod
    def _admin_pool_label(metadata: Dict[str, Any]) -> str:
        """Return the display/filter pool for a stored document."""
        pool_type = str(metadata.get("pool_type") or "").strip().lower()
        if pool_type:
            return pool_type
        if str(metadata.get("source") or "").strip().lower() == "opentargets":
            return "opentargets"
        return "other"

    @staticmethod
    def _citation_value(metadata: Dict[str, Any]) -> int | None:
        value = metadata.get("citationCount")
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def document_inventory(self) -> Dict[str, Any]:
        """Summarize the read-only literature index for the admin browser.

        Embeddings are intentionally excluded. Only document metadata is read.
        """
        result = self._collection.get(include=["metadatas"])
        metadata_rows = result.get("metadatas") or []
        genes: dict[str, Counter[str]] = {}
        gene_phenotypes: dict[str, Counter[str]] = {}
        pool_totals: Counter[str] = Counter()
        phenotype_totals: Counter[str] = Counter()

        for raw_metadata in metadata_rows:
            metadata = dict(raw_metadata or {})
            gene = str(metadata.get("gene") or "").strip()
            if not gene:
                continue
            pool = self._admin_pool_label(metadata)
            genes.setdefault(gene, Counter())[pool] += 1
            pool_totals[pool] += 1
            query_phenotype = str(metadata.get("phenotype") or "").strip()
            if pool == "phenotype" and query_phenotype:
                gene_phenotypes.setdefault(gene, Counter())[query_phenotype] += 1
                phenotype_totals[query_phenotype] += 1

        gene_rows = []
        for gene in sorted(genes, key=str.casefold):
            counts = genes[gene]
            gene_rows.append(
                {
                    "gene": gene,
                    "total": sum(counts.values()),
                    "pools": dict(sorted(counts.items())),
                    "phenotypes": dict(sorted(gene_phenotypes.get(gene, {}).items())),
                }
            )

        return {
            "document_count": sum(pool_totals.values()),
            "gene_count": len(gene_rows),
            "pools": dict(sorted(pool_totals.items())),
            "phenotypes": dict(sorted(phenotype_totals.items())),
            "genes": gene_rows,
        }

    def browse_documents(
        self,
        *,
        gene: str,
        pool: str = "all",
        phenotype: str = "",
        search: str = "",
        sort: str = "citations_desc",
        offset: int = 0,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """Return a paginated, metadata-only view of documents for one gene."""
        result = self._collection.get(
            where={"gene": gene},
            include=["documents", "metadatas"],
        )
        ids = result.get("ids") or []
        documents = result.get("documents") or []
        metadata_rows = result.get("metadatas") or []
        needle = search.strip().casefold()
        items: list[dict[str, Any]] = []

        for document_id, document, raw_metadata in zip(ids, documents, metadata_rows):
            metadata = dict(raw_metadata or {})
            display_pool = self._admin_pool_label(metadata)
            if pool != "all" and display_pool != pool:
                continue
            query_phenotype = str(metadata.get("phenotype") or "").strip()
            if phenotype and query_phenotype.casefold() != phenotype.strip().casefold():
                continue

            title = str(metadata.get("title") or "").strip()
            text = str(document or "")
            paper_id = str(metadata.get("paperId") or "").strip()
            if needle and needle not in "\n".join((title, text, paper_id)).casefold():
                continue

            items.append(
                {
                    "id": str(document_id),
                    "gene": str(metadata.get("gene") or gene),
                    "pool": display_pool,
                    "source": str(metadata.get("source") or ""),
                    "phenotype": metadata.get("phenotype"),
                    "paper_id": paper_id or None,
                    "title": title or "Untitled document",
                    "url": metadata.get("url"),
                    "journal": metadata.get("journal"),
                    "citation_count": self._citation_value(metadata),
                    "extracted_genes": metadata.get("extracted_genes"),
                    "extracted_phenotypes": metadata.get("extracted_phenotypes"),
                    "document": text,
                }
            )

        if sort == "title":
            items.sort(key=lambda item: (item["title"].casefold(), item["id"]))
        elif sort == "pool":
            items.sort(
                key=lambda item: (
                    item["pool"],
                    item["title"].casefold(),
                    item["id"],
                )
            )
        else:
            items.sort(
                key=lambda item: (
                    -(item["citation_count"] if item["citation_count"] is not None else -1),
                    item["title"].casefold(),
                    item["id"],
                )
            )

        total = len(items)
        start = max(0, offset)
        page_size = max(1, limit)
        return {
            "gene": gene,
            "pool": pool,
            "phenotype": phenotype,
            "search": search,
            "sort": sort,
            "total": total,
            "offset": start,
            "limit": page_size,
            "documents": items[start : start + page_size],
        }

    def query(
        self,
        query: str,
        top_k: int = 5,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[Tuple[str, Dict[str, Any]]]:
        q_emb = self.embed([query])[0]
        res = self._collection.query(
            query_embeddings=[q_emb],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        distances = res.get("distances", [[]])[0]
        out: List[Tuple[str, Dict[str, Any]]] = []
        for text, meta, distance in zip(docs, metas, distances):
            enriched = dict(meta or {})
            enriched["dense_distance"] = float(distance)
            out.append((text, enriched))
        return out

    def _load_reranker(self):
        if self._reranker is not None or not self._reranker_enabled:
            return self._reranker
        from sentence_transformers import CrossEncoder

        logger.info("[RAG] Loading reranker %s", self._reranker_model_name)
        self._reranker = CrossEncoder(
            self._reranker_model_name,
            device="cpu",
            max_length=self._reranker_max_length,
        )
        return self._reranker

    def rerank(
        self,
        query: str,
        candidates: List[Tuple[str, Dict[str, Any]]],
        top_k: int | None = None,
    ) -> List[Tuple[str, Dict[str, Any]]]:
        if not candidates:
            return []
        if not self._reranker_enabled:
            return candidates[:top_k] if top_k is not None else candidates

        try:
            # Summary workers share this CPU model. Serial inference prevents
            # thread oversubscription and keeps request latency predictable.
            with self._reranker_lock:
                reranker = self._load_reranker()
                scores = reranker.predict(
                    [[query, text] for text, _ in candidates],
                    batch_size=self._reranker_batch_size,
                    show_progress_bar=False,
                    convert_to_numpy=True,
                )
                if hasattr(scores, "reshape"):
                    scores = scores.reshape(-1)
            rescored: List[Tuple[str, Dict[str, Any]]] = []
            for (text, meta), score in zip(candidates, scores):
                enriched = dict(meta or {})
                enriched["reranker_score"] = float(score)
                rescored.append((text, enriched))
            rescored.sort(
                key=lambda item: item[1].get("reranker_score", float("-inf")),
                reverse=True,
            )
            return rescored[:top_k] if top_k is not None else rescored
        except Exception as exc:
            self._reranker_error = str(exc)
            logger.exception("[RAG] Reranking failed; preserving dense order")
            return candidates[:top_k] if top_k is not None else candidates

    def reranker_status(self) -> Dict[str, Any]:
        return {
            "enabled": self._reranker_enabled,
            "model": self._reranker_model_name,
            "loaded": self._reranker is not None,
            "error": self._reranker_error,
        }
