from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[1]
REPORTS_DIR = PROJECT_DIR / "output" / "reports"
EDIT_PLAN_PATH = REPORTS_DIR / "edit_plan.json"
DIGEST_QA_PATH = REPORTS_DIR / "digest_qa_selection.json"
VIDEO_TITLE_PATH = REPORTS_DIR / "video_title.json"
REPORT_PATH = REPORTS_DIR / "right_digest_replacement_report.json"

JST = timezone(timedelta(hours=9))

OLD_EVENT_ID = "digest_qa_02_answer_02"
NEW_EVENT_ID = "digest_qa_right_user_anxiety_01"

MASTER_IN = 1752.35
MASTER_SPEECH_IN = 1752.5
MASTER_SPEECH_OUT = 1757.5
MASTER_OUT = 1757.75
CAM_PERSON_03_OFFSET = 13.38
CAM_PERSON_02_AUDIO_OFFSET = 7.467854

CAPTION_TEXT = "ユーザーが不安なら自動化しても使われない"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def event_duration(event: dict[str, Any]) -> float:
    return round(float(event.get("timeline_end") or 0.0) - float(event.get("timeline_start") or 0.0), 3)


def caption_texts(event: dict[str, Any]) -> list[str]:
    return [
        str(overlay.get("text") or "")
        for overlay in event.get("overlays", [])
        if isinstance(overlay, dict) and overlay.get("type") == "caption"
    ]


def digest_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [event for event in events if event.get("section") == "digest"]


def digest_duration(events: list[dict[str, Any]]) -> float:
    return round(sum(event_duration(event) for event in digest_events(events)), 3)


def recompute_timeline(events: list[dict[str, Any]]) -> None:
    cursor = 0.0
    for event in events:
        duration = event_duration(event)
        event["timeline_start"] = round(cursor, 3)
        event["timeline_end"] = round(cursor + duration, 3)
        cursor = round(cursor + duration, 3)


def build_replacement_event(timeline_start: float) -> dict[str, Any]:
    duration = round(MASTER_OUT - MASTER_IN, 3)
    source_in = round(MASTER_IN + CAM_PERSON_03_OFFSET, 3)
    source_out = round(MASTER_OUT + CAM_PERSON_03_OFFSET, 3)
    audio_in = round(MASTER_IN + CAM_PERSON_02_AUDIO_OFFSET, 3)
    audio_out = round(MASTER_OUT + CAM_PERSON_02_AUDIO_OFFSET, 3)
    caption_start = round(MASTER_SPEECH_IN - MASTER_IN, 3)
    caption_end = duration

    return {
        "event_id": NEW_EVENT_ID,
        "timeline_start": round(timeline_start, 3),
        "timeline_end": round(timeline_start + duration, 3),
        "duration": duration,
        "type": "source_clip",
        "section": "digest",
        "source": {
            "media_id": "cam_person_03",
            "in": source_in,
            "out": source_out,
        },
        "reference_source": {
            "media_id": "group_wide",
            "in": MASTER_IN,
            "out": MASTER_OUT,
        },
        "audio": {
            "mode": "single_interview_source",
            "source_media_id": "cam_person_02",
            "in": audio_in,
            "out": audio_out,
            "timing_reference_media_id": "group_wide",
            "timing_reference_in": MASTER_IN,
            "timing_reference_out": MASTER_OUT,
            "reason": "Use the same continuous interview audio source; source time follows app sync offset for cam_person_02.",
        },
        "layout": {
            "type": "single",
            "selected_media_id": "cam_person_03",
            "target_person_id": "person_03",
            "active_person_id": "person_03",
            "crop_mode": "person_centered",
            "speaker_person_id": "person_03",
            "speaker_attribution_confidence": 0.761,
            "selection_reason": "Replacement digest beat for the right participant; voice attribution and source caption plan identify Murata as the speaker.",
            "reference_alignment": {
                "reference_image_id": "single_person_fullscreen_intro_white_text",
                "apply": ["speaker_closeup", "face_centered_crop", "logo_title_style", "caption_safe_lower_zone"],
            },
        },
        "overlays": [
            {
                "type": "topic_title",
                "position": "top_right",
                "text": "AI時代のドメインエキスパート論",
                "style_id": "opening_digest_top_right_title",
            },
            {
                "type": "caption",
                "start": caption_start,
                "end": caption_end,
                "text": CAPTION_TEXT,
                "style_id": "opening_digest_sample_caption",
                "caption_id": "digest_caption_right_user_anxiety_01",
                "source_segment_ids": ["seg_000514", "seg_000515"],
                "source_timecode": "00:29:12,500 --> 00:29:17,500",
                "speaker_person_id": "person_03",
                "speaker_name": "村田",
                "metadata": {
                    "source": "edit_plan_caption_overlay",
                    "caption_source_of_truth": "edit_plan.json",
                    "source_main_caption_ids": ["main_caption_042", "main_caption_043"],
                    "source_main_event_id": "main_full_069",
                    "caption_start_sec": MASTER_SPEECH_IN,
                    "caption_end_sec": MASTER_OUT,
                    "source_start_sec": MASTER_SPEECH_IN,
                    "source_end_sec": MASTER_SPEECH_OUT,
                    "speaker_name": "村田",
                    "speaker_person_id": "person_03",
                    "digest_caption_hold_after_speech_sec": round(MASTER_OUT - MASTER_SPEECH_OUT, 3),
                    "digest_caption_hold_sync_fixed": True,
                    "replacement_for_event_id": OLD_EVENT_ID,
                    "replacement_reason": "Previous right-participant digest beat was too weak and generic.",
                },
                "audio_alignment": {
                    "method": "source_caption_plan_and_voice_attribution",
                    "source_audio_media_id": "group_wide",
                    "source_window_sec": [MASTER_SPEECH_IN, MASTER_SPEECH_OUT],
                    "speech_window_sec": [MASTER_SPEECH_IN, MASTER_SPEECH_OUT],
                    "diagnostics": {
                        "source_main_event_id": "main_full_069",
                        "evidence_segments": ["seg_000514", "seg_000515"],
                        "speaker_person_id": "person_03",
                    },
                },
            },
        ],
        "digest_qa_source": {
            "question": "AI時代に、ドメインエキスパートの価値は何ですか？",
            "clip_title": "不安なら使われない機能になる",
            "part_kind": "answer",
            "start_timecode": "00:29:12,500",
            "end_timecode": "00:29:17,500",
            "answer_summary": "自動化してもユーザーに不安が残ると、結局ユーザーは自分で調べてしまい、機能が使われなくなる。",
            "evidence_excerpt": "「心配になって自分で調べるようになる」「使われない機能になる」",
            "caption_only_cut": True,
            "speaker_person_id": "person_03",
            "speaker_name": "村田",
            "replacement_for_event_id": OLD_EVENT_ID,
        },
        "reason": "Right-participant digest replacement: use a stronger product-value statement instead of the generic domain-research line.",
    }


