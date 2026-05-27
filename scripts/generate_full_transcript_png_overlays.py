from __future__ import annotations

import json
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
SPEAKER_ROLES = OUTPUT_REPORTS / "full_transcript_speaker_roles.json"
MAX_IMAGE_WIDTH = 1760
CAPTION_PAD_X = 18
CAPTION_STROKE = 0
FONT_SIZE = 80
MAX_CAPTION_LINES = 3
MIN_LINE_CHARS = 6
APP_CONFIG = load_app_config()
SRT = selected_subtitle_path(APP_CONFIG, extensions=(".srt",))
MANUAL_LINE_BREAKS = {
    "定義で言うと強いプロダクトというかプロダクトが中心にあって": (
        "定義で言うと強いプロダクトというか",
        "プロダクトが中心にあって",
    ),
    "それをある程度セミオゴーだとかセミカスタマイズの形で": (
        "それをある程度セミオゴーだとか",
        "セミカスタマイズの形で",
    ),
    "そこで一定なスケールメリットが出るということが大事だと思いますね": (
        "そこで一定なスケールメリットが",
        "出るということが大事だと思いますね",
    ),
    "PDMというフリーに関する論争みたいな感じで続いて質問しておこうかなと思ったんですけど": (
        "PDMというフリーに関する論争みたいな感じで",
        "続いて質問しておこうかなと思ったんですけど",
    ),
    "ある程度先ほどの話の中からもお伺いできているところがあるので": (
        "ある程度先ほどの話の中からも",
        "お伺いできているところがあるので",
    ),
    "個別のものに踏み込むつもりはないかと思うんですが": (
        "個別のものに踏み込むつもりは",
        "ないかと思うんですが",
    ),
    "どうしてああいう論争になっちゃうのかなというところに関してはどう感じますか": (
        "どうしてああいう論争になっちゃうのかな",
        "というところに関してはどう感じますか",
    ),
}


@dataclass(frozen=True)
class Caption:
    start: str
    end: str
    lines: tuple[str, ...]
    font_size: int


def parse_srt_timestamp(timestamp: str) -> str:
    hours, minutes, seconds = timestamp.replace(",", ".").split(":")
    return f"{int(hours)}:{minutes}:{seconds}"


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
        start_raw, end_raw = [part.strip() for part in rows[1].split("-->")]
        body = normalize_caption_text(" ".join(rows[2:]))
        lines, font_size = layout_caption_text(body)
        captions.append(Caption(parse_srt_timestamp(start_raw), parse_srt_timestamp(end_raw), tuple(lines), font_size))
    return captions


def text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=CAPTION_STROKE)
    return tracked_text_width(draw, text, font, CAPTION_STROKE) if len(text) > 1 else bbox[2] - bbox[0]


def split_caption_text(text: str, font_size: int, max_text_width: int) -> list[str]:
    font = ImageFont.truetype(str(FONT_PATH), font_size, index=1)
    probe = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    draw = ImageDraw.Draw(probe)
    if text_width(draw, text, font) <= max_text_width:
        return [text]
    manual_lines = MANUAL_LINE_BREAKS.get(text)
    if manual_lines and all(text_width(draw, line, font) <= max_text_width for line in manual_lines):
        return list(manual_lines)
    return wrap_japanese_text(text, draw, font, max_text_width, MAX_CAPTION_LINES)


def split_japanese_line_naturally(line: str, draw: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont) -> tuple[str, str]:
    break_chars = "、。，．・／/）)]」』"
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
        if line[index - 1] in break_chars:
            score -= 800
        if any(left.endswith(particle) for particle in particles):
            score -= 500
        if line[index:index + 1] in "、。，．・":
            score -= 500
        if score < best_score:
            best_score = score
            best_index = index
    return line[:best_index].rstrip(), line[best_index:].lstrip()


def wrap_japanese_text(
    text: str,
    draw: ImageDraw.ImageDraw,
    font: ImageFont.FreeTypeFont,
    max_text_width: int,
    max_lines: int,
) -> list[str]:
    break_chars = "、。，．・／/）)]」』"
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
                if text[index - 1] in break_chars:
                    score -= 900
                if any(text[:index].endswith(particle) for particle in particles):
                    score -= 550
                if text[index:index + 1] in "、。，．・":
                    score -= 550
                if score < best_score:
                    best_score = score
                    best_index = index
            if best_index is None:
                best_index = center
            split_points.append(best_index)
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


def layout_caption_text(text: str) -> tuple[list[str], int]:
    max_text_width = MAX_IMAGE_WIDTH - CAPTION_PAD_X * 2
    font_size = int_value(APP_CONFIG, "style", "subtitleSize", default=FONT_SIZE)
    font = ImageFont.truetype(str(FONT_PATH), font_size, index=1)
    probe = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    draw = ImageDraw.Draw(probe)
    lines = split_caption_text(text, font_size, max_text_width)
    return lines[:MAX_CAPTION_LINES], font_size


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
        role = roles.get(str(index), "onscreen")
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
