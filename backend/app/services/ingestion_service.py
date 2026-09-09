"""Background-job orchestration for online lecture ingestion.

The backend is the API layer: it stages an educator's uploaded assets to a
per-job working directory and runs the heavy pipeline (extract → Gemini →
API embeddings → Qdrant) on a background thread, exposing status by polling.

The actual pipeline lives in the ``database`` package
(``src.ingest_service.ingest_lecture``) and is injected as ``runner`` so this
orchestration can be unit-tested without the ML dependencies or credentials.
"""
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
import sys
import threading
import uuid
from typing import Any, Callable, Optional

from app.core.config import BACKEND_ROOT
from app.core.logging import get_logger
from app.schemas import IngestJob


logger = get_logger(__name__)

Runner = Callable[..., dict[str, Any]]
DATABASE_DIR = BACKEND_ROOT.parent / "database"


def _now() -> str:
    # Single timestamp helper so created/updated times share one format.
    return datetime.now(timezone.utc).isoformat()


def default_runner(**kwargs: Any) -> dict[str, Any]:
    # Lazily loads and calls the database pipeline so the backend imports heavy ML deps only when a job actually runs.
    if str(DATABASE_DIR) not in sys.path:
        sys.path.insert(0, str(DATABASE_DIR))
    from src.ingest_service import ingest_lecture  # type: ignore

    return ingest_lecture(**kwargs)


class IngestionJobManager:
    def __init__(
        self,
        data_dir: Path,
        runner: Optional[Runner] = None,
        max_workers: int = 1,
    ) -> None:
        # Sets up the job store, a serial worker pool, and the (injectable) pipeline runner.
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._runner = runner or default_runner
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._jobs: dict[str, IngestJob] = {}
        self._lock = threading.Lock()

    def job_dir(self, job_id: str) -> Path:
        # Returns the isolated working directory for one job's uploads and intermediates.
        return self.data_dir / job_id

    def create_job(self, *, lecture_id: str, course_id: str, owner: str | None) -> IngestJob:
        # Registers a queued job and its working directory so files can be staged before it starts.
        job_id = str(uuid.uuid4())
        now = _now()
        job = IngestJob(
            job_id=job_id,
            status="queued",
            stage="queued",
            lecture_id=lecture_id,
            course_id=course_id,
            owner=owner,
            created_at=now,
            updated_at=now,
        )
        self.job_dir(job_id).mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._jobs[job_id] = job
        return job

    def save_upload(self, job_id: str, filename: str, data: bytes) -> Path:
        # Writes one uploaded asset into the job directory and returns its path for the runner.
        target = self.job_dir(job_id) / filename
        target.write_bytes(data)
        return target

    def start(self, job_id: str, files: dict[str, Path]) -> "Future[Any]":
        # Submits the pipeline to the worker pool so the request returns immediately while ingestion runs in the background.
        return self._executor.submit(self._run, job_id, files)

    def get(self, job_id: str) -> IngestJob | None:
        # Reads current job state so the status endpoint can report progress.
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list[IngestJob]:
        # Lists jobs newest-first so a UI can show recent ingestion runs.
        with self._lock:
            return sorted(self._jobs.values(), key=lambda job: job.created_at, reverse=True)

    def _update(self, job_id: str, **fields: Any) -> None:
        # Thread-safe patch of a job's fields, always refreshing updated_at.
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            self._jobs[job_id] = job.model_copy(update={**fields, "updated_at": _now()})

    def _run(self, job_id: str, files: dict[str, Path]) -> dict[str, Any]:
        # Executes one job: runs the pipeline, recording running/completed/failed state and progress along the way.
        job = self.get(job_id)
        if job is None:
            return {}

        def progress(stage: str, pct: float, message: str) -> None:
            self._update(job_id, stage=stage, progress=round(float(pct), 3), message=message)

        self._update(job_id, status="running", stage="starting", message="pipeline started")
        try:
            result = self._runner(
                work_dir=self.job_dir(job_id),
                lecture_id=job.lecture_id,
                course_id=job.course_id,
                caption_path=files.get("caption"),
                slide_path=files.get("slide"),
                transcript_path=files.get("transcript"),
                video_path=files.get("video"),
                progress=progress,
            )
            self._update(
                job_id,
                status="completed",
                stage="done",
                progress=1.0,
                message="ingestion complete",
                result=result,
            )
            return result
        except Exception as exc:  # keep the worker alive; surface failure on the job
            logger.exception("Ingestion job %s failed", job_id)
            self._update(job_id, status="failed", message="ingestion failed", error=str(exc))
            raise


@lru_cache
def get_ingestion_manager() -> IngestionJobManager:
    # Provides a cached manager as a FastAPI dependency so all requests share one job store and worker pool.
    return IngestionJobManager(data_dir=BACKEND_ROOT / ".data" / "ingest")
