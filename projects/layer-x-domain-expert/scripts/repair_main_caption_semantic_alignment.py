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
TRANSCRIPT = REPORTS / "transcript.json"
VOICE_ATTRIBUTION = REPORTS / "voice_speaker_attribution.json"
REPORT_PATH = REPORTS / "main_caption_semantic_alignment_repair_report.json"

JST = timezone(timedelta(hours=9))
SEARCH_SPAN_SEC = 140.0
MAX_WINDOW_SEC = 24.0
MIN_SCORE_IMPROVEMENT = 0.75

MANUAL_SPEAKER_OVERRIDES = {
    # These lines are from 根本's accounting-career introduction. Voice diarization has
    # short noisy flips, but the semantic block and camera context are the middle person.
    "main_caption_004": "person_02",
    "main_caption_005": "person_02",
    "main_caption_006": "person_02",
    "main_caption_007": "person_02",
    "main_caption_008": "person_02",
    "main_caption_009": "person_02",
    "main_caption_064": "person_02",
    "main_caption_065": "person_02",
}


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clean(text: Any) -> str:
    return re.sub(r"\s+", "", str(text or "").replace("、", "").replace("。", "").replace("「", "").replace("」", ""))


def score_text(keys: list[str], text: str) -> tuple[float, list[str], list[str]]:
    normalized = clean(text)
    normalized_keys = [clean(key) for key in keys if clean(key)]
    hits: list[str] = []
    partials: list[str] = []
    for key in normalized_keys:
        if key in normalized:
            hits.append(key)
            continue
        if len(key) >= 8:
            for n in range(min(len(key), 10), 4, -1):
                if key[:n] in normalized or key[-n:] in normalized:
                    partials.append(key)
                    break
    return len(hits) + 0.5 * len(partials), hits, partials


def segment_text(segments: list[dict[str, Any]]) -> str:
    return "".join(str(segment.get("text") or "") for segment in segments)


def overlapping_segments(segments: list[dict[str, Any]], start: float, end: float, pad: float = 0.1) -> list[dict[str, Any]]:
    return [
        segment
        for segment in segments
        if float(segment.get("end") or 0.0) >= start - pad and float(segment.get("start") or 0.0) <= end + pad
    ]


def best_transcript_window(caption: dict[str, Any], transcript_segments: list[dict[str, Any]]) -> dict[str, Any] | None:
    keys = caption.get("search_keys") or []
    if not keys or caption.get("source_start_sec") is None or caption.get("source_end_sec") is None:
        return None
    current_start = float(caption["source_start_sec"])
    current_end = float(caption["source_end_sec"])
    current_segments = overlapping_segments(transcript_segments, current_start, current_end)
    current_score, current_hits, current_partials = score_text(keys, segment_text(current_segments))

    low = max(0.0, current_start - SEARCH_SPAN_SEC)
    high = current_end + SEARCH_SPAN_SEC
    candidates = [segment for segment in transcript_segments if low <= float(segment.get("start") or 0.0) <= high]

    best: dict[str, Any] | None = None
    for i in range(len(candidates)):
        window: list[dict[str, Any]] = []
        start = float(candidates[i].get("start") or 0.0)
        for j in range(i, min(len(candidates), i + 8)):
            end = float(candidates[j].get("end") or 0.0)
            if end - start > MAX_WINDOW_SEC:
                break
            window.append(candidates[j])
            score, hits, partials = score_text(keys, segment_text(window))
            candidate = {
                "start": start,
                "end": end,
                "score": score,
                "hits": hits,
                "partials": partials,
                "text": segment_text(window),
            }
            if best is None or (candidate["score"], -(candidate["end"] - candidate["start"])) > (
                best["score"],
                -(best["end"] - best["start"]),
            ):
                best = candidate

    if not best or best["score"] <= current_score + MIN_SCORE_IMPROVEMENT:
        return None
    return {
        "current": {
            "start": current_start,
            "end": current_end,
            "score": current_score,
            "hits": current_hits,
            "partials": current_partials,
            "text": segment_text(current_segments),
        },
        "best": best,
    }


def event_ref_window(event: dict[str, Any]) -> tuple[float, float] | None:
    source = event.get("reference_source") if isinstance(event.get("reference_source"), dict) else event.get("source")
    if not isinstance(source, dict) or source.get("in") is None or source.get("out") is None:
        return None
    return float(source["in"]), float(source["out"])


def event_duration(event: dict[str, Any]) -> float:
    return max(0.01, float(event["timeline_end"]) - float(event["timeline_start"]))


def source_to_local(event: dict[str, Any], start: float, end: float) -> tuple[float, float]:
    ref = event_ref_window(event)
    if not ref:
        return 0.0, min(3.0, event_duration(event))
    duration = event_duration(event)
    local_start = max(0.0, min(duration, start - ref[0]))
    local_end = max(local_start + 0.8, min(duration, end - ref[0]))
    return round(local_start, 3), round(local_end, 3)


