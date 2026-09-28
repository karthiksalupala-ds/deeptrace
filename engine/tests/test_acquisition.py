import json
import shutil

import pytest

from engine.acquisition import AcquisitionError, IntegrityVerificationError, acquire_image


def _copying_imager(command, check):
    source = next(arg[3:] for arg in command if arg.startswith("if="))
    destination = next(arg[3:] for arg in command if arg.startswith("of="))
    shutil.copyfile(source, destination)


def test_acquisition_writes_verified_manifest(monkeypatch, tmp_path):
    source = tmp_path / "source-device.bin"
    destination = tmp_path / "evidence.img"
    source.write_bytes(b"forensic source bytes" * 1024)
    monkeypatch.setattr("engine.acquisition.shutil.which", lambda name: f"/usr/bin/{name}" if name == "dd" else None)
    monkeypatch.setattr("engine.acquisition.subprocess.run", _copying_imager)

    manifest = acquire_image(source, destination, operator_name="Investigator A")

    manifest_path = tmp_path / "evidence.img.acquisition.json"
    assert manifest["imager"] == "dd"
    assert manifest["integrity_status"] == "verified"
    assert manifest["source_sha256"] == manifest["image_sha256"]
    assert manifest["source_size_bytes"] == manifest["image_size_bytes"] == source.stat().st_size
    assert "Hardware write-blocking" in manifest["write_blocking_notice"]
    assert json.loads(manifest_path.read_text(encoding="utf-8")) == manifest


def test_acquisition_records_hash_mismatch_before_failing(monkeypatch, tmp_path):
    source = tmp_path / "source-device.bin"
    destination = tmp_path / "evidence.img"
    source.write_bytes(b"original")
    monkeypatch.setattr("engine.acquisition.shutil.which", lambda name: "/usr/bin/dd" if name == "dd" else None)
    monkeypatch.setattr("engine.acquisition.subprocess.run", lambda *_args, **_kwargs: destination.write_bytes(b"altered"))

    with pytest.raises(IntegrityVerificationError):
        acquire_image(source, destination, operator_name="Investigator A", preferred_tool="dd")

    manifest = json.loads((tmp_path / "evidence.img.acquisition.json").read_text(encoding="utf-8"))
    assert manifest["integrity_status"] == "integrity_mismatch"
    assert manifest["source_sha256"] != manifest["image_sha256"]


def test_acquisition_refuses_existing_destination(monkeypatch, tmp_path):
    source = tmp_path / "source.bin"
    destination = tmp_path / "evidence.img"
    source.write_bytes(b"source")
    destination.write_bytes(b"existing")
    monkeypatch.setattr("engine.acquisition.shutil.which", lambda _name: "/usr/bin/dd")

    with pytest.raises(AcquisitionError, match="Destination already exists"):
        acquire_image(source, destination, operator_name="Investigator A")


def test_missing_imager_has_actionable_error(monkeypatch, tmp_path):
    source = tmp_path / "source.bin"
    source.write_bytes(b"source")
    monkeypatch.setattr("engine.acquisition.shutil.which", lambda _name: None)

    with pytest.raises(AcquisitionError, match="install an agency-approved, validated imager"):
        acquire_image(source, tmp_path / "evidence.img", operator_name="Investigator A")
