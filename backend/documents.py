"""
Getting text out of an uploaded resume, whatever format it arrived in.

Two formats, one contract: bytes in, plain text out, and a clear refusal when
the file cannot yield any. Everything downstream works on text, so this is the
only place that needs to know a PDF from a DOCX.

Detection is by content, never by filename. An extension is attacker-controlled
input and proves nothing about what the bytes actually are.
"""

from __future__ import annotations

import io

import pymupdf

PDF_MAGIC = b"%PDF-"
# DOCX is a zip container; every one starts with the local file header.
ZIP_MAGIC = b"PK\x03\x04"

SUPPORTED = ("PDF", "DOCX")


class UnreadableDocument(Exception):
    """The bytes are a recognised format but could not be read."""


class UnsupportedDocument(Exception):
    """The bytes are not a format we handle."""


def detect(content: bytes) -> str | None:
    """Return "pdf", "docx", or None, based on the bytes themselves."""
    if content.startswith(PDF_MAGIC):
        return "pdf"
    if content.startswith(ZIP_MAGIC):
        return "docx"
    return None


def _extract_pdf(content: bytes) -> str:
    try:
        with pymupdf.open(stream=content, filetype="pdf") as document:
            pages = [
                document.load_page(index).get_text("text")
                for index in range(len(document))
            ]
    except Exception as exc:
        raise UnreadableDocument(str(exc)) from exc
    return "\n".join(pages).strip()


def _extract_docx(content: bytes) -> str:
    try:
        import docx
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise UnreadableDocument("DOCX support is not installed.") from exc

    try:
        document = docx.Document(io.BytesIO(content))
    except Exception as exc:
        # A zip that is not a Word file lands here - .pages, .odt, a renamed
        # archive. All of them are "unsupported" rather than "corrupt".
        raise UnsupportedDocument(str(exc)) from exc

    parts: list[str] = [paragraph.text for paragraph in document.paragraphs]

    # Plenty of resumes lay themselves out in tables, and their text lives
    # nowhere else in the document body.
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                parts.append("  ".join(cells))

    return "\n".join(part for part in parts if part.strip()).strip()


def extract_text(content: bytes) -> tuple[str, str]:
    """
    Extract text from an uploaded resume.

    Returns (text, kind). Raises UnsupportedDocument for anything that is not a
    PDF or DOCX, and UnreadableDocument when the format is right but the file
    is damaged or protected.
    """
    kind = detect(content)
    if kind == "pdf":
        return _extract_pdf(content), "pdf"
    if kind == "docx":
        return _extract_docx(content), "docx"
    raise UnsupportedDocument("Not a PDF or DOCX file.")
