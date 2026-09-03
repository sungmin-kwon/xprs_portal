import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import gaussian_kde

from disease_registry import DiseaseConfig, enabled_disease_config


def plot_cache_paths(disease: str | None = None) -> dict[str, Path]:
    config = enabled_disease_config(disease)
    return {
        "annotated_info": config.plot_cache_dir / "annotated_info.parquet",
        "prs_info": config.plot_cache_dir / "prs_info.parquet",
        "full_prs": config.plot_cache_dir / "full_prs.parquet",
    }


class PlotDataStore:
    def __init__(
        self,
        annotated_info: pd.DataFrame,
        prs_info: pd.DataFrame,
        full_prs: pd.DataFrame,
        disease_config: DiseaseConfig,
    ):
        self.annotated_info = annotated_info
        self.prs_info = prs_info
        self.full_prs = full_prs
        self.disease_config = disease_config

    def validate_individual_id(self, individual_id: str) -> None:
        if individual_id not in self.prs_info.columns:
            raise ValueError(f"Individual '{individual_id}' not found in PRS_info.")

    def manhattan_plot_data(self, individual_id: str, use_midpoint: bool = True) -> dict[str, Any]:
        self.validate_individual_id(individual_id)

        ann = self.annotated_info.loc[:, ["chr", "symbol", "start", "end"]].copy()
        ann["BP"] = (
            (pd.to_numeric(ann["start"], errors="coerce") + pd.to_numeric(ann["end"], errors="coerce")) / 2
            if use_midpoint
            else pd.to_numeric(ann["start"], errors="coerce")
        )

        ann["CHR"] = (
            ann["chr"]
            .astype(str)
            .str.replace(r"^chr", "", regex=True, case=False)
        )
        ann = ann[ann["CHR"].isin([str(i) for i in range(1, 23)])].copy()
        ann["CHR"] = pd.to_numeric(ann["CHR"], errors="coerce").astype("Int64")
        ann = ann.dropna(subset=["BP", "CHR"]).copy()

        if len(self.prs_info) != len(ann):
            raise ValueError("Row counts differ between PRS_info and annotated_info; need a symbol-based merge.")

        ann["ATTR"] = pd.to_numeric(self.prs_info[individual_id], errors="coerce")
        ann = ann[np.isfinite(ann["ATTR"])].copy()
        ann = ann.sort_values(["CHR", "BP"]).reset_index(drop=True)

        chr_sizes = (
            ann.groupby("CHR", as_index=False)["BP"]
            .max()
            .rename(columns={"BP": "chr_len"})
            .sort_values("CHR")
            .reset_index(drop=True)
        )
        chr_sizes["chr_start"] = chr_sizes["chr_len"].cumsum().shift(fill_value=0)
        ann = ann.merge(chr_sizes.loc[:, ["CHR", "chr_start"]], on="CHR", how="left")
        ann["x"] = ann["BP"] + ann["chr_start"]

        chr_centers = (
            ann.groupby("CHR", as_index=False)["x"]
            .agg(center=lambda s: (s.min() + s.max()) / 2)
            .sort_values("CHR")
            .reset_index(drop=True)
        )

        points = [
            {
                "gene": str(row.symbol),
                "chr": int(row.CHR),
                "pos": float(row.BP),
                "x": float(row.x),
                "variance": float(row.ATTR),
            }
            for row in ann.itertuples(index=False)
        ]

        return {
            "points": points,
            "chr_centers": [
                {"chr": int(row.CHR), "center": float(row.center)}
                for row in chr_centers.itertuples(index=False)
            ],
            "title": f"{self.disease_config.display_name} Gene-based Manhattan Plot (Individual: {individual_id})",
            "y_label": "Gene Contribution Var.",
        }

    def prs_density_data(self, individual_id: str, label_digits: int = 2) -> dict[str, Any]:
        self.validate_individual_id(individual_id)

        if not {"IID", "PRS"}.issubset(self.full_prs.columns):
            raise ValueError("full_prs must contain columns: IID, PRS")

        prs_all = pd.to_numeric(self.full_prs["PRS"], errors="coerce")
        prs_all = prs_all[np.isfinite(prs_all)].to_numpy(dtype=float)
        if prs_all.size == 0:
            raise ValueError("No valid PRS values found in full_prs.")

        prs_matches = pd.to_numeric(
            self.full_prs.loc[self.full_prs["IID"] == individual_id, "PRS"],
            errors="coerce",
        )
        prs_matches = prs_matches[np.isfinite(prs_matches)]
        if len(prs_matches) != 1:
            raise ValueError("Invalid PRS value for individual.")

        prs_value = float(prs_matches.iloc[0])
        percentile = float(np.mean(prs_all <= prs_value))
        label = f"Bottom {percentile * 100:.{label_digits}f} %"

        kde = gaussian_kde(prs_all)
        std = float(np.std(prs_all))
        pad = max(std * 0.5, 0.1)
        x_vals = np.linspace(float(prs_all.min() - pad), float(prs_all.max() + pad), 512)
        y_vals = kde(x_vals)

        return {
            "density": {
                "x": x_vals.astype(float).tolist(),
                "y": y_vals.astype(float).tolist(),
            },
            "prs_value": prs_value,
            "percentile": percentile,
            "label": label,
            "cohort_prs": prs_all.astype(float).tolist(),
            "title": f"{self.disease_config.display_name} Cohort Risk Density (Individual: {individual_id})",
            "x_label": "PRS",
            "y_label": "Density",
        }

    def build_plot_payload(self, individual_id: str) -> dict[str, Any]:
        return {
            "manhattan": self.manhattan_plot_data(individual_id),
            "density": self.prs_density_data(individual_id),
        }


def _missing_data_message(config: DiseaseConfig) -> str:
    paths = plot_cache_paths(config.slug)
    return (
        f"Missing Python-native plot cache files for {config.display_name}. Expected: "
        f"{paths['annotated_info']}, {paths['prs_info']}, and {paths['full_prs']}."
    )


@lru_cache(maxsize=None)
def load_plot_data_store(disease: str = "breast_cancer") -> PlotDataStore:
    config = enabled_disease_config(disease)
    paths = plot_cache_paths(config.slug)
    if not all(path.exists() for path in paths.values()):
        raise FileNotFoundError(_missing_data_message(config))

    annotated_info = pd.read_parquet(paths["annotated_info"])
    prs_info = pd.read_parquet(paths["prs_info"])
    full_prs = pd.read_parquet(paths["full_prs"])
    return PlotDataStore(
        annotated_info=annotated_info,
        prs_info=prs_info,
        full_prs=full_prs,
        disease_config=config,
    )


def write_plotdata_files(individual_id: str, out_dir: Path, disease: str = "breast_cancer") -> dict[str, Path]:
    config = enabled_disease_config(disease)
    store = load_plot_data_store(config.slug)
    payload = store.build_plot_payload(individual_id)

    out_dir.mkdir(parents=True, exist_ok=True)
    manhattan_path = out_dir / f"{individual_id}_manhattan.json"
    density_path = out_dir / f"{individual_id}_density.json"

    with open(manhattan_path, "w", encoding="utf-8") as f:
        json.dump(payload["manhattan"], f, ensure_ascii=False)
    with open(density_path, "w", encoding="utf-8") as f:
        json.dump(payload["density"], f, ensure_ascii=False)

    return {
        "manhattan": manhattan_path,
        "density": density_path,
    }
