from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT_ROOT / "output" / "reports"
CAPTIONS_MD = REPORTS / "captions.md"
JST = timezone(timedelta(hours=9))


PEOPLE = {
    "person_01": {"name": "矢野", "screen_position": "left", "role": "interviewer"},
    "person_02": {"name": "根本", "screen_position": "middle", "role": "interviewee"},
    "person_03": {"name": "村田", "screen_position": "right", "role": "interviewee"},
}


def now_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("、", "")).strip()


def compact_caption_text(text: str, max_chars: int = 36) -> str:
    text = clean_text(text)
    if len(text) <= max_chars:
        return text
    for marker in ("。", "という", "ため", "こと", "役割", "価値", "重要", "おすすめ", "できる"):
        index = text.find(marker)
        if 12 <= index + len(marker) <= max_chars:
            return text[: index + len(marker)].strip("。")
    return text[:max_chars].rstrip("。")


def normalize(text: str) -> str:
    return re.sub(r"\s+", "", clean_text(text).replace("。", "").replace("？", "").replace("?", ""))


def parse_timecode(value: str) -> float:
    text = value.strip()
    parts = text.split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    raise ValueError(value)


def parse_captions_md() -> list[dict[str, Any]]:
    text = CAPTIONS_MD.read_text(encoding="utf-8")
    matches = list(re.finditer(r"^##\s+(\d+)(?:[｜|]\s*([0-9:]+)\s*[〜~-]\s*([0-9:]+))?\s*$", text, re.M))
    items: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        lines = [line.strip() for line in body.splitlines() if line.strip()]
        display_lines = []
        search_keys = []
        for line in lines:
            if line.startswith("検索キー"):
                _, _, keys = line.partition("：")
                if not keys:
                    _, _, keys = line.partition(":")
                search_keys = [clean_text(part) for part in re.split(r"[/／]", keys) if clean_text(part)]
                break
            if line == "---":
                continue
            display_lines.append(line)
        display_text = clean_text(" ".join(display_lines))
        if not display_text:
            continue
        item: dict[str, Any] = {
            "caption_no": int(match.group(1)),
            "display_text": display_text,
            "search_keys": search_keys,
        }
        if match.group(2) and match.group(3):
            item["time_hint_start_sec"] = parse_timecode(match.group(2))
            item["time_hint_end_sec"] = parse_timecode(match.group(3))
        items.append(item)
    return items


def transcript_segments() -> list[dict[str, Any]]:
    transcript = read_json(REPORTS / "transcript.json", {})
    content = read_json(REPORTS / "content_window.json", {})
    usable = content.get("usable_master_range") if isinstance(content.get("usable_master_range"), dict) else {}
    start_bound = float(usable.get("start_sec") or 0.0)
    end_bound = float(usable.get("end_sec") or 999999.0)
    result = []
    for segment in transcript.get("segments", []):
        text = clean_text(str(segment.get("text") or ""))
        if not text or text == "音声に忠実に文字起こしないでください。":
            continue
        start = float(segment.get("start") or 0.0)
        end = float(segment.get("end") or start)
        if end <= start_bound or start >= end_bound:
            continue
        result.append({**segment, "text": text, "start": start, "end": end, "norm": normalize(text)})
    return result


def load_activity() -> dict[str, dict[str, Any]]:
    payload = read_json(REPORTS / "speaker_activity_analysis.json", {})
    return {
        str(item.get("segment_id")): item
        for item in payload.get("segments", [])
        if isinstance(item, dict) and item.get("segment_id")
    }


def person_for_time(start: float, text: str, segment_id: str, activity: dict[str, dict[str, Any]]) -> tuple[str, str, float]:
    activity_item = activity.get(segment_id)
    if activity_item and activity_item.get("active_person_id") in PEOPLE:
        return str(activity_item["active_person_id"]), "speaker_activity_analysis", float(activity_item.get("confidence") or 0.5)
    if start < 623.52:
        return "person_01", "intro_time_window", 0.9
    if start < 671.06:
        return "person_02", "intro_time_window", 0.9
    if start < 722.5:
        return "person_03", "intro_time_window", 0.9
    if start < 786.2:
        return "person_01", "intro_time_window", 0.9

    norm = normalize(text)
    if any(token in norm for token in ("根元さん", "根本さん", "お二人", "ですか", "ますか", "聞いていきます", "おすすめしてください")):
        return "person_01", "question_text_heuristic", 0.72
    if any(token in norm for token in ("経理", "PDM", "バクラク", "決算", "プロダクトマネージャー", "会計", "バックオフィス")):
        return "person_02", "domain_keyword_heuristic", 0.62
    if any(token in norm for token in ("労務", "人事", "HR", "勤怠", "給与", "社会保険", "村田")):
        return "person_03", "domain_keyword_heuristic", 0.62
    return "person_01", "fallback_wide_safe", 0.35


