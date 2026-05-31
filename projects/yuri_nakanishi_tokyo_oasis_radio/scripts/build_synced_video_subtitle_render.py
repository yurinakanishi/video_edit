from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


PROJECT_ID = "yuri_nakanishi_tokyo_oasis_radio"
DEFAULT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class SyncChunk:
    target_start: float
    target_end: float
    source_start: float
    source_end: float
    reason: str

    @property
    def target_duration(self) -> float:
        return self.target_end - self.target_start

    @property
    def source_duration(self) -> float:
        return self.source_end - self.source_start

    @property
    def setpts_ratio(self) -> float:
        return self.target_duration / self.source_duration


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run(command: list[str], *, cwd: Path) -> None:
    print(json.dumps({"command": command}, ensure_ascii=False), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def seconds_to_srt(seconds: float) -> str:
    millis = max(0, int(round(seconds * 1000)))
    hours, rem = divmod(millis, 3600000)
    minutes, rem = divmod(rem, 60000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", str(text)).strip()
    jp = r"\u3040-\u30ff\u3400-\u9fff"
    text = re.sub(fr"(?<=[{jp}])\s+(?=[{jp}])", "", text)
    return text


def apply_corrections(text: str, replacements: list[dict[str, str]]) -> str:
    corrected = str(text)
    for item in replacements:
        source = str(item.get("from", ""))
        target = str(item.get("to", ""))
        if source:
            corrected = corrected.replace(source, target)
    return corrected


def normalize_int_key_map(data: Any) -> dict[int, str]:
    if not isinstance(data, dict):
        return {}
    result: dict[int, str] = {}
    for key, value in data.items():
        try:
            result[int(key)] = str(value)
        except (TypeError, ValueError):
            continue
    return result


def normalize_role_override_map(data: Any) -> dict[int, str]:
    allowed = {"interviewer", "interviewee", "unknown"}
    result: dict[int, str] = {}
    for key, value in normalize_int_key_map(data).items():
        if value in allowed:
            result[key] = value
    return result


LINE_START_PROHIBITED = "、。，．！？!?・ーぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮんン）)]」』"
LINE_END_PROHIBITED = "っゃゅょァィゥェォッャュョ（([「『"
LINE_END_PREFERRED = "、。，．！？!?・はがをにでとへもやねし"
MIN_NATURAL_LINE_CHARS = 6
MAX_EXTRA_WRAP_LINES = 2
PROTECTED_PHRASES = (
    "Kiitos",
    "中西裕理",
    "中西さん",
    "長谷川美穂",
    "東京オアシス",
    "花岡洋行",
    "白旗眞生",
    "白旗さん",
    "認定NPO法人",
    "青少年の居場所",
    "あしなが育英会",
    "Bump of Chicken",
    "バンプオブチキン",
    "BUMP OF CHICKEN",
    "ラフメイカー",
    "ラフメーカー",
    "ラフ・メイカー",
    "システムエンジニア",
    "ホームページ",
    "ボランティアさん",
    "ゲストをお迎え",
    "中にはね、",
    "そうですね",
    "厳しいですね",
    "足りない",
    "かもしれない",
    "するする",
    "する、する",
    "スリランカの悪魔払い",
    "言われても",
    "言ってますけど",
    "もう際限なく",
    "学んでもらいたい",
    "学んでもらいたいな",
    "戸惑うんですけど",
    "という",
    "っていう",
    "そんなこと",
)
DEPENDENT_CAPTION_PREFIXES = (
    "という内容",
    "ということで",
)
LINE_START_AVOIDED_PREFIXES = (
    "ております",
    "しております",
    "ています",
    "ていく",
    "ていただ",
    "いただ",
    "おります",
    "ました",
    "ます",
    "です",
    "でしょうか",
    "ください",
    "けれども",
    "ですけれども",
    "と思います",
    "ると思います",
    "という",
    "っていう",
    "すね",
    "すけど",
    "らいたい",
    "いもの",
    "ところ",
    "もの",
    "こと",
    "ので",
    "から",
    "ため",
    "には",
    "では",
    "は",
)
LINE_END_AVOIDED_SUFFIXES = (
    "お招きし",
    "お",
    "期待し",
    "維持し",
    "継続し",
    "設",
    "認",
    "入",
    "見",
    "思",
    "言",
    "キー",
    "Ki",
    "Kiit",
    "し",
    "て",
    "と",
)


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


def protected_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for pattern in (r"[A-Za-z0-9+#._-]+", r"[ァ-ヶー]+"):
        for match in re.finditer(pattern, text):
            if match.end() - match.start() > 1:
                spans.append((match.start(), match.end()))
    for phrase in PROTECTED_PHRASES:
        start = text.find(phrase)
        while start >= 0:
            spans.append((start, start + len(phrase)))
            start = text.find(phrase, start + 1)
    spans.sort()
    merged: list[tuple[int, int]] = []
    for start, end in spans:
        if not merged or start >= merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged


def inside_protected_span(index: int, spans: list[tuple[int, int]]) -> bool:
    return any(start < index < end for start, end in spans)


def split_boundary_penalty(text: str, index: int, spans: list[tuple[int, int]]) -> float:
    if index <= 0 or index >= len(text):
        return 0.0
    left = text[:index]
    right = text[index:]
    previous = text[index - 1]
    current = text[index]
    if current in LINE_START_PROHIBITED or previous in LINE_END_PROHIBITED:
        return 10_000_000.0
    penalty = 0.0
    if inside_protected_span(index, spans):
        penalty += 8_000_000.0
    previous_class = script_class(previous)
    current_class = script_class(current)
    particle_boundary = any(left.endswith(particle) for particle in ("は", "が", "を", "に", "で", "と", "も", "へ", "から", "まで", "より"))
    if previous_class == current_class and not particle_boundary:
        if previous_class in {"latin", "katakana"}:
            penalty += 5_000_000.0
        elif previous_class == "kanji":
            penalty += 100_000.0
        elif previous_class == "hiragana":
            penalty += 60_000.0
    if previous_class == "kanji" and current_class == "hiragana" and current not in "はがをにでともへのか":
        penalty += 220_000.0
    if any(right.startswith(prefix) for prefix in LINE_START_AVOIDED_PREFIXES):
        penalty += 260_000.0
    if current in "のがをにへ":
        penalty += 180_000.0
    elif current == "で" and not right.startswith(("でも", "では")):
        penalty += 180_000.0
    elif current == "と" and not right.startswith(("とても", "という", "ところ")):
        penalty += 180_000.0
    elif current == "も" and not right.startswith(("もう", "もしくは", "もちろん", "もともと")):
        penalty += 180_000.0
    if any(left.endswith(suffix) for suffix in LINE_END_AVOIDED_SUFFIXES):
        penalty += 220_000.0
    if previous in LINE_END_PREFERRED:
        penalty -= 4_000.0
    if particle_boundary:
        penalty -= 1_200.0
    return penalty


def choose_natural_lines(text: str, max_line_chars: int) -> list[str]:
    if len(text) <= max_line_chars:
        return [text]
    n = len(text)
    min_line_count = max(2, math.ceil(n / max_line_chars))
    max_line_count = min(n, min_line_count + MAX_EXTRA_WRAP_LINES)
    spans = protected_spans(text)
    best_lines: list[str] | None = None
    best_cost = float("inf")
    for line_count in range(min_line_count, max_line_count + 1):
        target = n / line_count
        dp: list[dict[int, tuple[float, int | None]]] = [{0: (0.0, None)}]
        for line_index in range(1, line_count + 1):
            current: dict[int, tuple[float, int | None]] = {}
            min_remaining = line_count - line_index
            for end in range(1, n + 1):
                if n - end < min_remaining:
                    continue
                for start, (prev_cost, _) in dp[-1].items():
                    if start >= end:
                        continue
                    segment = text[start:end].strip()
                    if not segment or len(segment) > max_line_chars:
                        continue
                    length_cost = ((len(segment) - target) / max(1.0, max_line_chars)) ** 2 * 3_000.0
                    if len(segment) < MIN_NATURAL_LINE_CHARS and n >= MIN_NATURAL_LINE_CHARS * line_count:
                        length_cost += (MIN_NATURAL_LINE_CHARS - len(segment)) * 20_000.0
                    boundary_cost = 0.0 if end == n else split_boundary_penalty(text, end, spans)
                    cost = prev_cost + length_cost + boundary_cost
                    if end == n and len(segment) < 8 and line_count > 1:
                        cost += 120_000.0
                    existing = current.get(end)
                    if existing is None or cost < existing[0]:
                        current[end] = (cost, start)
            dp.append(current)
        if n not in dp[-1]:
            continue
        lines: list[str] = []
        end = n
        for line_index in range(line_count, 0, -1):
            _, start = dp[line_index][end]
            if start is None:
                lines = []
                break
            lines.append(text[start:end].strip())
            end = start
        if not lines:
            continue
        lines.reverse()
        total_cost = dp[-1][n][0] + (line_count - min_line_count) * 8_000.0
        if total_cost < best_cost:
            best_cost = total_cost
            best_lines = lines
    if best_lines:
        return best_lines
    return [text[index:index + max_line_chars] for index in range(0, len(text), max_line_chars)]


def make_lines(text: str, max_line_chars: int = 20, max_lines: int = 2) -> list[list[str]]:
    lines = choose_natural_lines(text, max_line_chars)
    return [lines[index:index + max_lines] for index in range(0, len(lines), max_lines)]


def font_path() -> str:
    candidates = [
        Path(r"C:\Windows\Fonts\YuGothB.ttc"),
        Path(r"C:\Windows\Fonts\YuGothM.ttc"),
        Path(r"C:\Windows\Fonts\meiryob.ttc"),
        Path(r"C:\Windows\Fonts\meiryo.ttc"),
        Path(r"C:\Windows\Fonts\msgothic.ttc"),
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    raise RuntimeError("No Japanese-capable font found under C:\\Windows\\Fonts")


def load_font(size: int) -> ImageFont.FreeTypeFont:
    path = font_path()
    try:
        return ImageFont.truetype(path, size, index=1)
    except (OSError, TypeError):
        return ImageFont.truetype(path, size)


def hex_to_rgba(hex_color: str, opacity: float = 1.0) -> tuple[int, int, int, int]:
    text = str(hex_color).strip().lstrip("#")
    if not re.fullmatch(r"[0-9A-Fa-f]{6}", text):
        text = "FFFFFF"
    alpha = round(max(0.0, min(1.0, opacity)) * 255)
    return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16), alpha)


def tracked_text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, stroke: int, tracking: int) -> int:
    width = 0
    for index, char in enumerate(text):
        bbox = draw.textbbox((0, 0), char, font=font, stroke_width=stroke)
        width += bbox[2] - bbox[0]
        if index < len(text) - 1:
            width += tracking
    return width


