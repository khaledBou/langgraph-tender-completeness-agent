"""Convert uploaded files to plain text."""

from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

TEXT_EXTENSIONS = {".txt", ".md", ".csv"}


def file_to_text(name: str, data: bytes) -> str:
    """Return the text of a .txt, .md, .csv or .pdf file."""
    suffix = Path(name).suffix.lower()

    if suffix == ".pdf":
        reader = PdfReader(BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    if suffix in TEXT_EXTENSIONS:
        return data.decode("utf-8", errors="replace")

    raise ValueError(f"Unsupported file type: {suffix or 'no extension'}")
