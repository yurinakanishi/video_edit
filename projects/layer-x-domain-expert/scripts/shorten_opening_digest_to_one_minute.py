from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[1]
REPORTS_DIR = PROJECT_DIR / "output" / "reports"
EDIT_PLAN_PATH = REPORTS_DIR / "edit_plan.json"
DIGEST_QA_PATH = REPORTS_DIR / "digest_qa_selection.json"
REPORT_PATH = REPORTS_DIR / "digest_one_minute_shortening_report.json"


# Keep the strongest editorial beats only. Times are local to each existing
# digest event, so the source/audio sync model remains stable after trimming.
SELECTED_DIGEST_RANGES: list[dict[str, Any]] = [
    {
        "event_id": "digest_qa_01_question_01",
        "ranges": [(0.0, 8.04)],
        "reason": "Opening question: the digest needs the first concrete prompt.",
    },
    {
        "event_id": "digest_qa_01_answer_02",
        "ranges": [(0.0, 9.60)],
        "reason": "Core answer: verbalizing implicit work habits was hard.",
    },
    {
        "event_id": "digest_qa_01_answer_03",
        "ranges": [(0.0, 3.50)],
        "reason": "Punchline: verbalizing the previous default.",
    },
    {
        "event_id": "digest_qa_02_question_context_01",
        "ranges": [(0.0, 8.48)],
        "reason": "Sets up the domain expert knowledge hurdle.",
    },
    {
        "event_id": "digest_qa_02_answer_02",
        "ranges": [(0.0, 8.56)],
        "reason": "Shows that engineers also research the domain deeply.",
    },
    {
        "event_id": "digest_qa_03_answer_01",
        "ranges": [(0.0, 8.88)],
        "reason": "Keeps the strongest why-question pressure section and removes the trailing explanation.",
    },
    {
        "event_id": "digest_qa_04_answer_02",
        "ranges": [(0.0, 3.36), (6.72, 10.60), (12.62, 15.42)],
        "reason": "AI-era role shift: sharpened expectations, not just writing specs, but defining what to realize.",
    },
    {
        "event_id": "digest_qa_05_answer_02",
        "ranges": [(0.0, 6.00)],
        "reason": "Closing takeaway: the career path is recommended.",
    },
]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def timeline_events(plan: dict[str, Any]) -> list[dict[str, Any]]:
    timeline = plan.get("timeline")
    if isinstance(timeline, dict):
        events = timeline.get("events")
    else:
        events = timeline
    if not isinstance(events, list):
        raise TypeError("edit_plan.json timeline must be a list or a dict containing events")
    return events


def set_timeline_events(plan: dict[str, Any], events: list[dict[str, Any]]) -> None:
    if isinstance(plan.get("timeline"), dict):
        plan["timeline"]["events"] = events
    else:
        plan["timeline"] = events


def event_duration(event: dict[str, Any]) -> float:
    return max(0.001, float(event.get("timeline_end", 0.0)) - float(event.get("timeline_start", 0.0)))


def shift_media_range(media_range: dict[str, Any], local_start: float, local_end: float) -> dict[str, Any]:
    result = deepcopy(media_range)
    start = float(media_range.get("in") or 0.0)
    result["in"] = round(start + local_start, 3)
    result["out"] = round(start + local_end, 3)
    return result


def shifted_overlay(overlay: dict[str, Any], local_start: float, local_end: float) -> dict[str, Any] | None:
    duration = local_end - local_start
    result = deepcopy(overlay)
    if "start" not in result and "end" not in result:
        return result

    start = float(result.get("start") or 0.0)
    end = float(result.get("end") if result.get("end") is not None else duration)
    if end <= local_start or start >= local_end:
        return None
    result["start"] = round(max(0.0, start - local_start), 3)
    result["end"] = round(min(duration, end - local_start), 3)
    return result


def build_trimmed_event(event: dict[str, Any], local_start: float, local_end: float, index: int) -> dict[str, Any]:
    result = deepcopy(event)
    duration = max(0.001, local_end - local_start)
    suffix = "" if index == 1 else f"_short{index:02d}"
    result["event_id"] = f"{event['event_id']}{suffix}"

    if isinstance(event.get("source"), dict):
        result["source"] = shift_media_range(event["source"], local_start, local_end)
    if isinstance(event.get("reference_source"), dict):
        result["reference_source"] = shift_media_range(event["reference_source"], local_start, local_end)
    if isinstance(event.get("audio"), dict):
        audio = deepcopy(event["audio"])
        for in_key, out_key in (("in", "out"), ("timing_reference_in", "timing_reference_out")):
            if in_key in audio:
                base = float(audio.get(in_key) or 0.0)
                audio[in_key] = round(base + local_start, 3)
                audio[out_key] = round(base + local_end, 3)
        result["audio"] = audio

    overlays = []
    for overlay in event.get("overlays", []):
        if not isinstance(overlay, dict):
            continue
        shifted = shifted_overlay(overlay, local_start, local_end)
        if shifted is not None:
            overlays.append(shifted)
    result["overlays"] = overlays
    result["timeline_end"] = round(float(result.get("timeline_start") or 0.0) + duration, 3)
    result["duration"] = round(duration, 3)

    digest_source = result.get("digest_qa_source") if isinstance(result.get("digest_qa_source"), dict) else {}
    digest_source["one_minute_digest"] = True
    digest_source["selected_local_range"] = [round(local_start, 3), round(local_end, 3)]
    result["digest_qa_source"] = digest_source
    result["reason"] = str(result.get("reason") or "") + " Shortened opening digest: keep only the core captioned beat."
    return result


