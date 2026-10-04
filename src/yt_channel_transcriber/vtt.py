from __future__ import annotations

import re

from .models import Segment


def timestamp_to_seconds(value: str) -> float:
    raw = value.strip().replace(",", ".")
    parts = raw.split(":")
    if len(parts) not in (2, 3):
        raise ValueError(f"Invalid VTT timestamp: {value}")
    try:
        if len(parts) == 3:
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = float(parts[2])
        else:
            hours = 0
            minutes = int(parts[0])
            seconds = float(parts[1])
    except ValueError as exc:
        raise ValueError(f"Invalid VTT timestamp: {value}") from exc
    return hours * 3600 + minutes * 60 + seconds


def parse_vtt(text: str) -> list[Segment]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    segments: list[Segment] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if "-->" not in line:
            i += 1
            continue
        start_raw, end_part = [part.strip() for part in line.split("-->", 1)]
        end_raw = end_part.split()[0]
        try:
            start = timestamp_to_seconds(start_raw)
            end = timestamp_to_seconds(end_raw)
        except ValueError:
            i += 1
            continue
        i += 1
        payload: list[str] = []
        while i < len(lines) and lines[i].strip():
            clean = re.sub(r"<[^>]+>", "", lines[i]).strip()
            if clean and clean not in payload:
                payload.append(clean)
            i += 1
        text_value = " ".join(payload).strip()
        if text_value:
            segments.append(Segment(start=start, duration=max(0.0, end - start), text=text_value))
        i += 1
    return segments
