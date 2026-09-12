"""
engine/tests/test_report.py — Tests for the JSON report generator.
"""

import datetime
import os

from engine.vendors.hikvision import HikvisionParser
from engine.report import build_report
from engine.mp4_writer import RecoveredFile
from engine.temporal_sequencer import FrameSequence, SequencingStats
from engine.base_parser import FrameRecord


def test_build_report(tmp_path):
    ts = datetime.datetime.now(tz=datetime.timezone.utc)
    
    # Create a dummy image file
    image_path = tmp_path / "image.img"
    image_path.write_bytes(b"0" * 10000)
    
    seq = FrameSequence(
        vendor_id="hikvision",
        channel_id=0,
        frames=[],
        start_ts_utc=ts,
        end_ts_utc=ts + datetime.timedelta(seconds=10),
        gap_count=2,
        gap_before=False
    )
    
    dummy_frame = FrameRecord(
        offset=0, vendor_id="hikvision", frame_type=1, is_keyframe=False,
        frame_size=100, payload_size=80, frame_number=0, channel_id=0,
        timestamp_raw=0, timestamp_utc=ts, payload=b"", checksum_valid=True,
        valid=True, rejection_reason=None,
    )
    seq.frames = [dummy_frame] * 50
    
    rec_file = RecoveredFile(
        path="/tmp/test.mp4",
        filename="test.mp4",
        size_bytes=1024,
        md5="d41d8cd98f00b204e9800998ecf8427e",
        sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        frame_count=50,
        duration_seconds=10.0,
        vendor_id="hikvision",
        channel_id=0,
        start_ts_utc_iso=ts.isoformat(),
        end_ts_utc_iso=(ts + datetime.timedelta(seconds=10)).isoformat(),
        is_demo=False,
        is_raw_fallback=False,
    )
    
    parser = HikvisionParser()
    
    seq_stats = SequencingStats(
        total_frames_in=50,
        valid_frames_in=50,
        frames_in_sequences=50,
        frames_dropped_noise=0,
        sequences_found=1,
        gaps_detected=2
    )
    
    report = build_report(
        image_path=str(image_path),
        vendor_parser=parser,
        signature_offset=512,
        all_frames=seq.frames,
        sequences=[seq],
        seq_stats=seq_stats,
        recovered_files=[rec_file],
        operator_name="TEST_OP",
        case_number="CASE_001"
    )
    
    assert report["case_metadata"]["operator"] == "TEST_OP"
    assert report["case_metadata"]["case_number"] == "CASE_001"
    assert report["device_identification"]["vendor_id"] == "hikvision"
    assert report["device_identification"]["signature_found_at_offset"] == 512
    assert report["recovery_stats"]["valid_frames"] == 50
    assert report["recovery_stats"]["gaps_detected"] == 2
    assert report["recovery_stats"]["sequences_found"] == 1
    assert len(report["recovered_files"]) == 1
    assert report["recovered_files"][0]["md5"] == "d41d8cd98f00b204e9800998ecf8427e"
    assert "section_65b_certificate" in report
