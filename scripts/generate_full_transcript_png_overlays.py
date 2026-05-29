from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from project_paths import (
    CONFIG,
    OUTPUT_DIAGNOSTICS,
    OUTPUT_OVERLAYS,
    OUTPUT_REPORTS,
    OUTPUT_TRANSCRIPTS,
    OUTPUT_VIDEOS,
    ROOT as WORKSPACE_ROOT,
    SCRIPTS,
    SOURCE_AUDIO,
    SOURCE_IMAGES,
    SOURCE_SUBTITLES,
    SOURCE_VIDEO,
    multicam_source_root,
    resolve_project_path,
)

from PIL import Image, ImageDraw, ImageFont

from subtitle_png_style import BLACK, FONT_PATH, LIGHT_PURPLE, TRACKING, render_simple_caption, tracked_text_width
from video_edit_app_config import hex_rgba, int_value, load_app_config, nested, opacity_alpha, selected_subtitle_path


WORK = WORKSPACE_ROOT
OUT_DIR = OUTPUT_OVERLAYS / "full_transcript_png_overlays"
MAX_IMAGE_WIDTH = 1760
CAPTION_PAD_X = 18
CAPTION_STROKE = 0
FONT_SIZE = 80
MAX_CAPTION_LINES = 2
MAX_CAPTION_CHUNKS = 8
MIN_LINE_CHARS = 6
LINE_END_PREFERRED_CHARS = "、。，．・／/）)]」』"
LINE_START_PROHIBITED_CHARS = "、。，．,.！？!?：；;・）)]｝}」』】》〉"
APP_CONFIG = load_app_config()
SPEAKER_ROLES = Path(
    str(nested(APP_CONFIG, "subtitleSpeakers", "outputPath", default=str(OUTPUT_REPORTS / "full_transcript_speaker_roles.json")))
)
SRT = selected_subtitle_path(APP_CONFIG, extensions=(".srt",))
MANUAL_LINE_BREAKS: dict[str, tuple[str, ...]] = {}


@dataclass(frozen=True)
class Caption:
    source_index: int
    chunk_index: int
    chunk_count: int
    start: str
    end: str
    lines: tuple[str, ...]
    font_size: int


def parse_srt_seconds(timestamp: str) -> float:
    hours, minutes, seconds = timestamp.replace(",", ".").split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def format_manifest_timestamp(seconds: float) -> str:
    millis = round(max(0.0, seconds) * 1000)
    hours, remainder = divmod(millis, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, millis = divmod(remainder, 1000)
    return f"{hours}:{minutes:02d}:{whole_seconds:02d}.{millis:03d}"


def parse_srt_timestamp(timestamp: str) -> str:
    return format_manifest_timestamp(parse_srt_seconds(timestamp))


def normalize_caption_text(text: str) -> str:
    return re.sub(r"[ \t]+", "", text.strip())


def parse_srt(path: Path) -> list[Caption]:
    text = path.read_text(encoding="utf-8-sig")
    blocks = re.split(r"\n\s*\n", text.strip())
    captions: list[Caption] = []
    for block in blocks:
        rows = [row.strip() for row in block.splitlines() if row.strip()]
        if len(rows) < 3 or "-->" not in rows[1]:
            continue
        try:
            source_index = int(rows[0])
        except ValueError:
            source_index = len(captions) + 1
        start_raw, end_raw = [part.strip() for part in rows[1].split("-->")]
        body = normalize_caption_text(" ".join(rows[2:]))
        captions.extend(layout_timed_caption_chunks(source_index, start_raw, end_raw, body))
    return captions


def text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=CAPTION_STROKE)
    return tracked_text_width(draw, text, font, CAPTION_STROKE) if len(text) > 1 else bbox[2] - bbox[0]


def split_caption_text(
    text: str,
    font_size: int,
    max_text_width: int,
    max_lines: int = MAX_CAPTION_LINES,
) -> list[str]:
    font = ImageFont.truetype(str(FONT_PATH), font_size, index=1)
    probe = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    draw = ImageDraw.Draw(probe)
    if text_width(draw, text, font) <= max_text_width:
        return [text]
    manual_lines = MANUAL_LINE_BREAKS.get(text)
    if (
        manual_lines
        and len(manual_lines) <= max_lines
        and all(text_width(draw, line, font) <= max_text_width for line in manual_lines)
    ):
        return list(manual_lines)
    return wrap_japanese_text(text, draw, font, max_text_width, max_lines)


