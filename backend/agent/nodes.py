"""Nodes of the completeness review graph.

The nodes are methods of a class so the chat model can be injected,
which keeps the graph testable without network access.
"""

import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import Send, interrupt

from agent import prompts
from agent.evidence import evidence_in_file, find_file
from agent.report import compute_verdict, render_report, resolve_findings
from agent.schemas import (
    CheckOutput,
    ExtractedDocument,
    ExtractionOutput,
    Finding,
    HumanDecision,
    SubmittedFile,
)
from agent.state import CheckInput, ExtractionInput, ReviewState

logger = logging.getLogger(__name__)

# Characters of each file given to the check worker. Keeps the prompt bounded.
# A file longer than this is marked truncated in the prompt and in the finding.
MAX_CHARS_PER_FILE = 6000


def number_files(files: list[SubmittedFile]) -> list[SubmittedFile]:
    """Give every file a stable identifier F1, F2, ... in submission order."""
    return [f.model_copy(update={"id": f"F{i}"}) for i, f in enumerate(files, start=1)]


def validate_decisions(doubtful: list[Finding], answer: object) -> list[HumanDecision]:
    """Check that the reviewer answered every doubtful finding exactly once."""
    if not isinstance(answer, list):
        raise ValueError("Decisions must be a list")
    decisions = [HumanDecision.model_validate(item) for item in answer]
    expected = {f.requirement_code for f in doubtful}
    given = [d.requirement_code for d in decisions]
    if len(given) != len(set(given)):
        raise ValueError("Duplicate decision for the same requirement")
    unknown = set(given) - expected
    if unknown:
        raise ValueError(f"Decision for a requirement that is not doubtful: {sorted(unknown)}")
    absent = expected - set(given)
    if absent:
        raise ValueError(f"Missing decision for: {sorted(absent)}")
    return decisions


def format_files_for_check(
    documents: list[ExtractedDocument], files: list[SubmittedFile]
) -> tuple[str, list[str]]:
    """Render the readable files for the prompt. Also return the ids of truncated files."""
    text_by_id = {f.id: f.text for f in files}
    blocks = []
    truncated = []
    for doc in documents:
        if doc.status != "ok":
            continue
        text = text_by_id.get(doc.file_id, "")
        note = ""
        if len(text) > MAX_CHARS_PER_FILE:
            text = text[:MAX_CHARS_PER_FILE]
            truncated.append(doc.file_id)
            note = f' truncated="true" shown_characters="{MAX_CHARS_PER_FILE}"'
        header = f'<file id="{doc.file_id}" name="{doc.file_name}" type="{doc.document_type}"{note}>'
        blocks.append(f"{header}\n{text}\n</file>")
    return "\n\n".join(blocks) or "(no readable file)", truncated


def _format_findings(findings: list[Finding]) -> str:
    return "\n".join(f"- {f.requirement_code}: {f.status} ({f.decided_by}). {f.reasoning}" for f in findings)


