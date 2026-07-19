from __future__ import annotations

from folk_chord_finder.analysis import ChordSegment
from folk_chord_finder.render import suggest_capo, transpose_label


def _segment(root: int, quality: str = "major", duration: float = 4.0) -> ChordSegment:
    suffix = "m" if quality == "minor" else ""
    return ChordSegment(0, duration, f"x{suffix}", root, quality, 0.8, 4)


def test_transpose_label_for_capo_shape() -> None:
    assert transpose_label(2, "major", -2) == "C"
    assert transpose_label(9, "minor", -2) == "Gm"
    assert transpose_label(None, "none", -2) == "N"


def test_capo_prefers_open_shapes_for_d_flat_progression() -> None:
    # Db, Ab, Bbm, Gb become C, G, Am, F with capo 1.
    segments = [_segment(1), _segment(8), _segment(10, "minor"), _segment(6)]
    assert suggest_capo(segments, instrument="guitar") == 1
