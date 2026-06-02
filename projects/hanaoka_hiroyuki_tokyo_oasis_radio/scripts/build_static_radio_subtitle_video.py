from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


PROJECT_ID = "hanaoka_hiroyuki_tokyo_oasis_radio"
DEFAULT_ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run(command: list[str], *, cwd: Path) -> None:
    print(json.dumps({"command": command}, ensure_ascii=False), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def seconds_to_ass(seconds: float) -> str:
    centiseconds = max(0, int(round(seconds * 100)))
    hours, rem = divmod(centiseconds, 360000)
    minutes, rem = divmod(rem, 6000)
    secs, cs = divmod(rem, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def seconds_to_srt(seconds: float) -> str:
    millis = max(0, int(round(seconds * 1000)))
    hours, rem = divmod(millis, 3600000)
    minutes, rem = divmod(rem, 60000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def ass_color(hex_color: str, alpha: int = 0) -> str:
    text = str(hex_color).strip().lstrip("#")
    if not re.fullmatch(r"[0-9A-Fa-f]{6}", text):
        text = "FFFFFF"
    alpha = max(0, min(255, int(alpha)))
    red = text[0:2]
    green = text[2:4]
    blue = text[4:6]
    return f"&H{alpha:02X}{blue}{green}{red}".upper()


def alpha_from_opacity(opacity: float) -> int:
    return round((1.0 - max(0.0, min(1.0, float(opacity)))) * 255)


def hex_to_rgba(hex_color: str, opacity: float = 1.0) -> tuple[int, int, int, int]:
    text = str(hex_color).strip().lstrip("#")
    if not re.fullmatch(r"[0-9A-Fa-f]{6}", text):
        text = "FFFFFF"
    alpha = round(max(0.0, min(1.0, opacity)) * 255)
    return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16), alpha)


def ass_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", str(text)).strip()
    jp = r"\u3040-\u30ff\u3400-\u9fff"
    text = re.sub(fr"(?<=[{jp}])\s+(?=[{jp}])", "", text)
    return text


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
    allowed = {"interviewer", "interviewee"}
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
    "青少年の居場所Kiitos",
    "新生Kiitos",
    "Kiitosのすごさというのは",
    "キートス",
    "花岡洋行",
    "花岡さん",
    "長谷川美穂",
    "井の中の蛙",
    "元手も必要",
    "白旗眞生",
    "白旗さん",
    "止まり木",
    "『Sing』",
    "『You saved my life』",
    "新理事",
    "心理士",
    "お一人",
    "いらっしゃる",
    "いらっしゃいます",
    "お招きしております",
    "お話し",
    "お話を",
    "お伺い",
    "ご覧に",
    "お願いいたします",
    "ご存知でしょうか",
    "ホームページ",
    "子ども食堂",
    "青少年の居場所",
    "生きづらさ",
    "あり方",
    "きちっと",
    "きちっと運営",
    "貢献できる",
    "じっくりと",
    "お伺いしてみたい",
    "陰ながら",
    "子ども食堂です",
    "そうですね、はい",
    "良いものにしたい",
    "物乞い",
    "事業をやっていく",
    "ずっと居ちゃいけない",
    "止まりたい",
    "なんですけど",
    "なんでしょうか",
    "ですね",
    "いけない",
    "いかないといけない",
    "ことかな",
    "いいのかな",
    "というふう",
    "つなげられたら",
    "連れてって",
    "おありになった",
    "いただける",
    "かもしれない",
    "『You saved my life』ですね",
    "帰られて",
    "もちろん",
    "設立",
    "認識",
    "必要性",
    "若者支援",
    "認定NPO法人",
    "あしなが育英会",
    "など",
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
    "すけど",
    "すね",
    "けない",
    "きる",
    "りと",
    "ら",
    "な",
    "うふう",
    "なった",
    "でしょうか",
    "だける",
    "しれない",
    "ですね",
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
DEPENDENT_SEGMENT_PREFIXES = (
    "っていう",
    "という",
    "ので",
    "ております",
    "しております",
    "ています",
    "ていく",
    "ていただ",
    "いただ",
    "おります",
)
DANGLING_SEGMENT_END_SUFFIXES = (
    "それ以外の遺児、",
    "それ以外の遺児",
)
DEPENDENT_SEGMENT_MAX_GAP = 0.35
DEPENDENT_SEGMENT_MAX_CHARS = 90
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
    "キート",
    "Ki",
    "Kiit",
    "すご",
    "き",
    "貢献で",
    "じっく",
    "陰なが",
    "いかな",
    "ことか",
    "いいのか",
    "とい",
    "おありに",
    "いた",
    "かも",
    "連れ",
    "いら",
    "いらっし",
    "し",
    "て",
    "と",
)
MANUAL_CAPTION_GROUPS = {
    "それをどう生かすかというのがこれから考えていくことかなというふうに思っています": (
        ("それをどう生かすかというのが",),
        ("これから考えていくことかな", "というふうに思っています"),
    ),
    "やっぱりこれから頑張っていかないといけないかなというふうに思っています": (
        ("やっぱりこれから頑張っていかないと", "いけないかなというふうに思っています"),
    ),
    "どのようにこの未来に向かって連れてってくれるのかなっていう意味では": (
        ("どのようにこの未来に向かって", "連れてってくれるのかなっていう意味では"),
    ),
    "ある意味結構大変なことだったのかなって今更ながら思います": (
        ("ある意味結構大変なことだったのかなって", "今更ながら思います"),
    ),
    "そこで貢献できるのかなというふうには思っています": (
        ("そこで貢献できるのかなというふうには", "思っています"),
    ),
    "そのキャリアについては後半でじっくりとお伺いしてみたいと思うんですけれども": (
        ("そのキャリアについては後半で", "じっくりとお伺いしてみたいと"),
        ("思うんですけれども",),
    ),
    "全然恥ずかしいということはないと思うんですけど": (
        ("全然恥ずかしいということは", "ないと思うんですけど"),
    ),
    "そうなると、新卒でNPOっていうのもね、なかなかはっきり申し上げて、生活資金的にはNPOってそれほどいただけるものもいただけないような感じがするんですけれども、": (
        ("そうなると、新卒でNPOっていうのもね、",),
        ("なかなかはっきり申し上げて、", "生活資金的にはNPOってそれほど"),
        ("いただけるものもいただけないような感じが", "するんですけれども、"),
    ),
    "いきなりNPOに飛び込まれたっていうところなんでしょうか、新卒で。": (
        ("いきなりNPOに飛び込まれたっていう", "ところなんでしょうか、新卒で。"),
    ),
    "そのきっかけっておありになったんでしょうか": (
        ("そのきっかけっておありになったんでしょうか",),
    ),
    "これ認定をいただいたっていうことはKiitosにとってももちろんメリットがあるということですよね": (
        ("これ認定をいただいたっていうことは", "Kiitosにとっても"),
        ("もちろんメリットがあるということですよね",),
    ),
    "『You saved my life』ですね": (
        ("『You saved my life』ですね",),
    ),
    "さらに全国版のあしなが育英会の方で働かれて": (
        ("さらに全国版の", "あしなが育英会の方で働かれて"),
    ),
    "ただご飯をみんなで食べる場所じゃないんだよっていう明確なビジョンがあって": (
        ("ただご飯をみんなで",),
        ("食べる場所じゃないんだよっていう", "明確なビジョンがあって"),
    ),
    "子ども食堂とはあえて言ってないんだろうなというふうには思いますね": (
        ("子ども食堂とはあえて", "言ってないんだろうなというふうには思いますね"),
    ),
}


