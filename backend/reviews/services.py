"""Run, resume and recover reviews.

The review row is the source of truth for the status shown to users. The LangGraph
checkpoint is the source of truth for the workflow state. A status transition is
done under a row lock so two runs of the same review cannot overlap.

The workflow runs in a background thread. If the process dies, the review row can
stay "running": the recover_reviews command reconciles it with the checkpoint.
"""

import logging
import threading
import uuid

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from langgraph.types import Command

from agent.graph import build_graph
from agent.schemas import RequiredDocument, SubmittedFile
from agent.tracing import get_callbacks
from reviews.checkpoints import get_checkpointer
from reviews.models import Review

logger = logging.getLogger(__name__)


class ReviewStateError(Exception):
    """The review is not in a state that allows the requested action."""


def _transition(
    review_id: uuid.UUID, allowed: tuple[str, ...], new_status: str, decisions: list[dict] | None = None
) -> Review:
    """Move the review to new_status if it is in one of the allowed statuses, under a row lock."""
    with transaction.atomic():
        review = Review.objects.select_for_update().get(pk=review_id)
        if review.status not in allowed:
            raise ReviewStateError(f"Review is {review.status}, expected one of {allowed}")
        review.status = new_status
        if new_status == Review.Status.RUNNING and review.started_at is None:
            review.started_at = timezone.now()
        if decisions is not None:
            # Persisted before the workflow records them, so a crash loses nothing.
            review.human_decisions = decisions
        review.save()
        return review


def start_review(review: Review) -> None:
    """Start the workflow for a pending review."""
    _transition(review.id, (Review.Status.PENDING,), Review.Status.RUNNING)
    _dispatch(review.id, resume_value=None)


def resume_review(review: Review, decisions: list[dict]) -> None:
    """Send the reviewer decisions to a paused review."""
    _transition(review.id, (Review.Status.WAITING_FOR_HUMAN,), Review.Status.RUNNING, decisions=decisions)
    _dispatch(review.id, resume_value=decisions)


def _dispatch(review_id: uuid.UUID, resume_value: list[dict] | None) -> None:
    if settings.REVIEWS_RUN_SYNC:
        execute(review_id, resume_value)
        return
    thread = threading.Thread(target=execute, args=(review_id, resume_value), daemon=True)
    thread.start()


def run_config(review: Review) -> dict:
    return {
        "configurable": {"thread_id": str(review.id)},
        "max_concurrency": settings.REVIEWS_MAX_CONCURRENCY,
        "callbacks": get_callbacks(),
        "run_name": f"review {review.id}",
        "metadata": {"review_id": str(review.id), "candidate": review.candidate_name},
    }


def initial_input(review: Review) -> dict:
    return {
        "review_id": str(review.id),
        "required_documents": [RequiredDocument.model_validate(i) for i in review.requirements],
        "submitted_files": [SubmittedFile(name=f.name, text=f.text) for f in review.files.all()],
    }


def execute(review_id: uuid.UUID, resume_value: list[dict] | None) -> None:
    """Run the graph until it ends or pauses, then store the result on the review.

    Any failure, including a failure to store the result, marks the review failed.
    """
    try:
        review = Review.objects.get(pk=review_id)
        graph = build_graph(checkpointer=get_checkpointer())
        graph_input = initial_input(review) if resume_value is None else Command(resume=resume_value)
        state = graph.invoke(graph_input, run_config(review))
        store_state(review, state)
    except Exception as exc:
        logger.exception("Review %s failed", review_id)
        Review.objects.filter(pk=review_id).update(
            status=Review.Status.FAILED, error=str(exc), updated_at=timezone.now()
        )


def store_state(review: Review, state: dict) -> None:
    """Copy the workflow state on the review row."""
    review.extracted_documents = [d.model_dump() for d in state.get("extracted_documents", [])]
    review.findings = [f.model_dump() for f in state.get("findings", [])]
    review.human_decisions = [
        d.model_dump() for d in state.get("human_decisions", [])
    ] or review.human_decisions
    review.error = ""

    if "__interrupt__" in state:
        review.status = Review.Status.WAITING_FOR_HUMAN
        review.pending_review = state["__interrupt__"][0].value
    else:
        review.status = Review.Status.COMPLETED
        review.pending_review = None
        review.resolved_findings = [f.model_dump() for f in state.get("resolved_findings", [])]
        review.verdict = state.get("verdict", "")
        review.report = state.get("report", "")
        review.completed_at = timezone.now()
    review.save()


def recover_review(review: Review) -> str:
    """Reconcile a review stuck in pending or running with its checkpoint.

    Run it only when no worker is executing the review (after a restart).
    Returns a short description of what was done.
    """
    graph = build_graph(checkpointer=get_checkpointer())
    config = run_config(review)
    snapshot = graph.get_state(config)

    if not snapshot.values:
        # No checkpoint: the run never started. Start it from the stored inputs.
        state = graph.invoke(initial_input(review), config)
        store_state(review, state)
        return f"restarted, now {review.status}"

    if snapshot.interrupts:
        # Paused on human review: expose the pause again.
        review.status = Review.Status.WAITING_FOR_HUMAN
        review.pending_review = snapshot.interrupts[0].value
        review.save()
        return "restored the pause"

    if not snapshot.next:
        # The workflow finished but the result was not stored.
        store_state(review, snapshot.values)
        return "stored the finished result"

    # Stopped in the middle of the workflow: continue from the checkpoint.
    state = graph.invoke(None, config)
    store_state(review, state)
    return f"continued, now {review.status}"
