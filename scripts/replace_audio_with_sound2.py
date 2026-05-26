from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from project_paths import (
    CONFIG,
    OUTPUT_DIAGNOSTICS,
    OUTPUT_OVERLAYS,
    OUTPUT_REPORTS,
    OUTPUT_TRANSCRIPTS,
    OUTPUT_VIDEOS,
    ROOT as WORKSPACE_ROOT,
    SCRIPTS,
    SOURCE_AUDIO,
    SOURCE_IMAGES,
    SOURCE_SUBTITLES,
    SOURCE_VIDEO,
    multicam_source_root,
    resolve_project_path,
)

from shorten_silences import DEFAULT_KEEP_SILENCE, DEFAULT_MIN_SILENCE, DEFAULT_NOISE, SilenceShortenConfig, shorten_silences
from video_edit_app_config import load_app_config, optional_path


WORK = WORKSPACE_ROOT
APP_CONFIG = load_app_config()
FFMPEG = optional_path(APP_CONFIG, "tools", "ffmpeg", default=Path(r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"))
OFFSET_JSON = OUTPUT_TRANSCRIPTS / "sound2" / "sound2_audio_offset_refined.json"
DEFAULT_VIDEO = OUTPUT_VIDEOS / "ST7_7550_multicam_cut_5min_png_titles_punchlines.mp4"
DEFAULT_OUTPUT = OUTPUT_VIDEOS / "ST7_7550_multicam_cut_5min_png_titles_punchlines_sound2_audio.mp4"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replace a rendered 5-minute video's audio with synced sound-2 audio.")
    parser.add_argument("--video", type=Path, default=DEFAULT_VIDEO)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--duration", type=float, default=300.099117)
    parser.add_argument(
        "--no-shorten-silence",
        action="store_true",
        help="Do not shorten silent sections after replacing audio.",
    )
    parser.add_argument("--min-silence", type=float, default=DEFAULT_MIN_SILENCE)
    parser.add_argument("--keep-silence", type=float, default=DEFAULT_KEEP_SILENCE)
    parser.add_argument("--silence-noise", default=DEFAULT_NOISE)
    parser.add_argument("--keep-uncut", action="store_true", help="Keep the temporary uncut render next to the final output.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    offset_data = json.loads(OFFSET_JSON.read_text(encoding="utf-8"))
    sound = resolve_project_path(offset_data["sound_file"])
    offset = float(offset_data["refined_offset"])
    filter_complex = f"[1:a]atrim=start={offset:.6f}:duration={args.duration:.6f},asetpts=PTS-STARTPTS[a]"
    render_output = args.output
    if not args.no_shorten_silence:
        render_output = args.output.with_name(f"{args.output.stem}_uncut{args.output.suffix}")
    command = [
        str(FFMPEG),
        "-hide_banner",
        "-y",
        "-i",
        str(args.video),
        "-i",
        str(sound),
        "-filter_complex",
        filter_complex,
        "-map",
        "0:v:0",
        "-map",
        "[a]",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-shortest",
        str(render_output),
    ]
    subprocess.run(command, check=True, cwd=WORK)

    if not args.no_shorten_silence:
        report = shorten_silences(
            render_output,
            args.output,
            SilenceShortenConfig(
                min_silence=args.min_silence,
                keep_silence=args.keep_silence,
                noise=args.silence_noise,
            ),
        )
        if not args.keep_uncut:
            render_output.unlink(missing_ok=True)
        print(json.dumps({"output": str(args.output), "silence_shortening": report}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
