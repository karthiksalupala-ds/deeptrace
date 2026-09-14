"""
vendors/cpplus.py — CP Plus DVR/NVR parser.

CP Plus (brand of Aditya Infotech Ltd., India) is the largest CCTV brand
in India by market share. Published evidence:

  - Public product branding alone does not establish that a CP Plus model uses
    the Dahua filesystem. The relationship remains an unvalidated hypothesis.
  - NOTE: This adapter is detect-only until a citable source and real image
    validate a specific model family.

Detection strategy:
  - Check for Dahua DHFS4.1 filesystem signature (shared FS on OEM units)
  - Additionally look for CP Plus OEM marker string b'CPPLUS' or b'CP_PLUS'
    embedded in manufacturer header (some firmware revisions include this)
  - If only Dahua signature found: detect() returns True with a caveat flag;
    parse_frames() delegates to DahuaParser

IMPORTANT: This parser's detect() may match on a pure Dahua image. The
registry runs Hikvision first, then Dahua, then CP Plus — so pure Dahua
images are claimed by DahuaParser before this parser is checked.
"""

from __future__ import annotations

import logging
import os
from typing import Optional, Iterator

from ..base_parser import BaseVendorParser, FrameRecord
from .dahua import DahuaParser, DAHUA_DETECT_SIGNATURE, DETECT_OFFSETS, DETECT_READ_SIZE

logger = logging.getLogger(__name__)

CPPLUS_MARKERS = [b"CPPLUS", b"CP_PLUS", b"CPPLUS@INDIA", b"ADINFOTECH"]


class CpPlusParser(BaseVendorParser):
    """
    CP Plus parser — detect() finds Dahua-derived CP Plus images;
    parse_frames() delegates entirely to DahuaParser.
    """

    vendor_id = "cpplus"
    vendor_name = "CP Plus"
    vendor_description = (
        "CP Plus (Aditya Infotech, India) — recorder marker detection with "
        "provisional Dahua delegation; real-image validation is still required."
    )

    def __init__(self) -> None:
        super().__init__()
        self._dahua_parser = DahuaParser()

    def is_fully_implemented(self) -> bool:
      """Return False until a real CP Plus image validates the delegation."""
      return False

    def detect(self, image_path: str) -> tuple[bool, Optional[int]]:
        """
        Detect CP Plus by looking for a CP Plus OEM marker string in the
        manufacturer header region. Falls back to Dahua DHFS4.1 signature
        if no explicit CP Plus marker is found (covers rebrand-only units).

        Note: In the registry, DahuaParser runs before CpPlusParser, so
        this parser only fires for images that DahuaParser didn't already
        claim — meaning images where DHFS4.1 is present but the Dahua
        parser was somehow not registered (unusual). In practice this
        catches CP Plus-marker images that don't carry the Dahua FS sig.
        """
        file_size = os.path.getsize(image_path)
        with open(image_path, "rb") as fh:
            for offset in DETECT_OFFSETS:
                if offset + DETECT_READ_SIZE > file_size:
                    continue
                fh.seek(offset)
                window = fh.read(DETECT_READ_SIZE)
                # Prefer explicit CP Plus OEM marker
                for marker in CPPLUS_MARKERS:
                    if marker in window:
                        logger.debug("CP Plus OEM marker '%s' found at offset %d", marker, offset)
                        return True, offset
                # Fall back: Dahua FS sig + assume CP Plus OEM unit
                if DAHUA_DETECT_SIGNATURE in window:
                    logger.debug("CP Plus: Dahua FS signature found (OEM assumed) at offset %d", offset)
                    return True, offset
        return False, None

    def parse_frames(self, image_path: str, strict: bool = True) -> Iterator[FrameRecord]:
        """
        Delegate to DahuaParser — same DHAV frame format on OEM units.
        Returned FrameRecords have vendor_id rewritten to 'cpplus'.
        """
        count = 0
        for frame in self._dahua_parser.parse_frames(image_path, strict=strict):
            frame.vendor_id = self.vendor_id
            yield frame
            count += 1
        logger.info("CP Plus: recovered %d frames (via Dahua parser delegation)", count)
