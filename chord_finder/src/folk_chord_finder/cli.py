from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .analysis import ChordAnalyzer
from .render import chart_text, suggest_capo, write_exports
from .sources import download_youtube, prepare_upload
from .web import build_app


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="chord-finder", description="Estimate chords from audio or YouTube.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze = subparsers.add_parser("analyze", help="Analyze one song.")
    source = analyze.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", type=Path, help="Local audio file.")
    source.add_argument("--youtube", help="YouTube URL.")
    analyze.add_argument("--output-dir", type=Path, default=Path("chord-results"))
    analyze.add_argument("--instrument", choices=["guitar", "ukulele"], default="guitar")
    analyze.add_argument("--detail", choices=["basic", "extended"], default="basic")
    analyze.add_argument("--sensitivity", choices=["stable", "balanced", "responsive"], default="balanced")
    analyze.add_argument("--beats-per-bar", type=int, choices=[3, 4, 6], default=4)
    analyze.add_argument("--capo", default="auto", help="auto or fret 0-7")

    web = subparsers.add_parser("web", help="Launch the web app.")
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", type=int, default=7860)
    web.add_argument("--share", action="store_true")
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    if args.command == "web":
        build_app().launch(
            server_name=args.host,
            server_port=args.port,
            share=args.share,
            show_error=True,
            max_file_size="500mb",
        )
        return

    args.output_dir.mkdir(parents=True, exist_ok=True)
    job_dir = args.output_dir / ".source"
    if args.file:
        prepared = prepare_upload(args.file, job_dir)
    else:
        prepared = download_youtube(args.youtube, job_dir)

    analyzer = ChordAnalyzer()
    result = analyzer.analyze_file(
        prepared.path,
        title=prepared.title,
        source=prepared.source,
        detail_mode=args.detail,
        sensitivity=args.sensitivity,
    )
    if str(args.capo).lower() == "auto":
        capo = suggest_capo(result.segments, instrument=args.instrument)
    else:
        try:
            capo = int(args.capo)
        except ValueError:
            parser.error("--capo must be auto or a fret from 0 to 7")
        if capo not in range(8):
            parser.error("--capo must be auto or a fret from 0 to 7")

    exports = write_exports(
        result,
        args.output_dir,
        instrument=args.instrument,
        capo=capo,
        beats_per_bar=args.beats_per_bar,
    )
    sys.stdout.write(chart_text(result, capo=capo, beats_per_bar=args.beats_per_bar))
    sys.stdout.write("\nSaved:\n")
    for path in exports.values():
        sys.stdout.write(f"  {path}\n")


if __name__ == "__main__":
    main()
