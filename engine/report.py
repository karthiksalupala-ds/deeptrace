"""
engine/report.py — JSON Forensic Report Builder.

Produces a JSON-serializable report dict with:
  - disk_metadata: path, size, SHA-256, vendor, processed_at
  - recovery_stats: total/valid/invalid frames (grouped by rejection_reason),
    recovery_rate vs ground truth (from .meta.json sidecar if available),
    sequences_found, gaps_detected
  - recovered_files: per-file hash manifest
  - chain_of_custody: seeded for Phase 5 Section 65B certificate
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
from collections import Counter
from typing import Any, Optional

from .base_parser import BaseVendorParser, FrameRecord
from .mp4_writer import RecoveredFile
from .temporal_sequencer import FrameSequence, SequencingStats

TOOL_VERSION = "DeepTrace v0.1.0"


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _md5_file(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_meta_json(image_path: str) -> Optional[dict]:
    """Load the .meta.json sidecar emitted by SyntheticImageGenerator, if present."""
    meta_path = image_path + ".meta.json"
    if os.path.exists(meta_path):
        try:
            with open(meta_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def build_report(
    image_path: str,
    vendor_parser: Optional[BaseVendorParser],
    signature_offset: Optional[int],
    all_frames: list[FrameRecord],
    sequences: list[FrameSequence],
    seq_stats: SequencingStats,
    recovered_files: list[RecoveredFile],
    operator_name: str = "DEEPTRACE_OPERATOR",
    case_number: str = "UNKNOWN_CASE",
) -> dict[str, Any]:
    """
    Assemble the full DeepTrace forensic JSON report.

    Args:
        image_path:       Absolute path to the source disk image.
        vendor_parser:    The matched parser instance (or None).
        signature_offset: Byte offset where the vendor signature was found.
        all_frames:       Every FrameRecord yielded by parse_frames() (valid + invalid).
        sequences:        Output of sequence_frames().
        seq_stats:        SequencingStats from sequence_frames().
        recovered_files:  List of RecoveredFile objects from mp4_writer.
        operator_name:    For chain-of-custody.
        case_number:      For chain-of-custody.
    """
    now_iso = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()

    # ── Disk metadata ──────────────────────────────────────────────────────────
    file_size = os.path.getsize(image_path)
    sha256 = _sha256_file(image_path)
    md5 = _md5_file(image_path)

    # ── Device identification ──────────────────────────────────────────────────
    if vendor_parser:
        device_ident = {
            "vendor_id": vendor_parser.vendor_id,
            "vendor_name": vendor_parser.vendor_name,
            "signature_found_at_offset": signature_offset,
            "fully_implemented": vendor_parser.is_fully_implemented(),
            "detection_confidence": "high" if vendor_parser.is_fully_implemented() else "medium",
        }
    else:
        device_ident = {
            "vendor_id": "unknown",
            "vendor_name": "Unknown",
            "signature_found_at_offset": None,
            "fully_implemented": False,
            "detection_confidence": "low",
        }

    # ── Recovery stats ────────────────────────────────────────────────────────
    valid_frames = [f for f in all_frames if f.valid]
    invalid_frames = [f for f in all_frames if not f.valid]

    # Group invalid frames by rejection_reason
    rejection_counts: dict[str, int] = Counter(
        f.rejection_reason or "unknown" for f in invalid_frames
    )

    # Recovery rate vs ground truth from sidecar (synthetic data only)
    meta = _load_meta_json(image_path)
    recovery_rate_info: dict[str, Any] = {
        "note": "Ground truth unavailable (real-world image — no .meta.json sidecar)."
    }
    if meta:
        expected_valid = meta.get("valid_frames", 0)
        expected_total = meta.get("total_frames", 0)
        actual_valid = len(valid_frames)
        rate = (actual_valid / expected_total * 100) if expected_total else 0.0
        recovery_rate_info = {
            "source": "synthetic_sidecar",
            "expected_valid_frames": expected_valid,
            "expected_total_frames": expected_total,
            "expected_corrupted_frames": meta.get("corrupted_frames", 0),
            "expected_gaps": meta.get("gaps_inserted", 0),
            "actual_valid_recovered": actual_valid,
            "recovery_rate_pct": round(rate, 2),
            "note": (
                "Recovery rate computed against synthetic ground truth from .meta.json. "
                "Real-world runs will not have this ground truth — use as demo metric only."
            ),
        }

    recovery_stats = {
        "total_frames_scanned": len(all_frames),
        "valid_frames": len(valid_frames),
        "invalid_frames": len(invalid_frames),
        "invalid_by_rejection_reason": rejection_counts,
        "frames_in_sequences": seq_stats.frames_in_sequences,
        "frames_dropped_noise": seq_stats.frames_dropped_noise,
        "sequences_found": seq_stats.sequences_found,
        "gaps_detected": seq_stats.gaps_detected,
        "recovery_rate": recovery_rate_info,
    }

    # ── Recovered files ────────────────────────────────────────────────────────
    recovered_file_list = [
        {
            "filename": rf.filename,
            "path": rf.path,
            "size_bytes": rf.size_bytes,
            "md5": rf.md5,
            "sha256": rf.sha256,
            "frame_count": rf.frame_count,
            "duration_seconds": rf.duration_seconds,
            "channel_id": rf.channel_id,
            "start_ts": rf.start_ts_utc_iso,
            "end_ts": rf.end_ts_utc_iso,
            "is_demo": rf.is_demo,
            "is_raw_fallback": rf.is_raw_fallback,
        }
        for rf in recovered_files
    ]

    # ── Assemble report ────────────────────────────────────────────────────────
    report = {
        "tool": TOOL_VERSION,
        "generated_at": now_iso,
        "case_metadata": {
            "case_number": case_number,
            "operator": operator_name,
        },
        "disk_metadata": {
            "filename": os.path.basename(image_path),
            "path": os.path.abspath(image_path),
            "size_bytes": file_size,
            "md5": md5,
            "sha256": sha256,
            "processed_at": now_iso,
        },
        "device_identification": device_ident,
        "recovery_stats": recovery_stats,
        "recovered_files": recovered_file_list,
        "chain_of_custody": {
            "source_image_sha256": sha256,
            "acquired_by": operator_name,
            "acquired_at": now_iso,
            "tool": TOOL_VERSION,
            "hash_algorithms": ["MD5", "SHA-256"],
            "processing_note": (
                "Source image was not modified during analysis. "
                "All operations were read-only on the source disk image."
            ),
        },
        "section_65b_certificate": {
            "_note": "DRAFT CERTIFICATE — REQUIRES AUTHORIZED SIGNATORY",
            "certificate_type": "Section 65B, Indian Evidence Act 1872",
            "certifying_officer": operator_name,
            "device_description": f"{device_ident['vendor_name']} DVR/NVR",
            "source_image_sha256": sha256,
            "statement": (
                "I hereby certify that the electronic records detailed in this report "
                "were extracted from the original digital storage media using DeepTrace "
                f"({TOOL_VERSION}) in a forensically sound manner. The source media was "
                "not altered during analysis. The extracted records are true and accurate "
                "representations of the data present on the original media."
            ),
        },
    }
    return report


def save_report(report: dict[str, Any], output_path: str) -> None:
    """Write the report as pretty-printed JSON."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
