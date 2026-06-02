from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

from video_edit_core.paths import CONFIG, OUTPUT, OUTPUT_REPORTS
from video_edit_core.app_config import load_app_config, nested


SCHEMA_VERSION = "video-edit-timeline/v1"
DEFAULT_TIMELINE = OUTPUT / "timelines" / "current.timeline.json"
DEFAULT_REPORT = OUTPUT_REPORTS / "timeline_validation.json"
DEFAULT_SCHEMA = CONFIG / "timeline.schema.json"
MAX_SYNC_OFFSET_SECONDS = 24 * 60 * 60
EPSILON = 0.001
TOP_LEVEL_KEYS = {
    "schemaVersion",
    "id",
    "createdAt",
    "project",
    "timebase",
    "duration",
    "sources",
    "tracks",
    "clips",
    "transitions",
    "render",
    "analysis",
    "audit",
}


def is_finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def as_float(value: Any, default: float = 0.0) -> float:
    if is_finite_number(value):
        return float(value)
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def stable_path(value: Any) -> Path:
    return Path(str(value or "")).expanduser()


def duplicate_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def load_timeline(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(f"Timeline file does not exist: {path}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"Timeline JSON is invalid: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError("Timeline root must be a JSON object.")
    return payload


def load_schema(path: Path = DEFAULT_SCHEMA) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(f"Timeline schema file does not exist: {path}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"Timeline schema JSON is invalid: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError("Timeline schema root must be a JSON object.")
    return payload


def configured_timeline_path(config: dict[str, Any] | None = None) -> Path:
    app_config = config if isinstance(config, dict) else load_app_config()
    configured = nested(app_config, "render", "timelinePath", default="")
    return Path(str(configured)) if configured else DEFAULT_TIMELINE


def schema_ref(schema: dict[str, Any], ref: str) -> dict[str, Any]:
    if not ref.startswith("#/"):
        raise ValueError(f"unsupported schema $ref: {ref}")
    node: Any = schema
    for part in ref[2:].split("/"):
        if not isinstance(node, dict) or part not in node:
            raise ValueError(f"schema $ref does not resolve: {ref}")
        node = node[part]
    if not isinstance(node, dict):
        raise ValueError(f"schema $ref does not resolve to an object: {ref}")
    return node


def schema_type_matches(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "number":
        return is_finite_number(value)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    return True


def validate_schema_node(value: Any, node: dict[str, Any], root_schema: dict[str, Any], path: str) -> list[str]:
    errors: list[str] = []
    if "$ref" in node:
        try:
            node = schema_ref(root_schema, str(node["$ref"]))
        except ValueError as error:
            return [str(error)]

    if "const" in node and value != node["const"]:
        return [f"{path} must equal {node['const']!r}."]
    if "enum" in node and value not in node["enum"]:
        return [f"{path} must be one of {node['enum']!r}."]

    expected_type = node.get("type")
    if isinstance(expected_type, list):
        if not any(schema_type_matches(value, item) for item in expected_type if isinstance(item, str)):
            errors.append(f"{path} must match one of these types: {expected_type}.")
            return errors
    elif isinstance(expected_type, str) and not schema_type_matches(value, expected_type):
        errors.append(f"{path} must be type {expected_type}.")
        return errors

    if isinstance(value, dict):
        required = node.get("required")
        if isinstance(required, list):
            for key in required:
                if isinstance(key, str) and key not in value:
                    errors.append(f"{path}.{key} is required.")
        properties = node.get("properties") if isinstance(node.get("properties"), dict) else {}
        if node.get("additionalProperties") is False:
            for key in sorted(set(value.keys()) - set(properties.keys())):
                errors.append(f"{path}.{key} is not allowed by the schema.")
        for key, child in properties.items():
            if key in value and isinstance(child, dict):
                errors.extend(validate_schema_node(value[key], child, root_schema, f"{path}.{key}"))

    if isinstance(value, list):
        items = node.get("items")
        if isinstance(items, dict):
            for index, item in enumerate(value):
                errors.extend(validate_schema_node(item, items, root_schema, f"{path}[{index}]"))

    if isinstance(value, str):
        min_length = node.get("minLength")
        if isinstance(min_length, int) and len(value) < min_length:
            errors.append(f"{path} must be at least {min_length} characters.")
        pattern = node.get("pattern")
        if isinstance(pattern, str) and re.fullmatch(pattern, value) is None:
            errors.append(f"{path} must match pattern {pattern!r}.")

    if is_finite_number(value):
        number = float(value)
        minimum = node.get("minimum")
        if is_finite_number(minimum) and number < float(minimum):
            errors.append(f"{path} must be >= {minimum}.")
        maximum = node.get("maximum")
        if is_finite_number(maximum) and number > float(maximum):
            errors.append(f"{path} must be <= {maximum}.")
        exclusive_minimum = node.get("exclusiveMinimum")
        if is_finite_number(exclusive_minimum) and number <= float(exclusive_minimum):
            errors.append(f"{path} must be > {exclusive_minimum}.")

    return errors


def validate_json_schema(timeline: dict[str, Any], schema: dict[str, Any] | None = None) -> list[str]:
    schema_payload = schema if schema is not None else load_schema()
    return validate_schema_node(timeline, schema_payload, schema_payload, "$")


def validate_timeline(timeline: dict[str, Any], schema: dict[str, Any] | None = None) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    errors.extend(validate_json_schema(timeline, schema))

    if timeline.get("schemaVersion") != SCHEMA_VERSION:
        errors.append(f"schemaVersion must be {SCHEMA_VERSION}.")
    for key in sorted(TOP_LEVEL_KEYS - set(timeline.keys())):
        errors.append(f"missing top-level field: {key}")
    for key in sorted(set(timeline.keys()) - TOP_LEVEL_KEYS):
        errors.append(f"unexpected top-level field: {key}")

    duration = timeline.get("duration")
    if not is_finite_number(duration) or float(duration) <= 0:
        errors.append("duration must be a positive finite number.")
        duration_seconds = 0.0
    else:
        duration_seconds = float(duration)

    sources = timeline.get("sources")
    if not isinstance(sources, list):
        errors.append("sources must be an array.")
        sources = []
    tracks = timeline.get("tracks")
    if not isinstance(tracks, list):
        errors.append("tracks must be an array.")
        tracks = []
    clips = timeline.get("clips")
    if not isinstance(clips, list):
        errors.append("clips must be an array.")
        clips = []

    source_ids = [str(item.get("id") or "") for item in sources if isinstance(item, dict)]
    for duplicate in duplicate_values([value for value in source_ids if value]):
        errors.append(f"source id is duplicated: {duplicate}")
    track_ids = [str(item.get("id") or "") for item in tracks if isinstance(item, dict)]
    for duplicate in duplicate_values([value for value in track_ids if value]):
        errors.append(f"track id is duplicated: {duplicate}")
    clip_ids = [str(item.get("id") or "") for item in clips if isinstance(item, dict)]
    for duplicate in duplicate_values([value for value in clip_ids if value]):
        errors.append(f"clip id is duplicated: {duplicate}")
    transitions = timeline.get("transitions")
    if not isinstance(transitions, list):
        errors.append("transitions must be an array.")
        transitions = []
    transition_ids = [str(item.get("id") or "") for item in transitions if isinstance(item, dict)]
    for duplicate in duplicate_values([value for value in transition_ids if value]):
        errors.append(f"transition id is duplicated: {duplicate}")

    source_by_id: dict[str, dict[str, Any]] = {}
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            errors.append(f"sources[{index}] must be an object.")
            continue
        source_id = str(source.get("id") or "")
        if not source_id:
            errors.append(f"sources[{index}].id is required.")
            continue
        source_by_id[source_id] = source
        path = stable_path(source.get("path"))
        if not str(path):
            errors.append(f"source {source_id} path is required.")
        elif not path.exists():
            errors.append(f"source {source_id} path does not exist: {path}")
        sync_offset = source.get("syncOffset")
        if sync_offset is not None:
            if not is_finite_number(sync_offset):
                errors.append(f"source {source_id} syncOffset must be numeric.")
            elif abs(float(sync_offset)) > MAX_SYNC_OFFSET_SECONDS:
                errors.append(f"source {source_id} syncOffset exceeds {MAX_SYNC_OFFSET_SECONDS} seconds.")

    track_by_id: dict[str, dict[str, Any]] = {}
    for index, track in enumerate(tracks):
        if not isinstance(track, dict):
            errors.append(f"tracks[{index}] must be an object.")
            continue
        track_id = str(track.get("id") or "")
        if not track_id:
            errors.append(f"tracks[{index}].id is required.")
            continue
        track_by_id[track_id] = track
        if not isinstance(track.get("allowOverlap"), bool):
            errors.append(f"track {track_id} allowOverlap must be boolean.")

    clips_by_track: dict[str, list[dict[str, Any]]] = {}
    for index, clip in enumerate(clips):
        if not isinstance(clip, dict):
            errors.append(f"clips[{index}] must be an object.")
            continue
        clip_id = str(clip.get("id") or f"clips[{index}]")
        track_id = str(clip.get("trackId") or "")
        if track_id not in track_by_id:
            errors.append(f"clip {clip_id} references missing track: {track_id}")
        else:
            clips_by_track.setdefault(track_id, []).append(clip)

        start = clip.get("timelineStart")
        end = clip.get("timelineEnd")
        if not is_finite_number(start) or not is_finite_number(end):
            errors.append(f"clip {clip_id} timelineStart/timelineEnd must be numeric.")
            continue
        start_seconds = float(start)
        end_seconds = float(end)
        if start_seconds < -EPSILON:
            errors.append(f"clip {clip_id} starts before timeline zero.")
        if end_seconds <= start_seconds + EPSILON:
            errors.append(f"clip {clip_id} timelineEnd must be greater than timelineStart.")
        if duration_seconds and end_seconds > duration_seconds + EPSILON:
            errors.append(f"clip {clip_id} ends after timeline duration.")

        sync_offset = clip.get("audioSyncOffset")
        if sync_offset is not None:
            if not is_finite_number(sync_offset):
                errors.append(f"clip {clip_id} audioSyncOffset must be numeric.")
            elif abs(float(sync_offset)) > MAX_SYNC_OFFSET_SECONDS:
                errors.append(f"clip {clip_id} audioSyncOffset exceeds {MAX_SYNC_OFFSET_SECONDS} seconds.")

        source_id = clip.get("sourceId")
        if source_id is None:
            if clip.get("kind") not in {"generated"}:
                errors.append(f"clip {clip_id} must reference a sourceId unless it is generated.")
            continue
        source_id = str(source_id)
        source = source_by_id.get(source_id)
        if source is None:
            errors.append(f"clip {clip_id} references missing source: {source_id}")
            continue
        source_kind = str(source.get("kind") or "")
        clip_kind = str(clip.get("kind") or "")
        if clip_kind == "video" and source_kind != "video":
            errors.append(f"clip {clip_id} is video but source {source_id} is {source_kind or 'unknown'}.")
        elif clip_kind in {"audio", "music"} and source_kind not in {"audio", "video"}:
            errors.append(f"clip {clip_id} is {clip_kind} but source {source_id} is {source_kind or 'unknown'}.")
        elif clip_kind == "image" and source_kind != "image":
            errors.append(f"clip {clip_id} is image but source {source_id} is {source_kind or 'unknown'}.")
        elif clip_kind == "subtitle" and source_kind != "subtitle":
            errors.append(f"clip {clip_id} is subtitle but source {source_id} is {source_kind or 'unknown'}.")
        if source_kind in {"video", "audio"} or clip_kind in {"video", "audio", "music"}:
            if not is_finite_number(clip.get("sourceIn")) or not is_finite_number(clip.get("sourceOut")):
                errors.append(f"clip {clip_id} sourceIn/sourceOut are required for timed media.")
                continue
            source_in = float(clip["sourceIn"])
            source_out = float(clip["sourceOut"])
            if source_out <= source_in + EPSILON:
                errors.append(f"clip {clip_id} sourceOut must be greater than sourceIn.")
            source_duration = source.get("duration")
            if is_finite_number(source_duration) and float(source_duration) > 0:
                if source_in < -EPSILON:
                    errors.append(f"clip {clip_id} sourceIn is before source start.")
                if source_out > float(source_duration) + EPSILON:
                    errors.append(f"clip {clip_id} sourceOut exceeds source duration.")

    for track_id, track_clips in clips_by_track.items():
        track = track_by_id[track_id]
        if track.get("allowOverlap") is True:
            continue
        sorted_clips = sorted(track_clips, key=lambda item: (as_float(item.get("timelineStart")), as_float(item.get("timelineEnd"))))
        previous: dict[str, Any] | None = None
        for clip in sorted_clips:
            if clip.get("allowOverlap") is True:
                continue
            if previous is not None and as_float(previous.get("timelineEnd")) > as_float(clip.get("timelineStart")) + EPSILON:
                errors.append(
                    "clips overlap on non-overlap track "
                    f"{track_id}: {previous.get('id')} and {clip.get('id')}"
                )
            previous = clip

    clip_by_id = {str(clip.get("id") or ""): clip for clip in clips if isinstance(clip, dict)}
    for index, transition in enumerate(transitions):
        if not isinstance(transition, dict):
            errors.append(f"transitions[{index}] must be an object.")
            continue
        transition_id = str(transition.get("id") or f"transitions[{index}]")
        at = transition.get("at")
        if not is_finite_number(at):
            errors.append(f"transition {transition_id} at must be numeric.")
        else:
            at_seconds = float(at)
            if at_seconds < -EPSILON:
                errors.append(f"transition {transition_id} occurs before timeline zero.")
            if duration_seconds and at_seconds > duration_seconds + EPSILON:
                errors.append(f"transition {transition_id} occurs after timeline duration.")
        transition_duration = transition.get("duration")
        if transition_duration is not None and not is_finite_number(transition_duration):
            errors.append(f"transition {transition_id} duration must be numeric.")
        elif is_finite_number(transition_duration) and float(transition_duration) < -EPSILON:
            errors.append(f"transition {transition_id} duration must be non-negative.")
        for key in ("fromClipId", "toClipId"):
            clip_id = transition.get(key)
            if clip_id is not None and str(clip_id) not in clip_by_id:
                errors.append(f"transition {transition_id} references missing {key}: {clip_id}")

    target_paths: list[str] = []
    render = timeline.get("render")
    targets = render.get("targets") if isinstance(render, dict) else None
    if isinstance(targets, list):
        for target in targets:
            if not isinstance(target, dict):
                continue
            path = str(target.get("path") or "")
            if path:
                target_paths.append(path)
                parent = Path(path).parent
                if parent and not parent.exists():
                    warnings.append(f"render target parent does not exist yet: {parent}")
    else:
        errors.append("render.targets must be an array.")

    preview = render.get("preview") if isinstance(render, dict) and isinstance(render.get("preview"), dict) else None
    if preview is not None:
        preview_start = preview.get("rangeStart")
        preview_end = preview.get("rangeEnd")
        if not is_finite_number(preview_start) or not is_finite_number(preview_end):
            errors.append("render.preview rangeStart/rangeEnd must be numeric.")
        else:
            start_seconds = float(preview_start)
            end_seconds = float(preview_end)
            if start_seconds < -EPSILON:
                errors.append("render.preview rangeStart must be at or after timeline zero.")
            if end_seconds <= start_seconds + EPSILON:
                errors.append("render.preview rangeEnd must be greater than rangeStart.")
            if duration_seconds and end_seconds > duration_seconds + EPSILON:
                errors.append("render.preview rangeEnd exceeds timeline duration.")

    if not target_paths:
        warnings.append("timeline has no render target paths.")

    return errors, warnings


def write_report(path: Path, timeline_path: Path, errors: list[str], warnings: list[str], schema_path: Path = DEFAULT_SCHEMA) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "timeline": str(timeline_path),
                "schema": str(schema_path),
                "valid": not errors,
                "errorCount": len(errors),
                "warningCount": len(warnings),
                "errors": errors,
                "warnings": warnings,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a renderer-agnostic video edit timeline.")
    parser.add_argument("--timeline", type=Path, default=None, help="Timeline JSON path. Defaults to render.timelinePath or output/timelines/current.timeline.json.")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA, help="Schema path to report for auditability.")
    parser.add_argument("--output-report", type=Path, default=DEFAULT_REPORT, help="Validation report path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    timeline_path = args.timeline or configured_timeline_path()
    try:
        timeline = load_timeline(timeline_path)
        schema = load_schema(args.schema)
        errors, warnings = validate_timeline(timeline, schema=schema)
    except ValueError as error:
        errors = [str(error)]
        warnings = []
    write_report(args.output_report, timeline_path, errors, warnings, schema_path=args.schema)
    summary = {
        "timeline": str(timeline_path),
        "schema": str(args.schema),
        "validationReport": str(args.output_report),
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
