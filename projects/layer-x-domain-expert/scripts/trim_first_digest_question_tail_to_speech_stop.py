from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[1]
REPORTS_DIR = PROJECT_DIR / "output" / "reports"
EDIT_PLAN_PATH = REPORTS_DIR / "edit_plan.json"
DIGEST_QA_PATH = REPORTS_DIR / "digest_qa_selection.json"
REPORT_PATH = REPORTS_DIR / "first_digest_question_tail_trim_report.json"

JST = timezone(timedelta(hours=9))
EVENT_ID = "digest_qa_01_question_01"
TAIL_TRIM_SEC = 0.6


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def events_from_plan(plan: dict[str, Any]) -> list[dict[str, Any]]:
    timeline = plan.get("timeline")
    if isinstance(timeline, dict):
        events = timeline.get("events")
    else:
        events = timeline
    if not isinstance(events, list):
        raise TypeError("edit_plan.json timeline must be a list or dict containing events")
    return events


def event_duration(event: dict[str, Any]) -> float:
    return round(float(event.get("timeline_end", 0.0)) - float(event.get("timeline_start", 0.0)), 3)


def recompute_timeline(events: list[dict[str, Any]]) -> None:
    cursor = 0.0
    for event in events:
        duration = round(float(event.get("duration", event_duration(event))), 3)
        event["timeline_start"] = round(cursor, 3)
        event["timeline_end"] = round(cursor + duration, 3)
        cursor = round(cursor + duration, 3)


def digest_duration(events: list[dict[str, Any]]) -> float:
    return round(
        sum(float(event.get("duration", event_duration(event))) for event in events if event.get("section") == "digest"),
        3,
    )


def trim_out(range_obj: dict[str, Any], amount: float) -> None:
    if "out" in range_obj:
        range_obj["out"] = round(float(range_obj["out"]) - amount, 3)


def clamp_caption_overlays(event: dict[str, Any], new_duration: float) -> list[dict[str, Any]]:
    changed = []
    source_in = float((event.get("reference_source") or event.get("source") or {}).get("in", 0.0))
    source_out = round(source_in + new_duration, 3)
    for overlay in event.get("overlays", []):
        if not isinstance(overlay, dict) or overlay.get("type") != "caption":
            continue
        old_end = float(overlay.get("end", new_duration))
        if old_end > new_duration:
            overlay["end"] = new_duration
            changed.append({"text": overlay.get("text"), "old_end": old_end, "new_end": new_duration})
        if "これめっちゃ大変" in str(overlay.get("text") or ""):
            overlay["editorial_note"] = (
                "Trimmed to the left interviewer's speech stop; displayed text remains editorially complete."
            )
            metadata = overlay.setdefault("metadata", {})
            metadata["tail_trimmed_to_speech_stop"] = True
            metadata["caption_end_sec"] = source_out
            metadata["source_end_sec"] = source_out
            alignment = overlay.get("audio_alignment")
            if isinstance(alignment, dict):
                if isinstance(alignment.get("source_window_sec"), list) and len(alignment["source_window_sec"]) == 2:
                    alignment["source_window_sec"][1] = source_out
                if isinstance(alignment.get("speech_window_sec"), list) and len(alignment["speech_window_sec"]) == 2:
                    alignment["speech_window_sec"][1] = source_out
    return changed


def update_digest_sidecar(digest_duration_sec: float, trim_amount: float) -> dict[str, Any]:
    if not DIGEST_QA_PATH.exists():
        return {"updated": False}

    data = read_json(DIGEST_QA_PATH)
    changed = []
    one_minute = data.get("one_minute_digest")
    if isinstance(one_minute, dict):
        if "actual_duration_sec" in one_minute:
            one_minute["actual_duration_sec"] = digest_duration_sec
        for item in one_minute.get("selected_events", []):
            if item.get("event_id") == EVENT_ID:
                if "local_end" in item:
                    item["local_end"] = round(float(item["local_end"]) - trim_amount, 3)
                if "duration_sec" in item:
                    item["duration_sec"] = round(float(item["duration_sec"]) - trim_amount, 3)
                item["reason"] = (
                    "Opening question cuts at the left interviewer's speech stop; caption text remains complete."
                )
                changed.append(EVENT_ID)
    data["updated_at"] = datetime.now(JST).isoformat(timespec="seconds")
    write_json(DIGEST_QA_PATH, data)
    return {"updated": True, "changed_selected_events": changed}


