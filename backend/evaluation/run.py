"""Run the workflow on the evaluation dataset with the configured model and report the results.

    uv run python -m evaluation.run            # every case
    uv run python -m evaluation.run --only complete_separate_files missing_insurance

Results go to evaluation/results/<date>-<model>.json and .md.
"""

import argparse
import json
import os
import time
import traceback
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.callbacks import UsageMetadataCallbackHandler
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agent.graph import build_graph
from agent.loaders import file_to_text
from agent.report import compute_verdict, resolve_findings
from agent.schemas import RequiredDocument, SubmittedFile
from agent.serde import make_serializer

ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = Path(__file__).parent / "dataset"
RESULTS_DIR = Path(__file__).parent / "results"
CHECKLIST = Path(__file__).parents[1] / "agent" / "checklists" / "default.json"


def load_files(folder: Path) -> list[SubmittedFile]:
    files = []
    for path in sorted(folder.iterdir()):
        try:
            text = file_to_text(path.name, path.read_bytes())
        except Exception:
            # Same behaviour as the API: an unreadable upload reaches the workflow with no text.
            text = ""
        files.append(SubmittedFile(name=path.name, text=text))
    return files


def run_case(folder: Path, checklist: list[RequiredDocument]) -> dict:
    expected = json.loads((folder / "expected.json").read_text())
    usage = UsageMetadataCallbackHandler()
    graph = build_graph(checkpointer=InMemorySaver(serde=make_serializer()))
    config = {"configurable": {"thread_id": folder.name}, "callbacks": [usage]}
    started = time.perf_counter()
    result = {"case": folder.name, "group": expected["group"], "error": ""}
    try:
        state = graph.invoke(
            {
                "review_id": folder.name,
                "reference_date": expected["reference_date"],
                "required_documents": checklist,
                "submitted_files": load_files(folder / "files") if (folder / "files").exists() else [],
            },
            config,
        )
        findings = {f.requirement_code: f for f in state["findings"]}
        paused = "__interrupt__" in state
        if paused:
            decisions = [
                {
                    "requirement_code": code,
                    "status": expected["expectations"][code]["decision"] or "missing",
                    "comment": "reference",
                }
                for code in [f["requirement_code"] for f in state["__interrupt__"][0].value["findings"]]
            ]
            state = graph.invoke(Command(resume=decisions), config)
        before = resolve_findings(checklist, list(findings.values()), [])
        result.update(
            {
                "paused": paused,
                "findings": {
                    code: {"status": f.status, "file": f.matched_file, "reasoning": f.reasoning}
                    for code, f in findings.items()
                },
                "verdict_before_human": compute_verdict(checklist, before),
                "verdict_after_human": state["verdict"],
                "evidence_rejections": sum(
                    1
                    for f in findings.values()
                    if f.reasoning.startswith(("The quoted evidence", "The model named a file"))
                ),
            }
        )
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        traceback.print_exc()
    result["seconds"] = round(time.perf_counter() - started, 1)
    total = {"input_tokens": 0, "output_tokens": 0}
    for model_usage in usage.usage_metadata.values():
        total["input_tokens"] += model_usage.get("input_tokens", 0)
        total["output_tokens"] += model_usage.get("output_tokens", 0)
    result["tokens"] = total
    result["expected"] = expected
    return result


def score(results: list[dict]) -> dict:
    mandatory = {"DC1", "DC2", "KBIS", "INSURANCE"}
    s = {
        "cases": len(results),
        "technical_errors": sum(1 for r in results if r["error"]),
        "requirements": 0,
        "status_in_accepted": 0,
        "false_present": 0,
        "false_present_candidates": 0,
        "missed_mandatory_missing": 0,
        "mandatory_missing_candidates": 0,
        "verdict_before_human_correct": 0,
        "verdict_after_human_correct": 0,
        "paused": 0,
        "evidence_rejections": 0,
        "seconds": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
        "failures": [],
    }
    for r in results:
        s["seconds"] += r["seconds"]
        s["input_tokens"] += r["tokens"]["input_tokens"]
        s["output_tokens"] += r["tokens"]["output_tokens"]
        if r["error"]:
            s["failures"].append(f"{r['case']}: technical error {r['error']}")
            continue
        exp = r["expected"]
        s["paused"] += int(r["paused"])
        s["evidence_rejections"] += r["evidence_rejections"]
        expected_before = compute_verdict_from_expectations(exp)
        s["verdict_before_human_correct"] += int(r["verdict_before_human"] == expected_before)
        s["verdict_after_human_correct"] += int(r["verdict_after_human"] == exp["final_verdict"])
        if r["verdict_after_human"] != exp["final_verdict"]:
            s["failures"].append(
                f"{r['case']}: final verdict {r['verdict_after_human']}, expected {exp['final_verdict']}"
            )
        for code, e in exp["expectations"].items():
            got = r["findings"][code]["status"]
            s["requirements"] += 1
            if got in e["accepted"]:
                s["status_in_accepted"] += 1
            else:
                s["failures"].append(
                    f"{r['case']}: {code} got {got}, accepted {e['accepted']}. {r['findings'][code]['reasoning'][:140]}"
                )
            if "present" not in e["accepted"]:
                s["false_present_candidates"] += 1
                s["false_present"] += int(got == "present")
            if e["expected"] == "missing" and code in mandatory:
                s["mandatory_missing_candidates"] += 1
                s["missed_mandatory_missing"] += int(got == "present")
    return s


