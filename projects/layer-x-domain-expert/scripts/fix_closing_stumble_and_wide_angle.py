from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT_ROOT / "output" / "reports"
EDIT_PLAN = REPORTS / "edit_plan.json"
REPORT_PATH = REPORTS / "closing_tail_fix_20260612.json"
JST = timezone(timedelta(hours=9))

CLOSING_SOURCE_MEDIA_ID = "cam_person_02"
POST_STUMBLE_VISUAL_MEDIA_ID = "cam_person_01"
CLOSING_SOURCE_RANGES = [
    (3561.915, 3580.865),
    (3581.615, 3586.350),
    (3591.150, 3601.150),
    (3606.700, 3608.050),
]
CUT_RANGES = [
    {
        "source_in": 3580.865,
        "source_out": 3581.615,
        "reason": "Cut the filler/stumble around the closing lead-in before the outro information.",
    },
    {
        "source_in": 3586.350,
        "source_out": 3591.150,
        "reason": "Cut the stumble near the previous full-render 41:15 mark while preserving the final thanks.",
    },
    {
        "source_in": 3601.150,
        "source_out": 3606.700,
        "reason": "Cut the silent gap after the first closing thanks while keeping the final 'ありがとうございました' response.",
    },
]
CAPTION_EVIDENCE = [
    "2回目に渡ってドメインエキスパートというキャリアについて深掘りしていきました",
    "概要欄に採用の情報も入れてあります",
    "それではありがとうございました",
    "ありがとうございました",
]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sync_offsets() -> dict[str, float]:
    payload = read_json(REPORTS / "app_sync_offsets.json")
    offsets = payload.get("offsets") if isinstance(payload.get("offsets"), dict) else {}
    result: dict[str, float] = {}
    for key, value in offsets.items():
        try:
            result[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return result


def master_time_for_source(source_in: float, media_id: str, offsets: dict[str, float]) -> float:
    role_by_media = {"cam_person_01": "camera2", "cam_person_02": "camera3", "cam_person_03": "camera4"}
    role = role_by_media.get(media_id, "master")
    return source_in - offsets.get(role, 0.0)


def source_time_for_master(master_time: float, media_id: str, offsets: dict[str, float]) -> float:
    role_by_media = {"cam_person_01": "camera2", "cam_person_02": "camera3", "cam_person_03": "camera4"}
    role = role_by_media.get(media_id, "master")
    return master_time + offsets.get(role, 0.0)


def closing_event(
    *,
    index: int,
    source_in: float,
    source_out: float,
    timeline_start: float,
    topic_overlay: dict[str, Any],
    offsets: dict[str, float],
) -> dict[str, Any]:
    duration = source_out - source_in
    use_left_speaker_camera = index >= 3
    visual_media_id = POST_STUMBLE_VISUAL_MEDIA_ID if use_left_speaker_camera else CLOSING_SOURCE_MEDIA_ID
    master_in = master_time_for_source(source_in, CLOSING_SOURCE_MEDIA_ID, offsets)
    visual_in = source_time_for_master(master_in, visual_media_id, offsets)
    visual_out = visual_in + duration
    if use_left_speaker_camera:
        layout = {
            "type": "single",
            "selected_media_id": POST_STUMBLE_VISUAL_MEDIA_ID,
            "target_person_id": "person_01",
            "crop_mode": "loose_full_frame",
            "speaker_person_id": "person_01",
            "selection_reason": "After the closing stumble cut, switch to the left speaker camera so the speaking interviewer is clearly visible.",
        }
        reason = "Finish the full render at the natural closing thanks; after the stumble cut, show the left speaking interviewer camera and remove only the silent gap before the final thanks."
    else:
        layout = {
            "type": "split_grid",
            "media_ids": ["cam_person_01", "cam_person_02", "cam_person_03"],
            "grid_strategy": "three_person_closing_wide_equivalent",
            "panel_order": ["person_01", "person_02", "person_03"],
            "ensure_people_visible": ["person_01", "person_02", "person_03"],
            "selection_reason": "The true group-wide camera ends before the closing tail, so use the synced three-person split before the left-speaker closing cut.",
        }
        reason = "Finish the full render at the natural closing thanks; remove closing stumbles while keeping all three participants visible before the final left-speaker closing cut."
    return {
        "event_id": f"main_closing_thanks_{index:02d}",
        "timeline_start": round(timeline_start, 3),
        "timeline_end": round(timeline_start + duration, 3),
        "type": "source_clip",
        "section": "main",
        "source": {
            "media_id": visual_media_id,
            "in": round(visual_in, 3),
            "out": round(visual_out, 3),
        },
        "reference_source": {
            "media_id": CLOSING_SOURCE_MEDIA_ID,
            "in": round(source_in, 3),
            "out": round(source_out, 3),
        },
        "sync_reference_master_sec": round(master_in, 3),
        "layout": layout,
        "audio": {
            "mode": "single_interview_source",
            "source_media_id": CLOSING_SOURCE_MEDIA_ID,
            "in": round(source_in, 3),
            "out": round(source_out, 3),
            "timing_reference_media_id": CLOSING_SOURCE_MEDIA_ID,
            "timing_reference_in": round(source_in, 3),
            "timing_reference_out": round(source_out, 3),
            "reason": "Use the same continuous interview audio source through the closing and cut only the filler/stumble ranges.",
        },
        "overlays": [deepcopy(topic_overlay)],
        "main_caption_plan_items": [],
        "closing_outro": {
            "ends_at_thanks": index == len(CLOSING_SOURCE_RANGES),
            "source": "closing tail transcription from synced continuous interview audio",
            "caption_evidence": CAPTION_EVIDENCE,
            "removed_filler_ranges": CUT_RANGES,
        },
        "reason": reason,
        "duration": round(duration, 3),
    }


def main() -> None:
    plan = read_json(EDIT_PLAN)
    timeline = plan.get("timeline")
    if not isinstance(timeline, list):
        raise SystemExit("edit_plan.json has no timeline")

    first_closing_idx = next(
        (idx for idx, event in enumerate(timeline) if str(event.get("event_id") or "").startswith("main_closing_thanks_")),
        None,
    )
    if first_closing_idx is None:
        raise SystemExit("No closing thanks events found")

    existing_closing = [
        event for event in timeline[first_closing_idx:] if str(event.get("event_id") or "").startswith("main_closing_thanks_")
    ]
    if len(existing_closing) != len(timeline) - first_closing_idx:
        raise SystemExit("Closing events are not the final timeline events; refusing to rewrite tail")

    topic_overlay = next(
        (
            deepcopy(overlay)
            for event in existing_closing
            for overlay in event.get("overlays", [])
            if isinstance(overlay, dict) and overlay.get("type") == "topic_title"
        ),
        {"type": "topic_title", "position": "top_right", "topic_id": "topic_006", "style_id": "opening_digest_top_right_title"},
    )

    offsets = sync_offsets()
    cursor = float(existing_closing[0]["timeline_start"])
    new_closing: list[dict[str, Any]] = []
    for index, (source_in, source_out) in enumerate(CLOSING_SOURCE_RANGES, start=1):
        event = closing_event(
            index=index,
            source_in=source_in,
            source_out=source_out,
            timeline_start=cursor,
            topic_overlay=topic_overlay,
            offsets=offsets,
        )
        new_closing.append(event)
        cursor = float(event["timeline_end"])

    plan["timeline"] = timeline[:first_closing_idx] + new_closing
    now = datetime.now(JST).isoformat(timespec="seconds")
    plan["updated_at"] = now
    notes = plan.setdefault("revision_notes", [])
    if isinstance(notes, list):
        notes.append(
            {
                "updated_at": now,
                "reason": "Cut the closing stumble around the previous 41:15 render mark, keep the complete final thanks, and switch to the left speaker camera after the stumble cut.",
                "changed_event_ids": [event["event_id"] for event in new_closing],
                "removed_source_ranges": CUT_RANGES,
            }
        )
    write_json(EDIT_PLAN, plan)

    write_json(
        REPORT_PATH,
        {
            "schema_version": "closing_tail_fix.v1",
            "project_id": plan.get("project_id"),
            "generated_at": now,
            "source_media_id": CLOSING_SOURCE_MEDIA_ID,
            "old_event_ids": [event.get("event_id") for event in existing_closing],
            "new_events": [
                {
                    "event_id": event["event_id"],
                    "timeline_start": event["timeline_start"],
                    "timeline_end": event["timeline_end"],
                    "source": event["source"],
                    "layout": event["layout"],
                }
                for event in new_closing
            ],
            "removed_source_ranges": CUT_RANGES,
            "final_timeline_end": round(cursor, 3),
            "notes": [
                "The true group_wide camera ends before the closing tail.",
                "The previous final source range ended at 3597.550, but short-window transcription found closing thanks at 3599.020-3600.940 and another 'ありがとうございました' at 3606.940-3607.260.",
                "The post-stumble closing ranges now use cam_person_01 video synced to cam_person_02 audio, so the left speaking interviewer is visible while one continuous audio source is preserved.",
            ],
        },
    )


if __name__ == "__main__":
    main()
