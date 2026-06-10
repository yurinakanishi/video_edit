from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT_ROOT / "output" / "reports"


MEDIA_TO_PERSON = {
    "cam_person_01": "person_01",
    "cam_person_02": "person_02",
    "cam_person_03": "person_03",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def primary_camera_person(layout: dict[str, Any]) -> str | None:
    layout_type = str(layout.get("type") or "")
    if layout_type == "single":
        return str(layout.get("target_person_id") or layout.get("active_person_id") or "") or None
    if layout_type == "wide_group":
        return str(layout.get("active_person_id") or "") or None
    if layout_type == "split_grid":
        return str(layout.get("active_person_id") or "") or None
    return None


def visible_people(layout: dict[str, Any]) -> list[str]:
    layout_type = str(layout.get("type") or "")
    if layout_type == "single":
        person = primary_camera_person(layout)
        return [person] if person else []
    if layout_type == "wide_group":
        return [str(item) for item in layout.get("ensure_people_visible") or ["person_01", "person_02", "person_03"]]
    if layout_type == "split_grid":
        result = []
        for media_id in layout.get("media_ids") or []:
            person_id = MEDIA_TO_PERSON.get(str(media_id))
            if person_id:
                result.append(person_id)
        for person_id in layout.get("panel_order") or []:
            if person_id not in result:
                result.append(str(person_id))
        return result
    return []


def caption_speakers(event: dict[str, Any]) -> list[str]:
    speakers = []
    for overlay in event.get("overlays", []):
        if not isinstance(overlay, dict) or overlay.get("type") != "caption":
            continue
        person_id = str(overlay.get("speaker_person_id") or "")
        if person_id and person_id not in speakers:
            speakers.append(person_id)
    return speakers


def caption_texts(event: dict[str, Any]) -> list[str]:
    return [
        str(overlay.get("text") or "")
        for overlay in event.get("overlays", [])
        if isinstance(overlay, dict) and overlay.get("type") == "caption" and overlay.get("text")
    ]


def source_range(event: dict[str, Any]) -> dict[str, Any]:
    source = event.get("reference_source") if isinstance(event.get("reference_source"), dict) else event.get("source")
    source = source if isinstance(source, dict) else {}
    return {
        "media_id": source.get("media_id"),
        "in": source.get("in"),
        "out": source.get("out"),
    }


def main() -> None:
    plan = read_json(REPORTS / "edit_plan.json")
    events = []
    issues = []
    for event in plan.get("timeline", []):
        if not isinstance(event, dict) or event.get("section") != "digest":
            continue
        layout = event.get("layout") if isinstance(event.get("layout"), dict) else {}
        speakers = caption_speakers(event)
        primary = primary_camera_person(layout)
        visible = visible_people(layout)
        layout_type = str(layout.get("type") or "")
        speaker_focused = bool(speakers) and primary in speakers
        single_speaker = len(speakers) == 1
        if speakers and not speaker_focused:
            issues.append(
                {
                    "event_id": event.get("event_id"),
                    "severity": "needs_fix",
                    "reason": "primary_camera_not_on_caption_speaker",
                    "speaker_person_ids": speakers,
                    "primary_camera_person_id": primary,
                    "visible_people": visible,
                }
            )
        events.append(
            {
                "event_id": event.get("event_id"),
                "timeline_start": event.get("timeline_start"),
                "timeline_end": event.get("timeline_end"),
                "source": source_range(event),
                "layout_type": layout_type,
                "primary_camera_person_id": primary,
                "visible_people": visible,
                "caption_speaker_person_ids": speakers,
                "speaker_focused": speaker_focused,
                "caption_texts": caption_texts(event),
                "decision_basis": "caption speaker IDs are assigned from SRT context and digest selection metadata; layout must make that speaker the primary camera target.",
            }
        )

    payload = {
        "schema_version": "digest_speaker_layout_audit.v1",
        "project_id": "layer-x-domain-expert",
            "policy": {
            "single_speaker_digest_event": "split_grid is allowed, but active_person_id must match the current speaker",
            "primary_camera_person_id": "must_match_caption_speaker_person_id",
            "split_grid": "allowed only when multiple active participants are intentionally needed",
        },
        "summary": {
            "digest_events": len(events),
            "issue_count": len(issues),
            "ready": len(issues) == 0,
        },
        "issues": issues,
        "events": events,
    }
    output = REPORTS / "digest_speaker_layout_audit.json"
    write_json(output, payload)
    print(json.dumps({"output": str(output), **payload["summary"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
