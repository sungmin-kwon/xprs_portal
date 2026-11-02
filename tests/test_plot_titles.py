from __future__ import annotations

import unittest

from tests.support import ROOT


class PlotTitleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = (ROOT / "static" / "dashboard.js").read_text(encoding="utf-8")
        cls.html = (ROOT / "static" / "dashboard.html").read_text(encoding="utf-8")

    def test_card_headers_remain_the_single_visible_plot_titles(self):
        self.assertIn('data-i18n="densityTitle">PRS Density', self.html)
        self.assertIn('data-i18n="manhattanTitle">Individual Manhattan Plot', self.html)

        manhattan_start = self.script.index("function renderManhattanPlotly")
        density_start = self.script.index("function renderDensityPlotly")
        density_end = self.script.index("async function loadAppInfo", density_start)
        manhattan_renderer = self.script[manhattan_start:density_start]
        density_renderer = self.script[density_start:density_end]

        self.assertNotIn("rawTitle", manhattan_renderer)
        self.assertNotIn("text: titleText", manhattan_renderer)
        self.assertNotIn("rawTitle", density_renderer)
        self.assertNotIn("text: titleText", density_renderer)

        self._check_removed_titles_return_vertical_space_to_plots()

    def _check_removed_titles_return_vertical_space_to_plots(self):
        self.assertIn("{ l: 42, r: 14, t: 18, b: 40 }", self.script)
        self.assertIn("margin: { l: 44, r: 16, t: 18, b: 40 }", self.script)


if __name__ == "__main__":
    unittest.main()
