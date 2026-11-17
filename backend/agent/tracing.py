"""Optional Langfuse tracing. Enabled only when the Langfuse keys are present."""

import os


def langfuse_enabled() -> bool:
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))


def get_callbacks() -> list:
    """Return the LangChain callbacks to attach to a graph run."""
    if not langfuse_enabled():
        return []

    from langfuse.langchain import CallbackHandler

    return [CallbackHandler()]
