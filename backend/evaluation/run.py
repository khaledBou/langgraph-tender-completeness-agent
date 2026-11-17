"""Run the workflow on the evaluation dataset with the configured model and report the results.

    uv run python -m evaluation.run            # every case
    uv run python -m evaluation.run --only complete_separate_files missing_insurance

Results go to evaluation/results/<date>-<model>.json and .md. The JSON keeps the full
findings (evidence included), the reference decisions applied and the resolved findings,
so every number of the report can be audited.
"""

import argparse
import hashlib
import json
import os
import subprocess
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
from agent.nodes import MAX_CHARS_PER_FILE
from agent.report import compute_verdict, resolve_findings
from agent.schemas import RequiredDocument, SubmittedFile
from agent.serde import make_serializer

ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = Path(__file__).parent / "dataset"
RESULTS_DIR = Path(__file__).parent / "results"
CHECKLIST = Path(__file__).parents[1] / "agent" / "checklists" / "default.json"
MANDATORY = {"DC1", "DC2", "KBIS", "INSURANCE"}


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


def fingerprint(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT, check=True
        ).stdout.strip()
    except Exception:
        return "unknown"


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
        findings = list(state["findings"])
        paused = "__interrupt__" in state
        decisions = []
        if paused:
            decisions = [
                {
                    "requirement_code": code,
                    "status": expected["expectations"][code]["decision"] or "missing",
                    "comment": "reference decision",
                }
                for code in [f["requirement_code"] for f in state["__interrupt__"][0].value["findings"]]
            ]
            state = graph.invoke(Command(resume=decisions), config)
        provisional = resolve_findings(checklist, findings, [])
        result.update(
            {
                "paused": paused,
                "findings": [f.model_dump() for f in findings],
                "extracted_documents": [d.model_dump() for d in state.get("extracted_documents", [])],
                "reference_decisions_applied": decisions,
                "resolved_findings": [f.model_dump() for f in state["resolved_findings"]],
                "provisional_verdict": compute_verdict(checklist, provisional),
                "final_verdict": state["verdict"],
                "evidence_rejections": sum(
                    1
                    for f in findings
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


def expected_provisional_verdict(expected: dict) -> str:
    for code, e in expected["expectations"].items():
        if code in MANDATORY and e["expected"] != "present":
            return "incomplete"
    return "complete"


def score(results: list[dict]) -> dict:
    s = {
        "cases": len(results),
        "technical_errors": 0,
        "requirements": 0,
        "status_exact": 0,
        "status_in_accepted": 0,
        "false_present": 0,
        "false_present_candidates": 0,
        "absent_mandatory_marked_present": 0,
        "absent_mandatory_candidates": 0,
        "completed_without_human": 0,
        "completed_without_human_verdict_correct": 0,
        "paused": 0,
        "paused_provisional_verdict_correct": 0,
        "final_verdict_correct": 0,
        "evidence_rejections": 0,
        "seconds": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
        "failures": [],
        "deviations_from_expected": [],
    }
    for r in results:
        s["seconds"] += r["seconds"]
        s["input_tokens"] += r["tokens"]["input_tokens"]
        s["output_tokens"] += r["tokens"]["output_tokens"]
        if r["error"]:
            s["technical_errors"] += 1
            s["failures"].append(f"{r['case']}: technical error {r['error']}")
            continue
        exp = r["expected"]
        s["evidence_rejections"] += r["evidence_rejections"]
        if r["paused"]:
            s["paused"] += 1
            s["paused_provisional_verdict_correct"] += int(
                r["provisional_verdict"] == expected_provisional_verdict(exp)
            )
        else:
            s["completed_without_human"] += 1
            s["completed_without_human_verdict_correct"] += int(r["final_verdict"] == exp["final_verdict"])
        s["final_verdict_correct"] += int(r["final_verdict"] == exp["final_verdict"])
        if r["final_verdict"] != exp["final_verdict"]:
            s["failures"].append(
                f"{r['case']}: final verdict {r['final_verdict']}, expected {exp['final_verdict']}"
            )
        findings = {f["requirement_code"]: f for f in r["findings"]}
        for code, e in exp["expectations"].items():
            got = findings[code]["status"]
            s["requirements"] += 1
            s["status_exact"] += int(got == e["expected"])
            if got in e["accepted"]:
                s["status_in_accepted"] += 1
                if got != e["expected"]:
                    s["deviations_from_expected"].append(
                        f"{r['case']}: {code} got {got}, expected {e['expected']} (accepted)"
                    )
            else:
                s["failures"].append(
                    f"{r['case']}: {code} got {got}, accepted {e['accepted']}. {findings[code]['reasoning'][:140]}"
                )
            if "present" not in e["accepted"]:
                s["false_present_candidates"] += 1
                s["false_present"] += int(got == "present")
            if e["expected"] == "missing" and code in MANDATORY:
                s["absent_mandatory_candidates"] += 1
                s["absent_mandatory_marked_present"] += int(got == "present")
    return s


def write_markdown(path: Path, meta: dict, s: dict, results: list[dict]) -> None:
    ok = s["cases"] - s["technical_errors"]
    lines = [
        f"# Evaluation {meta['date']}",
        "",
        "Initial regression evaluation on short, largely templated English documents. These results do not establish performance on real tender applications.",
        "",
        f"Model: {meta['model']} (provider {meta['provider']}, structured outputs in JSON schema mode, {MAX_CHARS_PER_FILE} characters per file in the check prompt)",
        f"Code: commit {meta['commit']}. Dataset fingerprint {meta['dataset_fingerprint']}, checklist fingerprint {meta['checklist_fingerprint']}.",
        f"Dataset: {s['cases']} applications, {s['requirements']} requirement checks, reference date {meta['reference_date']}",
        f"Duration: {round(s['seconds'])} s. Tokens: {s['input_tokens']} in, {s['output_tokens']} out.",
        "",
        "The numbers measure the whole workflow, rules included, not the model alone.",
        "",
        "| Measure | Value |",
        "|---|---|",
        f"| Technical errors | {s['technical_errors']} / {s['cases']} |",
        f"| Finding status equal to the expected status | {s['status_exact']} / {s['requirements']} |",
        f"| Finding status within the accepted statuses | {s['status_in_accepted']} / {s['requirements']} |",
        f"| False present: document absent or not provable, workflow said present | {s['false_present']} / {s['false_present_candidates']} |",
        f"| Absent mandatory documents incorrectly marked present | {s['absent_mandatory_marked_present']} / {s['absent_mandatory_candidates']} |",
        f"| Applications completed without human intervention | {s['completed_without_human']} / {ok} |",
        f"| Of which the verdict is correct | {s['completed_without_human_verdict_correct']} / {s['completed_without_human']} |",
        f"| Applications paused for human review | {s['paused']} / {ok} |",
        f"| Of which the provisional verdict is correct (doubtful mandatory findings counted as incomplete) | {s['paused_provisional_verdict_correct']} / {s['paused']} |",
        f"| Final verdict correct after the reference decisions | {s['final_verdict_correct']} / {ok} |",
        f"| Model answers downgraded because the quote was not in the file | {s['evidence_rejections']} |",
        "",
        "## Failures",
        "",
    ]
    lines += [f"- {f}" for f in s["failures"]] or ["None."]
    lines += ["", "## Accepted deviations from the expected status", ""]
    lines += [f"- {d}" for d in s["deviations_from_expected"]] or ["None."]
    lines += [
        "",
        "## Cases",
        "",
        "| Case | Group | Paused | Provisional verdict | Final verdict | Expected | Seconds |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        if r["error"]:
            lines.append(
                f"| {r['case']} | {r['group']} | error | | | {r['expected']['final_verdict']} | {r['seconds']} |"
            )
        else:
            lines.append(
                f"| {r['case']} | {r['group']} | {'yes' if r['paused'] else 'no'} | {r['provisional_verdict']} | {r['final_verdict']} | {r['expected']['final_verdict']} | {r['seconds']} |"
            )
    lines += ["", "## Evidence of the present findings", ""]
    for r in results:
        if r["error"]:
            continue
        for f in r["findings"]:
            if f["status"] == "present":
                lines.append(
                    f'- {r["case"]} / {f["requirement_code"]} / {f["matched_file"]}: "{f["evidence"][:160]}"'
                )
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="*", help="Case names to run")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    provider = os.getenv("LLM_PROVIDER", "anthropic")
    model = (
        os.getenv("ANTHROPIC_MODEL", "claude-opus-5-5")
        if provider == "anthropic"
        else os.getenv("OLLAMA_MODEL", "")
    )
    checklist = [RequiredDocument.model_validate(i) for i in json.loads(CHECKLIST.read_text())]
    folders = sorted(p for p in DATASET_DIR.iterdir() if p.is_dir())
    if args.only:
        folders = [f for f in folders if f.name in args.only]

    results = []
    for folder in folders:
        result = run_case(folder, checklist)
        status = result["error"] or f"paused={result['paused']} verdict={result['final_verdict']}"
        print(f"{folder.name}: {status} ({result['seconds']} s)")
        results.append(result)

    s = score(results)
    meta = {
        "date": date.today().isoformat(),
        "model": model,
        "provider": provider,
        "commit": git_commit(),
        "dataset_fingerprint": fingerprint([p for p in DATASET_DIR.rglob("*") if p.is_file()]),
        "checklist_fingerprint": fingerprint([CHECKLIST]),
        "reference_date": results[0]["expected"]["reference_date"] if results else "",
        "max_chars_per_file": MAX_CHARS_PER_FILE,
        "cases_run": [f.name for f in folders],
    }
    RESULTS_DIR.mkdir(exist_ok=True)
    stem = f"{meta['date']}-{model.replace(':', '-')}"
    (RESULTS_DIR / f"{stem}.json").write_text(
        json.dumps({"meta": meta, "summary": s, "results": results}, indent=2) + "\n"
    )
    write_markdown(RESULTS_DIR / f"{stem}.md", meta, s, results)
    print(
        f"\nFalse present: {s['false_present']}/{s['false_present_candidates']}, final verdict: {s['final_verdict_correct']}/{s['cases']}, failures: {len(s['failures'])}"
    )
    print(f"Results: {RESULTS_DIR / stem}.md")


if __name__ == "__main__":
    main()
