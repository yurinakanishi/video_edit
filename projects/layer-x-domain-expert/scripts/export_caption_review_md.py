import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT_ROOT / "output" / "reports"
OUTPUT = PROJECT_ROOT / "caption_review.md"
CAPTION_FONT_FILE = Path(r"C:\Windows\Fonts\BIZ-UDGothicB.ttc")
CAPTION_FONT_SIZE = 76
CAPTION_MAX_TEXT_WIDTH = 1080

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
]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


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
    return caption_text_width(text) + 66 <= 1198 and caption_text_width(text) <= CAPTION_MAX_TEXT_WIDTH


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
        )
    )


def bad_caption_start(line: str) -> bool:
    return line.startswith(("の", "に", "を", "が", "は", "と", "で", "も", "へ", "や", "って", "て", "する", "した", "った", "る", "れ", "ん", "け", "い", "ゃ", "ど", "さ", "しい", "り", "ード", "ドル", "ル", "事", "味", "メイン"))


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


def wrap_caption_text(text: str, max_chars: int = 13) -> list[str]:
    text = " ".join(str(text).replace("、", "").split())
    if caption_line_fits(text):
        return [text]
    spans = protected_spans(text)
    semantic_candidates = set(caption_cut_candidates(text, spans))
    two_line_candidates = []
    for index in range(1, len(text)):
        if inside_protected_span(index, spans):
            continue
        first = text[:index].strip(" 、。")
        second = text[index:].strip(" 、。")
        if first and second and caption_line_fits(first) and caption_line_fits(second):
            semantic_bonus = -8 if index in semantic_candidates else 0
            bad_break_penalty = 12 if bad_caption_break(first) else 0
            bad_start_penalty = 16 if bad_caption_start(second) else 0
            balance = abs(caption_text_width(first) - caption_text_width(second)) / 100
            two_line_candidates.append((balance + bad_break_penalty + bad_start_penalty + semantic_bonus, index))
    if two_line_candidates:
        _, cut = min(two_line_candidates)
        return [line for line in (text[:cut].strip(" 、。"), text[cut:].strip(" 、。")) if line]

    cut = best_caption_cut(text, 2, spans)
    return [line for line in (text[:cut].strip(" 、。"), text[cut:].strip(" 、。")) if line][:2]


def fmt_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    ms = int(round((seconds - int(seconds)) * 1000))
    whole = int(seconds)
    if ms == 1000:
        whole += 1
        ms = 0
    h = whole // 3600
    m = (whole % 3600) // 60
    s = whole % 60
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def clean_cell(text: Any) -> str:
    return str(text).replace("|", "\\|").replace("\n", "<br>")


def people_lookup(people_map: dict[str, Any]) -> dict[str, dict[str, str]]:
    result = {}
    for person in people_map.get("people", []):
        person_id = str(person.get("person_id") or "")
        if not person_id:
            continue
        result[person_id] = {
            "name": str(person.get("display_name") or person_id),
            "position": str(person.get("screen_position") or ""),
            "role": str(person.get("conversation_role") or ""),
        }
    return result


def layout_speaker(event: dict[str, Any]) -> str | None:
    layout = event.get("layout") if isinstance(event.get("layout"), dict) else {}
    if layout.get("speaker_person_id"):
        return str(layout["speaker_person_id"])
    if layout.get("active_person_id"):
        return str(layout["active_person_id"])
    if layout.get("target_person_id"):
        return str(layout["target_person_id"])
    if str(event.get("event_id") or "").endswith("_question_01"):
        return "person_01"
    return None


def overlay_speaker(event: dict[str, Any], overlay: dict[str, Any]) -> str | None:
    if overlay.get("speaker_person_id"):
        return str(overlay["speaker_person_id"])
    return layout_speaker(event)


def source_time(event: dict[str, Any], local_time: float) -> float | None:
    reference = event.get("reference_source") if isinstance(event.get("reference_source"), dict) else {}
    try:
        return float(reference.get("in")) + local_time
    except (TypeError, ValueError):
        return None


def section_label(section: str) -> str:
    return {"digest": "ダイジェスト", "company_movie": "カンパニームービー", "main": "本編"}.get(section, section)


