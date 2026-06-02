from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from video_edit_core.paths import OUTPUT_REPORTS, OUTPUT_TRANSCRIPTS
from video_edit_core.graphics.subtitle_png import FONT_PATH, TRACKING, tracked_text_width
from video_edit_core.app_config import load_app_config, nested, selected_subtitle_path


APP_CONFIG = load_app_config()
VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
MAX_LINE_WIDTH = 1760
MAX_LINES_PER_DIALOGUE = 2
LINE_START_PROHIBITED = "、。，．,.！？!?：；;・）)]｝}」』】》〉"
LINE_END_PREFERRED = "、。，．・／/）)]」』"


@dataclass(frozen=True)
class Caption:
    index: int
    start: float
    end: float
    text: str


def parse_timestamp(value: str) -> float:
    text = value.strip().replace(",", ".")
    parts = text.split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    if len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    return float(text)


def parse_srt(path: Path) -> list[Caption]:
    raw = path.read_text(encoding="utf-8-sig").strip()
    if not raw:
        return []
    captions: list[Caption] = []
    for block in re.split(r"\n\s*\n", raw):
        rows = [row.strip() for row in block.splitlines() if row.strip()]
        if len(rows) < 3 or "-->" not in rows[1]:
            continue
        try:
            index = int(rows[0])
            start_raw, end_raw = [part.strip() for part in rows[1].split("-->", 1)]
            start = parse_timestamp(start_raw)
            end = parse_timestamp(end_raw)
        except ValueError:
            continue
        captions.append(Caption(index=index, start=start, end=end, text=normalize_text("".join(rows[2:]))))
    return captions


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", text).strip()


