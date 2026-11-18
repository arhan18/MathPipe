"""Verification stage orchestration (§18.1–§18.4).

Standard mode: free deterministic checks only.
Verified mode: + docx cross-check (when bytes supplied) + bounded repair.
AI-routed region checks are recorded as pending until provider keys exist —
the router decides per region, never the whole document.
"""
from __future__ import annotations

from .compare import Issue, check_docx_consistency, check_equation_structure, check_text_presence
from .compare import check_figure_assets, check_hallucinated_equations, check_math_density, check_question_sequence, check_source_coverage
from .compare import check_replacement_chars
from .repair import MAX_REPAIR_ATTEMPTS, VerificationReport, repair_equation_block


def run_verification(
    model: dict,
    pdf_path: str,
    *,
    mode: str = "standard",
    docx_bytes: bytes | None = None,
) -> VerificationReport:
    report = VerificationReport(mode=mode)
    pages = model.get("document", {}).get("pages", [])
    report.verified_pages = len(pages)

    text_report = check_text_presence(pdf_path, model)
    report.checks.append(text_report.check)
    report.issues.extend(text_report.issues)

    struct_report = check_equation_structure(model)
    report.checks.append(struct_report.check)
    report.issues.extend(struct_report.issues)

    # Recall direction: source content that never reached the model.
    # Deterministic and free, so it runs in standard mode too.
    coverage_report = check_source_coverage(pdf_path, model)
    report.checks.append(coverage_report.check)
    report.issues.extend(coverage_report.issues)

    sequence_report = check_question_sequence(pdf_path, model)
    report.checks.append(sequence_report.check)
    report.issues.extend(sequence_report.issues)

    figure_report = check_figure_assets(model)
    report.checks.append(figure_report.check)
    report.issues.extend(figure_report.issues)

    # Encoding integrity: U+FFFD means content was lost, never a clean ship.
    # Deterministic and free, so it runs in standard mode too.
    replacement_report = check_replacement_chars(model, docx_bytes)
    report.checks.append(replacement_report.check)
    report.issues.extend(replacement_report.issues)

    # Math recall: a math-heavy source with ~0 genuine OMML shipped means
    # equations were dropped before verification (model→DOCX check alone
    # stays green when both sides are empty).
    # Hallucination net: zero-denominator fractions and garbage-text
    # equations must never ship (enrich/OMML reject them; this fails
    # loudly if one ever reaches the model anyway).
    hallucinated_report = check_hallucinated_equations(model)
    report.checks.append(hallucinated_report.check)
    report.issues.extend(hallucinated_report.issues)

    density_report = check_math_density(pdf_path, model, docx_bytes)
    report.checks.append(density_report.check)
    report.issues.extend(density_report.issues)

    if docx_bytes is not None:
        docx_report = check_docx_consistency(model, docx_bytes)
        report.checks.append(docx_report.check)
        report.issues.extend(docx_report.issues)

    if mode == "verified":
        report.checks.append("bounded_repair")
        for page in pages:
            for block in page.get("blocks", []):
                related = [i for i in report.issues if i.block_id == block.get("id") and i.suggested_action == "repair"]
                if not related:
                    continue
                outcome = repair_equation_block(block)
                report.repairs.append(outcome)
                if outcome.fixed:
                    report.issues = [i for i in report.issues if i.block_id != block.get("id")]
        report.checks.append("ai_region_review")
        # Scaffold: no provider keys → every sub-threshold region is flagged,
        # never silently passed. The AI router (§19) consumes this list live.
        for page in pages:
            for block in page.get("blocks", []):
                if block.get("type") == "equation" and float(block.get("confidence", 1.0)) < 0.80:
                    report.issues.append(Issue(
                        page.get("pageNumber", 0), block.get("id"), "equation_structure",
                        "warning", "below AI-review threshold; queued for provider verification",
                        "review",
                    ))

    critical = sum(1 for i in report.issues if i.severity == "critical")
    if critical:
        report.status = "failed"
    elif report.issues:
        report.status = "warnings"
    return report


def max_attempts() -> int:
    return MAX_REPAIR_ATTEMPTS
