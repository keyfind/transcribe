# YouTube Channel Transcriber

Transcribe the latest public videos from a YouTube channel with **no YouTube API key** and **no external paid API**. The heavy lifting runs on GitHub Actions.

## How it works

1. Open **Issues → New issue → “Transcribe a YouTube channel”**.
2. Enter a YouTube `@handle` or channel URL.
3. Choose up to the latest 20 uploads and preferred caption languages.
4. Submitting the issue automatically starts a GitHub Actions workflow.
5. The workflow writes every available transcript back to `transcripts/<channel>/` as:
   - `.txt`
   - `.srt`
   - `.json`
6. A ZIP containing all generated files is also attached to the workflow run for 30 days.
7. The bot comments on the request issue with links when the run is finished.

You can also use **Actions → Transcribe YouTube channel → Run workflow** instead of creating an issue.

## Zero-key architecture

The project intentionally avoids the official YouTube Data API and external API credentials:

- [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) resolves a public channel and lists its latest uploads. The workflow installs Deno plus the `yt-dlp[default]` extras required for current YouTube support.
- Transcript retrieval uses a fallback chain. On GitHub-hosted runners the first practical provider is [FreeTranscriptAPI](https://freetranscriptapi.com/), whose anonymous endpoint needs no key and currently allows 20 requests per hour per IP.
- [youtube-transcript.ai](https://youtube-transcript.ai/youtube-transcript-api) is the second hosted no-key fallback and returns timestamped transcript text under fair-use limits.
- Direct `youtube-transcript-api`, InnerTube, `yt-dlp`, Invidious and Piped providers remain as additional fallbacks.
- GitHub's built-in `GITHUB_TOKEN` is used only to commit generated files and comment on the triggering issue. You do **not** configure or store a personal token.

## Important limitation: cloud IP blocking

YouTube increasingly blocks requests from cloud-provider IP ranges. `youtube-transcript-api` explicitly documents `RequestBlocked` / `IpBlocked` failures for cloud environments. GitHub-hosted runners can therefore fail for some videos or runs even though the code requires no API key.

The hosted no-key transcript providers avoid that GitHub-runner IP problem, but they are third-party services with their own availability and fair-use limits. The workflow records provider failures as `blocked` instead of aborting the whole channel run.

If you need higher-volume or fully self-controlled production usage, use a self-hosted GitHub runner on a normal residential/business connection or configure a transcript provider you operate yourself.

## Output layout

```text
transcripts/
└── openai/
    ├── README.md
    ├── manifest.json
    ├── 01-video-title-VIDEOID.txt
    ├── 01-video-title-VIDEOID.srt
    ├── 01-video-title-VIDEOID.json
    └── ...
```

`manifest.json` records success/failure state, selected language, provider, source video URL and transcript segments.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
yt-channel-transcriber @OpenAI --limit 20 --languages de,en
```

No `.env` file is required.

### Optional Invidious override

If the bundled public fallback instances are unavailable, you can supply your own comma-separated list. This is not a secret:

```bash
INVIDIOUS_INSTANCES="https://example.one,https://example.two" \
  yt-channel-transcriber @OpenAI
```

## Status values

| Status | Meaning |
|---|---|
| `completed` | Transcript was fetched and exported. |
| `no_transcript` | The video has no usable public caption track. |
| `blocked` | YouTube/direct provider and fallback access were blocked or unavailable. |
| `failed` | An unexpected per-video error occurred. |

One bad video never aborts the remaining videos.

## Security and permissions

The transcription workflow requests only:

```yaml
permissions:
  contents: write
  issues: write
```

This allows the repository's automatic GitHub token to commit transcript files and post the result link back to an issue. There are no user-managed secrets in the default setup.

## Notes on content rights

This tool only retrieves captions that are already exposed publicly by the source/fallback services. Users are responsible for how they store, redistribute, or reuse transcript content.

## License

MIT
