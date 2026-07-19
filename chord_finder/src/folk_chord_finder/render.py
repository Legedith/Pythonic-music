from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path
from typing import Literal, Sequence

from .analysis import AnalysisResult, BeatChord, ChordSegment, PITCH_NAMES, QUALITY_SUFFIX

Instrument = Literal["guitar", "ukulele"]


EASY_ROOTS = {
    "guitar": {
        "major": {0: 1.0, 2: 0.9, 4: 1.0, 5: 0.72, 7: 1.0, 9: 1.0},
        "minor": {2: 0.85, 4: 1.0, 9: 1.0},
        "dominant7": {0: 0.85, 2: 1.0, 4: 1.0, 7: 0.9, 9: 0.9},
    },
    "ukulele": {
        "major": {0: 1.0, 2: 0.9, 5: 1.0, 7: 1.0, 9: 0.9},
        "minor": {2: 0.9, 4: 0.85, 9: 1.0},
        "dominant7": {0: 0.9, 2: 0.9, 4: 0.9, 7: 0.9, 9: 0.9},
    },
}


def transpose_label(root: int | None, quality: str, semitones: int) -> str:
    if root is None:
        return "N"
    return f"{PITCH_NAMES[(root + semitones) % 12]}{QUALITY_SUFFIX.get(quality, '')}"


def suggest_capo(segments: Sequence[ChordSegment], instrument: Instrument = "guitar", max_fret: int = 7) -> int:
    if instrument not in EASY_ROOTS:
        raise ValueError(f"Unsupported instrument: {instrument}")
    sounding = [segment for segment in segments if segment.root is not None and segment.chord != "N"]
    if not sounding:
        return 0

    total_weight = sum(max(segment.duration, 0.25) for segment in sounding)
    scores: list[tuple[float, int]] = []
    for capo in range(max_fret + 1):
        weighted_ease = 0.0
        for segment in sounding:
            shape_root = (segment.root - capo) % 12  # type: ignore[operator]
            quality_scores = EASY_ROOTS[instrument].get(segment.quality, {})
            ease = quality_scores.get(shape_root, 0.25 if segment.quality in {"major", "minor"} else 0.12)
            weighted_ease += ease * max(segment.duration, 0.25)
        # High capos can produce easy shapes but reduce range and may be awkward.
        score = weighted_ease / max(total_weight, 1e-9) - 0.07 * capo
        scores.append((score, capo))
    best_score, best_capo = max(scores, key=lambda item: (item[0], -item[1]))
    zero_score = scores[0][0]
    return best_capo if best_score >= zero_score + 0.08 else 0


def summary_markdown(result: AnalysisResult, *, instrument: Instrument, capo: int) -> str:
    key_confidence = round(result.key_confidence * 100)
    lines = [
        f"### {result.title}",
        f"**Estimated key:** {result.key} ({key_confidence}% relative confidence)  ",
        f"**Tempo:** {result.tempo_bpm:.1f} BPM  ",
        f"**Duration:** {format_time(result.duration)}  ",
        f"**Tuning offset:** {result.tuning_cents:+.0f} cents  ",
    ]
    if capo:
        lines.append(
            f"**Suggested {instrument} capo:** fret {capo}. The chart shows chord shapes; they sound at the original pitch.  "
        )
    else:
        lines.append(f"**Suggested {instrument} capo:** none.  ")
    lines.append(
        "**Accuracy note:** chord recognition is an estimate. Listen especially at bass-heavy passages, drones, key changes, and unusual tunings."
    )
    return "\n".join(lines)


def chart_text(
    result: AnalysisResult,
    *,
    capo: int = 0,
    beats_per_bar: int = 4,
) -> str:
    if beats_per_bar not in {3, 4, 6}:
        raise ValueError("beats_per_bar must be 3, 4, or 6")
    lines = [
        result.title,
        f"Estimated key: {result.key} | Tempo: {result.tempo_bpm:.1f} BPM | Capo: {capo}",
        "",
        "TIMED CHORD CHANGES",
    ]
    for segment in result.segments:
        shape = transpose_label(segment.root, segment.quality, -capo)
        confidence = round(segment.confidence * 100)
        lines.append(f"{format_time(segment.start)}  {shape:<7}  ({confidence}%)")

    lines.extend(
        [
            "",
            f"APPROXIMATE {beats_per_bar}-BEAT BARS",
            "The first detected interval is treated as beat 1; pickup notes can shift the bar lines.",
        ]
    )
    displayed = [transpose_label(item.root, item.quality, -capo) for item in result.beat_chords]
    previous: str | None = None
    for bar_start in range(0, len(displayed), beats_per_bar):
        cells: list[str] = []
        for chord in displayed[bar_start : bar_start + beats_per_bar]:
            if chord == previous:
                cells.append("·")
            else:
                cells.append(chord)
            previous = chord
        cells.extend(["·"] * (beats_per_bar - len(cells)))
        bar_number = bar_start // beats_per_bar + 1
        lines.append(f"{bar_number:>3} | " + "  ".join(f"{cell:<6}" for cell in cells).rstrip())
    return "\n".join(lines).rstrip() + "\n"


def timeline_rows(result: AnalysisResult, *, capo: int = 0) -> list[list[object]]:
    rows: list[list[object]] = []
    for segment in result.segments:
        rows.append(
            [
                format_time(segment.start),
                format_time(segment.end),
                segment.chord,
                transpose_label(segment.root, segment.quality, -capo),
                round(segment.confidence * 100),
                segment.beat_count,
            ]
        )
    return rows


def write_exports(
    result: AnalysisResult,
    output_dir: str | Path,
    *,
    instrument: Instrument,
    capo: int,
    beats_per_bar: int,
) -> dict[str, Path]:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    stem = _safe_stem(result.title)
    json_path = destination / f"{stem}-chords.json"
    csv_path = destination / f"{stem}-chords.csv"
    text_path = destination / f"{stem}-chords.txt"

    payload = result.to_dict()
    payload["instrument"] = instrument
    payload["capo"] = capo
    payload["displayed_segments"] = [
        {
            **asdict(segment),
            "shape": transpose_label(segment.root, segment.quality, -capo),
        }
        for segment in result.segments
    ]
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["start_seconds", "end_seconds", "sounding_chord", "shape", "confidence", "beats"])
        for segment in result.segments:
            writer.writerow(
                [
                    f"{segment.start:.3f}",
                    f"{segment.end:.3f}",
                    segment.chord,
                    transpose_label(segment.root, segment.quality, -capo),
                    f"{segment.confidence:.3f}",
                    segment.beat_count,
                ]
            )

    text_path.write_text(chart_text(result, capo=capo, beats_per_bar=beats_per_bar), encoding="utf-8")
    return {"json": json_path, "csv": csv_path, "text": text_path}


def format_time(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _safe_stem(value: str) -> str:
    cleaned = "".join(character if character.isalnum() or character in {"-", "_"} else "-" for character in value)
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return cleaned[:80] or "song"
