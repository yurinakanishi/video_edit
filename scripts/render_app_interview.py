from __future__ import annotations

import json
import math
import re
import subprocess
import sys
from array import array
from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter, ImageStat

from project_paths import (
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

from shorten_silences import DEFAULT_KEEP_SILENCE, DEFAULT_MIN_SILENCE, DEFAULT_NOISE, SilenceShortenConfig, shorten_silences
from video_edit_app_config import (
    int_value,
    load_app_config,
    nested,
    optional_path,
    selected_subtitle_path,
    transcript_manifest_fingerprint,
    video_encoder_crf,
    video_encoder_preset,
)
from composition_rules import crop_window_center_for_subject, subject_target_for_face, visible_ratio_for_area


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
SYNC_OFFSET_USAGE_REPORT = OUTPUT_REPORTS / "sync_offset_usage.json"
SOURCE_COVERAGE_REPORT = OUTPUT_REPORTS / "source_coverage_usage.json"


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
        parts.append(f"afftdn=nr={nr}:nf=-35")
    if mastering:
        parts.extend(
            [
                "dynaudnorm=f=250:g=15:p=0.95:m=8",
                "acompressor=threshold=-20dB:ratio=2.8:attack=5:release=120:makeup=4",
                "loudnorm=I=-14:TP=-1.5:LRA=9",
            ]
        )
    return ",".join(parts)


def float_config(*keys: str, default: float) -> float:
    value = nested(APP_CONFIG, *keys, default=default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def text_config(*keys: str, default: str = "") -> str:
    value = nested(APP_CONFIG, *keys, default=default)
    return str(value) if value is not None else default


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


def crop_filter_from_subject_target(
    center_x: float,
    center_y: float,
    area_ratio: float,
    desired_subject_x: float,
    desired_subject_y: float,
) -> str:
    visible_ratio = visible_ratio_for_area(area_ratio)
    window_center_x = crop_window_center_for_subject(clamp(center_x, 0.2, 0.8), clamp(desired_subject_x, 0.35, 0.65), visible_ratio)
    window_center_y = crop_window_center_for_subject(clamp(center_y, 0.25, 0.75), clamp(desired_subject_y, 0.30, 0.52), visible_ratio)
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
    center = target.get("person_center_ratio") if isinstance(target.get("person_center_ratio"), list) else None
    area = target.get("person_area_ratio")
    face_direction = str(target.get("dominant_face_direction") or "unknown")
    desired_subject_x = target.get("desired_subject_x_ratio")
    desired_subject_y = target.get("desired_subject_y_ratio")

    center_x = clamp(float(center[0]), 0.2, 0.8) if center and center[0] is not None else 0.5
    center_y = clamp(float(center[1]), 0.25, 0.75) if center and center[1] is not None else 0.5
    area_ratio = float(area) if area is not None else 0.0

    if desired_subject_x is None:
        desired_subject_x = subject_target_for_face(face_direction).x
    if desired_subject_y is None:
        desired_subject_y = subject_target_for_face(face_direction).y
    return (
        f"{crop_filter_from_subject_target(center_x, center_y, area_ratio, float(desired_subject_x), float(desired_subject_y))},"
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
        center_x = float(crop_target["x"])
        center_y = float(crop_target["y"])
        desired_x = float(crop_target.get("desired_subject_x_ratio", segment.get("desired_subject_x_ratio", 0.5)))
        desired_y = float(crop_target.get("desired_subject_y_ratio", segment.get("desired_subject_y_ratio", 0.382)))
        area_ratio = float(segment.get("avg_area_ratio") or 0.0)
    except (KeyError, TypeError, ValueError):
        return None
    return crop_filter_from_subject_target(center_x, center_y, area_ratio, desired_x, desired_y)


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
    }
    return visual_filter, detail


def frame_visual_stats(path: Path, timestamps: list[float]) -> dict[str, Any] | None:
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
    except Exception:
        return None

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return None
    rows: list[dict[str, float]] = []
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
        neutral_mask = (hsv[:, :, 1] < 90) & (hsv[:, :, 2] > 80) & (hsv[:, :, 2] < 245)
        neutral_samples = frame[neutral_mask]
        if len(neutral_samples) < 500:
            neutral_samples = frame.reshape(-1, 3)
        mean_bgr = np.mean(frame.reshape(-1, 3), axis=0) / 255.0
        neutral_bgr = np.mean(neutral_samples, axis=0) / 255.0
        rows.append(
            {
                "brightness": float(np.mean(gray)) / 255.0,
                "contrast": float(np.std(gray)) / 255.0,
                "saturation": float(np.mean(hsv[:, :, 1])) / 255.0,
                "mean_b": float(mean_bgr[0]),
                "mean_g": float(mean_bgr[1]),
                "mean_r": float(mean_bgr[2]),
                "neutral_b": float(neutral_bgr[0]),
                "neutral_g": float(neutral_bgr[1]),
                "neutral_r": float(neutral_bgr[2]),
            }
        )
    cap.release()
    if not rows:
        return None
    return {
        "brightness": sum(row["brightness"] for row in rows) / len(rows),
        "contrast": sum(row["contrast"] for row in rows) / len(rows),
        "saturation": sum(row["saturation"] for row in rows) / len(rows),
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
        "samples": float(len(rows)),
    }


def bgr_triplet(stats: dict[str, Any], key: str) -> list[float] | None:
    value = stats.get(key)
    if not isinstance(value, list) or len(value) != 3:
        return None
    try:
        return [float(value[0]), float(value[1]), float(value[2])]
    except (TypeError, ValueError):
        return None


def color_channel_gains(master: dict[str, Any], item: dict[str, Any]) -> dict[str, float]:
    master_bgr = bgr_triplet(master, "neutralBgr") or bgr_triplet(master, "meanBgr")
    item_bgr = bgr_triplet(item, "neutralBgr") or bgr_triplet(item, "meanBgr")
    if master_bgr is None or item_bgr is None:
        return {"red": 1.0, "green": 1.0, "blue": 1.0}
    blue = clamp(master_bgr[0] / max(item_bgr[0], 0.025), 0.86, 1.16)
    green = clamp(master_bgr[1] / max(item_bgr[1], 0.025), 0.86, 1.16)
    red = clamp(master_bgr[2] / max(item_bgr[2], 0.025), 0.86, 1.16)
    return {"red": red, "green": green, "blue": blue}


def camera_color_match_filters(cameras: list[tuple[str, Path]], start: float, duration: float) -> tuple[dict[int, str], dict[str, Any]]:
    report: dict[str, Any] = {"enabled": bool_value("render", "colorMatchCameras", default=False), "items": []}
    if not report["enabled"] or len(cameras) < 2:
        return {}, report
    white_balance = bool_value("render", "colorMatchWhiteBalance", default=True)
    report["whiteBalance"] = white_balance
    sample_count = max(2, min(int_value(APP_CONFIG, "render", "colorMatchSamples", default=5), 12))
    sample_span = max(1.0, duration)
    timestamps = [start + sample_span * (index + 1) / (sample_count + 1) for index in range(sample_count)]
    stats = [frame_visual_stats(path, timestamps) for _, path in cameras]
    master = stats[0] if stats else None
    if not master:
        report["reason"] = "master stats unavailable"
        return {}, report

    filters: dict[int, str] = {}
    for index, ((role, path), item_stats) in enumerate(zip(cameras, stats)):
        if not item_stats:
            report["items"].append({"role": role, "path": str(path), "skipped": "stats unavailable"})
            continue
        if index == 0:
            report["items"].append({"role": role, "path": str(path), "reference": True, "stats": item_stats})
            continue
        master_contrast = float(master["contrast"])
        item_contrast = float(item_stats["contrast"])
        master_saturation = float(master["saturation"])
        item_saturation = float(item_stats["saturation"])
        brightness_adj = clamp((float(master["brightness"]) - float(item_stats["brightness"])) * 0.36, -0.12, 0.12)
        contrast_adj = 1.0 if master_contrast < 0.025 and item_contrast < 0.025 else clamp(master_contrast / max(item_contrast, 0.025), 0.84, 1.18)
        saturation_adj = (
            1.0
            if master_saturation < 0.08 and item_saturation < 0.08
            else clamp(master_saturation / max(item_saturation, 0.025), 0.74, 1.26)
        )
        gains = color_channel_gains(master, item_stats) if white_balance else {"red": 1.0, "green": 1.0, "blue": 1.0}
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
                "redGain": round(gains["red"], 5),
                "greenGain": round(gains["green"], 5),
                "blueGain": round(gains["blue"], 5),
                "brightness": round(brightness_adj, 5),
                "contrast": round(contrast_adj, 5),
                "saturation": round(saturation_adj, 5),
                "filter": filters[index],
            }
        )
    COLOR_MATCH_REPORT.parent.mkdir(parents=True, exist_ok=True)
    COLOR_MATCH_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return filters, report


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
    return (
        f"[{input_index}:v]fps=60,scale=1920:1080:force_original_aspect_ratio=decrease,"
        f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,"
        f"trim=duration={duration:.6f},setpts=PTS-STARTPTS,"
        f"fade=t=in:st=0:d=0.18,fade=t=out:st={fade_out:.3f}:d=0.25[{label}]"
    )


