from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


CAPTION_FONT_FILE = Path(r"C:\Windows\Fonts\BIZ-UDGothicB.ttc")
CAPTION_FONT_SIZE = 76
CAPTION_BOX_MAX_WIDTH = 1248
CAPTION_HORIZONTAL_PADDING = 28
CAPTION_MAX_TEXT_WIDTH = CAPTION_BOX_MAX_WIDTH - CAPTION_HORIZONTAL_PADDING

PROTECTED_CAPTION_TERMS = [
    "ドメインエキスパート",
    "プロダクトマネージャー",
    "プロダクトマネージャ",
    "プロダクトマーケティング",
    "バックオフィス",
    "エンジニア",
    "ユーザー",
    "LayerX",
    "PDM",
    "AI",
    "バクラク",
    "バクラクインテリジェンス",
    "言語化",
    "当たり前",
    "暗黙知",
    "慣行",
    "建設的",
    "プレッシャー",
    "リサーチ",
    "キャリア",
    "めちゃめちゃ",
    "おすすめ",
    "何でも知ってそう",
    "知ってそうな感じ",
    "こうできたらいいのに",
    "「こうできたらいいのに」",
    "実現していきたい",
    "研ぎ澄まされてきている",
    "探し出してきてくれる",
    "広く見れる",
    "健全なプレッシャー",
    "実務家のプライド",
    "始まる",
    "自動化",
    "動化",
    "こうできたらいいのに",
]

BREAK_AFTER = (
    "。",
    "？",
    "！",
    " ",
    "とか",
    "けど",
    "ので",
    "から",
    "ため",
    "中で",
    "ところで",
    "ところ",
    "感じで",
    "感じが",
    "ことは",
    "ことが",
    "ことも",
    "ものが",
    "ものを",
    "場合は",
    "ときに",
    "時に",
    "として",
    "ではなく",
    "だけでなく",
    "みたいな",
    "という",
    "って",
    "ます",
    "ました",
    "です",
    "でした",
    "ですよ",
    "ですね",
    "自分で",
    "結局",
    "今でいう",
    "最初は",
    "結果的に",
    "2年半くらい前から",
    "始まる",
    "やりたいことを",
    "なるべく",
    "一つの機能の中に",
    "持ち込んであげる",
    "みたいなのは",
    "意識して",
    "作れた",
    "機能なんじゃないかな",
    "と思いますね",
    "ある種",
    "乗っかってれば",
    "いつの間にか",
    "分析とかが",
    "できるように",
    "できるようになってたりとか",
)

BREAK_BEFORE = (
    "ドメインエキスパート",
    "プロダクトマネージャー",
    "プロダクトマーケティング",
    "バックオフィス",
    "エンジニア",
    "ユーザー",
    "LayerX",
    "AI",
    "PDM",
    "開発",
    "経理",
    "労務",
    "自分",
    "お客様",
    "製品",
    "自動化",
    "動化",
    "始まる",
)

BAD_LINE_ENDINGS = (
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
    "な",
    "い",
    "こ",
    "そ",
    "ち",
    "ま",
    "し",
    "れ",
    "さ",
    "的",
    "結果",
    "自",
    "事",
    "業",
    "経",
    "働",
    "向",
    "込",
    "ユー",
    "プロダクトマー",
)

HARD_BAD_LINE_ENDINGS = (
    "いけ",
    "ちゃ",
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
    "ございま",
    "お願いしま",
    "ありま",
    "なりま",
    "思いま",
    "しま",
    "ユー",
    "ザ",
    "プロダクトマー",
    "マー",
    "ケティン",
    "うや",
    "みたい",
)

BAD_LINE_STARTS = (
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
    "って",
    "て",
    "する",
    "した",
    "った",
    "る",
    "れ",
    "ん",
    "け",
    "けて",
    "ゃ",
    "ど",
    "さ",
    "しい",
    "り",
    "たり",
    "す",
    "です",
    "ます",
    "ました",
    "ございます",
    "ザー",
    "ケティング",
    "うやって",
    "的に",
    "業側",
    "ム",
    "割",
    "ないもの",
    "ことも",
    "して",
    "なる",
    "要",
    "な",
)

SMALL_KANA = set("ゃゅょぁぃぅぇぉっャュョァィゥェォッ")


def clean_caption_text(text: str) -> str:
    return " ".join(str(text).replace("、", "").split()).strip()


def _is_katakana(char: str) -> bool:
    return bool(re.match(r"[ァ-ヴー]", char))


