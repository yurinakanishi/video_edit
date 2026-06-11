from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[1]
REPORTS_DIR = PROJECT_DIR / "output" / "reports"
EDIT_PLAN_PATH = REPORTS_DIR / "edit_plan.json"
BEST_TRANSCRIPT_PATH = REPORTS_DIR / "transcript_best_audio_large_v3_master_aligned.json"
REPORT_JSON = REPORTS_DIR / "caption_vs_best_transcript_review.json"
REPORT_MD = PROJECT_DIR / "caption_vs_best_transcript_review.md"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def srt_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    ms_total = int(round(seconds * 1000))
    hours, rem = divmod(ms_total, 3600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def normalize(text: str) -> str:
    return re.sub(r"[\s、。！？?「」『』（）()・,.]", "", str(text or "")).lower()


def caption_master_time(event: dict[str, Any], overlay: dict[str, Any]) -> tuple[float, float]:
    metadata = overlay.get("metadata") if isinstance(overlay.get("metadata"), dict) else {}
    if metadata.get("source_start_sec") is not None and metadata.get("source_end_sec") is not None:
        return float(metadata["source_start_sec"]), float(metadata["source_end_sec"])
    source_timecode = overlay.get("source_timecode")
    if isinstance(source_timecode, str) and "-->" in source_timecode:
        left, right = [item.strip() for item in source_timecode.split("-->", 1)]
        return parse_srt_time(left), parse_srt_time(right)
    event_source = event.get("reference_source") or event.get("source") or {}
    base = float(event_source.get("in", 0.0))
    return base + float(overlay.get("start", 0.0)), base + float(overlay.get("end", 0.0))


def parse_srt_time(value: str) -> float:
    hh, mm, rest = value.split(":")
    ss, ms = rest.split(",")
    return int(hh) * 3600 + int(mm) * 60 + int(ss) + int(ms) / 1000


def overlap_text(segments: list[dict[str, Any]], start: float, end: float, pad: float = 0.35) -> str:
    lo = start - pad
    hi = end + pad
    parts = []
    for segment in segments:
        seg_start = float(segment.get("master_start", 0.0))
        seg_end = float(segment.get("master_end", seg_start))
        if seg_end < lo or seg_start > hi:
            continue
        text = str(segment.get("text") or "").strip()
        if text:
            parts.append(text)
    return "".join(parts)


def all_caption_overlays(plan: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    rows = []
    for event in plan.get("timeline", []):
        for overlay in event.get("overlays", []) if isinstance(event.get("overlays"), list) else []:
            if isinstance(overlay, dict) and overlay.get("type") == "caption":
                rows.append((event, overlay))
    return rows


def similarity(a: str, b: str) -> float:
    na = normalize(a)
    nb = normalize(b)
    if not na or not nb:
        return 0.0
    common = 0
    remaining = list(nb)
    for char in na:
        try:
            index = remaining.index(char)
        except ValueError:
            continue
        common += 1
        remaining.pop(index)
    return round(common / max(len(na), 1), 3)


def main() -> None:
    plan = load_json(EDIT_PLAN_PATH)
    transcript = load_json(BEST_TRANSCRIPT_PATH)
    segments = transcript.get("segments", [])
    rows = []
    for index, (event, overlay) in enumerate(all_caption_overlays(plan), 1):
        start, end = caption_master_time(event, overlay)
        whisper_text = overlap_text(segments, start, end)
        caption_text = str(overlay.get("text") or "").strip()
        rows.append(
            {
                "no": index,
                "section": event.get("section"),
                "event_id": event.get("event_id"),
                "caption_id": overlay.get("caption_id"),
                "speaker_person_id": overlay.get("speaker_person_id"),
                "speaker_name": (overlay.get("metadata") or {}).get("speaker_name")
                if isinstance(overlay.get("metadata"), dict)
                else None,
                "start": round(start, 3),
                "end": round(end, 3),
                "timecode": f"{srt_time(start)} - {srt_time(end)}",
                "caption_text": caption_text,
                "best_whisper_text": whisper_text,
                "char_overlap_ratio": similarity(caption_text, whisper_text),
            }
        )
    payload = {
        "schema_version": "caption_vs_best_transcript_review.v1",
        "generated_at": now_iso(),
        "best_transcript_source": str(BEST_TRANSCRIPT_PATH),
        "caption_count": len(rows),
        "rows": rows,
    }
    dump_json(REPORT_JSON, payload)

    lines = [
        "# Caption vs Best Whisper Transcript Review",
        "",
        "Whisper large-v3 の新規文字起こしと、現在の表示キャプションを同じ master 時刻で比較した確認表です。",
        "",
        "| No | Section | Time | Caption | Best Whisper Text | Overlap |",
        "|---:|---|---|---|---|---:|",
    ]
    for row in rows:
        caption = row["caption_text"].replace("|", "\\|")
        whisper = row["best_whisper_text"].replace("|", "\\|")
        lines.append(
            f"| {row['no']} | {row['section']} | {row['timecode']} | {caption} | {whisper} | {row['char_overlap_ratio']:.3f} |"
        )
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(REPORT_JSON), "md": str(REPORT_MD), "rows": len(rows)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
