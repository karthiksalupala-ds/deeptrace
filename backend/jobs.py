import datetime
import json
import logging
import os
import threading
import uuid
from pathlib import Path

from engine.pipeline import run_recovery

from .models import Job, JobStatus
from .storage import LOCAL_STORAGE_ROOT, get_output_dir

logger = logging.getLogger(__name__)

_JOB_STORE: dict[str, Job] = {}
_JOB_INPUTS: dict[str, tuple[str, bool, bool]] = {}
_JOB_LOCK = threading.Lock()
_CUSTODY_LOCK = threading.Lock()
CUSTODY_LOG_PATH = LOCAL_STORAGE_ROOT / "custody_log.jsonl"


def _load_last_custody_hash() -> str | None:
    """Return the newest valid entry hash from the append-only custody ledger."""
    if not CUSTODY_LOG_PATH.exists():
        return None

    last_hash: str | None = None
    try:
        with CUSTODY_LOG_PATH.open("r", encoding="utf-8") as log_file:
            for line_number, line in enumerate(log_file, start=1):
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    entry_hash = entry["chain_of_custody"]["entry_hash"]
                    if not isinstance(entry_hash, str) or len(entry_hash) != 64:
                        raise ValueError("entry_hash is not a SHA-256 hex digest")
                    int(entry_hash, 16)
                    last_hash = entry_hash
                except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                    logger.warning("Ignoring invalid custody ledger line %d: %s", line_number, exc)
    except OSError as exc:
        logger.error("Unable to read custody ledger %s: %s", CUSTODY_LOG_PATH, exc)
    return last_hash


def _append_custody_entry(job_id: str, custody_entry: dict) -> None:
    """Durably append one completed report's custody entry; never rewrite the ledger."""
    record = {
        "ledger_version": 1,
        "job_id": job_id,
        "recorded_at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        "chain_of_custody": custody_entry,
    }
    CUSTODY_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CUSTODY_LOG_PATH.open("a", encoding="utf-8", newline="\n") as log_file:
        log_file.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        log_file.flush()
        os.fsync(log_file.fileno())


# Restored during backend startup, so a restart cannot silently reset the chain.
_LAST_CUSTODY_HASH: str | None = _load_last_custody_hash()


def create_job(upload_path: str, filename: str | None = None, generate_demo_mp4s: bool = False, strict: bool = True) -> str:
    """Register an input path and return its new job ID."""
    job_id = uuid.uuid4().hex
    job = Job(
        job_id=job_id,
        filename=filename or Path(upload_path).name,
        created_at=datetime.datetime.now(tz=datetime.timezone.utc),
    )
    with _JOB_LOCK:
        _JOB_STORE[job_id] = job
        _JOB_INPUTS[job_id] = (upload_path, generate_demo_mp4s, strict)
    return job_id


def get_job(job_id: str) -> Job | None:
    with _JOB_LOCK:
        return _JOB_STORE.get(job_id)


def get_all_jobs() -> list[Job]:
    with _JOB_LOCK:
        return list(_JOB_STORE.values())


def set_job_input(job_id: str, image_path: str, generate_demo_mp4s: bool = False, strict: bool = True) -> None:
    with _JOB_LOCK:
        _JOB_INPUTS[job_id] = (image_path, generate_demo_mp4s, strict)


def run_job_async(job_id: str) -> None:
    """Run the synchronous recovery pipeline in FastAPI's worker thread."""
    global _LAST_CUSTODY_HASH
    with _JOB_LOCK:
        job = _JOB_STORE.get(job_id)
        input_info = _JOB_INPUTS.get(job_id)
        if job is None or input_info is None:
            logger.error("Job %s was not registered before processing", job_id)
            return
        job.status = JobStatus.PROCESSING

    image_path, generate_demo_mp4s, strict = input_info
    try:
        # Serialize recovery finalization: the prior hash, new report, and durable
        # append form one chain transition and must not interleave across workers.
        with _CUSTODY_LOCK:
            previous_hash = _LAST_CUSTODY_HASH
            report = run_recovery(
                image_path=image_path,
                out_dir=get_output_dir(job_id),
                generate_demo_mp4s=generate_demo_mp4s,
                case_number=f"CASE-{job_id[:8].upper()}",
                prev_entry_hash=previous_hash,
                strict=strict,
            )
            custody_entry = report["chain_of_custody"]
            _append_custody_entry(job_id, custody_entry)
            _LAST_CUSTODY_HASH = custody_entry["entry_hash"]
        with _JOB_LOCK:
            job.report = report
            job.status = JobStatus.DONE
    except Exception as exc:
        logger.exception("Recovery job %s failed", job_id)
        with _JOB_LOCK:
            job.status = JobStatus.FAILED
            job.error = str(exc)
