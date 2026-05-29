from __future__ import annotations

import argparse
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


FILLER_PREFIXES = (
    "あー",
    "えー",
    "えっと",
    "あの",
    "そのー",
    "まあ",
    "なんか",
    "別になんていうかな",
    "なんていうかな",
)
PUNCTUATION = set(" \t\r\n、。，．,.！？!?：；;・/／「」『』（）()[]【】{}｛｝<>＜＞\"“”'’`〜~…-")


@dataclass
class Caption:
    index: str
    start: float
    end: float
    text: str
    source_indexes: list[str] = field(default_factory=list)
    role: str = "onscreen"
    old_start: float = 0.0
    old_end: float = 0.0


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value)).lower()
    return "".join(ch for ch in text if ch not in PUNCTUATION and not ch.isspace())


def strip_leading_fillers(text: str) -> str:
    value = normalize_text(text)
    changed = True
    while changed:
        changed = False
        for filler in FILLER_PREFIXES:
            marker = normalize_text(filler)
            if marker and value.startswith(marker) and len(value) - len(marker) >= 3:
                value = value[len(marker) :]
                changed = True
                break
    return value


def seconds(timestamp: str) -> float:
    hours, minutes, seconds_text = timestamp.replace(",", ".").split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds_text)


def timestamp(value: float) -> str:
    millis = round(max(0.0, value) * 1000)
    hours, remainder = divmod(millis, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d},{millis:03d}"


def parse_srt(path: Path, roles: dict[str, str]) -> list[Caption]:
    blocks = re.split(r"\n\s*\n", path.read_text(encoding="utf-8-sig").strip())
    captions: list[Caption] = []
    for block in blocks:
        rows = [row.strip() for row in block.splitlines() if row.strip()]
        if len(rows) < 3 or "-->" not in rows[1]:
            continue
        start_raw, end_raw = [part.strip() for part in rows[1].split("-->", 1)]
        index = rows[0]
        caption = Caption(
            index=index,
            start=seconds(start_raw),
            end=seconds(end_raw),
            text="".join(rows[2:]).strip(),
            source_indexes=[index],
            role=roles.get(str(index), "onscreen"),
            old_start=seconds(start_raw),
            old_end=seconds(end_raw),
        )
        captions.append(caption)
    return captions


