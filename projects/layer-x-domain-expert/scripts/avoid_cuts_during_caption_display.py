from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT_ROOT / "output" / "reports"
EDIT_PLAN = REPORTS / "edit_plan.json"
REPORT = REPORTS / "caption_cut_boundary_avoidance_report.json"

# These constants mirror the active renderer behavior.  Captions can remain
# visible briefly after overlay.end because the renderer fades them out.
CAPTION_FADE_SEC = 0.10
CUT_AFTER_CAPTION_GAP_SEC = 0.12
START_GRACE_SEC = 0.04
MIN_EVENT_DURATION_SEC = 0.05
EMPTY_EVENT_ABSORB_THRESHOLD_SEC = 0.35
EPS = 0.001


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def round_sec(value: float) -> float:
    return round(float(value), 3)


def timed_overlay(overlay: dict[str, Any]) -> bool:
    return overlay.get("start") is not None and overlay.get("end") is not None


def is_caption(overlay: Any) -> bool:
    return isinstance(overlay, dict) and overlay.get("type") == "caption"


def is_continuation_caption(overlay: dict[str, Any]) -> bool:
    metadata = overlay.get("metadata") if isinstance(overlay.get("metadata"), dict) else {}
    return bool(metadata.get("caption_cut_continuation"))


def event_start(event: dict[str, Any]) -> float:
    return float(event.get("timeline_start") or 0.0)


def event_end(event: dict[str, Any]) -> float:
    return float(event.get("timeline_end") or 0.0)


def event_duration(event: dict[str, Any]) -> float:
    return max(0.0, event_end(event) - event_start(event))


def caption_key(event: dict[str, Any], overlay: dict[str, Any], index: int) -> str:
    metadata = overlay.get("metadata") if isinstance(overlay.get("metadata"), dict) else {}
    if overlay.get("caption_id"):
        return str(overlay["caption_id"])
    if metadata.get("caption_cut_continuation_root_id"):
        return str(metadata["caption_cut_continuation_root_id"])
    if overlay.get("source_segment_id"):
        return str(overlay["source_segment_id"])
    if overlay.get("source_srt_index") is not None:
        return f"srt_{overlay['source_srt_index']}_{event.get('event_id')}_{index}"
    return f"{event.get('event_id')}_caption_{index}"


def local_to_absolute(event: dict[str, Any], start: float, end: float) -> tuple[float, float]:
    base = event_start(event)
    return base + float(start), base + float(end)


def event_reference_window(event: dict[str, Any]) -> tuple[float, float] | None:
    source = event.get("reference_source") if isinstance(event.get("reference_source"), dict) else event.get("source")
    if not isinstance(source, dict):
        return None
    if source.get("media_id") != "group_wide":
        return None
    if source.get("in") is None or source.get("out") is None:
        return None
    return float(source["in"]), float(source["out"])


def source_to_absolute_timeline(event: dict[str, Any], source_time: float) -> float | None:
    ref = event_reference_window(event)
    if ref is None:
        return None
    return event_start(event) + (float(source_time) - ref[0])


def numeric_pair(value: Any) -> tuple[float, float] | None:
    if not (isinstance(value, list) and len(value) == 2):
        return None
    try:
        return float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return None


def source_window_for_caption(overlay: dict[str, Any]) -> tuple[float, float] | None:
    alignment = overlay.get("audio_alignment") if isinstance(overlay.get("audio_alignment"), dict) else {}
    source_window = numeric_pair(alignment.get("source_window_sec"))
    if source_window:
        return source_window
    metadata = overlay.get("metadata") if isinstance(overlay.get("metadata"), dict) else {}
    if metadata.get("source_start_sec") is not None and metadata.get("source_end_sec") is not None:
        try:
            return float(metadata["source_start_sec"]), float(metadata["source_end_sec"])
        except (TypeError, ValueError):
            return None
    return None


