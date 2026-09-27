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
    course_id: str = Form("Intro_to_bio"),
    owner: str | None = Form(None),
    captions: UploadFile | None = File(None),
    slides: UploadFile | None = File(None),
    transcript: UploadFile | None = File(None),
    discussion: UploadFile | None = File(None),
    quiz: UploadFile | None = File(None),
    quiz_solution: UploadFile | None = File(None),
    manager: IngestionJobManager = Depends(get_ingestion_manager),
) -> IngestJob:
    # Stages whichever lecture assets were uploaded (not every course has slides/captions) and starts a background job.
    if not any([captions, slides, transcript, discussion, quiz, quiz_solution]):
        raise HTTPException(
            status_code=422,
            detail=(
                "At least one asset is required: captions, slides, transcript, "
                "discussion, quiz, or quiz_solution."
            ),
        )

    job = manager.create_job(lecture_id=lecture_id, course_id=course_id, owner=owner)

    files: dict[str, Path] = {}
    if captions is not None:
        files["caption"] = manager.save_upload(job.job_id, f"captions{_suffix(captions, '.vtt')}", await captions.read())
    if slides is not None:
        files["slide"] = manager.save_upload(job.job_id, f"slides{_suffix(slides, '.pdf')}", await slides.read())
    if transcript is not None:
        files["transcript"] = manager.save_upload(
            job.job_id, f"transcript{_suffix(transcript, '.pdf')}", await transcript.read()
        )
    if discussion is not None:
        files["discussion"] = manager.save_upload(
            job.job_id, f"discussion{_suffix(discussion, '.md')}", await discussion.read()
        )
    if quiz is not None:
        files["quiz"] = manager.save_upload(job.job_id, f"quiz{_suffix(quiz, '.pdf')}", await quiz.read())
    if quiz_solution is not None:
        files["quiz_solution"] = manager.save_upload(
            job.job_id, f"quiz_solution{_suffix(quiz_solution, '.pdf')}", await quiz_solution.read()
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
