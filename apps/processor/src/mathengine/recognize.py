"""MathRecognizer interface + deterministic baseline (§11.2, §59.1, §60.1).

Never use one recognizer as unconditional truth. The deterministic parser
below handles born-digital ASCII/LaTeX-subset equations with structural
validation; anything it cannot parse cleanly escalates instead of guessing.
External models (pix2tex, Nougat, VLMs) sit behind GatedRecognizer and run
only after the license gate approves their exact weights.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from . import mathir
from .normalize import normalize_latex


@dataclass(frozen=True)
class Recognition:
    latex: str
    mathir: dict
    confidence: float
    recognizer: str


class MathRecognizer(Protocol):
    def recognize(self, region_text: str) -> Recognition: ...


class LicenseNotCleared(Exception):
    pass


class GatedRecognizer:
    """Placeholder for external models. Refuses until docs/license-audit.md
    approves the exact model/version."""

    def __init__(self, name: str):
        self.name = name

    def recognize(self, region_text: str) -> Recognition:
        raise LicenseNotCleared(
            f"{self.name} is not cleared for use: record code + weight licenses "
            "in docs/license-audit.md first (architecture §9)."
        )


_TOKEN_RE = re.compile(
    r"\\[a-zA-Z]+|[\d.]+|[a-zA-Z]+|[\^_+\-*/=(),\[\]{}|]|.",
    re.DOTALL,
)

_FUNCTIONS = {"sin", "cos", "tan", "sec", "csc", "cot", "cosec", "log", "ln", "lim", "exp"}
_OPERATORS = {"+", "-", "*", "=", ","}

#: Normalized LaTeX commands the parser understands. Operator commands
#: become operator nodes (clean parse); variable commands become text runs
#: rendered as their unicode glyph; n-ary commands become operator nodes
#: holding ∫/∑/∏ (schema-valid, renders natively, counts as math kernel).
_COMMAND_OPERATORS = {
    "\\times": "*", "\\ast": "*", "\\cdot": "*", "\\bullet": "*",
    "\\div": "/", "\\pm": "±",
    "\\leq": "≤", "\\le": "≤", "\\geq": "≥", "\\ge": "≥",
    "\\neq": "≠", "\\approx": "≈", "\\equiv": "≡",
    "\\in": "∈", "\\notin": "∉", "\\cup": "∪", "\\cap": "∩",
    "\\subset": "⊂", "\\to": "→", "\\gets": "←",
    "\\Rightarrow": "⇒", "\\Longrightarrow": "⇒",
    "\\longrightarrow": "→", "\\ldots": "…", "\\dots": "…",
}
_COMMAND_VARS = {
    "\\alpha": "α", "\\beta": "β", "\\gamma": "γ", "\\delta": "δ",
    "\\epsilon": "ε", "\\varepsilon": "ε", "\\theta": "θ",
    "\\lambda": "λ", "\\mu": "μ", "\\pi": "π", "\\sigma": "σ",
    "\\phi": "φ", "\\varphi": "φ", "\\omega": "ω",
    "\\Delta": "Δ", "\\Sigma": "Σ", "\\Omega": "Ω",
    "\\infty": "∞", "\\partial": "∂", "\\nabla": "∇",
    "\\emptyset": "∅",
}
_NARY_OPERATORS = {"\\int": "∫", "\\sum": "∑", "\\prod": "∏"}


class _Parser:
    def __init__(self, tokens: list[str]):
        self.tokens = tokens
        self.pos = 0
        self.clean = True

    def peek(self) -> str | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def next(self) -> str:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def parse_expr(self) -> dict:
        left = self.parse_term()
        while self.peek() in ("+", "-", "="):
            op = self.next()
            right = self.parse_term()
            left = mathir.row(left, mathir.operator(op), right)
        return left

    def parse_term(self) -> dict:
        left = self.parse_factor()
        while True:
            tok = self.peek()
            if tok == "*":
                self.next()
                left = mathir.row(left, mathir.operator("*"), self.parse_factor())
            elif tok == "/":
                self.next()
                left = self._divide_last(left, self.parse_factor())
            elif tok is None or tok in (")", "]", "}"):
                return left
            else:
                # Implicit multiplication ("3x", ")x", "2sin(x)") or a stray
                # glyph (extensible fence pieces ⎜ ⎟, hats): parse_factor
                # folds known structure cleanly and preserves unknowns as
                # unclean text instead of truncating the expression.
                left = mathir.row(left, self.parse_factor())

    @staticmethod
    def _divide_last(left: dict, denom: dict) -> dict:
        # "/" binds the nearest factor: "1/2x" is 1/(2x), and sequential
        # fractions stay whole ("1/2 (B) 1/3" keeps both fractions instead
        # of nesting the row under one bar or dropping content).
        if left.get("type") == "row" and left.get("children"):
            *head, last = left["children"]
            if last.get("type") != "operator":
                return mathir.row(*head, mathir.fraction(last, denom))
        return mathir.fraction(left, denom)

    def _parse_bound(self) -> dict | None:
        """Parse one n-ary bound (upper/lower) as a complete unit.

        Bounds arrive braced from block geometry ("^{2}", "_{-4}") so a
        signed multi-char bound ("-4", "a+b" is rejected upstream) survives
        as one node. Bare signs ("∫^- _-") fail here and stay unclaimed
        instead of minting a "-" bound. Returns None when no bound follows.
        """
        if self.peek() == "{":
            expr = self._braced_expr()
            return expr
        sign = None
        if self.peek() in ("-", "+"):
            sign = self.next()
        base = self.parse_base()
        if base.get("type") == "text" and base.get("value", "") == "":
            return None
        # A lone sign with no following base ("∫^- x") is not a bound:
        # it would render as a "-" limit (fake-OMML). Fail instead.
        if base.get("type") == "operator" and base.get("symbol") in ("-", "+") and sign is not None:
            return None
        if sign is not None:
            # "-4" as row("-", "4") — renders as "-4" in OMML sub/sup.
            return mathir.row(mathir.operator(sign), base)
        # Guard: a bare fence/hat fragment ("b", "l", "^h", "[", "]")
        # is bracket litter or hat-soup, never a bound.
        if base.get("type") == "text":
            val = str(base.get("value", "")).strip()
            if val in ("", "^", "_", "h", "^h", "b", "l", "[", "]", "(", ")", "⎛", "⎜", "⎝", "⎞", "⎟", "⎠"):
                return None
        return base

    def parse_factor(self) -> dict:
        base = self.parse_base()
        while self.peek() in ("^", "_"):
            op = self.next()
            script = self.parse_base()
            base = mathir.superscript(base, script) if op == "^" else mathir.subscript(base, script)
        return base

    def _braced_expr(self) -> dict | None:
        """Parse "{ <expr> }"; None when the group is malformed."""
        if self.peek() != "{":
            return None
        self.next()
        inner = self.parse_expr()
        if self.peek() != "}":
            return None
        self.next()
        return inner

    def parse_base(self) -> dict:
        tok = self.peek()
        if tok is None:
            self.clean = False
            return mathir.text("")
        if tok == "(":
            self.next()
            inner = self.parse_expr()
            if self.peek() == ")":
                self.next()
                return mathir.fence("(", ")", inner)
            self.clean = False
            return inner
        if tok == "[":
            self.next()
            inner = self.parse_expr()
            if self.peek() == "]":
                self.next()
                return mathir.fence("[", "]", inner)
            self.clean = False
            return inner
        if tok in ("sqrt", r"\sqrt"):
            self.next()
            if self.peek() == "(":
                self.next()
                inner = self.parse_expr()
                if self.peek() == ")":
                    self.next()
                return mathir.root(inner)
            if self.peek() is None:
                self.clean = False
                return mathir.text(tok)
            # Bare radicand: born-digital "√3" has no parentheses.
            return mathir.root(self.parse_factor())
        if tok == "{":
            self.next()
            inner = self.parse_expr()
            if self.peek() == "}":
                self.next()
                return inner
            self.clean = False
            return inner
        if tok == "\\frac":
            self.next()
            numerator = self._braced_expr()
            denominator = self._braced_expr()
            if numerator is None or denominator is None:
                self.clean = False
                return mathir.text(tok)
            return mathir.fraction(numerator, denominator)
        if tok in _NARY_OPERATORS:
            self.next()
            base = mathir.operator(_NARY_OPERATORS[tok])
            # Integral/sum/product bounds in either script order (∫_a^b or
            # ∫^b_a) become a limit node → structured <m:nary>. A single
            # bound stays an honest sub/superscript on the operator.
            lower: dict | None = None
            upper: dict | None = None
            for _ in range(2):
                nxt = self.peek()
                if nxt == "_" and lower is None:
                    self.next()
                    lower = self._parse_bound()
                    if lower is None:
                        self.clean = False
                        break
                elif nxt == "^" and upper is None:
                    self.next()
                    upper = self._parse_bound()
                    if upper is None:
                        self.clean = False
                        break
                else:
                    break
            if lower is not None and upper is not None:
                # Text base (not operator) routes to <m:nary> in OMML —
                # the same limit shape the schema and renderer expect.
                return mathir.limit(mathir.text(_NARY_OPERATORS[tok]), lower, upper)
            node: dict = base
            if lower is not None:
                node = mathir.subscript(node, lower)
            if upper is not None:
                node = mathir.superscript(node, upper)
            return node
        if tok in _COMMAND_OPERATORS:
            self.next()
            return mathir.operator(_COMMAND_OPERATORS[tok])
        if tok in _COMMAND_VARS:
            self.next()
            return mathir.text(_COMMAND_VARS[tok])
        if tok in _FUNCTIONS or (tok.startswith("\\") and tok[1:] in _FUNCTIONS):
            self.next()
            name = tok.lstrip("\\")
            if self.peek() == "^":
                self.next()
                sign = None
                if self.peek() in ("-", "+"):
                    sign = self.next()
                    if self.peek() == "^":
                        self.next()
                sup_node = self.parse_base()
                if sign is not None:
                    sup_node = mathir.row(mathir.operator(sign), sup_node)
                fn_node: dict = mathir.superscript(mathir.text(name), sup_node)
                if self.peek() == "(":
                    fn_node = mathir.row(fn_node, self.parse_base())
                return fn_node
            args = []
            if self.peek() == "(":
                self.next()
                if self.peek() == ")":
                    # Empty call "log( )": a bare name, not a call with a
                    # ")" argument (which rendered as "log)" OMML).
                    self.next()
                    return mathir.function(name)
                args.append(self.parse_expr())
                if self.peek() == ")":
                    self.next()
            return mathir.function(name, *args)
        if re.fullmatch(r"[\d.]+|[a-zA-Z]+", tok or ""):
            self.next()
            return mathir.text(tok or "")
        if tok in _OPERATORS:
            self.next()
            return mathir.operator(tok)
        # Unknown token: preserve as text but mark unclean.
        self.next()
        self.clean = False
        return mathir.text(tok)


#: Fraction operands that are bracket litter / hat-soup, never real math
#: ("^h", "b l", bare fences). Single letters stay valid variables ("a/b"
#: must keep its <m:f>): only multi-char litter and fences are debris here.
_FRACTION_DEBRIS_TEXTS = frozenset({
    "", "^", "_", "^h", "b l",
    "[", "]", "(", ")", "{", "}", "⎛", "⎜", "⎝", "⎞", "⎟", "⎠",
    ">H",
    "+", "-", "*", "=", "/", "−", "–", "—",
})


def _fraction_texts(node: dict | None, out: list[str]) -> list[str]:
    if node is None:
        return out
    if isinstance(node, dict):
        if node.get("type") in ("text", "operator"):
            out.append(str(node.get("value", node.get("symbol", ""))).strip())
        for value in node.values():
            if isinstance(value, (dict, list)):
                _fraction_texts(value, out)
    elif isinstance(node, list):
        for value in node:
            _fraction_texts(value, out)
    return out


def _fraction_has_debris(root: dict) -> bool:
    """True when any fraction side is pure debris (hat-soup/bracket litter)."""
    stack: list = [root]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            if cur.get("type") == "fraction":
                for side in (cur.get("numerator"), cur.get("denominator")):
                    texts = [t for t in _fraction_texts(side, []) if t]
                    if not texts:
                        return True
                    joined = " ".join(texts).strip()
                    if joined in _FRACTION_DEBRIS_TEXTS:
                        return True
                    if texts and all(t in _FRACTION_DEBRIS_TEXTS for t in texts):
                        return True
            for value in cur.values():
                if isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(cur, list):
            stack.extend(cur)
    return False


class DeterministicAsciiRecognizer:
    """ASCII/LaTeX-subset → MathIR. Reports honesty-graded confidence."""

    name = "deterministic-ascii-0.1"

    def recognize(self, region_text: str) -> Recognition:
        normalized = normalize_latex(region_text)
        tokens = [t for t in _TOKEN_RE.findall(normalized) if t.strip()]
        if not tokens:
            return Recognition(latex="", mathir=mathir.wrap(mathir.text("")), confidence=0.0, recognizer=self.name)
        parser = _Parser(tokens)
        root = parser.parse_expr()
        leftover = parser.pos != len(tokens)
        if leftover:
            parser.clean = False
        issues = mathir.validate_mathir(mathir.wrap(root))
        if issues:
            return Recognition(
                latex=normalized,
                mathir=mathir.wrap(mathir.text(region_text.strip())),
                confidence=0.35,
                recognizer=self.name,
            )
        if not mathir.has_math_kernel(root):
            # Parses cleanly but proves no mathematics ("(A) 1", "[1]",
            # "Part-C", bare numbers): honest low confidence so the caller
            # escalates instead of minting a fake equation.
            return Recognition(
                latex=normalized,
                mathir=mathir.wrap(mathir.text(region_text.strip())),
                confidence=0.35,
                recognizer=self.name,
            )
        if _fraction_has_debris(root):
            # Stacked debris ("^h/2", "b/2", "b l/2") parses as a fraction
            # but proves no mathematics — honest fallback, never fake OMML.
            return Recognition(
                latex=normalized,
                mathir=mathir.wrap(mathir.text(region_text.strip())),
                confidence=0.35,
                recognizer=self.name,
            )
        confidence = 0.97 if parser.clean else 0.72
        return Recognition(latex=normalized, mathir=mathir.wrap(root), confidence=confidence, recognizer=self.name)
