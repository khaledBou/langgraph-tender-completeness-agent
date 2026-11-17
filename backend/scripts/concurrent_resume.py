"""Prove that two simultaneous resumes of the same review cannot both run.

Needs a PostgreSQL DATABASE_URL (row locks are not exercised by SQLite in memory).

    DATABASE_URL=postgres://... uv run python -m scripts.concurrent_resume
"""

import os
import sys
import threading

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ["LLM_PROVIDER"] = "fake"
os.environ["REVIEWS_RUN_SYNC"] = "1"

import django  # noqa: E402

django.setup()

from django.core.management import call_command  # noqa: E402
from django.db import connection  # noqa: E402

from reviews import services  # noqa: E402
from reviews.models import Checklist, Review, ReviewFile  # noqa: E402


def main() -> int:
    call_command("migrate", verbosity=0)
    call_command("load_checklists", verbosity=0)
    checklist = Checklist.objects.get(slug="default")
    review = Review.objects.create(
        candidate_name="Concurrency check", checklist=checklist, requirements=checklist.items
    )
    # An unsupported file is unreadable, which pauses the review without calling the model.
    ReviewFile.objects.create(review=review, name="scan.xyz", extraction_error="Unsupported file type")
    services.start_review(review)
    review.refresh_from_db()
    assert review.status == Review.Status.WAITING_FOR_HUMAN, review.status

    decisions = [
        {"requirement_code": c, "status": "missing", "comment": ""}
        for c in ["DC1", "DC2", "KBIS", "INSURANCE", "REFERENCES"]
    ]
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def attempt():
        barrier.wait()
        try:
            services.resume_review(Review.objects.get(pk=review.id), decisions)
            outcomes.append("resumed")
        except services.ReviewStateError:
            outcomes.append("refused")
        finally:
            connection.close()

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    review.refresh_from_db()
    print(f"outcomes={sorted(outcomes)} status={review.status}")
    return 0 if sorted(outcomes) == ["refused", "resumed"] and review.status == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
