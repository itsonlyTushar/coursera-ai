from pathlib import Path

from app.services.ingestion_service import IngestionJobManager


# Asserts the manager drives a job to completion and records the runner's result + progress.
def test_manager_runs_job_to_completion(tmp_path):
    def runner(**kwargs):
        kwargs["progress"]("embedding", 0.5, "halfway")
        return {"points_upserted": 7}

    manager = IngestionJobManager(data_dir=tmp_path, runner=runner)
    job = manager.create_job(lecture_id="lec01", course_id="c", owner=None)
    manager.start(job.job_id, {"caption": Path("x"), "slide": Path("y")}).result(timeout=5)

    final = manager.get(job.job_id)
    assert final.status == "completed"
    assert final.result["points_upserted"] == 7
    assert final.progress == 1.0


# Asserts a runner exception is captured as a failed job rather than crashing the worker.
def test_manager_marks_failure(tmp_path):
    def runner(**kwargs):
        raise RuntimeError("boom")

    manager = IngestionJobManager(data_dir=tmp_path, runner=runner)
    job = manager.create_job(lecture_id="lec01", course_id="c", owner=None)
    try:
        manager.start(job.job_id, {}).result(timeout=5)
    except RuntimeError:
        pass

    final = manager.get(job.job_id)
    assert final.status == "failed"
    assert "boom" in (final.error or "")
