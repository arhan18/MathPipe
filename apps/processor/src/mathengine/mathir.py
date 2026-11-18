"""MathIR construction + schema validation (math-ir/v1.0).

Every equation persists schemaVersion + content hash for caching/provenance.
Validation uses the checked-in canonical schema — the same file the
TypeScript gate enforces.
"""
from __future__ import annotations

import hashlib
import json
import os
from functools import lru_cache

SCHEMA_VERSION = "1.0"

_SCHEMA_PATHS = [
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "packages",
                 "document-model", "schemas", "mathir", "v1", "math-ir.schema.json"),
    "/Volumes/Arhan/MathPipe/math-pdf-to-word/packages/document-model/schemas/mathir/v1/math-ir.schema.json",
]


@lru_cache(maxsize=1)
def load_schema() -> dict:
    for path in _SCHEMA_PATHS:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    raise FileNotFoundError("math-ir.schema.json not found; repo checkout incomplete")


def validate_mathir(doc: dict) -> list[str]:
    """Return a list of human-readable violations (empty = valid)."""
    import jsonschema

    try:
        jsonschema.validate(doc, load_schema())
    except jsonschema.ValidationError as exc:
        return [f"{list(exc.absolute_path)}: {exc.message}"]
    issues = _structural_checks(doc.get("root"))
    # Rectangular matrices (schema allows ragged arrays; product requires rectangular).
    return issues


def _structural_checks(node, path="$") -> list[str]:
    issues: list[str] = []
    if not isinstance(node, dict) or "type" not in node:
        return [f"{path}: node must be an object with a type"]
    if node["type"] == "matrix":
        rows = node.get("rows", [])
        widths = {len(r) for r in rows} if rows else {0}
        if len(widths) > 1:
            issues.append(f"{path}: ragged matrix widths {sorted(widths)}")
    return issues


def canonical_json(doc: dict) -> str:
    return json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(doc: dict) -> str:
    return hashlib.sha256(canonical_json(doc).encode("utf-8")).hexdigest()


# Node constructors -----------------------------------------------------------

def text(value: str) -> dict:
    return {"type": "text", "value": value}


def row(*children: dict) -> dict:
    return {"type": "row", "children": list(children)}


def fraction(numerator: dict, denominator: dict) -> dict:
    return {"type": "fraction", "numerator": numerator, "denominator": denominator}


def superscript(base: dict, script: dict) -> dict:
    return {"type": "superscript", "base": base, "script": script}


def subscript(base: dict, script: dict) -> dict:
    return {"type": "subscript", "base": base, "script": script}


def root(radicand: dict, degree: dict | None = None) -> dict:
    node: dict = {"type": "root", "radicand": radicand}
    if degree is not None:
        node["degree"] = degree
    return node


def operator(symbol: str, *children: dict) -> dict:
    return {"type": "operator", "symbol": symbol, "children": list(children)}


def limit(base: dict, lower: dict, upper: dict) -> dict:
    """N-ary operator with both bounds (∫_a^b); schema requires all three."""
    return {"type": "limit", "base": base, "lower": lower, "upper": upper}


def function(name: str, *arguments: dict) -> dict:
    return {"type": "function", "name": name, "arguments": list(arguments)}


def matrix(rows: list[list[dict]]) -> dict:
    return {"type": "matrix", "rows": rows}


def fence(left: str, right: str, child: dict) -> dict:
    return {"type": "fence", "left": left, "right": right, "child": child}


def wrap(root: dict) -> dict:
    return {"schemaVersion": SCHEMA_VERSION, "root": root}


#: Node types that are mathematical structure by themselves (a bare fence
#: or row of texts is not — "(A) 1" and "[1]" parse cleanly but prove nothing).
_STRUCTURAL_KERNEL_TYPES = frozenset({
    "fraction", "superscript", "subscript", "root", "function",
    "limit", "underover", "matrix", "cases", "accent",
})

#: Operator symbols that carry no mathematical claim on their own
#: (tuple separators, grouping leftovers).
_NON_KERNEL_OPERATORS = frozenset({",", "(", ")", "[", "]", "{", "}"})


def has_math_kernel(node: dict) -> bool:
    """True when a MathIR node holds genuine mathematical structure.

    Pure function used by the recognizer (honest confidence) and the
    enricher (promotion gate): operator-less rows such as ``(A) 1``,
    ``[1]`` or ``Part-C`` must never become editable equations, while a
    lone hyphen joining letters (``Part-C``) is prose punctuation, not a
    minus — it only counts as math beside digits or real structure.
    """
    structural = False
    operators: list[str] = []
    has_digit = False
    stack: list = [node]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            kind = cur.get("type")
            if kind in _STRUCTURAL_KERNEL_TYPES:
                structural = True
            elif kind == "operator":
                operators.append(str(cur.get("symbol", "")))
            elif kind == "text":
                if any(ch.isdigit() for ch in str(cur.get("value", ""))):
                    has_digit = True
            for value in cur.values():
                if isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(cur, list):
            stack.extend(cur)
    if not structural:
        if not operators:
            return False
        if set(operators) <= {"-"} and not has_digit:
            return False
        return any(op not in _NON_KERNEL_OPERATORS for op in operators)
    return True