def draw_tracked_text(
    draw: ImageDraw.ImageDraw,
    position: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int, int],
    *,
    stroke_width: int,
    stroke_fill: tuple[int, int, int, int],
    tracking: int,
) -> None:
    x, y = position
    for index, char in enumerate(text):
        bbox = draw.textbbox((0, 0), char, font=font, stroke_width=stroke_width)
        draw.text((x - bbox[0], y), char, font=font, fill=fill, stroke_width=stroke_width, stroke_fill=stroke_fill)
        x += bbox[2] - bbox[0]
        if index < len(text) - 1:
            x += tracking


def write_title_overlay(path: Path, config: dict[str, Any]) -> Path:
    edit = config.get("radioEdit", {})
    scale = float(edit.get("titleRenderScale", 1.0))
    text = str(edit.get("titleText", "【東京オアシス】中西裕理さん出演会"))
    font = load_font(round(int(edit.get("titleFontSize", 58)) * scale))
    pad_x = round(int(edit.get("titlePaddingX", 24)) * scale)
    pad_y = round(int(edit.get("titlePaddingY", 11)) * scale)
    stripe_h = round(int(edit.get("titleStripeHeight", 10)) * scale)
    tracking = round(int(edit.get("titleTracking", 0)) * scale)
    stroke = 0
    probe = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    draw = ImageDraw.Draw(probe)
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke)
    text_w = tracked_text_width(draw, text, font, stroke, tracking) if tracking else bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    width = text_w + pad_x * 2
    height = text_h + pad_y * 2 + stripe_h
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    box = hex_to_rgba(str(edit.get("titleBoxColor", "#FFFFFF")), float(edit.get("titleBoxOpacity", 0.94)))
    accent = hex_to_rgba(str(edit.get("titleAccentColor", "#F28C28")), 1.0)
    text_color = hex_to_rgba(str(edit.get("titleTextColor", "#F28C28")), 1.0)
    draw.rectangle((0, 0, width, height), fill=box)
    draw.rectangle((0, height - stripe_h, width, height), fill=(accent[0], accent[1], accent[2], 130))
    draw.rectangle((0, height - max(2, round(3 * scale)), width, height), fill=accent)
    draw_tracked_text(
        draw,
        (pad_x - bbox[0], pad_y - bbox[1]),
        text,
        font,
        text_color,
        stroke_width=stroke,
        stroke_fill=text_color,
        tracking=tracking,
    )
    if scale != 1.0:
        image = image.resize((round(width / scale), round(height / scale)), Image.Resampling.LANCZOS)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path


