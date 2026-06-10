from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT_ROOT / "output" / "reports"
EDIT_PLAN = REPORTS / "edit_plan.json"
REPORT = REPORTS / "digest_caption_tightening_report.json"

GAP_CUT_THRESHOLD_SEC = 0.35
EDGE_PAD_SEC = 0.03


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def event_duration(event: dict[str, Any]) -> float:
    return max(0.01, float(event.get("timeline_end") or 0.0) - float(event.get("timeline_start") or 0.0))


def source_out(source: dict[str, Any], start: float, duration: float) -> float:
    original_out = source.get("out")
    try:
        max_out = float(original_out)
    except (TypeError, ValueError):
        max_out = start + duration
    return round(min(max_out, start + duration), 3)


def caption_clusters(event: dict[str, Any]) -> list[dict[str, Any]]:
    duration = event_duration(event)
    captions = []
    for overlay in event.get("overlays", []):
        if not isinstance(overlay, dict) or overlay.get("type") != "caption":
            continue
        try:
            start = max(0.0, min(duration, float(overlay.get("start") or 0.0)))
            end = max(start + 0.01, min(duration, float(overlay.get("end") or start + 0.01)))
        except (TypeError, ValueError):
            continue
        captions.append((start, end, overlay))
    captions.sort(key=lambda item: (item[0], item[1]))

    clusters: list[dict[str, Any]] = []
    for start, end, overlay in captions:
        if not clusters or start - float(clusters[-1]["end"]) > GAP_CUT_THRESHOLD_SEC:
            clusters.append({"start": start, "end": end, "captions": [overlay]})
        else:
            clusters[-1]["end"] = max(float(clusters[-1]["end"]), end)
            clusters[-1]["captions"].append(overlay)
    return clusters


def shifted_overlay(overlay: dict[str, Any], cluster_start: float, duration: float) -> dict[str, Any]:
    result = deepcopy(overlay)
    if result.get("type") == "caption":
        start = max(0.0, float(result.get("start") or 0.0) - cluster_start)
        end = min(duration, max(start + 0.01, float(result.get("end") or 0.0) - cluster_start))
        result["start"] = round(start, 3)
        result["end"] = round(end, 3)
    elif "start" in result or "end" in result:
        try:
            start = max(0.0, float(result.get("start") or 0.0) - cluster_start)
            end = min(duration, max(start + 0.01, float(result.get("end") or 0.0) - cluster_start))
            result["start"] = round(start, 3)
            result["end"] = round(end, 3)
        except (TypeError, ValueError):
            pass
    return result


