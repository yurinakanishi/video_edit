from __future__ import annotations

import copy
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


PROJECT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT / "output" / "reports"
EDIT_PLAN = REPORTS / "edit_plan.json"
REPORT = REPORTS / "opening_digest_middle_replacement_report.json"
JST = timezone(timedelta(hours=9))

OLD_OPENING_ID = "digest_opening_murata_discomfort_01"
MIDDLE_SOURCE_ID = "digest_qa_middle_nemoto_value_01"
NEW_OPENING_ID = "digest_opening_nemoto_value_01"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def event_duration(event: dict[str, Any]) -> float:
    return round(float(event.get("timeline_end") or 0.0) - float(event.get("timeline_start") or 0.0), 3)


def source_duration(event: dict[str, Any]) -> float:
    source = event.get("reference_source") if isinstance(event.get("reference_source"), dict) else event.get("source")
    if isinstance(source, dict) and source.get("in") is not None and source.get("out") is not None:
        return round(float(source["out"]) - float(source["in"]), 3)
    return event_duration(event)


def retime_timeline(events: list[dict[str, Any]]) -> None:
    cursor = 0.0
    for event in events:
        duration = float(event.get("duration") or source_duration(event))
        event["timeline_start"] = round(cursor, 3)
        event["timeline_end"] = round(cursor + duration, 3)
        event["duration"] = round(duration, 3)
        cursor += duration


def root_for_overlay(event_id: str, overlay_index: int) -> str:
    return f"{event_id}_caption_{overlay_index}"


def normalize_opening_event(event: dict[str, Any]) -> dict[str, Any]:
    opening = copy.deepcopy(event)
    duration = source_duration(opening)
    opening["event_id"] = NEW_OPENING_ID
    opening["timeline_start"] = 0.0
    opening["timeline_end"] = duration
    opening["duration"] = duration
    opening["reason"] = (
        "Opening digest beat replaced per user request: use the middle participant's spoken caption instead of the previous Murata discomfort line."
    )

    layout = opening.get("layout") if isinstance(opening.get("layout"), dict) else {}
    layout["type"] = "single"
    layout["selected_media_id"] = "cam_person_02"
    layout["target_person_id"] = "person_02"
    layout["active_person_id"] = "person_02"
    layout["speaker_person_id"] = "person_02"
    layout["selection_reason"] = "Digest opening now uses the middle participant's concise value statement."
    opening["layout"] = layout

    for index, overlay in enumerate(opening.get("overlays", []) or []):
        if not isinstance(overlay, dict) or overlay.get("type") != "caption":
            continue
        metadata = overlay.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["source"] = "opening_digest_middle_speaker_replacement"
            metadata["replacement_for_event_id"] = OLD_OPENING_ID
            metadata["replacement_reason"] = "User requested replacing the opening '違和感を言うと良いものになっていく' with a middle-speaker caption."
            metadata["caption_source_of_truth"] = "edit_plan.json"
            metadata["speaker_name"] = "根本"
            metadata["speaker_person_id"] = "person_02"
            metadata["caption_cut_continuation_root_id"] = root_for_overlay(NEW_OPENING_ID, index)
        overlay["speaker_person_id"] = "person_02"
    return opening


def main() -> None:
    plan = load(EDIT_PLAN)
    timeline = [event for event in plan.get("timeline", []) if isinstance(event, dict)]
    old_opening = next((event for event in timeline if event.get("event_id") == OLD_OPENING_ID), None)
    middle = next((event for event in timeline if event.get("event_id") == MIDDLE_SOURCE_ID), None)
    existing_new = next((event for event in timeline if event.get("event_id") == NEW_OPENING_ID), None)
    if existing_new and not old_opening and not middle:
        next_timeline = [normalize_opening_event(existing_new)]
        next_timeline.extend(event for event in timeline if event.get("event_id") != NEW_OPENING_ID)
        retime_timeline(next_timeline)
        plan["timeline"] = next_timeline
        mode = "normalize_existing_opening"
    elif old_opening and middle:
        new_opening = normalize_opening_event(middle)
        next_timeline = [new_opening]
        for event in timeline:
            event_id = event.get("event_id")
            if event_id in {OLD_OPENING_ID, MIDDLE_SOURCE_ID}:
                continue
            next_timeline.append(event)
        retime_timeline(next_timeline)
        plan["timeline"] = next_timeline
        mode = "replace_opening"
    else:
        raise SystemExit(f"Required digest events not found: {OLD_OPENING_ID}, {MIDDLE_SOURCE_ID}")
    new_opening = plan["timeline"][0]

    updated_at = datetime.now(JST).isoformat(timespec="seconds")
    plan["updated_at"] = updated_at
    plan.setdefault("revision_notes", []).append(
        {
            "updated_at": updated_at,
            "script": Path(__file__).name,
            "summary": "Replaced or normalized the first digest beat so it uses the middle participant Nemoto caption.",
            "mode": mode,
        }
    )
    save(EDIT_PLAN, plan)

    report = {
        "schema_version": "opening_digest_middle_replacement.v1",
        "project_id": "layer-x-domain-expert",
        "updated_at": updated_at,
        "removed_opening_event_id": OLD_OPENING_ID,
        "moved_middle_event_id": MIDDLE_SOURCE_ID,
        "new_opening_event_id": NEW_OPENING_ID,
        "mode": mode,
        "caption_text": [
            overlay.get("text")
            for overlay in new_opening.get("overlays", []) or []
            if isinstance(overlay, dict) and overlay.get("type") == "caption"
        ],
        "source": new_opening.get("source"),
        "reference_source": new_opening.get("reference_source"),
        "layout": new_opening.get("layout"),
    }
    save(REPORT, report)
    print(json.dumps({"new_opening_event_id": NEW_OPENING_ID, "caption_text": report["caption_text"], "report": str(REPORT)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
