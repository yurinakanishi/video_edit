from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
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
from video_edit_app_config import int_value, load_app_config, nested, optional_path, video_encoder_crf, video_encoder_preset


WORK = WORKSPACE_ROOT
APP_CONFIG = load_app_config()
FFMPEG = optional_path(APP_CONFIG, "tools", "ffmpeg", default=Path(r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"))
FFPROBE = optional_path(APP_CONFIG, "tools", "ffprobe", default=Path(r"C:\ProgramData\chocolatey\bin\ffprobe.exe"))
DEFAULT_MIN_SILENCE = 3.0
DEFAULT_KEEP_SILENCE = 2.0
DEFAULT_NOISE = "-30dB"


@dataclass(frozen=True)
class SilenceShortenConfig:
    min_silence: float = DEFAULT_MIN_SILENCE
    keep_silence: float = DEFAULT_KEEP_SILENCE
    noise: str = DEFAULT_NOISE


def run_text(command: list[str]) -> str:
    completed = subprocess.run(command, cwd=WORK, check=True, text=True, capture_output=True)
    return completed.stdout + completed.stderr


def probe_duration(input_path: Path) -> float:
    text = run_text(
        [
            str(FFPROBE),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(input_path),
        ]
    )
    return float(text.strip())


def detect_silences(input_path: Path, config: SilenceShortenConfig, duration: float) -> list[dict[str, float]]:
    command = [
        str(FFMPEG),
        "-hide_banner",
        "-nostats",
        "-i",
        str(input_path),
        "-af",
        f"silencedetect=noise={config.noise}:d={config.min_silence:.6f}",
        "-f",
        "null",
        "-",
    ]
    completed = subprocess.run(command, cwd=WORK, text=True, capture_output=True)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "ffmpeg silencedetect failed")

    silences: list[dict[str, float]] = []
    current_start: float | None = None
    for line in completed.stderr.splitlines():
        start_match = re.search(r"silence_start:\s*([0-9.]+)", line)
        if start_match:
            current_start = float(start_match.group(1))
            continue
        end_match = re.search(r"silence_end:\s*([0-9.]+)\s*\|\s*silence_duration:\s*([0-9.]+)", line)
        if end_match and current_start is not None:
            end = min(float(end_match.group(1)), duration)
            silences.append(
                {
                    "start": max(0.0, current_start),
                    "end": end,
                    "duration": float(end_match.group(2)),
                }
            )
            current_start = None

    if current_start is not None and duration - current_start >= config.min_silence:
        silences.append({"start": current_start, "end": duration, "duration": duration - current_start})
    return [item for item in silences if item["end"] - item["start"] >= config.min_silence]


def removal_ranges(silences: list[dict[str, float]], duration: float, keep_silence: float) -> list[dict[str, float]]:
    half_keep = keep_silence / 2.0
    removals: list[dict[str, float]] = []
    for silence in silences:
        start = silence["start"]
        end = silence["end"]
        silence_duration = end - start
        if silence_duration <= keep_silence:
            continue

        if start <= 0.020:
            remove_start = start
            remove_end = max(start, end - keep_silence)
        elif end >= duration - 0.020:
            remove_start = min(end, start + keep_silence)
            remove_end = end
        else:
            remove_start = start + half_keep
            remove_end = end - half_keep

        if remove_end - remove_start > 0.020:
            removals.append({"start": remove_start, "end": remove_end, "duration": remove_end - remove_start})
    return removals


def keep_ranges(duration: float, removals: list[dict[str, float]]) -> list[dict[str, float]]:
    ranges: list[dict[str, float]] = []
    cursor = 0.0
    for removal in sorted(removals, key=lambda item: item["start"]):
        start = max(0.0, min(duration, removal["start"]))
        end = max(0.0, min(duration, removal["end"]))
        if start - cursor > 0.020:
            ranges.append({"start": cursor, "end": start, "duration": start - cursor})
        cursor = max(cursor, end)
    if duration - cursor > 0.020:
        ranges.append({"start": cursor, "end": duration, "duration": duration - cursor})
    return ranges


def write_filter_script(path: Path, ranges: list[dict[str, float]]) -> None:
    filters: list[str] = []
    pairs: list[str] = []
    for index, item in enumerate(ranges):
        start = item["start"]
        end = item["end"]
        filters.append(f"[0:v]trim=start={start:.6f}:end={end:.6f},setpts=PTS-STARTPTS[v{index}]")
        filters.append(f"[0:a]atrim=start={start:.6f}:end={end:.6f},asetpts=PTS-STARTPTS[a{index}]")
        pairs.append(f"[v{index}][a{index}]")
    filters.append("".join(pairs) + f"concat=n={len(ranges)}:v=1:a=1[v][a]")
    path.write_text(";\n".join(filters), encoding="utf-8")


def silence_shorten_encoder_config() -> tuple[dict[str, object], list[str]]:
    encoder = str(nested(APP_CONFIG, "render", "videoEncoder", default="libx264") or "libx264").strip().lower()
    if encoder == "h264_nvenc":
        preset = str(nested(APP_CONFIG, "render", "nvencPreset", default="p4") or "p4").strip().lower()
        if not re.fullmatch(r"p[1-7]|default|slow|medium|fast|hp|hq|bd|ll|llhq|llhp|lossless|losslesshp", preset):
            preset = "p4"
        cq = max(0, min(51, int_value(APP_CONFIG, "render", "cq", default=19)))
        return (
            {"name": "h264_nvenc", "preset": preset, "cq": cq},
            ["-c:v", "h264_nvenc", "-preset", preset, "-rc", "vbr", "-cq", str(cq), "-b:v", "0", "-pix_fmt", "yuv420p"],
        )

    encoder_preset = video_encoder_preset(APP_CONFIG, "render", "encoderPreset", default="medium")
    encoder_crf = video_encoder_crf(APP_CONFIG, "render", "crf")
    return (
        {"name": "libx264", "preset": encoder_preset, "crf": encoder_crf},
        ["-c:v", "libx264", "-preset", encoder_preset, "-crf", str(encoder_crf), "-pix_fmt", "yuv420p"],
    )


def shorten_silences(
    input_path: Path,
    output_path: Path,
    config: SilenceShortenConfig = SilenceShortenConfig(),
    report_path: Path | None = None,
    dry_run: bool = False,
) -> dict:
    input_path = input_path.resolve()
    output_path = output_path.resolve()
    duration = probe_duration(input_path)
    silences = detect_silences(input_path, config, duration)
    removals = removal_ranges(silences, duration, config.keep_silence)
    ranges = keep_ranges(duration, removals)
    encoder_report, encoder_args = silence_shorten_encoder_config()
    report = {
        "input": str(input_path),
        "output": str(output_path),
        "encoder": encoder_report,
        "noise": config.noise,
        "min_silence": config.min_silence,
        "keep_silence": config.keep_silence,
        "source_duration": duration,
        "output_duration": sum(item["duration"] for item in ranges),
        "detected_silences": silences,
        "removed_ranges": removals,
        "keep_ranges": ranges,
    }
    if report_path is None:
        report_path = output_path.with_suffix(".silence_shortening.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if dry_run:
        return report

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not removals:
        if input_path != output_path:
            shutil.copy2(input_path, output_path)
        return report

    with tempfile.NamedTemporaryFile("w", suffix=".ffmpeg_filter", delete=False, encoding="utf-8") as handle:
        filter_path = Path(handle.name)
    try:
        write_filter_script(filter_path, ranges)
        command = [
            str(FFMPEG),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(input_path),
            "-filter_complex_script",
            str(filter_path),
            "-map",
            "[v]",
            "-map",
            "[a]",
            *encoder_args,
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-ac",
            "2",
            str(output_path),
        ]
        subprocess.run(command, check=True, cwd=WORK)
    finally:
        filter_path.unlink(missing_ok=True)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Shorten silent sections: any silence >= 3 seconds is reduced to 2 seconds by cutting the middle."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--min-silence", type=float, default=DEFAULT_MIN_SILENCE)
    parser.add_argument("--keep-silence", type=float, default=DEFAULT_KEEP_SILENCE)
    parser.add_argument("--noise", default=DEFAULT_NOISE)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = shorten_silences(
        args.input,
        args.output,
        SilenceShortenConfig(min_silence=args.min_silence, keep_silence=args.keep_silence, noise=args.noise),
        report_path=args.report,
        dry_run=args.dry_run,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
