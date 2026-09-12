import datetime
from enum import Enum
from typing import Optional, Literal

from pydantic import BaseModel


class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    progress: float
    error_message: Optional[str] = None
    created_at: datetime.datetime
    completed_at: Optional[datetime.datetime] = None


class DemoGenerateRequest(BaseModel):
    vendor: Literal["hikvision", "dahua"]
    scenario: Literal["clean", "corrupted", "fragmented"]
