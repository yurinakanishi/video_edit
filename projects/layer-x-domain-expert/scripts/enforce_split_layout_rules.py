from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT_ROOT / "output" / "reports"
EDIT_PLAN = REPORTS / "edit_plan.json"
REPORT = REPORTS / "split_layout_rules_audit.json"
VOICE_ATTRIBUTION = REPORTS / "voice_speaker_attribution.json"

SEATING_ORDER = ["person_01", "person_02", "person_03"]
PERSON_CAMERA = {
    "person_01": {"media_id": "cam_person_01", "role": "camera2"},
    "person_02": {"media_id": "cam_person_02", "role": "camera3"},
    "person_03": {"media_id": "cam_person_03", "role": "camera4"},
}
MEDIA_TO_PERSON = {value["media_id"]: person_id for person_id, value in PERSON_CAMERA.items()}
MEDIA_TO_ROLE = {
    "group_wide": "master",
    "cam_person_01": "camera2",
    "cam_person_02": "camera3",
    "cam_person_03": "camera4",
}


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def ordered_people(people: list[str]) -> list[str]:
    seen = set()
    clean = [person_id for person_id in people if person_id in PERSON_CAMERA and not (person_id in seen or seen.add(person_id))]
    return [person_id for person_id in SEATING_ORDER if person_id in clean]


def duration(event: dict[str, Any]) -> float:
    return max(0.01, float(event.get("timeline_end") or 0.0) - float(event.get("timeline_start") or 0.0))


def source_clock(event: dict[str, Any]) -> tuple[str, float]:
    reference = event.get("reference_source") if isinstance(event.get("reference_source"), dict) else {}
    source = event.get("source") if isinstance(event.get("source"), dict) else {}
    media_id = str(reference.get("media_id") or source.get("media_id") or "group_wide")
    source_in = float(reference.get("in") if reference.get("in") is not None else source.get("in") or 0.0)
    return media_id, source_in


def synced_source_start(person_id: str, clock_media_id: str, clock_in: float, offsets: dict[str, float]) -> tuple[str, float]:
    media_id = PERSON_CAMERA[person_id]["media_id"]
    source_role = MEDIA_TO_ROLE.get(clock_media_id, "master")
    target_role = MEDIA_TO_ROLE.get(media_id, "master")
    shared_clock = clock_in - float(offsets.get(source_role, 0.0))
    return media_id, max(0.0, shared_clock + float(offsets.get(target_role, 0.0)))


def is_two_up(layout: dict[str, Any]) -> bool:
    return layout.get("type") == "split_grid" and len(layout.get("media_ids") or []) == 2


def normalize_split_order(event: dict[str, Any]) -> dict[str, Any] | None:
    layout = event.get("layout") if isinstance(event.get("layout"), dict) else None
    if not layout or layout.get("type") != "split_grid":
        return None
    media_ids = [str(media_id) for media_id in layout.get("media_ids") or [] if str(media_id) in MEDIA_TO_PERSON]
    people = ordered_people([MEDIA_TO_PERSON[media_id] for media_id in media_ids])
    if len(people) not in {2, 3}:
        return None
    ordered_media = [PERSON_CAMERA[person_id]["media_id"] for person_id in people]
    before = {"media_ids": layout.get("media_ids"), "panel_order": layout.get("panel_order")}
    layout["media_ids"] = ordered_media
    layout["panel_order"] = people
    if len(people) == 2:
        layout["grid_strategy"] = "two_person_vertical_split"
    elif len(people) == 3 and not str(layout.get("grid_strategy") or "").startswith("three_person_closing"):
        layout["grid_strategy"] = "three_person_vertical_split"
    after = {"media_ids": layout.get("media_ids"), "panel_order": layout.get("panel_order")}
    if before != after:
        return {"event_id": event.get("event_id"), "before": before, "after": after}
    return None


def reliable_active_person(layout: dict[str, Any]) -> str | None:
    for key in ("speaker_person_id", "active_person_id", "target_person_id"):
        person_id = str(layout.get(key) or "")
        if person_id in PERSON_CAMERA:
            return person_id
    speaker_window = layout.get("speaker_window_attribution") if isinstance(layout.get("speaker_window_attribution"), dict) else {}
    person_id = str(speaker_window.get("speaker_person_id") or "")
    if person_id in PERSON_CAMERA:
        return person_id
    return None


