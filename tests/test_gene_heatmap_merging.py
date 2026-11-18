from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from kpredict_data import _add_snp_sharing_links, cross_disease_gene_heatmap

PEOPLE = ["person-1", "person-2", "person-3", "person-4", "person-5"]
FILLERS = [f"FILLER{i}" for i in range(36)]
SYMBOLS = ["GENEA", "GENEB", "GENEA*", "NA_1"] + FILLERS  # 40 genes: top 5% = 2 genes per disease


def contribution_matrix() -> np.ndarray:
    """Genes x people. person-1 is far above the cohort on GENEA, GENEB and NA_1."""
    matrix = np.ones((len(SYMBOLS), len(PEOPLE)))
    matrix[4:, 1:] = [0.9, 1.1, 1.0, 1.0]       # fillers vary a little; person-1 sits at their mean
    matrix[0] = [10.0, 0.0, 1.0, 2.0, 1.0]      # GENEA
    matrix[1] = [6.0, 1.0, 1.0, 2.0, 0.0]       # GENEB, shares SNPs with GENEA
    matrix[2] = [3.0, 1.0, 1.0, 2.0, 0.0]       # "GENEA*" duplicate row, weaker
    matrix[3] = [50.0, 0.0, 1.0, 2.0, 1.0]      # unannotated window: must be excluded
    return matrix


def write_disease(root: Path, slug: str, matrix: np.ndarray) -> None:
    folder = root / "diseases" / slug
    folder.mkdir(parents=True)
    pd.DataFrame({
        "matrix_row": range(len(SYMBOLS)), "symbol": SYMBOLS, "chr": "1",
        "start": [i * 1000 for i in range(len(SYMBOLS))], "end": [i * 1000 + 500 for i in range(len(SYMBOLS))],
        # Deliberately wrong reference columns: the heatmap must use the cohort itself.
        "mean": 100.0, "variance": 1.0, "within_region_rank_by_variance": 1,
        "snps_sharing_genes": ["", "GENEA"] + [""] * (len(SYMBOLS) - 2),
    }).to_parquet(folder / "genes.parquet", index=False)
    pd.DataFrame({"individual_id": PEOPLE, "matrix_column": range(len(PEOPLE)), "sex": "F", "raw_prs": 1.0,
                  "z": 0.0, "percentile": 50.0, "applicable": True}).to_parquet(folder / "individual_risk.parquet", index=False)
    matrix.astype("<f4").T.tofile(folder / "contributions.f32")  # column-major: one person per column
    (folder / "matrix.json").write_text(json.dumps({"data_file": "contributions.f32", "shape": list(matrix.shape)}))


class GeneHeatmapTests(unittest.TestCase):
    def test_links_are_recorded_in_both_directions(self):
        links: dict[str, set[str]] = {}
        _add_snp_sharing_links(links, pd.DataFrame({"symbol": ["A*", "B", "C"], "snps_sharing_genes": ["B;C*", "", None]}))
        self.assertEqual(links, {"A": {"B", "C"}, "B": {"A"}, "C": {"A"}})

    def test_values_use_cohort_reference_and_snp_sharing_genes_share_a_row(self):
        matrix = contribution_matrix()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for slug in ("breast_cancer", "type2_diabetes"):
                write_disease(root, slug, matrix)
            (root / "manifest.json").write_text(json.dumps({"diseases": [
                {"portal_disease_slug": "breast_cancer"}, {"portal_disease_slug": "type2_diabetes"}]}))
            payload = cross_disease_gene_heatmap(root, "person-1", top_fraction=0.05, min_diseases=2)

        self.assertEqual(payload["genes"], ["GENEA"])                       # NA_1 excluded, GENEA* collapsed
        self.assertEqual(payload["gene_metrics"][0]["linked_genes"], ["GENEB"])
        self.assertEqual(payload["selection"]["locus_count"], 1)
        expected = (matrix[0, 0] - matrix[0].mean()) / matrix[0].std()      # cohort mean/SD, not the table's "mean"
        self.assertAlmostEqual(payload["values"][0][0], expected, places=5)
        self.assertAlmostEqual(payload["values"][0][1], expected, places=5)


if __name__ == "__main__":
    unittest.main()
