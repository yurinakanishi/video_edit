from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


PROJECT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT / "output" / "reports"
EDIT_PLAN = REPORTS / "edit_plan.json"
VOICE_ATTRIBUTION = REPORTS / "voice_speaker_attribution.json"
REPORT = REPORTS / "caption_display_phrase_timing_repair_report.json"

JST = timezone(timedelta(hours=9))
SEARCH_PAD_BEFORE_SEC = 0.25
SEARCH_PAD_AFTER_SEC = 6.0
MIN_START_SHIFT_SEC = 0.28
MIN_BETTER_SCORE_DELTA = 0.12
GOOD_SEGMENT_SCORE = 0.22

PERSON_NAMES = {
    "person_01": "矢野",
    "person_02": "根本",
    "person_03": "村田",
}

# Captions that were explicitly reported by review. These are still resolved
# from speech segments below, but the override keeps future broad keyword
# matching from pulling the caption back to the preceding sentence.
SEARCH_KEY_OVERRIDES = {
    "main_caption_025": ["違和感", "言う", "いいもの"],
}


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize(text: Any) -> str:
    value = str(text or "")
    replacements = {
        "良い": "いい",
        "良く": "よく",
        "良くなる": "よくなる",
        "いく": "いく",
        "っていう": "",
        "という": "",
        "と思います": "",
        "思います": "",
        "と思って": "",
        "思って": "",
        "感じ": "",
        "ですね": "",
        "ますね": "",
        "ですよね": "",
        "です": "",
        "ます": "",
    }
    for src, dst in replacements.items():
        value = value.replace(src, dst)
    return re.sub(r"[\s、。，．「」『』（）()・!?！？…ー〜~,.]+", "", value)


def ngrams(text: str, n: int = 2) -> Counter[str]:
    if len(text) < n:
        return Counter([text]) if text else Counter()
    return Counter(text[index : index + n] for index in range(len(text) - n + 1))


def dice_score(a: str, b: str) -> float:
    left = ngrams(a)
    right = ngrams(b)
    if not left or not right:
        return 0.0
    common = sum((left & right).values())
    return (2.0 * common) / (sum(left.values()) + sum(right.values()))


def direct_substring_bonus(display: str, segment: str) -> float:
    if not display or not segment:
        return 0.0
    best = 0
    max_len = min(14, len(display))
    for size in range(max_len, 2, -1):
        for index in range(0, len(display) - size + 1):
            if display[index : index + size] in segment:
                best = max(best, size)
        if best:
            break
    return min(0.28, best / 50.0)


def text_score(display_text: str, segment_text: str) -> float:
    display = normalize(display_text)
    segment = normalize(segment_text)
    return dice_score(display, segment) + direct_substring_bonus(display, segment)


def overlap(left: tuple[float, float], right: tuple[float, float]) -> float:
    return max(0.0, min(left[1], right[1]) - max(left[0], right[0]))


def event_ref_window(event: dict[str, Any]) -> tuple[float, float] | None:
    source = event.get("reference_source") if isinstance(event.get("reference_source"), dict) else event.get("source")
    if not isinstance(source, dict) or source.get("in") is None or source.get("out") is None:
        return None
    return float(source["in"]), float(source["out"])


def event_duration(event: dict[str, Any]) -> float:
    return max(0.01, float(event.get("timeline_end") or 0.0) - float(event.get("timeline_start") or 0.0))


def root_id_for_overlay(event: dict[str, Any], overlay: dict[str, Any], index: int) -> str:
    metadata = overlay.get("metadata") if isinstance(overlay.get("metadata"), dict) else {}
    root = metadata.get("main_caption_id") or metadata.get("caption_cut_continuation_root_id")
    if root:
        return str(root)
    caption_id = str(overlay.get("caption_id") or "")
    if "__cont__" in caption_id:
        return caption_id.split("__cont__", 1)[0]
    if caption_id:
        return caption_id
    return f"{event.get('event_id')}_caption_{index}"


def source_window_from_caption(caption: dict[str, Any]) -> tuple[float, float] | None:
    if caption.get("source_start_sec") is not None and caption.get("source_end_sec") is not None:
        return float(caption["source_start_sec"]), float(caption["source_end_sec"])
    if caption.get("caption_start_sec") is not None and caption.get("caption_end_sec") is not None:
        return float(caption["caption_start_sec"]), float(caption["caption_end_sec"])
    return None


def source_window_from_overlay(overlay: dict[str, Any]) -> tuple[float, float] | None:
    metadata = overlay.get("metadata") if isinstance(overlay.get("metadata"), dict) else {}
    if metadata.get("source_start_sec") is not None and metadata.get("source_end_sec") is not None:
        return float(metadata["source_start_sec"]), float(metadata["source_end_sec"])
    alignment = overlay.get("audio_alignment") if isinstance(overlay.get("audio_alignment"), dict) else {}
    window = alignment.get("source_window_sec")
    if isinstance(window, list) and len(window) == 2:
        return float(window[0]), float(window[1])
    return None


