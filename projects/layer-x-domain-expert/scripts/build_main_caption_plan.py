from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT_ROOT / "output" / "reports"
CAPTIONS_MD = REPORTS / "captions.md"
JST = timezone(timedelta(hours=9))


PEOPLE = {
    "person_01": {"name": "矢野", "screen_position": "left", "role": "interviewer"},
    "person_02": {"name": "根本", "screen_position": "middle", "role": "interviewee"},
    "person_03": {"name": "村田", "screen_position": "right", "role": "interviewee"},
}

DISPLAY_TEXT_OVERRIDES = {
    1: "ドメインエキスパートは開発チームの中での役割",
    3: "実務経験をプロダクト開発に持ち込む役割",
    4: "バックオフィスの生産性に強い問題意識があった",
    5: "決算期に終電で帰る状況は不健全だと思った",
    6: "バクラクには「こうできたらいいのに」が少なかった",
    7: "LayerXに惹かれた理由は開発に関われること",
    8: "開発は自分とは関係ないものだと思っていた",
    9: "経理一本のキャリアに迷ったタイミングだった",
    11: "LayerXのカルチャーをベンチマークしていた",
    12: "入口は採用体験や人事の勉強だった",
    14: "勤怠を作るなら面白そうだと思ってLayerXに来た",
    15: "開発に参画できる壁打ち相手として関われる",
    16: "PDMはプロダクト成長のために何でもやる人",
    18: "実務知識を活かせるなら挑戦できると思った",
    19: "家族には経理系の仕事だと説明していた",
    20: "共通点はドメイン知識で開発に関与すること",
    21: "労務を主務にしながら仕様検討にも深く関わる",
    22: "実務のモヤモヤをプロダクトに落とし込める",
    23: "違和感を出すことでプロダクトが良くなる",
    24: "フィードバックを良いものとして歓迎する文化がある",
    25: "違和感を言うだけでどんどん良いものになる",
    26: "PDMの仕事は日によって違う",
    27: "PDMはフェーズによって仕事内容が変わる",
    28: "一番大変だったのは当たり前を言語化すること",
    31: "当たり前の業務にも法律や会社ルールの背景がある",
    32: "何でも知っていそうに見える期待の高さが難しい",
    34: "LayerXのエンジニアはドメインをものすごく調べている",
    35: "専門家が一方的に教えるのではなく建設的に議論する",
    36: "「なんで？」を逃がさないことが健全なプレッシャーになる",
    38: "当たり前が開発の議論を通じて磨かれていく",
    39: "古い慣習を流さず一つひとつ調べることが大事",
    41: "労務領域では自分の目で確かめたい感覚が強い",
    42: "不安が残ると結局ユーザーは自分で調べてしまう",
    43: "ユーザーが不安なら自動化しても使われない",
    44: "機能で何を実現したいのかを体験込みで伝える",
    45: "全部やるとスピードも落ち画面も分かりにくくなる",
    46: "コア以外は落とす判断も必要",
    47: "ルール調査だけでなくビジョンが必要になる",
    48: "実務家のプライドを無視していないかを気にしている",
    49: "足すだけでなく「なくていい」と言えることも価値",
    50: "AIの情報を制度や実務にどう落とし込むかが重要",
    51: "ドメインエキスパートの役割とキャリアを聞いていく",
    52: "LayerXでは開発チームの中でドメイン知識を活かす",
    53: "LayerXでは開発チームに入り実務知識を活かす",
    54: "根本さんは経理や労務の経験を積んできた",
    55: "声をかけられたことが開発に関わるきっかけだった",
    56: "コードを書けなくても大丈夫かという感覚から始まった",
    57: "村田さんは社労士として外から助言する経験を積んだ",
    58: "事業会社の中から人事や労務に関わりたいと思った",
    59: "矢野さんはLayerXで初めて事業側の仕事に関わった",
    60: "最初はヒアリングから始まった",
    61: "最初は製品をどう伝えるかを中心に担当した",
    62: "二人が開発に関わった背景が対談のテーマ",
    64: "経理一本でどう生きるかという不安があった",
    65: "スタートアップで経理として伸びる難しさがあった",
    68: "LayerXのカルチャーでHRテックを作ることに興味を持った",
    70: "人事企画ではカルチャーを見ることも重要になる",
    71: "開発に関わることは少し違うキャリアへの一歩",
    73: "コードを書けなくても開発に関われると思えた",
    74: "PDMとしてまずは結果を出していきたい",
    75: "ドメインがない領域でも活躍できるスキルを身につけたい",
    76: "ドメインの貯金がなくなったときの怖さがある",
    77: "誰がやっても変わらない手作業が多い",
    78: "月次申告などの作業を減らしたい",
    79: "必要な情報を一つの画面で確認できるようにした",
    80: "作業量を減らし確認時間を短縮する",
    81: "自分の経験がプロダクトに活かされる瞬間がやりがい",
    82: "分析機能では経理の人たちの顔が浮かぶ",
    83: "AIで作業者が分析できるようになる変化を支援したい",
    84: "自動運転の先に新しい働き方がある",
    85: "AIで専門家の経験を多くの人が得られるかもしれない",
    86: "属人化は今後大きく変わっていく可能性がある",
    87: "働き方や時間の使い方そのものが変わっていく",
    88: "対人領域では人に聞きに来ることがある",
    89: "経理の役割はなくなるのではなく変わっていく",
    90: "人や現場に向き合う時間が増えていく",
    91: "バックオフィス経験者におすすめできるキャリア",
    92: "暗黙知が言語化され視野が広がる",
    93: "AIの活用や向き合い方も変わる",
}

