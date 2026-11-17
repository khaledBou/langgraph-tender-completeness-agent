"""LangGraph checkpointer shared by the process."""

from functools import lru_cache

from django.conf import settings
from langgraph.checkpoint.base import BaseCheckpointSaver

from agent.serde import make_serializer


@lru_cache(maxsize=1)
def get_checkpointer() -> BaseCheckpointSaver:
    """Return the checkpointer: PostgreSQL in normal use, in memory when configured so."""
    url = settings.CHECKPOINTER_URL
    if url == "memory":
        from langgraph.checkpoint.memory import InMemorySaver

        return InMemorySaver(serde=make_serializer())

    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg_pool import ConnectionPool

    pool = ConnectionPool(conninfo=url, min_size=1, max_size=4, kwargs={"autocommit": True}, open=True)
    checkpointer = PostgresSaver(pool, serde=make_serializer())
    checkpointer.setup()
    return checkpointer
