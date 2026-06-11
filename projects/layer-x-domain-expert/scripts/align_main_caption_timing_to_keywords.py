from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


PROJECT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT / "output" / "reports"
EDIT_PLAN = REPORTS / "edit_plan.json"
AUDIT_PATH = REPORTS / "main_caption_keyword_timing_audit.json"
REPORT_PATH = REPORTS / "main_caption_keyword_timing_repair_report.json"
JST = timezone(timedelta(hours=9))


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ref_window(event: dict[str, Any]) -> tuple[float, float] | None:
    source = event.get("reference_source") if isinstance(event.get("reference_source"), dict) else event.get("source")
    if not isinstance(source, dict) or source.get("in") is None or source.get("out") is None:
        return None
    return float(source["in"]), float(source["out"])


def event_duration(event: dict[str, Any]) -> float:
    return max(0.01, float(event.get("timeline_end") or 0.0) - float(event.get("timeline_start") or 0.0))


def find_event_for_source_time(events: list[dict[str, Any]], source_time: float, fallback: dict[str, Any]) -> dict[str, Any]:
    for event in events:
        if event.get("section") != "main":
            continue
        ref = ref_window(event)
        if ref and ref[0] - 0.05 <= source_time <= ref[1] + 0.05:
            return event
    return fallback


def move_context_item(caption_id: str, old_event: dict[str, Any], new_event: dict[str, Any]) -> None:
    if old_event is new_event:
        return
    moved = []
    kept = []
    for item in old_event.get("main_caption_plan_items", []) or []:
        if isinstance(item, dict) and item.get("caption_id") == caption_id:
            moved.append(item)
        else:
            kept.append(item)
    old_event["main_caption_plan_items"] = kept
    if moved:
        new_event.setdefault("main_caption_plan_items", []).extend(moved)


def audio_window_end(overlay: dict[str, Any], fallback_start: float) -> float:
    alignment = overlay.get("audio_alignment") if isinstance(overlay.get("audio_alignment"), dict) else {}
    for key in ("speech_window_sec", "source_window_sec"):
        window = alignment.get(key)
        if isinstance(window, list) and len(window) == 2:
            try:
                end = float(window[1])
                if end > fallback_start:
                    return end
            except (TypeError, ValueError):
                pass
    metadata = overlay.get("metadata") if isinstance(overlay.get("metadata"), dict) else {}
    for key in ("caption_end_sec", "source_end_sec"):
        if metadata.get(key) is not None:
            try:
                end = float(metadata[key])
                if end > fallback_start:
                    return end
            except (TypeError, ValueError):
                pass
    return fallback_start + 1.2


def main() -> None:
    plan = load(EDIT_PLAN)
    audit = load(AUDIT_PATH)
    issues = audit.get("issues", [])
    issue_by_caption: dict[str, dict[str, Any]] = {
        str(issue.get("caption_id")): issue
        for issue in issues
        if issue.get("caption_id") and issue.get("expected_keyword_source_start") is not None
    }
    changes: list[dict[str, Any]] = []
    events = plan.get("timeline", [])

    # Snapshot because overlays may move between adjacent events.
    entries: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for event in events:
        if event.get("section") != "main":
            continue
        for overlay in event.get("overlays", []) or []:
            if isinstance(overlay, dict) and overlay.get("type") == "caption":
                entries.append((event, overlay))

    for event, overlay in entries:
        ref = ref_window(event)
        if not ref:
            continue
        caption_id = str(overlay.get("caption_id") or "")
        issue = issue_by_caption.get(caption_id)
        if not issue:
            continue
        expected_source_start = float(issue["expected_keyword_source_start"])
        target_event = find_event_for_source_time(events, expected_source_start, event)
        target_ref = ref_window(target_event)
        if not target_ref:
            continue
        target_duration = event_duration(target_event)
        new_start = max(0.0, min(target_duration - 0.8, expected_source_start - target_ref[0]))
        expected_source_end = audio_window_end(overlay, expected_source_start)
        new_end = min(target_duration, max(new_start + 0.2, expected_source_end - target_ref[0]))
        if new_end - new_start < 1.2:
            new_end = min(target_duration, new_start + 1.2)
        old = [float(overlay.get("start") or 0.0), float(overlay.get("end") or 0.0)]
        old_event_id = event.get("event_id")
        if target_event is not event:
            event["overlays"] = [item for item in event.get("overlays", []) if item is not overlay]
            target_event.setdefault("overlays", []).append(overlay)
            move_context_item(caption_id, event, target_event)
        overlay["start"] = round(new_start, 3)
        overlay["end"] = round(new_end, 3)
        metadata = overlay.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["caption_start_sec"] = round(target_ref[0] + new_start, 3)
            metadata["caption_end_sec"] = round(target_ref[0] + new_end, 3)
            metadata["keyword_timing_aligned"] = True
            metadata["keyword_timing_anchor"] = issue.get("matched_fragment")
            metadata["caption_source_of_truth"] = "edit_plan.json"
            metadata["audio_strict_timing"] = True
            metadata["display_timing_from_audio_analysis"] = True
        alignment = overlay.setdefault("audio_alignment", {})
        if isinstance(alignment, dict):
            alignment["method"] = "main_keyword_anchor_timing"
            alignment["speech_window_sec"] = [round(target_ref[0] + new_start, 3), round(target_ref[0] + new_end, 3)]
            alignment["display_timing_source"] = "audio_analysis"
            alignment.setdefault("diagnostics", {})
            alignment["diagnostics"]["matched_fragment"] = issue.get("matched_fragment")
            alignment["diagnostics"]["old_local_timing"] = old
            alignment["diagnostics"]["early_by_sec"] = issue.get("early_by_sec")
        target_event["overlays"].sort(key=lambda item: (0 if item.get("type") == "topic_title" else 1, float(item.get("start") or 0.0)))
        changes.append(
            {
                "event_id": old_event_id,
                "new_event_id": target_event.get("event_id"),
                "caption_id": caption_id,
                "text": overlay.get("text"),
                "matched_fragment": issue.get("matched_fragment"),
                "old_local_timing": old,
                "new_local_timing": [overlay["start"], overlay["end"]],
                "old_source_start": issue.get("displayed_source_start"),
                "new_source_start": round(target_ref[0] + new_start, 3),
                "early_by_sec": issue.get("early_by_sec"),
            }
        )

    updated_at = datetime.now(JST).isoformat(timespec="seconds")
    plan["updated_at"] = updated_at
    plan.setdefault("revision_notes", []).append(
        {
            "updated_at": updated_at,
            "change": "Aligned main captions to spoken keyword anchors from edit_plan single source of truth.",
            "change_count": len(changes),
        }
    )
    save(EDIT_PLAN, plan)
    report = {
        "schema_version": "main_caption_keyword_timing_repair.v1",
        "project_id": "layer-x-domain-expert",
        "updated_at": updated_at,
        "source_of_truth": "edit_plan.json timeline[].overlays[type=caption]",
        "input_audit": str(AUDIT_PATH),
        "change_count": len(changes),
        "changes": changes,
    }
    save(REPORT_PATH, report)
    print(json.dumps({"change_count": len(changes), "report": str(REPORT_PATH)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
