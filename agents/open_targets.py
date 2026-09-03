from __future__ import annotations

import re
from typing import Any, Dict, Optional

import pandas as pd

from text_utils import normalize_output_language


class OpenTargetsAgent:
    def __init__(self, merged_csv: str):
        self.merged_csv = merged_csv
        self._has_granular = False
        self._by_symbol = self._load_and_index()

    @staticmethod
    def _strip_version(x):
        return re.sub(r"\.\d+$", "", str(x)) if pd.notna(x) else x

    def _load_and_index(self) -> Dict[str, Dict[str, Any]]:
        ot_all = pd.read_csv(self.merged_csv)

        if "Gene name" in ot_all.columns:
            ot_all = ot_all.rename(columns={"Gene name": "symbol"})
        elif "symbol" not in ot_all.columns:
            raise ValueError("Merged Open Targets file must contain a 'Gene name' or 'symbol' column.")

        ot_bc = ot_all[ot_all["diseaseId"] == "EFO_0000305"].copy()

        if "targetId" in ot_bc.columns:
            ot_bc["targetId"] = ot_bc["targetId"].astype(str).apply(self._strip_version)

        self._has_granular = all(
            c in ot_bc.columns for c in ["globalScore", "gwasCredibleSets", "europepmc", "cancerGeneCensus"]
        )

        d = ot_bc.copy()
        for col in ["score", "evidenceCount", "globalScore", "gwasCredibleSets", "europepmc", "cancerGeneCensus"]:
            if col in d.columns:
                d[col] = pd.to_numeric(d[col], errors="coerce")

        g = d.groupby("symbol", dropna=False)

        base = g.agg(
            n_assoc=("symbol", "size"),
            score_mean=("score", "mean") if "score" in d.columns else ("symbol", "size"),
            score_max=("score", "max") if "score" in d.columns else ("symbol", "size"),
            evidenceCount_sum=("evidenceCount", "sum") if "evidenceCount" in d.columns else ("symbol", "size"),
        ).fillna(0)

        if self._has_granular:
            extra = g.agg(
                globalScore_max=("globalScore", "max"),
                gwas_mean=("gwasCredibleSets", "mean"),
                lit_mean=("europepmc", "mean"),
                cgc_mean=("cancerGeneCensus", "mean"),
            ).fillna(0)
            base = base.join(extra, how="left").fillna(0)

        return base.to_dict(orient="index")

    def summary(self, gene_symbol: str) -> str:
        stats = self._by_symbol.get(gene_symbol)
        if not stats:
            return f"**Open Targets (Breast Carcinoma) for {gene_symbol}:** No association rows found."

        lines = [f"**Open Targets (Breast Carcinoma) for {gene_symbol}:**"]
        if "score_mean" in stats:
            lines.append(f"- Mean Association Score: **{stats['score_mean']:.3f}**")
            lines.append(f"- Max Association Score: **{stats['score_max']:.3f}**")
        if "evidenceCount_sum" in stats:
            lines.append(f"- Total Evidence Count: **{int(stats['evidenceCount_sum'])}**")
        lines.append(f"- Number of association records: **{int(stats['n_assoc'])}**")

        if self._has_granular:
            lines.append(f"- Max Global Score: **{stats['globalScore_max']:.3f}**")
            lines.append(f"- Mean GWAS Credible Sets: **{stats['gwas_mean']:.3f}**")
            lines.append(f"- Mean Literature (Europe PMC): **{stats['lit_mean']:.3f}**")
            lines.append(f"- Mean Cancer Gene Census: **{stats['cgc_mean']:.3f}**")

        score_for_flag = stats.get("globalScore_max", stats.get("score_max", 0))
        if score_for_flag >= 0.5:
            lines.append("Strong/compelling OT association signal for breast cancer.")
        elif score_for_flag >= 0.2:
            lines.append("Moderate association; consider corroborating evidence.")
        else:
            lines.append("Limited association signal in OT for breast cancer.")

        return "\n".join(lines)

    def structured_stats(self, gene_symbol: str, language: str = "en") -> dict[str, Any] | None:
        stats = self._by_symbol.get(gene_symbol)
        if not stats:
            return None

        is_korean = normalize_output_language(language) == "ko"
        score_for_flag = stats.get("globalScore_max", stats.get("score_max", 0))
        if score_for_flag >= 0.5:
            signal_strength = "strong"
            interpretation = (
                "이 유전자는 Open Targets에서 유방암과 비교적 강한 집계 연관성을 보입니다."
                if is_korean
                else "This gene has a comparatively strong aggregated association with breast carcinoma in Open Targets."
            )
        elif score_for_flag >= 0.2:
            signal_strength = "moderate"
            interpretation = (
                "이 유전자는 Open Targets에서 유방암과 중간 수준의 집계 연관성을 보입니다."
                if is_korean
                else "This gene has a moderate aggregated association with breast carcinoma in Open Targets."
            )
        else:
            signal_strength = "limited"
            interpretation = (
                "이 유전자는 Open Targets에서 유방암과의 집계 연관 근거가 제한적입니다."
                if is_korean
                else "This gene has only limited aggregated association support for breast carcinoma in Open Targets."
            )

        return {
            "database": "Open Targets",
            "gene": gene_symbol,
            "mean_association_score": stats.get("score_mean"),
            "max_association_score": stats.get("score_max"),
            "supporting_evidence_items": stats.get("evidenceCount_sum"),
            "association_records": stats.get("n_assoc"),
            "signal_strength": signal_strength,
            "interpretation": interpretation,
        }

    def doc_for_gene(self, gene: str) -> Optional[Dict[str, Any]]:
        try:
            summary = self.summary(gene)
        except Exception:
            return None
        if not summary:
            return None
        return {
            "id": f"ot::{gene}",
            "text": summary,
            "meta": {"source": "opentargets", "gene": gene},
        }
