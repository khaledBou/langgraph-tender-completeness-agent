"""API tests. The workflow runs inside the request with the deterministic model."""

from io import StringIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command

from reviews import services
from reviews.models import Checklist, Review


@pytest.fixture(autouse=True)
def checklists(db, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    call_command("load_checklists", verbosity=0)


def upload(name: str, text: str) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, text.encode(), content_type="text/plain")


def create_review(client, files, candidate="Volt Services"):
    return client.post(
        "/api/reviews/",
        {"candidate_name": candidate, "checklist": "default", "files": files},
        format="multipart",
    )


def test_checklists_are_listed(client):
    response = client.get("/api/checklists/")
    assert response.status_code == 200
    assert response.json()[0]["slug"] == "default"
    assert len(response.json()[0]["items"]) == 5


def test_complete_application_is_reviewed_and_completed(client):
    files = [upload("dc1.txt", "Application letter DC1 signed"), upload("kbis.txt", "Registration extract")]
    response = create_review(client, files)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "completed"
    assert body["verdict"] == "complete"
    assert len(body["files"]) == 2
    assert len(body["resolved_findings"]) == 5
    assert body["report"].startswith("# Completeness review")

    listed = client.get("/api/reviews/").json()
    assert listed[0]["id"] == body["id"]
    assert listed[0]["status"] == "completed"


def test_application_without_files_is_incomplete(client):
    response = create_review(client, [])

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "completed"
    assert body["verdict"] == "incomplete"
    assert all(f["status"] == "missing" for f in body["resolved_findings"])


def test_unsupported_file_is_stored_as_unreadable_and_pauses_the_review(client):
    files = [SimpleUploadedFile("scan.xyz", b"\x00\x01", content_type="application/octet-stream")]
    response = create_review(client, files)

    assert response.status_code == 201
    body = response.json()
    assert body["files"][0]["extraction_error"].startswith("Unsupported file type")
    assert body["status"] == "waiting_for_human"
    assert len(body["pending_review"]["findings"]) == 5


def test_decisions_resume_a_paused_review(client):
    files = [SimpleUploadedFile("scan.xyz", b"\x00\x01", content_type="application/octet-stream")]
    review_id = create_review(client, files).json()["id"]

    # Partial answer: refused, review stays paused.
    partial = client.post(
        f"/api/reviews/{review_id}/decisions/",
        {"decisions": [{"requirement_code": "DC1", "status": "present"}]},
        content_type="application/json",
    )
    assert partial.status_code == 400
    assert "Missing decision" in partial.json()["detail"]
    assert Review.objects.get(pk=review_id).status == "waiting_for_human"

    # Full answer: review completes.
    decisions = [
        {"requirement_code": code, "status": "missing"} for code in ["DC1", "DC2", "KBIS", "INSURANCE"]
    ]
    decisions.append({"requirement_code": "REFERENCES", "status": "present", "comment": "seen on paper"})
    response = client.post(
        f"/api/reviews/{review_id}/decisions/", {"decisions": decisions}, content_type="application/json"
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "completed"
    assert body["verdict"] == "incomplete"
    assert [f["decided_by"] for f in body["resolved_findings"]] == ["reviewer"] * 5

    # A completed review refuses new decisions.
    again = client.post(
        f"/api/reviews/{review_id}/decisions/", {"decisions": decisions}, content_type="application/json"
    )
    assert again.status_code == 409


def test_unknown_checklist_is_rejected(client):
    response = client.post("/api/reviews/", {"candidate_name": "X", "checklist": "nope"}, format="multipart")
    assert response.status_code == 400


def test_files_are_downloaded_through_the_api(client):
    files = [upload("dc1.txt", "Application letter DC1 signed")]
    body = create_review(client, files).json()
    url = body["files"][0]["url"]

    assert url == f"/api/reviews/{body['id']}/files/{body['files'][0]['id']}/download/"
    response = client.get(url)
    assert response.status_code == 200
    assert b"".join(response.streaming_content) == b"Application letter DC1 signed"


def test_requirements_are_frozen_at_creation(client):
    body = create_review(client, [upload("dc1.txt", "Application letter")]).json()
    assert [r["code"] for r in body["requirements"]] == ["DC1", "DC2", "KBIS", "INSURANCE", "REFERENCES"]

    checklist = Checklist.objects.get(slug="default")
    checklist.items = [{"code": "NEW", "label": "New requirement", "description": "", "mandatory": True}]
    checklist.save()

    detail = client.get(f"/api/reviews/{body['id']}/").json()
    assert [r["code"] for r in detail["requirements"]] == ["DC1", "DC2", "KBIS", "INSURANCE", "REFERENCES"]


def test_model_failure_marks_the_review_failed(client, monkeypatch):
    from agent.testing import FakeLLM

    monkeypatch.setattr("agent.graph.get_llm", lambda: FakeLLM(fail_on_file="dc1.txt"))
    body = create_review(client, [upload("dc1.txt", "Application letter")]).json()

    assert body["status"] == "failed"
    assert "provider unavailable" in body["error"]


def recover() -> str:
    out = StringIO()
    call_command("recover_reviews", stdout=out)
    return out.getvalue()


def test_recover_restores_a_pause_left_in_running(client):
    files = [SimpleUploadedFile("scan.xyz", b"\x00", content_type="application/octet-stream")]
    review = Review.objects.get(pk=create_review(client, files).json()["id"])
    assert review.status == "waiting_for_human"
    Review.objects.filter(pk=review.id).update(status="running", pending_review=None)

    assert "restored the pause" in recover()
    review.refresh_from_db()
    assert review.status == "waiting_for_human"
    assert len(review.pending_review["findings"]) == 5


def test_recover_stores_a_finished_result_left_in_running(client):
    review = Review.objects.get(
        pk=create_review(client, [upload("dc1.txt", "Application letter")]).json()["id"]
    )
    assert review.status == "completed"
    Review.objects.filter(pk=review.id).update(status="running", report="", verdict="")

    assert "stored the finished result" in recover()
    review.refresh_from_db()
    assert review.status == "completed"
    assert review.verdict == "complete"
    assert review.report.startswith("# Completeness review")


def test_recover_starts_a_review_that_never_ran(client):
    checklist = Checklist.objects.get(slug="default")
    review = Review.objects.create(candidate_name="Stuck", checklist=checklist, requirements=checklist.items)
    Review.objects.filter(pk=review.id).update(status="running")

    assert "restarted, now completed" in recover()
    review.refresh_from_db()
    assert review.status == "completed"
    assert review.verdict == "incomplete"


def test_recover_reports_nothing_to_do(client):
    assert "Nothing to recover" in recover()


def test_decisions_are_persisted_before_the_resume(client):
    files = [SimpleUploadedFile("scan.xyz", b"\x00", content_type="application/octet-stream")]
    review = Review.objects.get(pk=create_review(client, files).json()["id"])
    decisions = [
        {"requirement_code": c, "status": "missing", "comment": ""}
        for c in ["DC1", "DC2", "KBIS", "INSURANCE", "REFERENCES"]
    ]

    services.resume_review(review, decisions)

    review.refresh_from_db()
    assert review.status == "completed"
    assert [d["requirement_code"] for d in review.human_decisions] == [
        "DC1",
        "DC2",
        "KBIS",
        "INSURANCE",
        "REFERENCES",
    ]
