from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import gaussian_kde

from disease_registry import DISEASE_REGISTRY
from kpredict_schema import PORTAL_DISEASE_ORDER, normalize_kpredict_disease


@lru_cache(maxsize=1)
def _manifest(root_string: str) -> dict:
    return json.loads((Path(root_string) / "manifest.json").read_text(encoding="utf-8"))


def available_diseases(root: Path) -> dict[str, dict]:
    return {
        item["portal_disease_slug"]: item
        for item in _manifest(str(root)).get("diseases", [])
        if (root / "diseases" / item["portal_disease_slug"]).is_dir()
    }


@lru_cache(maxsize=16)
def _risk(root_string: str, disease: str) -> pd.DataFrame:
    return pd.read_parquet(Path(root_string) / "diseases" / disease / "individual_risk.parquet")


@lru_cache(maxsize=16)
def _genes(root_string: str, disease: str) -> pd.DataFrame:
    return pd.read_parquet(Path(root_string) / "diseases" / disease / "genes.parquet")


def individual_ids(root: Path, disease: str | None = None) -> list[str]:
    diseases = available_diseases(root)
    selected = disease if disease in diseases else next(iter(diseases), None)
    if not selected:
        return []
    return _risk(str(root), selected)["individual_id"].astype(str).tolist()


def risk_filtered_individuals(
    root: Path,
    disease: str,
    *,
    percentile_min: float = 0.0,
    percentile_max: float = 100.0,
    order: str = "desc",
    limit: int = 5000,
) -> dict:
    """Find applicable individuals by disease-specific cohort percentile."""
    configured = available_diseases(root)
    if disease not in configured:
        raise ValueError("No K-PREDICT data are available for this disease")
    percentile_min = float(percentile_min)
    percentile_max = float(percentile_max)
    if not 0 <= percentile_min <= percentile_max <= 100:
        raise ValueError("Percentile bounds must satisfy 0 <= minimum <= maximum <= 100")
    if order not in {"asc", "desc"}:
        raise ValueError("Order must be 'asc' or 'desc'")
    limit = max(1, min(int(limit), 5000))

    risk = _risk(str(root), disease).copy()
    risk["percentile"] = pd.to_numeric(risk["percentile"], errors="coerce")
    applicable = risk.loc[
        risk["applicable"].fillna(False)
        & risk["percentile"].notna()
    ].copy()
    matching = applicable.loc[
        applicable["percentile"].between(
            percentile_min,
            percentile_max,
            inclusive="both",
        )
    ].copy()
    matching["individual_id"] = matching["individual_id"].astype(str)
    matching = matching.sort_values(
        ["percentile", "individual_id"],
        ascending=[order == "asc", True],
        kind="stable",
    )
    records = [
        {
            "individual_id": str(row.individual_id),
            "percentile": float(row.percentile),
        }
        for row in matching.head(limit).itertuples(index=False)
    ]
    config = DISEASE_REGISTRY.get(disease)
    return {
        "disease": disease,
        "display_name": config.display_name if config is not None else disease,
        "percentile_min": percentile_min,
        "percentile_max": percentile_max,
        "order": order,
        "applicable_count": int(len(applicable)),
        "matching_count": int(len(matching)),
        "returned_count": len(records),
        "results": records,
    }


