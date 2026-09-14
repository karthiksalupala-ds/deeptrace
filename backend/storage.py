import os
import shutil
from pathlib import Path
from typing import BinaryIO, Any

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env", override=False)

STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local").strip().lower()
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "").strip()
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "deeptrace").strip() or "deeptrace"
LOCAL_STORAGE_ROOT = Path(__file__).resolve().parent / "data"


def get_supabase_client() -> Any | None:
    """Return a configured Supabase client when the keys are present."""
    if STORAGE_BACKEND != "supabase":
        return None
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise RuntimeError("Supabase keys are missing. Set SUPABASE_URL and SUPABASE_ANON_KEY in the project .env file.")
    try:
        from supabase import create_client
    except ImportError as exc:
        raise RuntimeError("The Supabase Python package is not installed. Install it with pip install supabase.") from exc
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


def _ensure_dir(job_id: str) -> Path:
    job_dir = LOCAL_STORAGE_ROOT / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    return job_dir


def save_upload(file: BinaryIO, job_id: str, filename: str = "source.img") -> str:
    """Persist an upload and return its absolute path.

    The app defaults to local storage to keep the MVP working while the Supabase
    keys are configured and ready for a future remote-backed deployment.
    """
    if STORAGE_BACKEND == "supabase":
        try:
            client = get_supabase_client()
            destination = Path(filename).name
            if client is not None:
                file_bytes = file.read()
                client.storage.from_(SUPABASE_BUCKET).upload(destination, file_bytes, file_options={"content-type": "application/octet-stream"})
                return str((LOCAL_STORAGE_ROOT / job_id / destination).resolve())
        except Exception:
            # Fall back to local storage rather than blocking a working MVP while the
            # Supabase bucket is still being configured in the project.
            pass
    destination = _ensure_dir(job_id) / Path(filename).name
    with destination.open("wb") as output:
        shutil.copyfileobj(file, output)
    return str(destination.resolve())


def get_output_dir(job_id: str) -> str:
    """Return the directory where a job's recovered files are written."""
    if STORAGE_BACKEND == "supabase":
        try:
            get_supabase_client()
        except RuntimeError:
            pass
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
