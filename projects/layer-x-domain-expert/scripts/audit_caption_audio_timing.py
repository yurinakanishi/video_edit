from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[1]
REPORTS_DIR = PROJECT_DIR / "output" / "reports"
EDIT_PLAN_PATH = REPORTS_DIR / "edit_plan.json"
REPORT_PATH = REPORTS_DIR / "caption_audio_timing_audit.json"

JST = timezone(timedelta(hours=9))
MAX_DELTA_SEC = 0.04
MAX_SOURCE_END_EARLY_SEC = 0.08


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ref_in(event: dict[str, Any]) -> float:
    source = event.get("reference_source") if isinstance(event.get("reference_source"), dict) else event.get("source")
    if not isinstance(source, dict):
        return 0.0
    return float(source.get("in") or 0.0)


def event_duration(event: dict[str, Any]) -> float:
    return max(0.01, float(event.get("timeline_end") or 0.0) - float(event.get("timeline_start") or 0.0))


def srt_time_to_seconds(value: str) -> float:
    hours, minutes, rest = value.strip().split(":")
    seconds, millis = rest.split(",")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000.0


def source_window(event: dict[str, Any], overlay: dict[str, Any], alignment: dict[str, Any], metadata: dict[str, Any]) -> list[float] | None:
    aligned_source = alignment.get("source_window_sec")
    if isinstance(aligned_source, list) and len(aligned_source) == 2:
        return [float(aligned_source[0]), float(aligned_source[1])]
    source_timecode = overlay.get("source_timecode")
    if isinstance(source_timecode, str) and "-->" in source_timecode:
        left, right = [part.strip() for part in source_timecode.split("-->", 1)]
        try:
            return [srt_time_to_seconds(left), srt_time_to_seconds(right)]
        except (ValueError, IndexError):
            return None
    if metadata.get("source_start_sec") is not None and metadata.get("source_end_sec") is not None:
        try:
            return [float(metadata["source_start_sec"]), float(metadata["source_end_sec"])]
        except (TypeError, ValueError):
            return None
    return None


