from __future__ import annotations

import argparse
from functools import lru_cache
import json
import math
import subprocess
from pathlib import Path
import sys
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parents[1]
REPORTS = PROJECT_ROOT / "output" / "reports"
VIDEOS = PROJECT_ROOT / "output" / "videos"
OVERLAYS = PROJECT_ROOT / "output" / "overlays" / "test_project1_style"
DIAGNOSTICS = PROJECT_ROOT / "output" / "diagnostics"
FFMPEG_DEFAULT = Path(r"C:\ProgramData\chocolatey\lib\ffmpeg\tools\ffmpeg\bin\ffmpeg.exe")
FONT_FILE = Path(r"C:\Windows\Fonts\YuGothB.ttc")
CAPTION_FONT_FILE = Path(r"C:\Windows\Fonts\BIZ-UDGothicB.ttc")
LOGO_PATH = PROJECT_ROOT / "source" / "assets" / "LayerX_Logo_Horizontal_RGB_Color.png"

WIDTH = 1280
HEIGHT = 720
FPS = 30

THEME_PURPLE = "#5A2DEF"
THEME_PURPLE_FFMPEG = "0x5A2DEF"
PURPLE_DARK = THEME_PURPLE
PURPLE_MID = THEME_PURPLE
PURPLE_LIGHT = THEME_PURPLE
CAPTION_STOPS = [THEME_PURPLE, THEME_PURPLE, THEME_PURPLE]
TOP_STOPS = [THEME_PURPLE, THEME_PURPLE, THEME_PURPLE]
BOTTOM_STOPS = [THEME_PURPLE, THEME_PURPLE, THEME_PURPLE]
TITLE_STOPS = [THEME_PURPLE, THEME_PURPLE, THEME_PURPLE]
DIVIDER_COLOR = THEME_PURPLE_FFMPEG
CAPTION_FONT_SIZE = 76
CAPTION_BOX_MAX_WIDTH = 1248
CAPTION_HORIZONTAL_PADDING = 28
CAPTION_MAX_TEXT_WIDTH = CAPTION_BOX_MAX_WIDTH - CAPTION_HORIZONTAL_PADDING
TARGET_AUDIO_LUFS = -17.0
INTERVIEW_AUDIO_MEDIA_IDS = {"group_wide", "cam_person_01", "cam_person_02", "cam_person_03"}
INTERVIEW_MAIN_AUDIO_MEDIA_ID = "cam_person_02"

MEDIA_PATHS = {
    "group_wide": PROJECT_ROOT / "source" / "video" / "three people.mp4",
    "cam_person_01": PROJECT_ROOT / "source" / "video" / "person-left.mp4",
    "cam_person_02": PROJECT_ROOT / "source" / "video" / "person-middle.mp4",
    "cam_person_03": PROJECT_ROOT / "source" / "video" / "person-right.mp4",
    "company_movie": PROJECT_ROOT / "source" / "video" / "company-movie.mp4",
}

MEDIA_TO_ROLE = {
    "cam_person_01": "camera2",
    "cam_person_02": "camera3",
    "cam_person_03": "camera4",
    "group_wide": "master",
}