def cohort_analysis(
    root: Path,
    disease: str,
    *,
    rare_status: str = "all",
    percentile_min: float = 0.0,
    percentile_max: float = 100.0,
    gene: str = "",
    consequence: str = "",
    individual_limit: int = 200,
) -> dict:
    """Aggregate disease-level PRS and panel-linked rare-variant evidence.

    Distribution data are returned as five-percentile bins rather than
    individual values. Pseudonymous IDs are exposed only in the explicitly
    filtered and capped drill-down list.
    """
    active_disease = normalize_kpredict_disease(disease)
    if active_disease not in available_diseases(root):
        raise ValueError("No K-PREDICT data are available for this disease")
    if rare_status not in {"all", "alert", "carrier", "none"}:
        raise ValueError("Rare-variant status must be all, alert, carrier, or none")
    percentile_min = float(percentile_min)
    percentile_max = float(percentile_max)
    if not 0 <= percentile_min <= percentile_max <= 100:
        raise ValueError("Percentile bounds must satisfy 0 <= minimum <= maximum <= 100")
    individual_limit = max(1, min(int(individual_limit), 200))
    selected_gene = str(gene or "").strip()
    selected_consequence = str(consequence or "").strip()

    risk = _risk(str(root), active_disease).copy()
    risk["individual_id"] = risk["individual_id"].astype(str)
    risk["percentile"] = pd.to_numeric(risk["percentile"], errors="coerce")
    cohort = risk.loc[
        risk["applicable"].fillna(False) & risk["percentile"].notna(),
        ["individual_id", "percentile"],
    ].copy()

    rare = _rare_findings(str(root)).copy()
    rare["individual_id"] = rare["individual_id"].astype(str)
    rare["xprs_disease"] = rare["xprs_disease"].fillna("").map(
        normalize_kpredict_disease
    )
    panel = rare.loc[
        rare["track"].fillna("").eq("panel")
        & rare["xprs_disease"].eq(active_disease)
        & rare["individual_id"].isin(cohort["individual_id"])
    ].copy()
    panel["gene"] = panel["gene"].fillna("").astype(str).str.strip()
    panel["consequence"] = panel["consequence"].fillna("").astype(str).str.strip()
    panel["moi_call"] = panel["moi_call"].fillna("").astype(str).str.lower()
    finding_key = "finding_id" if "finding_id" in panel else "variant"
    panel = panel.drop_duplicates(["individual_id", finding_key, "xprs_disease"])

    alert_ids = set(panel.loc[panel["moi_call"].eq("alert"), "individual_id"])
    carrier_ids = set(panel.loc[panel["moi_call"].eq("carrier"), "individual_id"]) - alert_ids
    cohort["rare_status"] = "none"
    cohort.loc[cohort["individual_id"].isin(carrier_ids), "rare_status"] = "carrier"
    cohort.loc[cohort["individual_id"].isin(alert_ids), "rare_status"] = "alert"

    status_labels = {
        "alert": "Panel alert",
        "carrier": "Carrier only",
        "none": "No panel finding",
    }
    bin_edges = np.arange(0.0, 105.0, 5.0)
    distributions: list[dict] = []
    for status in ("alert", "carrier", "none"):
        values = cohort.loc[cohort["rare_status"].eq(status), "percentile"].to_numpy(dtype=float)
        counts, _ = np.histogram(values, bins=bin_edges)
        cumulative = np.cumsum(counts)
        cumulative_percent = (
            (cumulative / values.size * 100.0).tolist()
            if values.size
            else [0.0] * len(counts)
        )
        distributions.append({
            "status": status,
            "label": status_labels[status],
            "count": int(values.size),
            "bin_upper_bounds": bin_edges[1:].tolist(),
            "bin_counts": counts.astype(int).tolist(),
            "cumulative_percent": cumulative_percent,
            "q1": float(np.quantile(values, 0.25)) if values.size else None,
            "median": float(np.quantile(values, 0.5)) if values.size else None,
            "q3": float(np.quantile(values, 0.75)) if values.size else None,
        })

    filtered = cohort.loc[
        cohort["percentile"].between(percentile_min, percentile_max, inclusive="both")
    ].copy()
    if rare_status != "all":
        filtered = filtered.loc[filtered["rare_status"].eq(rare_status)].copy()

    filtered_panel = panel.copy()
    if selected_gene:
        filtered_panel = filtered_panel.loc[filtered_panel["gene"].eq(selected_gene)]
    if selected_consequence:
        filtered_panel = filtered_panel.loc[
            filtered_panel["consequence"].eq(selected_consequence)
        ]
    if selected_gene or selected_consequence:
        filtered = filtered.loc[
            filtered["individual_id"].isin(filtered_panel["individual_id"])
        ].copy()

    matching_ids = set(filtered["individual_id"])
    analysis_panel = panel.loc[panel["individual_id"].isin(matching_ids)].copy()
    if selected_gene:
        analysis_panel = analysis_panel.loc[analysis_panel["gene"].eq(selected_gene)]
    if selected_consequence:
        analysis_panel = analysis_panel.loc[
            analysis_panel["consequence"].eq(selected_consequence)
        ]
    analysis_panel = analysis_panel.merge(
        cohort[["individual_id", "percentile"]],
        on="individual_id",
        how="left",
    )

    gene_rows: list[dict] = []
    for gene_name, rows in analysis_panel.loc[analysis_panel["gene"].ne("")].groupby(
        "gene",
        sort=False,
    ):
        distinct = rows.drop_duplicates("individual_id")
        gene_rows.append({
            "gene": str(gene_name),
            "individual_count": int(distinct["individual_id"].nunique()),
            "alert_count": int(
                rows.loc[rows["moi_call"].eq("alert"), "individual_id"].nunique()
            ),
            "carrier_count": int(
                rows.loc[rows["moi_call"].eq("carrier"), "individual_id"].nunique()
            ),
            "median_percentile": float(distinct["percentile"].median()),
            "top_10_percent_count": int(
                distinct.loc[distinct["percentile"].ge(90), "individual_id"].nunique()
            ),
        })
    gene_rows.sort(
        key=lambda row: (
            -row["individual_count"],
            -row["alert_count"],
            row["gene"],
        )
    )

    panel_by_individual = panel.groupby("individual_id", sort=False)
    filtered = filtered.sort_values(["percentile", "individual_id"], ascending=[False, True])
    individual_rows: list[dict] = []
    for row in filtered.head(individual_limit).itertuples(index=False):
        if row.individual_id in panel_by_individual.groups:
            findings = panel_by_individual.get_group(row.individual_id)
            genes = sorted({value for value in findings["gene"] if value})
            alert_count = int(findings["moi_call"].eq("alert").sum())
            carrier_count = int(findings["moi_call"].eq("carrier").sum())
        else:
            genes = []
            alert_count = 0
            carrier_count = 0
        individual_rows.append({
            "individual_id": str(row.individual_id),
            "percentile": float(row.percentile),
            "rare_status": str(row.rare_status),
            "genes": genes,
            "alert_count": alert_count,
            "carrier_count": carrier_count,
        })

    config = DISEASE_REGISTRY.get(active_disease)
    options_genes = sorted({value for value in panel["gene"] if value})
    options_consequences = sorted({value for value in panel["consequence"] if value})
    return {
        "disease": active_disease,
        "disease_label": (
            config.display_name
            if config is not None
            else active_disease.replace("_", " ").title()
        ),
        "summary": {
            "applicable_count": int(len(cohort)),
            "alert_individual_count": int(cohort["rare_status"].eq("alert").sum()),
            "carrier_individual_count": int(cohort["rare_status"].eq("carrier").sum()),
            "no_panel_finding_count": int(cohort["rare_status"].eq("none").sum()),
            "top_10_percent_count": int(cohort["percentile"].ge(90).sum()),
            "top_10_alert_overlap_count": int(
                (cohort["percentile"].ge(90) & cohort["rare_status"].eq("alert")).sum()
            ),
        },
        "distribution": {
            "bin_width": 5,
            "groups": distributions,
        },
        "filters": {
            "rare_status": rare_status,
            "percentile_min": percentile_min,
            "percentile_max": percentile_max,
            "gene": selected_gene or None,
            "consequence": selected_consequence or None,
        },
        "filter_options": {
            "genes": options_genes,
            "consequences": options_consequences,
        },
        "filtered": {
            "matching_count": int(len(filtered)),
            "returned_count": len(individual_rows),
            "individual_limit": individual_limit,
            "individuals": individual_rows,
            "genes": gene_rows[:100],
        },
    }


