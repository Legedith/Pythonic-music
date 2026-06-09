# Pythonic Music

Pythonic Music is a seeded instrumental song generator. It creates original MIDI/WAV/MP3 tracks from rule-based music theory, arrangement forms, and high-energy electronic style presets.

The project is managed with `uv`.

## Styles

- `songwriter`: layered instrumental writing with intro, build, groove, breakdown, and final return.
- `festival_edm`: 128 BPM big-room/festival arrangement with sparse build, pre-drop tension, four-on-floor kick, offbeat sub, snare rolls, and drop sections.
- `bangarang_energy`: 110 BPM glitch/wobble/high-impact electronic preset. It uses broad traits only: syncopated kicks, chopped stabs, wobble bass, double-time hats, and abrupt switch sections.
- `rolling_satisfaction`: 130 BPM rolling electro-house preset. It uses broad traits only: beat from bar one, four-on-floor kick, offbeat bass, sixteenth hats, and machine-like riff movement.

No preset copies melodies, vocals, samples, or arrangement from reference songs.

## Run

```bash
uv sync
uv run pytest
uv run songgen generate --samples 3 --style festival_edm --title demo --output-dir outputs
```

## High-energy examples

```bash
uv run songgen generate --samples 3 --style bangarang_energy --tempo-min 110 --tempo-max 110 --duration-min 92 --duration-max 108 --mood dark --mode-bias minor --energy 0.99 --bass-activity 0.95 --drum-complexity 0.96 --variation 0.82 --humanize 0.12 --title bangarang_energy --output-dir outputs/bangarang_energy
```

```bash
uv run songgen generate --samples 3 --style rolling_satisfaction --tempo-min 130 --tempo-max 130 --duration-min 92 --duration-max 108 --mood tense --mode-bias minor --energy 0.99 --bass-activity 0.98 --drum-complexity 0.97 --variation 0.58 --humanize 0.10 --title rolling_satisfaction --output-dir outputs/rolling_satisfaction
```

## Outputs

Each generation writes:

- `.mid` for DAW editing
- `.wav` from the built-in lightweight synth
- `.mp3` through `ffmpeg`, when available
- `.json` metadata with seed, tempo, key, style, form, and output paths

## Design note

The generator is intentionally MIDI-first. That keeps the composition editable and reproducible. The built-in synth is useful for quick previews, but serious production should render the MIDI through a DAW, better synths, sidechain compression, EQ, saturation, clipping, and mastering.
