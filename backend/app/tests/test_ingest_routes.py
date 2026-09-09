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
        data={"lecture_id": "lec01", "course_id": "deeplearning"},
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
