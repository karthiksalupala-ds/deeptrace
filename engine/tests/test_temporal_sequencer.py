"""
engine/tests/test_temporal_sequencer.py — Tests for the Temporal Sequencer.
"""

import datetime

from engine.base_parser import FrameRecord
from engine.temporal_sequencer import sequence_frames


def _make_frame(ts_seconds: int, fn: int, channel: int = 0) -> FrameRecord:
    ts = datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc) + datetime.timedelta(seconds=ts_seconds)
    return FrameRecord(
        offset=0,
        vendor_id="test",
        frame_type=1,
        is_keyframe=True,
        frame_size=100,
        payload_size=80,
        frame_number=fn,
        channel_id=channel,
        timestamp_raw=0,
        timestamp_utc=ts,
        payload=b"test",
        checksum_valid=True,
        valid=True,
        rejection_reason=None,
    )


class TestTemporalSequencer:

    def test_single_continuous_sequence(self):
        frames = [_make_frame(i, i) for i in range(15)]
        seqs, stats = sequence_frames(frames, min_sequence_frames=5)
        
        assert len(seqs) == 1
        assert seqs[0].frame_count == 15
        assert seqs[0].gap_count == 0
        assert seqs[0].duration_seconds == 14.0
        assert stats.sequences_found == 1
        assert stats.frames_in_sequences == 15

    def test_gap_detection_on_time_jump(self):
        # 10 frames at 1 fps, then 30 sec gap, then 10 frames at 1 fps
        frames = [_make_frame(i, i) for i in range(10)]
        frames += [_make_frame(i + 40, i + 10) for i in range(10)]
        
        seqs, stats = sequence_frames(frames, min_sequence_frames=5)
        assert len(seqs) == 2
        assert seqs[0].frame_count == 10
        assert seqs[1].frame_count == 10
        
        # gap count is attached to the sequence following the gap (or closed gap)
        assert seqs[0].gap_count == 0
        assert seqs[0].gap_before is False
        assert seqs[1].gap_count == 0
        assert seqs[1].gap_before is True
        assert stats.gaps_detected == 1

    def test_gap_detection_on_frame_number_jump(self):
        # 10 frames, then fn jumps by 5 (but time only jumps by 1s — happens in some corruptions)
        frames = [_make_frame(i, i) for i in range(10)]
        frames += [_make_frame(i + 10, i + 15) for i in range(10)]
        
        seqs, stats = sequence_frames(frames, min_sequence_frames=5)
        assert len(seqs) == 2
        assert seqs[1].gap_before is True
        assert stats.gaps_detected == 1

    def test_separates_channels(self):
        # Interleaved frames from CH0 and CH1
        frames = []
        for i in range(15):
            frames.append(_make_frame(i, i, channel=0))
            frames.append(_make_frame(i, i, channel=1))
            
        seqs, stats = sequence_frames(frames, min_sequence_frames=5)
        assert len(seqs) == 2
        assert seqs[0].channel_id != seqs[1].channel_id
        assert seqs[0].frame_count == 15
        assert seqs[1].frame_count == 15

    def test_drops_short_sequences(self):
        # 3 frames, then gap, then 10 frames
        frames = [_make_frame(i, i) for i in range(3)]
        frames += [_make_frame(i + 10, i + 3) for i in range(10)]
        
        seqs, stats = sequence_frames(frames, min_sequence_frames=5)
        assert len(seqs) == 1
        assert seqs[0].frame_count == 10
        assert stats.frames_dropped_noise == 3
