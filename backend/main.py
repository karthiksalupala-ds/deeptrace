import json
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from engine.registry import build_default_registry
from engine.synthetic_image_gen import generate_dahua_scenario, generate_hikvision_scenario

from .jobs import create_job, get_all_jobs, get_job, run_job_async, set_job_input
from .models import DemoGenerateRequest, Job
from .storage import get_output_dir, list_recovered_files, save_upload

app = FastAPI(
    title="DeepTrace API",
    description="Backend API for DeepTrace DVR/NVR forensic analysis.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _require_job(job_id: str) -> Job:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def _queue_uploaded_job(background_tasks: BackgroundTasks, file: UploadFile) -> Job:
    if not file.filename:
        raise HTTPException(status_code=400, detail="A file upload is required")

    job_id = create_job("pending", filename=Path(file.filename).name)
    try:
        saved_path = save_upload(file.file, job_id, filename=file.filename)
        if Path(saved_path).stat().st_size == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")
        set_job_input(job_id, saved_path)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {exc}") from exc

    background_tasks.add_task(run_job_async, job_id)
    return _require_job(job_id)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/vendors")
@app.get("/api/v1/vendors")
def list_vendors() -> dict:
    vendors = build_default_registry().list_vendors()
    return {"vendors": [{"id": item["vendor_id"], **item} for item in vendors]}


@app.post("/api/jobs", response_model=dict[str, str])
@app.post("/api/v1/jobs", response_model=dict[str, str])
def create_new_job(background_tasks: BackgroundTasks, file: UploadFile = File(...)) -> dict[str, str]:
    job = _queue_uploaded_job(background_tasks, file)
    return {"job_id": job.job_id}


@app.post("/api/demo/generate", response_model=dict[str, str])
@app.post("/api/v1/demo/generate", response_model=dict[str, str])
def generate_demo_job(req: DemoGenerateRequest, background_tasks: BackgroundTasks) -> dict[str, str]:
    job_id = create_job("pending", filename=f"{req.vendor}_demo.img", generate_demo_mp4s=True)
    image_path = Path(get_output_dir(job_id)) / "source.img"
    generator = generate_hikvision_scenario if req.vendor == "hikvision" else generate_dahua_scenario
    try:
        generator(
            path=str(image_path),
            num_frames=200,
            num_corrupted=0 if req.scenario == "clean" else 10,
            num_gaps=20 if req.scenario == "fragmented" else 0,
        )
        set_job_input(job_id, str(image_path), generate_demo_mp4s=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to generate synthetic data: {exc}") from exc

    background_tasks.add_task(run_job_async, job_id)
    return {"job_id": job_id}


@app.get("/api/jobs", response_model=list[Job])
@app.get("/api/v1/jobs", response_model=list[Job])
def list_jobs() -> list[Job]:
    return get_all_jobs()


@app.get("/api/jobs/{job_id}", response_model=Job)
@app.get("/api/v1/jobs/{job_id}", response_model=Job)
def get_job_status(job_id: str) -> Job:
    return _require_job(job_id)


@app.get("/api/jobs/{job_id}/report.json")
@app.get("/api/v1/jobs/{job_id}/report")
def get_job_report(job_id: str) -> dict:
    _require_job(job_id)
    report_path = Path(get_output_dir(job_id)) / "report.json"
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="Report not generated yet")
    return json.loads(report_path.read_text(encoding="utf-8"))


@app.get("/api/jobs/{job_id}/files")
@app.get("/api/v1/jobs/{job_id}/files")
def list_job_files(job_id: str) -> dict[str, list[str]]:
    _require_job(job_id)
    return {"files": [Path(path).name for path in list_recovered_files(job_id)]}


@app.get("/api/jobs/{job_id}/files/{filename}")
@app.get("/api/v1/jobs/{job_id}/download/{filename}")
def download_job_file(job_id: str, filename: str) -> FileResponse:
    _require_job(job_id)
    safe_name = Path(filename).name
    if safe_name != filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    file_path = Path(get_output_dir(job_id)) / safe_name
    if not file_path.is_file() or safe_name in {"source.img", "report.json"}:
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path=file_path, filename=safe_name)
