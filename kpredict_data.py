from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import gaussian_kde

from disease_registry import DISEASE_REGISTRY
from actionability import matching_reports
from kpredict_schema import PORTAL_DISEASE_ORDER, TRAIT_GROUPS, normalize_kpredict_disease


@lru_cache(maxsize=1)
def _manifest(root_string: str) -> dict:
    return json.loads((Path(root_string) / "manifest.json").read_text(encoding="utf-8"))


def available_diseases(root: Path) -> dict[str, dict]:
    return {
        item["portal_disease_slug"]: item
        for item in _manifest(str(root)).get("diseases", [])
        if (root / "diseases" / item["portal_disease_slug"]).is_dir()
    }


def _require_known_disease(root_string: str, disease: str) -> None:
    """Only disease slugs listed in the release manifest may become file paths.

    Disease names arrive as request parameters; an unknown name used to reach
    pd.read_parquet and fail with a FileNotFoundError (HTTP 500), and a name
    such as "../x" would otherwise be joined into a path.
    """
    known = {str(item.get("portal_disease_slug")) for item in _manifest(root_string).get("diseases", [])}
    if disease not in known:
        raise ValueError("Unknown disease for this cohort")


@lru_cache(maxsize=16)
def _risk(root_string: str, disease: str) -> pd.DataFrame:
    _require_known_disease(root_string, disease)
    return pd.read_parquet(Path(root_string) / "diseases" / disease / "individual_risk.parquet")


@lru_cache(maxsize=16)
def _genes(root_string: str, disease: str) -> pd.DataFrame:
    _require_known_disease(root_string, disease)
    return pd.read_parquet(Path(root_string) / "diseases" / disease / "genes.parquet")


