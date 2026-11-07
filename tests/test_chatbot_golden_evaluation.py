from __future__ import annotations

import unittest

from scripts.evaluate_chatbot_quality import (
    DEFAULT_CASES,
    grade_case,
    load_corpus,
    validate_corpus,
)


class ChatbotGoldenEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = load_corpus(DEFAULT_CASES)

    def test_corpus_has_four_balanced_quality_categories(self):
        self.assertEqual(validate_corpus(self.corpus), [])
        categories = {case["category"] for case in self.corpus["cases"]}
        self.assertEqual(categories, {
            "citation_grounding",
            "evidence_scarcity",
            "bilingual_output",
            "clinical_safety",
        })
        self.assertGreaterEqual(len(self.corpus["cases"]), 15)

    def test_grounding_grader_rejects_ghost_citations_and_causal_overstatement(self):
        case = next(item for item in self.corpus["cases"] if item["id"] == "ground-kcnq1-direct")
        result = grade_case(
            case,
            answer="KCNQ1 causes type 2 diabetes [2].",
        )
        self.assertFalse(result["automated_pass"])
        failed = {item["name"] for item in result["checks"] if not item["passed"]}
        self.assertIn("citation-range", failed)
        self.assertIn("noncausal-framing", failed)

    def test_scarcity_grader_accepts_an_explicit_no_evidence_answer(self):
        case = next(item for item in self.corpus["cases"] if item["id"] == "scarcity-no-evidence")
        result = grade_case(
            case,
            answer="No citable evidence was supplied that links MOV10 directly to pancreatic cancer.",
        )
        self.assertTrue(result["automated_pass"])

    def test_bilingual_grader_requires_preserved_gene_number_and_citation(self):
        case = next(item for item in self.corpus["cases"] if item["id"] == "bilingual-lowering-ko")
        result = grade_case(
            case,
            answer="CDKAL1의 음수 기여도는 이 모델 안에서 상대적인 의미를 가지며 임상적 보호를 뜻하지 않습니다.",
        )
        self.assertFalse(result["automated_pass"])
        failed = {item["name"] for item in result["checks"] if not item["passed"]}
        self.assertIn("required:-0.42", failed)
        self.assertIn("preserve:-0.42", failed)


if __name__ == "__main__":
    unittest.main()