class ReviewNodes:
    """Graph nodes bound to a chat model."""

    def __init__(self, llm: BaseChatModel):
        self.llm = llm

    # Step 1: read every submitted file in parallel.

    def start(self, state: ReviewState) -> dict:
        if not state.get("required_documents"):
            raise ValueError("The checklist is empty")
        return {"submitted_files": number_files(state.get("submitted_files", [])), "status": "extracting"}

    def fan_out_extraction(self, state: ReviewState) -> list[Send] | str:
        files = state.get("submitted_files", [])
        if not files:
            return "collect_documents"
        return [Send("extract_document", {"file": f}) for f in files]

    def extract_document(self, payload: ExtractionInput) -> dict:
        """Describe one file.

        A file without text is unreadable: that is a document problem, reported as such.
        A model error is a technical problem: it propagates, the retry policy of the node
        applies, and the review fails if the retries are exhausted.
        """
        file = payload["file"]
        if not file.text.strip():
            document = ExtractedDocument(
                file_id=file.id, file_name=file.name, status="unreadable", error="The file has no text"
            )
            return {"extracted_documents": [document]}

        output = self.llm.with_structured_output(ExtractionOutput).invoke(
            [
                SystemMessage(prompts.EXTRACTION_SYSTEM),
                HumanMessage(prompts.EXTRACTION_USER.format(file_name=file.name, text=file.text)),
            ]
        )
        document = ExtractedDocument(file_id=file.id, file_name=file.name, **output.model_dump())
        return {"extracted_documents": [document]}

    # Step 2: check every requirement in parallel against the readable files.

    def collect_documents(self, state: ReviewState) -> dict:
        return {"status": "checking"}

    def fan_out_checks(self, state: ReviewState) -> list[Send]:
        documents = state.get("extracted_documents", [])
        files = state.get("submitted_files", [])
        return [
            Send("check_requirement", {"requirement": r, "documents": documents, "files": files})
            for r in state["required_documents"]
        ]

    def check_requirement(self, payload: CheckInput) -> dict:
        requirement = payload["requirement"]
        documents = payload["documents"]
        files = payload["files"]
        readable = [d for d in documents if d.status == "ok"]
        unreadable = [d for d in documents if d.status == "unreadable"]
        code = requirement.code

        # Rules first. The model is only called when there is something to read.
        if not readable and not unreadable:
            finding = Finding(
                requirement_code=code, status="missing", reasoning="No file was submitted", decided_by="rule"
            )
            return {"findings": [finding]}
        if not readable:
            finding = Finding(
                requirement_code=code, status="doubtful", reasoning="No file could be read", decided_by="rule"
            )
            return {"findings": [finding]}

        rendered, truncated = format_files_for_check(readable, files)
        output = self.llm.with_structured_output(CheckOutput).invoke(
            [
                SystemMessage(prompts.CHECK_SYSTEM),
                HumanMessage(
                    prompts.CHECK_USER.format(
                        code=code,
                        label=requirement.label,
                        description=requirement.description,
                        documents=rendered,
                    )
                ),
            ]
        )
        finding = self.finding_from_output(code, output, files, bool(unreadable), truncated)
        return {"findings": [finding]}

    @staticmethod
    def finding_from_output(
        code: str,
        output: CheckOutput,
        files: list[SubmittedFile],
        has_unreadable: bool,
        truncated: list[str],
    ) -> Finding:
        """Turn the model answer into a finding, after validating the evidence."""
        file = find_file(files, output.file_id)
        finding = Finding(
            requirement_code=code,
            status=output.status,
            matched_file_id=file.id if file else None,
            matched_file=file.name if file else None,
            evidence=output.evidence,
            reasoning=output.reasoning,
        )
        if output.status == "present":
            if file is None:
                return finding.model_copy(
                    update={"status": "doubtful", "reasoning": "The model named a file that does not exist"}
                )
            if not evidence_in_file(output.evidence, file):
                return finding.model_copy(
                    update={
                        "status": "doubtful",
                        "reasoning": "The quoted evidence was not found in the file",
                    }
                )
        if output.status == "missing" and has_unreadable:
            return finding.model_copy(
                update={
                    "status": "doubtful",
                    "reasoning": "Not found in readable files, but one file could not be read",
                }
            )
        if output.status == "missing" and truncated:
            names = ", ".join(f.name for f in files if f.id in truncated)
            return finding.model_copy(
                update={
                    "status": "doubtful",
                    "reasoning": f"Not found in the first {MAX_CHARS_PER_FILE} characters of: {names}",
                }
            )
        return finding

    # Step 3: ask a human when the workflow is not sure, then finalize.

    def aggregate(self, state: ReviewState) -> dict:
        return {"status": "aggregated"}

    def route_after_checks(self, state: ReviewState) -> str:
        has_doubt = any(f.status == "doubtful" for f in state.get("findings", []))
        return "human_review" if has_doubt else "finalize"

    def human_review(self, state: ReviewState) -> dict:
        """Pause until the reviewer answers. One interrupt per execution of the node.

        An invalid answer is recorded in review_error and the conditional edge brings
        the graph back here, so the next pause shows the error and reads a fresh answer.
        """
        doubtful = [f for f in state["findings"] if f.status == "doubtful"]
        payload = {
            "reason": "Some findings need a human decision",
            "findings": [f.model_dump() for f in doubtful],
        }
        if state.get("review_error"):
            payload["error"] = state["review_error"]
        answer = interrupt(payload)
        try:
            decisions = validate_decisions(doubtful, answer)
        except ValueError as exc:
            return {"review_error": str(exc)}
        return {"human_decisions": decisions, "review_error": "", "status": "reviewed"}

    def route_after_review(self, state: ReviewState) -> str:
        return "human_review" if state.get("review_error") else "finalize"

    def finalize(self, state: ReviewState) -> dict:
        requirements = state["required_documents"]
        resolved = resolve_findings(requirements, state.get("findings", []), state.get("human_decisions", []))
        verdict = compute_verdict(requirements, resolved)
        # No file means nothing to summarise: the report is enough and the model is not called.
        summary = self._write_summary(verdict, resolved) if state.get("submitted_files") else ""
        report = render_report(
            review_id=state.get("review_id", ""),
            requirements=requirements,
            resolved=resolved,
            documents=state.get("extracted_documents", []),
            verdict=verdict,
            summary=summary,
        )
        return {"resolved_findings": resolved, "verdict": verdict, "report": report, "status": "completed"}

    def _write_summary(self, verdict: str, resolved: list[Finding]) -> str:
        """Plain language summary. Best effort: the report stands without it and there is no retry."""
        try:
            response = self.llm.invoke(
                [
                    SystemMessage(prompts.SUMMARY_SYSTEM),
                    HumanMessage(
                        prompts.SUMMARY_USER.format(verdict=verdict, findings=_format_findings(resolved))
                    ),
                ]
            )
            return response.content if isinstance(response.content, str) else ""
        except Exception as exc:
            logger.warning("Summary not written: %s", exc)
            return ""
