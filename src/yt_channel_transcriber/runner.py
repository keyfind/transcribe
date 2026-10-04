from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

from .exporters import write_transcript_files
from .models import TranscriptResult
from .providers import FallbackTranscriptProvider, TranscriptBlocked, TranscriptUnavailable
from .utils import channel_slug, ensure_clean_dir
from .youtube import list_latest_videos


def run(
    channel: str,
    output_root: Path,
    limit: int = 20,
    languages: list[str] | None = None,
    delay_seconds: float = 0.7,
) -> Path:
    languages = languages or ["de", "en"]
    channel_meta, videos = list_latest_videos(channel, limit)
    slug = channel_slug(channel)
    output_dir = output_root / slug
    ensure_clean_dir(output_dir)

    provider = FallbackTranscriptProvider()
    manifest_items: list[dict[str, object]] = []
    completed = 0

    for index, video in enumerate(videos, start=1):
        try:
            transcript = provider.fetch(video, languages)
            result = TranscriptResult(
                video=video,
                status="completed",
                language=transcript.language,
                language_code=transcript.language_code,
                is_generated=transcript.is_generated,
                provider=transcript.provider,
                segments=transcript.segments,
            )
            files = write_transcript_files(result, output_dir, index)
            completed += 1
            manifest_items.append({**result.to_dict(), "files": files})
        except TranscriptUnavailable as exc:
            result = TranscriptResult(video=video, status="no_transcript", error=str(exc))
            manifest_items.append(result.to_dict())
        except TranscriptBlocked as exc:
            result = TranscriptResult(video=video, status="blocked", error=str(exc))
            manifest_items.append(result.to_dict())
        except Exception as exc:  # noqa: BLE001 - keep one failed video from aborting the channel
            result = TranscriptResult(video=video, status="failed", error=f"{type(exc).__name__}: {exc}")
            manifest_items.append(result.to_dict())
        if index != len(videos):
            time.sleep(delay_seconds)

    manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "channel": channel_meta,
        "requested_limit": limit,
        "videos_found": len(videos),
        "completed": completed,
        "languages": languages,
        "items": manifest_items,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _write_index(output_dir, manifest)
    return output_dir


def _write_index(output_dir: Path, manifest: dict[str, object]) -> None:
    channel = manifest["channel"]
    assert isinstance(channel, dict)
    items = manifest["items"]
    assert isinstance(items, list)
    lines = [
        f"# {channel.get('title') or channel.get('input')} transcripts",
        "",
        f"Generated: `{manifest['generated_at']}`",
        "",
        f"Completed: **{manifest['completed']} / {manifest['videos_found']}**",
        "",
        "| # | Video | Status | Language | Downloads |",
        "|---:|---|---|---|---|",
    ]
    for index, item in enumerate(items, start=1):
        assert isinstance(item, dict)
        video = item.get("video") or {}
        assert isinstance(video, dict)
        title = str(video.get("title") or video.get("video_id") or "video").replace("|", "\\|")
        url = str(video.get("url") or "")
        status = str(item.get("status") or "unknown")
        language = str(item.get("language_code") or "-")
        files = item.get("files") or {}
        downloads = "-"
        if isinstance(files, dict) and files:
            links = [f"[{ext.upper()}]({name})" for ext, name in files.items()]
            downloads = " · ".join(links)
        lines.append(f"| {index} | [{title}]({url}) | `{status}` | {language} | {downloads} |")
    lines += ["", "Machine-readable metadata: [manifest.json](manifest.json)", ""]
    (output_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")