def write_logo_overlay(path: Path, logo_path: Path, config: dict[str, Any]) -> Path:
    edit = config.get("radioEdit", {})
    logo_height = int(edit.get("logoHeight", 120))
    pad_x = int(edit.get("logoBoxPaddingX", 24))
    pad_y = int(edit.get("logoBoxPaddingY", 16))
    logo = Image.open(logo_path).convert("RGBA")
    logo_width = round(logo.width * logo_height / logo.height)
    logo = logo.resize((logo_width, logo_height), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (logo_width + pad_x * 2, logo_height + pad_y * 2), (255, 255, 255, 255))
    canvas.alpha_composite(logo, (pad_x, pad_y))
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path)
    return path


def render_caption_overlay(path: Path, lines: tuple[str, ...], config: dict[str, Any], *, role: str) -> tuple[int, int]:
    edit = config.get("radioEdit", {})
    font_size = int(edit.get("subtitleFontSize", 80))
    pad_x = int(edit.get("subtitleBoxPadding", 18))
    pad_y = int(edit.get("subtitlePadY", 10))
    line_gap = int(edit.get("subtitleLineGap", 6))
    radius = int(edit.get("subtitleRadius", 10))
    stroke = int(edit.get("subtitleStrokeWidth", 0))
    tracking = int(edit.get("subtitleTracking", 4))
    opacity = float(edit.get("subtitleBoxOpacity", 1.0))
    if role == "interviewer":
        box_color = str(edit.get("hasegawaSubtitleBoxColor", "#E85AA3"))
    elif role == "interviewee":
        box_color = str(edit.get("nakanishiSubtitleBoxColor", "#2F80ED"))
    else:
        box_color = str(edit.get("unknownSubtitleBoxColor", "#555555"))
    box_fill = hex_to_rgba(box_color, opacity)
    text_fill = hex_to_rgba(str(edit.get("subtitleTextColor", "#FFFFFF")), 1.0)
    font = load_font(font_size)
    probe = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    draw = ImageDraw.Draw(probe)
    metrics: list[tuple[str, tuple[int, int, int, int], int, int]] = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font, stroke_width=stroke)
        width = tracked_text_width(draw, line, font, stroke, tracking) if len(line) > 1 else bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        metrics.append((line, bbox, width, height))
    max_width = max(width for _, _, width, _ in metrics)
    total_height = sum(height + pad_y * 2 for _, _, _, height in metrics) + line_gap * max(0, len(metrics) - 1)
    image = Image.new("RGBA", (max_width + pad_x * 2, total_height + pad_y * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    y = pad_y
    for line, bbox, width, height in metrics:
        box_w = width + pad_x * 2
        box_h = height + pad_y * 2
        x = round((image.width - box_w) / 2)
        draw.rounded_rectangle((x, y, x + box_w, y + box_h), radius=radius, fill=box_fill)
        draw_tracked_text(
            draw,
            (x + pad_x - bbox[0], y + pad_y - bbox[1]),
            line,
            font,
            fill=text_fill,
            stroke_width=stroke,
            stroke_fill=text_fill,
            tracking=tracking,
        )
        y += box_h + line_gap
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return image.width, image.height


def infer_role(text: str, lr_db: float | None, previous: str | None) -> str:
    interviewer_hints = (
        "長谷川美穂です",
        "ようこそ",
        "今夜はそのキートス",
        "今夜は調布市",
        "伺って",
        "伺いました",
        "ご紹介ください",
        "よろしいでしょうか",
        "ありますか",
        "いかがでしょうか",
        "いかがですか",
        "お聞かせ",
        "思うんですけど",
        "ありがとうございました",
        "今日は認定NPO法人",
    )
    interviewee_hints = (
        "中西裕理です",
        "私は",
        "私が",
        "私も",
        "利用させていただいて",
        "読ませていただいた",
        "選ばせていただきました",
    )
    if any(hint in text for hint in interviewer_hints):
        return "interviewer"
    if any(hint in text for hint in interviewee_hints):
        return "interviewee"
    if lr_db is not None:
        if lr_db <= -0.18:
            return "interviewee"
        if lr_db >= -0.08:
            return "interviewer"
    if text in {"そうですね", "はい", "そうです"} and previous:
        return previous
    return previous or "interviewer"


def should_merge_with_previous(text: str, previous: dict[str, Any] | None, start: float) -> bool:
    if previous is None:
        return False
    if not any(text.startswith(prefix) for prefix in DEPENDENT_CAPTION_PREFIXES):
        return False
    gap = start - float(previous["end"])
    combined = clean_text(str(previous["text"]) + text)
    return gap <= 0.35 and len(combined) <= 90


def load_lr_by_segment(project_root: Path) -> dict[int, float]:
    report_path = project_root / "output" / "reports" / "full_transcript_speaker_roles.json"
    if not report_path.exists():
        return {}
    data = load_json(report_path)
    lr_by_segment: dict[int, float] = {}
    for item in data.get("captions", []):
        if not isinstance(item, dict):
            continue
        features = item.get("audioFeatures", {})
        if not isinstance(features, dict) or features.get("lrDb") is None:
            continue
        try:
            lr_by_segment[int(item["index"])] = float(features["lrDb"])
        except (KeyError, TypeError, ValueError):
            continue
    return lr_by_segment


def detect_cut_start(segments: list[dict[str, Any]], replacements: list[dict[str, str]]) -> tuple[float, str]:
    for segment in segments:
        text = clean_text(apply_corrections(str(segment.get("text", "")), replacements))
        if float(segment.get("start", 0.0)) > 100.0 and text == "長谷川美穂です":
            return float(segment["start"]), "Detected main interviewer introduction: 長谷川美穂です"
    return 122.30, "Fallback to manually inspected main interview start"


def detect_cut_end(segments: list[dict[str, Any]], replacements: list[dict[str, str]]) -> tuple[float, str]:
    for index, segment in enumerate(segments):
        text = clean_text(apply_corrections(str(segment.get("text", "")), replacements))
        if "時間いっぱいまで" in text:
            previous = segments[max(0, index - 1)]
            return float(previous["end"]), "Detected music introduction; ending after final thanks"
    return 1436.60, "Fallback to manually inspected final thanks"


def target_segment_bounds(segments: list[dict[str, Any]], first_id: int, last_id: int) -> tuple[float, float]:
    selected = [segment for segment in segments if first_id <= int(segment.get("id", -1)) + 1 <= last_id]
    if not selected:
        raise RuntimeError(f"No transcript segments for range {first_id}-{last_id}")
    return float(selected[0]["start"]), float(selected[-1]["end"])


def build_sync_chunks(segments: list[dict[str, Any]]) -> list[SyncChunk]:
    # 1-based transcript segment ranges are anchored from transcript/waveform inspection.
    # Target times are edited-WAV transcript times. Source times are MP4-video times.
    specs = [
        (27, 174, 269.80, 846.78, "First interview block; start after opening music pickup"),
        (175, 176, 1043.64, 1055.68, "Post-break re-introduction; remove mid-program music lead-in"),
        (177, 274, 1055.68, 1415.08, "Second interview block before edited retake"),
        (275, 345, 1429.19, 1721.17, "Final topic block after removed retake"),
        (346, 354, 1721.17, 1769.04, "Song selection and closing setup"),
        (355, 359, 1771.21, 1783.89, "Final thanks before music introduction"),
    ]
    chunks: list[SyncChunk] = []
    for first_id, last_id, source_start, source_end, reason in specs:
        target_start, target_end = target_segment_bounds(segments, first_id, last_id)
        if first_id == 27:
            # Cut the middle break/music before the second-half radio pickup.
            target_end = 701.82
        if first_id == 175:
            # The ASR segment starts over the music bed; waveform match to MP4 speech starts here.
            target_start = 710.72
        if first_id == 346:
            # Do not carry the short musical pause before the closing recap.
            target_end = 1421.64
        chunks.append(
            SyncChunk(
                target_start=round(target_start, 3),
                target_end=round(target_end, 3),
                source_start=round(source_start, 3),
                source_end=round(source_end, 3),
                reason=reason,
            )
        )
    return chunks


def build_caption_events(
    segments: list[dict[str, Any]],
    replacements: list[dict[str, str]],
    *,
    cut_start: float,
    cut_end: float,
    max_line_chars: int,
    lr_by_segment: dict[int, float],
    segment_overrides: dict[int, str] | None = None,
    role_overrides: dict[int, str] | None = None,
) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    previous_role: str | None = None
    segment_overrides = segment_overrides or {}
    role_overrides = role_overrides or {}
    for segment in segments:
        original_id = int(segment.get("id", 0)) + 1
        start = float(segment.get("start", 0.0))
        end = float(segment.get("end", 0.0))
        if end <= cut_start or start >= cut_end:
            continue
        source_text = segment_overrides.get(original_id, str(segment.get("text", "")))
        text = clean_text(apply_corrections(source_text, replacements))
        if not text:
            continue
        clipped_start = max(start, cut_start) - cut_start
        clipped_end = min(end, cut_end) - cut_start
        if clipped_end <= clipped_start:
            continue
        role = role_overrides.get(original_id) or infer_role(text, lr_by_segment.get(original_id), previous_role)
        previous_role = role
        if should_merge_with_previous(text, units[-1] if units else None, clipped_start):
            units[-1]["text"] = clean_text(str(units[-1]["text"]) + text)
            units[-1]["end"] = round(clipped_end, 3)
            units[-1]["originalSegmentIds"].append(original_id)
            continue
        units.append(
            {
                "originalSegmentIds": [original_id],
                "start": round(clipped_start, 3),
                "end": round(clipped_end, 3),
                "role": role,
                "text": text,
            }
        )

    events: list[dict[str, Any]] = []
    for unit in units:
        start = float(unit["start"])
        end = float(unit["end"])
        text = str(unit["text"])
        line_groups = make_lines(text, max_line_chars=max_line_chars)
        weights = [max(1, sum(len(line) for line in group)) for group in line_groups]
        total_weight = sum(weights)
        duration = end - start
        elapsed = 0.0
        for group, weight in zip(line_groups, weights):
            chunk_duration = duration * weight / total_weight
            chunk_start = start + elapsed
            chunk_end = end if group is line_groups[-1] else min(end, chunk_start + chunk_duration)
            events.append(
                {
                    "originalSegmentId": unit["originalSegmentIds"][0],
                    "originalSegmentIds": list(unit["originalSegmentIds"]),
                    "start": round(chunk_start, 3),
                    "end": round(chunk_end, 3),
                    "role": unit["role"],
                    "text": "\n".join(group),
                }
            )
            elapsed += chunk_duration
    return events


def write_srt(path: Path, events: list[dict[str, Any]]) -> None:
    blocks: list[str] = []
    for index, event in enumerate(events, start=1):
        blocks.append(
            f"{index}\n{seconds_to_srt(float(event['start']))} --> {seconds_to_srt(float(event['end']))}\n{event['text']}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")


def write_caption_overlays(output_dir: Path, events: list[dict[str, Any]], config: dict[str, Any], project_root: Path) -> tuple[Path, list[dict[str, Any]]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    for old in output_dir.glob("caption_*.png"):
        if old.is_file():
            old.unlink()
    items: list[dict[str, Any]] = []
    for index, event in enumerate(events, start=1):
        filename = f"caption_{index:03d}.png"
        path = output_dir / filename
        width, height = render_caption_overlay(path, tuple(str(event["text"]).splitlines()), config, role=str(event["role"]))
        items.append(
            {
                "start": float(event["start"]),
                "end": float(event["end"]),
                "role": event["role"],
                "text": event["text"],
                "file": str(path.relative_to(project_root)).replace("\\", "/"),
                "width": width,
                "height": height,
            }
        )
    manifest = output_dir / "manifest.json"
    manifest.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest, items


def clip_chunks_for_window(chunks: list[SyncChunk], *, cut_start: float, window_start: float, duration: float | None) -> list[SyncChunk]:
    result: list[SyncChunk] = []
    window_end = None if duration is None else window_start + duration
    output_cursor = 0.0
    for chunk in chunks:
        chunk_duration = chunk.target_duration
        output_start = output_cursor
        output_end = output_cursor + chunk_duration
        output_cursor = output_end
        overlap_start = max(output_start, window_start)
        overlap_end = output_end if window_end is None else min(output_end, window_end)
        if overlap_end <= overlap_start:
            continue
        ratio = chunk.setpts_ratio
        source_start = chunk.source_start + (overlap_start - output_start) / ratio
        source_end = chunk.source_start + (overlap_end - output_start) / ratio
        result.append(
            SyncChunk(
                target_start=round(overlap_start - window_start, 3),
                target_end=round(overlap_end - window_start, 3),
                source_start=round(source_start, 3),
                source_end=round(source_end, 3),
                reason=chunk.reason,
            )
        )
    return result


def clip_audio_chunks_for_window(chunks: list[SyncChunk], *, window_start: float, duration: float | None) -> list[SyncChunk]:
    result: list[SyncChunk] = []
    window_end = None if duration is None else window_start + duration
    output_cursor = 0.0
    for chunk in chunks:
        chunk_duration = chunk.target_duration
        output_start = output_cursor
        output_end = output_cursor + chunk_duration
        output_cursor = output_end
        overlap_start = max(output_start, window_start)
        overlap_end = output_end if window_end is None else min(output_end, window_end)
        if overlap_end <= overlap_start:
            continue
        audio_start = chunk.target_start + (overlap_start - output_start)
        audio_end = chunk.target_start + (overlap_end - output_start)
        result.append(
            SyncChunk(
                target_start=round(audio_start, 3),
                target_end=round(audio_end, 3),
                source_start=round(chunk.source_start, 3),
                source_end=round(chunk.source_end, 3),
                reason=chunk.reason,
            )
        )
    return result


def remap_events_to_output(
    events: list[dict[str, Any]],
    chunks: list[SyncChunk],
    *,
    cut_start: float,
    window_start: float = 0.0,
    duration: float | None = None,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    window_end = None if duration is None else window_start + duration
    output_cursor = 0.0
    for chunk in chunks:
        chunk_output_start = output_cursor
        chunk_output_end = output_cursor + chunk.target_duration
        output_cursor = chunk_output_end
        for event in events:
            event_abs_start = cut_start + float(event["start"])
            event_abs_end = cut_start + float(event["end"])
            overlap_start = max(event_abs_start, chunk.target_start)
            overlap_end = min(event_abs_end, chunk.target_end)
            if overlap_end <= overlap_start:
                continue
            output_start = chunk_output_start + (overlap_start - chunk.target_start)
            output_end = chunk_output_start + (overlap_end - chunk.target_start)
            visible_start = max(output_start, window_start)
            visible_end = output_end if window_end is None else min(output_end, window_end)
            if visible_end <= visible_start:
                continue
            adjusted = dict(event)
            adjusted["start"] = round(visible_start - window_start, 3)
            adjusted["end"] = round(visible_end - window_start, 3)
            result.append(adjusted)
    result.sort(key=lambda item: (float(item["start"]), float(item["end"]), str(item.get("text", ""))))
    return result


def filter_escape(path: str) -> str:
    return path.replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def write_filter_script(
    path: Path,
    chunks: list[SyncChunk],
    audio_chunks: list[SyncChunk],
    caption_items: list[dict[str, Any]],
    config: dict[str, Any],
    *,
    logo_index: int | None,
    title_index: int | None,
) -> Path:
    edit = config.get("radioEdit", {})
    width = int(edit.get("targetWidth", 1920))
    height = int(edit.get("targetHeight", 1080))
    filters: list[str] = []
    video_labels: list[str] = []
    for index, chunk in enumerate(chunks):
        label = f"seg{index}"
        ratio = chunk.setpts_ratio
        filters.append(
            f"[0:v]trim=start={chunk.source_start:.3f}:end={chunk.source_end:.3f},"
            f"setpts=(PTS-STARTPTS)*{ratio:.9f},"
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1[{label}]"
        )
        video_labels.append(f"[{label}]")
    filters.append(f"{''.join(video_labels)}concat=n={len(video_labels)}:v=1:a=0,fps={config.get('render', {}).get('outputFps', '30000/1001')}[vbase]")
    current = "vbase"
    if logo_index is not None:
        logo_height = int(edit.get("logoFrameHeight" if edit.get("logoBoxEnabled") else "logoHeight", edit.get("logoHeight", 82)))
        margin_x = int(edit.get("logoMarginX", 36))
        margin_y = int(edit.get("logoMarginY", 28))
        filters.append(f"[{logo_index}:v]scale=-1:{logo_height},format=rgba[logo]")
        filters.append(f"[{current}][logo]overlay=W-w-{margin_x}:{margin_y}[vlogo]")
        current = "vlogo"
    if title_index is not None:
        title_x = int(edit.get("titleX", 18))
        title_y = int(edit.get("titleY", 18))
        filters.append(f"[{title_index}:v]format=rgba[title]")
        filters.append(f"[{current}][title]overlay={title_x}:{title_y}[vtitle]")
        current = "vtitle"
    margin_v = int(edit.get("subtitleMarginV", 16))
    for offset, item in enumerate(caption_items):
        source = filter_escape(str(item["file"]))
        label = f"cap{offset}"
        out_label = f"v{label}"
        start = float(item["start"])
        end = float(item["end"])
        filters.append(f"movie='{source}',format=rgba[{label}]")
        filters.append(
            f"[{current}][{label}]overlay=(W-w)/2:H-h-{margin_v}:"
            f"enable='between(t\\,{start:.3f}\\,{end:.3f})'[{out_label}]"
        )
        current = out_label
    filters.append(f"[{current}]format=yuv420p[v]")
    audio_labels: list[str] = []
    for index, chunk in enumerate(audio_chunks):
        label = f"aseg{index}"
        filters.append(f"[1:a]atrim=start={chunk.target_start:.3f}:end={chunk.target_end:.3f},asetpts=PTS-STARTPTS[{label}]")
        audio_labels.append(f"[{label}]")
    filters.append(f"{''.join(audio_labels)}concat=n={len(audio_labels)}:v=0:a=1,loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[a]")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(";\n".join(filters), encoding="utf-8")
    return path


def audit_subtitles(events: list[dict[str, Any]]) -> list[dict[str, str]]:
    protected = ["Kiitos", "中西裕理", "東京オアシス", "青少年の居場所", "認定NPO法人", "白旗眞生", "白旗さん"]
    bad_start = re.compile(
        r"^(ております|しております|ています|ていく|ていただ|いただ|おります|ました|ます(?!ます)|です(?!が|から|けど|けれど)|でしょうか|ください|けれども|ですけれども|と思います|ると思います|という内容|ということで|っていう|ところ|もの|こと|ので|から|ため|には|は(?!い|じめ|っきり|ず))"
    )
    issues: list[dict[str, str]] = []
    for index, event in enumerate(events, start=1):
        lines = str(event["text"]).splitlines()
        flat = "".join(lines)
        if lines and bad_start.search(lines[0]):
            issues.append({"event": str(index), "kind": "bad_cue_start", "text": event["text"]})
        for line in lines[1:]:
            if bad_start.search(line):
                issues.append({"event": str(index), "kind": "bad_line_start", "text": event["text"]})
        for phrase in protected:
            if phrase in flat and phrase not in str(event["text"]):
                issues.append({"event": str(index), "kind": f"protected_split:{phrase}", "text": event["text"]})
    return issues


def main() -> None:
    parser = argparse.ArgumentParser(description="Build synced video + edited audio subtitle render for Yuri Nakanishi.")
    parser.add_argument("--project-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--no-render", action="store_true")
    parser.add_argument("--preview-duration", type=float, default=None)
    parser.add_argument("--preview-offset", type=float, default=0.0)
    parser.add_argument("--preview-output", type=Path, default=None)
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    config = load_json(project_root / "project_state.json")
    edit = config.get("radioEdit", {})
    ffmpeg = str(config.get("tools", {}).get("ffmpeg", "ffmpeg"))
    source_video = Path(config["assets"]["masterVideo"])
    source_audio = Path(config["assets"]["externalAudio"])
    logo_path = Path(str(edit.get("logoPath") or config.get("assets", {}).get("logo") or ""))
    transcript_path = project_root / "output" / "transcripts" / "manifest_sources" / "external__20260528.json"
    if not transcript_path.exists():
        raise SystemExit(f"Transcript not found: {transcript_path}")
    transcript = load_json(transcript_path)
    segments = list(transcript.get("segments", []))
    corrections_path = Path(str(edit.get("transcriptCorrectionsPath") or project_root / "config" / "transcript_corrections.json"))
    corrections = load_json(corrections_path) if corrections_path.exists() else {}
    replacements = corrections.get("replacements", [])
    replacements = [item for item in replacements if isinstance(item, dict)]
    segment_overrides = normalize_int_key_map(corrections.get("segmentOverrides", {}))
    role_overrides = normalize_role_override_map(corrections.get("roleOverrides", {}))
    cut_start, cut_start_reason = detect_cut_start(segments, replacements)
    cut_end, cut_end_reason = detect_cut_end(segments, replacements)
    chunks = build_sync_chunks(segments)
    max_line_chars = int(edit.get("subtitleMaxLineChars", 20))
    lr_by_segment = load_lr_by_segment(project_root)
    events = build_caption_events(
        segments,
        replacements,
        cut_start=cut_start,
        cut_end=cut_end,
        max_line_chars=max_line_chars,
        lr_by_segment=lr_by_segment,
        segment_overrides=segment_overrides,
        role_overrides=role_overrides,
    )
    source_duration = round(cut_end - cut_start, 3)
    duration = round(sum(chunk.target_duration for chunk in chunks), 3)
    preview_offset = max(0.0, min(duration, float(args.preview_offset or 0.0)))
    render_duration = duration if args.preview_duration is None else min(duration - preview_offset, max(0.0, float(args.preview_duration)))
    render_chunks = clip_chunks_for_window(chunks, cut_start=cut_start, window_start=preview_offset, duration=render_duration)
    audio_chunks = clip_audio_chunks_for_window(chunks, window_start=preview_offset, duration=render_duration)
    if not render_chunks:
        raise SystemExit("No video sync chunks overlap the requested render window.")
    output_events = remap_events_to_output(events, chunks, cut_start=cut_start)
    overlay_events = remap_events_to_output(events, chunks, cut_start=cut_start, window_start=preview_offset, duration=render_duration)

    output_srt = project_root / "output" / "subtitles" / "tokyo_oasis_20260528_nakanishi_cut.srt"
    caption_overlay_dir = project_root / "output" / "overlays" / "synced_video_caption_png_overlays"
    title_overlay = project_root / "output" / "overlays" / "title" / "tokyo_oasis_nakanishi_title.png"
    logo_overlay = project_root / "output" / "overlays" / "logo" / "kiitos_logo_box.png"
    filter_script = project_root / "output" / "overlays" / "synced_video_filter_complex.ffmpeg"
    report_path = project_root / "output" / "reports" / "nakanishi_synced_video_build_report.json"
    if args.preview_output is not None:
        output_video = args.preview_output
    elif args.preview_duration is not None:
        output_video = project_root / "output" / "videos" / "tokyo_oasis_20260528_nakanishi_sync_preview.mp4"
    else:
        output_video = Path(config.get("render", {}).get("outputPath", project_root / "output" / "videos" / "tokyo_oasis_20260528_nakanishi_synced_subtitled.mp4"))
    if not output_video.is_absolute():
        output_video = project_root / output_video

    write_srt(output_srt, output_events)
    write_title_overlay(title_overlay, config)
    logo_input_path = write_logo_overlay(logo_overlay, logo_path, config) if logo_path.exists() and edit.get("logoBoxEnabled") else logo_path
    caption_manifest, caption_items = write_caption_overlays(caption_overlay_dir, overlay_events, config, project_root)
    filter_path = write_filter_script(
        filter_script,
        render_chunks,
        audio_chunks,
        caption_items,
        config,
        logo_index=2 if logo_input_path.exists() else None,
        title_index=3 if title_overlay.exists() else None,
    )
    render_command: list[str] | None = None
    if not args.no_render:
        output_video.parent.mkdir(parents=True, exist_ok=True)
        extra_inputs: list[str] = []
        if logo_input_path.exists():
            extra_inputs.extend(["-loop", "1", "-i", str(logo_input_path)])
        if title_overlay.exists():
            extra_inputs.extend(["-loop", "1", "-i", str(title_overlay)])
        render_command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source_video),
            "-i",
            str(source_audio),
            *extra_inputs,
            "-filter_complex_script",
            str(filter_path),
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-t",
            f"{render_duration:.3f}",
            "-c:v",
            str(config.get("render", {}).get("videoEncoder", "libx264")),
            "-preset",
            str(config.get("render", {}).get("videoPreset", "veryfast")),
            "-crf",
            str(config.get("render", {}).get("videoCrf", 18)),
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-movflags",
            "+faststart",
            str(output_video),
        ]
        run(render_command, cwd=project_root)

    issues = audit_subtitles(output_events)
    role_counts = {
        "interviewer": sum(1 for event in output_events if event["role"] == "interviewer"),
        "interviewee": sum(1 for event in output_events if event["role"] == "interviewee"),
        "unknown": sum(1 for event in output_events if event["role"] not in {"interviewer", "interviewee"}),
    }
    report = {
        "project": PROJECT_ID,
        "sourceVideo": str(source_video),
        "sourceAudio": str(source_audio),
        "transcript": str(transcript_path),
        "cutStartSeconds": cut_start,
        "cutEndSeconds": cut_end,
        "sourceTimelineDurationSeconds": source_duration,
        "durationSeconds": duration,
        "cutStartReason": cut_start_reason,
        "cutEndReason": cut_end_reason,
        "syncChunks": [asdict(chunk) | {"sourceDuration": round(chunk.source_duration, 3), "targetDuration": round(chunk.target_duration, 3), "setptsRatio": round(chunk.setpts_ratio, 6)} for chunk in chunks],
        "renderChunks": [asdict(chunk) | {"sourceDuration": round(chunk.source_duration, 3), "targetDuration": round(chunk.target_duration, 3), "setptsRatio": round(chunk.setpts_ratio, 6)} for chunk in render_chunks],
        "audioChunks": [asdict(chunk) | {"targetDuration": round(chunk.target_duration, 3)} for chunk in audio_chunks],
        "subtitleEventCount": len(output_events),
        "renderSubtitleEventCount": len(overlay_events),
        "subtitleAuditIssues": issues,
        "roleCounts": role_counts,
        "correctionCounts": {
            "replacements": len(replacements),
            "segmentOverrides": len(segment_overrides),
            "roleOverrides": len(role_overrides),
        },
        "outputs": {
            "srt": str(output_srt),
            "captionOverlayManifest": str(caption_manifest),
            "titleOverlay": str(title_overlay),
            "logoOverlay": str(logo_input_path) if logo_input_path.exists() else "",
            "filterScript": str(filter_path),
            "video": str(output_video) if not args.no_render else "",
        },
        "renderCommand": render_command,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(report_path), **report["outputs"], "durationSeconds": duration, "roleCounts": role_counts, "subtitleAuditIssueCount": len(issues)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