def risk_profile(root: Path, disease: str, individual_id: str) -> dict:
    risk = _risk(str(root), disease)
    row = risk.loc[risk["individual_id"] == individual_id]
    if row.empty:
        raise ValueError("Individual is not present in this disease dataset")
    record = row.iloc[0]
    if not bool(record["applicable"]):
        raise ValueError("This disease model is not applicable to the selected individual")
    return {
        "percentile": float(record["percentile"]),
        "prs_value": float(record["raw_prs"]),
    }


def gene_contribution_frame(root: Path, disease: str, individual_id: str) -> pd.DataFrame:
    disease_dir = root / "diseases" / disease
    risk = _risk(str(root), disease)
    selected = risk.loc[risk["individual_id"] == individual_id]
    if selected.empty:
        raise ValueError("Individual is not present in this disease dataset")
    if not bool(selected.iloc[0]["applicable"]):
        raise ValueError("This disease model is not applicable to the selected individual")
    column = int(selected.iloc[0]["matrix_column"])
    matrix_meta = json.loads((disease_dir / "matrix.json").read_text(encoding="utf-8"))
    gene_count, individual_count = [int(value) for value in matrix_meta["shape"]]
    contributions = np.memmap(
        disease_dir / matrix_meta["data_file"],
        dtype="<f4",
        mode="r",
        shape=(gene_count, individual_count),
        order="F",
    )[:, column]
    genes = _genes(str(root), disease)
    frame = pd.DataFrame({
        "Gene": genes["symbol"].astype(str),
        "contribution": np.asarray(contributions, dtype=float),
        "population_mean": pd.to_numeric(genes["mean"], errors="coerce"),
        "population_variance": pd.to_numeric(genes["variance"], errors="coerce"),
    })
    for column in (
        "matrix_row",
        "chr",
        "start",
        "end",
        "within_region_rank_by_variance",
    ):
        frame[column] = genes[column].to_numpy() if column in genes else pd.NA
    population_rank = frame["population_variance"].rank(method="min", ascending=False)
    frame["population_rank"] = population_rank.astype("Int64")
    return frame


def _representative_gene_contributions(
    root: Path,
    disease: str,
    individual_id: str,
) -> pd.DataFrame:
    """Return the canonical gene rows used by the Manhattan plot.

    The handoff can contain several rows for one gene and identifies one
    population-variance representative per genomic region. Keeping this
    selection in one helper ensures that plot outliers and the integrated
    evidence panel describe the same genes on the same contribution scale.
    """
    frame = gene_contribution_frame(root, disease, individual_id)
    rank = pd.to_numeric(frame["within_region_rank_by_variance"], errors="coerce")
    if rank.notna().any():
        frame = frame.loc[rank.eq(1)].copy()
    else:
        frame = frame.copy()
    frame["Gene"] = (
        frame["Gene"]
        .astype(str)
        .str.replace(r"\*+$", "", regex=True)
        .str.strip()
    )
    frame["contribution"] = pd.to_numeric(frame["contribution"], errors="coerce")
    frame = frame.loc[
        frame["Gene"].ne("")
        & ~frame["Gene"].str.match(r"^NA(?:_|$)", na=False)
        & np.isfinite(frame["contribution"])
    ].copy()
    frame["absolute_contribution"] = frame["contribution"].abs()
    return (
        frame.sort_values("absolute_contribution", ascending=False, kind="stable")
        .drop_duplicates("Gene", keep="first")
    )


@lru_cache(maxsize=32)
def _density_curve(root_string: str, disease: str) -> tuple[list[float], list[float], list[float]]:
    risk = _risk(root_string, disease)
    cohort = risk.loc[risk["applicable"].fillna(False), "raw_prs"].dropna().astype(float).to_numpy()
    if cohort.size < 2:
        return cohort.tolist(), [], []
    low, high = float(cohort.min()), float(cohort.max())
    padding = max((high - low) * 0.08, 1e-6)
    x = np.linspace(low - padding, high + padding, 256)
    y = gaussian_kde(cohort)(x)
    return cohort.tolist(), x.tolist(), y.tolist()


