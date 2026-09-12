"""
vendors/uniview.py — Uniview detection-only stub.

Uniview (Zhejiang Uniview Technologies Co., Ltd., Hangzhou, founded 2005)
is an independent Chinese CCTV manufacturer. While Uniview was originally
spun out of talent that worked in the broader Hangzhou surveillance
ecosystem, it uses its own proprietary DVR/NVR file system — NOT derived
from Hikvision or Dahua formats.

Current status: DETECTION ONLY.
parse_frames() raises NotImplementedError — Uniview file system parsing
is a roadmap item requiring access to physical Uniview hardware for
byte-level format research.

Detection: looks for b'UNIVIEW' or b'UNV' OEM header strings at canonical
           manufacturer offsets. Signature TBD from physical hardware
           analysis — placeholder strings used here.
           TODO(karthik): acquire a Uniview disk image to confirm signature bytes.
"""

from __future__ import annotations

import os
from typing import Optional, Iterator

from ..base_parser import BaseVendorParser, FrameRecord

UNIVIEW_MARKERS = [b"UNIVIEW", b"UNVTECH", b"UNV@HZ"]
DETECT_OFFSETS = [512, 1024, 2048]
DETECT_READ_SIZE = 1024


class UniviewParser(BaseVendorParser):
    vendor_id = "uniview"
    vendor_name = "Uniview"
    vendor_description = (
        "Uniview (Zhejiang Uniview Technologies, China) — independent "
        "manufacturer with proprietary file system. Detection only in MVP; "
        "deep parsing is roadmap."
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
                for marker in UNIVIEW_MARKERS:
                    if marker in window:
                        return True, offset
        return False, None

    def parse_frames(self, image_path: str) -> Iterator[FrameRecord]:
        raise NotImplementedError(
            "Uniview file system parsing is not yet implemented. "
            "Detection works; deep frame recovery requires physical hardware "
            "analysis to confirm the proprietary format. Roadmap item."
        )
