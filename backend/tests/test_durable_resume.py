"""Integration test: pause in one process, resume in another, through PostgreSQL.

Needs TEST_DATABASE_URL. Skipped otherwise.
"""

import os
import subprocess
import sys
import uuid

import pytest

DATABASE_URL = os.getenv("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL is not set")


def run_step(step: str, thread_id: str) -> str:
    env = {**os.environ, "DATABASE_URL": DATABASE_URL, "LLM_PROVIDER": "fake"}
    result = subprocess.run(
        [sys.executable, "-m", "scripts.durable_resume", step, thread_id],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    return result.stdout.strip()


def test_review_resumes_in_a_new_process_after_a_pause():
    thread_id = f"test-{uuid.uuid4()}"

    assert run_step("start", thread_id) == "paused on ['KBIS']"
    assert run_step("resume", thread_id) == "status=completed verdict=incomplete"


def test_resume_without_a_pause_is_refused():
    with pytest.raises(subprocess.CalledProcessError):
        run_step("resume", f"unknown-{uuid.uuid4()}")
