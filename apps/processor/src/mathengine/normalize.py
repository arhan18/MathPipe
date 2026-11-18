"""LaTeX normalization (§11.3): canonical forms before comparison/rendering."""
from __future__ import annotations

import re
import unicodedata

# Equivalent commands mapped to one canonical form.
COMMAND_ALIASES = {
    r"\dfrac": r"\frac",
    r"\tfrac": r"\frac",
    r"\cfrac": r"\frac",
    r"\cdot": r"\times",
    r"\ast": r"\times",
    r"\bullet": r"\times",
    r"\ldots": r"\dots",
    r"\longrightarrow": r"\to",
    r"\Longrightarrow": r"\Rightarrow",
    r"\le": r"\leq",
    r"\ge": r"\geq",
    r"\empty": r"\emptyset",
    r"\phi": r"\varphi",
    r"\epsilon": r"\varepsilon",
}

UNICODE_TO_LATEX = {
    "×": r"\times",
    "÷": r"\div",
    "±": r"\pm",
    "√": r"\sqrt",
    "∞": r"\infty",
    "∂": r"\partial",
    "∇": r"\nabla",
    "∑": r"\sum",
    "∏": r"\prod",
    "∫": r"\int",
    "≠": r"\neq",
    "≤": r"\leq",
    "≥": r"\geq",
    "≈": r"\approx",
    "≡": r"\equiv",
    "∈": r"\in",
    "∉": r"\notin",
    "∪": r"\cup",
    "∩": r"\cap",
    "⊂": r"\subset",
    "→": r"\to",
    "←": r"\gets",
    "⇒": r"\Rightarrow",
    "α": r"\alpha",
    "β": r"\beta",
    "γ": r"\gamma",
    "δ": r"\delta",
    "ε": r"\epsilon",
    "θ": r"\theta",
    "λ": r"\lambda",
    "μ": r"\mu",
    "π": r"\pi",
    "σ": r"\sigma",
    "φ": r"\varphi",
    "ω": r"\omega",
    "Δ": r"\Delta",
    "Σ": r"\Sigma",
    "Ω": r"\Omega",
    # Legacy Symbol-font PUA codepoints (U+F000+code): extraction remaps
    # these only for runs whose font is identified as Symbol
    # (understanding/text.py); PDFs without font evidence can still leak
    # them into recognition input, so canonicalize them here as well.
    # Code assignments follow the Adobe Symbol table in text.py
    # (0xCE is element-of; 0xC7 is intersection).
    "\uf06c": r"\lambda",  # 0x6C
    "\uf070": r"\pi",      # 0x70
    "\uf071": r"\theta",   # 0x71
    "\uf0a2": r"\prime",   # 0xA2
    "\uf0a5": r"\infty",   # 0xA5
    "\uf0b9": r"\neq",     # 0xB9
    "\uf0c7": r"\cap",     # 0xC7
    "\uf0ce": r"\in",      # 0xCE
    "\uf0f2": r"\int",     # 0xF2
}


# Letterspaced function names: born-digital PDFs sometimes emit "c o s"
# or "l n" as separate single-letter words, which block assembly joins with
# spaces. Rejoin ONLY spaced single letters that spell a known function —
# gaps are mandatory (\s+) so "s in" (prose) and "sin 4" never match.
_FUNCTION_DESPACE = [
    (re.compile(r"\b([Ss])\s+([Ii])\s+([Nn])\b"), "sin"),
    (re.compile(r"\b([Cc])\s+([Oo])\s+([Ss])\b"), "cos"),
    (re.compile(r"\b([Tt])\s+([Aa])\s+([Nn])\b"), "tan"),
    (re.compile(r"\b([Ll])\s+([Oo])\s+([Gg])\b"), "log"),
    (re.compile(r"\b([Ll])\s+([Ii])\s+([Mm])\b"), "lim"),
    (re.compile(r"\b([Ee])\s+([Xx])\s+([Pp])\b"), "exp"),
    (re.compile(r"\b([Ss])\s+([Ee])\s+([Cc])\b"), "sec"),
    (re.compile(r"\b([Ll])\s+([Nn])\b"), "ln"),
]


