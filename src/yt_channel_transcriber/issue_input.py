from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlparse


_HANDLE_RE = re.compile(r"^@[A-Za-z0-9._-]{1,100}$")
_LANG_RE = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})?$")


def section(body: str, heading: str) -> str | None:
    pattern = rf"(?ms)^### {re.escape(heading)}\s*\n+(.+?)(?=\n### |\Z)"
    match = re.search(pattern, body)
    return match.group(1).strip() if match else None


def validate_channel(value: str) -> str:
    value = value.strip()
    if _HANDLE_RE.fullmatch(value):
        return value
    if re.fullmatch(r"[A-Za-z0-9._-]{1,100}", value):
        return f"@{value}"
    if any(c in value for c in "\r\n\x00"):
        raise ValueError("channel contains invalid characters")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("channel must be an @handle or YouTube URL")
    host = (parsed.hostname or "").lower()
    if host not in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        raise ValueError("only youtube.com channel URLs are accepted")
    if not parsed.path or parsed.path == "/":
        raise ValueError("YouTube URL must identify a channel")
    return value.rstrip("/")


def validate_limit(value: str) -> str:
    try:
        limit = int(value.strip())
    except ValueError as exc:
        raise ValueError("limit must be a number") from exc
    if limit not in {5, 10, 20}:
        raise ValueError("workflow limit must be 5, 10, or 20")
    return str(limit)


def validate_languages(value: str) -> str:
    codes = [code.strip() for code in value.split(",") if code.strip()]
    if not codes or len(codes) > 8 or not all(_LANG_RE.fullmatch(code) for code in codes):
        raise ValueError("invalid language list")
    return ",".join(codes)


def parse_event(event_path: Path) -> dict[str, str]:
    event = json.loads(event_path.read_text(encoding="utf-8"))
    body = str((event.get("issue") or {}).get("body") or "")
    channel = section(body, "YouTube channel") or ""
    limit = section(body, "Number of videos") or "20"
    languages = section(body, "Preferred languages") or "de,en"
    return {
        "channel": validate_channel(channel),
        "limit": validate_limit(limit),
        "languages": validate_languages(languages),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("event_path", type=Path)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    values = parse_event(args.event_path)
    output = "\n".join(f"{key}={value}" for key, value in values.items()) + "\n"
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as handle:
            handle.write(output)
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
