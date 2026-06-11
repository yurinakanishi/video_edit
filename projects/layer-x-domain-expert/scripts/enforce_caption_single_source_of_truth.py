from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


PROJECT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT / "output" / "reports"
EDIT_PLAN = REPORTS / "edit_plan.json"
POLICY_JSON = REPORTS / "caption_source_of_truth.json"
REPORT_PATH = REPORTS / "caption_single_source_of_truth_report.json"
INSTRUCTIONS = PROJECT / "VIDEO_EDITING_INSTRUCTIONS.md"
JST = timezone(timedelta(hours=9))


POLICY = {
    "schema_version": "caption_source_of_truth.v1",
    "project_id": "layer-x-domain-expert",
    "canonical_caption_artifact": "output/reports/edit_plan.json",
    "canonical_caption_path": "timeline[].overlays[type=caption]",
    "rules": [
        "The renderer reads captions only from edit_plan.json caption overlays.",
        "caption_review.md is generated from edit_plan.json and is review-only.",
        "No markdown caption source is allowed for this project.",
        "main_caption_plan.json is an intermediate analysis cache; after manual edits, edit_plan.json is authoritative.",
    ],
}


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def update_edit_plan() -> dict[str, Any]:
    plan = load(EDIT_PLAN)
    updated_at = datetime.now(JST).isoformat(timespec="seconds")
    plan["caption_source_of_truth"] = {
        **POLICY,
        "updated_at": updated_at,
    }
    overlay_count = 0
    context_count = 0
    old_source_values: dict[str, int] = {}
    for event in plan.get("timeline", []):
        for overlay in event.get("overlays", []) or []:
            if not (isinstance(overlay, dict) and overlay.get("type") == "caption"):
                continue
            overlay_count += 1
            metadata = overlay.setdefault("metadata", {})
            if isinstance(metadata, dict):
                old = str(metadata.get("source") or "")
                if old:
                    old_source_values[old] = old_source_values.get(old, 0) + 1
                metadata["source"] = "edit_plan_caption_overlay"
                metadata["caption_source_of_truth"] = "edit_plan.json"
        for item in event.get("main_caption_plan_items", []) or []:
            if isinstance(item, dict) and item.get("caption_id"):
                context_count += 1
                item["source"] = "edit_plan_embedded_caption_context"
                item.pop("original_source_note", None)
                item["caption_source_of_truth"] = "edit_plan.json"
    plan["updated_at"] = updated_at
    plan.setdefault("revision_notes", []).append(
        {
            "updated_at": updated_at,
            "change": "Declared edit_plan.json caption overlays as the single source of truth and demoted markdown/intermediate sources.",
            "caption_overlay_count": overlay_count,
            "embedded_context_count": context_count,
        }
    )
    save(EDIT_PLAN, plan)
    return {
        "caption_overlay_count": overlay_count,
        "embedded_context_count": context_count,
        "old_overlay_metadata_source_values": old_source_values,
    }


def update_instructions() -> bool:
    marker = "### Caption Single Source Of Truth"
    text = INSTRUCTIONS.read_text(encoding="utf-8")
    block = f"""

{marker}

For this project, rendered caption subtitles have exactly one active source of truth:

- Canonical artifact: `output/reports/edit_plan.json`
- Canonical path: `timeline[].overlays[type=caption]`

`caption_review.md` is generated from `edit_plan.json` for human review only. Do not edit it as an input.

There is no markdown caption source for this project. `main_caption_plan.json` is an intermediate analysis cache only; after manual edit decisions it must not override `edit_plan.json`.

Any caption timing, speaker, line break, text, or visibility fix must update `edit_plan.json` first. After that, regenerate `caption_review.md` from `edit_plan.json`.
"""
    if marker in text:
        return False
    INSTRUCTIONS.write_text(text.rstrip() + block + "\n", encoding="utf-8")
    return True


def main() -> None:
    updated_at = datetime.now(JST).isoformat(timespec="seconds")
    policy = {**POLICY, "updated_at": updated_at}
    save(POLICY_JSON, policy)
    edit_plan_result = update_edit_plan()
    instructions_changed = update_instructions()
    report = {
        "schema_version": "caption_single_source_of_truth_report.v1",
        "project_id": "layer-x-domain-expert",
        "updated_at": updated_at,
        "policy": policy,
        "edit_plan": edit_plan_result,
        "instructions_changed": instructions_changed,
    }
    save(REPORT_PATH, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