def significant_people(layout: dict[str, Any]) -> list[str]:
    speaker_window = layout.get("speaker_window_attribution") if isinstance(layout.get("speaker_window_attribution"), dict) else {}
    people = [
        str(person_id)
        for person_id in speaker_window.get("significant_speaker_person_ids", [])
        if str(person_id) in PERSON_CAMERA
    ]
    return ordered_people(people)


def event_reference_range(event: dict[str, Any]) -> tuple[float, float] | None:
    reference = event.get("reference_source") if isinstance(event.get("reference_source"), dict) else None
    source = reference or (event.get("source") if isinstance(event.get("source"), dict) else None)
    if not source:
        return None
    try:
        start = float(source.get("in") or 0.0)
        end = float(source.get("out") or start)
    except (TypeError, ValueError):
        return None
    if end <= start:
        return None
    return start, end


def trusted_voice_segments(segments: list[dict[str, Any]], start: float, end: float) -> list[dict[str, Any]]:
    result = []
    for segment in segments:
        person_id = str(segment.get("speaker_person_id") or "")
        if person_id not in PERSON_CAMERA:
            continue
        try:
            segment_start = float(segment.get("start") or 0.0)
            segment_end = float(segment.get("end") or segment_start)
            confidence = float(segment.get("confidence") or 0.0)
        except (TypeError, ValueError):
            continue
        overlap = max(0.0, min(end, segment_end) - max(start, segment_start))
        if overlap < 0.22:
            continue
        method = str(segment.get("method") or "")
        if confidence < 0.42 and method not in {"forced_known_intro_window", "text_role_override_voice", "voice_and_text_agree"}:
            continue
        result.append({**segment, "window_overlap_sec": round(overlap, 3)})
    return result


def visible_people(event: dict[str, Any]) -> list[str]:
    layout = event.get("layout") if isinstance(event.get("layout"), dict) else {}
    layout_type = str(layout.get("type") or "")
    if layout_type == "wide_group":
        return list(SEATING_ORDER)
    if layout_type == "single":
        person_id = str(layout.get("target_person_id") or "")
        if person_id in PERSON_CAMERA:
            return [person_id]
        media_id = str(layout.get("selected_media_id") or event.get("source", {}).get("media_id") or "")
        person_id = MEDIA_TO_PERSON.get(media_id)
        return [person_id] if person_id else []
    if layout_type == "split_grid":
        people = [str(item) for item in layout.get("panel_order", []) if str(item) in PERSON_CAMERA]
        if people:
            return people
        media_ids = [str(item) for item in layout.get("media_ids", [])]
        return ordered_people([MEDIA_TO_PERSON[item] for item in media_ids if item in MEDIA_TO_PERSON])
    source = event.get("source") if isinstance(event.get("source"), dict) else {}
    media_id = str(source.get("media_id") or "")
    if media_id == "group_wide":
        return list(SEATING_ORDER)
    person_id = MEDIA_TO_PERSON.get(media_id)
    return [person_id] if person_id else []


def synced_group_start(clock_media_id: str, clock_in: float, offsets: dict[str, float]) -> float:
    source_role = MEDIA_TO_ROLE.get(clock_media_id, "master")
    shared_clock = clock_in - float(offsets.get(source_role, 0.0))
    return max(0.0, shared_clock + float(offsets.get("master", 0.0)))


