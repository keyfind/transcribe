from __future__ import annotations

from datetime import datetime
from typing import Any

from yt_dlp import YoutubeDL

from .models import Video
from .utils import normalize_channel


def _published(entry: dict[str, Any]) -> str | None:
    timestamp = entry.get("timestamp") or entry.get("release_timestamp")
    if timestamp:
        return datetime.utcfromtimestamp(timestamp).isoformat(timespec="seconds") + "Z"
    upload_date = entry.get("upload_date")
    if upload_date and len(upload_date) == 8:
        return f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}"
    return None


def list_latest_videos(channel: str, limit: int = 20) -> tuple[dict[str, str], list[Video]]:
    if limit < 1 or limit > 100:
        raise ValueError(f"limit must be between 1 and 100")
    url = normalize_channel(channel)
    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "playlistend": limit,
        "ignoreerrors": True,
        "socket_timeout": 30,
    }

    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)

    if not info:
        raise RuntimeError(f"Could not resolve channel: {channel}")

    entries = [entry for entry in (info.get("entries") or []) if entry]
    videos: list[Video] = []
    seen: set[str] = set()
    for entry in entries:
        video_id = str(entry.get("id") or "").strip()
        if not video_id or video_id in seen:
            continue
        seen.add(video_id)
        videos.append(
            Video(
                video_id=video_id,
                title=str(entry.get("title") or video_id),
                url=f"https://www.youtube.com/watch?v={video_id}",
                published_at=_published(entry),
                duration=entry.get("duration"),
            )
        )
        if len(videos) >= limit:
            break

    if not videos:
        raise RuntimeError(f"No videos found for channel: {channel}")

    meta = {
        "input": channel,
        "url": url,
        "title": str(info.get("channel") or info.get("uploader") or info.get("title") or channel),
        "channel_id": str(info.get("channel_id") or info.get("uploader_id") or ""),
    }
    return meta, videos
