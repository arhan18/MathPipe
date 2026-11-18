"""Confidence routing policy (§60.1). Starting thresholds; the golden
corpus calibrates them. A wrong editable equation is worse than a marked
fallback: correctness > editability > cosmetic perfection."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Routing:
    action: str  # accept | secondary_check | fallback_recognizer | escalate
    reason: str


def route_confidence(confidence: float) -> Routing:
    if confidence >= 0.95:
        return Routing("accept", "high confidence after structural validation")
    if confidence >= 0.80:
        return Routing("secondary_check", "lightweight secondary validation")
    if confidence >= 0.60:
        return Routing("fallback_recognizer", "approved fallback recognizer or stronger model")
    return Routing("escalate", "do not silently trust; image fallback + warning metadata")
