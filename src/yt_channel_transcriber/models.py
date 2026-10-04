from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(slots=True)
class Video:
    video_id: str
    title: str
    url: str
    published_at: str | None = None
    duration: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Segment:
    start: float
    duration: float
    text: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TranscriptResult:
    video: Video
    status: str
    language: str | None = None
    language_code: str | None = None
    is_generated: bool | None = None
    provider: str | None = None
    error: str | None = None
    segments: list[Segment] | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["video"] = self.video.to_dict()
        return data