EXCLUDED_CAPTION_NOS = {
    1,  # ドメインエキスパートは開発チームの中での役割
    51,  # ドメインエキスパートの役割とキャリアを聞いていく
    52,  # LayerXでは開発チームの中でドメイン知識を活かす
    53,  # LayerXでは開発チームに入り実務知識を活かす
    54,  # 根本さんは経理や労務の経験を積んできた
}

SUPPLEMENTAL_TARGET_GAP_SEC = 30.0
SUPPLEMENTAL_MIN_DISTANCE_SEC = 11.0
SUPPLEMENTAL_SKIP_WINDOWS = [
    (593.00, 623.52),  # Pre-introduction banter and setup checks.
    (623.52, 722.50),  # Interviewee self-introduction profile-card sequence.
]
SUPPLEMENTAL_KEYWORDS = (
    "AI",
    "PDM",
    "ドメイン",
    "エキスパート",
    "開発",
    "実務",
    "経理",
    "労務",
    "人事",
    "プロダクト",
    "キャリア",
    "価値",
    "重要",
    "役割",
    "ユーザー",
    "機能",
    "体験",
    "自動",
    "効率",
    "専門",
    "判断",
    "制度",
    "働き方",
)
SUPPLEMENTAL_NOISE_PATTERNS = (
    "ありがとうございます",
    "そうですね",
    "確かに",
    "大丈夫ですか",
    "はい",
    "えっと",
    "なんか",
    "ちょっと",
    "みたいな",
    "コーポレートっぽく",
    "砕けた感じ",
)


def now_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("、", "")).strip()


def compact_caption_text(text: str, max_chars: int = 96) -> str:
    text = clean_text(text)
    text = re.sub(r"^(ちなみに|ただ|でも|なので|だから|要は|そして|それで|この辺も|確かに)\s*", "", text)
    if len(text) <= max_chars:
        return text.rstrip("。")

    sentence_end = text.find("。")
    if 18 <= sentence_end + 1 <= max_chars:
        return text[:sentence_end].strip("。")

    markers = (
        "という役割",
        "という価値",
        "ということ",
        "という意味",
        "だと思った",
        "だと知った",
        "と思った",
        "と考えている",
        "になっている",
        "できる",
        "必要がある",
        "重要になる",
        "おすすめできる",
    )
    candidates = []
    for marker in markers:
        start = 0
        while True:
            index = text.find(marker, start)
            if index < 0:
                break
            cut = index + len(marker)
            if 18 <= cut <= max_chars:
                candidates.append(cut)
            start = cut
    if candidates:
        return text[: max(candidates)].strip("。")

    soft_breaks = ("こと", "ため", "役割", "価値", "重要", "おすすめ", "できる", "関わる", "活かす", "変わる", "増えていく")
    candidates = []
    for marker in soft_breaks:
        start = 0
        while True:
            index = text.find(marker, start)
            if index < 0:
                break
            cut = index + len(marker)
            if 24 <= cut <= max_chars:
                candidates.append(cut)
            start = cut
    if candidates:
        return text[: max(candidates)].strip("。")

    return text.rstrip("。")