def load_roles(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    roles = data.get("roles", {}) if isinstance(data, dict) else {}
    return {str(key): str(value) for key, value in roles.items()} if isinstance(roles, dict) else {}


def external_offset_seconds() -> float:
    sync_path = OUTPUT_REPORTS / "app_sync_offsets.json"
    if not sync_path.exists():
        return 0.0
    try:
        data = json.loads(sync_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return 0.0
    offsets = data.get("offsets", {}) if isinstance(data, dict) else {}
    external = offsets.get("external", {}) if isinstance(offsets, dict) else {}
    try:
        return float(external.get("offsetSeconds", 0.0))
    except (TypeError, ValueError):
        return 0.0


def format_ass_time(seconds: float) -> str:
    cs = max(0, round(seconds * 100))
    hours, rem = divmod(cs, 360000)
    minutes, rem = divmod(rem, 6000)
    secs, cs = divmod(rem, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def ass_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def font_size() -> int:
    try:
        return int(nested(APP_CONFIG, "style", "subtitleSize", default=80) or 80)
    except (TypeError, ValueError):
        return 80


def text_width(draw: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont, text: str) -> int:
    if not text:
        return 0
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=0)
    if len(text) == 1:
        return bbox[2] - bbox[0]
    return tracked_text_width(draw, text, font, 0)


def break_score(text: str, index: int) -> float:
    score = 0.0
    if text[index - 1 : index] in LINE_END_PREFERRED:
        score -= 800.0
    if text[index : index + 1] in LINE_START_PROHIBITED:
        score += 1200.0
    if text[index - 1 : index] in {"の", "に", "で", "が", "を", "は", "と", "も", "へ"}:
        score -= 80.0
    return score


def best_lines_for_count(text: str, count: int, draw: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont, max_width: int) -> list[str] | None:
    n = len(text)
    if count <= 0 or n <= 0:
        return None
    if count == 1:
        return [text] if text_width(draw, font, text) <= max_width else None

    @lru_cache(maxsize=None)
    def width(start: int, end: int) -> int:
        return text_width(draw, font, text[start:end])

    @lru_cache(maxsize=None)
    def solve(start: int, remaining: int) -> tuple[float, tuple[int, ...]] | None:
        if remaining == 1:
            if start < n and width(start, n) <= max_width:
                target = n / count
                return ((n - start - target) ** 2, (n,))
            return None
        min_end = start + 1
        max_end = n - remaining + 1
        best: tuple[float, tuple[int, ...]] | None = None
        target = n / count
        for end in range(min_end, max_end + 1):
            if text[end : end + 1] in LINE_START_PROHIBITED:
                continue
            if width(start, end) > max_width:
                break
            rest = solve(end, remaining - 1)
            if rest is None:
                continue
            balance = (end - start - target) ** 2
            score = balance + rest[0] + break_score(text, end)
            if best is None or score < best[0]:
                best = (score, (end, *rest[1]))
        return best

    solved = solve(0, count)
    if solved is None:
        return None
    ends = solved[1]
    lines: list[str] = []
    start = 0
    for end in ends:
        lines.append(text[start:end])
        start = end
    return lines if all(line for line in lines) else None


def wrap_lines(text: str, draw: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    if not text:
        return []
    min_needed = max(1, math.ceil(text_width(draw, font, text) / max_width))
    max_lines = max(1, min(24, min_needed + 8))
    for count in range(min_needed, max_lines + 1):
        lines = best_lines_for_count(text, count, draw, font, max_width)
        if lines is not None:
            return lines

    lines: list[str] = []
    remaining = text
    while remaining:
        end = 1
        while end <= len(remaining) and text_width(draw, font, remaining[:end]) <= max_width:
            end += 1
        end = max(1, end - 1)
        while end > 1 and remaining[end : end + 1] in LINE_START_PROHIBITED:
            end -= 1
        lines.append(remaining[:end])
        remaining = remaining[end:]
    return lines


def dialogue_chunks(caption: Caption, role: str, draw: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont, max_width: int) -> list[dict[str, Any]]:
    lines = wrap_lines(caption.text, draw, font, max_width)
    if not lines:
        return []
    grouped = [lines[index : index + MAX_LINES_PER_DIALOGUE] for index in range(0, len(lines), MAX_LINES_PER_DIALOGUE)]
    weights = [max(1, sum(len(line) for line in group)) for group in grouped]
    total = sum(weights)
    duration = max(0.1, caption.end - caption.start)
    chunks: list[dict[str, Any]] = []
    elapsed = 0.0
    for group, weight in zip(grouped, weights):
        chunk_duration = duration * weight / total
        start = caption.start + elapsed
        end = caption.end if group is grouped[-1] else min(caption.end, start + chunk_duration)
        chunks.append({"index": caption.index, "start": start, "end": end, "role": role, "lines": group})
        elapsed += chunk_duration
    return chunks


def ass_header(size: int) -> str:
    return f"""[Script Info]
ScriptType: v4.00+
WrapStyle: 2
ScaledBorderAndShadow: yes
PlayResX: {VIDEO_WIDTH}
PlayResY: {VIDEO_HEIGHT}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Onscreen,Yu Gothic,{size},&H00FFFFFF,&H000000FF,&H46E048AE,&H00000000,-1,0,0,0,100,100,{TRACKING},0,3,10,0,2,44,44,24,1
Style: Interviewer,Yu Gothic,{size},&H00FFFFFF,&H000000FF,&H50000000,&H00000000,-1,0,0,0,100,100,{TRACKING},0,3,10,0,2,44,44,24,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate role-aware full transcript ASS subtitles.")
    parser.add_argument("--srt", type=Path, default=selected_subtitle_path(APP_CONFIG, extensions=(".srt",)))
    parser.add_argument("--roles", type=Path, default=Path(str(nested(APP_CONFIG, "subtitleSpeakers", "outputPath", default=str(OUTPUT_REPORTS / "full_transcript_speaker_roles.json")))))
    parser.add_argument("--output", type=Path, default=Path(str(nested(APP_CONFIG, "render", "subtitleAssPath", default=str(OUTPUT_TRANSCRIPTS / "manifest_sources" / "primary_shifted_role_aware.ass")))))
    parser.add_argument("--offset", type=float, default=external_offset_seconds())
    args = parser.parse_args()
    if args.srt is None or not args.srt.exists():
        raise SystemExit("No SRT transcript found. Run transcription first.")

    captions = parse_srt(args.srt)
    roles = load_roles(args.roles)
    size = font_size()
    probe = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    draw = ImageDraw.Draw(probe)
    font = ImageFont.truetype(str(FONT_PATH), size, index=1)

    events: list[str] = []
    chunk_count = 0
    for caption in captions:
        role = roles.get(str(caption.index), "onscreen")
        style = "Interviewer" if role == "interviewer" else "Onscreen"
        shifted = Caption(caption.index, caption.start - args.offset, caption.end - args.offset, caption.text)
        if shifted.end <= 0:
            continue
        shifted = Caption(shifted.index, max(0.0, shifted.start), shifted.end, shifted.text)
        for chunk in dialogue_chunks(shifted, role, draw, font, MAX_LINE_WIDTH):
            text = r"\N".join(ass_escape(line) for line in chunk["lines"])
            events.append(
                f"Dialogue: 0,{format_ass_time(float(chunk['start']))},{format_ass_time(float(chunk['end']))},{style},,0,0,0,,{text}"
            )
            chunk_count += 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(ass_header(size) + "\n".join(events) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "captionCount": len(captions), "dialogueCount": chunk_count, "offsetSeconds": args.offset}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
