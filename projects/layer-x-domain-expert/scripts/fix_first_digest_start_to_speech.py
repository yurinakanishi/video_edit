from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[1]
REPORTS_DIR = PROJECT_DIR / "output" / "reports"
EDIT_PLAN_PATH = REPORTS_DIR / "edit_plan.json"
DIGEST_QA_PATH = REPORTS_DIR / "digest_qa_selection.json"
PREVIEW_REPORT_PATH = REPORTS_DIR / "test_project1_style_preview_report.json"
REPORT_PATH = REPORTS_DIR / "first_digest_start_to_speech_fix_report.json"

JST = timezone(timedelta(hours=9))
EVENT_ID = "digest_qa_01_question_01"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fmt_timecode(seconds: float) -> str:
    ms_total = round(seconds * 1000)
    h = ms_total // 3_600_000
    ms_total %= 3_600_000
    m = ms_total // 60_000
    ms_total %= 60_000
    s = ms_total // 1000
    ms = ms_total % 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def event_duration(event: dict[str, Any]) -> float:
    return round(float(event.get("timeline_end") or 0.0) - float(event.get("timeline_start") or 0.0), 3)


def digest_duration(events: list[dict[str, Any]]) -> float:
    return round(sum(event_duration(event) for event in events if event.get("section") == "digest"), 3)


def recompute_timeline(events: list[dict[str, Any]]) -> None:
    cursor = 0.0
    for event in events:
        duration = event_duration(event)
        event["timeline_start"] = round(cursor, 3)
        event["timeline_end"] = round(cursor + duration, 3)
        cursor = round(cursor + duration, 3)


def caption_overlays(event: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        overlay
        for overlay in event.get("overlays", [])
        if isinstance(overlay, dict) and overlay.get("type") == "caption"
    ]


def first_caption_speech_start(caption: dict[str, Any]) -> float:
    metadata = caption.get("metadata") if isinstance(caption.get("metadata"), dict) else {}
    if metadata.get("caption_start_sec") is not None:
        return float(metadata["caption_start_sec"])
    alignment = caption.get("audio_alignment") if isinstance(caption.get("audio_alignment"), dict) else {}
    window = alignment.get("speech_window_sec")
    if isinstance(window, list) and window:
        return float(window[0])
    raise RuntimeError("First digest caption does not have an absolute speech start")


def shift_event_start(event: dict[str, Any], trim_sec: float) -> None:
    for key in ("source", "reference_source"):
        range_obj = event.get(key)
        if isinstance(range_obj, dict) and range_obj.get("in") is not None:
            range_obj["in"] = round(float(range_obj["in"]) + trim_sec, 3)

    audio = event.get("audio")
    if isinstance(audio, dict):
        for key in ("in", "timing_reference_in"):
            if audio.get(key) is not None:
                audio[key] = round(float(audio[key]) + trim_sec, 3)
        audio["reason"] = "Trimmed so the first digest video/audio begin exactly at the spoken phrase '開発に関わる仕事をする中で'."

    for caption in caption_overlays(event):
        if caption.get("start") is not None:
            caption["start"] = round(max(0.0, float(caption["start"]) - trim_sec), 3)
        if caption.get("end") is not None:
            caption["end"] = round(max(0.0, float(caption["end"]) - trim_sec), 3)

    event["duration"] = round(event_duration(event) - trim_sec, 3)
    event["timeline_end"] = round(float(event.get("timeline_start") or 0.0) + float(event["duration"]), 3)


def sync_caption_metadata(event: dict[str, Any]) -> None:
    ref_in = float(event["reference_source"]["in"])
    for caption in caption_overlays(event):
        metadata = caption.get("metadata") if isinstance(caption.get("metadata"), dict) else {}
        speech_start = metadata.get("caption_start_sec")
        speech_end = metadata.get("caption_end_sec")
        if speech_start is not None:
            caption["start"] = round(max(0.0, float(speech_start) - ref_in), 3)
        if speech_end is not None:
            hold = float(metadata.get("digest_caption_hold_after_speech_sec") or 0.0)
            caption["end"] = round(max(float(caption.get("end") or 0.0), float(speech_end) + hold - ref_in), 3)

        source_end = metadata.get("source_end_sec") or speech_end
        if metadata.get("source_start_sec") is not None:
            metadata["source_start_sec"] = max(ref_in, float(metadata["source_start_sec"]))
        if caption.get("source_timecode") is not None and source_end is not None:
            caption["source_timecode"] = f"{fmt_timecode(ref_in + float(caption.get('start') or 0.0))} --> {fmt_timecode(float(source_end))}"

        alignment = caption.get("audio_alignment") if isinstance(caption.get("audio_alignment"), dict) else {}
        if isinstance(alignment, dict):
            source_window = alignment.get("source_window_sec")
            if isinstance(source_window, list) and source_window:
                source_window[0] = round(max(ref_in, float(source_window[0])), 3)
            speech_window = alignment.get("speech_window_sec")
            if isinstance(speech_window, list) and len(speech_window) == 2 and speech_start is not None:
                speech_window[0] = round(float(speech_start), 3)


