import json
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT / "output" / "reports"
EDIT_PLAN = REPORTS / "edit_plan.json"
DIGEST_SELECTION = REPORTS / "digest_qa_selection.json"
VIDEO_TITLE = REPORTS / "video_title.json"
REPORT_PATH = REPORTS / "digest_remove_blocks_add_middle_report.json"

JST = timezone(timedelta(hours=9))

REMOVE_EVENT_IDS = {
    "digest_qa_01_answer_02",
    "digest_qa_01_answer_03",
    "digest_qa_04_answer_02",
    "digest_qa_04_answer_02_short02",
    "digest_qa_04_answer_02_short03",
    "digest_qa_05_answer_02",
}

NEW_EVENT_ID = "digest_qa_middle_nemoto_value_01"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def caption_texts(event: dict) -> list[str]:
    return [
        str(overlay.get("text") or "")
        for overlay in event.get("overlays", [])
        if overlay.get("type") == "caption"
    ]


def build_middle_event(template: dict, timeline_start: float) -> dict:
    master_in = 1903.86
    master_out = 1907.86
    cam_person_02_app_offset = 7.467854
    source_in = round(master_in + cam_person_02_app_offset, 3)
    source_out = round(master_out + cam_person_02_app_offset, 3)
    duration = 4.0
    event = deepcopy(template)
    event["event_id"] = NEW_EVENT_ID
    event["section"] = "digest"
    event["timeline_start"] = round(timeline_start, 3)
    event["timeline_end"] = round(timeline_start + duration, 3)
    event["source"] = {
        "media_id": "cam_person_02",
        "in": source_in,
        "out": source_out,
    }
    event["reference_source"] = {
        "media_id": "group_wide",
        "in": master_in,
        "out": master_out,
    }
    event["audio"] = {
        "mode": "single_interview_source",
        "source_media_id": "cam_person_02",
        "in": source_in,
        "out": source_out,
        "timing_reference_media_id": "group_wide",
        "timing_reference_in": master_in,
        "timing_reference_out": master_out,
        "reason": "Use one continuous interview audio source; source time follows sync_map app_offset for cam_person_02.",
    }
    event["layout"] = {
        "type": "single",
        "selected_media_id": "cam_person_02",
        "target_person_id": "person_02",
        "active_person_id": "person_02",
        "crop_mode": "person_centered",
        "selection_reason": "User requested one digest statement from the middle participant; this line is a strong caption candidate from captions.md.",
        "reference_alignment": {
            "reference_image_id": "annotation_sample_review_meeting",
            "apply": ["speaker_closeup", "logo_title_style", "caption_safe_lower_zone"],
        },
    }
    event["overlays"] = [
        {
            "type": "topic_title",
            "position": "top_right",
            "text": "AI時代のドメインエキスパート論",
            "style_id": "opening_digest_top_right_title",
        },
        {
            "type": "caption",
            "start": 0.0,
            "end": duration,
            "text": "足すだけでなく「なくていい」と言えることも価値",
            "style_id": "opening_digest_sample_caption",
            "source_segment_id": "seg_000564",
            "source_timecode": "00:31:43,860 --> 00:31:47,860",
            "editorial_note": "Added as the replacement middle-participant digest beat after removing requested digest blocks.",
            "speaker_person_id": "person_02",
            "speaker_name": "根本",
            "force_single_line": True,
        },
    ]
    event["reason"] = "Replacement digest beat from the middle participant, selected from main_caption_049."
    event["digest_qa_source"] = {
        "question": "Replacement middle-participant digest beat",
        "clip_title": "なくていいと言える価値",
        "part_kind": "answer",
        "start_timecode": "00:31:43,860",
        "end_timecode": "00:31:47,860",
        "answer_summary": "必要そうなものを足すだけではなく、なくていいと言えることもドメインエキスパートの価値として伝える。",
        "evidence_excerpt": "「必要そうなものを足すだけではなく」「これはもうなくていいです」",
        "caption_only_cut": True,
        "added_by_user_request": True,
    }
    event["duration"] = duration
    event.pop("metadata", None)
    return event


