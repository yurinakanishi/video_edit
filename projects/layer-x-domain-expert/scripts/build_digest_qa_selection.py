from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT_ROOT / "output" / "reports"
SRT_PATH = PROJECT_ROOT / "output" / "transcripts" / "manifest_sources" / "primary.srt"
JST = timezone(timedelta(hours=9))


def now_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def seconds_to_srt(value: float) -> str:
    millis = round(value * 1000)
    hours = millis // 3_600_000
    millis %= 3_600_000
    minutes = millis // 60_000
    millis %= 60_000
    seconds = millis // 1000
    millis %= 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def srt_to_seconds(value: str) -> float:
    hours, minutes, rest = value.split(":")
    seconds, millis = rest.split(",")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("、", "")).strip()


def parse_srt(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig")
    entries: list[dict[str, Any]] = []
    blocks = re.split(r"\n\s*\n", text.strip())
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 3:
            continue
        timing = lines[1]
        if "-->" not in timing:
            continue
        start_text, end_text = [part.strip() for part in timing.split("-->", 1)]
        entries.append(
            {
                "index": int(lines[0]) if lines[0].isdigit() else len(entries) + 1,
                "start": srt_to_seconds(start_text),
                "end": srt_to_seconds(end_text),
                "start_timecode": start_text,
                "end_timecode": end_text,
                "text": clean_text(" ".join(lines[2:])),
            }
        )
    return entries


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
]


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


def split_caption_text(text: str, max_chars: int = 24) -> list[str]:
    text = clean_text(text)
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    remaining = text
    while len(remaining) > max_chars:
        spans = protected_spans(remaining)
        candidates = caption_cut_candidates(remaining, spans)
        lower_bound = max(6, max_chars - 5)
        preferred = [index for index in candidates if lower_bound <= index <= max_chars]
        if preferred:
            cut = preferred[-1]
        else:
            forward = [index for index in candidates if max_chars < index <= max_chars + 9]
            if forward:
                cut = forward[0]
            else:
                backward = [index for index in candidates if index < lower_bound]
                cut = backward[-1] if backward else max_chars
                while cut < len(remaining) and inside_protected_span(cut, spans):
                    cut += 1
        chunk = remaining[:cut].strip(" 、。！？,.")
        next_remaining = remaining[cut:].strip(" 、。！？,.")
        if next_remaining and len(next_remaining) < 5 and len(chunk) + len(next_remaining) <= max_chars + 5:
            chunks.append(f"{chunk}{next_remaining}")
            remaining = ""
            break
        if chunk:
            chunks.append(chunk)
        remaining = next_remaining
    if remaining:
        chunks.append(remaining)
    merged: list[str] = []
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        if merged and len(chunk) <= 3 and len(merged[-1]) + len(chunk) <= max_chars + 8:
            merged[-1] = f"{merged[-1]}{chunk}"
        else:
            merged.append(chunk)
    return merged


def subtitles_for_range(entries: list[dict[str, Any]], start: float, end: float) -> list[dict[str, Any]]:
    return [
        entry
        for entry in entries
        if entry["end"] > start and entry["start"] < end and entry["text"] != "音声に忠実に文字起こしないでください。"
    ]


def caption_overlays(entries: list[dict[str, Any]], start: float, end: float) -> list[dict[str, Any]]:
    overlays: list[dict[str, Any]] = []
    for entry in subtitles_for_range(entries, start, end):
        local_start = max(0.0, entry["start"] - start)
        local_end = min(end - start, entry["end"] - start)
        chunks = split_caption_text(entry["text"])
        if not chunks:
            continue
        span = max(0.8, local_end - local_start)
        chunk_duration = span / len(chunks)
        for index, chunk in enumerate(chunks):
            c_start = local_start + chunk_duration * index
            c_end = local_start + chunk_duration * (index + 1)
            overlays.append(
                {
                    "type": "caption",
                    "start": round(c_start, 3),
                    "end": round(c_end, 3),
                    "text": chunk,
                    "style_id": "opening_digest_sample_caption",
                    "source_srt_index": entry["index"],
                    "source_timecode": f"{entry['start_timecode']} --> {entry['end_timecode']}",
                }
            )
    return overlays


