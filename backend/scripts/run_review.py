"""Run a completeness review from the command line.

Usage:
    uv run python -m scripts.run_review examples/complete_application
    uv run python -m scripts.run_review examples/incomplete_application --auto missing

When a finding is doubtful the script asks for your decision and resumes the graph.
"""

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agent.graph import build_graph
from agent.loaders import file_to_text
from agent.schemas import RequiredDocument, SubmittedFile
from agent.tracing import get_callbacks

DEFAULT_CHECKLIST = Path(__file__).resolve().parents[1] / "agent" / "checklists" / "default.json"


def load_files(folder: Path) -> list[SubmittedFile]:
    files = []
    for path in sorted(folder.iterdir()):
        if path.is_file():
            files.append(SubmittedFile(name=path.name, text=file_to_text(path.name, path.read_bytes())))
    return files


def ask_decisions(findings: list[dict]) -> list[dict]:
    decisions = []
    for finding in findings:
        print(f"\n{finding['requirement_code']} is doubtful.")
        print(f"  evidence: {finding['evidence']}")
        print(f"  reasoning: {finding['reasoning']}")
        answer = ""
        while answer not in ("present", "missing"):
            answer = input("  your decision (present/missing): ").strip().lower()
        comment = input("  comment (optional): ").strip()
        decisions.append(
            {"requirement_code": finding["requirement_code"], "status": answer, "comment": comment}
        )
    return decisions


def print_findings(findings) -> None:
    print("\nFindings")
    for f in findings:
        print(f"  [{f.status:8}] {f.requirement_code:10} by {f.decided_by:8} file: {f.matched_file or '-'}")
        if f.evidence:
            print(f"             evidence: {f.evidence}")
        if f.reasoning:
            print(f"             reasoning: {f.reasoning}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Check a tender application against a checklist")
    parser.add_argument("folder", type=Path, help="Folder with the submitted files")
    parser.add_argument("--checklist", type=Path, default=DEFAULT_CHECKLIST)
    parser.add_argument(
        "--auto", choices=["present", "missing"], help="Answer doubtful findings without asking"
    )
    args = parser.parse_args()

    load_dotenv()
    checklist = [RequiredDocument.model_validate(item) for item in json.loads(args.checklist.read_text())]
    files = load_files(args.folder)
    print(f"{len(files)} files, {len(checklist)} requirements")

    graph = build_graph(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": args.folder.name}, "callbacks": get_callbacks()}
    state = graph.invoke(
        {"review_id": args.folder.name, "required_documents": checklist, "submitted_files": files},
        config,
    )

    while "__interrupt__" in state:
        payload = state["__interrupt__"][0].value
        if payload.get("error"):
            print(f"\nAnswer rejected: {payload['error']}")
        if args.auto:
            decisions = [
                {"requirement_code": f["requirement_code"], "status": args.auto, "comment": "auto"}
                for f in payload["findings"]
            ]
        else:
            decisions = ask_decisions(payload["findings"])
        state = graph.invoke(Command(resume=decisions), config)

    print_findings(state["resolved_findings"])
    print(f"\nVerdict: {state['verdict']}")
    print("\nReport\n")
    print(state["report"])


if __name__ == "__main__":
    main()
