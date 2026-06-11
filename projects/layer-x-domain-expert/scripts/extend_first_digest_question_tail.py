import json
from datetime import datetime, timezone, timedelta
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT / "output" / "reports"
EDIT_PLAN = REPORTS / "edit_plan.json"
DIGEST_SELECTION = REPORTS / "digest_qa_selection.json"
REPORT_PATH = REPORTS / "first_digest_question_tail_extend_report.json"

JST = timezone(timedelta(hours=9))
EVENT_ID = "digest_qa_01_question_01"
TAIL_EXTENSION_SEC = 0.6
CAM_PERSON_02_APP_OFFSET = 7.467854


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def extend_edit_plan() -> dict:
    data = load(EDIT_PLAN)
    timeline = data["timeline"]
    target = next((event for event in timeline if event.get("event_id") == EVENT_ID), None)
    if not target:
        raise SystemExit(f"{EVENT_ID} not found")

    old_timeline_end = float(target["timeline_end"])
    old_source_out = float(target["source"]["out"])
    new_timeline_end = round(old_timeline_end + TAIL_EXTENSION_SEC, 3)
    new_source_out = round(old_source_out + TAIL_EXTENSION_SEC, 3)

    target["timeline_end"] = new_timeline_end
    target["duration"] = round(new_timeline_end - float(target["timeline_start"]), 3)
    target["source"]["out"] = new_source_out
    target["reference_source"]["out"] = new_source_out
    if target.get("audio"):
        target["audio"]["out"] = round(new_source_out + CAM_PERSON_02_APP_OFFSET, 3)
        target["audio"]["timing_reference_out"] = new_source_out
        target["audio"]["reason"] = (
            "Extended by 0.6s so the first digest question finishes naturally before the hard cut."
        )
    for overlay in target.get("overlays", []):
        if overlay.get("type") == "caption" and "めっちゃ大変" in str(overlay.get("text") or ""):
            overlay["end"] = round(float(overlay.get("end") or old_timeline_end) + TAIL_EXTENSION_SEC, 3)
            overlay["source_timecode"] = "00:25:05,820 --> 00:25:09,360"
            overlay["editorial_note"] = (
                "Extended 0.6s beyond the original SRT end so the spoken question is not cut off."
            )
    digest_source = target.setdefault("digest_qa_source", {})
    digest_source["end_timecode"] = "00:25:09,360"
    digest_source["tail_extended_sec"] = TAIL_EXTENSION_SEC
    digest_source["tail_extension_reason"] = (
        "User review: the video cut away before the phrase 'めっちゃ大変でしたとかありますか？' finished."
    )

    shifted = []
    for event in timeline:
        if event is target:
            continue
        if float(event["timeline_start"]) >= old_timeline_end - 1e-6:
            event["timeline_start"] = round(float(event["timeline_start"]) + TAIL_EXTENSION_SEC, 3)
            event["timeline_end"] = round(float(event["timeline_end"]) + TAIL_EXTENSION_SEC, 3)
            shifted.append(event.get("event_id"))

    pacing = data.setdefault("digest_pacing", {})
    for part in pacing.get("parts", []):
        if part.get("part_id") == EVENT_ID:
            part["kept_duration_sec"] = target["duration"]
            part["tail_extended_sec"] = TAIL_EXTENSION_SEC
    one = pacing.setdefault("one_minute_shortening", {})
    for selected in one.get("selection", []):
        if selected.get("event_id") == EVENT_ID:
            selected["local_end"] = round(float(selected.get("local_end") or old_timeline_end) + TAIL_EXTENSION_SEC, 3)
            selected["duration_sec"] = target["duration"]
            selected["reason"] = (
                "Opening question keeps the full spoken ending; extended after user review found the tail was cut."
            )
    if "shortened_digest_duration_sec" in pacing:
        pacing["shortened_digest_duration_sec"] = round(float(pacing["shortened_digest_duration_sec"]) + TAIL_EXTENSION_SEC, 3)
    if "shortened_digest_duration_sec" in one:
        one["shortened_digest_duration_sec"] = round(float(one["shortened_digest_duration_sec"]) + TAIL_EXTENSION_SEC, 3)

    data["updated_at"] = datetime.now(JST).isoformat(timespec="seconds")
    data.setdefault("revision_notes", []).append(
        {
            "updated_at": data["updated_at"],
            "change": "Extended first digest question tail so the spoken question does not cut off.",
            "event_id": EVENT_ID,
            "tail_extension_sec": TAIL_EXTENSION_SEC,
        }
    )
    save(EDIT_PLAN, data)

    return {
        "event_id": EVENT_ID,
        "old_timeline_end": old_timeline_end,
        "new_timeline_end": new_timeline_end,
        "old_source_out": old_source_out,
        "new_source_out": new_source_out,
        "audio_out": target.get("audio", {}).get("out"),
        "shifted_event_count": len(shifted),
        "first_shifted_events": shifted[:8],
    }


def extend_digest_selection() -> dict:
    if not DIGEST_SELECTION.exists():
        return {"updated": False}
    data = load(DIGEST_SELECTION)
    changed = []
    one = data.setdefault("one_minute_digest", {})
    for selected in one.get("selected_events", []):
        if selected.get("event_id") == EVENT_ID:
            selected["local_end"] = round(float(selected.get("local_end") or 0.0) + TAIL_EXTENSION_SEC, 3)
            selected["duration_sec"] = round(float(selected.get("duration_sec") or 0.0) + TAIL_EXTENSION_SEC, 3)
            selected["reason"] = (
                "Opening question keeps the full spoken ending; extended after user review found the tail was cut."
            )
            changed.append(EVENT_ID)
    if "actual_duration_sec" in one:
        one["actual_duration_sec"] = round(float(one["actual_duration_sec"]) + TAIL_EXTENSION_SEC, 3)
    data["updated_at"] = datetime.now(JST).isoformat(timespec="seconds")
    save(DIGEST_SELECTION, data)
    return {"updated": True, "changed_selected_events": changed}


def main() -> None:
    report = {
        "schema_version": "first_digest_question_tail_extend_report.v1",
        "project_id": "layer-x-domain-expert",
        "updated_at": datetime.now(JST).isoformat(timespec="seconds"),
        "tail_extension_sec": TAIL_EXTENSION_SEC,
        "reason": "The rendered question cut before 'めっちゃ大変でしたとかありますか？' finished.",
    }
    report["edit_plan"] = extend_edit_plan()
    report["digest_selection"] = extend_digest_selection()
    save(REPORT_PATH, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
