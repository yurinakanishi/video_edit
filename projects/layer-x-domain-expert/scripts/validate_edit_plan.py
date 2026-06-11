from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT_ROOT / "output" / "reports"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def style_ids(style_guide: dict[str, Any]) -> set[str]:
    ids = set()
    for key in ("styles", "components"):
        value = style_guide.get(key)
        if isinstance(value, dict):
            ids.update(str(item) for item in value)
    return ids


def overlay_interval(event: dict[str, Any], overlay: dict[str, Any]) -> tuple[float, float] | None:
    duration = float(event.get("timeline_end") or 0.0) - float(event.get("timeline_start") or 0.0)
    start = overlay.get("start")
    end = overlay.get("end")
    if start is None and end is None:
        return None
    start_f = float(start or 0.0)
    end_f = float(end if end is not None else duration)
    return (start_f, end_f)


def intervals_overlap(left: tuple[float, float], right: tuple[float, float]) -> bool:
    return left[0] < right[1] and right[0] < left[1]


def event_reference_window(event: dict[str, Any]) -> tuple[float, float] | None:
    source = event.get("reference_source") if isinstance(event.get("reference_source"), dict) else event.get("source")
    if not isinstance(source, dict) or source.get("in") is None or source.get("out") is None:
        return None
    return float(source["in"]), float(source["out"])


def caption_source_window(overlay: dict[str, Any]) -> tuple[float, float] | None:
    alignment = overlay.get("audio_alignment") if isinstance(overlay.get("audio_alignment"), dict) else {}
    speech_window = alignment.get("speech_window_sec")
    if isinstance(speech_window, list) and len(speech_window) == 2:
        try:
            return float(speech_window[0]), float(speech_window[1])
        except (TypeError, ValueError):
            pass
    metadata = overlay.get("metadata") if isinstance(overlay.get("metadata"), dict) else {}
    start = metadata.get("source_start_sec", metadata.get("caption_start_sec"))
    end = metadata.get("source_end_sec", metadata.get("caption_end_sec"))
    if start is None:
        return None
    try:
        start_f = float(start)
        fallback_duration = max(0.8, float(overlay.get("end") or 0.0) - float(overlay.get("start") or 0.0))
        end_f = float(end) if end is not None else start_f + fallback_duration
        return start_f, max(start_f + 0.2, end_f)
    except (TypeError, ValueError):
        return None


def interval_overlap_seconds(left: tuple[float, float], right: tuple[float, float]) -> float:
    return max(0.0, min(left[1], right[1]) - max(left[0], right[0]))


def existing_reference_path(value: Any) -> bool:
    if not value:
        return True
    path = Path(str(value))
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.exists()