def load_roles(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    roles = payload.get("roles", {}) if isinstance(payload, dict) else {}
    return {str(key): str(value) for key, value in roles.items()} if isinstance(roles, dict) else {}


def word_timeline(path: Path) -> tuple[str, list[float]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    chars: list[str] = []
    char_times: list[float] = []
    for segment in payload.get("segments", []):
        if not isinstance(segment, dict):
            continue
        for word in segment.get("words") or []:
            token = normalize_text(word.get("word", ""))
            if not token:
                continue
            start = float(word.get("start", 0.0))
            for char in token:
                chars.append(char)
                char_times.append(start)
    return "".join(chars), char_times


def char_index_at_or_after(char_times: list[float], time_value: float) -> int:
    for index, char_time in enumerate(char_times):
        if char_time >= time_value:
            return index
    return len(char_times)


def first_content_match(
    caption: Caption,
    global_text: str,
    char_times: list[float],
    *,
    search_after: float,
) -> dict[str, Any] | None:
    variants: list[tuple[str, str]] = []
    exact = normalize_text(caption.text)
    if exact:
        variants.append(("exact", exact))
    stripped = strip_leading_fillers(caption.text)
    if stripped and stripped != exact:
        variants.append(("leading_filler_stripped", stripped))
    if not variants:
        return None

    search_from = char_index_at_or_after(char_times, max(0.0, caption.start - 0.35))
    search_to = char_index_at_or_after(char_times, caption.end + search_after)
    segment_text = global_text[search_from:search_to]
    best: dict[str, Any] | None = None
    for kind, value in variants:
        max_prefix = min(16, len(value))
        for prefix_length in range(max_prefix, 2, -1):
            prefix = value[:prefix_length]
            position = segment_text.find(prefix)
            if position < 0:
                continue
            absolute = search_from + position
            if absolute >= len(char_times):
                continue
            start = char_times[absolute]
            if start >= caption.end - 0.10:
                continue
            candidate = {
                "kind": kind,
                "prefix": prefix,
                "matched_start": start,
                "delay": start - caption.start,
            }
            if best is None or candidate["matched_start"] < best["matched_start"]:
                best = candidate
            break
    return best


def retime_starts(
    captions: list[Caption],
    global_text: str,
    char_times: list[float],
    *,
    lead_in: float,
    strong_delay: float,
    search_after: float,
) -> list[dict[str, Any]]:
    adjustments: list[dict[str, Any]] = []
    for caption in captions:
        match = first_content_match(caption, global_text, char_times, search_after=search_after)
        if not match or float(match["delay"]) < strong_delay:
            continue
        old_start = caption.start
        caption.start = max(caption.start, float(match["matched_start"]) - lead_in)
        if caption.start - old_start < 0.05:
            caption.start = old_start
            continue
        adjustments.append(
            {
                "index": caption.index,
                "text": caption.text,
                "oldStart": round(old_start, 3),
                "newStart": round(caption.start, 3),
                "matchedContentStart": round(float(match["matched_start"]), 3),
                "delay": round(caption.start - old_start, 3),
                "matchKind": match["kind"],
                "prefix": match["prefix"],
            }
        )
    return adjustments


def enforce_readable_durations(
    captions: list[Caption],
    *,
    min_duration: float,
    tail_hold: float,
    min_gap: float,
) -> None:
    for index, caption in enumerate(captions):
        next_start = captions[index + 1].start if index + 1 < len(captions) else None
        desired_end = max(caption.end, caption.start + min_duration)
        desired_end = max(desired_end, caption.end + tail_hold)
        if next_start is not None:
            desired_end = min(desired_end, max(caption.start + 0.25, next_start - min_gap))
        caption.end = max(caption.start + 0.25, desired_end)


def should_merge(left: Caption, right: Caption, *, max_chars: int, max_duration: float, max_gap: float) -> bool:
    if left.role != right.role:
        return False
    gap = right.start - left.end
    if gap > max_gap:
        return False
    merged_text = normalize_text(left.text + right.text)
    if len(merged_text) > max_chars:
        return False
    if right.end - left.start > max_duration:
        return False
    left_short = left.end - left.start < 1.65 or len(normalize_text(left.text)) <= 18
    right_short = right.end - right.start < 1.65 or len(normalize_text(right.text)) <= 18
    return left_short or right_short or gap <= 0.12


def merge_readable_captions(
    captions: list[Caption],
    *,
    max_chars: int,
    max_duration: float,
    max_gap: float,
) -> tuple[list[Caption], list[dict[str, Any]]]:
    merged: list[Caption] = []
    report: list[dict[str, Any]] = []
    for caption in captions:
        if merged and should_merge(merged[-1], caption, max_chars=max_chars, max_duration=max_duration, max_gap=max_gap):
            previous = merged[-1]
            before = {
                "left": previous.source_indexes[:],
                "right": caption.source_indexes[:],
                "oldText": previous.text,
                "rightText": caption.text,
            }
            previous.end = max(previous.end, caption.end)
            previous.text = previous.text + caption.text
            previous.source_indexes.extend(caption.source_indexes)
            before.update(
                {
                    "mergedIndexes": previous.source_indexes[:],
                    "newStart": round(previous.start, 3),
                    "newEnd": round(previous.end, 3),
                    "newText": previous.text,
                    "role": previous.role,
                }
            )
            report.append(before)
        else:
            merged.append(caption)
    return merged, report


def write_srt(path: Path, captions: list[Caption]) -> None:
    lines: list[str] = []
    for output_index, caption in enumerate(captions, start=1):
        lines.append(str(output_index))
        lines.append(f"{timestamp(caption.start)} --> {timestamp(caption.end)}")
        lines.append(caption.text)
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def output_caption_report(captions: list[Caption]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    rows: list[dict[str, Any]] = []
    roles: dict[str, str] = {}
    for output_index, caption in enumerate(captions, start=1):
        key = str(output_index)
        roles[key] = caption.role
        rows.append(
            {
                "index": output_index,
                "sourceIndexes": caption.source_indexes,
                "role": caption.role,
                "start": round(caption.start, 3),
                "end": round(caption.end, 3),
                "text": caption.text,
            }
        )
    return rows, roles


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Retiming SRT starts to spoken content while preserving readable subtitle pacing.")
    parser.add_argument("--srt", type=Path, required=True)
    parser.add_argument("--word-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--roles-json", type=Path)
    parser.add_argument("--lead-in", type=float, default=0.35)
    parser.add_argument("--strong-delay", type=float, default=0.70)
    parser.add_argument("--search-after", type=float, default=8.0)
    parser.add_argument("--min-duration", type=float, default=1.35)
    parser.add_argument("--tail-hold", type=float, default=0.25)
    parser.add_argument("--min-gap", type=float, default=0.04)
    parser.add_argument("--merge-max-chars", type=int, default=52)
    parser.add_argument("--merge-max-duration", type=float, default=8.5)
    parser.add_argument("--merge-max-gap", type=float, default=0.35)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    roles = load_roles(args.roles_json)
    captions = parse_srt(args.srt, roles)
    global_text, char_times = word_timeline(args.word_json)
    timing_adjustments = retime_starts(
        captions,
        global_text,
        char_times,
        lead_in=args.lead_in,
        strong_delay=args.strong_delay,
        search_after=args.search_after,
    )
    enforce_readable_durations(captions, min_duration=args.min_duration, tail_hold=args.tail_hold, min_gap=args.min_gap)
    captions, merges = merge_readable_captions(
        captions,
        max_chars=args.merge_max_chars,
        max_duration=args.merge_max_duration,
        max_gap=args.merge_max_gap,
    )
    enforce_readable_durations(captions, min_duration=args.min_duration, tail_hold=args.tail_hold, min_gap=args.min_gap)
    output_captions, output_roles = output_caption_report(captions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    write_srt(args.output, captions)
    report = {
        "sourceSrt": str(args.srt),
        "wordTimestamps": str(args.word_json),
        "rolesJson": str(args.roles_json) if args.roles_json else "",
        "outputSrt": str(args.output),
        "settings": {
            "leadIn": args.lead_in,
            "strongDelay": args.strong_delay,
            "minDuration": args.min_duration,
            "tailHold": args.tail_hold,
            "mergeMaxChars": args.merge_max_chars,
            "mergeMaxDuration": args.merge_max_duration,
            "mergeMaxGap": args.merge_max_gap,
        },
        "timingAdjustmentCount": len(timing_adjustments),
        "mergeCount": len(merges),
        "outputCaptionCount": len(captions),
        "outputRoles": output_roles,
        "outputCaptions": output_captions,
        "timingAdjustments": timing_adjustments,
        "merges": merges,
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