def normalize(text: str) -> str:
    return re.sub(r"\s+", "", clean_text(text).replace("。", "").replace("？", "").replace("?", ""))


def parse_timecode(value: str) -> float:
    text = value.strip()
    parts = text.split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    raise ValueError(value)


def parse_captions_md() -> list[dict[str, Any]]:
    text = CAPTIONS_MD.read_text(encoding="utf-8")
    matches = list(re.finditer(r"^##\s+(\d+)(?:[｜|]\s*([0-9:]+)\s*[〜~-]\s*([0-9:]+))?\s*$", text, re.M))
    items: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        lines = [line.strip() for line in body.splitlines() if line.strip()]
        display_lines = []
        search_keys = []
        for line in lines:
            if line.startswith("検索キー"):
                _, _, keys = line.partition("：")
                if not keys:
                    _, _, keys = line.partition(":")
                search_keys = [clean_text(part) for part in re.split(r"[/／]", keys) if clean_text(part)]
                break
            if line == "---":
                continue
            display_lines.append(line)
        display_text = clean_text(" ".join(display_lines))
        if not display_text:
            continue
        item: dict[str, Any] = {
            "caption_no": int(match.group(1)),
            "display_text": display_text,
            "search_keys": search_keys,
        }
        if match.group(2) and match.group(3):
            item["time_hint_start_sec"] = parse_timecode(match.group(2))
            item["time_hint_end_sec"] = parse_timecode(match.group(3))
        items.append(item)
    return items


def transcript_segments() -> list[dict[str, Any]]:
    transcript = read_json(REPORTS / "transcript.json", {})
    content = read_json(REPORTS / "content_window.json", {})
    usable = content.get("usable_master_range") if isinstance(content.get("usable_master_range"), dict) else {}
    start_bound = float(usable.get("start_sec") or 0.0)
    end_bound = float(usable.get("end_sec") or 999999.0)
    result = []
    for segment in transcript.get("segments", []):
        text = clean_text(str(segment.get("text") or ""))
        if not text or text == "音声に忠実に文字起こしないでください。":
            continue
        start = float(segment.get("start") or 0.0)
        end = float(segment.get("end") or start)
        if end <= start_bound or start >= end_bound:
            continue
        result.append({**segment, "text": text, "start": start, "end": end, "norm": normalize(text)})
    return result


def load_activity() -> dict[str, dict[str, Any]]:
    payload = read_json(REPORTS / "speaker_activity_analysis.json", {})
    return {
        str(item.get("segment_id")): item
        for item in payload.get("segments", [])
        if isinstance(item, dict) and item.get("segment_id")
    }


def person_for_time(start: float, text: str, segment_id: str, activity: dict[str, dict[str, Any]]) -> tuple[str, str, float]:
    activity_item = activity.get(segment_id)
    if activity_item and activity_item.get("active_person_id") in PEOPLE:
        return str(activity_item["active_person_id"]), "speaker_activity_analysis", float(activity_item.get("confidence") or 0.5)
    if start < 623.52:
        return "person_01", "intro_time_window", 0.9
    if start < 671.06:
        return "person_02", "intro_time_window", 0.9
    if start < 722.5:
        return "person_03", "intro_time_window", 0.9
    if start < 786.2:
        return "person_01", "intro_time_window", 0.9

    norm = normalize(text)
    if any(token in norm for token in ("根元さん", "根本さん", "お二人", "ですか", "ますか", "聞いていきます", "おすすめしてください")):
        return "person_01", "question_text_heuristic", 0.72
    if any(token in norm for token in ("経理", "PDM", "バクラク", "決算", "プロダクトマネージャー", "会計", "バックオフィス")):
        return "person_02", "domain_keyword_heuristic", 0.62
    if any(token in norm for token in ("労務", "人事", "HR", "勤怠", "給与", "社会保険", "村田")):
        return "person_03", "domain_keyword_heuristic", 0.62
    return "person_01", "fallback_wide_safe", 0.35


