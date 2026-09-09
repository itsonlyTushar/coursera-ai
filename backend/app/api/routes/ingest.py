from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.schemas import IngestJob, IngestJobList
from app.services.ingestion_service import IngestionJobManager, get_ingestion_manager


router = APIRouter(prefix="/api", tags=["ingest"])


def _suffix(upload: UploadFile, fallback: str) -> str:
    # Preserves an upload's file extension so downstream parsers (webvtt/PyMuPDF/OpenCV) pick the right reader.
    return Path(upload.filename or "").suffix or fallback


@router.post("/ingest", response_model=IngestJob)
async def create_ingestion(
    lecture_id: str = Form(...),
    course_id: str = Form("deeplearning"),
    owner: str | None = Form(None),
    captions: UploadFile = File(...),
    slides: UploadFile = File(...),
    transcript: UploadFile | None = File(None),
    video: UploadFile | None = File(None),
    manager: IngestionJobManager = Depends(get_ingestion_manager),
) -> IngestJob:
    # Stages an educator's uploaded lecture assets and kicks off ingestion as a background job, returning the job to poll.
    job = manager.create_job(lecture_id=lecture_id, course_id=course_id, owner=owner)

    files: dict[str, Path] = {
        "caption": manager.save_upload(job.job_id, f"captions{_suffix(captions, '.vtt')}", await captions.read()),
        "slide": manager.save_upload(job.job_id, f"slides{_suffix(slides, '.pdf')}", await slides.read()),
    }
    if transcript is not None:
        files["transcript"] = manager.save_upload(
            job.job_id, f"transcript{_suffix(transcript, '.pdf')}", await transcript.read()
        )
    if video is not None:
        files["video"] = manager.save_upload(
            job.job_id, f"video{_suffix(video, '.mp4')}", await video.read()
        )

    manager.start(job.job_id, files)
    return manager.get(job.job_id)


@router.get("/ingest", response_model=IngestJobList)
def list_ingestion_jobs(
    manager: IngestionJobManager = Depends(get_ingestion_manager),
) -> IngestJobList:
    # Lists recent ingestion jobs so a UI can show ingestion history and in-flight runs.
    return IngestJobList(jobs=manager.list())


@router.get("/ingest/{job_id}", response_model=IngestJob)
def get_ingestion_job(
    job_id: str,
    manager: IngestionJobManager = Depends(get_ingestion_manager),
) -> IngestJob:
    # Returns one job's live status/progress so the frontend can poll until completion or failure.
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Ingestion job not found.")
    return job
