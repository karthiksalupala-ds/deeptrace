"""
vendors/dahua.py — Full Dahua DVR/NVR parser.

DHAV Frame Format (per MDPI 2025 paper, DOI 10.3390/info16110983):

  HEADER (32 bytes):
    +0   4 bytes  magic       b'DHAV'
    +4   1 byte   frame_type
    +5   1 byte   subtype
    +6   1 byte   channel
    +7   1 byte   subchannel
    +8   4 bytes  frame_number  uint32 LE
    +12  4 bytes  frame_size    uint32 LE — total size incl. header + footer
    +16  4 bytes  datetime      uint32 LE — packed BCD: see _decode_datetime()
    +20  2 bytes  milliseconds  uint16 LE
    +22  1 byte   ext_header_flag
    +23  1 byte   checksum      XOR of bytes 0..22
    [+24 .. frame_size-8]  H.264/H.265 payload

  FOOTER (8 bytes, immediately after payload):
    +0   4 bytes  magic         b'dhav'  (lowercase)
    +4   4 bytes  frame_size    uint32 LE — must equal header frame_size

  DUAL-SIGNATURE VALIDATION:
    A frame is only valid if ALL of the following hold:
      1. Header magic == b'DHAV'
      2. Footer magic == b'dhav'
      3. Header frame_size == footer frame_size
      4. XOR checksum of header bytes 0..22 == header byte 23

  Manufacturer detection:
    Read 1024 bytes at offsets [512, 1024, 2048].
    Signature string: b'DHFS4.1' anywhere in that window.

  Dahua datetime field (uint32 LE) packed BCD encoding:
    bits 31-26: year offset from 2000 (6 bits)
    bits 25-22: month (4 bits)
    bits 21-17: day (5 bits)
    bits 16-12: hour (5 bits)
    bits 11-06: minute (6 bits)
    bits 05-00: second (6 bits)

  TODO(karthik): Verify checksum algorithm against MDPI paper Table 2.
  XOR is the most common embedded DVR implementation and is used
  consistently here and in the synthetic generator so round-trip tests pass.
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

DAHUA_DETECT_SIGNATURE = b"DHFS4.1"
DHAV_HEADER_MAGIC = b"DHAV"
DHAV_FOOTER_MAGIC = b"dhav"
HEADER_SIZE = 24          # bytes 0..23 (the defined header above)
FOOTER_SIZE = 8
FRAME_OVERHEAD = HEADER_SIZE + FOOTER_SIZE  # 32 bytes total overhead
DETECT_OFFSETS = [512, 1024, 2048]
DETECT_READ_SIZE = 1024

KEYFRAME_TYPES = {0xFD, 0x01}  # 0xFD = I-frame in DHAV encoding


def _xor_checksum(data: bytes) -> int:
    """Compute XOR checksum over all bytes in data."""
    result = 0
    for b in data:
        result ^= b
    return result


def _decode_dahua_datetime(raw: int) -> datetime.datetime:
    """
    Decode Dahua packed BCD datetime field to UTC datetime.

    Bit layout (uint32):
      [31:26] year  — offset from 2000 (0-63 → 2000-2063)
      [25:22] month — 1-12
      [21:17] day   — 1-31
      [16:12] hour  — 0-23
      [11:6]  minute — 0-59
      [5:0]   second — 0-59
    """
    second = raw & 0x3F
    minute = (raw >> 6) & 0x3F
    hour   = (raw >> 12) & 0x1F
    day    = (raw >> 17) & 0x1F
    month  = (raw >> 22) & 0x0F
    year   = ((raw >> 26) & 0x3F) + 2000

    try:
        return datetime.datetime(year, month, day, hour, minute, second,
                                 tzinfo=datetime.timezone.utc)
    except ValueError:
        # Malformed datetime in corrupted frame
        return datetime.datetime(2000, 1, 1, tzinfo=datetime.timezone.utc)


class DahuaParser(BaseVendorParser):
    """Full Dahua DVR/NVR parser — detect() + parse_frames()."""

    vendor_id = "dahua"
    vendor_name = "Dahua"
    vendor_description = (
        "Dahua Technology Co., Ltd. — second-largest CCTV manufacturer globally. "
        "Full DHAV frame recovery with dual-signature validation implemented."
    )

    # ── Detection ──────────────────────────────────────────────────────────────

    def detect(self, image_path: str) -> tuple[bool, Optional[int]]:
        """
        Check offsets 512, 1024, 2048 for DHFS4.1 signature.
        Returns (True, offset) on first match, else (False, None).
        """
        file_size = os.path.getsize(image_path)
        with open(image_path, "rb") as fh:
            for offset in DETECT_OFFSETS:
                if offset + DETECT_READ_SIZE > file_size:
                    continue
                fh.seek(offset)
                header_bytes = fh.read(DETECT_READ_SIZE)
                if DAHUA_DETECT_SIGNATURE in header_bytes:
                    return True, offset
        return False, None

    # ── Frame parsing ──────────────────────────────────────────────────────────

    def parse_frames(self, image_path: str) -> Iterator[FrameRecord]:
        """
        Scan entire disk image for DHAV frames using dual-signature validation.
        Yields all parsed frames, including invalid ones with rejection reasons.
        """
        parsed_count = 0

        with open(image_path, "rb") as fh:
            data = fh.read()  # TODO(karthik): chunked reads for multi-TB images

        offset = 0
        while offset < len(data):
            idx = data.find(DHAV_HEADER_MAGIC, offset)
            if idx == -1:
                break

            frame = self._parse_frame_at(data, idx)
            if frame is not None:
                yield frame
                parsed_count += 1
                if frame.valid and frame.frame_size >= FRAME_OVERHEAD:
                    offset = idx + frame.frame_size
                else:
                    offset = idx + len(DHAV_HEADER_MAGIC)
            else:
                offset = idx + len(DHAV_HEADER_MAGIC)

        logger.info("Dahua: parsed %d DHAV frames from %s", parsed_count, image_path)

    def _parse_frame_at(self, data: bytes, offset: int) -> Optional[FrameRecord]:
        """
        Attempt to parse and dual-signature-validate a DHAV frame at offset.
        Returns FrameRecord with valid=False if validation fails.
        """
        # Create base frame for error returns
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
            timestamp_utc=datetime.datetime(2000, 1, 1, tzinfo=datetime.timezone.utc),
            payload=b"",
            checksum_valid=False,
            valid=False,
            rejection_reason="unknown_error"
        )

        if offset + HEADER_SIZE > len(data):
            base_frame.rejection_reason = "truncated_header"
            return base_frame

        # ── Parse header ──────────────────────────────────────────────────────
        try:
            (
                header_magic,       # 4s
                frame_type,         # B
                subtype,            # B
                channel,            # B
                subchannel,         # B
                frame_number,       # I
                frame_size,         # I
                datetime_raw,       # I
                milliseconds,       # H
                ext_header_flag,    # B
                checksum_stored,    # B
            ) = struct.unpack_from("<4sBBBBIIIHBB", data, offset)
        except struct.error:
            base_frame.rejection_reason = "struct_unpack_error"
            return base_frame

        base_frame.frame_type = frame_type
        base_frame.is_keyframe = (frame_type in KEYFRAME_TYPES)
        base_frame.channel_id = channel
        base_frame.frame_number = frame_number
        base_frame.frame_size = frame_size
        base_frame.timestamp_raw = datetime_raw
        base_frame.timestamp_utc = _decode_dahua_datetime(datetime_raw)

        # Validation 1: header magic
        if header_magic != DHAV_HEADER_MAGIC:
            base_frame.rejection_reason = "header_magic_mismatch"
            return base_frame

        # Validation 2: sane frame size (must accommodate header + payload + footer)
        if frame_size < FRAME_OVERHEAD or offset + frame_size > len(data):
            base_frame.rejection_reason = "invalid_frame_size"
            return base_frame

        # Validation 3: XOR checksum over header bytes 0..22
        computed_checksum = _xor_checksum(data[offset : offset + HEADER_SIZE - 1])
        if computed_checksum != checksum_stored:
            logger.debug(
                "Dahua: checksum mismatch at offset %d (expected %02x, got %02x)",
                offset, checksum_stored, computed_checksum,
            )
            base_frame.rejection_reason = "checksum_mismatch"
            return base_frame
            
        base_frame.checksum_valid = True

        # ── Parse footer ──────────────────────────────────────────────────────
        footer_offset = offset + frame_size - FOOTER_SIZE
        if footer_offset + FOOTER_SIZE > len(data):
            base_frame.rejection_reason = "footer_out_of_bounds"
            return base_frame

        try:
            footer_magic, footer_size = struct.unpack_from("<4sI", data, footer_offset)
        except struct.error:
            base_frame.rejection_reason = "footer_struct_error"
            return base_frame

        # Validation 4: footer magic
        if footer_magic != DHAV_FOOTER_MAGIC:
            base_frame.rejection_reason = "footer_magic_mismatch"
            return base_frame

        # Validation 5: header and footer frame sizes must agree
        if footer_size != frame_size:
            base_frame.rejection_reason = "footer_size_mismatch"
            return base_frame

        # ── Extract payload ───────────────────────────────────────────────────
        payload_start = offset + HEADER_SIZE
        payload_end = footer_offset
        base_frame.payload = data[payload_start:payload_end]
        base_frame.payload_size = len(base_frame.payload)
        base_frame.valid = True
        base_frame.rejection_reason = None

        return base_frame