def part_payload(entries: list[dict[str, Any]], part: dict[str, Any], order: int, part_order: int) -> dict[str, Any]:
    start = float(part["start"])
    end = float(part["end"])
    return {
        "part_id": f"digest_qa_{order:02d}_{part['kind']}_{part_order:02d}",
        "kind": part["kind"],
        "start_sec": round(start, 3),
        "end_sec": round(end, 3),
        "start_timecode": seconds_to_srt(start),
        "end_timecode": seconds_to_srt(end),
        "duration_sec": round(end - start, 3),
        "layout": part.get("layout"),
        "caption_overlays": caption_overlays(entries, start, end),
        "srt_evidence": [
            {
                "index": entry["index"],
                "start": entry["start_timecode"],
                "end": entry["end_timecode"],
                "text": entry["text"],
            }
            for entry in subtitles_for_range(entries, start, end)
        ],
    }


def clip_payload(entries: list[dict[str, Any]], spec: dict[str, Any], order: int) -> dict[str, Any]:
    parts = [part_payload(entries, part, order, index) for index, part in enumerate(spec["parts"], start=1)]
    start = min(part["start_sec"] for part in parts)
    end = max(part["end_sec"] for part in parts)
    total_duration = sum(part["duration_sec"] for part in parts)
    evidence = subtitles_for_range(entries, start, end)
    return {
        "clip_id": f"digest_qa_{order:02d}",
        "order": order,
        "clip_title": spec["clip_title"],
        "question_title": spec["question_title"],
        "start_sec": round(start, 3),
        "end_sec": round(end, 3),
        "start_timecode": seconds_to_srt(start),
        "end_timecode": seconds_to_srt(end),
        "recommended_duration_sec": round(total_duration, 3),
        "source_range_note": "This digest clip is intentionally built from core question/answer parts; intervening non-core material is omitted.",
        "parts": parts,
        "question": spec["question_title"],
        "answer_summary": spec["answer_summary"],
        "layout": spec["layout"],
        "video_source": {
            "media_id": "group_wide",
            "in": round(start, 3),
            "out": round(end, 3),
            "visual_strategy": spec["visual_strategy"],
        },
        "audio_source": {
            "media_id": "group_wide",
            "in": round(start, 3),
            "out": round(end, 3),
            "policy": "continuous_reference_audio; do not switch audio by camera cut",
        },
        "caption_overlays": [caption for part in parts for caption in part["caption_overlays"]],
        "srt_evidence": [
            {
                "index": entry["index"],
                "start": entry["start_timecode"],
                "end": entry["end_timecode"],
                "text": entry["text"],
            }
            for entry in evidence
        ],
        "evidence_excerpt": spec["evidence_excerpt"],
        "selection_reason": spec["selection_reason"],
        "edit_note": spec["edit_note"],
        "short_version": spec.get("short_version"),
    }


