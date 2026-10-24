import io

import pdfplumber
import pymupdf

MIN_CHARS = 50


def extract_text(data: bytes) -> str:
    """pdfplumber first, PyMuPDF fallback. Raises ValueError if no extractable text (likely scanned)."""
    text = ""
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            text = "\n".join(p.extract_text() or "" for p in pdf.pages)
    except Exception:
        pass
    if len(text.strip()) < MIN_CHARS:
        try:
            with pymupdf.open(stream=data, filetype="pdf") as doc:
                text = "\n".join(p.get_text() for p in doc)
        except Exception:
            text = ""
    if len(text.strip()) < MIN_CHARS:
        raise ValueError("no extractable text")
    return text
