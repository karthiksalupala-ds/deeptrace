import pytest
from fastapi.testclient import TestClient

from backend.main import app

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
