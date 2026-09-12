"""
vendors/godrej.py — Godrej Security DVR/NVR parser.

Godrej Security Solutions (Godrej & Boyce Manufacturing Co., India) sells
DVR/NVR products under its security division. Published evidence:

  - Godrej's entry- and mid-range DVR/NVR product lines are widely
    documented in Indian security trade press as OEM'd from Hikvision
    (hardware and firmware, including file system format).
  - Godrej-branded units often carry the Hikvision embedded Linux firmware
    with cosmetic UI changes.
  - Source: Godrej product spec sheets, distributor listings (e.g.
    IndiaMART), and Indian security industry publications.
  - NOTE: Premium/enterprise Godrej Security products may use independent
    designs. This detection only applies to Hikvision-derived models.

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
        "Godrej Security Solutions (Godrej & Boyce, India) — entry/mid-range "
        "lines use Hikvision-derived file systems; full frame recovery via "
        "Hikvision parser delegation."
    )

    def __init__(self) -> None:
        super().__init__()
        self._hik_parser = HikvisionParser()

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
