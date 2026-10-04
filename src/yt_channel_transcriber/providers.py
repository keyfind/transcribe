from __future__ import annotations

import os
import time
from dataclasses import dataclass
from urllib.parse import urljoin

import requests
from youtube_transcript_api import (
    IpBlocked,
    NoTranscriptFound,
    RequestBlocked,
    TranscriptsDisabled,
    VideoUnavailable,
    YouTubeTranscriptApi,
    YouTubeTranscriptApiException,
)

from .models import Segment, Video
from .vtt import parse_vtt

DEFAULT_INVIDIOUS_INSTANCES = [
    "https://inv.nadeko.net",
    "https://invidious.nerdvpn.de",
    "https://yt.chocolatemoo53.com",
    "https://invidious.tiekoetter.com",
    "https://invidious.f5.si",
]


class TranscriptUnavailable(Exception):
    pass


class TranscriptBlocked(Exception):
    pass


@dataclass(slots=True)
class ProviderTranscript:
    segments: list[Segment]
    language: str
    language_code: str
    is_generated: bool | None
    provider: str


class YouTubeTranscriptProvider:
    def __init__(self) -> None:
        self.api = YouTubeTranscriptApi()

    def fetch(self, video: Video, languages: list[str]) -> ProviderTranscript:
        try:
            available = list(self.api.list(video.video_id))
            if not available:
                raise TranscriptUnavailable("No transcript tracks are available")

            chosen = None
            for code in languages:
                chosen = next((t for t in available if t.language_code == code), None)
                if chosen:
                    break
            if chosen is None:
                chosen = min(available, key=lambda t: (t.is_generated, t.language_code))

            fetched = chosen.fetch()
            segments = [
                Segment(start=float(s.start), duration=float(s.duration), text=s.text)
                for s in fetched
                if s.text.strip()
            ]
            return ProviderTranscript(
                segments=segments,
                language=chosen.language,
                language_code=chosen.language_code,
                is_generated=chosen.is_generated,
                provider="youtube-transcript-api",
            )
        except (IpBlocked, RequestBlocked) as exc:
            raise TranscriptBlocked(str(exc)) from exc
        except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable) as exc:
            raise TranscriptUnavailable(str(exc)) from exc
        except YouTubeTranscriptApiException as exc:
            raise TranscriptBlocked(str(exc)) from exc



class InvidiousTranscriptProvider:
    def __init__(self, instances: list[str] | None = None) -> None:
        configured = os.getenv("INVIDIOUS_INSTANCES", "").strip()
        self.instances = (
            [x.strip().rstrip("/") for x in configured.split(",") if x.strip()]
            if configured
            else (instances or DEFAULT_INVIDIOUS_INSTANCES)
        )
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "yt-channel-transcriber/0.1"})

    def fetch(self, video: Video, languages: list[str]) -> ProviderTranscript:
        errors: list[str] = []
        for base in self.instances:
            try:
                listing = self.session.get(
                    f"{base}/api/v1/captions/{video.video_id}", timeout=15
                )
                if listing.status_code == 404:
                    continue
                listing.raise_for_status()
                captions = listing.json().get("captions", [])
                if not captions:
                    continue

                chosen = None
                for code in languages:
                    chosen = next(
                        (c for c in captions if c.get("languageCode") == code), None
                    )
                    if chosen:
                        break
                chosen = chosen or captions[0]
                caption_url = urljoin(base + "/", str(chosen["url"]).lstrip("/"))
                response = self.session.get(caption_url, timeout=20)
                response.raise_for_status()
                segments = parse_vtt(response.text)
                if not segments:
                    raise RuntimeError("caption response contained no cues")
                return ProviderTranscript(
                    segments=segments,
                    language=str(chosen.get("label") or chosen.get("languageCode") or "unknown"),
                    language_code=str(chosen.get("languageCode") or "und"),
                    is_generated=None,
                    provider=f"invidious:{base}",
                )
            except (requests.RequestException, ValueError, KeyError, RuntimeError) as exc:
                errors.append(f"{base}: {exc}")
                time.sleep(0.3)
        if errors:
            raise TranscriptBlocked("; ".join(errors[-3:]))
        raise TranscriptUnavailable("No captions found on Invidious fallbacks")


class FallbackTranscriptProvider:
    def __init__(self) -> None:
        self.direct = YouTubeTranscriptProvider()
        self.invidious = InvidiousTranscriptProvider()

    def fetch(self, video: Video, languages: list[str]) -> ProviderTranscript:
        try:
            return self.direct.fetch(video, languages)
        except TranscriptUnavailable:
            raise
        except TranscriptBlocked as direct_error:
            try:
                return self.invidious.fetch(video, languages)
            except (TranscriptUnavailable, TranscriptBlocked) as fallback_error:
                raise TranscriptBlocked(
                    f"Direct provider failed: {direct_error}; fallback failed: {fallback_error}"
                ) from fallback_error
