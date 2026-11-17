"""Pydantic models shared by the graph state, the LLM structured outputs and the API."""

from typing import Literal

from pydantic import BaseModel, Field

FindingStatus = Literal["present", "missing", "doubtful"]
DecisionStatus = Literal["present", "missing"]
Verdict = Literal["complete", "incomplete"]


class RequiredDocument(BaseModel):
    """One item of the checklist the application must satisfy."""

    code: str = Field(description="Short unique code, for example DC1 or KBIS")
    label: str = Field(description="Human readable name of the document")
    description: str = Field(default="", description="What the document must contain")
    mandatory: bool = True


class SubmittedFile(BaseModel):
    """A file provided by the candidate, already converted to plain text."""

    id: str = Field(default="", description="Stable identifier, assigned by the workflow (F1, F2, ...)")
    name: str
    text: str


class ExtractedDocument(BaseModel):
    """What the workflow understood from one submitted file."""

    file_id: str
    file_name: str
    status: Literal["ok", "unreadable"] = "ok"
    error: str = Field(default="", description="Why the file could not be read, when unreadable")
    document_type: str = Field(default="", description="Type of document, in a few words")
    issuer: str | None = Field(default=None, description="Organisation that issued the document")
    issue_date: str | None = Field(default=None, description="Date found on the document")
    summary: str = Field(default="", description="Two sentences describing the content")


class Finding(BaseModel):
    """Result of checking one checklist item against the submitted files."""

    requirement_code: str
    status: FindingStatus
    matched_file_id: str | None = Field(
        default=None, description="Identifier of the file that covers the requirement"
    )
    matched_file: str | None = Field(default=None, description="Name of that file")
    evidence: str = Field(default="", description="Passage of the file that supports the status")
    reasoning: str = Field(default="", description="Why this status was chosen")
    decided_by: Literal["rule", "model", "reviewer"] = "model"


class HumanDecision(BaseModel):
    """Answer given by a reviewer for a doubtful finding."""

    requirement_code: str
    status: DecisionStatus
    comment: str = ""


class ExtractionOutput(BaseModel):
    """Structured output requested from the LLM when reading a file."""

    document_type: str
    issuer: str | None = None
    issue_date: str | None = None
    summary: str


class CheckOutput(BaseModel):
    """Structured output requested from the LLM when checking one requirement."""

    status: FindingStatus
    file_id: str | None = Field(
        default=None, description="Identifier of the file that covers the requirement"
    )
    evidence: str = Field(default="", description="Exact passage copied from that file")
    reasoning: str = ""
