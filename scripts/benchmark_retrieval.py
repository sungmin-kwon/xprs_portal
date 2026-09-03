#!/usr/bin/env python3
"""Compare dense, dense+reranker, and hybrid+reranker retrieval.

This is deliberately isolated from the portal's production Chroma and
Semantic Scholar cache directories. It downloads one shared pilot corpus,
embeds it once with BGE-M3, and gives all pipelines the same documents and
vectors.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import requests
from dotenv import load_dotenv
from sentence_transformers import CrossEncoder, SentenceTransformer


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUESTIONS = ROOT / "benchmarks" / "retrieval_questions.json"
S2_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
S2_FIELDS = (
    "paperId,title,year,abstract,url,authors,citationCount,venue,journal,"
    "publicationVenue,openAccessPdf"
)
EMBED_MODEL = "BAAI/bge-m3"
RERANKER_MODEL = "BAAI/bge-reranker-base"
_RERANKER_SNAPSHOT_ENV = os.getenv("RERANKER_SNAPSHOT", "").strip()
RERANKER_SNAPSHOT = (
    Path(_RERANKER_SNAPSHOT_ENV).expanduser().resolve()
    if _RERANKER_SNAPSHOT_ENV
    else None
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--lancedb-path", type=Path, required=True)
    parser.add_argument("--request-interval", type=float, default=1.05)
    return parser.parse_args()


def mentions_gene(text: str, gene: str) -> bool:
    return bool(
        re.search(
            rf"(?<![A-Za-z0-9]){re.escape(gene)}(?![A-Za-z0-9])",
            text or "",
            flags=re.IGNORECASE,
        )
    )


def journal_name(paper: dict[str, Any]) -> str:
    journal = paper.get("journal")
    if isinstance(journal, dict) and journal.get("name"):
        return str(journal["name"])
    if isinstance(journal, str):
        return journal
    venue = paper.get("publicationVenue")
    if isinstance(venue, dict) and venue.get("name"):
        return str(venue["name"])
    return str(paper.get("venue") or "")


class S2Fetcher:
    def __init__(self, api_key: str, interval: float):
        self.api_key = api_key
        self.interval = interval
        self.last_start = 0.0
        self.session = requests.Session()

    def search(self, query: str, limit: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        headers = {"x-api-key": self.api_key}
        params = {"query": query, "limit": limit, "fields": S2_FIELDS}
        started = time.perf_counter()
        attempts = 0
        status = None
        for attempt in range(1, 9):
            attempts = attempt
            delay = self.interval - (time.monotonic() - self.last_start)
            if delay > 0:
                time.sleep(delay)
            self.last_start = time.monotonic()
            response = self.session.get(S2_URL, headers=headers, params=params, timeout=30)
            status = response.status_code
            if status == 200:
                data = response.json().get("data") or []
                return data, {
                    "query": query,
                    "limit": limit,
                    "status": status,
                    "attempts": attempts,
                    "hits": len(data),
                    "elapsed_s": round(time.perf_counter() - started, 3),
                }
            if status == 429:
                try:
                    retry_after = float(response.headers.get("Retry-After", "2"))
                except ValueError:
                    retry_after = 2.0
                time.sleep(max(retry_after, min(60.0, 2.0**attempt)))
                continue
            response.raise_for_status()
        raise RuntimeError(f"Semantic Scholar failed for {query!r}: HTTP {status}")


def build_corpus(
    questions: list[dict[str, Any]], fetcher: S2Fetcher, raw_dir: Path
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    docs: list[dict[str, Any]] = []
    fetch_stats: list[dict[str, Any]] = []
    for gene in dict.fromkeys(q["gene"] for q in questions):
        by_paper: dict[str, dict[str, Any]] = {}
        for pool, phenotype, limit in [
            ("general", None, 50),
            ("phenotype", "breast cancer", 15),
        ]:
            query = f"{gene} {phenotype}".strip() if phenotype else gene
            raw_path = raw_dir / f"{re.sub(r'[^A-Za-z0-9]+', '_', gene)}_{pool}.json"
            if raw_path.exists():
                cached_payload = json.loads(raw_path.read_text(encoding="utf-8"))
                papers = cached_payload.get("data") or []
                stats = {
                    "query": query,
                    "limit": limit,
                    "status": 200,
                    "attempts": 0,
                    "hits": len(papers),
                    "elapsed_s": 0.0,
                    "source": "resume_cache",
                }
            else:
                papers, stats = fetcher.search(query, limit)
                stats["source"] = "api"
            stats.update({"gene": gene, "pool": pool})
            fetch_stats.append(stats)
            if not raw_path.exists():
                raw_path.write_text(
                    json.dumps(
                        {"gene": gene, "pool": pool, "query": query, "data": papers},
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            for paper in papers:
                paper_id = str(paper.get("paperId") or "").strip()
                title = str(paper.get("title") or "").strip()
                abstract = str(paper.get("abstract") or "").strip()
                citation_count = int(paper.get("citationCount") or 0)
                text = f"{title}\n\n{abstract}".strip()
                if not paper_id or not abstract or citation_count <= 0:
                    continue
                if not mentions_gene(text, gene):
                    continue
                existing = by_paper.get(paper_id)
                if existing:
                    pools = set(existing["pools"].split(","))
                    pools.add(pool)
                    existing["pools"] = ",".join(sorted(pools))
                    continue
                by_paper[paper_id] = {
                    "id": f"{gene}::{paper_id}",
                    "paper_id": paper_id,
                    "gene": gene,
                    "pools": pool,
                    "title": title,
                    "abstract": abstract,
                    "text": text,
                    "url": str(paper.get("url") or ""),
                    "journal": journal_name(paper),
                    "year": int(paper.get("year") or 0),
                    "citation_count": citation_count,
                }
        docs.extend(by_paper.values())
    return docs, fetch_stats


def keyword_metrics(text: str, keywords: list[str]) -> tuple[int, float]:
    normalized = text.lower()
    hits = sum(keyword.lower() in normalized for keyword in keywords)
    return hits, hits / max(1, len(keywords))


def rerank(
    reranker: CrossEncoder,
    question: str,
    candidates: list[dict[str, Any]],
    limit: int,
) -> tuple[list[dict[str, Any]], float]:
    if not candidates:
        return [], 0.0
    started = time.perf_counter()
    scores = reranker.predict(
        [[question, row["text"]] for row in candidates],
        batch_size=8,
        show_progress_bar=False,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    rescored = []
    for row, score in zip(candidates, np.asarray(scores).reshape(-1)):
        item = dict(row)
        item["cross_encoder_score"] = float(score)
        rescored.append(item)
    rescored.sort(key=lambda x: x["cross_encoder_score"], reverse=True)
    return rescored[:limit], elapsed_ms


def chroma_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    ids = (result.get("ids") or [[]])[0]
    documents = (result.get("documents") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]
    rows = []
    for doc_id, text, meta, distance in zip(ids, documents, metadatas, distances):
        row = dict(meta or {})
        row.update({"id": doc_id, "text": text, "dense_distance": float(distance)})
        rows.append(row)
    return rows


def public_result(row: dict[str, Any], keywords: list[str]) -> dict[str, Any]:
    hits, fraction = keyword_metrics(row["text"], keywords)
    return {
        "id": row["id"],
        "paper_id": row.get("paper_id"),
        "gene": row.get("gene"),
        "title": row.get("title"),
        "url": row.get("url"),
        "journal": row.get("journal"),
        "year": int(row.get("year") or 0),
        "citation_count": int(row.get("citation_count") or 0),
        "pools": row.get("pools"),
        "dense_distance": row.get("dense_distance"),
        "hybrid_score": row.get("_relevance_score"),
        "cross_encoder_score": row.get("cross_encoder_score"),
        "keyword_hits": hits,
        "keyword_fraction": fraction,
    }


def metric_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ce = [float(row["cross_encoder_score"]) for row in rows]
    keyword_hits = [int(row["keyword_hits"]) for row in rows]
    keyword_fraction = [float(row["keyword_fraction"]) for row in rows]
    return {
        "result_count": len(rows),
        "mean_cross_encoder_score": statistics.fmean(ce) if ce else None,
        "median_cross_encoder_score": statistics.median(ce) if ce else None,
        "keyword_any_rate": statistics.fmean(hit > 0 for hit in keyword_hits) if rows else None,
        "keyword_two_plus_rate": statistics.fmean(hit >= 2 for hit in keyword_hits) if rows else None,
        "mean_keyword_fraction": statistics.fmean(keyword_fraction) if rows else None,
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# XPRS retrieval pipeline pilot",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "## Corpus",
        "",
        f"- Questions: {len(payload['questions'])}",
        f"- Documents: {payload['corpus']['documents']}",
        f"- Genes: {payload['corpus']['genes']}",
        f"- Semantic Scholar requests: {payload['corpus']['s2_requests']}",
        f"- Embedding time: {payload['build_timings_ms']['embedding'] / 1000:.2f}s",
        "",
        "## Aggregate proxy metrics",
        "",
        "Cross-encoder relevance is a shared diagnostic proxy, not independent ground truth. "
        "Use `blinded_review.csv` for a valid human comparison.",
        "",
        "| Pipeline | Mean CE score | Any keyword | 2+ keywords | Mean retrieval ms | Mean rerank ms |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, agg in payload["aggregate"].items():
        lines.append(
            f"| {name} | {agg['mean_cross_encoder_score']:.3f} | "
            f"{agg['keyword_any_rate']:.1%} | {agg['keyword_two_plus_rate']:.1%} | "
            f"{agg['retrieval_ms']:.1f} | {agg['rerank_ms']:.1f} |"
        )
    for question in payload["questions"]:
        lines.extend(["", f"## {question['gene']}: {question['question']}", ""])
        for name, pipe in question["pipelines"].items():
            lines.append(f"### {name}")
            lines.append("")
            for rank, row in enumerate(pipe["results"][:5], 1):
                ce = row.get("cross_encoder_score")
                lines.append(
                    f"{rank}. {row['title']} "
                    f"(CE={ce:.3f}, keywords={row['keyword_hits']}, citations={row['citation_count']})"
                )
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    args = parse_args()
    args.output = args.output.resolve()
    if (args.output / "results.json").exists():
        raise SystemExit(f"Refusing to overwrite completed benchmark: {args.output}")
    args.output.mkdir(parents=True, exist_ok=True)

    sys.path.append(str(args.lancedb_path.resolve()))
    import lancedb  # noqa: PLC0415
    import chromadb  # noqa: PLC0415

    load_dotenv(ROOT / ".env")
    api_key = (os.getenv("S2_API_KEY") or "").strip()
    if not api_key:
        raise SystemExit("S2_API_KEY is required for this benchmark")
    questions = json.loads(args.questions.read_text(encoding="utf-8"))

    print("Fetching shared Semantic Scholar pilot corpus...", flush=True)
    fetcher = S2Fetcher(api_key, args.request_interval)
    docs, fetch_stats = build_corpus(questions, fetcher, args.output / "raw_s2")
    if not docs:
        raise SystemExit("No eligible documents were retrieved")
    (args.output / "corpus.json").write_text(
        json.dumps(docs, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.output / "fetch_stats.json").write_text(
        json.dumps(fetch_stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Eligible documents: {len(docs)}", flush=True)

    print("Loading BGE-M3 and embedding documents...", flush=True)
    embed_started = time.perf_counter()
    embedder = SentenceTransformer(EMBED_MODEL, device="cpu", local_files_only=True)
    vectors = embedder.encode(
        [doc["text"] for doc in docs],
        batch_size=8,
        normalize_embeddings=True,
        show_progress_bar=True,
        convert_to_numpy=True,
    ).astype(np.float32)
    embed_ms = (time.perf_counter() - embed_started) * 1000
    np.save(args.output / "embeddings.npy", vectors)

    print("Building isolated Chroma collection...", flush=True)
    chroma_started = time.perf_counter()
    chroma_client = chromadb.PersistentClient(path=str(args.output / "chroma"))
    chroma = chroma_client.create_collection(
        "retrieval_benchmark", metadata={"hnsw:space": "cosine"}
    )
    chroma.upsert(
        ids=[doc["id"] for doc in docs],
        documents=[doc["text"] for doc in docs],
        embeddings=vectors.tolist(),
        metadatas=[
            {
                "paper_id": doc["paper_id"],
                "gene": doc["gene"],
                "pools": doc["pools"],
                "title": doc["title"],
                "url": doc["url"],
                "journal": doc["journal"],
                "year": doc["year"],
                "citation_count": doc["citation_count"],
            }
            for doc in docs
        ],
    )
    chroma_ms = (time.perf_counter() - chroma_started) * 1000

    print("Building isolated LanceDB vector and FTS indexes...", flush=True)
    lance_started = time.perf_counter()
    lance_db = lancedb.connect(str(args.output / "lancedb"))
    lance_rows = []
    for doc, vector in zip(docs, vectors):
        row = dict(doc)
        row["vector"] = vector.tolist()
        lance_rows.append(row)
    lance = lance_db.create_table("retrieval_benchmark", data=lance_rows)
    lance.create_fts_index("text", replace=True)
    lance_ms = (time.perf_counter() - lance_started) * 1000

    print("Loading cross-encoder reranker...", flush=True)
    reranker_path = (
        RERANKER_SNAPSHOT
        if RERANKER_SNAPSHOT and RERANKER_SNAPSHOT.exists()
        else RERANKER_MODEL
    )
    reranker = CrossEncoder(str(reranker_path), device="cpu", local_files_only=True)
    reranker.predict([["warmup", "warmup"]], show_progress_bar=False)
    embedder.encode(["warmup"], normalize_embeddings=True, show_progress_bar=False)

    docs_by_id = {doc["id"]: doc for doc in docs}
    question_results: list[dict[str, Any]] = []
    blind_rows: list[dict[str, Any]] = []
    blind_seen: set[tuple[str, str]] = set()

    for q in questions:
        print(f"Running pipelines for {q['id']}...", flush=True)
        question = q["question"]
        gene = q["gene"]
        q_embed_started = time.perf_counter()
        q_vector = embedder.encode(
            [question], normalize_embeddings=True, show_progress_bar=False
        )[0].astype(np.float32)
        q_embed_ms = (time.perf_counter() - q_embed_started) * 1000
        gene_count = sum(doc["gene"] == gene for doc in docs)

        dense10_started = time.perf_counter()
        dense10_raw = chroma.query(
            query_embeddings=[q_vector.tolist()],
            n_results=min(10, gene_count),
            where={"gene": gene},
            include=["documents", "metadatas", "distances"],
        )
        dense10_retrieval_ms = (time.perf_counter() - dense10_started) * 1000
        dense10 = chroma_rows(dense10_raw)
        dense10_scored, dense10_eval_ms = rerank(reranker, question, dense10, 10)
        dense10_score_map = {row["id"]: row["cross_encoder_score"] for row in dense10_scored}
        for row in dense10:
            row["cross_encoder_score"] = dense10_score_map[row["id"]]

        dense30_started = time.perf_counter()
        dense30_raw = chroma.query(
            query_embeddings=[q_vector.tolist()],
            n_results=min(30, gene_count),
            where={"gene": gene},
            include=["documents", "metadatas", "distances"],
        )
        dense30_retrieval_ms = (time.perf_counter() - dense30_started) * 1000
        dense30 = chroma_rows(dense30_raw)
        dense_reranked, dense_rerank_ms = rerank(reranker, question, dense30, 10)

        hybrid_started = time.perf_counter()
        hybrid_raw = (
            lance.search(query_type="hybrid")
            .vector(q_vector.tolist())
            .text(question)
            .where(f"gene = '{gene.replace(chr(39), chr(39) * 2)}'", prefilter=True)
            .limit(min(30, gene_count))
            .to_list()
        )
        hybrid_retrieval_ms = (time.perf_counter() - hybrid_started) * 1000
        hybrid_candidates = []
        for row in hybrid_raw:
            item = dict(docs_by_id[row["id"]])
            item["_relevance_score"] = float(row.get("_relevance_score") or 0.0)
            hybrid_candidates.append(item)
        hybrid_reranked, hybrid_rerank_ms = rerank(
            reranker, question, hybrid_candidates, 10
        )

        pipelines = {
            "chroma_dense_10": {
                "retrieval_ms": dense10_retrieval_ms,
                "rerank_ms": 0.0,
                "diagnostic_scoring_ms": dense10_eval_ms,
                "results": [public_result(row, q["keywords"]) for row in dense10],
            },
            "chroma_dense_30_rerank_10": {
                "retrieval_ms": dense30_retrieval_ms,
                "rerank_ms": dense_rerank_ms,
                "results": [public_result(row, q["keywords"]) for row in dense_reranked],
            },
            "lancedb_hybrid_30_rerank_10": {
                "retrieval_ms": hybrid_retrieval_ms,
                "rerank_ms": hybrid_rerank_ms,
                "results": [public_result(row, q["keywords"]) for row in hybrid_reranked],
            },
        }
        for pipe in pipelines.values():
            pipe["metrics"] = metric_summary(pipe["results"])

        question_results.append(
            {
                **q,
                "candidate_documents": gene_count,
                "query_embedding_ms": q_embed_ms,
                "pipelines": pipelines,
            }
        )

        for pipeline_name, pipe in pipelines.items():
            for rank, result in enumerate(pipe["results"], 1):
                key = (q["id"], result["id"])
                if key in blind_seen:
                    continue
                blind_seen.add(key)
                doc = docs_by_id[result["id"]]
                token = hashlib.sha256(f"{q['id']}::{doc['paper_id']}".encode()).hexdigest()[:12]
                blind_rows.append(
                    {
                        "question_id": q["id"],
                        "gene": gene,
                        "question": question,
                        "document_token": token,
                        "title": doc["title"],
                        "abstract": doc["abstract"],
                        "relevance_0_to_3": "",
                        "review_notes": "",
                    }
                )

    aggregate: dict[str, dict[str, float]] = {}
    pipeline_names = list(question_results[0]["pipelines"])
    for name in pipeline_names:
        entries = [q["pipelines"][name] for q in question_results]
        aggregate[name] = {
            "mean_cross_encoder_score": statistics.fmean(
                e["metrics"]["mean_cross_encoder_score"] for e in entries
            ),
            "keyword_any_rate": statistics.fmean(
                e["metrics"]["keyword_any_rate"] for e in entries
            ),
            "keyword_two_plus_rate": statistics.fmean(
                e["metrics"]["keyword_two_plus_rate"] for e in entries
            ),
            "mean_keyword_fraction": statistics.fmean(
                e["metrics"]["mean_keyword_fraction"] for e in entries
            ),
            "retrieval_ms": statistics.fmean(e["retrieval_ms"] for e in entries),
            "rerank_ms": statistics.fmean(e["rerank_ms"] for e in entries),
        }

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "models": {"embedding": EMBED_MODEL, "reranker": RERANKER_MODEL},
        "design": {
            "candidate_text": "title + full abstract",
            "semantic_scholar_queries_per_gene": ["<gene>", "<gene> breast cancer"],
            "paper_filters": ["abstract present", "citationCount > 0", "explicit gene mention"],
            "paper_deduplication": "paperId within gene across pools",
        },
        "corpus": {
            "documents": len(docs),
            "genes": len({doc["gene"] for doc in docs}),
            "per_gene": dict(sorted((gene, len(items)) for gene, items in defaultdict(list, {
                gene: [doc for doc in docs if doc["gene"] == gene]
                for gene in {doc["gene"] for doc in docs}
            }).items())),
            "s2_requests": len(fetch_stats),
            "s2_elapsed_s": sum(row["elapsed_s"] for row in fetch_stats),
        },
        "build_timings_ms": {
            "embedding": embed_ms,
            "chroma": chroma_ms,
            "lancedb_and_fts": lance_ms,
        },
        "aggregate": aggregate,
        "questions": question_results,
    }
    (args.output / "results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.output / "report.md").write_text(render_markdown(payload), encoding="utf-8")
    with (args.output / "blinded_review.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(blind_rows[0]))
        writer.writeheader()
        writer.writerows(sorted(blind_rows, key=lambda row: (row["question_id"], row["document_token"])))
    print(f"Benchmark complete: {args.output}", flush=True)


if __name__ == "__main__":
    main()
