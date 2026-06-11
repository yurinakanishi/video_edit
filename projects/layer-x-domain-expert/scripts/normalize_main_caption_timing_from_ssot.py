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


def caption_source_window(overlay: dict[str, Any], event: dict[str, Any]) -> tuple[float, float] | None:
    alignment = overlay.get("audio_alignment") if isinstance(overlay.get("audio_alignment"), dict) else {}
    speech = alignment.get("speech_window_sec")
    if isinstance(speech, list) and len(speech) == 2:
        try:
            return float(speech[0]), float(speech[1])
        except (TypeError, ValueError):
            pass
    metadata = overlay.get("metadata") if isinstance(overlay.get("metadata"), dict) else {}
    for start_key, end_key in (("source_start_sec", "source_end_sec"), ("caption_start_sec", "caption_end_sec")):
        if metadata.get(start_key) is not None:
            try:
                start = float(metadata[start_key])
                end = float(metadata[end_key]) if metadata.get(end_key) is not None else start + max(0.8, float(overlay.get("end") or 0.0) - float(overlay.get("start") or 0.0))
                return start, max(start + 0.2, end)
            except (TypeError, ValueError):
                pass
    ref = ref_window(event)
    if ref:
        start = ref[0] + float(overlay.get("start") or 0.0)
        end = ref[0] + float(overlay.get("end") or overlay.get("start") or 0.0)
        return start, max(start + 0.2, end)
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
        source_window = caption_source_window(overlay, old_event)
        if source_window is None:
            continue
        source_start, source_end = source_window
        target_event = find_event_for_source_start(events, source_start, old_event)
        target_ref = ref_window(target_event)
        if not target_ref:
            continue
        target_duration = duration(target_event)
        local_start = max(0.0, min(target_duration, source_start - target_ref[0]))
        local_end = min(target_duration, max(local_start + 0.2, source_end - target_ref[0]))
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
            metadata["audio_strict_timing"] = True
            metadata["display_timing_from_audio_analysis"] = True
        if isinstance(overlay.get("audio_alignment"), dict):
            overlay["audio_alignment"]["speech_window_sec"] = [round(target_ref[0] + local_start, 3), round(target_ref[0] + local_end, 3)]
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
        "policy": "Caption display windows follow edit_plan audio_alignment.speech_window_sec instead of fixed text-length durations.",
        "change_count": len(changes),
        "changes": changes,
    }
    save(REPORT_PATH, report)
    print(json.dumps({"change_count": len(changes), "report": str(REPORT_PATH)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
