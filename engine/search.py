"""Transparent metadata search over recovered evidence artifacts.

This is intentionally not OCR or an LLM: it matches query terms against the
indexed report metadata and supports simple camera/vendor/time expressions.
"""

from __future__ import annotations

import datetime
import re
from typing import Any


_TIME_PATTERN = re.compile(r"\b(?:after|before|from|at)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", re.IGNORECASE)
_CAMERA_PATTERN = re.compile(r"\b(?:camera|cam|channel|ch)\s*#?\s*(\d+)\b", re.IGNORECASE)
_STOP_WORDS = {"show", "me", "clips", "clip", "from", "after", "before", "at", "on", "the", "and", "with"}


def _parse_time(query: str) -> tuple[str | None, datetime.time | None]:
    match = _TIME_PATTERN.search(query)
    if not match:
        return None, None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridiem = (match.group(3) or "").lower()
    if meridiem:
        if hour == 12:
            hour = 0
        if meridiem == "pm":
            hour += 12
    if hour > 23 or minute > 59:
        return None, None
    return query[match.start() : match.end()], datetime.time(hour, minute)


def search_recovered_files(report: dict[str, Any], query: str) -> list[dict[str, Any]]:
    """Return report artifacts matching a simple, explainable natural-language query."""
    normalized = query.strip().lower()
    files = report.get("recovered_files", [])
    if not normalized:
        return files

    camera_match = _CAMERA_PATTERN.search(normalized)
    requested_camera = int(camera_match.group(1)) if camera_match else None
    time_phrase, requested_time = _parse_time(normalized)
    is_before = bool(time_phrase and time_phrase.lower().startswith("before"))
    vendor_terms = {vendor for vendor in ("hikvision", "dahua", "cpplus", "godrej") if vendor in normalized}
    ignored = _STOP_WORDS | {"camera", "cam", "channel", "ch", "mp4", "raw", "footage", "video"}
    terms = {
        term for term in re.findall(r"[a-z0-9]+", normalized)
        if term not in ignored and not term.isdigit() and not re.fullmatch(r"\d+(?:am|pm)", term)
    }

    matches = []
    for item in files:
        start = datetime.datetime.fromisoformat(item["start_ts"])
        end = datetime.datetime.fromisoformat(item["end_ts"])
        # The UI presents zero-based channels as human-facing camera numbers.
        camera_number = item.get("channel_id", 0) + 1
        if requested_camera is not None and requested_camera != camera_number and requested_camera != item.get("channel_id"):
            continue
        if requested_time is not None:
            boundary = start.timetz().replace(tzinfo=None)
            if is_before and boundary >= requested_time:
                continue
            if not is_before and boundary < requested_time:
                continue
        if vendor_terms and item.get("vendor_id", "").lower() not in vendor_terms:
            continue
        searchable = " ".join([
            item.get("filename", "").lower(),
            item.get("vendor_id", "").lower(),
            item.get("start_ts", "").lower(),
            item.get("end_ts", "").lower(),
            f"camera {camera_number} ch{item.get('channel_id', 0)}",
        ])
        if terms and not all(term in searchable for term in terms):
            continue
        matches.append(item)
    return matches
