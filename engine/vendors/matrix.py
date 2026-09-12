"""
vendors/matrix.py — Matrix COSEC detection-only stub.

Matrix Comsec's official site presents its own enterprise video-surveillance
and NVR products. This project did not establish the raw filesystem or an OEM
relationship for those products.

Current status: DETECTION ONLY.
parse_frames() raises NotImplementedError — Matrix COSEC file system
format is undocumented in published research; physical hardware analysis
is required.

Detection: looks for MATRIX / COSEC brand strings at canonical offsets.
           TODO(karthik): contact Matrix Comsec for technical documentation
           or acquire a COSEC disk image for byte-level format research.
"""

from __future__ import annotations

import os
from typing import Optional, Iterator

from ..base_parser import BaseVendorParser, FrameRecord

MATRIX_MARKERS = [b"MATRIX", b"COSEC", b"MATRIXCOMSEC", b"MATRIX_DVR"]
DETECT_OFFSETS = [512, 1024, 2048]
DETECT_READ_SIZE = 1024


class MatrixParser(BaseVendorParser):
    vendor_id = "matrix"
    vendor_name = "Matrix COSEC"
    vendor_description = (
        "Matrix Comsec (Vadodara, India) COSEC DVR/NVR — recorder marker "
        "detection only; raw filesystem is undocumented here and requires "
        "hardware access."
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
                for marker in MATRIX_MARKERS:
                    if marker in window:
                        return True, offset
        return False, None

    def parse_frames(self, image_path: str) -> Iterator[FrameRecord]:
        raise NotImplementedError(
            "Matrix COSEC file system parsing not yet implemented. "
            "Format is proprietary and undocumented. Roadmap: acquire hardware "
            "for byte-level format research."
        )
