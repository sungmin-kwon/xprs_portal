from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from starlette.requests import Request

from routes.plots import plotdata_post
from schemas import PlotsRequest


class PlotRuntimeTests(unittest.TestCase):
    def test_public_plot_payload_is_built_in_memory(self):
        store = Mock()
        store.build_plot_payload.return_value = {
            "manhattan": {"points": []},
            "density": {"density": {"x": [], "y": []}},
        }
        request = Request({"type": "http", "headers": []})

        with patch("routes.plots.load_plot_data_store", return_value=store):
            result = plotdata_post(
                PlotsRequest(
                    individual_id="HG00436",
                    disease="breast_cancer",
                    cohort="1000_genomes",
                ),
                request,
            )

        store.build_plot_payload.assert_called_once_with("HG00436")
        self.assertTrue(result["generated"])
        self.assertIsNone(result["manhattan_url"])
        self.assertIsNone(result["density_url"])


if __name__ == "__main__":
    unittest.main()
