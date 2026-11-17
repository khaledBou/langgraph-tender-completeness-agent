"""Database records of the reviews. The workflow state itself lives in LangGraph checkpoints."""

import uuid

from django.db import models


class Checklist(models.Model):
    """A named list of required documents."""

    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=200)
    items = models.JSONField(help_text="List of RequiredDocument objects")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Review(models.Model):
    """One completeness check of one application. Its id is the LangGraph thread id."""

    class Status(models.TextChoices):
        PENDING = "pending"
        RUNNING = "running"
        WAITING_FOR_HUMAN = "waiting_for_human"
        COMPLETED = "completed"
        FAILED = "failed"

    class Verdict(models.TextChoices):
        COMPLETE = "complete"
        INCOMPLETE = "incomplete"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    candidate_name = models.CharField(max_length=200)
    checklist = models.ForeignKey(Checklist, on_delete=models.PROTECT, related_name="reviews")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    verdict = models.CharField(max_length=20, choices=Verdict.choices, blank=True)
    error = models.TextField(blank=True)

    # Snapshots of the workflow state, kept for the API and for audit.
    extracted_documents = models.JSONField(default=list, blank=True)
    findings = models.JSONField(default=list, blank=True)
    pending_review = models.JSONField(null=True, blank=True, help_text="Interrupt payload while paused")
    human_decisions = models.JSONField(default=list, blank=True)
    resolved_findings = models.JSONField(default=list, blank=True)
    report = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.candidate_name} ({self.status})"


def upload_path(instance: "ReviewFile", filename: str) -> str:
    return f"reviews/{instance.review_id}/{filename}"


class ReviewFile(models.Model):
    """A file of the application, with the text extracted at upload time."""

    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name="files")
    name = models.CharField(max_length=255)
    file = models.FileField(upload_to=upload_path)
    text = models.TextField(blank=True)
    extraction_error = models.TextField(blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return self.name
