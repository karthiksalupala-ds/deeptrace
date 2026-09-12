"""
synthetic_image_gen.py — Generates spec-accurate synthetic DVR/NVR disk images.

Produces raw binary .img files that embed correctly-formatted Hikvision and
Dahua frames (with deliberate corruption/fragmentation/gaps) for testing the
recovery engine without real seized hardware.

This is the standard, defensible approach for a forensic-tool hackathon
demo: "recovery engine validated against spec-accurate synthetic disk images;
ready to be pointed at real seized drives."

The PS-required "DVR/NVR Forensic Image" deliverable IS this synthetic
image set.
"""

from __future__ import annotations

import datetime
import io
import os
import random
import struct
import time
from dataclasses import dataclass, field
from typing import Literal

# ── Hikvision constants ────────────────────────────────────────────────────────
HIKVISION_SIGNATURE = b"HIKVISION@HANGZHOU"
HIKVISION_MAGIC = b"\x49\x56\x4B\x48"   # 0x484B5649 in LE
HIK_HEADER_SIZE = 24
HIK_SIGNATURE_OFFSET = 512

# ── Dahua constants ────────────────────────────────────────────────────────────
DAHUA_DETECT_SIGNATURE = b"DHFS4.1"
DHAV_HEADER_MAGIC = b"DHAV"
DHAV_FOOTER_MAGIC = b"dhav"
DAHUA_HEADER_SIZE = 24
DAHUA_FOOTER_SIZE = 8
DAHUA_FRAME_OVERHEAD = DAHUA_HEADER_SIZE + DAHUA_FOOTER_SIZE
DAHUA_SIGNATURE_OFFSET = 512

# ── Vendor OEM markers ─────────────────────────────────────────────────────────
OEM_MARKERS = {
    "cpplus": b"CPPLUS@INDIA",
    "godrej": b"GODREJ_SECURITY",
    "uniview": b"UNIVIEW",
    "honeywell": b"MAXPRO",
    "tplink": b"VIGI",
    "matrix": b"COSEC",
}

VendorId = Literal["hikvision", "dahua", "cpplus", "godrej", "uniview",
                   "honeywell", "tplink", "matrix"]


# ── Minimal synthetic H.264 NAL payload ───────────────────────────────────────
def _make_h264_nal(is_keyframe: bool = False, size: int = 256) -> bytes:
    """
    Return a minimal but structurally plausible H.264 NAL unit.
    Not a valid decodable frame — only used for pipeline testing.
    NAL start code: 0x00000001, then NAL header byte, then filler.
    """
    nal_type = 5 if is_keyframe else 1  # 5=IDR, 1=non-IDR
    start_code = b"\x00\x00\x00\x01"
    nal_header = bytes([0x60 | nal_type])  # forbidden_zero=0, nal_ref_idc=3
    payload_filler = bytes(
        [(i ^ 0xAB) & 0xFF for i in range(size - len(start_code) - 1)]
    )
    return start_code + nal_header + payload_filler


# ── Dahua datetime encoder ─────────────────────────────────────────────────────
def _encode_dahua_datetime(dt: datetime.datetime) -> int:
    """
    Pack a datetime into Dahua's uint32 format.
    Must be the inverse of dahua.py's _decode_dahua_datetime().
    """
    year_offset = dt.year - 2000
    return (
        (year_offset & 0x3F) << 26
        | (dt.month & 0x0F) << 22
        | (dt.day & 0x1F) << 17
        | (dt.hour & 0x1F) << 12
        | (dt.minute & 0x3F) << 6
        | (dt.second & 0x3F)
    )


def _xor_checksum(data: bytes) -> int:
    result = 0
    for b in data:
        result ^= b
    return result


@dataclass
class FrameSpec:
    """Specification for a single synthetic frame."""
    vendor_id: VendorId
    channel: int = 0
    frame_number: int = 0
    timestamp: datetime.datetime = field(
        default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc)
    )
    is_keyframe: bool = False
    payload_size: int = 256
    corrupt_header: bool = False   # zero out header bytes to simulate deletion
    corrupt_payload: bool = False  # randomize payload bytes


