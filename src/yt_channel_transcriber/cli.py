from __future__ import annotations

import argparse
from pathlib import Path

from .runner import run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Transcribe the latest public YouTube videos from a channel without API keys."
    )
    parser.add_argument("channel", help="YouTube @handle, handle, or channel URL")
    parser.add_argument("--limit", type=int, default=20, help="Number of latest videos (1-100)")
    parser.add_argument(
        "--languages",
        default="de,en",
        help="Comma-separated language preference, e.g. de,en",
    )
    parser.add_argument("--output", default="transcripts", help="Output root directory")
    parser.add_argument("--delay", type=float, default=0.7, help="Delay between videos in seconds")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    languages = [x.strip() for x in args.languages.split(",") if x.strip()]
    output = run(
        args.channel,
        Path(args.output),
        limit=args.limit,
        languages=languages,
        delay_seconds=max(0.0, args.delay),
    )
    print(output.as_posix())


if __name__ == "__main__":
    main()
