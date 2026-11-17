"""Helpers producing the unreadable PDF files of the dataset."""

from io import BytesIO

from pypdf import PdfWriter


def blank_pdf() -> bytes:
    """A valid PDF with one empty page: what a scan without OCR looks like to the loader."""
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def corrupted_pdf() -> bytes:
    return b"%PDF-1.7\n" + bytes(range(256)) * 20
