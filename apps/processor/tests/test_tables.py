"""Ruled-table reconstruction: geometry → Word tables.

Fixtures are generated locally with reportlab (no binary fixtures are
committed). Each test drives the real pipeline and inspects the DOCX XML,
so it checks what a reader sees, not the detector's opinion of itself.
"""
from __future__ import annotations

import io
import os
import shutil
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from lxml import etree  # noqa: E402
from reportlab.lib.pagesizes import LETTER  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

from src.pipeline.runner import run_pipeline  # noqa: E402
from src.word.builder import build_docx  # noqa: E402

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _ruled_table(path: str, *, caption: bool = False, break_middle: bool = False) -> None:
    """A bordered 3x3 table whose header cell spans the whole row."""
    c = canvas.Canvas(path, pagesize=LETTER)
    if caption:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(60, 720, "Table 1: Frequency distribution")
    xs = [60, 150, 350, 500]
    ys = [700, 660, 620, 580]
    for y in ys:
        c.line(xs[0], y, xs[-1], y)
    for i, x in enumerate(xs):
        if i in (1, 2):
            # Inner verticals skip the header band (merged header cell).
            # ``break_middle`` also punches a hole into the middle row, so
            # the rows no longer agree on the table's shape.
            if break_middle and i == 1:
                c.line(x, 580, x, 620)
            else:
                c.line(x, 580, x, 660)
        else:
            c.line(x, 580, x, 700)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(200, 675, "Header")
    c.setFont("Helvetica", 10)
    c.drawString(70, 635, "A")
    c.drawString(200, 635, "B")
    c.drawString(360, 635, "C")
    c.drawString(70, 595, "1")
    c.drawString(200, 595, "2")
    c.drawString(360, 595, "3")
    c.save()


def _borderless_table(path: str) -> None:
    """A borderless table whose first row is bold."""
    c = canvas.Canvas(path, pagesize=LETTER)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(60, 700, "Name")
    c.drawString(200, 700, "Age")
    c.drawString(320, 700, "City")
    c.setFont("Helvetica", 10)
    c.drawString(60, 680, "Alice")
    c.drawString(200, 680, "30")
    c.drawString(320, 680, "Paris")
    c.drawString(60, 660, "Bob")
    c.drawString(200, 660, "25")
    c.drawString(320, 660, "Rome")
    c.save()


def _option_grid(path: str) -> None:
    """A 2x2 block of MCQ options — aligned, but not a table."""
    c = canvas.Canvas(path, pagesize=LETTER)
    c.setFont("Helvetica", 10)
    c.drawString(60, 700, "(A) apple")
    c.drawString(220, 700, "(B) banana")
    c.drawString(60, 680, "(C) cherry")
    c.drawString(220, 680, "(D) date")
    c.save()


def _numeric_grid(path: str) -> None:
    """A 2x2 block of numbers — a table."""
    c = canvas.Canvas(path, pagesize=LETTER)
    c.setFont("Helvetica", 10)
    c.drawString(60, 700, "1")
    c.drawString(220, 700, "2")
    c.drawString(60, 680, "3")
    c.drawString(220, 680, "4")
    c.save()


def _horizontally_ruled(path: str) -> None:
    """Horizontal rules only: the columns come from the words themselves."""
    c = canvas.Canvas(path, pagesize=LETTER)
    for y in (700, 660, 620):
        c.line(60, y, 500, y)
    c.setFont("Helvetica", 10)
    for y in (675, 635):
        c.drawString(70, y, "Alpha")
        c.drawString(200, y, "Beta")
        c.drawString(350, y, "Gamma")
    c.save()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _docx_xml(path: str):
    """(document.xml root, docx bytes) for a converted PDF."""
    result = run_pipeline(
        path,
        source_name=os.path.basename(path),
        max_bytes=50 * 1024 * 1024,
        max_pages=50,
        mode="standard",
    )
    assert result.ok, result.message
    data, _report = build_docx(result.model)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        root = etree.fromstring(z.read("word/document.xml"))
    return root, result.model


def _tables(root):
    return root.findall(".//w:tbl", NS)


def _cell_text(tc) -> str:
    return "".join(t.text or "" for t in tc.findall(".//w:t", NS))


def _body_paragraphs(root):
    """Paragraph texts that are NOT inside a table (body prose)."""
    body = root.find("w:body", NS)
    out = []
    for p in body.findall("w:p", NS):
        out.append("".join(t.text or "" for t in p.findall(".//w:t", NS)))
    return out


class TableReconstructionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="mathpipe-tables-")
        cls.ruled = os.path.join(cls.tmp, "ruled.pdf")
        cls.ruled_caption = os.path.join(cls.tmp, "ruled-caption.pdf")
        cls.ruled_broken = os.path.join(cls.tmp, "ruled-broken.pdf")
        cls.borderless = os.path.join(cls.tmp, "borderless.pdf")
        cls.options = os.path.join(cls.tmp, "options.pdf")
        cls.numeric = os.path.join(cls.tmp, "numeric.pdf")
        cls.hrules = os.path.join(cls.tmp, "hrules.pdf")
        _ruled_table(cls.ruled)
        _ruled_table(cls.ruled_caption, caption=True)
        _ruled_table(cls.ruled_broken, break_middle=True)
        _borderless_table(cls.borderless)
        _option_grid(cls.options)
        _numeric_grid(cls.numeric)
        _horizontally_ruled(cls.hrules)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # (a) ruled table with a merged header cell
    def test_ruled_table_with_merged_header(self):
        root, model = _docx_xml(self.ruled)
        tables = _tables(root)
        self.assertEqual(len(tables), 1, "a bordered grid is exactly one Word table")

        rows = tables[0].findall("./w:tr", NS)
        self.assertEqual(len(rows), 3, "three ruled row bands")

        header_cells = rows[0].findall("./w:tc", NS)
        self.assertEqual(len(header_cells), 1, "the header cell spans the whole row")
        span = header_cells[0].find(".//w:gridSpan", NS)
        self.assertIsNotNone(span, "the merged header carries w:gridSpan")
        self.assertEqual(span.get(f"{{{W}}}val"), "3")
        self.assertEqual(_cell_text(header_cells[0]), "Header")

        # The two body rows keep three columns each, with the cell text.
        body_rows = [rows[1].findall("./w:tc", NS), rows[2].findall("./w:tc", NS)]
        self.assertEqual([[_cell_text(c) for c in r] for r in body_rows],
                         [["A", "B", "C"], ["1", "2", "3"]])

        # The table text is not repeated as body prose.
        prose = " ".join(_body_paragraphs(root))
        for token in ("Header", "Repairing"):
            self.assertNotIn(token, prose)
        self.assertNotIn("A B C", prose)

    # (b) borderless table with a bold header
    def test_borderless_table_with_bold_header(self):
        root, model = _docx_xml(self.borderless)
        tables = _tables(root)
        self.assertEqual(len(tables), 1, "a borderless table is still a table")

        spec = None
        for page in model["document"]["pages"]:
            for block in page["blocks"]:
                if block.get("type") == "table":
                    spec = block["table"]
        self.assertIsNotNone(spec)
        self.assertEqual(spec.get("headerRows"), [0], "the bold first row is the header")
        self.assertEqual(spec["rows"][0], ["Name", "Age", "City"])

        rows = tables[0].findall("./w:tr", NS)
        header = rows[0]
        self.assertIsNotNone(header.find(".//w:tblHeader", NS), "the header row repeats")
        for tc in header.findall("./w:tc", NS):
            runs = tc.findall(".//w:r", NS)
            self.assertTrue(runs, "header cells carry runs")
            for run in runs:
                self.assertIsNotNone(run.find("w:rPr/w:b", NS), "header text is bold")

    # (c) option grid vs numeric grid
    def test_option_grid_is_not_a_table(self):
        root, _model = _docx_xml(self.options)
        self.assertEqual(len(_tables(root)), 0, "an (A)/(B)/(C)/(D) grid is not a table")

    def test_numeric_2x2_grid_is_a_table(self):
        root, _model = _docx_xml(self.numeric)
        tables = _tables(root)
        self.assertEqual(len(tables), 1, "a 2x2 numeric grid is a table")
        rows = tables[0].findall("./w:tr", NS)
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            [[_cell_text(c) for c in r.findall("./w:tc", NS)] for r in rows],
            [["1", "2"], ["3", "4"]],
        )

    # (d) caption binding
    def test_caption_is_bound_to_the_table(self):
        root, model = _docx_xml(self.ruled_caption)
        tables = _tables(root)
        self.assertEqual(len(tables), 1)
        spec = None
        for page in model["document"]["pages"]:
            for block in page["blocks"]:
                if block.get("type") == "table":
                    spec = block["table"]
        self.assertIsNotNone(spec)
        self.assertEqual(spec.get("caption"), "Table 1: Frequency distribution")
        self.assertEqual(spec.get("captionPosition"), "above")

        body = root.find("w:body", NS)
        captions = []
        seen_table = False
        for child in body:
            if child.tag == f"{{{W}}}tbl":
                seen_table = True
            elif child.tag == f"{{{W}}}p":
                style = child.find("w:pPr/w:pStyle", NS)
                if style is not None and style.get(f"{{{W}}}val") == "Caption":
                    captions.append(
                        ("".join(t.text or "" for t in child.findall(".//w:t", NS)), seen_table)
                    )
        self.assertEqual(len(captions), 1, "exactly one caption paragraph")
        text, after_table = captions[0]
        self.assertEqual(text, "Table 1: Frequency distribution")
        self.assertFalse(after_table, "a caption above the table is emitted before it")

    # T3: horizontal rules only — the columns come from the words
    def test_horizontal_rules_only_infers_columns(self):
        root, model = _docx_xml(self.hrules)
        tables = _tables(root)
        self.assertEqual(len(tables), 1, "a horizontally ruled band is a table")
        rows = tables[0].findall("./w:tr", NS)
        self.assertEqual(
            [[_cell_text(c) for c in r.findall("./w:tc", NS)] for r in rows],
            [["Alpha", "Beta", "Gamma"], ["Alpha", "Beta", "Gamma"]],
        )

    # T9: a structure that cannot be trusted degrades to an image crop
    def test_invalid_structure_falls_back_to_image(self):
        root, model = _docx_xml(self.ruled_broken)
        self.assertEqual(len(_tables(root)), 0, "a broken grid is never shipped as a table")
        status = None
        for page in model["document"]["pages"]:
            for block in page["blocks"]:
                if block.get("type") == "table":
                    status = block["table"].get("parseStatus")
                    reason = block["table"].get("fallbackReason")
        self.assertEqual(status, "fallback_image")
        self.assertEqual(reason, "invalid_structure")
        self.assertTrue(
            root.findall(".//w:drawing", NS),
            "the region ships as an image crop instead of a broken table",
        )


if __name__ == "__main__":
    unittest.main()
