from __future__ import annotations

import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


PROJECT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT / "output" / "reports"
EDIT_PLAN = REPORTS / "edit_plan.json"
REPORT_PATH = REPORTS / "main_caption_timing_ssot_normalization_report.json"
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


def duration(event: dict[str, Any]) -> float:
    return max(0.01, float(event["timeline_end"]) - float(event["timeline_start"]))


def caption_source_start(overlay: dict[str, Any], event: dict[str, Any]) -> float | None:
    alignment = overlay.get("audio_alignment") if isinstance(overlay.get("audio_alignment"), dict) else {}
    speech = alignment.get("speech_window_sec")
    if isinstance(speech, list) and len(speech) == 2:
        try:
            return float(speech[0])
        except (TypeError, ValueError):
            pass
    metadata = overlay.get("metadata") if isinstance(overlay.get("metadata"), dict) else {}
    for key in ("source_start_sec", "caption_start_sec"):
        if metadata.get(key) is not None:
            try:
                return float(metadata[key])
            except (TypeError, ValueError):
                pass
    ref = ref_window(event)
    if ref:
        return ref[0] + float(overlay.get("start") or 0.0)
    return None


def display_duration(text: str) -> float:
    length = len(re.sub(r"\s+", "", text))
    if length <= 18:
        return 2.8
    if length <= 28:
        return 3.4
    if length <= 38:
        return 4.0
    return 4.6


def find_event_for_source_start(events: list[dict[str, Any]], source_start: float, fallback: dict[str, Any]) -> dict[str, Any]:
    candidates = []
    for event in events:
        if event.get("section") != "main":
            continue
        ref = ref_window(event)
        if not ref:
            continue
        if ref[0] - 0.05 <= source_start <= ref[1] + 0.05:
            remaining = ref[1] - source_start
            candidates.append((remaining, event))
    if candidates:
        return max(candidates, key=lambda item: item[0])[1]
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


def main() -> None:
    plan = load(EDIT_PLAN)
    events = plan.get("timeline", [])
    changes = []

    # Work from a snapshot so moving overlays does not disturb iteration.
    entries: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for event in events:
        if event.get("section") != "main":
            continue
        for overlay in event.get("overlays", []) or []:
            if isinstance(overlay, dict) and overlay.get("type") == "caption":
                entries.append((event, overlay))

    for old_event, overlay in entries:
        source_start = caption_source_start(overlay, old_event)
        if source_start is None:
            continue
        target_event = find_event_for_source_start(events, source_start, old_event)
        target_ref = ref_window(target_event)
        if not target_ref:
            continue
        target_duration = duration(target_event)
        local_start = max(0.0, min(target_duration, source_start - target_ref[0]))
        wanted_duration = display_duration(str(overlay.get("text") or ""))
        local_end = min(target_duration, local_start + wanted_duration)
        if local_end - local_start < 1.2:
            # If this would flash too briefly at the very end of a cut, keep it
            # visible from the beginning of the next cut only when the next cut
            # begins within 0.7s of the source start.
            next_events = [
                event
                for event in events
                if event.get("section") == "main"
                and ref_window(event)
                and 0.0 <= (ref_window(event)[0] - source_start) <= 0.7
            ]
            if next_events:
                target_event = next_events[0]
                target_ref = ref_window(target_event)
                target_duration = duration(target_event)
                local_start = 0.0
                local_end = min(target_duration, wanted_duration)
        old_timing = [overlay.get("start"), overlay.get("end")]
        old_event_id = old_event.get("event_id")
        if old_event is not target_event:
            old_event["overlays"] = [item for item in old_event.get("overlays", []) if item is not overlay]
            target_event.setdefault("overlays", []).append(overlay)
            move_context_item(str(overlay.get("caption_id") or ""), old_event, target_event)
        overlay["start"] = round(local_start, 3)
        overlay["end"] = round(local_end, 3)
        metadata = overlay.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["caption_start_sec"] = round(target_ref[0] + local_start, 3)
            metadata["caption_end_sec"] = round(target_ref[0] + local_end, 3)
            metadata["caption_source_of_truth"] = "edit_plan.json"
            metadata["display_timing_normalized"] = True
        if isinstance(overlay.get("audio_alignment"), dict):
            overlay["audio_alignment"].setdefault("diagnostics", {})["display_timing_normalized"] = True
        target_event["overlays"].sort(key=lambda item: (0 if item.get("type") == "topic_title" else 1, float(item.get("start") or 0.0)))
        if old_event_id != target_event.get("event_id") or old_timing != [overlay["start"], overlay["end"]]:
            changes.append(
                {
                    "caption_id": overlay.get("caption_id"),
                    "text": overlay.get("text"),
                    "old_event_id": old_event_id,
                    "new_event_id": target_event.get("event_id"),
                    "source_start_sec": round(source_start, 3),
                    "old_local_timing": old_timing,
                    "new_local_timing": [overlay["start"], overlay["end"]],
                }
            )

    updated_at = datetime.now(JST).isoformat(timespec="seconds")
    plan["updated_at"] = updated_at
    plan.setdefault("revision_notes", []).append(
        {
            "updated_at": updated_at,
            "change": "Normalized main caption display timing from edit_plan single source of truth.",
            "change_count": len(changes),
        }
    )
    save(EDIT_PLAN, plan)
    report = {
        "schema_version": "main_caption_timing_ssot_normalization.v1",
        "project_id": "layer-x-domain-expert",
        "updated_at": updated_at,
        "policy": "Caption source windows can be longer than display windows; display starts at the repaired source start and uses a short text-length-based duration.",
        "change_count": len(changes),
        "changes": changes,
    }
    save(REPORT_PATH, report)
    print(json.dumps({"change_count": len(changes), "report": str(REPORT_PATH)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