def density_data(root: Path, disease: str, individual_id: str) -> dict:
    profile = risk_profile(root, disease, individual_id)
    cohort, x, y = _density_curve(str(root), disease)
    percentile = float(profile["percentile"]) / 100.0
    return {
        "density": {"x": x, "y": y},
        "prs_value": float(profile["prs_value"]),
        "percentile": percentile,
        "label": f"{percentile * 100:.2f}th percentile",
        "cohort_prs": cohort,
        "title": f"K-PREDICT risk density ({individual_id})",
        "x_label": "PRS",
        "y_label": "Density",
    }


def disease_overview(root: Path, individual_id: str) -> dict[str, dict | None]:
    result: dict[str, dict | None] = {}
    for disease in available_diseases(root):
        try:
            result[disease] = density_data(root, disease, individual_id)
        except ValueError:
            result[disease] = None
    return result


def panel_finding_counts_by_disease(root: Path, individual_id: str) -> dict[str, dict]:
    """Count only validated disease-panel findings for one individual."""
    rare = _rare_findings(str(root))
    individual_rare = rare.loc[rare["individual_id"].astype(str).eq(individual_id)].copy()
    individual_rare["xprs_disease"] = individual_rare["xprs_disease"].fillna("").map(
        normalize_kpredict_disease
    )
    panel_rare = individual_rare.loc[individual_rare["track"].fillna("").eq("panel")]
    return {
        str(disease): {
            "finding_count": int(len(rows)),
            "alert_count": int(rows["moi_call"].eq("alert").sum()),
            "carrier_count": int(rows["moi_call"].eq("carrier").sum()),
        }
        for disease, rows in panel_rare.groupby("xprs_disease", sort=False)
        if disease
    }


def manhattan_data(root: Path, disease: str, individual_id: str) -> dict:
    representative = _representative_gene_contributions(root, disease, individual_id)
    representative["chr_number"] = pd.to_numeric(representative["chr"], errors="coerce")
    representative = representative.loc[representative["chr_number"].between(1, 22)].copy()
    representative["chr_number"] = representative["chr_number"].astype(int)
    representative["pos"] = (
        pd.to_numeric(representative["start"], errors="coerce")
        + pd.to_numeric(representative["end"], errors="coerce")
    ) / 2.0
    representative = representative.dropna(subset=["pos"]).sort_values(["chr_number", "pos"])

    offsets: dict[int, float] = {}
    centers: list[dict] = []
    offset = 0.0
    for chromosome, group in representative.groupby("chr_number", sort=True):
        offsets[int(chromosome)] = offset
        minimum, maximum = float(group["pos"].min()), float(group["pos"].max())
        centers.append({"chr": int(chromosome), "center": offset + (minimum + maximum) / 2.0})
        offset += maximum + 10_000_000.0

    points = []
    for row in representative.itertuples(index=False):
        value = float(row.contribution)
        if not np.isfinite(value):
            continue
        chromosome = int(row.chr_number)
        position = float(row.pos)
        points.append({
            "gene": str(row.Gene),
            "chr": chromosome,
            "pos": position,
            "x": offsets[chromosome] + position,
            "contribution": value,
            # Retained for compatibility with older cached frontend code.
            "variance": value,
        })
    return {
        "points": points,
        "chr_centers": centers,
        "title": f"K-PREDICT gene contributions ({individual_id})",
        "y_label": "Gene contribution",
    }


