"""
vendors/godrej.py — Godrej Security DVR/NVR parser.

Godrej Security Solutions (Godrej & Boyce Manufacturing Co., India) sells
DVR/NVR products under its security division. Published evidence:

    - Public product branding and reseller listings do not establish that a
        Godrej model uses the Hikvision filesystem. The relationship remains an
        unvalidated hypothesis.
    - NOTE: This adapter is detect-only until a citable source and real image
        validate a specific model family.

Detection: look for HIKVISION@HANGZHOU signature (shared FS on OEM units)
           or explicit Godrej marker strings.
parse_frames(): delegates to HikvisionParser.
"""

from __future__ import annotations

import logging
import os
from typing import Optional, Iterator

from ..base_parser import BaseVendorParser, FrameRecord
from .hikvision import (
    HikvisionParser,
    HIKVISION_SIGNATURE,
    DETECT_OFFSETS,
    DETECT_READ_SIZE,
)

logger = logging.getLogger(__name__)

GODREJ_MARKERS = [b"GODREJ", b"GODREJ_SECURITY", b"GODREJSEC"]


class GodrejParser(BaseVendorParser):
    """
    Godrej Security parser — detect() identifies Hikvision-derived Godrej
    images; parse_frames() delegates to HikvisionParser.
    """

    vendor_id = "godrej"
    vendor_name = "Godrej Security"
    vendor_description = (
        "Godrej Security Solutions (Godrej & Boyce, India) — recorder marker "
        "detection with provisional Hikvision delegation; real-image validation "
        "is still required."
    )

    def __init__(self) -> None:
        super().__init__()
        self._hik_parser = HikvisionParser()

    def is_fully_implemented(self) -> bool:
        """Return False until a real Godrej image validates the delegation."""
        return False

    def detect(self, image_path: str) -> tuple[bool, Optional[int]]:
        file_size = os.path.getsize(image_path)
        with open(image_path, "rb") as fh:
            for offset in DETECT_OFFSETS:
                if offset + DETECT_READ_SIZE > file_size:
                    continue
                fh.seek(offset)
                window = fh.read(DETECT_READ_SIZE)
                for marker in GODREJ_MARKERS:
                    if marker in window:
                        return True, offset
                if HIKVISION_SIGNATURE in window:
                    return True, offset
        return False, None

    def parse_frames(self, image_path: str) -> Iterator[FrameRecord]:
        count = 0
        for frame in self._hik_parser.parse_frames(image_path):
            frame.vendor_id = self.vendor_id
            yield frame
            count += 1
        logger.info("Godrej: recovered %d frames (via Hikvision parser delegation)", count)
