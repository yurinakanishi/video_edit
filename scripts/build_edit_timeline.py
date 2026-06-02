from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from video_edit_core.composition import crop_window_center_for_subject, visible_ratio_for_area
from video_edit_core.paths import OUTPUT, OUTPUT_AUDIO, OUTPUT_OVERLAYS, OUTPUT_REPORTS, OUTPUT_VIDEOS, ROOT as WORK, SOURCE
from video_edit_core.timeline.validation import DEFAULT_REPORT, DEFAULT_SCHEMA, SCHEMA_VERSION, validate_timeline, write_report
from video_edit_core.app_config import load_app_config, media_manifest, nested, selected_subtitle_path


DEFAULT_TIMELINE = OUTPUT / "timelines" / "current.timeline.json"
DEFAULT_SYNC = OUTPUT_REPORTS / "app_sync_offsets.json"
DEFAULT_CAMERA_PLAN = OUTPUT_REPORTS / "camera_cut_plan.json"
DEFAULT_MANUAL_CAMERA_PLAN = OUTPUT_REPORTS / "manual_camera_plan.json"
DEFAULT_COLOR_MATCH = OUTPUT_REPORTS / "camera_color_match.json"
DEFAULT_NATURAL_CUT = OUTPUT_REPORTS / "natural_dialogue_cuts.json"
DEFAULT_PERSON_EDIT_PLANS = OUTPUT_REPORTS / "person_edit_plans"
DEFAULT_PERSON_CROP = OUTPUT_REPORTS / "person_crop_usage.json"
DEFAULT_FACE_CROP = OUTPUT_REPORTS / "face_center_crop_usage.json"
DEFAULT_FACE_CENTER_PLAN = OUTPUT_REPORTS / "face_center_crop_plan.json"
DEFAULT_SOURCE_COVERAGE = OUTPUT_REPORTS / "source_coverage_usage.json"
DEFAULT_EXTERNAL_SYNC = OUTPUT_REPORTS / "external_audio_cut_sync_report.json"
DEFAULT_TRANSCRIPT_MANIFEST = OUTPUT / "transcripts" / "manifest_sources" / "manifest_transcripts.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def safe_id(prefix: str, value: str, used: set[str]) -> str:
    base = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._").lower()
    candidate = f"{prefix}_{base or 'item'}"
    if candidate not in used:
        used.add(candidate)
        return candidate
    index = 2
    while f"{candidate}_{index}" in used:
        index += 1
    unique = f"{candidate}_{index}"
    used.add(unique)
    return unique


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if result == result and abs(result) != float("inf") else default


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def bool_value(config: dict[str, Any], *keys: str, default: bool = False) -> bool:
    value = nested(config, *keys, default=default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return bool(value)


def text_value(config: dict[str, Any], *keys: str, default: str = "") -> str:
    value = nested(config, *keys, default=default)
    return str(value) if value is not None else default


def output_fps(config: dict[str, Any]) -> str:
    value = text_value(config, "render", "outputFps", default="60000/1001").strip()
    return value if re.fullmatch(r"\d+(?:/\d+)?(?:\.\d+)?", value) else "60000/1001"


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def resolve_path(value: Any) -> Path:
    path = Path(str(value or ""))
    return path if path.is_absolute() else WORK / path


def media_files(config: dict[str, Any]) -> list[dict[str, Any]]:
    manifest = media_manifest(config)
    files = manifest.get("files") if isinstance(manifest, dict) else []
    if not isinstance(files, list) or not files:
        files = manifest.get("items") if isinstance(manifest, dict) else []
    return [item for item in files if isinstance(item, dict)]


def camera_role_order(role: str) -> int:
    if role == "master":
        return 1
    if role.startswith("camera"):
        return as_int(role.replace("camera", ""), 50)
    return 100


def source_from_media_item(item: dict[str, Any], source_id: str, sync_offsets: dict[str, float]) -> dict[str, Any]:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    kind = str(item.get("kind") or "data")
    source: dict[str, Any] = {
        "id": source_id,
        "kind": kind if kind in {"video", "audio", "image", "subtitle"} else "data",
        "role": str(item.get("role") or ""),
        "path": str(resolve_path(item.get("path"))),
        "metadata": {
            "name": str(item.get("name") or ""),
            "manifestId": str(item.get("id") or ""),
            "relativePath": str(item.get("relativePath") or ""),
        },
    }
    duration = as_float(metadata.get("duration"), 0.0)
    if duration > 0:
        source["duration"] = round(duration, 6)
    width = as_int(metadata.get("width"), 0)
    height = as_int(metadata.get("height"), 0)
    if width:
        source["width"] = width
    if height:
        source["height"] = height
    if metadata.get("fps") not in {None, ""}:
        source["fps"] = metadata.get("fps")
    elif metadata.get("avgFrameRate") not in {None, ""}:
        source["fps"] = metadata.get("avgFrameRate")
    sample_rate = as_int(metadata.get("sampleRate"), 0)
    channels = as_int(metadata.get("channels"), 0)
    if sample_rate:
        source["sampleRate"] = sample_rate
    if channels:
        source["channels"] = channels
    codec = metadata.get("videoCodec") or metadata.get("audioCodec")
    if codec:
        source["codec"] = str(codec)
    role = str(item.get("role") or "")
    if role in sync_offsets:
        source["syncOffset"] = round(sync_offsets[role], 6)
    return source


def load_sync_offsets(config: dict[str, Any]) -> tuple[dict[str, float], Path]:
    sync_path = Path(text_value(config, "render", "syncOffsetsPath", default=str(DEFAULT_SYNC)))
    payload = load_json(sync_path)
    offsets: dict[str, float] = {}
    raw_offsets = payload.get("offsets") if isinstance(payload.get("offsets"), dict) else {}
    for role, item in raw_offsets.items():
        if isinstance(item, dict) and item.get("offsetSeconds") is not None:
            offsets[str(role)] = as_float(item.get("offsetSeconds"), 0.0)
    return offsets, sync_path


def add_configured_source(
    sources: list[dict[str, Any]],
    by_role: dict[str, str],
    by_path: dict[str, str],
    used_ids: set[str],
    *,
    kind: str,
    role: str,
    path: Path | None,
    sync_offset: float = 0.0,
) -> str | None:
    if not path:
        return None
    key = str(path.resolve()).casefold() if path.exists() else str(path).casefold()
    if key in by_path:
        by_role.setdefault(role, by_path[key])
        return by_path[key]
    source_id = safe_id("src", role or path.stem, used_ids)
    source = {"id": source_id, "kind": kind, "role": role, "path": str(path)}
    if sync_offset:
        source["syncOffset"] = round(sync_offset, 6)
    sources.append(source)
    by_path[key] = source_id
    by_role.setdefault(role, source_id)
    return source_id


def find_or_add_source(sources: list[dict[str, Any]], *, kind: str, role: str, path: Path) -> str | None:
    if not path.exists():
        return None
    path_key = str(path.resolve()).casefold()
    for source in sources:
        source_path = Path(str(source.get("path") or ""))
        try:
            source_key = str(source_path.resolve()).casefold()
        except OSError:
            source_key = str(source_path).casefold()
        if source_key == path_key:
            return str(source.get("id") or "")
    used = {str(source.get("id") or "") for source in sources}
    source_id = safe_id("src", role or path.stem, used)
    sources.append({"id": source_id, "kind": kind, "role": role, "path": str(path)})
    return source_id


def collect_sources(config: dict[str, Any], sync_offsets: dict[str, float]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    sources: list[dict[str, Any]] = []
    by_role: dict[str, str] = {}
    by_path: dict[str, str] = {}
    used_ids: set[str] = set()
    for item in media_files(config):
        role = str(item.get("role") or "")
        kind = str(item.get("kind") or "")
        path_text = str(item.get("path") or "")
        if not path_text or role == "ignore" or kind not in {"video", "audio", "image", "subtitle"}:
            continue
        path = resolve_path(path_text)
        key = str(path.resolve()).casefold() if path.exists() else str(path).casefold()
        if key in by_path:
            by_role.setdefault(role, by_path[key])
            continue
        source_id = safe_id("src", role or str(item.get("id") or path.stem), used_ids)
        sources.append(source_from_media_item({**item, "path": str(path)}, source_id, sync_offsets))
        by_path[key] = source_id
        by_role.setdefault(role, source_id)

    fallback_assets = [
        ("video", "master", nested(config, "assets", "masterVideo", default="")),
        ("video", "camera2", nested(config, "assets", "rightCloseVideo", default="")),
        ("video", "camera3", nested(config, "assets", "leftCloseVideo", default="")),
        ("audio", "external", nested(config, "assets", "externalAudio", default="")),
        ("image", "logo", nested(config, "assets", "logo", default="")),
    ]
    for kind, role, path_text in fallback_assets:
        if path_text:
            add_configured_source(
                sources,
                by_role,
                by_path,
                used_ids,
                kind=kind,
                role=role,
                path=resolve_path(path_text),
                sync_offset=sync_offsets.get(role, 0.0),
            )

    subtitle = selected_subtitle_path(config, extensions=(".srt", ".ass", ".vtt"))
    if subtitle:
        add_configured_source(sources, by_role, by_path, used_ids, kind="subtitle", role="subtitle", path=subtitle)
    return sources, by_role


def source_by_id(sources: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(source["id"]): source for source in sources}


def source_duration(source: dict[str, Any] | None) -> float:
    return as_float(source.get("duration"), 0.0) if source else 0.0


def render_start_duration(config: dict[str, Any], sources: list[dict[str, Any]], by_role: dict[str, str]) -> tuple[float, float]:
    start = max(0.0, as_float(nested(config, "render", "previewStart", default=0.0), 0.0))
    requested = max(0.1, as_float(nested(config, "render", "previewDuration", default=60.0), 60.0))
    role_sources = source_by_id(sources)
    master_duration = source_duration(role_sources.get(by_role.get("master", "")))
    if text_value(config, "render", "rangeMode", default="range") == "full" and master_duration > 0:
        return 0.0, max(0.1, master_duration)
    if master_duration > 0 and start < master_duration:
        requested = min(requested, max(0.1, master_duration - start))
    return start, requested


def render_preview_range(config: dict[str, Any], timeline_duration: float) -> tuple[float, float]:
    requested = max(0.1, as_float(nested(config, "render", "previewDuration", default=60.0), 60.0))
    if timeline_duration <= requested + 0.001:
        return 0.0, round(timeline_duration, 6)
    if text_value(config, "render", "rangeMode", default="range") == "full":
        start = max(0.0, as_float(nested(config, "render", "previewStart", default=0.0), 0.0))
        start = min(start, max(0.0, timeline_duration - requested))
    else:
        start = 0.0
    return round(start, 6), round(min(timeline_duration, start + requested), 6)


def load_plan_rows(config: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    configured_plan = nested(config, "render", "cameraPlan", default=[])
    if isinstance(configured_plan, list) and configured_plan:
        return [item for item in configured_plan if isinstance(item, dict)], "render.cameraPlan"

    configured_path = text_value(config, "render", "cameraPlanPath")
    candidate_paths: list[tuple[Path, str]] = []
    if configured_path:
        candidate_paths.append((resolve_path(configured_path), "render.cameraPlanPath"))
    if text_value(config, "render", "multicamMode", default="master-first") == "manual-plan":
        candidate_paths.append((DEFAULT_MANUAL_CAMERA_PLAN, str(DEFAULT_MANUAL_CAMERA_PLAN)))
    candidate_paths.append((DEFAULT_CAMERA_PLAN, str(DEFAULT_CAMERA_PLAN)))

    for path, source in candidate_paths:
        payload = load_json(path)
        rows = payload.get("segments") if isinstance(payload.get("segments"), list) else payload.get("cameraPlan")
        if isinstance(rows, list) and rows:
            return [item for item in rows if isinstance(item, dict)], source
    return [], "generated-master-first"


def simple_master_first_plan(duration: float, roles: list[str]) -> list[dict[str, Any]]:
    if not roles:
        return []
    master = "master" if "master" in roles else roles[0]
    closeups = [role for role in roles if role != master]
    if not closeups:
        return [{"role": master, "start": 0.0, "end": duration}]
    rows = [{"role": master, "start": 0.0, "end": min(8.0, duration)}]
    cursor = 8.0
    index = 0
    while cursor < duration:
        end = min(duration, cursor + 12.0)
        rows.append({"role": closeups[index % len(closeups)], "start": cursor, "end": end})
        cursor = end
        index += 1
    return rows


def source_in_out(
    role: str,
    segment_start: float,
    segment_end: float,
    render_start: float,
    sync_offsets: dict[str, float],
) -> tuple[float, float]:
    offset = sync_offsets.get(role, 0.0)
    return render_start + segment_start + offset, render_start + segment_end + offset


def role_covers_segment(
    role: str,
    segment_start: float,
    segment_end: float,
    render_start: float,
    sync_offsets: dict[str, float],
    sources: dict[str, dict[str, Any]],
    by_role: dict[str, str],
) -> bool:
    source = sources.get(by_role.get(role, ""))
    if source is None:
        return False
    duration = source_duration(source)
    if duration <= 0:
        return True
    source_in, source_out = source_in_out(role, segment_start, segment_end, render_start, sync_offsets)
    return source_in >= -0.001 and source_out <= duration + 0.001


def normalize_plan(
    rows: list[dict[str, Any]],
    duration: float,
    roles: list[str],
    render_start: float,
    sync_offsets: dict[str, float],
    sources_by_id: dict[str, dict[str, Any]],
    by_role: dict[str, str],
) -> list[dict[str, Any]]:
    if not rows:
        rows = simple_master_first_plan(duration, roles)
    fallback_role = "master" if "master" in roles else (roles[0] if roles else "")
    normalized: list[dict[str, Any]] = []
    cursor = 0.0
    for row in sorted(rows, key=lambda item: (as_float(item.get("start")), as_float(item.get("end")))):
        role = str(row.get("role") or row.get("camera") or fallback_role)
        start = max(0.0, min(duration, as_float(row.get("start"), 0.0)))
        end = max(0.0, min(duration, as_float(row.get("end"), duration)))
        if end <= start + 0.001:
            continue
        if start > cursor + 0.001 and fallback_role:
            normalized.append({"role": fallback_role, "start": cursor, "end": start, "reason": "filled gap"})
        start = max(start, cursor)
        if role not in by_role or not role_covers_segment(role, start, end, render_start, sync_offsets, sources_by_id, by_role):
            role = fallback_role
        if not role:
            continue
        normalized.append({"role": role, "start": start, "end": end, "reason": str(row.get("reason") or "camera plan")})
        cursor = end
    if cursor < duration - 0.001 and fallback_role:
        normalized.append({"role": fallback_role, "start": cursor, "end": duration, "reason": "filled tail"})

    merged: list[dict[str, Any]] = []
    for row in normalized:
        if merged and merged[-1]["role"] == row["role"] and abs(float(merged[-1]["end"]) - float(row["start"])) <= 0.001:
            merged[-1]["end"] = row["end"]
            continue
        merged.append(row)
    return merged


def report_ref(kind: str, path: Path) -> dict[str, Any]:
    text = str(path)
    return {"kind": kind, "path": "" if text == "." else text, "exists": bool(text and text != "." and path.exists())}


def safe_ffmpeg_filter(value: Any) -> str:
    text = str(value or "").strip()
    if not text or any(char in text for char in "\r\n;[]"):
        return ""
    return text


def load_color_filter_map(path: Path) -> tuple[dict[str, str], dict[str, str], str]:
    payload = load_json(path)
    role_filters: dict[str, str] = {}
    manual_filters: dict[str, str] = {}
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    for item in items:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "")
        filter_text = safe_ffmpeg_filter(item.get("filter"))
        if role and filter_text:
            role_filters[role] = filter_text
    extras = payload.get("manualExtraFilters") if isinstance(payload.get("manualExtraFilters"), list) else []
    for item in extras:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "")
        filter_text = safe_ffmpeg_filter(item.get("filter"))
        if role and filter_text:
            manual_filters[role] = filter_text
    output_look = safe_ffmpeg_filter(payload.get("outputLookFilter"))
    return role_filters, manual_filters, output_look


def load_face_center_segments(config: dict[str, Any]) -> tuple[list[dict[str, Any]], Path, str]:
    enabled = bool_value(config, "render", "faceCenterCrop", default=False)
    configured_path = text_value(config, "render", "faceCenterCropPlanPath", default="")
    plan_path = resolve_path(configured_path) if configured_path else DEFAULT_FACE_CENTER_PLAN
    if not enabled:
        return [], plan_path, "disabled"
    payload = load_json(plan_path)
    segments = payload.get("segments") if isinstance(payload.get("segments"), list) else []
    return [segment for segment in segments if isinstance(segment, dict)], plan_path, "loaded" if segments else "missing-or-empty"


def face_center_subject_screen_x(config: dict[str, Any], role: str) -> float:
    by_role = nested(config, "render", "faceCenterSubjectXByRole", default={})
    if isinstance(by_role, dict) and by_role.get(role) not in {None, ""}:
        return clamp(as_float(by_role.get(role), 0.5), 0.35, 0.65)
    return clamp(as_float(nested(config, "render", "faceCenterSubjectX", default=0.5), 0.5), 0.35, 0.65)


def adjusted_face_center_crop_x(center_x: float, zoom: float, subject_screen_x: float) -> float:
    if zoom <= 1.0001:
        return clamp(center_x, 0.0, 1.0)
    return clamp(center_x - ((subject_screen_x - 0.5) / zoom), 0.0, 1.0)


def face_center_segment_for_clip(
    segments: list[dict[str, Any]],
    role: str,
    start: float,
    end: float,
) -> dict[str, Any] | None:
    midpoint = (start + end) / 2
    best: dict[str, Any] | None = None
    best_overlap = 0.0
    for segment in segments:
        if str(segment.get("role") or "") != role:
            continue
        try:
            segment_start = float(segment.get("start", 0.0))
            segment_end = float(segment.get("end", segment_start))
            center_x = float(segment.get("centerX", segment.get("center_x")))
            center_y = float(segment.get("centerY", segment.get("center_y")))
        except (TypeError, ValueError):
            continue
        if not (0.0 <= center_x <= 1.0 and 0.0 <= center_y <= 1.0):
            continue
        if segment_start <= midpoint < segment_end:
            return segment
        overlap = max(0.0, min(end, segment_end) - max(start, segment_start))
        if overlap > best_overlap:
            best = segment
            best_overlap = overlap
    return best if best_overlap > 0.0 else None


def canonical_path_key(path: Path) -> str:
    try:
        return str(path.resolve()).casefold()
    except OSError:
        return str(path).casefold()


def plan_match_keys(path: Path) -> set[str]:
    keys = {canonical_path_key(path), path.name.casefold(), path.stem.casefold()}
    for suffix in ("_person_edit_plan", "_person_bboxes"):
        stem = path.stem.casefold()
        if stem.endswith(suffix):
            keys.add(stem[: -len(suffix)])
    return keys


def person_plan_keys(plan: dict[str, Any], plan_path: Path) -> set[str]:
    keys = plan_match_keys(plan_path)
    for key in ("video_path", "video"):
        value = str(plan.get(key) or "")
        if not value:
            continue
        candidate = resolve_path(value)
        keys.update(plan_match_keys(candidate))
    return keys


def load_person_edit_plans(
    config: dict[str, Any],
    sources_by_id: dict[str, dict[str, Any]],
    by_role: dict[str, str],
) -> tuple[dict[str, dict[str, Any]], Path, str]:
    if not bool_value(config, "render", "usePersonEditPlans", default=True):
        return {}, DEFAULT_PERSON_EDIT_PLANS, "disabled"
    configured_dir = text_value(config, "analysis", "personEditPlansDir", default="")
    plan_dir = resolve_path(configured_dir) if configured_dir else DEFAULT_PERSON_EDIT_PLANS
    if not plan_dir.exists():
        return {}, plan_dir, "missing"
    camera_keys: dict[str, set[str]] = {}
    for role, source_id in by_role.items():
        if role != "master" and not role.startswith("camera"):
            continue
        source = sources_by_id.get(source_id)
        if not source:
            continue
        camera_keys[role] = plan_match_keys(resolve_path(source.get("path")))

    plans: dict[str, dict[str, Any]] = {}
    for plan_path in sorted(plan_dir.glob("*_person_edit_plan.json")):
        plan = load_json(plan_path)
        if not plan:
            continue
        keys = person_plan_keys(plan, plan_path)
        for role, role_keys in camera_keys.items():
            if role in plans or keys.isdisjoint(role_keys):
                continue
            plans[role] = {**plan, "_planPath": str(plan_path)}
    return plans, plan_dir, "loaded" if plans else "empty"


def person_plan_segment_at(plan: dict[str, Any], source_time: float) -> dict[str, Any] | None:
    segments = plan.get("segments") if isinstance(plan.get("segments"), list) else []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        start = as_float(segment.get("start"), -1.0)
        end = as_float(segment.get("end"), start)
        if start <= source_time < end:
            return segment
    return None


def ratio_list(value: Any, length: int) -> list[float] | None:
    if not isinstance(value, list) or len(value) < length:
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
    return clamp((raw_start + raw_end) / 2, low, high)


def person_plan_crop(
    plan: dict[str, Any],
    role: str,
    source_time: float,
) -> dict[str, Any] | None:
    segment = person_plan_segment_at(plan, source_time)
    if segment is None:
        return None
    crop_target = segment.get("crop_target") if isinstance(segment.get("crop_target"), dict) else {}
    if not crop_target:
        return None
    try:
        focus_x = float(crop_target.get("focus_x", crop_target.get("x")))
        focus_y = float(crop_target.get("focus_y", crop_target.get("y")))
        desired_x = float(crop_target.get("desired_subject_x_ratio", segment.get("desired_subject_x_ratio", 0.5)))
        desired_y = float(crop_target.get("desired_subject_y_ratio", segment.get("desired_subject_y_ratio", 0.382)))
    except (TypeError, ValueError):
        return None
    area_ratio = as_float(segment.get("avg_area_ratio"), 0.0)
    visible_ratio = visible_ratio_for_area(area_ratio)
    center_x = crop_window_center_for_subject(clamp(focus_x, 0.2, 0.8), clamp(desired_x, 0.35, 0.65), visible_ratio)
    center_y = crop_window_center_for_subject(clamp(focus_y, 0.25, 0.75), clamp(desired_y, 0.30, 0.52), visible_ratio)
    protect_bbox = ratio_list(
        crop_target.get("protect_bbox_ratio")
        or segment.get("avg_face_protect_bbox_ratio")
        or crop_target.get("face_bbox_ratio")
        or segment.get("avg_face_bbox_ratio"),
        4,
    )
    if protect_bbox:
        left, top, right, bottom = [clamp(value, 0.0, 1.0) for value in protect_bbox]
        center_x = constrain_window_center_for_box(center_x, visible_ratio, left, right, 0.07, 0.07, 0.2, 0.8)
        center_y = constrain_window_center_for_box(center_y, visible_ratio, top, bottom, 0.075, 0.14, 0.25, 0.75)
    return {
        "type": "personEditPlanCrop",
        "role": role,
        "sourceTime": round(source_time, 3),
        "planPath": str(plan.get("_planPath") or ""),
        "planStart": segment.get("start"),
        "planEnd": segment.get("end"),
        "centerX": round(center_x, 6),
        "centerY": round(center_y, 6),
        "scale": round(1.0 / max(0.001, visible_ratio), 6),
        "cropStrategy": segment.get("crop_strategy"),
        "position": segment.get("position"),
        "shotSize": segment.get("shot_size"),
        "faceDirection": segment.get("face_direction"),
        "focusSource": segment.get("avg_focus_source"),
        "cropTarget": crop_target,
    }


def build_video_clips(
    plan: list[dict[str, Any]],
    *,
    config: dict[str, Any],
    by_role: dict[str, str],
    render_start: float,
    sync_offsets: dict[str, float],
    global_zoom: float,
    color_report: Path,
    color_filters: dict[str, str],
    manual_color_filters: dict[str, str],
    output_look_filter: str,
    face_center_segments: list[dict[str, Any]],
    face_center_plan_path: Path,
    face_center_status: str,
    person_plans: dict[str, dict[str, Any]],
    person_plans_dir: Path,
    person_plans_status: str,
) -> list[dict[str, Any]]:
    clips: list[dict[str, Any]] = []
    for index, row in enumerate(plan, start=1):
        role = str(row["role"])
        source_id = by_role[role]
        start = round(float(row["start"]), 6)
        end = round(float(row["end"]), 6)
        source_in, source_out = source_in_out(role, start, end, render_start, sync_offsets)
        effects = []
        crop_center_x = 0.5
        crop_center_y = 0.5
        clip_scale_value = global_zoom
        source_midpoint = (source_in + source_out) / 2
        person_crop = person_plan_crop(person_plans[role], role, source_midpoint) if role in person_plans else None
        face_segment = None if person_crop else face_center_segment_for_clip(face_center_segments, role, start, end)
        crop_metadata: dict[str, Any] = {}
        if person_crop:
            crop_center_x = as_float(person_crop.get("centerX"), 0.5)
            crop_center_y = as_float(person_crop.get("centerY"), 0.5)
            clip_scale_value = max(global_zoom, as_float(person_crop.get("scale"), 1.0))
            crop_metadata = {
                **person_crop,
                "planDirectory": str(person_plans_dir),
                "status": person_plans_status,
            }
        elif face_segment:
            detected_center_x = as_float(face_segment.get("centerX", face_segment.get("center_x")), 0.5)
            subject_screen_x = face_center_subject_screen_x(config, role)
            crop_center_x = adjusted_face_center_crop_x(detected_center_x, global_zoom, subject_screen_x)
            if text_value(config, "render", "faceCenterCropAxis", default="x").strip().lower() in {"xy", "both", "all"}:
                crop_center_y = clamp(as_float(face_segment.get("centerY", face_segment.get("center_y")), 0.5), 0.0, 1.0)
            crop_metadata = {
                "type": "faceCenterCrop",
                "planPath": str(face_center_plan_path),
                "status": face_center_status,
                "source": face_segment.get("source"),
                "detections": face_segment.get("detections"),
                "detectedCenterX": round(detected_center_x, 6),
                "centerX": round(crop_center_x, 6),
                "centerY": round(crop_center_y, 6),
                "subjectScreenX": round(subject_screen_x, 6),
            }
        if abs(clip_scale_value - 1.0) > 0.0001:
            params: dict[str, Any] = {
                "scale": round(clip_scale_value, 6),
                "crop": {"centerX": round(crop_center_x, 6), "centerY": round(crop_center_y, 6)},
            }
            if crop_metadata:
                params["source"] = crop_metadata
            effects.append({"type": "scaleCrop", "params": params})
        if color_report.exists():
            params: dict[str, Any] = {"reportPath": str(color_report), "role": role}
            if color_filters.get(role):
                params["filter"] = color_filters[role]
            if manual_color_filters.get(role):
                params["manualFilter"] = manual_color_filters[role]
            if output_look_filter:
                params["outputLookFilter"] = output_look_filter
            effects.append({"type": "colorCorrection", "params": params})
        clips.append(
            {
                "id": f"clip_video_{index:04d}",
                "trackId": "video.main",
                "kind": "video",
                "sourceId": source_id,
                "timelineStart": start,
                "timelineEnd": end,
                "sourceIn": round(max(0.0, source_in), 6),
                "sourceOut": round(max(0.0, source_out), 6),
                "fit": {"mode": "cover", "width": 1920, "height": 1080, "scale": round(clip_scale_value, 6)},
                "effects": effects,
                "metadata": {
                    "role": role,
                    "decisionSource": row.get("reason", "camera plan"),
                    "crop": crop_metadata,
                },
            }
        )
    return clips


def selected_audio_role(config: dict[str, Any], by_role: dict[str, str]) -> str:
    audio_source = text_value(config, "render", "audioSource", default="external-if-selected")
    if audio_source == "external-if-selected" and "external" in by_role:
        return "external"
    if audio_source == "rightCloseVideo" and "camera2" in by_role:
        return "camera2"
    if audio_source == "leftCloseVideo" and "camera3" in by_role:
        return "camera3"
    return "master" if "master" in by_role else next(iter(by_role.keys()), "")


def subtitle_overlay_manifest_path(mode: str) -> Path | None:
    if mode == "full":
        html_layout = OUTPUT_OVERLAYS / "full_transcript_png_overlays" / "layout.json"
        if html_layout.exists():
            return html_layout
        return OUTPUT_OVERLAYS / "full_transcript_png_overlays" / "manifest.json"
    if mode == "punchline":
        return OUTPUT_OVERLAYS / "punchline_png_overlays" / "manifest.json"
    return None


def subtitle_manifest_format(path: Path | None) -> str:
    if path is None:
        return ""
    if path.name == "layout.json":
        return "html-subtitle-layout"
    payload = load_json(path)
    if payload.get("schemaVersion") == "video-edit-subtitle-layout/v1":
        return "html-subtitle-layout"
    return "png-overlay-manifest"


def build_extra_clips(
    config: dict[str, Any],
    sources: list[dict[str, Any]],
    by_role: dict[str, str],
    *,
    render_start: float,
    duration: float,
    sync_offsets: dict[str, float],
    output_path: Path,
) -> list[dict[str, Any]]:
    clips: list[dict[str, Any]] = []
    audio_role = selected_audio_role(config, by_role)
    if audio_role and audio_role in by_role:
        source_in, source_out = source_in_out(audio_role, 0.0, duration, render_start, sync_offsets)
        audio_effects = []
        audio_denoise = bool_value(config, "render", "audioDenoise", default=True)
        audio_mastering = bool_value(config, "render", "audioMastering", default=False)
        if audio_denoise or audio_mastering:
            audio_effects.append(
                {
                    "type": "audioCleanup",
                    "params": {
                        "denoise": audio_denoise,
                        "strength": as_int(nested(config, "render", "audioDenoiseStrength", default=10), 10),
                        "mastering": audio_mastering,
                    },
                }
            )
        clips.append(
            {
                "id": "clip_audio_main",
                "trackId": "audio.main",
                "kind": "audio",
                "sourceId": by_role[audio_role],
                "timelineStart": 0.0,
                "timelineEnd": round(duration, 6),
                "sourceIn": round(max(0.0, source_in), 6),
                "sourceOut": round(max(0.0, source_out), 6),
                "audioSyncOffset": round(sync_offsets.get(audio_role, 0.0), 6),
                "effects": audio_effects,
                "metadata": {"role": audio_role, "selection": text_value(config, "render", "audioSource", default="external-if-selected")},
            }
        )

    if "logo" in by_role:
        clips.append(
            {
                "id": "clip_overlay_logo",
                "trackId": "overlay.graphics",
                "kind": "image",
                "sourceId": by_role["logo"],
                "timelineStart": 0.0,
                "timelineEnd": round(duration, 6),
                "position": {
                    "x": "W-w-40",
                    "y": 40,
                    "height": as_float(nested(config, "style", "logoHeight", default=48), 48.0),
                    "anchor": "top-right",
                },
                "effects": [],
                "metadata": {"role": "logo"},
            }
        )

    if "subtitle" in by_role:
        subtitle_mode = text_value(config, "render", "subtitleMode", default="full")
        overlay_manifest = subtitle_overlay_manifest_path(subtitle_mode)
        overlay_format = subtitle_manifest_format(overlay_manifest)
        overlay_manifest_source_id = None
        precomposed_source_id = None
        if overlay_manifest and overlay_manifest.exists():
            overlay_manifest_source_id = find_or_add_source(
                sources,
                kind="data",
                role=f"subtitle-{subtitle_mode}-{'layout' if overlay_format == 'html-subtitle-layout' else 'manifest'}",
                path=overlay_manifest,
            )
            precomposed = OUTPUT_OVERLAYS / "precomposed" / f"{output_path.stem}_full_subtitles.mov"
            if subtitle_mode == "full" and overlay_format != "html-subtitle-layout" and precomposed.exists():
                precomposed_source_id = find_or_add_source(
                    sources,
                    kind="video",
                    role="subtitle-precomposed-overlay",
                    path=precomposed,
                )
        precompose_target = OUTPUT_OVERLAYS / "precomposed" / f"{output_path.stem}_full_subtitles.mov"
        if overlay_manifest_source_id and overlay_format == "html-subtitle-layout":
            render_method = "html-subtitle-overlay"
        elif overlay_manifest_source_id and subtitle_mode == "full":
            render_method = "precompose-png-overlay"
        else:
            render_method = "ffmpeg-subtitles-filter"
        metadata: dict[str, Any] = {"timebase": text_value(config, "render", "subtitleTimebase", default="auto")}
        if overlay_manifest:
            metadata["overlayManifestPath"] = str(overlay_manifest)
            metadata["overlayManifestFormat"] = overlay_format
        if overlay_manifest_source_id:
            metadata["overlayManifestSourceId"] = overlay_manifest_source_id
            if overlay_format != "html-subtitle-layout":
                metadata["precomposedOverlayTargetPath"] = str(precompose_target)
                metadata["precomposeBottomMargin"] = 16
                metadata["precomposeFps"] = text_value(config, "render", "precomposeOverlayFps", default="30000/1001")
        if precomposed_source_id:
            metadata["precomposedOverlaySourceId"] = precomposed_source_id
            metadata["precomposedOverlayPath"] = str(precompose_target)
        clips.append(
            {
                "id": "clip_subtitles_main",
                "trackId": "subtitle.main",
                "kind": "subtitle",
                "sourceId": by_role["subtitle"],
                "timelineStart": 0.0,
                "timelineEnd": round(duration, 6),
                "style": {
                    "mode": text_value(config, "render", "subtitleMode", default="full"),
                    "fontSize": as_int(nested(config, "style", "subtitleSize", default=64), 64),
                    "highlightColor": text_value(config, "style", "highlightColor", default="#8b5cf6"),
                    "boxOpacity": as_float(nested(config, "style", "boxOpacity", default=65), 65.0),
                    "renderMethod": render_method,
                },
                "effects": [],
                "metadata": metadata,
            }
        )

    if bool_value(config, "music", "enabled", default=False):
        music_path = Path(text_value(config, "music", "outputPath", default=str(OUTPUT_AUDIO / "music_bed.wav")))
        source_id = None
        if music_path.exists():
            source_id = next((source["id"] for source in sources if source.get("path") == str(music_path)), None)
            if source_id is None:
                source_id = f"src_music_{len(sources) + 1}"
                sources.append({"id": source_id, "kind": "audio", "role": "music", "path": str(music_path)})
        clip: dict[str, Any] = {
            "id": "clip_music_bed",
            "trackId": "music.bed",
            "kind": "music" if source_id else "generated",
            "timelineStart": 0.0,
            "timelineEnd": round(duration, 6),
            "effects": [{"type": "gain", "params": {"levelPercent": as_float(nested(config, "music", "volume", default=14), 14.0)}}],
            "metadata": {
                "scope": text_value(config, "music", "scope", default="full"),
                "rangeSource": text_value(config, "music", "rangeSource", default="auto"),
                "generator": "generate_music_bed.py" if not source_id else "",
            },
        }
        if source_id:
            clip["sourceId"] = source_id
            clip["sourceIn"] = 0.0
            clip["sourceOut"] = round(duration, 6)
        clips.append(clip)

    return clips


def build_transitions(video_clips: list[dict[str, Any]]) -> list[dict[str, Any]]:
    transitions: list[dict[str, Any]] = []
    for index, (left, right) in enumerate(zip(video_clips, video_clips[1:]), start=1):
        transitions.append(
            {
                "id": f"transition_{index:04d}",
                "type": "cut",
                "at": left["timelineEnd"],
                "fromClipId": left["id"],
                "toClipId": right["id"],
                "duration": 0.0,
            }
        )
    return transitions


def build_timeline(config: dict[str, Any]) -> tuple[dict[str, Any], Path]:
    sync_offsets, sync_path = load_sync_offsets(config)
    sources, by_role = collect_sources(config, sync_offsets)
    sources_by_id = source_by_id(sources)
    render_start, duration = render_start_duration(config, sources, by_role)
    roles = sorted([role for role in by_role if role == "master" or role.startswith("camera")], key=camera_role_order)
    raw_plan, plan_source = load_plan_rows(config)
    plan = normalize_plan(raw_plan, duration, roles, render_start, sync_offsets, sources_by_id, by_role)
    color_report = DEFAULT_COLOR_MATCH
    color_filters, manual_color_filters, output_look_filter = load_color_filter_map(color_report)
    global_zoom = max(1.0, as_float(nested(config, "render", "globalVideoZoom", default=1.0), 1.0))
    face_center_segments, face_center_plan_path, face_center_status = load_face_center_segments(config)
    person_plans, person_plans_dir, person_plans_status = load_person_edit_plans(config, sources_by_id, by_role)
    output_path = Path(text_value(config, "render", "outputPath", default=str(OUTPUT_VIDEOS / "app_multicam_output.mp4")))
    video_clips = build_video_clips(
        plan,
        config=config,
        by_role=by_role,
        render_start=render_start,
        sync_offsets=sync_offsets,
        global_zoom=global_zoom,
        color_report=color_report,
        color_filters=color_filters,
        manual_color_filters=manual_color_filters,
        output_look_filter=output_look_filter,
        face_center_segments=face_center_segments,
        face_center_plan_path=face_center_plan_path,
        face_center_status=face_center_status,
        person_plans=person_plans,
        person_plans_dir=person_plans_dir,
        person_plans_status=person_plans_status,
    )
    clips = video_clips + build_extra_clips(
        config,
        sources,
        by_role,
        render_start=render_start,
        duration=duration,
        sync_offsets=sync_offsets,
        output_path=output_path,
    )
    timeline_path = Path(text_value(config, "render", "timelinePath", default=str(DEFAULT_TIMELINE)))
    render_fps = output_fps(config)
    preview_start, preview_end = render_preview_range(config, duration)
    project = nested(config, "project", default={})
    project_id = str(project.get("id") or config.get("projectId") or os.environ.get("VIDEO_EDIT_PROJECT", ""))
    project_name = str(project.get("name") or project_id)
    project_root = str(project.get("root") or (OUTPUT.parent if OUTPUT.name == "output" else ""))
    reports = [
        report_ref("media-manifest", Path(str(nested(config, "assets", "mediaManifestPath", default="")))),
        report_ref("sync-offsets", sync_path),
        report_ref("transcript-manifest", DEFAULT_TRANSCRIPT_MANIFEST),
        report_ref("camera-plan", DEFAULT_CAMERA_PLAN),
        report_ref("manual-camera-plan", DEFAULT_MANUAL_CAMERA_PLAN),
        report_ref("source-coverage", DEFAULT_SOURCE_COVERAGE),
        report_ref("external-audio-cut-sync", DEFAULT_EXTERNAL_SYNC),
        report_ref("natural-dialogue-cuts", DEFAULT_NATURAL_CUT),
        report_ref("camera-color-match", DEFAULT_COLOR_MATCH),
        report_ref("person-edit-plans", person_plans_dir),
        report_ref("person-crop", DEFAULT_PERSON_CROP),
        report_ref("face-center-crop", DEFAULT_FACE_CROP),
        report_ref("face-center-plan", face_center_plan_path),
    ]
    timeline = {
        "schemaVersion": SCHEMA_VERSION,
        "id": safe_id("timeline", project_id or project_name or "current", set()),
        "createdAt": now_iso(),
        "project": {
            "id": project_id,
            "name": project_name,
            "root": project_root,
            "sourceRoot": str(project.get("sourceRoot") or SOURCE),
            "outputRoot": str(project.get("outputRoot") or OUTPUT),
        },
        "timebase": {"unit": "seconds", "fps": render_fps},
        "duration": round(duration, 6),
        "sources": sources,
        "tracks": [
            {"id": "video.main", "kind": "video", "label": "Main video", "allowOverlap": False},
            {"id": "audio.main", "kind": "audio", "label": "Main dialogue audio", "allowOverlap": False},
            {"id": "overlay.graphics", "kind": "overlay", "label": "Graphic overlays", "allowOverlap": True},
            {"id": "subtitle.main", "kind": "subtitle", "label": "Subtitles", "allowOverlap": True},
            {"id": "music.bed", "kind": "music", "label": "Background music", "allowOverlap": True},
        ],
        "clips": clips,
        "transitions": build_transitions(video_clips),
        "render": {
            "targets": [
                {
                    "id": "final",
                    "path": str(output_path),
                    "format": output_path.suffix.lower().lstrip(".") or "mp4",
                    "width": 1920,
                    "height": 1080,
                    "fps": render_fps,
                    "profile": text_value(config, "render", "renderProfile", default="final"),
                    "videoCodec": text_value(config, "render", "videoEncoder", default="libx264"),
                    "audioCodec": "aac",
                }
            ],
            "preview": {
                "enabled": text_value(config, "render", "renderProfile", default="final") == "preview" or preview_end < round(duration, 6),
                "rangeStart": preview_start,
                "rangeEnd": preview_end,
                "proxy": text_value(config, "render", "renderProfile", default="final") == "preview",
            },
        },
        "analysis": {
            "mediaManifestPath": str(nested(config, "assets", "mediaManifestPath", default="")),
            "reports": reports,
        },
        "audit": {
            "createdBy": "scripts/build_edit_timeline.py",
            "inputs": [
                report_ref("schema", DEFAULT_SCHEMA),
                report_ref("runtime-config", Path(str(os.environ.get("VIDEO_EDIT_APP_CONFIG", "")))),
                report_ref("camera-plan-source", resolve_path(plan_source) if plan_source not in {"render.cameraPlan", "generated-master-first"} else Path(plan_source)),
            ],
            "planning": {
                "cameraPlanSource": plan_source,
                "renderStart": round(render_start, 6),
                "syncOffsetSource": str(sync_path),
                "note": "Timeline stores edit intent only. Renderer adapters generate FFmpeg/Remotion/Blender commands.",
            },
        },
    }
    return timeline, timeline_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a renderer-agnostic edit timeline from the active project config.")
    parser.add_argument("--output", type=Path, default=None, help="Timeline output path. Defaults to render.timelinePath or output/timelines/current.timeline.json.")
    parser.add_argument("--validation-report", type=Path, default=DEFAULT_REPORT, help="Validation report path.")
    parser.add_argument("--skip-validation", action="store_true", help="Write the timeline without semantic validation.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_app_config()
    timeline, default_path = build_timeline(config)
    output_path = args.output or default_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")
    errors: list[str] = []
    warnings: list[str] = []
    if not args.skip_validation:
        errors, warnings = validate_timeline(timeline)
        write_report(args.validation_report, output_path, errors, warnings)
    summary = {
        "timeline": str(output_path),
        "validationReport": str(args.validation_report),
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "clipCount": len(timeline["clips"]),
        "sourceCount": len(timeline["sources"]),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
