from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT_ROOT / "output" / "reports"
JST = timezone(timedelta(hours=9))


def now_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def clean(text: str) -> str:
    return (
        text.replace(" ", "")
        .replace("　", "")
        .replace(",", "、")
        .replace(".", "。")
        .strip()
    )


def find_start(segments: list[dict[str, Any]]) -> dict[str, Any]:
    countdown_index = None
    for index, segment in enumerate(segments):
        text = clean(str(segment.get("text") or ""))
        if "5、4、3" in text or "5,4,3" in text or "本番543" in text or "本番5秒前" in text:
            countdown_index = index
    if countdown_index is None:
        raise SystemExit("Could not find production countdown marker.")
    for segment in segments[countdown_index + 1 :]:
        text = clean(str(segment.get("text") or ""))
        if text and not text.isdigit():
            return {
                "start_sec": round(float(segment.get("start") or 0.0), 3),
                "anchor_segment_id": segment.get("segment_id"),
                "anchor_text": segment.get("text"),
                "detected_from": "first speech segment after final 本番 / 5,4,3 countdown marker",
            }
    raise SystemExit("Could not find first production speech after countdown marker.")


def find_end(segments: list[dict[str, Any]]) -> dict[str, Any]:
    ending_phrases = [
        "ご視聴いただきました。ありがとうございました。",
        "ご視聴いただきありがとうございました。",
        "ご視聴いただきましたありがとうございました",
        "ありがとうございました。",
    ]
    for segment in segments:
        text = clean(str(segment.get("text") or ""))
        if any(clean(phrase) in text for phrase in ending_phrases[:3]):
            return {
                "end_sec": round(float(segment.get("start") or 0.0), 3),
                "anchor_segment_id": segment.get("segment_id"),
                "anchor_text": segment.get("text"),
                "detected_from": "closing ご視聴 / ありがとうございました marker",
                "detected": True,
            }
    return {
        "end_sec": None,
        "anchor_segment_id": None,
        "anchor_text": None,
        "detected_from": "closing marker not present in current master transcript",
        "detected": False,
    }


def media_duration(manifest: dict[str, Any], media_id: str) -> float | None:
    for item in manifest.get("media", []):
        if item.get("media_id") == media_id:
            try:
                return float(item.get("duration") or 0.0)
            except (TypeError, ValueError):
                return None
    return None


def main() -> None:
    transcript = read_json(REPORTS / "transcript.json")
    manifest = read_json(REPORTS / "project_manifest.json")
    segments = [segment for segment in transcript.get("segments", []) if isinstance(segment, dict)]
    start = find_start(segments)
    end = find_end(segments)
    fallback_end = media_duration(manifest, "group_wide")
    effective_end = end["end_sec"] if end["end_sec"] is not None else fallback_end
    payload = {
        "schema_version": "content_window.v1",
        "project_id": "layer-x-domain-expert",
        "generated_at": now_iso(),
        "time_unit": "seconds",
        "reference_media_id": "group_wide",
        "usable_master_range": {
            "start_sec": start["start_sec"],
            "end_sec": round(float(effective_end), 3) if effective_end is not None else None,
            "start_inclusive": True,
            "end_exclusive": True,
        },
        "start_marker": start,
        "end_marker": end,
        "rules": {
            "exclude_before_start": True,
            "exclude_after_end_marker": True,
            "do_not_use_preroll_rehearsal_or_countdown": True,
            "do_not_use_closing_thanks_or_anything_after": True,
            "company_movie_bridge_uses_own_source_time": True,
        },
        "forbidden_text_markers": [
            "本番5秒前",
            "5、4、3",
            "本番543",
            "ご視聴いただきました。ありがとうございました。",
            "ご視聴いただきありがとうございました。",
            "ありがとうございました。",
        ],
    }
    write_json(REPORTS / "content_window.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
