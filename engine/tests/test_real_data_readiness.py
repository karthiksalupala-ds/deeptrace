import json
import os
import tracemalloc

from fastapi.testclient import TestClient

from backend.main import app
from engine.pipeline import run_recovery
from engine.synthetic_image_gen import SyntheticImageGenerator, generate_dahua_scenario
from engine.vendors.dahua import DahuaParser
from engine.vendors.hikvision import HikvisionParser


def test_dahua_permissive_mode_recovers_checksum_failures(tmp_path):
    image = str(tmp_path / "dahua_checksums.img")
    generate_dahua_scenario(image, num_frames=40, num_corrupted=10, num_gaps=0)
    parser = DahuaParser()

    strict = [frame for frame in parser.parse_frames(image, strict=True) if frame.valid]
    permissive = [frame for frame in parser.parse_frames(image, strict=False) if frame.valid]

    assert len(strict) < len(permissive) <= 40
    assert all(frame.validation_level == "full" for frame in strict)
    assert all(frame.validation_level == "permissive" for frame in permissive)


def test_verbose_detection_finds_signature_beyond_fixed_offsets(tmp_path):
    image = str(tmp_path / "offset.img")
    generator = SyntheticImageGenerator()
    generator.add_manufacturer_signature("hikvision", offset=733_184)
    generator.write(image)

    result = HikvisionParser().detect_verbose(image)

    assert result.found is True
    assert result.offset == 733_184
    assert result.method == "bounded_scan"


def test_large_sparse_images_parse_without_heap_copy(tmp_path):
    for vendor in ("hikvision", "dahua"):
        image = tmp_path / f"large_{vendor}.img"
        generator = SyntheticImageGenerator()
        generator.add_manufacturer_signature(vendor)
        for index in range(3):
            if vendor == "hikvision":
                generator.add_hikvision_frame(frame_number=index)
            else:
                generator.add_dahua_frame(frame_number=index)
        generator.write(str(image))
        with image.open("r+b") as handle:
            handle.seek(500 * 1024 * 1024 - 1)
            handle.write(b"\0")

        tracemalloc.start()
        parser = HikvisionParser() if vendor == "hikvision" else DahuaParser()
        frames = [frame for frame in parser.parse_frames(str(image)) if frame.valid]
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        assert len(frames) == 3
        assert peak < 32 * 1024 * 1024


def test_partial_report_explains_detected_but_unparsed_image(tmp_path):
    image = tmp_path / "variant.img"
    generator = SyntheticImageGenerator()
    generator.add_manufacturer_signature("hikvision")
    generator.add_noise(4096)
    generator.write(str(image))
    report = run_recovery(str(image), str(tmp_path / "out"))

    assert report["device_identification"]["vendor_name"] == "Hikvision"
    assert report["recovery_stats"]["valid_frames"] == 0
    assert "No valid frames extracted" in report["parsing_notes"]


def test_api_strict_parameter_is_recorded_in_report():
    response = TestClient(app).post(
        "/api/demo/generate",
        json={"vendor": "dahua", "scenario": "clean", "strict": False},
    )
    assert response.status_code == 200
    report = TestClient(app).get(
        f"/api/jobs/{response.json()['job_id']}/report.json"
    ).json()
    assert report["validation_level"] == "permissive"
    assert report["recovery_stats"]["validation_level"] == "permissive"