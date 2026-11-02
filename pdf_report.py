from __future__ import annotations

import base64
import html
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from text_utils import ui_label


def _decode_image_data(image_data: str | None) -> BytesIO | None:
    if not image_data:
        return None
    raw = image_data.strip()
    if not raw:
        return None
    if raw.startswith("data:"):
        match = re.match(r"^data:[^;]+;base64,(.*)$", raw, flags=re.S)
        if not match:
            return None
        raw = match.group(1)
    try:
        return BytesIO(base64.b64decode(raw))
    except Exception:
        return None


def _paragraph_text(
    text: str,
    cjk_font_name: str | None = None,
    latin_font_name: str | None = None,
    superscript_citations: bool = False,
) -> str:
    raw = str(text or "").strip()
    raw = re.sub(r"\*\*(.*?)\*\*", r"\1", raw)

    hangul_pattern = re.compile(r"([ᄀ-ᇿ㄰-㆏가-힯]+)")
    latin_pattern = re.compile(r"([A-Za-z0-9][A-Za-z0-9 /+_.:;,%&()\[\]{}<>=!?@#*$^~'\"`|-]*)")

    def render_text(segment: str) -> str:
        if not segment:
            return ""
        if not cjk_font_name and not latin_font_name:
            return html.escape(segment)

        rendered: list[str] = []
        pattern = latin_pattern if latin_font_name else hangul_pattern
        font_name = latin_font_name or cjk_font_name
        for chunk in pattern.split(segment):
            if not chunk:
                continue
            escaped_chunk = html.escape(chunk)
            if pattern.fullmatch(chunk):
                rendered.append(f'<font name="{font_name}">{escaped_chunk}</font>')
            else:
                rendered.append(escaped_chunk)
        return "".join(rendered)

    rendered_lines: list[str] = []
    for line in raw.split("\n"):
        parts: list[str] = []
        citation_pattern = r"\[\d+(?:\s*[,–-]\s*\d+)*\]"
        if superscript_citations:
            line = re.sub(rf"\s+(?={citation_pattern})", "", line)
        segments = (
            re.split(rf"((?:{citation_pattern})(?:\s*{citation_pattern})*)", line)
            if superscript_citations
            else [line]
        )
        for segment in segments:
            if superscript_citations and re.fullmatch(
                rf"(?:{citation_pattern})(?:\s*{citation_pattern})*",
                segment,
            ):
                citation_numbers: list[str] = []
                for citation_group in re.findall(r"\[([^\]]+)\]", segment):
                    for token in re.split(r"\s*,\s*", citation_group):
                        normalized_token = re.sub(r"\s*[–-]\s*", "–", token.strip())
                        if normalized_token and normalized_token not in citation_numbers:
                            citation_numbers.append(normalized_token)
                citation_text = html.escape(",".join(citation_numbers))
                citation_font = (
                    f' name="{latin_font_name}"' if latin_font_name else ""
                )
                parts.append(
                    f'<super><font{citation_font} size="7">{citation_text}</font></super>'
                )
            else:
                parts.append(render_text(segment))
        rendered_lines.append("".join(parts))
    return "<br/>".join(rendered_lines)


def _reference_markup(
    reference: dict[str, Any],
    italic_font_name: str,
) -> str:
    """Build a compact PDF citation without internal retrieval metadata."""
    label = html.escape(f"[{reference.get('n', '')}]")
    title = html.escape(str(reference.get("title") or "Untitled"))
    line1 = f"{label} {title}"

    lines = [line1]
    publication_parts: list[str] = []
    if reference.get("journal"):
        journal = html.escape(str(reference.get("journal")))
        publication_parts.append(f'<font name="{italic_font_name}">{journal}</font>')
    if reference.get("year"):
        publication_parts.append(html.escape(str(reference.get("year"))))
    if publication_parts:
        lines.append(", ".join(publication_parts))

    return "<br/>".join(lines)


@dataclass(frozen=True)
class FontConfig:
    regular: str
    bold: str
    italic: str
    cjk: str | None = None
    latin_inline: str | None = None
    latin_inline_bold: str | None = None


_REPO_ROOT = Path(__file__).resolve().parent
_BUNDLED_FONTS_DIR = _REPO_ROOT / "assets" / "fonts"

