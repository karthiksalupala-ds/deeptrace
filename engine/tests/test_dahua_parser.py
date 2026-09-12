"""
tests/test_dahua_parser.py — Round-trip tests for the Dahua DHAV parser.

Focuses on:
  - Detection via DHFS4.1 signature
  - Round-trip frame count with dual-signature validation
  - Rejection of bad-footer frames (valid=False + rejection_reason)
  - Rejection of bad-checksum frames
  - Datetime decoding accuracy
"""

import datetime

import pytest

from engine.vendors.dahua import DahuaParser, _decode_dahua_datetime
from engine.synthetic_image_gen import (
    SyntheticImageGenerator,
    generate_dahua_scenario,
    _encode_dahua_datetime,
)

BASE_TS = datetime.datetime(2025, 6, 15, 14, 30, 0, tzinfo=datetime.timezone.utc)


@pytest.fixture
def parser():
    return DahuaParser()


class TestDahuaDetect:

    def test_detects_dhfs41_signature(self, parser, tmp_path):
        gen = SyntheticImageGenerator()
        gen.add_manufacturer_signature("dahua", offset=512)
        img = str(tmp_path / "dahua.img")
        gen.write(img)
        found, offset = parser.detect(img)
        assert found is True
        assert offset == 512

    def test_no_detection_on_random_data(self, parser, tmp_path):
        gen = SyntheticImageGenerator()
        gen.add_noise(8192)
        img = str(tmp_path / "noise.img")
        gen.write(img)
        found, _ = parser.detect(img)
        assert found is False


class TestDahuaParseFrames:

    def test_round_trip_frame_count(self, parser, tmp_path):
        gen = SyntheticImageGenerator()
        gen.add_manufacturer_signature("dahua")
        for i in range(40):
            ts = BASE_TS + datetime.timedelta(seconds=i / 25.0)
            gen.add_dahua_frame(channel=0, frame_number=i, timestamp=ts)
        img = str(tmp_path / "dahua40.img")
        gen.write(img)

        frames = [f for f in parser.parse_frames(img) if f.valid]
        assert len(frames) == 40

    def test_dual_signature_rejects_corrupt_footer(self, parser, tmp_path):
        """Frames with corrupted footers must appear as valid=False."""
        gen = SyntheticImageGenerator()
        gen.add_manufacturer_signature("dahua")
        # 3 valid frames
        for i in range(3):
            gen.add_dahua_frame(frame_number=i,
                                 timestamp=BASE_TS + datetime.timedelta(seconds=i))
        # 2 frames with corrupt footer
        for i in range(3, 5):
            gen.add_dahua_frame(frame_number=i,
                                 timestamp=BASE_TS + datetime.timedelta(seconds=i),
                                 corrupt_footer=True)
        img = str(tmp_path / "dahua_footer.img")
        gen.write(img)

        frames = list(parser.parse_frames(img))
        valid = [f for f in frames if f.valid]
        invalid = [f for f in frames if not f.valid]
        assert len(valid) == 3, f"Expected 3 valid frames, got {len(valid)}"
        assert len(invalid) == 2
        assert all(f.rejection_reason in ("footer_magic_mismatch", "footer_size_mismatch") for f in invalid)

    def test_dual_signature_rejects_corrupt_header(self, parser, tmp_path):
        """Frames with corrupt headers must be absent from valid frames."""
        gen = SyntheticImageGenerator()
        gen.add_manufacturer_signature("dahua")
        gen.add_dahua_frame(frame_number=0, timestamp=BASE_TS)
        gen.add_dahua_frame(frame_number=1, timestamp=BASE_TS + datetime.timedelta(seconds=1),
                             corrupt_header=True)
        gen.add_dahua_frame(frame_number=2, timestamp=BASE_TS + datetime.timedelta(seconds=2))
        img = str(tmp_path / "dahua_chdr.img")
        gen.write(img)

        frames = list(parser.parse_frames(img))
        valid = [f for f in frames if f.valid]
        invalid = [f for f in frames if not f.valid]
        assert len(valid) == 2
        assert len(invalid) == 1
        assert invalid[0].rejection_reason == "checksum_mismatch"

    def test_datetime_decodes_correctly(self):
        """Encode then decode a datetime — must round-trip within 1 second."""
        original = datetime.datetime(2025, 8, 20, 15, 45, 30,
                                     tzinfo=datetime.timezone.utc)
        encoded = _encode_dahua_datetime(original)
        decoded = _decode_dahua_datetime(encoded)
        diff = abs((decoded - original).total_seconds())
        assert diff < 1.0, f"Datetime round-trip error: {diff}s"

    def test_datetime_in_parsed_frames(self, parser, tmp_path):
        """Timestamps in parsed frames must match embedded values within 1s."""
        gen = SyntheticImageGenerator()
        gen.add_manufacturer_signature("dahua")
        timestamps = []
        for i in range(5):
            ts = BASE_TS + datetime.timedelta(seconds=i * 2)
            gen.add_dahua_frame(frame_number=i, timestamp=ts)
            timestamps.append(ts)
        img = str(tmp_path / "dahua_ts.img")
        gen.write(img)

        frames = [f for f in parser.parse_frames(img) if f.valid]
        assert len(frames) == 5
        for frame, expected in zip(frames, timestamps):
            diff = abs((frame.timestamp_utc - expected).total_seconds())
            assert diff < 1.0

    def test_checksum_valid_on_good_frames(self, parser, tmp_path):
        gen = SyntheticImageGenerator()
        gen.add_manufacturer_signature("dahua")
        for i in range(5):
            gen.add_dahua_frame(frame_number=i,
                                 timestamp=BASE_TS + datetime.timedelta(seconds=i))
        img = str(tmp_path / "dahua_chk.img")
        gen.write(img)

        frames = [f for f in parser.parse_frames(img) if f.valid]
        assert all(f.checksum_valid is True for f in frames)

    def test_vendor_id_is_dahua(self, parser, tmp_path):
        gen = SyntheticImageGenerator()
        gen.add_manufacturer_signature("dahua")
        gen.add_dahua_frame(frame_number=0, timestamp=BASE_TS)
        img = str(tmp_path / "dahua_vid.img")
        gen.write(img)

        frames = [f for f in parser.parse_frames(img) if f.valid]
        assert all(f.vendor_id == "dahua" for f in frames)

    def test_gaps_between_frames(self, parser, tmp_path):
        gen = SyntheticImageGenerator()
        gen.add_manufacturer_signature("dahua")
        gen.add_dahua_frame(frame_number=0, timestamp=BASE_TS)
        gen.add_gap(16384)
        gen.add_dahua_frame(frame_number=1, timestamp=BASE_TS + datetime.timedelta(seconds=30))
        gen.add_gap(8192)
        gen.add_dahua_frame(frame_number=2, timestamp=BASE_TS + datetime.timedelta(seconds=60))
        img = str(tmp_path / "dahua_gaps.img")
        gen.write(img)

        frames = [f for f in parser.parse_frames(img) if f.valid]
        assert len(frames) == 3

    def test_scenario_recovery_rate(self, tmp_path):
        img = str(tmp_path / "dahua_scenario.img")
        meta = generate_dahua_scenario(img, num_frames=40, num_corrupted=4)
        frames = list(DahuaParser().parse_frames(img))
        valid = [f for f in frames if f.valid]
        assert len(valid) >= meta["valid_frames"]
