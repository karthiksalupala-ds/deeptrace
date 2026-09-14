"""
engine/pipeline.py — End-to-End Recovery Pipeline.

Ties together device identification, frame parsing, temporal sequencing,
MP4 muxing, and JSON reporting into a single callable flow.
"""

import os
from typing import Any

from .registry import build_default_registry
from .temporal_sequencer import sequence_frames
from .mp4_writer import write_mp4, write_demo_mp4
from .report import build_report, save_report


def run_recovery(
    image_path: str,
    out_dir: str,
    generate_demo_mp4s: bool = False,
    operator_name: str = "DEEPTRACE_OPERATOR",
    case_number: str = "UNKNOWN_CASE",
    prev_entry_hash: str | None = None,
    strict: bool = True,
) -> dict[str, Any]:
    """
    Run the full Phase 1 + Phase 2 DeepTrace pipeline on a disk image.

    Args:
        image_path:         Path to the raw disk image (.img)
        out_dir:            Directory to write MP4s and report.json
        generate_demo_mp4s: If True, uses ffmpeg lavfi to write synthetic
                            demonstration MP4s (that actually play) rather
                            than raw recovered frame bytes.
        operator_name:      For chain-of-custody metadata
        case_number:        For case metadata

    Returns:
        The generated JSON report dictionary.
    """
    os.makedirs(out_dir, exist_ok=True)

    # 1. Identify manufacturer
    registry = build_default_registry()
    parser, detection = registry.detect_vendor_verbose(image_path)
    offset = detection.offset
    
    all_frames = []
    
    if parser:
        # 2. Parse frames (streams the entire file)
        # Note: We consume the iterator completely here because the sequencer
        # and reporter need to see all frames (valid and invalid) to build stats.
        # In a fully streaming memory-constrained environment, we might push
        # chunks through the sequencer instead.
        all_frames = list(parser.parse_frames(image_path, strict=strict))
    
    # 3. Sequence frames
    sequences, seq_stats = sequence_frames(
        frames=all_frames,
        tolerance_factor=2.0,
        min_sequence_frames=10,
    )

    # 4. Write sequences to MP4 (or demo video)
    recovered_files = []
    for seq in sequences:
        if generate_demo_mp4s:
            rf = write_demo_mp4(seq, out_dir)
        else:
            rf = write_mp4(seq, out_dir)
        
        if rf:
            recovered_files.append(rf)

    # 5. Build and save report
    report = build_report(
        image_path=image_path,
        vendor_parser=parser,
        signature_offset=offset,
        all_frames=all_frames,
        sequences=sequences,
        seq_stats=seq_stats,
        recovered_files=recovered_files,
        operator_name=operator_name,
        case_number=case_number,
        prev_entry_hash=prev_entry_hash,
        validation_level="full" if strict else "permissive",
        detection_method=detection.method,
        parsing_notes=(
            f"Manufacturer detected ({parser.vendor_name}) at offset {offset}. "
            "No valid frames extracted — possible firmware/frame-format variant not covered by current parser. Recommend manual hex inspection."
            if parser and not any(frame.valid for frame in all_frames)
            else None
        ),
    )
    
    report_path = os.path.join(out_dir, "report.json")
    save_report(report, report_path)

    return report


if __name__ == "__main__":
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description="DeepTrace End-to-End Pipeline")
    parser.add_argument("image_path", help="Path to raw disk image")
    parser.add_argument("out_dir", help="Output directory for MP4s and report")
    parser.add_argument("--demo", action="store_true", help="Generate playable demo MP4s")
    parser.add_argument("--permissive", action="store_true", help="Skip Dahua checksum validation and mark results permissive")
    args = parser.parse_args()

    print(f"Running recovery on {args.image_path} -> {args.out_dir}")
    report = run_recovery(args.image_path, args.out_dir, generate_demo_mp4s=args.demo, strict=not args.permissive)
    
    print("\nRecovery Summary:")
    print(f"  Device: {report['device_identification']['vendor_name']}")
    print(f"  Total Frames Scanned: {report['recovery_stats']['total_frames_scanned']}")
    print(f"  Valid Frames: {report['recovery_stats']['valid_frames']}")
    print(f"  Sequences Recovered: {report['recovery_stats']['sequences_found']}")
    print(f"  Gaps Detected: {report['recovery_stats']['gaps_detected']}")
    
    if "recovery_rate_pct" in report['recovery_stats']['recovery_rate']:
        print(f"  Recovery Rate (vs Ground Truth): {report['recovery_stats']['recovery_rate']['recovery_rate_pct']}%")
        
    print(f"\nSaved report to {os.path.join(args.out_dir, 'report.json')}")