def still_filter(input_index: int, label: str, duration: float, still: dict[str, Any], phase: int) -> str:
    fade_out = max(0.0, duration - 0.25)
    kind = str(still["kind"])
    if kind in {"text", "diagram"}:
        base = (
            f"[{input_index}:v]fps=60,scale=1920:1080:force_original_aspect_ratio=decrease,"
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
            f"[{input_index}:v]fps=60,"
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
            "generator": SCRIPTS / "generate_full_transcript_png_overlays.py",
            "manifest": OUTPUT_OVERLAYS / "full_transcript_png_overlays" / "manifest.json",
            "bottom_margin": 16,
            "slide_px": 0,
            "pop": False,
            "animate": False,
        },
        "punchline": {
            "generator": SCRIPTS / "generate_punchline_png_overlays.py",
            "manifest": OUTPUT_OVERLAYS / "punchline_png_overlays" / "manifest.json",
            "bottom_margin": 12,
            "slide_px": 44,
            "pop": True,
            "animate": True,
        },
    }
    config = modes[mode]
    run([sys.executable, str(config["generator"])])
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


def read_overlay_items(manifest: Path, start: float, duration: float) -> list[dict[str, Any]]:
    if not manifest.exists():
        return []
    return [
        item
        for item in json.loads(manifest.read_text(encoding="utf-8"))
        if seconds(item["start"]) < start + duration and seconds(item["end"]) > start
    ]


