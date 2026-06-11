from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT_ROOT / "output" / "reports"
EDIT_PLAN = REPORTS / "edit_plan.json"
REPORT = REPORTS / "caption_cut_continuation_report.json"
MIN_OVERLAP_SEC = 0.20
NEXT_CAPTION_GAP_SEC = 0.04


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def event_ref_window(event: dict[str, Any]) -> tuple[float, float] | None:
    source = event.get("reference_source") if isinstance(event.get("reference_source"), dict) else event.get("source")
    if not isinstance(source, dict) or source.get("in") is None or source.get("out") is None:
        return None
    if source.get("media_id") != "group_wide":
        return None
    return float(source["in"]), float(source["out"])


def event_duration(event: dict[str, Any]) -> float:
    return max(0.0, float(event.get("timeline_end") or 0.0) - float(event.get("timeline_start") or 0.0))


def caption_root_id(event: dict[str, Any], overlay: dict[str, Any], index: int) -> str:
    metadata = overlay.get("metadata") if isinstance(overlay.get("metadata"), dict) else {}
    if metadata.get("caption_continuation_root_id"):
        return str(metadata["caption_continuation_root_id"])
    if overlay.get("caption_id"):
        return str(overlay["caption_id"])
    if overlay.get("caption_no") is not None:
        return f"caption_no_{overlay['caption_no']}"
    return f"{event.get('event_id')}_caption_{index}"


def source_window(overlay: dict[str, Any]) -> tuple[float, float] | None:
    alignment = overlay.get("audio_alignment") if isinstance(overlay.get("audio_alignment"), dict) else {}
    aligned_source = alignment.get("source_window_sec")
    if isinstance(aligned_source, list) and len(aligned_source) == 2:
        try:
            return float(aligned_source[0]), float(aligned_source[1])
        except (TypeError, ValueError):
            pass
    metadata = overlay.get("metadata") if isinstance(overlay.get("metadata"), dict) else {}
    if metadata.get("source_start_sec") is not None and metadata.get("source_end_sec") is not None:
        try:
            return float(metadata["source_start_sec"]), float(metadata["source_end_sec"])
        except (TypeError, ValueError):
            return None
    return None


def display_start(overlay: dict[str, Any], fallback: float) -> float:
    alignment = overlay.get("audio_alignment") if isinstance(overlay.get("audio_alignment"), dict) else {}
    speech = alignment.get("speech_window_sec")
    if isinstance(speech, list) and len(speech) == 2:
        try:
            return float(speech[0])
        except (TypeError, ValueError):
            pass
    return fallback


def update_overlay_timing(
    event: dict[str, Any],
    overlay: dict[str, Any],
    root_id: str,
    full_window: tuple[float, float],
    handoff_end: float,
    local_start: float,
    local_end: float,
    *,
    continuation: bool,
    original_event_id: str,
) -> None:
    ref_start, _ = event_ref_window(event) or (0.0, 0.0)
    overlay["start"] = round(local_start, 3)
    overlay["end"] = round(local_end, 3)
    absolute_window = [round(ref_start + local_start, 3), round(ref_start + local_end, 3)]
    metadata = overlay.setdefault("metadata", {})
    if isinstance(metadata, dict):
        metadata["caption_cut_continuation_root_id"] = root_id
        metadata["caption_source_full_window_sec"] = [round(full_window[0], 3), round(full_window[1], 3)]
        metadata["caption_handoff_end_sec"] = round(handoff_end, 3)
        metadata["caption_start_sec"] = absolute_window[0]
        metadata["caption_end_sec"] = absolute_window[1]
        metadata["audio_strict_timing"] = True
        metadata["display_timing_from_audio_analysis"] = True
        if continuation:
            metadata["caption_cut_continuation"] = True
            metadata["caption_continues_from_event_id"] = original_event_id
        else:
            metadata.pop("caption_cut_continuation", None)
            metadata.pop("caption_continues_from_event_id", None)
    alignment = overlay.setdefault("audio_alignment", {})
    if isinstance(alignment, dict):
        alignment["method"] = "audio_source_window_with_cut_continuation"
        alignment["source_audio_media_id"] = "group_wide"
        alignment["source_window_sec"] = [round(full_window[0], 3), round(full_window[1], 3)]
        alignment["speech_window_sec"] = absolute_window
        diagnostics = alignment.setdefault("diagnostics", {})
        if isinstance(diagnostics, dict):
            diagnostics["cut_continuation_root_id"] = root_id
            diagnostics["caption_handoff_end_sec"] = round(handoff_end, 3)
            diagnostics["display_end_policy"] = "caption visibility is continued across cut boundaries until source phrase end or next caption handoff"


def remove_existing_continuations(events: list[dict[str, Any]]) -> int:
    removed = 0
    for event in events:
        overlays = event.get("overlays")
        if not isinstance(overlays, list):
            continue
        kept = []
        for overlay in overlays:
            metadata = overlay.get("metadata") if isinstance(overlay, dict) and isinstance(overlay.get("metadata"), dict) else {}
            if metadata.get("caption_cut_continuation"):
                removed += 1
                continue
            kept.append(overlay)
        event["overlays"] = kept
    return removed