# Korean Hangul font search order. First entry whose paths both exist wins.
# Each tuple: (regular_path, bold_path, registered_family_name).
_KOREAN_FONT_CANDIDATES: list[tuple[Path, Path, str]] = [
    (
        _BUNDLED_FONTS_DIR / "NotoSansKR-Regular.ttf",
        _BUNDLED_FONTS_DIR / "NotoSansKR-Bold.ttf",
        "XPRSNotoSansKR",
    ),
    (
        _BUNDLED_FONTS_DIR / "NanumGothic.ttf",
        _BUNDLED_FONTS_DIR / "NanumGothicBold.ttf",
        "XPRSNanumGothic",
    ),
    (
        Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
        Path("/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"),
        "XPRSNanumGothic",
    ),
    (
        Path("C:/Windows/Fonts/malgun.ttf"),
        Path("C:/Windows/Fonts/malgunbd.ttf"),
        "XPRSMalgunGothic",
    ),
]

_DEJAVU_REGULAR = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
_DEJAVU_BOLD = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
_DEJAVU_OBLIQUE = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf")


def _register_korean_ttf_family() -> tuple[str, str] | None:
    """Register the first available Korean TTF family.

    Returns (regular_name, bold_name) on success, or None if no candidate was
    found and the caller should fall back to the built-in CID font.
    """
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    for regular_path, bold_path, family in _KOREAN_FONT_CANDIDATES:
        if not (regular_path.exists() and bold_path.exists()):
            continue
        bold_name = f"{family}-Bold"
        pdfmetrics.registerFont(TTFont(family, str(regular_path)))
        pdfmetrics.registerFont(TTFont(bold_name, str(bold_path)))
        pdfmetrics.registerFontFamily(
            family,
            normal=family,
            bold=bold_name,
            italic=family,
            boldItalic=bold_name,
        )
        return family, bold_name
    return None


def resolve_fonts(language: str) -> FontConfig:
    """Pick and register fonts for the given report language.

    All font registration happens here. The returned FontConfig holds the
    registered names callers should pass to ParagraphStyle / canvas.setFont.
    """
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfbase.ttfonts import TTFont

    regular = "Helvetica"
    bold = "Helvetica-Bold"
    italic = "Helvetica-Oblique"
    cjk: str | None = None
    latin_inline: str | None = None
    latin_inline_bold: str | None = None

    dejavu_ok = _DEJAVU_REGULAR.exists() and _DEJAVU_BOLD.exists()
    if dejavu_ok:
        pdfmetrics.registerFont(TTFont("XPRSDejaVuSans", str(_DEJAVU_REGULAR)))
        pdfmetrics.registerFont(TTFont("XPRSDejaVuSans-Bold", str(_DEJAVU_BOLD)))
        if _DEJAVU_OBLIQUE.exists():
            pdfmetrics.registerFont(TTFont("XPRSDejaVuSans-Oblique", str(_DEJAVU_OBLIQUE)))

    if language.startswith("ko"):
        korean_pair = _register_korean_ttf_family()
        if korean_pair is not None:
            regular, bold = korean_pair
            # The bundled Korean family contains Hangul, Latin, Greek, and
            # common mathematical symbols. Let ParagraphStyle select the
            # regular or true bold face for the entire run; per-script font
            # wrappers would otherwise force Hangul headings back to regular.
            cjk = None
            latin_inline = None
            latin_inline_bold = None
            if _DEJAVU_OBLIQUE.exists():
                italic = "XPRSDejaVuSans-Oblique"
            else:
                italic = regular
        else:
            # Last-resort CID fallback. No bold variant — visual hierarchy
            # in headings will be reduced to color/size only.
            if dejavu_ok:
                latin_inline = "XPRSDejaVuSans"
                latin_inline_bold = "XPRSDejaVuSans-Bold"
                if _DEJAVU_OBLIQUE.exists():
                    italic = "XPRSDejaVuSans-Oblique"
            pdfmetrics.registerFont(UnicodeCIDFont("HYGothic-Medium"))
            regular = bold = cjk = "HYGothic-Medium"
    elif dejavu_ok:
        regular = "XPRSDejaVuSans"
        bold = "XPRSDejaVuSans-Bold"
        if _DEJAVU_OBLIQUE.exists():
            italic = "XPRSDejaVuSans-Oblique"

    return FontConfig(
        regular=regular,
        bold=bold,
        italic=italic,
        cjk=cjk,
        latin_inline=latin_inline,
        latin_inline_bold=latin_inline_bold,
    )


