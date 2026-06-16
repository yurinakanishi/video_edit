from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parents[1]
TRANSCRIPTS = PROJECT / "output" / "transcripts" / "manifest_sources"
REPORTS = PROJECT / "output" / "reports"
STATE = PROJECT / "project_state.json"
PUNCTUATION_REVIEW = REPORTS / "subtitle_punctuation_review.md"

SUBTITLE_SOURCE_OFFSET = 8.7
OLD_TEXT = "ここのカスタマイズ"
NEW_TEXT = "個々のカスタマイズ"
SUBTITLE_TEXT_REPLACEMENTS = [
    (OLD_TEXT, NEW_TEXT),
    ("たまっていく", "溜まっていく"),
    ("それはそれこれはこれって感じ", "それはそれ、これはこれ、って感じ"),
    ("だとはいえAIの力によって", "とはいえAIの力によって"),
    ("なるほどどこまでも", "どこまでも"),
    ("どうしてああいう論争がなっちゃうのかな", "どうしてああいう論争になっちゃうのかな"),
    ("ノートの発言", "noteの発言"),
    ("ノートの記事", "noteの記事"),
    ("あなたの仕事例えばライターの仕事", "あなたの仕事、例えばライターの仕事"),
    ("それは採用求人状の話だけで", "それは採用求人上の話なだけで"),
    ("なるほどこういう役割を求めてるのねっていうのが", "なるほど、こういう役割を求めているのねっていうのが"),
    ("僕も事業責任者になってからそういう目線で", "僕も事業責任者になってから、そういう目線で"),
    ("本来的には仕事の中身何が求められて何が評価されるかみたいな", "本来的には仕事の中身、何が求められて何が評価されるかみたいな"),
    ("そことそもそも日本の雇用習慣というか", "そこと、そもそも日本の雇用習慣というか"),
    ("事業責任者が自分たちがどういう手段でお金を稼いで", "事業責任者が、自分たちがどういう手段でお金を稼いで"),
    ("そうですね FDE", "そうですね、FDE"),
    ("そうですねFDE", "そうですね、FDE"),
    ("そうですね FDEの", "そうですね、FDEの"),
    ("そうですねFDEの", "そうですね、FDEの"),
    ("プロダクトマネージャーになっている仕事ですということを考えると", "プロダクトマネージャーになっている仕事です、ということを考えると"),
    ("強いチームだと思っているんですよ なので", "強いチームだと思ってるんですよ、なので"),
    ("まあ全部一通りわかるしやれるんだけど より得意なのはこの人だから任せよって", "全部一通りわかるし、やれるんだけど、より得意なのはその人だから任せようっていう"),
    ("いう あのでその部分は背中を預けようっていうのが", "その部分は背中を預けよう"),
    ("すごく健全だと思っていて なんか私は例えば", "すごく健全だと思っていて"),
    ("営業だから エンジニアリングのことは全くわからない", "私は例えば営業だからエンジニアリングのことは\n全くわからないから任せた"),
    ("から任せたみたいな 任せたって言うと別に言葉は綺麗なんですけど", "みたいな 任せたって言うと別に言葉は綺麗なんですけど"),
    (
        "なんていうか関心ないですよって近いことだと思っていて お互いのやってることに関心があったりとかなんとなく肌感覚は持ちつつもでも",
        "なんていうか「関心ないですよ」に近いことだと思っていて、お互いのやってることに関心があったりとかなんとなく肉体感覚を持ちつつも、でも",
    ),
    ("肌感覚を持ちつつでも", "肉体感覚を持ちつつも、でも"),
    ("肌感覚は持ちつつもでも", "肉体感覚を持ちつつも、でも"),
    ("そこを何でもかんでも集約する人の役割をというわけじゃなくて", "そこを何でもかんでも集約する、人の役割というわけじゃなくて"),
    ("そのFDEを取り入れるのは本当にワークするのかな", "FDEを取り入れるのは、もう本当にわかったのかな"),
    ("ちょっと不安に思っているような若手中", "ちょっと不安に思っているような若手エンジニア"),
    ("前提僕もわからないところはあって", "前提、僕もわからん、というところはあって"),
    ("自分はどんな動きができるんだろうみたいな話の", "自分はどんな動きができるんだろうな、みたいな話の"),
    ("お客さんから収益をもれるわけじゃない", "お客さんから収益をもらえるわけじゃない"),
    ("特に自社で自社のプロダクトを持っている人は", "特に自社のプロダクトを持っている人は"),
    ("あとFDEって言うてもエンジニアってついてるじゃないですか", "FDEって言うても「エンジニア」ってついてるじゃないですか"),
    ("ファーストキャリアでエンジニアだったっていう経験がすごく今まで生きてると思うんですね", "ファーストキャリアがエンジニアだったという経験がすごく今の今まで生きていると思うんですよね"),
    ("やっぱりファーストキャリアがエンジニアだったという経験がすごく今の今まで生きていると思うんですよね", "ファーストキャリアがエンジニアだったという経験がすごく今の今まで生きていると思うんですよね"),
    ("何ですかね別にエンジニアタイプだから媚びてるわけじゃないけど", "別に『エンジニアtype』だから媚びてるわけじゃないけど"),
    ("なんかえ?", "なんか、え？"),
    ("コードを書く業数", "コードを書く行数"),
    ("ひねられたこの形", "決められたこの形"),
    ("改めて揃え直す", "改めて捉え直す"),
    ("?", "？"),
]
SUBTITLE_ONLY_DELETE_CUES = [
    {
        "start": "00:21:22,940",
        "end": "00:21:23,220",
        "text": "そうですね",
        "reason": "subtitle-only deletion: quick standalone そうですね around reviewed 16:29",
    },
    {
        "start": "00:39:25,580",
        "end": "00:39:27,060",
        "text": "若手エンジニア",
        "reason": "subtitle-only deletion: duplicate standalone 若手エンジニア",
    },
]
REVIEWED_VIDEO_SOURCE_START_CUT_SECONDS = 85.5
REVIEWED_VIDEO_SOURCE_END_CUT_SECONDS = 20.0


