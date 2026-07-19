from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, Sequence

import librosa
import numpy as np
import soundfile as sf

DetailMode = Literal["basic", "extended"]
Sensitivity = Literal["stable", "balanced", "responsive"]

PITCH_NAMES = ("C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")
QUALITY_SUFFIX = {
    "major": "",
    "minor": "m",
    "dominant7": "7",
    "minor7": "m7",
    "diminished": "dim",
    "sus2": "sus2",
    "sus4": "sus4",
}
QUALITY_INTERVALS: dict[str, tuple[int, ...]] = {
    "major": (0, 4, 7),
    "minor": (0, 3, 7),
    "dominant7": (0, 4, 7, 10),
    "minor7": (0, 3, 7, 10),
    "diminished": (0, 3, 6),
    "sus2": (0, 2, 7),
    "sus4": (0, 5, 7),
}
QUALITY_WEIGHTS: dict[str, tuple[float, ...]] = {
    "major": (1.0, 0.92, 0.78),
    "minor": (1.0, 0.92, 0.78),
    "dominant7": (1.0, 0.88, 0.72, 0.65),
    "minor7": (1.0, 0.88, 0.72, 0.62),
    "diminished": (1.0, 0.90, 0.78),
    "sus2": (1.0, 0.82, 0.76),
    "sus4": (1.0, 0.82, 0.76),
}

_MAJOR_PROFILE = np.asarray(
    [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88],
    dtype=float,
)
_MINOR_PROFILE = np.asarray(
    [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17],
    dtype=float,
)


@dataclass(frozen=True)
class ChordState:
    root: int | None
    quality: str

    @property
    def label(self) -> str:
        if self.root is None:
            return "N"
        return f"{PITCH_NAMES[self.root]}{QUALITY_SUFFIX[self.quality]}"


@dataclass(frozen=True)
class BeatChord:
    start: float
    end: float
    chord: str
    root: int | None
    quality: str
    confidence: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass(frozen=True)
class ChordSegment:
    start: float
    end: float
    chord: str
    root: int | None
    quality: str
    confidence: float
    beat_count: int

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass(frozen=True)
class AnalysisResult:
    title: str
    source: str
    duration: float
    tempo_bpm: float
    key: str
    key_confidence: float
    tuning_cents: float
    detail_mode: str
    sensitivity: str
    beat_chords: tuple[BeatChord, ...]
    segments: tuple[ChordSegment, ...]

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["beat_chords"] = [asdict(item) for item in self.beat_chords]
        data["segments"] = [asdict(item) for item in self.segments]
        return data


class ChordAnalysisError(RuntimeError):
    """Raised when an audio file cannot be analyzed safely or reliably."""