def adjust_split_index_for_kinsoku(text: str, index: int, *, min_index: int = 1, max_index: int | None = None) -> int:
    if len(text) < 2:
        return 0
    if max_index is None:
        max_index = len(text) - 1
    index = max(min_index, min(index, max_index))
    adjusted = index
    while adjusted <= max_index and text[adjusted] in LINE_START_PROHIBITED_CHARS:
        adjusted += 1
    if adjusted <= max_index:
        return adjusted
    fallback = index - 1
    while fallback >= min_index and text[fallback] in LINE_START_PROHIBITED_CHARS:
        fallback -= 1
    if fallback >= min_index:
        return fallback
    return index


def normalize_split_points_for_kinsoku(text: str, split_points: list[int]) -> list[int]:
    normalized: list[int] = []
    total_points = len(split_points)
    for point_index, raw_index in enumerate(split_points):
        min_index = normalized[-1] + 1 if normalized else 1
        max_index = len(text) - (total_points - point_index)
        if min_index > max_index:
            return []
        normalized.append(
            adjust_split_index_for_kinsoku(
                text,
                raw_index,
                min_index=min_index,
                max_index=max_index,
            )
        )
    return normalized


def split_japanese_line_naturally(line: str, draw: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont) -> tuple[str, str]:
    particles = ("は", "が", "を", "に", "で", "と", "も", "へ", "から", "まで", "より", "って", "という", "ので", "けど")
    best_index = max(1, min(len(line) - 1, len(line) // 2))
    best_score = 10**9
    for index in range(1, len(line)):
        left = line[:index].rstrip()
        right = line[index:].lstrip()
        if not left or not right:
            continue
        left_width = text_width(draw, left, font)
        right_width = text_width(draw, right, font)
        score = abs(left_width - right_width)
        if line[index - 1] in LINE_END_PREFERRED_CHARS:
            score -= 800
        if any(left.endswith(particle) for particle in particles):
            score -= 500
        if line[index:index + 1] in LINE_START_PROHIBITED_CHARS:
            score += 1200
        adjusted_index = adjust_split_index_for_kinsoku(line, index)
        if score < best_score:
            best_score = score
            best_index = adjusted_index
    return line[:best_index].rstrip(), line[best_index:].lstrip()


def wrap_japanese_text(
    text: str,
    draw: ImageDraw.ImageDraw,
    font: ImageFont.FreeTypeFont,
    max_text_width: int,
    max_lines: int,
) -> list[str]:
    particles = ("は", "が", "を", "に", "で", "と", "も", "へ", "から", "まで", "より", "って", "という", "ので", "けど")
    for split_count in range(2, max_lines + 1):
        candidates: list[list[str]] = []
        target = len(text) / split_count
        split_points: list[int] = []
        for segment_index in range(1, split_count):
            center = round(target * segment_index)
            best_index = None
            best_score = 10**9
            for index in range(max(1, center - 12), min(len(text), center + 13)):
                left_fragment = text[:index].split("\n")[-1].strip()
                right_fragment = text[index:].split("\n")[0].strip()
                if len(left_fragment) < MIN_LINE_CHARS or len(right_fragment) < MIN_LINE_CHARS:
                    continue
                score = abs(index - center) * 120
                if text[index - 1] in LINE_END_PREFERRED_CHARS:
                    score -= 900
                if any(text[:index].endswith(particle) for particle in particles):
                    score -= 550
                if text[index:index + 1] in LINE_START_PROHIBITED_CHARS:
                    score += 1400
                if score < best_score:
                    best_score = score
                    best_index = index
            if best_index is None:
                best_index = center
            split_points.append(best_index)
        split_points = normalize_split_points_for_kinsoku(text, split_points)
        if len(split_points) != split_count - 1:
            continue
        points = [0, *split_points, len(text)]
        lines = [text[points[i]:points[i + 1]].strip() for i in range(len(points) - 1)]
        if all(len(line) >= MIN_LINE_CHARS for line in lines) and all(text_width(draw, line, font) <= max_text_width for line in lines):
            candidates.append(lines)
        if candidates:
            return min(
                candidates,
                key=lambda lines: max(text_width(draw, line, font) for line in lines)
                - min(text_width(draw, line, font) for line in lines),
            )
    left, right = split_japanese_line_naturally(text, draw, font)
    return [left, right]


def wrapped_caption_lines(
    text: str,
    draw: ImageDraw.ImageDraw,
    font: ImageFont.FreeTypeFont,
    max_text_width: int,
) -> list[str]:
    manual_lines = MANUAL_LINE_BREAKS.get(text)
    if manual_lines and all(text_width(draw, line, font) <= max_text_width for line in manual_lines):
        return list(manual_lines)
    if text_width(draw, text, font) <= max_text_width:
        return [text]

    estimated_lines = max(MAX_CAPTION_LINES, math.ceil(text_width(draw, text, font) / max_text_width * 1.35) + 1)
    max_total_lines = max(MAX_CAPTION_LINES, min(MAX_CAPTION_LINES * MAX_CAPTION_CHUNKS, estimated_lines))
    lines = wrap_japanese_text(text, draw, font, max_text_width, max_total_lines)

    while len(lines) < MAX_CAPTION_LINES * MAX_CAPTION_CHUNKS:
        wide_indexes = [
            index
            for index, line in enumerate(lines)
            if text_width(draw, line, font) > max_text_width and len(line) > 1
        ]
        if not wide_indexes:
            break
        widest_index = max(wide_indexes, key=lambda index: text_width(draw, lines[index], font))
        left, right = split_japanese_line_naturally(lines[widest_index], draw, font)
        if not left or not right or (left, right) == (lines[widest_index], ""):
            break
        lines[widest_index:widest_index + 1] = [left, right]
    return lines


def group_caption_lines(lines: list[str]) -> list[tuple[str, ...]]:
    return [tuple(lines[index:index + MAX_CAPTION_LINES]) for index in range(0, len(lines), MAX_CAPTION_LINES)]


def layout_caption_chunks(text: str) -> tuple[list[tuple[str, ...]], int]:
    max_text_width = MAX_IMAGE_WIDTH - CAPTION_PAD_X * 2
    font_size = int_value(APP_CONFIG, "style", "subtitleSize", default=FONT_SIZE)
    font = ImageFont.truetype(str(FONT_PATH), font_size, index=1)
    probe = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    draw = ImageDraw.Draw(probe)
    lines = wrapped_caption_lines(text, draw, font, max_text_width)
    return group_caption_lines(lines), font_size


def layout_caption_text(text: str) -> tuple[list[str], int]:
    chunks, font_size = layout_caption_chunks(text)
    return list(chunks[0]) if chunks else [], font_size


def layout_timed_caption_chunks(source_index: int, start_raw: str, end_raw: str, text: str) -> list[Caption]:
    chunks, font_size = layout_caption_chunks(text)
    start_seconds = parse_srt_seconds(start_raw)
    end_seconds = parse_srt_seconds(end_raw)
    if len(chunks) <= 1 or end_seconds <= start_seconds:
        return [
            Caption(
                source_index=source_index,
                chunk_index=1,
                chunk_count=1,
                start=parse_srt_timestamp(start_raw),
                end=parse_srt_timestamp(end_raw),
                lines=chunks[0] if chunks else (text,),
                font_size=font_size,
            )
        ]

    weights = [max(1, sum(len(line) for line in lines)) for lines in chunks]
    total_weight = sum(weights)
    duration = end_seconds - start_seconds
    captions: list[Caption] = []
    cursor = start_seconds
    consumed_weight = 0
    for chunk_index, lines in enumerate(chunks, start=1):
        consumed_weight += weights[chunk_index - 1]
        if chunk_index == len(chunks):
            chunk_end = end_seconds
        else:
            chunk_end = start_seconds + duration * consumed_weight / total_weight
        captions.append(
            Caption(
                source_index=source_index,
                chunk_index=chunk_index,
                chunk_count=len(chunks),
                start=format_manifest_timestamp(cursor),
                end=format_manifest_timestamp(chunk_end),
                lines=lines,
                font_size=font_size,
            )
        )
        cursor = chunk_end
    return captions



def reset_output_dir() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for pattern in ("full_*.png", "manifest.json"):
        for path in OUT_DIR.glob(pattern):
            if path.is_file():
                path.unlink()


def main() -> None:
    reset_output_dir()
    if SRT is None:
        raise SystemExit("No subtitle file found. Run transcription or select a subtitle file before generating full overlays.")
    captions = parse_srt(SRT)
    roles = {}
    if SPEAKER_ROLES.exists():
        roles = json.loads(SPEAKER_ROLES.read_text(encoding="utf-8")).get("roles", {})
    alpha = opacity_alpha(nested(APP_CONFIG, "style", "boxOpacity"), 185)
    onscreen_fill = hex_rgba(nested(APP_CONFIG, "style", "highlightColor"), alpha=alpha, default=LIGHT_PURPLE)
    interviewer_fill = (*BLACK[:3], alpha)
    manifest = []
    for index, caption in enumerate(captions, start=1):
        role = roles.get(str(caption.source_index), "onscreen")
        box_fill = interviewer_fill if role == "interviewer" else onscreen_fill
        image = render_simple_caption(
            caption.lines,
            caption.font_size,
            stroke=CAPTION_STROKE,
            pad_x=CAPTION_PAD_X,
            pad_y=10,
            line_gap=6,
            box_fill=box_fill,
        )
        filename = f"full_{index:03d}.png"
        image.save(OUT_DIR / filename)
        manifest.append(
            {
                **asdict(caption),
                "speaker_role": role,
                "file": str((OUT_DIR / filename).relative_to(WORK)),
                "width": image.width,
                "height": image.height,
            }
        )
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
