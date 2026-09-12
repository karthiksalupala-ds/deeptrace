import os
import shutil
from pathlib import Path
from typing import BinaryIO


STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local")
LOCAL_STORAGE_ROOT = Path(__file__).resolve().parent / "data"


def _ensure_dir(job_id: str) -> Path:
    job_dir = LOCAL_STORAGE_ROOT / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    return job_dir


def save_upload(file: BinaryIO, job_id: str, filename: str = "source.img") -> str:
    """Persist an upload and return its absolute path."""
    if STORAGE_BACKEND != "local":
        raise NotImplementedError("Supabase storage is not configured in this MVP.")
    destination = _ensure_dir(job_id) / Path(filename).name
    with destination.open("wb") as output:
        shutil.copyfileobj(file, output)
    return str(destination.resolve())


def get_output_dir(job_id: str) -> str:
    """Return the directory where a job's recovered files are written."""
    if STORAGE_BACKEND != "local":
        raise NotImplementedError("Supabase storage is not configured in this MVP.")
    return str(_ensure_dir(job_id).resolve())


def list_recovered_files(job_id: str) -> list[str]:
    """List output artifacts, excluding the source image and report."""
    job_dir = Path(get_output_dir(job_id))
    return [
        str(path)
        for path in sorted(job_dir.iterdir())
        if (
            path.is_file()
            and path.name not in {"source.img", "report.json"}
            and not path.name.endswith(".meta.json")
        )
    ]


# Compatibility aliases for the initial backend scaffold.
save_upload_file = save_upload
get_job_dir = get_output_dir
get_job_files = list_recovered_files