PERSON_TO_MEDIA = {
    "person_01": "cam_person_01",
    "person_02": "cam_person_02",
    "person_03": "cam_person_03",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def ffmpeg_path() -> str:
    if FFMPEG_DEFAULT.exists():
        return str(FFMPEG_DEFAULT)
    state_path = PROJECT_ROOT / "project_state.json"
    if state_path.exists():
        state = read_json(state_path)
        configured = str(((state.get("tools") or {}).get("ffmpeg")) or "").strip()
        if configured and Path(configured).exists() and "chocolatey\\bin" not in configured.lower():
            return configured
    return "ffmpeg"


def app_offsets() -> dict[str, float]:
    path = REPORTS / "app_sync_offsets.json"
    if not path.exists():
        return {"master": 0.0}
    payload = read_json(path)
    result = {"master": 0.0}
    for key, value in (payload.get("offsets") or {}).items():
        try:
            result[str(key)] = float(value)
        except (TypeError, ValueError):
            pass
    return result


def topic_titles() -> dict[str, str]:
    path = REPORTS / "semantic_marks.json"
    if not path.exists():
        return {}
    payload = read_json(path)
    return {
        str(topic["topic_id"]): str(topic["title"])
        for topic in payload.get("topics", [])
        if isinstance(topic, dict) and topic.get("topic_id") and topic.get("title")
    }


def people_map() -> dict[str, dict[str, Any]]:
    path = REPORTS / "people_map.json"
    if not path.exists():
        return {}
    payload = read_json(path)
    return {
        str(person["person_id"]): person
        for person in payload.get("people", [])
        if isinstance(person, dict) and person.get("person_id")
    }


def intro_profile_cards() -> dict[str, dict[str, Any]]:
    path = REPORTS / "interviewee_profile_cards.json"
    if not path.exists():
        return {}
    payload = read_json(path)
    profiles = payload.get("profiles") if isinstance(payload.get("profiles"), dict) else {}
    return {str(key): value for key, value in profiles.items() if isinstance(value, dict)}


def duration(event: dict[str, Any]) -> float:
    return max(0.01, float(event["timeline_end"]) - float(event["timeline_start"]))


def clip_source(event: dict[str, Any]) -> dict[str, Any]:
    source = event.get("source")
    if not isinstance(source, dict):
        raise ValueError(f"event {event.get('event_id')} has no source")
    return source


def audio_source(event: dict[str, Any]) -> dict[str, Any]:
    source = event.get("source") if isinstance(event.get("source"), dict) else {}
    reference = event.get("reference_source") if isinstance(event.get("reference_source"), dict) else {}
    if str(event.get("section") or "") == "bridge" or str(source.get("media_id") or "") == "company_movie":
        return source
    clock_source = reference if reference else source
    clock_media_id = str(clock_source.get("media_id") or source.get("media_id") or "group_wide")
    clock_in = float(clock_source.get("in") or source.get("in") or 0.0)
    offsets = app_offsets()
    source_role = MEDIA_TO_ROLE.get(clock_media_id, "master")
    target_role = MEDIA_TO_ROLE.get(INTERVIEW_MAIN_AUDIO_MEDIA_ID, "master")
    source_clock = clock_in - offsets.get(source_role, 0.0)
    audio_in = max(0.0, source_clock + offsets.get(target_role, 0.0))
    duration_value = duration(event)
    return {
        "media_id": INTERVIEW_MAIN_AUDIO_MEDIA_ID,
        "in": audio_in,
        "out": audio_in + duration_value,
        "policy": "single_interview_audio_source",
        "reference_media_id": clock_media_id,
    }


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    text = value.lstrip("#")
    return int(text[:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def gradient_image(size: tuple[int, int], stops: list[str], alpha: int = 255) -> Image.Image:
    width, height = size
    colors = [hex_to_rgb(stop) for stop in stops]
    image = Image.new("RGBA", (max(1, width), max(1, height)), (0, 0, 0, 0))
    pixels = image.load()
    for x in range(max(1, width)):
        t = 0.0 if width <= 1 else x / (width - 1)
        segment = min(len(colors) - 2, int(t * (len(colors) - 1)))
        local_start = segment / (len(colors) - 1)
        local_end = (segment + 1) / (len(colors) - 1)
        local_t = 0.0 if local_end == local_start else (t - local_start) / (local_end - local_start)
        c0 = colors[segment]
        c1 = colors[segment + 1]
        color = tuple(round(c0[i] + (c1[i] - c0[i]) * local_t) for i in range(3)) + (alpha,)
        for y in range(max(1, height)):
            pixels[x, y] = color
    return image


def rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return mask


def paste_gradient_box(canvas: Image.Image, box: tuple[int, int, int, int], stops: list[str], radius: int, alpha: int = 255, shadow: bool = True) -> None:
    x0, y0, x1, y1 = box
    width = max(1, x1 - x0)
    height = max(1, y1 - y0)
    mask = rounded_mask((width, height), radius)
    if shadow:
        shadow_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        shadow_rect = Image.new("RGBA", (width, height), (0, 0, 0, 48))
        shadow_layer.paste(shadow_rect, (x0, y0 + 4), mask)
        canvas.alpha_composite(shadow_layer.filter(ImageFilter.GaussianBlur(7)))
    rect = gradient_image((width, height), stops, alpha)
    canvas.paste(rect, (x0, y0), mask)


def paste_slanted_gradient(canvas: Image.Image, polygon: list[tuple[int, int]], stops: list[str], alpha: int = 255) -> None:
    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    mask = Image.new("L", (x1 - x0, y1 - y0), 0)
    local = [(x - x0, y - y0) for x, y in polygon]
    ImageDraw.Draw(mask).polygon(local, fill=255)
    rect = gradient_image((x1 - x0, y1 - y0), stops, alpha)
    canvas.paste(rect, (x0, y0), mask)


def fit_font(text: str, max_width: int, size: int, min_size: int, font_file: Path = FONT_FILE) -> ImageFont.FreeTypeFont:
    probe = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    draw = ImageDraw.Draw(probe)
    for font_size in range(size, min_size - 1, -2):
        font = ImageFont.truetype(str(font_file), font_size)
        bbox = draw.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= max_width:
            return font
    return ImageFont.truetype(str(font_file), min_size)


PROTECTED_CAPTION_TERMS = [
    "ドメインエキスパート",
    "プロダクトマネージャー",
    "バックオフィス",
    "エンジニア",
    "PDM",
    "AI",
    "LayerX",
    "開発",
    "言語化",
    "当たり前",
    "暗黙知",
    "慣行",
    "建設的",
    "プレッシャー",
    "リサーチ",
    "プロダクト",
    "キャリア",
    "引っ張って",
    "使いづらい",
    "めっちゃ",
    "めちゃめちゃ",
    "おすすめ",
    "絶対に逃がして",
    "ある種",
    "っていう",
    "そういう",
    "という",
    "AIを",
    "建設的な",
    "ものすごく",
    "ドメインの方",
    "何でも知ってそう",
    "知ってそうな感じ",
    "知ってるんじゃないか",
    "思われること",
    "ことの難しさ",
    "開発に関わる仕事をする中で",
    "今までやってきたんだな",
    "磨かれて成長",
    "いらないもの",
    "前提になってきている",
    "実現していきたい",
    "研ぎ澄まされてきている",
    "研ぎ澄まされてきているなという",
    "探し出してきてくれる",
    "探し出してきてくれるんですけど",
    "広く見れる",
    "ものすごくこれを言語化するのに",
    "抵抗感っていう",
    "ドメインの方めっちゃ調べてるんですよ",
    "実現していきたいのか",
    "こういう形で広く見れる",
    "めちゃめちゃおすすめだと思います",
    "プロダクトマネージャ",
    "言語化する",
    "実現して",
    "役割というか",
    "使うのが",
    "当時",
    "とって",
    "働く人にとって",
    "ハードル",
    "僕より",
    "労務",
    "初めて",
    "伝える",
    "関わった",
    "生産性",
    "状況",
    "理由",
    "できたら",
    "大丈夫",
    "機能",
    "専門家",
    "人事企画",
    "カルチャー",
    "プロダクト",
    "バックオフィス",
    "ドメイン知識",
    "開発チーム",
    "ドメインエキスパートの役割",
    "キャリア",
    "なくていい",
    "こうできたらいいのに",
    "結果",
    "経験",
    "事業",
    "チーム",
    "役割",
    "生産性",
    "問題意識",
    "関係ない",
    "迷った",
    "生きる",
    "カルチャー",
    "ベンチマーク",
    "採用体験",
    "壁打ち",
    "モヤモヤ",
    "フィードバック",
    "法律",
    "期待の高さ",
    "建設的に議論",
    "健全なプレッシャー",
    "制度や実務",
    "実務にどう落とし込むか",
    "体験込み",
    "スピード",
    "無視していないか",
    "変わらない",
    "作業",
    "画面",
    "確認時間",
    "働き方",
    "向き合う",
    "得られる",
    "変わっていく",
    "そのあたり",
    "あたり",
]


def protected_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for term in PROTECTED_CAPTION_TERMS:
        if len(term) > 14:
            continue
        start = 0
        while True:
            index = text.find(term, start)
            if index < 0:
                break
            spans.append((index, index + len(term)))
            start = index + len(term)
    return spans


def inside_protected_span(index: int, spans: list[tuple[int, int]]) -> bool:
    return any(start < index < end for start, end in spans)


def caption_cut_candidates(text: str, spans: list[tuple[int, int]]) -> list[int]:
    candidates = set()
    break_after = (
        "、",
        "。",
        "？",
        "！",
        " ",
        "とか",
        "けど",
        "ので",
        "から",
        "って",
        "には",
        "では",
        "とは",
        "という",
        "みたいな",
        "ですけど",
        "ですよ",
        "ですね",
        "ます",
        "ました",
        "これまで",
        "今まで",
        "こと",
        "意味",
        "自分",
        "ドメイン",
        "プロダクト",
        "機能",
        "経理",
        "労務",
        "AI",
        "「",
        "」",
        "なく",
        "だけでなく",
        "足すだけでなく",
        "と言える",
        "できたら",
        "いいのに",
        "関係ない",
        "見ること",
        "知識で",
        "ことで",
        "として",
        "ではなく",
        "だけでなく",
        "役割は",
    )
    for phrase in break_after:
        start = 0
        while True:
            index = text.find(phrase, start)
            if index < 0:
                break
            candidates.add(index + len(phrase))
            start = index + len(phrase)
    for start, end in spans:
        candidates.add(start)
        candidates.add(end)
    return sorted(index for index in candidates if 0 < index < len(text) and not inside_protected_span(index, spans))


@lru_cache(maxsize=4096)
def caption_text_width(text: str) -> int:
    probe = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    draw = ImageDraw.Draw(probe)
    font = ImageFont.truetype(str(CAPTION_FONT_FILE), CAPTION_FONT_SIZE)
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def caption_line_fits(text: str) -> bool:
    text_width = caption_text_width(text)
    return text_width + CAPTION_HORIZONTAL_PADDING <= CAPTION_BOX_MAX_WIDTH and text_width <= CAPTION_MAX_TEXT_WIDTH


def bad_caption_break(line: str) -> bool:
    return line.endswith(
        (
            "の",
            "に",
            "を",
            "が",
            "は",
            "と",
            "で",
            "も",
            "へ",
            "や",
            "から",
            "まで",
            "より",
            "という",
            "す",
            "し",
            "いけ",
            "あ",
            "い",
            "こ",
            "そ",
            "ち",
            "ちゃ",
            "仕",
            "け",
            "しゃっ",
            "ハー",
            "ハード",
            "怖",
            "背",
            "求めら",
            "使い",
            "当",
            "とっ",
            "高",
            "詳",
            "僕よ",
            "な",
            "なく「な",
            "なく",
            "い",
            "いけ",
            "結",
            "体",
            "採用体",
            "ベ",
            "壁打",
            "モヤ",
            "ユーザ",
            "自",
            "体",
            "多",
            "変",
            "向き合",
            "こうできたら",
            "関係",
            "生産性",
            "役",
            "チー",
            "チーム",
            "経",
            "事",
            "業",
            "作",
            "画",
            "働",
            "向",
            "込",
            "そ",
            "ちょ",
            "キャリア",
            "経験",
            "実現していきたいとかそ",
            "重",
            "動",
        )
    )


def bad_caption_start(line: str) -> bool:
    return line.startswith(("の", "に", "を", "が", "は", "と", "で", "も", "へ", "や", "って", "て", "する", "した", "った", "る", "れ", "ん", "け", "けて", "い", "ゃ", "ど", "さ", "しい", "り", "たり", "ード", "ドル", "ル", "味", "メイン", "く", "くて", "なく", "ない", "ら", "構", "験", "業", "ム", "割", "に強い", "ないもの", "ことも", "して", "なく建設的", "が健全", "くの人", "なる", "う時間", "ういった", "的な意味", "あたり", "を込めて", "するって", "要", "かす"))


def hard_bad_caption_break(line: str) -> bool:
    return line.endswith(
        (
            "いけ",
            "ちゃ",
            "仕",
            "け",
            "しゃっ",
            "ハー",
            "ハード",
            "怖",
            "背",
            "求めら",
            "使い",
            "当",
            "とっ",
            "高",
            "詳",
            "僕よ",
            "なく「な",
            "結",
            "採用体",
            "ベ",
            "壁打",
            "モヤ",
            "ユーザ",
            "多",
            "変",
            "向き合",
            "関係",
            "役",
            "チー",
            "経",
            "画",
            "働",
            "向",
            "込",
            "そ",
            "ちょ",
            "実現していきたいとかそ",
            "重",
            "動",
        )
    )


def natural_caption_boundary(left: str, right: str) -> bool:
    left = left.strip(" 、。！？")
    right = right.strip(" 、。！？")
    if not left or not right:
        return False
    return not hard_bad_caption_break(left) and not bad_caption_start(right)


def best_caption_cut(text: str, lines_left: int, spans: list[tuple[int, int]]) -> int:
    semantic_candidates = set(caption_cut_candidates(text, spans))
    raw_candidates = [
        index
        for index in range(1, len(text))
        if not inside_protected_span(index, spans) and caption_line_fits(text[:index].strip(" 、。"))
    ]
    if not raw_candidates:
        fallback = 1
        for index in range(1, len(text)):
            if inside_protected_span(index, spans):
                continue
            if caption_text_width(text[:index].strip(" 、。")) > CAPTION_MAX_TEXT_WIDTH:
                break
            fallback = index
        return fallback

    target = max(1, round(len(text) / max(1, lines_left)))

    def score(index: int) -> tuple[float, int]:
        first = text[:index].strip(" 、。")
        rest = text[index:].strip(" 、。")
        first_w = caption_text_width(first)
        rest_pressure = max(0, caption_text_width(rest) - CAPTION_MAX_TEXT_WIDTH * max(1, lines_left - 1))
        semantic_bonus = -8 if index in semantic_candidates else 0
        bad_break_penalty = 12 if bad_caption_break(first) else 0
        bad_start_penalty = 16 if bad_caption_start(rest) else 0
        short_line_penalty = 8 if len(first) < 6 else 0
        return (
            abs(index - target) + rest_pressure / 80 + bad_break_penalty + bad_start_penalty + short_line_penalty + semantic_bonus,
            -index,
        )

    return min(raw_candidates, key=score)


CAPTION_WRAP_OVERRIDES = {
    "ドメインエキスパートの役割というか": ["ドメインエキスパートの", "役割というか"],
    "やっぱりちょっと一瞬でもいいのでこういう形で広く見れる": ["やっぱりちょっと一瞬でもいいので", "こういう形で広く見れる"],
    "足すだけでなく「なくていい」と言えることも価値": ["足すだけでなく", "「なくていい」と言えることも価値"],
    "ルール調査だけでなくビジョンが必要になる": ["ルール調査だけでなく", "ビジョンが必要になる"],
    "実務家のプライドを無視していないかを気にしている": ["実務家のプライドを無視していないか", "気にしている"],
    "実務家のプライドを無視していないか": ["実務家のプライドを", "無視していないか"],
    "ドメインがない領域でも活躍できるスキルを身につけたい": ["ドメインがない領域でも", "活躍できるスキルを身につけたい"],
    "誰がやっても変わらない手作業が多い": ["誰がやっても変わらない", "手作業が多い"],
    "必要な情報を一つの画面で確認できるようにした": ["必要な情報を一つの画面で", "確認できるようにした"],
    "作業量を減らし確認時間を短縮する": ["作業量を減らし", "確認時間を短縮する"],
    "自分の経験がプロダクトに活かされる瞬間がやりがい": ["自分の経験がプロダクトに", "活かされる瞬間がやりがい"],
    "分析機能では経理の人たちの顔が浮かぶ": ["分析機能では", "経理の人たちの顔が浮かぶ"],
    "AIで作業者が分析できるようになる変化を支援したい": ["AIで作業者が分析できるようになる", "変化を支援したい"],
    "AIで専門家の経験を多くの人が得られるかもしれない": ["AIで専門家の経験を", "多くの人が得られるかもしれない"],
    "対人領域では人に聞きに来ることがある": ["対人領域では", "人に聞きに来ることがある"],
    "根本さんは経理や労務の経験を積んできた": ["根本さんは経理や労務の", "経験を積んできた"],
    "矢野さんはLayerXで初めて事業側の仕事に関わった": ["矢野さんはLayerXで初めて", "事業側の仕事に関わった"],
    "バックオフィスの生産性に強い問題意識があった": ["バックオフィスの生産性に", "強い問題意識があった"],
    "バクラクには「こうできたらいいのに」が少なかった": ["バクラクには", "「こうできたらいいのに」が少なかった"],
    "労務領域では自分の目で確かめたい感覚が強い": ["労務領域では自分の目で", "確かめたい感覚が強い"],
    "活躍できるスキルを身につけたい": ["活躍できるスキルを", "身につけたい"],
    "AIで作業者が分析できるようになる": ["AIで作業者が分析できる", "ようになる"],
    "「なくていい」と言えることも価値": ["「なくていい」と言えることも", "価値"],
}


def wrap_caption_text(text: str, max_chars: int = 13) -> list[str]:
    text = " ".join(str(text).replace("、", "").split())
    if text in CAPTION_WRAP_OVERRIDES:
        return CAPTION_WRAP_OVERRIDES[text]
    if caption_line_fits(text):
        return [text]
    spans = protected_spans(text)
    two_line_candidates = []
    for index in range(1, len(text)):
        if inside_protected_span(index, spans):
            continue
        first = text[:index].strip(" 、。")
        second = text[index:].strip(" 、。")
        if first and second and caption_line_fits(first) and caption_line_fits(second):
            if not natural_caption_boundary(first, second):
                continue
            semantic_bonus = -8 if index in set(caption_cut_candidates(text, spans)) else 0
            balance = abs(caption_text_width(first) - caption_text_width(second)) / 100
            two_line_candidates.append((balance + semantic_bonus, index))
    if two_line_candidates:
        _, cut = min(two_line_candidates)
        return [line for line in (text[:cut].strip(" 、。"), text[cut:].strip(" 、。")) if line]

    semantic_candidates = set(caption_cut_candidates(text, spans))
    semantic_line_candidates = []
    for index in semantic_candidates:
        first = text[:index].strip(" 、。")
        second = text[index:].strip(" 、。")
        if first and second and caption_line_fits(first) and natural_caption_boundary(first, second):
            semantic_line_candidates.append((caption_text_width(second), abs(index - len(text) / 2), index))
    if semantic_line_candidates:
        _, _, cut = min(semantic_line_candidates)
    else:
        cut = best_caption_cut(text, 2, spans)
    return [line for line in (text[:cut].strip(" 、。"), text[cut:].strip(" 、。")) if line][:2]


from caption_wrap_rules import wrap_caption_text  # noqa: E402


def condensed_text_image(
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int, int],
    scale_x: float = 0.92,
    *,
    faux_bold_offsets: tuple[tuple[int, int], ...] = ((0, 0),),
) -> Image.Image:
    probe = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    draw = ImageDraw.Draw(probe)
    bbox = draw.textbbox((0, 0), text, font=font)
    width = max(1, bbox[2] - bbox[0] + 16)
    height = max(1, bbox[3] - bbox[1] + 14)
    text_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    text_draw = ImageDraw.Draw(text_layer)
    base_x = 8 - bbox[0]
    base_y = 7 - bbox[1]
    for dx, dy in faux_bold_offsets:
        text_draw.text((base_x + dx, base_y + dy), text, font=font, fill=fill)
    target_width = max(1, round(width * scale_x))
    return text_layer.resize((target_width, height), Image.Resampling.LANCZOS)


def draw_gradient_text(layer: Image.Image, position: tuple[int, int], text: str, font: ImageFont.FreeTypeFont, fill: str) -> None:
    ImageDraw.Draw(layer).text(position, text, font=font, fill=fill)


def ease_out_cubic(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return 1.0 - (1.0 - value) ** 3


def title_text(event: dict[str, Any]) -> str:
    titles = topic_titles()
    semantic = read_json(REPORTS / "semantic_marks.json") if (REPORTS / "semantic_marks.json").exists() else {}
    for overlay in event.get("overlays", []):
        if not isinstance(overlay, dict) or overlay.get("type") != "topic_title":
            continue
        if overlay.get("text"):
            return str(overlay["text"])
        topic_id = overlay.get("topic_id")
        if topic_id and str(topic_id) in titles:
            return titles[str(topic_id)]
    section = str(event.get("section") or "")
    if section == "digest":
        return "Domain Expert Digest"
    if section == "main":
        ref = event.get("reference_source") if isinstance(event.get("reference_source"), dict) else {}
        ref_time = float(ref.get("in") or 0.0)
        for topic in semantic.get("topics", []):
            if float(topic.get("start") or 0.0) <= ref_time < float(topic.get("end") or 0.0):
                return str(topic.get("title") or "")
        topics = semantic.get("topics") if isinstance(semantic.get("topics"), list) else []
        if topics:
            return str(topics[0].get("title") or "")
    return ""


def draw_logo(canvas: Image.Image, section: str, is_split: bool = False) -> None:
    if not LOGO_PATH.exists():
        return
    logo = Image.open(LOGO_PATH).convert("RGBA")
    bbox = logo.getbbox()
    if bbox:
        logo = logo.crop(bbox)
    # Keep the LayerX logo identical across digest, main, single, and split cuts.
    # The digest opening is the visual reference requested for all sections.
    logo_w = 216
    logo_h = round(logo.height * logo_w / logo.width)
    logo = logo.resize((logo_w, logo_h), Image.Resampling.LANCZOS)
    pos = (18, round((102 - logo_h) / 2))
    canvas.alpha_composite(logo, pos)


def draw_style_overlay(event: dict[str, Any], output: Path) -> None:
    section = str(event.get("section") or "")
    layout = event.get("layout") if isinstance(event.get("layout"), dict) else {}
    is_split = layout.get("type") == "split_grid"
    canvas = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    if section == "digest":
        canvas.alpha_composite(gradient_image((WIDTH, 102), TOP_STOPS, 255), (0, 0))
        canvas.alpha_composite(gradient_image((WIDTH, 20), BOTTOM_STOPS, 255), (0, HEIGHT - 20))
        draw.polygon([(0, 0), (305, 0), (280, 102), (0, 102)], fill=(255, 255, 255, 255))

    if section != "bridge":
        draw_logo(canvas, section, is_split)
        title = title_text(event).strip()
        if title:
            font = fit_font(title, 680, 45, 34)
            title_image = condensed_text_image(title, font, (255, 255, 255, 255), 0.92)
            text_w = title_image.width
            text_h = title_image.height
            pad_x = 18
            box_h = 72
            box_w = min(720, text_w + pad_x * 2 + 32)
            x1 = WIDTH - 22
            x0 = x1 - box_w
            y0 = 16
            y1 = y0 + box_h
            if section != "digest":
                paste_slanted_gradient(canvas, [(x0 + 18, y0), (x1, y0), (x1 - 18, y1), (x0, y1)], TITLE_STOPS, 244)
            draw = ImageDraw.Draw(canvas)
            canvas.alpha_composite(title_image, (round(x0 + (box_w - text_w) / 2), round(y0 + (box_h - text_h) / 2)))
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)


def person_label(person_id: str) -> str:
    person = people_map().get(person_id, {})
    company = str(person.get("company") or "LayerX")
    role = str(person.get("role_title") or "").strip()
    name = str(person.get("display_name") or person_id)
    return f"{company} {role}  {name}".replace("  ", " ").strip()


def person_intro_lines(person_id: str) -> tuple[str, str]:
    person = people_map().get(person_id, {})
    department = str(person.get("department") or "").strip()
    role = str(person.get("role_title") or "").strip()
    name = str(person.get("display_name") or person_id).strip()
    descriptor = " ".join(part for part in (department, role) if part)
    return descriptor or "LayerX", name


def draw_shadow_text(draw: ImageDraw.ImageDraw, position: tuple[float, float], text: str, font: ImageFont.FreeTypeFont, fill: tuple[int, int, int, int]) -> None:
    x, y = position
    shadow = (80, 80, 80, max(80, fill[3] - 40))
    for dx, dy in ((2, 2), (3, 3)):
        draw.text((x + dx, y + dy), text, font=font, fill=shadow)
    draw.text((x, y), text, font=font, fill=fill)


def draw_white_intro_label(canvas: Image.Image, person_id: str, x: int, y: int, max_width: int, *, name_size: int, role_size: int, opacity: float = 1.0) -> None:
    role, name = person_intro_lines(person_id)
    draw = ImageDraw.Draw(canvas)
    role_font = fit_font(role, max_width, role_size, max(20, role_size - 10))
    name_font = fit_font(name, max_width, name_size, max(36, name_size - 18))
    alpha = round(255 * max(0.0, min(1.0, opacity)))
    draw_shadow_text(draw, (x, y), role, role_font, (255, 255, 255, alpha))
    draw_shadow_text(draw, (x, y + role_size + 12), name, name_font, (255, 255, 255, alpha))


def draw_caption(canvas: Image.Image, text: str, now: float, start: float, end: float, *, section: str = "") -> None:
    lines = wrap_caption_text(text)
    line_height = 104
    gap = 10
    stack_h = len(lines) * line_height + (len(lines) - 1) * gap
    # Main interview captions were visually too high. Keep digest captions at
    # the reference position, but lower main captions closer to the bottom.
    caption_bottom_y = 690 if section == "main" else 660
    y_base = caption_bottom_y - stack_h
    y_positions = [y_base + index * (line_height + gap) for index in range(len(lines))]
    draw = ImageDraw.Draw(canvas)
    for index, line in enumerate(lines):
        line_start = start + index * 0.12
        if now < line_start or now > end + 0.1:
            continue
        reveal = ease_out_cubic((now - line_start) / 0.583)
        opacity = min(1.0, max(0.0, (now - line_start) / 0.12))
        if now > end:
            opacity *= max(0.0, 1.0 - (now - end) / 0.1)
        font = ImageFont.truetype(str(CAPTION_FONT_FILE), CAPTION_FONT_SIZE)
        bbox = draw.textbbox((0, 0), line, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        scale_x = 0.98
        text_image = condensed_text_image(
            line,
            font,
            (255, 255, 255, round(255 * opacity)),
            scale_x,
            faux_bold_offsets=((0, 0), (1, 0)),
        )
        text_w = text_image.width
        text_h = text_image.height
        box_w = min(CAPTION_BOX_MAX_WIDTH, text_w + CAPTION_HORIZONTAL_PADDING)
        box_h = line_height
        x0 = round((WIDTH - box_w) / 2)
        y0 = y_positions[index]
        line_layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        paste_gradient_box(line_layer, (x0, y0, x0 + box_w, y0 + box_h), CAPTION_STOPS, 5, round(245 * opacity), True)
        text_x = x0 + (box_w - text_w) / 2
        text_y = y0 + (box_h - text_h) / 2
        line_layer.alpha_composite(text_image, (round(text_x), round(text_y)))
        visible_w = round(WIDTH * reveal)
        mask = Image.new("L", (WIDTH, HEIGHT), 0)
        ImageDraw.Draw(mask).rectangle((0, 0, visible_w, HEIGHT), fill=255)
        canvas.alpha_composite(Image.composite(line_layer, Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0)), mask))


def draw_nameplate(canvas: Image.Image, overlay: dict[str, Any], start: float, end: float, now: float) -> None:
    if not (start <= now <= end):
        return
    person_id = str(overlay["person_id"])
    if overlay.get("style_id") == "single_intro_white_text_reference":
        opacity = min(1.0, max(0.0, (now - start) / 0.2))
        draw_white_intro_label(canvas, person_id, 80, 500, 720, name_size=64, role_size=34, opacity=opacity)
        return
    label = person_label(person_id)
    font = fit_font(label, 1080, 48, 36)
    draw = ImageDraw.Draw(canvas)
    bbox = draw.textbbox((0, 0), label, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    box_w = min(1160, text_w + 76)
    box_h = 78
    x0 = 52
    y0 = 510
    paste_gradient_box(canvas, (x0, y0, x0 + box_w, y0 + box_h), [PURPLE_DARK, PURPLE_MID, PURPLE_LIGHT], 4, 244, True)
    draw.text((x0 + 38, y0 + (box_h - text_h) / 2 - 6), label, font=font, fill=(255, 255, 255, 255))


def draw_split_person_labels(canvas: Image.Image, overlay: dict[str, Any], start: float, end: float, now: float) -> None:
    if not (start <= now <= end):
        return
    person_ids = [str(item) for item in overlay.get("person_ids", [])]
    if len(person_ids) != 2:
        return
    opacity = min(1.0, max(0.0, (now - start) / 0.2))
    draw_white_intro_label(canvas, person_ids[0], 52, 500, 520, name_size=56, role_size=28, opacity=opacity)
    draw_white_intro_label(canvas, person_ids[1], 710, 500, 520, name_size=56, role_size=28, opacity=opacity)


def wrap_text_pixels(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    draw = ImageDraw.Draw(Image.new("RGBA", (10, 10), (0, 0, 0, 0)))
    lines: list[str] = []
    for paragraph in str(text).splitlines():
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        current = ""
        for char in paragraph:
            candidate = current + char
            bbox = draw.textbbox((0, 0), candidate, font=font)
            if current and bbox[2] - bbox[0] > max_width:
                lines.append(current)
                current = char
            else:
                current = candidate
        if current:
            lines.append(current)
    return lines


def draw_intro_profile_card(canvas: Image.Image, overlay: dict[str, Any], start: float, end: float, now: float) -> None:
    if not (start <= now <= end):
        return
    person_id = str(overlay.get("person_id") or "")
    profile = intro_profile_cards().get(person_id, {})
    if not profile:
        person = people_map().get(person_id, {})
        profile = {
            "display_name": person.get("display_name") or person_id,
            "department": person.get("department") or "LayerX",
            "role_title": person.get("role_title") or "",
            "body_lines": person.get("bio_bullets") or [],
        }
    opacity = min(1.0, max(0.0, (now - start) / 0.22))
    alpha = round(255 * opacity)
    shadow_alpha = round(70 * opacity)
    name = str(profile.get("display_name") or person_id)
    suffix = str(profile.get("name_suffix") or "").strip()
    department = str(profile.get("department") or "LayerX").strip()
    role = str(profile.get("role_title") or "").strip()
    name_text = name + (f" ({suffix})" if suffix else "")
    title_text_value = " | ".join(part for part in (department, role) if part)
    header_text = f"{name_text}｜{title_text_value}" if title_text_value else name_text
    body_lines = [str(line).strip() for line in profile.get("body_lines", []) if str(line).strip()]

    name_x, name_y, name_h = 16, 438, 78
    body_x, body_y, body_w, body_h = 28, 515, 1224, 180
    header_slant = 36
    header_pad_x = 36
    header_max_w = body_x + body_w - name_x

    layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((body_x, body_y + 5, body_x + body_w, body_y + body_h + 5), radius=5, fill=(0, 0, 0, shadow_alpha))
    layer.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(7)))

    body = Image.new("RGBA", (body_w, body_h), (255, 255, 255, round(248 * opacity)))
    body_mask = rounded_mask((body_w, body_h), 5)
    layer.paste(body, (body_x, body_y), body_mask)
    draw = ImageDraw.Draw(layer)
    header_font = fit_font(header_text, header_max_w - header_pad_x * 2 - header_slant, 48, 28, FONT_FILE)
    header_bbox = draw.textbbox((0, 0), header_text, font=header_font)
    header_text_w = header_bbox[2] - header_bbox[0]
    header_text_h = header_bbox[3] - header_bbox[1]
    name_w = min(header_max_w, max(620, header_text_w + header_pad_x * 2 + header_slant))
    paste_slanted_gradient(
        layer,
        [(name_x, name_y), (name_x + name_w, name_y), (name_x + name_w - header_slant, name_y + name_h), (name_x, name_y + name_h)],
        CAPTION_STOPS,
        round(248 * opacity),
    )
    header_visual_w = name_w - header_slant // 2
    header_x = name_x + max(24, (header_visual_w - header_text_w) / 2 - header_bbox[0])
    header_y = name_y + (name_h - header_text_h) / 2 - header_bbox[1]
    draw.text((header_x, header_y), header_text, font=header_font, fill=(255, 255, 255, alpha))

    body_font = ImageFont.truetype(str(FONT_FILE), 31)
    text = "\n".join(body_lines)
    wrapped = wrap_text_pixels(text, body_font, body_w - 58)
    if len(wrapped) > 4:
        wrapped = wrapped[:4]
    line_gap = 9
    line_h = 35
    block_h = len(wrapped) * line_h + max(0, len(wrapped) - 1) * line_gap
    y = body_y + max(18, (body_h - block_h) / 2)
    for line in wrapped:
        line_bbox = draw.textbbox((0, 0), line, font=body_font)
        line_w = line_bbox[2] - line_bbox[0]
        line_x = body_x + (body_w - line_w) / 2 - line_bbox[0]
        draw.text((line_x, y - line_bbox[1]), line, font=body_font, fill=(22, 33, 41, alpha))
        y += line_h + line_gap

    canvas.alpha_composite(layer)


def render_text_overlay(ffmpeg: str, event: dict[str, Any], output: Path) -> bool:
    captions = [overlay for overlay in event.get("overlays", []) if isinstance(overlay, dict) and overlay.get("type") == "caption" and overlay.get("text")]
    nameplates = [overlay for overlay in event.get("overlays", []) if isinstance(overlay, dict) and overlay.get("type") == "lower_third_person" and overlay.get("person_id")]
    split_labels = [overlay for overlay in event.get("overlays", []) if isinstance(overlay, dict) and overlay.get("type") == "split_person_labels"]
    profile_cards = [overlay for overlay in event.get("overlays", []) if isinstance(overlay, dict) and overlay.get("type") == "intro_profile_card"]
    if not captions and not nameplates and not split_labels and not profile_cards:
        return False
    dur = duration(event)
    total_frames = math.ceil(dur * FPS)
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "warning",
        "-nostdin",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgba",
        "-s",
        f"{WIDTH}x{HEIGHT}",
        "-r",
        str(FPS),
        "-i",
        "-",
        "-an",
        "-c:v",
        "qtrle",
        str(output),
    ]
    process = subprocess.Popen(command, cwd=WORKSPACE_ROOT, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    assert process.stdin is not None
    write_error: OSError | None = None
    try:
        for frame_index in range(total_frames):
            now = frame_index / FPS
            canvas = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
            for overlay in captions:
                draw_caption(canvas, str(overlay["text"]), now, float(overlay.get("start") or 0.0), float(overlay.get("end") or dur), section=str(event.get("section") or ""))
            for overlay in nameplates:
                draw_nameplate(canvas, overlay, float(overlay.get("start") or 0.0), float(overlay.get("end") or dur), now)
            for overlay in split_labels:
                draw_split_person_labels(canvas, overlay, float(overlay.get("start") or 0.0), float(overlay.get("end") or dur), now)
            for overlay in profile_cards:
                draw_intro_profile_card(canvas, overlay, float(overlay.get("start") or 0.0), float(overlay.get("end") or dur), now)
            try:
                process.stdin.write(canvas.tobytes())
            except OSError as exc:
                write_error = exc
                break
    finally:
        try:
            process.stdin.close()
        except OSError:
            pass
    stderr = b""
    if process.stderr is not None:
        stderr = process.stderr.read()
    return_code = process.wait()
    if write_error is not None or return_code != 0:
        message = stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"text overlay render failed for {event.get('event_id')}: {write_error or return_code}; ffmpeg stderr: {message}")
    return True