def apply_corrections(text: str, replacements: list[dict[str, str]]) -> str:
    corrected = str(text)
    for item in replacements:
        source = str(item.get("from", ""))
        target = str(item.get("to", ""))
        if source:
            corrected = corrected.replace(source, target)
    return corrected


def is_dependent_segment_start(text: str) -> bool:
    return any(text.startswith(prefix) for prefix in DEPENDENT_SEGMENT_PREFIXES)


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
                    if n - end > 0 and n - end < min_remaining:
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
        line_count_cost = (line_count - min_line_count) * 8_000.0
        total_cost = dp[-1][n][0] + line_count_cost
        if total_cost < best_cost:
            best_cost = total_cost
            best_lines = lines
    if best_lines:
        return best_lines
    return [text[index:index + max_line_chars] for index in range(0, len(text), max_line_chars)]


def make_lines(text: str, max_line_chars: int = 24, max_lines: int = 2) -> list[list[str]]:
    if text in MANUAL_CAPTION_GROUPS:
        return [list(group) for group in MANUAL_CAPTION_GROUPS[text]]
    lines = choose_natural_lines(text, max_line_chars)
    return [lines[index:index + max_lines] for index in range(0, len(lines), max_lines)]


def role_for_segment(segment: dict[str, Any], roles: dict[str, str]) -> str:
    original_index = int(segment.get("id", 0)) + 1
    role = roles.get(str(original_index), "interviewee")
    return "interviewer" if role == "interviewer" else "interviewee"


def detect_cut_start(segments: list[dict[str, Any]]) -> tuple[float, str]:
    for segment in segments:
        text = clean_text(segment.get("text", ""))
        if "長谷川美穂です" in text:
            return float(segment["start"]), "Detected main interviewer introduction: 長谷川美穂です"
    for index, segment in enumerate(segments):
        if "それでは早速" in clean_text(segment.get("text", "")) and index + 1 < len(segments):
            return float(segments[index + 1]["start"]), "Detected transition after opening greeting"
    return 0.0, "No opening marker detected; using start of source"


def detect_cut_end(segments: list[dict[str, Any]]) -> tuple[float, str]:
    for index, segment in enumerate(segments):
        text = clean_text(segment.get("text", ""))
        if "時間いっぱいまで" in text or "YourSong" in text:
            previous = segments[max(0, index - 1)]
            return float(previous["end"]), "Detected music introduction; ending at previous thanks"
    return float(segments[-1]["end"]), "No music marker detected; using transcript end"


