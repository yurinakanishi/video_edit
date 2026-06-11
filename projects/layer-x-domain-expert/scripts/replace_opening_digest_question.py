from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT_ROOT / "output" / "reports"
EDIT_PLAN = REPORTS / "edit_plan.json"
DIGEST_SELECTION = REPORTS / "digest_qa_selection.json"
REPORT = REPORTS / "opening_digest_question_replacement_report.json"
JST = timezone(timedelta(hours=9))

REMOVED_EVENT_ID = "digest_qa_01_question_01"
NEW_EVENT_ID = "digest_opening_murata_discomfort_01"
REFERENCE_IN = 1412.34
REFERENCE_OUT = 1416.08
CAM_PERSON_03_OFFSET = 13.38
CAPTION_TEXT = "違和感を言うと良いものになっていく"
REMOVED_EVENT_DURATION_FALLBACK = 4.89


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def event_duration(event: dict[str, Any]) -> float:
    if not event:
        return REMOVED_EVENT_DURATION_FALLBACK
    return round(float(event["timeline_end"]) - float(event["timeline_start"]), 3)


def removed_event_duration(removed_event: dict[str, Any] | None) -> float:
    return event_duration(removed_event) if removed_event else REMOVED_EVENT_DURATION_FALLBACK


def retime_events(events: list[dict[str, Any]]) -> None:
    cursor = 0.0
    for event in events:
        duration = event_duration(event)
        event["timeline_start"] = round(cursor, 3)
        event["timeline_end"] = round(cursor + duration, 3)
        event["duration"] = duration
        cursor = round(cursor + duration, 3)


def replacement_event() -> dict[str, Any]:
    duration = round(REFERENCE_OUT - REFERENCE_IN, 3)
    source_in = round(REFERENCE_IN + CAM_PERSON_03_OFFSET, 3)
    source_out = round(REFERENCE_OUT + CAM_PERSON_03_OFFSET, 3)
    return {
        "event_id": NEW_EVENT_ID,
        "section": "digest",
        "timeline_start": 0.0,
        "timeline_end": duration,
        "duration": duration,
        "source": {
            "media_id": "cam_person_03",
            "in": source_in,
            "out": source_out,
        },
        "reference_source": {
            "media_id": "group_wide",
            "in": REFERENCE_IN,
            "out": REFERENCE_OUT,
        },
        "layout": {
            "type": "single",
            "selected_media_id": "cam_person_03",
            "target_person_id": "person_03",
            "active_person_id": "person_03",
            "speaker_person_id": "person_03",
            "selection_reason": "User requested replacing the opening interviewer question with another digest beat; this uses Murata's concise product-culture statement.",
        },
        "overlays": [
            {
                "type": "caption",
                "start": 0.0,
                "end": duration,
                "text": CAPTION_TEXT,
                "style_id": "opening_digest_sample_caption",
                "source_srt_index": 432,
                "source_timecode": "00:23:32,340 --> 00:23:36,080",
                "speaker_person_id": "person_03",
                "metadata": {
                    "source": "opening_digest_question_replacement",
                    "caption_source_of_truth": "edit_plan.json",
                    "speaker_name": "村田",
                    "speaker_person_id": "person_03",
                    "source_start_sec": REFERENCE_IN,
                    "source_end_sec": REFERENCE_OUT,
                    "caption_start_sec": REFERENCE_IN,
                    "caption_end_sec": REFERENCE_OUT,
                    "audio_strict_timing": True,
                    "display_timing_from_audio_analysis": True,
                    "replacement_for_event_id": REMOVED_EVENT_ID,
                    "selection_reason": "質問ではなく、短く強い回答発言でダイジェストを開始するため。",
                },
                "audio_alignment": {
                    "method": "audio_source_window_direct_phrase",
                    "source_audio_media_id": "group_wide",
                    "source_window_sec": [REFERENCE_IN, REFERENCE_OUT],
                    "speech_window_sec": [REFERENCE_IN, REFERENCE_OUT],
                    "diagnostics": {
                        "display_end_policy": "preserve source phrase end",
                        "replacement_for_event_id": REMOVED_EVENT_ID,
                    },
                },
            }
        ],
        "digest_qa_source": {
            "clip_title": "違和感がプロダクトを良くする",
            "question_title": "ドメインエキスパートが開発に入る価値",
            "answer_summary": "違和感を持ったら言うだけで、プロダクトが良くなっていく文化がある。",
            "evidence_excerpt": "「とりあえず違和感を持ったら言うといいものになっていく」",
            "replacement_for_event_id": REMOVED_EVENT_ID,
        },
        "metadata": {
            "created_by": "replace_opening_digest_question.py",
            "replacement_for_event_id": REMOVED_EVENT_ID,
            "reference_source_text": "とりあえず違和感を持ったら言うといいものになっていくっていうのが",
        },
    }


