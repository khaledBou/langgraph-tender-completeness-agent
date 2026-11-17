"""Checkpoint serializer with an explicit allowlist of the state types.

LangGraph refuses to rebuild arbitrary classes from a checkpoint unless they are
registered. Every Pydantic model stored in the state is listed here.
"""

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from agent.schemas import ExtractedDocument, Finding, HumanDecision, RequiredDocument, SubmittedFile

STATE_TYPES = [RequiredDocument, SubmittedFile, ExtractedDocument, Finding, HumanDecision]


def make_serializer() -> JsonPlusSerializer:
    return JsonPlusSerializer(allowed_msgpack_modules=STATE_TYPES)
