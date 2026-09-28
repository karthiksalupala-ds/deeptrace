"""Guarded CLI for raw forensic acquisition with hash verification.

This utility invokes an installed ``dc3dd`` or ``dd`` binary; it does not and
cannot make a source device read-only.  Use a validated hardware write-blocker
before invoking it against evidence media.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Literal

from .report import TOOL_VERSION


WRITE_BLOCKER_NOTICE = (
    "WRITE-BLOCKER WARNING: Hardware write-blocking is required for forensic "
    "acquisition. DeepTrace can verify hashes after copying but cannot enforce "
    "read-only access at the OS, cable, adapter, or device-controller level."
)


class AcquisitionError(RuntimeError):
    """An acquisition could not be started or completed safely."""


class IntegrityVerificationError(AcquisitionError):
    """The resulting image did not match a readable source-device hash."""


def sha256_file(path: str | Path) -> str:
    """Hash a file or readable device sequentially without loading it into memory."""
    digest = hashlib.sha256()
    with open(path, "rb", buffering=4 * 1024 * 1024) as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return dt.datetime.now(tz=dt.timezone.utc).isoformat()


def select_imager(preferred: Literal["auto", "dd", "dc3dd"] = "auto") -> tuple[str, str]:
    """Select an imager from PATH, preferring dc3dd for its forensic features."""
    candidates = ("dc3dd", "dd") if preferred == "auto" else (preferred,)
    for candidate in candidates:
        executable = shutil.which(candidate)
        if executable:
            return candidate, executable
    requested = "dc3dd or dd" if preferred == "auto" else preferred
    if os.name == "nt":
        raise AcquisitionError(
            f"No supported imager ({requested}) was found on PATH. Windows does not include "
            "dd or dc3dd by default; install an agency-approved, validated imager and add its "
            "installation directory to PATH before retrying."
        )
    raise AcquisitionError(f"No supported imager ({requested}) was found on PATH. Install a validated imager and retry.")


def _copy_command(executable: str, source: Path, destination: Path, block_size: str) -> list[str]:
    """Construct an argument-list invocation; source paths never pass through a shell."""
    return [
        executable,
        f"if={source}",
        f"of={destination}",
        f"bs={block_size}",
        "conv=noerror,sync",
    ]


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(manifest, output, indent=2, sort_keys=True)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())


def acquire_image(
    source: str | Path,
    destination: str | Path,
    *,
    operator_name: str,
    preferred_tool: Literal["auto", "dd", "dc3dd"] = "auto",
    block_size: str = "4M",
    manifest_path: str | Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Acquire a raw image and return its immutable-once-written manifest.

    If the source can be read by Python, its pre-acquisition SHA-256 must equal
    the destination SHA-256 or an :class:`IntegrityVerificationError` is raised.
    A source that is unreadable to Python is recorded honestly as unverified.
    """
    source_path = Path(source)
    destination_path = Path(destination)
    if not source_path.exists():
        raise AcquisitionError(f"Source device does not exist: {source_path}")
    if source_path.resolve() == destination_path.resolve():
        raise AcquisitionError("Source and destination must be different paths.")
    if destination_path.exists() and not force:
        raise AcquisitionError(f"Destination already exists: {destination_path}. Use --force to overwrite it.")

    resolved_manifest = Path(manifest_path) if manifest_path else Path(f"{destination_path}.acquisition.json")
    if resolved_manifest.exists():
        raise AcquisitionError(f"Manifest already exists: {resolved_manifest}. Choose --manifest with a new path.")

    tool_name, executable = select_imager(preferred_tool)
    started_at = _utc_now()
    source_hash: str | None = None
    source_hash_error: str | None = None
    try:
        source_hash = sha256_file(source_path)
    except OSError as exc:
        source_hash_error = str(exc)

    command = _copy_command(executable, source_path, destination_path, block_size)
    status = "copy_failed"
    destination_hash: str | None = None
    ended_at: str | None = None
    try:
        subprocess.run(command, check=True)
        destination_hash = sha256_file(destination_path)
        ended_at = _utc_now()
        status = "verified" if source_hash == destination_hash and source_hash else "unverified_source_unreadable"
        if source_hash and source_hash != destination_hash:
            status = "integrity_mismatch"
    except (OSError, subprocess.CalledProcessError) as exc:
        ended_at = _utc_now()
        status = "copy_failed"
        source_hash_error = source_hash_error or str(exc)

    destination_size = destination_path.stat().st_size if destination_path.exists() else None
    try:
        source_size = source_path.stat().st_size
    except OSError:
        source_size = None
    manifest: dict[str, Any] = {
        "manifest_version": 1,
        "tool": TOOL_VERSION,
        "imager": tool_name,
        "command": command,
        "source_device_identifier": str(source_path),
        "destination_image": str(destination_path),
        "source_size_bytes": source_size,
        "image_size_bytes": destination_size,
        "operator_name": operator_name,
        "started_at_utc": started_at,
        "ended_at_utc": ended_at,
        "source_sha256": source_hash,
        "image_sha256": destination_hash,
        "integrity_status": status,
        "source_hash_error": source_hash_error,
        "write_blocking_notice": WRITE_BLOCKER_NOTICE,
    }
    _write_manifest(resolved_manifest, manifest)

    if status == "integrity_mismatch":
        raise IntegrityVerificationError(
            f"SHA-256 mismatch. Acquisition output was retained and recorded in {resolved_manifest}."
        )
    if status == "copy_failed":
        raise AcquisitionError(f"Imager failed. Failure manifest written to {resolved_manifest}.")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Acquire a raw forensic image with dd/dc3dd and SHA-256 verification.",
        epilog=WRITE_BLOCKER_NOTICE,
    )
    parser.add_argument("source", help="Readable source device or source image path (for example /dev/sdX).")
    parser.add_argument("destination", help="New destination .img path.")
    parser.add_argument("--operator", required=True, help="Investigator or evidence-custodian name.")
    parser.add_argument("--tool", choices=("auto", "dd", "dc3dd"), default="auto", help="Imager selection (default: auto).")
    parser.add_argument("--block-size", default="4M", help="dd/dc3dd block size (default: 4M).")
    parser.add_argument("--manifest", help="New manifest JSON path (default: DESTINATION.img.acquisition.json).")
    parser.add_argument("--force", action="store_true", help="Allow overwriting an existing destination image.")
    args = parser.parse_args(argv)

    print(WRITE_BLOCKER_NOTICE, file=sys.stderr)
    try:
        manifest = acquire_image(
            args.source,
            args.destination,
            operator_name=args.operator,
            preferred_tool=args.tool,
            block_size=args.block_size,
            manifest_path=args.manifest,
            force=args.force,
        )
    except AcquisitionError as exc:
        print(f"ACQUISITION FAILED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
