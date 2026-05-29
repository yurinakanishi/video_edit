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
LINE_START_AVOIDED_PREFIXES = (
    "いう",
    "って",
    "という",
    "まらない",
    "け入れ",
    "られて",
    "よる",
    "させて",
    "いただ",
    "ただこう",
    "こと",
    "ところ",
    "もの",
    "ので",
    "けど",
    "とか",
    "たり",
    "だけ",
    "から",
    "まで",
    "より",
    "です",
    "ます",
    "ました",
    "して",
    "した",
    "する",
    "いる",
    "ある",
    "れる",
    "られる",
    "は",
    "が",
    "を",
    "に",
    "で",
    "と",
    "も",
    "へ",
    "の",
    "か",
)
LINE_END_AVOIDED_SUFFIXES = ("と", "っ", "ま", "も", "で", "や", "し", "す")
LINE_END_PREFERRED_PHRASES = (
    "、",
    "。",
    "けど",
    "ので",
    "から",
    "として",
    "について",
    "に関して",
    "という",
    "っていう",
    "みたいな",
    "ですよね",
    "ですよ",
    "ですね",
    "ますね",
    "思います",
)
LINE_START_PREFERRED_PREFIXES = (
    "ただ",
    "でも",
    "なので",
    "例えば",
    "つまり",
    "そうですね",
    "確かに",
    "じゃあ",
)
UNBREAKABLE_PHRASES = (
    "FDE",
    "PDM",
    "SaaS",
    "SMB",
    "SIer",
    "ClaudeCode",
    "ビジネスモデル",
    "プロダクト",
    "プロダクトマネージャー",
    "エンジニアリング",
    "エンジニア",
    "エコシステム",
    "デリバリー",
    "エンタープライズ",
    "セミオーダー",
    "セミカスタマイズ",
    "カスタマイズ",
    "パッケージソフト",
    "ソリューション営業",
    "セールスフォース",
    "マーケティング",
    "ジョブディスクリプション",
    "ステークホルダー",
    "ポジショントーク",
    "マルチプレイヤー",
    "ファーストキャリア",
    "プロフィール",
    "リバースエンジニアリング",
    "コンパイルエラー",
    "スキルセット",
    "務まらない",
    "受け入れられる",
    "限られている",
    "必要とされている",
    "参照させて",
    "参照させていただこう",
    "させていただこう",
    "いただこう",
    "レバレッジ",
    "ユーザー",
    "デザイナー",
    "ヒアリング",
    "ビルダー",
    "フロント",
    "コミュニケーション",
    "できる",
    "できない",
    "できた",
    "できて",
    "難しい",
    "働き方",
    "考え方",
    "作り方",
    "あり方",
    "変わらない",
    "近い",
    "思う",
    "考えて",
    "言うても",
    "いろいろ",
    "できました",
    "きました",
    "きます",
    "使って",
    "作って",
    "持って",
    "変わって",
    "揃って",
    "たまって",
    "している",
    "していく",
    "してきた",
    "してもらう",
    "してもらえる",
    "したり",
    "だったり",
    "あったり",
    "なったり",
    "されて",
    "される",
    "られる",
    "考える",
    "思います",
    "思って",
    "あります",
    "います",
    "という",
    "っていう",
    "というの",
    "ということ",
    "というところ",
    "という形",
    "という話",
    "じゃない",
    "じゃん",
    "そういう",
    "なっていく",
    "しなきゃ",
    "だろう",
    "いいよね",
    "みたいな",
    "かなと",
    "かもしれない",
    "ところ",
    "もの",
    "こと",
    "ため",
    "また",
    "まだ",
    "もう",
    "やっぱり",
    "すごく",
    "めちゃくちゃ",
    "ちょっと",
    "なんか",
    "必要",
    "条件",
    "領域",
    "設計",
    "反応",
    "人員",
    "商習慣",
    "御用聞き",
)
MAX_ACCEPTABLE_SPLIT_PENALTY = 80_000
APP_CONFIG = load_app_config()
SPEAKER_ROLES = Path(
    str(nested(APP_CONFIG, "subtitleSpeakers", "outputPath", default=str(OUTPUT_REPORTS / "full_transcript_speaker_roles.json")))
)
SRT = selected_subtitle_path(APP_CONFIG, extensions=(".srt",))
MANUAL_LINE_BREAKS: dict[str, tuple[str, ...]] = {
    "逆に言うとFDEはエンジニアじゃないと務まらないような仕事でもありますよね": (
        "逆に言うとFDEはエンジニアじゃないと",
        "務まらないような仕事でもありますよね",
    ),
}


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


