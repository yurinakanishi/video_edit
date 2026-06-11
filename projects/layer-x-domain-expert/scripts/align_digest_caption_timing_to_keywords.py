from __future__ import annotations

import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


PROJECT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT / "output" / "reports"
EDIT_PLAN = REPORTS / "edit_plan.json"
TRANSCRIPT = REPORTS / "transcript.json"
REPORT_PATH = REPORTS / "digest_caption_keyword_timing_report.json"
JST = timezone(timedelta(hours=9))


# The digest captions are editorial summaries. Their source SRT spans often
# start with filler such as "本当におっしゃっていたけど" or "そこのある意味".
# Align the display to the spoken keyword, not the whole source segment start.
ANCHOR_PHRASES: dict[str, list[str]] = {
    "開発に関わる仕事をする中で": ["開発に関わる仕事をする中で"],
    "これめっちゃ大変でしたとかありますか？": ["これめっちゃ大変"],
    "何でも知ってそうに見える": ["何でも知ってそう"],
    "期待の高さがハードルになる": ["ハードル"],
    "ドメインをめっちゃ調べている": ["ドメインの方めっちゃ調べ", "ドメイン", "めっちゃ調べ"],
    "正直僕より詳しいこともある": ["正直全然僕より詳しい", "正直", "僕より詳しい"],
    "「なんで？」を絶対に逃がしてくれない": ["なんでなんですかを絶対に逃がしてくれない", "絶対に逃がしてくれない"],
    "健全なプレッシャーがある": ["健全なプレッシャー"],
    "ちゃんと伝えるには背景まで整理する": ["ちゃんと伝えるには背景まで整理", "背景まで整理"],
    "足すだけでなく「なくていい」と言えることも価値": ["いらないもの", "言ってあげる", "なくていい"],
}


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clean(text: Any) -> str:
    return re.sub(r"\s+", "", str(text or "").replace("、", "").replace("。", "").replace("？", "?"))


def ref_window(event: dict[str, Any]) -> tuple[float, float] | None:
    source = event.get("reference_source") if isinstance(event.get("reference_source"), dict) else event.get("source")
    if not isinstance(source, dict) or source.get("in") is None or source.get("out") is None:
        return None
    return float(source["in"]), float(source["out"])


def digest_duration(event: dict[str, Any]) -> float:
    return max(0.01, float(event["timeline_end"]) - float(event["timeline_start"]))


def transcript_text_for_window(segments: list[dict[str, Any]], start: float, end: float) -> str:
    return "".join(
        str(segment.get("text") or "")
        for segment in segments
        if max(0.0, min(float(segment.get("end") or 0.0), end) - max(float(segment.get("start") or 0.0), start)) > 0.08
    )


def source_window_from_overlay(event: dict[str, Any], overlay: dict[str, Any]) -> tuple[float, float] | None:
    ref = ref_window(event)
    if not ref:
        return None
    metadata = overlay.get("metadata") if isinstance(overlay.get("metadata"), dict) else {}
    if metadata.get("source_start_sec") is not None and metadata.get("source_end_sec") is not None:
        try:
            start = float(metadata["source_start_sec"])
            end = float(metadata["source_end_sec"])
            return start, max(start + 0.2, end)
        except (TypeError, ValueError):
            pass
    start = ref[0] + float(overlay.get("start") or 0.0)
    end = ref[0] + float(overlay.get("end") or overlay.get("start") or 0.0)
    return start, max(start + 0.2, end)


def keyword_offset_ratio(source_text: str, phrases: list[str]) -> tuple[float, str] | None:
    normalized = clean(source_text)
    if not normalized:
        return None
    best: tuple[int, str] | None = None
    for phrase in phrases:
        normalized_phrase = clean(phrase)
        if not normalized_phrase:
            continue
        index = normalized.find(normalized_phrase)
        if index >= 0 and (best is None or index < best[0]):
            best = (index, normalized_phrase)
    if best is None:
        return None
    ratio = best[0] / max(1, len(normalized))
    return ratio, best[1]