def build_selection() -> dict[str, Any]:
    entries = parse_srt(SRT_PATH)
    specs = [
        {
            "clip_title": "当たり前を言語化する難しさ",
            "question_title": "開発に関わって、一番大変だったことは何ですか？",
            "parts": [
                {"kind": "question", "start": 1500.720, "end": 1508.760, "layout": {"type": "wide_group", "active_person_id": "person_01"}},
                {"kind": "answer", "start": 1533.420, "end": 1556.620, "layout": {"type": "single", "target_person_id": "person_03"}},
            ],
            "layout": {"type": "split_grid", "media_ids": ["cam_person_02", "cam_person_03"], "active_person_id": "person_03"},
            "visual_strategy": "two-person split of interviewees; focus on the respondent while keeping the other reaction visible",
            "answer_summary": "実務で当たり前や慣行として処理していたことを、エンジニアやPDMに説明できる言葉へ変換するのが大変だった。労務同士なら流せる話でも、背景や意味を整理する必要があった。",
            "evidence_excerpt": "「なんでそうするんですかって聞かれた時に」「ものすごくこれを言語化するのに大変だった」「今までの当たり前を言語化する」",
            "selection_reason": "質問開始から、回答の中心である「当たり前を言語化する」までがSRT上でまとまっている。",
            "edit_note": "冒頭は質問から入れる。25:08,760以降は回答者中心。末尾の「この言語化ですね」で自然に切れる。",
        },
        {
            "clip_title": "何でも知っている人ではない",
            "question_title": "ドメインエキスパートは、何でも知っていないといけないんですか？",
            "parts": [
                {"kind": "question_context", "start": 1595.620, "end": 1611.940, "layout": {"type": "single", "target_person_id": "person_03"}},
                {"kind": "answer", "start": 1619.160, "end": 1627.720, "layout": {"type": "single", "target_person_id": "person_02"}},
                {"kind": "answer", "start": 1633.820, "end": 1638.760, "layout": {"type": "split_grid", "media_ids": ["cam_person_02", "cam_person_03"], "active_person_id": "person_02"}},
            ],
            "layout": {"type": "split_grid", "media_ids": ["cam_person_02", "cam_person_03"], "active_person_id": "person_03"},
            "visual_strategy": "two-person split of interviewees; use both faces because the answer is about discussion with engineers",
            "answer_summary": "ドメインエキスパートは何でも知っていそうに見えるが、実際には知らないこともある。エンジニア側もかなり調べており、一方的に教えるより建設的に議論している。",
            "evidence_excerpt": "「何でも知ってそうな感じ」「自分が知らないことも知ってるんじゃないか」「皆さんドメインの方めっちゃ調べてる」「建設的な議論」",
            "selection_reason": "ハードルの高さと、建設的な議論で怖さはないという回答が同じ流れで説明されている。",
            "edit_note": "26:11,120から背景説明として入れる。26:35,620以降が本題。27:18,760直前で次テーマへつなぐ。",
        },
        {
            "clip_title": "なんで？が成長につながる",
            "question_title": "エンジニアから「なんで？」と聞かれるのは怖くないですか？",
            "parts": [
                {"kind": "answer", "start": 1641.880, "end": 1663.720, "layout": {"type": "single", "target_person_id": "person_03"}},
            ],
            "layout": {"type": "split_grid", "media_ids": ["cam_person_02", "cam_person_03"], "active_person_id": "person_03"},
            "visual_strategy": "two-person split of interviewees; keep the respondent and reaction visible",
            "answer_summary": "意見を言った後に「なんでなんですか」を逃がしてくれないことが、怖さではなく健全なプレッシャーになっている。背景まで整理して言語化する力が鍛えられ、自分の当たり前が磨かれる。",
            "evidence_excerpt": "「なんでなんですかを絶対に逃がしてくれない」「健全なプレッシャー」「背景まで整理して言語化」「磨かれて成長」",
            "selection_reason": "指定テーマのキーワードが連続し、回答が短く強いのでダイジェスト向き。",
            "edit_note": "前テーマから連続するので頭に0.2秒程度の余白だけでよい。27:43,720以降は補足なので、必要ならカット可。",
        },
        {
            "clip_title": "AI時代の実務家の手触り",
            "question_title": "AI時代に、ドメインエキスパートの価値は何ですか？",
            "parts": [
                {"kind": "question", "start": 1983.100, "end": 1995.100, "layout": {"type": "wide_group", "active_person_id": "person_01"}},
                {"kind": "answer", "start": 2010.100, "end": 2029.120, "layout": {"type": "single", "target_person_id": "person_02"}},
                {"kind": "answer", "start": 2051.540, "end": 2068.820, "layout": {"type": "single", "target_person_id": "person_02"}},
            ],
            "layout": {"type": "split_grid", "media_ids": ["cam_person_02", "cam_person_03"], "active_person_id": "person_02"},
            "visual_strategy": "two-person split of interviewees; use middle/right because the answer moves between domain expertise and practical judgment",
            "answer_summary": "AI利用が前提になるほど、ドメインエキスパートには仕様を書く以上に「なぜやるのか」「何を実現したいのか」を考える役割が求められる。AIのリサーチ力は強いが、実務家の手触りやユーザーが触った印象を伝える価値は残る。",
            "evidence_excerpt": "「AIを使うのが前提」「求められることは研ぎ澄まされて」「仕様をゴリゴリ」「なんでこれをやるのか」「手触り」「使いづらい機能」",
            "selection_reason": "AI時代の役割変化、仕様ではなく目的を考える価値、AIリサーチとの差分まで一続きで語られている。",
            "edit_note": "質問の核と回答の核だけを残す短縮版。AIのリサーチ力と実務家の手触りまで残す。",
            "short_version": {
                "start_timecode": "00:33:30,100",
                "end_timecode": "00:34:20,740",
                "duration_sec": 50.64,
                "note": "研ぎ澄まされる役割、仕様より目的、実務家の手触りまでを残す短縮案。",
            },
        },
        {
            "clip_title": "バックオフィス経験は開発で広がる",
            "question_title": "バックオフィス経験者に、PDMや開発関与のキャリアはおすすめですか？",
            "parts": [
                {"kind": "question", "start": 2918.040, "end": 2938.040, "layout": {"type": "wide_group", "active_person_id": "person_01"}},
                {"kind": "answer", "start": 2938.040, "end": 2958.040, "layout": {"type": "split_grid", "media_ids": ["cam_person_02", "cam_person_03"], "active_person_id": "person_02"}},
                {"kind": "answer", "start": 2973.700, "end": 2980.620, "layout": {"type": "single", "target_person_id": "person_02"}},
            ],
            "layout": {"type": "split_grid", "media_ids": ["cam_person_02", "cam_person_03"], "active_person_id": "person_02"},
            "visual_strategy": "two-person split of interviewees; keep both answers visible because both recommend the career path",
            "answer_summary": "バックオフィス経験者にとって、ドメインエキスパートやPDM的なキャリアは強くおすすめできる。暗黙知や慣行が言語化され、視野が広がり、AIとの向き合い方も変わる。",
            "evidence_excerpt": "「バックオフィスで働いている方」「ドメインエキスパートとかプロダクトマネージャー」「めちゃめちゃおすすめ」「暗黙知」「視野が広がる」「AIの活用、向き合い方」",
            "selection_reason": "質問から推奨理由までが明確で、ショート動画やチャプターに使いやすい結論がある。",
            "edit_note": "48:34,040から質問として入れる。49:40,620で「めちゃめちゃおすすめ」に着地して自然に切れる。",
        },
    ]
    clips = [clip_payload(entries, spec, index) for index, spec in enumerate(specs, start=1)]
    return {
        "schema_version": "digest_qa_selection.v1",
        "project_id": "layer-x-domain-expert",
        "generated_at": now_iso(),
        "source_srt": str(SRT_PATH),
        "video_title_ref": str(REPORTS / "video_title.json"),
        "selection_policy": {
            "only_requested_five_questions": True,
            "use_srt_timecodes": True,
            "digest_replaces_previous_digest": True,
            "clip_order": "chronological_by_srt_time",
            "clip_structure": "question_core_plus_answer_core_parts",
            "audio_policy": "use group_wide continuously for interview clips",
            "silence_policy": "clip boundaries are snapped to SRT subtitle starts/ends; no pre-roll setup or silent waiting beats included",
        },
        "clips": clips,
    }


def main() -> None:
    payload = build_selection()
    output = REPORTS / "digest_qa_selection.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    title_payload = {
        "schema_version": "video_title.v1",
        "project_id": "layer-x-domain-expert",
        "generated_at": now_iso(),
        "title": "AI時代のドメインエキスパート論",
        "subtitle": "実務知をプロダクト価値に変える仕事",
        "display": {
            "digest_top_right": "AI時代のドメインエキスパート論",
            "main_title_fallback": "ドメインエキスパートの役割",
        },
        "rationale": "字幕全体で、開発に関わる実務家が当たり前を言語化し、AI時代に仕様より目的や手触りを伝える価値を担う、というテーマが中心になっているため。",
        "source_evidence": [
            "今までの当たり前を言語化する",
            "AIを使うのが前提",
            "仕様をゴリゴリ書いていくというよりは",
            "手触りが実務家の実務の経験",
            "バックオフィス経験者にPDMや開発関与のキャリアをおすすめ",
        ],
    }
    (REPORTS / "video_title.json").write_text(json.dumps(title_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "clips": len(payload["clips"])}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
