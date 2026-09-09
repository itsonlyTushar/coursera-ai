from typing import Any

from pydantic import BaseModel, Field


# Lifecycle: queued -> running -> completed | failed
class IngestJob(BaseModel):
    job_id: str
    status: str = "queued"
    stage: str = "queued"
    progress: float = 0.0
    lecture_id: str
    course_id: str
    owner: str | None = None
    message: str = ""
    error: str | None = None
    result: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class IngestJobList(BaseModel):
    jobs: list[IngestJob] = Field(default_factory=list)
