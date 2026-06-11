from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT_ROOT / "output" / "reports"
EDIT_PLAN_PATH = REPORTS / "edit_plan.json"
REPORT_PATH = REPORTS / "trim_intro_pre_layerx_silence_report.json"

OLD_MASTER_START = 519.14
NEW_MASTER_START = 522.0


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def shift_source_start(source: dict[str, Any], delta: float) -> None:
    if source.get("in") is not None:
        source["in"] = round(float(source["in"]) + delta, 3)


def main() -> None:
    plan = read_json(EDIT_PLAN_PATH)
    timeline = plan["timeline"]
    first = next(event for event in timeline if event.get("event_id") == "main_intro_group_greeting")
    delta = round(NEW_MASTER_START - OLD_MASTER_START, 3)
    old_first = {
        "timeline_start": first.get("timeline_start"),
        "timeline_end": first.get("timeline_end"),
        "source": dict(first.get("source") or {}),
        "reference_source": dict(first.get("reference_source") or {}),
        "audio": dict(first.get("audio") or {}),
    }

    first["source"]["in"] = round(NEW_MASTER_START, 3)
    first["reference_source"]["in"] = round(NEW_MASTER_START, 3)
    if first.get("sync_reference_master_sec") is not None:
        first["sync_reference_master_sec"] = round(NEW_MASTER_START, 3)
    # Keep the company movie unchanged and make the next event butt up against
    # the shortened greeting clip.
    first["timeline_end"] = round(float(first["timeline_end"]) - delta, 3)
    first["audio"] = {
        "mode": "single_interview_source",
        "source_media_id": "cam_person_02",
        "in": 529.468,
        "out": round(529.468 + (float(first["timeline_end"]) - float(first["timeline_start"])), 3),
        "timing_reference_media_id": "group_wide",
        "timing_reference_in": round(NEW_MASTER_START, 3),
        "timing_reference_out": round(float(first["reference_source"]["out"]), 3),
        "reason": "Trim the post-company pre-speech silence before 'LayerXのYouTubeチャンネル...' while keeping the single interview audio source.",
    }
    first["intro_pre_speech_trim"] = {
        "old_master_start_sec": OLD_MASTER_START,
        "new_master_start_sec": NEW_MASTER_START,
        "removed_sec": delta,
        "reason": "Rendered preview showed the first audible 'LayerXのYouTube...' phrase starting around 89s, about 3s after the company movie ended.",
    }

    first_seen = False
    shifted_events = []
    for event in timeline:
        if event is first:
            first_seen = True
            continue
        if first_seen:
            event["timeline_start"] = round(float(event["timeline_start"]) - delta, 3)
            event["timeline_end"] = round(float(event["timeline_end"]) - delta, 3)
            shifted_events.append(event.get("event_id"))

    plan["updated_at"] = datetime.now(timezone.utc).isoformat()
    plan.setdefault("revision_notes", []).append(
        {
            "updated_at": plan["updated_at"],
            "script": Path(__file__).name,
            "summary": f"Trimmed {delta:.3f}s of silence before the LayerX YouTube greeting after the company movie.",
        }
    )
    write_json(EDIT_PLAN_PATH, plan)
    write_json(
        REPORT_PATH,
        {
            "schema_version": "trim_intro_pre_layerx_silence_report.v1",
            "project_id": "layer-x-domain-expert",
            "trimmed_sec": delta,
            "old_first_main": old_first,
            "new_first_main": {
                "timeline_start": first.get("timeline_start"),
                "timeline_end": first.get("timeline_end"),
                "source": first.get("source"),
                "reference_source": first.get("reference_source"),
                "audio": first.get("audio"),
            },
            "shifted_event_count": len(shifted_events),
        },
    )
    print(json.dumps({"trimmed_sec": delta, "shifted_event_count": len(shifted_events), "report": str(REPORT_PATH)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
