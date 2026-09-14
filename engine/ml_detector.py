"""Optional, explainable motion detection for recovered video clips."""

from __future__ import annotations

from typing import Any


class MotionDetector:
    """Detect coarse motion in one recovered clip when explicitly requested.

    This is motion detection only. It does not identify faces, objects, people,
    authenticity, or deepfakes.
    """
    def __init__(self, threshold: float = 1.0, sample_every: int = 3) -> None:
        self.threshold = threshold
        self.sample_every = max(1, sample_every)

    def detect(self, video_path: str) -> dict[str, Any]:
        try:
            import cv2
        except ImportError as exc:
            raise RuntimeError("OpenCV is not installed; motion detection is unavailable") from exc

        capture = cv2.VideoCapture(video_path)
        if not capture.isOpened():
            raise RuntimeError("Unable to open recovered video")
        fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
        previous = None
        events: list[dict[str, float]] = []
        active_start: float | None = None
        active_values: list[float] = []
        frame_index = 0
        try:
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                if frame_index % self.sample_every:
                    frame_index += 1
                    continue
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                if previous is not None:
                    difference = cv2.absdiff(previous, gray)
                    intensity = float(difference.mean())
                    timestamp = frame_index / fps
                    if intensity >= self.threshold:
                        if active_start is None:
                            active_start = timestamp
                        active_values.append(intensity)
                    elif active_start is not None:
                        events.append(self._event(active_start, timestamp, active_values))
                        active_start = None
                        active_values = []
                previous = gray
                frame_index += 1
            if active_start is not None:
                events.append(self._event(active_start, frame_index / fps, active_values))
        finally:
            capture.release()
        return {
            "method": "grayscale frame difference",
            "threshold": self.threshold,
            "motion_events": events,
            "summary": f"{len(events)} motion events detected",
        }

    @staticmethod
    def _event(start: float, end: float, values: list[float]) -> dict[str, float]:
        return {
            "start_sec": round(start, 2),
            "end_sec": round(end, 2),
            "intensity": round(sum(values) / len(values), 2),
        }


def detect_motion(video_path: str, threshold: float = 1.0, sample_every: int = 3) -> dict[str, Any]:
    """Compatibility wrapper for the on-demand motion detector."""
    return MotionDetector(threshold=threshold, sample_every=sample_every).detect(video_path)
