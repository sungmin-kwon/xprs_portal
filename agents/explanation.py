from __future__ import annotations

import html
import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import nullcontext
from threading import Lock
from typing import Any, Callable, Optional

import pandas as pd

from agents.conversation import ConversationAgent, ConversationState
from agents.evidence_assembly import EvidenceAssemblyAgent
from agents.gene_importance import GeneImportanceAgent
from agents.local_reference import LocalReferenceAgent
from agents.open_targets import OpenTargetsAgent
from agents.query_analysis import QueryAnalysisAgent
from config import REF_DIR
from llm_utils import LLMAgent
from plot_data import load_plot_data_store
from reference_utils import (
    extract_publication_id,
    infer_phenotypes_from_text,
    merge_references_preserve_numbers,
    normalize_citations,
    reference_identity,
    split_reference_genes,
)
from text_utils import (
    emit_progress,
    emit_timing,
    format_duration,
    normalize_output_language,
    ui_label,
    unique_preserving_order,
)

logger = logging.getLogger(__name__)

ENABLE_LLM_REFERENCE_EXTRACTION = os.getenv("ENABLE_LLM_REFERENCE_EXTRACTION", "false").lower() in {
    "1",
    "true",
    "yes",
    "on",
}

# Injected into every LLM generation prompt in this module. Keeps outputs research-framed
# rather than clinical. The committee-feedback rationale is documented in the README's
# safety-guardrails section.
SAFETY_RULES = (
    "Safety rules — these are non-negotiable:\n"
    "- Do NOT make diagnostic claims about this individual "
    "(e.g. \"this means you have / will develop X\", \"you are at high risk of cancer\").\n"
    "- Do NOT recommend or suggest screenings, tests, medications, surgeries, lifestyle "
    "interventions, or other clinical actions.\n"
    "- Do NOT state numeric prognoses (e.g. \"X% chance of developing Y\", \"Z-fold risk\") "
    "unless that exact figure is directly quoted from the provided evidence.\n"
    "- Frame all findings as statistical signals, association evidence, or research findings "
    "relative to the reference cohort — not as personal clinical conclusions.\n"
    "- It is fine to describe what genes do biologically, what the literature reports as "
    "associations, and what the PRS distribution shows. The line is at acting as a clinician."
)


class LiteratureEvidenceUnavailableError(RuntimeError):
    """Raised when a literature-backed summary cannot be cited responsibly."""


