from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.question_bank_checks import (
    DEFAULT_EXPECTATIONS,
    expectation_checks,
    general_checks,
    load_expectations,
    refusal_texts,
)
from scripts.run_question_bank import exit_code, load_questions, score

REFUSAL = refusal_texts()[0]


def failed(checks):
    return [c["check"] for c in checks if not c["passed"]]


def write_xlsx(path: Path, rows: list[list[str]]) -> None:
    """A minimal workbook with inline strings, enough for the question-bank reader."""
    def cell(ref, text):
        return f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>'
    sheet_rows = "".join(
        f'<row r="{r}">' + "".join(cell(f"{chr(65 + c)}{r}", text) for c, text in enumerate(row) if text) + "</row>"
        for r, row in enumerate(rows, start=1))
    main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", f'<workbook xmlns="{main}" xmlns:r="{rel}"><sheets>'
                                            '<sheet name="Question bank" sheetId="1" r:id="rId1"/></sheets></workbook>')
        archive.writestr("xl/_rels/workbook.xml.rels",
                         '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                         '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        archive.writestr("xl/worksheets/sheet1.xml", f'<worksheet xmlns="{main}"><sheetData>{sheet_rows}</sheetData></worksheet>')


class GeneralCheckTests(unittest.TestCase):
    def test_percentile_read_as_probability_fails_unless_negated(self):
        self.assertIn("percentile_not_probability",
                      failed(general_checks("There is a 93.0% chance of developing breast cancer.", percentile=93.0)))
        self.assertEqual(failed(general_checks(
            "This is a relative rank, not a 93.0% probability of developing breast cancer.", percentile=93.0)), [])

    def test_absence_claim_fails(self):
        self.assertIn("no_absence_claim",
                      failed(general_checks("The patient has no pathogenic variants.", percentile=None)))
        self.assertEqual(failed(general_checks("No panel finding is recorded for this individual.", percentile=None)), [])

    def test_absence_caveat_passes_but_bare_negation_does_not(self):
        caveat = ("No finding is recorded for the panel, so this does not mean the individual "
                  "has no pathogenic variants.")
        self.assertEqual(failed(general_checks(caveat, percentile=None)), [])
        self.assertEqual(failed(general_checks(
            "This does not mean this individual has no pathogenic variants in related genes.", percentile=None)), [])
        # A "no" earlier in the sentence is not a caveat; the claim still fails.
        self.assertIn("no_absence_claim", failed(general_checks(
            "There are no panel findings, so she has no pathogenic variants.", percentile=None)))

    def test_portal_failure_message_is_not_an_answer(self):
        from scripts.question_bank_checks import failure_texts
        failures = failure_texts()
        self.assertIn("answered", failed(general_checks(failures[0], percentile=None, failures=failures)))
        self.assertEqual(failed(general_checks("A normal answer.", percentile=None, failures=failures)), [])

    def test_identifiers_fail(self):
        self.assertIn("no_pseudonymous_id", failed(general_checks("Individual KP-ABCDEF123456 ...", percentile=None)))
        self.assertIn("no_rsid", failed(general_checks("The variant rs80357906 ...", percentile=None)))

    def test_quoted_percentile_must_match_the_report(self):
        text = "The PRS is higher than about 91.0% of the reference cohort."
        self.assertIn("percentile_matches_report", failed(general_checks(text, percentile=93.0)))
        self.assertEqual(failed(general_checks(text.replace("91.0", "93.0"), percentile=93.04)), [])
        # A premise such as "top 1% of the cohort" is not the report's percentile.
        self.assertEqual(failed(general_checks("A top 1% of the cohort LDL PRS is a rank.", percentile=93.0)), [])


class ExpectationTests(unittest.TestCase):
    def test_refusal_expectations(self):
        self.assertEqual(failed(expectation_checks(REFUSAL, {"refusal": "expected"}, [REFUSAL])), [])
        self.assertEqual(failed(expectation_checks("An answer.", {"refusal": "expected"}, [REFUSAL])), ["refusal_expected"])
        self.assertEqual(failed(expectation_checks(REFUSAL, {"refusal": "not_expected"}, [REFUSAL])), ["no_refusal"])

    def test_phrases_and_patterns(self):
        expectation = {"must_include_any": ["ClinGen"], "must_not_include": ["you should"], "must_match": "[가-힣]"}
        self.assertEqual(failed(expectation_checks("ClinGen 보고서 참고", expectation, [REFUSAL])), [])
        self.assertEqual(sorted(failed(expectation_checks("You should screen.", expectation, [REFUSAL]))),
                         ["excludes_phrase", "includes_expected", "matches_pattern"])

    def test_d03_and_t04_expectations(self):
        from scripts.question_bank_checks import expectation_checks, load_expectations, refusal_texts
        expectations, refusals = load_expectations(), refusal_texts()

        def passes(question_id, answer):
            return all(check["passed"] for check in expectation_checks(answer, expectations[question_id], refusals))

        self.assertTrue(passes("D03", "This report does not include an age-specific breast cancer risk estimate by age 70."))
        self.assertTrue(passes("D03", "The report contains no absolute or lifetime risk."))
        self.assertFalse(passes("D03", "Her risk by age 70 is about 12%."))
        # T04 (strict): checking the report or findings passes; a generic dodge does not.
        self.assertTrue(passes("T04", "The listed ClinGen report is in the adult context, not pediatric-only."))
        self.assertTrue(passes("T04", "This report does not include a 'Pediatric only' entry."))
        self.assertTrue(passes("T04", "No \u201cPediatric only\u201d entry appears in this report."))
        self.assertFalse(passes("T04", "The XPRS documentation does not define the 'Pediatric only' label, so its relevance cannot be determined."))

    def test_shipped_expectations_are_valid(self):
        self.assertTrue(load_expectations(DEFAULT_EXPECTATIONS))

    def test_invalid_expectations_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.json"
            path.write_text(json.dumps({"questions": {"X1": {"refusal": "maybe"}}}))
            with self.assertRaisesRegex(ValueError, "refusal must be one of.*add a reason"):
                load_expectations(path)


class RunnerTests(unittest.TestCase):
    def test_question_bank_reader_numbers_follow_up_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bank.xlsx"
            write_xlsx(path, [
                ["Q ID", "Section", "Topic", "Question (ask in English)", "Answered well?", "Comment"],
                ["D01", "Disease", "PRS", "What does the [disease] percentile mean?", "Good", ""],
                ["", "", "", "And the follow-up?", "", "note"],
            ])
            questions = load_questions(path)
        self.assertEqual([q["id"] for q in questions], ["D01", "D01b"])
        self.assertEqual(questions[1]["section"], "Disease")
        self.assertEqual(questions[1]["comment"], "note")

    def test_score_and_exit_code(self):
        def result(question_id, answer, status="ok"):
            return {"id": question_id, "individual_role": "general", "status": status, "answer": answer,
                    "error": None if status == "ok" else "timeout"}
        payload = {"run": {"percentiles": {"general": 93.0}},
                   "results": [result("Q1", "Higher than about 93.0% of the cohort."), result("Q2", REFUSAL)]}
        score(payload, {"Q2": {"refusal": "not_expected", "reason": "test"}})
        self.assertEqual(payload["summary"]["failed"], ["Q2"])
        self.assertEqual(exit_code(payload), 1)
        payload["results"].append(result("Q3", "", status="failed"))
        score(payload, {})
        self.assertEqual(exit_code(payload), 2)


if __name__ == "__main__":
    unittest.main()