class SyntheticImageGenerator:
    """
    Builds a raw binary disk image blob with embedded DVR frame data.

    Usage:
        gen = SyntheticImageGenerator()
        gen.add_manufacturer_signature("hikvision")
        for i in range(50):
            gen.add_hikvision_frame(channel=0, frame_number=i, ...)
        gen.write("sample_data/test_hikvision.img")
    """

    def __init__(self) -> None:
        self._buf = io.BytesIO()
        # Pre-fill first 4096 bytes with zeros (simulates MBR / partition table region)
        self._buf.write(b"\x00" * 4096)
        # Ground-truth tracking for .meta.json sidecar
        self._meta: dict = {
            "vendor": "unknown",
            "total_frames": 0,
            "valid_frames": 0,
            "corrupted_frames": 0,
            "gaps_inserted": 0,
        }

    # ── Manufacturer signature ─────────────────────────────────────────────────

    def add_manufacturer_signature(
        self, vendor_id: VendorId, offset: int = 512
    ) -> None:
        """
        Write the vendor's filesystem identification signature at the
        given offset (default 512, the first canonical check offset).
        Also writes OEM marker for delegation vendors.
        """
        current_pos = self._buf.tell()

        # Build a 1024-byte header block
        header = bytearray(1024)

        if vendor_id == "hikvision" or vendor_id == "godrej":
            sig = HIKVISION_SIGNATURE
            oem = OEM_MARKERS.get(vendor_id, b"")
            header[0:len(sig)] = sig
            if oem:
                header[len(sig)+2:len(sig)+2+len(oem)] = oem
        elif vendor_id in ("dahua", "cpplus"):
            sig = DAHUA_DETECT_SIGNATURE
            oem = OEM_MARKERS.get(vendor_id, b"")
            header[0:len(sig)] = sig
            if oem:
                header[len(sig)+2:len(sig)+2+len(oem)] = oem
        else:
            # Stub vendors — write their OEM marker
            oem = OEM_MARKERS.get(vendor_id, vendor_id.upper().encode())
            header[0:len(oem)] = oem

        # Seek to offset and write
        self._buf.seek(offset)
        self._buf.write(bytes(header))

        # Restore / advance position
        end = offset + 1024
        if end > current_pos:
            self._buf.seek(end)
        else:
            self._buf.seek(current_pos)

    # ── Hikvision frame builder ────────────────────────────────────────────────

    def add_hikvision_frame(
        self,
        channel: int = 0,
        frame_number: int = 0,
        timestamp: datetime.datetime | None = None,
        is_keyframe: bool = False,
        payload_size: int = 256,
        corrupt_header: bool = False,
    ) -> int:
        """
        Write a single Hikvision frame and return its byte offset.

        Frame layout (24-byte header + payload):
          +0   I  magic = 0x484B5649
          +4   B  frame_type
          +5   BBB reserved
          +8   I  frame_size  (uint32 LE)
          +12  I  timestamp   (Unix epoch, uint32 LE)
          +16  B  channel_id
          +17  BBB reserved
          +20  I  frame_number (uint32 LE)
          +24  ... payload
        """
        if timestamp is None:
            timestamp = datetime.datetime.now(tz=datetime.timezone.utc)

        payload = _make_h264_nal(is_keyframe=is_keyframe, size=payload_size)
        frame_size = HIK_HEADER_SIZE + len(payload)
        frame_type = 0x01 if is_keyframe else 0x02
        ts_raw = int(timestamp.timestamp())

        header = struct.pack(
            "<I B BBB I I B BBB I",
            0x484B5649,   # magic
            frame_type,
            0, 0, 0,      # reserved
            frame_size,
            ts_raw,
            channel & 0xFF,
            0, 0, 0,      # reserved
            frame_number,
        )

        if corrupt_header:
            # Corrupt frame size to fail validation, leaving magic intact
            header = header[:8] + b"\x00\x00\x00\x00" + header[12:]

        offset = self._buf.tell()
        self._buf.write(header + payload)
        return offset

    # ── Dahua DHAV frame builder ───────────────────────────────────────────────

    def add_dahua_frame(
        self,
        channel: int = 0,
        subchannel: int = 0,
        frame_number: int = 0,
        timestamp: datetime.datetime | None = None,
        is_keyframe: bool = False,
        payload_size: int = 256,
        corrupt_header: bool = False,
        corrupt_footer: bool = False,
    ) -> int:
        """
        Write a single DHAV frame with header + payload + footer.
        Returns its byte offset in the image.
        """
        if timestamp is None:
            timestamp = datetime.datetime.now(tz=datetime.timezone.utc)

        payload = _make_h264_nal(is_keyframe=is_keyframe, size=payload_size)
        frame_type = 0xFD if is_keyframe else 0x01
        subtype = 0x00
        frame_size = DAHUA_FRAME_OVERHEAD + len(payload)
        datetime_raw = _encode_dahua_datetime(timestamp)
        ms = 0
        ext_header_flag = 0

        # Build header bytes 0..22 for checksum, then append checksum byte
        header_no_checksum = struct.pack(
            "<4sBBBBIIIHBB",
            DHAV_HEADER_MAGIC,
            frame_type,
            subtype,
            channel & 0xFF,
            subchannel & 0xFF,
            frame_number,
            frame_size,
            datetime_raw,
            ms,
            ext_header_flag,
            0,  # checksum placeholder
        )
        checksum = _xor_checksum(header_no_checksum[:-1])  # XOR of first 23 bytes
        header = header_no_checksum[:-1] + bytes([checksum])

        footer = struct.pack("<4sI", DHAV_FOOTER_MAGIC, frame_size)

        if corrupt_header:
            # Corrupt checksum to fail validation
            header = header[:-1] + bytes([(header[-1] + 1) % 256])
        if corrupt_footer:
            # Corrupt footer frame size
            footer = footer[:4] + b"\x00\x00\x00\x00"

        offset = self._buf.tell()
        self._buf.write(header + payload + footer)
        return offset

    # ── Gap / padding helpers ──────────────────────────────────────────────────

    def add_gap(self, size_bytes: int = 4096) -> None:
        """Insert null bytes simulating deleted/unallocated disk region."""
        self._buf.write(b"\x00" * size_bytes)

    def add_noise(self, size_bytes: int = 512) -> None:
        """Insert random bytes simulating bit rot / unrelated data."""
        self._buf.write(bytes(random.randint(0, 255) for _ in range(size_bytes)))

    def corrupt_bytes_at(self, offset: int, count: int = 16) -> None:
        """Overwrite `count` bytes at `offset` with random data."""
        current = self._buf.tell()
        self._buf.seek(offset)
        self._buf.write(bytes(random.randint(0, 255) for _ in range(count)))
        self._buf.seek(current)

    # ── Write output ───────────────────────────────────────────────────────────

    def write(self, path: str) -> str:
        """Write the generated image to disk. Also emits a .meta.json sidecar."""
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        data = self._buf.getvalue()
        with open(path, "wb") as fh:
            fh.write(data)
        # Emit ground-truth sidecar for use by report.py recovery rate calculation
        meta_path = path + ".meta.json"
        with open(meta_path, "w", encoding="utf-8") as fh:
            import json as _json
            _json.dump(self._meta, fh, indent=2)
        return os.path.abspath(path)

    def getvalue(self) -> bytes:
        """Return raw bytes (for in-memory use without writing to disk)."""
        return self._buf.getvalue()

    def size(self) -> int:
        return self._buf.tell()


