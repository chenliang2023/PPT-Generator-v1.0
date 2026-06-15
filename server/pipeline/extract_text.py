from __future__ import annotations

import re
from pathlib import Path


MIN_EXTRACTED_CHARS = 120


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()


def extract_markdown(path: Path) -> str:
    return normalize_text(path.read_text(encoding="utf-8"))


def extract_pdf_with_pymupdf(path: Path) -> str:
    try:
        import fitz
    except Exception as exc:
        raise RuntimeError("PyMuPDF is not installed") from exc

    parts: list[str] = []
    with fitz.open(path) as doc:
        for page_no, page in enumerate(doc, start=1):
            page_text = page.get_text("text").strip()
            if page_text:
                parts.append(f"\n\n--- Page {page_no} ---\n{page_text}")
    return normalize_text("\n".join(parts))


def extract_pdf_with_pdfplumber(path: Path) -> str:
    try:
        import pdfplumber
    except Exception as exc:
        raise RuntimeError("pdfplumber is not installed") from exc

    parts: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            page_text = (page.extract_text() or "").strip()
            if page_text:
                parts.append(f"\n\n--- Page {page_no} ---\n{page_text}")
    return normalize_text("\n".join(parts))


def extract_pdf(path: Path) -> str:
    errors: list[str] = []
    for extractor in (extract_pdf_with_pymupdf, extract_pdf_with_pdfplumber):
        try:
            text = extractor(path)
            if len(text) >= MIN_EXTRACTED_CHARS:
                return text
        except Exception as exc:
            errors.append(f"{extractor.__name__}: {exc}")

    error_detail = "; ".join(errors) if errors else "no extractor returned enough text"
    raise ValueError(
        "PDF text extraction produced too little text. "
        "The file may be scanned or image-only. OCR is not supported in the first version. "
        f"Detail: {error_detail}"
    )


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".md":
        text = extract_markdown(path)
    elif suffix == ".pdf":
        text = extract_pdf(path)
    else:
        raise ValueError(f"Unsupported input file type: {suffix}")

    if len(text) < MIN_EXTRACTED_CHARS:
        raise ValueError("Extracted text is too short to generate a useful PPT.")
    return text


def suggest_page_count(text: str, *, max_page_count: int) -> int:
    length = len(text)
    if length < 3_000:
        count = 5
    elif length < 8_000:
        count = 8
    elif length < 15_000:
        count = 12
    else:
        count = 15
    return min(count, max_page_count)