def _is_latinish(char: str) -> bool:
    return bool(re.match(r"[A-Za-z0-9_+.#/-]", char))


def _merge_spans(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not spans:
        return []
    spans = sorted(spans)
    merged = [spans[0]]
    for start, end in spans[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def protected_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for term in PROTECTED_CAPTION_TERMS:
        start = 0
        while True:
            index = text.find(term, start)
            if index < 0:
                break
            spans.append((index, index + len(term)))
            start = index + len(term)
    for match in re.finditer(r"[ァ-ヴー][ァ-ヴー・]*[ァ-ヴー]", text):
        spans.append(match.span())
    for match in re.finditer(r"[A-Za-z0-9][A-Za-z0-9_+.#/-]*", text):
        spans.append(match.span())
    return _merge_spans([(start, end) for start, end in spans if end - start > 1])


def inside_protected_span(index: int, spans: list[tuple[int, int]]) -> bool:
    return any(start < index < end for start, end in spans)


def invalid_caption_cut(text: str, index: int, spans: list[tuple[int, int]] | None = None) -> bool:
    if index <= 0 or index >= len(text):
        return True
    spans = spans if spans is not None else protected_spans(text)
    if inside_protected_span(index, spans):
        return True
    left = text[index - 1]
    right = text[index]
    if right in SMALL_KANA or right == "ー" or left == "ー":
        return True
    if _is_katakana(left) and _is_katakana(right):
        return True
    if _is_latinish(left) and _is_latinish(right):
        return True
    return False


def caption_cut_candidates(text: str, spans: list[tuple[int, int]]) -> list[int]:
    candidates = set()
    for phrase in BREAK_AFTER:
        start = 0
        while True:
            index = text.find(phrase, start)
            if index < 0:
                break
            candidates.add(index + len(phrase))
            start = index + len(phrase)
    for phrase in BREAK_BEFORE:
        start = 0
        while True:
            index = text.find(phrase, start)
            if index < 0:
                break
            candidates.add(index)
            start = index + len(phrase)
    for start, end in spans:
        candidates.add(start)
        candidates.add(end)
    return sorted(index for index in candidates if 0 < index < len(text) and not invalid_caption_cut(text, index, spans))


@lru_cache(maxsize=8192)
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
    line = clean_caption_text(line)
    return line.endswith(BAD_LINE_ENDINGS) or hard_bad_caption_break(line)


def bad_caption_start(line: str) -> bool:
    return clean_caption_text(line).startswith(BAD_LINE_STARTS)


def hard_bad_caption_break(line: str) -> bool:
    line = clean_caption_text(line)
    return line.endswith(HARD_BAD_LINE_ENDINGS)


def natural_caption_boundary(left: str, right: str) -> bool:
    left = clean_caption_text(left).strip("。！？")
    right = clean_caption_text(right).strip("。！？")
    if not left or not right:
        return False
    text = left + right
    spans = protected_spans(text)
    if invalid_caption_cut(text, len(left), spans):
        return False
    if hard_bad_caption_break(left) or bad_caption_start(right):
        return False
    return True


def _two_line_cut(text: str) -> int | None:
    spans = protected_spans(text)
    semantic_candidates = set(caption_cut_candidates(text, spans))
    candidates = []
    for index in range(1, len(text)):
        if invalid_caption_cut(text, index, spans):
            continue
        first = text[:index].strip(" 。！？")
        second = text[index:].strip(" 。！？")
        if not first or not second:
            continue
        if not caption_line_fits(first) or not caption_line_fits(second):
            continue
        if not natural_caption_boundary(first, second):
            continue
        semantic_bonus = -10 if index in semantic_candidates else 0
        width_balance = abs(caption_text_width(first) - caption_text_width(second)) / 120
        char_balance = abs(len(first) - len(second)) / 6
        candidates.append((width_balance + char_balance + semantic_bonus, index))
    if not candidates:
        return None
    return min(candidates, key=lambda item: item[0])[1]


def best_caption_cut(text: str, lines_left: int, spans: list[tuple[int, int]]) -> int:
    text = clean_caption_text(text)
    semantic_candidates = set(caption_cut_candidates(text, spans))
    target_width = CAPTION_MAX_TEXT_WIDTH * max(1, lines_left)
    candidates = []
    for index in semantic_candidates:
        if invalid_caption_cut(text, index, spans):
            continue
        first = text[:index].strip(" 。！？")
        rest = text[index:].strip(" 。！？")
        if not first or not rest:
            continue
        if not caption_line_fits(first) and _two_line_cut(first) is None:
            continue
        if not natural_caption_boundary(first, rest):
            continue
        pressure = max(0, caption_text_width(rest) - target_width) / 120
        candidates.append((pressure - len(first) / 10, index))
    if candidates:
        return min(candidates, key=lambda item: item[0])[1]
    return len(text)


CAPTION_WRAP_OVERRIDES = {
    "ドメインエキスパートの役割というか": ["ドメインエキスパートの", "役割というか"],
    "不安が残ると結局ユーザーは自分で調べてしまう": ["不安が残ると結局", "ユーザーは自分で調べてしまう"],
    "やっぱりちょっと一瞬でもいいのでこういう形で広く見れる": ["やっぱりちょっと一瞬でもいいので", "こういう形で広く見れる"],
    "足すだけでなく「なくていい」と言えることも価値": ["足すだけでなく", "「なくていい」と言えることも価値"],
    "ルール調査だけでなくビジョンが必要になる": ["ルール調査だけでなく", "ビジョンが必要になる"],
    "実務家のプライドを無視していないかを気にしている": ["実務家のプライドを", "無視していないかを気にしている"],
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
    "「こうできたらいいのに」が少なかった": ["「こうできたらいいのに」が", "少なかった"],
    "労務領域では自分の目で確かめたい感覚が強い": ["労務領域では自分の目で", "確かめたい感覚が強い"],
    "活躍できるスキルを身につけたい": ["活躍できるスキルを", "身につけたい"],
    "AIで作業者が分析できるようになる": ["AIで作業者が分析できる", "ようになる"],
    "「なくていい」と言えることも価値": ["「なくていい」と言えることも", "価値"],
}

CAPTION_UNIT_OVERRIDES = {
    "ドメインエキスパートの役割というか重要性みたいなもので": [
        "ドメインエキスパートの役割というか",
        "重要性みたいなもので",
    ],
    "バクラクには「こうできたらいいのに」が少なかった": [
        "バクラクには",
        "「こうできたらいいのに」が少なかった",
    ],
}


def wrap_caption_text(text: str, max_chars: int = 13) -> list[str]:
    text = clean_caption_text(text)
    if not text:
        return []
    if text in CAPTION_WRAP_OVERRIDES:
        override = CAPTION_WRAP_OVERRIDES[text]
        if all(caption_line_fits(line) for line in override):
            return override
    if caption_line_fits(text):
        return [text]
    cut = _two_line_cut(text)
    if cut is None:
        return [text]
    return [line for line in (text[:cut].strip(" 。！？"), text[cut:].strip(" 。！？")) if line]


def unit_fits(text: str) -> bool:
    lines = wrap_caption_text(text)
    return 1 <= len(lines) <= 2 and all(caption_line_fits(line) for line in lines)


def split_caption_units(text: str) -> list[str]:
    remaining = clean_caption_text(text)
    if not remaining:
        return []
    if remaining in CAPTION_UNIT_OVERRIDES:
        return CAPTION_UNIT_OVERRIDES[remaining]
    if remaining in CAPTION_WRAP_OVERRIDES:
        override = CAPTION_WRAP_OVERRIDES[remaining]
        if all(caption_line_fits(line) for line in override):
            return [remaining]
    units: list[str] = []
    while remaining:
        if unit_fits(remaining):
            units.append(remaining)
            break
        spans = protected_spans(remaining)
        candidates = []
        for index in caption_cut_candidates(remaining, spans):
            prefix = remaining[:index].strip(" 。！？")
            rest = remaining[index:].strip(" 。！？")
            if not prefix or not rest:
                continue
            if not unit_fits(prefix):
                continue
            if not natural_caption_boundary(prefix, rest):
                continue
            remainder_pressure = max(0, caption_text_width(rest) - CAPTION_MAX_TEXT_WIDTH * 2) / 100
            candidates.append((len(prefix) - remainder_pressure, index, prefix, rest))
        if not candidates:
            cut = best_caption_cut(remaining, 2, spans)
            if cut >= len(remaining):
                units.append(remaining)
                break
            prefix = remaining[:cut].strip(" 。！？")
            rest = remaining[cut:].strip(" 。！？")
            if not prefix or not rest or not unit_fits(prefix):
                units.append(remaining)
                break
        else:
            _, _, prefix, rest = max(candidates, key=lambda item: (item[0], item[1]))
        units.append(prefix)
        remaining = rest
    return units