def normalize_audio_remove_ranges(edit: dict[str, Any], cut_start: float, cut_end: float) -> list[dict[str, Any]]:
    raw_ranges = edit.get("audioRemoveRangesSeconds", [])
    if not isinstance(raw_ranges, list):
        return []

    ranges: list[dict[str, Any]] = []
    for item in raw_ranges:
        reason = ""
        if isinstance(item, dict):
            start_value = item.get("start", item.get("startSeconds"))
            end_value = item.get("end", item.get("endSeconds"))
            reason = str(item.get("reason", ""))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            start_value = item[0]
            end_value = item[1]
        else:
            continue

        try:
            start = float(start_value)
            end = float(end_value)
        except (TypeError, ValueError):
            continue

        start = max(cut_start, start)
        end = min(cut_end, end)
        if end <= start:
            continue
        ranges.append(
            {
                "start": round(start, 3),
                "end": round(end, 3),
                "duration": round(end - start, 3),
                "reason": reason,
            }
        )

    ranges.sort(key=lambda item: (float(item["start"]), float(item["end"])))
    merged: list[dict[str, Any]] = []
    for item in ranges:
        if not merged or float(item["start"]) > float(merged[-1]["end"]):
            merged.append(dict(item))
            continue
        merged[-1]["end"] = round(max(float(merged[-1]["end"]), float(item["end"])), 3)
        merged[-1]["duration"] = round(float(merged[-1]["end"]) - float(merged[-1]["start"]), 3)
        if item.get("reason"):
            merged[-1]["reason"] = "; ".join(
                part for part in [str(merged[-1].get("reason", "")), str(item.get("reason", ""))] if part
            )
    return merged


def build_audio_keep_ranges(
    cut_start: float,
    cut_end: float,
    edit: dict[str, Any],
) -> tuple[list[tuple[float, float]], list[dict[str, Any]]]:
    remove_ranges = normalize_audio_remove_ranges(edit, cut_start, cut_end)
    keep_ranges: list[tuple[float, float]] = [(cut_start, cut_end)]
    for remove_range in remove_ranges:
        remove_start = float(remove_range["start"])
        remove_end = float(remove_range["end"])
        next_ranges: list[tuple[float, float]] = []
        for keep_start, keep_end in keep_ranges:
            if remove_end <= keep_start or remove_start >= keep_end:
                next_ranges.append((keep_start, keep_end))
                continue
            if remove_start > keep_start:
                next_ranges.append((keep_start, remove_start))
            if remove_end < keep_end:
                next_ranges.append((remove_end, keep_end))
        keep_ranges = next_ranges
    if not keep_ranges:
        raise SystemExit("Audio remove ranges leave no content to render.")
    return keep_ranges, remove_ranges


def audio_timeline_duration(keep_ranges: list[tuple[float, float]]) -> float:
    return sum(max(0.0, end - start) for start, end in keep_ranges)


def remap_events_to_keep_ranges(
    events: list[dict[str, Any]],
    keep_ranges: list[tuple[float, float]],
    cut_start: float,
) -> list[dict[str, Any]]:
    remapped: list[dict[str, Any]] = []
    output_cursor = 0.0
    for keep_start, keep_end in keep_ranges:
        for event in events:
            source_start = cut_start + float(event["start"])
            source_end = cut_start + float(event["end"])
            overlap_start = max(source_start, keep_start)
            overlap_end = min(source_end, keep_end)
            if overlap_end <= overlap_start:
                continue
            adjusted = dict(event)
            adjusted["start"] = round(output_cursor + overlap_start - keep_start, 3)
            adjusted["end"] = round(output_cursor + overlap_end - keep_start, 3)
            if float(adjusted["end"]) <= float(adjusted["start"]):
                continue
            remapped.append(adjusted)
        output_cursor += keep_end - keep_start
    remapped.sort(key=lambda item: (float(item["start"]), float(item["end"])))
    return remapped


def write_cut_audio(
    ffmpeg: str,
    source_audio: Path,
    output_audio: Path,
    keep_ranges: list[tuple[float, float]],
    project_root: Path,
) -> None:
    output_audio.parent.mkdir(parents=True, exist_ok=True)
    if len(keep_ranges) == 1:
        start, end = keep_ranges[0]
        run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                f"{start:.3f}",
                "-t",
                f"{end - start:.3f}",
                "-i",
                str(source_audio),
                "-vn",
                "-af",
                "loudnorm=I=-16:TP=-1.5:LRA=11",
                "-c:a",
                "pcm_s16le",
                str(output_audio),
            ],
            cwd=project_root,
        )
        return

    filter_parts: list[str] = []
    labels: list[str] = []
    for index, (start, end) in enumerate(keep_ranges):
        label = f"a{index}"
        labels.append(f"[{label}]")
        filter_parts.append(
            f"[0:a]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS[{label}]"
        )
    filter_parts.append(
        f"{''.join(labels)}concat=n={len(labels)}:v=0:a=1,loudnorm=I=-16:TP=-1.5:LRA=11[a]"
    )
    run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source_audio),
            "-filter_complex",
            ";".join(filter_parts),
            "-map",
            "[a]",
            "-c:a",
            "pcm_s16le",
            str(output_audio),
        ],
        cwd=project_root,
    )


