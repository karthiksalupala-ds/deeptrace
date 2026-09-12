"""Optional, explainable motion detection for recovered video clips."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def detect_motion(video_path: str, threshold: float = 18.0, sample_every: int = 3) -> dict[str, Any]:
    """Detect coarse motion using grayscale frame-difference intensity.

    This is motion detection only. It does not identify faces, objects, people,
    authenticity, or deepfakes.
    """
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
            if frame_index % sample_every:
                frame_index += 1
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if previous is not None:
                difference = cv2.absdiff(previous, gray)
                intensity = float(difference.mean())
                timestamp = frame_index / fps
                if intensity >= threshold:
                    if active_start is None:
                        active_start = timestamp
                    active_values.append(intensity)
                elif active_start is not None:
                    events.append({"start_sec": round(active_start, 2), "end_sec": round(timestamp, 2), "intensity": round(sum(active_values) / len(active_values), 2)})
                    active_start = None
                    active_values = []
            previous = gray
            frame_index += 1
        if active_start is not None:
            events.append({"start_sec": round(active_start, 2), "end_sec": round(frame_index / fps, 2), "intensity": round(sum(active_values) / len(active_values), 2)})
    finally:
        capture.release()
    return {"method": "grayscale frame difference", "threshold": threshold, "motion_events": events}