def candidate_segments(
    segments: list[dict[str, Any]],
    source_start: float,
    source_end: float,
) -> list[dict[str, Any]]:
    search_start = max(0.0, source_start - SEARCH_PAD_BEFORE_SEC)
    search_end = source_end + SEARCH_PAD_AFTER_SEC
    return [
        segment
        for segment in segments
        if float(segment.get("end") or 0.0) >= search_start and float(segment.get("start") or 0.0) <= search_end
    ]


def find_display_phrase_window(
    display_text: str,
    source_window: tuple[float, float],
    segments: list[dict[str, Any]],
) -> dict[str, Any] | None:
    source_start, source_end = source_window
    candidates = candidate_segments(segments, source_start, source_end)
    if len(candidates) < 2:
        return None

    scored = []
    for segment in candidates:
        seg_start = float(segment.get("start") or 0.0)
        seg_end = float(segment.get("end") or 0.0)
        if seg_end < source_start - SEARCH_PAD_BEFORE_SEC:
            continue
        scored.append(
            {
                "segment": segment,
                "score": text_score(display_text, str(segment.get("text") or "")),
                "start": seg_start,
                "end": seg_end,
                "text": str(segment.get("text") or ""),
            }
        )
    if not scored:
        return None

    first_inside = next((item for item in scored if item["end"] >= source_start - 0.02), scored[0])
    best = max(scored, key=lambda item: (item["score"], -abs(item["start"] - source_start)))
    if best["start"] <= source_start + MIN_START_SHIFT_SEC:
        return None
    if best["score"] < GOOD_SEGMENT_SCORE:
        return None
    if best["score"] < first_inside["score"] + MIN_BETTER_SCORE_DELTA:
        return None

    new_start = round(best["start"], 3)
    new_end = round(max(source_end, best["end"]), 3)
    if new_end <= new_start + 0.2:
        return None
    return {
        "old_source_window_sec": [round(source_start, 3), round(source_end, 3)],
        "new_source_window_sec": [new_start, new_end],
        "first_segment": {
            "segment_id": first_inside["segment"].get("segment_id"),
            "start": round(first_inside["start"], 3),
            "end": round(first_inside["end"], 3),
            "score": round(first_inside["score"], 3),
            "text": first_inside["text"],
        },
        "matched_segment": {
            "segment_id": best["segment"].get("segment_id"),
            "start": round(best["start"], 3),
            "end": round(best["end"], 3),
            "score": round(best["score"], 3),
            "text": best["text"],
            "speaker_person_id": best["segment"].get("speaker_person_id"),
            "speaker_name": best["segment"].get("speaker_name"),
        },
    }


def set_item_window(item: dict[str, Any], repair: dict[str, Any]) -> None:
    start, end = repair["new_source_window_sec"]
    item["source_start_sec"] = start
    item["source_end_sec"] = end
    item["caption_start_sec"] = start
    item["caption_end_sec"] = end
    matched = repair["matched_segment"]
    if matched.get("segment_id"):
        item["source_segment_id"] = matched["segment_id"]
    if matched.get("speaker_person_id"):
        item["speaker_person_id"] = matched["speaker_person_id"]
        item["speaker_name"] = PERSON_NAMES.get(str(matched["speaker_person_id"]), matched.get("speaker_name") or item.get("speaker_name"))
    if item.get("caption_id") in SEARCH_KEY_OVERRIDES:
        item["search_keys"] = SEARCH_KEY_OVERRIDES[str(item["caption_id"])]
    item["display_phrase_timing_repaired"] = True
    item["display_phrase_timing_repair_reason"] = (
        "Trimmed source start to the speech segment that actually contains the displayed caption phrase."
    )


def set_overlay_window(event: dict[str, Any], overlay: dict[str, Any], repair: dict[str, Any]) -> None:
    start, end = repair["new_source_window_sec"]
    ref = event_ref_window(event)
    duration = event_duration(event)
    if ref:
        local_start = max(0.0, min(duration, start - ref[0]))
        local_end = min(duration, max(local_start + 0.2, end - ref[0]))
        overlay["start"] = round(local_start, 3)
        overlay["end"] = round(local_end, 3)
    metadata = dict(overlay.get("metadata") or {})
    metadata["source_start_sec"] = start
    metadata["source_end_sec"] = end
    metadata["caption_start_sec"] = start
    metadata["caption_end_sec"] = end
    metadata["caption_source_full_window_sec"] = [start, end]
    metadata["caption_handoff_end_sec"] = end
    metadata["display_phrase_timing_repaired"] = True
    metadata["display_phrase_timing_repair_reason"] = (
        "Trimmed source start to the speech segment that actually contains the displayed caption phrase."
    )
    matched = repair["matched_segment"]
    if matched.get("speaker_person_id"):
        person_id = str(matched["speaker_person_id"])
        metadata["speaker_person_id"] = person_id
        metadata["speaker_name"] = PERSON_NAMES.get(person_id, matched.get("speaker_name") or metadata.get("speaker_name"))
        overlay["speaker_person_id"] = person_id
    overlay["metadata"] = metadata
    overlay["audio_alignment"] = {
        "method": "display_phrase_segment_timing_repair",
        "source_audio_media_id": "group_wide",
        "source_window_sec": [start, end],
        "speech_window_sec": [start, end],
        "diagnostics": {
            "old_source_window_sec": repair["old_source_window_sec"],
            "first_segment": repair["first_segment"],
            "matched_segment": repair["matched_segment"],
        },
    }