class ExplanationAgent:
    MAX_SUMMARY_GENES = 5
    GENE_SECTION_TIMEOUT = 35
    INTEGRATED_VIEW_TIMEOUT = 25
    FOLLOWUP_TIMEOUT = 60

    def __init__(
        self,
        llm: LLMAgent,
        gene_agent: GeneImportanceAgent,
        evidence_agent: EvidenceAssemblyAgent,
        ot_agent: OpenTargetsAgent | None,
        query_agent: Optional[QueryAnalysisAgent] = None,
        conversation_agent: Optional[ConversationAgent] = None,
        primary_phenotype: str = "breast cancer",
        disease_display_name: str = "Breast Cancer",
        risk_profile_provider: Optional[Callable[[str], dict[str, Any]]] = None,
        minimize_sensitive_context: bool = False,
    ):
        self.llm = llm
        self.gene_agent = gene_agent
        self.evidence_agent = evidence_agent
        self.ot_agent = ot_agent
        self.query_agent = query_agent
        self.conversation_agent = conversation_agent or ConversationAgent()
        self.primary_phenotype = primary_phenotype.strip().lower()
        self.disease_display_name = disease_display_name.strip()
        self.risk_profile_provider = risk_profile_provider
        self.minimize_sensitive_context = minimize_sensitive_context
        self.local_reference_agent = LocalReferenceAgent(REF_DIR)

    def _disease_relevance_label(self, language: str) -> str:
        if normalize_output_language(language) == "ko":
            return f"{self.disease_display_name} 관련성"
        return f"{self.disease_display_name} Relevance"

    def _model_ranking_text(self, target_genes: list[str], language: str) -> str:
        if self.minimize_sensitive_context:
            if normalize_output_language(language) == "ko":
                return "\n".join(
                    f"{index}. {gene} — 선택된 상위 기여 유전자"
                    for index, gene in enumerate(target_genes, 1)
                )
            return "\n".join(
                f"{index}. {gene} — selected top contributing gene"
                for index, gene in enumerate(target_genes, 1)
            )
        return ""

    @staticmethod
    def _extract_json_object(raw: str) -> dict[str, Any]:
        text = (raw or "").strip()
        if not text:
            return {}
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return {}
        try:
            return json.loads(match.group(0))
        except Exception:
            return {}

    def _generate_gene_section(
        self,
        *,
        gene: str,
        individual_contribution: str,
        evidence_context: str,
        citation_rules: str,
        language: str,
    ) -> dict[str, str]:
        output_language = "Korean" if language == "ko" else "English"
        try:
            raw = self.llm.chat(
                [
                    {
                        "role": "system",
                        "content": "You are a biomedical summarization assistant. Output JSON only.",
                    },
                    {
                        "role": "user",
                        "content": (
                            "Return JSON with exactly one key: disease_relevance.\n"
                            "Use only the provided evidence context. Write one concise paragraph of no more "
                            "than two sentences. Do not restate the gene's rank, contribution direction, or "
                            "that it belongs to a top/bottom group. Use at most two citations.\n"
                            f"Output language: {output_language}. If Korean, use consistent formal 존댓말.\n"
                            "Do not mention Open Targets or structured database evidence.\n"
                            "Describe disease relevance as research evidence, not as a personal clinical "
                            "interpretation or recommendation.\n\n"
                            f"{SAFETY_RULES}\n\n"
                            f"Primary disease context: {self.disease_display_name}\n"
                            f"Gene: {gene}\n"
                            f"Individual contribution: {individual_contribution}\n"
                            f"Citation rules: {citation_rules}\n"
                            f"Evidence context:\n{evidence_context}"
                        ),
                    },
                ],
                timeout=self.GENE_SECTION_TIMEOUT,
            )
            parsed = self._extract_json_object(raw)
            return {
                "disease_relevance": str(parsed.get("disease_relevance", "")).strip(),
            }
        except Exception:
            return {
                "disease_relevance": "",
            }

    def _generate_gene_group_sections(
        self,
        *,
        group_label: str,
        genes: list[dict[str, str]],
        language: str,
    ) -> dict[str, dict[str, str]]:
        """Draft one contribution-tail section with a single model call."""
        if not genes:
            return {}
        output_language = "Korean" if language == "ko" else "English"
        try:
            raw = self.llm.chat(
                [
                    {
                        "role": "system",
                        "content": "You are a biomedical summarization assistant. Output JSON only.",
                    },
                    {
                        "role": "user",
                        "content": (
                            "Return JSON with one key, items. items must contain one object per supplied gene "
                            "with exactly these keys: gene, disease_relevance.\n"
                            "Write one concise paragraph of no more than two sentences per gene and use only "
                            "that gene's supplied evidence. Do not restate its rank, contribution direction, "
                            "or membership in a top/bottom group. Use at most two citations per gene. "
                            "Preserve valid numbered citations exactly. If evidence is absent, do not invent a "
                            "biological or disease interpretation.\n"
                            f"Contribution section: {group_label}. Negative/lowering contributions mean that the "
                            "gene lowers this linear PRS relative to the other contributions in this model; do not "
                            "describe it as clinically protective.\n"
                            f"Output language: {output_language}. If Korean, use consistent formal 존댓말.\n\n"
                            f"{SAFETY_RULES}\n\n"
                            f"Primary disease context: {self.disease_display_name}\n"
                            f"Gene inputs:\n{json.dumps(genes, ensure_ascii=False)}"
                        ),
                    },
                ],
                timeout=max(self.GENE_SECTION_TIMEOUT, 60),
            )
            parsed = self._extract_json_object(raw)
            output: dict[str, dict[str, str]] = {}
            for item in parsed.get("items", []):
                if not isinstance(item, dict):
                    continue
                gene = str(item.get("gene") or "").strip().upper()
                if not gene:
                    continue
                output[gene] = {
                    "disease_relevance": str(item.get("disease_relevance") or "").strip(),
                }
            return output
        except Exception:
            return {}

    def _generate_integrated_view(
        self,
        *,
        selected_genes: str,
        top_genes_summary: str,
        gene_takeaways: str,
        citation_rules: str,
        language: str,
    ) -> str:
        output_language = "Korean" if language == "ko" else "English"
        try:
            raw = self.llm.chat(
                [
                    {
                        "role": "system",
                        "content": "You are a biomedical summarization assistant. Output JSON only.",
                    },
                    {
                        "role": "user",
                        "content": (
                            "Return JSON with exactly two keys: overall_interpretation and gene_overview.\n"
                            "Write 1-2 short sentences in overall_interpretation that give the overall pattern "
                            "and what it means within the reference cohort. Write 1-2 short sentences in "
                            "gene_overview that summarize the gene-level pattern without listing every gene. "
                            "Write both fields for a non-specialist reader and use only the provided takeaways. Avoid "
                            "specialist jargon; if a technical term is unavoidable, explain it in plain "
                            "language. Clearly distinguish a gene's contribution to this PRS model from "
                            "proof that it causes disease, and do not describe a risk-lowering contribution "
                            "as clinically protective. Keep citations sparse: place at most one citation "
                            "group at the end of a sentence and include no more than three of the most "
                            "directly relevant reference numbers in that group.\n"
                            f"Output language: {output_language}. If Korean, use consistent formal 존댓말.\n\n"
                            f"{SAFETY_RULES}\n\n"
                            f"Primary disease context: {self.disease_display_name}\n"
                            f"Citation rules: {citation_rules}\n"
                            f"Genes selected from the risk-increasing and risk-lowering tails: {selected_genes}\n"
                            f"Contribution ranking summary:\n{top_genes_summary}\n\n"
                            f"Gene takeaways:\n{gene_takeaways}"
                        ),
                    },
                ],
                timeout=self.INTEGRATED_VIEW_TIMEOUT,
            )
            parsed = self._extract_json_object(raw)
            overall = str(parsed.get("overall_interpretation") or "").strip()
            gene_overview = str(parsed.get("gene_overview") or "").strip()
            if overall or gene_overview:
                return "\n\n".join(part for part in [overall, gene_overview] if part)
            # Backward compatibility for cached/test responses using the prior schema.
            return str(parsed.get("integrated_view") or "").strip()
        except Exception:
            return ""

    def _generate_followup_text(
        self,
        *,
        background: str,
        compact_ctx: str,
        ref_index: str,
        question: str,
        n_max: int,
        language: str = "en",
        methodology_query: bool = False,
    ) -> str:
        output_language = "Korean" if normalize_output_language(language) == "ko" else "English"
        evidence_context = compact_ctx if compact_ctx else "(No evidence context available.)"
        reference_index = ref_index if ref_index else "(No references available.)"
        methodology_instructions = ""
        if methodology_query:
            methodology_instructions = (
                "This is a PRS/XPRS methodology question. Give the level of detail warranted by the supplied "
                "methodology sections rather than only restating their overview. For a calculation question, "
                "explain: (1) what is being calculated, (2) required inputs, (3) preprocessing and SNP-to-gene "
                "mapping, (4) each supplied equation with its variables, (5) population-relative interpretation, "
                "and (6) important limitations. Clearly distinguish calculation of the underlying PRS from "
                "XPRS decomposition and interpretation. Do not introduce formulas or details absent from the notes.\n"
            )
        try:
            raw = self.llm.chat(
                [
                    {
                        "role": "system",
                        "content": "You are a biomedical assistant answering a follow-up question. Output JSON only.",
                    },
                    {
                        "role": "user",
                        "content": (
                            "Return JSON with one key: answer.\n"
                            "Answer the user's follow-up question using only the provided XPRS background and evidence. "
                            "Cite literature only as [n] with n in the valid range; do not invent citations. "
                            "Do not include raw URLs.\n"
                            f"Output language: {output_language}. "
                            "If Korean, use consistent formal 존댓말.\n"
                            "Format mathematical expressions in LaTeX: use $...$ for inline math and $$...$$ for display math. "
                            "Prefer proper symbols such as \\beta, subscripts like _{i}, and \\cdot for multiplication. "
                            "Write named subscripts with \\mathrm, for example $CS_{\\mathrm{gene},j}$, "
                            "$A_{\\mathrm{gene},j}$, and $CS_{\\mathrm{SNP},i}$. Never escape an underscore as \\_ in math. "
                            "Do not use plain square brackets to display equations, and do not leave LaTeX fragments undelimited.\n\n"
                            f"{methodology_instructions}\n"
                            f"{SAFETY_RULES}\n\n"
                            f"Primary disease context: {self.disease_display_name}\n"
                            f"Largest valid reference number: {n_max}\n\n"
                            f"Background:\n{background}\n\n"
                            f"Evidence context:\n{evidence_context}\n\n"
                            f"Reference index:\n{reference_index}\n\n"
                            f"Question: {question}"
                        ),
                    },
                ],
                timeout=self.FOLLOWUP_TIMEOUT,
            )
            return self._extract_json_object(raw).get("answer", "").strip()
        except Exception:
            return ""

    @staticmethod
    def _ranked_gene_rows(gene_df: pd.DataFrame) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for row in gene_df.itertuples(index=False):
            rank = getattr(row, "population_rank", None)
            rows.append({
                "gene": str(getattr(row, "Gene")),
                "individual_contribution": float(getattr(row, "individual_contribution")),
                "population_rank": int(rank) if pd.notna(rank) else None,
            })
        return rows

    def _render_ranked_genes_table(self, gene_df: pd.DataFrame, title: str, language: str = "en") -> str:
        rows_html: list[str] = []
        for row in self._ranked_gene_rows(gene_df):
            rows_html.append(
                "<tr>"
                f"<td>{html.escape(str(row['gene']))}</td>"
                f"<td>{float(row['individual_contribution']):.2f}</td>"
                f"<td>{str(row['population_rank']) if row['population_rank'] is not None else '—'}</td>"
                "</tr>"
            )

        table = (
            '<table class="summary-top-genes-table">'
            "<thead><tr>"
            f"<th>{html.escape(ui_label(language, 'gene'))}</th>"
            f"<th>{html.escape(ui_label(language, 'individual_contribution'))}</th>"
            f"<th>{html.escape(ui_label(language, 'population_rank'))}</th>"
            "</tr></thead>"
            f"<tbody>{''.join(rows_html)}</tbody>"
            "</table>"
        )

        return "\n".join([f"### {title}", table]).strip()

    def _render_gene_rankings_section(
        self,
        *,
        top_df: pd.DataFrame,
        bottom_df: pd.DataFrame,
        language: str = "en",
    ) -> str:
        sections = [
            f"# {ui_label(language, 'summary_title')}",
            self._render_ranked_genes_table(top_df, ui_label(language, "top_genes"), language=language),
            self._render_ranked_genes_table(bottom_df, ui_label(language, "bottom_genes"), language=language),
        ]
        return "\n\n".join(part for part in sections if part.strip()).strip()

    def _build_verified_database_rows(self, genes: list[str], language: str = "en") -> list[dict[str, Any]]:
        if self.ot_agent is None:
            return []
        rows: list[dict[str, Any]] = []
        for gene in genes:
            stats = self.ot_agent.structured_stats(gene, language=language)
            rows.append({
                "gene": gene,
                "mean_association_score": stats.get("mean_association_score") if stats else None,
                "supporting_evidence_items": stats.get("supporting_evidence_items") if stats else None,
                "interpretation": (
                    str(stats.get("interpretation", "")).strip()
                    if stats
                    else ui_label(language, "no_association_rows")
                ),
            })
        return rows

    def _render_verified_databases_section(self, genes: list[str], language: str = "en") -> str:
        if self.ot_agent is None:
            return ""
        intro = ui_label(language, "verified_intro")

        rows_html: list[str] = []
        for row in self._build_verified_database_rows(genes, language=language):
            mean_score = row.get("mean_association_score")
            evidence_items = row.get("supporting_evidence_items")
            mean_score_cell = f"<td>{mean_score:.3f}</td>" if mean_score is not None else "<td>—</td>"
            evidence_items_cell = f"<td>{int(evidence_items)}</td>" if evidence_items is not None else "<td>—</td>"
            rows_html.append(
                "<tr>"
                f"<td>{html.escape(str(row.get('gene', '')))}</td>"
                f"{mean_score_cell}"
                f"{evidence_items_cell}"
                + f"<td>{html.escape(str(row.get('interpretation', '')))}</td>"
                "</tr>"
            )

        table = (
            '<table class="summary-top-genes-table">'
            '<thead><tr><th colspan="4" class="summary-table-banner">Open Targets Platform</th></tr>'
            "<tr>"
            f"<th>{html.escape(ui_label(language, 'gene'))}</th>"
            f"<th>{html.escape(ui_label(language, 'mean_association_score'))}</th>"
            f"<th>{html.escape(ui_label(language, 'evidence_items'))}</th>"
            f"<th>{html.escape(ui_label(language, 'interpretation'))}</th>"
            "</tr></thead>"
            f"<tbody>{''.join(rows_html)}</tbody>"
            "</table>"
        )

        return "\n".join([
            f"### {ui_label(language, 'verified_databases')}",
            intro,
            table,
        ]).strip()

    @staticmethod
    def _section_block(title: str, body: str) -> str:
        text = (body or "").strip()
        return f"### {title}\n{text}" if text else ""

    @staticmethod
    def _has_numbered_citation(text: str) -> bool:
        return bool(re.search(r"\[\d+\]", text or ""))

    @staticmethod
    def _strip_citations(text: str) -> str:
        cleaned = re.sub(r"\[(?:\d+(?:\s*[\-,–]\s*\d+)?)(?:\s*,\s*\d+(?:\s*[\-,–]\s*\d+)?)*\]", "", text or "")
        cleaned = re.sub(r"\s+([.,;:!?])", r"\1", cleaned)
        return cleaned

    @staticmethod
    def _plain_text(text: str) -> str:
        cleaned = re.sub(r"<[^>]+>", " ", text or "")
        cleaned = ExplanationAgent._strip_citations(cleaned)
        return re.sub(r"\s+", " ", cleaned).strip()

    @classmethod
    def _first_sentence_plain(cls, text: str) -> str:
        cleaned = cls._plain_text(text)
        if not cleaned:
            return ""

        for match in re.finditer(r"[.!?]", cleaned):
            idx = match.end()
            if idx >= len(cleaned) or cleaned[idx].isspace():
                return cleaned[:idx].strip()
        return cleaned

    @staticmethod
    def _remap_citations(text: str, mapping: dict[int, int]) -> str:
        if not text:
            return ""

        def replace(match: re.Match) -> str:
            old_val = int(match.group(1))
            if old_val in mapping:
                return f"[{mapping[old_val]}]"
            return ""

        return re.sub(r"\[(\d+)\]", replace, text)

    @classmethod
    def _normalize_used_references(
        cls,
        answer: str,
        ref_by_global_id: dict[int, dict[str, Any]],
        chunk_by_global_id: dict[int, str],
    ) -> tuple[str, str, list[dict[str, Any]], dict[int, int]]:
        """Canonicalize citations and return compact, display-numbered refs."""
        used_ids = [int(value) for value in re.findall(r"\[(\d+)\]", answer)]
        old_to_display: dict[int, int] = {}
        display_refs: dict[int, dict[str, Any]] = {}
        seen_ref_keys: dict[tuple[Any, ...], int] = {}
        used_valid_ids: list[int] = []

        for citation_id in used_ids:
            reference = ref_by_global_id.get(citation_id) or {}
            if not extract_publication_id(reference):
                continue
            if citation_id not in used_valid_ids:
                used_valid_ids.append(citation_id)

            identity = reference_identity(reference)
            display_number = seen_ref_keys.get(identity)
            if display_number is None:
                display_number = len(display_refs) + 1
                seen_ref_keys[identity] = display_number
                display_refs[display_number] = dict(reference)
            else:
                existing = display_refs[display_number]
                existing_genes = split_reference_genes(str(existing.get("gene") or ""))
                new_genes = split_reference_genes(str(reference.get("gene") or ""))
                merged_genes = unique_preserving_order([*existing_genes, *new_genes])
                if merged_genes:
                    existing["gene"] = ", ".join(merged_genes)
            old_to_display[citation_id] = display_number

        compact_context = "\n".join(
            f"[{old_to_display[citation_id]}] {chunk_by_global_id[citation_id]}"
            for citation_id in used_valid_ids
            if citation_id in chunk_by_global_id
        )
        answer = cls._remap_citations(answer, old_to_display)
        answer_body = re.sub(r"(?is)##?\s*references.*$", "", answer).rstrip()

        references: list[dict[str, Any]] = []
        for display_number, reference in sorted(display_refs.items()):
            paper_id = extract_publication_id(reference)
            if not paper_id:
                continue
            references.append({
                "n": display_number,
                "title": str(reference.get("title") or "Untitled").strip() or None,
                "gene": str(reference.get("gene") or "").strip() or None,
                "phenotype": str(reference.get("phenotype") or "").strip() or None,
                "source": str(reference.get("source") or "").strip().lower() or None,
                "paperId": paper_id,
                "url": str(reference.get("url") or "").strip() or None,
                "pmid": str(reference.get("pmid") or "").strip() or None,
                "pmcid": str(reference.get("pmcid") or "").strip() or None,
                "doi": str(reference.get("doi") or "").strip() or None,
                "journal": str(reference.get("journal") or "").strip() or None,
                "year": reference.get("year"),
                "authors": reference.get("authors"),
                "citationCount": reference.get("citationCount"),
                "disease_match": reference.get("disease_match"),
                "source_pool": reference.get("source_pool"),
                "reranker_score": reference.get("reranker_score"),
                "target_phenotypes": reference.get("target_phenotypes") or [],
            })
        return answer_body, compact_context, references, old_to_display

    def _get_density_profile(self, pid: str) -> dict[str, Any] | None:
        try:
            if self.risk_profile_provider is not None:
                profile = self.risk_profile_provider(pid)
                return {
                    "percentile": float(profile["percentile"]),
                    "prs_value": float(profile["prs_value"]),
                }
            density = load_plot_data_store().prs_density_data(pid)
        except Exception as exc:
            logger.warning("Failed to load density profile for %s: %s", pid, exc)
            return None

        percentile = float(density.get("percentile", 0.0)) * 100.0
        prs_value = density.get("prs_value")
        return {
            "percentile": percentile,
            "prs_value": float(prs_value) if prs_value is not None else None,
        }

    @staticmethod
    def _relative_risk_key(percentile: float | None) -> str:
        value = float(percentile or 0.0)
        if value < 25.0:
            return "risk_relative_lower"
        if value < 75.0:
            return "risk_relative_middle"
        if value < 90.0:
            return "risk_relative_higher"
        return "risk_relative_highest"

    @staticmethod
    def _render_compact_gene_rankings(
        top_rows: list[dict[str, Any]],
        bottom_rows: list[dict[str, Any]],
        language: str,
    ) -> str:
        """Render the ten-gene overview used in the compact chat summary.

        The PDF retains population-rank and narrative detail. The chatbot only
        shows gene symbols and individual contribution values so the ranking is
        visible without turning the message into a second full report.
        """
        top_five = top_rows[:5]
        bottom_five = bottom_rows[:5]
        row_count = max(len(top_five), len(bottom_five))
        if not row_count:
            return ""

        def cell(rows: list[dict[str, Any]], index: int) -> str:
            if index >= len(rows):
                return "<td>—</td>"
            row = rows[index]
            gene = html.escape(str(row.get("gene") or "—"))
            value = float(row.get("individual_contribution") or 0.0)
            value_text = f"{value:+.2f}"
            return (
                "<td>"
                f"<strong>{gene}</strong>"
                f'<span class="summary-gene-score">{html.escape(value_text)}</span>'
                "</td>"
            )

        rows_html = "".join(
            f"<tr>{cell(top_five, index)}{cell(bottom_five, index)}</tr>"
            for index in range(row_count)
        )
        table = (
            '<table class="summary-top-genes-table summary-gene-ranking-table">'
            "<thead><tr>"
            f"<th>{html.escape(ui_label(language, 'simple_top_genes'))}</th>"
            f"<th>{html.escape(ui_label(language, 'simple_bottom_genes'))}</th>"
            "</tr></thead>"
            f"<tbody>{rows_html}</tbody>"
            "</table>"
        )
        return "\n".join([
            f"### {ui_label(language, 'simple_gene_rankings')}",
            table,
        ])

    def _build_simple_summary(
        self,
        *,
        pid: str,
        density_profile: dict[str, Any] | None,
        top_rows: list[dict[str, Any]],
        bottom_rows: list[dict[str, Any]],
        gene_sections: list[dict[str, Any]],
        language: str,
        plain_language_interpretation: str = "",
    ) -> tuple[str, dict[str, Any]]:
        risk_title = ui_label(language, "risk_overview")
        note_text = ui_label(language, "simple_pdf_note")

        percentile = density_profile.get("percentile") if density_profile else None
        relative_position = ui_label(language, self._relative_risk_key(percentile))
        if percentile is not None:
            risk_summary = ui_label(
                language,
                "simple_risk_sentence",
                percentile=f"{percentile:.1f}",
                relative_position=relative_position,
            )
        else:
            risk_summary = ui_label(language, "simple_risk_fallback")

        risk_context = ui_label(language, "simple_risk_context")
        highlight_items: list[dict[str, Any]] = []
        gene_lookup = {item["gene"]: item for item in gene_sections}

        def contribution_section(title: str, rows: list[dict[str, Any]]) -> str:
            lines = [f"### {title}"]
            for row in rows[:5]:
                gene = row["gene"]
                gene_info = gene_lookup.get(gene, {})
                lead = (
                    self._first_sentence_plain(gene_info.get("disease_relevance", ""))
                    or ui_label(language, "simple_gene_fallback", gene=gene)
                )
                contribution = float(row.get("individual_contribution") or 0.0)
                value_label = "기여도" if language == "ko" else "contribution"
                lines.append(
                    f"- **{gene}** ({value_label} {contribution:.2f}): {lead}"
                )
                highlight_items.append({
                    "gene": gene,
                    "summary": lead,
                    "individual_contribution": contribution,
                    "group": gene_info.get("group"),
                })
            return "\n".join(lines)

        top_section = contribution_section(
            ui_label(language, "simple_top_genes"),
            top_rows,
        )
        bottom_section = contribution_section(
            ui_label(language, "simple_bottom_genes"),
            bottom_rows,
        )

        markdown_parts = [
            f"### {risk_title}",
            risk_summary,
            risk_context,
        ]
        if plain_language_interpretation.strip():
            markdown_parts.extend([
                "",
                f"### {ui_label(language, 'integrated_view')}",
                plain_language_interpretation.strip(),
            ])
        markdown_parts.extend(["", top_section, "", bottom_section])
        markdown_parts.extend([
            "",
            note_text,
        ])

        return "\n\n".join(part for part in markdown_parts if part).strip(), {
            "title": ui_label(language, "simple_summary_title"),
            "risk_overview": {
                "title": risk_title,
                "summary": risk_summary,
                "details": risk_context,
                "percentile": round(float(percentile), 2) if percentile is not None else None,
                "prs_value": density_profile.get("prs_value") if density_profile else None,
                "relative_position": relative_position,
            },
            "plain_language_interpretation": plain_language_interpretation.strip(),
            "gene_rankings": {
                "title": ui_label(language, "simple_gene_rankings"),
                "top": top_rows[:5],
                "bottom": bottom_rows[:5],
            },
            "highlights": highlight_items,
            "note": note_text,
        }

    def get_target_genes(self, pid: str, gene_count: int = 5) -> list[str]:
        selected_count = max(1, min(int(gene_count), self.MAX_SUMMARY_GENES))
        top, _ = self.gene_agent.get_top_genes(pid, top_n=selected_count)
        bottom = self.gene_agent.get_bottom_genes(pid, bottom_n=selected_count)
        return unique_preserving_order(
            list(top["Gene"].values)[:selected_count]
            + list(bottom["Gene"].values)[:selected_count]
        )

    def build_explanation(
        self,
        pid: str,
        evaluate: bool = False,
        gene_count: int = 5,
        language: str = "en",
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> dict[str, Any]:
        build_started_at = time.perf_counter()
        timings: dict[str, float] = {}

        def mark_timing(
            key: str,
            started_at: float,
            progress_label: str | None = None,
            *,
            live: bool = True,
            **details: Any,
        ) -> float:
            elapsed = time.perf_counter() - started_at
            timings[key] = round(elapsed, 3)
            if progress_label:
                emit_timing(progress_callback, progress_label, elapsed, live=live, **details)
            return elapsed

        language = normalize_output_language(language)
        emit_progress(progress_callback, f'Loading top genes for "{pid}"')
        top_genes_started_at = time.perf_counter()
        selected_count = max(1, min(int(gene_count), self.MAX_SUMMARY_GENES))
        top, _ = self.gene_agent.get_top_genes(
            pid,
            top_n=max(self.gene_agent.default_top_n, selected_count),
        )
        bottom = self.gene_agent.get_bottom_genes(pid, bottom_n=self.gene_agent.default_top_n)
        top_selected_genes = list(top.head(selected_count)["Gene"].values)
        bottom_selected_genes = list(bottom.head(selected_count)["Gene"].values)
        target_genes = unique_preserving_order(top_selected_genes + bottom_selected_genes)
        emit_progress(
            progress_callback,
            f"Selected {len(top_selected_genes)} risk-increasing and "
            f"{len(bottom_selected_genes)} risk-lowering genes for interpretation: "
            + ", ".join(target_genes),
        )
        mark_timing("top_gene_selection_s", top_genes_started_at, "Gene selection", genes=len(target_genes))

        # 1. Parallel Fetch
        results_map = {}
        retrieval_events: list[tuple[str | None, str]] = []
        retrieval_event_lock = Lock()

        def capture_retrieval_progress(message: str, gene: str | None = None) -> None:
            logger.info("[SUMMARY_RETRIEVAL] %s", message)
            with retrieval_event_lock:
                retrieval_events.append((gene, message))

        def fetch_gene_data(gene_symbol):
            c, r, s = self.evidence_agent.retrieve_gene_context(
                gene_symbol,
                top_k=5,
                progress_callback=lambda message: capture_retrieval_progress(message, gene_symbol),
            )
            return gene_symbol, c, r, s

        max_workers = 1 if ENABLE_LLM_REFERENCE_EXTRACTION else min(5, max(1, len(target_genes)))
        emit_progress(
            progress_callback,
            f"Retrieving literature for {len(target_genes)} selected genes",
        )
        fetch_started_at = time.perf_counter()
        batch_context = (
            self.evidence_agent.interactive_request_batch(capture_retrieval_progress)
            if hasattr(self.evidence_agent, "interactive_request_batch")
            else nullcontext()
        )
        with batch_context:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_gene = {executor.submit(fetch_gene_data, g): g for g in target_genes}
                completed_genes = 0
                progress_milestones = {
                    max(1, (len(target_genes) + 1) // 2),
                    len(target_genes),
                }
                for future in as_completed(future_to_gene):
                    try:
                        g_sym, c, r, s = future.result()
                        results_map[g_sym] = (c, r, s)
                    except Exception as exc:
                        logger.error(f"Gene {future_to_gene[future]} error: {exc}")
                        results_map[future_to_gene[future]] = ([], [], "ERROR")
                    completed_genes += 1
                    if completed_genes in progress_milestones:
                        emit_progress(
                            progress_callback,
                            f"Literature retrieval: {completed_genes}/{len(target_genes)} genes complete",
                        )
        fetch_elapsed = mark_timing(
            "gene_context_fetch_s",
            fetch_started_at,
            "Literature retrieval across selected genes",
            live=False,
            genes=len(target_genes),
            workers=max_workers,
        )

        evidence_backed_genes = [
            gene
            for gene in target_genes
            if any(
                extract_publication_id(ref or {})
                for ref in results_map.get(gene, ([], [], "ERROR"))[1]
            )
        ]
        europe_pmc_events = [
            (gene, message)
            for gene, message in retrieval_events
            if message.startswith("Sending query to Europe PMC")
        ]
        semantic_scholar_events = [
            (gene, message)
            for gene, message in retrieval_events
            if message.startswith("Sending query to Semantic Scholar")
        ]
        queried_genes = {
            gene
            for gene, _message in europe_pmc_events + semantic_scholar_events
            if gene
        }
        reused_gene_count = max(0, len(target_genes) - len(queried_genes))
        emit_progress(
            progress_callback,
            f"Literature sources: {reused_gene_count} genes reused the local index; "
            f"Europe PMC {len(europe_pmc_events)} requests for "
            f"{len({gene for gene, _message in europe_pmc_events if gene})} genes; "
            f"Semantic Scholar {len(semantic_scholar_events)} requests",
        )
        emit_progress(
            progress_callback,
            f"Literature ready: {len(evidence_backed_genes)}/{len(target_genes)} genes with citable evidence; "
            f"{format_duration(fetch_elapsed)}",
        )
        if target_genes and not evidence_backed_genes:
            genes_text = ", ".join(target_genes)
            message = (
                f"No citable literature is currently indexed for {genes_text}; "
                "the contribution summary will continue while fallback retrieval runs in the background"
            )
            logger.warning("[SUMMARY_EVIDENCE] %s", message)
            emit_progress(progress_callback, message)

        # 2. Sequential Assembly: literature refs are numbered; structured database evidence is rendered separately.
        ctx_sections: list[str] = []
        source_notes: list[str] = []
        citation_ranges: list[str] = []
        gene_context_map: dict[str, str] = {}
        gene_citation_rules: dict[str, str] = {}

        ref_by_global_id: dict[int, dict] = {}
        global_ref_counter = 1
        chunk_by_global_id: dict[int, str] = {}

        context_assembly_started_at = time.perf_counter()
        for g in target_genes:
            chunks, refs, src_used = results_map.get(g, ([], [], "ERROR"))

            start_id = global_ref_counter
            gene_lines: list[str] = []

            for chunk, ref in zip(chunks, refs):
                gid = global_ref_counter
                gene_lines.append(f"[{gid}] {chunk}")
                ref_by_global_id[gid] = (ref or {})
                chunk_by_global_id[gid] = chunk  # <-- NEW
                global_ref_counter += 1

            paper_end_id = global_ref_counter - 1

            if gene_lines:
                header_bits: list[str] = []
                if start_id <= paper_end_id:
                    header_bits.append(f"Paper citations [{start_id}]-[{paper_end_id}]")
                    citation_rule = (
                        f"Use ONLY paper citations [{start_id}]-[{paper_end_id}] for {g}. "
                        f"Every non-empty explanatory paragraph should include at least one valid inline [n] citation."
                    )
                    citation_ranges.append(f"- {g}: {citation_rule}")
                    gene_citation_rules[g] = citation_rule

                header_suffix = f" ({'; '.join(header_bits)})" if header_bits else ""
                gene_context = f"### Evidence for {g}{header_suffix}\n" + "\n\n".join(gene_lines)
                ctx_sections.append(gene_context)
                gene_context_map[g] = gene_context
            else:
                citation_ranges.append(f"- {g}: No specific literature citations available.")
                gene_context_map[g] = f"### Evidence for {g}\n(No specific literature evidence available.)"
                gene_citation_rules[g] = "No literature citations are available for this gene; avoid numbered citations."

            source_notes.append(f"{g}: {src_used}")
        mark_timing("context_assembly_s", context_assembly_started_at, "Evidence context assembly", genes=len(target_genes), refs=len(ref_by_global_id), live=False)

        rag_ctx = "\n\n".join(ctx_sections)
        ot_context = (
            "\n\n".join(self.ot_agent.summary(g) for g in target_genes)
            if self.ot_agent is not None else ""
        )
        top_for_display = top.rename(
            columns={
                "contribution": "individual_contribution",
                "population_rank": "population_rank",
            }
        )
        bottom_for_display = bottom.rename(
            columns={
                "contribution": "individual_contribution",
                "population_rank": "population_rank",
            }
        )
        top_rows = self._ranked_gene_rows(top_for_display)
        bottom_rows = self._ranked_gene_rows(bottom_for_display)
        top_text = top_for_display.loc[:, ["Gene", "individual_contribution", "population_rank"]].to_string(index=False)
        bottom_text = bottom_for_display.loc[:, ["Gene", "individual_contribution", "population_rank"]].to_string(index=False)
        ranking_text = (
            f"{ui_label(language, 'top_genes')}:\n{top_text}\n\n"
            f"{ui_label(language, 'bottom_genes')}:\n{bottom_text}"
        )
        model_ranking_text = self._model_ranking_text(target_genes, language) or ranking_text
        density_profile = self._get_density_profile(pid)

        selected_gene_text = ", ".join(target_genes) if target_genes else "None available"

        structured_sections: list[str] = []
        raw_gene_sections: list[dict[str, Any]] = []

        gene_takeaways: list[str] = []
        contribution_lookup = top_for_display.set_index("Gene")["individual_contribution"].to_dict()
        contribution_lookup.update(
            bottom_for_display.set_index("Gene")["individual_contribution"].to_dict()
        )

        if target_genes:
            gene_sections_started_at = time.perf_counter()
            emit_progress(progress_callback, "Drafting concise gene evidence sections")
            groups = [
                ("risk_increasing", ui_label(language, "simple_top_genes"), top_selected_genes),
                ("risk_lowering", ui_label(language, "simple_bottom_genes"), bottom_selected_genes),
            ]
            for group_key, group_label, group_genes in groups:
                evidence_inputs = []
                for gene in group_genes:
                    if gene not in evidence_backed_genes:
                        continue
                    contribution = float(contribution_lookup.get(gene, 0.0))
                    evidence_inputs.append({
                        "gene": gene,
                        "individual_contribution": (
                            "rank only; exact value withheld"
                            if self.minimize_sensitive_context else f"{contribution:.2f}"
                        ),
                        "citation_rules": gene_citation_rules.get(gene, ""),
                        "evidence_context": gene_context_map.get(gene, ""),
                    })
                generated = self._generate_gene_group_sections(
                    group_label=group_label,
                    genes=evidence_inputs,
                    language=language,
                )
                structured_sections.append(f"## {group_label}")
                for gene in group_genes:
                    contribution = float(contribution_lookup.get(gene, 0.0))
                    gene_section = generated.get(gene.upper())
                    if gene_section is None:
                        gene_section = {
                            "disease_relevance": (
                                "현재 이 유전자에 대해 인용 가능한 문헌이 색인되어 있지 않습니다. 보완 검색은 백그라운드에서 진행됩니다."
                                if language == "ko"
                                else "No citable literature is currently indexed for this gene; fallback retrieval is running in the background."
                            ),
                        }
                    section_parts = [
                        f"### {gene}",
                        gene_section.get("disease_relevance", "").strip(),
                    ]
                    section_text = "\n\n".join([part for part in section_parts if part.strip()])
                    if section_text.strip():
                        structured_sections.append(section_text)
                    raw_gene_sections.append({
                        "gene": gene,
                        "group": group_key,
                        "group_title": group_label,
                        "individual_contribution": contribution,
                        "disease_relevance": gene_section.get("disease_relevance", "").strip(),
                    })
                    takeaway = gene_section.get("disease_relevance", "").strip()
                    if takeaway:
                        gene_takeaways.append(f"{gene}: {takeaway}")
            mark_timing("gene_sections_total_s", gene_sections_started_at, "Gene evidence drafting", genes=len(target_genes), sections=2)

            verified_rows_started_at = time.perf_counter()
            verified_database_block = self._render_verified_databases_section(target_genes, language=language)
            if verified_database_block:
                structured_sections.append(verified_database_block)
            mark_timing("verified_database_render_s", verified_rows_started_at, "Verified database rendering", genes=len(target_genes), live=False)

            emit_progress(progress_callback, f"Drafting integrated summary with {self.llm.model}")
            integrated_rules = (
                "Use only valid numbered paper citations already present in the gene sections. "
                "Every evidence-based claim should carry at least one inline [n] citation."
            )
            integrated_started_at = time.perf_counter()
            integrated_view_text = self._generate_integrated_view(
                selected_genes=selected_gene_text,
                top_genes_summary=model_ranking_text,
                gene_takeaways="\n".join(gene_takeaways),
                citation_rules=integrated_rules,
                language=language,
            )
            integrated_block = self._section_block(ui_label(language, "integrated_view"), integrated_view_text)
            if integrated_block:
                structured_sections.append(integrated_block)
            mark_timing("integrated_summary_s", integrated_started_at, "Integrated summary drafting")

        answer = "\n\n".join([part for part in structured_sections if part.strip()])

        # Normalize grouped citations before parsing.
        answer = normalize_citations(answer)

        emit_progress(progress_callback, "Formatting references")
        reference_format_started_at = time.perf_counter()
        # 5. Output Cleanup & Structured References

        answer_body, compact_ctx, references_out, old_to_display = (
            self._normalize_used_references(
                answer,
                ref_by_global_id,
                chunk_by_global_id,
            )
        )
        integrated_view_text = self._remap_citations(locals().get("integrated_view_text", ""), old_to_display).strip()
        remapped_gene_sections: list[dict[str, Any]] = []
        for section in raw_gene_sections:
            remapped_gene_sections.append({
                "gene": section["gene"],
                "group": section.get("group"),
                "group_title": section.get("group_title"),
                "individual_contribution": section["individual_contribution"],
                "titles": {
                    "disease_relevance": self._disease_relevance_label(language),
                },
                "disease_relevance": self._remap_citations(section["disease_relevance"], old_to_display).strip(),
            })

        mark_timing("reference_formatting_s", reference_format_started_at, "Reference formatting", refs=len(references_out), live=False)

        simple_summary_started_at = time.perf_counter()
        top_genes_section = self._render_gene_rankings_section(
            top_df=top_for_display,
            bottom_df=bottom_for_display,
            language=language,
        )
        detailed_summary = top_genes_section if not answer_body else f"{top_genes_section}\n\n{answer_body}"
        simple_summary, simple_payload = self._build_simple_summary(
            pid=pid,
            density_profile=density_profile,
            top_rows=top_rows,
            bottom_rows=bottom_rows,
            gene_sections=remapped_gene_sections,
            language=language,
            plain_language_interpretation=integrated_view_text,
        )

        disclaimer_title = ui_label(language, "disclaimer_title")
        disclaimer_body = ui_label(language, "disclaimer")
        disclaimer_block = (
            f'<div class="xprs-disclaimer"><strong>{disclaimer_title}</strong><br/>'
            f'<em>{disclaimer_body}</em></div>'
        )
        simple_summary = f"{simple_summary}\n\n{disclaimer_block}" if simple_summary else disclaimer_block
        detailed_summary = f"{detailed_summary}\n\n{disclaimer_block}" if detailed_summary else disclaimer_block

        mark_timing("simple_summary_s", simple_summary_started_at, "Simple summary assembly", live=False)
        report_payload = {
            "title": ui_label(language, "report_title"),
            "individual_id": pid,
            "language": language,
            "gene_count": len(target_genes),
            "genes_per_section": selected_count,
            "disclaimer": {
                "title": disclaimer_title,
                "body": disclaimer_body,
            },
            "risk_overview": simple_payload.get("risk_overview", {}),
            "top_genes": {
                "title": ui_label(language, "top_genes"),
                "rows": top_rows,
                "selected_genes": top_selected_genes,
            },
            "bottom_genes": {
                "title": ui_label(language, "bottom_genes"),
                "rows": bottom_rows,
                "selected_genes": bottom_selected_genes,
            },
            "gene_sections": remapped_gene_sections,
            "verified_databases": {
                "title": ui_label(language, "verified_databases"),
                "intro": ui_label(language, "verified_intro"),
                "rows": self._build_verified_database_rows(target_genes, language=language),
            },
            "integrated_view": {
                "title": ui_label(language, "integrated_view"),
                "body": integrated_view_text,
            },
            "references": references_out,
            "simple_summary": simple_summary,
            "detailed_summary": detailed_summary,
            "timings": timings,
        }

        mark_timing("total_summary_build_s", build_started_at, "Total summary build", genes=len(target_genes), refs=len(references_out))
        emit_progress(progress_callback, "Summary complete")
        return {
            "Individual ID": pid,
            "Generated Explanation": detailed_summary,
            "Simple Explanation": simple_summary,
            "Detailed Explanation": detailed_summary,
            "Report Payload": report_payload,
            "References": references_out,
            "Discussed Genes": target_genes,
            "RAG Context": rag_ctx,
            "RAG Context Compact": compact_ctx,
            "Model Safe Context": answer_body,
            "OT Context Compact": "",
            "OT Summary": ot_context,
            "Source Path": "; ".join(source_notes),
            "Timings": timings,
            "Evaluation": None,
            "Gene Count Used": len(target_genes),
            "Threshold Used": None,
            "Language": language,
        }

    def answer_followup(
        self,
        pid: str,
        question: str,
        gene_count: int = 5,
        existing_references: list[dict[str, Any]] | None = None,
        conversation_history: list[str] | None = None,
        conversation_state: dict[str, Any] | None = None,
        language: str = "en",
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> dict[str, Any]:
        language = normalize_output_language(language)
        emit_progress(progress_callback, "Analyzing follow-up question")
        state = ConversationState.from_session(conversation_state)
        top_genes_df, _ = self.gene_agent.get_top_genes(
            pid,
            top_n=self.gene_agent.default_top_n,
        )
        bottom_genes_df = self.gene_agent.get_bottom_genes(pid, bottom_n=self.gene_agent.default_top_n)
        top_gene_symbols = list(top_genes_df["Gene"].values)
        bottom_gene_symbols = list(bottom_genes_df["Gene"].values)
        summary_gene_symbols = self.get_target_genes(pid, gene_count=gene_count)
        available_genes = unique_preserving_order(top_gene_symbols + bottom_gene_symbols + summary_gene_symbols + state.active_genes)
        resolution = self.conversation_agent.resolve_turn(
            question=question,
            state=state,
            available_genes=available_genes,
        ) if self.conversation_agent else {
            "turn_type": "biomedical_followup",
            "resolved_genes": [],
            "resolved_phenotypes": state.active_phenotypes,
            "resolved_intent": state.active_intent,
            "resolved_question": question,
        }
        turn_type = (resolution.get("turn_type") or "biomedical_followup").strip()

        if turn_type == "off_domain_request":
            logger.info(
                "[FOLLOWUP_QUERY] scope=%s question=%r effective_question=%r rewritten=%r genes=%s phenotypes=%s state_genes=%s",
                "off_domain_request",
                question,
                resolution.get("resolved_question") or question,
                "off-domain decline",
                [],
                [],
                state.active_genes,
            )
            answer = (
                ui_label(language, "off_domain_decline")
            )
            return {
                "Generated Answer": answer,
                "References": existing_references or [],
                "Gene Count Used": gene_count,
                "Threshold Used": None,
                "Discussed Genes": state.active_genes,
                "Conversation State": state.to_session(),
                "Store In History": False,
            }

        if turn_type == "medical_advice_seeking":
            logger.info(
                "[FOLLOWUP_QUERY] scope=%s question=%r effective_question=%r rewritten=%r genes=%s phenotypes=%s state_genes=%s",
                "medical_advice_seeking",
                question,
                resolution.get("resolved_question") or question,
                "medical-advice decline",
                [],
                [],
                state.active_genes,
            )
            answer = ui_label(language, "medical_advice_decline")
            return {
                "Generated Answer": answer,
                "References": existing_references or [],
                "Gene Count Used": gene_count,
                "Threshold Used": None,
                "Discussed Genes": state.active_genes,
                "Conversation State": state.to_session(),
                "Store In History": False,
            }

        # Short-circuit casual chat before rebuilding summaries or retrieving papers.
        if turn_type == "casual_chat":
            logger.info(
                "[FOLLOWUP_QUERY] scope=%s question=%r effective_question=%r rewritten=%r genes=%s phenotypes=%s state_genes=%s",
                "casual_chat",
                question,
                resolution.get("resolved_question") or question,
                "casual/off-topic response",
                [],
                [],
                state.active_genes,
            )
            try:
                answer = (self.llm.chat([
                    {
                        "role": "system",
                        "content": (
                            ui_label(language, "casual_prompt")
                        ),
                    },
                    {"role": "user", "content": question},
                ], timeout=60) or "").strip()
            except Exception:
                answer = ""
            if not answer:
                answer = ui_label(language, "casual_fallback")

            next_state = self.conversation_agent.build_next_state(
                previous_state=state,
                question=question,
                resolution=resolution,
                discussed_genes=state.active_genes,
            )
            return {
                "Generated Answer": answer,
                "References": existing_references or [],
                "Gene Count Used": gene_count,
                "Threshold Used": None,
                "Discussed Genes": state.active_genes,
                "Conversation State": next_state.to_session(),
                "Store In History": False,
            }

        effective_question = resolution.get("resolved_question") or question

        initial_methodology_query = self.local_reference_agent.is_methodology_query(
            f"{question}\n{effective_question}"
        )
        analysis = (
            self.query_agent.analyze(
                effective_question,
                available_genes=available_genes,
                conversation_history=conversation_history,
                default_phenotype=self.primary_phenotype,
            )
            if self.query_agent and not initial_methodology_query
            else {
                "rewritten_query": effective_question,
                "genes": [],
                "phenotypes": [],
                "scope": "general",
                "disease_intent": "disease_neutral",
            }
        )

        resolved_genes = resolution.get("resolved_genes") or []
        if resolved_genes:
            followup_genes = resolved_genes[: self.MAX_SUMMARY_GENES]
        elif analysis.get("scope") == "top10":
            followup_genes = top_gene_symbols[: self.MAX_SUMMARY_GENES]
        elif analysis.get("genes"):
            followup_genes = analysis["genes"][: self.MAX_SUMMARY_GENES]
        else:
            followup_genes = top_gene_symbols[: min(3, self.MAX_SUMMARY_GENES)]

        rewritten_query = analysis.get("rewritten_query") or question
        followup_phenotype = ", ".join(analysis.get("phenotypes") or [])
        combined_methodology_query = f"{question}\n{effective_question}\n{rewritten_query}"
        methodology_query = self.local_reference_agent.is_methodology_query(
            combined_methodology_query
        )
        local_reference_hits = (
            self.local_reference_agent.query_methodology(
                combined_methodology_query,
                top_k=10,
            )
            if methodology_query
            else []
        )

        if methodology_query and local_reference_hits:
            # Methodology questions are fully served by the curated local corpus.
            # Avoid regenerating an individual gene summary or querying literature.
            followup_genes = []
            base = {
                "Detailed Explanation": "",
                "Generated Explanation": "",
                "References": [],
                "RAG Context Compact": "",
                "Gene Count Used": gene_count,
            }
        else:
            emit_progress(progress_callback, "Loading summary context for follow-up")

            def _background_summary_progress(_: str) -> None:
                return

            base = self.build_explanation(
                pid,
                evaluate=False,
                gene_count=gene_count,
                language=language,
                progress_callback=_background_summary_progress,
            )
        logger.info(
            "[FOLLOWUP_QUERY] scope=%s question=%r effective_question=%r rewritten=%r genes=%s phenotypes=%s state_genes=%s",
            analysis.get("scope"),
            question,
            effective_question,
            rewritten_query,
            followup_genes,
            analysis.get("phenotypes"),
            state.active_genes,
        )

        followup_refs: list[dict[str, Any]] = []
        compact_ctx_lines: list[str] = []
        local_methodology_context_lines: list[str] = []
        local_ref_id = 1
        if local_reference_hits:
            emit_progress(progress_callback, "Checking local XPRS/PRS reference notes")
            logger.info(
                "[LOCAL_REFS] methodology_query=%s question=%r hits=%s",
                methodology_query,
                question,
                [
                    {
                        "id": hit.get("id"),
                        "title": hit.get("title"),
                        "heading": hit.get("heading"),
                    }
                    for hit in local_reference_hits
                ],
            )
            for hit in local_reference_hits:
                context_label = hit["title"]
                if hit.get("heading") and hit["heading"] != hit["title"]:
                    context_label = f"{hit['title']} — {hit['heading']}"
                local_methodology_context_lines.append(
                    f"### {context_label}\n{hit['text']}"
                )

        batch_context = (
            self.evidence_agent.interactive_request_batch(progress_callback)
            if followup_genes and hasattr(self.evidence_agent, "interactive_request_batch")
            else nullcontext()
        )
        with batch_context:
            for gene in followup_genes:
                chunks, refs, _ = self.evidence_agent.retrieve_gene_context_for_question(
                    gene,
                    rewritten_query,
                    top_k=6,
                    requested_phenotypes=analysis.get("phenotypes") or [],
                    disease_intent=analysis.get("disease_intent"),
                    progress_callback=progress_callback,
                )
                debug_rows: list[dict[str, Any]] = []
                for chunk, ref in zip(chunks, refs):
                    if not extract_publication_id(ref):
                        continue
                    inferred_phenotypes = infer_phenotypes_from_text(
                        "\n".join(
                            part for part in [
                                ref.get("title") or "",
                                chunk,
                            ] if part
                        )
                    )
                    debug_rows.append({
                        "paperId": extract_publication_id(ref) or None,
                        "title": (ref.get("title") or "Untitled").strip(),
                        "phenotypes": inferred_phenotypes,
                    })
                    compact_ctx_lines.append(f"[{local_ref_id}] [{gene}] {chunk}")
                    followup_refs.append({
                        "n": local_ref_id,
                        "title": (ref.get("title") or "Untitled").strip(),
                        "gene": (ref.get("gene") or gene).strip(),
                        "phenotype": ", ".join(inferred_phenotypes) if inferred_phenotypes else ((ref.get("phenotype") or followup_phenotype or "").strip() or None),
                        "source": (ref.get("source") or "").strip(),
                        "paperId": extract_publication_id(ref) or None,
                        "url": (ref.get("url") or "").strip() or None,
                        "pmid": (ref.get("pmid") or "").strip() or None,
                        "pmcid": (ref.get("pmcid") or "").strip() or None,
                        "doi": (ref.get("doi") or "").strip() or None,
                        "journal": (ref.get("journal") or "").strip() or None,
                        "year": ref.get("year"),
                        "authors": ref.get("authors"),
                        "citationCount": ref.get("citationCount"),
                        "disease_match": ref.get("disease_match"),
                        "source_pool": ref.get("source_pool"),
                        "reranker_score": ref.get("reranker_score"),
                        "target_phenotypes": ref.get("target_phenotypes") or [],
                    })
                    local_ref_id += 1
                logger.info(
                    "[FOLLOWUP_REFS] gene=%s query=%r retrieved=%s",
                    gene,
                    rewritten_query,
                    debug_rows,
                )

        refs = followup_refs or (base.get("References", []) or [])
        n_max = len(refs)

        compact_ctx = "\n".join(compact_ctx_lines).strip()
        if not compact_ctx:
            compact_ctx = (base.get("RAG Context Compact") or "").strip()

        ref_index_lines = []
        for r in refs:
            n = r.get("n")
            title = (r.get("title") or "Untitled").strip()
            gene = (r.get("gene") or "").strip()
            src = (r.get("source") or "").strip()
            if n:
                tag = f"{gene} • {src}" if (gene or src) else ""
                ref_index_lines.append(f"[{n}] {title}" + (f" ({tag})" if tag else ""))

        ref_index = "\n".join(ref_index_lines).strip()

        methodology_background = ""
        if local_methodology_context_lines:
            methodology_background = (
                "\n\nXPRS / PRS methodology notes:\n"
                + "\n".join(local_methodology_context_lines)
            )

        emit_progress(progress_callback, f"Drafting follow-up response with {self.llm.model}")
        answer = self._generate_followup_text(
            background=(
                f"{base.get('Model Safe Context', '')}{methodology_background}"
                if self.minimize_sensitive_context
                else f"{base.get('Detailed Explanation') or base['Generated Explanation']}{methodology_background}"
            ),
            compact_ctx=compact_ctx,
            ref_index=ref_index,
            question=question,
            n_max=n_max,
            language=language,
            methodology_query=methodology_query and bool(local_reference_hits),
        )

        # Normalize grouped citations, then remove any invalid ones
        answer = normalize_citations(answer)

        if n_max > 0:
            def drop_invalid(match: re.Match) -> str:
                k = int(match.group(1))
                return f"[{k}]" if 1 <= k <= n_max else ""
            answer = re.sub(r"\[(\d+)\]", drop_invalid, answer)
        else:
            # if no refs exist, strip any accidental [n]
            answer = re.sub(r"\[(\d+)\]", "", answer)

        cited_followup_numbers = {int(x) for x in re.findall(r"\[(\d+)\]", answer)}
        cited_refs = [r for r in refs if int(r.get("n") or 0) in cited_followup_numbers]

        merged_references, ref_number_map = merge_references_preserve_numbers(existing_references, cited_refs)

        def remap_reference(match: re.Match) -> str:
            current_n = int(match.group(1))
            return f"[{ref_number_map.get(current_n, current_n)}]"

        answer = re.sub(r"\[(\d+)\]", remap_reference, answer)

        next_state = self.conversation_agent.build_next_state(
            previous_state=state,
            question=question,
            resolution=resolution,
            discussed_genes=followup_genes,
        )

        emit_progress(progress_callback, "Formatting follow-up references")
        return {
            "Generated Answer": answer,
            "References": merged_references,
            "Gene Count Used": base.get("Gene Count Used", gene_count),
            "Threshold Used": None,
            "Discussed Genes": followup_genes,
            "Conversation State": next_state.to_session(),
            "Store In History": True,
        }
