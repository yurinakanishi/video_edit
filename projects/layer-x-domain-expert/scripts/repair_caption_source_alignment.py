from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT_ROOT / "output" / "reports"
EDIT_PLAN_PATH = REPORTS / "edit_plan.json"
REPORT_PATH = REPORTS / "caption_source_alignment_repair_report.json"

SOURCE_TOLERANCE_SEC = 0.08
MIN_OVERLAP_SEC = 0.20


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def event_id(event: dict[str, Any]) -> str:
    return str(event.get("event_id") or event.get("id") or "")


def event_ref_window(event: dict[str, Any]) -> tuple[float, float] | None:
    source = event.get("reference_source") if isinstance(event.get("reference_source"), dict) else event.get("source")
    if not isinstance(source, dict):
        return None
    if source.get("in") is None or source.get("out") is None:
        return None
    return float(source["in"]), float(source["out"])


def event_duration(event: dict[str, Any]) -> float:
    return max(0.01, float(event.get("timeline_end") or 0.0) - float(event.get("timeline_start") or 0.0))


def caption_source_window(overlay: dict[str, Any]) -> tuple[float, float] | None:
    alignment = overlay.get("audio_alignment") if isinstance(overlay.get("audio_alignment"), dict) else {}
    aligned_source = alignment.get("source_window_sec")
    if isinstance(aligned_source, list) and len(aligned_source) == 2:
        try:
            return float(aligned_source[0]), float(aligned_source[1])
        except (TypeError, ValueError):
            pass
    metadata = overlay.get("metadata") if isinstance(overlay.get("metadata"), dict) else {}
    start = metadata.get("source_start_sec", metadata.get("caption_start_sec"))
    end = metadata.get("source_end_sec", metadata.get("caption_end_sec"))
    if start is None:
        return None
    try:
        start_f = float(start)
        old_duration = max(0.8, float(overlay.get("end") or 0.0) - float(overlay.get("start") or 0.0))
        end_f = float(end) if end is not None else start_f + old_duration
        return start_f, max(start_f + 0.2, end_f)
    except (TypeError, ValueError):
        pass
    speech_window = alignment.get("speech_window_sec")
    if isinstance(speech_window, list) and len(speech_window) == 2:
        try:
            return float(speech_window[0]), float(speech_window[1])
        except (TypeError, ValueError):
            pass
    return None


def overlap(left: tuple[float, float], right: tuple[float, float]) -> float:
    return max(0.0, min(left[1], right[1]) - max(left[0], right[0]))


def caption_allowed_in_event(event: dict[str, Any]) -> bool:
    if str(event.get("section") or "") not in {"digest", "main"}:
        return False
    if str(event.get("caption_policy") or "").startswith("no_caption"):
        return False
    overlays = event.get("overlays") if isinstance(event.get("overlays"), list) else []
    if any(isinstance(overlay, dict) and overlay.get("type") == "intro_profile_card" for overlay in overlays):
        return False
    return True


def find_best_event(
    events: list[dict[str, Any]],
    source_window: tuple[float, float],
    *,
    section: str | None,
) -> dict[str, Any] | None:
    candidates = []
    source_mid = (source_window[0] + source_window[1]) / 2.0
    for event in events:
        if section is not None and event.get("section") != section:
            continue
        if not caption_allowed_in_event(event):
            continue
        ref = event_ref_window(event)
        if not ref:
            continue
        amount = overlap(source_window, ref)
        contains_mid = ref[0] - SOURCE_TOLERANCE_SEC <= source_mid <= ref[1] + SOURCE_TOLERANCE_SEC
        contains_start = ref[0] - SOURCE_TOLERANCE_SEC <= source_window[0] <= ref[1] + SOURCE_TOLERANCE_SEC
        if amount >= MIN_OVERLAP_SEC or contains_mid or contains_start:
            candidates.append((amount, contains_mid, contains_start, -abs(source_mid - ((ref[0] + ref[1]) / 2.0)), event))
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item[1], item[0], item[2], item[3]))[-1]


def has_same_caption(event: dict[str, Any], overlay: dict[str, Any]) -> bool:
    text = str(overlay.get("text") or "")
    caption_id = str(overlay.get("caption_id") or "")
    for existing in event.get("overlays", []):
        if not isinstance(existing, dict) or existing.get("type") != "caption":
            continue
        if caption_id and str(existing.get("caption_id") or "") == caption_id:
            return True
        if text and str(existing.get("text") or "") == text:
            return True
    return False


