#!/usr/bin/env python3
"""Compare rerankers on one fixed, locally cached biomedical corpus.

The script reads the isolated retrieval pilot artifacts. It never reads or
writes the portal's production Chroma collection or Semantic Scholar cache.
All models rerank the same BGE-M3 dense top-30 candidates for each question.
"""

from __future__ import annotations

import argparse
import csv
import gc
import hashlib
import json
import math
import os
import re
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import torch
from sentence_transformers import CrossEncoder, SentenceTransformer
from transformers import AutoModelForCausalLM, AutoTokenizer


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "benchmarks" / "retrieval_pilot_20260831"
DEFAULT_QUESTIONS = ROOT / "benchmarks" / "reranker_questions.json"
EMBED_MODEL = "BAAI/bge-m3"
TOP_CANDIDATES = 30
TOP_RESULTS = 10
QWEN_INSTRUCTION = (
    "Rank biomedical literature for answering the query. Prefer evidence about "
    "the disease explicitly named in the query, while retaining mechanistically "
    "relevant evidence from other diseases when direct evidence is sparse."
)

MODELS = {
    "bge_base_control": {
        "model_id": "BAAI/bge-reranker-base",
        "kind": "cross_encoder",
        "batch_size": 8,
    },
    "medcpt": {
        "model_id": "ncbi/MedCPT-Cross-Encoder",
        "kind": "cross_encoder",
        "batch_size": 8,
    },
    "bge_v2_m3": {
        "model_id": "BAAI/bge-reranker-v2-m3",
        "kind": "cross_encoder",
        "batch_size": 4,
    },
    "qwen3_0_6b": {
        "model_id": "Qwen/Qwen3-Reranker-0.6B",
        "kind": "qwen",
        "batch_size": 4,
    },
}


class Reranker(Protocol):
    def predict(self, pairs: list[list[str]], batch_size: int) -> np.ndarray: ...


class CrossEncoderReranker:
    def __init__(self, model_path: str):
        self.model = CrossEncoder(
            model_path,
            device="cpu",
            local_files_only=True,
            max_length=512,
        )

    def predict(self, pairs: list[list[str]], batch_size: int) -> np.ndarray:
        return np.asarray(
            self.model.predict(
                pairs,
                batch_size=batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
        ).reshape(-1)


class QwenReranker:
    """Qwen3 yes/no relevance scorer following the official model card."""

    def __init__(self, model_path: str, max_length: int = 2048):
        self.max_length = max_length
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_path, local_files_only=True, padding_side="left"
        )
        self.model = AutoModelForCausalLM.from_pretrained(
            model_path,
            local_files_only=True,
            torch_dtype=torch.float32,
            low_cpu_mem_usage=True,
        ).eval()
        self.false_id = self.tokenizer.convert_tokens_to_ids("no")
        self.true_id = self.tokenizer.convert_tokens_to_ids("yes")
        prefix = (
            "<|im_start|>system\nJudge whether the Document meets the requirements "
            "based on the Query and the Instruct provided. Note that the answer can "
            "only be \"yes\" or \"no\".<|im_end|>\n<|im_start|>user\n"
        )
        suffix = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
        self.prefix_tokens = self.tokenizer.encode(prefix, add_special_tokens=False)
        self.suffix_tokens = self.tokenizer.encode(suffix, add_special_tokens=False)

    def _encode(self, pairs: list[list[str]]) -> dict[str, torch.Tensor]:
        formatted = [
            f"<Instruct>: {QWEN_INSTRUCTION}\n<Query>: {query}\n<Document>: {document}"
            for query, document in pairs
        ]
        budget = self.max_length - len(self.prefix_tokens) - len(self.suffix_tokens)
        encoded = self.tokenizer(
            formatted,
            padding=False,
            truncation=True,
            max_length=budget,
            add_special_tokens=False,
        )
        encoded["input_ids"] = [
            self.prefix_tokens + ids + self.suffix_tokens for ids in encoded["input_ids"]
        ]
        encoded["attention_mask"] = [
            [1] * len(ids) for ids in encoded["input_ids"]
        ]
        return self.tokenizer.pad(encoded, padding=True, return_tensors="pt")

    def predict(self, pairs: list[list[str]], batch_size: int) -> np.ndarray:
        scores: list[float] = []
        with torch.inference_mode():
            for start in range(0, len(pairs), batch_size):
                encoded = self._encode(pairs[start : start + batch_size])
                logits = self.model(**encoded).logits[:, -1, :]
                binary = torch.stack(
                    [logits[:, self.false_id], logits[:, self.true_id]], dim=1
                )
                scores.extend(torch.softmax(binary.float(), dim=1)[:, 1].tolist())
        return np.asarray(scores, dtype=np.float32)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--models",
        nargs="+",
        choices=sorted(MODELS),
        default=list(MODELS),
    )
    parser.add_argument("--threads", type=int, default=32)
    parser.add_argument(
        "--finalize-only",
        action="store_true",
        help="Rebuild metrics and reports from checkpointed model results.",
    )
    return parser.parse_args()