def main() -> None:
    plan = read_json(EDIT_PLAN_PATH)
    events = events_from_plan(plan)
    target = next((event for event in events if event.get("event_id") == EVENT_ID), None)
    if target is None:
        raise RuntimeError(f"{EVENT_ID} not found")

    old_duration = event_duration(target)
    digest_source = target.get("digest_qa_source") if isinstance(target.get("digest_qa_source"), dict) else {}
    already_trimmed = "tail_trimmed_to_speech_stop" in digest_source
    trim_amount = 0.0 if already_trimmed else TAIL_TRIM_SEC
    new_duration = round(old_duration - trim_amount, 3)
    if new_duration <= 0:
        raise RuntimeError(f"tail trim {trim_amount} is longer than event duration {old_duration}")

    old_source = dict(target.get("source") or {})
    old_reference_source = dict(target.get("reference_source") or {})
    old_audio = dict(target.get("audio") or {})

    if isinstance(target.get("source"), dict):
        trim_out(target["source"], trim_amount)
    if isinstance(target.get("reference_source"), dict):
        trim_out(target["reference_source"], trim_amount)
    if isinstance(target.get("audio"), dict):
        trim_out(target["audio"], trim_amount)
        if "timing_reference_out" in target["audio"]:
            target["audio"]["timing_reference_out"] = round(float(target["audio"]["timing_reference_out"]) - trim_amount, 3)
        target["audio"]["reason"] = (
            "Trimmed at the left interviewer's speech stop so the digest question hard-cuts without dead air."
        )

    target["duration"] = new_duration
    target["timeline_end"] = round(float(target.get("timeline_start", 0.0)) + new_duration, 3)
    overlay_changes = clamp_caption_overlays(target, new_duration)

    digest_source["tail_trimmed_to_speech_stop"] = {
        "trim_sec": TAIL_TRIM_SEC,
        "kept_caption_text": "これめっちゃ大変でしたとかありますか？",
        "reason": "User requested a hard cut at the left interviewer's speech stop.",
    }
    if "tail_extended_sec" in digest_source:
        digest_source["tail_extended_sec_previous"] = digest_source.pop("tail_extended_sec")
    if "tail_extension_reason" in digest_source:
        digest_source["tail_extension_reason_previous"] = digest_source.pop("tail_extension_reason")
    target["digest_qa_source"] = digest_source

    recompute_timeline(events)
    digest_duration_sec = digest_duration(events)

    if isinstance(plan.get("digest_pacing"), dict):
        plan["digest_pacing"]["shortened_digest_duration_sec"] = digest_duration_sec
        if isinstance(plan["digest_pacing"].get("one_minute_shortening"), dict):
            plan["digest_pacing"]["one_minute_shortening"]["shortened_digest_duration_sec"] = digest_duration_sec
    plan.setdefault("metadata", {})["first_digest_question_tail_trim"] = {
        "enabled": True,
        "event_id": EVENT_ID,
        "trim_sec": TAIL_TRIM_SEC,
        "actual_digest_duration_sec": digest_duration_sec,
        "report": str(REPORT_PATH),
    }
    plan["updated_at"] = datetime.now(JST).isoformat(timespec="seconds")
    plan.setdefault("revision_notes", []).append(
        {
            "updated_at": plan["updated_at"],
            "change": "Trimmed first digest question tail to the left interviewer's speech stop.",
            "event_id": EVENT_ID,
            "trim_sec": trim_amount,
        }
    )

    write_json(EDIT_PLAN_PATH, plan)
    digest_sidecar = update_digest_sidecar(digest_duration_sec, trim_amount)
    report = {
        "schema_version": "first_digest_question_tail_trim.v1",
        "updated_at": plan["updated_at"],
        "event_id": EVENT_ID,
        "trim_sec": trim_amount,
        "already_trimmed": already_trimmed,
        "old_duration_sec": old_duration,
        "new_duration_sec": new_duration,
        "old_source": old_source,
        "new_source": target.get("source"),
        "old_reference_source": old_reference_source,
        "new_reference_source": target.get("reference_source"),
        "old_audio": old_audio,
        "new_audio": target.get("audio"),
        "overlay_changes": overlay_changes,
        "digest_duration_sec": digest_duration_sec,
        "digest_sidecar": digest_sidecar,
    }
    write_json(REPORT_PATH, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
