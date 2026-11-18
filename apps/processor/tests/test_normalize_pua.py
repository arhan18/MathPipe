"""Legacy Symbol-font PUA normalization (U+F000+code).

Born-digital PDFs using the Adobe Symbol font can leak private-use
codepoints into recognition input when extraction has no font-name
evidence for the run (understanding/text.py remaps them only for
Symbol-typed fonts). normalize_latex must canonicalize every ruled
codepoint so no private-use glyph survives into math parsing.

Code assignments follow the Adobe Symbol table in understanding/text.py
(0xCE is element-of; 0xC7 is intersection).
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.mathengine.normalize import normalize_latex  # noqa: E402


class TestSymbolPuaMappings(unittest.TestCase):
    def test_integral_and_prime(self):
        self.assertEqual(normalize_latex("\uf0f2_0^1 x dx \uf0a2"), r"\int_0^1 x dx \prime")

    def test_greek_symbols(self):
        self.assertEqual(normalize_latex("\uf070 \uf071 \uf06c"), r"\pi \theta \lambda")

    def test_relation_and_set_symbols(self):
        self.assertEqual(normalize_latex("\uf0a5 \uf0b9 \uf0ce \uf0c7"), r"\infty \neq \in \cap")

    def test_symbol_minus(self):
        self.assertEqual(normalize_latex("x \uf02d 3"), "x - 3")

    def test_no_pua_residue(self):
        src = "\uf0f2 \uf0a2 \uf070 \uf071 \uf06c \uf0a5 \uf0b9 \uf0ce \uf0c7 \uf02d"
        out = normalize_latex(src)
        self.assertEqual(out, r"\int \prime \pi \theta \lambda \infty \neq \in \cap -")
        self.assertFalse(
            any(0xE000 <= ord(ch) <= 0xF8FF for ch in out),
            f"private-use codepoint survived normalization: {out!r}",
        )


if __name__ == "__main__":
    unittest.main()