def update_digest_pacing(plan: dict[str, Any], events: list[dict[str, Any]]) -> None:
    duration_sec = digest_duration(events)
    pacing = plan.get("digest_pacing") if isinstance(plan.get("digest_pacing"), dict) else {}
    pacing["shortened_digest_duration_sec"] = duration_sec
    for item in pacing.get("parts", []):
        if item.get("part_id") == EVENT_ID:
            item["kept_duration_sec"] = next(event_duration(event) for event in events if event.get("event_id") == EVENT_ID)
            item["policy"] = "active_digest_event_starts_at_spoken_phrase"
    one_minute = pacing.get("one_minute_shortening")
    if isinstance(one_minute, dict):
        one_minute["shortened_digest_duration_sec"] = duration_sec
        for item in one_minute.get("selection", []):
            if item.get("event_id") == EVENT_ID:
                item["local_start"] = 0.0
                item["local_end"] = next(event_duration(event) for event in events if event.get("event_id") == EVENT_ID)
                item["duration_sec"] = item["local_end"]
                item["reason"] = "Opening digest now starts exactly at the spoken phrase '開発に関わる仕事をする中で'."
    plan["digest_pacing"] = pacing
    if isinstance(plan.get("metadata"), dict) and isinstance(plan["metadata"].get("digest_one_minute_shortening"), dict):
        plan["metadata"]["digest_one_minute_shortening"]["actual_duration_sec"] = duration_sec


def update_digest_qa(duration_sec: float, event_duration_sec: float, now: str) -> None:
    if not DIGEST_QA_PATH.exists():
        return
    data = read_json(DIGEST_QA_PATH)
    one_minute = data.get("one_minute_digest")
    if isinstance(one_minute, dict):
        one_minute["actual_duration_sec"] = duration_sec
        for item in one_minute.get("selected_events", []):
            if item.get("event_id") == EVENT_ID:
                item["local_start"] = 0.0
                item["local_end"] = event_duration_sec
                item["duration_sec"] = event_duration_sec
                item["reason"] = "Opening digest now starts exactly at the spoken phrase '開発に関わる仕事をする中で'."
    data["updated_at"] = now
    data.setdefault("change_log", []).append(
        {
            "updated_at": now,
            "change": "Fixed first digest video/audio/caption to start at the spoken '開発に関わる' phrase.",
            "event_id": EVENT_ID,
        }
    )
    write_json(DIGEST_QA_PATH, data)


def update_preview_report(now: str) -> None:
    if not PREVIEW_REPORT_PATH.exists():
        return
    report = read_json(PREVIEW_REPORT_PATH)
    report["updated_at"] = now
    report["output"] = None
    report["status"] = "no_current_trusted_preview_after_first_digest_start_fix"
    report["reason"] = "The first digest source start and caption timing were changed after the last preview render. Existing rendered preview and segment cache are stale."
    report["next_render_required"] = True
    report["first_digest_start_to_speech_fix_report"] = str(REPORT_PATH.relative_to(PROJECT_DIR))
    write_json(PREVIEW_REPORT_PATH, report)


def main() -> None:
    plan = read_json(EDIT_PLAN_PATH)
    events = [event for event in plan.get("timeline", []) if isinstance(event, dict)]
    event = next((item for item in events if item.get("event_id") == EVENT_ID), None)
    if event is None:
        raise SystemExit(f"{EVENT_ID} not found")
    captions = caption_overlays(event)
    if not captions:
        raise SystemExit(f"{EVENT_ID} has no captions")

    old_event = json.loads(json.dumps(event, ensure_ascii=False))
    old_ref_in = float(event["reference_source"]["in"])
    speech_start = first_caption_speech_start(captions[0])
    trim_sec = round(max(0.0, speech_start - old_ref_in), 3)
    if trim_sec > 0:
        shift_event_start(event, trim_sec)
    sync_caption_metadata(event)

    source_start = float(event["reference_source"]["in"])
    event.setdefault("digest_qa_source", {})["start_timecode"] = fmt_timecode(source_start)
    event["digest_qa_source"]["start_synced_to_spoken_caption"] = {
        "previous_reference_in_sec": old_ref_in,
        "new_reference_in_sec": source_start,
        "trim_sec_from_previous_source": trim_sec,
        "kept_start_phrase": "開発に関わる仕事をする中で",
    }
    event["reason"] = "Opening digest question starts exactly at the spoken phrase '開発に関わる仕事をする中で'."

    recompute_timeline(events)
    duration_sec = digest_duration(events)
    event_duration_sec = event_duration(event)
    update_digest_pacing(plan, events)
    now = datetime.now(JST).isoformat(timespec="seconds")
    plan["updated_at"] = now
    plan.setdefault("revision_notes", []).append(
        {
            "updated_at": now,
            "change": "Fixed first digest video/audio/caption to start at the spoken '開発に関わる' phrase.",
            "event_id": EVENT_ID,
            "trim_sec_from_previous_source": trim_sec,
        }
    )
    write_json(EDIT_PLAN_PATH, plan)
    update_digest_qa(duration_sec, event_duration_sec, now)
    update_preview_report(now)

    report = {
        "schema_version": "first_digest_start_to_speech_fix.v1",
        "project_id": "layer-x-domain-expert",
        "updated_at": now,
        "event_id": EVENT_ID,
        "trim_sec_from_previous_source": trim_sec,
        "old_reference_in_sec": old_ref_in,
        "new_reference_in_sec": source_start,
        "old_event": {
            "source": old_event.get("source"),
            "reference_source": old_event.get("reference_source"),
            "audio": old_event.get("audio"),
            "captions": [
                {"text": item.get("text"), "start": item.get("start"), "end": item.get("end")}
                for item in caption_overlays(old_event)
            ],
        },
        "new_event": {
            "source": event.get("source"),
            "reference_source": event.get("reference_source"),
            "audio": event.get("audio"),
            "duration_sec": event_duration_sec,
            "captions": [
                {"text": item.get("text"), "start": item.get("start"), "end": item.get("end")}
                for item in caption_overlays(event)
            ],
        },
        "digest_duration_sec": duration_sec,
    }
    write_json(REPORT_PATH, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