def color_match_filter(media_id: str) -> str:
    if media_id in {"cam_person_01", "cam_person_02", "cam_person_03"}:
        return ",eq=saturation=0.72:contrast=0.92:brightness=0.025:gamma=1.03"
    return ""


def source_skip_sec(event: dict[str, Any]) -> float:
    if str(event.get("event_id") or "") == "digest_001":
        return 0.45
    return 0.0


def segment_audio_filter_chain(media_id: str) -> str:
    if media_id not in INTERVIEW_AUDIO_MEDIA_IDS:
        return "aresample=48000"
    return (
        "highpass=f=85,"
        "lowpass=f=10500,"
        "afftdn=nr=18:nf=-32:tn=1:rf=-44,"
        "anlmdn=s=0.00035:p=0.002:r=0.006:m=11,"
        "acompressor=threshold=-30dB:ratio=2.4:attack=6:release=130:makeup=3,"
        "dynaudnorm=f=180:g=7:p=0.90:m=8,"
        "aresample=48000"
    )


def final_audio_filter_chain() -> str:
    loudnorm = f"loudnorm=I={TARGET_AUDIO_LUFS}:TP=-1.5:LRA=11"
    return (
        "highpass=f=70,"
        "lowpass=f=12000,"
        "afftdn=nr=10:nf=-38:tn=1:rf=-48,"
        "acompressor=threshold=-26dB:ratio=2.2:attack=5:release=140:makeup=2,"
        "dynaudnorm=f=180:g=7:p=0.90:m=8,"
        f"{loudnorm}"
    )