def snapshot_path(model_id: str) -> str:
    cache_root = Path(os.getenv("HF_HOME", Path.home() / ".cache" / "huggingface"))
    model_dir = cache_root / "hub" / f"models--{model_id.replace('/', '--')}" / "snapshots"
    snapshots = sorted(
        (path for path in model_dir.glob("*") if (path / "config.json").exists()),
        key=lambda path: path.stat().st_mtime,
    )
    if not snapshots:
        raise FileNotFoundError(
            f"Model is not cached: {model_id}. Download it before running this benchmark."
        )
    return str(snapshots[-1])


def term_match(text: str, terms: list[str]) -> bool:
    normalized = re.sub(r"\s+", " ", text.lower())
    return any(term.lower() in normalized for term in terms)


def keyword_hits(text: str, keywords: list[str]) -> int:
    normalized = text.lower()
    return sum(keyword.lower() in normalized for keyword in keywords)


def dcg(labels: list[int]) -> float:
    return sum(label / math.log2(rank + 1) for rank, label in enumerate(labels, 1))


def ranking_metrics(
    rows: list[dict[str, Any]], total_target_matches: int | None = None
) -> dict[str, Any]:
    labels = [int(row["target_text_match"]) for row in rows]
    relevant = sum(labels) if total_target_matches is None else total_target_matches
    ideal = [1] * relevant
    first = next((rank for rank, label in enumerate(labels, 1) if label), None)
    return {
        "target_at_1": bool(labels and labels[0]),
        "target_count_at_3": sum(labels[:3]),
        "target_count_at_10": sum(labels[:10]),
        "target_title_count_at_3": sum(int(row["target_title_match"]) for row in rows[:3]),
        "target_title_count_at_10": sum(int(row["target_title_match"]) for row in rows[:10]),
        "target_mrr": 1.0 / first if first else 0.0,
        "target_ndcg_at_10": dcg(labels[:10]) / dcg(ideal[:10]) if ideal else 0.0,
        "keyword_any_count_at_10": sum(row["keyword_hits"] > 0 for row in rows[:10]),
        "keyword_two_plus_count_at_10": sum(row["keyword_hits"] >= 2 for row in rows[:10]),
        "phenotype_pool_count_at_10": sum(
            "phenotype" in str(row.get("pools", "")) for row in rows[:10]
        ),
    }


