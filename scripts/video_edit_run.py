from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from project_paths import OUTPUT_VIDEOS, ROOT as WORK, SCRIPTS
from video_edit_app_config import load_app_config, nested, optional_path


APP_CONFIG = load_app_config()
FFMPEG = optional_path(APP_CONFIG, "tools", "ffmpeg", default=Path(r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"))
FFPROBE = optional_path(APP_CONFIG, "tools", "ffprobe", default=Path(r"C:\ProgramData\chocolatey\bin\ffprobe.exe"))

SIMPLE_PYTHON_ACTIONS = {
    "generate-punchlines": "generate_punchline_png_overlays.py",
    "generate-full-overlays": "generate_full_transcript_png_overlays.py",
    "generate-glossary-overlays": "generate_glossary_term_overlays.py",
    "analyze-blocking": "analyze_multicam_blocking.py",
    "auto-sync-dropped": "auto_sync_app_sources.py",
    "transcribe-align": "transcribe_align_st7_7550_multicam.py",
    "compare-all-cameras": "transcribe_compare_all_st7_7550_multicam.py",
    "refine-strong-wave": "refine_st7_7550_strong_wave_offsets.py",
    "build-base": "build_st7_7550_strong_transcript_multicam.py",
    "transcribe-sound2": "transcribe_sound2.py",
    "compare-sound2": "compare_sound2_transcripts.py",
    "refine-sound2": "refine_sound2_audio_offset.py",
}

RENDER_SCRIPTS = {
    "render_1min_color_matched.py",
    "render_1min_onepass_ffmpeg.py",
    "render_app_interview.py",
    "render_final_png_overlays.py",
}

THUMBNAIL_MODE_FLAGS = {
    "standard": "",
    "closeup_bottom_title": "--closeup-bottom-title",
    "right_face_title_stack": "--right-face-title-stack",
    "left_face_title_stack": "--left-face-title-stack",
}


def bool_value(*keys: str, default: bool = False) -> bool:
    value = nested(APP_CONFIG, *keys, default=default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return bool(value)


def value(*keys: str, default: Any = None) -> Any:
    return nested(APP_CONFIG, *keys, default=default)


def str_value(*keys: str, default: str = "") -> str:
    item = value(*keys, default=default)
    return str(item) if item is not None else default


def path_value(*keys: str) -> str:
    return str_value(*keys).strip()


def run(command: list[str], *, dry_run: bool = False) -> int:
    if dry_run:
        print(json.dumps({"command": command}, ensure_ascii=False, indent=2))
        return 0
    completed = subprocess.run(command, cwd=WORK)
    return int(completed.returncode)


def add_audio_args(command: list[str]) -> None:
    if not bool_value("render", "audioDenoise", default=True):
        command.append("--no-audio-denoise")
    command.extend(["--audio-denoise-strength", str(value("render", "audioDenoiseStrength", default=10))])


def add_silence_args(command: list[str]) -> None:
    if not bool_value("render", "shortenSilence", default=True):
        command.append("--no-shorten-silence")
    command.extend(
        [
            "--min-silence",
            str(value("render", "minSilence", default=3.0)),
            "--keep-silence",
            str(value("render", "keepSilence", default=2.0)),
            "--silence-noise",
            str_value("render", "silenceNoise", default="-30dB"),
        ]
    )
    if bool_value("render", "keepUncut"):
        command.append("--keep-uncut")


def selected_mode() -> str:
    mode = str_value("render", "subtitleMode", default="full")
    return mode if mode in {"full", "punchline", "none"} else "full"


def render_command() -> list[str]:
    script = Path(str_value("render", "renderScript", default="render_1min_color_matched.py")).name
    if script not in RENDER_SCRIPTS:
        raise SystemExit(f"Unsupported render script: {script}")
    command = [sys.executable, str(SCRIPTS / script)]
    if script == "render_app_interview.py":
        return command

    output = path_value("render", "outputPath")
    if not output:
        raise SystemExit("render.outputPath is required for selected render scripts.")

    mode = selected_mode()
    command.extend(["--mode", mode, "--output", output])
    if script == "render_1min_onepass_ffmpeg.py":
        command.extend(
            [
                "--preview-start",
                str(value("render", "previewStart", default=0)),
                "--preview-duration",
                str(value("render", "previewDuration", default=60)),
            ]
        )
    if script in {"render_final_png_overlays.py", "render_1min_color_matched.py"}:
        command.extend(["--duration", str(value("render", "previewDuration", default=60))])
    if script == "render_1min_color_matched.py":
        if bool_value("render", "rebuildBase"):
            command.append("--rebuild-base")
        if bool_value("render", "skipSubtitleRegeneration"):
            command.append("--skip-subtitle-regeneration")
        if bool_value("render", "reclassifySpeakers"):
            command.append("--reclassify-speakers")
    if script == "render_1min_onepass_ffmpeg.py":
        if bool_value("render", "skipSubtitleRegeneration"):
            command.append("--skip-subtitle-regeneration")
        command.append("--auto-context-cuts" if bool_value("render", "autoContextCuts", default=True) else "--no-auto-context-cuts")
        if bool_value("render", "naturalDialogueCuts"):
            command.append("--natural-dialogue-cuts")
        if not bool_value("render", "termExplanations", default=True):
            command.append("--no-term-explanations")
    add_audio_args(command)
    add_silence_args(command)
    return command


def subtitle_review_command() -> list[str]:
    command = [sys.executable, str(SCRIPTS / "subtitle_review_cycle.py")]
    if bool_value("workflow", "noAudioClips"):
        command.append("--no-audio-clips")
    if bool_value("workflow", "transcribeReview"):
        command.extend(["--transcribe-review", "--review-model", str_value("workflow", "reviewModel", default="medium")])
    return command


def thumbnail_command() -> list[str]:
    mode = str_value("thumbnails", "mode", default=str_value("render", "thumbnailMode", default="standard"))
    main_color = str_value("thumbnails", "mainColor", default=str_value("render", "thumbnailMainColor", default="yellow"))
    command = [
        sys.executable,
        str(SCRIPTS / "generate_thumbnail_candidates.py"),
        "--main-color",
        main_color,
        "--mode",
        mode,
    ]
    if bool_value("thumbnails", "importAssets", default=True):
        command.append("--import-assets")
    asset_source = path_value("thumbnails", "assetSource")
    if asset_source:
        command.extend(["--asset-source", asset_source])
    return command


def person_analysis_command(reference: bool = False) -> list[str]:
    command = [
        sys.executable,
        str(SCRIPTS / "analyze_person_edit_metadata.py"),
        "--fps-sample",
        str(value("analysis", "personFpsSample", default=1)),
        "--model",
        str_value("analysis", "personModel", default="yolov8n.pt"),
        "--confidence",
        str(value("analysis", "personConfidence", default=0.35)),
    ]
    if reference:
        reference_video = path_value("assets", "referenceVideo")
        if not reference_video:
            raise SystemExit("assets.referenceVideo is required for analyze-reference-video.")
        command.extend(
            [
                "--input",
                reference_video,
                "--output-dir",
                str_value("analysis", "referencePersonBboxesDir"),
                "--plan-output-dir",
                str_value("analysis", "referenceEditPlansDir"),
                "--max-duration",
                "60",
                "--reference-profile-output",
                str_value("analysis", "referenceEditProfilePath"),
            ]
        )
        max_seconds = value("analysis", "personMaxSeconds")
        if max_seconds:
            command.extend(["--max-seconds", str(min(60, float(max_seconds)))])
        return command

    command.extend(
        [
            "--output-dir",
            str_value("analysis", "personBboxesDir"),
            "--plan-output-dir",
            str_value("analysis", "personEditPlansDir"),
        ]
    )
    for flag, key in (("--max-seconds", "personMaxSeconds"), ("--limit", "personLimit")):
        item = value("analysis", key)
        if item not in {None, ""}:
            command.extend([flag, str(item)])
    if bool_value("analysis", "personNoMulticamRoot"):
        command.append("--no-multicam-root")
    videos = [path for path in (path_value("assets", "masterVideo"), path_value("assets", "rightCloseVideo"), path_value("assets", "leftCloseVideo")) if path]
    if videos:
        command.append("--input")
        command.extend(videos)
    return command


def replace_sound2_command() -> list[str]:
    output = path_value("render", "outputPath")
    if not output:
        raise SystemExit("render.outputPath is required before replacing audio.")
    command = [
        sys.executable,
        str(SCRIPTS / "replace_audio_with_sound2.py"),
        "--video",
        path_value("workflow", "replaceAudioInput") or path_value("workflow", "inputVideoPath") or output,
        "--output",
        output,
    ]
    add_silence_args(command)
    return command


def shorten_input_command() -> list[str]:
    input_video = path_value("workflow", "inputVideoPath") or path_value("render", "outputPath")
    output = path_value("render", "outputPath")
    if not input_video or not output:
        raise SystemExit("workflow.inputVideoPath and render.outputPath are required for silence shortening.")
    return [
        sys.executable,
        str(SCRIPTS / "shorten_silences.py"),
        "--input",
        input_video,
        "--output",
        output,
        "--min-silence",
        str(value("render", "minSilence", default=3.0)),
        "--keep-silence",
        str(value("render", "keepSilence", default=2.0)),
        "--noise",
        str_value("render", "silenceNoise", default="-30dB"),
    ]


def extract_still_command() -> list[str]:
    input_video = path_value("workflow", "inputVideoPath") or path_value("render", "outputPath")
    if not input_video:
        raise SystemExit("workflow.inputVideoPath is required before extracting a still.")
    output = path_value("workflow", "stillOutputPath")
    if not output:
        source = Path(input_video)
        output = str(source.with_name(f"{source.stem}_still.png"))
    return [str(FFMPEG), "-y", "-ss", str_value("workflow", "stillTime", default="00:00:25"), "-i", input_video, "-frames:v", "1", "-update", "1", output]


def ffprobe_command(kind: str) -> list[str]:
    input_video = path_value("workflow", "inputVideoPath") or path_value("render", "outputPath")
    if not input_video:
        raise SystemExit("workflow.inputVideoPath is required before verification.")
    if kind == "verify-duration":
        return [str(FFPROBE), "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", input_video]
    return [str(FFPROBE), "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_name,sample_rate,channels", "-of", "json", input_video]


def command_for_action(action: str) -> list[str]:
    if action == "render-selected":
        return render_command()
    if action == "subtitle-review":
        return subtitle_review_command()
    if action == "generate-thumbnails":
        return thumbnail_command()
    if action == "analyze-person-edit-metadata":
        return person_analysis_command()
    if action == "analyze-reference-video":
        return person_analysis_command(reference=True)
    if action == "replace-sound2":
        return replace_sound2_command()
    if action == "shorten-input":
        return shorten_input_command()
    if action == "extract-still":
        return extract_still_command()
    if action in {"verify-duration", "verify-audio"}:
        return ffprobe_command(action)
    if action in SIMPLE_PYTHON_ACTIONS:
        return [sys.executable, str(SCRIPTS / SIMPLE_PYTHON_ACTIONS[action])]
    raise SystemExit(f"Unknown workflow action: {action}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run video_edit actions from the shared runtime config.")
    parser.add_argument("--action", default=str_value("render", "workflowAction", default="render-selected"))
    parser.add_argument("--dry-run", action="store_true", help="Print the resolved command without running it.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    command = command_for_action(args.action)
    raise SystemExit(run(command, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