# ── Pre-built scenario generators ─────────────────────────────────────────────

def generate_hikvision_scenario(
    path: str,
    num_frames: int = 50,
    num_corrupted: int = 5,
    num_gaps: int = 3,
    base_timestamp: datetime.datetime | None = None,
) -> dict:
    """
    Generate a realistic Hikvision scenario:
    - Manufacturer signature at offset 512
    - num_frames frames at ~30fps spacing
    - num_corrupted frames with zeroed headers (simulates deletion)
    - num_gaps large null regions (simulates unallocated space / fragmentation)

    Returns metadata dict for use in validation reports.
    """
    if base_timestamp is None:
        base_timestamp = datetime.datetime(2025, 1, 15, 10, 0, 0,
                                           tzinfo=datetime.timezone.utc)

    gen = SyntheticImageGenerator()
    gen.add_manufacturer_signature("hikvision")
    gen.add_gap(512)  # padding before first frame

    frames_written = []
    gap_offsets = sorted(random.sample(range(num_frames), min(num_gaps, num_frames)))
    corrupt_indices = set(random.sample(range(num_frames), min(num_corrupted, num_frames)))

    for i in range(num_frames):
        ts = base_timestamp + datetime.timedelta(seconds=i / 30.0)
        is_keyframe = (i % 10 == 0)
        corrupt = (i in corrupt_indices)

        # Insert gap before some frames
        if i in gap_offsets:
            gen.add_gap(8192)

        offset = gen.add_hikvision_frame(
            channel=0,
            frame_number=i,
            timestamp=ts,
            is_keyframe=is_keyframe,
            payload_size=random.randint(200, 512),
            corrupt_header=corrupt,
        )
        frames_written.append({"index": i, "offset": offset, "corrupted": corrupt})

    gen.add_gap(1024)
    gen._meta = {
        "vendor": "hikvision",
        "total_frames": num_frames,
        "valid_frames": num_frames - num_corrupted,
        "corrupted_frames": num_corrupted,
        "gaps_inserted": num_gaps,
    }
    gen.write(path)

    return {
        "vendor": "hikvision",
        "path": path,
        "total_frames": num_frames,
        "valid_frames": num_frames - num_corrupted,
        "corrupted_frames": num_corrupted,
        "gaps_inserted": num_gaps,
        "frames": frames_written,
    }


