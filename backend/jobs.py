import datetime
import logging
import threading
import uuid
from pathlib import Path

from engine.pipeline import run_recovery

from .models import Job, JobStatus
from .storage import get_output_dir

logger = logging.getLogger(__name__)

_JOB_STORE: dict[str, Job] = {}
_JOB_INPUTS: dict[str, tuple[str, bool]] = {}
_JOB_LOCK = threading.Lock()


def create_job(upload_path: str, filename: str | None = None, generate_demo_mp4s: bool = False) -> str:
    """Register an input path and return its new job ID."""
    job_id = uuid.uuid4().hex
    job = Job(
        job_id=job_id,
        filename=filename or Path(upload_path).name,
        created_at=datetime.datetime.now(tz=datetime.timezone.utc),
    )
    with _JOB_LOCK:
        _JOB_STORE[job_id] = job
        _JOB_INPUTS[job_id] = (upload_path, generate_demo_mp4s)
    return job_id


def get_job(job_id: str) -> Job | None:
    with _JOB_LOCK:
        return _JOB_STORE.get(job_id)


def get_all_jobs() -> list[Job]:
    with _JOB_LOCK:
        return list(_JOB_STORE.values())


def set_job_input(job_id: str, image_path: str, generate_demo_mp4s: bool = False) -> None:
    with _JOB_LOCK:
        _JOB_INPUTS[job_id] = (image_path, generate_demo_mp4s)


def run_job_async(job_id: str) -> None:
    """Run the synchronous recovery pipeline in FastAPI's worker thread."""
    with _JOB_LOCK:
        job = _JOB_STORE.get(job_id)
        input_info = _JOB_INPUTS.get(job_id)
        if job is None or input_info is None:
            logger.error("Job %s was not registered before processing", job_id)
            return
        job.status = JobStatus.PROCESSING

    image_path, generate_demo_mp4s = input_info
    try:
        report = run_recovery(
            image_path=image_path,
            out_dir=get_output_dir(job_id),
            generate_demo_mp4s=generate_demo_mp4s,
        )
        with _JOB_LOCK:
            job.report = report
            job.status = JobStatus.DONE
    except Exception as exc:
        logger.exception("Recovery job %s failed", job_id)
        with _JOB_LOCK:
            job.status = JobStatus.FAILED
            job.error = str(exc)
