"""Settings for the test suite: in-memory database, in-process checkpoints, deterministic model."""

import os

os.environ["LLM_PROVIDER"] = "fake"

from config.settings import *  # noqa: E402, F403

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
REVIEWS_RUN_SYNC = True
CHECKPOINTER_URL = "memory"
