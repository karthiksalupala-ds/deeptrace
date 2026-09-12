"""
vendors/hikvision.py — Full Hikvision DVR/NVR parser.

Frame format (fixed-offset binary struct, per MDPI 2025 paper):
  +0   4 bytes  magic       0x484B5649  ('HKVI')
  +4   1 byte   frame_type
  +5   3 bytes  reserved
  +8   4 bytes  frame_size  uint32 LE — total frame bytes incl. header
  +12  4 bytes  timestamp   uint32 LE — Unix epoch seconds
  +16  1 byte   channel_id
  +17  3 bytes  reserved
  +20  4 bytes  frame_number uint32 LE
  +24  ...      payload     H.264/H.265 NAL data, length = frame_size - 24

Manufacturer detection:
  Read 1024 bytes at each of offsets [512, 1024, 2048].
  Signature string: b'HIKVISION@HANGZHOU' anywhere in that window.

Source: MDPI Information 2025, 16(11), 983 — DOI 10.3390/info16110983
"""

from __future__ import annotations

import datetime
import logging
import os
import struct
from typing import Optional, Iterator

from ..base_parser import BaseVendorParser, FrameRecord

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

HIKVISION_SIGNATURE = b"HIKVISION@HANGZHOU"
HIKVISION_MAGIC = 0x484B5649           # 'HKVI' as uint32 LE → bytes b'\x49\x56\x4B\x48'
HIKVISION_MAGIC_BYTES = b"\x49\x56\x4B\x48"
HEADER_SIZE = 24                        # bytes before payload
DETECT_OFFSETS = [512, 1024, 2048]
DETECT_READ_SIZE = 1024

# Frame type → is_keyframe mapping
KEYFRAME_TYPES = {0x01}  # type 1 = I-frame in Hikvision encoding


class HikvisionParser(BaseVendorParser):
    """Full Hikvision DVR/NVR parser — detect() + parse_frames()."""

    vendor_id = "hikvision"
    vendor_name = "Hikvision"
    vendor_description = (
        "Hikvision (Hangzhou Hikvision Digital Technology Co., Ltd.) — "
        "world's largest CCTV manufacturer. Full frame recovery implemented."
    )

    # ── Detection ──────────────────────────────────────────────────────────────

    def detect(self, image_path: str) -> tuple[bool, Optional[int]]:
        """
        Check offsets 512, 1024, 2048 for HIKVISION@HANGZHOU signature.
        Returns (True, offset) on first match, else (False, None).
        """
        file_size = os.path.getsize(image_path)
        with open(image_path, "rb") as fh:
            for offset in DETECT_OFFSETS:
                if offset + DETECT_READ_SIZE > file_size:
                    continue
                fh.seek(offset)
                header_bytes = fh.read(DETECT_READ_SIZE)
                if HIKVISION_SIGNATURE in header_bytes:
                    return True, offset
        return False, None

    # ── Frame parsing ──────────────────────────────────────────────────────────

    def parse_frames(self, image_path: str) -> Iterator[FrameRecord]:
        """
        Scan the entire disk image for Hikvision frame magic bytes and
        yield each frame as a FrameRecord.

        Strategy: sliding scan for HIKVISION_MAGIC_BYTES, then attempt
        to parse the header at that location. Invalid/truncated frames
        are yielded with valid=False and a rejection_reason.
        """
        file_size = os.path.getsize(image_path)
        parsed_count = 0

        with open(image_path, "rb") as fh:
            data = fh.read()  # MVP: read entire image; TODO(karthik): chunked for multi-TB

        offset = 0
        while offset < len(data):
            # Fast scan: find next magic occurrence
            idx = data.find(HIKVISION_MAGIC_BYTES, offset)
            if idx == -1:
                break

            frame = self._parse_frame_at(data, idx, file_size)
            if frame is not None:
                yield frame
                parsed_count += 1
                if frame.valid and frame.frame_size > HEADER_SIZE:
                    offset = idx + frame.frame_size
                else:
                    offset = idx + len(HIKVISION_MAGIC_BYTES)
            else:
                offset = idx + len(HIKVISION_MAGIC_BYTES)

        logger.info("Hikvision: parsed %d frames from %s", parsed_count, image_path)

    def _parse_frame_at(
        self, data: bytes, offset: int, file_size: int
    ) -> Optional[FrameRecord]:
        """
        Parse a single Hikvision frame at the given byte offset.
        Returns FrameRecord with valid=False on validation failure.
        """
        # Create a base skeleton that we can return if parsing fails
        base_frame = FrameRecord(
            offset=offset,
            vendor_id=self.vendor_id,
            frame_type=0,
            is_keyframe=False,
            frame_size=0,
            payload_size=0,
            frame_number=0,
            channel_id=0,
            timestamp_raw=0,
            timestamp_utc=datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc),
            payload=b"",
            checksum_valid=True,
            valid=False,
            rejection_reason="unknown_error"
        )

        if offset + HEADER_SIZE > len(data):
            base_frame.rejection_reason = "truncated_header"
            return base_frame

        try:
            (
                magic,
                frame_type,
                _r1, _r2, _r3,
                frame_size,
                timestamp_raw,
                channel_id,
                _r4, _r5, _r6,
                frame_number,
            ) = struct.unpack_from("<I B BBB I I B BBB I", data, offset)
        except struct.error:
            base_frame.rejection_reason = "struct_unpack_error"
            return base_frame

        base_frame.frame_type = frame_type
        base_frame.is_keyframe = (frame_type in KEYFRAME_TYPES)
        base_frame.frame_number = frame_number
        base_frame.channel_id = channel_id
        base_frame.timestamp_raw = timestamp_raw
        
        try:
            base_frame.timestamp_utc = datetime.datetime.fromtimestamp(
                timestamp_raw, tz=datetime.timezone.utc
            )
        except (OSError, OverflowError, ValueError):
            pass

        if magic != HIKVISION_MAGIC:
            base_frame.rejection_reason = "magic_mismatch"
            return base_frame

        if frame_size <= HEADER_SIZE or offset + frame_size > len(data):
            base_frame.rejection_reason = "invalid_frame_size"
            return base_frame

        base_frame.frame_size = frame_size
        base_frame.payload_size = frame_size - HEADER_SIZE
        base_frame.payload = data[offset + HEADER_SIZE : offset + frame_size]
        base_frame.valid = True
        base_frame.rejection_reason = None
        return base_frame
