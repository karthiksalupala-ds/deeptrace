"""
engine/temporal_sequencer.py — Temporal Sequencing and Gap Detection.

Reconstructs the timeline of parsed video frames into contiguous video
sequences, detecting gaps (deleted / circular-buffer-fragmented regions)
using a running-median inter-frame interval heuristic.

Algorithm (per MDPI 2025 DOI 10.3390/info16110983, §3.3):
  1. Filter valid=True frames only; group by (vendor_id, channel_id).
  2. Sort each group chronologically (timestamp_utc, then frame_number).
  3. Compute running median of inter-frame Δt (sliding window of last 30
     intervals chosen to adapt quickly to variable-framerate recordings
     while remaining robust to isolated outliers).
  4. Walk the sorted list:
       - if Δt > tolerance_factor × median_interval → temporal gap
       - if Δframe_number > 2 (Dahua/vendors that carry frame numbers) → gap
       - if Δt < 0 → timestamp anomaly (out-of-order or corrupt) → gap
  5. On gap: close current_sequence if len ≥ min_sequence_frames, else
     discard as noise; start a new sequence.
  6. Return (sequences, stats).
"""

from __future__ import annotations

import datetime
import statistics
from dataclasses import dataclass, field
from typing import Sequence as Seq

from .base_parser import FrameRecord


@dataclass
class FrameSequence:
    vendor_id: str
    channel_id: int
    frames: list[FrameRecord]
    start_ts_utc: datetime.datetime
    end_ts_utc: datetime.datetime
    gap_count: int           # gaps detected *during* this sequence (internal resets)
    gap_before: bool = False # True if a gap was detected before this sequence started

    @property
    def frame_count(self) -> int:
        return len(self.frames)

    @property
    def duration_seconds(self) -> float:
        return (self.end_ts_utc - self.start_ts_utc).total_seconds()


@dataclass
class SequencingStats:
    total_frames_in: int
    valid_frames_in: int
    frames_in_sequences: int
    frames_dropped_noise: int   # valid frames in sequences < min_sequence_frames
    sequences_found: int
    gaps_detected: int


def sequence_frames(
    frames: Seq[FrameRecord],
    tolerance_factor: float = 2.0,
    min_sequence_frames: int = 10,
) -> tuple[list[FrameSequence], SequencingStats]:
    """
    Groups parsed frames into contiguous video sequences.

    Args:
        frames:               All FrameRecord objects (valid + invalid).
        tolerance_factor:     Gap threshold multiplier against median interval.
        min_sequence_frames:  Minimum frames to keep a sequence; shorter ones
                              are discarded as noise.

    Returns:
        (sequences, stats) tuple.
    """
    total_in = len(frames)
    valid_frames = [f for f in frames if f.valid]
    valid_in = len(valid_frames)

    if not valid_frames:
        return [], SequencingStats(
            total_frames_in=total_in,
            valid_frames_in=0,
            frames_in_sequences=0,
            frames_dropped_noise=0,
            sequences_found=0,
            gaps_detected=0,
        )

    # Group by (vendor, channel)
    groups: dict[tuple[str, int], list[FrameRecord]] = {}
    for f in valid_frames:
        key = (f.vendor_id, f.channel_id)
        groups.setdefault(key, []).append(f)

    sequences: list[FrameSequence] = []
    total_gaps = 0
    frames_dropped = 0
    frames_in_seqs = 0

    for (vendor_id, channel_id), group_frames in groups.items():
        group_frames.sort(key=lambda x: (x.timestamp_utc, x.frame_number))

        current_seq: list[FrameRecord] = []
        running_intervals: list[float] = []
        gap_before_next = False  # will be True for the next sequence after a gap

        for frame in group_frames:
            if not current_seq:
                current_seq.append(frame)
                continue

            prev_frame = current_seq[-1]
            dt = (frame.timestamp_utc - prev_frame.timestamp_utc).total_seconds()
            df = frame.frame_number - prev_frame.frame_number

            is_gap = False
            if dt < 0:
                # Timestamp going backwards — treat as gap
                is_gap = True
            else:
                if running_intervals:
                    median_dt = statistics.median(running_intervals[-30:])
                    if median_dt > 0 and dt > (tolerance_factor * median_dt):
                        is_gap = True
                # Frame-number gap (works for vendors that carry frame numbers)
                if df > 2:
                    is_gap = True

            if is_gap:
                total_gaps += 1
                if len(current_seq) >= min_sequence_frames:
                    sequences.append(
                        FrameSequence(
                            vendor_id=vendor_id,
                            channel_id=channel_id,
                            frames=current_seq,
                            start_ts_utc=current_seq[0].timestamp_utc,
                            end_ts_utc=current_seq[-1].timestamp_utc,
                            gap_count=0,
                            gap_before=gap_before_next,
                        )
                    )
                    frames_in_seqs += len(current_seq)
                else:
                    frames_dropped += len(current_seq)
                gap_before_next = True
                current_seq = [frame]
                running_intervals.clear()
            else:
                current_seq.append(frame)
                if dt > 0:
                    running_intervals.append(dt)

        # Close final sequence
        if len(current_seq) >= min_sequence_frames:
            sequences.append(
                FrameSequence(
                    vendor_id=vendor_id,
                    channel_id=channel_id,
                    frames=current_seq,
                    start_ts_utc=current_seq[0].timestamp_utc,
                    end_ts_utc=current_seq[-1].timestamp_utc,
                    gap_count=0,
                    gap_before=gap_before_next,
                )
            )
            frames_in_seqs += len(current_seq)
        else:
            frames_dropped += len(current_seq)

    sequences.sort(key=lambda s: s.start_ts_utc)

    stats = SequencingStats(
        total_frames_in=total_in,
        valid_frames_in=valid_in,
        frames_in_sequences=frames_in_seqs,
        frames_dropped_noise=frames_dropped,
        sequences_found=len(sequences),
        gaps_detected=total_gaps,
    )
    return sequences, stats
