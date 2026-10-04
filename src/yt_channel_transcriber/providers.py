from __future__ import annotations

import base64
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urljoin

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
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from .models import Segment, Video
from .vtt import parse_vtt

DEFAULT_INVIDIOUS_INSTANCES = [
    "https://inv.nadeko.net",
    "https://invidious.nerdvpn.de",
    "https://yt.chocolatemoo53.com",
    "https://invidious.tiekoetter.com",
    "https://invidious.f5.si",
]


DEFAULT_PIPED_INSTANCES = [
    "https://pipedapi.kavin.rocks",
    "https://pipedapi-libre.kavin.rocks",
    "https://pipedapi.adminforge.de",
    "https://api.piped.yt",
    "https://api.piped.private.coffee",
    "https://pipedapi.leptons.xyz",
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


class InnerTubeTranscriptPanelProvider:
    ENDPOINT = "https://www.youtube.com/youtubei/v1/get_transcript"
    CLIENTS = (
        {
            "name": "WEB",
            "id": "1",
            "version": "2.20260722.01.00",
            "key": None,
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
            ),
            "extra": {
                "clientScreen": "WATCH_FULL_SCREEN",
                "osName": "Windows",
                "osVersion": "10.0",
                "platform": "DESKTOP",
            },
        },
        {
            "name": "ANDROID",
            "id": "3",
            "version": "20.10.38",
            "key": "AIzaSyA8eiZmM1FaDVjRy-df2KTyQ_vz_yYM39w",
            "user_agent": "com.google.android.youtube/20.10.38 (Linux; U; Android 11) gzip",
            "extra": {"osName": "Android", "osVersion": "11"},
        },
        {
            "name": "IOS",
            "id": "5",
            "version": "19.45.4",
            "key": "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8",
            "user_agent": (
                "com.google.ios.youtube/19.45.4 "
                "(iPhone16,2; U; CPU iOS 18_1_0 like Mac OS X;)"
            ),
            "extra": {"deviceModel": "iPhone16,2", "osName": "iPhone", "osVersion": "18.1.0"},
        },
    )

    @staticmethod
    def _params(video_id: str, language_code: str) -> str:
        inner = b"\n\x03asr\x12\x02" + language_code.encode() + b"\x1a\x00"
        encoded_language = base64.urlsafe_b64encode(inner)
        panel = b"engagement-panel-searchable-transcript-search-panel"
        outer = (
            b"\n\x0b"
            + video_id.encode()
            + b"\x12\x10"
            + encoded_language
            + b"\x18\x01"
            + b"\x2a\x33"
            + panel
            + b"\x30\x01\x38\x01\x40\x01"
        )
        encoded_outer = base64.urlsafe_b64encode(outer).decode()
        return quote(encoded_outer, safe="")

    @staticmethod
    def _text(value: dict[str, Any]) -> str:
        if value.get("simpleText"):
            return str(value["simpleText"]).strip()
        return "".join(str(run.get("text") or "") for run in value.get("runs", [])).strip()

    @classmethod
    def _segments(cls, payload: dict[str, Any]) -> list[Segment]:
        found: list[Segment] = []

        def walk(value: Any) -> None:
            if isinstance(value, dict):
                renderer = value.get("transcriptSegmentRenderer")
                if isinstance(renderer, dict):
                    text = cls._text(renderer.get("snippet") or {})
                    if text:
                        start_ms = float(renderer.get("startMs") or 0)
                        end_ms = float(renderer.get("endMs") or start_ms)
                        found.append(
                            Segment(
                                start=start_ms / 1000,
                                duration=max(0.001, (end_ms - start_ms) / 1000),
                                text=text,
                            )
                        )
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        walk(payload)
        return found

    def fetch(self, video: Video, languages: list[str]) -> ProviderTranscript:
        errors: list[str] = []
        for language_code in languages:
            params_value = self._params(video.video_id, language_code)
            for client in self.CLIENTS:
                client_context = {
                    "hl": "en",
                    "gl": "US",
                    "timeZone": "UTC",
                    "clientName": client["name"],
                    "clientVersion": client["version"],
                    "userAgent": client["user_agent"],
                    **client["extra"],
                }
                headers = {
                    "User-Agent": str(client["user_agent"]),
                    "Content-Type": "application/json",
                    "X-YouTube-Client-Name": str(client["id"]),
                    "X-YouTube-Client-Version": str(client["version"]),
                }
                try:
                    query = {"prettyPrint": "false"}
                    if client["key"]:
                        query["key"] = str(client["key"])
                    response = requests.post(
                        self.ENDPOINT,
                        params=query,
                        headers=headers,
                        json={"context": {"client": client_context}, "params": params_value},
                        timeout=(5, 15),
                    )
                    response.raise_for_status()
                    payload = response.json()
                except (requests.RequestException, ValueError) as exc:
                    errors.append(f"{client['name']}/{language_code}: {exc}")
                    continue

                segments = self._segments(payload)
                if segments:
                    return ProviderTranscript(
                        segments=segments,
                        language=language_code,
                        language_code=language_code,
                        is_generated=True,
                        provider=f"youtube-get-transcript:{client['name'].lower()}",
                    )

                errors.append(
                    f"{client['name']}/{language_code}: response contained no transcript segments"
                )

        if errors:
            raise TranscriptBlocked("; ".join(errors[-4:]))
        raise TranscriptUnavailable("get_transcript returned no transcript")


