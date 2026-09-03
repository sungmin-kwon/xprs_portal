from __future__ import annotations

import re
from pathlib import Path
from typing import Any

LOCAL_REFERENCE_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "about", "your",
    "what", "when", "where", "which", "whose", "their", "there", "than", "then",
    "have", "has", "had", "been", "were", "was", "are", "how", "why", "does", "did",
    "can", "could", "would", "should", "will", "may", "might", "not", "but", "only",
    "through", "between", "using", "used", "use", "into", "onto", "over", "under",
    "show", "shown", "explain", "explained", "question", "portal", "report",
}
LOCAL_REFERENCE_METHODOLOGY_TERMS = {
    "xprs", "prs", "polygenic", "score", "scores", "method", "methods", "methodology",
    "calculate", "calculated", "calculation", "compute", "computed", "formula", "input",
    "inputs", "contribution", "contributions", "rank", "shap", "mapping", "snp", "snps",
    "pipeline", "workflow", "interpretation",
}
LOCAL_REFERENCE_STRONG_METHODOLOGY_TERMS = {
    "xprs", "prs", "polygenic", "methodology", "formula", "shap", "snp", "snps",
}
LOCAL_REFERENCE_METHOD_VERBS = {
    "calculate", "calculated", "calculation", "compute", "computed", "derive", "derived",
    "estimate", "estimated", "input", "inputs", "mapping", "interpretation",
}
LOCAL_REFERENCE_LITERATURE_TERMS = {
    "association", "associations", "associated", "correlated", "correlation", "correlations",
    "documented", "literature", "papers", "paper", "reported", "report", "cancer", "cancers",
    "tumor", "tumors", "tumour", "tumours", "disease", "diseases", "phenotype", "phenotypes",
    "gene", "genes", "breast", "lung", "ovarian", "prostate", "pancreatic", "colorectal",
}


def _tokenize_reference_text(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", (text or "").lower())
        if token not in LOCAL_REFERENCE_STOPWORDS
    }


class LocalReferenceAgent:
    def __init__(self, ref_dir: Path):
        self.ref_dir = Path(ref_dir)
        self._entries = self._load_entries()

    @staticmethod
    def _extract_title(lines: list[str], fallback: str) -> str:
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                return stripped.lstrip("#").strip() or fallback
        return fallback

    def _load_entries(self) -> list[dict[str, Any]]:
        if not self.ref_dir.exists():
            return []

        entries: list[dict[str, Any]] = []
        for path in sorted(self.ref_dir.glob("*.md")):
            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                continue
            lines = text.splitlines()
            title = self._extract_title(lines, path.stem.replace("_", " ").title())

            heading = title
            buffer: list[str] = []

            def flush_buffer() -> None:
                nonlocal buffer
                paragraph = " ".join(line.strip() for line in buffer if line.strip()).strip()
                buffer = []
                if len(paragraph) < 80:
                    return
                entries.append({
                    "id": f"{path.stem}:{len(entries) + 1}",
                    "title": title,
                    "heading": heading,
                    "text": paragraph,
                    "path": str(path),
                    "tokens": _tokenize_reference_text(f"{title} {heading} {paragraph}"),
                })

            for line in lines:
                stripped = line.strip()
                if stripped.startswith("#"):
                    flush_buffer()
                    heading = stripped.lstrip("#").strip() or title
                    continue
                if not stripped:
                    flush_buffer()
                    continue
                buffer.append(stripped)
            flush_buffer()
        return entries

    def is_methodology_query(self, question: str) -> bool:
        tokens = _tokenize_reference_text(question)
        if not tokens:
            return False

        strong_hits = tokens & LOCAL_REFERENCE_STRONG_METHODOLOGY_TERMS
        method_hits = tokens & LOCAL_REFERENCE_METHOD_VERBS
        methodology_hits = tokens & LOCAL_REFERENCE_METHODOLOGY_TERMS
        literature_hits = tokens & LOCAL_REFERENCE_LITERATURE_TERMS

        if strong_hits and method_hits:
            return True
        if len(strong_hits) >= 2:
            return True
        if "xprs" in tokens or "prs" in tokens:
            return bool(methodology_hits - {"interpretation"}) or not literature_hits
        if "score" in tokens or "scores" in tokens:
            return bool(method_hits or {"rank", "contribution"} & tokens)
        return False

    def query(self, question: str, top_k: int = 3) -> list[dict[str, Any]]:
        if not self._entries:
            return []
        query_tokens = _tokenize_reference_text(question)
        if not query_tokens:
            return []

        scored: list[tuple[float, dict[str, Any]]] = []
        for entry in self._entries:
            overlap = query_tokens & entry["tokens"]
            if not overlap:
                continue
            score = float(len(overlap))
            if "xprs" in overlap or "prs" in overlap:
                score += 2.0
            if any(token in overlap for token in {"method", "methods", "methodology", "calculate", "calculation", "input", "inputs", "shap"}):
                score += 1.5
            scored.append((score, entry))

        scored.sort(key=lambda item: (-item[0], item[1]["title"], item[1]["heading"]))
        return [entry for score, entry in scored[:top_k] if score >= 2.0]
