from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT_ROOT / "output" / "reports"
JST = timezone(timedelta(hours=9))

MEDIA_PERSON = {
    "cam_person_01": "person_01",
    "cam_person_02": "person_02",
    "cam_person_03": "person_03",
}
ALL_PEOPLE = ["person_01", "person_02", "person_03"]


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def now_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def visible_people(event: dict[str, Any]) -> list[str]:
    layout = event.get("layout") if isinstance(event.get("layout"), dict) else {}
    layout_type = str(layout.get("type") or "")
    if layout_type == "wide_group":
        return list(ALL_PEOPLE)
    if layout_type == "single":
        person_id = str(layout.get("target_person_id") or "")
        if person_id in ALL_PEOPLE:
            return [person_id]
        media_id = str(layout.get("selected_media_id") or event.get("source", {}).get("media_id") or "")
        person_id = MEDIA_PERSON.get(media_id)
        return [person_id] if person_id else []
    if layout_type == "split_grid":
        people = [str(item) for item in layout.get("panel_order", []) if str(item) in ALL_PEOPLE]
        if people:
            return people
        people = [MEDIA_PERSON[item] for item in layout.get("media_ids", []) if item in MEDIA_PERSON]
        return list(dict.fromkeys(people))
    source = event.get("source") if isinstance(event.get("source"), dict) else {}
    media_id = str(source.get("media_id") or "")
    if media_id == "group_wide":
        return list(ALL_PEOPLE)
    person_id = MEDIA_PERSON.get(media_id)
    return [person_id] if person_id else []


def event_reference_range(event: dict[str, Any]) -> tuple[float, float] | None:
    reference = event.get("reference_source") if isinstance(event.get("reference_source"), dict) else None
    source = reference or (event.get("source") if isinstance(event.get("source"), dict) else None)
    if not source:
        return None
    try:
        start = float(source.get("in") or 0.0)
        end = float(source.get("out") or start)
    except (TypeError, ValueError):
        return None
    if end <= start:
        return None
    return start, end


def allows_intro_target_exception(event: dict[str, Any], speaker_person_id: str) -> bool:
    layout = event.get("layout") if isinstance(event.get("layout"), dict) else {}
    if not layout.get("intro_target_split_exception"):
        return False
    exception = layout.get("speaker_visibility_exception")
    if not isinstance(exception, dict) or not exception.get("enabled"):
        return False
    return str(exception.get("speaker_person_id") or "") == speaker_person_id


def overlapping_voice_segments(segments: list[dict[str, Any]], start: float, end: float) -> list[dict[str, Any]]:
    result = []
    for segment in segments:
        person_id = str(segment.get("speaker_person_id") or "")
        if person_id not in ALL_PEOPLE:
            continue
        try:
            segment_start = float(segment.get("start") or 0.0)
            segment_end = float(segment.get("end") or segment_start)
            confidence = float(segment.get("confidence") or 0.0)
        except (TypeError, ValueError):
            continue
        overlap = max(0.0, min(end, segment_end) - max(start, segment_start))
        if overlap < 0.22:
            continue
        method = str(segment.get("method") or "")
        if confidence < 0.42 and method not in {"forced_known_intro_window", "text_role_override_voice", "voice_and_text_agree"}:
            continue
        result.append({**segment, "window_overlap_sec": round(overlap, 3)})
    return result


def main() -> None:
    plan = read_json(REPORTS / "edit_plan.json", {})
    voice = read_json(REPORTS / "voice_speaker_attribution.json", {})
    voice_segments = [
        item
        for item in voice.get("segments", [])
        if isinstance(item, dict) and item.get("speaker_person_id") in ALL_PEOPLE
    ]

    violations = []
    event_summaries = []
    checked_events = 0
    checked_segments = 0
    for event in plan.get("timeline", []):
        if not isinstance(event, dict) or event.get("section") != "main":
            continue
        event_id = str(event.get("event_id") or "")
        time_range = event_reference_range(event)
        if not time_range:
            continue
        start, end = time_range
        visible = visible_people(event)
        segments = overlapping_voice_segments(voice_segments, start, end)
        if not segments:
            continue
        checked_events += 1
        checked_segments += len(segments)
        missing = []
        for segment in segments:
            person_id = str(segment.get("speaker_person_id") or "")
            if person_id not in visible:
                if allows_intro_target_exception(event, person_id):
                    continue
                missing.append(
                    {
                        "segment_id": segment.get("segment_id"),
                        "start": round(float(segment.get("start") or 0.0), 3),
                        "end": round(float(segment.get("end") or 0.0), 3),
                        "speaker_person_id": person_id,
                        "speaker_name": segment.get("speaker_name"),
                        "confidence": segment.get("confidence"),
                        "method": segment.get("method"),
                        "text": str(segment.get("text") or "")[:100],
                    }
                )
        event_summaries.append(
            {
                "event_id": event_id,
                "reference_start": round(start, 3),
                "reference_end": round(end, 3),
                "layout_type": (event.get("layout") or {}).get("type") if isinstance(event.get("layout"), dict) else None,
                "visible_people": visible,
                "voice_speakers_in_window": list(dict.fromkeys(str(item.get("speaker_person_id")) for item in segments)),
                "missing_count": len(missing),
            }
        )
        if missing:
            violations.append(
                {
                    "event_id": event_id,
                    "reference_start": round(start, 3),
                    "reference_end": round(end, 3),
                    "visible_people": visible,
                    "missing_speaker_segments": missing,
                }
            )

    report = {
        "schema_version": "main_speaker_layout_audit.v1",
        "project_id": "layer-x-domain-expert",
        "generated_at": now_iso(),
        "edit_plan_source": str(REPORTS / "edit_plan.json"),
        "voice_speaker_attribution_source": str(REPORTS / "voice_speaker_attribution.json"),
        "policy": "Every trusted voice-attributed utterance overlapping a main-section event must have its speaker visible in the selected layout.",
        "checked_main_events": checked_events,
        "checked_voice_segments": checked_segments,
        "violation_count": len(violations),
        "ready_for_render": len(violations) == 0,
        "violations": violations,
        "event_summaries": event_summaries,
    }
    output = REPORTS / "main_speaker_layout_audit.json"
    write_json(output, report)
    print(json.dumps({"output": str(output), "checked_events": checked_events, "violations": len(violations)}, ensure_ascii=False, indent=2))
    if violations:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