def update_edit_plan() -> dict:
    data = load_json(EDIT_PLAN)
    timeline = data["timeline"]
    removed = [event for event in timeline if event.get("event_id") in REMOVE_EVENT_IDS]
    if not removed:
        raise SystemExit("No requested digest events were found to remove.")

    template = next(event for event in timeline if event.get("event_id") == "digest_qa_02_answer_02")
    new_timeline = []
    cursor = 0.0
    inserted = False
    added_event = None

    for event in timeline:
        event_id = event.get("event_id")
        if event_id in REMOVE_EVENT_IDS or event_id == NEW_EVENT_ID:
            continue
        duration = round(float(event["timeline_end"]) - float(event["timeline_start"]), 6)
        event["timeline_start"] = round(cursor, 3)
        event["timeline_end"] = round(cursor + duration, 3)
        new_timeline.append(event)
        cursor = round(cursor + duration, 6)

        if event_id == "digest_qa_03_answer_01":
            added_event = build_middle_event(template, cursor)
            new_timeline.append(added_event)
            cursor = round(float(added_event["timeline_end"]), 6)
            inserted = True

    if not inserted:
        raise SystemExit("Could not insert replacement middle digest event.")

    data["timeline"] = new_timeline
    data["updated_at"] = datetime.now(JST).isoformat(timespec="seconds")
    data.setdefault("revision_notes", []).append(
        {
            "updated_at": data["updated_at"],
            "change": "Removed requested opening digest blocks and added one middle-participant digest statement.",
            "removed_event_ids": sorted(REMOVE_EVENT_IDS),
            "added_event_id": NEW_EVENT_ID,
        }
    )
    save_json(EDIT_PLAN, data)
    return {
        "removed_events": [
            {
                "event_id": event.get("event_id"),
                "timeline_start": event.get("timeline_start"),
                "timeline_end": event.get("timeline_end"),
                "captions": caption_texts(event),
            }
            for event in removed
        ],
        "added_event": {
            "event_id": added_event.get("event_id"),
            "timeline_start": added_event.get("timeline_start"),
            "timeline_end": added_event.get("timeline_end"),
            "source": added_event.get("source"),
            "caption": caption_texts(added_event),
            "speaker_person_id": "person_02",
        },
        "new_digest_duration_sec": next(
            event["timeline_start"]
            for event in new_timeline
            if event.get("event_id") == "digest_to_main_company_movie"
        ),
    }


def update_digest_selection(report: dict) -> None:
    if not DIGEST_SELECTION.exists():
        return
    data = load_json(DIGEST_SELECTION)
    one_minute = data.setdefault("one_minute_digest", {})
    selected = [
        event
        for event in one_minute.get("selected_events", [])
        if event.get("event_id") not in REMOVE_EVENT_IDS and event.get("event_id") != NEW_EVENT_ID
    ]
    insert_at = next((i + 1 for i, event in enumerate(selected) if event.get("event_id") == "digest_qa_03_answer_01"), len(selected))
    selected.insert(
        insert_at,
        {
            "event_id": NEW_EVENT_ID,
            "source_event_id": "main_caption_049",
            "local_start": 0.0,
            "local_end": 4.0,
            "duration_sec": 4.0,
            "reason": "Replacement digest beat from the middle participant.",
            "captions": ["足すだけでなく「なくていい」と言えることも価値"],
            "speaker_person_id": "person_02",
            "speaker_name": "根本",
        },
    )
    one_minute["selected_events"] = selected
    one_minute["actual_duration_sec"] = round(sum(float(event.get("duration_sec") or 0.0) for event in selected), 3)
    removed = one_minute.setdefault("removed_events", [])
    existing = {event.get("event_id") for event in removed}
    for event in report["removed_events"]:
        if event["event_id"] not in existing:
            removed.append(
                {
                    "event_id": event["event_id"],
                    "duration_sec": round(float(event["timeline_end"]) - float(event["timeline_start"]), 3),
                    "reason": "Removed by user request from the opening digest.",
                    "captions": event["captions"],
                }
            )
    data["updated_at"] = datetime.now(JST).isoformat(timespec="seconds")
    data.setdefault("change_log", []).append(
        {
            "updated_at": data["updated_at"],
            "change": "Removed requested digest blocks and added a middle-participant replacement beat.",
            "removed_event_ids": sorted(REMOVE_EVENT_IDS),
            "added_event_id": NEW_EVENT_ID,
        }
    )
    save_json(DIGEST_SELECTION, data)


def update_video_title() -> None:
    if not VIDEO_TITLE.exists():
        return
    data = load_json(VIDEO_TITLE)
    removed_phrases = {
        "今までの当たり前を言語化する",
        "自分たちに求められることが研ぎ澄まされる",
        "学ぶのめちゃめちゃおすすめ",
    }
    for key in ("key_phrases", "supporting_phrases"):
        if isinstance(data.get(key), list):
            data[key] = [phrase for phrase in data[key] if phrase not in removed_phrases]
    data.setdefault("supporting_phrases", []).append("足すだけでなく「なくていい」と言えることも価値")
    data["updated_at"] = datetime.now(JST).isoformat(timespec="seconds")
    save_json(VIDEO_TITLE, data)


def main() -> None:
    report = {
        "schema_version": "digest_remove_blocks_add_middle_report.v1",
        "project_id": "layer-x-domain-expert",
        "updated_at": datetime.now(JST).isoformat(timespec="seconds"),
        "user_request": [
            "Remove the digest block from 癖とか慣れとか through 今までの当たり前を言語化する.",
            "Remove the digest block from 自分たちに求められる through 学ぶのめちゃめちゃおすすめ.",
            "Add one middle-participant statement to the digest.",
        ],
    }
    report.update(update_edit_plan())
    update_digest_selection(report)
    update_video_title()
    save_json(REPORT_PATH, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
