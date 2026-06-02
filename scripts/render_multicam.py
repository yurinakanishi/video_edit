from __future__ import annotations

import json
import hashlib
import math
import re
import subprocess
import sys
from array import array
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageFilter, ImageStat

from video_edit_core.paths import (
    CONFIG,
    OUTPUT_AUDIO,
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

from video_edit_core.audio.silence import DEFAULT_KEEP_SILENCE, DEFAULT_MIN_SILENCE, DEFAULT_NOISE, SilenceShortenConfig, shorten_silences
from video_edit_core.app_config import (
    int_value,
    load_app_config,
    nested,
    optional_path,
    selected_subtitle_path,
    transcript_manifest_fingerprint,
    video_encoder_crf,
    video_encoder_preset,
)
from video_edit_core.composition import crop_window_center_for_subject, subject_target_for_face, visible_ratio_for_area


WORK = WORKSPACE_ROOT
APP_CONFIG = load_app_config()
FFMPEG = optional_path(APP_CONFIG, "tools", "ffmpeg", default=Path(r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"))
FFPROBE = optional_path(APP_CONFIG, "tools", "ffprobe", default=Path(r"C:\ProgramData\chocolatey\bin\ffprobe.exe"))
TITLE = OUTPUT_OVERLAYS / "title_overlay.png"
DEFAULT_OMISSION_CARD = OUTPUT_OVERLAYS / "omission_card.png"
DEFAULT_SYNC = OUTPUT_REPORTS / "app_sync_offsets.json"
DEFAULT_TRANSCRIPT_COMPARISON = OUTPUT_REPORTS / "transcript_comparison.json"
DEFAULT_DENOISE_STRENGTH = 10
DEFAULT_REFERENCE_PROFILE = OUTPUT_REPORTS / "reference_edit_profile.json"
DEFAULT_PERSON_EDIT_PLANS = OUTPUT_REPORTS / "person_edit_plans"
DEFAULT_STILL_DURATION = 3.5
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
COLOR_MATCH_REPORT = OUTPUT_REPORTS / "camera_color_match.json"
CAMERA_PLAN_REPORT = OUTPUT_REPORTS / "camera_cut_plan.json"
NATURAL_CUT_REPORT = OUTPUT_REPORTS / "natural_dialogue_cuts.json"
PERSON_CROP_REPORT = OUTPUT_REPORTS / "person_crop_usage.json"
FACE_CENTER_CROP_REPORT = OUTPUT_REPORTS / "face_center_crop_usage.json"
SYNC_OFFSET_USAGE_REPORT = OUTPUT_REPORTS / "sync_offset_usage.json"
SOURCE_COVERAGE_REPORT = OUTPUT_REPORTS / "source_coverage_usage.json"
ONSCREEN_CLOSEUP_REPORT = OUTPUT_REPORTS / "onscreen_closeup_camera_mask.json"
SUBTITLE_TIMEBASE_REPORT = OUTPUT_REPORTS / "subtitle_timebase_usage.json"
EXTERNAL_AUDIO_CUT_SYNC_REPORT = OUTPUT_REPORTS / "external_audio_cut_sync_report.json"
RENDER_USAGE_REPORT = OUTPUT_REPORTS / "render_usage.json"
PROXY_PROFILE = "h264-960p-ultrafast-crf28"


def seconds(timestamp: str) -> float:
    hours, minutes, rest = timestamp.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(rest)


def path_value(*keys: str) -> Path | None:
    value = nested(APP_CONFIG, *keys, default="")
    return Path(value) if value else None


def list_value(*keys: str) -> list[Any]:
    value = nested(APP_CONFIG, *keys, default=[])
    return value if isinstance(value, list) else []


def media_manifest() -> dict[str, Any]:
    manifest = nested(APP_CONFIG, "assets", "mediaManifest", default={})
    if isinstance(manifest, dict) and manifest.get("files"):
        return manifest
    path = nested(APP_CONFIG, "assets", "mediaManifestPath", default="")
    if path and Path(path).exists():
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return {}


def manifest_files(kind: str | None = None) -> list[dict[str, Any]]:
    manifest = media_manifest()
    files = manifest.get("files", []) if isinstance(manifest, dict) else []
    if not isinstance(files, list):
        return []
    items = [item for item in files if isinstance(item, dict)]
    if kind is not None:
        items = [item for item in items if item.get("kind") == kind]
    return items


def camera_role_sort(role: str) -> int:
    if role == "master":
        return 1
    if role.startswith("camera"):
        try:
            return int(role.replace("camera", ""))
        except ValueError:
            return 50
    return 100


def manifest_cameras() -> list[tuple[str, Path]]:
    camera_roles = {"master", "camera2", "camera3", "camera4", "camera5", "camera6"}
    cameras = [
        (str(item.get("role") or ""), Path(str(item.get("path") or "")))
        for item in manifest_files("video")
        if item.get("role") in camera_roles and item.get("path")
    ]
    cameras = [(role, path) for role, path in cameras if path.exists()]
    cameras.sort(key=lambda item: camera_role_sort(item[0]))
    return cameras


def render_profile() -> str:
    profile = str(nested(APP_CONFIG, "render", "renderProfile", default="final") or "final").strip().lower()
    return profile if profile in {"preview", "final"} else "final"


def render_range_mode() -> str:
    mode = str(nested(APP_CONFIG, "render", "rangeMode", default="range") or "range").strip().lower()
    return mode if mode in {"range", "full"} else "range"


def source_signature(path: Path) -> str:
    stat = path.stat()
    payload = json.dumps(
        {
            "path": str(path.resolve()).lower(),
            "size": stat.st_size,
            "mtimeNs": stat.st_mtime_ns,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def manifest_camera_item(role: str, path: Path) -> dict[str, Any] | None:
    for item in manifest_files("video"):
        if str(item.get("role") or "") == role and paths_match(item.get("path"), path):
            return item
    return None


def camera_input_paths_for_render(cameras: list[tuple[str, Path]], profile: str) -> tuple[dict[int, Path], list[dict[str, Any]]]:
    input_paths: dict[int, Path] = {}
    usage: list[dict[str, Any]] = []
    for index, (role, source_path) in enumerate(cameras):
        input_path = source_path
        entry: dict[str, Any] = {
            "index": index,
            "role": role,
            "sourcePath": str(source_path),
            "inputPath": str(source_path),
            "proxyUsed": False,
        }
        if profile != "preview":
            entry["reason"] = "final profile uses original source"
            input_paths[index] = input_path
            usage.append(entry)
            continue

        item = manifest_camera_item(role, source_path)
        proxy = item.get("proxy") if isinstance(item, dict) and isinstance(item.get("proxy"), dict) else None
        if not proxy:
            entry["reason"] = "proxy metadata missing"
            input_paths[index] = input_path
            usage.append(entry)
            continue
        proxy_path = Path(str(proxy.get("path") or ""))
        if proxy.get("profile") != PROXY_PROFILE:
            entry["reason"] = "proxy profile mismatch"
        elif not proxy_path.exists():
            entry["reason"] = "proxy file missing"
        else:
            try:
                expected_signature = str(proxy.get("sourceSignature") or "")
                actual_signature = source_signature(source_path)
            except OSError as error:
                entry["reason"] = f"source signature failed: {error}"
            else:
                if expected_signature and expected_signature != actual_signature:
                    entry["reason"] = "proxy source signature is stale"
                    entry["expectedSourceSignature"] = expected_signature
                    entry["actualSourceSignature"] = actual_signature
                else:
                    input_path = proxy_path
                    entry["inputPath"] = str(proxy_path)
                    entry["proxyUsed"] = True
                    entry["reason"] = "proxy selected"
                    entry["profile"] = proxy.get("profile")
        input_paths[index] = input_path
        usage.append(entry)
    return input_paths, usage


def manifest_audio_sources() -> list[tuple[str, Path]]:
    audio = [
        (str(item.get("role") or "external"), Path(str(item.get("path") or "")))
        for item in manifest_files("audio")
        if str(item.get("role") or "").startswith("external") and item.get("path")
    ]
    return [(role, path) for role, path in audio if path.exists()]


def manifest_image(role: str) -> Path | None:
    for item in manifest_files("image"):
        if item.get("role") == role and item.get("path"):
            path = Path(str(item["path"]))
            if path.exists():
                return path
    return None


def selected_logo_path() -> Path | None:
    configured = path_value("assets", "logo")
    if configured and configured.exists():
        return configured
    return manifest_image("logo")


def bool_value(*keys: str, default: bool = False) -> bool:
    value = nested(APP_CONFIG, *keys, default=default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return bool(value)


def audio_cleanup_filter(strength: int, mastering: bool = False, denoise: bool = True) -> str:
    nr = max(0, min(30, int(strength)))
    parts = ["highpass=f=80"]
    if denoise and nr > 0:
        parts.extend([f"afftdn=nr={nr}:nf=-35", "lowpass=f=16000"])
    if mastering:
        parts.extend(
            [
                "dynaudnorm=f=250:g=15:p=0.95:m=8",
                "acompressor=threshold=-20dB:ratio=2.8:attack=5:release=120:makeup=4",
                "loudnorm=I=-14:TP=-1.5:LRA=9",
                "alimiter=limit=0.95",
            ]
        )
    return ",".join(parts)


def video_encoder_config() -> dict[str, object]:
    if render_profile() == "preview":
        return {
            "name": "libx264",
            "preset": "ultrafast",
            "crf": 30,
            "args": [
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "30",
                "-pix_fmt",
                "yuv420p",
            ],
        }

    encoder = str(nested(APP_CONFIG, "render", "videoEncoder", default="libx264") or "libx264").strip().lower()
    if encoder == "h264_nvenc":
        preset = str(nested(APP_CONFIG, "render", "nvencPreset", default="p4") or "p4").strip().lower()
        if not re.fullmatch(r"p[1-7]|default|slow|medium|fast|hp|hq|bd|ll|llhq|llhp|lossless|losslesshp", preset):
            preset = "p4"
        cq = max(0, min(51, int_value(APP_CONFIG, "render", "cq", default=19)))
        return {
            "name": "h264_nvenc",
            "preset": preset,
            "cq": cq,
            "args": [
                "-c:v",
                "h264_nvenc",
                "-preset",
                preset,
                "-rc",
                "vbr",
                "-cq",
                str(cq),
                "-b:v",
                "0",
                "-pix_fmt",
                "yuv420p",
            ],
        }

    preset = video_encoder_preset(APP_CONFIG, "render", "encoderPreset")
    crf = video_encoder_crf(APP_CONFIG, "render", "crf")
    return {
        "name": "libx264",
        "preset": preset,
        "crf": crf,
        "args": [
            "-c:v",
            "libx264",
            "-preset",
            preset,
            "-crf",
            str(crf),
            "-pix_fmt",
            "yuv420p",
        ],
    }


def float_config(*keys: str, default: float) -> float:
    value = nested(APP_CONFIG, *keys, default=default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def text_config(*keys: str, default: str = "") -> str:
    value = nested(APP_CONFIG, *keys, default=default)
    return str(value) if value is not None else default


def output_fps() -> str:
    value = text_config("render", "outputFps", default="60000/1001").strip()
    if re.fullmatch(r"\d+(?:/\d+)?(?:\.\d+)?", value):
        return value
    return "60000/1001"


def parse_time_value(value: str) -> float | None:
    text = value.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        pass
    parts = text.split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    except ValueError:
        return None
    return None


def normalize_ranges(ranges: list[tuple[float, float]], start: float, duration: float) -> list[tuple[float, float]]:
    normalized: list[tuple[float, float]] = []
    for range_start, range_end in ranges:
        local_start = max(0.0, range_start - start)
        local_end = min(duration, range_end - start)
        if local_end > local_start:
            normalized.append((local_start, local_end))
    if not normalized:
        return []
    normalized.sort()
    merged = [normalized[0]]
    for range_start, range_end in normalized[1:]:
        previous_start, previous_end = merged[-1]
        if range_start <= previous_end + 0.05:
            merged[-1] = (previous_start, max(previous_end, range_end))
        else:
            merged.append((range_start, range_end))
    return merged


def explicit_music_ranges(start: float, duration: float) -> list[tuple[float, float]]:
    raw_ranges = nested(APP_CONFIG, "music", "ranges", default=[])
    ranges: list[tuple[float, float]] = []
    if isinstance(raw_ranges, list):
        for item in raw_ranges:
            if not isinstance(item, dict):
                continue
            try:
                range_start = float(item.get("start", 0.0))
                range_end = float(item.get("end", 0.0))
            except (TypeError, ValueError):
                continue
            ranges.append((range_start, range_end))
    text = text_config("music", "rangesText")
    for line in text.splitlines():
        match = re.match(r"^\s*([0-9:.]+)\s*[-–]\s*([0-9:.]+)", line)
        if not match:
            continue
        range_start = parse_time_value(match.group(1))
        range_end = parse_time_value(match.group(2))
        if range_start is None or range_end is None:
            continue
        ranges.append((range_start, range_end))

    return normalize_ranges(ranges, start, duration)


def overlay_item_text(item: dict[str, Any]) -> str:
    lines = item.get("lines")
    if isinstance(lines, list):
        line_text = " ".join(str(line) for line in lines)
    else:
        line_text = ""
    return " ".join(str(value or "") for value in (line_text, item.get("text"), item.get("label"), item.get("title")))


def is_omission_overlay_item(item: dict[str, Any]) -> bool:
    role = str(item.get("speaker_role") or item.get("role") or "").lower()
    if role == "interviewer":
        return True
    text = overlay_item_text(item).lower()
    markers = ("省略", "割愛", "カット", "聞き手", "インタビュアー", "interviewer", "omit", "omission", "...", "…")
    return any(marker in text for marker in markers)


def overlay_manifest_ranges(manifest: Path, start: float, duration: float) -> list[tuple[float, float]]:
    if not manifest.exists():
        return []
    try:
        items = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    ranges = []
    iterable = items if isinstance(items, list) else []
    for item in iterable:
        if not isinstance(item, dict) or not is_omission_overlay_item(item):
            continue
        try:
            ranges.append((seconds(str(item["start"])), seconds(str(item["end"]))))
        except (KeyError, ValueError):
            continue
    return normalize_ranges(ranges, start, duration)


def automatic_music_ranges(start: float, duration: float) -> list[tuple[float, float]]:
    manifests = [
        OUTPUT_OVERLAYS / "full_transcript_png_overlays" / "manifest.json",
        OUTPUT_OVERLAYS / "punchline_png_overlays" / "manifest.json",
    ]
    configured = nested(APP_CONFIG, "music", "rangeManifestPaths", default=[])
    if isinstance(configured, list):
        manifests.extend(Path(str(item)) for item in configured if item)
    ranges: list[tuple[float, float]] = []
    for manifest in manifests:
        ranges.extend(overlay_manifest_ranges(manifest, start, duration))
    return normalize_ranges(ranges, 0.0, duration)


def music_ranges(start: float, duration: float) -> list[tuple[float, float]]:
    ranges = explicit_music_ranges(start, duration)
    if text_config("music", "rangeSource", default="auto") != "manual":
        ranges.extend(automatic_music_ranges(start, duration))
    return normalize_ranges(ranges, 0.0, duration)


def music_output_path() -> Path:
    configured = text_config("music", "outputPath")
    return Path(configured) if configured else OUTPUT_AUDIO / "music_bed.wav"


def ensure_music_bed(duration: float) -> Path | None:
    if not bool_value("music", "enabled", default=False):
        return None
    output = music_output_path()
    output.parent.mkdir(parents=True, exist_ok=True)
    if not output.exists() or bool_value("music", "regenerate", default=True):
        run([sys.executable, str(SCRIPTS / "generate_music_bed.py"), "--duration", f"{duration:.6f}", "--output", str(output)])
    return output if output.exists() else None


def should_mix_music(start: float, duration: float, replacements: list[dict[str, Any]] | None = None) -> bool:
    if not bool_value("music", "enabled", default=False):
        return False
    if text_config("music", "scope", default="full") == "omission" and not (replacements or music_ranges(start, duration)):
        return False
    return True


def music_volume_value() -> float:
    value = float_config("music", "volume", default=14.0)
    if value > 1.0:
        value /= 100.0
    return max(0.0, min(1.0, value))


def music_volume_filter(start: float, duration: float, replacements: list[dict[str, Any]] | None = None) -> str:
    volume = music_volume_value()
    scope = text_config("music", "scope", default="full")
    if scope == "omission":
        ranges = (
            [(float(item["output_start"]), float(item["output_end"])) for item in replacements]
            if replacements
            else music_ranges(start, duration)
        )
        if not ranges:
            return "volume=0"
        expr = "+".join(f"between(t\\,{range_start:.3f}\\,{range_end:.3f})" for range_start, range_end in ranges)
        return f"volume='{volume:.4f}*min(1\\,{expr})':eval=frame"
    fade_out_start = max(0.0, duration - 1.2)
    return f"volume={volume:.4f},afade=t=in:st=0:d=0.5,afade=t=out:st={fade_out_start:.3f}:d=1.2"


def default_omission_card_text() -> tuple[str, str]:
    raw = text_config("omissionCard", "text").strip()
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if lines:
        return lines[0], " ".join(lines[1:])
    return (
        text_config("omissionCard", "title", default="質問を要約"),
        text_config("omissionCard", "subtitle", default="ここでは聞き手の質問を短くまとめています"),
    )


def parse_omission_range_line(line: str) -> dict[str, Any] | None:
    match = re.match(r"^\s*([0-9:.]+)\s*[-–]\s*([0-9:.]+)(.*)$", line)
    if not match:
        return None
    range_start = parse_time_value(match.group(1))
    range_end = parse_time_value(match.group(2))
    if range_start is None or range_end is None or range_end <= range_start:
        return None
    title, subtitle = default_omission_card_text()
    rest = match.group(3).strip(" |,\t")
    parts = [part.strip() for part in rest.split("|") if part.strip()]
    if parts:
        title = parts[0]
    if len(parts) > 1:
        subtitle = parts[1]
    return {"start": range_start, "end": range_end, "title": title, "subtitle": subtitle}


def configured_omission_range_specs(start: float, source_duration: float) -> list[dict[str, Any]]:
    raw_specs = nested(APP_CONFIG, "omissionCard", "ranges", default=[])
    title, subtitle = default_omission_card_text()
    specs: list[dict[str, Any]] = []
    if isinstance(raw_specs, list):
        for item in raw_specs:
            if not isinstance(item, dict):
                continue
            try:
                range_start = float(item.get("start", 0.0))
                range_end = float(item.get("end", 0.0))
            except (TypeError, ValueError):
                continue
            if range_end > range_start:
                specs.append(
                    {
                        "start": range_start,
                        "end": range_end,
                        "title": str(item.get("title") or title),
                        "subtitle": str(item.get("subtitle") or subtitle),
                    }
                )

    ranges_text = text_config("omissionCard", "rangesText")
    if not ranges_text and bool_value("omissionCard", "useMusicRanges", default=True):
        ranges_text = text_config("music", "rangesText")
    for line in ranges_text.splitlines():
        spec = parse_omission_range_line(line)
        if spec:
            specs.append(spec)

    local_specs: list[dict[str, Any]] = []
    for spec in specs:
        local_start = max(0.0, float(spec["start"]) - start)
        local_end = min(source_duration, float(spec["end"]) - start)
        if local_end - local_start <= 0.05:
            continue
        local_specs.append({**spec, "source_start": local_start, "source_end": local_end})

    local_specs.sort(key=lambda item: (float(item["source_start"]), float(item["source_end"])))
    filtered: list[dict[str, Any]] = []
    last_end = -1.0
    for spec in local_specs:
        source_start = float(spec["source_start"])
        source_end = float(spec["source_end"])
        if source_start < last_end - 0.05:
            continue
        filtered.append(spec)
        last_end = source_end
    return filtered


def omission_card_output_path(index: int, count: int) -> Path:
    configured = text_config("omissionCard", "outputPath")
    base = Path(configured) if configured else DEFAULT_OMISSION_CARD
    if count <= 1:
        return base
    return base.with_name(f"{base.stem}_{index + 1:02d}{base.suffix}")


def build_omission_replacements(start: float, source_duration: float) -> tuple[list[dict[str, Any]], float]:
    if not bool_value("omissionCard", "enabled", default=False):
        return [], source_duration
    specs = configured_omission_range_specs(start, source_duration)
    if not specs:
        return [], source_duration
    card_duration = max(0.5, min(float_config("omissionCard", "duration", default=5.0), 30.0))
    replacements: list[dict[str, Any]] = []
    source_cursor = 0.0
    output_cursor = 0.0
    for index, spec in enumerate(specs):
        source_start = float(spec["source_start"])
        source_end = float(spec["source_end"])
        output_cursor += max(0.0, source_start - source_cursor)
        output_start = output_cursor
        output_end = output_start + card_duration
        replacements.append(
            {
                "source_start": source_start,
                "source_end": source_end,
                "output_start": output_start,
                "output_end": output_end,
                "duration": card_duration,
                "title": str(spec.get("title") or default_omission_card_text()[0]),
                "subtitle": str(spec.get("subtitle") or default_omission_card_text()[1]),
                "path": omission_card_output_path(index, len(specs)),
                "input_index": None,
            }
        )
        source_cursor = source_end
        output_cursor = output_end
    output_duration = output_cursor + max(0.0, source_duration - source_cursor)
    return replacements, max(0.1, output_duration)


def ensure_omission_cards(replacements: list[dict[str, Any]]) -> None:
    for replacement in replacements:
        output = Path(replacement["path"])
        output.parent.mkdir(parents=True, exist_ok=True)
        run(
            [
                sys.executable,
                str(SCRIPTS / "generate_omission_card.py"),
                "--output",
                str(output),
                "--title",
                str(replacement["title"]),
                "--subtitle",
                str(replacement["subtitle"]),
            ]
        )


def output_local_to_source_local(t: float, replacements: list[dict[str, Any]]) -> float | None:
    source_cursor = 0.0
    output_cursor = 0.0
    for replacement in replacements:
        source_start = float(replacement["source_start"])
        source_end = float(replacement["source_end"])
        output_start = float(replacement["output_start"])
        output_end = float(replacement["output_end"])
        if t < output_start - 0.0001:
            return source_cursor + (t - output_cursor)
        if t < output_end - 0.0001:
            return None
        source_cursor = source_end
        output_cursor = output_end
    return source_cursor + (t - output_cursor)


def source_local_to_output_local(t: float, replacements: list[dict[str, Any]]) -> float | None:
    source_cursor = 0.0
    output_cursor = 0.0
    for replacement in replacements:
        source_start = float(replacement["source_start"])
        source_end = float(replacement["source_end"])
        output_end = float(replacement["output_end"])
        if t <= source_start + 0.0001:
            return output_cursor + (t - source_cursor)
        if t < source_end - 0.0001:
            return None
        source_cursor = source_end
        output_cursor = output_end
    return output_cursor + (t - source_cursor)


def format_overlay_time(total_seconds: float) -> str:
    total_seconds = max(0.0, total_seconds)
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    secs = total_seconds - hours * 3600 - minutes * 60
    return f"{hours}:{minutes:02d}:{secs:06.3f}"


def overlaps_omission(source_start: float, source_end: float, replacements: list[dict[str, Any]]) -> bool:
    return any(source_start < float(item["source_end"]) and source_end > float(item["source_start"]) for item in replacements)


def transform_overlay_items(
    items: list[dict[str, Any]],
    replacements: list[dict[str, Any]],
    start: float,
    source_duration: float,
    output_duration: float,
) -> list[dict[str, Any]]:
    if not replacements:
        return items
    transformed: list[dict[str, Any]] = []
    for item in items:
        try:
            item_start = seconds(str(item["start"])) - start
            item_end = seconds(str(item["end"])) - start
        except (KeyError, ValueError):
            continue
        item_start = max(0.0, min(source_duration, item_start))
        item_end = max(0.0, min(source_duration, item_end))
        if item_end <= item_start or overlaps_omission(item_start, item_end, replacements):
            continue
        output_start = source_local_to_output_local(item_start, replacements)
        output_end = source_local_to_output_local(item_end, replacements)
        if output_start is None or output_end is None:
            continue
        output_start = max(0.0, min(output_duration, output_start))
        output_end = max(0.0, min(output_duration, output_end))
        if output_end <= output_start:
            continue
        next_item = dict(item)
        next_item["start"] = format_overlay_time(start + output_start)
        next_item["end"] = format_overlay_time(start + output_end)
        transformed.append(next_item)
    return transformed


def same_resolved_path(left: Path | None, right: Path | None) -> bool:
    if left is None or right is None:
        return False
    try:
        return str(left.resolve()).casefold() == str(right.resolve()).casefold()
    except OSError:
        return str(left).casefold() == str(right).casefold()


def selected_subtitle_source_role() -> str | None:
    srt = selected_subtitle_path(APP_CONFIG, extensions=(".srt",))
    if srt is None:
        return None
    manifest = OUTPUT_TRANSCRIPTS / "manifest_sources" / "manifest_transcripts.json"
    if not manifest.exists():
        return None
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if same_resolved_path(srt, Path(str(payload.get("primarySrt") or ""))):
        for item in payload.get("transcripts", []):
            if isinstance(item, dict) and item.get("primary"):
                return str(item.get("role") or "")
    for item in payload.get("transcripts", []):
        if not isinstance(item, dict):
            continue
        if same_resolved_path(srt, Path(str(item.get("srt") or ""))):
            return str(item.get("role") or "")
    return None


def subtitle_source_offset_seconds(audio_role: str, sync_offsets: dict[str, float]) -> float:
    override = nested(APP_CONFIG, "render", "subtitleTimelineOffsetSeconds", default=None)
    if override is not None:
        try:
            return float(override)
        except (TypeError, ValueError):
            return 0.0

    timebase = text_config("render", "subtitleTimebase", default="auto").strip().lower()
    if timebase in {"timeline", "master", "master-video"}:
        return 0.0
    if timebase in {"external", "external-audio", "audio-source", "source-audio"}:
        return float(sync_offsets.get(audio_role, 0.0))
    if timebase != "auto":
        return 0.0

    subtitle_role = selected_subtitle_source_role()
    if subtitle_role and subtitle_role == audio_role:
        return float(sync_offsets.get(audio_role, 0.0))
    return 0.0


def normalize_text(text: str) -> str:
    return re.sub(r"[\s　、。,.!！?？:：;；・/\\|_\-()\[\]（）「」『』\"'`]+", "", text.lower())


def sidecar_text(path: Path) -> str:
    text_path = path.with_suffix(".txt")
    if text_path.exists():
        return text_path.read_text(encoding="utf-8", errors="ignore").strip()
    return ""


def optional_ocr_text(path: Path) -> str:
    try:
        import pytesseract  # type: ignore

        return pytesseract.image_to_string(str(path), lang="jpn+eng").strip()
    except Exception:
        return ""


def text_density(path: Path) -> float:
    try:
        image = Image.open(path).convert("L").resize((360, 202))
    except Exception:
        return 0.0
    edges = image.filter(ImageFilter.FIND_EDGES)
    stat = ImageStat.Stat(edges)
    return float(stat.mean[0]) / 255.0


def still_kind(path: Path, extracted_text: str) -> str:
    if len(normalize_text(extracted_text)) >= 4:
        return "text"
    density = text_density(path)
    return "diagram" if density >= 0.115 else "photo"


def still_text(path: Path) -> str:
    return " ".join(part for part in [sidecar_text(path), optional_ocr_text(path), path.stem.replace("_", " ")] if part).strip()


def visual_text(path: Path) -> str:
    return " ".join(part for part in [sidecar_text(path), optional_ocr_text(path)] if part).strip()


def weighted_focus(path: Path) -> tuple[float, float]:
    try:
        image = Image.open(path).convert("L")
    except Exception:
        return (0.5, 0.5)
    width, height = image.size
    if width <= 0 or height <= 0:
        return (0.5, 0.5)

    sample_width = 160
    sample_height = max(1, round(sample_width * height / width))
    sample = image.resize((sample_width, sample_height))
    edges = sample.filter(ImageFilter.FIND_EDGES)
    edge_data = list(edges.getdata())
    light_data = list(sample.getdata())
    total = 0.0
    sum_x = 0.0
    sum_y = 0.0
    for index, edge in enumerate(edge_data):
        x = index % sample_width
        y = index // sample_width
        light = light_data[index]
        weight = float(edge) * 0.85 + max(0.0, float(light) - 96.0) * 0.15
        total += weight
        sum_x += x * weight
        sum_y += y * weight
    if total <= 0:
        return (0.5, 0.5)
    return (clamp((sum_x / total) / max(1, sample_width - 1), 0.22, 0.78), clamp((sum_y / total) / max(1, sample_height - 1), 0.24, 0.76))


def detect_photo_faces(path: Path) -> list[dict[str, float]]:
    try:
        import cv2  # type: ignore

        image = cv2.imread(str(path))
        if image is None:
            return []
        height, width = image.shape[:2]
        cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        cascade = cv2.CascadeClassifier(str(cascade_path))
        if cascade.empty():
            return []
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        min_size = max(24, min(width, height) // 12)
        boxes = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(min_size, min_size))
    except Exception:
        return []

    faces = []
    for x, y, box_width, box_height in boxes:
        area = float(box_width * box_height)
        faces.append(
            {
                "x": round(float(x) / width, 4),
                "y": round(float(y) / height, 4),
                "width": round(float(box_width) / width, 4),
                "height": round(float(box_height) / height, 4),
                "center_x": round((float(x) + float(box_width) / 2) / width, 4),
                "center_y": round((float(y) + float(box_height) / 2) / height, 4),
                "area": round(area / float(width * height), 5),
            }
        )
    return sorted(faces, key=lambda face: face["area"], reverse=True)


def photo_effect(photo_kind: str) -> dict[str, float | str]:
    if photo_kind == "person":
        return {"name": "portrait_face_push", "zoom_start": 1.045, "zoom_end": 1.075, "pan_x": 18.0, "pan_y": 8.0}
    if photo_kind == "landscape":
        return {"name": "landscape_slow_drift", "zoom_start": 1.03, "zoom_end": 1.065, "pan_x": 82.0, "pan_y": 18.0}
    return {"name": "object_focus_push", "zoom_start": 1.04, "zoom_end": 1.07, "pan_x": 42.0, "pan_y": 14.0}


def analyze_still_image(path: Path, kind: str) -> dict[str, Any]:
    try:
        with Image.open(path) as image:
            width, height = image.size
    except Exception:
        width, height = 0, 0
    aspect = (width / height) if height else 1.0
    if kind in {"text", "diagram"}:
        return {
            "kind": kind,
            "width": width,
            "height": height,
            "aspect": round(aspect, 4),
            "photo_kind": None,
            "focus": [0.5, 0.5],
            "faces": [],
            "effect": {"name": "static_readable_fade"},
        }

    faces = detect_photo_faces(path)
    if faces:
        primary = faces[0]
        photo_kind = "person"
        focus = (float(primary["center_x"]), float(primary["center_y"]))
    else:
        photo_kind = "landscape" if aspect >= 1.25 else "object"
        focus = weighted_focus(path)

    return {
        "kind": "photo",
        "width": width,
        "height": height,
        "aspect": round(aspect, 4),
        "photo_kind": photo_kind,
        "focus": [round(focus[0], 4), round(focus[1], 4)],
        "faces": faces[:3],
        "effect": photo_effect(photo_kind),
    }


def parse_still_images() -> list[dict[str, Any]]:
    stills = []
    configured_stills = list_value("assets", "stillImages")
    if not configured_stills:
        configured_stills = [
            item
            for item in manifest_files("image")
            if item.get("role") == "still"
        ]
    for item in configured_stills:
        path = Path(item.get("path", "")) if isinstance(item, dict) else Path(str(item))
        if not path or path.suffix.lower() not in IMAGE_EXTENSIONS or not path.exists():
            continue
        explicit_text = str(item.get("text", "")).strip() if isinstance(item, dict) else ""
        image_text = explicit_text or visual_text(path)
        text = image_text or path.stem.replace("_", " ")
        kind = str(item.get("kind", "")).strip() if isinstance(item, dict) else ""
        kind = kind or still_kind(path, image_text)
        analysis = analyze_still_image(path, kind)
        duration = float(item.get("duration", 0) or 0) if isinstance(item, dict) else 0.0
        stills.append(
            {
                "path": path,
                "text": text,
                "kind": analysis["kind"],
                "analysis": analysis,
                "effect": analysis["effect"],
                "duration": duration if duration > 0 else float(nested(APP_CONFIG, "render", "stillDuration", default=DEFAULT_STILL_DURATION)),
            }
        )
    return stills


def text_match_score(query: str, candidate: str) -> float:
    query_norm = normalize_text(query)
    candidate_norm = normalize_text(candidate)
    if len(query_norm) < 3 or len(candidate_norm) < 3:
        return 0.0
    query_chars = set(query_norm)
    candidate_chars = set(candidate_norm)
    overlap = len(query_chars & candidate_chars) / max(1, min(len(query_chars), len(candidate_chars)))
    substring_bonus = 0.22 if query_norm in candidate_norm or candidate_norm in query_norm else 0.0
    return min(1.0, overlap + substring_bonus)


def transcript_captions(captions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if captions:
        return [
            {
                "start": seconds(item["start"]),
                "end": seconds(item["end"]),
                "text": "".join(item.get("lines") or []),
            }
            for item in captions
        ]
    srt = selected_subtitle_path(APP_CONFIG, extensions=(".srt",))
    if srt is None:
        return []
    rows = []
    for block in re.split(r"\n\s*\n", srt.read_text(encoding="utf-8", errors="ignore")):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 3 or "-->" not in lines[1]:
            continue
        start_raw, end_raw = [part.strip() for part in lines[1].split("-->")]
        rows.append({"start": seconds(timestamp_to_filter_time(start_raw)), "end": seconds(timestamp_to_filter_time(end_raw)), "text": "".join(lines[2:])})
    return rows


def load_subtitle_speaker_roles() -> dict[str, str]:
    path_text = str(nested(APP_CONFIG, "subtitleSpeakers", "outputPath", default="") or "").strip()
    path = resolve_project_path(path_text) if path_text else OUTPUT_REPORTS / "full_transcript_speaker_roles.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    roles = payload.get("roles") if isinstance(payload, dict) else {}
    return {str(key): str(value).lower() for key, value in roles.items()} if isinstance(roles, dict) else {}


def subtitle_planning_items() -> list[dict[str, Any]]:
    srt = selected_subtitle_path(APP_CONFIG, extensions=(".srt",))
    if srt is None or not srt.exists():
        return []
    roles = load_subtitle_speaker_roles()
    items: list[dict[str, Any]] = []
    for block in re.split(r"\n\s*\n", srt.read_text(encoding="utf-8", errors="ignore")):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 3 or "-->" not in lines[1]:
            continue
        try:
            source_index = int(lines[0])
        except ValueError:
            source_index = len(items) + 1
        start_raw, end_raw = [part.strip() for part in lines[1].split("-->", 1)]
        items.append(
            {
                "source_index": source_index,
                "start": timestamp_to_filter_time(start_raw),
                "end": timestamp_to_filter_time(end_raw),
                "speaker_role": roles.get(str(source_index), "onscreen"),
                "lines": ["".join(lines[2:])],
            }
        )
    return items


def timestamp_to_filter_time(value: str) -> str:
    hours, minutes, rest = value.replace(",", ".").split(":")
    return f"{int(hours)}:{int(minutes):02d}:{float(rest):05.2f}"


def plan_still_inserts(stills: list[dict[str, Any]], captions: list[dict[str, Any]], timeline_start: float, duration: float) -> list[dict[str, Any]]:
    if not stills:
        return []
    transcript = transcript_captions(captions)
    inserts: list[dict[str, Any]] = []
    fallback_index = 0
    for index, still in enumerate(stills):
        still_duration = max(1.0, min(float(still["duration"]), max(1.0, duration / 3)))
        best = None
        if still["kind"] in {"text", "diagram"} and transcript:
            scored = [
                (text_match_score(str(still["text"]), row["text"]), row)
                for row in transcript
                if timeline_start <= row["start"] < timeline_start + duration
            ]
            best = max(scored, key=lambda item: item[0]) if scored else None
        if best and best[0] >= 0.34:
            start_t = max(0.0, min(float(best[1]["start"]) - timeline_start, duration - still_duration))
            reason = f"matched transcript score {best[0]:.3f}: {best[1]['text'][:40]}"
        else:
            fallback_index += 1
            start_t = min(max(1.0, duration * fallback_index / (len(stills) + 1)), max(0.0, duration - still_duration))
            reason = "fallback evenly spaced insert"
        while any(start_t < item["end"] and start_t + still_duration > item["start"] for item in inserts):
            start_t = min(start_t + 1.0, max(0.0, duration - still_duration))
            if start_t + still_duration >= duration:
                break
        inserts.append({**still, "start": round(start_t, 3), "end": round(start_t + still_duration, 3), "reason": reason, "input_index": None})
    return sorted(inserts, key=lambda item: item["start"])


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def ratio_list(value: object, length: int) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) < length:
        return None
    values: list[float] = []
    for item in value[:length]:
        try:
            values.append(float(item))
        except (TypeError, ValueError):
            return None
    return values


def constrain_window_center_for_box(
    window_center: float,
    visible_ratio: float,
    box_start: float,
    box_end: float,
    start_margin: float,
    end_margin: float,
    low: float,
    high: float,
) -> float:
    raw_start = clamp(min(box_start, box_end), 0.0, 1.0)
    raw_end = clamp(max(box_start, box_end), 0.0, 1.0)
    min_center = raw_end - (0.5 - end_margin) * visible_ratio
    max_center = raw_start + (0.5 - start_margin) * visible_ratio
    if min_center <= max_center:
        return clamp(window_center, max(low, min_center), min(high, max_center))
    box_center = (raw_start + raw_end) / 2
    return clamp(box_center, low, high)


def load_reference_profile() -> dict[str, object]:
    if not path_value("assets", "referenceVideo"):
        return {}
    path = Path(nested(APP_CONFIG, "analysis", "referenceEditProfilePath", default=str(DEFAULT_REFERENCE_PROFILE)))
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def visual_adjustment_filter(visual: dict[str, object]) -> str:
    brightness = visual.get("brightness")
    contrast = visual.get("contrast")
    saturation = visual.get("saturation")
    brightness_adj = clamp((float(brightness) - 0.48) * 0.22, -0.08, 0.08) if brightness is not None else 0.0
    contrast_adj = clamp(0.88 + float(contrast) * 1.15, 0.88, 1.24) if contrast is not None else 1.0
    saturation_adj = clamp(0.78 + float(saturation) * 1.15, 0.78, 1.34) if saturation is not None else 1.0
    return f"eq=brightness={brightness_adj:.4f}:contrast={contrast_adj:.4f}:saturation={saturation_adj:.4f}"


def global_video_zoom_value() -> float:
    raw_zoom = nested(APP_CONFIG, "render", "globalVideoZoom", default=None)
    if raw_zoom is not None and raw_zoom != "":
        try:
            return clamp(float(raw_zoom), 1.0, 2.0)
        except (TypeError, ValueError):
            return 1.0
    crop_percent = float_config("render", "cropPercent", default=0.0)
    if crop_percent <= 0:
        return 1.0
    visible_ratio = clamp((100.0 - crop_percent) / 100.0, 0.5, 1.0)
    return clamp(1.0 / visible_ratio, 1.0, 2.0)


def global_video_zoom_filter(zoom: float, center_x: float = 0.5, center_y: float = 0.5) -> str:
    if zoom <= 1.0001:
        return ""
    scaled_width = max(1920, round((1920 * zoom) / 2) * 2)
    scaled_height = max(1080, round((1080 * zoom) / 2) * 2)
    center_x = clamp(center_x, 0.0, 1.0)
    center_y = clamp(center_y, 0.0, 1.0)
    return (
        "scale="
        f"w='if(gte(iw/ih\\,1.777778)\\,-2\\,{scaled_width})':"
        f"h='if(gte(iw/ih\\,1.777778)\\,{scaled_height}\\,-2)',"
        f"crop=1920:1080:x='min(max(iw*{center_x:.6f}-960\\,0)\\,iw-1920)':"
        f"y='min(max(ih*{center_y:.6f}-540\\,0)\\,ih-1080)',setsar=1"
    )


def crop_filter_from_subject_target(
    center_x: float,
    center_y: float,
    area_ratio: float,
    desired_subject_x: float,
    desired_subject_y: float,
    protect_bbox_ratio: list[float] | None = None,
) -> str:
    visible_ratio = visible_ratio_for_area(area_ratio)
    window_center_x = crop_window_center_for_subject(clamp(center_x, 0.2, 0.8), clamp(desired_subject_x, 0.35, 0.65), visible_ratio)
    window_center_y = crop_window_center_for_subject(clamp(center_y, 0.25, 0.75), clamp(desired_subject_y, 0.30, 0.52), visible_ratio)
    if protect_bbox_ratio and len(protect_bbox_ratio) >= 4:
        left, top, right, bottom = [clamp(float(value), 0.0, 1.0) for value in protect_bbox_ratio[:4]]
        window_center_x = constrain_window_center_for_box(
            window_center_x,
            visible_ratio,
            left,
            right,
            start_margin=0.07,
            end_margin=0.07,
            low=0.2,
            high=0.8,
        )
        window_center_y = constrain_window_center_for_box(
            window_center_y,
            visible_ratio,
            top,
            bottom,
            start_margin=0.075,
            end_margin=0.14,
            low=0.25,
            high=0.75,
        )
    scale_w = round(1920 / visible_ratio / 2) * 2
    scale_h = round(1080 / visible_ratio / 2) * 2
    crop_x = f"min(max(iw*{window_center_x:.4f}-960\\,0)\\,iw-1920)"
    crop_y = f"min(max(ih*{window_center_y:.4f}-540\\,0)\\,ih-1080)"
    return f"scale={scale_w}:{scale_h},crop=1920:1080:x='{crop_x}':y='{crop_y}'"


def reference_visual_filter(profile: dict[str, object]) -> str:
    target = profile.get("target") if isinstance(profile.get("target"), dict) else {}
    visual = target.get("visual_style") if isinstance(target.get("visual_style"), dict) else {}
    return visual_adjustment_filter(visual)


def reference_video_filter(profile: dict[str, object]) -> str:
    target = profile.get("target") if isinstance(profile.get("target"), dict) else {}
    center = (
        target.get("face_focus_ratio")
        if isinstance(target.get("face_focus_ratio"), list)
        else target.get("person_center_ratio")
        if isinstance(target.get("person_center_ratio"), list)
        else None
    )
    area = target.get("person_area_ratio")
    face_direction = str(target.get("dominant_face_direction") or "unknown")
    desired_subject_x = target.get("desired_subject_x_ratio")
    desired_subject_y = target.get("desired_subject_y_ratio")
    protect_bbox = ratio_list(target.get("face_protect_bbox_ratio") or target.get("face_bbox_ratio"), 4)

    center_x = clamp(float(center[0]), 0.2, 0.8) if center and center[0] is not None else 0.5
    center_y = clamp(float(center[1]), 0.25, 0.75) if center and center[1] is not None else 0.5
    area_ratio = float(area) if area is not None else 0.0

    if desired_subject_x is None:
        desired_subject_x = subject_target_for_face(face_direction).x
    if desired_subject_y is None:
        desired_subject_y = subject_target_for_face(face_direction).y
    return (
        f"{crop_filter_from_subject_target(center_x, center_y, area_ratio, float(desired_subject_x), float(desired_subject_y), protect_bbox)},"
        f"{reference_visual_filter(profile)}"
    )


def dynamic_reframe_filter(segment_index: int, role: str, reference_style_filter: str) -> str:
    if role == "master":
        pattern = [
            (0.92, 0.50, 0.04),
            (0.84, 0.58, 0.06),
            (0.88, 0.42, 0.05),
        ]
    else:
        pattern = [
            (0.76, 0.68, 0.06),
            (0.88, 0.44, 0.04),
            (0.72, 0.60, 0.08),
            (0.82, 0.52, 0.05),
        ]
    crop, x_bias, y_bias = pattern[segment_index % len(pattern)]
    crop = clamp(crop, 0.55, 1.0)
    x_bias = clamp(x_bias, 0.0, 1.0)
    y_bias = clamp(y_bias, 0.0, 1.0)
    base = (
        f"crop=w='iw*{crop:.6f}':h='ih*{crop:.6f}':"
        f"x='(iw-ow)*{x_bias:.6f}':y='(ih-oh)*{y_bias:.6f}',scale=1920:1080"
    )
    return f"{base},{reference_style_filter}" if reference_style_filter else base


def canonical_path_key(path: Path) -> str:
    try:
        return str(path.resolve()).casefold()
    except OSError:
        return str(path).casefold()


def person_edit_plan_keys(plan: dict[str, object], path: Path) -> set[str]:
    keys = {path.name.casefold(), path.stem.casefold()}
    for suffix in ("_person_edit_plan", "_person_bboxes"):
        if path.stem.casefold().endswith(suffix):
            keys.add(path.stem.casefold()[: -len(suffix)])
    for field in ("video_path", "video"):
        value = plan.get(field)
        if not value:
            continue
        candidate = Path(str(value))
        keys.add(str(value).casefold())
        keys.add(candidate.name.casefold())
        keys.add(candidate.stem.casefold())
        for suffix in ("_person_edit_plan", "_person_bboxes"):
            if candidate.stem.casefold().endswith(suffix):
                keys.add(candidate.stem.casefold()[: -len(suffix)])
        if candidate.exists():
            keys.add(canonical_path_key(candidate))
    return keys


def load_person_edit_plans(cameras: list[tuple[str, Path]]) -> tuple[dict[str, dict[str, object]], dict[str, object]]:
    enabled = bool_value("render", "usePersonEditPlans", default=True)
    plan_dir = path_value("analysis", "personEditPlansDir") or DEFAULT_PERSON_EDIT_PLANS
    report: dict[str, object] = {
        "enabled": enabled,
        "directory": str(plan_dir),
        "matched": [],
        "missingCameraPlans": [],
        "segments": [],
    }
    if not enabled:
        return {}, report
    if not plan_dir.exists():
        report["reason"] = "person edit plan directory does not exist"
        return {}, report

    camera_keys = {
        role: {canonical_path_key(path), path.name.casefold(), path.stem.casefold()}
        for role, path in cameras
    }
    plans: dict[str, dict[str, object]] = {}
    for plan_path in sorted(plan_dir.glob("*_person_edit_plan.json")):
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(plan, dict):
            continue
        keys = person_edit_plan_keys(plan, plan_path)
        for role, keys_for_camera in camera_keys.items():
            if role in plans or keys.isdisjoint(keys_for_camera):
                continue
            plans[role] = plan
            cast_list = report["matched"]
            if isinstance(cast_list, list):
                cast_list.append({"role": role, "plan": str(plan_path), "video": plan.get("video_path") or plan.get("video")})

    missing = report["missingCameraPlans"]
    if isinstance(missing, list):
        missing.extend(role for role, _ in cameras if role not in plans)
    return plans, report


def person_plan_segment_at(plan: dict[str, object], source_time: float) -> dict[str, object] | None:
    segments = plan.get("segments")
    if not isinstance(segments, list):
        return None
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        try:
            start_t = float(segment.get("start", 0.0))
            end_t = float(segment.get("end", start_t))
        except (TypeError, ValueError):
            continue
        if start_t <= source_time < end_t:
            return segment
    return None


def person_plan_crop_filter(segment: dict[str, object]) -> str | None:
    crop_target = segment.get("crop_target")
    if not isinstance(crop_target, dict):
        return None
    try:
        center_x = float(crop_target.get("focus_x", crop_target["x"]))
        center_y = float(crop_target.get("focus_y", crop_target["y"]))
        desired_x = float(crop_target.get("desired_subject_x_ratio", segment.get("desired_subject_x_ratio", 0.5)))
        desired_y = float(crop_target.get("desired_subject_y_ratio", segment.get("desired_subject_y_ratio", 0.382)))
        area_ratio = float(segment.get("avg_area_ratio") or 0.0)
    except (KeyError, TypeError, ValueError):
        return None
    protect_bbox = ratio_list(
        crop_target.get("protect_bbox_ratio")
        or segment.get("avg_face_protect_bbox_ratio")
        or crop_target.get("face_bbox_ratio")
        or segment.get("avg_face_bbox_ratio"),
        4,
    )
    return crop_filter_from_subject_target(center_x, center_y, area_ratio, desired_x, desired_y, protect_bbox)


def camera_segment_visual_filter(
    fallback_filter: str,
    reference_style_filter: str,
    person_plans: dict[str, dict[str, object]],
    role: str,
    source_time: float,
) -> tuple[str, dict[str, object] | None]:
    plan = person_plans.get(role)
    if not plan:
        return fallback_filter, None
    segment = person_plan_segment_at(plan, source_time)
    if not segment:
        return fallback_filter, None
    crop_filter = person_plan_crop_filter(segment)
    if not crop_filter:
        return fallback_filter, None
    visual_filter = crop_filter
    if reference_style_filter:
        visual_filter = f"{visual_filter},{reference_style_filter}"
    detail = {
        "role": role,
        "sourceTime": round(source_time, 3),
        "planStart": segment.get("start"),
        "planEnd": segment.get("end"),
        "presence": segment.get("presence"),
        "cropStrategy": segment.get("crop_strategy"),
        "position": segment.get("position"),
        "shotSize": segment.get("shot_size"),
        "faceDirection": segment.get("face_direction"),
        "rawFaceDirection": segment.get("raw_face_direction"),
        "directionSource": segment.get("direction_source"),
        "focusSource": segment.get("avg_focus_source"),
        "focusRatio": segment.get("avg_focus_ratio"),
        "faceCenterRatio": segment.get("avg_face_center_ratio"),
        "faceProtectBboxRatio": segment.get("avg_face_protect_bbox_ratio"),
        "cropTarget": segment.get("crop_target"),
        "isFixedCamera": plan.get("is_fixed_camera"),
        "cameraMotionType": plan.get("camera_motion_type"),
    }
    return visual_filter, detail


def frame_visual_stats(path: Path, timestamps: list[float]) -> dict[str, Any] | None:
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
    except Exception:
        return None

    def robust_scalar_mean(values: Any) -> float:
        arr = np.asarray(values, dtype=np.float32).reshape(-1)
        arr = arr[np.isfinite(arr)]
        if arr.size == 0:
            return 0.0
        if arr.size >= 64:
            low, high = np.percentile(arr, [8, 92])
            trimmed = arr[(arr >= low) & (arr <= high)]
            if trimmed.size:
                arr = trimmed
        return float(np.mean(arr))

    def robust_bgr_mean(samples: Any) -> list[float]:
        arr = np.asarray(samples, dtype=np.float32).reshape(-1, 3)
        if arr.size == 0:
            return [0.0, 0.0, 0.0]
        return [robust_scalar_mean(arr[:, channel]) / 255.0 for channel in range(3)]

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return None
    face_detector = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"))
    rows: list[dict[str, float]] = []
    skin_rows: list[dict[str, float]] = []
    for timestamp in timestamps:
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, timestamp) * 1000.0)
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        height, width = frame.shape[:2]
        if width <= 0 or height <= 0:
            continue
        scale = min(1.0, 480.0 / float(width))
        if scale < 1.0:
            frame = cv2.resize(frame, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        ycrcb = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)
        frame_skin_mask = (
            (ycrcb[:, :, 1] >= 138)
            & (ycrcb[:, :, 1] <= 174)
            & (ycrcb[:, :, 2] >= 78)
            & (ycrcb[:, :, 2] <= 130)
            & (hsv[:, :, 1] >= 25)
            & (hsv[:, :, 1] <= 165)
            & (hsv[:, :, 2] >= 60)
        )
        neutral_mask = (hsv[:, :, 1] < 90) & (hsv[:, :, 2] > 80) & (hsv[:, :, 2] < 245)
        background_mask = neutral_mask & (~frame_skin_mask)
        neutral_samples = frame[neutral_mask]
        if len(neutral_samples) < 500:
            neutral_samples = frame.reshape(-1, 3)
        skin_samples = None
        skin_source = "none"
        face_bbox: tuple[int, int, int, int] | None = None
        if not face_detector.empty():
            faces = face_detector.detectMultiScale(gray, 1.08, 5, minSize=(40, 40))
            if len(faces):
                x, y, w, h = max(faces, key=lambda rect: rect[2] * rect[3])
                face_bbox = (int(x), int(y), int(w), int(h))
                x1 = max(0, int(x + w * 0.12))
                x2 = min(frame.shape[1], int(x + w * 0.88))
                y1 = max(0, int(y + h * 0.30))
                y2 = min(frame.shape[0], int(y + h * 0.86))
                roi = frame[y1:y2, x1:x2]
                roi_hsv = hsv[y1:y2, x1:x2]
                roi_ycrcb = ycrcb[y1:y2, x1:x2]
                if roi.size:
                    skin_mask = (
                        (roi_ycrcb[:, :, 1] >= 133)
                        & (roi_ycrcb[:, :, 1] <= 178)
                        & (roi_ycrcb[:, :, 2] >= 72)
                        & (roi_ycrcb[:, :, 2] <= 135)
                        & (roi_hsv[:, :, 1] >= 22)
                        & (roi_hsv[:, :, 1] <= 175)
                        & (roi_hsv[:, :, 2] >= 55)
                    )
                    samples = roi[skin_mask]
                    if len(samples) >= 90:
                        skin_samples = samples
                        skin_source = "face-skin-mask"
        if skin_samples is None:
            # Fall back to a conservative full-frame skin mask. This is weaker than face ROI,
            # but keeps fixed-camera shots from losing color matching entirely.
            samples = frame[frame_skin_mask]
            if 300 <= len(samples) <= frame.shape[0] * frame.shape[1] * 0.18:
                skin_samples = samples
                skin_source = "frame-skin-mask"
        if face_bbox is not None:
            x, y, w, h = face_bbox
            bx1 = max(0, int(x - w * 0.35))
            bx2 = min(frame.shape[1], int(x + w * 1.35))
            by1 = max(0, int(y - h * 0.35))
            by2 = min(frame.shape[0], int(y + h * 1.90))
            background_mask[by1:by2, bx1:bx2] = False
        background_samples = frame[background_mask]
        background_gray = gray[background_mask]
        background_hsv = hsv[background_mask]
        if len(background_samples) < 500:
            background_samples = neutral_samples
            background_gray = cv2.cvtColor(background_samples.reshape(-1, 1, 3), cv2.COLOR_BGR2GRAY).reshape(-1)
            background_hsv = cv2.cvtColor(background_samples.reshape(-1, 1, 3), cv2.COLOR_BGR2HSV).reshape(-1, 3)
        mean_bgr = robust_bgr_mean(frame.reshape(-1, 3))
        neutral_bgr = robust_bgr_mean(neutral_samples)
        background_bgr = robust_bgr_mean(background_samples)
        rows.append(
            {
                "brightness": robust_scalar_mean(gray) / 255.0,
                "contrast": float(np.std(gray)) / 255.0,
                "saturation": robust_scalar_mean(hsv[:, :, 1]) / 255.0,
                "background_brightness": robust_scalar_mean(background_gray) / 255.0,
                "background_saturation": robust_scalar_mean(background_hsv[:, 1]) / 255.0,
                "mean_b": float(mean_bgr[0]),
                "mean_g": float(mean_bgr[1]),
                "mean_r": float(mean_bgr[2]),
                "neutral_b": float(neutral_bgr[0]),
                "neutral_g": float(neutral_bgr[1]),
                "neutral_r": float(neutral_bgr[2]),
                "background_b": float(background_bgr[0]),
                "background_g": float(background_bgr[1]),
                "background_r": float(background_bgr[2]),
            }
        )
        if skin_samples is not None:
            skin_bgr = robust_bgr_mean(skin_samples)
            skin_hsv = cv2.cvtColor(skin_samples.reshape(-1, 1, 3), cv2.COLOR_BGR2HSV).reshape(-1, 3)
            skin_rows.append(
                {
                    "skin_b": float(skin_bgr[0]),
                    "skin_g": float(skin_bgr[1]),
                    "skin_r": float(skin_bgr[2]),
                    "skin_brightness": robust_scalar_mean(skin_hsv[:, 2]) / 255.0,
                    "skin_saturation": robust_scalar_mean(skin_hsv[:, 1]) / 255.0,
                    "skin_pixel_count": float(len(skin_samples)),
                    "skin_source": 1.0 if skin_source == "face-skin-mask" else 0.0,
                }
            )
    cap.release()
    if not rows:
        return None
    stats = {
        "brightness": sum(row["brightness"] for row in rows) / len(rows),
        "contrast": sum(row["contrast"] for row in rows) / len(rows),
        "saturation": sum(row["saturation"] for row in rows) / len(rows),
        "backgroundBrightness": sum(row["background_brightness"] for row in rows) / len(rows),
        "backgroundSaturation": sum(row["background_saturation"] for row in rows) / len(rows),
        "meanBgr": [
            sum(row["mean_b"] for row in rows) / len(rows),
            sum(row["mean_g"] for row in rows) / len(rows),
            sum(row["mean_r"] for row in rows) / len(rows),
        ],
        "neutralBgr": [
            sum(row["neutral_b"] for row in rows) / len(rows),
            sum(row["neutral_g"] for row in rows) / len(rows),
            sum(row["neutral_r"] for row in rows) / len(rows),
        ],
        "backgroundBgr": [
            sum(row["background_b"] for row in rows) / len(rows),
            sum(row["background_g"] for row in rows) / len(rows),
            sum(row["background_r"] for row in rows) / len(rows),
        ],
        "samples": float(len(rows)),
    }
    if skin_rows:
        stats.update(
            {
                "skinBgr": [
                    sum(row["skin_b"] for row in skin_rows) / len(skin_rows),
                    sum(row["skin_g"] for row in skin_rows) / len(skin_rows),
                    sum(row["skin_r"] for row in skin_rows) / len(skin_rows),
                ],
                "skinBrightness": sum(row["skin_brightness"] for row in skin_rows) / len(skin_rows),
                "skinSaturation": sum(row["skin_saturation"] for row in skin_rows) / len(skin_rows),
                "skinSamples": float(len(skin_rows)),
                "skinPixels": sum(row["skin_pixel_count"] for row in skin_rows),
                "skinFaceRoiSamples": sum(row["skin_source"] for row in skin_rows),
            }
        )
    return stats


def bgr_triplet(stats: dict[str, Any], key: str) -> list[float] | None:
    value = stats.get(key)
    if not isinstance(value, list) or len(value) != 3:
        return None
    try:
        return [float(value[0]), float(value[1]), float(value[2])]
    except (TypeError, ValueError):
        return None


def weighted_bgr_profile(stats: dict[str, Any]) -> list[float] | None:
    # Use wall/neutral pixels for white balance. Skin is useful for exposure/saturation,
    # but driving channel gains from skin can make a pale background turn green/cyan.
    weights = {"backgroundBgr": 0.80, "neutralBgr": 0.20, "meanBgr": 0.0, "skinBgr": 0.0}
    total = 0.0
    result = [0.0, 0.0, 0.0]
    for key, weight in weights.items():
        triplet = bgr_triplet(stats, key)
        if triplet is None:
            continue
        total += weight
        for index in range(3):
            result[index] += triplet[index] * weight
    if total <= 0:
        return None
    return [value / total for value in result]


def color_temperature_adjustment(master: dict[str, Any], item: dict[str, Any], strength: float) -> dict[str, float]:
    master_bgr = weighted_bgr_profile(master) or bgr_triplet(master, "neutralBgr") or bgr_triplet(master, "meanBgr")
    item_bgr = weighted_bgr_profile(item) or bgr_triplet(item, "neutralBgr") or bgr_triplet(item, "meanBgr")
    if master_bgr is None or item_bgr is None:
        return {"red": 1.0, "blue": 1.0, "targetRb": None, "itemRb": None, "ratio": None}
    target_rb = master_bgr[2] / max(master_bgr[0], 0.025)
    item_rb = item_bgr[2] / max(item_bgr[0], 0.025)
    ratio = clamp(target_rb / max(item_rb, 0.025), 0.72, 1.28)
    # Color temperature should not change exposure; push red/blue in opposite directions.
    factor = ratio ** (clamp(strength, 0.0, 1.0) * 0.5)
    return {
        "red": clamp(factor, 0.90, 1.10),
        "blue": clamp(1.0 / max(factor, 0.001), 0.90, 1.10),
        "targetRb": target_rb,
        "itemRb": item_rb,
        "ratio": ratio,
    }


def color_channel_gains(
    master: dict[str, Any],
    item: dict[str, Any],
    *,
    temperature_enabled: bool,
    temperature_strength: float,
) -> dict[str, float]:
    master_bgr = weighted_bgr_profile(master) or bgr_triplet(master, "neutralBgr") or bgr_triplet(master, "meanBgr")
    item_bgr = weighted_bgr_profile(item) or bgr_triplet(item, "neutralBgr") or bgr_triplet(item, "meanBgr")
    if master_bgr is None or item_bgr is None:
        return {"red": 1.0, "green": 1.0, "blue": 1.0, "temperature": {"enabled": False}}
    blue = clamp(master_bgr[0] / max(item_bgr[0], 0.025), 0.88, 1.14)
    green = clamp(master_bgr[1] / max(item_bgr[1], 0.025), 0.88, 1.14)
    red = clamp(master_bgr[2] / max(item_bgr[2], 0.025), 0.88, 1.14)
    temperature = color_temperature_adjustment(master, item, temperature_strength) if temperature_enabled else {
        "red": 1.0,
        "blue": 1.0,
        "targetRb": None,
        "itemRb": None,
        "ratio": None,
    }
    red = clamp(red * float(temperature["red"]), 0.86, 1.16)
    blue = clamp(blue * float(temperature["blue"]), 0.86, 1.16)
    return {"red": red, "green": green, "blue": blue, "temperature": {"enabled": temperature_enabled, **temperature}}


def weighted_saturation_profile(stats: dict[str, Any], skin_priority: bool) -> float:
    components: list[tuple[float, float]] = []
    if skin_priority and "skinSaturation" in stats:
        components.append((float(stats["skinSaturation"]), 0.15))
    if "backgroundSaturation" in stats:
        components.append((float(stats["backgroundSaturation"]), 0.30 if skin_priority else 0.45))
    components.append((float(stats["saturation"]), 0.55 if skin_priority else 0.55))
    total = sum(weight for _, weight in components)
    return sum(value * weight for value, weight in components) / max(total, 0.001)


def evenly_limited_times(values: list[float], max_count: int) -> list[float]:
    unique = sorted({round(value, 3) for value in values if value >= 0.0})
    if len(unique) <= max_count:
        return unique
    if max_count <= 1:
        return [unique[len(unique) // 2]]
    selected: list[float] = []
    for index in range(max_count):
        selected_index = round(index * (len(unique) - 1) / (max_count - 1))
        selected.append(unique[selected_index])
    return selected


def segment_source_local_sample_times(
    role: str,
    segments: list[tuple[str, int, float, float]],
    duration: float,
    replacements: list[dict[str, Any]] | None,
    max_count: int,
) -> list[float]:
    candidates: list[float] = []
    for segment_role, _, start_t, end_t in segments:
        if segment_role != role:
            continue
        start_t = clamp(start_t, 0.0, duration)
        end_t = clamp(end_t, 0.0, duration)
        segment_duration = end_t - start_t
        if segment_duration < 0.35:
            continue
        if segment_duration >= 12.0:
            fractions = (0.20, 0.50, 0.80)
        elif segment_duration >= 4.0:
            fractions = (0.35, 0.65)
        else:
            fractions = (0.50,)
        for fraction in fractions:
            output_local = start_t + segment_duration * fraction
            source_local = output_local_to_source_local(output_local, replacements) if replacements else output_local
            if source_local is not None:
                candidates.append(source_local)
    return evenly_limited_times(candidates, max_count)


def fallback_source_local_sample_times(duration: float, max_count: int) -> list[float]:
    count = max(2, max_count)
    return [duration * (index + 1) / (count + 1) for index in range(count)]


def camera_color_match_filters(
    cameras: list[tuple[str, Path]],
    start: float,
    duration: float,
    sync_offsets: dict[str, float] | None = None,
    segments: list[tuple[str, int, float, float]] | None = None,
    replacements: list[dict[str, Any]] | None = None,
) -> tuple[dict[int, str], dict[str, Any]]:
    report: dict[str, Any] = {
        "enabled": bool_value("render", "colorMatchCameras", default=False),
        "items": [],
        "sampleBasis": "actual camera plan" if segments else "preview duration",
    }
    if not report["enabled"] or len(cameras) < 2:
        return {}, report
    white_balance = bool_value("render", "colorMatchWhiteBalance", default=True)
    temperature_enabled = bool_value("render", "colorMatchTemperature", default=True)
    temperature_strength = float_config("render", "colorMatchTemperatureStrength", default=0.65)
    report["whiteBalance"] = white_balance
    report["temperatureMatch"] = {
        "enabled": temperature_enabled,
        "strength": round(clamp(temperature_strength, 0.0, 1.0), 4),
        "basis": "background/neutral red-blue ratio",
    }
    sample_count = max(2, min(int_value(APP_CONFIG, "render", "colorMatchSamples", default=5), 12))
    offsets = sync_offsets or {}
    master_role, master_path = cameras[0]
    master_local_times = (
        segment_source_local_sample_times(master_role, segments, duration, replacements, sample_count)
        if segments
        else fallback_source_local_sample_times(duration, sample_count)
    )
    if not master_local_times:
        master_local_times = fallback_source_local_sample_times(duration, sample_count)
    master_source_times = [max(0.0, start + value + offsets.get(master_role, 0.0)) for value in master_local_times]
    default_master = frame_visual_stats(master_path, master_source_times)
    if not default_master:
        report["reason"] = "master stats unavailable"
        return {}, report

    filters: dict[int, str] = {}
    for index, (role, path) in enumerate(cameras):
        role_local_times = (
            segment_source_local_sample_times(role, segments, duration, replacements, sample_count)
            if segments
            else fallback_source_local_sample_times(duration, sample_count)
        )
        if index > 0 and segments and not role_local_times:
            report["items"].append({"role": role, "path": str(path), "skipped": "not used in current camera plan"})
            continue
        if not role_local_times:
            role_local_times = fallback_source_local_sample_times(duration, sample_count)
        timeline_timestamps = [start + value for value in role_local_times]
        source_timestamps = [max(0.0, start + value + offsets.get(role, 0.0)) for value in role_local_times]
        item_stats = default_master if index == 0 else frame_visual_stats(path, source_timestamps)
        if not item_stats:
            report["items"].append(
                {
                    "role": role,
                    "path": str(path),
                    "skipped": "stats unavailable",
                    "sampleTimelineSeconds": [round(value, 3) for value in timeline_timestamps],
                    "sampleSourceSeconds": [round(value, 3) for value in source_timestamps],
                }
            )
            continue
        if index == 0:
            report["items"].append(
                {
                    "role": role,
                    "path": str(path),
                    "reference": True,
                    "stats": item_stats,
                    "sampleTimelineSeconds": [round(value, 3) for value in timeline_timestamps],
                    "sampleSourceSeconds": [round(value, 3) for value in source_timestamps],
                }
            )
            continue
        master = frame_visual_stats(master_path, [max(0.0, start + value + offsets.get(master_role, 0.0)) for value in role_local_times])
        if not master:
            master = default_master
        skin_priority = "skinBgr" in master and "skinBgr" in item_stats
        master_contrast = float(master["contrast"])
        item_contrast = float(item_stats["contrast"])
        master_global_brightness = float(master["brightness"])
        item_global_brightness = float(item_stats["brightness"])
        master_background_brightness = float(master.get("backgroundBrightness", master_global_brightness))
        item_background_brightness = float(item_stats.get("backgroundBrightness", item_global_brightness))
        master_skin_brightness = (
            float(master.get("skinBrightness", master_global_brightness)) if skin_priority else master_global_brightness
        )
        item_skin_brightness = (
            float(item_stats.get("skinBrightness", item_global_brightness)) if skin_priority else item_global_brightness
        )
        master_saturation = weighted_saturation_profile(master, skin_priority)
        item_saturation = weighted_saturation_profile(item_stats, skin_priority)
        skin_delta = master_skin_brightness - item_skin_brightness
        global_delta = master_global_brightness - item_global_brightness
        background_delta = master_background_brightness - item_background_brightness
        # Close-up shots can match skin while still looking dark overall; blend scene/background
        # brightness into the correction instead of letting skin samples fully override it.
        brightness_delta = (skin_delta * 0.20 + global_delta * 0.45 + background_delta * 0.35) if skin_priority else global_delta
        brightness_adj = clamp(brightness_delta * 0.42, -0.12, 0.12)
        contrast_adj = 1.0 if master_contrast < 0.025 and item_contrast < 0.025 else clamp(master_contrast / max(item_contrast, 0.025), 0.84, 1.18)
        saturation_adj = (
            1.0
            if master_saturation < 0.08 and item_saturation < 0.08
            else clamp(master_saturation / max(item_saturation, 0.025), 0.84, 1.16)
        )
        gains = (
            color_channel_gains(
                master,
                item_stats,
                temperature_enabled=temperature_enabled,
                temperature_strength=temperature_strength,
            )
            if white_balance
            else {"red": 1.0, "green": 1.0, "blue": 1.0, "temperature": {"enabled": False}}
        )
        filter_parts: list[str] = []
        if max(abs(gains["red"] - 1.0), abs(gains["green"] - 1.0), abs(gains["blue"] - 1.0)) >= 0.018:
            filter_parts.append(
                f"colorchannelmixer=rr={gains['red']:.5f}:gg={gains['green']:.5f}:bb={gains['blue']:.5f}"
            )
        if abs(brightness_adj) >= 0.006 or abs(contrast_adj - 1.0) >= 0.025 or abs(saturation_adj - 1.0) >= 0.025:
            filter_parts.append(f"eq=brightness={brightness_adj:.4f}:contrast={contrast_adj:.4f}:saturation={saturation_adj:.4f}")
        if not filter_parts:
            report["items"].append({"role": role, "path": str(path), "stats": item_stats, "filter": "none"})
            continue
        filters[index] = ",".join(filter_parts)
        report["items"].append(
            {
                "role": role,
                "path": str(path),
                "stats": item_stats,
                "referenceStats": master,
                "sampleTimelineSeconds": [round(value, 3) for value in timeline_timestamps],
                "sampleSourceSeconds": [round(value, 3) for value in source_timestamps],
                "referenceSourceSeconds": [
                    round(max(0.0, start + value + offsets.get(master_role, 0.0)), 3) for value in role_local_times
                ],
                "redGain": round(gains["red"], 5),
                "greenGain": round(gains["green"], 5),
                "blueGain": round(gains["blue"], 5),
                "temperatureMatch": {
                    "enabled": bool(gains.get("temperature", {}).get("enabled")),
                    "targetRb": round(float(gains["temperature"]["targetRb"]), 5)
                    if gains.get("temperature", {}).get("targetRb") is not None
                    else None,
                    "itemRb": round(float(gains["temperature"]["itemRb"]), 5)
                    if gains.get("temperature", {}).get("itemRb") is not None
                    else None,
                    "ratio": round(float(gains["temperature"]["ratio"]), 5)
                    if gains.get("temperature", {}).get("ratio") is not None
                    else None,
                    "redMultiplier": round(float(gains["temperature"].get("red", 1.0)), 5),
                    "blueMultiplier": round(float(gains["temperature"].get("blue", 1.0)), 5),
                },
                "brightness": round(brightness_adj, 5),
                "brightnessComponents": {
                    "skinDelta": round(skin_delta, 5),
                    "globalDelta": round(global_delta, 5),
                    "backgroundDelta": round(background_delta, 5),
                    "weightedDelta": round(brightness_delta, 5),
                },
                "contrast": round(contrast_adj, 5),
                "saturation": round(saturation_adj, 5),
                "saturationComponents": {
                    "masterWeighted": round(master_saturation, 5),
                    "itemWeighted": round(item_saturation, 5),
                    "masterSkin": round(float(master.get("skinSaturation", master["saturation"])), 5) if skin_priority else None,
                    "itemSkin": round(float(item_stats.get("skinSaturation", item_stats["saturation"])), 5) if skin_priority else None,
                    "masterBackground": round(float(master.get("backgroundSaturation", master["saturation"])), 5),
                    "itemBackground": round(float(item_stats.get("backgroundSaturation", item_stats["saturation"])), 5),
                    "masterGlobal": round(float(master["saturation"]), 5),
                    "itemGlobal": round(float(item_stats["saturation"]), 5),
                },
                "colorMatchBasis": "skin+global+background" if skin_priority else "global",
                "filter": filters[index],
            }
        )
    COLOR_MATCH_REPORT.parent.mkdir(parents=True, exist_ok=True)
    COLOR_MATCH_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return filters, report


def configured_camera_extra_filters(cameras: list[tuple[str, Path]]) -> tuple[dict[int, str], list[dict[str, str]]]:
    configured = nested(APP_CONFIG, "render", "cameraExtraFilters", default={})
    if not isinstance(configured, dict):
        return {}, []
    filters: dict[int, str] = {}
    report: list[dict[str, str]] = []
    for index, (role, path) in enumerate(cameras):
        value = configured.get(role) or configured.get(path.name) or configured.get(path.stem)
        if not value:
            continue
        text = str(value).strip()
        if not text:
            continue
        filters[index] = text
        report.append({"role": role, "path": str(path), "filter": text})
    return filters, report


def load_face_center_crop_plan() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    enabled = bool_value("render", "faceCenterCrop", default=False)
    plan_path = path_value("render", "faceCenterCropPlanPath") or (OUTPUT_REPORTS / "face_center_crop_plan.json")
    report: dict[str, Any] = {
        "enabled": enabled,
        "plan": str(plan_path),
        "segments": [],
        "fallbackSegments": [],
    }
    if not enabled:
        report["reason"] = "disabled"
        return [], report
    if not plan_path.exists():
        report["reason"] = "plan missing"
        return [], report
    try:
        payload = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        report["reason"] = f"cannot read plan: {exc}"
        return [], report
    segments = payload.get("segments") if isinstance(payload, dict) else None
    if not isinstance(segments, list):
        report["reason"] = "plan has no segments"
        return [], report
    valid_segments = [segment for segment in segments if isinstance(segment, dict)]
    report["loadedSegments"] = len(valid_segments)
    return valid_segments, report


def face_center_crop_segment(
    plan_segments: list[dict[str, Any]],
    role: str,
    output_start: float,
    output_end: float,
) -> dict[str, Any] | None:
    midpoint = (output_start + output_end) / 2
    best: dict[str, Any] | None = None
    best_overlap = 0.0
    for segment in plan_segments:
        if str(segment.get("role") or "") != role:
            continue
        try:
            start_t = float(segment.get("start", 0.0))
            end_t = float(segment.get("end", start_t))
            center_x = float(segment.get("centerX", segment.get("center_x")))
            center_y = float(segment.get("centerY", segment.get("center_y")))
        except (TypeError, ValueError):
            continue
        if not (0.0 <= center_x <= 1.0 and 0.0 <= center_y <= 1.0):
            continue
        if start_t <= midpoint < end_t:
            return segment
        overlap = max(0.0, min(output_end, end_t) - max(output_start, start_t))
        if overlap > best_overlap:
            best = segment
            best_overlap = overlap
    return best if best_overlap > 0.0 else None


def face_center_crop_axis() -> str:
    value = text_config("render", "faceCenterCropAxis", default="x").strip().lower()
    if value in {"x", "horizontal", "horizontal-only"}:
        return "x"
    if value in {"xy", "both", "all"}:
        return "xy"
    return "x"


def face_center_subject_screen_x(role: str) -> float:
    by_role = nested(APP_CONFIG, "render", "faceCenterSubjectXByRole", default={})
    if isinstance(by_role, dict):
        value = by_role.get(role)
        if value is not None and value != "":
            try:
                return clamp(float(value), 0.35, 0.65)
            except (TypeError, ValueError):
                pass
    return clamp(float_config("render", "faceCenterSubjectX", default=0.5), 0.35, 0.65)


def adjusted_face_center_crop_x(center_x: float, zoom: float, subject_screen_x: float) -> float:
    if zoom <= 1.0001:
        return clamp(center_x, 0.0, 1.0)
    # Moving the crop window left makes the detected subject land slightly right.
    return clamp(center_x - ((subject_screen_x - 0.5) / zoom), 0.0, 1.0)


def run(command: list[str]) -> None:
    subprocess.run(command, check=True, cwd=WORK)


def normalized_path_key(path: Path) -> str:
    try:
        return str(path.resolve()).casefold()
    except OSError:
        return str(path).casefold()


def paths_match(left: str | Path | None, right: Path) -> bool:
    if not left:
        return False
    return normalized_path_key(Path(str(left))) == normalized_path_key(right)


def transcript_class_rank(value: Any) -> int:
    text = str(value or "").strip().lower().replace("-", "_")
    if text == "strong":
        return 2
    if text in {"usable", "usable_review"}:
        return 1
    return 0


def transcript_comparison_sync_offsets(
    report: dict[str, Any],
    sources: list[tuple[str, Path]],
    *,
    min_class: str = "strong",
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    source_paths = {role: path for role, path in sources}
    details: dict[str, Any] = {
        "enabled": True,
        "minClass": min_class,
        "primaryRole": "",
        "items": [],
    }
    if not source_paths:
        details["reason"] = "no render sync sources"
        return {}, details

    primary = report.get("primary", {})
    if not isinstance(primary, dict):
        details["reason"] = "comparison report has no primary transcript"
        return {}, details

    primary_role = str(primary.get("role") or "")
    primary_path = str(primary.get("path") or "")
    if primary_role not in source_paths or (primary_path and not paths_match(primary_path, source_paths[primary_role])):
        primary_role = next(
            (role for role, path in source_paths.items() if primary_path and paths_match(primary_path, path)),
            "",
        )
    if not primary_role:
        details["reason"] = "primary transcript is not one of the render sync sources"
        return {}, details

    details["primaryRole"] = primary_role
    min_rank = transcript_class_rank(min_class)
    if min_rank <= 0:
        min_rank = transcript_class_rank("strong")
    offset_to_primary: dict[str, dict[str, Any]] = {
        primary_role: {
            "offsetToPrimary": 0.0,
            "matchClass": "primary",
            "score": 1.0,
            "path": str(source_paths[primary_role]),
        }
    }
    for item in report.get("items", []):
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "")
        if role not in source_paths:
            continue
        item_path = str(item.get("path") or "")
        if item_path and not paths_match(item_path, source_paths[role]):
            details["items"].append({"role": role, "path": item_path, "used": False, "reason": "path mismatch"})
            continue
        match_class = str(item.get("bestClass") or "")
        if transcript_class_rank(match_class) < min_rank:
            details["items"].append(
                {
                    "role": role,
                    "path": item_path,
                    "used": False,
                    "matchClass": match_class or "no_match",
                    "reason": "below class threshold",
                }
            )
            continue
        offset_value = item.get("suggestedOffsetSeconds")
        if offset_value is None and isinstance(item.get("bestMatch"), dict):
            offset_value = item["bestMatch"].get("offsetSeconds")
        try:
            offset = float(offset_value)
        except (TypeError, ValueError):
            details["items"].append({"role": role, "path": item_path, "used": False, "reason": "missing offset"})
            continue
        score = item.get("bestScore")
        if score is None and isinstance(item.get("bestMatch"), dict):
            score = item["bestMatch"].get("score")
        offset_to_primary[role] = {
            "offsetToPrimary": offset,
            "matchClass": match_class,
            "score": score,
            "path": str(source_paths[role]),
        }
        details["items"].append(
            {
                "role": role,
                "path": str(source_paths[role]),
                "used": True,
                "matchClass": match_class,
                "score": score,
                "offsetToPrimary": offset,
            }
        )

    master_to_primary = offset_to_primary.get("master", {}).get("offsetToPrimary")
    if master_to_primary is None:
        details["reason"] = "master transcript match unavailable"
        return {}, details

    offsets: dict[str, dict[str, Any]] = {}
    for role, item in offset_to_primary.items():
        offsets[role] = {
            "offsetSeconds": round(float(master_to_primary) - float(item["offsetToPrimary"]), 3),
            "matchClass": item["matchClass"],
            "score": item["score"],
            "primaryRole": primary_role,
            "path": item["path"],
        }
    details["reason"] = "usable transcript comparison offsets found"
    return offsets, details


def load_transcript_comparison_offsets(sources: list[tuple[str, Path]]) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    enabled = bool_value("render", "useTranscriptComparisonSync", default=True)
    details: dict[str, Any] = {"enabled": enabled, "items": []}
    if not enabled:
        details["reason"] = "disabled by render.useTranscriptComparisonSync"
        return {}, details

    report_path = Path(text_config("transcriptComparison", "outputPath", default=str(DEFAULT_TRANSCRIPT_COMPARISON)))
    details["path"] = str(report_path)
    if not report_path.exists():
        details["reason"] = "comparison report missing"
        return {}, details

    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        details["reason"] = f"comparison report unreadable: {error}"
        return {}, details
    if not isinstance(report, dict):
        details["reason"] = "comparison report is not a JSON object"
        return {}, details

    expected_fingerprint = transcript_manifest_fingerprint(APP_CONFIG)
    actual_fingerprint = str(report.get("manifestFingerprint") or "")
    details["manifestFingerprint"] = actual_fingerprint
    if not expected_fingerprint:
        details["reason"] = "current transcript manifest fingerprint unavailable"
        return {}, details
    if actual_fingerprint != expected_fingerprint:
        details["reason"] = "comparison report does not match the current media manifest"
        details["expectedManifestFingerprint"] = expected_fingerprint
        return {}, details

    min_class = text_config("render", "transcriptSyncMinClass", default="strong")
    offsets, comparison_details = transcript_comparison_sync_offsets(report, sources, min_class=min_class)
    comparison_details["path"] = str(report_path)
    comparison_details["manifestFingerprint"] = actual_fingerprint
    return offsets, comparison_details


def write_sync_usage_report(report: dict[str, Any]) -> None:
    try:
        SYNC_OFFSET_USAGE_REPORT.parent.mkdir(parents=True, exist_ok=True)
        SYNC_OFFSET_USAGE_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def load_sync_offsets(sources: list[tuple[str, Path]]) -> dict[str, float]:
    sync_path = Path(nested(APP_CONFIG, "render", "syncOffsetsPath", default=str(DEFAULT_SYNC)))
    offsets = {role: 0.0 for role, _ in sources}
    offsets.setdefault("master", 0.0)
    usage: dict[str, Any] = {
        "syncPath": str(sync_path),
        "fallbackBelowScore": float_config("render", "transcriptSyncFallbackBelowScore", default=0.65),
        "items": [],
    }
    transcript_offsets, transcript_details = load_transcript_comparison_offsets(sources)
    usage["transcriptComparison"] = transcript_details

    data: dict[str, Any] = {}
    if sync_path.exists():
        try:
            payload = json.loads(sync_path.read_text(encoding="utf-8"))
            data = payload.get("offsets", {}) if isinstance(payload, dict) else {}
            if not isinstance(data, dict):
                data = {}
        except (OSError, json.JSONDecodeError) as error:
            usage["syncError"] = str(error)
    else:
        usage["syncError"] = "sync report missing"

    for role, path in sources:
        source = "default"
        score: float | None = None
        item = data.get(role)
        if isinstance(item, dict) and paths_match(item.get("path"), path):
            try:
                offsets[role] = float(item.get("offsetSeconds", 0.0))
                source = "waveform"
            except (TypeError, ValueError):
                source = "default"
            try:
                score = float(item.get("score"))
            except (TypeError, ValueError):
                score = None

        transcript_item = transcript_offsets.get(role)
        should_use_transcript = (
            role != "master"
            and transcript_item is not None
            and (source != "waveform" or (score is not None and score < usage["fallbackBelowScore"]))
        )
        if should_use_transcript:
            offsets[role] = float(transcript_item["offsetSeconds"])
            source = "transcript-comparison"

        usage["items"].append(
            {
                "role": role,
                "path": str(path),
                "offsetSeconds": offsets.get(role, 0.0),
                "source": source,
                "waveformScore": score,
                "transcript": transcript_item or None,
            }
        )
    write_sync_usage_report(usage)
    return offsets


def manifest_duration(role: str, path: Path) -> float | None:
    for item in manifest_files():
        if str(item.get("role") or "") != role or not paths_match(item.get("path"), path):
            continue
        metadata = item.get("metadata", {})
        if not isinstance(metadata, dict):
            continue
        try:
            duration = float(metadata.get("duration") or 0.0)
        except (TypeError, ValueError):
            continue
        if duration > 0:
            return duration
    return None


def probe_duration(path: Path) -> float | None:
    try:
        completed = subprocess.run(
            [
                str(FFPROBE),
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            cwd=WORK,
            check=True,
            capture_output=True,
            text=True,
        )
        duration = float(completed.stdout.strip())
    except (OSError, subprocess.CalledProcessError, TypeError, ValueError):
        return None
    return duration if duration > 0 else None


def source_duration(role: str, path: Path) -> float | None:
    return manifest_duration(role, path) or probe_duration(path)


def full_range_duration(cameras: list[tuple[str, Path]], fallback: float) -> float:
    preferred = next(((role, path) for role, path in cameras if role == "master"), cameras[0] if cameras else None)
    if preferred:
        detected = source_duration(preferred[0], preferred[1])
        if detected and detected > 0:
            return detected
    return fallback


def source_local_at_output_time(output_time: float, replacements: list[dict[str, Any]] | None) -> float | None:
    return output_local_to_source_local(output_time, replacements) if replacements else output_time


def output_time_for_source_local(source_time: float, replacements: list[dict[str, Any]] | None) -> float | None:
    return source_local_to_output_local(source_time, replacements) if replacements else source_time


def constrain_segments_to_source_coverage(
    segments: list[tuple[str, int, float, float]],
    cameras: list[tuple[str, int, Path]],
    *,
    duration: float,
    timeline_start: float,
    sync_offsets: dict[str, float],
    replacements: list[dict[str, Any]] | None = None,
) -> tuple[list[tuple[str, int, float, float]], dict[str, Any]]:
    enabled = bool_value("render", "respectSourceCoverage", default=True)
    report: dict[str, Any] = {"enabled": enabled, "items": [], "adjustments": []}
    if not enabled or not segments or not cameras:
        report["reason"] = "disabled" if not enabled else "no camera segments"
        return segments, report

    windows: dict[str, tuple[float, float] | None] = {}
    for role, _, path in cameras:
        media_duration = source_duration(role, path)
        offset = sync_offsets.get(role, 0.0)
        if media_duration is None:
            windows[role] = None
            report["items"].append({"role": role, "path": str(path), "duration": None, "coverage": "unknown"})
            continue
        start_local = max(0.0, -timeline_start - offset)
        end_local = min(duration, max(0.0, media_duration - timeline_start - offset))
        if end_local <= start_local + 0.02:
            windows[role] = (0.0, 0.0)
        else:
            windows[role] = (start_local, end_local)
        report["items"].append(
            {
                "role": role,
                "path": str(path),
                "duration": round(media_duration, 3),
                "syncOffset": round(offset, 3),
                "sourceLocalCoverage": [round(windows[role][0], 3), round(windows[role][1], 3)] if windows[role] else "unknown",
            }
        )

    def covers(role: str, output_time: float) -> bool:
        window = windows.get(role)
        if window is None:
            return True
        source_local = source_local_at_output_time(output_time, replacements)
        if source_local is None:
            return True
        return window[0] - 0.01 <= source_local <= window[1] + 0.01

    cuts = {0.0, duration}
    for _, _, start_t, end_t in segments:
        cuts.add(max(0.0, min(duration, start_t)))
        cuts.add(max(0.0, min(duration, end_t)))
    for window in windows.values():
        if window is None:
            continue
        for source_time in window:
            output_time = output_time_for_source_local(source_time, replacements)
            if output_time is not None:
                cuts.add(max(0.0, min(duration, output_time)))

    constrained: list[tuple[str, int, float, float]] = []
    timeline = sorted(cuts)
    for start_t, end_t in zip(timeline, timeline[1:]):
        if end_t - start_t <= 0.02:
            continue
        midpoint = (start_t + end_t) / 2
        original = next((item for item in segments if item[2] <= midpoint < item[3]), segments[-1])
        selected = original
        if not covers(original[0], midpoint):
            fallback = next((item for item in cameras if item[0] == "master" and covers(item[0], midpoint)), None)
            if fallback is None:
                fallback = next((item for item in cameras if covers(item[0], midpoint)), None)
            if fallback is not None:
                selected = (fallback[0], fallback[1], original[2], original[3])
                adjustments = report["adjustments"]
                if isinstance(adjustments, list):
                    adjustments.append(
                        {
                            "start": round(start_t, 3),
                            "end": round(end_t, 3),
                            "fromRole": original[0],
                            "toRole": fallback[0],
                            "reason": "outside source coverage",
                        }
                    )
            else:
                adjustments = report["adjustments"]
                if isinstance(adjustments, list):
                    adjustments.append(
                        {
                            "start": round(start_t, 3),
                            "end": round(end_t, 3),
                            "fromRole": original[0],
                            "toRole": original[0],
                            "reason": "no covered fallback source",
                        }
                    )
        constrained.append((selected[0], selected[1], start_t, end_t))

    normalized = normalize_camera_segments(duration, constrained, segments[0][:2])
    report["changed"] = normalized != segments
    SOURCE_COVERAGE_REPORT.parent.mkdir(parents=True, exist_ok=True)
    SOURCE_COVERAGE_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return normalized, report


def rms_envelope(samples: list[float], sample_rate: int, frame_seconds: float) -> np.ndarray:
    frame = max(1, int(round(sample_rate * frame_seconds)))
    if len(samples) < frame * 4:
        return np.array([], dtype=np.float32)
    values = np.asarray(samples, dtype=np.float32)
    usable = (values.size // frame) * frame
    if usable < frame * 4:
        return np.array([], dtype=np.float32)
    framed = values[:usable].reshape(-1, frame)
    return np.sqrt(np.mean(framed * framed, axis=1)).astype(np.float32)


def normalized_dot(left: np.ndarray, right: np.ndarray) -> float:
    if left.size == 0 or right.size == 0 or left.size != right.size:
        return -1.0
    left_centered = left - float(np.mean(left))
    right_centered = right - float(np.mean(right))
    denom = float(np.linalg.norm(left_centered) * np.linalg.norm(right_centered))
    if denom <= 1e-8:
        return -1.0
    return float(np.dot(left_centered, right_centered) / denom)


def external_audio_local_shift(
    camera_path: Path,
    external_audio_path: Path,
    *,
    camera_center: float,
    external_center: float,
    probe_duration: float,
    search_radius: float,
    sample_rate: int,
    frame_seconds: float,
    decode_cache: dict[tuple[str, float, float, int], list[float]],
) -> dict[str, Any]:
    camera_start = max(0.0, camera_center - probe_duration / 2.0)
    external_start = max(0.0, external_center - probe_duration / 2.0 - search_radius)
    external_duration = probe_duration + search_radius * 2.0

    def cached_decode(path: Path, start_t: float, duration_t: float) -> list[float]:
        key = (str(path.resolve()).casefold(), round(start_t, 3), round(duration_t, 3), sample_rate)
        if key not in decode_cache:
            decode_cache[key] = decode_audio_window(path, start_t, duration_t, sample_rate)
        return decode_cache[key]

    try:
        camera_samples = cached_decode(camera_path, camera_start, probe_duration)
        external_samples = cached_decode(external_audio_path, external_start, external_duration)
    except Exception as error:
        return {
            "passed": False,
            "reason": f"decode_failed: {error}",
            "cameraStart": round(camera_start, 3),
            "externalStart": round(external_start, 3),
        }

    camera_env = rms_envelope(camera_samples, sample_rate, frame_seconds)
    external_env = rms_envelope(external_samples, sample_rate, frame_seconds)
    if camera_env.size < 4 or external_env.size < camera_env.size:
        return {
            "passed": False,
            "reason": "insufficient_audio_energy_or_duration",
            "cameraStart": round(camera_start, 3),
            "externalStart": round(external_start, 3),
        }

    best_score = -1.0
    best_index = 0
    max_index = int(external_env.size - camera_env.size)
    for index in range(max_index + 1):
        score = normalized_dot(camera_env, external_env[index : index + camera_env.size])
        if score > best_score:
            best_score = score
            best_index = index

    actual_external_start = external_start + best_index * frame_seconds
    planned_external_start = max(0.0, external_center - probe_duration / 2.0)
    shift = actual_external_start - planned_external_start
    return {
        "passed": True,
        "score": round(best_score, 4),
        "shiftSeconds": round(shift, 4),
        "cameraStart": round(camera_start, 3),
        "externalStart": round(planned_external_start, 3),
        "matchedExternalStart": round(actual_external_start, 3),
    }


def sync_probe_points(start_t: float, end_t: float, max_probes: int) -> list[float]:
    segment_duration = max(0.0, end_t - start_t)
    if max_probes <= 1 or segment_duration < 12.0:
        return [(start_t + end_t) / 2.0]
    if max_probes == 2:
        return [start_t + segment_duration * 0.33, start_t + segment_duration * 0.67]
    return [start_t + segment_duration * 0.25, start_t + segment_duration * 0.5, start_t + segment_duration * 0.75]


def guard_segments_by_external_audio_sync(
    segments: list[tuple[str, int, float, float]],
    cameras: list[tuple[str, int, Path]],
    *,
    duration: float,
    timeline_start: float,
    sync_offsets: dict[str, float],
    external_audio_path: Path | None,
    audio_role: str,
    replacements: list[dict[str, Any]] | None = None,
) -> tuple[list[tuple[str, int, float, float]], dict[str, Any]]:
    enabled = bool_value("render", "externalAudioCutSyncGuard", default=True)
    min_score = float_config("render", "externalAudioCutSyncMinScore", default=0.45)
    max_shift = float_config("render", "externalAudioCutSyncMaxShift", default=0.22)
    min_segment = float_config("render", "externalAudioCutSyncMinSegment", default=1.5)
    probe_duration = float_config("render", "externalAudioCutSyncProbeDuration", default=4.0)
    search_radius = float_config("render", "externalAudioCutSyncSearchRadius", default=0.75)
    max_probes = max(1, min(3, int_value(APP_CONFIG, "render", "externalAudioCutSyncMaxProbes", default=2)))
    sample_rate = max(4000, int_value(APP_CONFIG, "render", "externalAudioCutSyncSampleRate", default=8000))
    frame_seconds = float_config("render", "externalAudioCutSyncFrameSeconds", default=0.025)
    camera_by_role = {role: (input_index, path) for role, input_index, path in cameras}
    fallback = camera_by_role.get("master") or next(iter(camera_by_role.values()), None)
    fallback_role = "master" if "master" in camera_by_role else (cameras[0][0] if cameras else "")
    report: dict[str, Any] = {
        "enabled": enabled,
        "externalAudio": str(external_audio_path) if external_audio_path else "",
        "audioRole": audio_role,
        "thresholds": {
            "minScore": min_score,
            "maxShiftSeconds": max_shift,
            "minSegmentSeconds": min_segment,
            "probeDurationSeconds": probe_duration,
            "searchRadiusSeconds": search_radius,
            "maxProbes": max_probes,
        },
        "items": [],
        "adjustments": [],
    }
    if not enabled:
        report["reason"] = "disabled"
        return segments, report
    if not external_audio_path or not external_audio_path.exists() or fallback is None:
        report["reason"] = "missing_external_audio_or_fallback"
        EXTERNAL_AUDIO_CUT_SYNC_REPORT.parent.mkdir(parents=True, exist_ok=True)
        EXTERNAL_AUDIO_CUT_SYNC_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return segments, report

    decode_cache: dict[tuple[str, float, float, int], list[float]] = {}
    guarded: list[tuple[str, int, float, float]] = []
    for role, input_index, start_t, end_t in segments:
        segment_duration = end_t - start_t
        item: dict[str, Any] = {
            "role": role,
            "start": round(start_t, 3),
            "end": round(end_t, 3),
            "duration": round(segment_duration, 3),
            "action": "keep",
        }
        if role == fallback_role:
            item["reason"] = "fallback camera"
            guarded.append((role, input_index, start_t, end_t))
            report["items"].append(item)
            continue
        camera_info = camera_by_role.get(role)
        if camera_info is None:
            item["action"] = "fallback"
            item["reason"] = "camera path missing"
            guarded.append((fallback_role, fallback[0], start_t, end_t))
            report["items"].append(item)
            continue
        if segment_duration < min_segment:
            item["action"] = "fallback"
            item["reason"] = "segment too short for reliable waveform sync"
            guarded.append((fallback_role, fallback[0], start_t, end_t))
            report["items"].append(item)
            report["adjustments"].append({**item, "toRole": fallback_role})
            continue

        _, camera_path = camera_info
        probes: list[dict[str, Any]] = []
        for output_time in sync_probe_points(start_t, end_t, max_probes):
            source_local = output_local_to_source_local(output_time, replacements) if replacements else output_time
            if source_local is None:
                probes.append({"outputTime": round(output_time, 3), "passed": False, "reason": "inside_omission_card"})
                continue
            camera_center = max(0.0, sync_offsets.get(role, 0.0) + timeline_start + source_local)
            external_center = max(0.0, sync_offsets.get(audio_role, 0.0) + timeline_start + source_local)
            probe = external_audio_local_shift(
                camera_path,
                external_audio_path,
                camera_center=camera_center,
                external_center=external_center,
                probe_duration=min(probe_duration, max(0.75, segment_duration - 0.1)),
                search_radius=search_radius,
                sample_rate=sample_rate,
                frame_seconds=frame_seconds,
                decode_cache=decode_cache,
            )
            probe["outputTime"] = round(output_time, 3)
            probe["cameraCenter"] = round(camera_center, 3)
            probe["externalCenter"] = round(external_center, 3)
            probes.append(probe)

        valid_scores = [float(probe["score"]) for probe in probes if probe.get("passed") and probe.get("score") is not None]
        valid_shifts = [abs(float(probe["shiftSeconds"])) for probe in probes if probe.get("passed") and probe.get("shiftSeconds") is not None]
        item["probes"] = probes
        if not valid_scores or not valid_shifts:
            item["action"] = "fallback"
            item["reason"] = "no valid waveform probe"
        elif min(valid_scores) < min_score:
            item["action"] = "fallback"
            item["reason"] = "waveform score below threshold"
            item["minScore"] = round(min(valid_scores), 4)
        elif max(valid_shifts) > max_shift:
            item["action"] = "fallback"
            item["reason"] = "local waveform shift exceeds threshold"
            item["maxAbsShiftSeconds"] = round(max(valid_shifts), 4)
        else:
            item["minScore"] = round(min(valid_scores), 4)
            item["maxAbsShiftSeconds"] = round(max(valid_shifts), 4)

        if item["action"] == "fallback":
            guarded.append((fallback_role, fallback[0], start_t, end_t))
            report["adjustments"].append({**{key: value for key, value in item.items() if key != "probes"}, "toRole": fallback_role})
        else:
            guarded.append((role, input_index, start_t, end_t))
        report["items"].append(item)

    normalized = normalize_camera_segments(duration, guarded, (fallback_role, fallback[0]))
    report["changed"] = normalized != segments
    EXTERNAL_AUDIO_CUT_SYNC_REPORT.parent.mkdir(parents=True, exist_ok=True)
    EXTERNAL_AUDIO_CUT_SYNC_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if report["changed"]:
        write_camera_plan_report(
            f"{text_config('render', 'multicamMode', default='master-first')}+external-audio-sync-guard",
            normalized,
            str(EXTERNAL_AUDIO_CUT_SYNC_REPORT),
        )
    return normalized, report


def camera_index_map(cameras: list[tuple[str, int]]) -> dict[str, tuple[str, int]]:
    return {role: (role, input_index) for role, input_index in cameras}


def normalize_camera_segments(
    duration: float,
    segments: list[tuple[str, int, float, float]],
    fallback: tuple[str, int],
) -> list[tuple[str, int, float, float]]:
    normalized = []
    for role, input_index, start_t, end_t in sorted(segments, key=lambda item: (item[2], item[3])):
        local_start = max(0.0, min(duration, float(start_t)))
        local_end = max(0.0, min(duration, float(end_t)))
        if local_end - local_start > 0.05:
            normalized.append((role, input_index, local_start, local_end))
    if not normalized:
        return [(fallback[0], fallback[1], 0.0, duration)]

    filled: list[tuple[str, int, float, float]] = []
    cursor = 0.0
    previous = fallback
    for role, input_index, start_t, end_t in normalized:
        if start_t > cursor + 0.05:
            filled.append((previous[0], previous[1], cursor, start_t))
        if end_t > cursor + 0.05:
            filled.append((role, input_index, max(cursor, start_t), end_t))
            cursor = end_t
            previous = (role, input_index)
    if cursor < duration - 0.05:
        filled.append((previous[0], previous[1], cursor, duration))

    merged: list[tuple[str, int, float, float]] = []
    for role, input_index, start_t, end_t in filled:
        if merged and merged[-1][0] == role and merged[-1][1] == input_index and start_t <= merged[-1][3] + 0.2:
            prev_role, prev_index, prev_start, _ = merged[-1]
            merged[-1] = (prev_role, prev_index, prev_start, end_t)
        else:
            merged.append((role, input_index, start_t, end_t))
    return merged


def parse_manual_camera_plan(duration: float, cameras: list[tuple[str, int]]) -> list[tuple[str, int, float, float]]:
    role_map = camera_index_map(cameras)
    plan_data = nested(APP_CONFIG, "render", "cameraPlan", default=None)
    plan_path = text_config("render", "cameraPlanPath") or str(OUTPUT_REPORTS / "manual_camera_plan.json")
    if plan_data is None and Path(plan_path).exists():
        try:
            plan_data = json.loads(Path(plan_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            plan_data = None
    if isinstance(plan_data, dict):
        raw_segments = plan_data.get("segments", [])
    else:
        raw_segments = plan_data if isinstance(plan_data, list) else []

    segments: list[tuple[str, int, float, float]] = []
    for item in raw_segments:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or item.get("camera") or "").strip()
        if role not in role_map:
            continue
        try:
            start_t = float(item.get("start", 0.0))
            end_t = float(item.get("end", duration))
        except (TypeError, ValueError):
            continue
        camera_role, input_index = role_map[role]
        segments.append((camera_role, input_index, start_t, end_t))
    return normalize_camera_segments(duration, segments, cameras[0]) if segments else []


def caption_local_range(item: dict[str, Any], timeline_start: float, duration: float) -> tuple[float, float] | None:
    try:
        start_t = seconds(str(item["start"])) - timeline_start
        end_t = seconds(str(item["end"])) - timeline_start
    except (KeyError, ValueError):
        return None
    start_t = max(0.0, min(duration, start_t))
    end_t = max(0.0, min(duration, end_t))
    if end_t - start_t <= 0.05:
        return None
    return start_t, end_t


def speaker_aware_segments(
    duration: float,
    cameras: list[tuple[str, int]],
    captions: list[dict[str, Any]],
    timeline_start: float,
) -> list[tuple[str, int, float, float]]:
    if len(cameras) == 1 or not captions:
        return []
    master = cameras[0]
    closeups = cameras[1:] or cameras[:1]
    segments: list[tuple[str, int, float, float]] = []
    closeup_index = 0
    active_closeup = closeups[0]
    active_until = 0.0
    for item in captions:
        local = caption_local_range(item, timeline_start, duration)
        if local is None:
            continue
        start_t, end_t = local
        role = str(item.get("speaker_role") or item.get("role") or "").lower()
        if role == "interviewer":
            selected = master
        else:
            if start_t >= active_until - 0.05:
                active_closeup = closeups[closeup_index % len(closeups)]
                closeup_index += 1
                active_until = start_t + 12.0
            selected = active_closeup
        segments.append((selected[0], selected[1], max(0.0, start_t - 0.12), min(duration, end_t + 0.18)))
    return normalize_camera_segments(duration, segments, master) if segments else []


def onscreen_speech_ranges(
    captions: list[dict[str, Any]],
    timeline_start: float,
    duration: float,
) -> list[tuple[float, float]]:
    pad = float_config("render", "closeupSpeechPadding", default=0.18)
    gap_merge = float_config("render", "closeupSpeechGapMerge", default=0.80)
    ranges: list[tuple[float, float]] = []
    for item in captions:
        role = str(item.get("speaker_role") or item.get("role") or "onscreen").lower()
        if role == "interviewer":
            continue
        local = caption_local_range(item, timeline_start, duration)
        if local is None:
            continue
        start_t, end_t = local
        ranges.append((max(0.0, start_t - pad), min(duration, end_t + pad)))
    if not ranges:
        return []
    ranges.sort()
    merged = [ranges[0]]
    for start_t, end_t in ranges[1:]:
        prev_start, prev_end = merged[-1]
        if start_t <= prev_end + gap_merge:
            merged[-1] = (prev_start, max(prev_end, end_t))
        else:
            merged.append((start_t, end_t))
    return merged


def restrict_closeups_to_onscreen_speech(
    segments: list[tuple[str, int, float, float]],
    duration: float,
    cameras: list[tuple[str, int]],
    captions: list[dict[str, Any]],
    timeline_start: float,
) -> tuple[list[tuple[str, int, float, float]], dict[str, Any]]:
    enabled = bool_value("render", "closeupsOnlyWhenOnscreenSpeaker", default=False)
    report: dict[str, Any] = {
        "enabled": enabled,
        "changed": False,
        "inputSegments": len(segments),
        "outputSegments": len(segments),
        "onscreenSpeechRanges": [],
        "replacedCloseupGaps": [],
    }
    if not enabled or len(cameras) <= 1 or not segments:
        return segments, report
    master = cameras[0]
    ranges = onscreen_speech_ranges(captions, timeline_start, duration)
    report["onscreenSpeechRanges"] = [{"start": round(a, 3), "end": round(b, 3)} for a, b in ranges]
    if not ranges:
        restricted = [(master[0], master[1], start_t, end_t) for _, _, start_t, end_t in segments]
        report["changed"] = restricted != segments
        report["outputSegments"] = len(restricted)
        report["reason"] = "no onscreen speech ranges; close-ups replaced with master"
        ONSCREEN_CLOSEUP_REPORT.parent.mkdir(parents=True, exist_ok=True)
        ONSCREEN_CLOSEUP_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return normalize_camera_segments(duration, restricted, master), report

    min_fragment = 0.08
    restricted: list[tuple[str, int, float, float]] = []
    replaced: list[dict[str, Any]] = []
    for role, input_index, start_t, end_t in segments:
        if role == master[0] or input_index == master[1]:
            restricted.append((role, input_index, start_t, end_t))
            continue
        cursor = start_t
        used_closeup = False
        for range_start, range_end in ranges:
            if range_end <= start_t + min_fragment or range_start >= end_t - min_fragment:
                continue
            close_start = max(start_t, range_start)
            close_end = min(end_t, range_end)
            if close_start > cursor + min_fragment:
                restricted.append((master[0], master[1], cursor, close_start))
                replaced.append({"role": role, "start": round(cursor, 3), "end": round(close_start, 3)})
            if close_end > close_start + min_fragment:
                restricted.append((role, input_index, close_start, close_end))
                used_closeup = True
            cursor = max(cursor, close_end)
        if cursor < end_t - min_fragment:
            restricted.append((master[0], master[1], cursor, end_t))
            replaced.append({"role": role, "start": round(cursor, 3), "end": round(end_t, 3)})
        elif not used_closeup and cursor <= start_t + min_fragment:
            restricted.append((master[0], master[1], start_t, end_t))
            replaced.append({"role": role, "start": round(start_t, 3), "end": round(end_t, 3)})

    normalized = normalize_camera_segments(duration, restricted, master)
    report["changed"] = normalized != segments
    report["outputSegments"] = len(normalized)
    report["replacedCloseupGaps"] = replaced
    ONSCREEN_CLOSEUP_REPORT.parent.mkdir(parents=True, exist_ok=True)
    ONSCREEN_CLOSEUP_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return normalized, report


def dynamic_cut_segments(
    duration: float,
    cameras: list[tuple[str, int]],
    captions: list[dict[str, Any]],
    timeline_start: float,
) -> list[tuple[str, int, float, float]]:
    if len(cameras) == 1:
        return []
    master = cameras[0]
    closeups = cameras[1:] or cameras[:1]
    min_segment = float_config("render", "dynamicCutMinSegment", default=2.4)
    max_segment = float_config("render", "dynamicCutMaxSegment", default=5.2)
    max_segment = max(min_segment + 0.2, max_segment)
    segments: list[tuple[str, int, float, float]] = []

    closeup_index = 0
    active_closeup = closeups[0]
    active_until = 0.0
    for item in captions:
        local = caption_local_range(item, timeline_start, duration)
        if local is None:
            continue
        start_t, end_t = local
        role = str(item.get("speaker_role") or item.get("role") or "").lower()
        if role == "interviewer":
            selected = master
        else:
            if start_t >= active_until - 0.05:
                active_closeup = closeups[closeup_index % len(closeups)]
                closeup_index += 1
                active_until = start_t + max_segment
            selected = active_closeup

        cursor = max(0.0, start_t - 0.08)
        padded_end = min(duration, end_t + 0.14)
        while cursor < padded_end - 0.05:
            chunk_end = min(padded_end, cursor + max_segment)
            if chunk_end - cursor < min_segment and segments:
                prev_role, prev_input, prev_start, _ = segments[-1]
                if prev_role == selected[0] and prev_input == selected[1]:
                    segments[-1] = (prev_role, prev_input, prev_start, chunk_end)
                    break
            segments.append((selected[0], selected[1], cursor, chunk_end))
            cursor = chunk_end
            if selected != master and cursor < padded_end - 0.05:
                active_closeup = closeups[closeup_index % len(closeups)]
                closeup_index += 1
                selected = active_closeup

    if segments:
        return normalize_camera_segments(duration, segments, master)

    pattern = [3.2, 4.4, 3.6, 5.0, 4.0]
    cursor = 0.0
    index = 0
    while cursor < duration:
        length = pattern[index % len(pattern)]
        end_t = min(duration, cursor + length)
        selected = master if index == 0 or index % 5 == 4 else closeups[(index - 1) % len(closeups)]
        segments.append((selected[0], selected[1], cursor, end_t))
        cursor = end_t
        index += 1
    return normalize_camera_segments(duration, segments, master)


def write_camera_plan_report(mode: str, segments: list[tuple[str, int, float, float]], source: str) -> None:
    CAMERA_PLAN_REPORT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "mode": mode,
        "source": source,
        "segments": [
            {"role": role, "inputIndex": input_index, "start": round(start_t, 3), "end": round(end_t, 3)}
            for role, input_index, start_t, end_t in segments
        ],
    }
    CAMERA_PLAN_REPORT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def decode_audio_window(path: Path, start: float, duration: float, sample_rate: int = 8000) -> list[float]:
    start = max(0.0, float(start))
    duration = max(0.05, float(duration))
    command = [
        str(FFMPEG),
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{start:.6f}",
        "-t",
        f"{duration:.6f}",
        "-i",
        str(path),
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
    samples = array("h")
    samples.frombytes(completed.stdout)
    if sys.byteorder != "little":
        samples.byteswap()
    return [value / 32768.0 for value in samples]


def quiet_audio_time_near(
    path: Path,
    planned_time: float,
    *,
    search_before: float,
    search_after: float,
    sample_rate: int = 8000,
    window_seconds: float = 0.08,
    hop_seconds: float = 0.02,
) -> tuple[float, dict[str, Any]]:
    search_start = max(0.0, planned_time - search_before)
    duration = search_before + search_after
    samples = decode_audio_window(path, search_start, duration, sample_rate)
    window = max(1, round(window_seconds * sample_rate))
    hop = max(1, round(hop_seconds * sample_rate))
    if len(samples) < window:
        return planned_time, {"reason": "audio_window_too_short", "plannedAudioTime": round(planned_time, 3)}
    target = planned_time - search_start
    candidates: list[dict[str, float]] = []
    for index in range(0, len(samples) - window + 1, hop):
        chunk = samples[index : index + window]
        rms = math.sqrt(sum(value * value for value in chunk) / len(chunk))
        center = (index + window / 2.0) / sample_rate
        candidates.append({"audioTime": search_start + center, "rms": rms, "distance": abs(center - target)})
    if not candidates:
        return planned_time, {"reason": "no_audio_windows", "plannedAudioTime": round(planned_time, 3)}
    best = min(candidates, key=lambda item: (item["rms"], item["distance"]))
    return float(best["audioTime"]), {
        "plannedAudioTime": round(planned_time, 3),
        "chosenAudioTime": round(float(best["audioTime"]), 3),
        "shiftSeconds": round(float(best["audioTime"]) - planned_time, 3),
        "rms": round(float(best["rms"]), 8),
        "searchStart": round(search_start, 3),
        "searchEnd": round(search_start + duration, 3),
    }


def adjust_segments_to_dialogue_gaps(
    segments: list[tuple[str, int, float, float]],
    *,
    duration: float,
    audio_path: Path | None,
    audio_role: str,
    timeline_start: float,
    sync_offsets: dict[str, float],
    replacements: list[dict[str, Any]],
) -> tuple[list[tuple[str, int, float, float]], dict[str, Any]]:
    enabled = bool_value("render", "naturalDialogueCuts", default=False)
    report: dict[str, Any] = {
        "enabled": enabled,
        "audio": str(audio_path) if audio_path else "",
        "items": [],
    }
    if not enabled:
        report["reason"] = "disabled"
        return segments, report
    if not audio_path or not audio_path.exists() or len(segments) < 2:
        report["reason"] = "missing_audio_or_single_segment"
        NATURAL_CUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
        NATURAL_CUT_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return segments, report

    adjusted = [tuple(segment) for segment in segments]
    search_before = float_config("render", "naturalCutSearchBefore", default=0.25)
    search_after = float_config("render", "naturalCutSearchAfter", default=0.08)
    min_segment = float_config("render", "naturalCutMinSegment", default=1.0)
    max_shift = float_config("render", "naturalCutMaxShift", default=0.35)
    offset = sync_offsets.get(audio_role, 0.0)
    for index in range(len(adjusted) - 1):
        left = adjusted[index]
        right = adjusted[index + 1]
        planned = float(left[3])
        if planned <= 0.05 or planned >= duration - 0.05 or left[0] == right[0]:
            continue
        source_local = output_local_to_source_local(planned, replacements) if replacements else planned
        if source_local is None:
            report["items"].append({"boundary": index, "planned": round(planned, 3), "skipped": "inside_omission_card"})
            continue
        audio_time = max(0.0, offset + timeline_start + source_local)
        try:
            chosen_audio_time, detail = quiet_audio_time_near(
                audio_path,
                audio_time,
                search_before=search_before,
                search_after=search_after,
            )
        except Exception as error:
            report["items"].append({"boundary": index, "planned": round(planned, 3), "skipped": str(error)})
            continue
        source_shift = max(-max_shift, min(max_shift, chosen_audio_time - audio_time))
        chosen_source_local = source_local + source_shift
        chosen_output = source_local_to_output_local(chosen_source_local, replacements) if replacements else chosen_source_local
        if chosen_output is None:
            report["items"].append({"boundary": index, "planned": round(planned, 3), "skipped": "chosen_inside_omission_card"})
            continue
        lower = float(left[2]) + min_segment
        upper = float(right[3]) - min_segment
        if upper <= lower:
            report["items"].append({"boundary": index, "planned": round(planned, 3), "skipped": "segments_too_short"})
            continue
        chosen = max(lower, min(upper, chosen_output))
        adjusted[index] = (left[0], left[1], left[2], chosen)
        adjusted[index + 1] = (right[0], right[1], chosen, right[3])
        detail.update(
            {
                "boundary": index,
                "fromRole": left[0],
                "toRole": right[0],
                "planned": round(planned, 3),
                "chosen": round(chosen, 3),
                "outputShiftSeconds": round(chosen - planned, 3),
            }
        )
        report["items"].append(detail)

    NATURAL_CUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    NATURAL_CUT_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if report["items"]:
        write_camera_plan_report(
            f"{text_config('render', 'multicamMode', default='master-first')}+natural-dialogue",
            adjusted,
            str(NATURAL_CUT_REPORT),
        )
    return adjusted, report


def build_segments(
    duration: float,
    cameras: list[tuple[str, int]],
    captions: list[dict[str, Any]] | None = None,
    timeline_start: float = 0.0,
) -> list[tuple[str, int, float, float]]:
    if not cameras:
        raise RuntimeError("At least one camera input is required.")
    mode = nested(APP_CONFIG, "render", "multicamMode", default="master-first")
    if mode == "manual-plan":
        manual = parse_manual_camera_plan(duration, cameras)
        if manual:
            write_camera_plan_report(mode, manual, text_config("render", "cameraPlanPath") or str(OUTPUT_REPORTS / "manual_camera_plan.json"))
            return manual
    if mode == "speaker-aware":
        aware = speaker_aware_segments(duration, cameras, captions or [], timeline_start)
        if aware:
            write_camera_plan_report(mode, aware, "subtitle speaker roles")
            return aware
    if mode == "dynamic-cuts":
        dynamic = dynamic_cut_segments(duration, cameras, captions or [], timeline_start)
        if dynamic:
            write_camera_plan_report(mode, dynamic, "current captions with rhythmic punch-in fallback")
            return dynamic
    if mode == "master-first" or len(cameras) == 1:
        if len(cameras) == 1:
            segments = [(cameras[0][0], cameras[0][1], 0.0, duration)]
            write_camera_plan_report(mode, segments, "single camera")
            return segments
        segments = [(cameras[0][0], cameras[0][1], 0.0, min(8.0, duration))]
        t = 8.0
        closeups = cameras[1:] or cameras[:1]
        index = 0
        while t < duration:
            end = min(duration, t + 12.0)
            role, input_index = closeups[index % len(closeups)]
            segments.append((role, input_index, t, end))
            t = end
            index += 1
        write_camera_plan_report(mode, segments, "master-first rotation")
        return segments

    order = cameras[1:] + cameras[:1] if len(cameras) > 1 else cameras
    segments = []
    t = 0.0
    index = 0
    while t < duration:
        end = min(duration, t + 15.0)
        role, input_index = order[index % len(order)]
        segments.append((role, input_index, t, end))
        t = end
        index += 1
    write_camera_plan_report(mode, segments, "fallback close-up rotation")
    return segments


def video_segments_with_stills(
    duration: float,
    camera_segments: list[tuple[str, int, float, float]],
    still_inserts: list[dict[str, Any]],
    replacements: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    replacements = replacements or []
    cuts = {0.0, duration}
    for _, _, start_t, end_t in camera_segments:
        cuts.add(max(0.0, min(duration, start_t)))
        cuts.add(max(0.0, min(duration, end_t)))
    for still in still_inserts:
        cuts.add(float(still["start"]))
        cuts.add(float(still["end"]))
    for replacement in replacements:
        cuts.add(float(replacement["output_start"]))
        cuts.add(float(replacement["output_end"]))
    timeline = sorted(cuts)
    segments = []
    for start_t, end_t in zip(timeline, timeline[1:]):
        if end_t - start_t <= 0.02:
            continue
        midpoint = (start_t + end_t) / 2
        replacement = next(
            (item for item in replacements if float(item["output_start"]) <= midpoint < float(item["output_end"])),
            None,
        )
        if replacement:
            segments.append({"type": "omission_card", "replacement": replacement, "start": start_t, "end": end_t})
            continue
        still = next((item for item in still_inserts if float(item["start"]) <= midpoint < float(item["end"])), None)
        if still:
            segments.append({"type": "still", "still": still, "start": start_t, "end": end_t})
            continue
        camera = next((item for item in camera_segments if item[2] <= midpoint < item[3]), camera_segments[-1])
        role, input_index, _, _ = camera
        segments.append({"type": "camera", "role": role, "input_index": input_index, "start": start_t, "end": end_t})
    return segments


def omission_card_filter(input_index: int, label: str, duration: float) -> str:
    fade_out = max(0.0, duration - 0.25)
    fps = output_fps()
    return (
        f"[{input_index}:v]fps={fps},scale=1920:1080:force_original_aspect_ratio=decrease,"
        f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,"
        f"trim=duration={duration:.6f},setpts=PTS-STARTPTS,"
        f"fade=t=in:st=0:d=0.18,fade=t=out:st={fade_out:.3f}:d=0.25[{label}]"
    )


def still_filter(input_index: int, label: str, duration: float, still: dict[str, Any], phase: int) -> str:
    fade_out = max(0.0, duration - 0.25)
    kind = str(still["kind"])
    fps = output_fps()
    if kind in {"text", "diagram"}:
        base = (
            f"[{input_index}:v]fps={fps},scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=white,setsar=1"
        )
    else:
        analysis = still.get("analysis") if isinstance(still.get("analysis"), dict) else {}
        effect = still.get("effect") if isinstance(still.get("effect"), dict) else {}
        focus = analysis.get("focus") if isinstance(analysis.get("focus"), list) else [0.5, 0.5]
        focus_x = clamp(float(focus[0]), 0.08, 0.92)
        focus_y = clamp(float(focus[1]), 0.10, 0.90)
        zoom_start = float(effect.get("zoom_start", 1.04))
        zoom_end = float(effect.get("zoom_end", 1.07))
        pan_x = float(effect.get("pan_x", 42.0)) * (1 if phase % 2 else -1)
        pan_y = float(effect.get("pan_y", 14.0)) * (1 if phase % 3 == 0 else -1)
        progress = f"min(1,max(0,t/{max(duration, 0.1):.3f}))"
        zoom = f"({zoom_start:.5f}+({zoom_end:.5f}-{zoom_start:.5f})*{progress})"
        x_expr = f"min(max(iw*{focus_x:.5f}-960+{pan_x:.3f}*({progress}-0.5),0),iw-1920)"
        y_expr = f"min(max(ih*{focus_y:.5f}-540+{pan_y:.3f}*({progress}-0.5),0),ih-1080)"
        base = (
            f"[{input_index}:v]fps={fps},"
            f"scale=w='if(gte(iw/ih,1.777778),-2,1920*{zoom})':h='if(gte(iw/ih,1.777778),1080*{zoom},-2)':eval=frame,"
            f"crop=1920:1080:x='{x_expr}':y='{y_expr}',setsar=1"
        )
    return f"{base},trim=duration={duration:.6f},setpts=PTS-STARTPTS,fade=t=in:st=0:d=0.22,fade=t=out:st={fade_out:.3f}:d=0.25[{label}]"


def still_report(still_inserts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "file": str(item["path"]),
            "kind": item["kind"],
            "start": item["start"],
            "end": item["end"],
            "reason": item["reason"],
            "photo_kind": item.get("analysis", {}).get("photo_kind") if isinstance(item.get("analysis"), dict) else None,
            "focus": item.get("analysis", {}).get("focus") if isinstance(item.get("analysis"), dict) else None,
            "faces": len(item.get("analysis", {}).get("faces", [])) if isinstance(item.get("analysis"), dict) else 0,
            "effect": item.get("effect", {}).get("name") if isinstance(item.get("effect"), dict) else None,
        }
        for item in still_inserts
    ]


def omission_card_report(replacements: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "enabled": bool_value("omissionCard", "enabled", default=False),
        "items": [
            {
                "source_start": round(float(item["source_start"]), 3),
                "source_end": round(float(item["source_end"]), 3),
                "output_start": round(float(item["output_start"]), 3),
                "output_end": round(float(item["output_end"]), 3),
                "title": str(item.get("title") or ""),
                "subtitle": str(item.get("subtitle") or ""),
                "image": str(item.get("path") or ""),
            }
            for item in replacements
        ],
    }


def color_match_summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "enabled": bool(report.get("enabled")),
        "report": str(COLOR_MATCH_REPORT) if report.get("enabled") else "",
        "items": report.get("items", []),
        "manualExtraFilters": report.get("manualExtraFilters", []),
        "reason": report.get("reason", ""),
    }


def person_crop_summary(report: dict[str, Any]) -> dict[str, Any]:
    matched = report.get("matched", [])
    segments = report.get("segments", [])
    return {
        "enabled": bool(report.get("enabled")),
        "report": str(PERSON_CROP_REPORT) if report.get("enabled") else "",
        "matchedPlans": len(matched) if isinstance(matched, list) else 0,
        "croppedSegments": len(segments) if isinstance(segments, list) else 0,
        "reason": report.get("reason", ""),
    }


def face_center_crop_summary(report: dict[str, Any]) -> dict[str, Any]:
    segments = report.get("segments", [])
    fallback = report.get("fallbackSegments", [])
    return {
        "enabled": bool(report.get("enabled")),
        "report": str(FACE_CENTER_CROP_REPORT) if report.get("enabled") else "",
        "loadedSegments": report.get("loadedSegments", 0),
        "croppedSegments": len(segments) if isinstance(segments, list) else 0,
        "fallbackSegments": len(fallback) if isinstance(fallback, list) else 0,
        "reason": report.get("reason", ""),
    }


def camera_plan_summary() -> dict[str, str]:
    return {
        "mode": text_config("render", "multicamMode", default="master-first"),
        "report": str(CAMERA_PLAN_REPORT),
        "naturalDialogueReport": str(NATURAL_CUT_REPORT) if bool_value("render", "naturalDialogueCuts", default=False) else "",
    }


def music_report(start: float, duration: float, music: Path | None, replacements: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    scope = text_config("music", "scope", default="full")
    ranges = (
        [(float(item["output_start"]), float(item["output_end"])) for item in replacements]
        if scope == "omission" and replacements
        else music_ranges(start, duration) if scope == "omission" else []
    )
    return {
        "enabled": bool_value("music", "enabled", default=False),
        "scope": scope,
        "output": str(music) if music else "",
        "ranges": [{"start": round(range_start, 3), "end": round(range_end, 3)} for range_start, range_end in ranges],
    }


def subtitle_mode() -> str:
    mode = nested(APP_CONFIG, "render", "subtitleMode", default="none")
    return mode if mode in {"full", "punchline"} else "none"


def subtitle_manifest(mode: str) -> tuple[Path, dict[str, object]]:
    modes = {
        "full": {
            "kind": "full-subtitle",
            "generator": SCRIPTS / "generate_full_transcript_png_overlays.py",
            "manifest": OUTPUT_OVERLAYS / "full_transcript_png_overlays" / "manifest.json",
            "bottom_margin": 16,
            "slide_px": 0,
            "pop": False,
            "animate": False,
        },
        "punchline": {
            "kind": "punchline",
            "generator": SCRIPTS / "generate_punchline_png_overlays.py",
            "manifest": OUTPUT_OVERLAYS / "punchline_png_overlays" / "manifest.json",
            "bottom_margin": 12,
            "slide_px": 44,
            "pop": True,
            "animate": True,
        },
    }
    config = modes[mode]
    command = [sys.executable, str(config["generator"])]
    if mode == "full":
        command.extend(["--format", "png"])
    run(command)
    return Path(config["manifest"]), config


def glossary_manifest() -> tuple[Path, dict[str, object]]:
    run([sys.executable, str(SCRIPTS / "generate_glossary_term_overlays.py")])
    return OUTPUT_OVERLAYS / "glossary_term_overlays" / "manifest.json", {
        "bottom_margin": 180,
        "slide_px": 0,
        "pop": False,
        "animate": False,
        "x_expr": "W-w-40",
        "y_expr": "H-h-180",
    }


def chapter_title_manifest() -> tuple[Path, dict[str, object]] | None:
    if not bool_value("style", "chapterTitlesEnabled", default=False):
        return None
    run([sys.executable, str(SCRIPTS / "generate_chapter_title_png_overlays.py")])
    return OUTPUT_OVERLAYS / "chapter_title_png_overlays" / "manifest.json", {
        "bottom_margin": 0,
        "slide_px": 0,
        "pop": False,
        "animate": False,
        "x_expr": str(int_value(APP_CONFIG, "style", "titleX", default=18)),
        "y_expr": str(int_value(APP_CONFIG, "style", "titleY", default=18)),
    }


def read_overlay_items(manifest: Path, start: float, duration: float, source_offset: float = 0.0) -> list[dict[str, Any]]:
    if not manifest.exists():
        return []
    shifted: list[dict[str, Any]] = []
    for item in json.loads(manifest.read_text(encoding="utf-8")):
        item_start = seconds(str(item["start"])) - source_offset
        item_end = seconds(str(item["end"])) - source_offset
        if item_start < start + duration and item_end > start:
            next_item = dict(item)
            next_item["start"] = format_overlay_time(item_start)
            next_item["end"] = format_overlay_time(item_end)
            shifted.append(next_item)
    return shifted


def should_precompose_overlay_items(mode: str, items: list[dict[str, Any]], config: dict[str, object], duration: float) -> bool:
    if not bool_value("render", "precomposeLongPngOverlays", default=True):
        return False
    if mode != "full" or config.get("kind") != "full-subtitle":
        return False
    return duration >= float_config("render", "precomposeOverlayMinDuration", default=300.0) or len(items) >= int_value(
        APP_CONFIG,
        "render",
        "precomposeOverlayMinItems",
        default=120,
    )


def precompose_overlay_video(
    items: list[dict[str, Any]],
    config: dict[str, object],
    start: float,
    duration: float,
    output_stem: str,
) -> Path:
    precompose_dir = OUTPUT_OVERLAYS / "precomposed"
    precompose_dir.mkdir(parents=True, exist_ok=True)
    safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", output_stem).strip("._") or "overlay"
    manifest = precompose_dir / f"{safe_stem}_manifest.json"
    output = precompose_dir / f"{safe_stem}.mov"
    sequence_dir = precompose_dir / f"{safe_stem}_frames"
    local_items: list[dict[str, Any]] = []
    for item in items:
        item_start = max(0.0, seconds(str(item["start"])) - start)
        item_end = min(duration, seconds(str(item["end"])) - start)
        if item_end <= item_start:
            continue
        local_item = dict(item)
        local_item["start"] = format_overlay_time(item_start)
        local_item["end"] = format_overlay_time(item_end)
        local_items.append(local_item)
    manifest_payload = json.dumps(local_items, ensure_ascii=False, indent=2)
    if (
        output.exists()
        and output.stat().st_size > 0
        and manifest.exists()
        and manifest.read_text(encoding="utf-8") == manifest_payload
    ):
        return output
    manifest.write_text(manifest_payload, encoding="utf-8")
    run(
        [
            sys.executable,
            str(SCRIPTS / "precompose_png_overlay_video.py"),
            "--manifest",
            str(manifest),
            "--output",
            str(output),
            "--sequence-dir",
            str(sequence_dir),
            "--duration",
            f"{duration:.6f}",
            "--bottom-margin",
            str(int(config.get("bottom_margin", 16))),
            "--fps",
            text_config("render", "precomposeOverlayFps", default="30000/1001"),
        ]
    )
    return output


def write_filter_complex_script(filters: list[str], output_stem: str) -> Path:
    filter_dir = OUTPUT_REPORTS / "filtergraphs"
    filter_dir.mkdir(parents=True, exist_ok=True)
    safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", output_stem).strip("._") or "render"
    path = filter_dir / f"{safe_stem}.ffgraph"
    path.write_text(";\n".join(filters) + "\n", encoding="utf-8")
    return path


def main() -> None:
    manifest_camera_sources = manifest_cameras()
    master = path_value("assets", "masterVideo")
    right = path_value("assets", "rightCloseVideo")
    left = path_value("assets", "leftCloseVideo")
    audio_sources = manifest_audio_sources()
    external_audio = audio_sources[0][1] if audio_sources else path_value("assets", "externalAudio")
    external_audio_role = audio_sources[0][0] if audio_sources else "external"
    logo = selected_logo_path()
    output = Path(nested(APP_CONFIG, "render", "outputPath", default=OUTPUT_VIDEOS / "app_multicam_output.mp4"))
    render_profile_value = render_profile()
    range_mode_value = render_range_mode()
    start = float(nested(APP_CONFIG, "render", "previewStart", default=0.0) or 0.0)
    source_duration = float(nested(APP_CONFIG, "render", "previewDuration", default=60.0) or 60.0)
    logo_height = int_value(APP_CONFIG, "style", "logoHeight", default=48)
    audio_denoise = bool_value("render", "audioDenoise", default=True)
    audio_denoise_strength = int_value(APP_CONFIG, "render", "audioDenoiseStrength", default=DEFAULT_DENOISE_STRENGTH)
    audio_mastering = bool_value("render", "audioMastering", default=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    reference_profile = load_reference_profile()
    reference_filter = reference_video_filter(reference_profile) if reference_profile else "scale=1920:1080"
    reference_style_filter = reference_visual_filter(reference_profile) if reference_profile else ""
    global_zoom = global_video_zoom_value()
    global_zoom_filter = global_video_zoom_filter(global_zoom)
    output_look_filter = text_config("render", "outputLookFilter").strip()
    render_fps = output_fps()
    multicam_mode = text_config("render", "multicamMode", default="master-first")

    cameras: list[tuple[str, Path]] = []
    if manifest_camera_sources:
        cameras = manifest_camera_sources
    else:
        if master:
            cameras.append(("master", master))
        if right:
            cameras.append(("camera2", right))
        if left:
            cameras.append(("camera3", left))
    if not cameras:
        raise RuntimeError("Drop or select at least a Camera 1 / master video before running the multicam renderer.")
    if range_mode_value == "full":
        start = 0.0
        source_duration = full_range_duration(cameras, source_duration)
    replacements, duration = build_omission_replacements(start, source_duration)
    sync_sources = cameras + audio_sources
    if external_audio and not audio_sources:
        sync_sources.append(("external", external_audio))
    sync_offsets = load_sync_offsets(sync_sources)
    person_plans, person_crop_report = load_person_edit_plans(cameras)
    face_center_segments, face_center_report = load_face_center_crop_plan()
    face_crop_axis = face_center_crop_axis()
    face_center_report["axis"] = face_crop_axis
    ensure_omission_cards(replacements)

    audio_source = nested(APP_CONFIG, "render", "audioSource", default="external-if-selected")
    use_external_audio = audio_source == "external-if-selected" and external_audio
    audio_input_index = 0
    if audio_source == "rightCloseVideo":
        audio_input_index = next((i for i, (name, _) in enumerate(cameras) if name == "camera2"), 0)
    elif audio_source == "leftCloseVideo":
        audio_input_index = next((i for i, (name, _) in enumerate(cameras) if name == "camera3"), 0)
    elif use_external_audio:
        audio_input_index = -1

    audio_role = cameras[audio_input_index][0] if 0 <= audio_input_index < len(cameras) else external_audio_role
    natural_cut_audio_path = external_audio if use_external_audio else cameras[audio_input_index][1]
    camera_indexes = [(name, index) for index, (name, _) in enumerate(cameras)]
    subtitle_source_offset = subtitle_source_offset_seconds(audio_role, sync_offsets)
    SUBTITLE_TIMEBASE_REPORT.parent.mkdir(parents=True, exist_ok=True)
    SUBTITLE_TIMEBASE_REPORT.write_text(
        json.dumps(
            {
                "subtitlePath": str(selected_subtitle_path(APP_CONFIG, extensions=(".srt",)) or ""),
                "subtitleSourceRole": selected_subtitle_source_role(),
                "audioRole": audio_role,
                "sourceOffsetSeconds": round(subtitle_source_offset, 6),
                "interpretation": "overlay timeline seconds = subtitle source seconds - sourceOffsetSeconds",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    mode = subtitle_mode()
    subtitle_items: list[dict[str, Any]] = []
    overlay_inputs: list[tuple[dict[str, Any], dict[str, object]]] = []
    precomposed_overlay_videos: list[Path] = []
    chapter_title_items: list[dict[str, Any]] = []
    chapter_config = chapter_title_manifest()
    if chapter_config:
        manifest, title_config = chapter_config
        chapter_title_items = transform_overlay_items(
            read_overlay_items(manifest, start, source_duration, subtitle_source_offset),
            replacements,
            start,
            source_duration,
            duration,
        )
        overlay_inputs.extend((item, title_config) for item in chapter_title_items)
    if not chapter_title_items:
        run([sys.executable, str(SCRIPTS / "generate_title_png_overlay.py")])
    if mode != "none":
        manifest, caption_config = subtitle_manifest(mode)
        subtitle_items = transform_overlay_items(
            read_overlay_items(manifest, start, source_duration, subtitle_source_offset),
            replacements,
            start,
            source_duration,
            duration,
        )
        if should_precompose_overlay_items(mode, subtitle_items, caption_config, duration):
            precomposed_overlay_videos.append(
                precompose_overlay_video(subtitle_items, caption_config, start, duration, f"{output.stem}_full_subtitles")
            )
        else:
            overlay_inputs.extend((item, caption_config) for item in subtitle_items)
    if bool_value("glossary", "enabled", default=bool_value("render", "termExplanations", default=False)):
        manifest, glossary_config = glossary_manifest()
        overlay_inputs.extend(
            (item, glossary_config)
            for item in transform_overlay_items(
                read_overlay_items(manifest, start, source_duration, subtitle_source_offset),
                replacements,
                start,
                source_duration,
                duration,
            )
        )
    planning_subtitle_items = subtitle_items or subtitle_planning_items()
    still_inserts = plan_still_inserts(parse_still_images(), subtitle_items, start, duration)
    timeline_segments = build_segments(duration, camera_indexes, planning_subtitle_items, start)
    timeline_segments, natural_cut_report = adjust_segments_to_dialogue_gaps(
        timeline_segments,
        duration=duration,
        audio_path=natural_cut_audio_path,
        audio_role=audio_role,
        timeline_start=start,
        sync_offsets=sync_offsets,
        replacements=replacements,
    )
    timeline_segments, onscreen_closeup_report = restrict_closeups_to_onscreen_speech(
        timeline_segments,
        duration=duration,
        cameras=camera_indexes,
        captions=planning_subtitle_items,
        timeline_start=start,
    )
    if onscreen_closeup_report.get("changed"):
        write_camera_plan_report(
            f"{multicam_mode}+onscreen-speaker-mask",
            timeline_segments,
            str(ONSCREEN_CLOSEUP_REPORT),
        )
    timeline_segments, source_coverage_report = constrain_segments_to_source_coverage(
        timeline_segments,
        [(role, index, path) for index, (role, path) in enumerate(cameras)],
        duration=duration,
        timeline_start=start,
        sync_offsets=sync_offsets,
        replacements=replacements,
    )
    if source_coverage_report.get("changed"):
        write_camera_plan_report(
            f"{multicam_mode}+source-coverage",
            timeline_segments,
            str(SOURCE_COVERAGE_REPORT),
        )
    if use_external_audio:
        timeline_segments, external_sync_report = guard_segments_by_external_audio_sync(
            timeline_segments,
            [(role, index, path) for index, (role, path) in enumerate(cameras)],
            duration=duration,
            timeline_start=start,
            sync_offsets=sync_offsets,
            external_audio_path=external_audio,
            audio_role=audio_role,
            replacements=replacements,
        )
    color_filters, color_report = camera_color_match_filters(
        cameras,
        start,
        duration,
        sync_offsets,
        segments=timeline_segments,
        replacements=replacements,
    )
    extra_camera_filters, extra_camera_filter_report = configured_camera_extra_filters(cameras)
    if output_look_filter:
        color_report["outputLookFilter"] = output_look_filter
    if extra_camera_filter_report:
        color_report["manualExtraFilters"] = extra_camera_filter_report
    if output_look_filter or extra_camera_filter_report:
        COLOR_MATCH_REPORT.parent.mkdir(parents=True, exist_ok=True)
        COLOR_MATCH_REPORT.write_text(json.dumps(color_report, ensure_ascii=False, indent=2), encoding="utf-8")
    video_segments = video_segments_with_stills(duration, timeline_segments, still_inserts, replacements)
    source_ranges: dict[int, list[float]] = {}
    for segment in video_segments:
        if segment["type"] != "camera":
            continue
        role = str(segment["role"])
        input_index = int(segment["input_index"])
        source_start_local = output_local_to_source_local(float(segment["start"]), replacements) if replacements else float(segment["start"])
        source_end_local = output_local_to_source_local(float(segment["end"]), replacements) if replacements else float(segment["end"])
        if source_start_local is None or source_end_local is None:
            continue
        source_start = max(0.0, sync_offsets.get(role, 0.0) + start + source_start_local)
        source_end = max(source_start, sync_offsets.get(role, 0.0) + start + source_end_local)
        current_range = source_ranges.setdefault(input_index, [source_start, source_end])
        current_range[0] = min(current_range[0], source_start)
        current_range[1] = max(current_range[1], source_end)

    if 0 <= audio_input_index < len(cameras):
        audio_role = cameras[audio_input_index][0]
        audio_start = max(0.0, sync_offsets.get(audio_role, 0.0) + start)
        audio_end = audio_start + source_duration
        current_range = source_ranges.setdefault(audio_input_index, [audio_start, audio_end])
        current_range[0] = min(current_range[0], audio_start)
        current_range[1] = max(current_range[1], audio_end)

    input_seek: dict[int, float] = {}
    camera_input_paths, proxy_usage = camera_input_paths_for_render(cameras, render_profile_value)
    command = [str(FFMPEG), "-hide_banner", "-y"]
    for index, (_, camera_path) in enumerate(cameras):
        range_start, range_end = source_ranges.get(index, [start, start + source_duration])
        input_seek[index] = range_start
        command.extend(
            [
                "-ss",
                f"{range_start:.6f}",
                "-t",
                f"{max(0.1, range_end - range_start):.6f}",
                "-i",
                str(camera_input_paths.get(index, camera_path)),
            ]
        )

    for still_index, still in enumerate(still_inserts):
        still["input_index"] = len(cameras) + still_index
        command.extend(["-loop", "1", "-framerate", render_fps, "-t", f"{max(0.1, float(still['end']) - float(still['start'])):.6f}", "-i", str(still["path"])])

    next_input_index = len(cameras) + len(still_inserts)
    for replacement in replacements:
        replacement["input_index"] = next_input_index
        command.extend(["-loop", "1", "-framerate", render_fps, "-t", f"{float(replacement['duration']):.6f}", "-i", str(replacement["path"])])
        next_input_index += 1
    logo_index = None
    if logo:
        logo_index = next_input_index
        command.extend(["-i", str(logo)])
        next_input_index += 1
    title_index = None
    if not chapter_title_items:
        title_index = next_input_index
        command.extend(["-i", str(TITLE)])
        next_input_index += 1
    precomposed_overlay_input_start_index = next_input_index
    for overlay_video in precomposed_overlay_videos:
        command.extend(["-i", str(overlay_video)])
        next_input_index += 1
    overlay_input_start_index = next_input_index
    for item, _ in overlay_inputs:
        overlay_start = max(0.0, seconds(item["start"]) - start)
        overlay_end = min(duration, seconds(item["end"]) - start)
        overlay_duration = max(0.1, overlay_end - overlay_start + 0.4)
        command.extend(["-loop", "1", "-framerate", render_fps, "-t", f"{overlay_duration:.3f}", "-i", str(WORK / item["file"])])
    next_input_index += len(overlay_inputs)
    external_audio_index = None
    if use_external_audio:
        external_audio_index = next_input_index
        external_audio_start = max(0.0, sync_offsets.get(external_audio_role, 0.0) + start)
        command.extend(["-ss", f"{external_audio_start:.6f}", "-t", f"{source_duration:.6f}", "-i", str(external_audio)])
        next_input_index += 1
        audio_input_index = external_audio_index
    music = ensure_music_bed(duration) if should_mix_music(start, duration, replacements) else None
    music_index = None
    if music:
        music_index = next_input_index
        command.extend(["-stream_loop", "-1", "-i", str(music)])
        next_input_index += 1

    filters: list[str] = []
    segment_labels: list[str] = []
    for segment_index, segment in enumerate(video_segments):
        label = f"seg{segment_index}"
        seg_start = float(segment["start"])
        seg_end = float(segment["end"])
        if segment["type"] == "still":
            still = segment["still"]
            filters.append(still_filter(int(still["input_index"]), label, seg_end - seg_start, still, segment_index))
        elif segment["type"] == "omission_card":
            replacement = segment["replacement"]
            filters.append(omission_card_filter(int(replacement["input_index"]), label, seg_end - seg_start))
        else:
            role = str(segment["role"])
            input_index = int(segment["input_index"])
            source_start_local = output_local_to_source_local(seg_start, replacements) if replacements else seg_start
            source_end_local = output_local_to_source_local(seg_end, replacements) if replacements else seg_end
            if source_start_local is None or source_end_local is None:
                continue
            source_start = max(0.0, sync_offsets.get(role, 0.0) + start + source_start_local)
            source_end = max(source_start, sync_offsets.get(role, 0.0) + start + source_end_local)
            local_start = max(0.0, source_start - input_seek.get(input_index, 0.0))
            local_end = max(local_start, source_end - input_seek.get(input_index, 0.0))
            source_mid = (source_start + source_end) / 2
            fallback_visual_filter = (
                dynamic_reframe_filter(segment_index, role, reference_style_filter)
                if multicam_mode == "dynamic-cuts"
                else reference_filter
            )
            visual_filter, person_crop_detail = camera_segment_visual_filter(
                fallback_visual_filter,
                reference_style_filter,
                person_plans,
                role,
                source_mid,
            )
            if person_crop_detail:
                cast_segments = person_crop_report.get("segments")
                if isinstance(cast_segments, list):
                    cast_segments.append(
                        {
                            **person_crop_detail,
                            "outputStart": round(seg_start, 3),
                            "outputEnd": round(seg_end, 3),
                        }
                    )
            if color_filters.get(input_index):
                visual_filter = f"{visual_filter},{color_filters[input_index]}"
            if extra_camera_filters.get(input_index):
                visual_filter = f"{visual_filter},{extra_camera_filters[input_index]}"
            if output_look_filter:
                visual_filter = f"{visual_filter},{output_look_filter}"
            face_center_segment = face_center_crop_segment(face_center_segments, role, seg_start, seg_end)
            center_x = 0.5
            center_y = 0.5
            if face_center_segment:
                detected_center_x = float(face_center_segment.get("centerX", face_center_segment.get("center_x", 0.5)))
                subject_screen_x = face_center_subject_screen_x(role)
                center_x = adjusted_face_center_crop_x(detected_center_x, global_zoom, subject_screen_x)
                if face_crop_axis == "xy":
                    center_y = float(face_center_segment.get("centerY", face_center_segment.get("center_y", 0.5)))
                cast_face_segments = face_center_report.get("segments")
                if isinstance(cast_face_segments, list):
                    cast_face_segments.append(
                        {
                            "role": role,
                            "outputStart": round(seg_start, 3),
                            "outputEnd": round(seg_end, 3),
                            "zoom": round(global_zoom, 4),
                            "detectedCenterX": round(detected_center_x, 5),
                            "centerX": round(center_x, 5),
                            "centerY": round(center_y, 5),
                            "subjectScreenX": round(subject_screen_x, 5),
                            "detectedCenterY": face_center_segment.get("centerY", face_center_segment.get("center_y")),
                            "source": face_center_segment.get("source"),
                            "detections": face_center_segment.get("detections"),
                        }
                    )
            else:
                cast_fallback = face_center_report.get("fallbackSegments")
                if isinstance(cast_fallback, list) and face_center_report.get("enabled"):
                    cast_fallback.append({"role": role, "outputStart": round(seg_start, 3), "outputEnd": round(seg_end, 3)})
            segment_global_zoom_filter = global_video_zoom_filter(global_zoom, center_x, center_y)
            if segment_global_zoom_filter:
                visual_filter = f"{visual_filter},{segment_global_zoom_filter}"
            filters.append(
                f"[{input_index}:v]setpts=PTS-STARTPTS,trim=start={local_start:.6f}:end={local_end:.6f},"
                f"setpts=PTS-STARTPTS,{visual_filter}[{label}]"
            )
        segment_labels.append(label)

    PERSON_CROP_REPORT.parent.mkdir(parents=True, exist_ok=True)
    PERSON_CROP_REPORT.write_text(json.dumps(person_crop_report, ensure_ascii=False, indent=2), encoding="utf-8")
    FACE_CENTER_CROP_REPORT.parent.mkdir(parents=True, exist_ok=True)
    FACE_CENTER_CROP_REPORT.write_text(json.dumps(face_center_report, ensure_ascii=False, indent=2), encoding="utf-8")

    if len(segment_labels) == 1:
        filters.append(f"[{segment_labels[0]}]copy[vbase_raw]")
    else:
        filters.append("".join(f"[{label}]" for label in segment_labels) + f"concat=n={len(segment_labels)}:v=1:a=0[vbase_raw]")
    filters.append(f"[vbase_raw]fps={render_fps}[vbase]")

    title_base = "vbase"
    if logo_index is not None:
        filters.extend(
            [
                f"[{logo_index}:v]scale=-1:{logo_height}[logo]",
                "[vbase][logo]overlay=W-w-40:40[vlogo]",
            ]
        )
        title_base = "vlogo"
    if title_index is not None:
        title_x = int_value(APP_CONFIG, "style", "titleX", default=18)
        title_y = int_value(APP_CONFIG, "style", "titleY", default=18)
        filters.append(f"[{title_base}][{title_index}:v]overlay={title_x}:{title_y}[vtitle]")
        current = "vtitle"
    else:
        current = title_base
    for index, _ in enumerate(precomposed_overlay_videos, start=1):
        stream_index = precomposed_overlay_input_start_index + index - 1
        next_label = f"vprecomp{index}"
        filters.append(
            f"[{stream_index}:v]format=rgba[precomp{index}];"
            f"[{current}][precomp{index}]overlay=0:0:enable='between(t,0.000,{duration:.3f})'[{next_label}]"
        )
        current = next_label
    first_overlay_index = overlay_input_start_index
    for index, (item, caption_config) in enumerate(overlay_inputs, start=1):
        stream_index = first_overlay_index + index - 1
        start_t = max(0.0, seconds(item["start"]) - start)
        end_t = min(duration, seconds(item["end"]) - start)
        fade_out = max(start_t, end_t - 0.18)
        base_scale = "if(gt(iw,1760),1760/iw,1)"
        if caption_config.get("pop"):
            pop_scale = f"if(between(t,{start_t:.3f},{start_t + 0.22:.3f}),0.88+0.12*(t-{start_t:.3f})/0.22,1)"
        else:
            pop_scale = "1"
        if caption_config.get("animate"):
            y_expr = (
                f"H-h-{caption_config['bottom_margin']}+"
                f"if(between(t,{start_t:.3f},{start_t + 0.26:.3f}),"
                f"{caption_config['slide_px']}*(1-(t-{start_t:.3f})/0.26),0)"
            )
            filters.append(
                f"[{stream_index}:v]format=rgba,"
                f"setpts=PTS+{start_t:.3f}/TB,"
                f"fade=t=in:st={start_t:.3f}:d=0.16:alpha=1,"
                f"fade=t=out:st={fade_out:.3f}:d=0.18:alpha=1,"
                f"scale=w='iw*{base_scale}*{pop_scale}':h='ih*{base_scale}*{pop_scale}':eval=frame[p{index}]"
            )
        else:
            y_expr = str(caption_config.get("y_expr") or f"H-h-{caption_config['bottom_margin']}")
            filters.append(
                f"[{stream_index}:v]format=rgba,setpts=PTS+{start_t:.3f}/TB,"
                f"scale=w='iw*{base_scale}':h='ih*{base_scale}':eval=init[p{index}]"
            )
        x_expr = str(caption_config.get("x_expr") or "(W-w)/2")
        next_label = f"vsub{index}"
        filters.append(f"[{current}][p{index}]overlay=x='{x_expr}':y='{y_expr}':enable='between(t,{start_t:.3f},{end_t:.3f})'[{next_label}]")
        current = next_label

    def audio_local_time(source_local: float) -> float:
        if audio_role.startswith("external"):
            return max(0.0, source_local)
        audio_abs = max(0.0, sync_offsets.get(audio_role, 0.0) + start + source_local)
        return max(0.0, audio_abs - input_seek.get(audio_input_index, 0.0))

    if replacements:
        audio_parts: list[dict[str, float | str]] = []
        source_cursor = 0.0
        for replacement in replacements:
            source_start = float(replacement["source_start"])
            source_end = float(replacement["source_end"])
            if source_start - source_cursor > 0.02:
                audio_parts.append({"type": "source", "start": source_cursor, "end": source_start})
            audio_parts.append({"type": "card", "duration": float(replacement["duration"])})
            source_cursor = source_end
        if source_duration - source_cursor > 0.02:
            audio_parts.append({"type": "source", "start": source_cursor, "end": source_duration})

        audio_labels: list[str] = []
        for index, part in enumerate(audio_parts):
            label = f"aud{index}"
            if part["type"] == "card":
                filters.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={float(part['duration']):.6f},asetpts=PTS-STARTPTS[{label}]")
            else:
                local_start = audio_local_time(float(part["start"]))
                local_end = max(local_start, audio_local_time(float(part["end"])))
                filters.append(f"[{audio_input_index}:a]atrim=start={local_start:.6f}:end={local_end:.6f},asetpts=PTS-STARTPTS[{label}]")
            audio_labels.append(label)
        if len(audio_labels) == 1:
            filters.append(f"[{audio_labels[0]}]anull[voice_raw]")
        else:
            filters.append("".join(f"[{label}]" for label in audio_labels) + f"concat=n={len(audio_labels)}:v=0:a=1[voice_raw]")
        filters.append(
            f"[voice_raw]{audio_cleanup_filter(audio_denoise_strength, audio_mastering, audio_denoise) if audio_denoise or audio_mastering else 'anull'}[voice]"
        )
    else:
        audio_start = max(0.0, sync_offsets.get(audio_role, 0.0) + start)
        audio_local_start = 0.0 if audio_role.startswith("external") else max(0.0, audio_start - input_seek.get(audio_input_index, 0.0))
        audio_filters = f"atrim=start={audio_local_start:.6f}:duration={duration:.6f},asetpts=PTS-STARTPTS"
        if audio_denoise or audio_mastering:
            audio_filters += f",{audio_cleanup_filter(audio_denoise_strength, audio_mastering, audio_denoise)}"
        filters.append(f"[{audio_input_index}:a]{audio_filters}[voice]")
    audio_output = "voice"
    if music_index is not None:
        filters.append(
            f"[{music_index}:a]atrim=start=0:duration={duration:.6f},asetpts=PTS-STARTPTS,"
            f"{music_volume_filter(start, duration, replacements)}[music]"
        )
        filters.append("[voice][music]amix=inputs=2:duration=first:dropout_transition=0,alimiter=limit=0.95[a]")
        audio_output = "a"

    shorten_silence_enabled = bool_value("render", "shortenSilence", default=True) and render_profile_value != "preview"
    render_output = output
    if shorten_silence_enabled:
        render_output = output.with_name(f"{output.stem}_uncut{output.suffix}")
    encoder_config = video_encoder_config()
    encoder_args = [str(item) for item in encoder_config["args"]]
    audio_bitrate = "96k" if render_profile_value == "preview" else "192k"
    filter_script = write_filter_complex_script(filters, output.stem)

    command.extend(
        [
            "-filter_complex_script",
            str(filter_script),
            "-map",
            f"[{current}]",
            "-map",
            f"[{audio_output}]",
            *encoder_args,
            "-c:a",
            "aac",
            "-b:a",
            audio_bitrate,
            "-shortest",
            str(render_output),
        ]
    )
    run(command)

    silence_shortening_report = None
    if shorten_silence_enabled:
        silence_shortening_report = shorten_silences(
            render_output,
            output,
            SilenceShortenConfig(
                min_silence=float(nested(APP_CONFIG, "render", "minSilence", default=DEFAULT_MIN_SILENCE)),
                keep_silence=float(nested(APP_CONFIG, "render", "keepSilence", default=DEFAULT_KEEP_SILENCE)),
                noise=str(nested(APP_CONFIG, "render", "silenceNoise", default=DEFAULT_NOISE)),
            ),
        )
        if not nested(APP_CONFIG, "render", "keepUncut", default=False):
            render_output.unlink(missing_ok=True)
    usage_report = {
        "renderProfile": render_profile_value,
        "rangeMode": range_mode_value,
        "start": start,
        "sourceDuration": source_duration,
        "outputDuration": duration,
        "outputPath": str(output),
        "renderOutputPath": str(render_output),
        "filterScript": str(filter_script),
        "encoder": {key: value for key, value in encoder_config.items() if key != "args"},
        "audioBitrate": audio_bitrate,
        "shortenSilenceRequested": bool_value("render", "shortenSilence", default=True),
        "shortenSilenceApplied": shorten_silence_enabled,
        "proxyUsage": proxy_usage,
    }
    try:
        RENDER_USAGE_REPORT.parent.mkdir(parents=True, exist_ok=True)
        RENDER_USAGE_REPORT.write_text(json.dumps(usage_report, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
    summary = {
        "output": str(output),
        "render_usage_report": str(RENDER_USAGE_REPORT),
        "render_profile": render_profile_value,
        "range_mode": range_mode_value,
        "audio_denoise": audio_denoise,
        "audio_mastering": audio_mastering,
        "encoder": {key: value for key, value in encoder_config.items() if key != "args"},
        "global_video_zoom": global_zoom,
        "camera_cut_plan": camera_plan_summary(),
        "source_coverage": source_coverage_report,
        "natural_dialogue_cuts": natural_cut_report,
        "camera_color_match": color_match_summary(color_report),
        "person_crop": person_crop_summary(person_crop_report),
        "face_center_crop": face_center_crop_summary(face_center_report),
        "still_inserts": still_report(still_inserts),
        "omission_card": omission_card_report(replacements),
        "music": music_report(start, duration, music, replacements),
        "proxy_usage": proxy_usage,
    }
    if silence_shortening_report:
        summary["silence_shortening"] = silence_shortening_report
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
