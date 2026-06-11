from __future__ import annotations

import copy
import json
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


PROJECT = Path(__file__).resolve().parents[1]
WORKSPACE = PROJECT.parents[1]
REPORTS = PROJECT / "output" / "reports"
EDIT_PLAN = REPORTS / "edit_plan.json"
REPORT = REPORTS / "caption_overlay_baseline_restore_report.json"
EDIT_PLAN_REPO_PATH = "projects/layer-x-domain-expert/output/reports/edit_plan.json"
JST = timezone(timedelta(hours=9))


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_baseline() -> Any:
    raw = subprocess.check_output(["git", "show", f"HEAD:{EDIT_PLAN_REPO_PATH}"], cwd=WORKSPACE)
    return json.loads(raw.decode("utf-8"))


def ref_window(event: dict[str, Any]) -> tuple[float, float] | None:
    source = event.get("reference_source") if isinstance(event.get("reference_source"), dict) else event.get("source")
    if not isinstance(source, dict) or source.get("in") is None or source.get("out") is None:
        return None
    return float(source["in"]), float(source["out"])


def duration(event: dict[str, Any]) -> float:
    return max(0.01, float(event.get("timeline_end") or 0.0) - float(event.get("timeline_start") or 0.0))


def root_id(event: dict[str, Any], overlay: dict[str, Any], index: int) -> str:
    metadata = overlay.get("metadata") if isinstance(overlay.get("metadata"), dict) else {}
    root = metadata.get("main_caption_id") or metadata.get("caption_cut_continuation_root_id") or overlay.get("caption_id")
    if root:
        return str(root).split("__cont__", 1)[0]
    return f"{event.get('event_id')}_caption_{index}"


