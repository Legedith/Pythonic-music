from __future__ import annotations

import pytest

from folk_chord_finder.sources import SourceError, validate_youtube_url


def test_accepts_youtube_hosts() -> None:
    assert validate_youtube_url("https://youtu.be/abc123") == "https://youtu.be/abc123"
    assert validate_youtube_url("https://music.youtube.com/watch?v=abc123")


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "https://example.com/video",
        "javascript:alert(1)",
        "https://youtu.be/",
    ],
)
def test_rejects_non_youtube_or_malformed_urls(url: str) -> None:
    with pytest.raises(SourceError):
        validate_youtube_url(url)
