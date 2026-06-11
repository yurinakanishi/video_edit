from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT_ROOT / "output" / "reports"
EDIT_PLAN_PATH = REPORTS / "edit_plan.json"
MAIN_CAPTION_PLAN_PATH = REPORTS / "main_caption_plan.json"
REPORT_PATH = REPORTS / "removed_requested_captions_20260611.json"

REMOVE_TEXTS = {
    "それぞれの立場から開発に関与している",
    "実務経験をプロダクト開発に持ち込む役割",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def text_matches(value: Any) -> bool:
    text = str(value or "")
    return any(remove_text in text for remove_text in REMOVE_TEXTS)


def remove_from_edit_plan() -> list[dict[str, Any]]:
    plan = read_json(EDIT_PLAN_PATH)
    removed: list[dict[str, Any]] = []
    for event in plan.get("timeline", []):
        overlays = event.get("overlays")
        if not isinstance(overlays, list):
            continue
        kept = []
        for overlay in overlays:
            if isinstance(overlay, dict) and overlay.get("type") == "caption" and text_matches(overlay.get("text")):
                removed.append(
                    {
                        "source_file": str(EDIT_PLAN_PATH),
                        "event_id": event.get("event_id"),
                        "caption_id": overlay.get("caption_id"),
                        "text": overlay.get("text"),
                        "start": overlay.get("start"),
                        "end": overlay.get("end"),
                    }
                )
            else:
                kept.append(overlay)
        event["overlays"] = kept
    for event in plan.get("timeline", []):
        metadata = event.get("metadata")
        if not isinstance(metadata, dict):
            continue
        for key in ("main_caption", "caption_candidate", "source_caption"):
            candidate = metadata.get(key)
            if isinstance(candidate, dict) and (
                text_matches(candidate.get("display_text"))
                or text_matches(candidate.get("full_reference_text"))
                or text_matches(candidate.get("text"))
            ):
                candidate["excluded_from_render"] = True
                candidate["exclude_reason"] = "Removed per user review on 2026-06-11."
                removed.append(
                    {
                        "source_file": str(EDIT_PLAN_PATH),
                        "event_id": event.get("event_id"),
                        "metadata_key": key,
                        "display_text": candidate.get("display_text") or candidate.get("text"),
                        "action": "metadata_candidate_excluded",
                    }
                )
    for event in plan.get("timeline", []):
        items = event.get("main_caption_plan_items")
        if not isinstance(items, list):
            continue
        kept_items = []
        for item in items:
            if isinstance(item, dict) and (text_matches(item.get("display_text")) or text_matches(item.get("full_reference_text"))):
                removed.append(
                    {
                        "source_file": str(EDIT_PLAN_PATH),
                        "event_id": event.get("event_id"),
                        "caption_id": item.get("caption_id"),
                        "display_text": item.get("display_text"),
                        "action": "main_caption_plan_item_removed",
                    }
                )
            else:
                kept_items.append(item)
        event["main_caption_plan_items"] = kept_items
    plan["updated_at"] = datetime.now(timezone.utc).isoformat()
    plan.setdefault("revision_notes", []).append(
        {
            "updated_at": plan["updated_at"],
            "script": Path(__file__).name,
            "summary": "Removed two user-requested main caption overlays from the render plan.",
        }
    )
    write_json(EDIT_PLAN_PATH, plan)
    return removed


def disable_in_main_caption_plan() -> list[dict[str, Any]]:
    if not MAIN_CAPTION_PLAN_PATH.exists():
        return []
    plan = read_json(MAIN_CAPTION_PLAN_PATH)
    disabled: list[dict[str, Any]] = []
    items = plan.get("captions") if isinstance(plan, dict) else None
    if not isinstance(items, list):
        return []
    kept_items = []
    for item in items:
        if not isinstance(item, dict):
            kept_items.append(item)
            continue
        if text_matches(item.get("display_text")) or text_matches(item.get("full_reference_text")):
            disabled.append(
                {
                    "source_file": str(MAIN_CAPTION_PLAN_PATH),
                    "caption_id": item.get("caption_id") or item.get("id"),
                    "display_text": item.get("display_text"),
                    "action": "main_caption_plan_item_removed",
                }
            )
        else:
            kept_items.append(item)
    plan["captions"] = kept_items
    write_json(MAIN_CAPTION_PLAN_PATH, plan)
    return disabled


def main() -> None:
    removed = remove_from_edit_plan()
    disabled = disable_in_main_caption_plan()
    payload = {
        "schema_version": "removed_requested_captions_20260611.v1",
        "project_id": "layer-x-domain-expert",
        "remove_texts": sorted(REMOVE_TEXTS),
        "removed_from_edit_plan": removed,
        "disabled_in_main_caption_plan": disabled,
    }
    write_json(REPORT_PATH, payload)
    print(json.dumps({"removed": len(removed), "disabled": len(disabled), "report": str(REPORT_PATH)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
