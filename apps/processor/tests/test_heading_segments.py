"""Heading span segmentation (ADR-2/ADR-3 applied to headings).

The two strings below are exact Mathematics - II.pdf heading extractions
whose math leaked as plain text (G5). Headings must pass through the same
span segmentation + single promotion gate as paragraphs: enrich attaches
ordered segments, the builder renders them inside the heading paragraph —
never the headline content a second time.
"""
from __future__ import annotations

import copy
import io
import os
import sys
import unittest
import zipfile
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from src.mathengine.enrich import _segment_paragraph, enrich_blocks  # noqa: E402
from src.mathengine.recognize import DeterministicAsciiRecognizer  # noqa: E402
from src.understanding.blocks import Block  # noqa: E402
from src.word.builder import build_docx  # noqa: E402
try:
    from test_docx import sample_model  # noqa: E402
except ImportError:
    from tests.test_docx import sample_model  # noqa: E402

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
NS = {"w": W_NS, "m": M_NS}

#: Exact leaking heading strings from Mathematics - II.pdf.
INTEGRAL_HEADING = "∫ ( 2 - x 2 - − 1 y 2 2 ) d x + ( x 2 + y 2 ) d y"
CAUCHY_HEADING = "i) Define Cauchy-Riemann 2 2 / 0 equations. Check whether the function 𝑓(𝑧) = √|𝑥𝑦| satisfies"
CAUCHY_MATH = "𝑓(𝑧) = √|𝑥𝑦|"


def _heading_block(text: str) -> Block:
    return Block(
        id="h1",
        kind="heading",
        page_number=1,
        bbox=[0, 0, 1, 1],
        text=text,
        size=14.0,
        bold=True,
        confidence=0.99,
    )


def _doc_xml(data: bytes) -> ET.Element:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return ET.fromstring(z.read("word/document.xml"))


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _text_outside_omath(p) -> str:
    out: list[str] = []
    for child in p:
        if _local(child.tag) == "oMath":
            continue
        for t in child.iter(f"{{{W_NS}}}t"):
            out.append(t.text or "")
    return "".join(out)


def _text_inside_omath(p) -> str:
    out: list[str] = []
    for child in p:
        if _local(child.tag) != "oMath":
            continue
        for t in child.iter():
            if _local(t.tag) == "t":
                out.append(t.text or "")
    return "".join(out)


def _heading_model(segments: list) -> dict:
    model = copy.deepcopy(sample_model())
    model["document"]["pages"][0]["blocks"] = [
        {
            "id": "h1",
            "type": "heading",
            "bbox": [0, 0, 1, 1],
            "readingOrder": 1,
            "style": {},
            "content": INTEGRAL_HEADING,
            "segments": segments,
        }
    ]
    return model


class TestHeadingEnrichDispatch(unittest.TestCase):
    """Headings must receive the same span segmentation as paragraphs."""

    def setUp(self):
        self.rec = DeterministicAsciiRecognizer()

    def test_integral_heading_gets_segments(self):
        block = _heading_block(INTEGRAL_HEADING)
        enrich_blocks([block], recognizer=self.rec)
        segs = block.extra.get("segments")
        self.assertIsInstance(segs, list)
        self.assertTrue(segs)
        self.assertEqual("".join(s["text"] for s in segs), INTEGRAL_HEADING)
        self.assertGreaterEqual(sum(1 for s in segs if s["kind"] == "math"), 1)

    def test_cauchy_heading_gets_segments(self):
        block = _heading_block(CAUCHY_HEADING)
        enrich_blocks([block], recognizer=self.rec)
        segs = block.extra.get("segments")
        self.assertIsInstance(segs, list)
        self.assertEqual("".join(s["text"] for s in segs), CAUCHY_HEADING)
        math_texts = [s["text"] for s in segs if s["kind"] == "math"]
        self.assertIn(CAUCHY_MATH, math_texts)
        # Prose and the rejected "2 2 / 0" fragment stay text (never guessed).
        text_texts = "".join(s["text"] for s in segs if s["kind"] == "text")
        self.assertEqual(text_texts, CAUCHY_HEADING.replace(CAUCHY_MATH, ""))


class TestHeadingBuilderEmission(unittest.TestCase):
    def test_heading_with_segments_renders_omath_once(self):
        rec = DeterministicAsciiRecognizer()
        segs = _segment_paragraph(INTEGRAL_HEADING, rec)
        self.assertTrue(segs)
        data, report = build_docx(_heading_model(segs))
        root = _doc_xml(data)
        paras = root.findall(".//w:body/w:p", NS)
        self.assertEqual(len(paras), 1)
        p = paras[0]
        # Heading style preserved; math rides inside the heading paragraph.
        pstyle = p.find("w:pPr/w:pStyle", NS)
        self.assertIsNotNone(pstyle)
        self.assertEqual(pstyle.get(f"{{{W_NS}}}val"), "Heading1")
        omaths = p.findall("m:oMath", NS)
        self.assertEqual(len(omaths), 1)
        # Covered exactly once: nothing duplicated as plain heading text.
        self.assertEqual(_text_outside_omath(p), "")
        inside = _text_inside_omath(p)
        self.assertIn("∫", inside)
        self.assertIn("x", inside)
        self.assertEqual(report["equations"], 1)
        self.assertEqual(report["equation_fallbacks"], 0)


class TestSegmenterCoverage(unittest.TestCase):
    """ADR-2: segments cover the heading text exactly once."""

    def test_heading_strings_covered_exactly_once(self):
        rec = DeterministicAsciiRecognizer()
        for text in (INTEGRAL_HEADING, CAUCHY_HEADING):
            segs = _segment_paragraph(text, rec)
            self.assertIsNotNone(segs, text)
            self.assertEqual("".join(seg["text"] for seg in segs), text)


if __name__ == "__main__":
    unittest.main()
