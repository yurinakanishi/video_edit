from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRANSCRIPT_PATH = PROJECT_ROOT / "output" / "reports" / "transcript.json"
CONTENT_WINDOW_PATH = PROJECT_ROOT / "output" / "reports" / "content_window.json"
OUT_PATH = PROJECT_ROOT / "output" / "reports" / "full_conversation_review.md"


def fmt_time(sec: float) -> str:
    sec = max(0.0, float(sec))
    hours = int(sec // 3600)
    minutes = int((sec % 3600) // 60)
    seconds = sec % 60
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:05.2f}"
    return f"{minutes:02d}:{seconds:05.2f}"


def clean(text: str) -> str:
    return " ".join(str(text).split())


def format_segments(items: list[dict]) -> str:
    texts = [str(item.get("text", "")).strip() for item in items if str(item.get("text", "")).strip()]
    return "\n\n".join(texts)


def main() -> None:
    transcript = json.loads(TRANSCRIPT_PATH.read_text(encoding="utf-8"))
    content_window = json.loads(CONTENT_WINDOW_PATH.read_text(encoding="utf-8"))
    segments = transcript.get("segments", [])
    usable = content_window.get("usable_master_range", {})
    start_sec = float(usable.get("start_sec", 0) or 0)
    end_sec = float(usable.get("end_sec", 10**9) or 10**9)
    start_anchor = str(content_window.get("start_marker", {}).get("anchor_text", ""))

    pre_roll: list[dict] = []
    main: list[dict] = []
    post: list[dict] = []
    for segment in segments:
        text = clean(segment.get("text", ""))
        if not text:
            continue
        start = float(segment.get("start", 0) or 0)
        item = {
            "id": segment.get("segment_id", ""),
            "start": start,
            "end": float(segment.get("end", 0) or 0),
            "text": text,
        }
        if start < start_sec:
            pre_roll.append(item)
        elif start >= end_sec:
            post.append(item)
        else:
            main.append(item)

    all_items = pre_roll + main + post
    full_text = format_segments(all_items)
    main_text = format_segments(main)

    lines: list[str] = [
        "# LayerX Domain Expert 全会話文字起こし（補正済み）",
        "",
        "> 一覧確認用。`transcript.json` の補正済みテキストを、発音セグメントごとに空行を挟んで並べたものです。",
        "",
        "## 概要",
        "",
        f"- 生成元: `output/reports/transcript.json`",
        f"- セグメント数: {len(all_items)}",
        f"- 文字数（全会話・改行除く）: {len(full_text.replace(chr(10), ''))}",
        f"- 文字数（本編のみ・改行除く）: {len(main_text.replace(chr(10), ''))}",
        f"- 本編開始: `{fmt_time(start_sec)}`（{start_anchor}）",
        f"- 本編終了: `{fmt_time(end_sec)}`",
        "",
        "## 目次",
        "",
        "1. [全会話（発音ごと）](#全会話発音ごと)",
        "2. [本編のみ（発音ごと）](#本編のみ発音ごと)",
        "3. [タイムコード付き一覧](#タイムコード付き一覧)",
        "4. [本編タイムコード付き一覧](#本編タイムコード付き一覧)",
        "",
        "---",
        "",
        "## 全会話（発音ごと）",
        "",
        '<a id="全会話発音ごと"></a>',
        "",
        full_text,
        "",
        "---",
        "",
        "## 本編のみ（発音ごと）",
        "",
        '<a id="本編のみ発音ごと"></a>',
        "",
        main_text,
        "",
        "---",
        "",
        "## タイムコード付き一覧",
        "",
        '<a id="タイムコード付き一覧"></a>',
        "",
    ]

    for item in all_items:
        lines.append(f"**[{fmt_time(item['start'])} - {fmt_time(item['end'])}]**")
        lines.append("")
        lines.append(item["text"])
        lines.append("")

    lines.extend(
        [
            "---",
            "",
            "## 本編タイムコード付き一覧",
            "",
            '<a id="本編タイムコード付き一覧"></a>',
            "",
        ]
    )

    for item in main:
        lines.append(f"**[{fmt_time(item['start'])} - {fmt_time(item['end'])}]**")
        lines.append("")
        lines.append(item["text"])
        lines.append("")

    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(str(OUT_PATH))
    print(f"segments={len(all_items)} full_chars={len(full_text)} main_chars={len(main_text)}")


if __name__ == "__main__":
    main()