def person_for_caption_no(caption_no: int) -> tuple[str, str, float] | None:
    ranges = [
        (range(1, 4), "person_01"),
        (range(4, 11), "person_02"),
        (range(11, 16), "person_03"),
        (range(16, 20), "person_02"),
        (range(20, 21), "person_01"),
        (range(21, 26), "person_03"),
        (range(26, 28), "person_02"),
        (range(28, 32), "person_03"),
        (range(32, 39), "person_03"),
        (range(39, 44), "person_03"),
        (range(44, 50), "person_02"),
        (range(50, 51), "person_03"),
        (range(51, 54), "person_01"),
        (range(54, 57), "person_02"),
        (range(57, 59), "person_03"),
        (range(59, 63), "person_01"),
        (range(63, 66), "person_02"),
        (range(66, 72), "person_03"),
        (range(72, 74), "person_02"),
        (range(74, 84), "person_02"),
        (range(84, 89), "person_03"),
        (range(89, 91), "person_02"),
        (range(91, 92), "person_01"),
        (range(92, 93), "person_02"),
        (range(93, 94), "person_03"),
    ]
    for number_range, person_id in ranges:
        if caption_no in number_range:
            return person_id, "captions_md_topic_speaker_map", 0.78
    return None


def find_by_keywords(item: dict[str, Any], segments: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str, float]:
    keys = [normalize(key) for key in item.get("search_keys", []) if normalize(key)]
    if not keys:
        return None, "no_search_keys", 0.0
    best: tuple[float, dict[str, Any] | None] = (0.0, None)
    for index, segment in enumerate(segments):
        window = " ".join(s["norm"] for s in segments[index : index + 3])
        hits = sum(1 for key in keys if key and key in window)
        if not hits:
            continue
        score = hits / len(keys)
        if score > best[0]:
            best = (score, segment)
    if best[1] is None:
        return None, "keyword_match_failed", 0.0
    return best[1], "keyword_match", round(best[0], 3)


def find_segment_for_item(item: dict[str, Any], segments: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str, float]:
    if "time_hint_start_sec" in item:
        target = float(item["time_hint_start_sec"])
        timed = [segment for segment in segments if float(segment["end"]) > target and float(segment["start"]) < float(item.get("time_hint_end_sec", target + 15))]
        if timed:
            return timed[0], "captions_md_time_hint", 0.9
    return find_by_keywords(item, segments)


def in_supplemental_skip_window(start: float) -> bool:
    return any(window_start <= start < window_end for window_start, window_end in SUPPLEMENTAL_SKIP_WINDOWS)


def supplemental_score(text: str) -> float:
    cleaned = clean_text(text)
    norm = normalize(cleaned)
    if len(norm) < 13:
        return -100.0
    if any(norm == normalize(pattern) or norm.startswith(normalize(pattern)) and len(norm) < 24 for pattern in SUPPLEMENTAL_NOISE_PATTERNS):
        return -80.0
    score = 0.0
    score += min(len(norm), 70) / 18.0
    score += sum(2.0 for keyword in SUPPLEMENTAL_KEYWORDS if keyword in cleaned)
    score += sum(1.0 for keyword in ("必要", "できる", "変わる", "思います", "感じ", "作る", "使う", "関わる") if keyword in cleaned)
    if any(pattern in cleaned for pattern in ("どうですか", "ありますか", "でしょうか", "聞かれる")):
        score += 1.2
    if any(pattern in cleaned for pattern in ("笑", "緊張感", "ニックネーム", "呼び名", "これはもう", "コーポレートっぽく", "砕けた感じ")):
        score -= 3.0
    if len(norm) > 95:
        score -= 1.5
    return score


def supplemental_display_text(text: str) -> str:
    cleaned = clean_text(text)
    cleaned = re.sub(r"^(ただ|でも|なので|だから|それで|あとは|要は|正直|多分|たぶん|やっぱり|何か|なんか)\s*", "", cleaned)
    compacted = compact_caption_text(cleaned, max_chars=58)
    if len(compacted) <= 58:
        return compacted
    candidates = []
    for marker in ("こと", "ため", "役割", "価値", "重要", "必要", "できる", "変わる", "思います", "感じます"):
        start = 0
        while True:
            index = compacted.find(marker, start)
            if index < 0:
                break
            cut = index + len(marker)
            if 24 <= cut <= 58:
                candidates.append(cut)
            start = cut
    if candidates:
        return compacted[: max(candidates)].strip("。")
    return compacted[:58].strip("。")


