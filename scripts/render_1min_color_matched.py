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

import cv2
import numpy as np

from shorten_silences import DEFAULT_KEEP_SILENCE, DEFAULT_MIN_SILENCE, DEFAULT_NOISE, SilenceShortenConfig, shorten_silences
from video_edit_app_config import int_value, load_app_config, optional_path


WORK = WORKSPACE_ROOT
APP_CONFIG = load_app_config()
FFMPEG = optional_path(APP_CONFIG, "tools", "ffmpeg", default=Path(r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"))
FFPROBE = optional_path(APP_CONFIG, "tools", "ffprobe", default=Path(r"C:\ProgramData\chocolatey\bin\ffprobe.exe"))
BASE_5MIN = OUTPUT_VIDEOS / "ST7_7550_multicam_cut_5min_strong_transcript_wave_refined.mp4"
BASE_1MIN = OUTPUT_VIDEOS / "ST7_7550_multicam_cut_1min_color_matched_base.mp4"
CAM1 = SOURCE_VIDEO / "1cam" / "ST7_7550_overlap_5min.mp4"
CAM2_7192 = multicam_source_root() / "2cam" / "0H4A7192.MP4"
LOGO = optional_path(APP_CONFIG, "assets", "logo", default=SOURCE_IMAGES / "type-logo-transparent-cropped.png")
TITLE = OUTPUT_OVERLAYS / "ai_engineer_now_title.png"
LOGO_HEIGHT = int_value(APP_CONFIG, "style", "logoHeight", default=48)
SOUND_OFFSET = OUTPUT_TRANSCRIPTS / "sound2" / "sound2_audio_offset_refined.json"
SPEAKER_ROLES = OUTPUT_REPORTS / "full_transcript_speaker_roles.json"

MODES = {
    "none": {
        "generator": None,
        "manifest": None,
        "output": OUTPUT_VIDEOS / "ST7_7550_multicam_cut_1min_multi_cut_sound2_audio_color_matched_no_subtitles.mp4",
        "bottom_margin": 16,
        "slide_px": 0,
        "pop": False,
        "animate": False,
    },
    "punchline": {
        "generator": SCRIPTS / "generate_punchline_png_overlays.py",
        "manifest": OUTPUT_OVERLAYS / "punchline_png_overlays" / "manifest.json",
        "output": OUTPUT_VIDEOS / "ST7_7550_multicam_cut_1min_multi_cut_sound2_audio_color_matched.mp4",
        "bottom_margin": 12,
        "slide_px": 44,
        "pop": True,
        "animate": True,
    },
    "full": {
        "generator": SCRIPTS / "generate_full_transcript_png_overlays.py",
        "manifest": OUTPUT_OVERLAYS / "full_transcript_png_overlays" / "manifest.json",
        "output": OUTPUT_VIDEOS / "ST7_7550_multicam_cut_1min_multi_cut_sound2_audio_color_matched_full_transcript.mp4",
        "bottom_margin": 16,
        "slide_px": 0,
        "pop": False,
        "animate": False,
    },
}

FPS = 60000 / 1001
WIDTH = 1920
HEIGHT = 1080
DURATION = 60.0
DEFAULT_DENOISE_STRENGTH = 10
CAM2_SOURCE_OFFSET = 1102.710
CAMERA_PLAN = [
    {
        "camera": "2cam",
        "timeline_start": 0.0,
        "timeline_end": 20.0,
        "video_path": CAM2_7192,
        "video_start": CAM2_SOURCE_OFFSET,
        "reason": "onscreen speaker answer; use zoom",
    },
    {
        "camera": "1cam",
        "timeline_start": 20.0,
        "timeline_end": 60.0,
        "video_path": CAM1,
        "video_start": 20.0,
        "reason": "offscreen interviewer turn; keep wide through final short answer to avoid a 3-second end cut",
    },
]
REF_WALL_ROI = (160, 160, 860, 700)
TARGET_WALL_ROI = (80, 140, 780, 700)
WB_STRENGTH = 1.0
SATURATION_SCALE = 0.75
SHADOW_BLUE_REDUCTION = 0.12
CAM1_TO_CAM2_SKIN_GAIN = np.array([0.90265487, 0.93055556, 0.95431472], dtype=np.float32)
CAM1_SKIN_GAIN_STRENGTH = 0.82
CAM1_SATURATION_SCALE = 0.94


def run(command: list[str]) -> None:
    subprocess.run(command, check=True, cwd=WORK)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render the 1-minute color-matched edit with selectable subtitles.")
    parser.add_argument(
        "--mode",
        choices=sorted(MODES),
        default="full",
        help="Subtitle mode. full renders every caption; punchline renders selected punchlines.",
    )
    parser.add_argument(
        "--rebuild-base",
        action="store_true",
        help="Rebuild the color-matched base video. This is slow; use only after camera/color/timing changes.",
    )
    parser.add_argument(
        "--skip-base",
        action="store_true",
        help="Deprecated compatibility flag. Base reuse is now the default.",
    )
    parser.add_argument(
        "--reclassify-speakers",
        action="store_true",
        help="Re-run OpenCV speaker diagnostics. By default existing full_transcript_speaker_roles.json is reused.",
    )
    parser.add_argument(
        "--skip-subtitle-regeneration",
        action="store_true",
        help="Reuse existing PNG subtitle overlays and manifest.",
    )
    parser.add_argument("--output", type=Path, help="Optional output path override.")
    parser.add_argument("--duration", type=float, default=DURATION, help="Rendered output length in seconds before optional silence shortening. Max 60 for this preset.")
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


def seconds(timestamp: str) -> float:
    hours, minutes, rest = timestamp.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(rest)


def audio_cleanup_filter(strength: int) -> str:
    nr = max(0, min(30, int(strength)))
    if nr <= 0:
        return "highpass=f=80"
    return f"highpass=f=80,afftdn=nr={nr}:nf=-35"


def grab_frame(video: Path, t: float) -> np.ndarray:
    cap = cv2.VideoCapture(str(video))
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise RuntimeError(f"Could not read frame at {t:.3f}s")
    return frame


def wall_samples(frame: np.ndarray, roi: tuple[int, int, int, int]) -> np.ndarray:
    x1, y1, x2, y2 = roi
    crop = frame[y1:y2, x1:x2]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    # Use bright, low/mid-saturation wall pixels shared by both camera angles.
    mask = (hsv[:, :, 1] < 90) & (hsv[:, :, 2] > 115) & (hsv[:, :, 2] < 245)
    samples = crop[mask]
    if len(samples) < 1000:
        samples = crop.reshape(-1, 3)
    return samples.astype(np.float32)


def wall_stats_for(video: Path, times: list[float], roi: tuple[int, int, int, int]) -> tuple[np.ndarray, np.ndarray]:
    samples = [wall_samples(grab_frame(video, t), roi) for t in times]
    merged = np.concatenate(samples, axis=0)
    mean = merged.mean(axis=0)
    std = merged.std(axis=0)
    std[std < 1.0] = 1.0
    return mean, std


def match_camera_grade(frame: np.ndarray, ref_wall_mean: np.ndarray, target_wall_mean: np.ndarray) -> np.ndarray:
    gain = ref_wall_mean / target_wall_mean
    mixed_gain = 1.0 + (gain - 1.0) * WB_STRENGTH
    corrected = frame.astype(np.float32) * mixed_gain.reshape(1, 1, 3)

    # The 2cam source has a blue cast in dark hair/jacket shadows. Reduce it
    # only in darker tones so the bright wood wall stays the matching anchor.
    luma = cv2.cvtColor(np.clip(corrected, 0, 255).astype(np.uint8), cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    shadow_mask = np.clip((0.72 - luma) / 0.72, 0.0, 1.0)
    corrected[:, :, 0] *= 1.0 - SHADOW_BLUE_REDUCTION * shadow_mask
    corrected = np.clip(corrected, 0, 255).astype(np.uint8)

    hsv = cv2.cvtColor(corrected, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[:, :, 1] *= SATURATION_SCALE
    corrected = cv2.cvtColor(np.clip(hsv, 0, 255).astype(np.uint8), cv2.COLOR_HSV2BGR)
    return corrected


def match_cam1_to_cam2_skin(frame: np.ndarray) -> np.ndarray:
    gain = 1.0 + (CAM1_TO_CAM2_SKIN_GAIN - 1.0) * CAM1_SKIN_GAIN_STRENGTH
    corrected = frame.astype(np.float32) * gain.reshape(1, 1, 3)
    corrected = np.clip(corrected, 0, 255).astype(np.uint8)

    hsv = cv2.cvtColor(corrected, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[:, :, 1] *= CAM1_SATURATION_SCALE
    return cv2.cvtColor(np.clip(hsv, 0, 255).astype(np.uint8), cv2.COLOR_HSV2BGR)


def make_color_matched_base() -> dict:
    ref_times = [24.0, 34.0, 46.0, 56.0]
    target_times = [CAM2_SOURCE_OFFSET + t for t in [2.0, 5.5, 9.5, 14.0, 18.5]]
    ref_wall_mean, ref_wall_std = wall_stats_for(CAM1, ref_times, REF_WALL_ROI)
    target_wall_mean, target_wall_std = wall_stats_for(CAM2_7192, target_times, TARGET_WALL_ROI)

    total_frames = int(round(DURATION * FPS))
    command = [
        str(FFMPEG),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "-s",
        f"{WIDTH}x{HEIGHT}",
        "-r",
        "60000/1001",
        "-i",
        "-",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        str(BASE_1MIN),
    ]
    proc = subprocess.Popen(command, cwd=WORK, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    written_frames = 0
    for segment in CAMERA_PLAN:
        cap = cv2.VideoCapture(str(segment["video_path"]))
        cap.set(cv2.CAP_PROP_POS_MSEC, float(segment["video_start"]) * 1000)
        segment_frames = int(round((float(segment["timeline_end"]) - float(segment["timeline_start"])) * FPS))
        for _ in range(segment_frames):
            if written_frames >= total_frames:
                break
            ok, frame = cap.read()
            if not ok:
                break
            if frame.shape[1] != WIDTH or frame.shape[0] != HEIGHT:
                frame = cv2.resize(frame, (WIDTH, HEIGHT), interpolation=cv2.INTER_AREA)
            if segment["camera"] == "1cam":
                frame = match_cam1_to_cam2_skin(frame)
            proc.stdin.write(frame.tobytes())
            written_frames += 1
        cap.release()
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg failed while writing color-matched base")
    if written_frames < total_frames:
        raise RuntimeError(f"Only wrote {written_frames} of {total_frames} expected frames")

    report = {
        "camera_plan": [
            {
                "camera": str(item["camera"]),
                "timeline_start": item["timeline_start"],
                "timeline_end": item["timeline_end"],
                "video_path": str(item["video_path"]),
                "video_start": item["video_start"],
                "reason": item["reason"],
            }
            for item in CAMERA_PLAN
        ],
        "reference_times": ref_times,
        "target_times": target_times,
        "reference_wall_roi": list(REF_WALL_ROI),
        "target_wall_roi": list(TARGET_WALL_ROI),
        "reference_wall_bgr_mean": ref_wall_mean.tolist(),
        "reference_wall_bgr_std": ref_wall_std.tolist(),
        "target_wall_bgr_mean": target_wall_mean.tolist(),
        "target_wall_bgr_std": target_wall_std.tolist(),
        "legacy_2cam_to_1cam_bgr_gain": (ref_wall_mean / target_wall_mean).tolist(),
        "cam1_to_cam2_skin_bgr_gain": CAM1_TO_CAM2_SKIN_GAIN.tolist(),
        "cam1_skin_gain_strength": CAM1_SKIN_GAIN_STRENGTH,
        "cam1_saturation_scale": CAM1_SATURATION_SCALE,
        "white_balance_strength": 0.0,
        "saturation_scale": 1.0,
        "shadow_blue_reduction": 0.0,
        "corrected_ranges": [
            [item["timeline_start"], item["timeline_end"]]
            for item in CAMERA_PLAN
            if item["camera"] == "1cam"
        ],
    }
    (OUTPUT_REPORTS / "color_match_1min_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def render_overlays_and_sound(
    mode: str,
    output: Path,
    *,
    duration: float = DURATION,
    audio_denoise: bool = True,
    audio_denoise_strength: int = DEFAULT_DENOISE_STRENGTH,
    reclassify_speakers: bool = False,
    regenerate_subtitles: bool = True,
) -> None:
    config = MODES[mode]
    run([sys.executable, str(SCRIPTS / "generate_title_png_overlay.py")])
    if mode == "none":
        regenerate_subtitles = False
    if regenerate_subtitles and mode == "full":
        run([sys.executable, str(SCRIPTS / "apply_st7_7550_subtitle_corrections.py")])
        if reclassify_speakers or not SPEAKER_ROLES.exists():
            run([sys.executable, str(SCRIPTS / "classify_full_transcript_speakers.py")])
    if regenerate_subtitles:
        run([sys.executable, str(config["generator"])])
    offset_data = json.loads(SOUND_OFFSET.read_text(encoding="utf-8"))
    sound = resolve_project_path(offset_data["sound_file"])
    sound_start = float(offset_data["refined_offset"])

    captions = []
    if mode != "none":
        captions = [
            item
            for item in json.loads(Path(config["manifest"]).read_text(encoding="utf-8"))
            if seconds(item["start"]) < duration
        ]
    command = [
        str(FFMPEG),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(BASE_1MIN),
        "-i",
        str(LOGO),
        "-i",
        str(TITLE),
    ]
    for item in captions:
        command.extend(["-loop", "1", "-framerate", "60", "-t", f"{duration:.3f}", "-i", str(WORK / item["file"])])
    sound_index = 3 + len(captions)
    command.extend(["-i", str(sound)])

    filters = [
        f"[1:v]scale=-1:{LOGO_HEIGHT}[logo]",
        "[0:v][logo]overlay=W-w-40:40[v1]",
        "[v1][2:v]overlay=42:42[v2]",
    ]
    current = "v2"
    for index, item in enumerate(captions, start=1):
        stream_index = index + 2
        start = seconds(item["start"])
        end = min(seconds(item["end"]), duration)
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
            filters.append(
                f"[{stream_index}:v]format=rgba,"
                f"scale=w='iw*{base_scale}':h='ih*{base_scale}':eval=init[p{index}]"
            )
        next_stream = f"v{index + 2}"
        filters.append(
            f"[{current}][p{index}]overlay=x='(W-w)/2':y='{y_expr}':enable='between(t,{start:.3f},{end:.3f})'[{next_stream}]"
        )
        current = next_stream
    audio_filters = f"atrim=start={sound_start:.6f}:duration={duration:.6f},asetpts=PTS-STARTPTS"
    if audio_denoise:
        audio_filters += f",{audio_cleanup_filter(audio_denoise_strength)}"
    filters.append(f"[{sound_index}:a]{audio_filters}[a]")
    command.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            f"[{current}]",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
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
            "-t",
            f"{duration:.6f}",
            "-shortest",
            str(output),
        ]
    )
    run(command)


def main() -> None:
    args = parse_args()
    duration = max(0.1, min(float(args.duration), DURATION))
    report = make_color_matched_base() if args.rebuild_base else None
    output = args.output or Path(MODES[args.mode]["output"])
    output.parent.mkdir(parents=True, exist_ok=True)
    render_output = output
    if not args.no_shorten_silence:
        render_output = output.with_name(f"{output.stem}_uncut{output.suffix}")
    render_overlays_and_sound(
        args.mode,
        render_output,
        duration=duration,
        audio_denoise=not args.no_audio_denoise,
        audio_denoise_strength=args.audio_denoise_strength,
        reclassify_speakers=args.reclassify_speakers,
        regenerate_subtitles=not args.skip_subtitle_regeneration,
    )
    silence_report = None
    if not args.no_shorten_silence:
        silence_report = shorten_silences(
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
    print(
        json.dumps(
                {
                    "mode": args.mode,
                    "output": str(output),
                    "duration": duration,
                    "audio_denoise": not args.no_audio_denoise,
                    "report": report,
                    "silence_shortening": silence_report,
                },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
