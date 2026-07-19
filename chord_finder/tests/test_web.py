from __future__ import annotations

from folk_chord_finder.web import build_app


def test_web_app_builds() -> None:
    app = build_app()
    assert app is not None
