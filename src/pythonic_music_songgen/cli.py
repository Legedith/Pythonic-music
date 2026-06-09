from __future__ import annotations

import argparse
import json
import math
import random
import shutil
import subprocess
import wave
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

SCALE = {
    "major": [0, 2, 4, 5, 7, 9, 11],
    "minor": [0, 2, 3, 5, 7, 8, 10],
}
ROOTS = {"C": 60, "Db": 61, "D": 62, "Eb": 63, "E": 64, "F": 65, "Gb": 66, "G": 67, "Ab": 68, "A": 69, "Bb": 70, "B": 71}
PROGRESSIONS = {
    "major": [[0, 4, 5, 3], [0, 5, 3, 4], [5, 3, 0, 4], [0, 3, 4, 0]],
    "minor": [[0, 5, 2, 6], [0, 3, 6, 2], [0, 5, 3, 4], [0, 6, 5, 6]],
}
STYLE_DEFAULTS = {
    "songwriter": dict(tempo=96, mode="minor", form=[("intro", 8), ("build", 16), ("groove", 16), ("breakdown", 8), ("final", 16)]),
    "festival_edm": dict(tempo=128, mode="minor", form=[("intro", 8), ("build", 16), ("pre_drop", 8), ("drop", 16), ("breakdown", 8), ("final_drop", 16)]),
    "bangarang_energy": dict(tempo=110, mode="minor", form=[("attack", 8), ("wobble_drop", 16), ("glitch_break", 8), ("second_drop", 16), ("switch", 8), ("final", 16)]),
    "rolling_satisfaction": dict(tempo=130, mode="minor", form=[("rolling_start", 16), ("filter_build", 16), ("drive", 16), ("strip", 8), ("machine_return", 16)]),
}

@dataclass
class Event:
    inst: str
    start: float
    dur: float
    pitch: int
    velocity: float

@dataclass
class SongMeta:
    title: str
    seed: int
    style: str
    tempo: float
    key: str
    mode: str
    seconds: float
    events: int

class Song:
    def __init__(self, meta: SongMeta, events: list[Event]):
        self.meta = meta
        self.events = events


