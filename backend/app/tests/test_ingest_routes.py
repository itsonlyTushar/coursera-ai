import time

from app.main import app
from app.services.ingestion_service import IngestionJobManager, get_ingestion_manager


# Fake pipeline runner so the route tests exercise orchestration without ML deps or credentials.
def _fake_runner(**kwargs):
    progress = kwargs.get("progress")
    if progress:
        progress("extract", 0.5, "extracting")
    return {
        "lecture_id": kwargs["lecture_id"],
        "caption_records": 3,
        "slide_records": 2,
        "points_upserted": 5,
        "collection": "TEST",
    }


# Builds a manager backed by the fake runner and a temp working dir.
def _manager(tmp_path):
    return IngestionJobManager(data_dir=tmp_path / "ingest", runner=_fake_runner)


# Minimal multipart payload (captions + slides required).
def _files():
    return {
        "captions": ("lec01.vtt", b"WEBVTT\n\n00:00.000 --> 00:01.000\nhi", "text/vtt"),
        "slides": ("lec01.pdf", b"%PDF-1.4 fake", "application/pdf"),
    }


# Polls the status endpoint until the job leaves the running state.
def _wait(client, job_id, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/ingest/{job_id}").json()
        if body["status"] in ("completed", "failed"):
            return body
        time.sleep(0.05)
    return client.get(f"/api/ingest/{job_id}").json()


# Asserts POST /api/ingest stages files, starts a job, and runs it to completion.
def test_ingest_creates_and_runs_job(client, tmp_path):
    manager = _manager(tmp_path)
    app.dependency_overrides[get_ingestion_manager] = lambda: manager

    resp = client.post(
        "/api/ingest",
        data={"lecture_id": "lec01", "course_id": "Intro_to_bio"},
        files=_files(),
    )
    assert resp.status_code == 200
    job = resp.json()
    assert job["lecture_id"] == "lec01"
    assert job["status"] in ("queued", "running", "completed")

    done = _wait(client, job["job_id"])
    assert done["status"] == "completed"
    assert done["result"]["points_upserted"] == 5
    assert (manager.job_dir(job["job_id"]) / "captions.vtt").exists()


# Asserts an unknown job id returns 404.
def test_ingest_job_not_found(client, tmp_path):
    app.dependency_overrides[get_ingestion_manager] = lambda: _manager(tmp_path)
    assert client.get("/api/ingest/does-not-exist").status_code == 404


# Asserts the list endpoint surfaces created jobs.
def test_ingest_list(client, tmp_path):
    manager = _manager(tmp_path)
    app.dependency_overrides[get_ingestion_manager] = lambda: manager
    client.post("/api/ingest", data={"lecture_id": "lec02"}, files=_files())

    jobs = client.get("/api/ingest").json()["jobs"]
    assert any(job["lecture_id"] == "lec02" for job in jobs)


# Asserts a request with no asset files at all is rejected before a job is even created.
def test_ingest_requires_at_least_one_asset(client, tmp_path):
    app.dependency_overrides[get_ingestion_manager] = lambda: _manager(tmp_path)

    resp = client.post("/api/ingest", data={"lecture_id": "lec03"})

    assert resp.status_code == 422
    assert "at least one asset" in resp.json()["detail"].lower()


# Asserts a lecture with only a transcript (no captions/slides) is accepted and staged,
# since many courses lack slide decks or synced captions.
def test_ingest_accepts_transcript_only(client, tmp_path):
    manager = _manager(tmp_path)
    app.dependency_overrides[get_ingestion_manager] = lambda: manager

    resp = client.post(
        "/api/ingest",
        data={"lecture_id": "readings", "course_id": "bio-101"},
        files={"transcript": ("transcript.md", b"# Readings\n\nSome notes.", "text/markdown")},
    )

    assert resp.status_code == 200
    job = resp.json()
    done = _wait(client, job["job_id"])
    assert done["status"] == "completed"
    assert (manager.job_dir(job["job_id"]) / "transcript.md").exists()
    assert not (manager.job_dir(job["job_id"]) / "captions.vtt").exists()


# Asserts a quiz question set + its solutions (no captions/slides/transcript) is accepted,
# since exam/assignment evidence is exactly the "quiz + student answers" content the app needs.
def test_ingest_accepts_quiz_and_solution_only(client, tmp_path):
    manager = _manager(tmp_path)
    app.dependency_overrides[get_ingestion_manager] = lambda: manager

    resp = client.post(
        "/api/ingest",
        data={"lecture_id": "exam-1", "course_id": "bio-101"},
        files={
            "quiz": ("quiz.pdf", b"%PDF-1.4 fake question", "application/pdf"),
            "quiz_solution": ("quiz_solution.pdf", b"%PDF-1.4 fake solution", "application/pdf"),
        },
    )

    assert resp.status_code == 200
    job = resp.json()
    done = _wait(client, job["job_id"])
    assert done["status"] == "completed"
    assert (manager.job_dir(job["job_id"]) / "quiz.pdf").exists()
    assert (manager.job_dir(job["job_id"]) / "quiz_solution.pdf").exists()
