"""Prove that a paused review survives a process restart.

Run the two steps in two different processes, with the same thread id:

    DATABASE_URL=postgres://... uv run python -m scripts.durable_resume start my-review
    DATABASE_URL=postgres://... uv run python -m scripts.durable_resume resume my-review

The first step runs the workflow until it pauses on a doubtful finding and exits.
The second step opens a new connection, sends the reviewer decision and prints the verdict.
"""

import argparse
import os
import sys

import psycopg
from dotenv import load_dotenv
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command
from psycopg.rows import dict_row

from agent.graph import build_graph
from agent.schemas import CheckOutput, RequiredDocument, SubmittedFile
from agent.serde import make_serializer
from agent.testing import FakeLLM

CHECKLIST = [
    RequiredDocument(code="DC1", label="Application letter"),
    RequiredDocument(code="KBIS", label="Registration extract"),
]
FILES = [
    SubmittedFile(name="dc1.txt", text="Application letter signed by the director"),
    SubmittedFile(name="kbis.txt", text="Registration extract issued in March"),
]


def make_llm():
    if os.getenv("LLM_PROVIDER", "fake") == "fake":
        return FakeLLM(
            {"KBIS": CheckOutput(status="doubtful", file_id="F2", reasoning="extract may be too old")}
        )
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("step", choices=["start", "resume"])
    parser.add_argument("thread_id")
    args = parser.parse_args()

    load_dotenv()
    database_url = os.environ["DATABASE_URL"]
    config = {"configurable": {"thread_id": args.thread_id}}

    with psycopg.connect(database_url, autocommit=True, row_factory=dict_row) as conn:
        checkpointer = PostgresSaver(conn, serde=make_serializer())
        checkpointer.setup()
        graph = build_graph(llm=make_llm(), checkpointer=checkpointer)

        if args.step == "start":
            state = graph.invoke(
                {"review_id": args.thread_id, "required_documents": CHECKLIST, "submitted_files": FILES},
                config,
            )
            if "__interrupt__" not in state:
                print("The workflow did not pause")
                return 1
            codes = [f["requirement_code"] for f in state["__interrupt__"][0].value["findings"]]
            print(f"paused on {codes}")
            return 0

        snapshot = graph.get_state(config)
        if not snapshot.next:
            print("Nothing to resume")
            return 1
        decisions = [
            {"requirement_code": "KBIS", "status": "missing", "comment": "extract older than 3 months"}
        ]
        state = graph.invoke(Command(resume=decisions), config)
        print(f"status={state['status']} verdict={state['verdict']}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