def script_class(char: str) -> str:
    code = ord(char)
    if ("A" <= char <= "Z") or ("a" <= char <= "z") or ("0" <= char <= "9"):
        return "latin"
    if 0x30A0 <= code <= 0x30FF:
        return "katakana"
    if 0x3040 <= code <= 0x309F:
        return "hiragana"
    if 0x4E00 <= code <= 0x9FFF:
        return "kanji"
    return "other"


def merged_unbreakable_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for pattern in (r"[A-Za-z0-9+#._-]+", r"[ァ-ヶー]+"):
        for match in re.finditer(pattern, text):
            if match.end() - match.start() > 1:
                spans.append((match.start(), match.end()))
    for phrase in UNBREAKABLE_PHRASES:
        start = text.find(phrase)
        while start >= 0:
            spans.append((start, start + len(phrase)))
            start = text.find(phrase, start + 1)
    if not spans:
        return []
    spans.sort()
    merged: list[tuple[int, int]] = []
    for start, end in spans:
        if not merged or start >= merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged


def inside_unbreakable_span(index: int, spans: list[tuple[int, int]]) -> bool:
    return any(start < index < end for start, end in spans)


def boundary_penalty(text: str, index: int, spans: list[tuple[int, int]]) -> int:
    if index <= 0 or index >= len(text):
        return 0
    if text[index] in LINE_START_PROHIBITED_CHARS:
        return 10**9
    left = text[:index]
    right = text[index:]
    score = 0
    if inside_unbreakable_span(index, spans):
        score += 9_000_000
    previous_class = script_class(text[index - 1])
    next_class = script_class(text[index])
    particle_boundary = any(left.endswith(particle) for particle in ("は", "が", "を", "に", "で", "と", "も", "へ", "から", "まで", "より"))
    if previous_class == "kanji" and next_class == "hiragana":
        # Avoid splitting inside Japanese okurigana words, e.g. 務|まらない or 受|け入れ.
        # Particle starts are still awkward as line starts, but okurigana splits are worse.
        score += 260_000 if text[index] not in "はがをにでともへのか" else 120_000
    if previous_class == next_class and not particle_boundary:
        if previous_class in {"latin", "katakana"}:
            score += 7_000_000
        elif previous_class == "kanji":
            score += 120_000
        elif previous_class == "hiragana":
            score += 90_000
    if any(right.startswith(prefix) for prefix in LINE_START_AVOIDED_PREFIXES):
        score += 180_000
    if any(left.endswith(suffix) for suffix in LINE_END_AVOIDED_SUFFIXES):
        score += 70_000
    if text[index - 1] in LINE_END_PREFERRED_CHARS:
        score -= 8_000
    if any(left.endswith(phrase) for phrase in LINE_END_PREFERRED_PHRASES):
        score -= 5_000
    if any(right.startswith(prefix) for prefix in LINE_START_PREFERRED_PREFIXES):
        score -= 3_000
    if particle_boundary:
        score -= 1_500
    return score