class ChordAnalyzer:
    """Estimate beat-synchronous chords using harmonic chroma and temporal smoothing."""

    def __init__(
        self,
        *,
        sample_rate: int = 22_050,
        hop_length: int = 512,
        max_duration_seconds: float = 15 * 60,
    ) -> None:
        self.sample_rate = sample_rate
        self.hop_length = hop_length
        self.max_duration_seconds = max_duration_seconds

    def analyze_file(
        self,
        path: str | Path,
        *,
        title: str | None = None,
        source: str = "upload",
        detail_mode: DetailMode = "basic",
        sensitivity: Sensitivity = "balanced",
    ) -> AnalysisResult:
        audio_path = Path(path)
        if not audio_path.is_file():
            raise ChordAnalysisError(f"Audio file not found: {audio_path}")

        duration = _audio_duration(audio_path)
        if not math.isfinite(duration) or duration <= 0.5:
            raise ChordAnalysisError("The audio is empty or too short to analyze.")
        if duration > self.max_duration_seconds:
            minutes = self.max_duration_seconds / 60
            raise ChordAnalysisError(f"Audio is longer than the {minutes:.0f}-minute safety limit.")

        try:
            y, sr = librosa.load(audio_path, sr=self.sample_rate, mono=True)
        except Exception as exc:  # pragma: no cover - backend-specific errors
            raise ChordAnalysisError(f"Could not decode the audio: {exc}") from exc

        if y.size < sr:
            raise ChordAnalysisError("At least one second of audio is required.")
        if not np.any(np.isfinite(y)):
            raise ChordAnalysisError("The decoded audio contains no finite samples.")

        y = np.nan_to_num(y, copy=False)
        peak = float(np.max(np.abs(y)))
        if peak < 1e-6:
            raise ChordAnalysisError("The audio is effectively silent.")
        y = y / peak

        harmonic = librosa.effects.harmonic(
            y,
            margin=2.5,
            n_fft=2048,
            hop_length=self.hop_length,
        )
        # ``estimate_tuning`` returns a fraction of one analysis bin.  We use
        # 12 bins per octave here so the value maps directly to semitones for
        # the user-facing cents estimate.  ``chroma_cqt`` then estimates its
        # own tuning on the 36-bin CQT grid, avoiding a unit mismatch.
        tuning_semitones = float(
            librosa.estimate_tuning(y=harmonic, sr=sr, bins_per_octave=12)
        )
        chroma = librosa.feature.chroma_cqt(
            y=harmonic,
            sr=sr,
            hop_length=self.hop_length,
            bins_per_octave=36,
            n_octaves=7,
            tuning=None,
            norm=2,
        )
        if chroma.shape[-1] < 2:
            raise ChordAnalysisError("Not enough harmonic information was found.")

        rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=self.hop_length)[0]
        n_frames = min(chroma.shape[-1], rms.shape[-1])
        chroma = chroma[:, :n_frames]
        rms = rms[:n_frames]

        boundaries, tempo = _beat_boundaries(
            y,
            sr=sr,
            hop_length=self.hop_length,
            n_frames=n_frames,
        )
        sync_chroma = librosa.util.sync(chroma, boundaries, aggregate=np.median, pad=False)
        sync_rms = librosa.util.sync(rms, boundaries, aggregate=np.mean, pad=False)
        times = librosa.frames_to_time(boundaries, sr=sr, hop_length=self.hop_length)
        times[-1] = float(len(y) / sr)

        states, emissions = score_chroma(sync_chroma, sync_rms, detail_mode=detail_mode)
        path_indices = decode_states(emissions, states, sensitivity=sensitivity)
        path_indices = _repair_isolated_states(path_indices, sensitivity=sensitivity)
        confidences = _frame_confidences(emissions, path_indices)

        beat_chords = tuple(
            BeatChord(
                start=float(times[i]),
                end=float(times[i + 1]),
                chord=states[state_index].label,
                root=states[state_index].root,
                quality=states[state_index].quality,
                confidence=float(confidences[i]),
            )
            for i, state_index in enumerate(path_indices)
        )
        segments = tuple(_merge_segments(beat_chords))
        key, key_confidence = estimate_key(sync_chroma)

        return AnalysisResult(
            title=title or audio_path.stem,
            source=source,
            duration=float(len(y) / sr),
            tempo_bpm=float(tempo),
            key=key,
            key_confidence=float(key_confidence),
            tuning_cents=float(tuning_semitones * 100),
            detail_mode=detail_mode,
            sensitivity=sensitivity,
            beat_chords=beat_chords,
            segments=segments,
        )