def main() -> None:
    plan = load(EDIT_PLAN)
    transcript = load(TRANSCRIPT).get("segments", [])
    changes: list[dict[str, Any]] = []

    for event in plan.get("timeline", []):
        if event.get("section") != "digest":
            continue
        ref = ref_window(event)
        if not ref:
            continue
        event_duration = digest_duration(event)
        for overlay in event.get("overlays", []) or []:
            if not (isinstance(overlay, dict) and overlay.get("type") == "caption"):
                continue
            text = str(overlay.get("text") or "")
            phrases = ANCHOR_PHRASES.get(text)
            if not phrases:
                continue
            old_start = float(overlay.get("start") or 0.0)
            old_end = float(overlay.get("end") or old_start)
            source = source_window_from_overlay(event, overlay)
            if not source:
                continue
            source_text = transcript_text_for_window(transcript, source[0], source[1])
            anchor = keyword_offset_ratio(source_text, phrases)
            if not anchor:
                continue
            ratio, matched_phrase = anchor
            source_duration = max(0.2, source[1] - source[0])
            anchor_shift = source_duration * ratio
            source_local_start = max(0.0, source[0] - ref[0])
            new_start = round(min(event_duration - 0.5, max(0.0, source_local_start + anchor_shift)), 3)
            # Keep the next caption boundary stable. If a caption starts late in
            # its segment, display it through the original segment end.
            min_display = 1.45 if len(clean(text)) <= 18 else 1.9
            new_end = round(min(event_duration, max(old_end, new_start + min_display)), 3)
            # Avoid swallowing the next caption when the original boundary was
            # already the transition point.
            following_starts = [
                float(other.get("start") or 0.0)
                for other in event.get("overlays", []) or []
                if isinstance(other, dict)
                and other is not overlay
                and other.get("type") == "caption"
                and float(other.get("start") or 0.0) > old_start
            ]
            if following_starts:
                next_start = min(following_starts)
                new_end = min(new_end, next_start)
            if abs(new_start - old_start) < 0.08 and abs(new_end - old_end) < 0.08:
                continue
            overlay["start"] = new_start
            overlay["end"] = new_end
            metadata = overlay.setdefault("metadata", {})
            if isinstance(metadata, dict):
                metadata["source"] = "edit_plan_caption_overlay"
                metadata["caption_source_of_truth"] = "edit_plan.json"
                metadata["keyword_timing_aligned"] = True
                metadata["keyword_timing_anchor"] = matched_phrase
                metadata["caption_start_sec"] = round(ref[0] + new_start, 3)
                metadata["caption_end_sec"] = round(ref[0] + new_end, 3)
                metadata.setdefault("source_start_sec", round(source[0], 3))
                metadata.setdefault("source_end_sec", round(source[1], 3))
            overlay["audio_alignment"] = {
                "method": "digest_keyword_anchor_timing",
                "source_audio_media_id": "group_wide",
                "source_window_sec": [round(source[0], 3), round(source[1], 3)],
                "speech_window_sec": [round(ref[0] + new_start, 3), round(ref[0] + new_end, 3)],
                "diagnostics": {
                    "source_text": source_text,
                    "matched_phrase": matched_phrase,
                    "keyword_offset_ratio": round(ratio, 3),
                    "old_local_timing": [old_start, old_end],
                },
            }
            changes.append(
                {
                    "event_id": event.get("event_id"),
                    "text": text,
                    "matched_phrase": matched_phrase,
                    "source_text": source_text,
                    "old_local_timing": [old_start, old_end],
                    "new_local_timing": [new_start, new_end],
                    "old_source_time": [round(ref[0] + old_start, 3), round(ref[0] + old_end, 3)],
                    "new_source_time": [round(ref[0] + new_start, 3), round(ref[0] + new_end, 3)],
                }
            )

    updated_at = datetime.now(JST).isoformat(timespec="seconds")
    plan["updated_at"] = updated_at
    plan.setdefault("revision_notes", []).append(
        {
            "updated_at": updated_at,
            "change": "Aligned digest captions to the spoken keyword inside each source segment.",
            "change_count": len(changes),
        }
    )
    save(EDIT_PLAN, plan)
    report = {
        "schema_version": "digest_caption_keyword_timing_report.v1",
        "project_id": "layer-x-domain-expert",
        "updated_at": updated_at,
        "root_cause": "Digest captions were editorial summaries but used whole SRT segment starts, so summary captions appeared during spoken prefixes.",
        "source_of_truth": "edit_plan.json timeline[].overlays[type=caption]",
        "change_count": len(changes),
        "changes": changes,
    }
    save(REPORT_PATH, report)
    print(json.dumps({"change_count": len(changes), "report": str(REPORT_PATH)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