def build_pdf_report(
    session: dict[str, Any],
    density_image_data: str | None,
    manhattan_image_data: str | None,
) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import (
            HRFlowable,
            Image,
            KeepTogether,
            PageBreak,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as exc:
        raise HTTPException(status_code=500, detail="PDF export requires reportlab to be installed.") from exc

    report = session.get("report_payload") or {}
    if not report:
        report = {
            "title": "XPRS Detailed Report",
            "individual_id": session.get("individual_id"),
            "language": session.get("language", "en"),
            "gene_count": session.get("gene_count_used") or session.get("gene_count"),
            "threshold_used": session.get("threshold_used"),
            "disclaimer": {
                "title": "Research Use Disclaimer",
                "body": (
                    "This output is generated by a research prototype. The polygenic risk score (PRS) "
                    "values shown here are statistical signals relative to a reference cohort, not clinical "
                    "diagnoses, prognoses, or treatment recommendations. This tool does not substitute for "
                    "medical evaluation, genetic counseling, or care decisions, which should be discussed "
                    "with a qualified clinician."
                ),
            },
            "risk_overview": {
                "title": "Risk Overview",
                "summary": session.get("simple_summary") or "",
                "details": "",
            },
            "top_genes": {"title": "Top 5 Genes", "rows": []},
            "bottom_genes": {"title": "Bottom 5 Genes", "rows": []},
            "gene_sections": [],
            "verified_databases": {"title": "Verified Databases", "intro": "", "rows": []},
            "integrated_view": {"title": "Integrated View", "body": ""},
            "references": session.get("references", []),
            "detailed_summary": session.get("detailed_summary") or "",
        }

    report_language = str(report.get("language") or session.get("language") or "en").lower()
    font_config = resolve_fonts(report_language)
    regular_font_name = font_config.regular
    bold_font_name = font_config.bold
    italic_font_name = font_config.italic
    cjk_font_name = font_config.cjk
    latin_inline_font_name = font_config.latin_inline
    latin_inline_bold_font_name = font_config.latin_inline_bold

    ACCENT_COLOR = colors.HexColor("#1f4f7a")
    ACCENT_RULE_COLOR = colors.HexColor("#cbd5e1")
    CALLOUT_BG_COLOR = colors.HexColor("#eef4fb")
    CALLOUT_BORDER_COLOR = colors.HexColor("#1f4f7a")

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontName=bold_font_name,
        fontSize=24,
        leading=28,
        textColor=ACCENT_COLOR,
        alignment=TA_LEFT,
        spaceAfter=4,
    )
    heading_style = ParagraphStyle(
        "ReportHeading",
        parent=styles["Heading2"],
        fontName=bold_font_name,
        textColor=colors.HexColor("#1f4f7a"),
        spaceAfter=8,
        spaceBefore=12,
        alignment=TA_LEFT,
    )
    subheading_style = ParagraphStyle(
        "ReportSubheading",
        parent=styles["Heading3"],
        fontName=bold_font_name,
        textColor=colors.HexColor("#234e52"),
        spaceAfter=6,
        spaceBefore=8,
    )
    gene_heading_style = ParagraphStyle(
        "ReportGeneHeading",
        parent=styles["Heading3"],
        fontName=bold_font_name,
        fontSize=11,
        leading=13,
        textColor=colors.HexColor("#334155"),
        spaceAfter=4,
        spaceBefore=7,
        alignment=TA_LEFT,
    )
    body_style = ParagraphStyle(
        "ReportBody",
        parent=styles["BodyText"],
        fontName=regular_font_name,
        leading=14,
        spaceAfter=8,
    )
    small_style = ParagraphStyle(
        "ReportSmall",
        parent=styles["BodyText"],
        fontName=regular_font_name,
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#5f6b7a"),
        spaceAfter=4,
    )
    table_header_style = ParagraphStyle(
        "ReportTableHeader",
        parent=small_style,
        fontName=bold_font_name,
        textColor=colors.HexColor("#1e3a5f"),
        fontSize=8.5,
        leading=10,
        spaceAfter=0,
    )
    table_body_style = ParagraphStyle(
        "ReportTableBody",
        parent=small_style,
        fontName=regular_font_name,
        textColor=colors.HexColor("#22313f"),
        fontSize=8.5,
        leading=10.5,
        spaceAfter=0,
    )

    bold_style_names = {
        title_style.name,
        heading_style.name,
        subheading_style.name,
        gene_heading_style.name,
        table_header_style.name,
    }

    def p(text: str, style=body_style) -> Paragraph:
        inline_latin_font = None
        if report_language.startswith("ko"):
            inline_latin_font = (
                latin_inline_bold_font_name if style.name in bold_style_names else latin_inline_font_name
            )
        return Paragraph(
            _paragraph_text(
                text,
                cjk_font_name=None if inline_latin_font else cjk_font_name,
                latin_font_name=inline_latin_font,
                superscript_citations=True,
            ),
            style,
        )

    def heading_with_rule(title: str, style=heading_style) -> list[Any]:
        return [
            p(title, style),
            HRFlowable(
                width="100%",
                thickness=0.6,
                color=ACCENT_RULE_COLOR,
                spaceBefore=0,
                spaceAfter=6,
                lineCap="butt",
            ),
        ]

    def add_section_block(
        title: str,
        body_parts: list[Any],
        title_style=heading_style,
        include_rule: bool = True,
    ) -> None:
        heading_flowables = (
            heading_with_rule(title, title_style) if include_rule else [p(title, title_style)]
        )
        flowables = [*heading_flowables, *body_parts]
        if body_parts:
            story.append(KeepTogether(flowables))
        else:
            story.extend(flowables)

    individual_label = report.get("individual_id") or session.get("individual_id") or "—"
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.8 * inch,
        rightMargin=0.8 * inch,
        topMargin=0.8 * inch,
        bottomMargin=0.75 * inch,
    )
    story = []

    def draw_page_chrome(canvas, pdf_doc) -> None:
        canvas.saveState()
        page_num = canvas.getPageNumber()

        if page_num == 1:
            band_height = 0.35 * inch
            band_y = letter[1] - band_height
            canvas.setFillColor(colors.HexColor("#1f4f7a"))
            canvas.rect(0, band_y, letter[0], band_height, stroke=0, fill=1)
            canvas.setFillColor(colors.white)
            canvas.setFont(bold_font_name, 10)
            canvas.drawString(
                pdf_doc.leftMargin,
                band_y + (band_height - 10) / 2.0,
                "XPRS",
            )
            canvas.setFont(regular_font_name, 9)
            canvas.drawRightString(
                letter[0] - pdf_doc.rightMargin,
                band_y + (band_height - 9) / 2.0,
                ui_label(report_language, "report_subtitle") or "Detailed Report",
            )

        footer_y = 0.45 * inch
        canvas.setStrokeColor(colors.HexColor("#d7dee6"))
        canvas.setLineWidth(0.5)
        canvas.line(pdf_doc.leftMargin, footer_y + 0.18 * inch, letter[0] - pdf_doc.rightMargin, footer_y + 0.18 * inch)
        canvas.setFont(regular_font_name, 8.5)
        canvas.setFillColor(colors.HexColor("#5f6b7a"))
        canvas.drawCentredString(letter[0] / 2.0, footer_y, str(page_num))

        if page_num >= 2:
            header_y = letter[1] - 0.5 * inch
            canvas.line(pdf_doc.leftMargin, header_y - 0.12 * inch, letter[0] - pdf_doc.rightMargin, header_y - 0.12 * inch)
            canvas.setFont(bold_font_name, 9)
            canvas.setFillColor(colors.HexColor("#1f4f7a"))
            canvas.drawString(pdf_doc.leftMargin, header_y, ui_label(report_language, "report_title") or "XPRS Detailed Report")
            canvas.setFont(regular_font_name, 9)
            canvas.drawRightString(
                letter[0] - pdf_doc.rightMargin,
                header_y,
                f"{ui_label(report_language, 'individual_id_label') or 'Individual ID'}: {individual_label}",
            )

        canvas.restoreState()

    story.append(p(report.get("title") or ui_label(report_language, "report_title") or "XPRS Detailed Report", title_style))
    individual_id_label = ui_label(report_language, "individual_id_label") or "Individual ID"
    generated_at_label = ui_label(report_language, "generated_at_label") or "Generated At"

    raw_generated_at = (
        session.get("updated_at")
        or session.get("created_at")
        or datetime.now(timezone.utc).isoformat()
    )
    try:
        parsed_generated_at = datetime.fromisoformat(str(raw_generated_at))
        if parsed_generated_at.tzinfo is not None:
            parsed_generated_at = parsed_generated_at.astimezone(timezone.utc)
        generated_at_display = parsed_generated_at.strftime("%Y-%m-%d %H:%M:%S") + " UTC"
    except (TypeError, ValueError):
        generated_at_display = str(raw_generated_at)

    meta_lines = [
        f"{individual_id_label}: {individual_label}",
        f"{generated_at_label}: {generated_at_display}",
    ]
    generation_model = session.get("generation_model")
    if generation_model:
        generation_model_label = ui_label(report_language, "generation_model_label") or "Generation Model"
        meta_lines.insert(1, f"{generation_model_label}: {generation_model}")
    for line in meta_lines:
        story.append(p(line, small_style))
    story.append(Spacer(1, 0.15 * inch))

    risk = report.get("risk_overview") or {}
    story.append(p(risk.get("title") or "Risk Overview", heading_style))
    if risk.get("summary"):
        callout = Table(
            [[p(risk.get("summary"), body_style)]],
            colWidths=[doc.width],
            hAlign="LEFT",
        )
        callout.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), CALLOUT_BG_COLOR),
            ("LINEBEFORE", (0, 0), (0, -1), 3, CALLOUT_BORDER_COLOR),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(callout)
        story.append(Spacer(1, 0.1 * inch))
    if risk.get("details"):
        story.append(p(risk.get("details"), body_style))

    integrated = report.get("integrated_view") or {}
    if integrated.get("body"):
        parts = [
            p(paragraph, body_style)
            for paragraph in re.split(r"\n\s*\n", str(integrated.get("body") or "").strip())
            if paragraph.strip()
        ]
        add_section_block(
            integrated.get("title")
            or ui_label(report_language, "integrated_view")
            or "Plain-Language Interpretation",
            parts,
        )

    reading_notes = [
        ui_label(report_language, "reading_note_prs"),
        ui_label(report_language, "reading_note_contributions"),
        ui_label(report_language, "reading_note_evidence"),
    ]
    add_section_block(
        ui_label(report_language, "how_to_read_result") or "How to Read This Result",
        [p(f"• {note}", body_style) for note in reading_notes if note],
    )

    technical_heading_flowables = heading_with_rule(
        ui_label(report_language, "technical_details") or "Technical Details"
    )

    density_image = _decode_image_data(density_image_data)
    manhattan_image = _decode_image_data(manhattan_image_data)
    figure_blocks: list[tuple[str, BytesIO | None]] = [
        (ui_label(report_language, "cohort_density_plot") or "Cohort Density Plot", density_image),
        (ui_label(report_language, "individual_manhattan_plot") or "Individual Manhattan Plot", manhattan_image),
    ]

    def add_ranked_gene_table(
        section: dict[str, Any],
        fallback_title: str,
        leading_flowables: list[Any] | None = None,
    ) -> bool:
        rows = section.get("rows") or []
        if not rows:
            return False
        table_rows = [[
            p(ui_label(report_language, "gene") or "Gene", table_header_style),
            p(ui_label(report_language, "individual_contribution") or "Individual Contribution Score", table_header_style),
            p(ui_label(report_language, "population_rank") or "Population Rank", table_header_style),
        ]]
        for row in rows:
            table_rows.append([
                p(str(row.get("gene") or "—"), table_body_style),
                p(f"{float(row.get('individual_contribution')):.2f}" if row.get("individual_contribution") is not None else "—", table_body_style),
                p(str(row.get("population_rank")) if row.get("population_rank") is not None else "—", table_body_style),
            ])
        table = Table(table_rows, repeatRows=1, colWidths=[1.5 * inch, 2.0 * inch, 1.6 * inch], hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dbeafe")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("PADDING", (0, 0), (-1, -1), 6),
        ]))
        section_heading = p(section.get("title") or fallback_title, heading_style)
        story.append(KeepTogether([*(leading_flowables or []), section_heading, table]))
        return True

    top_genes = report.get("top_genes") or {}
    bottom_genes = report.get("bottom_genes") or {}
    top_table_added = add_ranked_gene_table(
        top_genes,
        "Top 5 Genes",
        leading_flowables=technical_heading_flowables,
    )
    bottom_table_added = add_ranked_gene_table(
        bottom_genes,
        "Bottom 5 Genes",
        leading_flowables=[] if top_table_added else technical_heading_flowables,
    )
    if not top_table_added and not bottom_table_added:
        story.extend(technical_heading_flowables)

    current_gene_group = None
    for section in report.get("gene_sections") or []:
        group = section.get("group")
        if group and group != current_gene_group:
            story.extend(heading_with_rule(section.get("group_title") or str(group)))
            current_gene_group = group
        disease_relevance = section.get("disease_relevance")
        if disease_relevance is None:
            # Read reports created before the disease-neutral schema revision.
            disease_relevance = section.get("breast_cancer_relevance")
        if not disease_relevance:
            continue
        body_paras = [
            p(paragraph, body_style)
            for paragraph in re.split(r"\n\s*\n", str(disease_relevance).strip())
            if paragraph.strip()
        ]
        gene_heading_flowables = [p(section.get("gene") or "Gene", gene_heading_style)]
        if body_paras:
            story.append(KeepTogether([*gene_heading_flowables, body_paras[0]]))
            story.extend(body_paras[1:])
        else:
            story.append(KeepTogether(gene_heading_flowables))

    verified = report.get("verified_databases") or {}
    verified_rows = verified.get("rows") or []
    if verified_rows:
        preamble: list[Any] = []
        if verified.get("intro"):
            preamble.append(p(verified.get("intro"), body_style))
        add_section_block(verified.get("title") or "Verified Databases", preamble)
        table_rows = [[
            p(ui_label(report_language, "gene") or "Gene", table_header_style),
            p(ui_label(report_language, "mean_association_score") or "Mean Association Score", table_header_style),
            p(ui_label(report_language, "evidence_items") or "Evidence Items", table_header_style),
            p(ui_label(report_language, "interpretation") or "Interpretation", table_header_style),
        ]]
        for row in verified_rows:
            mean_score = row.get("mean_association_score")
            evidence_items = row.get("supporting_evidence_items")
            table_rows.append([
                p(str(row.get("gene") or "—"), table_body_style),
                p(f"{float(mean_score):.3f}" if mean_score is not None else "—", table_body_style),
                p(str(int(evidence_items)) if evidence_items is not None else "—", table_body_style),
                p(str(row.get("interpretation") or ""), table_body_style),
            ])
        table = Table(table_rows, repeatRows=1, colWidths=[0.95 * inch, 1.2 * inch, 1.0 * inch, 3.35 * inch], hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dbeafe")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ("PADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(table)

    references = report.get("references") or session.get("references") or []
    if references:
        reference_style = ParagraphStyle(
            "ReportReference",
            parent=small_style,
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#22313f"),
            leftIndent=20,
            firstLineIndent=-20,
            spaceAfter=5,
        )
        ref_paras = []
        for ref in references:
            markup = _reference_markup(
                ref,
                italic_font_name,
            )
            ref_paras.append(Paragraph(markup, reference_style))
        add_section_block(ui_label(report_language, "references") or "References", ref_paras[:1])
        story.extend(ref_paras[1:])

    disclaimer = report.get("disclaimer") or {}
    if disclaimer.get("body"):
        disclaimer_heading_style = ParagraphStyle(
            "ReportDisclaimerHeading",
            parent=small_style,
            fontName=bold_font_name,
            fontSize=7.5,
            leading=9,
            textColor=colors.HexColor("#7a7a7a"),
            spaceBefore=10,
            spaceAfter=2,
        )
        disclaimer_body_style = ParagraphStyle(
            "ReportDisclaimerBody",
            parent=small_style,
            fontSize=7.5,
            leading=10,
            textColor=colors.HexColor("#7a7a7a"),
            spaceAfter=0,
        )
        story.append(Spacer(1, 0.1 * inch))
        story.append(p(disclaimer.get("title") or "Research Use Disclaimer", disclaimer_heading_style))
        story.append(p(disclaimer.get("body"), disclaimer_body_style))

    available_figures = [item for item in figure_blocks if item[1] is not None]
    if available_figures:
        story.append(PageBreak())
        story.extend(heading_with_rule(ui_label(report_language, "figures") or "Figures"))
        for label, image_io in figure_blocks:
            story.append(p(label, subheading_style))
            if image_io:
                story.append(Image(image_io, width=doc.width, height=3.5 * inch))
            else:
                story.append(p("Plot image was not provided for this export.", small_style))
            story.append(Spacer(1, 0.12 * inch))

    doc.build(story, onFirstPage=draw_page_chrome, onLaterPages=draw_page_chrome)
    return buffer.getvalue()