def tighten_digest_event(event: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    duration = event_duration(event)
    clusters = caption_clusters(event)
    if not clusters:
        return [event], {
            "event_id": event.get("event_id"),
            "status": "unchanged_no_captions",
            "original_duration_sec": round(duration, 3),
            "kept_duration_sec": round(duration, 3),
        }

    non_caption_overlays = [
        overlay
        for overlay in event.get("overlays", [])
        if isinstance(overlay, dict) and overlay.get("type") != "caption"
    ]
    source = event.get("source") if isinstance(event.get("source"), dict) else {}
    reference = event.get("reference_source") if isinstance(event.get("reference_source"), dict) else {}
    source_in = float(source.get("in") or 0.0)
    reference_in = float(reference.get("in") or source_in)

    tightened: list[dict[str, Any]] = []
    kept_duration = 0.0
    for index, cluster in enumerate(clusters, start=1):
        cluster_start = max(0.0, float(cluster["start"]) - EDGE_PAD_SEC)
        cluster_end = min(duration, float(cluster["end"]) + EDGE_PAD_SEC)
        cluster_duration = max(0.01, cluster_end - cluster_start)
        kept_duration += cluster_duration

        next_event = deepcopy(event)
        next_event["event_id"] = str(event.get("event_id")) if len(clusters) == 1 else f"{event.get('event_id')}_tight{index:02d}"
        next_source = deepcopy(source)
        next_reference = deepcopy(reference)
        next_source["in"] = round(source_in + cluster_start, 3)
        next_source["out"] = source_out(source, float(next_source["in"]), cluster_duration)
        next_reference["in"] = round(reference_in + cluster_start, 3)
        next_reference["out"] = source_out(reference, float(next_reference["in"]), cluster_duration)
        next_event["source"] = next_source
        next_event["reference_source"] = next_reference
        next_event["timeline_end"] = round(float(next_event.get("timeline_start") or 0.0) + cluster_duration, 3)
        next_event["overlays"] = [
            deepcopy(overlay)
            for overlay in non_caption_overlays
            if not ("start" in overlay or "end" in overlay)
        ]
        next_event["overlays"].extend(
            shifted_overlay(overlay, cluster_start, cluster_duration)
            for overlay in non_caption_overlays
            if "start" in overlay or "end" in overlay
        )
        next_event["overlays"].extend(
            shifted_overlay(overlay, cluster_start, cluster_duration)
            for overlay in cluster["captions"]
        )
        digest_source = next_event.get("digest_qa_source") if isinstance(next_event.get("digest_qa_source"), dict) else {}
        digest_source["caption_only_cut"] = True
        digest_source["post_audio_tightened"] = True
        digest_source["cluster_index"] = index
        digest_source["cluster_count"] = len(clusters)
        next_event["digest_qa_source"] = digest_source
        next_event["reason"] = str(next_event.get("reason") or "") + " Opening digest is tightened to captioned speech only."
        tightened.append(next_event)

    return tightened, {
        "event_id": event.get("event_id"),
        "status": "tightened",
        "original_duration_sec": round(duration, 3),
        "kept_duration_sec": round(kept_duration, 3),
        "removed_duration_sec": round(max(0.0, duration - kept_duration), 3),
        "cluster_count": len(clusters),
    }


def recompute_timeline(events: list[dict[str, Any]]) -> None:
    cursor = 0.0
    for event in events:
        duration = event_duration(event)
        event["timeline_start"] = round(cursor, 3)
        event["timeline_end"] = round(cursor + duration, 3)
        cursor += duration


def main() -> None:
    plan = read_json(EDIT_PLAN)
    events = plan["timeline"]["events"] if isinstance(plan.get("timeline"), dict) else plan.get("timeline", [])
    tightened_events: list[dict[str, Any]] = []
    report_items = []
    for event in events:
        if isinstance(event, dict) and event.get("section") == "digest":
            next_events, report = tighten_digest_event(event)
            tightened_events.extend(next_events)
            report_items.append(report)
        else:
            tightened_events.append(event)
    recompute_timeline(tightened_events)
    if isinstance(plan.get("timeline"), dict):
        plan["timeline"]["events"] = tightened_events
    else:
        plan["timeline"] = tightened_events
    summary = {
        "schema_version": "digest_caption_tightening.v1",
        "gap_cut_threshold_sec": GAP_CUT_THRESHOLD_SEC,
        "edge_pad_sec": EDGE_PAD_SEC,
        "original_digest_duration_sec": round(sum(item["original_duration_sec"] for item in report_items), 3),
        "kept_digest_duration_sec": round(sum(item["kept_duration_sec"] for item in report_items), 3),
        "removed_digest_duration_sec": round(sum(item.get("removed_duration_sec", 0.0) for item in report_items), 3),
        "input_digest_event_count": len(report_items),
        "output_digest_event_count": sum(1 for event in tightened_events if isinstance(event, dict) and event.get("section") == "digest"),
    }
    plan.setdefault("digest_pacing", {})
    plan["digest_pacing"]["post_audio_tightening"] = summary
    write_json(EDIT_PLAN, plan)
    write_json(REPORT, {"summary": summary, "events": report_items})
    print(json.dumps({"output": str(EDIT_PLAN), "report": str(REPORT), **summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