def single_person_crop_filter(event: dict[str, Any], media_id: str) -> str | None:
    layout = event.get("layout") if isinstance(event.get("layout"), dict) else {}
    crop_mode = str(layout.get("crop_mode") or "")
    if media_id not in {"cam_person_01", "cam_person_02", "cam_person_03"}:
        return None
    if crop_mode not in {"person_centered", "single_intro_reference_fullscreen"}:
        return None
    profile = SPLIT_FACE_PROFILES.get(media_id)
    if not profile:
        return None
    scale_h = int(profile.get("single_scale_h") or 900)
    scale = scale_h / 1080
    scaled_w = even_width_for_height(scale_h)
    target_face_x = 640
    target_face_y = float(profile.get("single_target_face_y") or 245)
    crop_x = round(float(profile["face_center_x"]) * scale - target_face_x)
    crop_y = round(float(profile["face_center_y"]) * scale - target_face_y)
    crop_x = max(0, min(crop_x, max(0, scaled_w - WIDTH)))
    crop_y = max(0, min(crop_y, max(0, scale_h - HEIGHT)))
    return (
        f"scale=-2:{scale_h}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT}:{crop_x}:{crop_y}{color_match_filter(media_id)},setsar=1,setpts=PTS-STARTPTS"
    )


def base_video_filter(event: dict[str, Any], media_id: str) -> str:
    section = str(event.get("section") or "")
    if section == "bridge":
        return "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,setpts=PTS-STARTPTS"
    single_filter = single_person_crop_filter(event, media_id)
    if single_filter:
        if section == "digest":
            return f"{single_filter}[scaled];color=c=black:s=1280x720:r=30:d={{dur}}[canvas];[canvas][scaled]overlay=0:69:format=auto"
        return single_filter
    if section == "digest":
        return f"scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720{color_match_filter(media_id)},setsar=1,setpts=PTS-STARTPTS[scaled];color=c=black:s=1280x720:r=30:d={{dur}}[canvas];[canvas][scaled]overlay=0:69:format=auto"
    return f"scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720{color_match_filter(media_id)},setsar=1,setpts=PTS-STARTPTS"