def main() -> None:
    plan = read_json(EDIT_PLAN_PATH)
    issues: list[dict[str, Any]] = []
    coverage: dict[str, dict[str, Any]] = {}
    checked = 0
    strict_count = 0

    for event_index, event in enumerate(plan.get("timeline", [])):
        if not isinstance(event, dict):
            continue
        base = ref_in(event)
        duration = event_duration(event)
        for overlay_index, overlay in enumerate(event.get("overlays", [])):
            if not (isinstance(overlay, dict) and overlay.get("type") == "caption"):
                continue
            checked += 1
            alignment = overlay.get("audio_alignment") if isinstance(overlay.get("audio_alignment"), dict) else {}
            speech = alignment.get("speech_window_sec")
            metadata = overlay.get("metadata") if isinstance(overlay.get("metadata"), dict) else {}
            src_window = source_window(event, overlay, alignment, metadata)
            if metadata.get("audio_strict_timing"):
                strict_count += 1
            if not isinstance(speech, list) or len(speech) != 2:
                issues.append(
                    {
                        "event_id": event.get("event_id"),
                        "text": overlay.get("text"),
                        "reason": "missing_audio_alignment_speech_window",
                    }
                )
                continue
            expected_start = max(0.0, min(duration, float(speech[0]) - base))
            expected_end = max(expected_start, min(duration, float(speech[1]) - base))
            actual_start = float(overlay.get("start") or 0.0)
            actual_end = float(overlay.get("end") or 0.0)
            actual_abs_start = base + actual_start
            actual_abs_end = base + actual_end
            start_delta = round(actual_start - expected_start, 3)
            end_delta = round(actual_end - expected_end, 3)
            if abs(start_delta) > MAX_DELTA_SEC or abs(end_delta) > MAX_DELTA_SEC:
                issues.append(
                    {
                        "event_id": event.get("event_id"),
                        "section": event.get("section"),
                        "caption_id": overlay.get("caption_id"),
                        "text": overlay.get("text"),
                        "reason": "display_window_does_not_match_audio_speech_window",
                        "expected_local": [round(expected_start, 3), round(expected_end, 3)],
                        "actual_local": [round(actual_start, 3), round(actual_end, 3)],
                        "delta_sec": [start_delta, end_delta],
                        "speech_window_sec": [round(float(speech[0]), 3), round(float(speech[1]), 3)],
                    }
                )
            if src_window:
                root_id = str(
                    metadata.get("caption_cut_continuation_root_id")
                    or overlay.get("caption_id")
                    or f"{event.get('event_id')}_caption_{overlay_index}"
                )
                expected_visibility_end = float(metadata.get("caption_handoff_end_sec") or src_window[1])
                item = coverage.setdefault(
                    root_id,
                    {
                        "section": event.get("section"),
                        "caption_id": overlay.get("caption_id"),
                        "text": overlay.get("text"),
                        "source_window_sec": [float(src_window[0]), float(src_window[1])],
                        "expected_visibility_end_sec": expected_visibility_end,
                        "intervals": [],
                    },
                )
                item["expected_visibility_end_sec"] = max(float(item["expected_visibility_end_sec"]), expected_visibility_end)
                item["source_window_sec"][0] = min(float(item["source_window_sec"][0]), float(src_window[0]))
                item["source_window_sec"][1] = max(float(item["source_window_sec"][1]), float(src_window[1]))
                item["intervals"].append(
                    {
                        "event_id": event.get("event_id"),
                        "event_index": event_index,
                        "start": round(actual_abs_start, 3),
                        "end": round(actual_abs_end, 3),
                        "timeline_start": round(float(event.get("timeline_start") or 0.0) + actual_start, 3),
                        "timeline_end": round(float(event.get("timeline_start") or 0.0) + actual_end, 3),
                    }
                )

    for root_id, item in coverage.items():
        intervals = sorted(item["intervals"], key=lambda interval: (float(interval["start"]), float(interval["end"])))
        if not intervals:
            continue
        merged: list[list[float]] = []
        for interval in intervals:
            start = float(interval["start"])
            end = float(interval["end"])
            if not merged or start > merged[-1][1] + MAX_SOURCE_END_EARLY_SEC:
                merged.append([start, end])
            else:
                merged[-1][1] = max(merged[-1][1], end)
        expected_end = float(item["expected_visibility_end_sec"])
        final_end = merged[-1][1]
        if final_end + MAX_SOURCE_END_EARLY_SEC < expected_end:
            issues.append(
                {
                    "caption_root_id": root_id,
                    "section": item.get("section"),
                    "caption_id": item.get("caption_id"),
                    "text": item.get("text"),
                    "reason": "caption_visibility_does_not_reach_source_phrase_or_handoff_end",
                    "coverage_end_sec": round(final_end, 3),
                    "expected_visibility_end_sec": round(expected_end, 3),
                    "early_by_sec": round(expected_end - final_end, 3),
                    "source_window_sec": [round(float(item["source_window_sec"][0]), 3), round(float(item["source_window_sec"][1]), 3)],
                    "intervals": intervals,
                }
            )
        timeline_intervals = sorted(
            [[float(interval["timeline_start"]), float(interval["timeline_end"])] for interval in intervals],
            key=lambda interval: (interval[0], interval[1]),
        )
        timeline_merged: list[list[float]] = []
        for start, end in timeline_intervals:
            if not timeline_merged or start > timeline_merged[-1][1] + MAX_SOURCE_END_EARLY_SEC:
                timeline_merged.append([start, end])
            else:
                timeline_merged[-1][1] = max(timeline_merged[-1][1], end)
        for left, right in zip(timeline_merged, timeline_merged[1:]):
            gap = right[0] - left[1]
            if gap > MAX_SOURCE_END_EARLY_SEC:
                issues.append(
                    {
                        "caption_root_id": root_id,
                        "section": item.get("section"),
                        "caption_id": item.get("caption_id"),
                        "text": item.get("text"),
                        "reason": "caption_visibility_gap_across_cut",
                        "gap_sec": round(gap, 3),
                        "left_timeline_end_sec": round(left[1], 3),
                        "right_timeline_start_sec": round(right[0], 3),
                    }
                )

    report = {
        "schema_version": "caption_audio_timing_audit.v1",
        "project_id": "layer-x-domain-expert",
        "generated_at": datetime.now(JST).isoformat(timespec="seconds"),
        "policy": "Every rendered caption start/end must match audio_alignment.speech_window_sec. No fixed text-length display durations are allowed.",
        "max_delta_sec": MAX_DELTA_SEC,
        "max_source_end_early_sec": MAX_SOURCE_END_EARLY_SEC,
        "checked_caption_count": checked,
        "strict_audio_timing_count": strict_count,
        "issue_count": len(issues),
        "ready": len(issues) == 0 and strict_count == checked,
        "issues": issues,
    }
    write_json(REPORT_PATH, report)
    print(json.dumps({k: report[k] for k in ("checked_caption_count", "strict_audio_timing_count", "issue_count", "ready")}, ensure_ascii=False, indent=2))
    if issues or strict_count != checked:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
