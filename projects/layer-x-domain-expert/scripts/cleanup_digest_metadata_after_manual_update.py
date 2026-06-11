import json
from datetime import datetime, timezone, timedelta
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT / "output" / "reports"
EDIT_PLAN = REPORTS / "edit_plan.json"
DIGEST_SELECTION = REPORTS / "digest_qa_selection.json"
REPORT_PATH = REPORTS / "digest_metadata_cleanup_report.json"
JST = timezone(timedelta(hours=9))

REMOVE_EVENT_IDS = {
    "digest_qa_01_answer_02",
    "digest_qa_01_answer_03",
    "digest_qa_04_answer_02",
    "digest_qa_04_answer_02_short02",
    "digest_qa_04_answer_02_short03",
    "digest_qa_05_answer_02",
}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest_event_summary(event: dict) -> dict:
    duration = round(float(event["timeline_end"]) - float(event["timeline_start"]), 3)
    return {
        "event_id": event["event_id"],
        "source_event_id": event.get("event_id"),
        "local_start": 0.0,
        "local_end": duration,
        "duration_sec": duration,
        "reason": event.get("reason") or event.get("layout", {}).get("selection_reason") or "Current active digest timeline event.",
        "captions": [
            overlay.get("text")
            for overlay in event.get("overlays", [])
            if overlay.get("type") == "caption" and overlay.get("text")
        ],
        "speaker_person_id": next(
            (
                overlay.get("speaker_person_id")
                for overlay in event.get("overlays", [])
                if overlay.get("type") == "caption" and overlay.get("speaker_person_id")
            ),
            event.get("layout", {}).get("target_person_id") or event.get("layout", {}).get("active_person_id"),
        ),
    }


def main() -> None:
    updated_at = datetime.now(JST).isoformat(timespec="seconds")
    edit_plan = load(EDIT_PLAN)
    digest_events = [
        event
        for event in edit_plan["timeline"]
        if event.get("section") == "digest"
    ]
    digest_duration = round(
        next(event["timeline_start"] for event in edit_plan["timeline"] if event.get("event_id") == "digest_to_main_company_movie"),
        3,
    )
    selected = [digest_event_summary(event) for event in digest_events]

    pacing = edit_plan.setdefault("digest_pacing", {})
    pacing["policy"] = "Opening digest keeps only the active selected question/answer beats after manual removals."
    pacing["parts"] = [
        {
            "part_id": event["event_id"],
            "kept_duration_sec": round(float(event["timeline_end"]) - float(event["timeline_start"]), 3),
            "policy": "active_digest_event",
        }
        for event in digest_events
    ]
    pacing["shortened_digest_duration_sec"] = digest_duration
    one_minute = pacing.setdefault("one_minute_shortening", {})
    one_minute["schema_version"] = "digest_one_minute_shortening.v1"
    one_minute["shortened_digest_duration_sec"] = digest_duration
    one_minute["kept_event_count"] = len(selected)
    one_minute["selection"] = selected
    one_minute["removed_event_ids_by_user_request"] = sorted(REMOVE_EVENT_IDS)

    edit_plan["updated_at"] = updated_at
    save(EDIT_PLAN, edit_plan)

    selection_removed = []
    if DIGEST_SELECTION.exists():
        digest_selection = load(DIGEST_SELECTION)
        one = digest_selection.setdefault("one_minute_digest", {})
        old_selected = one.get("selected_events", [])
        selection_removed = [
            event.get("event_id")
            for event in old_selected
            if event.get("event_id") in REMOVE_EVENT_IDS
        ]
        one["selected_events"] = selected
        one["actual_duration_sec"] = digest_duration
        one["removed_event_ids_by_user_request"] = sorted(REMOVE_EVENT_IDS)
        digest_selection["updated_at"] = updated_at
        save(DIGEST_SELECTION, digest_selection)

    report = {
        "schema_version": "digest_metadata_cleanup_report.v1",
        "project_id": "layer-x-domain-expert",
        "updated_at": updated_at,
        "active_digest_event_ids": [event["event_id"] for event in digest_events],
        "active_digest_duration_sec": digest_duration,
        "removed_event_ids_by_user_request": sorted(REMOVE_EVENT_IDS),
        "selection_removed_event_ids": selection_removed,
    }
    save(REPORT_PATH, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