def synced_media_start(media_id: str, master_time: float, offsets: dict[str, float]) -> float:
    role = MEDIA_TO_ROLE.get(media_id, "master")
    return max(0.0, master_time + offsets.get(role, 0.0))


def split_media_ids(event: dict[str, Any]) -> list[str]:
    layout = event.get("layout") if isinstance(event.get("layout"), dict) else {}
    media_ids = layout.get("media_ids")
    if isinstance(media_ids, list):
        return [str(media_id) for media_id in media_ids if str(media_id) in MEDIA_PATHS]
    return []


def split_divider_chain(media_count: int) -> str:
    width = 8
    if media_count == 2:
        return f",drawbox=x={640 - width // 2}:y=0:w={width}:h=720:color={DIVIDER_COLOR}@1:t=fill"
    if media_count == 3:
        return f",drawbox=x={426 - width // 2}:y=0:w={width}:h=720:color={DIVIDER_COLOR}@1:t=fill,drawbox=x={853 - width // 2}:y=0:w={width}:h=720:color={DIVIDER_COLOR}@1:t=fill"
    return ""


SPLIT_FACE_PROFILES = {
    # Original 1920x1080 ROI centers from the synced split-grid edit events.
    # These values keep faces close in size and on the same vertical band while
    # preserving enough shoulder room for the reference split composition.
    "cam_person_01": {"scale_h": 740, "face_center_x": 811, "face_center_y": 392, "target_face_y": 260, "single_scale_h": 900, "single_target_face_y": 255},
    "cam_person_02": {"scale_h": 770, "face_center_x": 1058.5, "face_center_y": 333, "target_face_y": 225, "single_scale_h": 900, "single_target_face_y": 245},
    "cam_person_03": {"scale_h": 730, "face_center_x": 1148.5, "face_center_y": 288.5, "single_scale_h": 900, "single_target_face_y": 240},
}