def cross_disease_gene_heatmap(
    root: Path,
    individual_id: str,
    *,
    top_fraction: float = 0.0025,
    min_diseases: int = 3,
    max_genes: int = 20,
) -> dict:
    """Build a compact, variance-standardized gene-by-disease matrix.

    Genes qualify when they fall in the strongest absolute within-disease
    fraction in multiple applicable models. This recurrence-aware selection
    favors shared cross-disease patterns rather than a union of disconnected
    disease-specific extremes. Raw gene contribution scales are not compared
    directly: each value is divided by the square root of the supplied
    population variance for that gene row.
    """
    top_fraction = max(0.0005, min(float(top_fraction), 0.05))
    min_diseases = max(2, min(int(min_diseases), 6))
    max_genes = max(8, min(int(max_genes), 30))
    configured = available_diseases(root)
    disease_values: dict[str, pd.Series] = {}
    disease_rows: list[dict] = []

    for disease in PORTAL_DISEASE_ORDER:
        if disease not in configured:
            continue
        config = DISEASE_REGISTRY.get(disease)
        display_name = (
            config.display_name
            if config is not None
            else disease.replace("_", " ").title()
        )
        try:
            frame = gene_contribution_frame(root, disease, individual_id)
        except ValueError:
            disease_rows.append({
                "slug": disease,
                "display_name": display_name,
                "applicable": False,
            })
            continue

        frame["Gene"] = (
            frame["Gene"]
            .astype(str)
            .str.replace(r"\*+$", "", regex=True)
            .str.strip()
        )
        variance = pd.to_numeric(frame["population_variance"], errors="coerce")
        contribution = pd.to_numeric(frame["contribution"], errors="coerce")
        valid = (
            frame["Gene"].ne("")
            & ~frame["Gene"].str.match(r"^NA(?:_|$)", na=False)
            & variance.gt(0)
            & np.isfinite(contribution)
            & np.isfinite(variance)
        )
        frame = frame.loc[valid, ["Gene"]].copy()
        frame["standardized_contribution"] = (
            contribution.loc[valid] / np.sqrt(variance.loc[valid])
        )
        frame = frame.loc[np.isfinite(frame["standardized_contribution"])].copy()
        frame["absolute_standardized_contribution"] = frame[
            "standardized_contribution"
        ].abs()
        frame = (
            frame.sort_values(
                "absolute_standardized_contribution",
                ascending=False,
                kind="stable",
            )
            .drop_duplicates("Gene", keep="first")
        )
        values = frame.set_index("Gene")["standardized_contribution"]
        disease_values[disease] = values
        disease_rows.append({
            "slug": disease,
            "display_name": display_name,
            "applicable": True,
        })

    applicable_diseases = [row for row in disease_rows if row["applicable"]]
    if not applicable_diseases:
        raise ValueError("Individual is not applicable to any configured disease model")
    if not disease_values:
        raise ValueError("No variance-standardized gene contributions are available")

    full_matrix = pd.DataFrame(disease_values)
    effective_min_diseases = min(min_diseases, len(applicable_diseases))
    qualifying = pd.DataFrame(
        False,
        index=full_matrix.index,
        columns=full_matrix.columns,
    )
    for disease in full_matrix.columns:
        values = full_matrix[disease].dropna().abs()
        selection_count = max(1, int(np.ceil(len(values) * top_fraction)))
        qualifying.loc[values.nlargest(selection_count).index, disease] = True

    support = qualifying.sum(axis=1).astype(int)
    qualifying_magnitude = full_matrix.abs().where(qualifying).mean(axis=1)
    candidate_metrics = pd.DataFrame({
        "support": support,
        "qualifying_magnitude": qualifying_magnitude,
    })
    candidate_metrics = candidate_metrics.loc[
        candidate_metrics["support"].ge(effective_min_diseases)
    ]
    if candidate_metrics.empty:
        raise ValueError(
            "No genes meet the cross-disease recurrence threshold for this individual"
        )
    candidate_metrics = candidate_metrics.sort_values(
        ["support", "qualifying_magnitude"],
        ascending=False,
        kind="stable",
    ).head(max_genes)
    selected_genes = candidate_metrics.index.astype(str).tolist()

    matrix: list[list[float | None]] = []
    finite_values: list[float] = []
    for gene in selected_genes:
        row: list[float | None] = []
        for disease in applicable_diseases:
            value = disease_values[disease["slug"]].get(gene)
            numeric = float(value) if value is not None and np.isfinite(value) else None
            row.append(numeric)
            if numeric is not None:
                finite_values.append(numeric)
        matrix.append(row)

    absolute = np.abs(np.asarray(finite_values, dtype=float))
    color_limit = float(np.quantile(absolute, 0.95)) if absolute.size else 1.0
    color_limit = max(2.0, min(color_limit, 8.0))
    gene_metrics = [
        {
            "gene": gene,
            "qualifying_disease_count": int(candidate_metrics.loc[gene, "support"]),
            "applicable_disease_count": len(applicable_diseases),
            "mean_absolute_qualifying_contribution": float(
                candidate_metrics.loc[gene, "qualifying_magnitude"]
            ),
        }
        for gene in selected_genes
    ]
    return {
        "individual_id": individual_id,
        "genes": selected_genes,
        "gene_metrics": gene_metrics,
        "diseases": applicable_diseases,
        "unavailable_diseases": [row for row in disease_rows if not row["applicable"]],
        "values": matrix,
        "selection": {
            "top_fraction": top_fraction,
            "minimum_qualifying_diseases": effective_min_diseases,
            "maximum_genes": max_genes,
            "candidate_count": int(
                (
                    support.ge(effective_min_diseases)
                ).sum()
            ),
        },
        "color_limit": color_limit,
        "color_limit_absolute_quantile": 0.95,
        "normalization": "contribution / sqrt(population variance)",
    }