def score_chroma(
    chroma: np.ndarray,
    rms: np.ndarray | Sequence[float] | None = None,
    *,
    detail_mode: DetailMode = "basic",
) -> tuple[tuple[ChordState, ...], np.ndarray]:
    """Return chord states and an emission score matrix shaped ``(states, frames)``."""
    if chroma.ndim != 2 or chroma.shape[0] != 12:
        raise ValueError("chroma must have shape (12, frames)")
    frame_count = chroma.shape[1]
    if frame_count == 0:
        raise ValueError("chroma must contain at least one frame")

    qualities = ("major", "minor")
    if detail_mode == "extended":
        qualities = ("major", "minor", "dominant7", "minor7", "diminished", "sus2", "sus4")
    elif detail_mode != "basic":
        raise ValueError(f"Unknown detail mode: {detail_mode}")

    states = [ChordState(None, "none")]
    templates: list[np.ndarray] = []
    masks: list[np.ndarray] = []
    for quality in qualities:
        intervals = QUALITY_INTERVALS[quality]
        weights = QUALITY_WEIGHTS[quality]
        for root in range(12):
            state = ChordState(root, quality)
            states.append(state)
            template = np.full(12, 0.015, dtype=float)
            mask = np.zeros(12, dtype=float)
            for interval, weight in zip(intervals, weights, strict=True):
                pitch = (root + interval) % 12
                template[pitch] = weight
                mask[pitch] = 1.0
            template /= np.linalg.norm(template) + 1e-12
            templates.append(template)
            masks.append(mask)

    x = np.maximum(np.asarray(chroma, dtype=float), 0.0)
    l2 = np.linalg.norm(x, axis=0, keepdims=True)
    x_norm = x / np.maximum(l2, 1e-12)
    x_mass = x / np.maximum(np.sum(x, axis=0, keepdims=True), 1e-12)

    template_matrix = np.stack(templates, axis=0)
    mask_matrix = np.stack(masks, axis=0)
    cosine = template_matrix @ x_norm
    chord_mass = mask_matrix @ x_mass
    non_chord_mass = 1.0 - chord_mass

    chord_scores = cosine + 0.18 * chord_mass - 0.22 * non_chord_mass
    for index, state in enumerate(states[1:]):
        if state.root is not None:
            chord_scores[index] += 0.06 * x_mass[state.root]
        # Richer labels must earn their extra notes; this avoids calling every triad a seventh.
        if state.quality in {"dominant7", "minor7"}:
            seventh = (state.root + QUALITY_INTERVALS[state.quality][-1]) % 12  # type: ignore[operator]
            chord_scores[index] += 0.12 * x_mass[seventh] - 0.035
        elif state.quality in {"sus2", "sus4", "diminished"}:
            chord_scores[index] -= 0.025

    if rms is None:
        energy = np.ones(frame_count, dtype=float)
    else:
        energy = np.asarray(rms, dtype=float).reshape(-1)
        if energy.shape[0] != frame_count:
            raise ValueError("rms must have one value per chroma frame")
    positive = energy[energy > 1e-10]
    reference = float(np.percentile(positive, 75)) if positive.size else 1.0
    energy_ratio = np.clip(energy / max(reference, 1e-10), 0.0, 1.5)

    probabilities = x_mass
    entropy = -np.sum(probabilities * np.log(probabilities + 1e-12), axis=0) / math.log(12)
    no_chord_score = 0.64 - 1.10 * np.clip(energy_ratio, 0.0, 1.0) + 0.22 * entropy
    no_chord_score = np.where(l2.reshape(-1) < 1e-5, 0.95, no_chord_score)

    emissions = np.vstack([no_chord_score, chord_scores])
    return tuple(states), emissions