def overlap(a: tuple[float, float], b: tuple[float, float]) -> float:
    return max(0.0, min(a[1], b[1]) - max(a[0], b[0]))


def find_target_event(timeline: list[dict[str, Any]], start: float, end: float) -> dict[str, Any] | None:
    main_events = [event for event in timeline if event.get("section") == "main" and event_ref_window(event)]
    containing = [
        event
        for event in main_events
        if (ref := event_ref_window(event)) and ref[0] - 0.05 <= start <= ref[1] + 0.05
    ]
    if containing:
        return max(containing, key=lambda event: overlap(event_ref_window(event) or (0, 0), (start, end)))
    overlapping = [
        event
        for event in main_events
        if overlap(event_ref_window(event) or (0, 0), (start, end)) > 0.2
    ]
    if overlapping:
        return max(overlapping, key=lambda event: overlap(event_ref_window(event) or (0, 0), (start, end)))
    return None


def speaker_for_window(
    caption_id: str,
    start: float,
    end: float,
    current: str | None,
    voice_segments: list[dict[str, Any]],
) -> str | None:
    if caption_id in MANUAL_SPEAKER_OVERRIDES:
        return MANUAL_SPEAKER_OVERRIDES[caption_id]
    weights: Counter[str] = Counter()
    for segment in voice_segments:
        person = segment.get("speaker_person_id")
        if not person:
            continue
        seg_start = float(segment.get("start") or 0.0)
        seg_end = float(segment.get("end") or 0.0)
        amount = overlap((seg_start, seg_end), (start, end))
        if amount > 0:
            weights[str(person)] += amount
    if weights:
        return weights.most_common(1)[0][0]
    return current


def visible_people_for_event(event: dict[str, Any]) -> set[str]:
    layout = event.get("layout") if isinstance(event.get("layout"), dict) else {}
    people = set(layout.get("person_ids") or layout.get("panel_order") or [])
    for key in ("target_person_id", "active_person_id"):
        if layout.get(key):
            people.add(str(layout[key]))
    if layout.get("type") in {"wide_group", "split_grid"}:
        people.update({"person_01", "person_02", "person_03"})
    return people