def update_digest_pacing(plan: dict[str, Any], new_event: dict[str, Any], removed_event: dict[str, Any] | None) -> None:
    digest_pacing = plan.setdefault("digest_pacing", {})
    parts = digest_pacing.get("parts")
    if isinstance(parts, list):
        digest_pacing["parts"] = [
            part for part in parts if not (isinstance(part, dict) and part.get("part_id") == REMOVED_EVENT_ID)
        ]
        digest_pacing["parts"].insert(
            0,
            {
                "part_id": NEW_EVENT_ID,
                "kept_duration_sec": event_duration(new_event),
                "policy": "active_digest_event_replaces_opening_question",
            },
        )
    one_minute = digest_pacing.get("one_minute_shortening")
    if isinstance(one_minute, dict):
        selection = one_minute.get("selection")
        if isinstance(selection, list):
            one_minute["selection"] = [
                item for item in selection if not (isinstance(item, dict) and item.get("event_id") == REMOVED_EVENT_ID)
            ]
            one_minute["selection"].insert(
                0,
                {
                    "event_id": NEW_EVENT_ID,
                    "source_event_id": NEW_EVENT_ID,
                    "local_start": 0.0,
                    "local_end": event_duration(new_event),
                    "duration_sec": event_duration(new_event),
                    "reason": "Opening interviewer question removed by user request; replaced with Murata's concise answer beat.",
                    "captions": [CAPTION_TEXT],
                    "speaker_person_id": "person_03",
                    "speaker_name": "村田",
                },
            )
        if isinstance(one_minute.get("removed_event_ids_by_user_request"), list) and REMOVED_EVENT_ID not in one_minute["removed_event_ids_by_user_request"]:
            one_minute["removed_event_ids_by_user_request"].append(REMOVED_EVENT_ID)
        replacements = one_minute.setdefault("replaced_event_ids_by_user_request", [])
        if isinstance(replacements, list) and REMOVED_EVENT_ID not in replacements:
            replacements.append(REMOVED_EVENT_ID)
        one_minute["opening_question_replacement"] = {
            "removed_event_id": REMOVED_EVENT_ID,
            "added_event_id": NEW_EVENT_ID,
            "removed_captions": [
                "開発に関わる仕事をする中で",
                "これめっちゃ大変でしたとかありますか？",
            ],
            "added_caption": CAPTION_TEXT,
        }
        if isinstance(selection := one_minute.get("selection"), list):
            one_minute["actual_duration_sec"] = round(sum(float(item.get("duration_sec") or 0.0) for item in selection), 3)
            one_minute["shortened_digest_duration_sec"] = one_minute["actual_duration_sec"]
    digest_pacing["policy"] = "Opening digest removes the interviewer question and starts with a strong captioned answer beat."
    digest_pacing["opening_question_removed"] = {
        "removed_event_id": REMOVED_EVENT_ID,
        "added_event_id": NEW_EVENT_ID,
        "removed_duration_sec": removed_event_duration(removed_event),
        "added_duration_sec": event_duration(new_event),
    }