def build_caption_events(
    segments: list[dict[str, Any]],
    roles: dict[str, str],
    cut_start: float,
    cut_end: float,
    replacements: list[dict[str, str]],
    max_line_chars: int,
    segment_overrides: dict[int, str] | None = None,
    role_overrides: dict[int, str] | None = None,
) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    normalized_roles = {str(key): str(value) for key, value in roles.items()}
    segment_overrides = segment_overrides or {}
    role_overrides = role_overrides or {}
    for segment in segments:
        segment_id = int(segment.get("id", 0))
        start = float(segment.get("start", 0.0))
        end = float(segment.get("end", 0.0))
        if end <= cut_start or start >= cut_end:
            continue
        source_text = segment_overrides.get(segment_id, str(segment.get("text", "")))
        text = clean_text(apply_corrections(source_text, replacements))
        if not text:
            continue
        clipped_start = max(start, cut_start) - cut_start
        clipped_end = min(end, cut_end) - cut_start
        if clipped_end <= clipped_start:
            continue
        role = role_overrides.get(segment_id) or role_for_segment(segment, normalized_roles)
        if units:
            previous = units[-1]
            gap = start - float(previous["sourceEnd"])
            combined_text = clean_text(str(previous["text"]) + text)
            previous_is_dangling = any(
                str(previous["text"]).endswith(suffix) for suffix in DANGLING_SEGMENT_END_SUFFIXES
            )
            if (
                (is_dependent_segment_start(text) or previous_is_dangling)
                and gap <= DEPENDENT_SEGMENT_MAX_GAP
                and len(combined_text) <= DEPENDENT_SEGMENT_MAX_CHARS
            ):
                previous["text"] = combined_text
                previous["end"] = round(clipped_end, 3)
                previous["sourceEnd"] = end
                previous["originalSegmentIds"].append(segment.get("id"))
                continue
        units.append(
            {
                "originalSegmentIds": [segment.get("id")],
                "start": round(clipped_start, 3),
                "end": round(clipped_end, 3),
                "sourceEnd": end,
                "role": role,
                "text": text,
            }
        )

    events: list[dict[str, Any]] = []
    for unit in units:
        start = float(unit["start"])
        end = float(unit["end"])
        text = str(unit["text"])
        role = str(unit["role"])
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
                    "role": role,
                    "text": "\n".join(group),
                }
            )
            elapsed += chunk_duration
    return events


def write_srt(path: Path, events: list[dict[str, Any]]) -> None:
    blocks: list[str] = []
    for index, event in enumerate(events, start=1):
        text = str(event["text"])
        blocks.append(
            f"{index}\n{seconds_to_srt(float(event['start']))} --> {seconds_to_srt(float(event['end']))}\n{text}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")