def summarize_digest_event(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "part_id": event.get("event_id"),
        "kept_duration_sec": event_duration(event),
        "policy": "active_digest_event",
    }


def summarize_selection_event(event: dict[str, Any]) -> dict[str, Any]:
    duration = event_duration(event)
    digest_source = event.get("digest_qa_source") if isinstance(event.get("digest_qa_source"), dict) else {}
    captions = caption_texts(event)
    return {
        "event_id": event.get("event_id"),
        "source_event_id": digest_source.get("replacement_for_event_id") or event.get("event_id"),
        "local_start": 0.0,
        "local_end": duration,
        "duration_sec": duration,
        "reason": event.get("reason") or digest_source.get("answer_summary") or "Active digest beat.",
        "captions": captions,
        "speaker_person_id": digest_source.get("speaker_person_id")
        or next(
            (
                overlay.get("speaker_person_id")
                for overlay in event.get("overlays", [])
                if isinstance(overlay, dict) and overlay.get("type") == "caption"
            ),
            None,
        ),
        "speaker_name": digest_source.get("speaker_name")
        or next(
            (
                overlay.get("speaker_name")
                for overlay in event.get("overlays", [])
                if isinstance(overlay, dict) and overlay.get("type") == "caption"
            ),
            None,
        ),
    }


def update_digest_pacing(plan: dict[str, Any], events: list[dict[str, Any]], old_event: dict[str, Any]) -> None:
    digest = digest_events(events)
    duration_sec = digest_duration(events)
    pacing = plan.setdefault("digest_pacing", {})
    pacing["policy"] = "Opening digest keeps selected captioned beats; weak right-participant beat replaced with a stronger Murata product-value statement."
    pacing["parts"] = [summarize_digest_event(event) for event in digest]
    pacing["shortened_digest_duration_sec"] = duration_sec

    one_minute = pacing.setdefault("one_minute_shortening", {})
    one_minute.setdefault("schema_version", "digest_one_minute_shortening.v1")
    one_minute["target_duration_sec"] = 60
    one_minute["shortened_digest_duration_sec"] = duration_sec
    one_minute["kept_event_count"] = len(digest)
    one_minute["selection"] = [summarize_selection_event(event) for event in digest]
    replaced = one_minute.setdefault("replaced_event_ids_by_user_request", [])
    if OLD_EVENT_ID not in replaced:
        replaced.append(OLD_EVENT_ID)
    one_minute["replacement"] = {
        "removed_event_id": OLD_EVENT_ID,
        "removed_captions": caption_texts(old_event),
        "added_event_id": NEW_EVENT_ID,
        "added_captions": [CAPTION_TEXT],
        "reason": "Right-participant digest beat was weak; replaced by a stronger Murata statement about user anxiety and unused automation.",
    }

    if isinstance(plan.get("metadata"), dict) and isinstance(plan["metadata"].get("digest_one_minute_shortening"), dict):
        plan["metadata"]["digest_one_minute_shortening"]["actual_duration_sec"] = duration_sec