@lru_cache(maxsize=16)
def population_gene_architecture(
    root: Path,
    *,
    percentile_threshold: float = 99.0,
    min_diseases: int = 3,
    max_genes: int = 24,
) -> dict:
    """Compare population gene-contribution variance across disease models.

    Raw contribution variances are model-specific and therefore should not be
    compared directly between diseases. Each gene is instead assigned its
    within-model variance percentile. Genes shown in the prototype must reach
    the requested percentile in several diseases, which favors shared
    population-level architecture rather than one disease's largest signals.
    """
    percentile_threshold = max(50.0, min(float(percentile_threshold), 99.9))
    min_diseases = max(2, min(int(min_diseases), 6))
    max_genes = max(8, min(int(max_genes), 40))
    configured = available_diseases(root)
    percentile_values: dict[str, pd.Series] = {}
    raw_variances: dict[str, pd.Series] = {}
    disease_rows: list[dict] = []

    for disease in PORTAL_DISEASE_ORDER:
        if disease not in configured:
            continue
        config = DISEASE_REGISTRY.get(disease)
        display_name = (
            config.display_name
            if config is not None
            else disease.replace("_", " ").title()
        )
        genes = _genes(str(root), disease).copy()
        representative_rank = pd.to_numeric(
            genes.get("within_region_rank_by_variance"),
            errors="coerce",
        )
        if representative_rank.notna().any():
            genes = genes.loc[representative_rank.eq(1)].copy()
        genes["gene"] = (
            genes["symbol"]
            .astype(str)
            .str.replace(r"\*+$", "", regex=True)
            .str.strip()
        )
        genes["population_variance"] = pd.to_numeric(
            genes["variance"],
            errors="coerce",
        )
        genes = genes.loc[
            genes["gene"].ne("")
            & ~genes["gene"].str.match(r"^NA(?:_|$)", na=False)
            & genes["population_variance"].gt(0)
            & np.isfinite(genes["population_variance"])
        ].copy()
        genes = (
            genes.sort_values("population_variance", ascending=False, kind="stable")
            .drop_duplicates("gene", keep="first")
        )
        if genes.empty:
            continue
        genes["variance_percentile"] = (
            genes["population_variance"].rank(method="max", pct=True) * 100.0
        )
        percentile_values[disease] = genes.set_index("gene")["variance_percentile"]
        raw_variances[disease] = genes.set_index("gene")["population_variance"]
        risk = _risk(str(root), disease)
        disease_rows.append({
            "slug": disease,
            "display_name": display_name,
            "applicable_count": int(risk["applicable"].fillna(False).sum()),
            "gene_count": int(len(genes)),
        })

    if not percentile_values:
        raise ValueError("No population gene-variance data are available")
    effective_min_diseases = min(min_diseases, len(disease_rows))
    percentile_matrix = pd.DataFrame(percentile_values)
    qualifying = percentile_matrix.ge(percentile_threshold)
    support = qualifying.sum(axis=1).astype(int)
    qualifying_mean = percentile_matrix.where(qualifying).mean(axis=1)
    peak = percentile_matrix.max(axis=1)
    candidate_metrics = pd.DataFrame({
        "support": support,
        "qualifying_mean": qualifying_mean,
        "peak": peak,
    })
    candidate_metrics = candidate_metrics.loc[
        candidate_metrics["support"].ge(effective_min_diseases)
    ].sort_values(
        ["support", "qualifying_mean", "peak"],
        ascending=False,
        kind="stable",
    )
    if candidate_metrics.empty:
        raise ValueError(
            "No genes meet the shared population-architecture threshold"
        )
    candidate_count = int(len(candidate_metrics))
    selected_genes = candidate_metrics.head(max_genes).index.astype(str).tolist()

    percentile_rows: list[list[float | None]] = []
    variance_rows: list[list[float | None]] = []
    for gene in selected_genes:
        percentile_row: list[float | None] = []
        variance_row: list[float | None] = []
        for disease in disease_rows:
            slug = disease["slug"]
            percentile = percentile_values[slug].get(gene)
            variance = raw_variances[slug].get(gene)
            percentile_row.append(
                float(percentile) if percentile is not None and np.isfinite(percentile) else None
            )
            variance_row.append(
                float(variance) if variance is not None and np.isfinite(variance) else None
            )
        percentile_rows.append(percentile_row)
        variance_rows.append(variance_row)

    return {
        "genes": selected_genes,
        "gene_metrics": [
            {
                "gene": gene,
                "qualifying_disease_count": int(candidate_metrics.loc[gene, "support"]),
                "disease_count": len(disease_rows),
                "mean_qualifying_percentile": float(
                    candidate_metrics.loc[gene, "qualifying_mean"]
                ),
                "peak_percentile": float(candidate_metrics.loc[gene, "peak"]),
            }
            for gene in selected_genes
        ],
        "diseases": disease_rows,
        "values": percentile_rows,
        "raw_variances": variance_rows,
        "selection": {
            "percentile_threshold": percentile_threshold,
            "minimum_qualifying_diseases": effective_min_diseases,
            "maximum_genes": max_genes,
            "candidate_count": candidate_count,
        },
        "metric": "within-disease percentile of population gene-contribution variance",
        "prototype": True,
    }


@lru_cache(maxsize=1)
def _rare_findings(root_string: str) -> pd.DataFrame:
    return pd.read_parquet(Path(root_string) / "rare_findings.parquet")


RARE_FINDING_DETAIL_FIELDS = (
    "finding_id",
    "track",
    "xprs_disease",
    "xprs_disease_label",
    "gene",
    "variant",
    "hgvs",
    "rsid",
    "genotype",
    "moi_call",
    "moi_why",
    "panelapp_moi",
    "panelapp_n_panels",
    "clingen_moi",
    "clingen_tier",
    "clingen_detail",
    "clnsig",
    "stars",
    "tier",
    "category",
    "consequence",
    "consequence_class",
    "clinvar_conditions",
    "gnomad_af",
    "gnomad_af_eas",
    "eas_specific",
    "cohort_af",
    "qc_pass",
    "qc_flags",
)


def _json_scalar(value):
    """Convert a nullable pandas value to a JSON-safe scalar."""
    if value is None or pd.isna(value):
        return None
    return value.item() if hasattr(value, "item") else value


def _rare_finding_records(source: pd.DataFrame) -> list[dict]:
    """Return the complete non-identifying annotation for each finding row."""
    records: list[dict] = []
    for row in source.itertuples(index=False):
        values = row._asdict()
        records.append({
            field: _json_scalar(values.get(field))
            for field in RARE_FINDING_DETAIL_FIELDS
        })
    return records


