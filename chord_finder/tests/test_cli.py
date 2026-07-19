from __future__ import annotations

from folk_chord_finder.cli import _build_parser


def test_web_subcommand_accepts_launch_options() -> None:
    args = _build_parser().parse_args(["web", "--host", "0.0.0.0", "--port", "9000", "--share"])
    assert args.command == "web"
    assert args.host == "0.0.0.0"
    assert args.port == 9000
    assert args.share is True
