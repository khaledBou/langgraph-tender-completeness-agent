"""API tests. The workflow runs inside the request with the deterministic model."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command

from reviews.models import Review


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
