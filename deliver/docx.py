"""Deliverable Word (.docx) report generation with redundant 3-way classification stamping.

NON-NEGOTIABLE DESIGN PRINCIPLES:
1. Three-way classification stamping:
   - Top banner paragraph on page 1 (bold, centered, colored run).
   - Running header AND footer on all pages.
   - Output filename stamped with classification tier.
   Rationale: A banner gets skimmed, a header survives photocopying, a filename survives renaming.
2. Two-level model: Paragraphs hold alignment; runs hold bold/size/color.
3. Refuse to build a report for an abstained response.
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Optional
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor
from contracts import AskResponse, Tier

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def _add_markdown_runs(paragraph, text: str) -> None:
    """Split '**bold**' spans out of a line and add each as a separate run."""
    pos = 0
    for m in _BOLD_RE.finditer(text):
        if m.start() > pos:
            paragraph.add_run(text[pos:m.start()])
        bold_run = paragraph.add_run(m.group(1))
        bold_run.bold = True
        pos = m.end()
    if pos < len(text):
        paragraph.add_run(text[pos:])


def _add_markdown_answer(doc: Document, answer: str) -> None:
    """Render the agent's Markdown-formatted answer as real Word formatting
    (headings, bold, bullet/numbered lists) instead of dumping literal
    '#'/'**' characters into a single paragraph."""
    for raw_line in answer.split("\n"):
        line = raw_line.strip()
        if not line:
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading_match:
            level = min(len(heading_match.group(1)) + 1, 4)  # nest under "Verified Synthesized Findings"
            doc.add_heading(heading_match.group(2), level=level)
            continue

        bullet_match = re.match(r"^[-*]\s+(.*)$", line)
        if bullet_match:
            p = doc.add_paragraph(style="List Bullet")
            _add_markdown_runs(p, bullet_match.group(1))
            continue

        numbered_match = re.match(r"^\d+\.\s+(.*)$", line)
        if numbered_match:
            p = doc.add_paragraph(style="List Number")
            _add_markdown_runs(p, numbered_match.group(1))
            continue

        p = doc.add_paragraph()
        p.paragraph_format.line_spacing = 1.15
        p.paragraph_format.space_after = Pt(8)
        _add_markdown_runs(p, line)

# Stamping color palette by Tier
TIER_COLORS: dict[Tier, RGBColor] = {
    Tier.SECRET: RGBColor(185, 28, 28),         # Crimson Red
    Tier.CONFIDENTIAL: RGBColor(194, 65, 12),   # Deep Amber / Orange
    Tier.INTERNAL: RGBColor(29, 78, 216),       # Deep Blue
    Tier.PUBLIC: RGBColor(4, 120, 87),          # Forest Green
}


def get_classification_banner_text(response: AskResponse) -> str:
    """Format standard classification banner text."""
    tier_str = response.effective_label.tier.value.upper()
    comps = response.effective_label.compartments
    if comps:
        comp_str = ", ".join(sorted(c.value.upper() for c in comps))
        return f"CLASSIFICATION: {tier_str} // COMPARTMENTS: [{comp_str}]"
    return f"CLASSIFICATION: {tier_str} // UNRESTRICTED DISTRIBUTION"


def get_report_filename(response: AskResponse) -> str:
    """Generate canonical classification-stamped filename."""
    row_id = response.ledger_row_id or "Unrecorded"
    tier_str = response.effective_label.tier.value.upper()
    return f"SEVERANCE_Report_Row{row_id}_{tier_str}.docx"


def build_report(
    response: AskResponse,
    question: str,
    output_path: Optional[str | Path] = None,
) -> bytes:
    """Build a formal Word report with 3-way redundant classification stamping.

    Refuses to build a report for an abstained response.
    """
    if response.status == "abstained":
        raise ValueError("Cannot generate deliverable report for an abstained query response.")

    doc = Document()
    tier = response.effective_label.tier
    stamp_color = TIER_COLORS.get(tier, RGBColor(0, 0, 0))
    banner_text = get_classification_banner_text(response)

    # -----------------------------------------------------------------------
    # Stamp 1 & 2: Running Header and Footer on Every Page
    # -----------------------------------------------------------------------
    for section in doc.sections:
        # Header
        header_p = section.header.paragraphs[0]
        header_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        header_run = header_p.add_run(banner_text)
        header_run.bold = True
        header_run.font.size = Pt(8.5)
        header_run.font.color.rgb = stamp_color

        # Footer
        footer_p = section.footer.paragraphs[0]
        footer_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        footer_run = footer_p.add_run(banner_text)
        footer_run.bold = True
        footer_run.font.size = Pt(8.5)
        footer_run.font.color.rgb = stamp_color

    # -----------------------------------------------------------------------
    # Stamp 3: Top Banner Paragraph on First Page
    # -----------------------------------------------------------------------
    banner_p = doc.add_paragraph()
    banner_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    b_run = banner_p.add_run(f"*** {banner_text} ***\n")
    b_run.bold = True
    b_run.font.size = Pt(13)
    b_run.font.color.rgb = stamp_color

    # Title & Metadata
    title_p = doc.add_heading("MRPL Document Intelligence Synthesis", level=1)
    title_p.alignment = WD_ALIGN_PARAGRAPH.LEFT

    meta_p = doc.add_paragraph()
    meta_p.add_run("Query: ").bold = True
    meta_p.add_run(f"{question}\n")
    meta_p.add_run("Effective Classification: ").bold = True
    meta_p.add_run(f"{response.effective_label.tier.value.upper()}\n")
    if response.effective_label.compartments:
        meta_p.add_run("Effective Compartments: ").bold = True
        comps = ", ".join(sorted(c.value.upper() for c in response.effective_label.compartments))
        meta_p.add_run(f"{comps}\n")
    meta_p.add_run("Ledger Row ID: ").bold = True
    meta_p.add_run(f"#{response.ledger_row_id or 'Unrecorded'}\n")

    doc.add_paragraph().paragraph_format.space_after = Pt(6)

    # -----------------------------------------------------------------------
    # Synthesis Answer Section
    # -----------------------------------------------------------------------
    doc.add_heading("Verified Synthesized Findings", level=2)
    _add_markdown_answer(doc, response.answer)

    # -----------------------------------------------------------------------
    # Citations Table (Verbatim Verified Proof)
    # -----------------------------------------------------------------------
    if response.citations:
        doc.add_heading("Verbatim Citation Verification Ledger", level=2)
        table = doc.add_table(rows=1, cols=3)
        table.style = "Light Shading Accent 1" if "Light Shading Accent 1" in [s.name for s in doc.styles] else "Table Grid"

        hdr_cells = table.rows[0].cells
        hdr_cells[0].text = "Document ID"
        hdr_cells[1].text = "Page"
        hdr_cells[2].text = "Verbatim Quoted Passage"
        for c in hdr_cells:
            for p in c.paragraphs:
                for r in p.runs:
                    r.bold = True

        for cit in response.citations:
            row_cells = table.add_row().cells
            row_cells[0].text = cit.doc_id
            row_cells[1].text = str(cit.page)
            row_cells[2].text = f'"{cit.quote}"'

    # -----------------------------------------------------------------------
    # Withheld Materials (Denials without Content)
    # -----------------------------------------------------------------------
    if response.denials:
        doc.add_heading("Severability Clause & Withheld Documents", level=2)
        denial_intro = doc.add_paragraph(
            "Under Section 10 of the RTI Act 2005 (Severability), the following documents "
            "matched the query parameters but were withheld by the two-axis security gate. "
            "Document contents were completely excluded from the synthesis environment:"
        )
        for denial in response.denials:
            p_den = doc.add_paragraph(style="List Bullet")
            p_den.add_run(f"Document ID: {denial.doc_id} — ").bold = True
            p_den.add_run(f"Reason: {denial.reason}")

    # Bottom Banner Paragraph
    doc.add_paragraph().paragraph_format.space_after = Pt(12)
    bot_p = doc.add_paragraph()
    bot_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    bot_run = bot_p.add_run(f"*** END OF REPORT — {banner_text} ***")
    bot_run.bold = True
    bot_run.font.size = Pt(10)
    bot_run.font.color.rgb = stamp_color

    bio = io.BytesIO()
    doc.save(bio)
    file_bytes = bio.getvalue()

    if output_path:
        Path(output_path).write_bytes(file_bytes)

    return file_bytes
