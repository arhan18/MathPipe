"""Bounded repair loop (§18.4): max 2 attempts per region, then escalate.

Deterministic repairs only in scaffold: re-normalize LaTeX, re-parse with the
alternate strategy (item-label stripping variants), re-validate MathIR. Each
attempt re-checks; success closes the issue, exhaustion escalates to review.
AI-backed repair plugs in behind the same budget interface later.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..mathengine.mathir import validate_mathir
from ..mathengine.normalize import normalize_latex
from ..mathengine.recognize import DeterministicAsciiRecognizer
from .compare import Issue

MAX_REPAIR_ATTEMPTS = 2


@dataclass
class RepairOutcome:
    block_id: str | None
    attempts: int
    fixed: bool
    escalated: bool
    note: str = ""


def _alternate_parses(text: str) -> list[str]:
    """Deterministic alternates: spacing/alias variants of the same content."""
    variants = [normalize_latex(text)]
    # Variant: drop a leading leftover label character some PDFs emit.
    stripped = text.lstrip("•·-–— ").strip()
    if stripped != text.strip():
        variants.append(normalize_latex(stripped))
    # Variant: collapse internal double spaces aggressively.
    variants.append(" ".join(text.split()))
    seen: list[str] = []
    for v in variants:
        if v not in seen:
            seen.append(v)
    return seen


def repair_equation_block(block: dict, *, recognizer=None) -> RepairOutcome:
    recognizer = recognizer or DeterministicAsciiRecognizer()
    attempts = 0
    original = str(block.get("content", ""))
    for candidate in _alternate_parses(original):
        if attempts >= MAX_REPAIR_ATTEMPTS:
            break
        attempts += 1
        try:
            result = recognizer.recognize(candidate)
        except Exception:
            continue
        if result.confidence >= 0.80 and not validate_mathir(result.mathir):
            block["type"] = "equation"
            block["latex"] = result.latex
            block["mathir"] = result.mathir
            block["confidence"] = result.confidence
            block["recognizer"] = result.recognizer
            block["routing"] = "fallback_recognizer"
            block["repaired"] = True
            return RepairOutcome(block.get("id"), attempts, True, False, "deterministic re-parse accepted")
    return RepairOutcome(block.get("id"), attempts, False, True, "repair budget exhausted; flagged for review")


@dataclass
class VerificationReport:
    mode: str
    checks: list[str] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    repairs: list[RepairOutcome] = field(default_factory=list)
    verified_pages: int = 0
    status: str = "passed"  # passed | warnings | failed

    def summarize(self) -> dict:
        critical = sum(1 for i in self.issues if i.severity == "critical")
        # Ship gate: outputs with critical issues must never be delivered as
        # if complete. Consumers (Modal worker, API) must check this flag.
        return {
            "mode": self.mode,
            "status": self.status,
            "checks": self.checks,
            "issues": len(self.issues),
            "critical": critical,
            "repaired": sum(1 for r in self.repairs if r.fixed),
            "escalated": sum(1 for r in self.repairs if r.escalated),
            "verified_pages": self.verified_pages,
            "shippable": critical == 0,
        }
