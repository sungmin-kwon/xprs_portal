from __future__ import annotations

import pandas as pd


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


# ============================================================
# 5. Evidence Assembly Agent (RAG + OT + S2)
# ============================================================

