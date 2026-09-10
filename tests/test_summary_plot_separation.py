from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SummaryPlotSeparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = (ROOT / "static" / "dashboard.js").read_text(encoding="utf-8")

    def test_summary_generation_does_not_reload_plots(self):
        start = self.script.index("async function generateSummary()")
        end = self.script.index("// Follow-up chat", start)
        summary_flow = self.script[start:end]

        self.assertNotIn("loadPlotsForIndividual", summary_flow)
        self.assertNotIn("resetVisualizations", summary_flow)
        self.assertNotIn("resetDashboardForIndividualChange", summary_flow)
        self.assertNotIn("viz-status", summary_flow)
        self.assertNotIn("Loading plots", summary_flow)

    def test_visualizations_are_reset_only_when_the_individual_changes(self):
        reset_start = self.script.index("function resetConversationState()")
        reset_end = self.script.index("function getReferenceIdentity", reset_start)
        reset_flow = self.script[reset_start:reset_end]
        change_start = self.script.index("async function changeIndividual()")
        change_end = self.script.index("// Summary generation", change_start)
        change_flow = self.script[change_start:change_end]

        self.assertNotIn("resetVisualizations();", reset_flow.split("function resetDashboardForIndividualChange")[0])
        self.assertIn("resetVisualizations();", reset_flow)
        self.assertIn("resetDashboardForIndividualChange();", change_flow)

    def test_summary_failure_is_not_attributed_to_the_selected_model(self):
        start = self.script.index("async function generateSummary()")
        end = self.script.index("// Follow-up chat", start)
        summary_flow = self.script[start:end]
        catch_start = summary_flow.index("} catch (e) {")
        failure_flow = summary_flow[catch_start:]

        self.assertIn("showModel: false", failure_flow)
        self.assertIn("individualId: pid", failure_flow)

    def test_plot_failures_do_not_write_to_chat_status(self):
        change_start = self.script.index("async function changeIndividual()")
        change_end = self.script.index("// Summary generation", change_start)
        change_flow = self.script[change_start:change_end]
        initial_start = self.script.index('window.addEventListener("DOMContentLoaded"')
        initial_plot_start = self.script.index(
            "await loadPlotsForIndividual(initialIndividualId)",
            initial_start,
        )
        initial_plot_end = self.script.index("} else {", initial_plot_start)
        initial_plot_flow = self.script[initial_plot_start:initial_plot_end]

        self.assertNotIn("chat-status", change_flow)
        self.assertNotIn("chat-status", initial_plot_flow)

    def test_stale_combined_flow_name_is_removed(self):
        self.assertNotIn("generateSummaryAndPlots", self.script)
        self.assertIn(
            '$("header-generate-btn")?.addEventListener("click", generateSummary);',
            self.script,
        )

    def test_removed_dashboard_controls_do_not_leave_translation_artifacts(self):
        for stale_key in (
            "portalSubtitle",
            "selectedIndividual",
            "visualizations",
            "referenceModelLabel",
            "welcomeMessage",
            "askQuestion",
            "landingCopy",
            "languageLabel",
            "languageHint",
            "themeLabel",
            "noPaperSelected",
            "noPlotStatus",
            "noChatWelcome",
            "summaryButton",
        ):
            with self.subTest(stale_key=stale_key):
                self.assertNotIn(f"{stale_key}:", self.script)


if __name__ == "__main__":
    unittest.main()
