from __future__ import annotations

import pandas as pd
from pathlib import Path

from kpredict_data import gene_contribution_frame


class GeneImportanceAgent:
    def __init__(
        self,
        csv_path: str,
        default_top_n: int = 5,
        default_thr: float = 10.0,
    ):
        self.csv_path = csv_path
        self.data = pd.read_csv(csv_path)
        self.default_top_n = default_top_n
        self.default_thr = default_thr

        numeric_cols = self.data.columns[1:]
        self.population_importance = (
            self.data
            .assign(population_mean=self.data[numeric_cols].mean(axis=1))
            .sort_values("population_mean", ascending=False)
            .reset_index(drop=True)
        )
        self.population_importance["population_rank"] = self.population_importance.index + 1
        self.population_lookup = (
            self.population_importance.loc[:, ["Gene", "population_rank", "population_mean"]]
            .set_index("Gene")
            .to_dict(orient="index")
        )

    def get_top_genes(
        self,
        pid: str,
        top_n: int | None = None,
        thr: float | None = None,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:

        if pid not in self.data.columns:
            raise ValueError(f"Individual {pid} not in CSV.")

        if top_n is None:
            top_n = self.default_top_n
        if thr is None:
            thr = self.default_thr

        df = self.data[["Gene", pid]].rename(columns={pid: "contribution"})
        top = df.nlargest(top_n, "contribution").copy()
        top["population_rank"] = top["Gene"].map(
            lambda g: self.population_lookup.get(g, {}).get("population_rank")
        )
        top["population_mean"] = top["Gene"].map(
            lambda g: self.population_lookup.get(g, {}).get("population_mean")
        )
        sig = (
            df[df["contribution"] > thr]
            .nlargest(5, "contribution")
        )

        return top, sig

    def get_bottom_genes(
        self,
        pid: str,
        bottom_n: int | None = None,
    ) -> pd.DataFrame:

        if pid not in self.data.columns:
            raise ValueError(f"Individual {pid} not in CSV.")

        if bottom_n is None:
            bottom_n = self.default_top_n

        df = self.data[["Gene", pid]].rename(columns={pid: "contribution"})
        bottom = df.nsmallest(bottom_n, "contribution").copy()
        bottom["population_rank"] = bottom["Gene"].map(
            lambda g: self.population_lookup.get(g, {}).get("population_rank")
        )
        bottom["population_mean"] = bottom["Gene"].map(
            lambda g: self.population_lookup.get(g, {}).get("population_mean")
        )
        return bottom


class KPredictGeneImportanceAgent:
    """Read one K-PREDICT contribution column without loading the full matrix."""

    def __init__(self, root: Path, disease: str, default_top_n: int = 5):
        self.root = Path(root)
        self.disease = disease
        self.default_top_n = default_top_n
        self.default_thr = None

    def _frame(self, pid: str) -> pd.DataFrame:
        frame = gene_contribution_frame(self.root, self.disease, pid)
        # The handoff appends asterisks to repeated region-level symbols to
        # keep row labels unique. Literature retrieval needs canonical symbols,
        # and one symbol should not occupy several summary slots.
        frame["Gene"] = frame["Gene"].str.replace(r"\*+$", "", regex=True)
        return frame

    def get_top_genes(
        self,
        pid: str,
        top_n: int | None = None,
        thr: float | None = None,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        del thr
        count = top_n or self.default_top_n
        top = (
            self._frame(pid)
            .sort_values("contribution", ascending=False)
            .drop_duplicates("Gene", keep="first")
            .head(count)
            .copy()
        )
        return top, pd.DataFrame(columns=top.columns)

    def get_bottom_genes(self, pid: str, bottom_n: int | None = None) -> pd.DataFrame:
        count = bottom_n or self.default_top_n
        return (
            self._frame(pid)
            .sort_values("contribution", ascending=True)
            .drop_duplicates("Gene", keep="first")
            .head(count)
            .copy()
        )


# ============================================================
# 5. Evidence Assembly Agent (RAG + OT + S2)
# ============================================================