def reviewed_time_to_source_time(reviewed_seconds: float) -> float:
    return REVIEWED_VIDEO_SOURCE_START_CUT_SECONDS + reviewed_seconds


def source_time_to_reviewed_time(source_seconds: float) -> float:
    return source_seconds - REVIEWED_VIDEO_SOURCE_START_CUT_SECONDS


def subtitle_time_to_source_time(subtitle_seconds: float) -> float:
    return subtitle_seconds - SUBTITLE_SOURCE_OFFSET


def subtitle_time_to_reviewed_time(subtitle_seconds: float) -> float:
    return source_time_to_reviewed_time(subtitle_time_to_source_time(subtitle_seconds))


def timestamp(total_seconds: float) -> str:
    total_seconds = max(0.0, float(total_seconds))
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = total_seconds - hours * 3600 - minutes * 60
    return f"{hours}:{minutes:02d}:{seconds:06.3f}"


def srt_timestamp_seconds(value: str) -> float:
    hours, minutes, seconds = value.replace(",", ".").split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def backup_once(path: Path) -> None:
    backup = path.with_suffix(path.suffix + ".before_review_fix")
    if path.exists() and not backup.exists():
        backup.write_bytes(path.read_bytes())


def remove_terminal_period(value: str) -> str:
    return re.sub(r"。+$", "", value.rstrip())


def load_punctuation_review_replacements() -> dict[int, str]:
    if not PUNCTUATION_REVIEW.exists():
        return {}
    replacements: dict[int, str] = {}
    for line in PUNCTUATION_REVIEW.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| ") or line.startswith("| 字幕ID") or line.startswith("|---"):
            continue
        parts = [part.strip().replace(r"\|", "|") for part in line.strip().strip("|").split("|")]
        if len(parts) < 4:
            continue
        try:
            cue_id = int(parts[0])
        except ValueError:
            continue
        replacements[cue_id] = parts[3]
    return replacements


