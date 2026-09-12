"""
tests/test_hikvision_parser.py — Round-trip tests for the Hikvision parser.

Generate synthetic Hikvision images → scan → verify frame count, timestamps,
channel IDs, payloads match what was embedded.
"""

import datetime

import pytest

from engine.vendors.hikvision import HikvisionParser
from engine.synthetic_image_gen import (
    SyntheticImageGenerator,
    generate_hikvision_scenario,
)


BASE_TS = datetime.datetime(2025, 3, 1, 8, 0, 0, tzinfo=datetime.timezone.utc)


@pytest.fixture
def parser():
    return HikvisionParser()


class TestHikvisionDetect:

    def test_detects_signature_at_512(self, parser, tmp_path):
        gen = SyntheticImageGenerator()
        gen.add_manufacturer_signature("hikvision", offset=512)
        img = str(tmp_path / "hik.img")
        gen.write(img)
        found, offset = parser.detect(img)
        assert found is True
        assert offset == 512

    def test_detects_signature_at_1024(self, parser, tmp_path):
        gen = SyntheticImageGenerator()
        gen.add_manufacturer_signature("hikvision", offset=1024)
        img = str(tmp_path / "hik.img")
        gen.write(img)
        found, offset = parser.detect(img)
        assert found is True
        assert offset == 512  # detect() reads 1024 bytes starting at 512 → covers 1024

    def test_no_detection_on_empty(self, parser, tmp_path):
        gen = SyntheticImageGenerator()
        gen.add_noise(8192)
        img = str(tmp_path / "noise.img")
        gen.write(img)
        found, offset = parser.detect(img)
        assert found is False
        assert offset is None


class TestHikvisionParseFrames:

    def test_round_trip_frame_count(self, parser, tmp_path):
        """50 valid frames → parser recovers all 50 as valid."""
        gen = SyntheticImageGenerator()
        gen.add_manufacturer_signature("hikvision")
        for i in range(50):
            ts = BASE_TS + datetime.timedelta(seconds=i / 30.0)
            gen.add_hikvision_frame(channel=0, frame_number=i, timestamp=ts)
        img = str(tmp_path / "hik50.img")
        gen.write(img)

        frames = list(parser.parse_frames(img))
        valid = [f for f in frames if f.valid]
        assert len(valid) == 50

    def test_frame_timestamps_match(self, parser, tmp_path):
        """Timestamps in parsed frames must match embedded timestamps (within 1s)."""
        gen = SyntheticImageGenerator()
        gen.add_manufacturer_signature("hikvision")
        timestamps = []
        for i in range(10):
            ts = BASE_TS + datetime.timedelta(seconds=i)
            gen.add_hikvision_frame(frame_number=i, timestamp=ts)
            timestamps.append(ts)
        img = str(tmp_path / "hik_ts.img")
        gen.write(img)

        frames = [f for f in parser.parse_frames(img) if f.valid]
        assert len(frames) == 10
        for frame, expected_ts in zip(frames, timestamps):
            diff = abs((frame.timestamp_utc - expected_ts).total_seconds())
            assert diff < 1.0, f"Timestamp mismatch: got {frame.timestamp_utc}, expected {expected_ts}"

    def test_frame_numbers_sequential(self, parser, tmp_path):
        gen = SyntheticImageGenerator()
        gen.add_manufacturer_signature("hikvision")
        for i in range(20):
            gen.add_hikvision_frame(frame_number=i,
                                    timestamp=BASE_TS + datetime.timedelta(seconds=i))
        img = str(tmp_path / "hik_seq.img")
        gen.write(img)

        frames = [f for f in parser.parse_frames(img) if f.valid]
        numbers = [f.frame_number for f in frames]
        assert numbers == list(range(20))

    def test_keyframe_detection(self, parser, tmp_path):
        gen = SyntheticImageGenerator()
        gen.add_manufacturer_signature("hikvision")
        for i in range(20):
            gen.add_hikvision_frame(
                frame_number=i,
                timestamp=BASE_TS + datetime.timedelta(seconds=i),
                is_keyframe=(i % 10 == 0),
            )
        img = str(tmp_path / "hik_kf.img")
        gen.write(img)

        frames = [f for f in parser.parse_frames(img) if f.valid]
        keyframes = [f for f in frames if f.is_keyframe]
        assert len(keyframes) == 2

    def test_corrupted_frames_have_valid_false(self, parser, tmp_path):
        """Frames with zeroed headers must appear as valid=False with a rejection_reason."""
        gen = SyntheticImageGenerator()
        gen.add_manufacturer_signature("hikvision")
        # 5 valid + 5 corrupted
        for i in range(5):
            gen.add_hikvision_frame(frame_number=i,
                                    timestamp=BASE_TS + datetime.timedelta(seconds=i))
        for i in range(5, 10):
            gen.add_hikvision_frame(frame_number=i,
                                    timestamp=BASE_TS + datetime.timedelta(seconds=i),
                                    corrupt_header=True)
        img = str(tmp_path / "hik_corrupt.img")
        gen.write(img)

        frames = list(parser.parse_frames(img))
        valid = [f for f in frames if f.valid]
        invalid = [f for f in frames if not f.valid]
        assert len(valid) == 5, f"Expected 5 valid frames, got {len(valid)}"
        assert len(invalid) == 5
        assert all(f.rejection_reason is not None for f in invalid)

    def test_frames_with_gaps(self, parser, tmp_path):
        """Gaps (null regions) between frames should not break the scan."""
        gen = SyntheticImageGenerator()
        gen.add_manufacturer_signature("hikvision")
        gen.add_hikvision_frame(frame_number=0, timestamp=BASE_TS)
        gen.add_gap(8192)
        gen.add_hikvision_frame(frame_number=1,
                                 timestamp=BASE_TS + datetime.timedelta(seconds=10))
        gen.add_gap(4096)
        gen.add_hikvision_frame(frame_number=2,
                                 timestamp=BASE_TS + datetime.timedelta(seconds=20))
        img = str(tmp_path / "hik_gaps.img")
        gen.write(img)

        frames = [f for f in parser.parse_frames(img) if f.valid]
        assert len(frames) == 3

    def test_vendor_id_is_hikvision(self, parser, tmp_path):
        gen = SyntheticImageGenerator()
        gen.add_manufacturer_signature("hikvision")
        gen.add_hikvision_frame(frame_number=0, timestamp=BASE_TS)
        img = str(tmp_path / "hik_vid.img")
        gen.write(img)

        frames = [f for f in parser.parse_frames(img) if f.valid]
        assert all(f.vendor_id == "hikvision" for f in frames)

    def test_scenario_recovery_rate(self, tmp_path):
        """Scenario generator: valid frames must be >= (total - corrupted)."""
        img = str(tmp_path / "scenario.img")
        meta = generate_hikvision_scenario(img, num_frames=50, num_corrupted=5)
        frames = list(HikvisionParser().parse_frames(img))
        valid = [f for f in frames if f.valid]
        assert len(valid) >= meta["valid_frames"]
