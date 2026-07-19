from __future__ import annotations

import numpy as np

from folk_chord_finder.analysis import decode_states, estimate_key, score_chroma


def _triad(root: int, minor: bool = False, noise: float = 0.015) -> np.ndarray:
    vector = np.full(12, noise, dtype=float)
    intervals = (0, 3, 7) if minor else (0, 4, 7)
    vector[(root + intervals[0]) % 12] = 1.0
    vector[(root + intervals[1]) % 12] = 0.82
    vector[(root + intervals[2]) % 12] = 0.68
    return vector


def test_basic_decoder_recognizes_common_progression() -> None:
    # C | G | Am | F, two beats each.
    chroma = np.stack(
        [
            _triad(0),
            _triad(0),
            _triad(7),
            _triad(7),
            _triad(9, minor=True),
            _triad(9, minor=True),
            _triad(5),
            _triad(5),
        ],
        axis=1,
    )
    states, emissions = score_chroma(chroma, np.ones(chroma.shape[1]), detail_mode="basic")
    path = decode_states(emissions, states, sensitivity="balanced")
    labels = [states[index].label for index in path]
    assert labels == ["C", "C", "G", "G", "Am", "Am", "F", "F"]


def test_silence_is_marked_no_chord() -> None:
    chroma = np.zeros((12, 3), dtype=float)
    states, emissions = score_chroma(chroma, np.zeros(3), detail_mode="basic")
    path = decode_states(emissions, states)
    assert [states[index].label for index in path] == ["N", "N", "N"]


def test_key_estimation_finds_c_major() -> None:
    chroma = np.stack([_triad(0), _triad(5), _triad(7), _triad(9, minor=True)] * 3, axis=1)
    key, confidence = estimate_key(chroma)
    assert key == "C major"
    assert 0 <= confidence <= 1
