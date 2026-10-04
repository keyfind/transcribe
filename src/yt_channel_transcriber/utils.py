from __future__ import annotations

import re
import unicodedata
from pathlib import Path


def normalize_channel(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("channel must not be empty")
    if value.startswith(("http://", "https://")):
        url = value.rstrip("/")
        if not url.endswith("/videos"):
            url += "/videos"
        return url
    handle = value if value.startswith("@") else f"@{value}"
    return f"https://www.youtube.com/{handle}/videos"


def channel_slug(value: str) -> str:
    raw = value.strip().rstrip("/").split("/")[-1]
    if raw == "videos" and "/" in value.strip().rstrip("/"):
        raw = value.strip().rstrip("/").split("/")[-2]
    raw = raw.lstrip("@") or "channel"
    ascii_value = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", ascii_value).strip("-._").lower()
    return slug or "channel"


def safe_filename(value: str, max_length: int = 90) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = re.sub(r"[^A-Za-z0-9._ -]+", "", value)
    value = re.sub(r"\s+", "-", value.strip()).strip("-._").lower()
    return (value[:max_length].rstrip("-._") or "video")


def ensure_clean_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for child in path.iterdir():
        if child.is_file() or child.is_symlink():
            child.unlink()
        elif child.is_dir():
            import shutil

            shutil.rmtree(child)