def force_three_person_split(event: dict[str, Any], offsets: dict[str, float], reason: str) -> dict[str, Any]:
    original_layout = deepcopy(event.get("layout") if isinstance(event.get("layout"), dict) else {})
    clock_media_id, clock_in = source_clock(event)
    group_in = synced_group_start(clock_media_id, clock_in, offsets)
    event["source"] = {
        "media_id": "group_wide",
        "in": round(group_in, 3),
        "out": round(group_in + duration(event), 3),
    }
    event["layout"] = {
        "type": "split_grid",
        "media_ids": [PERSON_CAMERA[person_id]["media_id"] for person_id in SEATING_ORDER],
        "grid_strategy": "three_person_vertical_split",
        "panel_order": list(SEATING_ORDER),
        "ensure_people_visible": list(SEATING_ORDER),
        "speaker_window_attribution": original_layout.get("speaker_window_attribution"),
        "selection_reason": reason,
        "previous_layout": {
            "type": original_layout.get("type"),
            "media_ids": original_layout.get("media_ids"),
            "panel_order": original_layout.get("panel_order"),
            "grid_strategy": original_layout.get("grid_strategy"),
            "clock_media_id": clock_media_id,
        },
    }
    return {
        "event_id": event.get("event_id"),
        "converted_to": "three_person_split",
        "previous_layout_type": original_layout.get("type"),
        "previous_panel_order": original_layout.get("panel_order"),
        "reason": reason,
    }


def convert_consecutive_two_up(event: dict[str, Any], offsets: dict[str, float]) -> dict[str, Any]:
    original_layout = deepcopy(event.get("layout") if isinstance(event.get("layout"), dict) else {})
    active = reliable_active_person(original_layout)
    sig = significant_people(original_layout)
    if active and (not sig or len(sig) <= 2):
        clock_media_id, clock_in = source_clock(event)
        media_id, media_in = synced_source_start(active, clock_media_id, clock_in, offsets)
        event["source"] = {
            "media_id": media_id,
            "in": round(media_in, 3),
            "out": round(media_in + duration(event), 3),
        }
        event["layout"] = {
            "type": "single",
            "selected_media_id": media_id,
            "target_person_id": active,
            "crop_mode": "person_centered",
            "speaker_person_id": active,
            "speaker_window_attribution": original_layout.get("speaker_window_attribution"),
            "selection_reason": "Converted from a consecutive two-person split to a speaker close-up to avoid 2up-to-2up cut changes.",
            "previous_layout": {
                "type": original_layout.get("type"),
                "media_ids": original_layout.get("media_ids"),
                "panel_order": original_layout.get("panel_order"),
                "grid_strategy": original_layout.get("grid_strategy"),
            },
        }
        return {
            "event_id": event.get("event_id"),
            "converted_to": "single",
            "target_person_id": active,
            "previous_panel_order": original_layout.get("panel_order"),
        }

    people = ["person_01", "person_02", "person_03"]
    event["source"] = {
        "media_id": "group_wide",
        "in": round(source_clock(event)[1], 3),
        "out": round(source_clock(event)[1] + duration(event), 3),
    }
    event["layout"] = {
        "type": "split_grid",
        "media_ids": [PERSON_CAMERA[person_id]["media_id"] for person_id in people],
        "grid_strategy": "three_person_vertical_split",
        "panel_order": people,
        "ensure_people_visible": people,
        "speaker_window_attribution": original_layout.get("speaker_window_attribution"),
        "selection_reason": "Converted from a consecutive two-person split to a three-person split to avoid 2up-to-2up cut changes.",
        "previous_layout": {
            "type": original_layout.get("type"),
            "media_ids": original_layout.get("media_ids"),
            "panel_order": original_layout.get("panel_order"),
            "grid_strategy": original_layout.get("grid_strategy"),
        },
    }
    return {
        "event_id": event.get("event_id"),
        "converted_to": "three_person_split",
        "previous_panel_order": original_layout.get("panel_order"),
    }


def repair_voice_visibility(
    events: list[dict[str, Any]], voice_segments: list[dict[str, Any]], offsets: dict[str, float]
) -> list[dict[str, Any]]:
    repairs = []
    for event in events:
        if not isinstance(event, dict) or event.get("section") != "main":
            continue
        time_range = event_reference_range(event)
        if not time_range:
            continue
        start, end = time_range
        speakers = ordered_people([str(segment.get("speaker_person_id") or "") for segment in trusted_voice_segments(voice_segments, start, end)])
        if not speakers:
            continue
        visible = set(visible_people(event))
        missing = [person_id for person_id in speakers if person_id not in visible]
        if not missing:
            continue
        repair = force_three_person_split(
            event,
            offsets,
            "Converted to a three-person split because trusted voice attribution found speakers outside the selected layout.",
        )
        repair["missing_speaker_person_ids"] = missing
        repair["trusted_speaker_person_ids"] = speakers
        repairs.append(repair)
    return repairs