def rare_findings(root: Path, individual_id: str, disease: str) -> dict:
    frame = _rare_findings(str(root))
    rows = frame.loc[frame["individual_id"] == individual_id].copy()
    rows["xprs_disease"] = rows["xprs_disease"].fillna("").map(
        normalize_kpredict_disease
    )
    active_disease = normalize_kpredict_disease(disease)
    panel_rows = rows.loc[rows["track"].fillna("").eq("panel")]
    unassigned_rows = rows.loc[rows["track"].fillna("").eq("other")]
    active_rows = panel_rows.loc[panel_rows["xprs_disease"].eq(active_disease)]
    other_panel_rows = panel_rows.loc[~panel_rows["xprs_disease"].eq(active_disease)]

    def group(source: pd.DataFrame, disease_slug: str, disease_label: str) -> dict:
        return {
            "disease": disease_slug,
            "disease_label": disease_label,
            "finding_count": int(len(source)),
            "alert_count": int(source["moi_call"].eq("alert").sum()),
            "carrier_count": int(source["moi_call"].eq("carrier").sum()),
            "findings": _rare_finding_records(source),
        }

    active_config = DISEASE_REGISTRY.get(active_disease)
    active_label = (
        active_config.display_name
        if active_config is not None
        else active_disease.replace("_", " ").title()
    )
    other_groups: list[dict] = []
    present_diseases = set(other_panel_rows["xprs_disease"].astype(str))
    ordered_diseases = [
        slug for slug in PORTAL_DISEASE_ORDER if slug in present_diseases
    ]
    ordered_diseases.extend(sorted(present_diseases.difference(ordered_diseases)))
    for disease_slug in ordered_diseases:
        disease_rows = other_panel_rows.loc[
            other_panel_rows["xprs_disease"].eq(disease_slug)
        ]
        labels = disease_rows["xprs_disease_label"].dropna().astype(str)
        config = DISEASE_REGISTRY.get(disease_slug)
        disease_label = (
            config.display_name
            if config is not None
            else (labels.iloc[0] if not labels.empty else disease_slug.replace("_", " ").title())
        )
        other_groups.append(group(disease_rows, disease_slug, disease_label))

    active_group = group(active_rows, active_disease, active_label)
    unassigned_group = {
        "finding_count": int(len(unassigned_rows)),
        "alert_count": int(unassigned_rows["moi_call"].eq("alert").sum()),
        "carrier_count": int(unassigned_rows["moi_call"].eq("carrier").sum()),
        "findings": _rare_finding_records(unassigned_rows),
    }

    return {
        "individual_id": individual_id,
        "disease": active_disease,
        "finding_count": int(len(rows)),
        "alert_count": int((rows["moi_call"] == "alert").sum()),
        "carrier_count": int((rows["moi_call"] == "carrier").sum()),
        "panel_finding_count": int(len(panel_rows)),
        "unassigned_finding_count": int(len(unassigned_rows)),
        "active_disease_group": active_group,
        "other_disease_groups": other_groups,
        "unassigned_group": unassigned_group,
        # Compatibility aliases for any clients using the first API shape.
        "disease_findings": active_group["findings"],
        "other_findings": unassigned_group["findings"],
    }


def disease_evidence_summary(
    root: Path,
    individual_id: str,
    disease: str,
    *,
    gene_limit: int = 2,
) -> dict:
    """Join common- and rare-variant evidence without combining their scores.

    Common-variant genes use the same representative rows and raw contribution
    scale as the individual Manhattan plot. Variance standardization remains
    specific to the cross-disease heatmap, where disease models must be made
    comparable.
    Rare-variant results are deliberately restricted to the active disease
    panel; findings from other panels and unassigned findings remain in the
    full rare-variant analysis view.
    """
    gene_limit = max(1, min(int(gene_limit), 5))
    active_disease = normalize_kpredict_disease(disease)
    profile = risk_profile(root, active_disease, individual_id)
    frame = _representative_gene_contributions(
        root,
        active_disease,
        individual_id,
    )
    variance = pd.to_numeric(frame["population_variance"], errors="coerce")
    contribution = pd.to_numeric(frame["contribution"], errors="coerce")
    valid = (
        np.isfinite(contribution)
    )
    ranked = frame.loc[valid, [
        "Gene",
        "contribution",
        "population_rank",
        "population_variance",
    ]].copy()
    ranked["standardized_contribution"] = np.where(
        variance.loc[valid].gt(0) & np.isfinite(variance.loc[valid]),
        contribution.loc[valid] / np.sqrt(variance.loc[valid]),
        np.nan,
    )

    def gene_records(source: pd.DataFrame) -> list[dict]:
        records: list[dict] = []
        for row in source.itertuples(index=False):
            population_rank = getattr(row, "population_rank", None)
            records.append({
                "gene": str(row.Gene),
                "contribution": float(row.contribution),
                "standardized_contribution": float(row.standardized_contribution),
                "population_variance_rank": (
                    int(population_rank)
                    if population_rank is not None and not pd.isna(population_rank)
                    else None
                ),
            })
        return records

    increasing = ranked.loc[
        ranked["contribution"].gt(0)
    ].nlargest(gene_limit, "contribution")
    lowering = ranked.loc[
        ranked["contribution"].lt(0)
    ].nsmallest(gene_limit, "contribution")
    active_rare_group = rare_findings(
        root,
        individual_id,
        active_disease,
    )["active_disease_group"]
    config = DISEASE_REGISTRY.get(active_disease)

    return {
        "individual_id": individual_id,
        "disease": active_disease,
        "disease_label": (
            config.display_name
            if config is not None
            else active_disease.replace("_", " ").title()
        ),
        "common_variant": {
            "percentile": profile["percentile"],
            "prs_value": profile["prs_value"],
            "increasing_genes": gene_records(increasing),
            "lowering_genes": gene_records(lowering),
            "scale": "raw gene contribution",
        },
        "rare_variant": active_rare_group,
        "combined_score": None,
    }