def collect_captions(edit_plan: dict[str, Any], people: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    events = edit_plan["timeline"]["events"] if isinstance(edit_plan.get("timeline"), dict) else edit_plan.get("timeline", [])
    rows = []
    order = 1
    for event in events:
        event_start = float(event.get("timeline_start") or 0.0)
        event_end = float(event.get("timeline_end") or event_start)
        overlays = sorted(
            [overlay for overlay in event.get("overlays", []) if overlay.get("type") == "caption"],
            key=lambda overlay: float(overlay.get("start") or 0.0),
        )
        for overlay in overlays:
            local_start = float(overlay.get("start") or 0.0)
            local_end = float(overlay.get("end") or local_start)
            speaker_id = overlay_speaker(event, overlay)
            speaker = people.get(speaker_id or "", {})
            text = str(overlay.get("text") or "")
            lines = wrap_caption_text(text)
            source_start = source_time(event, local_start)
            source_end = source_time(event, local_end)
            rows.append(
                {
                    "order": order,
                    "section": str(event.get("section") or ""),
                    "event_id": str(event.get("event_id") or ""),
                    "layout_type": str((event.get("layout") or {}).get("type") or ""),
                    "speaker_id": speaker_id or "unknown",
                    "speaker_name": speaker.get("name") or str(overlay.get("metadata", {}).get("speaker_name") or "不明"),
                    "speaker_position": speaker.get("position") or "",
                    "speaker_role": speaker.get("role") or "",
                    "timeline_start": event_start + local_start,
                    "timeline_end": event_start + local_end,
                    "source_start": source_start,
                    "source_end": source_end,
                    "text": text,
                    "lines": lines,
                    "style_id": str(overlay.get("style_id") or ""),
                    "caption_id": str(overlay.get("caption_id") or overlay.get("source_srt_index") or f"caption_{order:03d}"),
                }
            )
            order += 1
    return rows


def chunk_captions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chunks = []
    current = None
    for row in rows:
        key = (row["section"], row["speaker_id"])
        if (
            current is None
            or current["key"] != key
            or row["timeline_start"] - current["end"] > 6.0
            or (row["section"] == "digest" and row["event_id"].split("_answer_")[0].split("_question_")[0] != current["event_group"])
        ):
            event_group = row["event_id"].split("_answer_")[0].split("_question_")[0]
            current = {
                "key": key,
                "section": row["section"],
                "speaker_id": row["speaker_id"],
                "speaker_name": row["speaker_name"],
                "speaker_position": row["speaker_position"],
                "speaker_role": row["speaker_role"],
                "start": row["timeline_start"],
                "end": row["timeline_end"],
                "event_group": event_group,
                "rows": [],
            }
            chunks.append(current)
        current["rows"].append(row)
        current["end"] = row["timeline_end"]
    return chunks


def render_md(rows: list[dict[str, Any]], chunks: list[dict[str, Any]], edit_plan: dict[str, Any]) -> str:
    lines = [
        "# Caption Review",
        "",
        "このファイルは `output/reports/edit_plan.json` に実際に入っている字幕オーバーレイから生成しています。",
        "画面上の改行は `<br>` で示しています。折り返しは現在のレンダー処理と同じ `wrap_caption_text` ロジックです。",
        "",
        "## Summary",
        "",
        f"- Total displayed captions: {len(rows)}",
        f"- Chunks by continuous speaker: {len(chunks)}",
        f"- Source edit plan: `output/reports/edit_plan.json`",
        "",
    ]
    assignment = edit_plan.get("main_caption_assignment")
    if isinstance(assignment, dict):
        lines.extend(
            [
                "## Main Caption Assignment",
                "",
                f"- Main caption candidates: {assignment.get('total_candidates')}",
                f"- Attached to timeline: {assignment.get('attached_count')}",
                f"- Skipped: {assignment.get('skipped_count')}",
                "",
            ]
        )
        skipped = assignment.get("skipped") if isinstance(assignment.get("skipped"), list) else []
        if skipped:
            lines.extend(["| Caption ID | Reason | Event | Source Time |", "|---|---|---|---|"])
            for item in skipped:
                lines.append(
                    f"| `{clean_cell(item.get('caption_id'))}` | {clean_cell(item.get('reason'))} | `{clean_cell(item.get('event_id', ''))}` | {fmt_time(float(item.get('caption_start_sec') or 0.0))} |"
                )
            lines.append("")

    for index, chunk in enumerate(chunks, start=1):
        lines.extend(
            [
                f"## Chunk {index:03d}: {section_label(chunk['section'])} / {chunk['speaker_name']}",
                "",
                f"- Timeline: `{fmt_time(chunk['start'])}` - `{fmt_time(chunk['end'])}`",
                f"- Speaker: `{chunk['speaker_id']}` / {chunk['speaker_position']} / {chunk['speaker_role']}",
                "",
                "| No | Timeline | Source | Event | Layout | Caption ID | Rendered Lines | Raw Text | Style |",
                "|---:|---|---|---|---|---|---|---|---|",
            ]
        )
        for row in chunk["rows"]:
            source = "-"
            if row["source_start"] is not None and row["source_end"] is not None:
                source = f"{fmt_time(row['source_start'])} - {fmt_time(row['source_end'])}"
            rendered = "<br>".join(clean_cell(line) for line in row["lines"])
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(row["order"]),
                        f"{fmt_time(row['timeline_start'])} - {fmt_time(row['timeline_end'])}",
                        source,
                        f"`{clean_cell(row['event_id'])}`",
                        clean_cell(row["layout_type"]),
                        f"`{clean_cell(row['caption_id'])}`",
                        rendered,
                        clean_cell(row["text"]),
                        f"`{clean_cell(row['style_id'])}`",
                    ]
                )
                + " |"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    edit_plan = read_json(REPORTS / "edit_plan.json")
    people_map = read_json(REPORTS / "people_map.json")
    people = people_lookup(people_map)
    rows = collect_captions(edit_plan, people)
    chunks = chunk_captions(rows)
    OUTPUT.write_text(render_md(rows, chunks, edit_plan), encoding="utf-8", newline="\n")
    print(json.dumps({"output": str(OUTPUT), "captions": len(rows), "chunks": len(chunks)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
