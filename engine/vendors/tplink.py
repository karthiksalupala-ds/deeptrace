"""
vendors/tplink.py — TP-Link (VIGI / Tapo) detection-only stub.

TP-Link's VIGI product line is an official recorder family. This project did
not establish its raw storage filesystem or whether exported video containers
are sufficient for disk-level recovery.

Current status: DETECTION ONLY.
parse_frames() raises NotImplementedError — standard container extraction
requires a different approach (container parser rather than raw binary
frame scanner).

Detection: looks for TP-Link / VIGI / Tapo brand strings in the
           manufacturer header region.
           TODO(karthik): research whether VIGI NVR uses NFS/ext4 and
           whether standard forensic container tools suffice.
"""

from __future__ import annotations

import os
from typing import Optional, Iterator

from ..base_parser import BaseVendorParser, FrameRecord

TPLINK_MARKERS = [b"TP-LINK", b"TPLINK", b"VIGI", b"TAPO_NVR"]
DETECT_OFFSETS = [512, 1024, 2048]
DETECT_READ_SIZE = 1024


class TpLinkParser(BaseVendorParser):
    vendor_id = "tplink"
    vendor_name = "TP-Link VIGI"
    vendor_description = (
        "TP-Link VIGI/Tapo NVR — recorder marker detection only; raw storage "
        "format and container extraction require device samples."
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
                for marker in TPLINK_MARKERS:
                    if marker in window:
                        return True, offset
        return False, None

    def parse_frames(self, image_path: str) -> Iterator[FrameRecord]:
        raise NotImplementedError(
            "TP-Link VIGI file system parsing not yet implemented. "
            "VIGI NVRs appear to use standard Linux container formats rather "
            "than proprietary binary frames. Roadmap: add container-based extractor."
        )
