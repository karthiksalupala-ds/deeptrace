"""
base_parser.py — BaseVendorParser interface and shared data types.

All vendor plugins must subclass BaseVendorParser and implement:
  - detect(image_path) -> bool
  - parse_frames(image_path) -> list[FrameRecord]

Detection-only stubs should override is_fully_implemented() to return False
and raise NotImplementedError in parse_frames() with a clear message.
"""

from __future__ import annotations

import abc
import datetime
from typing import Optional, TypedDict, Iterator


from dataclasses import dataclass

@dataclass
class FrameRecord:
    """Normalized frame record emitted by every vendor parser."""
    offset: int                      # byte offset in the disk image
    vendor_id: str                   # e.g. "hikvision", "dahua"
    frame_type: int                  # raw type byte from header
    is_keyframe: bool                # True if this is an I-frame
    frame_size: int                  # total frame size in bytes (from header)
    payload_size: int                # actual H.264/H.265 payload bytes
    frame_number: int                # vendor-native frame / sequence counter
    channel_id: int                  # camera channel
    timestamp_raw: int               # vendor-native value (epoch, BCD, etc.)
    timestamp_utc: datetime.datetime # normalized to UTC datetime
    payload: bytes                   # raw H.264/H.265 NAL data
    checksum_valid: bool             # True if checksum passed (or N/A for vendor)
    valid: bool = True               # True if fully parsed and valid
    rejection_reason: Optional[str] = None # Reason if valid=False


class BaseVendorParser(abc.ABC):
    """
    Abstract base class for all DVR/NVR vendor parsers.

    Subclasses register themselves via VendorRegistry.register().
    Priority is determined by registration order — Hikvision and Dahua
    are always registered first since they are the most common formats.
    """

    # Override these in every subclass
    vendor_id: str = ""          # machine-readable, e.g. "hikvision"
    vendor_name: str = ""        # human-readable, e.g. "Hikvision"
    vendor_description: str = "" # one-sentence description for the UI

    def is_fully_implemented(self) -> bool:
        """
        Return True if parse_frames() is fully implemented and can
        recover real frames. Return False for detection-only stubs.

        UI and reports must never claim a vendor is "supported" unless
        this returns True.
        """
        return True

    @abc.abstractmethod
    def detect(self, image_path: str) -> tuple[bool, Optional[int]]:
        """
        Scan the disk image for this vendor's signature.

        Returns:
            (found, offset) where offset is the byte offset where the
            signature was found, or None if not found.
        """

    @abc.abstractmethod
    def parse_frames(self, image_path: str) -> Iterator[FrameRecord]:
        """
        Scan the entire disk image and return all parseable frames.

        For detection-only stubs, raise NotImplementedError with a
        descriptive message explaining the roadmap status.

        Args:
            image_path: absolute path to the raw disk image (.img)

        Returns:
            List of FrameRecord dicts, ordered by file offset.
        """