def update_digest_selection(new_event: dict[str, Any], removed_event: dict[str, Any] | None) -> None:
    if not DIGEST_SELECTION.exists():
        return
    selection = read_json(DIGEST_SELECTION)
    active = selection.get("active_digest_events")
    replacement_selection = {
        "event_id": NEW_EVENT_ID,
        "source_event_id": NEW_EVENT_ID,
        "local_start": 0.0,
        "local_end": event_duration(new_event),
        "duration_sec": event_duration(new_event),
        "reason": "Opening interviewer question removed by user request; replaced with Murata's concise answer beat.",
        "captions": [CAPTION_TEXT],
        "speaker_person_id": "person_03",
        "speaker_name": "村田",
    }
    if isinstance(active, list):
        selection["active_digest_events"] = [
            item for item in active if not (isinstance(item, dict) and item.get("event_id") == REMOVED_EVENT_ID)
        ]
        selection["active_digest_events"] = [
            item for item in selection["active_digest_events"] if not (isinstance(item, dict) and item.get("event_id") == NEW_EVENT_ID)
        ]
        selection["active_digest_events"].insert(0, replacement_selection)
    one_minute = selection.get("one_minute_digest")
    if isinstance(one_minute, dict) and isinstance(one_minute.get("selected_events"), list):
        one_minute["selected_events"] = [
            item
            for item in one_minute["selected_events"]
            if not (isinstance(item, dict) and item.get("event_id") in {REMOVED_EVENT_ID, NEW_EVENT_ID})
        ]
        one_minute["selected_events"].insert(0, replacement_selection)
        one_minute["actual_duration_sec"] = round(sum(float(item.get("duration_sec") or 0.0) for item in one_minute["selected_events"]), 3)
        removed_events = one_minute.setdefault("removed_events", [])
        if isinstance(removed_events, list) and not any(isinstance(item, dict) and item.get("event_id") == REMOVED_EVENT_ID for item in removed_events):
            removed_events.append(
                {
                    "event_id": REMOVED_EVENT_ID,
                    "duration_sec": removed_event_duration(removed_event),
                    "reason": "Removed by user request from the opening digest.",
                    "captions": [
                        "開発に関わる仕事をする中で",
                        "これめっちゃ大変でしたとかありますか？",
                    ],
                }
            )
    selection.setdefault("change_log", [])
    if isinstance(selection["change_log"], list):
        selection["change_log"].append(
            {
                "generated_at": datetime.now(JST).isoformat(timespec="seconds"),
                "change": "Removed opening digest interviewer question and replaced it with a Murata answer beat.",
                "removed_event_id": REMOVED_EVENT_ID,
                "added_event_id": NEW_EVENT_ID,
                "removed_captions": [
                    "開発に関わる仕事をする中で",
                    "これめっちゃ大変でしたとかありますか？",
                ],
                "added_caption": CAPTION_TEXT,
            }
        )
    removed = selection.setdefault("removed_event_ids_by_user_request", [])
    if isinstance(removed, list) and REMOVED_EVENT_ID not in removed:
        removed.append(REMOVED_EVENT_ID)
    write_json(DIGEST_SELECTION, selection)


def main() -> None:
    plan = read_json(EDIT_PLAN)
    events = [event for event in plan.get("timeline", []) if isinstance(event, dict)]
    removed_event = next((event for event in events if event.get("event_id") == REMOVED_EVENT_ID), None)
    new_event = replacement_event()
    next_events = [event for event in events if event.get("event_id") not in {REMOVED_EVENT_ID, NEW_EVENT_ID}]
    first_digest_index = next((index for index, event in enumerate(next_events) if event.get("section") == "digest"), 0)
    next_events.insert(first_digest_index, new_event)
    retime_events(next_events)
    plan["timeline"] = next_events
    update_digest_pacing(plan, new_event, removed_event)
    metadata = plan.setdefault("metadata", {})
    metadata["opening_digest_question_replacement"] = {
        "generated_at": datetime.now(JST).isoformat(timespec="seconds"),
        "removed_event_id": REMOVED_EVENT_ID,
        "added_event_id": NEW_EVENT_ID,
        "removed_reason": "User requested deleting the opening question captions and replacing them with another beat.",
        "added_caption": CAPTION_TEXT,
        "added_source_window_sec": [REFERENCE_IN, REFERENCE_OUT],
    }
    write_json(EDIT_PLAN, plan)
    update_digest_selection(new_event, removed_event)
    report = {
        "schema_version": "opening_digest_question_replacement_report.v1",
        "generated_at": datetime.now(JST).isoformat(timespec="seconds"),
        "removed_event": {
            "event_id": REMOVED_EVENT_ID,
            "duration_sec": removed_event_duration(removed_event),
            "captions": [
                "開発に関わる仕事をする中で",
                "これめっちゃ大変でしたとかありますか？",
            ],
        },
        "added_event": {
            "event_id": NEW_EVENT_ID,
            "duration_sec": event_duration(new_event),
            "caption": CAPTION_TEXT,
            "reference_source": new_event["reference_source"],
            "source": new_event["source"],
        },
    }
    write_json(REPORT, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