def choose_natural_lines(
    text: str,
    draw: ImageDraw.ImageDraw,
    font: ImageFont.FreeTypeFont,
    max_text_width: int,
    line_count: int,
) -> list[str] | None:
    if line_count <= 1:
        return [text] if text_width(draw, text, font) <= max_text_width else None
    n = len(text)
    if n < line_count:
        return None
    spans = merged_unbreakable_spans(text)
    points = list(range(n + 1))
    char_widths: list[int] = []
    for char in text:
        bbox = draw.textbbox((0, 0), char, font=font, stroke_width=CAPTION_STROKE)
        char_widths.append(bbox[2] - bbox[0])
    prefix_widths = [0]
    for width in char_widths:
        prefix_widths.append(prefix_widths[-1] + width)

    def segment_width(start: int, end: int) -> int:
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if end <= start:
            return 0
        return prefix_widths[end] - prefix_widths[start] + TRACKING * max(0, end - start - 1)

    total_width = text_width(draw, text, font)
    target_width = min(max_text_width, max(1, total_width / line_count))
    dp: list[dict[int, tuple[float, int | None]]] = [{0: (0.0, None)}]
    for line_index in range(1, line_count + 1):
        current: dict[int, tuple[float, int | None]] = {}
        previous = dp[-1]
        min_remaining_chars = line_count - line_index
        for end in points[1:]:
            if n - end < min_remaining_chars:
                continue
            best: tuple[float, int | None] | None = None
            for start, (prev_cost, _) in previous.items():
                if start >= end:
                    continue
                segment = text[start:end].strip()
                if not segment:
                    continue
                width = segment_width(start, end)
                if width > max_text_width:
                    continue
                length_penalty = 0
                if n >= MIN_LINE_CHARS * line_count and len(segment) < MIN_LINE_CHARS:
                    length_penalty = (MIN_LINE_CHARS - len(segment)) * 8_000
                balance_penalty = ((width - target_width) / max_text_width) ** 2 * 4_000
                end_penalty = 0 if end == n else boundary_penalty(text, end, spans)
                start_penalty = 0 if start == 0 else boundary_penalty(text, start, spans) * 0.15
                cost = prev_cost + balance_penalty + length_penalty + end_penalty + start_penalty
                if best is None or cost < best[0]:
                    best = (cost, start)
            if best is not None:
                current[end] = best
        dp.append(current)
    if n not in dp[-1]:
        return None
    lines: list[str] = []
    end = n
    for line_index in range(line_count, 0, -1):
        _, start = dp[line_index][end]
        if start is None:
            return None
        lines.append(text[start:end].strip())
        end = start
    lines.reverse()
    return lines if all(lines) else None


def max_split_penalty(text: str, lines: list[str]) -> int:
    if len(lines) <= 1:
        return 0
    spans = merged_unbreakable_spans(text)
    cursor = 0
    max_penalty = 0
    for line in lines[:-1]:
        cursor += len(line)
        max_penalty = max(max_penalty, boundary_penalty(text, cursor, spans))
    return max_penalty


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
    natural = choose_natural_lines(line, draw, font, text_width(draw, line, font), 2)
    if natural and len(natural) == 2:
        return natural[0], natural[1]
    spans = merged_unbreakable_spans(line)
    best_index = max(1, min(len(line) - 1, len(line) // 2))
    best_score = 10**9
    for index in range(1, len(line)):
        left = line[:index].rstrip()
        right = line[index:].lstrip()
        if not left or not right:
            continue
        score = abs(text_width(draw, left, font) - text_width(draw, right, font)) + boundary_penalty(line, index, spans)
        if score < best_score:
            best_score = score
            best_index = adjust_split_index_for_kinsoku(line, index)
    return line[:best_index].rstrip(), line[best_index:].lstrip()


def wrap_japanese_text(
    text: str,
    draw: ImageDraw.ImageDraw,
    font: ImageFont.FreeTypeFont,
    max_text_width: int,
    max_lines: int,
) -> list[str]:
    for split_count in range(2, max_lines + 1):
        lines = choose_natural_lines(text, draw, font, max_text_width, split_count)
        if lines and all(text_width(draw, line, font) <= max_text_width for line in lines):
            if split_count < max_lines and max_split_penalty(text, lines) > MAX_ACCEPTABLE_SPLIT_PENALTY:
                continue
            return lines
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
