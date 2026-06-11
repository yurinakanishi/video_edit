from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[1]
REPORTS_DIR = PROJECT_DIR / "output" / "reports"
EDIT_PLAN_PATH = REPORTS_DIR / "edit_plan.json"
ONE_MINUTE_REPORT_PATH = REPORTS_DIR / "digest_one_minute_shortening_report.json"
DIGEST_QA_PATH = REPORTS_DIR / "digest_qa_selection.json"
REPORT_PATH = REPORTS_DIR / "first_digest_question_trim_report.json"

EVENT_ID = "digest_qa_01_question_01"
TRIM_START_SEC = 2.10


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fmt_timecode(seconds: float) -> str:
    ms_total = round(seconds * 1000)
    h = ms_total // 3_600_000
    ms_total %= 3_600_000
    m = ms_total // 60_000
    ms_total %= 60_000
    s = ms_total // 1000
    ms = ms_total % 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


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
    return max(0.001, float(event.get("timeline_end", 0.0)) - float(event.get("timeline_start", 0.0)))


def shift_range_start(range_obj: dict[str, Any], amount: float) -> None:
    if "in" in range_obj:
        range_obj["in"] = round(float(range_obj["in"]) + amount, 3)


def trim_audio(audio: dict[str, Any], amount: float) -> None:
    for key in ("in", "timing_reference_in"):
        if key in audio:
            audio[key] = round(float(audio[key]) + amount, 3)


def recompute_timeline(events: list[dict[str, Any]]) -> None:
    cursor = 0.0
    for event in events:
        duration = event_duration(event)
        event["timeline_start"] = round(cursor, 3)
        event["timeline_end"] = round(cursor + duration, 3)
        cursor += duration


def digest_duration(events: list[dict[str, Any]]) -> float:
    return round(sum(event_duration(event) for event in events if isinstance(event, dict) and event.get("section") == "digest"), 3)


def update_one_minute_reports(events: list[dict[str, Any]], duration_sec: float) -> None:
    if ONE_MINUTE_REPORT_PATH.exists():
        report = read_json(ONE_MINUTE_REPORT_PATH)
        report["shortened_digest_duration_sec"] = duration_sec
        if "original_digest_duration_sec" in report:
            report["removed_digest_duration_sec"] = round(float(report["original_digest_duration_sec"]) - duration_sec, 3)
        for item in report.get("kept", []):
            if item.get("event_id") == EVENT_ID:
                item["local_start"] = TRIM_START_SEC
                item["local_end"] = 8.04
                item["duration_sec"] = round(8.04 - TRIM_START_SEC, 3)
                item["reason"] = "Opening question trimmed so video/audio begin at the captioned phrase."
        write_json(ONE_MINUTE_REPORT_PATH, report)

    if DIGEST_QA_PATH.exists():
        digest_qa = read_json(DIGEST_QA_PATH)
        one_minute = digest_qa.get("one_minute_digest")
        if isinstance(one_minute, dict):
            one_minute["actual_duration_sec"] = duration_sec
            for item in one_minute.get("selected_events", []):
                if item.get("event_id") == EVENT_ID:
                    item["local_start"] = TRIM_START_SEC
                    item["local_end"] = 8.04
                    item["duration_sec"] = round(8.04 - TRIM_START_SEC, 3)
                    item["reason"] = "Opening question trimmed so video/audio begin at the captioned phrase."
        write_json(DIGEST_QA_PATH, digest_qa)