def full_caption_source_end(overlay: dict[str, Any]) -> float | None:
    metadata = overlay.get("metadata") if isinstance(overlay.get("metadata"), dict) else {}
    alignment = overlay.get("audio_alignment") if isinstance(overlay.get("audio_alignment"), dict) else {}
    diagnostics = alignment.get("diagnostics") if isinstance(alignment.get("diagnostics"), dict) else {}
    source_window = source_window_for_caption(overlay)
    full_window = numeric_pair(metadata.get("caption_source_full_window_sec")) or numeric_pair(diagnostics.get("full_unit_source_window_sec"))
    if not source_window or not full_window:
        return None
    handoff = metadata.get("caption_handoff_end_sec")
    try:
        handoff_end = float(handoff) if handoff is not None else full_window[1]
    except (TypeError, ValueError):
        handoff_end = full_window[1]
    target_end = min(full_window[1], handoff_end)
    # Previous continuation overlays sometimes carried the rest of a caption
    # across an event boundary.  When those overlays are removed, the base
    # caption must keep the full speech-unit window, otherwise it disappears
    # while the matching utterance is still being spoken.
    if target_end > source_window[1] + 0.05:
        return target_end
    return None


def visible_end(abs_end: float) -> float:
    return abs_end + CAPTION_FADE_SEC + CUT_AFTER_CAPTION_GAP_SEC


def copy_timing_fields_for_new_window(event: dict[str, Any], old_start: float, new_start: float, new_end: float) -> None:
    """Retarget source/reference/audio ranges to the new output window.

    Each existing in/out range maps linearly to the event output time.  When a
    cut boundary moves, this preserves the underlying continuous source content
    while assigning a longer or shorter output span to the event's layout.
    """

    for key in ("source", "reference_source"):
        source = event.get(key)
        if isinstance(source, dict) and source.get("in") is not None and source.get("out") is not None:
            old_in = float(source["in"])
            source["in"] = round_sec(old_in + (new_start - old_start))
            source["out"] = round_sec(old_in + (new_end - old_start))

    audio = event.get("audio")
    if isinstance(audio, dict):
        if audio.get("in") is not None and audio.get("out") is not None:
            old_audio_in = float(audio["in"])
            audio["in"] = round_sec(old_audio_in + (new_start - old_start))
            audio["out"] = round_sec(old_audio_in + (new_end - old_start))
        if audio.get("timing_reference_in") is not None and audio.get("timing_reference_out") is not None:
            old_ref_in = float(audio["timing_reference_in"])
            audio["timing_reference_in"] = round_sec(old_ref_in + (new_start - old_start))
            audio["timing_reference_out"] = round_sec(old_ref_in + (new_end - old_start))


def clean_caption_continuation_metadata(overlay: dict[str, Any]) -> None:
    metadata = overlay.get("metadata") if isinstance(overlay.get("metadata"), dict) else None
    if metadata is not None:
        metadata.pop("caption_cut_continuation", None)
        metadata.pop("caption_continues_from_event_id", None)
        metadata["caption_boundary_policy"] = "no_camera_cut_while_caption_visible"
        metadata["caption_boundary_safety_gap_sec"] = CUT_AFTER_CAPTION_GAP_SEC
    alignment = overlay.get("audio_alignment") if isinstance(overlay.get("audio_alignment"), dict) else None
    if alignment is not None:
        if alignment.get("method") == "audio_source_window_with_cut_continuation":
            alignment["method"] = "audio_source_window_no_cut_during_caption"
        diagnostics = alignment.get("diagnostics") if isinstance(alignment.get("diagnostics"), dict) else None
        if diagnostics is not None:
            diagnostics.pop("cut_continuation_root_id", None)
            diagnostics["display_end_policy"] = "camera cuts are moved outside the caption visible window"


def update_caption_source_end(overlay: dict[str, Any], caption: dict[str, Any]) -> None:
    source_window = caption.get("source_window")
    expanded_source_end = caption.get("expanded_source_end")
    if not (isinstance(source_window, tuple) and expanded_source_end is not None):
        return
    try:
        source_start = float(source_window[0])
        source_end = float(expanded_source_end)
    except (TypeError, ValueError):
        return

    metadata = overlay.get("metadata") if isinstance(overlay.get("metadata"), dict) else None
    if metadata is not None:
        metadata["caption_start_sec"] = round_sec(source_start)
        metadata["caption_end_sec"] = round_sec(source_end)
        metadata["source_start_sec"] = round_sec(source_start)
        metadata["source_end_sec"] = round_sec(source_end)
        metadata["caption_extended_to_full_speech_unit"] = True
        metadata["caption_extended_from_source_end_sec"] = round_sec(caption.get("expanded_from_source_end") or source_window[1])
    alignment = overlay.get("audio_alignment") if isinstance(overlay.get("audio_alignment"), dict) else None
    if alignment is not None:
        alignment["source_window_sec"] = [round_sec(source_start), round_sec(source_end)]
        alignment["speech_window_sec"] = [round_sec(source_start), round_sec(source_end)]
        diagnostics = alignment.setdefault("diagnostics", {})
        if isinstance(diagnostics, dict):
            diagnostics["caption_extended_to_full_speech_unit"] = True
            diagnostics["caption_extended_from_source_end_sec"] = round_sec(caption.get("expanded_from_source_end") or source_window[1])


