from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT_ROOT / "output" / "reports"
EDIT_PLAN = REPORTS / "edit_plan.json"
VOICE_ATTRIBUTION = REPORTS / "voice_speaker_attribution.json"
REPORT_JSON = REPORTS / "long_caption_speech_unit_split_report.json"
REPORT_MD = REPORTS / "long_caption_speech_unit_split_report.md"
JST = timezone(timedelta(hours=9))

PERSON_NAMES = {
    "person_01": "矢野",
    "person_02": "根本",
    "person_03": "村田",
}

FILLER_PATTERNS = [
    "そうですね",
    "確かに",
    "なるほど",
    "なんか",
    "やっぱり",
    "結構",
    "ちょっと",
    "ある種",
    "本当に",
    "多分",
    "いわゆる",
]

TAIL_PATTERNS = [
    "という感じです",
    "という感じ",
    "っていう感じです",
    "っていう感じ",
    "と思いますね",
    "と思います",
    "思いますね",
    "思います",
    "と思っていて",
    "と思ってて",
    "思っていて",
    "思ってて",
    "なんですよね",
    "なんですよ",
    "ですよね",
    "ですね",
    "ですけれども",
    "ですけど",
    "ますけれども",
    "ますけど",
]

MANUAL_SPLITS: dict[str, list[dict[str, Any]]] = {
    "main_caption_047": [
        {
            "start": 1848.54,
            "end": 1853.76,
            "text": "ルールを調べるだけなら\nエンジニアにもできる",
            "speaker_person_id": "person_02",
            "reason": "User-reported mismatch around 22:00; the first half is about rule research only.",
        },
        {
            "start": 1855.46,
            "end": 1866.46,
            "text": "何を実現したいかという\nビジョンが必要になる",
            "speaker_person_id": "person_01",
            "reason": "User-reported mismatch around 22:00; the latter half is the vision point.",
        },
    ],
}

SKIP_TEXT_NORMALIZED = {
    "そう",
    "はい",
    "ええ",
    "うん",
    "いや",
    "確かに",
    "なるほど",
}

