"""ADR-2 segments contract: ordered text/math runs in ONE <w:p>.

A block carrying extra["segments"] is covered exactly once by the emitted
segments; content/inlineMath must not be emitted again for that block.
A math segment is emitted as <m:oMath> only (no duplicate text run), so the
equation is covered exactly once and token duplication stays bounded.
Blocks without segments must keep byte-for-byte legacy output.
"""
from __future__ import annotations

import copy
import io
import os
import sys
import types
import unittest
import zipfile
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from src.word.builder import build_docx  # noqa: E402
from src.mathengine.recognize import DeterministicAsciiRecognizer  # noqa: E402
try:
    from test_docx import sample_model  # noqa: E402
except ImportError:
    from tests.test_docx import sample_model  # noqa: E402

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
NS = {"w": W_NS, "m": M_NS}

#: Exact style of string the segment feature exists for (prose host with
#: math embedded mid-sentence).
PROSE = "Evaluate x^2 + 3x + 2 = 0 over the region R"


def _doc_xml(data: bytes) -> ET.Element:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return ET.fromstring(z.read("word/document.xml"))


def _paragraphs(root: ET.Element) -> list:
    return root.findall(".//w:body/w:p", NS)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _text_outside_omath(p) -> str:
    """w:t of the paragraph's own runs, excluding anything inside m:oMath."""
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
        # OMML math runs carry <m:t>, host runs carry <w:t>: collect both.
        for t in child.iter():
            if _local(t.tag) == "t":
                out.append(t.text or "")
    return "".join(out)


def _segments_model(segments: list) -> dict:
    model = copy.deepcopy(sample_model())
    model["document"]["pages"][0]["blocks"] = [
        {
            "id": "seg1",
            "type": "paragraph",
            "bbox": [0, 0, 1, 1],
            "readingOrder": 1,
            "style": {},
            # Host content still carries the whole line: it must NOT be
            # emitted a second time when segments exist.
            "content": PROSE,
            "inlineMath": [{"text": "x^2 + 3x + 2 = 0", "mathir": {"schemaVersion": "1.0", "root": {"type": "text", "value": "dup"}}}],
            "segments": segments,
        }
    ]
    return model


class TestSegmentsEmission(unittest.TestCase):
    def setUp(self):
        rec = DeterministicAsciiRecognizer()
        self.mathir = rec.recognize("x^2 + 3x + 2 = 0").mathir

    def test_text_math_text_in_one_paragraph_in_order(self):
        segments = [
            {"kind": "text", "text": "Evaluate "},
            {"kind": "math", "text": "x^2 + 3x + 2 = 0", "mathir": self.mathir},
            {"kind": "text", "text": " over the region R"},
        ]
        data, report = build_docx(_segments_model(segments))
        paras = _paragraphs(_doc_xml(data))
        self.assertEqual(len(paras), 1)
        p = paras[0]
        self.assertEqual([_local(c.tag) for c in p], ["r", "oMath", "r"])
        outside = _text_outside_omath(p)
        inside = _text_inside_omath(p)
        # Covered exactly once: prose outside, math only inside OMML (no
        # duplicate text run — G8 token-duplication bound).
        self.assertEqual(outside, "Evaluate  over the region R")
        self.assertNotIn("^2", outside)
        self.assertNotIn("+ 3x + 2", outside)
        self.assertIn("x", inside)
        self.assertEqual(report["equations"], 1)
        self.assertEqual(report["equation_fallbacks"], 0)

    def test_unsupported_math_segment_falls_back_to_text(self):
        segments = [
            {"kind": "text", "text": "Evaluate "},
            {
                "kind": "math",
                "text": "∫ x^2 y dx dy",
                "mathir": {"schemaVersion": "1.0", "root": {"type": "teleport"}},
            },
            {"kind": "text", "text": " over the region R"},
        ]
        data, report = build_docx(_segments_model(segments))
        root = _doc_xml(data)
        paras = _paragraphs(root)
        self.assertEqual(len(paras), 1)
        self.assertEqual(root.findall(".//m:oMath", NS), [])
        self.assertEqual(
            _text_outside_omath(paras[0]),
            "Evaluate ∫ x^2 y dx dy over the region R",
        )
        self.assertEqual(report["equations"], 0)
        self.assertEqual(report["equation_fallbacks"], 1)

    def test_math_segment_without_mathir_keeps_text(self):
        segments = [{"kind": "math", "text": "x + 1"}]
        data, report = build_docx(_segments_model(segments))
        paras = _paragraphs(_doc_xml(data))
        self.assertEqual(len(paras), 1)
        self.assertEqual(_text_outside_omath(paras[0]), "x + 1")
        self.assertEqual(report["equations"], 0)


class TestLegacyPathUnchanged(unittest.TestCase):
    def test_empty_segments_equals_no_segments(self):
        base = copy.deepcopy(sample_model())
        with_empty = copy.deepcopy(sample_model())
        with_empty["document"]["pages"][0]["blocks"][4]["segments"] = []
        with_none = copy.deepcopy(sample_model())
        with_none["document"]["pages"][0]["blocks"][4]["segments"] = None
        data_a, _ = build_docx(base)
        data_b, _ = build_docx(with_empty)
        data_c, _ = build_docx(with_none)
        self.assertEqual(data_a, data_b)
        self.assertEqual(data_a, data_c)

    def test_output_matches_pre_segments_builder(self):
        """Byte-for-byte against the backed-up builder (previous code path)."""
        bak = "/tmp/worker_backup/W1/builder.py"
        if not os.path.exists(bak):
            self.skipTest("no pre-change builder backup available")
        mod = types.ModuleType("src.word.builder_baseline")
        mod.__package__ = "src.word"
        sys.modules["src.word.builder_baseline"] = mod
        with open(bak, "r", encoding="utf-8") as f:
            code = f.read()
        exec(compile(code, bak, "exec"), mod.__dict__)  # noqa: S102
        old_bytes, _ = mod.build_docx(sample_model())
        new_bytes, _ = build_docx(sample_model())
        self.assertEqual(old_bytes, new_bytes)


if __name__ == "__main__":
    unittest.main()