def even_width_for_height(height: int) -> int:
    width = round(height * 16 / 9)
    return width if width % 2 == 0 else width + 1


def split_crop_profile(media_id: str, panel_width: int) -> tuple[int, int, int]:
    profile = SPLIT_FACE_PROFILES.get(media_id, {"scale_h": 720, "face_center_x": 960, "face_center_y": 330})
    scale_h = int(profile["scale_h"])
    scale = scale_h / 1080
    scaled_w = even_width_for_height(scale_h)
    target_face_x = panel_width / 2
    target_face_y = float(profile.get("target_face_y", 205))
    crop_x = round(float(profile["face_center_x"]) * scale - target_face_x)
    crop_y = round(float(profile["face_center_y"]) * scale - target_face_y)
    crop_x = max(0, min(crop_x, max(0, scaled_w - panel_width)))
    crop_y = max(0, min(crop_y, max(0, scale_h - 720)))
    return scale_h, crop_x, crop_y


def split_panel_filter(index: int, media_id: str, panel_width: int) -> str:
    scale_h, crop_x, crop_y = split_crop_profile(media_id, panel_width)
    if scale_h < 720:
        y_pad = (720 - scale_h) // 2
        return (
            f"[{index}:v]scale=-2:{scale_h}:force_original_aspect_ratio=increase,"
            f"crop={panel_width}:{scale_h}:{crop_x}:0,"
            f"pad={panel_width}:720:0:{y_pad}{color_match_filter(media_id)},setsar=1,setpts=PTS-STARTPTS[v{index}]"
        )
    return (
        f"[{index}:v]scale=-2:{scale_h}:force_original_aspect_ratio=increase,"
        f"crop={panel_width}:720:{crop_x}:{crop_y}{color_match_filter(media_id)},setsar=1,setpts=PTS-STARTPTS[v{index}]"
    )


