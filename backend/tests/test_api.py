import pytest
from fastapi.testclient import TestClient

from backend.main import app
from engine.synthetic_image_gen import generate_hikvision_scenario

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_list_vendors():
    response = client.get("/api/v1/vendors")
    assert response.status_code == 200
    data = response.json()
    assert "vendors" in data
    # Should at least have hikvision and dahua
    vendor_ids = [v["id"] for v in data["vendors"]]
    assert "hikvision" in vendor_ids
    assert "dahua" in vendor_ids

def test_generate_demo_unsupported_vendor():
    response = client.post("/api/v1/demo/generate", json={"vendor": "unknown", "scenario": "clean"})
    # Pydantic should catch the invalid literal value before the handler
    assert response.status_code == 422 


def test_upload_poll_report_and_download(tmp_path):
    image_path = tmp_path / "fixture.img"
    generate_hikvision_scenario(
        str(image_path), num_frames=20, num_corrupted=0, num_gaps=0
    )

    response = client.post(
        "/api/jobs",
        files={"file": ("fixture.img", image_path.read_bytes(), "application/octet-stream")},
    )
    assert response.status_code == 200
    job_id = response.json()["job_id"]

    status = client.get(f"/api/jobs/{job_id}")
    assert status.status_code == 200
    body = status.json()
    assert body["status"] == "done"
    assert body["report"] is not None
    assert "recovery_stats" in body["report"]

    report = client.get(f"/api/jobs/{job_id}/report.json")
    assert report.status_code == 200
    assert "device_identification" in report.json()

    files = client.get(f"/api/jobs/{job_id}/files")
    assert files.status_code == 200
    assert files.json()["files"]
    downloaded = client.get(f"/api/jobs/{job_id}/files/{files.json()['files'][0]}")
    assert downloaded.status_code == 200
    assert "attachment" in downloaded.headers["content-disposition"]
    assert int(downloaded.headers["content-length"]) > 0


def test_empty_upload_is_rejected():
    response = client.post(
        "/api/jobs",
        files={"file": ("empty.img", b"", "application/octet-stream")},
    )
    assert response.status_code == 400
