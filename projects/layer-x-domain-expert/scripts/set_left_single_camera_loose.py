from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[1]
REPORTS_DIR = PROJECT_DIR / "output" / "reports"
EDIT_PLAN_PATH = REPORTS_DIR / "edit_plan.json"
REPORT_PATH = REPORTS_DIR / "left_single_camera_loose_report.json"

JST = timezone(timedelta(hours=9))
LEFT_MEDIA_ID = "cam_person_01"
LEFT_PERSON_ID = "person_01"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def is_left_single_event(event: dict[str, Any]) -> bool:
    layout = event.get("layout") if isinstance(event.get("layout"), dict) else {}
    source = event.get("source") if isinstance(event.get("source"), dict) else {}
    return (
        layout.get("type") == "single"
        and (
            source.get("media_id") == LEFT_MEDIA_ID
            or layout.get("selected_media_id") == LEFT_MEDIA_ID
            or layout.get("target_person_id") == LEFT_PERSON_ID
        )
    )


def main() -> None:
    plan = read_json(EDIT_PLAN_PATH)
    changed = []

    for index, event in enumerate(plan.get("timeline", []), start=1):
        if not isinstance(event, dict) or not is_left_single_event(event):
            continue
        layout = event["layout"]
        before = {
            "crop_mode": layout.get("crop_mode"),
            "single_scale_h": layout.get("single_scale_h"),
            "single_target_face_y": layout.get("single_target_face_y"),
            "selection_reason": layout.get("selection_reason"),
        }

        layout["crop_mode"] = "loose_full_frame"
        layout["selection_reason"] = (
            "User review: when the left participant is shown alone, use the looser full-frame camera view "
            "instead of a close-up, matching the other participants' pullback feel."
        )
        layout["reference_alignment"] = {
            "reference_image_id": "left_single_loose_full_frame",
            "apply": ["loose_single_camera", "speaker_visible", "no_closeup_crop"],
        }
        for key in (
            "single_scale_h",
            "single_target_face_y",
            "face_center_x",
            "face_center_y",
            "crop_analysis",
        ):
            layout.pop(key, None)

        changed.append(
            {
                "index": index,
                "event_id": event.get("event_id"),
                "timeline_start": event.get("timeline_start"),
                "timeline_end": event.get("timeline_end"),
                "before": before,
                "after": {
                    "crop_mode": layout.get("crop_mode"),
                    "selection_reason": layout.get("selection_reason"),
                },
            }
        )

    now = datetime.now(JST).isoformat(timespec="seconds")
    plan["updated_at"] = now
    plan.setdefault("revision_notes", []).append(
        {
            "updated_at": now,
            "change": "Changed all left-participant single-camera events from close-up crops to loose full-frame camera view.",
            "changed_event_count": len(changed),
        }
    )
    write_json(EDIT_PLAN_PATH, plan)

    report = {
        "schema_version": "left_single_camera_loose_report.v1",
        "updated_at": now,
        "reason_not_fixed_before": (
            "The active edit_plan still contained close-up crop modes for left-only single-camera events, "
            "so renders followed those JSON instructions. This was separate from the stale segment cache issue."
        ),
        "changed_event_count": len(changed),
        "changed_events": changed,
    }
    write_json(REPORT_PATH, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
