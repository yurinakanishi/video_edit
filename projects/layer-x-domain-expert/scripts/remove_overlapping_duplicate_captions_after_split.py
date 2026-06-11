from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT_ROOT / "output" / "reports"
EDIT_PLAN = REPORTS / "edit_plan.json"
REPORT = REPORTS / "overlapping_duplicate_caption_removal_report.json"
JST = timezone(timedelta(hours=9))

REMOVE_ROOTS = {
    "main_caption_023": "Overlaps the new split units for main_caption_022 in the same source window.",
    "main_caption_strong_003": "Duplicate of the polished main_caption_078 unit.",
    "main_caption_083": "Longer duplicate of main_caption_strong_005.",
    "main_caption_auto_025": "Duplicate of the polished main_caption_088 unit.",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_root(value: Any) -> str:
    text = str(value or "")
    if "__unit_" in text:
        return text.split("__unit_", 1)[0]
    if "__cont__" in text:
        return text.split("__cont__", 1)[0]
    return text


def root_for_overlay(event: dict[str, Any], overlay: dict[str, Any], index: int) -> str:
    metadata = overlay.get("metadata") if isinstance(overlay.get("metadata"), dict) else {}
    for key in ("speech_unit_split_root_id", "main_caption_id", "caption_cut_continuation_root_id", "caption_continuation_root_id"):
        if metadata.get(key):
            return normalize_root(metadata[key])
    if overlay.get("caption_id"):
        return normalize_root(overlay.get("caption_id"))
    return f"{event.get('event_id')}_caption_{index}"


def root_for_item(item: dict[str, Any]) -> str:
    if item.get("speech_unit_split_root_id"):
        return normalize_root(item.get("speech_unit_split_root_id"))
    return normalize_root(item.get("caption_id"))


def main() -> None:
    plan = read_json(EDIT_PLAN)
    removed = []
    events = [event for event in plan.get("timeline", []) if isinstance(event, dict)]
    for event in events:
        overlays = event.get("overlays") if isinstance(event.get("overlays"), list) else []
        kept_overlays = []
        for index, overlay in enumerate(overlays):
            if isinstance(overlay, dict) and overlay.get("type") == "caption":
                root = root_for_overlay(event, overlay, index)
                if root in REMOVE_ROOTS:
                    removed.append(
                        {
                            "event_id": event.get("event_id"),
                            "root_caption_id": root,
                            "caption_id": overlay.get("caption_id"),
                            "text": overlay.get("text"),
                            "reason": REMOVE_ROOTS[root],
                        }
                    )
                    continue
            kept_overlays.append(overlay)
        event["overlays"] = kept_overlays

        items = event.get("main_caption_plan_items") if isinstance(event.get("main_caption_plan_items"), list) else []
        kept_items = []
        for item in items:
            if isinstance(item, dict) and root_for_item(item) in REMOVE_ROOTS:
                continue
            kept_items.append(item)
        event["main_caption_plan_items"] = kept_items

    now = datetime.now(JST).isoformat(timespec="seconds")
    plan["updated_at"] = now
    plan.setdefault("revision_notes", []).append(
        {
            "updated_at": now,
            "script": Path(__file__).name,
            "summary": f"Removed {len(removed)} overlapping duplicate caption overlays after speech-unit splitting.",
            "removed_roots": sorted(REMOVE_ROOTS),
            "report": str(REPORT),
        }
    )
    write_json(EDIT_PLAN, plan)
    report = {
        "schema_version": "overlapping_duplicate_caption_removal_report.v1",
        "generated_at": now,
        "removed_root_reasons": REMOVE_ROOTS,
        "removed_overlay_count": len(removed),
        "removed_overlays": removed,
    }
    write_json(REPORT, report)
    print(json.dumps({"removed_overlay_count": len(removed), "report": str(REPORT)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
