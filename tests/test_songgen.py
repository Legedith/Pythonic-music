from pathlib import Path

from pythonic_music_songgen.cli import STYLE_DEFAULTS, generate, write_midi, write_wav


def test_all_styles_generate_events():
    for style in STYLE_DEFAULTS:
        song = generate(
            seed=1234,
            style=style,
            duration_min=20,
            duration_max=25,
            energy=0.9,
            variation=0.6,
            humanize=0.1,
            title="test",
        )
        assert song.meta.style == style
        assert song.meta.seconds > 10
        assert len(song.events) > 50
        assert any(e.inst in {"kick", "snare", "hat"} for e in song.events)


def test_writes_midi_and_wav(tmp_path: Path):
    song = generate(99, "festival_edm", 20, 22, 0.9, 0.5, 0.1, "test")
    midi_path = tmp_path / "test.mid"
    wav_path = tmp_path / "test.wav"
    write_midi(song, midi_path)
    write_wav(song, wav_path)
    assert midi_path.exists()
    assert wav_path.exists()
    assert midi_path.stat().st_size > 100
    assert wav_path.stat().st_size > 1000
