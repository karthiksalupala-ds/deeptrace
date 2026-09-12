import os
import shutil
from pathlib import Path
from typing import BinaryIO

# Default to local storage for zero-config MVP
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local")
LOCAL_STORAGE_ROOT = Path("sample_data") / "jobs"


def _ensure_dir(job_id: str) -> Path:
    job_dir = LOCAL_STORAGE_ROOT / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    return job_dir


def save_upload_file(file: BinaryIO, job_id: str, filename: str = "source.img") -> str:
    """Save an uploaded file to local storage. Returns the absolute path."""
    if STORAGE_BACKEND == "local":
        job_dir = _ensure_dir(job_id)
        out_path = job_dir / filename
        with open(out_path, "wb") as f:
            shutil.copyfileobj(file, f)
        return str(out_path.absolute())
    else:
        raise NotImplementedError("Supabase storage not yet implemented.")


def get_job_dir(job_id: str) -> str:
    """Return the output directory path for a job."""
    if STORAGE_BACKEND == "local":
        job_dir = _ensure_dir(job_id)
        return str(job_dir.absolute())
    else:
        raise NotImplementedError("Supabase storage not yet implemented.")


def get_job_files(job_id: str) -> list[str]:
    """List all recovered MP4 files in a job's directory."""
    if STORAGE_BACKEND == "local":
        job_dir = _ensure_dir(job_id)
        return [str(p) for p in job_dir.glob("*.mp4")]
    else:
        raise NotImplementedError("Supabase storage not yet implemented.")