def despace_function_names(text: str) -> str:
    """Rejoin letterspaced math function names ("c o s" → "cos")."""
    for pattern, name in _FUNCTION_DESPACE:
        text = pattern.sub(name, text)
    return text


# Single-glyph super/subscripts mapped before NFKC (which would fold them
# to plain digits and lose the script). Values are parser-ready "^n"/"_n".
_SCRIPT_GLYPHS = {
    "⁰": "^0", "¹": "^1", "²": "^2", "³": "^3", "⁴": "^4",
    "⁵": "^5", "⁶": "^6", "⁷": "^7", "⁸": "^8", "⁹": "^9",
    "⁻": "^-", "⁺": "^+",
    "₀": "_0", "₁": "_1", "₂": "_2", "₃": "_3", "₄": "_4",
    "₅": "_5", "₆": "_6", "₇": "_7", "₈": "_8", "₉": "_9",
    "₋": "_-", "₊": "_+",
}

# Unicode operators the ASCII parser cannot tokenize: canonicalize to the
# ASCII form so structure (minus, fraction bar) survives.
_ASCII_OPERATOR_GLYPHS = {
    "−": "-",  # minus sign U+2212
    "–": "-",  # en dash
    "—": "-",  # em dash
    "⁄": "/",  # fraction slash
    "\uf02d": "-",  # legacy Symbol-font PUA minus (code 0x2D)
}


def normalize_latex(latex: str) -> str:
    """Collapse whitespace, resolve aliases, map unicode symbols to commands."""
    s = latex
    # Born-digital PDFs emit single glyphs for super/subscripts ("x²",
    # "x₀"). Map them before NFKC (which would fold them to plain digits
    # and destroy the script structure).
    for glyph, script in _SCRIPT_GLYPHS.items():
        if glyph in s:
            s = s.replace(glyph, script)
    # Collapse doubled Mathematical Alphanumeric Symbols (U+1D400-U+1D7FF)
    # caused by broken CambriaMath ToUnicode CMaps ("𝑥𝑥" -> "𝑥") before NFKC.
    s = re.sub(r"([\U0001D400-\U0001D7FF])\1", r"\1", s)
    # Strip stray extensible-brace characters cleanly to spaces so piecewise
    # lines never leak raw ⎨/⎩ into <m:t>.
    s = re.sub(r"[⎧⎨⎩⎪⎫⎬⎭]+", " ", s)
    # Fold compatibility characters (math-italic 𝑥 → x, ligatures, fullwidth)
    # so the ASCII parser sees variables; combining marks (⃗, ˆ) are dropped.
    s = unicodedata.normalize("NFKC", s)
    s = "".join(
        ch for ch in s
        if unicodedata.category(ch) not in ("Mn", "Me")
    )
    # Unicode dashes/slashes are operators the ASCII parser must see.
    for glyph, ascii_op in _ASCII_OPERATOR_GLYPHS.items():
        if glyph in s:
            s = s.replace(glyph, ascii_op)
    s = re.sub(r"\s+", " ", s).strip()
    # Letterspaced extraction ("c o s", "l n") rejoins before parsing so
    # function structure survives; prose is unaffected (\s+ gaps required).
    s = despace_function_names(s)
    for alias, canonical in COMMAND_ALIASES.items():
        s = s.replace(alias, canonical)
    for uni, cmd in UNICODE_TO_LATEX.items():
        if uni in s:
            if cmd.startswith("\\"):
                s = re.sub(
                    re.escape(uni) + r"(?=[A-Za-z0-9])",
                    lambda _, c=cmd: c + " ",
                    s,
                )
            s = s.replace(uni, cmd)
    # Normalize delimiter spacing variants: "\left(" -> "(" etc. is renderer
    # policy; keep sizing commands but collapse redundant nesting.
    s = re.sub(r"\\left\s*([(\[{|])", r"\g<1>", s)
    s = re.sub(r"\\right\s*([)\]}|])", r"\g<1>", s)
    return s