def applicable_count(root: Path, disease: str) -> int:
    """Number of individuals the disease model applies to (the percentile reference).

    The supplied percentiles equal each individual's rank among these
    applicable K-PREDICT individuals (verified 2026-11-11 against the
    2026-09-17 release: max difference 0.03 percentile points), so this is
    the reference group a percentile is compared with.
    """
    risk = _risk(str(root), disease)
    return int((risk["applicable"].astype(bool) & risk["percentile"].notna()).sum())


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
    rare_status: str = "all",
    gene: str = "",
) -> dict:
    """Find applicable individuals by disease percentile and panel rare-variant findings.

    ``rare_status``: all, alert, carrier, finding (alert or carrier), or none.
    With ``gene``, only individuals with a panel finding in that gene match,
    and the status refers to their findings in that gene.
    """
    if disease not in available_diseases(root):
        raise ValueError("No K-PREDICT data are available for this disease")
    percentile_min = float(percentile_min)
    percentile_max = float(percentile_max)
    if not 0 <= percentile_min <= percentile_max <= 100:
        raise ValueError("Percentile bounds must satisfy 0 <= minimum <= maximum <= 100")
    if order not in {"asc", "desc"}:
        raise ValueError("Order must be 'asc' or 'desc'")
    limit = max(1, min(int(limit), 5000))
    if rare_status not in RARE_STATUS_FILTERS:
        raise ValueError("Rare-variant status must be all, alert, carrier, finding, or none")
    selected_gene = str(gene or "").strip()
    if selected_gene and rare_status == "none":
        raise ValueError("A gene filter needs individuals with a finding in that gene")

    applicable, panel = _panel_cohort(root, disease)
    candidates = applicable
    if selected_gene:
        gene_status = _status_by_individual(panel.loc[panel["gene"].eq(selected_gene)])
        candidates = candidates.loc[candidates["individual_id"].isin(gene_status.index)].copy()
        candidates["rare_status"] = gene_status.reindex(candidates["individual_id"]).to_numpy()
    if rare_status == "finding":
        candidates = candidates.loc[candidates["rare_status"].isin({"alert", "carrier"})]
    elif rare_status != "all":
        candidates = candidates.loc[candidates["rare_status"].eq(rare_status)]
    matching = candidates.loc[
        candidates["percentile"].between(
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
            "rare_status": str(row.rare_status),
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
        "rare_status": rare_status,
        "gene": selected_gene or None,
        "applicable_count": int(len(applicable)),
        "matching_count": int(len(matching)),
        "returned_count": len(records),
        "results": records,
    }


RARE_STATUS_FILTERS = {"all", "alert", "carrier", "finding", "none"}


def _panel_cohort(root: Path, disease: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Applicable individuals with their panel status, and the disease's panel findings.

    Returns ``cohort`` (individual_id, percentile, rare_status in
    alert/carrier/none) and ``panel`` (one row per individual and finding,
    columns include gene, consequence, moi_call). An individual with both an
    alert and a carrier finding counts as "alert".
    """
    active_disease = normalize_kpredict_disease(disease)
    if active_disease not in available_diseases(root):
        raise ValueError("No K-PREDICT data are available for this disease")
    risk = _risk(str(root), active_disease).copy()
    risk["individual_id"] = risk["individual_id"].astype(str)
    risk["percentile"] = pd.to_numeric(risk["percentile"], errors="coerce")
    cohort = risk.loc[
        risk["applicable"].fillna(False) & risk["percentile"].notna(),
        ["individual_id", "percentile"],
    ].copy()

    rare = _rare_findings(str(root)).copy()
    rare["individual_id"] = rare["individual_id"].astype(str)
    rare["xprs_disease"] = rare["xprs_disease"].fillna("").map(normalize_kpredict_disease)
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

    status = _status_by_individual(panel)
    cohort["rare_status"] = status.reindex(cohort["individual_id"]).fillna("none").to_numpy()
    return cohort, panel


def _status_by_individual(panel: pd.DataFrame) -> pd.Series:
    """"alert" if any of an individual's findings is an alert, else "carrier" (index: individual_id)."""
    if panel.empty:
        return pd.Series(dtype=object)
    is_alert = panel["moi_call"].eq("alert").groupby(panel["individual_id"]).any()
    is_carrier = panel["moi_call"].eq("carrier").groupby(panel["individual_id"]).any()
    status = pd.Series("none", index=is_alert.index, dtype=object)
    status[is_carrier] = "carrier"
    status[is_alert] = "alert"
    return status[status.ne("none")]


def panel_gene_options(root: Path, disease: str) -> list[dict]:
    """Genes with panel findings for one disease, for the Overview's individual finder."""
    _cohort, panel = _panel_cohort(root, disease)
    rows = []
    for gene_name, rows_for_gene in panel.loc[panel["gene"].ne("")].groupby("gene", sort=False):
        status = _status_by_individual(rows_for_gene)
        rows.append({
            "gene": str(gene_name),
            "individual_count": int(len(status)),
            "alert_count": int(status.eq("alert").sum()),
            "carrier_count": int(status.eq("carrier").sum()),
        })
    return sorted(rows, key=lambda row: (-row["individual_count"], row["gene"]))


def cohort_analysis(root: Path, disease: str) -> dict:
    """Panel-linked rare-variant findings across the cohort, with their PRS percentiles.

    Returns a cohort summary (including how many alert carriers would be in
    the top 10% by chance), one point per individual and gene with a panel
    finding (no IDs; for the dot plot), and a per-gene table. Finding
    individuals is done on the Overview (risk_filtered_individuals).
    """
    cohort, panel = _panel_cohort(root, disease)
    active_disease = normalize_kpredict_disease(disease)
    percentile_by_id = cohort.set_index("individual_id")["percentile"]
    top_10 = cohort["percentile"].ge(90)
    top_10_share = float(top_10.mean()) if len(cohort) else 0.0
    alert_count = int(cohort["rare_status"].eq("alert").sum())

    points: list[dict] = []
    gene_rows: list[dict] = []
    for gene_name, rows_for_gene in panel.loc[panel["gene"].ne("")].groupby("gene", sort=False):
        status = _status_by_individual(rows_for_gene)
        percentiles = percentile_by_id.reindex(status.index)
        points.extend(
            {"gene": str(gene_name), "status": str(value), "percentile": float(percentile)}
            for value, percentile in zip(status, percentiles)
        )
        gene_rows.append({
            "gene": str(gene_name),
            "individual_count": int(len(status)),
            "alert_count": int(status.eq("alert").sum()),
            "carrier_count": int(status.eq("carrier").sum()),
            "median_percentile": float(percentiles.median()),
            "top_10_percent_count": int(percentiles.ge(90).sum()),
        })
    gene_rows.sort(key=lambda row: (-row["individual_count"], -row["alert_count"], row["gene"]))

    config = DISEASE_REGISTRY.get(active_disease)
    return {
        "disease": active_disease,
        "disease_label": (
            config.display_name if config is not None else active_disease.replace("_", " ").title()
        ),
        "summary": {
            "applicable_count": int(len(cohort)),
            "alert_individual_count": alert_count,
            "carrier_individual_count": int(cohort["rare_status"].eq("carrier").sum()),
            "no_panel_finding_count": int(cohort["rare_status"].eq("none").sum()),
            "top_10_percent_count": int(top_10.sum()),
            "top_10_alert_overlap_count": int((top_10 & cohort["rare_status"].eq("alert")).sum()),
            # If PRS and alerts were unrelated, about this many alert carriers would be in the top 10%.
            "top_10_alert_expected_count": round(alert_count * top_10_share, 1),
        },
        "points": sorted(points, key=lambda point: (point["gene"], point["percentile"])),
        "genes": gene_rows,
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


@lru_cache(maxsize=16)
def _cohort_gene_stats(root_string: str, disease: str) -> tuple[np.ndarray, np.ndarray]:
    """Per-gene mean and SD of contributions over the applicable K-PREDICT individuals.

    Indexed by matrix_row. The gene tables' ``mean`` column is not the cohort
    mean: in release 2026-11-19 it is offset by a median 1.75 (type 2 diabetes)
    to 2.74 (breast cancer) cohort SDs, while ``variance`` matches the cohort.
    The supplied PRS z-scores are standardised against the applicable cohort,
    so gene deviations use the same reference. Computed once per disease by
    streaming person columns (~0.5 GB matrix per disease).
    """
    _require_known_disease(root_string, disease)
    folder = Path(root_string) / "diseases" / disease
    matrix_meta = json.loads((folder / "matrix.json").read_text(encoding="utf-8"))
    gene_count, individual_count = [int(value) for value in matrix_meta["shape"]]
    matrix = np.memmap(folder / matrix_meta["data_file"], dtype="<f4", mode="r",
                       shape=(gene_count, individual_count), order="F")
    risk = _risk(root_string, disease)
    columns = np.sort(risk.loc[risk["applicable"].astype(bool), "matrix_column"].to_numpy(dtype=np.int64))
    if columns.size < 2:
        raise ValueError("Too few applicable individuals to standardise gene contributions")
    total = np.zeros(gene_count)
    squares = np.zeros(gene_count)
    for start in range(0, columns.size, 256):
        block = np.asarray(matrix[:, columns[start:start + 256]], dtype=np.float64)
        total += block.sum(axis=1)
        squares += np.square(block).sum(axis=1)
    mean = total / columns.size
    sd = np.sqrt(np.maximum(squares / columns.size - np.square(mean), 0.0))
    return mean, sd


def _add_snp_sharing_links(links: dict[str, set[str]], genes: pd.DataFrame) -> None:
    """Record, in both directions, which genes share SNPs (from ``snps_sharing_genes``)."""
    if "snps_sharing_genes" not in genes:
        return
    symbols = genes["symbol"].astype(str).str.replace(r"\*+$", "", regex=True).str.strip()
    for symbol, shared in zip(symbols, genes["snps_sharing_genes"].fillna("").astype(str)):
        for other in shared.split(";"):
            other = other.strip().rstrip("*").strip()
            if other and other != symbol:
                links.setdefault(symbol, set()).add(other)
                links.setdefault(other, set()).add(symbol)


def cross_disease_gene_heatmap(
    root: Path,
    individual_id: str,
    *,
    top_fraction: float = 0.0025,
    min_diseases: int = 3,
    max_genes: int = 20,
) -> dict:
    """Genes where one individual differs most from the cohort, across disease models.

    Each cell is the individual's gene contribution relative to the applicable
    K-PREDICT cohort: (contribution - cohort mean) / cohort SD, the same
    reference as the PRS z-score. Gene contributions are not centred on zero,
    and the gene tables' ``mean`` column is not the cohort mean (see
    _cohort_gene_stats), so neither the raw contribution nor that column can
    be used as the reference.

    A gene qualifies when its absolute deviation is in the individual's top
    ``top_fraction`` of genes in at least ``min_diseases`` applicable models.
    Genes that share SNPs (``snps_sharing_genes``) carry the same genotype
    signal, so they are merged into one row, represented by the strongest gene.
    """
    top_fraction = max(0.0005, min(float(top_fraction), 0.05))
    min_diseases = max(2, min(int(min_diseases), 6))
    max_genes = max(8, min(int(max_genes), 30))
    configured = available_diseases(root)
    disease_values: dict[str, pd.Series] = {}
    disease_rows: list[dict] = []
    snp_links: dict[str, set[str]] = {}

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
        cohort_mean, cohort_sd = _cohort_gene_stats(str(root), disease)
        rows = pd.to_numeric(frame["matrix_row"], errors="coerce").astype(int).to_numpy()
        mean = pd.Series(cohort_mean[rows], index=frame.index)
        sd = pd.Series(cohort_sd[rows], index=frame.index)
        contribution = pd.to_numeric(frame["contribution"], errors="coerce")
        valid = (
            frame["Gene"].ne("")
            & ~frame["Gene"].str.match(r"^NA(?:_|$)", na=False)
            & sd.gt(0)
            & np.isfinite(contribution)
            & np.isfinite(mean)
        )
        frame = frame.loc[valid, ["Gene"]].copy()
        frame["standardized_contribution"] = (
            (contribution.loc[valid] - mean.loc[valid]) / sd.loc[valid]
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
        _add_snp_sharing_links(snp_links, _genes(str(root), disease))
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
    )
    # Walk candidates from strongest to weakest; a gene that shares SNPs with
    # an earlier gene joins that gene's row instead of getting its own.
    groups: dict[str, list[str]] = {}
    for gene in candidate_metrics.index.astype(str):
        linked = snp_links.get(gene, set())
        representative = next((rep for rep in groups if rep in linked or gene in snp_links.get(rep, set())), None)
        if representative is not None:
            groups[representative].append(gene)
        else:
            groups[gene] = []
    locus_count = len(groups)
    selected_genes = list(groups)[:max_genes]
    candidate_metrics = candidate_metrics.loc[selected_genes]

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
            "linked_genes": groups[gene],
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
            "locus_count": locus_count,
        },
        "color_limit": color_limit,
        "color_limit_absolute_quantile": 0.95,
        "normalization": "(contribution - cohort mean) / cohort SD, over applicable K-PREDICT individuals",
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


def _with_actionability(record: dict, call: object) -> dict:
    """Attach ClinGen Actionability references to alerts (see actionability.py).

    Carrier findings are, by the supplied classification, single variants for
    recessive conditions, so dominant-condition reports are not attached to them.
    """
    record["actionability"] = matching_reports(record) if str(call or "").lower() == "alert" else []
    return record


def _rare_finding_records(source: pd.DataFrame) -> list[dict]:
    """Return the complete non-identifying annotation for each finding row."""
    records: list[dict] = []
    for row in source.itertuples(index=False):
        values = row._asdict()
        record = {
            field: _json_scalar(values.get(field))
            for field in RARE_FINDING_DETAIL_FIELDS
        }
        records.append(_with_actionability(record, record.get("moi_call")))
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


def available_traits(root: Path) -> list[dict]:
    """Continuous-trait entries of the release manifest whose folder exists (empty before 2026-11-19)."""
    return [
        item for item in _manifest(str(root)).get("traits") or []
        if (root / "traits" / str(item.get("portal_trait_slug") or "")).is_dir()
    ]


@lru_cache(maxsize=64)
def _trait_risk(root_string: str, slug: str) -> pd.DataFrame:
    return pd.read_parquet(Path(root_string) / "traits" / slug / "individual_risk.parquet")


def trait_overview(root: Path, individual_id: str) -> dict:
    """One individual's percentile and z for every continuous trait, grouped for the overview.

    Percentiles are within K-PREDICT (0-100). A higher value means a higher
    genetically predicted trait level, which is not necessarily unfavourable.
    Raises ValueError if the individual is not in the release.
    """
    traits = available_traits(root)
    if not traits:
        return {"individual_id": individual_id, "trait_count": 0, "groups": []}
    by_source = {str(item["source_trait_id"]): item for item in traits}
    order = [(group, ids) for group, ids in TRAIT_GROUPS]
    grouped_ids = {trait_id for _group, ids in TRAIT_GROUPS for trait_id in ids}
    order.append(("other", tuple(sorted(set(by_source) - grouped_ids))))

    groups = []
    for group, ids in order:
        rows = []
        for trait_id in ids:
            item = by_source.get(trait_id)
            if item is None:
                continue
            risk = _trait_risk(str(root), str(item["portal_trait_slug"]))
            row = risk.loc[risk["individual_id"] == individual_id]
            if row.empty:
                raise ValueError("Individual is not present in the trait data")
            record = row.iloc[0]
            applicable = bool(record["applicable"]) and pd.notna(record["percentile"])
            rows.append({
                "slug": str(item["portal_trait_slug"]),
                "source_trait_id": trait_id,
                "label": str(item.get("trait_label") or trait_id),
                "applicable": applicable,
                "percentile": float(record["percentile"]) if applicable else None,
                "z": float(record["z"]) if applicable and pd.notna(record["z"]) else None,
            })
        if rows:
            groups.append({"key": group, "traits": rows})
    return {
        "individual_id": individual_id,
        "trait_count": sum(len(group["traits"]) for group in groups),
        "reference_cohort": str(traits[0].get("reference_cohort") or ""),
        "groups": groups,
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
            # Filled in below, once the record is complete.
            "actionability": [],
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
        _with_actionability(variants[-1], call)

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
