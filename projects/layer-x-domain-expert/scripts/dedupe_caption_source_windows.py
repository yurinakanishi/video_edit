from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT_ROOT / "output" / "reports"
EDIT_PLAN = REPORTS / "edit_plan.json"
REPORT = REPORTS / "caption_source_window_dedupe_report.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def root_id(event: dict[str, Any], overlay: dict[str, Any], index: int) -> str:
    metadata = overlay.get("metadata") if isinstance(overlay.get("metadata"), dict) else {}
    return str(metadata.get("caption_cut_continuation_root_id") or overlay.get("caption_id") or f"{event.get('event_id')}_caption_{index}")


def source_window(overlay: dict[str, Any]) -> tuple[float, float] | None:
    alignment = overlay.get("audio_alignment") if isinstance(overlay.get("audio_alignment"), dict) else {}
    source = alignment.get("source_window_sec")
    if isinstance(source, list) and len(source) == 2:
        try:
            return float(source[0]), float(source[1])
        except (TypeError, ValueError):
            pass
    metadata = overlay.get("metadata") if isinstance(overlay.get("metadata"), dict) else {}
    if metadata.get("source_start_sec") is not None and metadata.get("source_end_sec") is not None:
        try:
            return float(metadata["source_start_sec"]), float(metadata["source_end_sec"])
        except (TypeError, ValueError):
            return None
    return None


def speech_start(overlay: dict[str, Any], fallback: float) -> float:
    alignment = overlay.get("audio_alignment") if isinstance(overlay.get("audio_alignment"), dict) else {}
    speech = alignment.get("speech_window_sec")
    if isinstance(speech, list) and len(speech) == 2:
        try:
            return float(speech[0])
        except (TypeError, ValueError):
            pass
    return fallback


def main() -> None:
    plan = read_json(EDIT_PLAN)
    events = [event for event in plan.get("timeline", []) if isinstance(event, dict)]
    grouped: dict[tuple[Any, ...], dict[str, dict[str, Any]]] = defaultdict(dict)

    for event in events:
        section = event.get("section")
        for index, overlay in enumerate(event.get("overlays", []) or []):
            if not (isinstance(overlay, dict) and overlay.get("type") == "caption"):
                continue
            metadata = overlay.get("metadata") if isinstance(overlay.get("metadata"), dict) else {}
            if metadata.get("caption_cut_continuation"):
                continue
            src = source_window(overlay)
            if not src:
                continue
            key = (section, round(src[0], 2), round(src[1], 2))
            rid = root_id(event, overlay, index)
            current = grouped[key].setdefault(
                rid,
                {
                    "root_id": rid,
                    "caption_id": overlay.get("caption_id"),
                    "text": overlay.get("text"),
                    "source_window_sec": [round(src[0], 3), round(src[1], 3)],
                    "first_speech_start_sec": speech_start(overlay, src[0]),
                    "event_id": event.get("event_id"),
                },
            )
            current["first_speech_start_sec"] = min(float(current["first_speech_start_sec"]), speech_start(overlay, src[0]))

    dropped_roots: set[str] = set()
    duplicate_groups = []
    for key, roots in grouped.items():
        if len(roots) <= 1:
            continue
        ordered = sorted(
            roots.values(),
            key=lambda item: (
                float(item["first_speech_start_sec"]),
                0 if not str(item.get("caption_id") or "").startswith("main_caption_auto_") else 1,
                str(item.get("caption_id") or ""),
            ),
        )
        keep = ordered[0]
        drop = ordered[1:]
        for item in drop:
            dropped_roots.add(str(item["root_id"]))
        duplicate_groups.append({"key": key, "kept": keep, "dropped": drop})

    removed = []
    if dropped_roots:
        for event in events:
            next_overlays = []
            for index, overlay in enumerate(event.get("overlays", []) or []):
                if not (isinstance(overlay, dict) and overlay.get("type") == "caption"):
                    next_overlays.append(overlay)
                    continue
                rid = root_id(event, overlay, index)
                if rid in dropped_roots:
                    removed.append(
                        {
                            "event_id": event.get("event_id"),
                            "caption_id": overlay.get("caption_id"),
                            "root_id": rid,
                            "text": overlay.get("text"),
                        }
                    )
                    continue
                next_overlays.append(overlay)
            event["overlays"] = next_overlays

    plan.setdefault("metadata", {})["caption_source_window_dedupe"] = {
        "enabled": True,
        "dropped_root_count": len(dropped_roots),
        "reason": "Only one caption root may own a source speech window; later duplicate captions get pushed out of sync.",
    }
    write_json(EDIT_PLAN, plan)
    report = {
        "schema_version": "caption_source_window_dedupe_report.v1",
        "duplicate_group_count": len(duplicate_groups),
        "dropped_root_count": len(dropped_roots),
        "removed_overlay_count": len(removed),
        "duplicate_groups": duplicate_groups,
        "removed": removed,
    }
    write_json(REPORT, report)
    print(json.dumps({k: report[k] for k in ("duplicate_group_count", "dropped_root_count", "removed_overlay_count")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