def update_digest_qa_selection(events: list[dict[str, Any]], old_event: dict[str, Any], now: str) -> None:
    if not DIGEST_QA_PATH.exists():
        return
    data = read_json(DIGEST_QA_PATH)
    digest = digest_events(events)
    one_minute = data.setdefault("one_minute_digest", {})
    one_minute.setdefault("schema_version", "digest_one_minute_shortening.v1")
    one_minute["target_duration_sec"] = 60
    one_minute["actual_duration_sec"] = digest_duration(events)
    one_minute["selected_events"] = [summarize_selection_event(event) for event in digest]
    replaced = one_minute.setdefault("replaced_event_ids_by_user_request", [])
    if OLD_EVENT_ID not in replaced:
        replaced.append(OLD_EVENT_ID)
    removed = one_minute.setdefault("removed_events", [])
    if not any(item.get("event_id") == OLD_EVENT_ID for item in removed):
        removed.append(
            {
                "event_id": OLD_EVENT_ID,
                "duration_sec": event_duration(old_event),
                "reason": "Replaced by user request because the right-participant digest beat was weak.",
                "captions": caption_texts(old_event),
            }
        )
    data["updated_at"] = now
    data.setdefault("change_log", []).append(
        {
            "updated_at": now,
            "change": "Replaced weak right-participant digest beat.",
            "removed_event_id": OLD_EVENT_ID,
            "added_event_id": NEW_EVENT_ID,
            "added_caption": CAPTION_TEXT,
        }
    )
    write_json(DIGEST_QA_PATH, data)


def update_video_title(now: str) -> None:
    if not VIDEO_TITLE_PATH.exists():
        return
    data = read_json(VIDEO_TITLE_PATH)
    phrases = data.setdefault("supporting_phrases", [])
    if CAPTION_TEXT not in phrases:
        phrases.append(CAPTION_TEXT)
    data["updated_at"] = now
    write_json(VIDEO_TITLE_PATH, data)


def update_plan() -> dict[str, Any]:
    plan = read_json(EDIT_PLAN_PATH)
    events = [event for event in plan.get("timeline", []) if isinstance(event, dict)]
    old_event = next((event for event in events if event.get("event_id") == OLD_EVENT_ID), None)
    if old_event is None:
        raise SystemExit(f"{OLD_EVENT_ID} was not found in edit_plan.json")

    new_events: list[dict[str, Any]] = []
    inserted = False
    replacement_event: dict[str, Any] | None = None
    for event in events:
        event_id = event.get("event_id")
        if event_id in {OLD_EVENT_ID, NEW_EVENT_ID}:
            continue
        new_events.append(event)
        if event_id == "digest_qa_03_answer_01":
            replacement_event = build_replacement_event(float(event.get("timeline_end") or 0.0))
            new_events.append(replacement_event)
            inserted = True

    if not inserted or replacement_event is None:
        raise SystemExit("Could not insert replacement after digest_qa_03_answer_01")

    recompute_timeline(new_events)
    now = datetime.now(JST).isoformat(timespec="seconds")
    plan["timeline"] = new_events
    plan["updated_at"] = now
    plan.setdefault("revision_notes", []).append(
        {
            "updated_at": now,
            "change": "Replaced weak right-participant digest beat with a stronger Murata statement.",
            "removed_event_id": OLD_EVENT_ID,
            "removed_captions": caption_texts(old_event),
            "added_event_id": NEW_EVENT_ID,
            "added_captions": [CAPTION_TEXT],
        }
    )
    update_digest_pacing(plan, new_events, old_event)
    write_json(EDIT_PLAN_PATH, plan)
    update_digest_qa_selection(new_events, old_event, now)
    update_video_title(now)

    return {
        "schema_version": "right_digest_replacement_report.v1",
        "project_id": "layer-x-domain-expert",
        "updated_at": now,
        "removed_event": {
            "event_id": OLD_EVENT_ID,
            "captions": caption_texts(old_event),
            "duration_sec": event_duration(old_event),
        },
        "added_event": {
            "event_id": NEW_EVENT_ID,
            "captions": [CAPTION_TEXT],
            "duration_sec": event_duration(replacement_event),
            "speaker_person_id": "person_03",
            "speaker_name": "村田",
            "source": replacement_event["source"],
            "reference_source": replacement_event["reference_source"],
        },
        "digest_duration_sec": digest_duration(new_events),
    }


def main() -> None:
    report = update_plan()
    write_json(REPORT_PATH, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
