"""Validation of the evidence returned by the model."""

import re

from agent.schemas import SubmittedFile

WHITESPACE = re.compile(r"\s+")


def normalise(text: str) -> str:
    return WHITESPACE.sub(" ", text).strip().lower()


def find_file(files: list[SubmittedFile], file_id: str | None) -> SubmittedFile | None:
    for file in files:
        if file.id == file_id:
            return file
    return None


def evidence_in_file(evidence: str, file: SubmittedFile) -> bool:
    """True when the quoted passage appears in the file text, ignoring whitespace and case."""
    needle = normalise(evidence)
    if not needle:
        return False
    return needle in normalise(file.text)