def main() -> None:
    manifest_camera_sources = manifest_cameras()
    master = path_value("assets", "masterVideo")
    right = path_value("assets", "rightCloseVideo")
    left = path_value("assets", "leftCloseVideo")
    audio_sources = manifest_audio_sources()
    external_audio = audio_sources[0][1] if audio_sources else path_value("assets", "externalAudio")
    external_audio_role = audio_sources[0][0] if audio_sources else "external"
    logo = selected_logo_path()
    output = Path(nested(APP_CONFIG, "render", "outputPath", default=OUTPUT_VIDEOS / "app_interview_output.mp4"))
    start = float(nested(APP_CONFIG, "render", "previewStart", default=0.0) or 0.0)
    source_duration = float(nested(APP_CONFIG, "render", "previewDuration", default=60.0) or 60.0)
    replacements, duration = build_omission_replacements(start, source_duration)
    logo_height = int_value(APP_CONFIG, "style", "logoHeight", default=48)
    audio_denoise = bool_value("render", "audioDenoise", default=True)
    audio_denoise_strength = int_value(APP_CONFIG, "render", "audioDenoiseStrength", default=DEFAULT_DENOISE_STRENGTH)
    audio_mastering = bool_value("render", "audioMastering", default=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    reference_profile = load_reference_profile()
    reference_filter = reference_video_filter(reference_profile) if reference_profile else "scale=1920:1080"
    reference_style_filter = reference_visual_filter(reference_profile) if reference_profile else ""
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
        raise RuntimeError("Drop or select at least a Camera 1 / master video before running render_app_interview.py.")
    person_plans, person_crop_report = load_person_edit_plans(cameras)
    color_filters, color_report = camera_color_match_filters(cameras, start, source_duration)
    sync_sources = cameras + audio_sources
    if external_audio and not audio_sources:
        sync_sources.append(("external", external_audio))
    sync_offsets = load_sync_offsets(sync_sources)
    run([sys.executable, str(SCRIPTS / "generate_title_png_overlay.py")])
    ensure_omission_cards(replacements)

    mode = subtitle_mode()
    subtitle_items: list[dict[str, Any]] = []
    overlay_inputs: list[tuple[dict[str, Any], dict[str, object]]] = []
    if mode != "none":
        manifest, caption_config = subtitle_manifest(mode)
        subtitle_items = transform_overlay_items(
            read_overlay_items(manifest, start, source_duration),
            replacements,
            start,
            source_duration,
            duration,
        )
        overlay_inputs.extend((item, caption_config) for item in subtitle_items)
    if bool_value("glossary", "enabled", default=bool_value("render", "termExplanations", default=False)):
        manifest, glossary_config = glossary_manifest()
        overlay_inputs.extend(
            (item, glossary_config)
            for item in transform_overlay_items(
                read_overlay_items(manifest, start, source_duration),
                replacements,
                start,
                source_duration,
                duration,
            )
        )

    still_inserts = plan_still_inserts(parse_still_images(), subtitle_items, start, duration)
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
    timeline_segments = build_segments(duration, camera_indexes, subtitle_items, start)
    timeline_segments, natural_cut_report = adjust_segments_to_dialogue_gaps(
        timeline_segments,
        duration=duration,
        audio_path=natural_cut_audio_path,
        audio_role=audio_role,
        timeline_start=start,
        sync_offsets=sync_offsets,
        replacements=replacements,
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
    command = [str(FFMPEG), "-hide_banner", "-y"]
    for index, (_, camera_path) in enumerate(cameras):
        range_start, range_end = source_ranges.get(index, [start, start + source_duration])
        input_seek[index] = range_start
        command.extend(["-ss", f"{range_start:.6f}", "-t", f"{max(0.1, range_end - range_start):.6f}", "-i", str(camera_path)])

    for still_index, still in enumerate(still_inserts):
        still["input_index"] = len(cameras) + still_index
        command.extend(["-loop", "1", "-framerate", "60", "-t", f"{max(0.1, float(still['end']) - float(still['start'])):.6f}", "-i", str(still["path"])])

    next_input_index = len(cameras) + len(still_inserts)
    for replacement in replacements:
        replacement["input_index"] = next_input_index
        command.extend(["-loop", "1", "-framerate", "60", "-t", f"{float(replacement['duration']):.6f}", "-i", str(replacement["path"])])
        next_input_index += 1
    logo_index = None
    if logo:
        logo_index = next_input_index
        command.extend(["-i", str(logo)])
        next_input_index += 1
    title_index = next_input_index
    command.extend(["-i", str(TITLE)])
    next_input_index += 1
    for item, _ in overlay_inputs:
        command.extend(["-loop", "1", "-framerate", "60", "-t", f"{duration:.3f}", "-i", str(WORK / item["file"])])
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
            filters.append(
                f"[{input_index}:v]setpts=PTS-STARTPTS,trim=start={local_start:.6f}:end={local_end:.6f},"
                f"setpts=PTS-STARTPTS,{visual_filter}[{label}]"
            )
        segment_labels.append(label)

    PERSON_CROP_REPORT.parent.mkdir(parents=True, exist_ok=True)
    PERSON_CROP_REPORT.write_text(json.dumps(person_crop_report, ensure_ascii=False, indent=2), encoding="utf-8")

    if len(segment_labels) == 1:
        filters.append(f"[{segment_labels[0]}]copy[vbase]")
    else:
        filters.append("".join(f"[{label}]" for label in segment_labels) + f"concat=n={len(segment_labels)}:v=1:a=0[vbase]")

    title_base = "vbase"
    if logo_index is not None:
        filters.extend(
            [
                f"[{logo_index}:v]scale=-1:{logo_height}[logo]",
                "[vbase][logo]overlay=W-w-40:40[vlogo]",
            ]
        )
        title_base = "vlogo"
    filters.append(f"[{title_base}][{title_index}:v]overlay=42:42[vtitle]")

    current = "vtitle"
    first_overlay_index = title_index + 1
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
                f"fade=t=in:st={start_t:.3f}:d=0.16:alpha=1,"
                f"fade=t=out:st={fade_out:.3f}:d=0.18:alpha=1,"
                f"scale=w='iw*{base_scale}*{pop_scale}':h='ih*{base_scale}*{pop_scale}':eval=frame[p{index}]"
            )
        else:
            y_expr = str(caption_config.get("y_expr") or f"H-h-{caption_config['bottom_margin']}")
            filters.append(f"[{stream_index}:v]format=rgba,scale=w='iw*{base_scale}':h='ih*{base_scale}':eval=init[p{index}]")
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

    render_output = output
    if nested(APP_CONFIG, "render", "shortenSilence", default=True):
        render_output = output.with_name(f"{output.stem}_uncut{output.suffix}")
    encoder_preset = video_encoder_preset(APP_CONFIG, "render", "encoderPreset")
    encoder_crf = video_encoder_crf(APP_CONFIG, "render", "crf")

    command.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            f"[{current}]",
            "-map",
            f"[{audio_output}]",
            "-c:v",
            "libx264",
            "-preset",
            encoder_preset,
            "-crf",
            str(encoder_crf),
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            str(render_output),
        ]
    )
    run(command)

    if nested(APP_CONFIG, "render", "shortenSilence", default=True):
        report = shorten_silences(
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
        print(
            json.dumps(
                {
                    "output": str(output),
                    "audio_denoise": audio_denoise,
                    "audio_mastering": audio_mastering,
                    "encoder": {"preset": encoder_preset, "crf": encoder_crf},
                    "camera_cut_plan": camera_plan_summary(),
                    "source_coverage": source_coverage_report,
                    "natural_dialogue_cuts": natural_cut_report,
                    "camera_color_match": color_match_summary(color_report),
                    "person_crop": person_crop_summary(person_crop_report),
                    "still_inserts": still_report(still_inserts),
                    "omission_card": omission_card_report(replacements),
                    "music": music_report(start, duration, music, replacements),
                    "silence_shortening": report,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(
            json.dumps(
                {
                    "output": str(output),
                    "audio_denoise": audio_denoise,
                    "audio_mastering": audio_mastering,
                    "encoder": {"preset": encoder_preset, "crf": encoder_crf},
                    "camera_cut_plan": camera_plan_summary(),
                    "source_coverage": source_coverage_report,
                    "natural_dialogue_cuts": natural_cut_report,
                    "camera_color_match": color_match_summary(color_report),
                    "person_crop": person_crop_summary(person_crop_report),
                    "still_inserts": still_report(still_inserts),
                    "omission_card": omission_card_report(replacements),
                    "music": music_report(start, duration, music, replacements),
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
