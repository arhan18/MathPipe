"""Stage 1 — PDF validation (§6). Pure inspection, no ML, CPU only."""
from __future__ import annotations

from dataclasses import dataclass
from pypdf import PdfReader
from pypdf.errors import PdfReadError


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    error_code: str | None
    page_count: int
    file_bytes: int
    encrypted: bool
    message: str


def validate_pdf(path: str, *, max_bytes: int, max_pages: int) -> ValidationResult:
    """Validate structure, encryption, size and page count.

    Never raises on malformed input — every failure is a typed result.
    """
    import os

    try:
        size = os.path.getsize(path)
    except OSError:
        return ValidationResult(False, "FILE_INVALID", 0, 0, False, "File not found or unreadable.")

    if size == 0:
        return ValidationResult(False, "FILE_INVALID", 0, size, False, "File is empty.")
    if size > max_bytes:
        return ValidationResult(
            False, "FILE_TOO_LARGE", 0, size, False,
            f"File is {size / 1024 / 1024:.1f} MB; limit is {max_bytes / 1024 / 1024:.0f} MB.",
        )

    try:
        reader = PdfReader(path, strict=False)
    except (PdfReadError, ValueError, TypeError) as exc:
        return ValidationResult(False, "FILE_INVALID", 0, size, False, f"Unreadable PDF: {exc}")

    if reader.is_encrypted:
        return ValidationResult(False, "FILE_INVALID", 0, size, True, "Password-protected PDFs are not supported.")

    try:
        pages = len(reader.pages)
    except (PdfReadError, ValueError) as exc:
        return ValidationResult(False, "FILE_INVALID", 0, size, False, f"Page index unreadable: {exc}")

    if pages == 0:
        return ValidationResult(False, "FILE_INVALID", 0, size, False, "PDF has no pages.")
    if pages > max_pages:
        return ValidationResult(
            False, "PAGE_LIMIT_EXCEEDED", pages, size, False,
            f"Document has {pages} pages; limit is {max_pages} per job.",
        )
    return ValidationResult(True, None, pages, size, False, "OK")
