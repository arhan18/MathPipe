"""Generates tests/golden-corpus fixtures locally (never commit real PDFs here)."""
from __future__ import annotations

import os

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import BaseDocTemplate, Frame, FrameBreak, PageBreak, PageTemplate, Paragraph, Spacer

HERE = os.path.dirname(os.path.abspath(__file__))


def build_two_column(path: str) -> None:
    styles = getSampleStyleSheet()
    doc = BaseDocTemplate(path, pagesize=LETTER, leftMargin=48, rightMargin=48, topMargin=48, bottomMargin=48)
    w, h = LETTER
    usable = w - 96
    col_w = (usable - 24) / 2
    left = Frame(48, 48, col_w, h - 96, id="left")
    right = Frame(48 + col_w + 24, 48, col_w, h - 96, id="right")
    doc.addPageTemplates([PageTemplate(id="two-col", frames=[left, right])])
    story = [
        Paragraph("Quadratic Equations", styles["Heading1"]),
        Paragraph("The quadratic formula solves ax^2 + bx + c = 0 for any real coefficients.", styles["Normal"]),
        Spacer(1, 12),
        Paragraph("Left column first. It must read before the right column.", styles["Normal"]),
        Paragraph("x = (-b +- sqrt(b^2 - 4ac)) / 2a", styles["Normal"]),
        Spacer(1, 12),
        FrameBreak(),
        Paragraph("Right column second. Reading order crosses the gutter only after the left column ends.", styles["Normal"]),
        Paragraph("Matrices appear inline: [a b; c d] for testing.", styles["Normal"]),
    ]
    doc.build(story)


def build_single_column(path: str) -> None:
    styles = getSampleStyleSheet()
    doc = BaseDocTemplate(path, pagesize=LETTER, leftMargin=48, rightMargin=48, topMargin=48, bottomMargin=48)
    w, h = LETTER
    frame = Frame(48, 48, w - 96, h - 96, id="single")
    doc.addPageTemplates([PageTemplate(id="single", frames=[frame])])
    story = [
        Paragraph("Algebra Worksheet", styles["Heading1"]),
        Paragraph("Solve each equation. Show all steps.", styles["Normal"]),
        Spacer(1, 24),
        Paragraph("1. x^2 + 3x + 2 = 0", styles["Normal"]),
        Spacer(1, 24),
        Paragraph("2. (x + 1)(x + 2) = 0", styles["Normal"]),
    ]
    doc.build(story)


def build_redteam(path: str) -> None:
    styles = getSampleStyleSheet()
    doc = BaseDocTemplate(path, pagesize=LETTER, leftMargin=48, rightMargin=48, topMargin=48, bottomMargin=48)
    w, h = LETTER
    frame = Frame(48, 48, w - 96, h - 96, id="single")
    doc.addPageTemplates([PageTemplate(id="single", frames=[frame])])
    story = [
        Paragraph("Adversarial cases. Each must degrade honestly.", styles["Heading1"]),
        Spacer(1, 24),
        Paragraph("Nested: ((a / b) / (c / d)) / e", styles["Normal"]),
        Spacer(1, 24),
        Paragraph("Long: x_1 + x_2 + x_3 + x_4 + x_5 + x_6 + x_7 + x_8 = S", styles["Normal"]),
        Spacer(1, 24),
        Paragraph("Matrix row: [a b c d e f g h] wide content here", styles["Normal"]),
        Spacer(1, 24),
        Paragraph("Unbalanced: (x + (y + z)", styles["Normal"]),
    ]
    doc.build(story)


def build_long(path: str, pages: int = 60) -> None:
    """Stress fixture: many single-column pages with display equations."""
    styles = getSampleStyleSheet()
    doc = BaseDocTemplate(path, pagesize=LETTER, leftMargin=48, rightMargin=48, topMargin=48, bottomMargin=48)
    w, h = LETTER
    frame = Frame(48, 48, w - 96, h - 96, id="single")
    doc.addPageTemplates([PageTemplate(id="single", frames=[frame])])
    story = []
    for n in range(1, pages + 1):
        if n > 1:
            story.append(PageBreak())
        story.append(Paragraph(f"Chapter {n}. Practice set.", styles["Heading1"]))
        story.append(Paragraph(f"Problem {n}.1 with prose context for page {n}.", styles["Normal"]))
        story.append(Spacer(1, 24))
        story.append(Paragraph(f"x^{n} + {n}x + {n} = 0", styles["Normal"]))
        story.append(Spacer(1, 24))
    doc.build(story)


if __name__ == "__main__":
    os.makedirs(os.path.join(HERE, "golden"), exist_ok=True)
    build_two_column(os.path.join(HERE, "golden", "algebra-two-column.pdf"))
    build_single_column(os.path.join(HERE, "golden", "algebra-worksheet.pdf"))
    build_long(os.path.join(HERE, "golden", "algebra-long-60.pdf"))
    build_redteam(os.path.join(HERE, "golden", "redteam-tricky.pdf"))
    with open(os.path.join(HERE, "golden", "redteam-malformed.pdf"), "wb") as f:
        f.write(b"%PDF-1.4 truncated without xref or trailer")
    print("fixtures written")
