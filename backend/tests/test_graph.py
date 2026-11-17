import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agent.graph import build_graph
from agent.nodes import MAX_CHARS_PER_FILE
from agent.schemas import CheckOutput, RequiredDocument, SubmittedFile
from agent.testing import FakeLLM, TransientModelError

CHECKLIST = [
    RequiredDocument(code="DC1", label="Application letter"),
    RequiredDocument(code="KBIS", label="Registration extract"),
    RequiredDocument(code="REFS", label="References", mandatory=False),
]
FILES = [
    SubmittedFile(name="dc1.txt", text="Application letter signed by the director"),
    SubmittedFile(name="kbis.txt", text="Registration extract issued in October"),
]


def run(llm, files=FILES, thread_id="t1", checklist=CHECKLIST):
    graph = build_graph(llm=llm, checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": thread_id}}
    state = graph.invoke(
        {"review_id": thread_id, "required_documents": checklist, "submitted_files": files},
        config,
    )
    return graph, config, state


def statuses(state, key="resolved_findings"):
    return {f.requirement_code: f.status for f in state[key]}


# A1: complete application


def test_complete_application_goes_straight_to_report():
    llm = FakeLLM()
    _, _, state = run(llm)

    assert state["status"] == "completed"
    assert state["verdict"] == "complete"
    assert statuses(state) == {"DC1": "present", "KBIS": "present", "REFS": "present"}
    assert [f.requirement_code for f in state["resolved_findings"]] == ["DC1", "KBIS", "REFS"]
    assert state["report"].startswith("# Completeness review t1")
    assert "Verdict: **complete**" in state["report"]
    assert llm.calls.count("extract") == 2
    assert llm.calls.count("check") == 3
    assert llm.calls.count("summary") == 1


def test_files_get_stable_identifiers():
    _, _, state = run(FakeLLM())
    assert [f.id for f in state["submitted_files"]] == ["F1", "F2"]
    assert state["resolved_findings"][0].matched_file == "dc1.txt"
    assert state["resolved_findings"][0].matched_file_id == "F1"


# A2: no file submitted


def test_no_files_means_every_requirement_is_missing_without_calling_the_model():
    llm = FakeLLM()
    _, _, state = run(llm, files=[])

    assert state["status"] == "completed"
    assert state["verdict"] == "incomplete"
    assert statuses(state) == {"DC1": "missing", "KBIS": "missing", "REFS": "missing"}
    assert all(f.decided_by == "rule" for f in state["resolved_findings"])
    assert llm.calls == []


# A3: doubtful finding, pause and resume


def test_doubtful_finding_pauses_for_human_review_and_resumes():
    llm = FakeLLM({"KBIS": CheckOutput(status="doubtful", file_id="F2", reasoning="old extract")})
    graph, config, state = run(llm)

    assert "report" not in state
    payload = state["__interrupt__"][0].value
    assert [f["requirement_code"] for f in payload["findings"]] == ["KBIS"]

    decisions = [{"requirement_code": "KBIS", "status": "missing", "comment": "older than 3 months"}]
    final = graph.invoke(Command(resume=decisions), config)

    assert final["status"] == "completed"
    assert final["verdict"] == "incomplete"
    # Original findings are kept for audit, resolved findings carry the decision.
    assert statuses(final, "findings")["KBIS"] == "doubtful"
    resolved = {f.requirement_code: f for f in final["resolved_findings"]}
    assert resolved["KBIS"].status == "missing"
    assert resolved["KBIS"].decided_by == "reviewer"
    assert resolved["KBIS"].reasoning == "older than 3 months"
    assert "older than 3 months" in final["report"]
    # Resuming does not run the workers again.
    assert llm.calls.count("extract") == 2
    assert llm.calls.count("check") == 3


# A4 and A5: invalid reviewer answers keep the review paused


@pytest.mark.parametrize(
    "answer, message",
    [
        ([], "Missing decision"),
        ([{"requirement_code": "DC1", "status": "missing"}], "not doubtful"),
        (
            [
                {"requirement_code": "KBIS", "status": "missing"},
                {"requirement_code": "KBIS", "status": "present"},
            ],
            "Duplicate",
        ),
    ],
)
def test_invalid_decisions_are_rejected_and_the_review_stays_paused(answer, message):
    llm = FakeLLM({"KBIS": CheckOutput(status="doubtful", file_id="F2")})
    graph, config, _ = run(llm)

    state = graph.invoke(Command(resume=answer), config)

    # Still paused, with the error explained to the reviewer.
    assert "report" not in state
    assert message in state["__interrupt__"][0].value["error"]
    assert graph.get_state(config).values["review_error"]

    # A valid answer completes the review.
    final = graph.invoke(Command(resume=[{"requirement_code": "KBIS", "status": "present"}]), config)
    assert final["status"] == "completed"
    assert final["verdict"] == "complete"


# A6: evidence that is not in the file


def test_evidence_not_found_in_file_makes_the_finding_doubtful():
    llm = FakeLLM({"DC1": CheckOutput(status="present", file_id="F1", evidence="invented passage")})
    _, _, state = run(llm)

    finding = next(f for f in state["findings"] if f.requirement_code == "DC1")
    assert finding.status == "doubtful"
    assert "not found" in finding.reasoning
    assert "__interrupt__" in state


def test_unknown_file_reference_makes_the_finding_doubtful():
    llm = FakeLLM({"DC1": CheckOutput(status="present", file_id="F9", evidence="Application letter")})
    _, _, state = run(llm)

    finding = next(f for f in state["findings"] if f.requirement_code == "DC1")
    assert finding.status == "doubtful"
    assert finding.matched_file is None


# A7: unreadable file


def test_unreadable_file_never_produces_a_missing_finding():
    llm = FakeLLM({"KBIS": CheckOutput(status="missing", reasoning="nothing found")})
    files = [FILES[0], SubmittedFile(name="kbis.txt", text="  ")]
    _, _, state = run(llm, files=files)

    unreadable = [d for d in state["extracted_documents"] if d.status == "unreadable"]
    assert [d.file_name for d in unreadable] == ["kbis.txt"]
    finding = next(f for f in state["findings"] if f.requirement_code == "KBIS")
    assert finding.status == "doubtful"
    assert "could not be read" in finding.reasoning


def test_model_error_during_extraction_is_retried_then_fails_the_review():
    llm = FakeLLM(fail_on_file="kbis.txt")
    graph = build_graph(llm=llm, checkpointer=InMemorySaver())

    with pytest.raises(TransientModelError):
        graph.invoke(
            {"review_id": "t", "required_documents": CHECKLIST, "submitted_files": FILES},
            {"configurable": {"thread_id": "t"}},
        )

    # Three attempts for the failing file: the provider error was retried, not hidden.
    assert llm.calls.count("extract") == 1 + 3


def test_truncated_file_cannot_produce_a_missing_finding():
    long_text = (
        "Registration extract. "
        + ("filler " * (MAX_CHARS_PER_FILE // 7 + 10))
        + " Insurance certificate at the end."
    )
    files = [FILES[0], SubmittedFile(name="long.txt", text=long_text)]
    llm = FakeLLM({"KBIS": CheckOutput(status="missing", reasoning="not seen")})
    _, _, state = run(llm, files=files)

    finding = next(f for f in state["findings"] if f.requirement_code == "KBIS")
    assert finding.status == "doubtful"
    assert "first 6000 characters of: long.txt" in finding.reasoning


def test_all_files_unreadable_skips_the_model_and_asks_a_human():
    llm = FakeLLM()
    _, _, state = run(llm, files=[SubmittedFile(name="empty.txt", text="   ")])

    assert all(f.status == "doubtful" for f in state["findings"])
    assert llm.calls.count("check") == 0
    assert "__interrupt__" in state


# A9: optional requirement missing


def test_missing_optional_requirement_keeps_the_verdict_complete():
    llm = FakeLLM({"REFS": CheckOutput(status="missing", reasoning="no references")})
    _, _, state = run(llm)

    assert state["verdict"] == "complete"
    assert statuses(state)["REFS"] == "missing"
    assert "REFS References (optional)" in state["report"]


def test_report_escapes_html_in_reviewer_comments_and_evidence():
    llm = FakeLLM({"KBIS": CheckOutput(status="doubtful", file_id="F2", evidence="<b>bold</b>")})
    graph, config, _ = run(llm)
    comment = '<img src=x onerror="alert(1)">'
    final = graph.invoke(
        Command(resume=[{"requirement_code": "KBIS", "status": "missing", "comment": comment}]), config
    )

    assert "<img" not in final["report"]
    assert "&lt;img src=x onerror=&quot;" not in final["report"]  # quotes stay readable
    assert '&lt;img src=x onerror="alert(1)"&gt;' in final["report"]


def test_summary_failure_does_not_block_the_report():
    class NoSummaryLLM(FakeLLM):
        def invoke(self, messages):
            raise RuntimeError("model down")

    _, _, state = run(NoSummaryLLM())
    assert state["status"] == "completed"
    assert "## Summary" not in state["report"]


def test_empty_checklist_is_rejected():
    graph = build_graph(llm=FakeLLM())
    with pytest.raises(ValueError):
        graph.invoke({"required_documents": [], "submitted_files": FILES})
