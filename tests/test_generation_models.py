import json
import unittest

from tests.support import ROOT


class GenerationModelTests(unittest.TestCase):
    def setUp(self):
        self.model_config = json.loads(
            (ROOT / "models.json").read_text(encoding="utf-8")
        )

    def test_generation_allowlist_has_three_frontier_and_two_open_weight_models(self):
        models = self.model_config["generation"]
        self.assertEqual(
            [model["id"] for model in models],
            [
                "openai/gpt-6.1-sol",
                "openai/gpt-6-sol",
                "anthropic/claude-opus-5.5",
                "qwen/qwen3.8-27b",
                "google/gemma-4-31b-it",
            ],
        )
        self.assertTrue(models[1]["default"])
        self.assertEqual(sum(bool(model.get("default")) for model in models), 1)
        self.assertIn("open-weight", models[3]["label"])
        self.assertIn("open-weight", models[4]["label"])

    def test_reference_extraction_default_remains_gpt_5_mini(self):
        models = self.model_config["reference_extraction"]
        default = next(model for model in models if model.get("default"))
        self.assertEqual(default["id"], "openai/gpt-5-mini")

    def test_public_environment_default_matches_ui_default(self):
        template = (ROOT / ".env.example").read_text(encoding="utf-8")
        ui_default = next(m["id"] for m in self.model_config["generation"] if m.get("default"))
        self.assertIn(f"LLM_MODEL={ui_default}\n", template)

    def test_llm_transport_uses_openrouter_without_legacy_direct_providers(self):
        # Direct provider paths would bypass the ZDR settings enforced on every
        # OpenRouter request (see test_openrouter_privacy.py).
        source = (ROOT / "llm_utils.py").read_text(encoding="utf-8")

        self.assertNotIn("OPENAI_API_KEY", source)
        self.assertNotIn("QWEN_API_KEY", source)
        self.assertNotIn('if provider == "openai":', source)
        self.assertNotIn('if provider == "qwen":', source)


if __name__ == "__main__":
    unittest.main()
