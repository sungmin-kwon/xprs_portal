from __future__ import annotations

import json
import re
from typing import Any

from config import GENERIC_PHENOTYPES, PHENOTYPE_ALIASES
from llm_utils import LLMAgent
from phenotype_utils import infer_phenotypes_from_text, normalize_phenotype_values
from text_utils import unique_preserving_order


class QueryAnalysisAgent:
    PHENOTYPE_ALIASES = PHENOTYPE_ALIASES
    GENERIC_PHENOTYPES = GENERIC_PHENOTYPES

    def __init__(self, llm: LLMAgent):
        self.llm = llm

    @staticmethod
    def _extract_json(raw: str) -> dict[str, Any]:
        raw = (raw or "").strip()
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except Exception:
            pass

        match = re.search(r"\{.*\}", raw, flags=re.S)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                return {}
        return {}

    def analyze(
        self,
        question: str,
        available_genes: list[str],
        conversation_history: list[str] | None = None,
        default_phenotype: str = "breast cancer",
    ) -> dict[str, Any]:
        q_lower = question.lower()
        gene_hits = [g for g in available_genes if re.search(rf"\b{re.escape(g.lower())}\b", q_lower)]

        phenotype_hits = infer_phenotypes_from_text(question)

        broad_disease_query = bool(
            re.search(r"\b(other\s+)?(cancer|cancers|disease|diseases|phenotype|phenotypes|tumou?r|tumou?rs)\b", q_lower)
            or re.search(r"(다른|기타).*(암|질환|질병)", question)
            or re.search(r"(암|질환|질병).*(외|이외)", question)
        )

        prompt = f"""
You analyze biomedical user questions for retrieval.

Return JSON with keys:
- rewritten_query: concise retrieval-oriented query
- genes: array of gene symbols explicitly mentioned or clearly requested
- phenotypes: array of diseases/phenotypes mentioned or implied
- scope: one of "named_genes", "top10", "summary_genes", "general"
- disease_intent: one of "primary_disease", "other_disease", "disease_neutral"

Rules:
- Prefer the user's exact genes when named.
- If the user refers to "Top 10", "my list", or "other genes in my Top 10", set scope to "top10".
- A question about a gene's general function with no disease named is disease_neutral; do not add a default phenotype.
- Use primary_disease only when "{default_phenotype}" is explicitly requested or clearly carried forward from context.
- Use other_disease when another named disease is requested, or when the user asks broadly about other diseases/cancers.
- For broad questions like "what other cancers" or "what diseases", do not infer "{default_phenotype}" unless the user explicitly mentions it.
- rewritten_query must be an English biomedical retrieval query, even when the user's question is Korean.
- Output JSON only.

Available genes:
{", ".join(available_genes)}

Question:
{question}
""".strip()

        parsed = self._extract_json(self.llm.chat([
            {"role": "system", "content": "You are a precise biomedical query analysis assistant. Output JSON only."},
            {"role": "user", "content": prompt},
        ]))

        llm_genes = [g for g in parsed.get("genes", []) if g in available_genes]
        raw_llm_phenotypes = [
            p.strip()
            for p in parsed.get("phenotypes", [])
            if isinstance(p, str) and p.strip() and p.strip().lower() not in self.GENERIC_PHENOTYPES
        ]
        llm_phenotypes: list[str] = []
        for phenotype in raw_llm_phenotypes:
            canonical = normalize_phenotype_values([phenotype])
            llm_phenotypes.extend(canonical or [phenotype.lower()])
        scope = parsed.get("scope") if isinstance(parsed.get("scope"), str) else "general"
        rewritten_query = parsed.get("rewritten_query") if isinstance(parsed.get("rewritten_query"), str) else ""

        final_genes = unique_preserving_order(gene_hits + llm_genes)
        final_phenotypes = unique_preserving_order(phenotype_hits + llm_phenotypes)
        if broad_disease_query and not phenotype_hits:
            final_phenotypes = [p for p in final_phenotypes if p.lower() != default_phenotype.lower()]

        if broad_disease_query and not phenotype_hits:
            disease_intent = "other_disease"
        elif any(p != default_phenotype for p in final_phenotypes):
            disease_intent = "other_disease"
        elif default_phenotype in final_phenotypes:
            disease_intent = "primary_disease"
        else:
            disease_intent = "disease_neutral"

        if not rewritten_query:
            rewritten_query = question
        if final_phenotypes:
            phenotype_text = ", ".join(final_phenotypes)
            if phenotype_text.lower() not in rewritten_query.lower():
                rewritten_query = f"{rewritten_query} {phenotype_text}".strip()

        return {
            "rewritten_query": rewritten_query,
            "genes": final_genes,
            "phenotypes": final_phenotypes,
            "scope": scope,
            "disease_intent": disease_intent,
        }

# ============================================================
# 7. Explanation Agent
# ============================================================
