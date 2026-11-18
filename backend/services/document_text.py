"""Plain text from an uploaded PDF, DOCX or text file."""
from __future__ import annotations

import io
from pathlib import Path

from engine.loaders import BatchFormatError, decode_bytes

from .errors import ServiceError, unprocessable

MAX_BYTES = 5 * 1024 * 1024
TEXT_TYPES = (".txt", ".md")
SUPPORTED = (".pdf", ".docx") + TEXT_TYPES


def pdf_text(data: bytes) -> str:
    import pdfplumber
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def docx_text(data: bytes) -> str:
    import docx
    doc = docx.Document(io.BytesIO(data))
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text for cell in row.cells))
    return "\n".join(parts)


def extract(filename: str, data: bytes, allowed=SUPPORTED) -> str:
    if len(data) > MAX_BYTES:
        raise ServiceError(413, "File is larger than 5 MB")
    ext = Path(filename or "").suffix.lower()
    if ext not in allowed:
        raise ServiceError(415, f"Unsupported file type '{ext or '(none)'}'; use {', '.join(allowed)}")
    try:
        if ext == ".pdf":
            text = pdf_text(data)
        elif ext == ".docx":
            text = docx_text(data)
        else:
            text = decode_bytes(data)
    except BatchFormatError:
        raise unprocessable("The text file is not UTF-8 or Windows-1252") from None
    except Exception:  # noqa: BLE001 - a corrupt document is a user error, not a server error
        raise unprocessable(f"Could not read {filename}; is it a valid {ext[1:].upper()} file?") from None
    if not text.strip():
        raise unprocessable("No extractable text in the document")
    return text