def person_for_caption_no(caption_no: int) -> tuple[str, str, float] | None:
    ranges = [
        (range(1, 4), "person_01"),
        (range(4, 11), "person_02"),
        (range(11, 16), "person_03"),
        (range(16, 20), "person_02"),
        (range(20, 21), "person_01"),
        (range(21, 26), "person_03"),
        (range(26, 28), "person_02"),
        (range(28, 32), "person_03"),
        (range(32, 39), "person_03"),
        (range(39, 44), "person_03"),
        (range(44, 50), "person_02"),
        (range(50, 51), "person_03"),
        (range(51, 54), "person_01"),
        (range(54, 57), "person_02"),
        (range(57, 59), "person_03"),
        (range(59, 63), "person_01"),
        (range(63, 66), "person_02"),
        (range(66, 72), "person_03"),
        (range(72, 74), "person_02"),
        (range(74, 84), "person_02"),
        (range(84, 89), "person_03"),
        (range(89, 91), "person_02"),
        (range(91, 92), "person_01"),
        (range(92, 93), "person_02"),
        (range(93, 94), "person_03"),
    ]
    for number_range, person_id in ranges:
        if caption_no in number_range:
            return person_id, "captions_md_topic_speaker_map", 0.78
    return None


def find_by_keywords(item: dict[str, Any], segments: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str, float]:
    keys = [normalize(key) for key in item.get("search_keys", []) if normalize(key)]
    if not keys:
        return None, "no_search_keys", 0.0
    best: tuple[float, dict[str, Any] | None] = (0.0, None)
    for index, segment in enumerate(segments):
        window = " ".join(s["norm"] for s in segments[index : index + 3])
        hits = sum(1 for key in keys if key and key in window)
        if not hits:
            continue
        score = hits / len(keys)
        if score > best[0]:
            best = (score, segment)
    if best[1] is None:
        return None, "keyword_match_failed", 0.0
    return best[1], "keyword_match", round(best[0], 3)


def find_segment_for_item(item: dict[str, Any], segments: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str, float]:
    if "time_hint_start_sec" in item:
        target = float(item["time_hint_start_sec"])
        timed = [segment for segment in segments if float(segment["end"]) > target and float(segment["start"]) < float(item.get("time_hint_end_sec", target + 15))]
        if timed:
            return timed[0], "captions_md_time_hint", 0.9
    return find_by_keywords(item, segments)


def build_plan() -> dict[str, Any]:
    items = parse_captions_md()
    segments = transcript_segments()
    activity = load_activity()
    selected = []
    used_starts: list[float] = []
    for item in items:
        segment, method, confidence = find_segment_for_item(item, segments)
        if not segment:
            continue
        start = float(item.get("time_hint_start_sec", segment["start"]))
        end = float(item.get("time_hint_end_sec", min(segment["end"], start + 7.0)))
        if any(abs(start - used) < 8.0 for used in used_starts):
            continue
        mapped_person = person_for_caption_no(int(item["caption_no"]))
        if mapped_person:
            person_id, speaker_method, speaker_confidence = mapped_person
        else:
            person_id, speaker_method, speaker_confidence = person_for_time(start, str(segment.get("text") or item["display_text"]), str(segment.get("segment_id") or ""), activity)
        person = PEOPLE[person_id]
        selected.append(
            {
                "caption_id": f"main_caption_{int(item['caption_no']):03d}",
                "caption_no": item["caption_no"],
                "source": "captions.md",
                "source_match_method": method,
                "source_match_confidence": confidence,
                "source_segment_id": segment.get("segment_id"),
                "source_start_sec": round(float(segment["start"]), 3),
                "source_end_sec": round(float(segment["end"]), 3),
                "caption_start_sec": round(start, 3),
                "caption_end_sec": round(max(end, start + 3.0), 3),
                "display_text": compact_caption_text(item["display_text"]),
                "full_reference_text": clean_text(item["display_text"]),
                "search_keys": item.get("search_keys", []),
                "speaker_person_id": person_id,
                "speaker_name": person["name"],
                "speaker_screen_position": person["screen_position"],
                "speaker_role": person["role"],
                "speaker_attribution_method": speaker_method,
                "speaker_attribution_confidence": round(speaker_confidence, 3),
            }
        )
        used_starts.append(start)
    selected.sort(key=lambda item: (float(item["caption_start_sec"]), int(item["caption_no"])))
    return {
        "schema_version": "main_caption_plan.v1",
        "project_id": "layer-x-domain-expert",
        "generated_at": now_iso(),
        "source": str(CAPTIONS_MD),
        "policy": {
            "main_only": True,
            "not_full_subtitles": True,
            "remove_japanese_commas": True,
            "speaker_metadata_required": True,
        },
        "people": PEOPLE,
        "captions": selected,
    }


def main() -> None:
    output = REPORTS / "main_caption_plan.json"
    plan = build_plan()
    write_json(output, plan)
    print(json.dumps({"output": str(output), "captions": len(plan["captions"])}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