def ass_header(config: dict[str, Any]) -> str:
    edit = config.get("radioEdit", {})
    width = int(edit.get("targetWidth", 1920))
    height = int(edit.get("targetHeight", 1080))
    size = int(edit.get("subtitleFontSize", 58))
    margin_v = int(edit.get("subtitleMarginV", 64))
    tracking = int(edit.get("subtitleTracking", 4))
    text_color = ass_color(str(edit.get("subtitleTextColor", "#FFFFFF")))
    box_alpha = alpha_from_opacity(float(edit.get("subtitleBoxOpacity", 0.88)))
    shadow_alpha = alpha_from_opacity(float(edit.get("subtitleShadowAlpha", 0.35)))
    hasegawa_box = ass_color(str(edit.get("hasegawaSubtitleBoxColor", edit.get("interviewerColor", "#E85AA3"))), box_alpha)
    hanaoka_box = ass_color(str(edit.get("hanaokaSubtitleBoxColor", edit.get("intervieweeColor", "#2FAE66"))), box_alpha)
    unknown_box = ass_color(str(edit.get("unknownSubtitleBoxColor", edit.get("unknownColor", "#555555"))), box_alpha)
    shadow = ass_color("#000000", shadow_alpha)
    box_padding = int(edit.get("subtitleBoxPadding", 18))
    return f"""[Script Info]
ScriptType: v4.00+
WrapStyle: 2
ScaledBorderAndShadow: yes
PlayResX: {width}
PlayResY: {height}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Interviewer,Yu Gothic,{size},{text_color},&H000000FF,{hasegawa_box},{shadow},-1,0,0,0,100,100,{tracking},0,3,{box_padding},3,2,80,80,{margin_v},1
Style: Interviewee,Yu Gothic,{size},{text_color},&H000000FF,{hanaoka_box},{shadow},-1,0,0,0,100,100,{tracking},0,3,{box_padding},3,2,80,80,{margin_v},1
Style: Unknown,Yu Gothic,{size},{text_color},&H000000FF,{unknown_box},{shadow},-1,0,0,0,100,100,{tracking},0,3,{box_padding},3,2,80,80,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def write_ass(path: Path, events: list[dict[str, Any]], config: dict[str, Any]) -> None:
    lines = [ass_header(config)]
    for event in events:
        style = "Interviewer" if event["role"] == "interviewer" else "Interviewee"
        text = r"\N".join(ass_escape(part) for part in str(event["text"]).splitlines())
        lines.append(
            f"Dialogue: 0,{seconds_to_ass(float(event['start']))},{seconds_to_ass(float(event['end']))},{style},,0,0,0,,{text}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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


def tracked_text_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    stroke: int,
    tracking: int,
) -> int:
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
        draw.text(
            (x - bbox[0], y),
            char,
            font=font,
            fill=fill,
            stroke_width=stroke_width,
            stroke_fill=stroke_fill,
        )
        x += bbox[2] - bbox[0]
        if index < len(text) - 1:
            x += tracking


def write_title_overlay(path: Path, config: dict[str, Any]) -> Path:
    edit = config.get("radioEdit", {})
    title = str(edit.get("titleText", "【東京オアシス】花岡洋行さん出演会"))
    size = round(int(edit.get("titleFontSize", 58)) * float(edit.get("titleRenderScale", 1.2)))
    pad_x = int(edit.get("titlePaddingX", 24))
    pad_y = int(edit.get("titlePaddingY", 11))
    stripe = int(edit.get("titleStripeHeight", 10))
    tracking = int(edit.get("titleTracking", edit.get("subtitleTracking", 4)))
    font = load_font(size)
    probe = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    draw = ImageDraw.Draw(probe)
    stroke = int(edit.get("titleStrokeWidth", 1))
    bbox = draw.textbbox((0, 0), title, font=font, stroke_width=stroke)
    text_width = tracked_text_width(draw, title, font, stroke, tracking)
    width = text_width + pad_x * 2
    height = bbox[3] - bbox[1] + pad_y * 2
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    accent = hex_to_rgba(str(edit.get("titleAccentColor", edit.get("titleTextColor", "#F28C28"))), 1.0)
    alpha = round(max(0.0, min(1.0, float(edit.get("titleBoxOpacity", 0.94)))) * 255)
    box_fill = hex_to_rgba(str(edit.get("titleBoxColor", "#FFFFFF")), alpha / 255)
    stripe_fill = (*accent[:3], max(70, min(180, round(alpha * 0.55))))
    draw.rectangle((0, 0, width, height), fill=box_fill)
    draw.rectangle((0, height - stripe, width, height), fill=stripe_fill)
    draw.rectangle((0, height - 2, width, height), fill=accent)
    draw_tracked_text(
        draw,
        (pad_x - bbox[0], pad_y - bbox[1]),
        title,
        font=font,
        fill=accent,
        stroke_width=stroke,
        stroke_fill=accent,
        tracking=tracking,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path


def write_logo_overlay(path: Path, logo_path: Path, config: dict[str, Any]) -> Path:
    edit = config.get("radioEdit", {})
    logo_height = int(edit.get("logoHeight", 120))
    pad_x = int(edit.get("logoBoxPaddingX", 24))
    pad_y = int(edit.get("logoBoxPaddingY", 16))
    logo = Image.open(logo_path).convert("RGBA")
    if logo.height > 0:
        logo_width = max(1, round(logo.width * logo_height / logo.height))
        logo = logo.resize((logo_width, logo_height), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (logo.width + pad_x * 2, logo.height + pad_y * 2), (255, 255, 255, 255))
    canvas.alpha_composite(logo, (pad_x, pad_y))
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path)
    return path


def render_caption_overlay(
    path: Path,
    lines: tuple[str, ...],
    config: dict[str, Any],
    *,
    role: str,
) -> tuple[int, int]:
    edit = config.get("radioEdit", {})
    font_size = int(edit.get("subtitleFontSize", 80))
    pad_x = int(edit.get("subtitleBoxPadding", 18))
    pad_y = int(edit.get("subtitlePadY", 10))
    line_gap = int(edit.get("subtitleLineGap", 6))
    radius = int(edit.get("subtitleRadius", 10))
    stroke = int(edit.get("subtitleStrokeWidth", 0))
    tracking = int(edit.get("subtitleTracking", 4))
    opacity = float(edit.get("subtitleBoxOpacity", 0.73))
    role_color_key = "hasegawaSubtitleBoxColor" if role == "interviewer" else "hanaokaSubtitleBoxColor"
    default_color = "#E85AA3" if role == "interviewer" else "#2FAE66"
    box_fill = hex_to_rgba(str(edit.get(role_color_key, default_color)), opacity)
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
            font=font,
            fill=text_fill,
            stroke_width=stroke,
            stroke_fill=text_fill,
            tracking=tracking,
        )
        y += box_h + line_gap
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return image.width, image.height


def write_caption_overlays(
    output_dir: Path,
    events: list[dict[str, Any]],
    config: dict[str, Any],
    project_root: Path,
) -> tuple[Path, list[dict[str, Any]]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    for old in output_dir.glob("caption_*.png"):
        if old.is_file():
            old.unlink()
    items: list[dict[str, Any]] = []
    for index, event in enumerate(events, start=1):
        filename = f"caption_{index:03d}.png"
        path = output_dir / filename
        lines = tuple(str(event["text"]).splitlines())
        width, height = render_caption_overlay(path, lines, config, role=str(event["role"]))
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


def ffmpeg_filter(
    ass_path: Path,
    config: dict[str, Any],
    project_root: Path,
    *,
    logo_index: int | None = None,
    title_index: int | None = None,
) -> str:
    edit = config.get("radioEdit", {})
    width = int(edit.get("targetWidth", 1920))
    height = int(edit.get("targetHeight", 1080))
    ass_relative = ass_path.relative_to(project_root).as_posix()
    filters = [
        f"[0:v]split=2[bgsrc][fgsrc]",
        f"[bgsrc]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},boxblur=24:1,eq=brightness=-0.08:saturation=0.9[bg]",
        f"[fgsrc]scale={width}:{height}:force_original_aspect_ratio=decrease[fg]",
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,ass='{ass_relative}',setsar=1[vsub]",
    ]
    current = "vsub"
    if logo_index is not None:
        logo_height = int(edit.get("logoFrameHeight" if edit.get("logoBoxEnabled") else "logoHeight", edit.get("logoHeight", 82)))
        margin_x = int(edit.get("logoMarginX", 36))
        margin_y = int(edit.get("logoMarginY", 28))
        filters.append(f"[{logo_index}:v]scale=-1:{logo_height},format=rgba[logo]")
        filters.append(f"[{current}][logo]overlay=W-w-{margin_x}:{margin_y}[vlogo]")
        current = "vlogo"
    if title_index is not None:
        title_x = int(edit.get("titleX", 36))
        title_y = int(edit.get("titleY", 32))
        filters.append(f"[{title_index}:v]format=rgba[title]")
        filters.append(f"[{current}][title]overlay={title_x}:{title_y}[vtitle]")
        current = "vtitle"
    filters.append(f"[{current}]format=yuv420p[v]")
    return ";".join(filters)


def ffmpeg_png_overlay_filter(
    config: dict[str, Any],
    caption_items: list[dict[str, Any]],
    *,
    logo_index: int | None = None,
    title_index: int | None = None,
    caption_start_index: int,
) -> str:
    edit = config.get("radioEdit", {})
    width = int(edit.get("targetWidth", 1920))
    height = int(edit.get("targetHeight", 1080))
    filters = [
        f"[0:v]split=2[bgsrc][fgsrc]",
        f"[bgsrc]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},boxblur=24:1,eq=brightness=-0.08:saturation=0.9[bg]",
        f"[fgsrc]scale={width}:{height}:force_original_aspect_ratio=decrease[fg]",
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[vbase]",
    ]
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
        input_index = caption_start_index + offset
        label = f"cap{offset}"
        out_label = f"v{label}"
        start = float(item["start"])
        end = float(item["end"])
        filters.append(f"[{input_index}:v]format=rgba[{label}]")
        filters.append(
            f"[{current}][{label}]overlay=(W-w)/2:H-h-{margin_v}:"
            f"enable='between(t\\,{start:.3f}\\,{end:.3f})'[{out_label}]"
        )
        current = out_label
    filters.append(f"[{current}]format=yuv420p[v]")
    return ";".join(filters)


def ffmpeg_png_movie_overlay_filter(
    config: dict[str, Any],
    caption_items: list[dict[str, Any]],
    *,
    logo_index: int | None = None,
    title_index: int | None = None,
) -> str:
    edit = config.get("radioEdit", {})
    width = int(edit.get("targetWidth", 1920))
    height = int(edit.get("targetHeight", 1080))
    filters = [
        f"[0:v]split=2[bgsrc][fgsrc]",
        f"[bgsrc]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},boxblur=24:1,eq=brightness=-0.08:saturation=0.9[bg]",
        f"[fgsrc]scale={width}:{height}:force_original_aspect_ratio=decrease[fg]",
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[vbase]",
    ]
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
        source = str(item["file"]).replace("\\", "/").replace("'", r"\'")
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
    return ";\n".join(filters)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the static-image Tokyo Oasis radio subtitle video.")
    parser.add_argument("--project-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--no-render", action="store_true")
    parser.add_argument("--start", type=float, default=None)
    parser.add_argument("--end", type=float, default=None)
    parser.add_argument("--preview-duration", type=float, default=None)
    parser.add_argument("--preview-offset", type=float, default=0.0, help="Preview start offset in the cut timeline.")
    parser.add_argument("--preview-output", type=Path, default=None)
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    config = load_json(project_root / "project_state.json")
    source_audio = Path(config["assets"]["sourceAudio"])
    main_image = Path(config["assets"]["mainImage"])
    edit = config.get("radioEdit", {})
    logo_path = Path(str(edit.get("logoPath") or config.get("assets", {}).get("logo") or ""))
    transcript_path = project_root / "output" / "transcripts" / "manifest_sources" / "primary.json"
    if not transcript_path.exists():
        raise SystemExit(f"Transcript not found: {transcript_path}")
    transcript = load_json(transcript_path)
    segments = list(transcript.get("segments", []))
    if not segments:
        raise SystemExit("Transcript has no segments.")

    detected_start, start_reason = detect_cut_start(segments)
    detected_end, end_reason = detect_cut_end(segments)
    cut_start = float(args.start if args.start is not None else edit.get("cutStartSeconds", detected_start))
    cut_end = float(args.end if args.end is not None else edit.get("cutEndSeconds", detected_end))
    if cut_end <= cut_start:
        raise SystemExit(f"Invalid cut range: {cut_start} - {cut_end}")
    keep_ranges, remove_ranges = build_audio_keep_ranges(cut_start, cut_end, edit)
    source_duration = cut_end - cut_start
    duration = audio_timeline_duration(keep_ranges)

    roles_path = Path(str(edit.get("speakerRolesPath") or project_root / "output" / "reports" / "full_transcript_speaker_roles_lr_tuned.json"))
    roles_data = load_json(roles_path) if roles_path.exists() else {"roles": {}}
    roles = {str(key): str(value) for key, value in dict(roles_data.get("roles", {})).items()}
    corrections_path = Path(str(edit.get("transcriptCorrectionsPath") or project_root / "config" / "transcript_corrections.json"))
    corrections_data = load_json(corrections_path) if corrections_path.exists() else {}
    corrections = corrections_data.get("replacements", [])
    replacements = [item for item in corrections if isinstance(item, dict)]
    segment_overrides = normalize_int_key_map(corrections_data.get("segmentOverrides", {}))
    role_overrides = normalize_role_override_map(corrections_data.get("roleOverrides", {}))
    max_line_chars = int(edit.get("subtitleMaxLineChars", 20))
    source_events = build_caption_events(
        segments,
        roles,
        cut_start,
        cut_end,
        replacements,
        max_line_chars,
        segment_overrides=segment_overrides,
        role_overrides=role_overrides,
    )
    events = remap_events_to_keep_ranges(source_events, keep_ranges, cut_start)

    output_audio = project_root / "output" / "audio" / "tokyo_oasis_20260205_hanaoka_cut.wav"
    output_srt = project_root / "output" / "subtitles" / "tokyo_oasis_20260205_hanaoka_cut.srt"
    output_ass = Path(config.get("render", {}).get("subtitleAssPath", project_root / "output" / "subtitles" / "tokyo_oasis_20260205_hanaoka_role_colored.ass"))
    if args.preview_output is not None:
        output_video = args.preview_output
    elif args.preview_duration is not None:
        output_video = project_root / "output" / "videos" / "tokyo_oasis_20260205_hanaoka_style_preview_90s.mp4"
    else:
        output_video = Path(config.get("render", {}).get("outputPath", project_root / "output" / "videos" / "tokyo_oasis_20260205_hanaoka_static_subtitled.mp4"))
    if not output_video.is_absolute():
        output_video = project_root / output_video
    title_overlay = project_root / "output" / "overlays" / "title" / "tokyo_oasis_hanaoka_title.png"
    logo_overlay = project_root / "output" / "overlays" / "logo" / "kiitos_logo_box.png"
    caption_overlay_dir = project_root / "output" / "overlays" / "static_radio_caption_png_overlays"
    report_path = project_root / "output" / "reports" / "static_radio_subtitle_build_report.json"

    write_srt(output_srt, events)
    write_ass(output_ass, events, config)
    write_title_overlay(title_overlay, config)
    logo_input_path = logo_path
    if logo_path.exists() and edit.get("logoBoxEnabled"):
        logo_input_path = write_logo_overlay(logo_overlay, logo_path, config)

    ffmpeg = str(config.get("tools", {}).get("ffmpeg", "ffmpeg"))
    preview_offset = max(0.0, min(duration, float(args.preview_offset or 0.0)))
    render_duration = duration
    if args.preview_duration is not None:
        render_duration = min(duration - preview_offset, max(0.0, float(args.preview_duration)))
    if args.preview_duration is None:
        overlay_events = events
    else:
        preview_end = preview_offset + render_duration
        overlay_events = []
        for event in events:
            event_start = float(event["start"])
            event_end = float(event["end"])
            if event_start >= preview_end or event_end <= preview_offset:
                continue
            adjusted = dict(event)
            adjusted["start"] = round(max(0.0, event_start - preview_offset), 3)
            adjusted["end"] = round(min(render_duration, event_end - preview_offset), 3)
            overlay_events.append(adjusted)
    caption_manifest, caption_items = write_caption_overlays(caption_overlay_dir, overlay_events, config, project_root)
    write_cut_audio(ffmpeg, source_audio, output_audio, keep_ranges, project_root)

    render_command: list[str] | None = None
    if not args.no_render:
        output_video.parent.mkdir(parents=True, exist_ok=True)
        extra_inputs: list[str] = []
        logo_index: int | None = None
        title_index: int | None = None
        next_input_index = 2
        if logo_input_path.exists():
            logo_index = next_input_index
            next_input_index += 1
            extra_inputs.extend(["-loop", "1", "-i", str(logo_input_path)])
        if title_overlay.exists():
            title_index = next_input_index
            next_input_index += 1
            extra_inputs.extend(["-loop", "1", "-i", str(title_overlay)])
        caption_start_index = next_input_index
        if args.preview_duration is not None:
            for item in caption_items:
                caption_path = project_root / str(item["file"])
                extra_inputs.extend(["-loop", "1", "-i", str(caption_path)])
                next_input_index += 1
            filter_graph = ffmpeg_png_overlay_filter(
                config,
                caption_items,
                logo_index=logo_index,
                title_index=title_index,
                caption_start_index=caption_start_index,
            )
            filter_args = ["-filter_complex", filter_graph]
        else:
            filter_graph = ffmpeg_png_movie_overlay_filter(
                config,
                caption_items,
                logo_index=logo_index,
                title_index=title_index,
            )
            filter_script_path = caption_overlay_dir / "filter_complex_full.ffmpeg"
            filter_script_path.write_text(filter_graph, encoding="utf-8")
            filter_args = ["-filter_complex_script", str(filter_script_path)]
        audio_input_args = ["-i", str(output_audio)]
        if args.preview_duration is not None and preview_offset > 0:
            audio_input_args = ["-ss", f"{preview_offset:.3f}", "-i", str(output_audio)]
        render_command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-loop",
            "1",
            "-framerate",
            str(config.get("render", {}).get("outputFps", "30000/1001")),
            "-i",
            str(main_image),
            *audio_input_args,
            *extra_inputs,
            *filter_args,
            "-map",
            "[v]",
            "-map",
            "1:a",
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
            "-ar",
            "48000",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(output_video),
        ]
        run(render_command, cwd=project_root)

    kept_original_ids = set()
    merged_continuation_groups: list[list[Any]] = []
    seen_merged_groups: set[tuple[Any, ...]] = set()
    for event in events:
        ids = tuple(event.get("originalSegmentIds", [event.get("originalSegmentId")]))
        kept_original_ids.update(ids)
        if len(ids) > 1 and ids not in seen_merged_groups:
            seen_merged_groups.add(ids)
            merged_continuation_groups.append(list(ids))
    omitted_opening = [segment for segment in segments if float(segment.get("end", 0.0)) <= cut_start]
    omitted_ending = [segment for segment in segments if float(segment.get("start", 0.0)) >= cut_end]
    omitted_middle = [
        {
            "rangeStart": remove_range["start"],
            "rangeEnd": remove_range["end"],
            "segmentStart": segment.get("start"),
            "segmentEnd": segment.get("end"),
            "text": segment.get("text"),
        }
        for remove_range in remove_ranges
        for segment in segments
        if float(segment.get("end", 0.0)) > float(remove_range["start"])
        and float(segment.get("start", 0.0)) < float(remove_range["end"])
    ]
    role_counts = {
        "interviewer": sum(1 for event in events if event["role"] == "interviewer"),
        "interviewee": sum(1 for event in events if event["role"] == "interviewee"),
    }
    report = {
        "project": PROJECT_ID,
        "sourceAudio": str(source_audio),
        "mainImage": str(main_image),
        "transcript": str(transcript_path),
        "speakerRoles": str(roles_path),
        "transcriptCorrections": str(corrections_path) if corrections_path.exists() else "",
        "cutStartSeconds": cut_start,
        "cutEndSeconds": cut_end,
        "sourceTimelineDurationSeconds": round(source_duration, 3),
        "audioRemoveRangesSeconds": remove_ranges,
        "audioKeepRangesSeconds": [
            {"start": round(start, 3), "end": round(end, 3), "duration": round(end - start, 3)}
            for start, end in keep_ranges
        ],
        "durationSeconds": round(duration, 3),
        "detectedStartSeconds": detected_start,
        "detectedEndSeconds": detected_end,
        "startReason": str(edit.get("cutStartReason") or start_reason),
        "endReason": str(edit.get("cutEndReason") or end_reason),
        "subtitleEventCount": len(events),
        "keptOriginalSegmentCount": len(kept_original_ids),
        "mergedContinuationSegmentGroups": merged_continuation_groups,
        "roleCounts": role_counts,
        "correctionCounts": {
            "replacements": len(replacements),
            "segmentOverrides": len(segment_overrides),
            "roleOverrides": len(role_overrides),
        },
        "outputs": {
            "audio": str(output_audio),
            "srt": str(output_srt),
            "ass": str(output_ass),
            "captionOverlayManifest": str(caption_manifest),
            "titleOverlay": str(title_overlay),
            "logo": str(logo_path) if logo_path.exists() else "",
            "logoOverlay": str(logo_input_path) if logo_input_path.exists() else "",
            "video": str(output_video) if not args.no_render else "",
        },
        "omittedOpeningPreview": [
            {"start": segment.get("start"), "end": segment.get("end"), "text": segment.get("text")}
            for segment in omitted_opening[-8:]
        ],
        "omittedEndingPreview": [
            {"start": segment.get("start"), "end": segment.get("end"), "text": segment.get("text")}
            for segment in omitted_ending[:10]
        ],
        "omittedMiddlePreview": omitted_middle[:20],
        "renderCommand": render_command,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(report_path), **report["outputs"], "durationSeconds": report["durationSeconds"], "roleCounts": role_counts}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