def generate_dahua_scenario(
    path: str,
    num_frames: int = 50,
    num_corrupted: int = 5,
    num_gaps: int = 3,
    base_timestamp: datetime.datetime | None = None,
) -> dict:
    """
    Generate a realistic Dahua scenario with DHAV frames.
    num_corrupted frames will have zeroed headers (fail dual-sig validation).
    """
    if base_timestamp is None:
        base_timestamp = datetime.datetime(2025, 1, 15, 10, 0, 0,
                                           tzinfo=datetime.timezone.utc)

    gen = SyntheticImageGenerator()
    gen.add_manufacturer_signature("dahua")
    gen.add_gap(512)

    frames_written = []
    gap_offsets = sorted(random.sample(range(num_frames), min(num_gaps, num_frames)))
    corrupt_indices = set(random.sample(range(num_frames), min(num_corrupted, num_frames)))

    for i in range(num_frames):
        ts = base_timestamp + datetime.timedelta(seconds=i / 25.0)
        is_keyframe = (i % 8 == 0)
        corrupt = (i in corrupt_indices)

        if i in gap_offsets:
            gen.add_gap(8192)

        c_head = corrupt and (i % 2 == 0)
        c_foot = corrupt and (i % 2 != 0)

        offset = gen.add_dahua_frame(
            channel=0,
            frame_number=i,
            timestamp=ts,
            is_keyframe=is_keyframe,
            payload_size=random.randint(200, 512),
            corrupt_header=c_head,
            corrupt_footer=c_foot,
        )
        frames_written.append({"index": i, "offset": offset, "corrupted": corrupt})

    gen.add_gap(1024)
    gen._meta = {
        "vendor": "dahua",
        "total_frames": num_frames,
        "valid_frames": num_frames - num_corrupted,
        "corrupted_frames": num_corrupted,
        "gaps_inserted": num_gaps,
    }
    gen.write(path)

    return {
        "vendor": "dahua",
        "path": path,
        "total_frames": num_frames,
        "valid_frames": num_frames - num_corrupted,
        "corrupted_frames": num_corrupted,
        "gaps_inserted": num_gaps,
        "frames": frames_written,
    }


def generate_mixed_corruption_scenario(path: str, vendor: VendorId = "hikvision") -> dict:
    """
    Heavy corruption scenario: 50% corrupted frames, many gaps, noise regions.
    Used for stress-testing the recovery engine.
    """
    return (generate_hikvision_scenario if vendor == "hikvision"
            else generate_dahua_scenario)(
        path=path,
        num_frames=60,
        num_corrupted=30,
        num_gaps=8,
    )


def generate_hikvision_image(path: str, num_frames: int = 200, corruption_rate: float = 0.05, fragmentation: bool = True) -> dict:
    num_corrupted = int(num_frames * corruption_rate)
    num_gaps = max(3, int(num_frames * 0.1)) if fragmentation else 0
    return generate_hikvision_scenario(path, num_frames=num_frames, num_corrupted=num_corrupted, num_gaps=num_gaps)


def generate_dahua_image(path: str, num_frames: int = 200, corruption_rate: float = 0.05, fragmentation: bool = True) -> dict:
    num_corrupted = int(num_frames * corruption_rate)
    num_gaps = max(3, int(num_frames * 0.1)) if fragmentation else 0
    return generate_dahua_scenario(path, num_frames=num_frames, num_corrupted=num_corrupted, num_gaps=num_gaps)


def generate_image(vendor_id: str, path: str, **kwargs) -> dict:
    if vendor_id == "hikvision":
        return generate_hikvision_image(path, **kwargs)
    elif vendor_id == "dahua":
        return generate_dahua_image(path, **kwargs)
    else:
        raise NotImplementedError(f"Generator for {vendor_id} not implemented")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate synthetic forensic image")
    parser.add_argument("--manufacturer", required=True, help="Vendor ID (e.g. hikvision, dahua)")
    parser.add_argument("--out", required=True, help="Output path")
    parser.add_argument("--frames", type=int, default=200, help="Number of frames to generate")
    parser.add_argument("--corruption_rate", type=float, default=0.05, help="Fraction of frames to corrupt")
    parser.add_argument("--no-fragmentation", action="store_false", dest="fragmentation", help="Disable fragmentation/gaps")
    args = parser.parse_args()

    print(f"Generating {args.manufacturer} image at {args.out}...")
    meta = generate_image(args.manufacturer, args.out, num_frames=args.frames, corruption_rate=args.corruption_rate, fragmentation=args.fragmentation)
    print(f"Done. Generated {meta['total_frames']} frames ({meta['corrupted_frames']} corrupted, {meta['gaps_inserted']} gaps).")

