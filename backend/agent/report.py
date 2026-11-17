"""Deterministic verdict and report. The model never decides the outcome."""

import html

from agent.schemas import ExtractedDocument, Finding, HumanDecision, RequiredDocument, Verdict


def resolve_findings(
    requirements: list[RequiredDocument],
    findings: list[Finding],
    decisions: list[HumanDecision],
) -> list[Finding]:
    """Apply the reviewer decisions and return the findings in checklist order."""
    by_code = {f.requirement_code: f for f in findings}
    decision_by_code = {d.requirement_code: d for d in decisions}
    resolved = []
    for requirement in requirements:
        finding = by_code.get(requirement.code)
        if finding is None:
            finding = Finding(
                requirement_code=requirement.code,
                status="missing",
                reasoning="No finding was produced for this requirement",
                decided_by="rule",
            )
        decision = decision_by_code.get(requirement.code)
        if finding.status == "doubtful" and decision is not None:
            finding = finding.model_copy(
                update={
                    "status": decision.status,
                    "reasoning": decision.comment or f"Reviewer decided: {decision.status}",
                    "decided_by": "reviewer",
                }
            )
        resolved.append(finding)
    return resolved


def compute_verdict(requirements: list[RequiredDocument], resolved: list[Finding]) -> Verdict:
    """Complete when every mandatory requirement is present."""
    status_by_code = {f.requirement_code: f.status for f in resolved}
    for requirement in requirements:
        if requirement.mandatory and status_by_code.get(requirement.code) != "present":
            return "incomplete"
    return "complete"


def escape(text: str) -> str:
    """Make a text safe to embed in the Markdown report. HTML tags become literal text."""
    return html.escape(text, quote=False).replace("\n", " ")


def render_report(
    review_id: str,
    requirements: list[RequiredDocument],
    resolved: list[Finding],
    documents: list[ExtractedDocument],
    verdict: Verdict,
    summary: str = "",
) -> str:
    """Render the Markdown report from the resolved findings."""
    label_by_code = {r.code: r for r in requirements}
    lines = [f"# Completeness review {review_id}", "", f"Verdict: **{verdict}**", ""]

    if summary:
        lines += ["## Summary", "", escape(summary.strip()), ""]

    missing = [f for f in resolved if f.status != "present"]
    present = [f for f in resolved if f.status == "present"]

    lines += ["## Missing documents", ""]
    if not missing:
        lines.append("None.")
    for f in missing:
        req = label_by_code[f.requirement_code]
        kind = "mandatory" if req.mandatory else "optional"
        lines.append(f"- {req.code} {escape(req.label)} ({kind}): {escape(f.reasoning or f.status)}")
    lines.append("")

    lines += ["## Documents present", ""]
    if not present:
        lines.append("None.")
    for f in present:
        req = label_by_code[f.requirement_code]
        source = escape(f.matched_file or "unknown file")
        lines.append(f"- {req.code} {escape(req.label)}: {source}")
        if f.evidence:
            lines.append(f'  Evidence: "{escape(f.evidence)}"')
    lines.append("")

    reviewed = [f for f in resolved if f.decided_by == "reviewer"]
    if reviewed:
        lines += ["## Reviewer decisions", ""]
        for f in reviewed:
            lines.append(f"- {f.requirement_code}: {f.status}. {escape(f.reasoning)}")
        lines.append("")

    unreadable = [d for d in documents if d.status == "unreadable"]
    if unreadable:
        lines += ["## Unreadable files", ""]
        for d in unreadable:
            lines.append(f"- {escape(d.file_name)}: {escape(d.error)}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
