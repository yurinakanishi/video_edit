from __future__ import annotations

import argparse
import json
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

from PIL import Image, ImageDraw, ImageFont

from shorten_silences import DEFAULT_KEEP_SILENCE, DEFAULT_MIN_SILENCE, DEFAULT_NOISE, SilenceShortenConfig, shorten_silences
from video_edit_app_config import int_value, load_app_config, optional_path


WORK = WORKSPACE_ROOT
APP_CONFIG = load_app_config()
FFMPEG = optional_path(APP_CONFIG, "tools", "ffmpeg", default=Path(r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"))
CAM1 = SOURCE_VIDEO / "1cam" / "ST7_7550_overlap_5min.mp4"
CAM2_7192 = multicam_source_root() / "2cam" / "0H4A7192.MP4"
LOGO = optional_path(APP_CONFIG, "assets", "logo", default=SOURCE_IMAGES / "type-logo-transparent-cropped.png")
TITLE = OUTPUT_OVERLAYS / "ai_engineer_now_title.png"
SUMMARY_CARD = OUTPUT_OVERLAYS / "interviewer_question_summary_card.png"
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


def seconds(timestamp: str) -> float:
    hours, minutes, rest = timestamp.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(rest)


def run(command: list[str]) -> None:
    subprocess.run(command, check=True, cwd=WORK)


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


def generate_summary_card() -> None:
    canvas = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, 1920, 1080), fill=(0, 0, 0, 92))
    panel = (190, 260, 1730, 800)
    draw.rounded_rectangle(panel, radius=34, fill=(12, 16, 24, 218), outline=(255, 255, 255, 120), width=3)
    draw.rectangle((190, 765, 1730, 800), fill=(174, 72, 224, 220))

    main_font = ImageFont.truetype(str(FONT_PATH), 92, index=1)
    sub_font = ImageFont.truetype(str(FONT_PATH), 86, index=1)
    y = 380
    y = draw_centered_text(draw, y, SUMMARY_LINES[0], main_font, (255, 255, 255, 255)) + 34
    draw_centered_text(draw, y, SUMMARY_LINES[1], sub_font, (255, 255, 255, 255))
    canvas.save(SUMMARY_CARD)


def render(args: argparse.Namespace) -> Path:
    if args.omit_interviewer_question and (args.preview_start != 0.0 or args.preview_duration < DURATION):
        raise RuntimeError("--omit-interviewer-question currently supports full-range renders only")
    config = MODES[args.mode]
    if not args.skip_subtitle_regeneration:
        run([sys.executable, str(SCRIPTS / "generate_title_png_overlay.py")])
        if args.mode == "full":
            run([sys.executable, str(SCRIPTS / "apply_st7_7550_subtitle_corrections.py")])
        if args.mode != "none":
            run([sys.executable, str(config["generator"])])
    if args.omit_interviewer_question:
        generate_summary_card()

    output = args.output or Path(config["output"])
    if args.omit_interviewer_question and args.output is None:
        output = output.with_name(f"{output.stem}_omit_interviewer{output.suffix}")
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
    sound_start = float(offset_data["refined_offset"]) + args.preview_start
    source_end = OMIT_ANSWER_END if args.omit_interviewer_question else args.preview_start + args.preview_duration
    input_duration = source_end - args.preview_start
    preview_end = source_end
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
    sound_index = first_caption_input + len(captions)
    command.extend(["-ss", f"{sound_start:.6f}", "-t", f"{input_duration:.6f}", "-i", str(sound)])

    r_gain, g_gain, b_gain = cam1_rgb_gain()
    camera_crop_filter = (
        f"crop=w='iw*{CAMERA_CENTER_CROP:.6f}':h='ih*{CAMERA_CENTER_CROP:.6f}':"
        "x='(iw-ow)/2':y='(ih-oh)/2',scale=1920:1080"
    )
    filters = []
    video_segments: list[str] = []
    if args.omit_interviewer_question:
        timeline_segments = [
            ("2cam", 0, 0.0, 20.0, 0.0, 20.0),
            ("summary", 1, 20.0, 25.0, 0.0, OMIT_SUMMARY_DURATION),
            ("1cam", 1, 57.0, OMIT_ANSWER_END, 37.0, OMIT_ANSWER_END - CAM1_SOURCE_OFFSET),
        ]
    else:
        timeline_segments = [
            ("2cam", 0, 0.0, 20.0, 0.0, 20.0),
            ("1cam", 1, 20.0, 60.0, 0.0, 40.0),
        ]
    for segment_index, (camera, input_index, start_t, end_t, local_source_start, local_source_end) in enumerate(timeline_segments):
        start = max(args.preview_start, start_t)
        end = min(preview_end, end_t)
        if end <= start:
            continue
        if args.omit_interviewer_question:
            local_start = local_source_start
            local_end = local_source_end
        else:
            local_start = 0.0
            local_end = end - start
        label = f"vseg{segment_index}"
        if camera in {"1cam", "summary"}:
            filters.append(
                f"[{input_index}:v]setpts=PTS-STARTPTS,{camera_crop_filter},"
                f"colorchannelmixer=rr={r_gain:.6f}:gg={g_gain:.6f}:bb={b_gain:.6f},"
                f"eq=saturation={CAM1_SATURATION_SCALE:.6f},"
                f"trim=start={local_start:.6f}:end={local_end:.6f},setpts=PTS-STARTPTS[{label}]"
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
                f"[{input_index}:v]setpts=PTS-STARTPTS,{camera_crop_filter},"
                f"colorchannelmixer=rr={r2_gain:.6f}:gg={g2_gain:.6f}:bb={b2_gain:.6f},"
                f"eq=saturation={CAM2_SATURATION_SCALE:.6f},"
                f"trim=start={local_start:.6f}:end={local_end:.6f},setpts=PTS-STARTPTS[{label}]"
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

    audio_filter = youtube_audio_filter(args)
    if args.omit_interviewer_question:
        filters.extend(
            [
                f"[{sound_index}:a]atrim=start=0:end=20,asetpts=PTS-STARTPTS[a0]",
                f"[{sound_index}:a]atrim=start=57:end={OMIT_ANSWER_END:.6f},asetpts=PTS-STARTPTS[a1]",
                f"aevalsrc=0:d={OMIT_SUMMARY_DURATION:.3f}:s=48000[sil]",
                f"sine=frequency=196:duration={OMIT_SUMMARY_DURATION:.3f}:sample_rate=48000,volume=0.030,afade=t=in:st=0:d=0.25,afade=t=out:st=4.35:d=0.65[music1]",
                f"sine=frequency=294:duration={OMIT_SUMMARY_DURATION:.3f}:sample_rate=48000,volume=0.022,afade=t=in:st=0:d=0.25,afade=t=out:st=4.35:d=0.65[music2]",
                f"sine=frequency=392:duration={OMIT_SUMMARY_DURATION:.3f}:sample_rate=48000,volume=0.018,afade=t=in:st=0:d=0.25,afade=t=out:st=4.35:d=0.65[music3]",
                "sine=frequency=880:duration=0.14:sample_rate=48000,volume=0.18,adelay=80|80[sfx1]",
                "sine=frequency=1320:duration=0.18:sample_rate=48000,volume=0.12,adelay=180|180[sfx2]",
                "[sil][music1][music2][music3][sfx1][sfx2]amix=inputs=6:duration=first[aq]",
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
