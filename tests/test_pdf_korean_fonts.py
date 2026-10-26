from pathlib import Path
import unittest

from pdf_report import _paragraph_text, build_pdf_report, resolve_fonts


ROOT = Path(__file__).resolve().parents[1]
FONT_DIR = ROOT / "assets" / "fonts"


class KoreanPdfFontTests(unittest.TestCase):
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
                    "gene_sections": [],
                    "verified_databases": {"rows": []},
                    "integrated_view": {"body": ""},
                    "references": [],
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


if __name__ == "__main__":
    unittest.main()
