import unittest

from pdf_report import _paragraph_text, _reference_markup, build_pdf_report, resolve_fonts
from tests.support import ROOT
FONT_DIR = ROOT / "assets" / "fonts"


class KoreanPdfFontTests(unittest.TestCase):
    def test_gene_report_uses_one_compact_evidence_field(self):
        source = (ROOT / "pdf_report.py").read_text(encoding="utf-8")
        self.assertNotIn('report.get("key_findings")', source)
        self.assertNotIn("Potential Clinical Meaning", source)
        self.assertNotIn('section.get("clinical_meaning")', source)
        self.assertNotIn('section.get("why_it_matters")', source)

    def test_reference_markup_omits_internal_gene_tags(self):
        markup = _reference_markup(
            {
                "n": 3,
                "title": "A shared association study",
                "gene": "KCNQ1, CDKAL1, KCNQ1",
                "journal": "Diabetes",
                "year": 2025,
            },
            "Helvetica-Oblique",
        )

        self.assertTrue(markup.endswith("Diabetes</font>, 2025"))
        self.assertLess(markup.index("A shared association study"), markup.index("Diabetes"))
        self.assertNotIn("KCNQ1", markup)
        self.assertNotIn("CDKAL1", markup)
        self.assertNotIn("{", markup)
        self.assertNotIn("Gene:", markup)

    def test_reference_without_publication_metadata_has_no_gene_line(self):
        markup = _reference_markup(
            {"n": 1, "title": "연구", "gene": "PTEN"},
            "Helvetica-Oblique",
        )

        self.assertTrue(markup.endswith("연구"))
        self.assertNotIn("PTEN", markup)
        self.assertNotIn("{", markup)
        self.assertNotIn("Helvetica-Bold", markup)
        self.assertNotIn("Gene:", markup)
        self.assertNotIn("유전자:", markup)

    def test_bundled_regular_bold_and_license_are_present(self):
        for filename in (
            "NotoSansKR-Regular.ttf",
            "NotoSansKR-Bold.ttf",
            "OFL-NotoSansKR.txt",
        ):
            with self.subTest(filename=filename):
                self.assertTrue((FONT_DIR / filename).is_file())

    def test_korean_uses_one_unicode_family_with_true_bold(self):
        fonts = resolve_fonts("ko")
        self.assertEqual(fonts.regular, "XPRSNotoSansKR")
        self.assertEqual(fonts.bold, "XPRSNotoSansKR-Bold")
        self.assertNotEqual(fonts.regular, fonts.bold)
        self.assertIsNone(fonts.cjk)
        self.assertIsNone(fonts.latin_inline)
        self.assertIsNone(fonts.latin_inline_bold)

    def test_korean_report_builds_with_mixed_text_and_symbols(self):
        pdf = build_pdf_report(
            session={
                "individual_id": "KP-TEST",
                "language": "ko",
                "generation_model": "test/model",
                "report_payload": {
                    "title": "XPRS 한국어 전체 보고서",
                    "language": "ko",
                    "individual_id": "KP-TEST",
                    "risk_overview": {
                        "title": "위험도 개요",
                        "summary": "대장암 PRS와 MLH1 희귀변이 소견을 함께 표시합니다.",
                        "details": "유전자 기여도 β = 0.25이며 참조집단 백분위는 32.3%입니다.",
                    },
                    "top_genes": {"title": "상위 유전자", "rows": []},
                    "bottom_genes": {"title": "하위 유전자", "rows": []},
                    "gene_sections": [{
                        "gene": "KCNQ1",
                        "group": "risk_increasing",
                        "group_title": "위험 증가 기여 유전자",
                        "disease_relevance": "KCNQ1은 제2형 당뇨병 관련 연구 근거가 보고되어 있습니다 [1].",
                    }],
                    "verified_databases": {"rows": []},
                    "integrated_view": {
                        "title": "쉬운 말로 보는 결과",
                        "body": "이 결과는 여러 유전자 기여 신호를 함께 보여줍니다 [1][1].",
                    },
                    "references": [{
                        "n": 1,
                        "title": "KCNQ1과 제2형 당뇨병 연관성 연구",
                        "gene": "KCNQ1",
                        "journal": "Diabetes Research",
                        "year": 2025,
                    }],
                    "disclaimer": {
                        "title": "연구용 안내",
                        "body": "본 결과는 임상 진단이 아닌 연구용 정보입니다.",
                    },
                },
            },
            density_image_data=None,
            manhattan_image_data=None,
        )
        self.assertTrue(pdf.startswith(b"%PDF-"))
        self.assertGreater(len(pdf), 10_000)

    def test_unicode_dashes_and_minus_are_preserved(self):
        rendered = _paragraph_text("PRS–XPRS 비교 — β−값")
        self.assertIn("–", rendered)
        self.assertIn("—", rendered)
        self.assertIn("−", rendered)

    def test_pdf_citations_are_rendered_as_unbracketed_superscripts(self):
        rendered = _paragraph_text(
            "Combined evidence [8][9], another group [1] [2], and one paper [12].",
            superscript_citations=True,
        )

        self.assertIn('<super><font size="7">8,9</font></super>', rendered)
        self.assertIn('<super><font size="7">1,2</font></super>', rendered)
        self.assertIn('<super><font size="7">12</font></super>', rendered)
        self.assertIn('evidence<super><font size="7">8,9</font></super>', rendered)
        self.assertNotIn('evidence <super>', rendered)
        self.assertNotIn(">89<", rendered)
        self.assertNotIn("[12]", rendered)

    def test_pdf_report_uses_plain_language_then_technical_layers(self):
        source = (ROOT / "pdf_report.py").read_text(encoding="utf-8")
        plain_language_position = source.index('integrated = report.get("integrated_view")')
        reading_help_position = source.index('ui_label(report_language, "how_to_read_result")')
        technical_position = source.index('ui_label(report_language, "technical_details")')
        gene_tables_position = source.index('top_genes = report.get("top_genes")')

        self.assertLess(plain_language_position, reading_help_position)
        self.assertLess(reading_help_position, technical_position)
        self.assertLess(technical_position, gene_tables_position)

    def test_pdf_metadata_omits_fixed_gene_count(self):
        source = (ROOT / "pdf_report.py").read_text(encoding="utf-8")
        self.assertNotIn('gene_count_used_label =', source)
        self.assertNotIn('selection_line,', source)
        self.assertIn("XPRS Detailed Report", source)


if __name__ == "__main__":
    unittest.main()