def remove_continuations_for_roots(events: list[dict[str, Any]], repaired_roots: set[str]) -> int:
    removed = 0
    for event in events:
        overlays = event.get("overlays") if isinstance(event.get("overlays"), list) else []
        kept = []
        for index, overlay in enumerate(overlays):
            if not isinstance(overlay, dict) or overlay.get("type") != "caption":
                kept.append(overlay)
                continue
            metadata = overlay.get("metadata") if isinstance(overlay.get("metadata"), dict) else {}
            root = root_id_for_overlay(event, overlay, index)
            if metadata.get("caption_cut_continuation") and root in repaired_roots:
                removed += 1
                continue
            kept.append(overlay)
        event["overlays"] = kept
    return removed


def main() -> None:
    plan = load(EDIT_PLAN)
    segments = sorted(load(VOICE_ATTRIBUTION).get("segments", []), key=lambda segment: float(segment.get("start") or 0.0))
    events = [event for event in plan.get("timeline", []) if isinstance(event, dict)]

    item_by_root: dict[str, dict[str, Any]] = {}
    root_text: dict[str, str] = {}
    root_source: dict[str, tuple[float, float]] = {}
    for event in events:
        for item in event.get("main_caption_plan_items", []) or []:
            if not isinstance(item, dict) or not item.get("caption_id"):
                continue
            root = str(item["caption_id"])
            item_by_root[root] = item
            root_text[root] = str(item.get("display_text") or item.get("text") or "")
            if window := source_window_from_caption(item):
                root_source[root] = window

    overlay_refs: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for event in events:
        for index, overlay in enumerate(event.get("overlays", []) or []):
            if not isinstance(overlay, dict) or overlay.get("type") != "caption":
                continue
            metadata = overlay.get("metadata") if isinstance(overlay.get("metadata"), dict) else {}
            if metadata.get("caption_cut_continuation"):
                continue
            root = root_id_for_overlay(event, overlay, index)
            overlay_refs.setdefault(root, []).append((event, overlay))
            root_text.setdefault(root, str(overlay.get("text") or ""))
            if root not in root_source:
                if window := source_window_from_overlay(overlay):
                    root_source[root] = window

    repairs: list[dict[str, Any]] = []
    repaired_roots: set[str] = set()
    for root, display_text in sorted(root_text.items()):
        if not display_text or root not in root_source:
            continue
        repair = find_display_phrase_window(display_text, root_source[root], segments)
        if not repair:
            continue
        repaired_roots.add(root)
        repair_record = {
            "root_caption_id": root,
            "display_text": display_text,
            **repair,
        }
        if root in item_by_root:
            set_item_window(item_by_root[root], repair)
        for event, overlay in overlay_refs.get(root, []):
            set_overlay_window(event, overlay, repair)
        repairs.append(repair_record)

    removed_continuations = remove_continuations_for_roots(events, repaired_roots)
    updated_at = datetime.now(JST).isoformat(timespec="seconds")
    plan["updated_at"] = updated_at
    plan.setdefault("revision_notes", []).append(
        {
            "updated_at": updated_at,
            "script": Path(__file__).name,
            "summary": (
                f"Trimmed {len(repairs)} caption source windows to the speech segment that matches the displayed phrase; "
                f"removed {removed_continuations} stale continuation overlays for regeneration."
            ),
        }
    )
    save(EDIT_PLAN, plan)
    report = {
        "schema_version": "caption_display_phrase_timing_repair.v1",
        "project_id": "layer-x-domain-expert",
        "updated_at": updated_at,
        "root_cause": [
            "Some summarized captions kept the start time of their wider reference sentence.",
            "Audio RMS alignment then snapped to the preceding sentence audio because the source window already included it.",
            "The previous source-window audit only checked whether the caption window overlapped the rendered event, not whether the first spoken segment matched the displayed caption phrase.",
        ],
        "repair_policy": (
            "For each active digest/main caption, compare the displayed caption text against voice-attributed speech segments in and just after its source window. "
            "When a later segment has a clearly stronger text match than the first segment, move the caption source start to that later segment."
        ),
        "repair_count": len(repairs),
        "removed_stale_continuation_count": removed_continuations,
        "repairs": repairs,
    }
    save(REPORT, report)
    print(json.dumps({"repair_count": len(repairs), "removed_stale_continuations": removed_continuations, "report": str(REPORT)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
