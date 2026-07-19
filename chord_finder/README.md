# Folk Chord Finder

A local-first web app and command-line tool that estimates chords from either:

- a YouTube URL; or
- an uploaded/downloaded audio file.

It is designed for play-along use when local, traditional, and folk songs have no published chord sheet.

## What it returns

- timed chord changes;
- an approximate 3-, 4-, or 6-beat bar chart;
- estimated key, tempo, and tuning offset;
- capo-relative chord names, with capo scoring tuned separately for guitar and ukulele;
- an optional automatic capo suggestion; and
- text, CSV, and JSON downloads.

## Important limit

Automatic chord recognition is not exact. It works best on songs with clear harmony and stable tuning. Drones, dense percussion, bass-heavy mixes, key changes, microtonal music, unusual tunings, and extended chords can reduce accuracy. The default **basic** mode intentionally prefers major and minor chords because a simpler, playable chart is often more useful than a fragile complex transcription.

## Run with `uv`

Requirements: Python 3.11+, `uv`, and `ffmpeg`. A JavaScript runtime such as Node.js or Deno improves current YouTube support in `yt-dlp`.

```bash
cd chord_finder
uv sync --extra dev
uv run pytest
uv run chord-finder-web --host 127.0.0.1 --port 7860
# Equivalent: uv run chord-finder web --host 127.0.0.1 --port 7860
```

Open `http://127.0.0.1:7860`.

## Command line

Analyze a downloaded song:

```bash
uv run chord-finder analyze \
  --file /path/to/song.mp3 \
  --instrument guitar \
  --detail basic \
  --sensitivity balanced \
  --beats-per-bar 4 \
  --capo auto \
  --output-dir chord-results
```

Analyze a YouTube link:

```bash
uv run chord-finder analyze \
  --youtube "https://www.youtube.com/watch?v=VIDEO_ID" \
  --output-dir chord-results
```

Uploading/downloading the audio yourself is more reliable than direct YouTube processing. YouTube changes frequently, can block data-center IP addresses, and may require browser cookies for some videos. Live streams and videos longer than 15 minutes are rejected.

## Docker

```bash
docker build -t folk-chord-finder .
docker run --rm -p 7860:7860 folk-chord-finder
```

## How it works

1. Audio is converted to mono WAV.
2. Harmonic content is separated from percussion.
3. A constant-Q chromagram measures the twelve pitch classes over time.
4. Chroma is synchronized to detected beats.
5. Major/minor or extended chord templates are scored.
6. A Viterbi-style decoder suppresses implausible one-beat chord flicker.
7. Consecutive beats are merged into timed chord segments.

No paid API or external model is required. Audio analysis runs on the machine hosting the app. Direct YouTube input still sends the URL to YouTube through `yt-dlp`.

## Safety and lawful use

Only process audio you are allowed to access and use. Do not expose this app publicly without authentication, file-size limits, cleanup, and rate limiting. The app validates YouTube hosts, rejects arbitrary URLs, limits analysis to 15 minutes, serializes jobs, and removes old cached jobs, but a public deployment still needs normal production hardening.

## Tests

```bash
uv run pytest
```

The tests cover chord-template decoding, silence handling, key estimation, capo shaping, URL validation, and web-app construction.
