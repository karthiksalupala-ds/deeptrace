import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel


class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class Job(BaseModel):
    job_id: str
    filename: str
    status: JobStatus = JobStatus.QUEUED
    created_at: datetime.datetime
    report: dict | None = None
    error: str | None = None


JobResponse = Job


class DemoGenerateRequest(BaseModel):
    vendor: Literal["hikvision", "dahua"]
    scenario: Literal["clean", "corrupted", "fragmented"]