def recompute_timeline(events: list[dict[str, Any]]) -> None:
    cursor = 0.0
    for event in events:
        duration = float(event.get("duration") or event_duration(event))
        event["timeline_start"] = round(cursor, 3)
        event["timeline_end"] = round(cursor + duration, 3)
        cursor += duration


def shorten_plan() -> dict[str, Any]:
    plan = read_json(EDIT_PLAN_PATH)
    events = timeline_events(plan)
    selected_by_id = {item["event_id"]: item for item in SELECTED_DIGEST_RANGES}
    new_events: list[dict[str, Any]] = []
    removed_digest_events: list[dict[str, Any]] = []
    kept_digest_events: list[dict[str, Any]] = []

    for event in events:
        if not isinstance(event, dict) or event.get("section") != "digest":
            new_events.append(event)
            continue
        event_id = str(event.get("event_id"))
        selected = selected_by_id.get(event_id)
        if not selected:
            removed_digest_events.append(
                {
                    "event_id": event_id,
                    "duration_sec": round(event_duration(event), 3),
                    "reason": "Dropped from one-minute digest to keep only the strongest beats.",
                }
            )
            continue
        for index, (local_start, local_end) in enumerate(selected["ranges"], start=1):
            trimmed = build_trimmed_event(event, float(local_start), float(local_end), index)
            new_events.append(trimmed)
            kept_digest_events.append(
                {
                    "event_id": trimmed["event_id"],
                    "source_event_id": event_id,
                    "local_start": round(float(local_start), 3),
                    "local_end": round(float(local_end), 3),
                    "duration_sec": round(float(local_end) - float(local_start), 3),
                    "reason": selected["reason"],
                    "captions": [
                        overlay.get("text")
                        for overlay in trimmed.get("overlays", [])
                        if isinstance(overlay, dict) and overlay.get("type") == "caption"
                    ],
                }
            )

    recompute_timeline(new_events)
    set_timeline_events(plan, new_events)
    shortened_duration = round(
        sum(item["duration_sec"] for item in kept_digest_events),
        3,
    )
    original_digest_duration = round(
        sum(event_duration(event) for event in events if isinstance(event, dict) and event.get("section") == "digest"),
        3,
    )
    plan["digest_pacing"] = {
        **(plan.get("digest_pacing") if isinstance(plan.get("digest_pacing"), dict) else {}),
        "policy": "Opening digest shortened to about one minute by retaining only the strongest question/answer beats.",
        "target_duration_sec": 60,
        "one_minute_shortening": {
            "schema_version": "digest_one_minute_shortening.v1",
            "original_digest_duration_sec": original_digest_duration,
            "shortened_digest_duration_sec": shortened_duration,
            "removed_digest_duration_sec": round(original_digest_duration - shortened_duration, 3),
            "kept_event_count": len(kept_digest_events),
            "removed_event_count": len(removed_digest_events),
            "selection": kept_digest_events,
        },
    }
    plan.setdefault("metadata", {})["digest_one_minute_shortening"] = {
        "enabled": True,
        "target_duration_sec": 60,
        "actual_duration_sec": shortened_duration,
        "report": str(REPORT_PATH),
    }
    write_json(EDIT_PLAN_PATH, plan)

    if DIGEST_QA_PATH.exists():
        digest_qa = read_json(DIGEST_QA_PATH)
        digest_qa["one_minute_digest"] = {
            "schema_version": "digest_one_minute_shortening.v1",
            "target_duration_sec": 60,
            "actual_duration_sec": shortened_duration,
            "selected_events": kept_digest_events,
            "removed_events": removed_digest_events,
        }
        write_json(DIGEST_QA_PATH, digest_qa)

    report = {
        "schema_version": "digest_one_minute_shortening.v1",
        "target_duration_sec": 60,
        "original_digest_duration_sec": original_digest_duration,
        "shortened_digest_duration_sec": shortened_duration,
        "removed_digest_duration_sec": round(original_digest_duration - shortened_duration, 3),
        "kept": kept_digest_events,
        "removed": removed_digest_events,
    }
    write_json(REPORT_PATH, report)
    return report


def main() -> None:
    report = shorten_plan()
    print(
        json.dumps(
            {
                "output": str(EDIT_PLAN_PATH),
                "report": str(REPORT_PATH),
                "target_duration_sec": report["target_duration_sec"],
                "shortened_digest_duration_sec": report["shortened_digest_duration_sec"],
                "kept_event_count": len(report["kept"]),
                "removed_event_count": len(report["removed"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
