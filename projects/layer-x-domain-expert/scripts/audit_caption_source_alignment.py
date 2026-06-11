from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT_ROOT / "output" / "reports"
EDIT_PLAN_PATH = REPORTS / "edit_plan.json"
REPORT_PATH = REPORTS / "caption_source_alignment_audit.json"

SOURCE_TOLERANCE_SEC = 0.12
MIN_OVERLAP_SEC = 0.25
MAX_TIMING_DELTA_SEC = 0.45


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def event_ref_window(event: dict[str, Any]) -> tuple[float, float] | None:
    source = event.get("reference_source") if isinstance(event.get("reference_source"), dict) else event.get("source")
    if not isinstance(source, dict) or source.get("in") is None or source.get("out") is None:
        return None
    return float(source["in"]), float(source["out"])


def caption_source_window(overlay: dict[str, Any]) -> tuple[float, float] | None:
    alignment = overlay.get("audio_alignment") if isinstance(overlay.get("audio_alignment"), dict) else {}
    speech_window = alignment.get("speech_window_sec")
    if isinstance(speech_window, list) and len(speech_window) == 2:
        try:
            return float(speech_window[0]), float(speech_window[1])
        except (TypeError, ValueError):
            pass
    metadata = overlay.get("metadata") if isinstance(overlay.get("metadata"), dict) else {}
    start = metadata.get("source_start_sec", metadata.get("caption_start_sec"))
    end = metadata.get("source_end_sec", metadata.get("caption_end_sec"))
    if start is None:
        return None
    try:
        start_f = float(start)
        end_f = float(end) if end is not None else start_f + max(0.8, float(overlay.get("end") or 0.0) - float(overlay.get("start") or 0.0))
        return start_f, max(start_f + 0.2, end_f)
    except (TypeError, ValueError):
        return None


def overlap(left: tuple[float, float], right: tuple[float, float]) -> float:
    return max(0.0, min(left[1], right[1]) - max(left[0], right[0]))


def main() -> None:
    plan = read_json(EDIT_PLAN_PATH)
    issues: list[dict[str, Any]] = []
    checked = 0
    for event in plan.get("timeline", []):
        if not isinstance(event, dict):
            continue
        ref = event_ref_window(event)
        if not ref:
            continue
        duration = max(0.01, float(event.get("timeline_end") or 0.0) - float(event.get("timeline_start") or 0.0))
        for overlay in event.get("overlays", []):
            if not (isinstance(overlay, dict) and overlay.get("type") == "caption"):
                continue
            source_window = caption_source_window(overlay)
            if not source_window:
                continue
            checked += 1
            current_overlap = overlap(source_window, ref)
            source_mid = (source_window[0] + source_window[1]) / 2.0
            source_present = current_overlap >= MIN_OVERLAP_SEC or (ref[0] - SOURCE_TOLERANCE_SEC <= source_mid <= ref[1] + SOURCE_TOLERANCE_SEC)
            expected_start = max(0.0, min(duration, source_window[0] - ref[0]))
            timing_delta = float(overlay.get("start") or 0.0) - expected_start
            if not source_present:
                issues.append(
                    {
                        "event_id": event.get("event_id"),
                        "caption_id": overlay.get("caption_id"),
                        "text": overlay.get("text"),
                        "reason": "caption_source_not_in_event_reference_window",
                        "event_reference_window_sec": [round(ref[0], 3), round(ref[1], 3)],
                        "caption_source_window_sec": [round(source_window[0], 3), round(source_window[1], 3)],
                    }
                )
            elif abs(timing_delta) > MAX_TIMING_DELTA_SEC:
                issues.append(
                    {
                        "event_id": event.get("event_id"),
                        "caption_id": overlay.get("caption_id"),
                        "text": overlay.get("text"),
                        "reason": "caption_local_timing_does_not_match_source_window",
                        "caption_start": overlay.get("start"),
                        "expected_start": round(expected_start, 3),
                        "delta_sec": round(timing_delta, 3),
                        "event_reference_window_sec": [round(ref[0], 3), round(ref[1], 3)],
                        "caption_source_window_sec": [round(source_window[0], 3), round(source_window[1], 3)],
                    }
                )
    report = {
        "schema_version": "caption_source_alignment_audit.v1",
        "project_id": "layer-x-domain-expert",
        "checked_captions_with_source_metadata": checked,
        "issue_count": len(issues),
        "ready": len(issues) == 0,
        "issues": issues,
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("checked_captions_with_source_metadata", "issue_count", "ready")}, ensure_ascii=False, indent=2))
    if issues:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