def decode_states(
    emissions: np.ndarray,
    states: Sequence[ChordState],
    *,
    sensitivity: Sensitivity = "balanced",
) -> np.ndarray:
    """Decode the most likely chord path with a small music-aware transition prior."""
    if emissions.ndim != 2 or emissions.shape[0] != len(states):
        raise ValueError("emissions and states do not match")
    if emissions.shape[1] == 0:
        return np.asarray([], dtype=int)

    base_penalty = {
        "stable": 0.22,
        "balanced": 0.13,
        "responsive": 0.065,
    }.get(sensitivity)
    if base_penalty is None:
        raise ValueError(f"Unknown sensitivity: {sensitivity}")

    state_count, frame_count = emissions.shape
    transition = np.full((state_count, state_count), base_penalty, dtype=float)
    np.fill_diagonal(transition, 0.0)

    for previous, prev_state in enumerate(states):
        for current, cur_state in enumerate(states):
            if previous == current:
                continue
            if prev_state.root is None or cur_state.root is None:
                transition[previous, current] *= 0.75
                continue
            root_distance = (cur_state.root - prev_state.root) % 12
            if root_distance in {5, 7}:  # fourth/fifth motion is common
                transition[previous, current] *= 0.72
            elif root_distance in {3, 4, 8, 9}:  # relative/mediant motion
                transition[previous, current] *= 0.86
            if prev_state.root == cur_state.root:
                transition[previous, current] *= 0.65

    dp = np.empty((state_count, frame_count), dtype=float)
    back = np.zeros((state_count, frame_count), dtype=np.int32)
    dp[:, 0] = emissions[:, 0]
    for frame in range(1, frame_count):
        candidate = dp[:, frame - 1][:, None] - transition
        back[:, frame] = np.argmax(candidate, axis=0)
        dp[:, frame] = emissions[:, frame] + candidate[back[:, frame], np.arange(state_count)]

    path = np.zeros(frame_count, dtype=np.int32)
    path[-1] = int(np.argmax(dp[:, -1]))
    for frame in range(frame_count - 1, 0, -1):
        path[frame - 1] = back[path[frame], frame]
    return path


def estimate_key(chroma: np.ndarray) -> tuple[str, float]:
    if chroma.ndim != 2 or chroma.shape[0] != 12 or chroma.shape[1] == 0:
        return "Unknown", 0.0
    profile = np.maximum(np.mean(chroma, axis=1), 0.0)
    if float(np.sum(profile)) < 1e-9:
        return "Unknown", 0.0
    profile = (profile - np.mean(profile)) / (np.std(profile) + 1e-12)

    candidates: list[tuple[float, int, str]] = []
    for root in range(12):
        for mode, key_profile in (("major", _MAJOR_PROFILE), ("minor", _MINOR_PROFILE)):
            rotated = np.roll(key_profile, root)
            rotated = (rotated - np.mean(rotated)) / (np.std(rotated) + 1e-12)
            score = float(np.dot(profile, rotated) / 12)
            candidates.append((score, root, mode))
    candidates.sort(reverse=True)
    best, second = candidates[0], candidates[1]
    label = PITCH_NAMES[best[1]] + (" major" if best[2] == "major" else " minor")
    confidence = float(np.clip(0.5 + 1.5 * (best[0] - second[0]), 0.0, 0.99))
    return label, confidence


def _audio_duration(path: Path) -> float:
    try:
        return float(sf.info(path).duration)
    except Exception:
        try:
            return float(librosa.get_duration(path=path))
        except Exception as exc:  # pragma: no cover - backend-specific errors
            raise ChordAnalysisError(f"Could not read audio duration: {exc}") from exc