def overlay_assets(ffmpeg: str, event: dict[str, Any], segment_id: str) -> tuple[Path, Path | None]:
    style_path = OVERLAYS / f"{segment_id}_style.png"
    text_path = OVERLAYS / f"{segment_id}_text.mov"
    draw_style_overlay(event, style_path)
    has_text = render_text_overlay(ffmpeg, event, text_path)
    return style_path, text_path if has_text else None


def render_segment(ffmpeg: str, event: dict[str, Any], output: Path, segment_id: str) -> None:
    layout = event.get("layout") if isinstance(event.get("layout"), dict) else {}
    if layout.get("type") == "split_grid" and split_media_ids(event):
        render_split_segment(ffmpeg, event, output, segment_id)
        return
    src = clip_source(event)
    aud = audio_source(event)
    video_path = MEDIA_PATHS.get(str(src.get("media_id")))
    audio_path = MEDIA_PATHS.get(str(aud.get("media_id")))
    if video_path is None or not video_path.exists():
        raise FileNotFoundError(f"Video media not available for preview: {src.get('media_id')}")
    if audio_path is None or not audio_path.exists():
        raise FileNotFoundError(f"Audio media not available for preview: {aud.get('media_id')}")
    dur = duration(event)
    skip = source_skip_sec(event)
    style_path, text_path = overlay_assets(ffmpeg, event, segment_id)
    filter_base = base_video_filter(event, str(src.get("media_id"))).format(dur=f"{dur:.3f}")
    inputs = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "warning",
        "-nostdin",
        "-y",
        "-ss",
        f"{float(src.get('in') or 0.0) + skip:.3f}",
        "-t",
        f"{dur:.3f}",
        "-i",
        str(video_path),
        "-ss",
        f"{float(aud.get('in') or 0.0) + skip:.3f}",
        "-t",
        f"{dur:.3f}",
        "-i",
        str(audio_path),
        "-loop",
        "1",
        "-i",
        str(style_path),
    ]
    if text_path:
        inputs.extend(["-i", str(text_path)])
    audio_filter = segment_audio_filter_chain(str(aud.get("media_id") or ""))
    if text_path:
        filter_complex = f"[0:v]{filter_base}[base];[base][2:v]overlay=0:0:format=auto[styled];[styled][3:v]overlay=0:0:format=auto[vout];[1:a]{audio_filter}[aout]"
    else:
        filter_complex = f"[0:v]{filter_base}[base];[base][2:v]overlay=0:0:format=auto[vout];[1:a]{audio_filter}[aout]"
    command = inputs + [
        "-filter_complex",
        filter_complex,
        "-map",
        "[vout]",
        "-map",
        "[aout]",
        "-t",
        f"{dur:.3f}",
        "-r",
        str(FPS),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "24",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-ar",
        "48000",
        "-shortest",
        "-movflags",
        "+faststart",
        str(output),
    ]
    subprocess.run(command, cwd=WORKSPACE_ROOT, check=True)