MAX_AUTO_UNIT_SEC = 6.8
LONG_SOURCE_SEC = 9.0
LONG_DISPLAY_SEC = 7.8
SHORT_TEXT_CHARS = 34


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clean_space(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def normalize_id(caption_id: Any) -> str:
    value = str(caption_id or "")
    if "__cont__" in value:
        return value.split("__cont__", 1)[0]
    return value


def root_id_for_overlay(event: dict[str, Any], overlay: dict[str, Any], index: int) -> str:
    metadata = overlay.get("metadata") if isinstance(overlay.get("metadata"), dict) else {}
    for key in ("main_caption_id", "caption_cut_continuation_root_id", "caption_continuation_root_id"):
        if metadata.get(key):
            return normalize_id(metadata[key])
    if overlay.get("caption_id"):
        return normalize_id(overlay.get("caption_id"))
    return f"{event.get('event_id')}_caption_{index}"


def event_ref_window(event: dict[str, Any]) -> tuple[float, float] | None:
    source = event.get("reference_source") if isinstance(event.get("reference_source"), dict) else event.get("source")
    if not isinstance(source, dict) or source.get("in") is None or source.get("out") is None:
        return None
    if source.get("media_id") != "group_wide":
        return None
    return float(source["in"]), float(source["out"])


def event_duration(event: dict[str, Any]) -> float:
    return max(0.01, float(event.get("timeline_end") or 0.0) - float(event.get("timeline_start") or 0.0))


def source_window_for_overlay(overlay: dict[str, Any]) -> tuple[float, float] | None:
    alignment = overlay.get("audio_alignment") if isinstance(overlay.get("audio_alignment"), dict) else {}
    window = alignment.get("source_window_sec")
    if isinstance(window, list) and len(window) == 2:
        return float(window[0]), float(window[1])
    metadata = overlay.get("metadata") if isinstance(overlay.get("metadata"), dict) else {}
    if metadata.get("source_start_sec") is not None and metadata.get("source_end_sec") is not None:
        return float(metadata["source_start_sec"]), float(metadata["source_end_sec"])
    if metadata.get("caption_start_sec") is not None and metadata.get("caption_end_sec") is not None:
        return float(metadata["caption_start_sec"]), float(metadata["caption_end_sec"])
    return None


def normalize_text(text: str) -> str:
    value = clean_space(text)
    value = re.sub(r"[、。，．「」『』（）()・!?！？…ー〜~,.]", "", value)
    return value


def strip_fillers(text: str) -> str:
    value = str(text or "").replace("、", "").replace("。", "")
    value = re.sub(r"\s+", "", value)
    for pattern in FILLER_PATTERNS:
        if value.startswith(pattern):
            value = value[len(pattern) :]
    for pattern in TAIL_PATTERNS:
        if value.endswith(pattern):
            value = value[: -len(pattern)]
    value = value.replace("っていう", "という")
    value = value.replace("じゃないですか", "")
    value = value.replace("じゃないですけど", "")
    value = value.replace("みたいな", "")
    return value


def captionize(text: str) -> str:
    value = strip_fillers(text)
    replacements = {
        "ルールを調べて機能を作るんだったら": "ルールを調べて機能を作るだけなら",
        "エンジニアの人はできると思うんですよ": "エンジニアにもできる",
        "これからのこの機能でこういうことが実現したいんだ": "この機能で何を実現したいのか",
        "ビジョン的なものを描く逆に言うと": "ビジョンを描く",
        "ご興味がありましたらぜひご覧いただけると嬉しいです": "興味があればぜひご覧ください",
    }
    for src, dst in replacements.items():
        value = value.replace(src, dst)
    value = value.strip()
    if not value or normalize_text(value) in SKIP_TEXT_NORMALIZED:
        return ""
    if len(value) <= 28:
        return value

    separators = ["ので", "から", "けど", "が", "し", "と", "には", "なら", "ために", "上で"]
    best: list[str] | None = None
    for sep in separators:
        idx = value.find(sep)
        if 7 <= idx <= len(value) - 7:
            left = value[: idx + len(sep)]
            right = value[idx + len(sep) :]
            if len(left) <= 24 and len(right) <= 26:
                best = [left, right]
                break
    if best:
        return "\n".join(best)

    if len(value) > 52:
        value = value[:52]
    return value


def useful_segments(
    segments: list[dict[str, Any]],
    window: tuple[float, float],
) -> list[dict[str, Any]]:
    start, end = window
    result = []
    for segment in segments:
        seg_start = float(segment.get("start") or 0.0)
        seg_end = float(segment.get("end") or 0.0)
        overlap = max(0.0, min(end, seg_end) - max(start, seg_start))
        if overlap < 0.45:
            continue
        text = str(segment.get("text") or "")
        if not captionize(text):
            continue
        result.append(segment)
    return result


def auto_split_units(root: str, text: str, window: tuple[float, float], segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if root in MANUAL_SPLITS:
        return MANUAL_SPLITS[root]

    chunks: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []

    def flush() -> None:
        nonlocal current
        if not current:
            return
        start = max(window[0], float(current[0].get("start") or 0.0))
        end = min(window[1], float(current[-1].get("end") or 0.0))
        raw_text = "".join(str(segment.get("text") or "") for segment in current)
        caption_text = captionize(raw_text)
        if caption_text and end - start >= 0.5:
            chunks.append(
                {
                    "start": round(start, 3),
                    "end": round(end, 3),
                    "text": caption_text,
                    "speaker_person_id": current[0].get("speaker_person_id"),
                    "reason": "Split long summarized caption into a speech-matched unit.",
                }
            )
        current = []

    for segment in useful_segments(segments, window):
        seg_start = float(segment.get("start") or 0.0)
        seg_end = float(segment.get("end") or 0.0)
        speaker = segment.get("speaker_person_id")
        if current:
            cur_start = float(current[0].get("start") or 0.0)
            cur_speaker = current[0].get("speaker_person_id")
            if speaker != cur_speaker or seg_end - cur_start > MAX_AUTO_UNIT_SEC:
                flush()
        current.append(segment)
    flush()

    if not chunks:
        return []

    # Avoid creating many noisy fragments. Keep at most the first three speech
    # units, unless this is the explicitly reviewed caption.
    if len(chunks) > 3:
        chunks = chunks[:3]
    return chunks


def is_candidate(root: str, overlay: dict[str, Any], source_window: tuple[float, float]) -> bool:
    if root in MANUAL_SPLITS:
        return True
    text = str(overlay.get("text") or "")
    chars = len(clean_space(text))
    duration = float(overlay.get("end") or 0.0) - float(overlay.get("start") or 0.0)
    source_dur = source_window[1] - source_window[0]
    metadata = overlay.get("metadata") if isinstance(overlay.get("metadata"), dict) else {}
    if metadata.get("caption_cut_continuation"):
        return False
    if source_dur >= 12.0 and chars <= SHORT_TEXT_CHARS + 8:
        return True
    if source_dur >= LONG_SOURCE_SEC and duration >= LONG_DISPLAY_SEC and chars <= SHORT_TEXT_CHARS:
        return True
    return False


def make_overlay(
    *,
    root: str,
    part_index: int,
    base_overlay: dict[str, Any],
    event: dict[str, Any],
    unit: dict[str, Any],
    local_start: float,
    local_end: float,
    continuation: bool,
) -> dict[str, Any]:
    speaker_id = str(unit.get("speaker_person_id") or base_overlay.get("speaker_person_id") or "")
    caption_id = f"{root}__unit_{part_index:02d}"
    if continuation:
        caption_id = f"{caption_id}__cont__{event.get('event_id')}"
    metadata = dict(base_overlay.get("metadata") or {})
    metadata.update(
        {
            "main_caption_id": root,
            "source": "edit_plan_caption_overlay",
            "source_start_sec": round(float(unit["start"]), 3),
            "source_end_sec": round(float(unit["end"]), 3),
            "caption_start_sec": round(float(unit["start"]), 3),
            "caption_end_sec": round(float(unit["end"]), 3),
            "caption_source_full_window_sec": [round(float(unit["start"]), 3), round(float(unit["end"]), 3)],
            "caption_handoff_end_sec": round(float(unit["end"]), 3),
            "caption_source_of_truth": "edit_plan.json",
            "speech_unit_split": True,
            "speech_unit_split_root_id": root,
            "speech_unit_split_reason": unit.get("reason"),
        }
    )
    if speaker_id:
        metadata["speaker_person_id"] = speaker_id
        metadata["speaker_name"] = PERSON_NAMES.get(speaker_id, metadata.get("speaker_name") or speaker_id)
    if continuation:
        metadata["caption_cut_continuation"] = True
        metadata["caption_continues_from_event_id"] = metadata.get("caption_continues_from_event_id") or root
    else:
        metadata.pop("caption_cut_continuation", None)
        metadata.pop("caption_continues_from_event_id", None)
    overlay = {
        "type": "caption",
        "start": round(local_start, 3),
        "end": round(local_end, 3),
        "text": str(unit["text"]),
        "style_id": base_overlay.get("style_id") or "main_punchline_caption",
        "caption_id": caption_id,
        "caption_no": base_overlay.get("caption_no"),
        "speaker_person_id": speaker_id or base_overlay.get("speaker_person_id"),
        "metadata": metadata,
        "audio_alignment": {
            "method": "speech_unit_caption_split",
            "source_audio_media_id": "group_wide",
            "source_window_sec": [round(float(unit["start"]), 3), round(float(unit["end"]), 3)],
            "speech_window_sec": [round(float(unit["start"]), 3), round(float(unit["end"]), 3)],
            "diagnostics": {
                "root_caption_id": root,
                "unit_index": part_index,
                "previous_caption_text": base_overlay.get("text"),
                "previous_source_window_sec": metadata.get("caption_source_full_window_sec"),
            },
        },
    }
    return overlay


def add_unit_overlays(
    events: list[dict[str, Any]],
    root: str,
    base_overlay: dict[str, Any],
    units: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    added: list[dict[str, Any]] = []
    for part_index, unit in enumerate(units, start=1):
        start = float(unit["start"])
        end = float(unit["end"])
        for event in events:
            ref = event_ref_window(event)
            if not ref or event.get("section") != "main":
                continue
            overlap_start = max(start, ref[0])
            overlap_end = min(end, ref[1])
            if overlap_end - overlap_start < 0.18:
                continue
            local_start = overlap_start - ref[0]
            local_end = min(event_duration(event), overlap_end - ref[0])
            overlay = make_overlay(
                root=root,
                part_index=part_index,
                base_overlay=base_overlay,
                event=event,
                unit=unit,
                local_start=local_start,
                local_end=local_end,
                continuation=overlap_start > start + 0.001,
            )
            event.setdefault("overlays", []).append(overlay)
            event.setdefault("main_caption_plan_items", []).append(
                {
                    "caption_id": overlay["caption_id"],
                    "caption_no": overlay.get("caption_no"),
                    "source": "speech_unit_caption_split",
                    "source_start_sec": round(start, 3),
                    "source_end_sec": round(end, 3),
                    "caption_start_sec": round(start, 3),
                    "caption_end_sec": round(end, 3),
                    "display_text": unit["text"],
                    "speaker_person_id": overlay.get("speaker_person_id"),
                    "speaker_name": overlay["metadata"].get("speaker_name"),
                    "caption_source_of_truth": "edit_plan.json",
                    "speech_unit_split_root_id": root,
                }
            )
            added.append(
                {
                    "event_id": event.get("event_id"),
                    "caption_id": overlay["caption_id"],
                    "timeline_start": round(float(event.get("timeline_start") or 0.0) + local_start, 3),
                    "timeline_end": round(float(event.get("timeline_start") or 0.0) + local_end, 3),
                    "source_window_sec": [round(start, 3), round(end, 3)],
                    "text": unit["text"],
                    "speaker_person_id": overlay.get("speaker_person_id"),
                }
            )
    return added


def main() -> None:
    plan = read_json(EDIT_PLAN)
    segments = sorted(read_json(VOICE_ATTRIBUTION).get("segments", []), key=lambda item: float(item.get("start") or 0.0))
    events = [event for event in plan.get("timeline", []) if isinstance(event, dict)]

    root_base: dict[str, dict[str, Any]] = {}
    root_window: dict[str, tuple[float, float]] = {}
    root_events: dict[str, set[str]] = defaultdict(set)
    candidates: set[str] = set()

    for event in events:
        if event.get("section") != "main":
            continue
        for index, overlay in enumerate(event.get("overlays", []) or []):
            if not isinstance(overlay, dict) or overlay.get("type") != "caption":
                continue
            root = root_id_for_overlay(event, overlay, index)
            source_window = source_window_for_overlay(overlay)
            if not source_window:
                continue
            root_events[root].add(str(event.get("event_id")))
            if root not in root_base or not (overlay.get("metadata") or {}).get("caption_cut_continuation"):
                root_base[root] = overlay
                root_window[root] = source_window
            if is_candidate(root, overlay, source_window):
                candidates.add(root)

    repairs: list[dict[str, Any]] = []
    for root in sorted(candidates):
        base = root_base[root]
        window = root_window[root]
        old_text = str(base.get("text") or "")
        units = auto_split_units(root, old_text, window, segments)
        if not units:
            continue
        if len(units) == 1 and clean_space(units[0]["text"]) == clean_space(old_text) and abs(float(units[0]["start"]) - window[0]) < 0.05:
            continue

        # Remove the old root overlays and stale plan items before inserting
        # speech-unit replacements.
        removed_overlays = 0
        removed_plan_items = 0
        for event in events:
            overlays = event.get("overlays") if isinstance(event.get("overlays"), list) else []
            kept_overlays = []
            for index, overlay in enumerate(overlays):
                if isinstance(overlay, dict) and overlay.get("type") == "caption" and root_id_for_overlay(event, overlay, index) == root:
                    removed_overlays += 1
                    continue
                kept_overlays.append(overlay)
            event["overlays"] = kept_overlays

            items = event.get("main_caption_plan_items") if isinstance(event.get("main_caption_plan_items"), list) else []
            kept_items = []
            for item in items:
                item_root = normalize_id(item.get("caption_id")) if isinstance(item, dict) else ""
                if item_root == root:
                    removed_plan_items += 1
                    continue
                kept_items.append(item)
            event["main_caption_plan_items"] = kept_items

        added = add_unit_overlays(events, root, base, units)
        repairs.append(
            {
                "root_caption_id": root,
                "old_text": old_text,
                "old_source_window_sec": [round(window[0], 3), round(window[1], 3)],
                "old_source_duration_sec": round(window[1] - window[0], 3),
                "old_events": sorted(root_events[root]),
                "removed_overlay_count": removed_overlays,
                "removed_plan_item_count": removed_plan_items,
                "new_unit_count": len(units),
                "new_units": [
                    {
                        "source_window_sec": [round(float(unit["start"]), 3), round(float(unit["end"]), 3)],
                        "duration_sec": round(float(unit["end"]) - float(unit["start"]), 3),
                        "text": unit["text"],
                        "speaker_person_id": unit.get("speaker_person_id"),
                        "reason": unit.get("reason"),
                    }
                    for unit in units
                ],
                "added_overlays": added,
            }
        )

    for event in events:
        overlays = event.get("overlays")
        if isinstance(overlays, list):
            overlays.sort(key=lambda overlay: (float(overlay.get("start") or 0.0), str(overlay.get("type") or ""), str(overlay.get("caption_id") or "")) if isinstance(overlay, dict) else (0.0, "", ""))
        items = event.get("main_caption_plan_items")
        if isinstance(items, list):
            items.sort(key=lambda item: (float(item.get("caption_start_sec") or item.get("source_start_sec") or 0.0), str(item.get("caption_id") or "")) if isinstance(item, dict) else (0.0, ""))

    now = datetime.now(JST).isoformat(timespec="seconds")
    plan["updated_at"] = now
    plan.setdefault("revision_notes", []).append(
        {
            "updated_at": now,
            "script": Path(__file__).name,
            "summary": f"Split {len(repairs)} long summarized caption roots into speech-matched caption units.",
            "report": str(REPORT_JSON),
        }
    )
    write_json(EDIT_PLAN, plan)

    report = {
        "schema_version": "long_caption_speech_unit_split_report.v1",
        "project_id": plan.get("project_id", "layer-x-domain-expert"),
        "generated_at": now,
        "root_cause": (
            "Several punchline captions used a short editorial summary while their source/audio window still covered a longer multi-clause speech block. "
            "The continuation logic then kept that same short caption visible across the whole block, so the on-screen text stopped matching the spoken content."
        ),
        "policy": {
            "single_source_of_truth": "edit_plan.json",
            "long_caption_detection": {
                "long_source_sec": LONG_SOURCE_SEC,
                "long_display_sec": LONG_DISPLAY_SEC,
                "short_text_chars": SHORT_TEXT_CHARS,
            },
            "repair": "Replace each long summary overlay with 1-3 speech-unit overlays whose source windows and text match the actual voice-attributed transcript segment.",
        },
        "repair_count": len(repairs),
        "repairs": repairs,
    }
    write_json(REPORT_JSON, report)

    lines = [
        "# Long Caption Speech Unit Split Report",
        "",
        f"- Generated: {now}",
        f"- Repair count: {len(repairs)}",
        "",
        "## Root Cause",
        "",
        report["root_cause"],
        "",
        "## Repairs",
        "",
    ]
    for repair in repairs:
        lines.append(f"### {repair['root_caption_id']}")
        lines.append("")
        lines.append(f"- Old: `{repair['old_text']}`")
        lines.append(f"- Old source: `{repair['old_source_window_sec'][0]:.3f} - {repair['old_source_window_sec'][1]:.3f}` ({repair['old_source_duration_sec']:.3f}s)")
        lines.append(f"- Removed overlays: {repair['removed_overlay_count']}")
        lines.append("- New units:")
        for unit in repair["new_units"]:
            text = str(unit["text"]).replace("\n", "<br>")
            lines.append(
                f"  - `{unit['source_window_sec'][0]:.3f} - {unit['source_window_sec'][1]:.3f}` "
                f"({unit['duration_sec']:.3f}s): {text}"
            )
        lines.append("")
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8", newline="\n")

    print(json.dumps({"repair_count": len(repairs), "report_json": str(REPORT_JSON), "report_md": str(REPORT_MD)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
