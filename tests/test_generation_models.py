import json
import unittest

from tests.support import ROOT


class GenerationModelTests(unittest.TestCase):
    def setUp(self):
        self.model_config = json.loads(
            (ROOT / "models.json").read_text(encoding="utf-8")
        )

    def test_generation_allowlist_has_two_frontier_and_two_open_weight_models(self):
        models = self.model_config["generation"]
        self.assertEqual(
            [model["id"] for model in models],
            [
                "openai/gpt-5.6-sol",
                "anthropic/claude-opus-5",
                "qwen/qwen3.8-27b",
                "google/gemma-4-31b-it",
            ],
        )
        self.assertTrue(models[0]["default"])
        self.assertIn("open-weight", models[2]["label"])
        self.assertIn("open-weight", models[3]["label"])

    def test_reference_extraction_default_remains_gpt_5_mini(self):
        models = self.model_config["reference_extraction"]
        default = next(model for model in models if model.get("default"))
        self.assertEqual(default["id"], "openai/gpt-5-mini")

    def test_answer_model_select_is_visible_without_a_settings_menu(self):
        html = (ROOT / "static" / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn('id="generation-model-select"', html)
        self.assertNotIn('id="settings-menu"', html)
        self.assertNotIn('id="settings-menu-btn"', html)
        self.assertNotIn("chatbot-model-dot", html)
        self.assertNotIn("chatbot-model-label", html)
        model_row = html[html.index('class="generation-model-control"') :]
        model_row = model_row[: model_row.index("</div>")]
        self.assertLess(
            model_row.index('id="header-generate-btn"'),
            model_row.index('id="generation-model-select"'),
        )
        self.assertNotIn(">Answer model</label>", model_row)
        self.assertNotIn('aria-label="Refresh"', html)

    def test_public_environment_default_matches_ui_default(self):
        template = (ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn("LLM_MODEL=openai/gpt-5.6-sol", template)

    def test_llm_transport_uses_openrouter_without_legacy_direct_providers(self):
        source = (ROOT / "llm_utils.py").read_text(encoding="utf-8")

        self.assertIn('LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openrouter")', source)
        self.assertIn('if provider == "openrouter":', source)
        self.assertNotIn("OPENAI_API_KEY", source)
        self.assertNotIn("QWEN_API_KEY", source)
        self.assertNotIn('if provider == "openai":', source)
        self.assertNotIn('if provider == "qwen":', source)


if __name__ == "__main__":
    unittest.main()