class InnerTubeCaptionProvider:
    PLAYER_URL = "https://www.youtube.com/youtubei/v1/player"
    CLIENT_NAME = "ANDROID"
    CLIENT_ID = "3"
    CLIENT_VERSION = "21.26.364"
    USER_AGENT = "com.google.android.youtube/21.26.364 (Linux; U; Android 11) gzip"
    PUBLIC_ANDROID_KEY = "AIzaSyA8eiZmM1FaDVjRy-df2KTyQ_vz_yYM39w"

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": self.USER_AGENT,
                "Content-Type": "application/json",
                "X-YouTube-Client-Name": self.CLIENT_ID,
                "X-YouTube-Client-Version": self.CLIENT_VERSION,
            }
        )

    @staticmethod
    def _json3_segments(payload: dict[str, Any]) -> list[Segment]:
        segments: list[Segment] = []
        for event in payload.get("events", []):
            pieces = event.get("segs")
            if not pieces:
                continue
            text = "".join(str(piece.get("utf8") or "") for piece in pieces).strip()
            if not text:
                continue
            start = float(event.get("tStartMs") or 0) / 1000
            duration = float(event.get("dDurationMs") or 0) / 1000
            segments.append(Segment(start=start, duration=duration, text=text))
        return segments

    def fetch(self, video: Video, languages: list[str]) -> ProviderTranscript:
        body = {
            "context": {
                "client": {
                    "clientName": self.CLIENT_NAME,
                    "clientVersion": self.CLIENT_VERSION,
                    "androidSdkVersion": 30,
                    "userAgent": self.USER_AGENT,
                    "osName": "Android",
                    "osVersion": "11",
                    "hl": "en",
                    "gl": "US",
                }
            },
            "videoId": video.video_id,
            "contentCheckOk": True,
            "racyCheckOk": True,
        }
        try:
            response = self.session.post(
                self.PLAYER_URL,
                params={"key": self.PUBLIC_ANDROID_KEY, "prettyPrint": "false"},
                json=body,
                timeout=(5, 15),
            )
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise TranscriptBlocked(f"InnerTube player request failed: {exc}") from exc

        playability = data.get("playabilityStatus") or {}
        if playability.get("status") not in {None, "OK"}:
            reason = playability.get("reason") or playability.get("status") or "unavailable"
            raise TranscriptBlocked(f"InnerTube playability: {reason}")

        renderer = (
            data.get("captions", {})
            .get("playerCaptionsTracklistRenderer", {})
        )
        tracks = renderer.get("captionTracks") or []
        if not tracks:
            raise TranscriptUnavailable("InnerTube found no public caption tracks")

        chosen = None
        for code in languages:
            chosen = next(
                (track for track in tracks if track.get("languageCode") == code),
                None,
            )
            if chosen:
                break
        chosen = chosen or tracks[0]

        base_url = str(chosen.get("baseUrl") or "")
        if not base_url:
            raise TranscriptUnavailable("InnerTube caption track has no base URL")
        separator = "&" if "?" in base_url else "?"
        caption_url = f"{base_url}{separator}fmt=json3"

        try:
            caption_response = self.session.get(caption_url, timeout=(5, 15))
            caption_response.raise_for_status()
            if not caption_response.content:
                raise TranscriptUnavailable("InnerTube timedtext returned an empty body")
            payload = caption_response.json()
        except TranscriptUnavailable:
            raise
        except (requests.RequestException, ValueError) as exc:
            raise TranscriptBlocked(f"InnerTube caption download failed: {exc}") from exc

        segments = self._json3_segments(payload)
        if not segments:
            raise TranscriptUnavailable("InnerTube JSON3 contained no transcript segments")

        language_code = str(chosen.get("languageCode") or "und")
        return ProviderTranscript(
            segments=segments,
            language=language_code,
            language_code=language_code,
            is_generated=chosen.get("kind") == "asr",
            provider="youtube-innertube",
        )