def preserve_existing_line_breaks(proposed: str, existing: str) -> str:
    existing_lines = [line.strip() for line in existing.splitlines() if line.strip()]
    if "\n" in proposed or len(existing_lines) < 2:
        return proposed
    for tail in reversed(existing_lines[1:]):
        if tail and f" {tail}" in proposed:
            return proposed.replace(f" {tail}", f"\n{tail}", 1)
    return proposed


def apply_punctuation_review_to_srt(text: str, replacements: dict[int, str]) -> str:
    if not replacements:
        return text
    blocks = re.split(r"(\r?\n\r?\n)", text)
    updated: list[str] = []
    for block in blocks:
        rows = block.splitlines()
        if len(rows) >= 3 and "-->" in rows[1]:
            try:
                cue_id = int(rows[0].strip())
            except ValueError:
                cue_id = -1
            proposed = replacements.get(cue_id)
            if proposed:
                existing = "\n".join(rows[2:]).strip()
                rows[2:] = preserve_existing_line_breaks(proposed, existing).splitlines()
                block = "\n".join(rows)
        updated.append(block)
    return "".join(updated)


def apply_punctuation_review_to_json_segments(payload: Any, replacements: dict[int, str]) -> Any:
    if not replacements or not isinstance(payload, dict):
        return payload
    segments = payload.get("segments")
    if not isinstance(segments, list):
        return payload
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        try:
            cue_id = int(segment.get("id")) + 1
        except (TypeError, ValueError):
            continue
        proposed = replacements.get(cue_id)
        if proposed:
            existing = str(segment.get("text", "")).strip()
            segment["text"] = preserve_existing_line_breaks(proposed, existing)
    if "text" in payload:
        payload["text"] = "".join(
            str(segment.get("text", ""))
            for segment in segments
            if isinstance(segment, dict)
        )
    return payload


def normalize_srt_subtitle_lines(text: str) -> str:
    rows = text.splitlines()
    normalized: list[str] = []
    for row in rows:
        stripped = row.strip()
        if not stripped or stripped.isdigit() or "-->" in row:
            normalized.append(row)
        else:
            normalized.append(remove_terminal_period(row))
    return "\n".join(normalized) + ("\n" if text.endswith(("\n", "\r")) else "")


def retime_special_srt_cues(text: str) -> str:
    blocks = re.split(r"(\r?\n\r?\n)", text)
    updated: list[str] = []
    for block in blocks:
        rows = block.splitlines()
        if len(rows) >= 3 and "-->" in rows[1]:
            body = "\n".join(rows[2:]).strip()
            if body == "確かに大規模":
                rows[1] = "00:15:48,840 --> 00:15:49,680"
                rows[2:] = ["大規模"]
                block = "\n".join(rows)
        updated.append(block)
    return "".join(updated)


def remove_subtitle_only_srt_cues(text: str) -> str:
    delete_keys = {
        (item["start"], item["end"], item["text"])
        for item in SUBTITLE_ONLY_DELETE_CUES
    }
    blocks = re.split(r"(\r?\n\r?\n)", text)
    updated: list[str] = []
    skip_separator = False
    for index, block in enumerate(blocks):
        if re.fullmatch(r"\r?\n\r?\n", block):
            if skip_separator:
                skip_separator = False
                continue
            updated.append(block)
            continue
        rows = block.splitlines()
        if len(rows) >= 3 and "-->" in rows[1]:
            start_raw, end_raw = [part.strip() for part in rows[1].split("-->", 1)]
            body = "".join(row.strip() for row in rows[2:])
            if (start_raw, end_raw, body) in delete_keys:
                skip_separator = index + 1 < len(blocks)
                continue
        updated.append(block)
    return "".join(updated)


