from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from project_paths import (
    CONFIG,
    OUTPUT_DIAGNOSTICS,
    OUTPUT_AUDIO,
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

from PIL import Image, ImageDraw, ImageFont

from shorten_silences import DEFAULT_KEEP_SILENCE, DEFAULT_MIN_SILENCE, DEFAULT_NOISE, SilenceShortenConfig, shorten_silences
from video_edit_app_config import int_value, load_app_config, optional_path


WORK = WORKSPACE_ROOT
APP_CONFIG = load_app_config()
FFMPEG = optional_path(APP_CONFIG, "tools", "ffmpeg", default=Path(r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"))
CAM1 = SOURCE_VIDEO / "1cam" / "ST7_7550_overlap_5min.mp4"
CAM2_7192 = multicam_source_root() / "2cam" / "0H4A7192.MP4"
CAM2_7193 = multicam_source_root() / "2cam" / "0H4A7193.MP4"
LOGO = optional_path(APP_CONFIG, "assets", "logo", default=SOURCE_IMAGES / "type-logo-transparent-cropped.png")
TITLE = OUTPUT_OVERLAYS / "ai_engineer_now_title.png"
SUMMARY_CARD = OUTPUT_OVERLAYS / "interviewer_question_summary_card.png"
GLOSSARY_MANIFEST = OUTPUT_OVERLAYS / "glossary_term_overlays" / "manifest.json"
OMIT_SUMMARY_MUSIC = OUTPUT_AUDIO / "omit_summary_card_music_5s.wav"
FONT_PATH = Path(r"C:\Windows\Fonts\YuGothB.ttc")
LOGO_HEIGHT = int_value(APP_CONFIG, "style", "logoHeight", default=120)
LOGO_MARGIN_X = int_value(APP_CONFIG, "style", "logoMarginX", default=16)
LOGO_MARGIN_Y = int_value(APP_CONFIG, "style", "logoMarginY", default=-10)
TITLE_X = int_value(APP_CONFIG, "style", "titleX", default=24)
TITLE_Y = int_value(APP_CONFIG, "style", "titleY", default=24)
SOUND_OFFSET = OUTPUT_TRANSCRIPTS / "sound2" / "sound2_audio_offset_refined.json"

MODES = {
    "none": {
        "generator": None,
        "manifest": None,
        "output": OUTPUT_VIDEOS / "ST7_7550_multicam_cut_1min_onepass_no_subtitles.mp4",
        "bottom_margin": 16,
        "slide_px": 0,
        "pop": False,
        "animate": False,
    },
    "full": {
        "generator": SCRIPTS / "generate_full_transcript_png_overlays.py",
        "manifest": OUTPUT_OVERLAYS / "full_transcript_png_overlays" / "manifest.json",
        "output": OUTPUT_VIDEOS / "ST7_7550_multicam_cut_1min_onepass_full_transcript.mp4",
        "bottom_margin": 16,
        "slide_px": 0,
        "pop": False,
        "animate": False,
    },
    "punchline": {
        "generator": SCRIPTS / "generate_punchline_png_overlays.py",
        "manifest": OUTPUT_OVERLAYS / "punchline_png_overlays" / "manifest.json",
        "output": OUTPUT_VIDEOS / "ST7_7550_multicam_cut_1min_onepass_punchline.mp4",
        "bottom_margin": 12,
        "slide_px": 44,
        "pop": True,
        "animate": True,
    },
}

DEFAULT_OUTPUT_END = 85.0
DURATION = DEFAULT_OUTPUT_END
CAM2_SOURCE_OFFSET = 1102.710
CAM2_7193_SOURCE_OFFSET = 59.640 - 85.000
LATE_CAM2_SWITCH = 68.0
CAM1_SOURCE_OFFSET = 20.0
CAM2_RGB_GAIN = (0.96, 0.98, 1.02)  # R, G, B. Slightly cool the zoom camera.
CAM2_SATURATION_SCALE = 0.94
CAM1_SKIN_GAIN = (0.90265487, 0.93055556, 0.95431472)  # B, G, R measured by OpenCV skin median.
CAM1_SKIN_GAIN_STRENGTH = 1.00
CAM1_SATURATION_SCALE = 0.90
CAMERA_CENTER_CROP = 0.80
DEFAULT_DENOISE_STRENGTH = 10
OMIT_INTERVIEWER_START = 20.0
OMIT_INTERVIEWER_END = 57.0
OMIT_ANSWER_END = DEFAULT_OUTPUT_END
OMIT_SUMMARY_DURATION = 5.0
OMIT_OUTPUT_DURATION = OMIT_INTERVIEWER_START + OMIT_SUMMARY_DURATION + (OMIT_ANSWER_END - OMIT_INTERVIEWER_END)
SUMMARY_LINES = (
    "PDMフリー化をめぐる論争について",
    "どう感じますか？",
)
DYNAMIC_TIMELINE_SEGMENTS = [
    {"camera": "2cam", "input_index": 0, "start": 0.0, "end": 3.2, "local_start": 0.0, "local_end": 3.2, "crop": 0.74, "x": 0.77, "y": 0.06},
    {"camera": "2cam", "input_index": 0, "start": 3.2, "end": 6.8, "local_start": 3.2, "local_end": 6.8, "crop": 0.88, "x": 0.66, "y": 0.04},
    {"camera": "2cam", "input_index": 0, "start": 6.8, "end": 10.6, "local_start": 6.8, "local_end": 10.6, "crop": 0.76, "x": 0.78, "y": 0.07},
    {"camera": "2cam", "input_index": 0, "start": 10.6, "end": 14.4, "local_start": 10.6, "local_end": 14.4, "crop": 0.92, "x": 0.62, "y": 0.04},
    {"camera": "2cam", "input_index": 0, "start": 14.4, "end": 20.0, "local_start": 14.4, "local_end": 20.0, "crop": 0.72, "x": 0.80, "y": 0.08},
    {"camera": "1cam", "input_index": 1, "start": 20.0, "end": 24.5, "local_start": 0.0, "local_end": 4.5, "crop": 0.94, "x": 0.50, "y": 0.02},
    {"camera": "1cam", "input_index": 1, "start": 24.5, "end": 31.0, "local_start": 4.5, "local_end": 11.0, "crop": 0.70, "x": 0.76, "y": 0.11},
    {"camera": "1cam", "input_index": 1, "start": 31.0, "end": 37.0, "local_start": 11.0, "local_end": 17.0, "crop": 0.86, "x": 0.60, "y": 0.04},
    {"camera": "1cam", "input_index": 1, "start": 37.0, "end": 44.0, "local_start": 17.0, "local_end": 24.0, "crop": 0.74, "x": 0.76, "y": 0.10},
    {"camera": "1cam", "input_index": 1, "start": 44.0, "end": 51.0, "local_start": 24.0, "local_end": 31.0, "crop": 0.90, "x": 0.56, "y": 0.03},
    {"camera": "1cam", "input_index": 1, "start": 51.0, "end": 57.0, "local_start": 31.0, "local_end": 37.0, "crop": 0.72, "x": 0.77, "y": 0.10},
    {"camera": "1cam", "input_index": 1, "start": 57.0, "end": 63.0, "local_start": 37.0, "local_end": 43.0, "crop": 0.70, "x": 0.76, "y": 0.11},
    {"camera": "1cam", "input_index": 1, "start": 63.0, "end": 70.0, "local_start": 43.0, "local_end": 50.0, "crop": 0.84, "x": 0.61, "y": 0.04},
    {"camera": "1cam", "input_index": 1, "start": 70.0, "end": 78.0, "local_start": 50.0, "local_end": 58.0, "crop": 0.72, "x": 0.77, "y": 0.10},
    {"camera": "1cam", "input_index": 1, "start": 78.0, "end": 85.0, "local_start": 58.0, "local_end": 65.0, "crop": 0.94, "x": 0.50, "y": 0.02},
]


def seconds(timestamp: str) -> float:
    hours, minutes, rest = timestamp.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(rest)


def run(command: list[str]) -> None:
    subprocess.run(command, check=True, cwd=WORK)


def slug_number(value: float) -> str:
    return f"{value:g}".replace(".", "p")


def default_render_output(args: argparse.Namespace) -> Path:
    tokens: list[str] = []
    if args.mode != "full":
        tokens.append(args.mode)
    if args.omit_interviewer_question:
        tokens.append("omit-interviewer")
    if args.dynamic_cuts:
        tokens.append("dynamic-cuts")
    if not args.auto_context_cuts:
        tokens.append("fixed-cuts")
    if args.natural_dialogue_cuts:
        tokens.append("natural-dialogue-cuts")
    if args.preview_start != 0.0 or args.preview_duration != DURATION:
        tokens.append(f"preview-{slug_number(args.preview_start)}-{slug_number(args.preview_duration)}s")
    if args.no_shorten_silence:
        tokens.append("no-shorten")
    if args.keep_uncut:
        tokens.append("keep-uncut")
    if args.no_audio_denoise:
        tokens.append("no-denoise")
    elif args.audio_denoise_strength != DEFAULT_DENOISE_STRENGTH:
        tokens.append(f"denoise-{args.audio_denoise_strength}")
    if not args.term_explanations:
        tokens.append("no-terms")
    if args.crf != "18":
        tokens.append(f"crf-{args.crf}")
    if args.preset != "veryfast":
        tokens.append(f"preset-{args.preset}")

    stem = datetime.now().strftime("%Y%m%d_%H%M%S")
    if tokens:
        stem = f"{stem}_{'_'.join(tokens)}"
    return OUTPUT_VIDEOS / f"{stem}.mp4"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render the 1-minute edit in one ffmpeg filter graph.")
    parser.add_argument("--mode", choices=sorted(MODES), default="full")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--skip-subtitle-regeneration", action="store_true")
    parser.add_argument("--preview-start", type=float, default=0.0)
    parser.add_argument("--preview-duration", type=float, default=DURATION)
    parser.add_argument("--preset", default="veryfast")
    parser.add_argument("--crf", default="18")
    parser.add_argument("--no-shorten-silence", action="store_true")
    parser.add_argument("--min-silence", type=float, default=DEFAULT_MIN_SILENCE)
    parser.add_argument("--keep-silence", type=float, default=DEFAULT_KEEP_SILENCE)
    parser.add_argument("--silence-noise", default=DEFAULT_NOISE)
    parser.add_argument("--keep-uncut", action="store_true")
    parser.add_argument("--no-audio-denoise", action="store_true", help="Disable afftdn background-noise reduction.")
    parser.add_argument("--audio-denoise-strength", type=int, default=DEFAULT_DENOISE_STRENGTH)
    parser.add_argument(
        "--omit-interviewer-question",
        action="store_true",
        help="Replace the offscreen interviewer question with a 5-second summary card and sound effect.",
    )
    parser.add_argument(
        "--auto-context-cuts",
        dest="auto_context_cuts",
        action="store_true",
        default=True,
        help="Use subtitle speaker roles and answer context to choose camera changes.",
    )
    parser.add_argument(
        "--no-auto-context-cuts",
        dest="auto_context_cuts",
        action="store_false",
        help="Use the simple fixed camera plan without subtitle-context camera changes.",
    )
    parser.add_argument(
        "--natural-dialogue-cuts",
        dest="natural_dialogue_cuts",
        action="store_true",
        default=False,
        help="Move short camera-change points into nearby low-energy dialogue gaps without shortening the audio.",
    )
    parser.add_argument(
        "--no-natural-dialogue-cuts",
        dest="natural_dialogue_cuts",
        action="store_false",
        help="Keep context camera-change points at exact subtitle/context boundaries.",
    )
    parser.add_argument(
        "--dynamic-cuts",
        action="store_true",
        help="Use a faster edit with rhythmic punch-ins and reframes while keeping source sync and audio intact.",
    )
    parser.add_argument(
        "--term-explanations",
        dest="term_explanations",
        action="store_true",
        default=True,
        help="Show glossary popups for uncommon/specialized terms detected from the subtitles.",
    )
    parser.add_argument(
        "--no-term-explanations",
        dest="term_explanations",
        action="store_false",
        help="Disable glossary popups.",
    )
    return parser.parse_args()


def youtube_audio_filter(args: argparse.Namespace) -> str:
    parts = ["highpass=f=80"]
    if not args.no_audio_denoise:
        nr = max(0, min(30, int(args.audio_denoise_strength)))
        if nr > 0:
            parts.append(f"afftdn=nr={nr}:nf=-35")
    parts.extend(
        [
            "dynaudnorm=f=250:g=15:p=0.95:m=8",
            "acompressor=threshold=-20dB:ratio=2.8:attack=5:release=120:makeup=4",
            "loudnorm=I=-14:TP=-1.5:LRA=9",
        ]
    )
    return ",".join(parts)


def cam1_rgb_gain() -> tuple[float, float, float]:
    b_gain, g_gain, r_gain = CAM1_SKIN_GAIN
    return tuple(1.0 + (gain - 1.0) * CAM1_SKIN_GAIN_STRENGTH for gain in (r_gain, g_gain, b_gain))


def draw_centered_text(
    draw: ImageDraw.ImageDraw,
    y: int,
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int, int],
) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    x = round((1920 - (bbox[2] - bbox[0])) / 2)
    draw.text((x - bbox[0], y - bbox[1]), text, font=font, fill=fill)
    return y + (bbox[3] - bbox[1])


def text_visual_height(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[3] - bbox[1]


def generate_summary_card() -> None:
    canvas = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, 1920, 1080), fill=(0, 0, 0, 92))
    panel = (190, 260, 1730, 800)
    draw.rounded_rectangle(panel, radius=34, fill=(12, 16, 24, 218), outline=(255, 255, 255, 120), width=3)
    draw.rectangle((190, 765, 1730, 800), fill=(174, 72, 224, 220))

    main_font = ImageFont.truetype(str(FONT_PATH), 92, index=1)
    sub_font = ImageFont.truetype(str(FONT_PATH), 86, index=1)
    line_gap = 34
    block_height = (
        text_visual_height(draw, SUMMARY_LINES[0], main_font)
        + line_gap
        + text_visual_height(draw, SUMMARY_LINES[1], sub_font)
    )
    y = panel[1] + round(((panel[3] - panel[1]) - block_height) / 2)
    y = draw_centered_text(draw, y, SUMMARY_LINES[0], main_font, (255, 255, 255, 255)) + line_gap
    draw_centered_text(draw, y, SUMMARY_LINES[1], sub_font, (255, 255, 255, 255))
    canvas.save(SUMMARY_CARD)


def camera_crop_filter(crop: float, x_bias: float = 0.5, y_bias: float = 0.5) -> str:
    crop = max(0.55, min(1.0, crop))
    x_bias = max(0.0, min(1.0, x_bias))
    y_bias = max(0.0, min(1.0, y_bias))
    return (
        f"crop=w='iw*{crop:.6f}':h='ih*{crop:.6f}':"
        f"x='(iw-ow)*{x_bias:.6f}':y='(ih-oh)*{y_bias:.6f}',scale=1920:1080"
    )


def natural_dialogue_cut_time(
    sound: Path,
    sound_offset: float,
    planned_time: float,
    *,
    search_before: float = 0.25,
    search_after: float = 0.05,
    sample_rate: int = 8000,
    window_seconds: float = 0.08,
    hop_seconds: float = 0.02,
) -> tuple[float, dict[str, object]]:
    search_start = max(0.0, planned_time - search_before)
    duration = search_before + search_after
    command = [
        str(FFMPEG),
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{sound_offset + search_start:.6f}",
        "-t",
        f"{duration:.6f}",
        "-i",
        str(sound),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "s16le",
        "pipe:1",
    ]
    completed = subprocess.run(command, cwd=WORK, check=True, capture_output=True)
    raw = completed.stdout
    samples = [
        int.from_bytes(raw[index : index + 2], "little", signed=True) / 32768.0
        for index in range(0, len(raw) - 1, 2)
    ]
    window = max(1, round(window_seconds * sample_rate))
    hop = max(1, round(hop_seconds * sample_rate))
    windows: list[dict[str, float]] = []
    for index in range(0, max(0, len(samples) - window + 1), hop):
        chunk = samples[index : index + window]
        rms = math.sqrt(sum(value * value for value in chunk) / len(chunk))
        center = search_start + (index + (window / 2.0)) / sample_rate
        windows.append({"center": center, "rms": rms})

    if not windows:
        return planned_time, {"planned": planned_time, "chosen": planned_time, "reason": "no_audio_windows"}

    best = min(windows, key=lambda item: (item["rms"], abs(item["center"] - planned_time)))
    chosen = round(float(best["center"]), 3)
    return chosen, {
        "planned": planned_time,
        "chosen": chosen,
        "shift": round(chosen - planned_time, 3),
        "search_start": search_start,
        "search_end": search_start + duration,
        "window_seconds": window_seconds,
        "best_rms": best["rms"],
    }


def render(args: argparse.Namespace) -> Path:
    if args.omit_interviewer_question and (args.preview_start != 0.0 or args.preview_duration < DURATION):
        raise RuntimeError("--omit-interviewer-question currently supports full-range renders only")
    if args.dynamic_cuts and (
        args.omit_interviewer_question
        or args.preview_start != 0.0
        or args.preview_duration < DURATION
    ):
        raise RuntimeError("--dynamic-cuts currently supports normal full-range renders only")
    config = MODES[args.mode]
    if not args.skip_subtitle_regeneration:
        run([sys.executable, str(SCRIPTS / "generate_title_png_overlay.py")])
        if args.mode != "none":
            run([sys.executable, str(config["generator"])])
        if args.term_explanations:
            run([sys.executable, str(SCRIPTS / "generate_glossary_term_overlays.py")])
    if args.term_explanations and not GLOSSARY_MANIFEST.exists():
        run([sys.executable, str(SCRIPTS / "generate_glossary_term_overlays.py")])
    if args.omit_interviewer_question:
        generate_summary_card()
        if not OMIT_SUMMARY_MUSIC.exists():
            run([sys.executable, str(SCRIPTS / "generate_omit_summary_music.py")])

    output = args.output or default_render_output(args)
    output.parent.mkdir(parents=True, exist_ok=True)
    render_output = output
    should_shorten = (
        not args.omit_interviewer_question
        and not args.no_shorten_silence
        and args.preview_start == 0.0
        and args.preview_duration >= DURATION
    )
    if should_shorten:
        render_output = output.with_name(f"{output.stem}_uncut{output.suffix}")
    offset_data = json.loads(SOUND_OFFSET.read_text(encoding="utf-8"))
    sound = resolve_project_path(offset_data["sound_file"])
    sound_offset = float(offset_data["refined_offset"])
    sound_start = sound_offset + args.preview_start
    source_end = OMIT_ANSWER_END if args.omit_interviewer_question else args.preview_start + args.preview_duration
    input_duration = source_end - args.preview_start
    preview_end = source_end
    late_cam2_switch = LATE_CAM2_SWITCH
    natural_cut_report: dict[str, object] = {"enabled": False}
    if args.auto_context_cuts and args.natural_dialogue_cuts and not args.dynamic_cuts and preview_end > LATE_CAM2_SWITCH:
        late_cam2_switch, natural_cut_report = natural_dialogue_cut_time(sound, sound_offset, LATE_CAM2_SWITCH)
        natural_cut_report["enabled"] = True
        natural_cut_report["cut"] = "late_interviewee_answer_camera2"
        natural_cut_report["note"] = "Camera switch only; audio timing is not shortened."
    captions = []
    if args.mode != "none":
        captions = [
            item
            for item in json.loads(Path(config["manifest"]).read_text(encoding="utf-8"))
            if seconds(item["start"]) < preview_end and seconds(item["end"]) > args.preview_start
        ]
        if args.omit_interviewer_question:
            shifted = []
            for item in captions:
                start = seconds(item["start"])
                end = seconds(item["end"])
                if OMIT_INTERVIEWER_START <= start < OMIT_INTERVIEWER_END:
                    continue
                copy = dict(item)
                if start >= OMIT_INTERVIEWER_END:
                    shift = OMIT_INTERVIEWER_END - (OMIT_INTERVIEWER_START + OMIT_SUMMARY_DURATION)
                    copy["start"] = f"0:00:{start - shift:06.3f}"
                    copy["end"] = f"0:00:{min(OMIT_OUTPUT_DURATION, end - shift):06.3f}"
                shifted.append(copy)
            captions = shifted

    glossary_items = []
    if args.term_explanations:
        glossary_items = [
            item
            for item in json.loads(GLOSSARY_MANIFEST.read_text(encoding="utf-8"))
            if seconds(item["start"]) < preview_end and seconds(item["end"]) > args.preview_start
        ]
        if args.omit_interviewer_question:
            shifted_glossary = []
            for item in glossary_items:
                start = seconds(item["start"])
                end = seconds(item["end"])
                if OMIT_INTERVIEWER_START <= start < OMIT_INTERVIEWER_END:
                    continue
                copy = dict(item)
                if start >= OMIT_INTERVIEWER_END:
                    shift = OMIT_INTERVIEWER_END - (OMIT_INTERVIEWER_START + OMIT_SUMMARY_DURATION)
                    copy["start"] = f"0:00:{start - shift:06.3f}"
                    copy["end"] = f"0:00:{min(OMIT_OUTPUT_DURATION, end - shift):06.3f}"
                shifted_glossary.append(copy)
            glossary_items = shifted_glossary

    cam2_input_start = CAM2_SOURCE_OFFSET + min(args.preview_start, 20.0)
    cam1_input_start = CAM1_SOURCE_OFFSET + max(args.preview_start - 20.0, 0.0)
    command = [
        str(FFMPEG),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{cam2_input_start:.6f}",
        "-t",
        f"{input_duration:.6f}",
        "-i",
        str(CAM2_7192),
        "-ss",
        f"{cam1_input_start:.6f}",
        "-t",
        f"{input_duration:.6f}",
        "-i",
        str(CAM1),
        "-i",
        str(LOGO),
        "-i",
        str(TITLE),
    ]
    if args.omit_interviewer_question:
        command.extend(["-loop", "1", "-framerate", "60", "-t", f"{OMIT_SUMMARY_DURATION:.3f}", "-i", str(SUMMARY_CARD)])
    for item in captions:
        command.extend(["-loop", "1", "-framerate", "60", "-t", f"{args.preview_duration:.3f}", "-i", str(WORK / item["file"])])
    summary_input_count = 1 if args.omit_interviewer_question else 0
    first_caption_input = 4 + summary_input_count
    first_glossary_input = first_caption_input + len(captions)
    for item in glossary_items:
        command.extend(["-loop", "1", "-framerate", "60", "-t", f"{args.preview_duration:.3f}", "-i", str(WORK / item["file"])])
    sound_index = first_glossary_input + len(glossary_items)
    command.extend(["-ss", f"{sound_start:.6f}", "-t", f"{input_duration:.6f}", "-i", str(sound)])
    music_index = sound_index + 1
    if args.omit_interviewer_question:
        command.extend(["-i", str(OMIT_SUMMARY_MUSIC)])
    late_cam2_index = sound_index + (2 if args.omit_interviewer_question else 1)
    if args.auto_context_cuts and not args.dynamic_cuts and preview_end > late_cam2_switch:
        late_input_master_start = max(args.preview_start, late_cam2_switch)
        late_input_start = late_input_master_start + CAM2_7193_SOURCE_OFFSET
        late_input_duration = max(0.1, preview_end - late_input_master_start)
        command.extend(["-ss", f"{late_input_start:.6f}", "-t", f"{late_input_duration:.6f}", "-i", str(CAM2_7193)])

    r_gain, g_gain, b_gain = cam1_rgb_gain()
    filters = []
    video_segments: list[str] = []
    if args.omit_interviewer_question and args.auto_context_cuts:
        timeline_segments = [
            {"camera": "2cam", "input_index": 0, "start": 0.0, "end": 20.0, "local_start": 0.0, "local_end": 20.0},
            {"camera": "summary", "input_index": 1, "start": 20.0, "end": 25.0, "local_start": 0.0, "local_end": OMIT_SUMMARY_DURATION},
            {"camera": "1cam", "input_index": 1, "start": 57.0, "end": late_cam2_switch, "local_start": 37.0, "local_end": late_cam2_switch - CAM1_SOURCE_OFFSET},
            {"camera": "2cam", "input_index": late_cam2_index, "start": late_cam2_switch, "end": OMIT_ANSWER_END, "crop": 0.86, "x": 0.55, "y": 0.08},
        ]
    elif args.omit_interviewer_question:
        timeline_segments = [
            {"camera": "2cam", "input_index": 0, "start": 0.0, "end": 20.0, "local_start": 0.0, "local_end": 20.0},
            {"camera": "summary", "input_index": 1, "start": 20.0, "end": 25.0, "local_start": 0.0, "local_end": OMIT_SUMMARY_DURATION},
            {"camera": "1cam", "input_index": 1, "start": 57.0, "end": OMIT_ANSWER_END, "local_start": 37.0, "local_end": OMIT_ANSWER_END - CAM1_SOURCE_OFFSET},
        ]
    elif args.dynamic_cuts:
        timeline_segments = DYNAMIC_TIMELINE_SEGMENTS
    elif args.auto_context_cuts:
        timeline_segments = [
            {"camera": "2cam", "input_index": 0, "start": 0.0, "end": 20.0},
            {"camera": "1cam", "input_index": 1, "start": 20.0, "end": late_cam2_switch},
            {"camera": "2cam", "input_index": late_cam2_index, "start": late_cam2_switch, "end": DURATION, "crop": 0.86, "x": 0.55, "y": 0.08},
        ]
    else:
        timeline_segments = [
            {"camera": "2cam", "input_index": 0, "start": 0.0, "end": 20.0},
            {"camera": "1cam", "input_index": 1, "start": 20.0, "end": DURATION},
        ]
    for segment_index, segment in enumerate(timeline_segments):
        camera = str(segment["camera"])
        input_index = int(segment["input_index"])
        start_t = float(segment["start"])
        end_t = float(segment["end"])
        start = max(args.preview_start, start_t)
        end = min(preview_end, end_t)
        if end <= start:
            continue
        if "local_start" in segment:
            local_start = float(segment["local_start"]) + (start - start_t)
            local_end = float(segment["local_end"]) - (end_t - end)
        elif args.omit_interviewer_question:
            local_start = 0.0
            local_end = end - start
        else:
            local_start = 0.0
            local_end = end - start
        label = f"vseg{segment_index}"
        crop_filter = camera_crop_filter(
            float(segment.get("crop", CAMERA_CENTER_CROP)),
            float(segment.get("x", 0.5)),
            float(segment.get("y", 0.5)),
        )
        if camera in {"1cam", "summary"}:
            filters.append(
                f"[{input_index}:v]trim=start={local_start:.6f}:end={local_end:.6f},setpts=PTS-STARTPTS,{crop_filter},"
                f"colorchannelmixer=rr={r_gain:.6f}:gg={g_gain:.6f}:bb={b_gain:.6f},"
                f"eq=saturation={CAM1_SATURATION_SCALE:.6f}[{label}]"
            )
            if camera == "summary":
                card_input = 4
                card_label = f"card{segment_index}"
                filters.append(f"[{card_input}:v]format=rgba,setpts=PTS-STARTPTS[{card_label}]")
                summary_label = f"vsummary{segment_index}"
                filters.append(f"[{label}][{card_label}]overlay=0:0:enable='between(t,0,{OMIT_SUMMARY_DURATION:.3f})'[{summary_label}]")
                label = summary_label
        else:
            r2_gain, g2_gain, b2_gain = CAM2_RGB_GAIN
            filters.append(
                f"[{input_index}:v]trim=start={local_start:.6f}:end={local_end:.6f},setpts=PTS-STARTPTS,{crop_filter},"
                f"colorchannelmixer=rr={r2_gain:.6f}:gg={g2_gain:.6f}:bb={b2_gain:.6f},"
                f"eq=saturation={CAM2_SATURATION_SCALE:.6f}[{label}]"
            )
        video_segments.append(label)
    if not video_segments:
        raise RuntimeError("Preview range does not overlap the 1-minute camera plan")
    if len(video_segments) == 1:
        filters.append(f"[{video_segments[0]}]copy[vbase]")
    else:
        filters.append("".join(f"[{label}]" for label in video_segments) + f"concat=n={len(video_segments)}:v=1:a=0[vbase]")
    filters.extend([
        f"[2:v]scale=-1:{LOGO_HEIGHT}[logo]",
        f"[vbase][logo]overlay=W-w-{LOGO_MARGIN_X}:{LOGO_MARGIN_Y}[vlogo]",
        f"[vlogo][3:v]overlay={TITLE_X}:{TITLE_Y}[vtitle]",
    ])
    current = "vtitle"
    for index, item in enumerate(captions, start=1):
        stream_index = first_caption_input + index - 1
        start = max(0.0, seconds(item["start"]) - args.preview_start)
        end = min(args.preview_duration, seconds(item["end"]) - args.preview_start)
        fade_out = max(start, end - 0.18)
        base_scale = "if(gt(iw,1760),1760/iw,1)"
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
            filters.append(f"[{stream_index}:v]format=rgba,scale=w='iw*{base_scale}':h='ih*{base_scale}':eval=init[p{index}]")
        next_stream = f"vsub{index}"
        filters.append(f"[{current}][p{index}]overlay=x='(W-w)/2':y='{y_expr}':enable='between(t,{start:.3f},{end:.3f})'[{next_stream}]")
        current = next_stream

    for index, item in enumerate(glossary_items, start=1):
        stream_index = first_glossary_input + index - 1
        start = max(0.0, seconds(item["start"]) - args.preview_start)
        end = min(args.preview_duration, seconds(item["end"]) - args.preview_start)
        fade_out = max(start, end - 0.18)
        y_expr = (
            f"150+if(between(t,{start:.3f},{start + 0.24:.3f}),"
            f"24*(1-(t-{start:.3f})/0.24),0)"
        )
        filters.append(
            f"[{stream_index}:v]format=rgba,"
            f"fade=t=in:st={start:.3f}:d=0.15:alpha=1,"
            f"fade=t=out:st={fade_out:.3f}:d=0.18:alpha=1[g{index}]"
        )
        next_stream = f"vglossary{index}"
        filters.append(
            f"[{current}][g{index}]overlay=x='W-w-36':y='{y_expr}':"
            f"enable='between(t,{start:.3f},{end:.3f})'[{next_stream}]"
        )
        current = next_stream

    audio_filter = youtube_audio_filter(args)
    if args.omit_interviewer_question:
        filters.extend(
            [
                f"[{sound_index}:a]atrim=start=0:end=20,asetpts=PTS-STARTPTS[a0]",
                f"[{sound_index}:a]atrim=start=57:end={OMIT_ANSWER_END:.6f},asetpts=PTS-STARTPTS[a1]",
                f"[{music_index}:a]atrim=start=0:end={OMIT_SUMMARY_DURATION:.3f},asetpts=PTS-STARTPTS,volume=0.52[aq]",
                f"[a0][aq][a1]concat=n=3:v=0:a=1,{audio_filter}[a]",
            ]
        )
    else:
        filters.append(f"[{sound_index}:a]asetpts=PTS-STARTPTS,{audio_filter}[a]")
    command.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            f"[{current}]",
            "-map",
            "[a]",
            "-dn",
            "-map_metadata",
            "-1",
            "-c:v",
            "libx264",
            "-preset",
            args.preset,
            "-crf",
            args.crf,
            "-pix_fmt",
            "yuv420p",
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
    )
    run(command)
    if natural_cut_report.get("enabled"):
        report_path = output.with_suffix(".natural_dialogue_cuts.json")
        report_path.write_text(json.dumps(natural_cut_report, ensure_ascii=False, indent=2), encoding="utf-8")
    if should_shorten:
        shorten_silences(
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
    return output


def main() -> None:
    output = render(parse_args())
    print(json.dumps({"output": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