def _beat_boundaries(
    y: np.ndarray,
    *,
    sr: int,
    hop_length: int,
    n_frames: int,
) -> tuple[np.ndarray, float]:
    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop_length, aggregate=np.median)
    tempo_raw, beats = librosa.beat.beat_track(
        onset_envelope=onset,
        sr=sr,
        hop_length=hop_length,
        trim=False,
        units="frames",
    )
    tempo = float(np.atleast_1d(tempo_raw)[0]) if np.size(tempo_raw) else 0.0
    beats = np.asarray(beats, dtype=int)
    beats = beats[(beats > 0) & (beats < n_frames)]

    valid = beats.size >= 4
    if valid:
        gaps = np.diff(beats)
        median_gap = float(np.median(gaps)) if gaps.size else 0.0
        valid = median_gap >= 2 and np.mean(np.abs(gaps - median_gap) <= max(2.0, median_gap * 0.55)) >= 0.55

    if not valid:
        fallback_seconds = 0.5
        step = max(1, int(round(fallback_seconds * sr / hop_length)))
        beats = np.arange(step, n_frames, step, dtype=int)
        tempo = 60.0 / fallback_seconds
    elif beats.size:
        median_gap = float(np.median(np.diff(beats))) if beats.size > 1 else 0.0
        # Beat trackers often report a beat a few milliseconds after time zero.
        # Treat that as the first boundary instead of creating a fake pickup beat.
        if median_gap > 0 and beats[0] <= 0.35 * median_gap:
            beats = beats[1:]
        # Likewise, discard a near-end beat that would create a tiny final interval.
        if beats.size and median_gap > 0 and n_frames - beats[-1] <= 0.20 * median_gap:
            beats = beats[:-1]

    boundaries = librosa.util.fix_frames(beats, x_min=0, x_max=n_frames)
    boundaries = np.unique(np.clip(boundaries, 0, n_frames))
    if boundaries.size < 2:
        boundaries = np.asarray([0, n_frames], dtype=int)
    return boundaries, tempo


def _frame_confidences(emissions: np.ndarray, path: np.ndarray) -> np.ndarray:
    confidence = np.zeros(path.shape[0], dtype=float)
    for frame, selected in enumerate(path):
        scores = emissions[:, frame]
        if scores.size == 1:
            confidence[frame] = 1.0
            continue
        selected_score = float(scores[selected])
        runner_up = float(np.max(np.delete(scores, selected)))
        margin = selected_score - runner_up
        confidence[frame] = float(np.clip(0.50 + 1.8 * margin, 0.20, 0.99))
    return confidence


def _repair_isolated_states(path: np.ndarray, *, sensitivity: Sensitivity) -> np.ndarray:
    if path.size < 3 or sensitivity == "responsive":
        return path
    repaired = path.copy()
    for index in range(1, path.size - 1):
        if path[index - 1] == path[index + 1] != path[index]:
            repaired[index] = path[index - 1]
    if sensitivity == "stable" and repaired.size >= 4:
        # Remove one-beat runs at the edges of longer, stable runs.
        runs = _runs(repaired)
        for run_index, (start, end, value) in enumerate(runs):
            if end - start > 1:
                continue
            left = runs[run_index - 1] if run_index > 0 else None
            right = runs[run_index + 1] if run_index + 1 < len(runs) else None
            if left and right and left[2] == right[2]:
                repaired[start:end] = left[2]
            elif left and (not right or left[1] - left[0] >= right[1] - right[0]):
                repaired[start:end] = left[2]
            elif right:
                repaired[start:end] = right[2]
    return repaired


def _runs(values: np.ndarray) -> list[tuple[int, int, int]]:
    if values.size == 0:
        return []
    runs: list[tuple[int, int, int]] = []
    start = 0
    for index in range(1, values.size):
        if values[index] != values[start]:
            runs.append((start, index, int(values[start])))
            start = index
    runs.append((start, values.size, int(values[start])))
    return runs


def _merge_segments(beat_chords: Sequence[BeatChord]) -> list[ChordSegment]:
    if not beat_chords:
        return []
    segments: list[ChordSegment] = []
    start = 0
    for index in range(1, len(beat_chords) + 1):
        if index < len(beat_chords) and beat_chords[index].chord == beat_chords[start].chord:
            continue
        group = beat_chords[start:index]
        weights = np.asarray([max(item.duration, 1e-6) for item in group], dtype=float)
        confidences = np.asarray([item.confidence for item in group], dtype=float)
        first = group[0]
        segments.append(
            ChordSegment(
                start=first.start,
                end=group[-1].end,
                chord=first.chord,
                root=first.root,
                quality=first.quality,
                confidence=float(np.average(confidences, weights=weights)),
                beat_count=len(group),
            )
        )
        start = index
    return segments