def main() -> None:
    plan = read_json(EDIT_PLAN)
    events = [event for event in plan.get("timeline", []) if isinstance(event, dict)]
    removed = remove_existing_continuations(events)

    originals: list[dict[str, Any]] = []
    original_caption_starts: list[dict[str, Any]] = []
    for event_index, event in enumerate(events):
        ref_window = event_ref_window(event)
        if not ref_window:
            continue
        for overlay_index, overlay in enumerate(event.get("overlays", []) or []):
            if not (isinstance(overlay, dict) and overlay.get("type") == "caption"):
                continue
            src_window = source_window(overlay)
            if not src_window:
                continue
            root_id = caption_root_id(event, overlay, overlay_index)
            start_abs = display_start(overlay, src_window[0])
            original = {
                "event_index": event_index,
                "event": event,
                "overlay": overlay,
                "overlay_index": overlay_index,
                "root_id": root_id,
                "section": event.get("section"),
                "start_abs": start_abs,
                "source_window": src_window,
            }
            originals.append(original)
            original_caption_starts.append(
                {
                    "root_id": root_id,
                    "section": event.get("section"),
                    "start_abs": start_abs,
                }
            )

    added = 0
    updated = 0
    continued_roots: list[dict[str, Any]] = []
    for item in originals:
        event = item["event"]
        root_id = item["root_id"]
        section = item["section"]
        source_start, source_end = item["source_window"]
        # The continuation window must start at the caption source phrase, not
        # at a display time that may have been padded inside a previous cut.
        # Using padded display starts here causes captions to appear before the
        # spoken phrase when a caption begins close to a cut boundary.
        full_start = source_start
        full_end = source_end
        next_starts = [
            float(other["start_abs"])
            for other in original_caption_starts
            if other["section"] == section and other["root_id"] != root_id and float(other["start_abs"]) > full_start + 0.001
        ]
        handoff_end = full_end
        if next_starts:
            next_start = min(next_starts)
            if next_start < full_end:
                handoff_end = max(full_start + MIN_OVERLAP_SEC, next_start - NEXT_CAPTION_GAP_SEC)

        event_segments = []
        for target_event in events:
            if target_event.get("section") != section:
                continue
            ref_window = event_ref_window(target_event)
            if not ref_window:
                continue
            ref_start, ref_end = ref_window
            overlap_start = max(full_start, ref_start)
            overlap_end = min(handoff_end, ref_end)
            if overlap_end - overlap_start < MIN_OVERLAP_SEC:
                continue
            local_start = max(0.0, overlap_start - ref_start)
            local_end = min(event_duration(target_event), overlap_end - ref_start)
            if local_end - local_start < MIN_OVERLAP_SEC:
                continue
            event_segments.append((target_event, local_start, local_end))

        if not event_segments:
            continue

        original_event_id = str(event.get("event_id"))
        for target_event, local_start, local_end in event_segments:
            if target_event is event:
                update_overlay_timing(
                    target_event,
                    item["overlay"],
                    root_id,
                    (full_start, full_end),
                    handoff_end,
                    local_start,
                    local_end,
                    continuation=False,
                    original_event_id=original_event_id,
                )
                updated += 1
                continue
            clone = copy.deepcopy(item["overlay"])
            clone["caption_id"] = f"{root_id}__cont__{target_event.get('event_id')}"
            update_overlay_timing(
                target_event,
                clone,
                root_id,
                (full_start, full_end),
                handoff_end,
                local_start,
                local_end,
                continuation=True,
                original_event_id=original_event_id,
            )
            target_event.setdefault("overlays", []).append(clone)
            added += 1

        if len(event_segments) > 1:
            continued_roots.append(
                {
                    "root_id": root_id,
                    "text": item["overlay"].get("text"),
                    "source_window_sec": [round(full_start, 3), round(full_end, 3)],
                    "handoff_window_end_sec": round(handoff_end, 3),
                    "segment_count": len(event_segments),
                    "events": [segment[0].get("event_id") for segment in event_segments],
                }
            )

    for event in events:
        overlays = event.get("overlays")
        if isinstance(overlays, list):
            overlays.sort(key=lambda overlay: (str(overlay.get("type") or ""), float(overlay.get("start") or 0.0), str(overlay.get("caption_id") or "")) if isinstance(overlay, dict) else ("", 0.0, ""))

    plan.setdefault("metadata", {})["caption_cut_continuation"] = {
        "enabled": True,
        "method": "caption source windows are projected across group_wide reference events so display survives camera cuts",
        "continued_caption_count": len(continued_roots),
    }
    write_json(EDIT_PLAN, plan)
    report = {
        "schema_version": "caption_cut_continuation_report.v1",
        "removed_previous_continuations": removed,
        "updated_original_overlays": updated,
        "added_continuation_overlays": added,
        "continued_caption_count": len(continued_roots),
        "continued_captions": continued_roots,
    }
    write_json(REPORT, report)
    print(json.dumps({k: report[k] for k in ("removed_previous_continuations", "updated_original_overlays", "added_continuation_overlays", "continued_caption_count")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