def remove_subtitle_only_json_segments(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    segments = payload.get("segments")
    if not isinstance(segments, list):
        return payload
    delete_keys = {
        (round(srt_timestamp_seconds(item["start"]), 3), round(srt_timestamp_seconds(item["end"]), 3), item["text"])
        for item in SUBTITLE_ONLY_DELETE_CUES
    }
    updated_segments = []
    for segment in segments:
        if not isinstance(segment, dict):
            updated_segments.append(segment)
            continue
        try:
            key = (
                round(float(segment.get("start")), 3),
                round(float(segment.get("end")), 3),
                str(segment.get("text", "")).strip(),
            )
        except (TypeError, ValueError):
            updated_segments.append(segment)
            continue
        if key in delete_keys:
            continue
        updated_segments.append(segment)
    payload["segments"] = updated_segments
    if "text" in payload:
        payload["text"] = "".join(
            str(segment.get("text", ""))
            for segment in updated_segments
            if isinstance(segment, dict)
        )
    return payload


def replace_text_recursive(value: Any) -> Any:
    if isinstance(value, str):
        for before, after in SUBTITLE_TEXT_REPLACEMENTS:
            value = value.replace(before, after)
        return remove_terminal_period(value)
    if isinstance(value, list):
        return [replace_text_recursive(item) for item in value]
    if isinstance(value, dict):
        return {key: replace_text_recursive(item) for key, item in value.items()}
    return value


def apply_subtitle_wording() -> None:
    punctuation_replacements = load_punctuation_review_replacements()
    for path in (
        TRANSCRIPTS / "external_140101-003.reviewed.srt",
        TRANSCRIPTS / "external_140101-003.reviewed.json",
    ):
        backup_once(path)
    srt = TRANSCRIPTS / "external_140101-003.reviewed.srt"
    srt_text = srt.read_text(encoding="utf-8")
    for before, after in SUBTITLE_TEXT_REPLACEMENTS:
        srt_text = srt_text.replace(before, after)
    srt_text = retime_special_srt_cues(srt_text)
    srt_text = remove_subtitle_only_srt_cues(srt_text)
    srt_text = apply_punctuation_review_to_srt(srt_text, punctuation_replacements)
    srt_text = normalize_srt_subtitle_lines(srt_text)
    srt.write_text(srt_text, encoding="utf-8")

    reviewed_json = TRANSCRIPTS / "external_140101-003.reviewed.json"
    payload = json.loads(reviewed_json.read_text(encoding="utf-8"))
    payload = replace_text_recursive(payload)
    payload = remove_subtitle_only_json_segments(payload)
    payload = apply_punctuation_review_to_json_segments(payload, punctuation_replacements)
    reviewed_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def apply_chapter_titles() -> None:
    path = REPORTS / "chapter_titles_from_full_transcript.json"
    backup_once(path)

    # Review timestamps are based on the reviewed video: the pre-latest-commit
    # render with only the first 1:25.5 and final 0:20 removed. They are not final
    # output timestamps after the review cuts below. Store the equivalent source
    # timeline positions, then let render_multicam apply the current cutRanges.
    #
    # The review notes use rounded minute/second positions. Keep the chapter
    # boundaries tied to the actual subtitle/content anchors near those notes,
    # then let render_multicam apply the review cuts to these source-timeline
    # points. This prevents the upper-left title from switching just before the
    # intended line appears.
    strong_product_end = subtitle_time_to_reviewed_time(340.140)  # "こういう人だよっていうふうに言語化するとなると"
    fde_workers_end = subtitle_time_to_reviewed_time(484.200)  # after the subtitle-only "確かに" prefix before FDE trend discussion
    fde_boom_end = subtitle_time_to_reviewed_time(684.600)  # "続いてなんですけど"
    fde_product_start = subtitle_time_to_reviewed_time(720.240)  # "なのでFDEを支える要素..."
    japan_start = subtitle_time_to_reviewed_time(1007.240)  # after the revised cut ending before "徐々に分かってきた..."
    pdm_start = subtitle_time_to_reviewed_time(1129.360)  # "ちょっと事前の想定ではPDMとFDE..."
    pdm_end = subtitle_time_to_reviewed_time(1436.880)  # before the next topic after the PDM/FDE discussion
    rows = [
        (0.0, strong_product_end, "強いプロダクト", "強いプロダクトの条件とFDEの前提を整理する導入。"),
        (strong_product_end, fde_workers_end, "既にFDE的に働く人", "既存職種の中にあるFDE的な働き方を整理する。"),
        (fde_workers_end, fde_boom_end, "FDEブームの正体", "FDE流行の背景と採用マーケティングの文脈。"),
        (fde_product_start, japan_start, "FDE向きプロダクト", "FDEが必要になるプロダクト条件とカスタマイズ性。"),
        (japan_start, pdm_start, "日本企業でワークするか", "日本企業・SI文化・受託文化との相性。"),
        (pdm_start, pdm_end, "PDM vs FDE論争", "PDM廃止論とFDE化の論点整理。"),
        (pdm_end, 1680.0, "日本の職種設計", "ジョブディスクリプションと職種設計の違い。"),
        (1680.0, 1920.0, "職種分化と再統合", "AI時代の職種分化と再統合。"),
        (1920.0, 2160.0, "PMの本質は統合", "プロダクトマネージャーのコア価値を整理する。"),
        (2160.0, 2400.0, "FDE導入の条件", "FDEを導入すべき事業条件を整理する。"),
        (2400.0, 2640.0, "仕事の対価を考える", "仕事の価値と対価を収益から捉え直す。"),
        (2640.0, 2880.0, "FDEに向く人", "FDEに向く人のマインドセット。"),
        (2880.0, 3178.0, "AI時代の人の価値", "AI時代に残るエンジニア経験と人の価値。"),
    ]
    payload = {
        "sourceSubtitle": str(TRANSCRIPTS / "external_140101-003.reviewed.srt"),
        "method": (
            "review_result.md corrections applied from the review baseline "
            "(pre-latest-commit render with first 85.5s and final 20s removed); "
            "stored times include subtitle sync offset for chapter overlay rendering."
        ),
        "chapters": [
            {
                "start": timestamp(reviewed_time_to_source_time(start) + SUBTITLE_SOURCE_OFFSET),
                "end": timestamp(end + REVIEWED_VIDEO_SOURCE_START_CUT_SECONDS + SUBTITLE_SOURCE_OFFSET),
                "title": title,
                "topic": topic,
            }
            for start, end, title, topic in rows
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def review_cut_ranges() -> list[dict[str, Any]]:
    def review_range(start: float, end: float, label: str) -> tuple[float, float, str]:
        return reviewed_time_to_source_time(start), reviewed_time_to_source_time(end), label

    def srt_range(start: float, end: float, label: str) -> tuple[float, float, str]:
        return subtitle_time_to_source_time(start), subtitle_time_to_source_time(end), label

    ranges = [
        srt_range(299.400, 302.000, "subtitle-only filler: 確かに"),
        srt_range(402.020, 403.940, "subtitle-only filler: なるほど確かに"),
        srt_range(421.120, 423.060, "subtitle-only filler: 確かに"),
        srt_range(553.720, 556.100, "review cut: 7:40 確かにありがとうございます"),
        # The revised speech-anchor instruction asks to tighten the gap between
        # "そうですね" and "なのでFDEを支える要素...". Those anchors are contiguous
        # in the transcript, so there is no source-time cut range to store here.
        srt_range(
            771.980,
            929.320,
            "review cut: after ポイントとしてあるかなと思いますね including 外部要素ですか before 先ほどの話に付属して考えると",
        ),
        srt_range(
            970.880,
            1007.240,
            "review cut: from 確かに確かに through 日本の中で... before 徐々に分かってきた",
        ),
        srt_range(1269.760, 1271.040, "subtitle-only filler: 確かに"),
        srt_range(1458.680, 1462.100, "review cut: 22:47 確かにな"),
        srt_range(1511.920, 1513.080, "review cut: 23:39 確かにな"),
        srt_range(
            1513.080,
            1545.380,
            "review cut: from そこをちょっと考えてみたい before そもそもFDEとPDMは共存する",
        ),
        srt_range(1746.980, 1748.480, "subtitle-only filler: 確かに"),
        srt_range(1808.400, 1810.380, "subtitle-only filler: 確かに"),
        srt_range(2023.620, 2024.840, "review cut: keep silence after みたいなことは思います, cut just before 確かに確かに"),
        srt_range(
            2229.560,
            2341.160,
            "review cut: reset/setup block after 分かりましたありがとうございます before FDEについて",
        ),
        srt_range(2191.300, 2193.000, "subtitle-only filler: 確かに"),
        srt_range(
            2634.880,
            2681.260,
            "review cut: after そこは改めて捉え直す before FDEに向いている人",
        ),
        srt_range(2812.460, 2814.900, "review cut: 45:17 確かに確かに"),
    ]
    return [{"start": start, "end": end, "label": label} for start, end, label in sorted(ranges, key=lambda item: item[0])]


def source_master_duration(state: dict[str, Any]) -> float:
    manifest = state.get("assets", {}).get("mediaManifest", {})
    candidates: list[dict[str, Any]] = []
    for key in ("items", "files"):
        value = manifest.get(key)
        if isinstance(value, list):
            candidates.extend(item for item in value if isinstance(item, dict))
    for item in candidates:
        if item.get("kind") != "video" or item.get("role") != "master":
            continue
        try:
            return float(item.get("metadata", {}).get("duration"))
        except (TypeError, ValueError):
            pass

    render = state.get("render", {})
    try:
        return (
            float(render.get("previewStart", 0.0) or 0.0)
            + float(render.get("previewDuration", 0.0) or 0.0)
            + REVIEWED_VIDEO_SOURCE_END_CUT_SECONDS
        )
    except (TypeError, ValueError):
        raise RuntimeError("Unable to determine master source duration for reviewed-video trim.")


def apply_reviewed_video_source_trim(state: dict[str, Any]) -> None:
    render = state.setdefault("render", {})
    master_duration = source_master_duration(state)
    trimmed_duration = master_duration - REVIEWED_VIDEO_SOURCE_START_CUT_SECONDS - REVIEWED_VIDEO_SOURCE_END_CUT_SECONDS
    if trimmed_duration <= 0:
        raise RuntimeError(
            "Reviewed-video trim is longer than the master source duration: "
            f"start={REVIEWED_VIDEO_SOURCE_START_CUT_SECONDS}, "
            f"end={REVIEWED_VIDEO_SOURCE_END_CUT_SECONDS}, duration={master_duration}"
        )
    render["previewStart"] = REVIEWED_VIDEO_SOURCE_START_CUT_SECONDS
    render["previewDuration"] = round(trimmed_duration, 6)
    render["reviewedVideoSourceTrim"] = {
        "startSeconds": REVIEWED_VIDEO_SOURCE_START_CUT_SECONDS,
        "endSeconds": REVIEWED_VIDEO_SOURCE_END_CUT_SECONDS,
        "sourceDurationSeconds": round(master_duration, 6),
        "reason": "Review was made against the derived file with the first 85.5s and last 20s removed.",
    }


def update_project_state() -> None:
    backup_once(STATE)
    state = json.loads(STATE.read_text(encoding="utf-8"))
    render = state.setdefault("render", {})
    apply_reviewed_video_source_trim(state)
    render["cutRanges"] = review_cut_ranges()
    render["extraOverlayManifests"] = []
    render["cameraMinSegmentSeconds"] = 2.0
    style = state.setdefault("style", {})
    style["chapterTitlesEnabled"] = True
    style["chapterTitlesPath"] = str(REPORTS / "chapter_titles_from_full_transcript.json")
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    apply_subtitle_wording()
    apply_chapter_titles()
    update_project_state()
    (REPORTS / "review_cut_ranges.json").write_text(json.dumps(review_cut_ranges(), ensure_ascii=False, indent=2), encoding="utf-8")
    state = json.loads(STATE.read_text(encoding="utf-8"))
    reviewed_trim = state.get("render", {}).get("reviewedVideoSourceTrim", {})
    print(
        json.dumps(
            {
                "subtitleCorrections": [f"{before} -> {after}" for before, after in SUBTITLE_TEXT_REPLACEMENTS],
                "reviewedVideoSourceTrim": reviewed_trim,
                "chapterTitles": str(REPORTS / "chapter_titles_from_full_transcript.json"),
                "cutRanges": str(REPORTS / "review_cut_ranges.json"),
                "projectState": str(STATE),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