def collect_base_captions(events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    captions: list[dict[str, Any]] = []
    removed_continuations = 0
    seen: set[tuple[str, float, float, str]] = set()
    for event_index, event in enumerate(events):
        for overlay_index, overlay in enumerate(event.get("overlays", []) or []):
            if not is_caption(overlay):
                continue
            if is_continuation_caption(overlay):
                removed_continuations += 1
                continue
            if not timed_overlay(overlay):
                continue
            abs_start, abs_end = local_to_absolute(event, float(overlay["start"]), float(overlay["end"]))
            source_window = source_window_for_caption(overlay)
            expanded_source_end = full_caption_source_end(overlay)
            expanded_from_source_end: float | None = None
            if expanded_source_end is not None:
                expanded_abs_end = source_to_absolute_timeline(event, expanded_source_end)
                if expanded_abs_end is not None and expanded_abs_end > abs_end + 0.05:
                    expanded_from_source_end = source_window[1] if source_window else None
                    abs_end = expanded_abs_end
            key = (
                caption_key(event, overlay, overlay_index),
                round_sec(abs_start),
                round_sec(abs_end),
                str(overlay.get("text") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            captions.append(
                {
                    "key": key[0],
                    "event_index": event_index,
                    "event_id": event.get("event_id"),
                    "abs_start": abs_start,
                    "abs_end": abs_end,
                    "visible_end": visible_end(abs_end),
                    "overlay": copy.deepcopy(overlay),
                    "text": str(overlay.get("text") or ""),
                    "section": event.get("section"),
                    "source_window": source_window,
                    "expanded_source_end": expanded_source_end,
                    "expanded_from_source_end": expanded_from_source_end,
                }
            )
    captions.sort(key=lambda item: (float(item["abs_start"]), float(item["abs_end"]), str(item["key"])))
    return captions, removed_continuations


def active_caption_blocks(boundary: float, captions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for caption in captions:
        start = float(caption["abs_start"])
        end_visible = float(caption["visible_end"])
        # A cut exactly at caption start is allowed.  The bad case is changing
        # camera/layout after the caption has already appeared and before it
        # has visually faded out.
        if start + START_GRACE_SEC < boundary < end_visible - EPS:
            blocks.append(caption)
    return blocks


def compute_new_boundaries(events: list[dict[str, Any]], captions: list[dict[str, Any]]) -> tuple[list[float], list[dict[str, Any]], list[dict[str, Any]]]:
    old_boundaries = [event_start(events[0])] + [event_end(event) for event in events]
    proposed = old_boundaries[:]
    moved: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []

    for boundary_index in range(1, len(old_boundaries) - 1):
        original = old_boundaries[boundary_index]
        candidate = original
        blockers = active_caption_blocks(candidate, captions)
        iterations = 0
        while blockers and iterations < 20:
            candidate = max(float(blocker["visible_end"]) for blocker in blockers)
            candidate = round_sec(candidate)
            blockers = active_caption_blocks(candidate, captions)
            iterations += 1

        if candidate <= original + EPS:
            continue

        max_allowed = old_boundaries[boundary_index + 1] - MIN_EVENT_DURATION_SEC
        if candidate > max_allowed:
            unresolved.append(
                {
                    "boundary_index": boundary_index,
                    "old_boundary_sec": round_sec(original),
                    "requested_new_boundary_sec": round_sec(candidate),
                    "max_allowed_sec": round_sec(max_allowed),
                    "prev_event_id": events[boundary_index - 1].get("event_id"),
                    "next_event_id": events[boundary_index].get("event_id"),
                    "blocking_captions": [
                        {
                            "key": blocker["key"],
                            "text": blocker["text"],
                            "abs_start": round_sec(blocker["abs_start"]),
                            "abs_end": round_sec(blocker["abs_end"]),
                            "visible_end": round_sec(blocker["visible_end"]),
                        }
                        for blocker in active_caption_blocks(original, captions)
                    ],
                }
            )
            candidate = max_allowed

        proposed[boundary_index] = candidate
        moved.append(
            {
                "boundary_index": boundary_index,
                "old_boundary_sec": round_sec(original),
                "new_boundary_sec": round_sec(candidate),
                "delta_sec": round_sec(candidate - original),
                "prev_event_id": events[boundary_index - 1].get("event_id"),
                "next_event_id": events[boundary_index].get("event_id"),
                "blocking_captions": [
                    {
                        "key": blocker["key"],
                        "text": blocker["text"],
                        "abs_start": round_sec(blocker["abs_start"]),
                        "abs_end": round_sec(blocker["abs_end"]),
                        "visible_end": round_sec(blocker["visible_end"]),
                    }
                    for blocker in active_caption_blocks(original, captions)
                ],
            }
        )

    for index in range(1, len(proposed)):
        if proposed[index] - proposed[index - 1] < MIN_EVENT_DURATION_SEC - EPS:
            unresolved.append(
                {
                    "boundary_index": index,
                    "reason": "minimum_event_duration_would_be_violated",
                    "previous_boundary_sec": round_sec(proposed[index - 1]),
                    "boundary_sec": round_sec(proposed[index]),
                    "event_id": events[index - 1].get("event_id") if index - 1 < len(events) else None,
                }
            )

    return proposed, moved, unresolved


def has_blocking_overlay(event: dict[str, Any]) -> bool:
    blocking_types = {"caption", "nameplate", "split_person_labels", "profile_card"}
    for overlay in event.get("overlays", []) or []:
        if isinstance(overlay, dict) and str(overlay.get("type") or "") in blocking_types:
            return True
    return False


def absorb_short_empty_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(events) < 3:
        return []
    removed: list[dict[str, Any]] = []
    index = 1
    while index < len(events) - 1:
        event = events[index]
        duration = event_duration(event)
        if duration > EMPTY_EVENT_ABSORB_THRESHOLD_SEC or has_blocking_overlay(event):
            index += 1
            continue
        previous = events[index - 1]
        old_previous_end = event_end(previous)
        new_previous_end = event_end(event)
        previous["timeline_end"] = round_sec(new_previous_end)
        for key in ("source", "reference_source"):
            prev_source = previous.get(key)
            event_source = event.get(key)
            if (
                isinstance(prev_source, dict)
                and isinstance(event_source, dict)
                and prev_source.get("media_id") == event_source.get("media_id")
                and event_source.get("out") is not None
            ):
                prev_source["out"] = round_sec(float(event_source["out"]))
        prev_audio = previous.get("audio")
        event_audio = event.get("audio")
        if isinstance(prev_audio, dict) and isinstance(event_audio, dict):
            if prev_audio.get("source_media_id") == event_audio.get("source_media_id") and event_audio.get("out") is not None:
                prev_audio["out"] = round_sec(float(event_audio["out"]))
            if event_audio.get("timing_reference_out") is not None:
                prev_audio["timing_reference_out"] = round_sec(float(event_audio["timing_reference_out"]))
        removed.append(
            {
                "event_id": event.get("event_id"),
                "duration_sec": round_sec(duration),
                "absorbed_into_event_id": previous.get("event_id"),
                "previous_old_end_sec": round_sec(old_previous_end),
                "previous_new_end_sec": round_sec(new_previous_end),
            }
        )
        del events[index]
    return removed


def place_caption_in_event(caption: dict[str, Any], events: list[dict[str, Any]]) -> tuple[int | None, float, float]:
    abs_start = float(caption["abs_start"])
    abs_end = float(caption["abs_end"])
    best_index: int | None = None
    best_overlap = 0.0
    for index, event in enumerate(events):
        overlap = max(0.0, min(abs_end, event_end(event)) - max(abs_start, event_start(event)))
        if overlap > best_overlap:
            best_overlap = overlap
            best_index = index
        if event_start(event) - EPS <= abs_start and abs_end <= event_end(event) + EPS:
            return index, abs_start - event_start(event), abs_end - event_start(event)
    if best_index is None:
        return None, 0.0, 0.0
    event = events[best_index]
    return best_index, max(0.0, abs_start - event_start(event)), min(event_duration(event), abs_end - event_start(event))


def reassign_captions(events: list[dict[str, Any]], captions: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    for event in events:
        overlays = event.get("overlays")
        if isinstance(overlays, list):
            event["overlays"] = [overlay for overlay in overlays if not is_caption(overlay)]
        else:
            event["overlays"] = []

    reassigned: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for caption in captions:
        event_index, local_start, local_end = place_caption_in_event(caption, events)
        if event_index is None or local_end - local_start < 0.05:
            unresolved.append(
                {
                    "key": caption["key"],
                    "text": caption["text"],
                    "abs_start": round_sec(caption["abs_start"]),
                    "abs_end": round_sec(caption["abs_end"]),
                    "reason": "no_event_contains_caption_after_boundary_shift",
                }
            )
            continue
        event = events[event_index]
        if not (event_start(event) - EPS <= float(caption["abs_start"]) and float(caption["abs_end"]) <= event_end(event) + EPS):
            unresolved.append(
                {
                    "key": caption["key"],
                    "text": caption["text"],
                    "abs_start": round_sec(caption["abs_start"]),
                    "abs_end": round_sec(caption["abs_end"]),
                    "target_event_id": event.get("event_id"),
                    "event_start": round_sec(event_start(event)),
                    "event_end": round_sec(event_end(event)),
                    "reason": "caption_still_crosses_event_boundary",
                }
            )
        overlay = copy.deepcopy(caption["overlay"])
        clean_caption_continuation_metadata(overlay)
        update_caption_source_end(overlay, caption)
        overlay["start"] = round_sec(local_start)
        overlay["end"] = round_sec(local_end)
        event.setdefault("overlays", []).append(overlay)
        reassigned.append(
            {
                "key": caption["key"],
                "text": caption["text"],
                "from_event_id": caption["event_id"],
                "to_event_id": event.get("event_id"),
                "abs_start": round_sec(caption["abs_start"]),
                "abs_end": round_sec(caption["abs_end"]),
                "local_start": round_sec(local_start),
                "local_end": round_sec(local_end),
            }
        )
    return reassigned, unresolved


def sort_overlays(events: list[dict[str, Any]]) -> None:
    priority = {
        "topic_title": 0,
        "caption": 1,
        "nameplate": 2,
        "split_person_labels": 3,
        "profile_card": 4,
    }
    for event in events:
        overlays = event.get("overlays")
        if isinstance(overlays, list):
            overlays.sort(
                key=lambda overlay: (
                    priority.get(str(overlay.get("type") or ""), 50) if isinstance(overlay, dict) else 99,
                    float(overlay.get("start") or 0.0) if isinstance(overlay, dict) else 0.0,
                    str(overlay.get("caption_id") or overlay.get("text") or "") if isinstance(overlay, dict) else "",
                )
            )


def audit_remaining_caption_cut_violations(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for index in range(len(events) - 1):
        event = events[index]
        boundary = event_end(event)
        active: list[dict[str, Any]] = []
        for overlay_index, overlay in enumerate(event.get("overlays", []) or []):
            if not is_caption(overlay):
                continue
            abs_start, abs_end = local_to_absolute(event, float(overlay.get("start") or 0.0), float(overlay.get("end") or 0.0))
            if abs_start + START_GRACE_SEC < boundary < visible_end(abs_end) - EPS:
                active.append(
                    {
                        "overlay_index": overlay_index,
                        "text": overlay.get("text"),
                        "abs_start": round_sec(abs_start),
                        "abs_end": round_sec(abs_end),
                        "visible_end": round_sec(visible_end(abs_end)),
                    }
                )
        if active:
            violations.append(
                {
                    "boundary_index": index + 1,
                    "boundary_sec": round_sec(boundary),
                    "prev_event_id": event.get("event_id"),
                    "next_event_id": events[index + 1].get("event_id"),
                    "active_captions": active,
                }
            )
    return violations


def main() -> None:
    plan = read_json(EDIT_PLAN)
    events = [event for event in plan.get("timeline", []) if isinstance(event, dict)]
    if not events:
        raise SystemExit("No timeline events found in edit_plan.json")

    original_windows = [
        {
            "event_id": event.get("event_id"),
            "timeline_start": event_start(event),
            "timeline_end": event_end(event),
            "source": copy.deepcopy(event.get("source")),
            "reference_source": copy.deepcopy(event.get("reference_source")),
            "audio": copy.deepcopy(event.get("audio")),
        }
        for event in events
    ]

    captions, removed_continuations = collect_base_captions(events)
    expanded_captions = [
        {
            "key": caption["key"],
            "event_id": caption["event_id"],
            "text": caption["text"],
            "source_window": [round_sec(caption["source_window"][0]), round_sec(caption["source_window"][1])] if isinstance(caption.get("source_window"), tuple) else None,
            "expanded_source_end": round_sec(caption["expanded_source_end"]),
            "added_sec": round_sec(float(caption["expanded_source_end"]) - float(caption["expanded_from_source_end"])),
        }
        for caption in captions
        if caption.get("expanded_source_end") is not None and caption.get("expanded_from_source_end") is not None
    ]
    new_boundaries, moved_boundaries, boundary_unresolved = compute_new_boundaries(events, captions)

    for index, event in enumerate(events):
        old_start = float(original_windows[index]["timeline_start"])
        new_start = new_boundaries[index]
        new_end = new_boundaries[index + 1]
        copy_timing_fields_for_new_window(event, old_start, new_start, new_end)
        event["timeline_start"] = round_sec(new_start)
        event["timeline_end"] = round_sec(new_end)

    reassigned, caption_unresolved = reassign_captions(events, captions)
    sort_overlays(events)
    absorbed_short_events = absorb_short_empty_events(events)

    remaining_violations = audit_remaining_caption_cut_violations(events)

    metadata = plan.setdefault("metadata", {})
    metadata["caption_cut_continuation"] = {
        "enabled": False,
        "superseded_by": "caption_cut_boundary_avoidance",
        "reason": "User requested no camera/layout cuts while a caption is visible.",
    }
    metadata["caption_cut_boundary_avoidance"] = {
        "enabled": True,
        "method": "move adjacent event boundaries after the caption fade window and reassign captions to the containing event",
        "caption_fade_sec": CAPTION_FADE_SEC,
        "cut_after_caption_gap_sec": CUT_AFTER_CAPTION_GAP_SEC,
        "moved_boundary_count": len(moved_boundaries),
        "removed_continuation_caption_count": removed_continuations,
        "expanded_caption_count": len(expanded_captions),
        "absorbed_short_empty_event_count": len(absorbed_short_events),
        "remaining_violation_count": len(remaining_violations),
    }
    notes = plan.setdefault("revision_notes", [])
    if isinstance(notes, list):
        notes.append(
            {
                "source": Path(__file__).name,
                "summary": "Moved camera/layout cut boundaries outside visible caption windows and removed caption continuation overlays.",
            }
        )

    write_json(EDIT_PLAN, plan)

    report = {
        "schema_version": "caption_cut_boundary_avoidance_report.v1",
        "edit_plan": str(EDIT_PLAN),
        "caption_count": len(captions),
        "removed_continuation_caption_count": removed_continuations,
        "expanded_caption_count": len(expanded_captions),
        "expanded_captions": expanded_captions,
        "moved_boundary_count": len(moved_boundaries),
        "moved_boundaries": moved_boundaries,
        "absorbed_short_empty_event_count": len(absorbed_short_events),
        "absorbed_short_empty_events": absorbed_short_events,
        "reassigned_caption_count": len(reassigned),
        "reassigned_captions": reassigned,
        "unresolved": boundary_unresolved + caption_unresolved,
        "remaining_violation_count": len(remaining_violations),
        "remaining_violations": remaining_violations,
    }
    write_json(REPORT, report)
    print(
        json.dumps(
            {
                "caption_count": len(captions),
                "removed_continuation_caption_count": removed_continuations,
                "moved_boundary_count": len(moved_boundaries),
                "expanded_caption_count": len(expanded_captions),
                "absorbed_short_empty_event_count": len(absorbed_short_events),
                "reassigned_caption_count": len(reassigned),
                "unresolved_count": len(report["unresolved"]),
                "remaining_violation_count": len(remaining_violations),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
