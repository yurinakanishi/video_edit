from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


PROJECT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT / "output" / "reports"
EDIT_PLAN = REPORTS / "edit_plan.json"
TRANSCRIPT = REPORTS / "transcript.json"
REPORT_PATH = REPORTS / "main_caption_keyword_timing_audit.json"

MAX_EARLY_SEC = 0.75


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def clean(text: Any) -> str:
    return re.sub(r"\s+", "", str(text or "").replace("、", "").replace("。", "").replace("「", "").replace("」", ""))


def ref_window(event: dict[str, Any]) -> tuple[float, float] | None:
    source = event.get("reference_source") if isinstance(event.get("reference_source"), dict) else event.get("source")
    if not isinstance(source, dict) or source.get("in") is None or source.get("out") is None:
        return None
    return float(source["in"]), float(source["out"])


def overlap(a: tuple[float, float], b: tuple[float, float]) -> float:
    return max(0.0, min(a[1], b[1]) - max(a[0], b[0]))


def transcript_text(segments: list[dict[str, Any]], start: float, end: float) -> str:
    return "".join(
        str(segment.get("text") or "")
        for segment in segments
        if overlap((float(segment.get("start") or 0.0), float(segment.get("end") or 0.0)), (start, end)) > 0.08
    )


def context_items_by_caption_id(event: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item["caption_id"]): item
        for item in event.get("main_caption_plan_items", []) or []
        if isinstance(item, dict) and item.get("caption_id")
    }


def find_anchor(text: str, context: dict[str, Any], source_text: str) -> tuple[float, str, str] | None:
    normalized_source = clean(source_text)
    if not normalized_source:
        return None
    candidates: list[tuple[int, str, str]] = []
    for key in context.get("search_keys", []) or []:
        k = clean(key)
        if not k:
            continue
        index = normalized_source.find(k)
        if index >= 0:
            candidates.append((index, k, "search_key"))
            continue
        if len(k) >= 8:
            for n in range(min(len(k), 10), 4, -1):
                for fragment in (k[:n], k[-n:]):
                    index = normalized_source.find(fragment)
                    if index >= 0:
                        candidates.append((index, fragment, "search_key_fragment"))
                        break
                else:
                    continue
                break
    display = clean(text)
    for n in range(min(len(display), 12), 5, -1):
        for fragment in (display[:n], display[-n:]):
            index = normalized_source.find(fragment)
            if index >= 0:
                candidates.append((index, fragment, "display_fragment"))
                break
        if candidates and candidates[-1][2] == "display_fragment":
            break
    if not candidates:
        return None
    index, fragment, method = min(candidates, key=lambda item: item[0])
    return index / max(1, len(normalized_source)), fragment, method


def main() -> None:
    plan = load(EDIT_PLAN)
    transcript = load(TRANSCRIPT).get("segments", [])
    issues: list[dict[str, Any]] = []
    checked = 0
    unknown_anchor = 0

    for event in plan.get("timeline", []):
        if event.get("section") != "main":
            continue
        ref = ref_window(event)
        if not ref:
            continue
        context = context_items_by_caption_id(event)
        for overlay in event.get("overlays", []) or []:
            if not (isinstance(overlay, dict) and overlay.get("type") == "caption"):
                continue
            metadata = overlay.get("metadata") if isinstance(overlay.get("metadata"), dict) else {}
            source_start = metadata.get("source_start_sec")
            source_end = metadata.get("source_end_sec")
            if source_start is None or source_end is None:
                continue
            source_start = float(source_start)
            source_end = float(source_end)
            source_text = transcript_text(transcript, source_start, source_end)
            item = context.get(str(overlay.get("caption_id") or ""), {})
            anchor = find_anchor(str(overlay.get("text") or ""), item, source_text)
            if not anchor:
                unknown_anchor += 1
                continue
            checked += 1
            ratio, fragment, method = anchor
            expected_source_start = source_start + (source_end - source_start) * ratio
            displayed_source_start = ref[0] + float(overlay.get("start") or 0.0)
            early_by = expected_source_start - displayed_source_start
            if early_by > MAX_EARLY_SEC:
                issues.append(
                    {
                        "event_id": event.get("event_id"),
                        "caption_id": overlay.get("caption_id"),
                        "text": overlay.get("text"),
                        "displayed_source_start": round(displayed_source_start, 3),
                        "expected_keyword_source_start": round(expected_source_start, 3),
                        "early_by_sec": round(early_by, 3),
                        "matched_fragment": fragment,
                        "anchor_method": method,
                        "source_window_sec": [round(source_start, 3), round(source_end, 3)],
                        "source_text": source_text,
                    }
                )
    report = {
        "schema_version": "main_caption_keyword_timing_audit.v1",
        "project_id": "layer-x-domain-expert",
        "source_of_truth": "edit_plan.json timeline[].overlays[type=caption]",
        "checked_caption_count": checked,
        "unknown_anchor_count": unknown_anchor,
        "issue_count": len(issues),
        "max_early_sec": MAX_EARLY_SEC,
        "issues": issues,
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ["checked_caption_count", "unknown_anchor_count", "issue_count"]}, ensure_ascii=False, indent=2))
    if issues:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
