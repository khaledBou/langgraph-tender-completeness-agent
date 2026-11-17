"""Integration test: two simultaneous resumes, only one runs. Needs TEST_DATABASE_URL."""

import os
import subprocess
import sys

import pytest

DATABASE_URL = os.getenv("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL is not set")


def test_concurrent_resumes_are_serialised_by_the_row_lock():
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings",
        "DATABASE_URL": DATABASE_URL,
        "CHECKPOINTER_URL": DATABASE_URL,
    }
    result = subprocess.run(
        [sys.executable, "-m", "scripts.concurrent_resume"], capture_output=True, text=True, env=env
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "outcomes=['refused', 'resumed'] status=completed" in result.stdout
