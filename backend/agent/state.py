"""Graph state and the payloads sent to the parallel workers."""

from operator import add
from typing import Annotated, TypedDict

from agent.schemas import (
    ExtractedDocument,
    Finding,
    HumanDecision,
    RequiredDocument,
    SubmittedFile,
    Verdict,
)


class ReviewState(TypedDict, total=False):
    """State of one completeness review. One graph thread equals one review."""

    review_id: str
    required_documents: list[RequiredDocument]
    submitted_files: list[SubmittedFile]
    # Filled by parallel workers, so both lists use an append reducer.
    extracted_documents: Annotated[list[ExtractedDocument], add]
    findings: Annotated[list[Finding], add]
    human_decisions: list[HumanDecision]
    # Set when the reviewer answer was refused. Routes back to human_review.
    review_error: str
    # Authoritative result, written once by the finalize node.
    resolved_findings: list[Finding]
    verdict: Verdict
    report: str
    status: str


class ExtractionInput(TypedDict):
    """Payload of one extraction worker."""

    file: SubmittedFile


class CheckInput(TypedDict):
    """Payload of one requirement check worker."""

    requirement: RequiredDocument
    documents: list[ExtractedDocument]
    files: list[SubmittedFile]
