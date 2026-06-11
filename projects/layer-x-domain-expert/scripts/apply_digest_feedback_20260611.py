from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT_ROOT / "output" / "reports"
EDIT_PLAN_PATH = REPORTS / "edit_plan.json"
REPORT_PATH = REPORTS / "digest_feedback_20260611_report.json"

OFFSETS = {
    "group_wide": 0.0,
    "cam_person_01": 3.332479,
    "cam_person_02": -7.467854,
    "cam_person_03": -13.38,
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def event_id(event: dict[str, Any]) -> str:
    return str(event.get("event_id") or event.get("id") or "")


def find_event(timeline: list[dict[str, Any]], target: str) -> dict[str, Any]:
    for event in timeline:
        if event_id(event) == target:
            return event
    raise KeyError(target)


def camera_time(media_id: str, master_time: float) -> float:
    return round(master_time - OFFSETS[media_id], 3)


def set_ref_range(event: dict[str, Any], media_id: str, start: float, end: float) -> None:
    event["reference_source"] = {
        "media_id": media_id,
        "in": round(start, 3),
        "out": round(end, 3),
    }
    event["sync_reference_master_sec"] = round(start, 3)


def set_source_from_master(event: dict[str, Any], media_id: str, start: float, end: float) -> None:
    event["source"] = {
        "media_id": media_id,
        "in": camera_time(media_id, start),
        "out": camera_time(media_id, end),
    }


def set_duration_and_shift_after(
    timeline: list[dict[str, Any]],
    target_event: dict[str, Any],
    new_duration: float,
    report: list[dict[str, Any]],
    reason: str,
) -> None:
    old_end = float(target_event["timeline_end"])
    old_duration = old_end - float(target_event["timeline_start"])
    delta = round(new_duration - old_duration, 6)
    if abs(delta) < 0.0001:
        return
    target_event["timeline_end"] = round(float(target_event["timeline_start"]) + new_duration, 3)
    found = False
    shifted = []
    for event in timeline:
        if event is target_event:
            found = True
            continue
        if found:
            event["timeline_start"] = round(float(event["timeline_start"]) + delta, 3)
            event["timeline_end"] = round(float(event["timeline_end"]) + delta, 3)
            shifted.append(event_id(event))
    report.append(
        {
            "event_id": event_id(target_event),
            "old_duration": round(old_duration, 3),
            "new_duration": round(new_duration, 3),
            "timeline_shift_after_sec": round(delta, 3),
            "shifted_event_count": len(shifted),
            "reason": reason,
        }
    )


def set_single_layout(event: dict[str, Any], media_id: str, person_id: str, reason: str) -> None:
    event["layout"] = {
        "type": "single",
        "selected_media_id": media_id,
        "target_person_id": person_id,
        "active_person_id": person_id,
        "crop_mode": "person_centered",
        "selection_reason": reason,
        "reference_alignment": {
            "reference_image_id": "annotation_sample_review_meeting",
            "apply": ["speaker_closeup", "logo_title_style", "caption_safe_lower_zone"],
        },
    }


def set_split_layout(event: dict[str, Any], media_ids: list[str], active_person_id: str, reason: str) -> None:
    event["layout"] = {
        "type": "split_grid",
        "media_ids": media_ids,
        "active_person_id": active_person_id,
        "panel_order": [
            {"cam_person_01": "person_01", "cam_person_02": "person_02", "cam_person_03": "person_03"}[media_id]
            for media_id in media_ids
        ],
        "selection_reason": reason,
        "reference_alignment": {
            "reference_image_id": "annotation_sample_review_meeting",
            "apply": ["split_layout", "speaker_visible", "logo_title_style", "caption_safe_lower_zone"],
        },
    }


def caption(text: str, start: float, end: float, speaker_person_id: str, note: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": "caption",
        "start": round(start, 3),
        "end": round(end, 3),
        "text": text,
        "speaker_person_id": speaker_person_id,
    }
    if note:
        payload["review_note"] = note
    return payload


def main() -> None:
    plan = read_json(EDIT_PLAN_PATH)
    timeline = plan["timeline"]
    changes: list[dict[str, Any]] = []

    # 1. The first answer digest was cutting off the phrase after "癖とか慣れとか".
    ev = find_event(timeline, "digest_qa_01_answer_02")
    set_duration_and_shift_after(
        timeline,
        ev,
        16.2,
        changes,
        "Extend to the natural end of the utterance at master 00:25:49.620 instead of cutting at 00:25:43.020.",
    )
    set_source_from_master(ev, "cam_person_03", 1533.42, 1549.62)
    set_ref_range(ev, "group_wide", 1533.42, 1549.62)
    ev["overlays"] = [
        caption("なんでそうするんですかと聞かれた時に", 0.0, 1.88, "person_03"),
        caption("ものすごくこれを言語化するのに大変だった", 1.88, 5.2, "person_03"),
        caption("癖とか慣れとかそういうもので", 5.2, 10.5, "person_03"),
        caption("今までやってきたんだなと分かる", 10.5, 16.2, "person_03"),
    ]
    changes.append(
        {
            "event_id": event_id(ev),
            "fix": "extended_audio_and_video_source_range",
            "source": ev["source"],
            "reference_source": ev["reference_source"],
        }
    )

    # 2. The "何でも知ってそう" digest should be a two-person split.
    ev = find_event(timeline, "digest_qa_02_question_context_01")
    set_source_from_master(ev, "group_wide", 1595.62, 1604.1)
    set_ref_range(ev, "group_wide", 1595.62, 1604.1)
    set_split_layout(
        ev,
        ["cam_person_01", "cam_person_03"],
        "person_01",
        "User review requested a two-person split for the domain-expert expectation line; left speaker remains visible.",
    )
    for ov in ev.get("overlays", []):
        if isinstance(ov, dict) and ov.get("type") == "caption":
            ov["speaker_person_id"] = "person_01"
            ov["review_note"] = "Voice attribution and user review place this line on the left participant."
    changes.append({"event_id": event_id(ev), "fix": "set_two_person_split_for_domain_expectation"})

    # 3. Keep the "僕より詳しい" caption as a single line and keep both speakers visible.
    ev = find_event(timeline, "digest_qa_02_answer_02")
    set_split_layout(
        ev,
        ["cam_person_01", "cam_person_02", "cam_person_03"],
        "person_03",
        "This short answer contains a right-person line followed by a middle-person line, so use the ordered three-person split instead of cutting away from a speaker.",
    )
    for ov in ev.get("overlays", []):
        if isinstance(ov, dict) and ov.get("type") == "caption" and ov.get("text") == "正直僕より詳しいこともある":
            ov["force_single_line"] = True
            ov["speaker_person_id"] = "person_02"
            ov["review_note"] = "Keep as one line; voice attribution points to the middle participant for this phrase."
    changes.append({"event_id": event_id(ev), "fix": "force_single_line_and_three_split_for_boku_yori_kuwashii_caption"})

    # 4. User review overrides the AI speaker attribution for this digest line: use the left participant camera.
    ev = find_event(timeline, "digest_qa_04_answer_02")
    set_duration_and_shift_after(
        timeline,
        ev,
        6.72,
        changes,
        "Use the full phrase at master 00:33:30.100-00:33:36.820 and avoid clipping the captioned utterance.",
    )
    set_source_from_master(ev, "cam_person_01", 2010.1, 2016.82)
    set_ref_range(ev, "group_wide", 2010.1, 2016.82)
    set_single_layout(
        ev,
        "cam_person_01",
        "person_01",
        "User review says this digest line should use the left participant, so the speaker separation override is applied here.",
    )
    ev["overlays"] = [
        caption(
            "自分たちに求められることが研ぎ澄まされる",
            0.0,
            6.72,
            "person_01",
            "Text changed per user review; left-person speaker override applied.",
        )
    ]
    changes.append({"event_id": event_id(ev), "fix": "left_speaker_override_and_caption_text_update"})

    # 5. The "学ぶの..." line used the middle camera while the voice attribution points left.
    ev = find_event(timeline, "digest_qa_05_answer_02")
    set_source_from_master(ev, "cam_person_01", 2938.04, 2944.04)
    set_ref_range(ev, "group_wide", 2938.04, 2944.04)
    set_single_layout(
        ev,
        "cam_person_01",
        "person_01",
        "Voice attribution for '学ぶの、めちゃめちゃおすすめ' points to the left participant; use the matching close-up.",
    )
    for ov in ev.get("overlays", []):
        if isinstance(ov, dict) and ov.get("type") == "caption":
            ov["speaker_person_id"] = "person_01"
            ov["review_note"] = "Camera changed to the left participant to match the spoken audio and mouth movement."
    changes.append({"event_id": event_id(ev), "fix": "changed_learning_recommendation_to_left_speaker_camera"})

    plan["updated_at"] = datetime.now(timezone.utc).isoformat()
    plan.setdefault("revision_notes", []).append(
        {
            "updated_at": plan["updated_at"],
            "script": Path(__file__).name,
            "summary": "Applied user feedback for digest clipping, speaker-matched cameras, one-line caption, and requested caption text.",
        }
    )
    write_json(EDIT_PLAN_PATH, plan)
    write_json(
        REPORT_PATH,
        {
            "schema_version": "digest_feedback_20260611_report.v1",
            "project_id": "layer-x-domain-expert",
            "edit_plan": str(EDIT_PLAN_PATH),
            "changes": changes,
        },
    )
    print(json.dumps({"updated": str(EDIT_PLAN_PATH), "report": str(REPORT_PATH), "changes": len(changes)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
