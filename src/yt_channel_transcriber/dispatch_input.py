from __future__ import annotations

import os

from .issue_input import validate_channel, validate_languages, validate_limit


def main() -> None:
    values = {
        "channel": validate_channel(os.environ["DISPATCH_CHANNEL"]),
        "limit": validate_limit(os.environ["DISPATCH_LIMIT"]),
        "languages": validate_languages(os.environ["DISPATCH_LANGUAGES"]),
    }
    output_path = os.environ["GITHUB_OUTPUT"]
    with open(output_path, "a", encoding="utf-8") as handle:
        handle.writelines(f"{key}={value}\n" for key, value in values.items())


if __name__ == "__main__":
    main()
