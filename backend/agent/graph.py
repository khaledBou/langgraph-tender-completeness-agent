"""Definition of the completeness review graph.

Flow:
    start -> extract_document (one worker per file, skipped when no file)
          -> collect_documents -> check_requirement (one worker per requirement)
          -> aggregate -> human_review (only when a finding is doubtful, repeated
             while the reviewer answer is invalid)
          -> finalize
"""

from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import RetryPolicy

from agent.llm import get_llm
from agent.nodes import ReviewNodes
from agent.state import ReviewState

# Model calls are retried a few times on transient errors (network, rate limit).
MODEL_RETRY = RetryPolicy(max_attempts=3)


def build_graph(
    llm: BaseChatModel | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    """Compile the review graph.

    A checkpointer is required to pause on human review and resume later.
    """
    nodes = ReviewNodes(llm or get_llm())
    graph = StateGraph(ReviewState)

    graph.add_node("start", nodes.start)
    graph.add_node("extract_document", nodes.extract_document, retry_policy=MODEL_RETRY)
    graph.add_node("collect_documents", nodes.collect_documents)
    graph.add_node("check_requirement", nodes.check_requirement, retry_policy=MODEL_RETRY)
    graph.add_node("aggregate", nodes.aggregate)
    graph.add_node("human_review", nodes.human_review)
    graph.add_node("finalize", nodes.finalize)

    graph.add_edge(START, "start")
    graph.add_conditional_edges("start", nodes.fan_out_extraction, ["extract_document", "collect_documents"])
    graph.add_edge("extract_document", "collect_documents")
    graph.add_conditional_edges("collect_documents", nodes.fan_out_checks, ["check_requirement"])
    graph.add_edge("check_requirement", "aggregate")
    graph.add_conditional_edges("aggregate", nodes.route_after_checks, ["human_review", "finalize"])
    graph.add_conditional_edges("human_review", nodes.route_after_review, ["human_review", "finalize"])
    graph.add_edge("finalize", END)

    return graph.compile(checkpointer=checkpointer)
