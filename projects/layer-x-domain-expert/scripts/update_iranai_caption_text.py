from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


PROJECT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT / "output" / "reports"
EDIT_PLAN = REPORTS / "edit_plan.json"
REPORT_PATH = REPORTS / "iranai_caption_text_update_report.json"
JST = timezone(timedelta(hours=9))

OLD_TEXT = "足すだけでなく「なくていい」と言えることも価値"
NEW_TEXT = "いらないものをちゃんと言ってあげる"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    plan = load(EDIT_PLAN)
    changed: list[dict[str, Any]] = []
    for event in plan.get("timeline", []):
        for overlay in event.get("overlays", []) or []:
            if not (isinstance(overlay, dict) and overlay.get("type") == "caption"):
                continue
            if overlay.get("text") != OLD_TEXT:
                continue
            overlay["text"] = NEW_TEXT
            metadata = overlay.setdefault("metadata", {})
            if isinstance(metadata, dict):
                metadata["display_text_replaced_from"] = OLD_TEXT
                metadata["keyword_timing_anchor"] = "いらないもの"
                metadata["caption_source_of_truth"] = "edit_plan.json"
            changed.append(
                {
                    "event_id": event.get("event_id"),
                    "section": event.get("section"),
                    "caption_id": overlay.get("caption_id"),
                    "old_text": OLD_TEXT,
                    "new_text": NEW_TEXT,
                    "local_timing": [overlay.get("start"), overlay.get("end")],
                }
            )
        for item in event.get("main_caption_plan_items", []) or []:
            if isinstance(item, dict) and item.get("display_text") == OLD_TEXT:
                item["display_text"] = NEW_TEXT
                item["display_text_replaced_from"] = OLD_TEXT
                item["caption_source_of_truth"] = "edit_plan.json"
    updated_at = datetime.now(JST).isoformat(timespec="seconds")
    plan["updated_at"] = updated_at
    plan.setdefault("revision_notes", []).append(
        {
            "updated_at": updated_at,
            "change": "Updated requested caption text for the 'いらないもの' statement.",
            "old_text": OLD_TEXT,
            "new_text": NEW_TEXT,
            "changed_count": len(changed),
        }
    )
    save(EDIT_PLAN, plan)
    report = {
        "schema_version": "iranai_caption_text_update_report.v1",
        "project_id": "layer-x-domain-expert",
        "updated_at": updated_at,
        "old_text": OLD_TEXT,
        "new_text": NEW_TEXT,
        "changed_count": len(changed),
        "changes": changed,
    }
    save(REPORT_PATH, report)
    print(json.dumps({"changed_count": len(changed), "report": str(REPORT_PATH)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