def render_split_segment(ffmpeg: str, event: dict[str, Any], output: Path, segment_id: str) -> None:
    aud = audio_source(event)
    audio_path = MEDIA_PATHS.get(str(aud.get("media_id")))
    if audio_path is None or not audio_path.exists():
        raise FileNotFoundError(f"Audio media not available for preview: {aud.get('media_id')}")
    media_ids = split_media_ids(event)
    dur = duration(event)
    master_in = float(
        event.get("sync_reference_master_sec")
        if event.get("sync_reference_master_sec") is not None
        else (event.get("reference_source") or {}).get("in") or (event.get("source") or {}).get("in") or 0.0
    )
    offsets = app_offsets()
    style_path, text_path = overlay_assets(ffmpeg, event, segment_id)
    command = [ffmpeg, "-hide_banner", "-loglevel", "warning", "-nostdin", "-y"]
    for media_id in media_ids:
        command.extend(["-ss", f"{synced_media_start(media_id, master_in, offsets):.3f}", "-t", f"{dur:.3f}", "-i", str(MEDIA_PATHS[media_id])])
    command.extend(["-ss", f"{float(aud.get('in') or master_in):.3f}", "-t", f"{dur:.3f}", "-i", str(audio_path)])
    command.extend(["-loop", "1", "-i", str(style_path)])
    if text_path:
        command.extend(["-i", str(text_path)])

    filters = []
    if len(media_ids) == 2:
        for index, media_id in enumerate(media_ids):
            filters.append(split_panel_filter(index, media_id, 640))
        stack = "[v0][v1]hstack=inputs=2"
    elif len(media_ids) == 3:
        for index, media_id in enumerate(media_ids):
            filters.append(split_panel_filter(index, media_id, 426))
        stack = "[v0][v1][v2]hstack=inputs=3,pad=1280:720:1:0"
    else:
        raise ValueError(f"Unsupported split media count: {len(media_ids)}")
    filters.append(f"{stack}{split_divider_chain(len(media_ids))}[base]")
    style_index = len(media_ids) + 1
    if text_path:
        text_index = style_index + 1
        filters.append(f"[base][{style_index}:v]overlay=0:0:format=auto[styled]")
        filters.append(f"[styled][{text_index}:v]overlay=0:0:format=auto[vout]")
    else:
        filters.append(f"[base][{style_index}:v]overlay=0:0:format=auto[vout]")
    filters.append(f"[{len(media_ids)}:a]{segment_audio_filter_chain(str(aud.get('media_id') or ''))}[aout]")
    command.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[vout]",
            "-map",
            "[aout]",
            "-t",
            f"{dur:.3f}",
            "-r",
            str(FPS),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "24",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ar",
            "48000",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )
    subprocess.run(command, cwd=WORKSPACE_ROOT, check=True)


def concat_segments(ffmpeg: str, segments: list[Path], output: Path) -> None:
    list_path = DIAGNOSTICS / "test_project1_style_preview_concat.txt"
    temp_output = output.with_name(f"{output.stem}_audio_unprocessed{output.suffix}")
    list_path.parent.mkdir(parents=True, exist_ok=True)
    list_path.write_text("".join(f"file '{path.as_posix()}'\n" for path in segments), encoding="utf-8")
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "warning",
            "-nostdin",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "24",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ar",
            "48000",
            "-movflags",
            "+faststart",
            str(temp_output),
        ],
        cwd=WORKSPACE_ROOT,
        check=True,
    )
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "warning",
            "-nostdin",
            "-y",
            "-i",
            str(temp_output),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0",
            "-c:v",
            "copy",
            "-af",
            final_audio_filter_chain(),
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ar",
            "48000",
            "-movflags",
            "+faststart",
            str(output),
        ],
        cwd=WORKSPACE_ROOT,
        check=True,
    )
    try:
        temp_output.unlink()
    except OSError:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Render LayerX preview with test-project-1 style overlays.")
    parser.add_argument("--max-events", type=int, default=None)
    parser.add_argument("--output", type=Path, default=VIDEOS / "preview_test_project1_style.mp4")
    parser.add_argument("--resume-existing", action="store_true", help="Reuse already rendered non-empty segment files.")
    args = parser.parse_args()
    plan = read_json(REPORTS / "edit_plan.json")
    if not (plan.get("validation") or {}).get("ready_for_preview"):
        raise SystemExit("edit_plan.json is not marked ready_for_preview")
    events = [event for event in plan.get("timeline", []) if isinstance(event, dict)]
    if args.max_events:
        events = events[: args.max_events]
    segment_dir = VIDEOS / "preview_test_project1_style_segments"
    segment_dir.mkdir(parents=True, exist_ok=True)
    if not args.resume_existing:
        for old_segment in segment_dir.glob("*.mp4"):
            old_segment.unlink()
    ffmpeg = ffmpeg_path()
    rendered = []
    for index, event in enumerate(events, start=1):
        segment_id = f"segment_{index:03d}_{event.get('event_id', 'event')}"
        segment_path = segment_dir / f"{segment_id}.mp4"
        if not (args.resume_existing and segment_path.exists() and segment_path.stat().st_size > 0):
            render_segment(ffmpeg, event, segment_path, segment_id)
        rendered.append(segment_path)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    concat_segments(ffmpeg, rendered, args.output)
    report = {
        "schema_version": "test_project1_style_preview_report.v1",
        "output": str(args.output),
        "segments": len(rendered),
        "style_reference": "projects/test-project-1 styled preview: sample-11 frame overlay + sample-1 catchphrase subtitle style",
        "notes": [
            "Digest uses opaque top/bottom bands and slanted white LayerX logo panel.",
            "Main section removes the full-width top/bottom bands completely.",
            "Captions are rendered as animated RGBA overlays with horizontal reveal and quick fade.",
            "Split dividers use the theme purple color and a thinner rule.",
            "Split crops align face scale and vertical head height across participants.",
            "White overlay text is rendered without black stroke outlines.",
            f"Interview audio uses one continuous {INTERVIEW_MAIN_AUDIO_MEDIA_ID} source across all interview video cuts, including the closing.",
        ],
    }
    write_json(REPORTS / "test_project1_style_preview_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