def baseline_main_roots(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    roots: dict[str, dict[str, Any]] = {}
    for event in plan.get("timeline", []):
        if not isinstance(event, dict) or event.get("section") != "main":
            continue
        for index, overlay in enumerate(event.get("overlays", []) or []):
            if not isinstance(overlay, dict) or overlay.get("type") != "caption":
                continue
            metadata = overlay.get("metadata") if isinstance(overlay.get("metadata"), dict) else {}
            if metadata.get("caption_cut_continuation"):
                continue
            rid = root_id(event, overlay, index)
            if rid.startswith("main_caption_"):
                roots.setdefault(rid, copy.deepcopy(overlay))
    return roots


def current_roots(plan: dict[str, Any]) -> set[str]:
    roots: set[str] = set()
    for event in plan.get("timeline", []):
        if not isinstance(event, dict):
            continue
        for index, overlay in enumerate(event.get("overlays", []) or []):
            if isinstance(overlay, dict) and overlay.get("type") == "caption":
                roots.add(root_id(event, overlay, index))
    return roots


def caption_items(plan: dict[str, Any]) -> dict[str, tuple[dict[str, Any], dict[str, Any]]]:
    items: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for event in plan.get("timeline", []):
        if not isinstance(event, dict):
            continue
        for item in event.get("main_caption_plan_items", []) or []:
            if isinstance(item, dict) and item.get("caption_id"):
                items[str(item["caption_id"])] = (event, item)
    return items


def overlap(left: tuple[float, float], right: tuple[float, float]) -> float:
    return max(0.0, min(left[1], right[1]) - max(left[0], right[0]))


def target_event_for_window(events: list[dict[str, Any]], start: float, end: float) -> dict[str, Any] | None:
    candidates = []
    for event in events:
        if event.get("section") != "main":
            continue
        ref = ref_window(event)
        if not ref:
            continue
        contains_start = ref[0] - 0.05 <= start <= ref[1] + 0.05
        amount = overlap(ref, (start, end))
        if contains_start or amount >= 0.25:
            candidates.append((contains_start, amount, event))
    if candidates:
        return max(candidates, key=lambda item: (item[0], item[1]))[2]
    return None


def move_plan_item(root: str, events: list[dict[str, Any]], target: dict[str, Any]) -> None:
    moved: list[dict[str, Any]] = []
    for event in events:
        kept = []
        for item in event.get("main_caption_plan_items", []) or []:
            if isinstance(item, dict) and item.get("caption_id") == root:
                moved.append(item)
            else:
                kept.append(item)
        event["main_caption_plan_items"] = kept
    if moved and not any(isinstance(item, dict) and item.get("caption_id") == root for item in target.get("main_caption_plan_items", []) or []):
        target.setdefault("main_caption_plan_items", []).extend(moved)


def build_overlay(template: dict[str, Any], root: str, item: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    source_start = float(item["source_start_sec"])
    source_end = float(item["source_end_sec"])
    ref = ref_window(event) or (source_start, source_end)
    local_start = max(0.0, min(duration(event), source_start - ref[0]))
    local_end = min(duration(event), max(local_start + 0.2, source_end - ref[0]))
    overlay = copy.deepcopy(template)
    overlay["caption_id"] = root
    overlay["caption_no"] = item.get("caption_no", overlay.get("caption_no"))
    overlay["text"] = item.get("display_text") or overlay.get("text")
    overlay["start"] = round(local_start, 3)
    overlay["end"] = round(local_end, 3)
    if item.get("speaker_person_id"):
        overlay["speaker_person_id"] = item["speaker_person_id"]
    metadata = dict(overlay.get("metadata") or {})
    metadata.pop("caption_cut_continuation", None)
    metadata.pop("caption_continues_from_event_id", None)
    metadata["main_caption_id"] = root
    metadata["source"] = "edit_plan_caption_overlay"
    metadata["source_start_sec"] = round(source_start, 3)
    metadata["source_end_sec"] = round(source_end, 3)
    metadata["caption_start_sec"] = round(ref[0] + local_start, 3)
    metadata["caption_end_sec"] = round(ref[0] + local_end, 3)
    metadata["caption_source_full_window_sec"] = [round(source_start, 3), round(source_end, 3)]
    metadata["caption_handoff_end_sec"] = round(source_end, 3)
    metadata["caption_cut_continuation_root_id"] = root
    metadata["caption_source_of_truth"] = "edit_plan.json"
    metadata["audio_strict_timing"] = True
    metadata["display_timing_from_audio_analysis"] = True
    if item.get("speaker_person_id"):
        metadata["speaker_person_id"] = item["speaker_person_id"]
    if item.get("speaker_name"):
        metadata["speaker_name"] = item["speaker_name"]
    overlay["metadata"] = metadata
    overlay["audio_alignment"] = {
        "method": "restored_from_baseline_overlay_and_current_plan_item",
        "source_audio_media_id": "group_wide",
        "source_window_sec": [round(source_start, 3), round(source_end, 3)],
        "speech_window_sec": [round(ref[0] + local_start, 3), round(ref[0] + local_end, 3)],
        "diagnostics": {
            "restored_root_from_git_head_overlay": True,
            "target_event_id": event.get("event_id"),
        },
    }
    return overlay


def main() -> None:
    plan = load(EDIT_PLAN)
    baseline = load_baseline()
    events = [event for event in plan.get("timeline", []) if isinstance(event, dict)]
    baseline_roots = baseline_main_roots(baseline)
    roots_now = current_roots(plan)
    items = caption_items(plan)
    restored = []

    for root, template in sorted(baseline_roots.items()):
        if root in roots_now or root not in items:
            continue
        _, item = items[root]
        if item.get("source_start_sec") is None or item.get("source_end_sec") is None:
            continue
        target = target_event_for_window(events, float(item["source_start_sec"]), float(item["source_end_sec"]))
        if not target:
            continue
        overlay = build_overlay(template, root, item, target)
        target.setdefault("overlays", []).append(overlay)
        target["overlays"].sort(key=lambda entry: (0 if not isinstance(entry, dict) or entry.get("type") != "caption" else 1, float(entry.get("start") or 0.0) if isinstance(entry, dict) else 0.0))
        move_plan_item(root, events, target)
        restored.append(
            {
                "root_caption_id": root,
                "text": overlay.get("text"),
                "target_event_id": target.get("event_id"),
                "source_window_sec": [round(float(item["source_start_sec"]), 3), round(float(item["source_end_sec"]), 3)],
            }
        )

    updated_at = datetime.now(JST).isoformat(timespec="seconds")
    plan["updated_at"] = updated_at
    plan.setdefault("revision_notes", []).append(
        {
            "updated_at": updated_at,
            "script": Path(__file__).name,
            "summary": f"Restored {len(restored)} main caption overlays that existed in git HEAD and were accidentally removed during timing repair.",
        }
    )
    save(EDIT_PLAN, plan)
    report = {
        "schema_version": "caption_overlay_baseline_restore.v1",
        "project_id": "layer-x-domain-expert",
        "updated_at": updated_at,
        "restored_count": len(restored),
        "restored": restored,
    }
    save(REPORT, report)
    print(json.dumps({"restored_count": len(restored), "report": str(REPORT)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
