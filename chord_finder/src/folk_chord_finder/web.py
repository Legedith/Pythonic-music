from __future__ import annotations

import argparse
import os

import gradio as gr

from .service import ChordFinderService


def build_app(service: ChordFinderService | None = None) -> gr.Blocks:
    chord_service = service or ChordFinderService(os.getenv("CHORD_FINDER_CACHE_DIR"))

    def run_analysis(
        youtube_url: str,
        audio_path: str | None,
        instrument: str,
        detail_mode: str,
        sensitivity: str,
        beats_per_bar: int,
        capo_choice: str,
    ):
        try:
            result = chord_service.analyze(
                youtube_url=youtube_url,
                upload_path=audio_path,
                instrument=instrument,  # type: ignore[arg-type]
                detail_mode=detail_mode,
                sensitivity=sensitivity,
                beats_per_bar=int(beats_per_bar),
                capo_choice=capo_choice,
            )
        except Exception as exc:
            raise gr.Error(str(exc)) from exc
        return (
            result.summary,
            result.chart,
            result.timeline,
            str(result.text_path),
            str(result.csv_path),
            str(result.json_path),
        )

    with gr.Blocks(title="Folk Chord Finder") as app:
        gr.Markdown(
            "# Folk Chord Finder\n"
            "Estimate chords from a YouTube link or an uploaded song. Uploading a file is the most reliable option."
        )
        with gr.Row():
            with gr.Column(scale=1):
                youtube_url = gr.Textbox(
                    label="YouTube URL",
                    placeholder="https://www.youtube.com/watch?v=...",
                )
                audio = gr.Audio(
                    label="Or upload a song",
                    sources=["upload"],
                    type="filepath",
                    format="wav",
                )
                with gr.Row():
                    instrument = gr.Dropdown(
                        ["guitar", "ukulele"],
                        value="guitar",
                        label="Instrument",
                    )
                    capo = gr.Dropdown(
                        ["Auto", "0", "1", "2", "3", "4", "5", "6", "7"],
                        value="Auto",
                        label="Capo",
                    )
                with gr.Row():
                    detail = gr.Dropdown(
                        ["basic", "extended"],
                        value="basic",
                        label="Chord vocabulary",
                        info="Basic is usually cleaner for folk music.",
                    )
                    sensitivity = gr.Dropdown(
                        ["stable", "balanced", "responsive"],
                        value="balanced",
                        label="Change sensitivity",
                    )
                meter = gr.Dropdown([3, 4, 6], value=4, label="Beats per bar")
                analyze_button = gr.Button("Find chords", variant="primary")
                gr.Markdown(
                    "Use only audio you are allowed to process. YouTube may block downloads from hosted servers; "
                    "the file-upload path still works."
                )

            with gr.Column(scale=2):
                summary = gr.Markdown()
                chart = gr.Code(label="Play-along chart", language=None, lines=20)
                timeline = gr.Dataframe(
                    headers=["Start", "End", "Sounding chord", "Shape", "Confidence %", "Beats"],
                    datatype=["str", "str", "str", "str", "number", "number"],
                    type="array",
                    interactive=False,
                    label="Chord timeline",
                )
                with gr.Row():
                    text_download = gr.DownloadButton("Download chart")
                    csv_download = gr.DownloadButton("Download CSV")
                    json_download = gr.DownloadButton("Download JSON")

        analyze_button.click(
            run_analysis,
            inputs=[youtube_url, audio, instrument, detail, sensitivity, meter, capo],
            outputs=[summary, chart, timeline, text_download, csv_download, json_download],
            concurrency_limit=1,
        )
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Launch the Folk Chord Finder web app.")
    parser.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "7860")))
    parser.add_argument("--share", action="store_true")
    args = parser.parse_args()
    build_app().launch(
        server_name=args.host,
        server_port=args.port,
        share=args.share,
        show_error=True,
        max_file_size="500mb",
    )


if __name__ == "__main__":
    main()
