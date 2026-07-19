from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

_ALLOWED_YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
}
_SAFE_TITLE = re.compile(r"[^A-Za-z0-9._ -]+")


class SourceError(RuntimeError):
    """Raised when a URL or uploaded file cannot be prepared."""


@dataclass(frozen=True)
class PreparedAudio:
    path: Path
    title: str
    source: str


def validate_youtube_url(url: str) -> str:
    value = url.strip()
    if not value:
        raise SourceError("Enter a YouTube URL or upload an audio file.")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        raise SourceError("The YouTube URL must start with http:// or https://.")
    hostname = (parsed.hostname or "").lower()
    if hostname not in _ALLOWED_YOUTUBE_HOSTS:
        raise SourceError("Only youtube.com and youtu.be links are accepted.")
    if hostname.endswith("youtu.be") and not parsed.path.strip("/"):
        raise SourceError("The youtu.be link does not contain a video ID.")
    return value


def prepare_upload(upload_path: str | Path, job_dir: str | Path) -> PreparedAudio:
    source = Path(upload_path)
    if not source.is_file():
        raise SourceError("The uploaded audio file is missing.")
    destination_dir = Path(job_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    title = _clean_title(source.stem) or "uploaded-song"
    wav_path = destination_dir / "source.wav"
    _to_wav(source, wav_path)
    return PreparedAudio(wav_path, title, "upload")


def download_youtube(url: str, job_dir: str | Path) -> PreparedAudio:
    normalized_url = validate_youtube_url(url)
    try:
        from yt_dlp import YoutubeDL
        from yt_dlp.utils import match_filter_func
    except ImportError as exc:  # pragma: no cover - dependency is optional in local test env
        raise SourceError("yt-dlp is not installed. Run `uv sync` inside chord_finder.") from exc

    destination_dir = Path(job_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(destination_dir / "download.%(ext)s")
    options = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
        "socket_timeout": 30,
        "retries": 3,
        "max_filesize": 500 * 1024 * 1024,
        "match_filter": match_filter_func("!is_live & duration <= 900"),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
                "preferredquality": "0",
            }
        ],
    }
    try:
        with YoutubeDL(options) as downloader:
            info = downloader.extract_info(normalized_url, download=True)
    except Exception as exc:  # yt-dlp uses a broad exception hierarchy
        raise SourceError(
            "YouTube download failed. Uploading the audio file is more reliable when YouTube blocks server downloads. "
            f"Details: {exc}"
        ) from exc

    candidates = sorted(destination_dir.glob("download*.wav"))
    if not candidates:
        raise SourceError("yt-dlp completed but did not produce a WAV file. Check that ffmpeg is installed.")
    title = _clean_title(str(info.get("title") or "youtube-song")) or "youtube-song"
    return PreparedAudio(candidates[0], title, normalized_url)


def _to_wav(source: Path, destination: Path) -> None:
    if source.resolve() == destination.resolve():
        return
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "22050",
            "-c:a",
            "pcm_s16le",
            str(destination),
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True, timeout=180)
            return
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            detail = getattr(exc, "stderr", "") or str(exc)
            raise SourceError(f"ffmpeg could not decode the uploaded file: {detail.strip()}") from exc
    if source.suffix.lower() != ".wav":
        raise SourceError("ffmpeg is required for non-WAV uploads.")
    shutil.copy2(source, destination)


def _clean_title(value: str) -> str:
    return _SAFE_TITLE.sub("", value).strip()[:120]