def prefer_speaker_visible_event(
    timeline: list[dict[str, Any]],
    start: float,
    end: float,
    speaker: str | None,
    fallback: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not speaker or (fallback and speaker in visible_people_for_event(fallback)):
        return fallback
    candidates = []
    for event in timeline:
        if event.get("section") != "main" or not event_ref_window(event):
            continue
        ref = event_ref_window(event)
        ov = overlap(ref or (0, 0), (start, end))
        if ov > 0.2 and speaker in visible_people_for_event(event):
            candidates.append((ov, event))
    if candidates:
        return max(candidates, key=lambda item: item[0])[1]
    return fallback


def main() -> None:
    edit_plan = load(EDIT_PLAN)
    transcript_segments = load(TRANSCRIPT).get("segments", [])
    voice_segments = load(VOICE_ATTRIBUTION).get("segments", [])
    timeline = edit_plan.get("timeline", [])

    captions_by_id: dict[str, dict[str, Any]] = {}
    caption_item_event_by_id: dict[str, dict[str, Any]] = {}
    for event in timeline:
        for item in event.get("main_caption_plan_items", []) or []:
            if isinstance(item, dict) and item.get("caption_id"):
                captions_by_id[str(item["caption_id"])] = item
                caption_item_event_by_id[str(item["caption_id"])] = event
    displayed_ids: set[str] = set()
    overlay_by_id: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for event in timeline:
        for overlay in event.get("overlays", []):
            if isinstance(overlay, dict) and overlay.get("type") == "caption" and overlay.get("caption_id"):
                caption_id = str(overlay["caption_id"])
                displayed_ids.add(caption_id)
                overlay_by_id[caption_id] = (event, overlay)

    repairs: list[dict[str, Any]] = []
    for caption_id in sorted(displayed_ids):
        caption = captions_by_id.get(caption_id)
        if not caption:
            continue
        candidate = best_transcript_window(caption, transcript_segments)
        if not candidate:
            continue
        best = candidate["best"]
        start = round(float(best["start"]), 3)
        end = round(float(best["end"]), 3)
        if end <= start:
            continue
        old_event, old_overlay = overlay_by_id[caption_id]
        old_item_event = caption_item_event_by_id.get(caption_id)
        speaker = speaker_for_window(caption_id, start, end, caption.get("speaker_person_id"), voice_segments)
        target_event = prefer_speaker_visible_event(timeline, start, end, speaker, find_target_event(timeline, start, end))
        if not target_event:
            continue

        new_start, new_end = source_to_local(target_event, start, end)
        if new_end <= new_start:
            continue

        old_event["overlays"] = [overlay for overlay in old_event.get("overlays", []) if overlay is not old_overlay]
        new_overlay = dict(old_overlay)
        new_overlay["start"] = new_start
        new_overlay["end"] = new_end
        if speaker:
            new_overlay["speaker_person_id"] = speaker
        metadata = dict(new_overlay.get("metadata") or {})
        metadata["source_start_sec"] = start
        metadata["source_end_sec"] = end
        metadata["caption_start_sec"] = start
        metadata["caption_end_sec"] = end
        if speaker:
            metadata["speaker_person_id"] = speaker
            name = {"person_01": "矢野", "person_02": "根本", "person_03": "村田"}.get(speaker)
            if name:
                metadata["speaker_name"] = name
        metadata["semantic_alignment_repaired"] = True
        metadata["semantic_alignment_repair_reason"] = "search_keys matched a better transcript window than the previous source window"
        new_overlay["metadata"] = metadata
        new_overlay["audio_alignment"] = {
            "method": "semantic_transcript_window_repair",
            "source_audio_media_id": "group_wide",
            "source_window_sec": [start, end],
            "speech_window_sec": [start, end],
            "diagnostics": {
                "previous_source_window_sec": [
                    round(float(candidate["current"]["start"]), 3),
                    round(float(candidate["current"]["end"]), 3),
                ],
                "previous_score": candidate["current"]["score"],
                "new_score": best["score"],
                "hits": best["hits"],
                "partials": best["partials"],
            },
        }
        target_event.setdefault("overlays", []).append(new_overlay)
        target_event["overlays"].sort(key=lambda overlay: (0 if overlay.get("type") == "topic_title" else 1, float(overlay.get("start") or 0.0)))

        caption["source_start_sec"] = start
        caption["source_end_sec"] = end
        caption["caption_start_sec"] = start
        caption["caption_end_sec"] = end
        caption["source"] = "edit_plan_embedded_caption_context"
        if speaker:
            caption["speaker_person_id"] = speaker
            caption["speaker_name"] = {"person_01": "矢野", "person_02": "根本", "person_03": "村田"}.get(speaker, caption.get("speaker_name"))
        caption["semantic_alignment_repaired"] = True
        if old_item_event is not None and old_item_event is not target_event:
            old_item_event["main_caption_plan_items"] = [
                item
                for item in (old_item_event.get("main_caption_plan_items", []) or [])
                if not (isinstance(item, dict) and item.get("caption_id") == caption_id)
            ]
            target_event.setdefault("main_caption_plan_items", []).append(caption)
        elif old_item_event is None:
            target_event.setdefault("main_caption_plan_items", []).append(caption)

        repairs.append(
            {
                "caption_id": caption_id,
                "text": new_overlay.get("text"),
                "old_event_id": old_event.get("event_id"),
                "new_event_id": target_event.get("event_id"),
                "old_source_window_sec": [
                    round(float(candidate["current"]["start"]), 3),
                    round(float(candidate["current"]["end"]), 3),
                ],
                "new_source_window_sec": [start, end],
                "old_score": candidate["current"]["score"],
                "new_score": best["score"],
                "speaker_person_id": speaker,
                "local_timing": [new_start, new_end],
                "matched_text": clean(best["text"])[:180],
            }
        )

    updated_at = datetime.now(JST).isoformat(timespec="seconds")
    edit_plan["updated_at"] = updated_at
    edit_plan["caption_source_of_truth"] = {
        "artifact": "edit_plan.json",
        "path": "timeline[].overlays[type=caption]",
        "policy": "Rendered captions are authoritative only in edit_plan.json; caption_review.md is generated from edit_plan and no markdown caption source is used for repairs.",
    }
    edit_plan.setdefault("revision_notes", []).append(
        {
            "updated_at": updated_at,
            "change": "Repaired main caption source windows and event attachment using transcript semantic-key matching.",
            "repair_count": len(repairs),
        }
    )
    save(EDIT_PLAN, edit_plan)
    report = {
        "schema_version": "main_caption_semantic_alignment_repair.v1",
        "project_id": "layer-x-domain-expert",
        "updated_at": updated_at,
        "root_cause": [
            "Some captions inherited source windows from weak keyword/time-hint matching that landed on adjacent transcript text.",
            "The previous source-alignment audit only checked partial overlap, so it missed captions whose true phrase was outside or across the event boundary.",
        ],
        "single_source_of_truth": "edit_plan.json timeline[].overlays[type=caption]",
        "repair_policy": "Only displayed captions embedded in edit_plan.json with search_keys were moved, and only when a nearby transcript window had a clearly better key match.",
        "repair_count": len(repairs),
        "repairs": repairs,
    }
    save(REPORT_PATH, report)
    print(json.dumps({"repair_count": len(repairs), "report": str(REPORT_PATH)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
