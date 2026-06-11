from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT_ROOT / "output" / "reports"
EDIT_PLAN_PATH = REPORTS / "edit_plan.json"
CONTENT_WINDOW_PATH = REPORTS / "content_window.json"
REPORT_PATH = REPORTS / "post_company_wait_cut_report.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    plan = read_json(EDIT_PLAN_PATH)
    content_window = read_json(CONTENT_WINDOW_PATH)
    start_sec = float(content_window["usable_master_range"]["start_sec"])

    timeline = plan["timeline"]
    company = next(event for event in timeline if event.get("event_id") == "digest_to_main_company_movie")
    first_main = next(event for event in timeline if event.get("section") == "main")

    old = {
        "first_main_event_id": first_main.get("event_id"),
        "source": first_main.get("source"),
        "reference_source": first_main.get("reference_source"),
        "layout": first_main.get("layout"),
        "timeline_gap_after_company_sec": round(float(first_main["timeline_start"]) - float(company["timeline_end"]), 3),
    }

    duration = round(float(first_main["timeline_end"]) - float(first_main["timeline_start"]), 3)
    first_main["source"] = {
        "media_id": "group_wide",
        "in": round(start_sec, 3),
        "out": round(start_sec + duration, 3),
    }
    first_main["reference_source"] = {
        "media_id": "group_wide",
        "in": round(start_sec, 3),
        "out": round(start_sec + duration, 3),
    }
    first_main["sync_reference_master_sec"] = round(start_sec, 3)
    first_main["layout"] = {
        "type": "wide_group",
        "ensure_people_visible": ["person_01", "person_02", "person_03"],
        "active_person_id": "person_01",
        "safe_margin": 0.06,
        "selection_reason": "Post-company-movie wait is removed by starting the main interview at the first production greeting and showing the three-person wide shot.",
        "reference_alignment": {
            "reference_image_id": "annotation_sample_review_meeting",
            "apply": ["wide_group_context", "speaker_visible", "logo_title_style", "caption_safe_lower_zone"],
        },
    }
    first_main["post_company_wait_cut"] = {
        "policy": "company_movie_preserved; main starts at first production greeting",
        "start_marker_text": content_window.get("start_marker", {}).get("anchor_text"),
        "removed_before_master_sec": round(start_sec, 3),
    }

    plan["updated_at"] = datetime.now(timezone.utc).isoformat()
    plan.setdefault("revision_notes", []).append(
        {
            "updated_at": plan["updated_at"],
            "script": Path(__file__).name,
            "summary": "Ensured the first main event after the company movie starts at the production greeting with a three-person wide shot.",
        }
    )
    write_json(EDIT_PLAN_PATH, plan)
    write_json(
        REPORT_PATH,
        {
            "schema_version": "post_company_wait_cut_report.v1",
            "project_id": "layer-x-domain-expert",
            "company_movie_preserved": True,
            "timeline_gap_after_company_sec": round(float(first_main["timeline_start"]) - float(company["timeline_end"]), 3),
            "main_start_master_sec": round(start_sec, 3),
            "main_start_marker": content_window.get("start_marker"),
            "old_first_main": old,
            "new_first_main": {
                "event_id": first_main.get("event_id"),
                "source": first_main.get("source"),
                "reference_source": first_main.get("reference_source"),
                "layout": first_main.get("layout"),
            },
        },
    )
    print(json.dumps({"updated": str(EDIT_PLAN_PATH), "report": str(REPORT_PATH)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