def build_candidates(
    source: Path,
    questions: list[dict[str, Any]],
    candidate_path: Path,
) -> dict[str, list[dict[str, Any]]]:
    if candidate_path.exists():
        return json.loads(candidate_path.read_text(encoding="utf-8"))
    docs = json.loads((source / "corpus.json").read_text(encoding="utf-8"))
    vectors = np.load(source / "embeddings.npy")
    if len(docs) != len(vectors):
        raise ValueError("Corpus and embedding counts differ")
    print("Loading BGE-M3 to construct fixed dense top-30 candidates...", flush=True)
    embedder = SentenceTransformer(
        snapshot_path(EMBED_MODEL), device="cpu", local_files_only=True
    )
    query_vectors = embedder.encode(
        [q["question"] for q in questions],
        batch_size=8,
        normalize_embeddings=True,
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    output: dict[str, list[dict[str, Any]]] = {}
    for question, query_vector in zip(questions, query_vectors):
        indices = [i for i, doc in enumerate(docs) if doc["gene"] == question["gene"]]
        scored = sorted(
            ((float(np.dot(query_vector, vectors[i])), i) for i in indices),
            reverse=True,
        )[:TOP_CANDIDATES]
        output[question["id"]] = [
            {**docs[i], "dense_score": score} for score, i in scored
        ]
    candidate_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    del embedder
    gc.collect()
    return output


def load_reranker(name: str) -> Reranker:
    config = MODELS[name]
    path = snapshot_path(config["model_id"])
    if config["kind"] == "qwen":
        return QwenReranker(path)
    return CrossEncoderReranker(path)


def evaluate_model(
    name: str,
    questions: list[dict[str, Any]],
    candidates: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    config = MODELS[name]
    print(f"Loading {name} ({config['model_id']})...", flush=True)
    load_started = time.perf_counter()
    reranker = load_reranker(name)
    load_ms = (time.perf_counter() - load_started) * 1000
    reranker.predict([["warmup", "warmup"]], batch_size=1)
    results = []
    for index, question in enumerate(questions, 1):
        rows = candidates[question["id"]]
        pairs = [[question["question"], row["text"]] for row in rows]
        started = time.perf_counter()
        scores = reranker.predict(pairs, batch_size=int(config["batch_size"]))
        elapsed_ms = (time.perf_counter() - started) * 1000
        ranked = []
        for row, score in zip(rows, scores):
            item = dict(row)
            item["reranker_score"] = float(score)
            item["target_title_match"] = term_match(item["title"], question["target_terms"])
            item["target_text_match"] = term_match(item["text"], question["target_terms"])
            item["keyword_hits"] = keyword_hits(item["text"], question["keywords"])
            ranked.append(item)
        ranked.sort(key=lambda row: row["reranker_score"], reverse=True)
        top_rows = ranked[:TOP_RESULTS]
        results.append(
            {
                **question,
                "candidate_count": len(rows),
                "rerank_ms": elapsed_ms,
                "metrics": ranking_metrics(ranked),
                "results": [
                    {
                        key: row[key]
                        for key in [
                            "id", "paper_id", "title", "abstract", "url", "journal",
                            "year", "citation_count", "pools", "dense_score",
                            "reranker_score", "target_title_match", "target_text_match",
                            "keyword_hits",
                        ]
                    }
                    for row in top_rows
                ],
            }
        )
        print(
            f"  {index}/{len(questions)} {question['id']}: {elapsed_ms / 1000:.2f}s",
            flush=True,
        )
    del reranker
    gc.collect()
    return {
        "model_id": config["model_id"],
        "kind": config["kind"],
        "batch_size": config["batch_size"],
        "load_ms": load_ms,
        "questions": results,
    }


def fmean(rows: list[float]) -> float:
    return statistics.fmean(rows) if rows else 0.0


def aggregate(model: dict[str, Any]) -> dict[str, Any]:
    questions = model["questions"]
    output: dict[str, Any] = {
        "mean_rerank_ms": fmean([q["rerank_ms"] for q in questions]),
        "median_rerank_ms": statistics.median(q["rerank_ms"] for q in questions),
    }
    for slice_name, predicate in {
        "all": lambda q: True,
        "primary_disease": lambda q: q["intent"] == "primary_disease",
        "other_disease": lambda q: q["intent"] == "other_disease",
        "english": lambda q: q["language"] == "en",
        "korean": lambda q: q["language"] == "ko",
    }.items():
        selected = [q for q in questions if predicate(q)]
        output[slice_name] = {
            "questions": len(selected),
            "target_at_1_rate": fmean([float(q["metrics"]["target_at_1"]) for q in selected]),
            "target_title_at_1_rate": fmean(
                [float(q["results"][0]["target_title_match"]) for q in selected]
            ),
            "mean_target_count_at_3": fmean([q["metrics"]["target_count_at_3"] for q in selected]),
            "mean_target_count_at_10": fmean([q["metrics"]["target_count_at_10"] for q in selected]),
            "mean_target_title_count_at_3": fmean(
                [q["metrics"]["target_title_count_at_3"] for q in selected]
            ),
            "mean_mrr": fmean([q["metrics"]["target_mrr"] for q in selected]),
            "mean_ndcg_at_10": fmean([q["metrics"]["target_ndcg_at_10"] for q in selected]),
            "mean_keyword_two_plus_at_10": fmean(
                [q["metrics"]["keyword_two_plus_count_at_10"] for q in selected]
            ),
        }
    return output


def render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# XPRS reranker comparison",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "All rerankers received the same BGE-M3 dense top-30 candidates. Scores are not "
        "compared across models because their calibrations differ.",
        "",
        "## Aggregate results",
        "",
        "| Model | Mean latency | Disease mention @1 | Disease in title @1 | Target nDCG@10 | Primary nDCG@10 | Other-disease nDCG@10 | Korean nDCG@10 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, model in payload["models"].items():
        agg = model["aggregate"]
        lines.append(
            f"| {name} | {agg['mean_rerank_ms'] / 1000:.2f}s | "
            f"{agg['all']['target_at_1_rate']:.1%} | "
            f"{agg['all']['target_title_at_1_rate']:.1%} | "
            f"{agg['all']['mean_ndcg_at_10']:.3f} | "
            f"{agg['primary_disease']['mean_ndcg_at_10']:.3f} | "
            f"{agg['other_disease']['mean_ndcg_at_10']:.3f} | "
            f"{agg['korean']['mean_ndcg_at_10']:.3f} |"
        )
    for question in payload["questions"]:
        lines.extend(["", f"## {question['id']}", "", question["question"], ""])
        for name, model in payload["models"].items():
            result = next(q for q in model["questions"] if q["id"] == question["id"])
            lines.append(f"### {name} ({result['rerank_ms'] / 1000:.2f}s)")
            lines.append("")
            for rank, row in enumerate(result["results"][:5], 1):
                target = "target" if row["target_text_match"] else "non-target"
                lines.append(
                    f"{rank}. {row['title']} ({target}, keywords={row['keyword_hits']})"
                )
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_blinded_review(payload: dict[str, Any], output: Path) -> None:
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    rank_map: dict[tuple[str, str], dict[str, int]] = {}
    for model_name, model in payload["models"].items():
        for question in model["questions"]:
            for rank, result in enumerate(question["results"], 1):
                key = (question["id"], result["paper_id"])
                rank_map.setdefault(key, {})[model_name] = rank
                if key not in rows:
                    token = hashlib.sha256("::".join(key).encode()).hexdigest()[:12]
                    rows[key] = {
                        "question_id": question["id"],
                        "question": question["question"],
                        "document_token": token,
                        "title": result["title"],
                        "abstract": result["abstract"],
                        "relevance_0_to_3": "",
                        "disease_match_yes_no": "",
                        "review_notes": "",
                    }
    review_rows = sorted(rows.values(), key=lambda row: (row["question_id"], row["document_token"]))
    with (output / "blinded_review.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(review_rows[0]))
        writer.writeheader()
        writer.writerows(review_rows)
    mapping = [
        {
            "question_id": key[0],
            "paper_id": key[1],
            "document_token": rows[key]["document_token"],
            "ranks": ranks,
        }
        for key, ranks in sorted(rank_map.items())
    ]
    (output / "review_mapping.json").write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main() -> None:
    args = parse_args()
    args.source = args.source.resolve()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    final_path = args.output / "results.json"
    if final_path.exists() and not args.finalize_only:
        raise SystemExit(f"Refusing to overwrite completed benchmark: {final_path}")
    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    questions = json.loads(args.questions.read_text(encoding="utf-8"))
    candidates = build_candidates(args.source, questions, args.output / "candidates.json")
    partial_path = args.output / "partial_results.json"
    completed = json.loads(partial_path.read_text(encoding="utf-8")) if partial_path.exists() else {}
    for name in args.models:
        if name in completed:
            print(f"Skipping completed model: {name}", flush=True)
            continue
        completed[name] = evaluate_model(name, questions, candidates)
        partial_path.write_text(
            json.dumps(completed, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    missing = [name for name in args.models if name not in completed]
    if missing:
        raise RuntimeError(f"Incomplete model results: {missing}")
    question_by_id = {question["id"]: question for question in questions}
    for model in completed.values():
        for result in model["questions"]:
            question = question_by_id[result["id"]]
            total_target_matches = sum(
                term_match(row["text"], question["target_terms"])
                for row in candidates[result["id"]]
            )
            result["metrics"] = ranking_metrics(
                result["results"], total_target_matches=total_target_matches
            )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "design": {
            "source": str(args.source),
            "candidate_retrieval": f"{EMBED_MODEL} dense top {TOP_CANDIDATES} within gene",
            "candidate_text": "title + full abstract",
            "top_results": TOP_RESULTS,
            "threads": args.threads,
            "qwen_instruction": QWEN_INSTRUCTION,
            "production_stores_touched": False,
        },
        "questions": questions,
        "models": {
            name: {**completed[name], "aggregate": aggregate(completed[name])}
            for name in args.models
        },
    }
    final_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.output / "report.md").write_text(render_report(payload), encoding="utf-8")
    write_blinded_review(payload, args.output)
    print(f"Benchmark complete: {args.output}", flush=True)


if __name__ == "__main__":
    main()
