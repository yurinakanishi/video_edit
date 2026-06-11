from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[1]
REPORTS_DIR = PROJECT_DIR / "output" / "reports"
EDIT_PLAN_PATH = REPORTS_DIR / "edit_plan.json"
REPORT_PATH = REPORTS_DIR / "digest_caption_hold_sync_fix_report.json"

JST = timezone(timedelta(hours=9))
HOLD_AFTER_SPEECH_SEC = 0.25
MIN_GAP_BEFORE_NEXT_CAPTION_SEC = 0.08
MAX_TAIL_EXTENSION_SEC = 0.25
NO_TAIL_EXTEND_EVENTS = {"digest_qa_01_question_01"}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def event_duration(event: dict[str, Any]) -> float:
    return round(float(event.get("timeline_end") or 0.0) - float(event.get("timeline_start") or 0.0), 3)


def set_out(range_obj: dict[str, Any], new_out: float) -> None:
    if "out" in range_obj:
        range_obj["out"] = round(new_out, 3)


def trim_or_extend_event_tail(event: dict[str, Any], extension: float) -> None:
    if extension <= 0:
        return
    event["duration"] = round(float(event.get("duration") or event_duration(event)) + extension, 3)
    event["timeline_end"] = round(float(event.get("timeline_end") or 0.0) + extension, 3)
    if isinstance(event.get("source"), dict):
        set_out(event["source"], float(event["source"].get("out") or 0.0) + extension)
    if isinstance(event.get("reference_source"), dict):
        set_out(event["reference_source"], float(event["reference_source"].get("out") or 0.0) + extension)
    if isinstance(event.get("audio"), dict):
        set_out(event["audio"], float(event["audio"].get("out") or 0.0) + extension)
        if "timing_reference_out" in event["audio"]:
            event["audio"]["timing_reference_out"] = round(float(event["audio"]["timing_reference_out"]) + extension, 3)
        event["audio"]["reason"] = (
            "Extended minimally so digest caption remains visible through the spoken phrase ending."
        )


def recompute_timeline(events: list[dict[str, Any]]) -> None:
    cursor = 0.0
    for event in events:
        duration = event_duration(event)
        event["timeline_start"] = round(cursor, 3)
        event["timeline_end"] = round(cursor + duration, 3)
        cursor = round(cursor + duration, 3)


def digest_duration(events: list[dict[str, Any]]) -> float:
    return round(sum(event_duration(event) for event in events if event.get("section") == "digest"), 3)


def speech_end_local(event: dict[str, Any], overlay: dict[str, Any]) -> float | None:
    reference = event.get("reference_source") if isinstance(event.get("reference_source"), dict) else event.get("source")
    ref_in = float((reference or {}).get("in") or 0.0)
    alignment = overlay.get("audio_alignment") if isinstance(overlay.get("audio_alignment"), dict) else {}
    window = alignment.get("speech_window_sec")
    if not isinstance(window, list) or len(window) != 2:
        return None
    return round(float(window[1]) - ref_in, 3)


def update_digest_pacing(plan: dict[str, Any], events: list[dict[str, Any]]) -> None:
    duration_sec = digest_duration(events)
    if isinstance(plan.get("digest_pacing"), dict):
        plan["digest_pacing"]["shortened_digest_duration_sec"] = duration_sec
        if isinstance(plan["digest_pacing"].get("one_minute_shortening"), dict):
            plan["digest_pacing"]["one_minute_shortening"]["shortened_digest_duration_sec"] = duration_sec
    if isinstance(plan.get("metadata"), dict) and isinstance(plan["metadata"].get("digest_one_minute_shortening"), dict):
        plan["metadata"]["digest_one_minute_shortening"]["actual_duration_sec"] = duration_sec


def main() -> None:
    plan = read_json(EDIT_PLAN_PATH)
    events = [event for event in plan.get("timeline", []) if isinstance(event, dict)]
    changes = []

    for event in events:
        if event.get("section") != "digest":
            continue
        captions = [overlay for overlay in event.get("overlays", []) if isinstance(overlay, dict) and overlay.get("type") == "caption"]
        if not captions:
            continue
        duration = event_duration(event)
        required_tail_extension = 0.0

        for index, caption in enumerate(captions):
            old_end = round(float(caption.get("end") or 0.0), 3)
            spoken_end = speech_end_local(event, caption)
            if spoken_end is None:
                continue
            target_end = round(spoken_end + HOLD_AFTER_SPEECH_SEC, 3)
            if index + 1 < len(captions):
                next_start = round(float(captions[index + 1].get("start") or 0.0), 3)
                target_end = min(target_end, round(next_start - MIN_GAP_BEFORE_NEXT_CAPTION_SEC, 3))
            else:
                if event.get("event_id") in NO_TAIL_EXTEND_EVENTS:
                    target_end = min(target_end, duration)
                elif target_end > duration:
                    extension = min(MAX_TAIL_EXTENSION_SEC, round(target_end - duration, 3))
                    required_tail_extension = max(required_tail_extension, extension)
                    target_end = round(duration + extension, 3)

            target_end = max(old_end, round(target_end, 3))
            if target_end > old_end + 0.001:
                caption["end"] = target_end
                metadata = caption.setdefault("metadata", {})
                metadata["digest_caption_hold_after_speech_sec"] = round(target_end - spoken_end, 3)
                metadata["digest_caption_hold_sync_fixed"] = True
                changes.append(
                    {
                        "event_id": event.get("event_id"),
                        "text": caption.get("text"),
                        "old_end": old_end,
                        "new_end": target_end,
                        "spoken_end_local": spoken_end,
                    }
                )

        if required_tail_extension > 0:
            trim_or_extend_event_tail(event, required_tail_extension)
            changes.append(
                {
                    "event_id": event.get("event_id"),
                    "event_tail_extended_sec": required_tail_extension,
                    "reason": "last digest caption needed visible hold through speech ending",
                }
            )

    recompute_timeline(events)
    update_digest_pacing(plan, events)
    now = datetime.now(JST).isoformat(timespec="seconds")
    plan["updated_at"] = now
    plan.setdefault("revision_notes", []).append(
        {
            "updated_at": now,
            "change": "Extended digest caption visibility so captions remain through spoken phrase endings.",
            "hold_after_speech_sec": HOLD_AFTER_SPEECH_SEC,
            "changed_count": len(changes),
        }
    )
    write_json(EDIT_PLAN_PATH, plan)
    report = {
        "schema_version": "digest_caption_hold_sync_fix.v1",
        "updated_at": now,
        "hold_after_speech_sec": HOLD_AFTER_SPEECH_SEC,
        "min_gap_before_next_caption_sec": MIN_GAP_BEFORE_NEXT_CAPTION_SEC,
        "max_tail_extension_sec": MAX_TAIL_EXTENSION_SEC,
        "no_tail_extend_events": sorted(NO_TAIL_EXTEND_EVENTS),
        "changed_count": len(changes),
        "changes": changes,
        "digest_duration_sec": digest_duration(events),
    }
    write_json(REPORT_PATH, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