class YtDlpCaptionProvider:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0"})

    @staticmethod
    def _pick_language(
        subtitles: dict[str, Any],
        automatic: dict[str, Any],
        languages: list[str],
    ) -> tuple[str, list[dict[str, Any]], bool] | None:
        for code in languages:
            for key in (code, f"{code}-orig"):
                if key in subtitles:
                    return key, subtitles[key], False
                if key in automatic:
                    return key, automatic[key], True

        if subtitles:
            key = min(subtitles)
            return key, subtitles[key], False

        original_auto = sorted(key for key in automatic if key.endswith("-orig"))
        if original_auto:
            key = original_auto[0]
            return key, automatic[key], True

        if automatic:
            key = min(automatic)
            return key, automatic[key], True

        return None

    @staticmethod
    def _pick_vtt(tracks: list[dict[str, Any]]) -> dict[str, Any] | None:
        return next(
            (
                track
                for track in tracks
                if track.get("ext") == "vtt" and track.get("url")
            ),
            None,
        )

    def fetch(self, video: Video, languages: list[str]) -> ProviderTranscript:
        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            "socket_timeout": 20,
        }
        try:
            with YoutubeDL(options) as ydl:
                info = ydl.extract_info(video.url, download=False)
        except DownloadError as exc:
            raise TranscriptBlocked(f"yt-dlp metadata extraction failed: {exc}") from exc

        if not info:
            raise TranscriptUnavailable("yt-dlp returned no video metadata")

        subtitles = info.get("subtitles") or {}
        automatic = info.get("automatic_captions") or {}
        chosen = self._pick_language(subtitles, automatic, languages)
        if chosen is None:
            raise TranscriptUnavailable("yt-dlp found no public caption tracks")

        language_code, tracks, is_generated = chosen
        track = self._pick_vtt(tracks)
        if track is None:
            raise TranscriptUnavailable(
                f"yt-dlp found captions for {language_code}, but no VTT format"
            )

        headers = dict(info.get("http_headers") or {})
        headers.update(track.get("http_headers") or {})
        try:
            response = self.session.get(
                str(track["url"]),
                headers=headers,
                timeout=(5, 15),
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise TranscriptBlocked(f"yt-dlp caption download failed: {exc}") from exc

        segments = parse_vtt(response.text)
        if not segments:
            raise TranscriptUnavailable("yt-dlp caption response contained no VTT cues")

        return ProviderTranscript(
            segments=segments,
            language=language_code,
            language_code=language_code.removesuffix("-orig"),
            is_generated=is_generated,
            provider="yt-dlp",
        )


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
        self.dead_instances: set[str] = set()

    def fetch(self, video: Video, languages: list[str]) -> ProviderTranscript:
        errors: list[str] = []
        for base in self.instances:
            if base in self.dead_instances:
                continue
            try:
                listing = self.session.get(
                    f"{base}/api/v1/captions/{video.video_id}", timeout=(3, 5)
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
                response = self.session.get(caption_url, timeout=(3, 7))
                response.raise_for_status()
                segments = parse_vtt(response.text)
                if not segments:
                    raise RuntimeError("caption response contained no cues")
                return ProviderTranscript(
                    segments=segments,
                    language=str(
                        chosen.get("label") or chosen.get("languageCode") or "unknown"
                    ),
                    language_code=str(chosen.get("languageCode") or "und"),
                    is_generated=None,
                    provider=f"invidious:{base}",
                )
            except (requests.RequestException, ValueError, KeyError, RuntimeError) as exc:
                errors.append(f"{base}: {exc}")
                self.dead_instances.add(base)
                time.sleep(0.3)

        if errors:
            raise TranscriptBlocked("; ".join(errors[-3:]))
        raise TranscriptUnavailable("No captions found on Invidious fallbacks")



class InvidiousDirectTranscriptProvider:
    def __init__(self, instances: list[str] | None = None) -> None:
        self.instances = instances or DEFAULT_INVIDIOUS_INSTANCES
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "yt-channel-transcriber/0.1"})
        self.dead_instances: set[str] = set()

    def fetch(self, video: Video, languages: list[str]) -> ProviderTranscript:
        errors: list[str] = []
        codes = list(dict.fromkeys([*languages, "en"]))

        for base in self.instances:
            if base in self.dead_instances:
                continue

            hard_failure = False
            for code in codes:
                for auto_generated in (True, False):
                    params = {"lang": code}
                    if auto_generated:
                        params["autogen"] = "true"
                    try:
                        response = self.session.get(
                            f"{base}/api/v1/transcripts/{video.video_id}",
                            params=params,
                            timeout=(2, 5),
                        )
                        if response.status_code == 404:
                            continue
                        response.raise_for_status()
                        payload = response.json().get("transcript") or {}
                        body = payload.get("body") or []
                        segments = [
                            Segment(
                                start=float(line["startMs"]) / 1000.0,
                                duration=max(
                                    0.001,
                                    (float(line["endMs"]) - float(line["startMs"])) / 1000.0,
                                ),
                                text=str(line.get("line") or "").strip(),
                            )
                            for line in body
                            if str(line.get("line") or "").strip()
                        ]
                        if not segments:
                            continue
                        return ProviderTranscript(
                            segments=segments,
                            language=str(payload.get("label") or code),
                            language_code=str(payload.get("languageCode") or code),
                            is_generated=bool(payload.get("autoGenerated", auto_generated)),
                            provider=f"invidious-transcript:{base}",
                        )
                    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
                        errors.append(f"{base}/{code}: {exc}")
                        hard_failure = True
                        break
                if hard_failure:
                    break

            if hard_failure:
                self.dead_instances.add(base)

        if errors:
            raise TranscriptBlocked("; ".join(errors[-5:]))
        raise TranscriptUnavailable("No transcript returned by public Invidious instances")