def main() -> None:
    manifest = read_json(REPORTS / "project_manifest.json")
    people = read_json(REPORTS / "people_map.json")
    style_guide = read_json(REPORTS / "style_guide.json")
    plan = read_json(REPORTS / "edit_plan.json")
    content_window = read_json(REPORTS / "content_window.json") if (REPORTS / "content_window.json").exists() else {}

    media_durations = {
        str(item.get("media_id")): float(item.get("duration") or 0.0)
        for item in manifest.get("media", [])
        if item.get("media_id")
    }
    person_ids = {str(item.get("person_id")) for item in people.get("people", []) if item.get("person_id")}
    known_styles = style_ids(style_guide)

    errors: list[str] = []
    warnings: list[str] = []
    usable = content_window.get("usable_master_range") if isinstance(content_window.get("usable_master_range"), dict) else {}
    usable_start = float(usable.get("start_sec") or 0.0)
    usable_end_raw = usable.get("end_sec")
    usable_end = float(usable_end_raw) if usable_end_raw is not None else None
    forbidden_markers = [str(item) for item in content_window.get("forbidden_text_markers", [])] if isinstance(content_window.get("forbidden_text_markers"), list) else []
    previous_end: float | None = None
    events = [item for item in plan.get("timeline", []) if isinstance(item, dict)]
    for event in events:
        event_id = str(event.get("event_id") or "unknown_event")
        start = float(event.get("timeline_start") or 0.0)
        end = float(event.get("timeline_end") or 0.0)
        if end <= start:
            errors.append(f"{event_id}: timeline_end must be greater than timeline_start")
        if previous_end is not None:
            if start < previous_end - 0.001:
                errors.append(f"{event_id}: overlaps previous event by {previous_end - start:.3f}s")
            elif start > previous_end + 0.001:
                warnings.append(f"{event_id}: timeline gap of {start - previous_end:.3f}s before event")
        previous_end = end

        for source_key in ("source", "reference_source"):
            source = event.get(source_key)
            if not isinstance(source, dict):
                continue
            media_id = str(source.get("media_id") or "")
            if media_id not in media_durations:
                errors.append(f"{event_id}: {source_key}.media_id does not exist: {media_id}")
                continue
            source_in = float(source.get("in") or 0.0)
            source_out = float(source.get("out") or 0.0)
            if source_in < -0.001 or source_out <= source_in:
                errors.append(f"{event_id}: invalid {source_key} range {source_in:.3f}-{source_out:.3f}")
            if source_out > media_durations[media_id] + 0.001:
                errors.append(f"{event_id}: {source_key} range exceeds {media_id} duration")
            if source_key == "reference_source" and media_id == "group_wide":
                if source_in < usable_start - 0.001:
                    errors.append(f"{event_id}: reference_source starts before usable content window")
                if usable_end is not None and source_out > usable_end + 0.001:
                    errors.append(f"{event_id}: reference_source exceeds usable content window")
            if source_key == "source" and media_id == "group_wide":
                if source_in < usable_start - 0.001:
                    errors.append(f"{event_id}: source starts before usable content window")
                if usable_end is not None and source_out > usable_end + 0.001:
                    errors.append(f"{event_id}: source exceeds usable content window")

        layout = event.get("layout") if isinstance(event.get("layout"), dict) else {}
        layout_type = str(layout.get("type") or "")
        reference_alignment = layout.get("reference_alignment")
        if isinstance(reference_alignment, dict):
            for key in ("analysis_path", "fallback_analysis_path"):
                if reference_alignment.get(key) and not existing_reference_path(reference_alignment.get(key)):
                    errors.append(f"{event_id}: layout.reference_alignment.{key} does not exist")
        for key in ("target_person_id", "person_id"):
            value = layout.get(key)
            if value and str(value) not in person_ids:
                errors.append(f"{event_id}: layout.{key} does not exist: {value}")
        for key in ("ensure_people_visible", "person_ids"):
            values = layout.get(key)
            if isinstance(values, list):
                missing = [str(value) for value in values if str(value) not in person_ids]
                if missing:
                    errors.append(f"{event_id}: layout.{key} has unknown people: {', '.join(missing)}")

        caption_intervals: list[tuple[float, float]] = []
        explainer_intervals: list[tuple[float, float]] = []
        nameplate_intervals: list[tuple[float, float]] = []
        for overlay in event.get("overlays", []):
            if not isinstance(overlay, dict):
                continue
            style_id = overlay.get("style_id")
            if style_id and str(style_id) not in known_styles:
                errors.append(f"{event_id}: overlay style_id does not exist: {style_id}")
            text = str(overlay.get("text") or "")
            for marker in forbidden_markers:
                if marker and marker in text:
                    errors.append(f"{event_id}: overlay text contains forbidden marker: {marker}")
            person_id = overlay.get("person_id")
            if person_id and str(person_id) not in person_ids:
                errors.append(f"{event_id}: overlay person_id does not exist: {person_id}")
            interval = overlay_interval(event, overlay)
            if interval and interval[1] <= interval[0]:
                errors.append(f"{event_id}: overlay has invalid interval {interval[0]:.3f}-{interval[1]:.3f}")
            if interval and overlay.get("type") == "caption":
                caption_intervals.append(interval)
                reference_window = event_reference_window(event)
                source_window = caption_source_window(overlay)
                if reference_window and source_window:
                    source_mid = (source_window[0] + source_window[1]) / 2.0
                    source_present = (
                        interval_overlap_seconds(source_window, reference_window) >= 0.25
                        or reference_window[0] - 0.12 <= source_mid <= reference_window[1] + 0.12
                    )
                    if not source_present:
                        errors.append(
                            f"{event_id}: caption source window {source_window[0]:.3f}-{source_window[1]:.3f} is outside event reference window {reference_window[0]:.3f}-{reference_window[1]:.3f}"
                        )
            if interval and overlay.get("type") == "entity_explainer":
                explainer_intervals.append(interval)
            if interval and overlay.get("type") in {"lower_third_person", "lower_third_people"}:
                nameplate_intervals.append(interval)
                if layout_type == "split_grid":
                    errors.append(f"{event_id}: nameplate overlays are not allowed in split_grid layouts")
            reference_alignment = overlay.get("reference_alignment")
            if isinstance(reference_alignment, dict) and reference_alignment.get("analysis_path"):
                if not existing_reference_path(reference_alignment.get("analysis_path")):
                    errors.append(f"{event_id}: overlay.reference_alignment.analysis_path does not exist")
        for caption in caption_intervals:
            for explainer in explainer_intervals:
                if intervals_overlap(caption, explainer):
                    errors.append(f"{event_id}: caption overlaps entity explainer")
            for nameplate in nameplate_intervals:
                if intervals_overlap(caption, nameplate):
                    errors.append(f"{event_id}: caption overlaps nameplate")

    report = {
        "schema_version": "edit_plan_validation_report.v1",
        "project_id": "layer-x-domain-expert",
        "source": str(REPORTS / "edit_plan.json"),
        "ready_for_preview": bool(events) and not errors and bool((plan.get("validation") or {}).get("ready_for_preview")),
        "errors": errors,
        "warnings": warnings + list((plan.get("validation") or {}).get("warnings") or []),
        "plan_blockers": list((plan.get("validation") or {}).get("blockers") or []),
        "event_count": len(events),
    }
    output = REPORTS / "edit_plan_validation_report.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
