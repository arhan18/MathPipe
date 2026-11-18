"""Equation-number detection (§11.5): trailing "(4)" belongs to the equation,
never to the prose. Stored as linked metadata, not floating text."""
from __future__ import annotations

import re
from dataclasses import dataclass

_NUMBER_RE = re.compile(r"^(?P<body>.*?)[\(\[\{](?P<num>\d+[a-z]?)\)[\]\}]?\s*$")


@dataclass(frozen=True)
class NumberedEquation:
    body: str
    number: str | None


def split_equation_number(text: str) -> NumberedEquation:
    stripped = text.strip()
    m = _NUMBER_RE.match(stripped)
    if not m:
        return NumberedEquation(body=stripped, number=None)
    body = m.group("body").strip()
    # Guard: "(see 4)" style prose references and short fragments.
    if len(body) < 2:
        return NumberedEquation(body=stripped, number=None)
    return NumberedEquation(body=body, number=m.group("num"))
