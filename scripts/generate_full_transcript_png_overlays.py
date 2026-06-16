from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from video_edit_core.paths import (
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

from video_edit_core.graphics.subtitle_png import BLACK, FONT_PATH, LIGHT_PURPLE, TRACKING, render_simple_caption, tracked_text_width
from video_edit_core.app_config import hex_rgba, int_value, load_app_config, nested, opacity_alpha, selected_subtitle_path


WORK = WORKSPACE_ROOT
OUT_DIR = OUTPUT_OVERLAYS / "full_transcript_png_overlays"
LAYOUT_PATH = OUT_DIR / "layout.json"
PNG_MANIFEST_PATH = OUT_DIR / "manifest.json"
PNG_CACHE_PATH = OUT_DIR / "png_cache.json"
MAX_IMAGE_WIDTH = 1760
CAPTION_PAD_X = 18
CAPTION_STROKE = 0
FONT_SIZE = 80
MAX_CAPTION_LINES = 2
MAX_CAPTION_CHUNKS = 8
MIN_LINE_CHARS = 6
LINE_END_PREFERRED_CHARS = "、。，．・／/）)]」』"
LINE_START_PROHIBITED_CHARS = "、。，．,.！？!?：；;・）)]｝}」』】》〉"
LINE_BREAK_TRAILING_PUNCTUATION_RE = re.compile(r"[、。,.，．]+$")
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
    "って",
    "そういう",
    "どうか",
    "なっていく",
    "しなきゃ",
    "だろう",
    "あるかな",
    "ものって",
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
    "お金",
    "によって",
)
MAX_ACCEPTABLE_SPLIT_PENALTY = 220_000
LINE_WIDTH_BALANCE_WEIGHT = 400_000
LINE_CHAR_BALANCE_WEIGHT = 1_300_000
APP_CONFIG = load_app_config()
SPEAKER_ROLES = Path(
    str(nested(APP_CONFIG, "subtitleSpeakers", "outputPath", default=str(OUTPUT_REPORTS / "full_transcript_speaker_roles.json")))
)
SRT = selected_subtitle_path(APP_CONFIG, extensions=(".srt",))
MANUAL_LINE_BREAKS: dict[str, tuple[str, ...]] = {
    "逆に言うと、FDEはエンジニアじゃないと務まらないような仕事でもありますよね": (
        "逆に言うと、FDEはエンジニアじゃないと",
        "務まらないような仕事でもありますよね",
    ),
    "人を採用するほど生き残っていけないというところがもちろんあるので": (
        "人を採用するほど生き残っていけない",
        "というところがもちろんあるので",
    ),
    "本来的には仕事の中身、何が求められて何が評価されるかみたいな話は": (
        "本来的には仕事の中身、何が求められて",
        "何が評価されるかみたいな話は",
    ),
    "事業責任者が、自分たちがどういう手段でお金を稼いで": (
        "事業責任者が、自分たちが",
        "どういう手段でお金を稼いで",
    ),
    "どういうふうに投資をしたら、積み上がるものが作れるのかというところを": (
        "どういうふうに投資をしたら、",
        "積み上がるものが作れるのかというところを",
    ),
    "そうですね、FDEの何でもできるマルチプレイヤーみたいな側面が": (
        "そうですね、FDEの何でもできる",
        "マルチプレイヤーみたいな側面が",
    ),
    "それは方法というか手段でしかなかったはずなんですよ": (
        "それは方法というか手段でしか",
        "なかったはずなんですよ",
    ),
    "この時代になってくると、やったらいいじゃんと思うわけです": (
        "この時代になってくると、",
        "やったらいいじゃんと思うわけです",
    ),
    "プロダクトマネージャーになっている仕事です、ということを考えると": (
        "プロダクトマネージャーになっている仕事です、",
        "ということを考えると",
    ),
    "私は、例えば営業だからエンジニアリングのことは全くわからないから任せた": (
        "私は、例えば営業だからエンジニアリングのことは",
        "全くわからないから任せた",
    ),
    "どの企業であっても、アメリカで流行っているからといって": (
        "どの企業であっても、",
        "アメリカで流行っているからといって",
    ),
    "FDEは、そのまま転用できるのかどうかっていう話で言うと": (
        "FDEはそのまま転用できるのか",
        "どうかっていう話で言うと",
    ),
    "それはそれ、これはこれ、って感じで残っていくような気がしますね": (
        "それはそれ、これはこれ、",
        "って感じで残っていくような気がしますね",
    ),
    "これなんでなのかなっていうところも純粋に疑問があって": (
        "これなんでなのかなっていうところも",
        "純粋に疑問があって",
    ),
    "でも、なんかそういうのすらあるんじゃないかなって思うんですけど": (
        "でも、なんかそういうのすら",
        "あるんじゃないかって思うんですけど",
    ),
    "たまたま、すごくジョブディスクリプションとかが分かりやすい": (
        "たまたま、すごくジョブディスクリプション",
        "とかが分かりやすい",
    ),
    "人の価値っていうのを何に見出しているのかっていうところの違いだと思っていて": (
        "人の価値っていうのを何に見出しているのか",
        "っていうところの違いだと思っていて",
    ),
    "具体的な名前出すとすると、セールスフォースとかは近いのかもしれないですよね": (
        "具体的な名前出すとすると、セールスフォースとかは",
        "近いのかもしれないですよね",
    ),
    "AIによって、みんな多分一人でできることが増えていくんだろうな": (
        "AIによって、みんな多分一人で",
        "できることが増えていくんだろうな",
    ),
    "FDEに向いているプロダクトという話と、両方あると思います": (
        "FDEに向いているプロダクトという",
        "話と、両方あると思います",
    ),
    "それ、なんかコード書くとかというよりは思考体系っていうか": (
        "それ、なんかコード書くとか",
        "というよりは思考体系っていうか",
    ),
    "一定セミオーダー的にカスタマイズしてやっていくというところを": (
        "一定セミオーダー的にカスタマイズして",
        "やっていくというところを",
    ),
    "確かにちょっと参照させていただこうかなと思っていたんですけど": (
        "確かにちょっと参照させて",
        "いただこうかなと思っていたんですけど",
    ),
    "越境した方がいいんだろうなみたいなところとか考えたりするわけですよね": (
        "越境した方がいいんだろうなみたいな",
        "ところとか考えたりするわけですよね",
    ),
    "なので、当たり前に考えなきゃいけない時代が来たんだなと": (
        "なので、当たり前に考えなきゃいけない",
        "時代が来たんだなと",
    ),
    "FDEって言うても「エンジニア」ってついてるじゃないですか": (
        "FDEって言うても「エンジニア」って",
        "ついてるじゃないですか",
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


def rgba_css(color: tuple[int, int, int, int]) -> str:
    red, green, blue, alpha = color
    return f"rgba({red}, {green}, {blue}, {alpha / 255:.4f})"


def measure_simple_caption(
    lines: tuple[str, ...],
    font_size: int,
    *,
    stroke: int = CAPTION_STROKE,
    pad_x: int = CAPTION_PAD_X,
    pad_y: int = 10,
    line_gap: int = 6,
) -> tuple[int, int]:
    font = ImageFont.truetype(str(FONT_PATH), font_size, index=1)
    probe = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    draw = ImageDraw.Draw(probe)
    widths: list[int] = []
    heights: list[int] = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font, stroke_width=stroke)
        widths.append(tracked_text_width(draw, line, font, stroke) if len(line) > 1 else bbox[2] - bbox[0])
        heights.append(bbox[3] - bbox[1])
    max_width = max(widths, default=0)
    total_height = sum(height + pad_y * 2 for height in heights) + line_gap * max(0, len(lines) - 1)
    return max_width + pad_x * 2, total_height + pad_y * 2


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
    if text[index - 1] in "っッ":
        score += 2_000_000
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
    target_chars = n / line_count
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
                width_balance_penalty = ((width - target_width) / max_text_width) ** 2 * LINE_WIDTH_BALANCE_WEIGHT
                char_balance_penalty = ((len(segment) - target_chars) / max(1, n)) ** 2 * LINE_CHAR_BALANCE_WEIGHT
                balance_penalty = width_balance_penalty + char_balance_penalty
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


def strip_line_break_trailing_punctuation(lines: list[str]) -> list[str]:
    if len(lines) <= 1:
        return lines
    return [
        LINE_BREAK_TRAILING_PUNCTUATION_RE.sub("", line.rstrip()) if index < len(lines) - 1 else line
        for index, line in enumerate(lines)
    ]


def layout_caption_chunks(text: str) -> tuple[list[tuple[str, ...]], int]:
    max_text_width = MAX_IMAGE_WIDTH - CAPTION_PAD_X * 2
    font_size = int_value(APP_CONFIG, "style", "subtitleSize", default=FONT_SIZE)
    font = ImageFont.truetype(str(FONT_PATH), font_size, index=1)
    probe = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    draw = ImageDraw.Draw(probe)
    lines = wrapped_caption_lines(text, draw, font, max_text_width)
    lines = strip_line_break_trailing_punctuation(lines)
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
    for pattern in ("full_*.png", "manifest.json", "layout.json", "png_cache.json"):
        for path in OUT_DIR.glob(pattern):
            if path.is_file():
                path.unlink()


def stable_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def png_fingerprint(item: dict[str, object], box_fill: tuple[int, ...]) -> str:
    payload = {
        "schema": "full-transcript-png-cache/v1",
        "item": {
            "lines": item.get("lines"),
            "font_size": item.get("font_size"),
            "speaker_role": item.get("speaker_role"),
        },
        "style": {
            "stroke": CAPTION_STROKE,
            "pad_x": CAPTION_PAD_X,
            "pad_y": 10,
            "line_gap": 6,
            "tracking": TRACKING,
            "font_path": str(FONT_PATH),
            "box_fill": list(box_fill),
        },
    }
    return hashlib.sha256(stable_json(payload).encode("utf-8")).hexdigest()


def load_png_cache() -> dict[str, dict[str, object]]:
    try:
        payload = json.loads(PNG_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    entries = payload.get("entries") if isinstance(payload, dict) else None
    return entries if isinstance(entries, dict) else {}


def cleanup_stale_pngs(used_files: set[Path]) -> None:
    for path in OUT_DIR.glob("full_*.png"):
        if path not in used_files and path.is_file():
            path.unlink()


def parse_args() -> argparse.Namespace:
    default_format = str(nested(APP_CONFIG, "render", "subtitleOverlayFormat", default="html") or "html").strip().lower()
    if default_format in {"layout", "json", "html-css"}:
        default_format = "html"
    if default_format not in {"html", "png", "both"}:
        default_format = "html"
    parser = argparse.ArgumentParser(description="Generate full transcript subtitle layout data and optional PNG overlays.")
    parser.add_argument(
        "--format",
        choices=["html", "png", "both"],
        default=default_format,
        help="html writes layout.json only; png/both also rasterize per-caption PNG assets.",
    )
    parser.add_argument("--fresh", action="store_true", help="Delete existing subtitle PNG cache before rendering.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.fresh:
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
    write_png = args.format in {"png", "both"}
    layout_items = []
    png_manifest = []
    cache_entries = load_png_cache() if write_png else {}
    next_cache_entries: dict[str, dict[str, object]] = {}
    used_pngs: set[Path] = set()
    cache_reused = 0
    cache_rendered = 0
    for index, caption in enumerate(captions, start=1):
        role = roles.get(str(caption.source_index), "onscreen")
        box_fill = interviewer_fill if role == "interviewer" else onscreen_fill
        width, height = measure_simple_caption(caption.lines, caption.font_size)
        item = {
            **asdict(caption),
            "speaker_role": role,
            "width": width,
            "height": height,
        }
        layout_items.append(item)
        if write_png:
            filename = f"full_{index:03d}.png"
            path = OUT_DIR / filename
            fingerprint = png_fingerprint(item, box_fill)
            cached = cache_entries.get(filename)
            if (
                isinstance(cached, dict)
                and cached.get("fingerprint") == fingerprint
                and path.exists()
                and path.stat().st_size > 0
            ):
                image_width = int(cached.get("width") or item["width"])
                image_height = int(cached.get("height") or item["height"])
                cache_reused += 1
            else:
                image = render_simple_caption(
                    caption.lines,
                    caption.font_size,
                    stroke=CAPTION_STROKE,
                    pad_x=CAPTION_PAD_X,
                    pad_y=10,
                    line_gap=6,
                    box_fill=box_fill,
                )
                image.save(path)
                image_width = image.width
                image_height = image.height
                cache_rendered += 1
            used_pngs.add(path)
            next_cache_entries[filename] = {"fingerprint": fingerprint, "width": image_width, "height": image_height}
            png_manifest.append({**item, "file": str(path.relative_to(WORK)), "width": image_width, "height": image_height})
    layout = {
        "schemaVersion": "video-edit-subtitle-layout/v1",
        "kind": "full-subtitle",
        "renderMode": "html",
        "source": {
            "subtitlePath": str(SRT),
            "speakerRolesPath": str(SPEAKER_ROLES),
            "speakerRolesExist": SPEAKER_ROLES.exists(),
        },
        "style": {
            "fontFamily": "Yu Gothic UI",
            "fontPath": str(FONT_PATH),
            "fontSize": int_value(APP_CONFIG, "style", "subtitleSize", default=FONT_SIZE),
            "fontWeight": 700,
            "tracking": TRACKING,
            "maxImageWidth": MAX_IMAGE_WIDTH,
            "padX": CAPTION_PAD_X,
            "padY": 10,
            "lineGap": 6,
            "boxRadius": 10,
            "bottomMargin": 16,
            "textColor": "rgba(255, 255, 255, 1)",
            "onscreenBoxColor": rgba_css(onscreen_fill),
            "interviewerBoxColor": rgba_css(interviewer_fill),
        },
        "items": layout_items,
    }
    LAYOUT_PATH.write_text(json.dumps(layout, ensure_ascii=False, indent=2), encoding="utf-8")
    if write_png:
        cleanup_stale_pngs(used_pngs)
        PNG_MANIFEST_PATH.write_text(json.dumps(png_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        PNG_CACHE_PATH.write_text(
            json.dumps({"schemaVersion": "full-transcript-png-cache/v1", "entries": next_cache_entries}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    else:
        PNG_MANIFEST_PATH.unlink(missing_ok=True)
    print(
        json.dumps(
            {
                "layout": str(LAYOUT_PATH),
                "pngManifest": str(PNG_MANIFEST_PATH) if write_png else "",
                "format": args.format,
                "captionCount": len(layout_items),
                "pngCount": len(png_manifest),
                "pngCache": {"reused": cache_reused, "rendered": cache_rendered, "path": str(PNG_CACHE_PATH) if write_png else ""},
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