def compute_verdict_from_expectations(expected: dict) -> str:
    mandatory = {"DC1", "DC2", "KBIS", "INSURANCE"}
    for code, e in expected["expectations"].items():
        if code in mandatory and e["expected"] != "present":
            return "incomplete"
    return "complete"


def write_markdown(path: Path, model: str, s: dict, results: list[dict]) -> None:
    lines = [
        f"# Evaluation {date.today().isoformat()}",
        "",
        f"Model: {model}",
        f"Dataset: {s['cases']} applications, {s['requirements']} requirement checks, reference date 2026-11-17",
        f"Duration: {round(s['seconds'])} s. Tokens: {s['input_tokens']} in, {s['output_tokens']} out.",
        "",
        "| Measure | Value |",
        "|---|---|",
        f"| Technical errors | {s['technical_errors']} / {s['cases']} |",
        f"| Finding status within the accepted statuses | {s['status_in_accepted']} / {s['requirements']} |",
        f"| False present (document absent or not provable, model said present) | {s['false_present']} / {s['false_present_candidates']} |",
        f"| Missed mandatory missing (expected missing, model said present) | {s['missed_mandatory_missing']} / {s['mandatory_missing_candidates']} |",
        f"| Verdict correct before any human decision | {s['verdict_before_human_correct']} / {s['cases'] - s['technical_errors']} |",
        f"| Verdict correct after the reference decisions | {s['verdict_after_human_correct']} / {s['cases'] - s['technical_errors']} |",
        f"| Applications paused for human review | {s['paused']} / {s['cases'] - s['technical_errors']} |",
        f"| Model answers downgraded because the quote was not in the file | {s['evidence_rejections']} |",
        "",
        "## Failures",
        "",
    ]
    lines += [f"- {f}" for f in s["failures"]] or ["None."]
    lines += [
        "",
        "## Cases",
        "",
        "| Case | Group | Paused | Verdict before | Verdict after | Expected | Seconds |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        if r["error"]:
            lines.append(
                f"| {r['case']} | {r['group']} | error | | | {r['expected']['final_verdict']} | {r['seconds']} |"
            )
        else:
            lines.append(
                f"| {r['case']} | {r['group']} | {'yes' if r['paused'] else 'no'} | {r['verdict_before_human']} | {r['verdict_after_human']} | {r['expected']['final_verdict']} | {r['seconds']} |"
            )
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="*", help="Case names to run")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    model = (
        os.getenv("ANTHROPIC_MODEL", "claude-opus-5-5")
        if os.getenv("LLM_PROVIDER", "anthropic") == "anthropic"
        else os.getenv("OLLAMA_MODEL", "")
    )
    checklist = [RequiredDocument.model_validate(i) for i in json.loads(CHECKLIST.read_text())]
    folders = sorted(p for p in DATASET_DIR.iterdir() if p.is_dir())
    if args.only:
        folders = [f for f in folders if f.name in args.only]

    results = []
    for folder in folders:
        result = run_case(folder, checklist)
        status = result["error"] or f"paused={result['paused']} verdict={result['verdict_after_human']}"
        print(f"{folder.name}: {status} ({result['seconds']} s)")
        results.append(result)

    s = score(results)
    RESULTS_DIR.mkdir(exist_ok=True)
    stem = f"{date.today().isoformat()}-{model.replace(':', '-')}"
    (RESULTS_DIR / f"{stem}.json").write_text(
        json.dumps({"model": model, "summary": s, "results": results}, indent=2) + "\n"
    )
    write_markdown(RESULTS_DIR / f"{stem}.md", model, s, results)
    print(
        f"\nFalse present: {s['false_present']}/{s['false_present_candidates']}, verdict after human: {s['verdict_after_human_correct']}/{s['cases']}, failures: {len(s['failures'])}"
    )
    print(f"Results: {RESULTS_DIR / stem}.md")


if __name__ == "__main__":
    main()
