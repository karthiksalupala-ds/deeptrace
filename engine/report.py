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
import logging
import os
from collections import Counter
from typing import Any, Optional

from .base_parser import BaseVendorParser, FrameRecord
from .mp4_writer import RecoveredFile
from .temporal_sequencer import FrameSequence, SequencingStats

TOOL_VERSION = "DeepTrace v0.1.0"
logger = logging.getLogger(__name__)


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
    prev_entry_hash: Optional[str] = None,
    validation_level: str = "full",
    parsing_notes: str | None = None,
    detection_method: str = "fixed_offsets",
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
            "signature_detection_method": detection_method,
            "fully_implemented": vendor_parser.is_fully_implemented(),
            "detection_confidence": "high" if vendor_parser.is_fully_implemented() else "medium",
        }
    else:
        device_ident = {
            "vendor_id": "unknown",
            "vendor_name": "Unknown",
            "signature_found_at_offset": None,
            "signature_detection_method": detection_method,
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
        "source": "scanned_frames",
        "recovery_rate_basis": "scanned_only",
        "expected_valid_frames": None,
        "expected_total_frames": len(all_frames),
        "expected_corrupted_frames": None,
        "expected_gaps": None,
        "actual_valid_recovered": len(valid_frames),
        "recovery_rate_pct": round(
            len(valid_frames) / len(all_frames) * 100, 2
        ) if all_frames else 0.0,
        "note": (
            "Recovery rate uses yielded frame records because no synthetic "
            "ground-truth sidecar is available."
        ),
    }
    if meta:
        expected_valid = meta.get("valid_frames", 0)
        expected_total = meta.get("total_frames", 0)
        actual_valid = len(valid_frames)
        rate = (actual_valid / expected_total * 100) if expected_total else 0.0
        recovery_rate_info = {
            "source": "synthetic_sidecar",
            "recovery_rate_basis": "ground_truth",
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

    logger.info(
        "Recovery rate: numerator=%d denominator=%d basis=%s rate_pct=%.2f",
        len(valid_frames),
        recovery_rate_info["expected_total_frames"],
        recovery_rate_info["recovery_rate_basis"],
        recovery_rate_info["recovery_rate_pct"],
    )

    recovery_stats = {
        "total_frames_scanned": len(all_frames),
        "valid_frames": len(valid_frames),
        "invalid_frames": len(invalid_frames),
        "invalid_by_rejection_reason": rejection_counts,
        "rejected_frames_by_reason": rejection_counts,
        "frames_in_sequences": seq_stats.frames_in_sequences,
        "frames_dropped_noise": seq_stats.frames_dropped_noise,
        "sequences_found": seq_stats.sequences_found,
        "gaps_detected": seq_stats.gaps_detected,
        "recovery_rate": recovery_rate_info,
        "validation_level": validation_level,
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
    custody_entry = {
        "source_image_sha256": sha256,
        "acquired_by": operator_name,
        "acquired_at": now_iso,
        "tool": TOOL_VERSION,
        "validation_level": validation_level,
        "parsing_notes": parsing_notes,
        "hash_algorithms": ["MD5", "SHA-256"],
        "processing_note": (
            "Source image was not modified during analysis. "
            "All operations were read-only on the source disk image."
        ),
        "prev_entry_hash": prev_entry_hash,
    }
    entry_hash = hashlib.sha256(
        json.dumps(custody_entry, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    report = {
        "tool": TOOL_VERSION,
        "generated_at": now_iso,
        "validation_level": validation_level,
        "parsing_notes": parsing_notes,
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
        "sequences": [
            {
                "vendor_id": sequence.vendor_id,
                "channel_id": sequence.channel_id,
                "frame_count": sequence.frame_count,
                "start_ts": sequence.start_ts_utc.isoformat(),
                "end_ts": sequence.end_ts_utc.isoformat(),
                "gap_count": sequence.gap_count,
                "gap_before": sequence.gap_before,
            }
            for sequence in sequences
        ],
        "chain_of_custody": {**custody_entry, "entry_hash": entry_hash},
        "section_65b_certificate": {
            "_note": "DRAFT CERTIFICATE — REQUIRES AUTHORIZED SIGNATORY",
            "certificate_type": "Section 65B, Indian Evidence Act 1872",
            "certifying_officer": operator_name,
            "device_description": f"{device_ident['vendor_name']} DVR/NVR",
            "source_image_sha256": sha256,
            "statement": (
                "DRAFT FACTUAL CONTENT FOR HUMAN REVIEW: the electronic records detailed "
                "in this report were extracted from the original digital storage media "
                f"using DeepTrace ({TOOL_VERSION}) in a read-only process. The source "
                "media was not modified during analysis. The lawful custodian must "
                "independently verify these facts and complete/sign any certificate. "
                "DeepTrace does not issue or sign a Section 65B certificate."
            ),
        },
    }
    return report


def save_report(report: dict[str, Any], output_path: str) -> None:
    """Write the report as pretty-printed JSON."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