def set_overlay_local_timing(event: dict[str, Any], overlay: dict[str, Any], source_window: tuple[float, float]) -> None:
    ref = event_ref_window(event)
    if not ref:
        return
    duration = event_duration(event)
    old_duration = max(0.8, float(overlay.get("end") or 0.0) - float(overlay.get("start") or 0.0))
    local_start = max(0.0, source_window[0] - ref[0])
    local_end = min(duration, source_window[1] - ref[0])
    if local_end - local_start < min(0.6, old_duration):
        local_end = min(duration, local_start + min(duration - local_start, old_duration))
    if local_end <= local_start:
        local_start = max(0.0, min(duration - 0.8, local_start))
        local_end = min(duration, local_start + 0.8)
    overlay["start"] = round(local_start, 3)
    overlay["end"] = round(local_end, 3)
    overlay["source_alignment_repaired"] = {
        "method": "move_caption_to_event_containing_source_window",
        "source_window_sec": [round(source_window[0], 3), round(source_window[1], 3)],
        "event_reference_window_sec": [round(ref[0], 3), round(ref[1], 3)],
    }


def main() -> None:
    plan = read_json(EDIT_PLAN_PATH)
    events = [event for event in plan.get("timeline", []) if isinstance(event, dict)]
    moved: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    retimed: list[dict[str, Any]] = []

    pending_moves: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any], tuple[float, float]]] = []
    for event in events:
        ref = event_ref_window(event)
        overlays = event.get("overlays") if isinstance(event.get("overlays"), list) else []
        kept = []
        for overlay in overlays:
            if not (isinstance(overlay, dict) and overlay.get("type") == "caption"):
                kept.append(overlay)
                continue
            source_window = caption_source_window(overlay)
            if not source_window or not ref:
                kept.append(overlay)
                continue
            current_overlap = overlap(source_window, ref)
            source_mid = (source_window[0] + source_window[1]) / 2.0
            in_current = current_overlap >= MIN_OVERLAP_SEC or (ref[0] - SOURCE_TOLERANCE_SEC <= source_mid <= ref[1] + SOURCE_TOLERANCE_SEC)
            expected_start = max(0.0, source_window[0] - ref[0])
            current_start = float(overlay.get("start") or 0.0)
            if in_current:
                if abs(current_start - expected_start) > 0.15:
                    old = {"start": overlay.get("start"), "end": overlay.get("end")}
                    set_overlay_local_timing(event, overlay, source_window)
                    retimed.append(
                        {
                            "event_id": event_id(event),
                            "caption_id": overlay.get("caption_id"),
                            "text": overlay.get("text"),
                            "old": old,
                            "new": {"start": overlay.get("start"), "end": overlay.get("end")},
                        }
                    )
                kept.append(overlay)
                continue
            target = find_best_event(events, source_window, section=str(event.get("section") or "") or None)
            if target and target is not event:
                pending_moves.append((event, target, copy.deepcopy(overlay), source_window))
                moved.append(
                    {
                        "caption_id": overlay.get("caption_id"),
                        "text": overlay.get("text"),
                        "from_event": event_id(event),
                        "to_event": event_id(target),
                        "source_window_sec": [round(source_window[0], 3), round(source_window[1], 3)],
                    }
                )
            else:
                removed.append(
                    {
                        "event_id": event_id(event),
                        "caption_id": overlay.get("caption_id"),
                        "text": overlay.get("text"),
                        "reason": "caption source window is not present in any caption-eligible rendered event",
                        "source_window_sec": [round(source_window[0], 3), round(source_window[1], 3)],
                    }
                )
            # Drop from original event when moved or removed.
        event["overlays"] = kept

    for _, target, overlay, source_window in pending_moves:
        if has_same_caption(target, overlay):
            continue
        set_overlay_local_timing(target, overlay, source_window)
        target.setdefault("overlays", []).append(overlay)

    for event in events:
        if isinstance(event.get("overlays"), list):
            event["overlays"].sort(key=lambda item: (0 if not isinstance(item, dict) or item.get("type") != "caption" else 1, float(item.get("start") or 0.0) if isinstance(item, dict) else 0.0))

    plan["updated_at"] = datetime.now(timezone.utc).isoformat()
    plan.setdefault("revision_notes", []).append(
        {
            "updated_at": plan["updated_at"],
            "script": Path(__file__).name,
            "summary": f"Repaired caption source alignment: moved {len(moved)}, retimed {len(retimed)}, removed {len(removed)}.",
        }
    )
    write_json(EDIT_PLAN_PATH, plan)
    report = {
        "schema_version": "caption_source_alignment_repair_report.v1",
        "project_id": "layer-x-domain-expert",
        "moved_count": len(moved),
        "retimed_count": len(retimed),
        "removed_count": len(removed),
        "moved": moved,
        "retimed": retimed,
        "removed": removed,
    }
    write_json(REPORT_PATH, report)
    print(json.dumps({"moved": len(moved), "retimed": len(retimed), "removed": len(removed), "report": str(REPORT_PATH)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