class PipedCaptionProvider:
    def __init__(self, instances: list[str] | None = None) -> None:
        self.instances = instances or DEFAULT_PIPED_INSTANCES
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "yt-channel-transcriber/0.1"})
        self.dead_instances: set[str] = set()

    def fetch(self, video: Video, languages: list[str]) -> ProviderTranscript:
        errors: list[str] = []
        for base in self.instances:
            if base in self.dead_instances:
                continue
            try:
                response = self.session.get(
                    f"{base}/streams/{video.video_id}",
                    timeout=(3, 10),
                )
                if response.status_code == 404:
                    continue
                response.raise_for_status()
                subtitles = response.json().get("subtitles") or []
                if not subtitles:
                    continue

                chosen = None
                for code in languages:
                    chosen = next(
                        (item for item in subtitles if item.get("code") == code),
                        None,
                    )
                    if chosen:
                        break
                chosen = chosen or subtitles[0]
                subtitle_url = str(chosen.get("url") or "")
                if not subtitle_url:
                    continue
                subtitle_url = urljoin(base + "/", subtitle_url)

                subtitle = self.session.get(subtitle_url, timeout=(3, 12))
                subtitle.raise_for_status()
                segments = parse_vtt(subtitle.text)
                if not segments:
                    raise RuntimeError("Piped subtitle response contained no VTT cues")

                code = str(chosen.get("code") or "und")
                return ProviderTranscript(
                    segments=segments,
                    language=code,
                    language_code=code,
                    is_generated=bool(chosen.get("autoGenerated")),
                    provider=f"piped:{base}",
                )
            except (requests.RequestException, ValueError, KeyError, TypeError, RuntimeError) as exc:
                errors.append(f"{base}: {exc}")
                self.dead_instances.add(base)

        if errors:
            raise TranscriptBlocked("; ".join(errors[-4:]))
        raise TranscriptUnavailable("No subtitles returned by public Piped instances")


class FallbackTranscriptProvider:
    def __init__(self) -> None:
        self.invidious_transcript = InvidiousDirectTranscriptProvider()
        self.piped = PipedCaptionProvider()
        self.transcript_panel = InnerTubeTranscriptPanelProvider()
        self.innertube = InnerTubeCaptionProvider()
        self.ytdlp = YtDlpCaptionProvider()
        self.direct = YouTubeTranscriptProvider()
        self.invidious = InvidiousTranscriptProvider()
        self.direct_blocked = False

    def fetch(self, video: Video, languages: list[str]) -> ProviderTranscript:
        errors: list[str] = []

        try:
            return self.piped.fetch(video, languages)
        except (TranscriptUnavailable, TranscriptBlocked) as exc:
            errors.append(f"piped: {exc}")

        try:
            return self.invidious_transcript.fetch(video, languages)
        except (TranscriptUnavailable, TranscriptBlocked) as exc:
            errors.append(f"invidious-transcript: {exc}")

        try:
            return self.transcript_panel.fetch(video, languages)
        except (TranscriptUnavailable, TranscriptBlocked) as exc:
            errors.append(f"get-transcript: {exc}")

        try:
            return self.innertube.fetch(video, languages)
        except (TranscriptUnavailable, TranscriptBlocked) as exc:
            errors.append(f"innertube: {exc}")

        try:
            return self.ytdlp.fetch(video, languages)
        except (TranscriptUnavailable, TranscriptBlocked) as exc:
            errors.append(f"yt-dlp: {exc}")

        if not self.direct_blocked:
            try:
                return self.direct.fetch(video, languages)
            except TranscriptUnavailable as exc:
                errors.append(f"youtube-transcript-api: {exc}")
            except TranscriptBlocked as exc:
                self.direct_blocked = True
                errors.append(f"youtube-transcript-api: {exc}")
        else:
            errors.append("youtube-transcript-api: direct provider previously blocked")

        try:
            return self.invidious.fetch(video, languages)
        except (TranscriptUnavailable, TranscriptBlocked) as exc:
            errors.append(f"invidious: {exc}")

        raise TranscriptBlocked("; ".join(errors))
