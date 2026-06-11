from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT_ROOT / "output" / "reports"
EDIT_PLAN_PATH = REPORTS / "edit_plan.json"
PROFILE_CARDS_PATH = REPORTS / "interviewee_profile_cards.json"
REPORT_PATH = REPORTS / "yano_profile_card_intro_report.json"

CAM_PERSON_01_APP_OFFSET = -3.332479
CAM_PERSON_02_APP_OFFSET = 7.467854


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def camera_time(master_sec: float, app_offset: float) -> float:
    return round(master_sec + app_offset, 3)


def add_yano_profile() -> dict[str, Any]:
    payload = read_json(PROFILE_CARDS_PATH)
    profiles = payload.setdefault("profiles", {})
    profiles["person_01"] = {
        "person_id": "person_01",
        "display_name": "矢野",
        "name_suffix": "",
        "department": "バクラク事業部",
        "role_title": "聞き手",
        "body_lines": [
            "監査法人を経て、事業会社で経営企画・IRなどを経験。",
            "LayerXでは事業側・ビジネス側の仕事に携わり、プロダクトづくりに関与。",
            "ドメインエキスパートとして、顧客理解や開発チームとの橋渡しを担う。",
        ],
    }
    write_json(PROFILE_CARDS_PATH, payload)
    return profiles["person_01"]


def main() -> None:
    yano_profile = add_yano_profile()
    plan = read_json(EDIT_PLAN_PATH)
    timeline = plan["timeline"]
    by_id = {str(event.get("event_id")): event for event in timeline if isinstance(event, dict)}

    target_ids = ["main_full_001", "main_full_002", "main_full_003", "main_full_004"]
    old_events = [by_id[event_id] for event_id in target_ids]
    block_start = float(old_events[0]["timeline_start"])
    old_block_end = float(old_events[-1]["timeline_end"])
    old_duration = round(old_block_end - block_start, 3)

    master_start = 727.46
    master_end = 784.38
    new_duration = round(master_end - master_start, 3)
    new_end = round(block_start + new_duration, 3)
    delta = round(new_duration - old_duration, 3)

    new_event = old_events[0]
    new_event["event_id"] = "main_yano_profile_intro"
    new_event["timeline_start"] = round(block_start, 3)
    new_event["timeline_end"] = new_end
    new_event["source"] = {
        "media_id": "cam_person_01",
        "in": camera_time(master_start, CAM_PERSON_01_APP_OFFSET),
        "out": camera_time(master_end, CAM_PERSON_01_APP_OFFSET),
    }
    new_event["reference_source"] = {
        "media_id": "group_wide",
        "in": round(master_start, 3),
        "out": round(master_end, 3),
    }
    new_event["audio"] = {
        "mode": "single_interview_source",
        "source_media_id": "cam_person_02",
        "in": camera_time(master_start, CAM_PERSON_02_APP_OFFSET),
        "out": camera_time(master_end, CAM_PERSON_02_APP_OFFSET),
        "timing_reference_media_id": "group_wide",
        "timing_reference_in": round(master_start, 3),
        "timing_reference_out": round(master_end, 3),
        "reason": "Use the existing single continuous interview audio source; timing follows the Yano self-introduction master window.",
    }
    new_event["layout"] = {
        "type": "single",
        "selected_media_id": "cam_person_01",
        "target_person_id": "person_01",
        "crop_mode": "single_intro_reference_fullscreen",
        "introduction_nameplate": False,
        "selection_reason": "Yano self-introduction should match the other two profile-card introductions: one-person close-up with a profile card.",
        "reference_alignment": {
            "reference_image_id": "single_person_fullscreen_intro_white_text",
            "analysis_path": str(REPORTS / "reference_image_analysis" / "single-person-introduction-name-subtitle-reference.json"),
            "apply": ["medium_closeup", "eyes_upper_third", "single_person_bio_card_lower_third"],
        },
    }
    new_event["overlays"] = [
        {
            "type": "intro_profile_card",
            "person_id": "person_01",
            "profile_source": "output/reports/interviewee_profile_cards.json",
            "reference_image_id": "single_person_bio_card_lower_third",
            "style_id": "single_person_bio_card_lower_third_reference",
            "start": 0.35,
            "end": round(new_duration - 0.35, 3),
        }
    ]
    new_event["caption_policy"] = "no_caption_during_self_introduction"
    new_event["reason"] = "矢野さんの自己紹介開始に合わせて、単独カメラでプロフィールカードを表示。"
    new_event["yano_profile_intro_window"] = {
        "source": "voice_speaker_attribution",
        "start_text": "最後に簡単に私の自己紹介をさせていただきます",
        "end_text": "2年半くらい前から開発に関与しているという感じでございます。よろしくお願いします。",
        "master_start_sec": master_start,
        "master_end_sec": master_end,
    }

    remove_ids = set(target_ids[1:])
    new_timeline: list[dict[str, Any]] = []
    for event in timeline:
        if not isinstance(event, dict):
            new_timeline.append(event)
            continue
        event_id = str(event.get("event_id"))
        if event_id in remove_ids:
            continue
        if float(event.get("timeline_start") or 0.0) >= old_block_end:
            event["timeline_start"] = round(float(event["timeline_start"]) + delta, 3)
            event["timeline_end"] = round(float(event["timeline_end"]) + delta, 3)
        new_timeline.append(event)

    plan["timeline"] = new_timeline
    plan["updated_at"] = datetime.now(timezone.utc).isoformat()
    plan.setdefault("revision_notes", []).append(
        {
            "updated_at": plan["updated_at"],
            "script": Path(__file__).name,
            "summary": "Replaced the 4:50 Yano self-introduction block with a single left-camera close-up and matching intro profile card.",
        }
    )
    write_json(EDIT_PLAN_PATH, plan)
    report = {
        "schema_version": "yano_profile_card_intro_report.v1",
        "project_id": "layer-x-domain-expert",
        "profile_added": yano_profile,
        "replaced_event_ids": target_ids,
        "new_event_id": "main_yano_profile_intro",
        "old_duration_sec": old_duration,
        "new_duration_sec": new_duration,
        "timeline_shift_after_sec": delta,
        "master_window_sec": [master_start, master_end],
        "source": new_event["source"],
        "reference_source": new_event["reference_source"],
    }
    write_json(REPORT_PATH, report)
    print(json.dumps({"updated": str(EDIT_PLAN_PATH), "report": str(REPORT_PATH), "delta": delta}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