def rare_findings_overview(root: Path, individual_id: str) -> dict:
    """Group one individual's rare findings by unique gene/variant.

    The source handoff stores one row per disease-panel assignment, so the
    same biological variant can occur several times. The overview collapses
    those rows and retains the associated disease panels as badges.
    """
    frame = _rare_findings(str(root))
    rows = frame.loc[frame["individual_id"].astype(str).eq(individual_id)].copy()
    if rows.empty:
        return {
            "individual_id": individual_id,
            "assignment_count": 0,
            "variant_count": 0,
            "gene_count": 0,
            "alert_count": 0,
            "carrier_count": 0,
            "variants": [],
        }
    rows["xprs_disease"] = rows["xprs_disease"].fillna("").map(
        normalize_kpredict_disease
    )
    rows["gene"] = rows["gene"].fillna("").astype(str)
    rows["variant"] = rows["variant"].fillna("").astype(str)
    rows["_variant_key"] = rows.apply(
        lambda row: (
            row["gene"],
            row["variant"]
            or str(row.get("hgvs") or "")
            or str(row.get("rsid") or "")
            or str(row.get("finding_id") or ""),
        ),
        axis=1,
    )

    variants: list[dict] = []
    for _, group in rows.groupby("_variant_key", sort=False):
        first = group.iloc[0]
        panel_rows = group.loc[group["track"].fillna("").eq("panel")]
        present_diseases = set(panel_rows["xprs_disease"].astype(str)) - {""}
        ordered_diseases = [
            slug for slug in PORTAL_DISEASE_ORDER if slug in present_diseases
        ]
        ordered_diseases.extend(sorted(present_diseases.difference(ordered_diseases)))
        disease_records = []
        for disease_slug in ordered_diseases:
            config = DISEASE_REGISTRY.get(disease_slug)
            labels = panel_rows.loc[
                panel_rows["xprs_disease"].eq(disease_slug),
                "xprs_disease_label",
            ].dropna().astype(str)
            disease_records.append({
                "slug": disease_slug,
                "display_name": (
                    config.display_name
                    if config is not None
                    else (labels.iloc[0] if not labels.empty else disease_slug.replace("_", " ").title())
                ),
            })

        calls = set(group["moi_call"].fillna("").astype(str))
        call = "alert" if "alert" in calls else ("carrier" if "carrier" in calls else "")

        def first_value(column: str):
            values = group[column].dropna() if column in group else pd.Series(dtype=object)
            if values.empty:
                return None
            value = values.iloc[0]
            return value.item() if hasattr(value, "item") else value

        panel_assignments: list[dict] = []
        for disease_slug in ordered_diseases:
            disease_rows = panel_rows.loc[
                panel_rows["xprs_disease"].eq(disease_slug)
            ]
            if disease_rows.empty:
                continue
            assignment = _rare_finding_records(disease_rows.iloc[[0]])[0]
            config = DISEASE_REGISTRY.get(disease_slug)
            labels = disease_rows["xprs_disease_label"].dropna().astype(str)
            assignment["disease"] = disease_slug
            assignment["disease_label"] = (
                config.display_name
                if config is not None
                else (labels.iloc[0] if not labels.empty else disease_slug.replace("_", " ").title())
            )
            panel_assignments.append(assignment)

        variants.append({
            "finding_id": first_value("finding_id"),
            "gene": str(first["gene"]),
            "variant": str(first["variant"]),
            "hgvs": first_value("hgvs"),
            "rsid": first_value("rsid"),
            "genotype": first_value("genotype"),
            "call": call,
            "clnsig": first_value("clnsig"),
            "stars": int(first_value("stars") or 0),
            "tier": first_value("tier"),
            "consequence": first_value("consequence"),
            "consequence_class": first_value("consequence_class"),
            "clinvar_conditions": first_value("clinvar_conditions"),
            "moi_why": first_value("moi_why"),
            "panelapp_moi": first_value("panelapp_moi"),
            "panelapp_n_panels": first_value("panelapp_n_panels"),
            "clingen_moi": first_value("clingen_moi"),
            "clingen_tier": first_value("clingen_tier"),
            "clingen_detail": first_value("clingen_detail"),
            "category": first_value("category"),
            "gnomad_af": first_value("gnomad_af"),
            "gnomad_af_eas": first_value("gnomad_af_eas"),
            "eas_specific": first_value("eas_specific"),
            "cohort_af": first_value("cohort_af"),
            "qc_pass": first_value("qc_pass"),
            "qc_flags": first_value("qc_flags"),
            "diseases": disease_records,
            "panel_assignments": panel_assignments,
            "unassigned": bool(group["track"].fillna("").eq("other").any()),
            "assignment_count": int(len(group)),
        })

    tier_rank = {"HIGH": 0, "MODERATE": 1, "LOW": 2}
    variants.sort(key=lambda item: (
        0 if item["call"] == "alert" else 1,
        0 if item["diseases"] else 1,
        -len(item["diseases"]),
        tier_rank.get(str(item["tier"]).upper(), 9),
        item["gene"],
    ))
    return {
        "individual_id": individual_id,
        "assignment_count": int(len(rows)),
        "variant_count": len(variants),
        "gene_count": len({item["gene"] for item in variants if item["gene"]}),
        "alert_count": sum(item["call"] == "alert" for item in variants),
        "carrier_count": sum(item["call"] == "carrier" for item in variants),
        "variants": variants,
    }