def scale_pitch(root: int, mode: str, degree: int, octave: int = 0) -> int:
    notes = SCALE[mode]
    return root + 12 * octave + notes[degree % len(notes)] + 12 * (degree // len(notes))


def chord(root: int, mode: str, degree: int, octave: int = -1) -> list[int]:
    return [scale_pitch(root, mode, degree + x, octave) for x in (0, 2, 4)]


def human(rng: random.Random, value: float, amount: float, floor: float = 0.0) -> float:
    return max(floor, value + rng.uniform(-amount, amount))


def add(events: list[Event], inst: str, start: float, dur: float, pitch: int, vel: float, rng: random.Random, hum: float):
    events.append(Event(inst, human(rng, start, hum * 0.015), max(0.03, human(rng, dur, hum * 0.02, 0.03)), pitch, max(0.05, min(1.0, human(rng, vel, hum * 0.08, 0.05)))))


def generate(seed: int, style: str, duration_min: int, duration_max: int, energy: float, variation: float, humanize: float, title: str) -> Song:
    rng = random.Random(seed)
    style_def = STYLE_DEFAULTS[style]
    tempo = style_def["tempo"]
    mode = style_def["mode"]
    key = rng.choice(["A", "C", "D", "F", "G"] if mode == "minor" else ["C", "D", "F", "G", "A"])
    root = ROOTS[key]
    beat = 60.0 / tempo
    target = rng.uniform(duration_min, duration_max)
    bars_needed = max(16, int(target / (4 * beat)))
    base_form = style_def["form"]
    form = []
    total_bars = 0
    i = 0
    while total_bars < bars_needed:
        name, bars = base_form[i % len(base_form)]
        form.append((name, bars))
        total_bars += bars
        i += 1
    prog = rng.choice(PROGRESSIONS[mode])
    motif = [rng.choice([0, 2, 4, 5]), rng.choice([2, 3, 4, 6]), rng.choice([4, 5, 6, 7]), rng.choice([2, 0, 4])]
    events: list[Event] = []
    bar = 0
    for section, bars in form:
        sec_e = energy
        if any(x in section for x in ["intro", "break", "strip"]): sec_e *= 0.45
        if "build" in section or "pre" in section or "filter" in section: sec_e *= 0.70
        if "drop" in section or "drive" in section or "rolling" in section or "attack" in section: sec_e *= 1.05
        for b in range(bars):
            bar_start = (bar + b) * 4 * beat
            deg = prog[(bar + b) % len(prog)]
            ch = chord(root, mode, deg, -1)
            # chords / stabs
            if style == "songwriter" or "break" in section or "build" in section:
                dur = 4 * beat if style == "songwriter" else 1.5 * beat
                for p in ch:
                    add(events, "pad", bar_start, dur, p + 24, 0.35 + 0.25 * sec_e, rng, humanize)
            elif style == "festival_edm":
                for off in [0, 1.5, 2.5, 3.5]:
                    for p in ch:
                        add(events, "stab", bar_start + off * beat, 0.35 * beat, p + 36, 0.5 + 0.3 * sec_e, rng, humanize)
            elif style == "bangarang_energy":
                for off in [0, .75, 1.5, 2.25, 3.25]:
                    add(events, "lead", bar_start + off * beat, 0.22 * beat, scale_pitch(root, mode, rng.choice(motif), 1), 0.55 + 0.35 * sec_e, rng, humanize)
            else:
                riff = [0, 0, 3, 0, 5, 0, 3, 0]
                for n, d in enumerate(riff):
                    add(events, "lead", bar_start + n * 0.5 * beat, 0.25 * beat, scale_pitch(root, mode, d, 1), 0.45 + 0.35 * sec_e, rng, humanize)
            # melody hook where appropriate
            if section not in ["strip"] and rng.random() < 0.75:
                for n, d in enumerate(motif):
                    if rng.random() < 0.18: continue
                    dd = (d + (rng.choice([-1, 0, 1]) if rng.random() < variation * 0.25 else 0))
                    add(events, "lead", bar_start + n * beat, 0.42 * beat, scale_pitch(root, mode, dd, 2), 0.45 + 0.35 * sec_e, rng, humanize)
            # bass
            if section not in ["intro", "breakdown"]:
                if style in ["festival_edm", "rolling_satisfaction"]:
                    for off in [0.5, 1.5, 2.5, 3.5]:
                        add(events, "bass", bar_start + off * beat, 0.45 * beat, ch[0] - 12, 0.75 + 0.2 * sec_e, rng, humanize)
                elif style == "bangarang_energy":
                    for off in [0, .75, 1.25, 2, 2.75, 3.5]:
                        add(events, "wobble", bar_start + off * beat, rng.choice([0.18, 0.35, 0.55]) * beat, ch[0] - 12 + rng.choice([0, 0, 7, 12]), 0.7 + 0.25 * sec_e, rng, humanize)
                else:
                    for off in [0, 2]:
                        add(events, "bass", bar_start + off * beat, 0.8 * beat, ch[0] - 12, 0.55 + 0.25 * sec_e, rng, humanize)
            # drums
            if style != "songwriter" or section not in ["intro"]:
                kick_grid = [0, 1, 2, 3] if style in ["festival_edm", "rolling_satisfaction"] else [0, 1.5, 2, 3.25]
                for off in kick_grid:
                    add(events, "kick", bar_start + off * beat, 0.08, 36, 0.9, rng, 0)
                for off in [1, 3]:
                    add(events, "snare", bar_start + off * beat, 0.08, 38, 0.72 + 0.18 * sec_e, rng, humanize)
                hat_step = 0.25 if style in ["bangarang_energy", "rolling_satisfaction"] else 0.5
                for n in range(int(4 / hat_step)):
                    if rng.random() < 0.88:
                        add(events, "hat", bar_start + n * hat_step * beat, 0.04, 42, 0.25 + 0.35 * sec_e, rng, humanize * 0.5)
                if ("build" in section or "pre" in section or "filter" in section) and b >= bars - 2:
                    for n in range(16):
                        add(events, "snare", bar_start + n * 0.25 * beat, 0.04, 38, 0.35 + 0.03 * n, rng, humanize * 0.25)
                if b == 0 and ("drop" in section or "drive" in section or "return" in section):
                    add(events, "crash", bar_start, 1.2, 49, 0.9, rng, 0)
        bar += bars
    seconds = max((e.start + e.dur for e in events), default=0)
    return Song(SongMeta(title, seed, style, tempo, key, mode, seconds, len(events)), events)


def midi_var_len(v: int) -> bytes:
    out = [v & 0x7F]
    v >>= 7
    while v:
        out.insert(0, (v & 0x7F) | 0x80)
        v >>= 7
    return bytes(out)


def write_midi(song: Song, path: Path):
    ticks = 480
    tempo_us = int(60_000_000 / song.meta.tempo)
    msgs = [(0, bytes([0xFF, 0x51, 3, (tempo_us >> 16) & 255, (tempo_us >> 8) & 255, tempo_us & 255]))]
    channel = {"pad": 0, "stab": 1, "lead": 2, "bass": 3, "wobble": 4, "kick": 9, "snare": 9, "hat": 9, "crash": 9}
    for e in song.events:
        ch = channel.get(e.inst, 0)
        tick = max(0, round(e.start * song.meta.tempo / 60 * ticks))
        end = max(tick + 1, round((e.start + e.dur) * song.meta.tempo / 60 * ticks))
        vel = max(1, min(127, round(e.velocity * 127)))
        msgs.append((tick, bytes([0x90 | ch, e.pitch, vel])))
        msgs.append((end, bytes([0x80 | ch, e.pitch, 0])))
    msgs.sort(key=lambda x: (x[0], x[1][0] & 0xF0))
    data = bytearray()
    last = 0
    for tick, msg in msgs:
        data += midi_var_len(tick - last) + msg
        last = tick
    data += b"\x00\xff\x2f\x00"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        f.write(b"MThd" + (6).to_bytes(4, "big") + (0).to_bytes(2, "big") + (1).to_bytes(2, "big") + ticks.to_bytes(2, "big"))
        f.write(b"MTrk" + len(data).to_bytes(4, "big") + data)


def synth_event(buf: np.ndarray, sr: int, e: Event):
    start = max(0, int(e.start * sr))
    end = min(len(buf), int((e.start + e.dur) * sr))
    if end <= start: return
    t = np.arange(end - start) / sr
    amp = e.velocity * 0.18
    if e.inst == "kick":
        wavef = np.sin(2 * np.pi * (55 * np.exp(-t * 18)) * t) * np.exp(-t * 9) * 1.8
    elif e.inst in ["snare", "hat", "crash"]:
        rng = np.random.default_rng(int((e.start + e.pitch) * 1000) & 0xFFFFFFFF)
        decay = 18 if e.inst == "hat" else 6 if e.inst == "snare" else 2
        wavef = rng.uniform(-1, 1, len(t)) * np.exp(-t * decay)
    else:
        freq = 440 * 2 ** ((e.pitch - 69) / 12)
        saw = 2 * ((t * freq) % 1) - 1
        sine = np.sin(2 * np.pi * freq * t)
        wavef = 0.65 * saw + 0.35 * sine if e.inst in ["lead", "stab", "wobble"] else sine
        env = np.minimum(1, t / 0.015) * np.exp(-t / max(0.2, e.dur * 1.4))
        if e.inst in ["bass", "wobble"]: wavef = np.tanh(wavef * 2.4) * env * 1.25
        else: wavef = wavef * env
    buf[start:end] += amp * wavef[: end - start]


def write_wav(song: Song, path: Path, sr: int = 44100):
    length = int((song.meta.seconds + 1.0) * sr)
    buf = np.zeros(length, dtype=np.float32)
    for e in song.events:
        synth_event(buf, sr, e)
    # soft limiter
    buf = np.tanh(buf * 1.4)
    pcm = np.int16(np.clip(buf, -1, 1) * 32767)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(sr); f.writeframes(pcm.tobytes())


def wav_to_mp3(wav_path: Path, mp3_path: Path):
    if not shutil.which("ffmpeg"):
        return False
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav_path), "-codec:a", "libmp3lame", "-q:a", "3", str(mp3_path)], check=True)
    return True


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Generate seeded instrumental songs.")
    p.add_argument("command", choices=["generate"])
    p.add_argument("--samples", type=int, default=1)
    p.add_argument("--seed", type=int, default=4100)
    p.add_argument("--style", choices=sorted(STYLE_DEFAULTS), default="songwriter")
    p.add_argument("--duration-min", type=int, default=90)
    p.add_argument("--duration-max", type=int, default=120)
    p.add_argument("--energy", type=float, default=0.8)
    p.add_argument("--variation", type=float, default=0.5)
    p.add_argument("--humanize", type=float, default=0.25)
    p.add_argument("--title", default="song")
    p.add_argument("--output-dir", default="outputs")
    args, _unknown = p.parse_known_args(argv)
    out = Path(args.output_dir); out.mkdir(parents=True, exist_ok=True)
    summary = []
    for i in range(args.samples):
        song = generate(args.seed + i, args.style, args.duration_min, args.duration_max, args.energy, args.variation, args.humanize, f"{args.title}_{i+1:02d}")
        stem = f"{args.title}_{i+1:02d}_seed_{song.meta.seed}_{song.meta.style}"
        midi = out / f"{stem}.mid"; wav = out / f"{stem}.wav"; mp3 = out / f"{stem}.mp3"; meta = out / f"{stem}.json"
        write_midi(song, midi); write_wav(song, wav); made_mp3 = wav_to_mp3(wav, mp3)
        payload = asdict(song.meta) | {"midi": str(midi), "wav": str(wav), "mp3": str(mp3) if made_mp3 else None}
        meta.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        summary.append(payload)
        print(json.dumps(payload))
    (out / "generation_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