def main() -> None:
    plan = read_json(EDIT_PLAN_PATH)
    events = events_from_plan(plan)
    target = next((event for event in events if event.get("event_id") == EVENT_ID), None)
    if target is None:
        raise RuntimeError(f"{EVENT_ID} not found")

    already_trimmed = isinstance(target.get("digest_qa_source"), dict) and "trimmed_leading_unsubtitled_phrase" in target["digest_qa_source"]
    old_duration = event_duration(target)
    if not already_trimmed and TRIM_START_SEC >= old_duration:
        raise RuntimeError(f"trim amount {TRIM_START_SEC} is longer than event duration {old_duration}")

    old_source = dict(target.get("source") or {})
    old_reference = dict(target.get("reference_source") or {})
    old_audio = dict(target.get("audio") or {})

    if not already_trimmed:
        if isinstance(target.get("source"), dict):
            shift_range_start(target["source"], TRIM_START_SEC)
        if isinstance(target.get("reference_source"), dict):
            shift_range_start(target["reference_source"], TRIM_START_SEC)
        if isinstance(target.get("audio"), dict):
            trim_audio(target["audio"], TRIM_START_SEC)

    new_duration = round(old_duration if already_trimmed else old_duration - TRIM_START_SEC, 3)
    target["duration"] = new_duration
    target["timeline_end"] = round(float(target.get("timeline_start") or 0.0) + new_duration, 3)

    captions = [overlay for overlay in target.get("overlays", []) if isinstance(overlay, dict) and overlay.get("type") == "caption"]
    if len(captions) >= 2:
        first_end = round(min(new_duration, 3.0), 3)
        captions[0]["start"] = 0.0
        captions[0]["end"] = first_end
        captions[0]["source_timecode"] = f"{fmt_timecode(float((target.get('reference_source') or {}).get('in', 0.0)))} --> {fmt_timecode(float((target.get('reference_source') or {}).get('in', 0.0)) + first_end)}"
        captions[0]["editorial_note"] = "Trimmed leading phrase 'ちなみにお二人の中でこれまで' so video/audio begin at '開発'."
        captions[1]["start"] = first_end
        captions[1]["end"] = new_duration
        captions[1]["source_timecode"] = f"{fmt_timecode(float((target.get('reference_source') or {}).get('in', 0.0)) + first_end)} --> {fmt_timecode(float((target.get('reference_source') or {}).get('out', 0.0)))}"

    digest_source = target.get("digest_qa_source") if isinstance(target.get("digest_qa_source"), dict) else {}
    digest_source["trimmed_leading_unsubtitled_phrase"] = {
        "trim_sec": TRIM_START_SEC,
        "removed_phrase": "ちなみにお二人の中でこれまで",
        "kept_start_phrase": "開発に関わる仕事をする中で",
    }
    target["digest_qa_source"] = digest_source
    target["reason"] = str(target.get("reason") or "") + " First digest question starts at the captioned phrase '開発'."

    recompute_timeline(events)

    digest_duration_sec = digest_duration(events)
    if isinstance(plan.get("digest_pacing"), dict):
        plan["digest_pacing"]["shortened_digest_duration_sec"] = digest_duration_sec
        if isinstance(plan["digest_pacing"].get("one_minute_shortening"), dict):
            plan["digest_pacing"]["one_minute_shortening"]["shortened_digest_duration_sec"] = digest_duration_sec
            if "original_digest_duration_sec" in plan["digest_pacing"]["one_minute_shortening"]:
                plan["digest_pacing"]["one_minute_shortening"]["removed_digest_duration_sec"] = round(
                    float(plan["digest_pacing"]["one_minute_shortening"]["original_digest_duration_sec"]) - digest_duration_sec,
                    3,
                )
    if isinstance(plan.get("metadata"), dict) and isinstance(plan["metadata"].get("digest_one_minute_shortening"), dict):
        plan["metadata"]["digest_one_minute_shortening"]["actual_duration_sec"] = digest_duration_sec
    plan.setdefault("metadata", {})["first_digest_question_trim"] = {
        "enabled": True,
        "event_id": EVENT_ID,
        "trim_sec": TRIM_START_SEC,
        "actual_digest_duration_sec": digest_duration_sec,
        "report": str(REPORT_PATH),
    }

    write_json(EDIT_PLAN_PATH, plan)
    update_one_minute_reports(events, digest_duration_sec)
    report = {
        "schema_version": "first_digest_question_trim.v1",
        "event_id": EVENT_ID,
        "trim_sec": TRIM_START_SEC,
        "already_trimmed": already_trimmed,
        "old_duration_sec": round(old_duration, 3),
        "new_duration_sec": new_duration,
        "digest_duration_sec": digest_duration_sec,
        "old_source": old_source,
        "new_source": target.get("source"),
        "old_reference_source": old_reference,
        "new_reference_source": target.get("reference_source"),
        "old_audio": old_audio,
        "new_audio": target.get("audio"),
        "removed_phrase": "ちなみにお二人の中でこれまで",
        "kept_start_phrase": "開発に関わる仕事をする中で",
    }
    write_json(REPORT_PATH, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
