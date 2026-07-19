from __future__ import annotations

import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from .analysis import ChordAnalyzer
from .render import Instrument, chart_text, suggest_capo, summary_markdown, timeline_rows, write_exports
from .sources import PreparedAudio, SourceError, download_youtube, prepare_upload


@dataclass(frozen=True)
class ServiceResult:
    summary: str
    chart: str
    timeline: list[list[object]]
    json_path: Path
    csv_path: Path
    text_path: Path


class ChordFinderService:
    def __init__(self, cache_dir: str | Path | None = None) -> None:
        root = Path(cache_dir) if cache_dir else Path(tempfile.gettempdir()) / "folk-chord-finder"
        self.cache_dir = root
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.analyzer = ChordAnalyzer()

    def analyze(
        self,
        *,
        youtube_url: str | None,
        upload_path: str | Path | None,
        instrument: Instrument = "guitar",
        detail_mode: str = "basic",
        sensitivity: str = "balanced",
        beats_per_bar: int = 4,
        capo_choice: str = "Auto",
    ) -> ServiceResult:
        self.cleanup_old_jobs()
        if bool(youtube_url and youtube_url.strip()) == bool(upload_path):
            raise SourceError("Provide exactly one source: a YouTube URL or an uploaded audio file.")

        job_dir = Path(tempfile.mkdtemp(prefix="job-", dir=self.cache_dir))
        prepared: PreparedAudio
        if upload_path:
            prepared = prepare_upload(upload_path, job_dir)
        else:
            prepared = download_youtube(youtube_url or "", job_dir)

        result = self.analyzer.analyze_file(
            prepared.path,
            title=prepared.title,
            source=prepared.source,
            detail_mode=detail_mode,  # type: ignore[arg-type]
            sensitivity=sensitivity,  # type: ignore[arg-type]
        )
        if capo_choice == "Auto":
            capo = suggest_capo(result.segments, instrument=instrument)
        else:
            try:
                capo = int(capo_choice)
            except (TypeError, ValueError) as exc:
                raise ValueError("Capo must be Auto or a fret from 0 to 7.") from exc
            if capo not in range(8):
                raise ValueError("Capo fret must be between 0 and 7.")

        exports = write_exports(
            result,
            job_dir,
            instrument=instrument,
            capo=capo,
            beats_per_bar=beats_per_bar,
        )
        return ServiceResult(
            summary=summary_markdown(result, instrument=instrument, capo=capo),
            chart=chart_text(result, capo=capo, beats_per_bar=beats_per_bar),
            timeline=timeline_rows(result, capo=capo),
            json_path=exports["json"],
            csv_path=exports["csv"],
            text_path=exports["text"],
        )

    def cleanup_old_jobs(self, *, max_age_seconds: float = 24 * 60 * 60) -> None:
        cutoff = time.time() - max_age_seconds
        for child in self.cache_dir.glob("job-*"):
            try:
                if child.is_dir() and child.stat().st_mtime < cutoff:
                    shutil.rmtree(child, ignore_errors=True)
            except OSError:
                continue
