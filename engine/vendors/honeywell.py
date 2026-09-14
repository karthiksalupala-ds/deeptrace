"""
vendors/honeywell.py — Honeywell Security detection-only stub.

Honeywell Security / MAXPRO is a recorder product family. The project
research notes reference CARVE as a lead for future Honeywell recovery, but
this pass did not verify a primary accessible copy or filesystem details.

Current status: DETECTION ONLY.
parse_frames() raises NotImplementedError — the CARVE paper approach
(PaddleOCR-based fragment matching + PRNU fingerprinting) is roadmap
for a future phase.

Detection: looks for Honeywell/MAXPRO header strings at canonical offsets.
           TODO(karthik): confirm exact signature bytes from CARVE paper
           supplementary materials or physical MAXPRO hardware.
"""

from __future__ import annotations

import os
from typing import Optional, Iterator

from ..base_parser import BaseVendorParser, FrameRecord

HONEYWELL_MARKERS = [b"HONEYWELL", b"MAXPRO", b"HW_DVR", b"HWELL"]
DETECT_OFFSETS = [512, 1024, 2048]
DETECT_READ_SIZE = 1024


class HoneywellParser(BaseVendorParser):
    vendor_id = "honeywell"
    vendor_name = "Honeywell Security"
    vendor_description = (
        "Honeywell Security / Resideo MAXPRO series — detection only; CARVE is "
        "a research lead and raw filesystem recovery is roadmap."
    )

    def is_fully_implemented(self) -> bool:
        return False

    def detect(self, image_path: str) -> tuple[bool, Optional[int]]:
        file_size = os.path.getsize(image_path)
        with open(image_path, "rb") as fh:
            for offset in DETECT_OFFSETS:
                if offset + DETECT_READ_SIZE > file_size:
                    continue
                fh.seek(offset)
                window = fh.read(DETECT_READ_SIZE)
                for marker in HONEYWELL_MARKERS:
                    if marker in window:
                        return True, offset
        return False, None

    def parse_frames(self, image_path: str, strict: bool = True) -> Iterator[FrameRecord]:
        raise NotImplementedError(
            "Honeywell MAXPRO file system parsing not yet implemented. "
            "See CARVE paper (Saheed et al.) for the required approach. Roadmap item."
        )
