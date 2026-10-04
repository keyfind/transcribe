from __future__ import annotations

import html
import json
from pathlib import Path

from .models import Segment, TranscriptResult
from .utils import safe_filename


def _srt_time(seconds: float) -> str:
    total_ms = max(0, round(seconds * 1000))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, ms = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def to_plain_text(segments: list[Segment]) -> str:
    return "\n".join(segment.text.strip() for segment in segments if segment.text.strip()) + "\n"


def to_srt(segments: list[Segment]) -> str:
    blocks: list[str] = []
    for index, segment in enumerate(segments, start=1):
        start = _srt_time(segment.start)
        end = _srt_time(segment.start + max(segment.duration, 0.001))
        blocks.append(f"{index}\n{start} --> {end}\n{html.unescape(segment.text).strip()}")
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def write_transcript_files(result: TranscriptResult, output_dir: Path, index: int) -> dict[str, str]:
    assert result.segments is not None
    stem = f"{index:02d}-{safe_filename(result.video.title)}-{result.video.video_id}"
    txt_name = f"{stem}.txt"
    srt_name = f"{stem}.srt"
    json_name = f"{stem}.json"

    (output_dir / txt_name).write_text(to_plain_text(result.segments), encoding="utf-8")
    (output_dir / srt_name).write_text(to_srt(result.segments), encoding="utf-8")
    payload = result.to_dict()
    (output_dir / json_name).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {"txt": txt_name, "srt": srt_name, "json": json_name}
