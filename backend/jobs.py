import datetime
import logging
import traceback
from typing import Dict, Any

from engine.pipeline import run_recovery
from .models import JobStatus, JobResponse
from .storage import get_job_dir

logger = logging.getLogger(__name__)

# Global in-memory job store for zero-config MVP
_JOB_STORE: Dict[str, JobResponse] = {}


def create_job(job_id: str) -> JobResponse:
    job = JobResponse(
        job_id=job_id,
        status=JobStatus.QUEUED,
        progress=0.0,
        created_at=datetime.datetime.now(tz=datetime.timezone.utc),
    )
    _JOB_STORE[job_id] = job
    return job


def get_job(job_id: str) -> JobResponse | None:
    return _JOB_STORE.get(job_id)


def get_all_jobs() -> list[JobResponse]:
    return list(_JOB_STORE.values())


def run_job_async(job_id: str, image_path: str, is_demo_scenario: bool = False):
    """
    Background worker that executes the core forensic pipeline.
    """
    job = _JOB_STORE.get(job_id)
    if not job:
        logger.error(f"Job {job_id} not found when starting worker.")
        return

    job.status = JobStatus.PROCESSING
    job.progress = 10.0

    try:
        output_dir = get_job_dir(job_id)
        # DeepTrace pipeline is synchronous right now, so we just call it.
        # It's blocking the worker thread, but FastAPI BackgroundTasks run in a separate threadpool.
        run_recovery(image_path, output_dir, demo_mode=is_demo_scenario)

        job.status = JobStatus.COMPLETED
        job.progress = 100.0
        job.completed_at = datetime.datetime.now(tz=datetime.timezone.utc)
    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}")
        logger.error(traceback.format_exc())
        job.status = JobStatus.ERROR
        job.progress = 0.0
        job.error_message = str(e)
        job.completed_at = datetime.datetime.now(tz=datetime.timezone.utc)