def best_supplemental_segment(
    segments: list[dict[str, Any]],
    start_after: float,
    start_before: float,
    existing_starts: list[float],
) -> dict[str, Any] | None:
    candidates = []
    for segment in segments:
        start = float(segment["start"])
        if start < start_after or start >= start_before:
            continue
        if in_supplemental_skip_window(start):
            continue
        if any(abs(start - existing) < SUPPLEMENTAL_MIN_DISTANCE_SEC for existing in existing_starts):
            continue
        text = str(segment.get("text") or "")
        score = supplemental_score(text)
        if score <= 0:
            continue
        target = (start_after + start_before) / 2.0
        distance_penalty = abs(start - target) / 8.0
        candidates.append((score - distance_penalty, segment))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], float(item[1]["start"])), reverse=True)
    return candidates[0][1]


def add_density_supplemental_captions(
    selected: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    activity: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    if not selected:
        return selected
    selected.sort(key=lambda item: (float(item["caption_start_sec"]), int(item.get("caption_no") or 9999)))
    additions: list[dict[str, Any]] = []
    existing_starts = [float(item["caption_start_sec"]) for item in selected]
    supplemental_index = 1

    def add_from_segment(segment: dict[str, Any]) -> None:
        nonlocal supplemental_index
        start = float(segment["start"])
        end = float(segment["end"])
        text = supplemental_display_text(str(segment.get("text") or ""))
        if len(normalize(text)) < 10:
            return
        person_id, speaker_method, speaker_confidence = person_for_time(
            start,
            str(segment.get("text") or ""),
            str(segment.get("segment_id") or ""),
            activity,
        )
        person = PEOPLE[person_id]
        additions.append(
            {
                "caption_id": f"main_caption_auto_{supplemental_index:03d}",
                "caption_no": f"auto_{supplemental_index:03d}",
                "source": "transcript_density_backfill",
                "source_match_method": "density_gap_backfill",
                "source_match_confidence": 0.66,
                "source_segment_id": segment.get("segment_id"),
                "source_start_sec": round(start, 3),
                "source_end_sec": round(end, 3),
                "caption_start_sec": round(start, 3),
                "caption_end_sec": round(max(end, start + 3.0), 3),
                "display_text": text,
                "full_reference_text": clean_text(str(segment.get("text") or "")),
                "search_keys": [],
                "speaker_person_id": person_id,
                "speaker_name": person["name"],
                "speaker_screen_position": person["screen_position"],
                "speaker_role": person["role"],
                "speaker_attribution_method": speaker_method,
                "speaker_attribution_confidence": round(speaker_confidence, 3),
                "density_backfill": True,
            }
        )
        existing_starts.append(start)
        supplemental_index += 1

    cursor_items = list(selected)
    for previous, following in zip(cursor_items, cursor_items[1:]):
        previous_start = float(previous["caption_start_sec"])
        following_start = float(following["caption_start_sec"])
        target_start = previous_start + SUPPLEMENTAL_TARGET_GAP_SEC
        while following_start - target_start > 6.0:
            segment = best_supplemental_segment(
                segments,
                max(previous_start + SUPPLEMENTAL_MIN_DISTANCE_SEC, target_start - 8.0),
                min(following_start - SUPPLEMENTAL_MIN_DISTANCE_SEC, target_start + 12.0),
                existing_starts,
            )
            if segment is None:
                segment = best_supplemental_segment(
                    segments,
                    previous_start + SUPPLEMENTAL_MIN_DISTANCE_SEC,
                    following_start - SUPPLEMENTAL_MIN_DISTANCE_SEC,
                    existing_starts,
                )
            if segment is None:
                break
            add_from_segment(segment)
            target_start = float(segment["start"]) + SUPPLEMENTAL_TARGET_GAP_SEC

    for _ in range(5):
        current = sorted(selected + additions, key=lambda item: (float(item["caption_start_sec"]), str(item.get("caption_no"))))
        made_addition = False
        for previous, following in zip(current, current[1:]):
            previous_start = float(previous["caption_start_sec"])
            following_start = float(following["caption_start_sec"])
            if following_start - previous_start <= SUPPLEMENTAL_TARGET_GAP_SEC + 6.0:
                continue
            midpoint = (previous_start + following_start) / 2.0
            segment = best_supplemental_segment(
                segments,
                max(previous_start + SUPPLEMENTAL_MIN_DISTANCE_SEC, midpoint - 14.0),
                min(following_start - SUPPLEMENTAL_MIN_DISTANCE_SEC, midpoint + 14.0),
                existing_starts,
            )
            if segment is None:
                segment = best_supplemental_segment(
                    segments,
                    previous_start + SUPPLEMENTAL_MIN_DISTANCE_SEC,
                    following_start - SUPPLEMENTAL_MIN_DISTANCE_SEC,
                    existing_starts,
                )
            if segment is None:
                continue
            add_from_segment(segment)
            made_addition = True
            break
        if not made_addition:
            break

    if additions:
        selected = selected + additions
        selected.sort(key=lambda item: (float(item["caption_start_sec"]), str(item.get("caption_no"))))
    return selected


def build_plan() -> dict[str, Any]:
    items = parse_captions_md()
    segments = transcript_segments()
    activity = load_activity()
    selected = []
    used_starts: list[float] = []
    for item in items:
        caption_no = int(item["caption_no"])
        if caption_no in EXCLUDED_CAPTION_NOS:
            continue
        segment, method, confidence = find_segment_for_item(item, segments)
        if not segment:
            continue
        start = float(item.get("time_hint_start_sec", segment["start"]))
        end = float(item.get("time_hint_end_sec", min(segment["end"], start + 7.0)))
        if any(abs(start - used) < 8.0 for used in used_starts):
            continue
        mapped_person = person_for_caption_no(caption_no)
        if mapped_person:
            person_id, speaker_method, speaker_confidence = mapped_person
        else:
            person_id, speaker_method, speaker_confidence = person_for_time(start, str(segment.get("text") or item["display_text"]), str(segment.get("segment_id") or ""), activity)
        person = PEOPLE[person_id]
        selected.append(
            {
                "caption_id": f"main_caption_{int(item['caption_no']):03d}",
                "caption_no": item["caption_no"],
                "source": "captions.md",
                "source_match_method": method,
                "source_match_confidence": confidence,
                "source_segment_id": segment.get("segment_id"),
                "source_start_sec": round(float(segment["start"]), 3),
                "source_end_sec": round(float(segment["end"]), 3),
                "caption_start_sec": round(start, 3),
                "caption_end_sec": round(max(end, start + 3.0), 3),
                "display_text": clean_text(DISPLAY_TEXT_OVERRIDES.get(caption_no, compact_caption_text(item["display_text"]))),
                "full_reference_text": clean_text(item["display_text"]),
                "search_keys": item.get("search_keys", []),
                "speaker_person_id": person_id,
                "speaker_name": person["name"],
                "speaker_screen_position": person["screen_position"],
                "speaker_role": person["role"],
                "speaker_attribution_method": speaker_method,
                "speaker_attribution_confidence": round(speaker_confidence, 3),
            }
        )
        used_starts.append(start)
    selected = add_density_supplemental_captions(selected, segments, activity)
    selected.sort(key=lambda item: (float(item["caption_start_sec"]), str(item["caption_no"])))
    return {
        "schema_version": "main_caption_plan.v1",
        "project_id": "layer-x-domain-expert",
        "generated_at": now_iso(),
        "source": str(CAPTIONS_MD),
        "policy": {
            "main_only": True,
            "not_full_subtitles": True,
            "remove_japanese_commas": True,
            "speaker_metadata_required": True,
        },
        "people": PEOPLE,
        "captions": selected,
    }


def main() -> None:
    output = REPORTS / "main_caption_plan.json"
    plan = build_plan()
    write_json(output, plan)
    print(json.dumps({"output": str(output), "captions": len(plan["captions"])}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