def audit(events: list[dict[str, Any]]) -> dict[str, Any]:
    consecutive = []
    order_violations = []
    previous_two_up: dict[str, Any] | None = None
    for event in events:
        if event.get("section") != "main":
            continue
        layout = event.get("layout") if isinstance(event.get("layout"), dict) else {}
        if layout.get("type") == "split_grid":
            media_ids = layout.get("media_ids") or []
            panel_order = layout.get("panel_order") or []
            expected = ordered_people([MEDIA_TO_PERSON.get(str(media_id), "") for media_id in media_ids])
            if panel_order != expected:
                order_violations.append(
                    {
                        "event_id": event.get("event_id"),
                        "media_ids": media_ids,
                        "panel_order": panel_order,
                        "expected_panel_order": expected,
                    }
                )
        current_two_up = is_two_up(layout)
        if current_two_up and previous_two_up:
            consecutive.append(
                {
                    "previous_event_id": previous_two_up.get("event_id"),
                    "event_id": event.get("event_id"),
                    "previous_panel_order": previous_two_up.get("layout", {}).get("panel_order"),
                    "panel_order": layout.get("panel_order"),
                }
            )
        previous_two_up = event if current_two_up else None
    return {
        "consecutive_two_up_violation_count": len(consecutive),
        "consecutive_two_up_violations": consecutive,
        "panel_order_violation_count": len(order_violations),
        "panel_order_violations": order_violations,
    }


def main() -> None:
    plan = read_json(EDIT_PLAN, {})
    offsets_payload = read_json(REPORTS / "app_sync_offsets.json", {"offsets": {"master": 0.0}})
    offsets = offsets_payload.get("offsets") if isinstance(offsets_payload.get("offsets"), dict) else {"master": 0.0}
    voice_payload = read_json(VOICE_ATTRIBUTION, {"segments": []})
    voice_segments = [item for item in voice_payload.get("segments", []) if isinstance(item, dict)]
    events = plan["timeline"]["events"] if isinstance(plan.get("timeline"), dict) else plan.get("timeline", [])
    order_fixes = []
    conversions = []
    previous_two_up = False
    for event in events:
        if not isinstance(event, dict):
            previous_two_up = False
            continue
        fix = normalize_split_order(event)
        if fix:
            order_fixes.append(fix)
        layout = event.get("layout") if isinstance(event.get("layout"), dict) else {}
        current_two_up = event.get("section") == "main" and is_two_up(layout)
        if current_two_up and previous_two_up:
            conversions.append(convert_consecutive_two_up(event, offsets))
            normalize_split_order(event)
            current_two_up = is_two_up(event.get("layout") if isinstance(event.get("layout"), dict) else {})
        previous_two_up = current_two_up if event.get("section") == "main" else False
    voice_visibility_repairs = repair_voice_visibility(events, voice_segments, offsets)
    plan.setdefault("layout_policy", {})
    plan["layout_policy"]["split_layout_rules"] = {
        "schema_version": "split_layout_rules.v1",
        "no_consecutive_two_person_splits": True,
        "panel_order": SEATING_ORDER,
        "rule": "After a two-person split, insert a speaker close-up, wide group, or three-person split before using another two-person split.",
        "voice_visibility_guard": "If trusted voice attribution finds a speaker outside the selected layout, use a three-person split for that event.",
    }
    write_json(EDIT_PLAN, plan)
    result = {
        "schema_version": "split_layout_rules_audit.v1",
        "project_id": "layer-x-domain-expert",
        "policy": plan["layout_policy"]["split_layout_rules"],
        "order_fix_count": len(order_fixes),
        "order_fixes": order_fixes,
        "conversion_count": len(conversions),
        "conversions": conversions,
        "voice_visibility_repair_count": len(voice_visibility_repairs),
        "voice_visibility_repairs": voice_visibility_repairs,
        "post_audit": audit(events),
    }
    write_json(REPORT, result)
    print(json.dumps({"edit_plan": str(EDIT_PLAN), "report": str(REPORT), "conversion_count": len(conversions), **result["post_audit"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
