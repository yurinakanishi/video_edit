from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[1]
REPORTS_DIR = PROJECT_DIR / "output" / "reports"
EDIT_PLAN_PATH = REPORTS_DIR / "edit_plan.json"
REPORT_PATH = REPORTS_DIR / "two_guest_intro_split_restore_report.json"

JST = timezone(timedelta(hours=9))
EVENT_ID = "main_intro_two_guests_named"
INTRO_PEOPLE = ["person_02", "person_03"]
INTRO_MEDIA = ["cam_person_02", "cam_person_03"]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def event_duration(event: dict[str, Any]) -> float:
    return round(float(event.get("timeline_end") or 0.0) - float(event.get("timeline_start") or 0.0), 3)


def restore_event(event: dict[str, Any]) -> dict[str, Any]:
    before = {
        "layout": event.get("layout"),
        "overlays": event.get("overlays"),
        "reason": event.get("reason"),
    }
    duration = event_duration(event)
    reference_analysis = REPORTS_DIR / "reference_image_analysis" / "two-person-split-introduction-name-subtitle-reference.json"

    event["layout"] = {
        "type": "split_grid",
        "media_ids": INTRO_MEDIA,
        "grid_strategy": "two_person_vertical_split",
        "panel_order": INTRO_PEOPLE,
        "ensure_people_visible": INTRO_PEOPLE,
        "introduced_person_ids": INTRO_PEOPLE,
        "intro_target_split_exception": True,
        "speaker_visibility_exception": {
            "enabled": True,
            "speaker_person_id": "person_01",
            "reason": "During this introduction sentence, the interviewer is speaking but the edit must show the two guests being introduced.",
        },
        "selection_reason": "At '根本さんと村田さんにお越しいただきました', restore the two-interviewee split: Nemoto left, Murata right, with white per-panel intro labels.",
        "reference_alignment": {
            "reference_image_id": "two_person_split_intro_white_names",
            "analysis_path": str(reference_analysis),
            "apply": [
                "stable_panel_order",
                "matched_face_scale",
                "per_panel_white_name_labels",
                "no_purple_name_boxes",
            ],
        },
    }

    topic_overlays = [
        overlay
        for overlay in event.get("overlays", [])
        if isinstance(overlay, dict) and overlay.get("type") == "topic_title"
    ]
    if not topic_overlays:
        topic_overlays = [
            {
                "type": "topic_title",
                "position": "top_right",
                "topic_id": "topic_001",
                "style_id": "opening_digest_top_right_title",
            }
        ]

    event["overlays"] = topic_overlays + [
        {
            "type": "split_person_labels",
            "start": 0.0,
            "end": duration,
            "person_ids": INTRO_PEOPLE,
            "reference_image_id": "two_person_split_intro_white_names",
            "reference_alignment": {
                "analysis_path": str(reference_analysis),
                "apply": ["white_lower_text_per_panel", "role_above_name", "soft_shadow_only"],
            },
            "editorial_note": "Restored per-panel white introduction text for the two interviewees.",
        }
    ]
    event["caption_policy"] = "no_caption_while_nameplate_visible"
    event["reason"] = (
        "At '根本さんと村田さんにお越しいただきました', use the right-two-person split with white labels. "
        "This is an explicit introduction exception to the normal speaker-visible rule."
    )
    return before


def main() -> None:
    plan = read_json(EDIT_PLAN_PATH)
    event = next((item for item in plan.get("timeline", []) if isinstance(item, dict) and item.get("event_id") == EVENT_ID), None)
    if event is None:
        raise SystemExit(f"{EVENT_ID} was not found in edit_plan.json")

    before = restore_event(event)
    now = datetime.now(JST).isoformat(timespec="seconds")
    plan["updated_at"] = now
    plan.setdefault("revision_notes", []).append(
        {
            "updated_at": now,
            "change": "Restored the two-interviewee introduction split with white per-panel labels.",
            "event_id": EVENT_ID,
            "person_ids": INTRO_PEOPLE,
            "media_ids": INTRO_MEDIA,
            "speaker_visibility_exception": "interviewer introduces the two visible guests",
        }
    )
    write_json(EDIT_PLAN_PATH, plan)

    report = {
        "schema_version": "two_guest_intro_split_restore_report.v1",
        "project_id": "layer-x-domain-expert",
        "updated_at": now,
        "event_id": EVENT_ID,
        "before": before,
        "after": {
            "layout": event.get("layout"),
            "overlays": event.get("overlays"),
            "reason": event.get("reason"),
        },
    }
    write_json(REPORT_PATH, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
