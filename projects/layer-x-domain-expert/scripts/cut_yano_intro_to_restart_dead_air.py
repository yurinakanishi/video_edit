from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT_ROOT / "output" / "reports"
EDIT_PLAN_PATH = REPORTS / "edit_plan.json"
REPORT_PATH = REPORTS / "cut_yano_intro_to_restart_dead_air_report.json"

CAM_PERSON_02_APP_OFFSET = 7.467854


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def event_id(event: dict[str, Any]) -> str:
    return str(event.get("event_id") or event.get("id") or "")


def main() -> None:
    plan = read_json(EDIT_PLAN_PATH)
    timeline = plan["timeline"]

    cut_start_timeline = 346.258
    cut_end_timeline = 399.898
    cut_duration = round(cut_end_timeline - cut_start_timeline, 3)
    restart_master = 836.14
    restart_event_id = "main_full_008"

    removed_events = []
    adjusted_events = []
    new_timeline: list[dict[str, Any]] = []
    for event in timeline:
        if not isinstance(event, dict):
            new_timeline.append(event)
            continue
        ts = float(event.get("timeline_start") or 0.0)
        te = float(event.get("timeline_end") or 0.0)
        eid = event_id(event)

        if te <= cut_start_timeline:
            new_timeline.append(event)
            continue

        if ts >= cut_end_timeline:
            event["timeline_start"] = round(ts - cut_duration, 3)
            event["timeline_end"] = round(te - cut_duration, 3)
            new_timeline.append(event)
            continue

        if ts >= cut_start_timeline and te <= cut_end_timeline:
            removed_events.append(
                {
                    "event_id": eid,
                    "timeline_start": ts,
                    "timeline_end": te,
                    "source": event.get("source"),
                    "reference_source": event.get("reference_source"),
                }
            )
            continue

        if eid == restart_event_id and ts < cut_end_timeline < te:
            # Keep only the useful restart phrase: "ではですね最初ちょっと..."
            old = {
                "timeline_start": ts,
                "timeline_end": te,
                "source": event.get("source"),
                "reference_source": event.get("reference_source"),
                "audio": event.get("audio"),
            }
            new_duration = round(te - cut_end_timeline, 3)
            event["timeline_start"] = round(cut_start_timeline, 3)
            event["timeline_end"] = round(cut_start_timeline + new_duration, 3)
            event["source"] = {
                "media_id": "group_wide",
                "in": round(restart_master, 3),
                "out": round(restart_master + new_duration, 3),
            }
            event["reference_source"] = {
                "media_id": "group_wide",
                "in": round(restart_master, 3),
                "out": round(restart_master + new_duration, 3),
            }
            event["audio"] = {
                "mode": "single_interview_source",
                "source_media_id": "cam_person_02",
                "in": round(restart_master + CAM_PERSON_02_APP_OFFSET, 3),
                "out": round(restart_master + CAM_PERSON_02_APP_OFFSET + new_duration, 3),
                "timing_reference_media_id": "group_wide",
                "timing_reference_in": round(restart_master, 3),
                "timing_reference_out": round(restart_master + new_duration, 3),
                "reason": "Trimmed out the awkward dead-air/restart section; keep continuous main audio source aligned to the restart phrase.",
            }
            event["dead_air_trim"] = {
                "cut_reason": "Remove post-self-introduction awkward talk including 'いやいやむずい' before the real restart.",
                "removed_timeline_sec": [cut_start_timeline, cut_end_timeline],
                "kept_restart_master_sec": restart_master,
                "kept_restart_text": "ではですね最初ちょっとお二人に聞きたいのが",
            }
            adjusted_events.append({"event_id": eid, "old": old, "new": {k: event.get(k) for k in ["timeline_start", "timeline_end", "source", "reference_source", "audio"]}})
            new_timeline.append(event)
            continue

        # If an unexpected event partially overlaps the cut, leave it and report
        # rather than silently corrupting timing.
        adjusted_events.append(
            {
                "event_id": eid,
                "warning": "unexpected_partial_overlap_left_unchanged",
                "timeline_start": ts,
                "timeline_end": te,
            }
        )
        new_timeline.append(event)

    plan["timeline"] = new_timeline
    plan["updated_at"] = datetime.now(timezone.utc).isoformat()
    plan.setdefault("revision_notes", []).append(
        {
            "updated_at": plan["updated_at"],
            "script": Path(__file__).name,
            "summary": "Removed the awkward dead-air/restart section after Yano's self-introduction, including the 'むずい' exchange.",
        }
    )
    write_json(EDIT_PLAN_PATH, plan)
    report = {
        "schema_version": "cut_yano_intro_to_restart_dead_air_report.v1",
        "project_id": "layer-x-domain-expert",
        "requested_full_render_range_sec": [342.0, 393.0],
        "semantic_cut_timeline_sec": [cut_start_timeline, cut_end_timeline],
        "cut_duration_sec": cut_duration,
        "removed_events": removed_events,
        "adjusted_events": adjusted_events,
        "kept_before": "Yano self-introduction profile card block remains complete.",
        "resume_at": {
            "master_sec": restart_master,
            "text": "ではですね最初ちょっとお二人に聞きたいのが",
        },
    }
    write_json(REPORT_PATH, report)
    print(json.dumps({"updated": str(EDIT_PLAN_PATH), "report": str(REPORT_PATH), "removed_events": len(removed_events), "cut_duration_sec": cut_duration}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
