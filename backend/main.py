import json
import os
import uuid
from pathlib import Path
from typing import List

from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse

from engine.registry import build_default_registry
from engine.synthetic_image_gen import generate_dahua_scenario, generate_hikvision_scenario
from .models import JobResponse, DemoGenerateRequest
from .jobs import create_job, get_job, get_all_jobs, run_job_async
from .storage import save_upload_file, get_job_dir, get_job_files, LOCAL_STORAGE_ROOT

app = FastAPI(
    title="DeepTrace API",
    description="Backend API for DeepTrace Multi-Vendor DVR/NVR Forensic Analysis Tool.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/api/v1/vendors")
def list_vendors():
    registry = build_default_registry()
    vendors = registry.list_vendors()
    return {"vendors": vendors}


@app.post("/api/v1/jobs", response_model=JobResponse)
def create_new_job(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    job_id = str(uuid.uuid4())
    job = create_job(job_id)
    
    try:
        # Save uploaded file
        saved_path = save_upload_file(file.file, job_id, filename="source.img")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {e}")

    # Enqueue pipeline
    background_tasks.add_task(run_job_async, job_id, saved_path, is_demo_scenario=False)
    return job


@app.post("/api/v1/demo/generate", response_model=JobResponse)
def generate_demo_job(req: DemoGenerateRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    job = create_job(job_id)
    job_dir = Path(get_job_dir(job_id))
    img_path = job_dir / "source.img"
    
    try:
        if req.vendor == "hikvision":
            generate_hikvision_scenario(
                path=str(img_path),
                num_frames=200,
                num_corrupted=10 if req.scenario != "clean" else 0,
                num_gaps=20 if req.scenario == "fragmented" else 0,
            )
        elif req.vendor == "dahua":
            generate_dahua_scenario(
                path=str(img_path),
                num_frames=200,
                num_corrupted=10 if req.scenario != "clean" else 0,
                num_gaps=20 if req.scenario == "fragmented" else 0,
            )
        else:
            raise HTTPException(status_code=400, detail="Unsupported demo vendor")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate synthetic data: {e}")

    # Enqueue pipeline in demo mode (writes burned-in timestamps on mp4s if possible)
    background_tasks.add_task(run_job_async, job_id, str(img_path), is_demo_scenario=True)
    return job


@app.get("/api/v1/jobs", response_model=List[JobResponse])
def get_jobs():
    return get_all_jobs()


@app.get("/api/v1/jobs/{job_id}", response_model=JobResponse)
def get_job_status(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/v1/jobs/{job_id}/report")
def get_job_report(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    report_path = Path(get_job_dir(job_id)) / "report.json"
    if not report_path.exists():
        if job.status == "completed":
            raise HTTPException(status_code=500, detail="Job marked complete but report missing")
        raise HTTPException(status_code=404, detail="Report not generated yet")
        
    with open(report_path, "r") as f:
        return json.load(f)


@app.get("/api/v1/jobs/{job_id}/files")
def list_job_files(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    mp4_files = get_job_files(job_id)
    # Return relative paths from the jobs directory so the frontend can request them
    # MVP: we just return filenames and serve the job directory statically or provide a download endpoint
    filenames = [Path(f).name for f in mp4_files]
    return {"files": filenames}


@app.get("/api/v1/jobs/{job_id}/download/{filename}")
def download_job_file(job_id: str, filename: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    file_path = Path(get_job_dir(job_id)) / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
        
    return FileResponse(path=file_path, filename=filename)
