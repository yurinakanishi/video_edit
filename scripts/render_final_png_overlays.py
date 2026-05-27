from __future__ import annotations

import json
import argparse
import subprocess
import sys
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
from video_edit_app_config import int_value, load_app_config, optional_path


WORK = WORKSPACE_ROOT
APP_CONFIG = load_app_config()
FFMPEG = optional_path(APP_CONFIG, "tools", "ffmpeg", default=Path(r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"))
BASE = OUTPUT_VIDEOS / "ST7_7550_multicam_cut_5min_strong_transcript_wave_refined.mp4"
LOGO = optional_path(APP_CONFIG, "assets", "logo", default=SOURCE_IMAGES / "type-logo-transparent-cropped.png")
TITLE = OUTPUT_OVERLAYS / "ai_engineer_now_title.png"
LOGO_HEIGHT = int_value(APP_CONFIG, "style", "logoHeight", default=48)
DEFAULT_DURATION = 300.1
DEFAULT_DENOISE_STRENGTH = 10


MODES = {
    "none": {
        "generator": None,
        "manifest": None,
        "output": OUTPUT_VIDEOS / "ST7_7550_multicam_cut_5min_png_titles_no_subtitles.mp4",
        "max_width": 1760,
        "bottom_margin": 16,
        "slide_px": 0,
        "pop": False,
        "animate": False,
    },
    "punchline": {
        "generator": SCRIPTS / "generate_punchline_png_overlays.py",
        "manifest": OUTPUT_OVERLAYS / "punchline_png_overlays" / "manifest.json",
        "output": OUTPUT_VIDEOS / "ST7_7550_multicam_cut_5min_png_titles_punchlines.mp4",
        "max_width": 1760,
        "bottom_margin": 12,
        "slide_px": 44,
        "pop": True,
        "animate": True,
    },
    "full": {
        "generator": SCRIPTS / "generate_full_transcript_png_overlays.py",
        "manifest": OUTPUT_OVERLAYS / "full_transcript_png_overlays" / "manifest.json",
        "output": OUTPUT_VIDEOS / "ST7_7550_multicam_cut_5min_png_titles_full_transcript.mp4",
        "max_width": 1760,
        "bottom_margin": 16,
        "slide_px": 0,
        "pop": False,
        "animate": False,
    },
}


def seconds(timestamp: str) -> float:
    hours, minutes, rest = timestamp.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(rest)


def audio_cleanup_filter(strength: int) -> str:
    nr = max(0, min(30, int(strength)))
    if nr <= 0:
        return "highpass=f=80"
    return f"highpass=f=80,afftdn=nr={nr}:nf=-35"


def run_generators(mode: str) -> None:
    subprocess.run([sys.executable, str(SCRIPTS / "generate_title_png_overlay.py")], check=True, cwd=WORK)
    if mode == "none":
        return
    subprocess.run([sys.executable, str(MODES[mode]["generator"])], check=True, cwd=WORK)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render the 5-minute edit with PNG title/subtitle overlays.")
    parser.add_argument(
        "--mode",
        choices=sorted(MODES),
        default="punchline",
        help="Subtitle overlay mode. punchline renders selected punchlines; full renders every SRT caption.",
    )
    parser.add_argument("--output", type=Path, help="Optional output path override.")
    parser.add_argument("--duration", type=float, default=DEFAULT_DURATION, help="Rendered output length in seconds before optional silence shortening.")
    parser.add_argument(
        "--no-shorten-silence",
        action="store_true",
        help="Do not shorten silent sections after rendering.",
    )
    parser.add_argument("--min-silence", type=float, default=DEFAULT_MIN_SILENCE)
    parser.add_argument("--keep-silence", type=float, default=DEFAULT_KEEP_SILENCE)
    parser.add_argument("--silence-noise", default=DEFAULT_NOISE)
    parser.add_argument("--keep-uncut", action="store_true", help="Keep the temporary uncut render next to the final output.")
    parser.add_argument("--no-audio-denoise", action="store_true", help="Disable high-pass/afftdn background-noise reduction.")
    parser.add_argument("--audio-denoise-strength", type=int, default=DEFAULT_DENOISE_STRENGTH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    mode = args.mode
    duration = max(0.1, float(args.duration))
    config = MODES[mode]
    run_generators(mode)
    captions = [] if mode == "none" else [
        item
        for item in json.loads(Path(config["manifest"]).read_text(encoding="utf-8"))
        if seconds(item["start"]) < duration
    ]
    output = args.output or Path(config["output"])
    output.parent.mkdir(parents=True, exist_ok=True)
    render_output = output
    if not args.no_shorten_silence:
        render_output = output.with_name(f"{output.stem}_uncut{output.suffix}")

    command = [
        str(FFMPEG),
        "-hide_banner",
        "-y",
        "-i",
        str(BASE),
        "-i",
        str(LOGO),
        "-i",
        str(TITLE),
    ]
    for item in captions:
        command.extend(["-loop", "1", "-framerate", "60", "-t", f"{duration:.3f}", "-i", str(WORK / item["file"])])

    filters = [
        f"[1:v]scale=-1:{LOGO_HEIGHT}[logo]",
        "[0:v][logo]overlay=W-w-40:40[v1]",
        "[v1][2:v]overlay=42:42[v2]",
    ]
    current = "v2"
    for index, item in enumerate(captions, start=1):
        stream_index = index + 2
        start = seconds(item["start"])
        end = min(duration, seconds(item["end"]))
        fade_out = max(start, end - 0.18)
        base_scale = f"if(gt(iw,{config['max_width']}),{config['max_width']}/iw,1)"
        if config["pop"]:
            pop_scale = f"if(between(t,{start:.3f},{start + 0.22:.3f}),0.88+0.12*(t-{start:.3f})/0.22,1)"
        else:
            pop_scale = "1"
        if config["animate"]:
            y_expr = (
                f"H-h-{config['bottom_margin']}+"
                f"if(between(t,{start:.3f},{start + 0.26:.3f}),"
                f"{config['slide_px']}*(1-(t-{start:.3f})/0.26),0)"
            )
            filters.append(
                f"[{stream_index}:v]format=rgba,"
                f"fade=t=in:st={start:.3f}:d=0.16:alpha=1,"
                f"fade=t=out:st={fade_out:.3f}:d=0.18:alpha=1,"
                f"scale=w='iw*{base_scale}*{pop_scale}':h='ih*{base_scale}*{pop_scale}':eval=frame[p{index}]"
            )
        else:
            y_expr = f"H-h-{config['bottom_margin']}"
            filters.append(
                f"[{stream_index}:v]format=rgba,"
                f"scale=w='iw*{base_scale}':h='ih*{base_scale}':eval=init[p{index}]"
            )
        next_stream = f"v{index + 2}"
        filters.append(
            f"[{current}][p{index}]overlay=x='(W-w)/2':y='{y_expr}':enable='between(t,{start:.3f},{end:.3f})'[{next_stream}]"
        )
        current = next_stream
    audio_denoise = not args.no_audio_denoise
    if audio_denoise:
        filters.append(
            f"[0:a:0]atrim=start=0:duration={duration:.6f},asetpts=PTS-STARTPTS,"
            f"{audio_cleanup_filter(args.audio_denoise_strength)}[a]"
        )

    command.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            f"[{current}]",
            "-map",
            "[a]" if audio_denoise else "0:a:0",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
        ]
    )
    if audio_denoise:
        command.extend(["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"])
    else:
        command.extend(["-c:a", "copy"])
    command.extend(["-t", f"{duration:.6f}", str(render_output)])
    subprocess.run(command, check=True, cwd=WORK)

    if not args.no_shorten_silence:
        report = shorten_silences(
            render_output,
            output,
            SilenceShortenConfig(
                min_silence=args.min_silence,
                keep_silence=args.keep_silence,
                noise=args.silence_noise,
            ),
        )
        if not args.keep_uncut:
            render_output.unlink(missing_ok=True)
        print(json.dumps({"output": str(output), "duration": duration, "audio_denoise": audio_denoise, "silence_shortening": report}, ensure_ascii=False, indent=2))
    else:
        print(json.dumps({"output": str(output), "duration": duration, "audio_denoise": audio_denoise}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
