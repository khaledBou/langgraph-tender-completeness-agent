"""Reconcile reviews left in pending or running with their LangGraph checkpoints.

Use it after a restart of the service, when no worker is running.
"""

from django.core.management.base import BaseCommand

from reviews import services
from reviews.models import Review


class Command(BaseCommand):
    help = "Recover reviews stuck in pending or running after a restart"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="List the reviews without touching them")

    def handle(self, *args, **options):
        stuck = Review.objects.filter(status__in=[Review.Status.PENDING, Review.Status.RUNNING])
        if not stuck.exists():
            self.stdout.write("Nothing to recover")
            return
        for review in stuck:
            if options["dry_run"]:
                self.stdout.write(f"{review.id}: {review.status}")
                continue
            try:
                outcome = services.recover_review(review)
            except Exception as exc:
                Review.objects.filter(pk=review.id).update(status=Review.Status.FAILED, error=str(exc))
                outcome = f"failed: {exc}"
            self.stdout.write(f"{review.id}: {outcome}")
