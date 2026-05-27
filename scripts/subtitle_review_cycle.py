from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from project_paths import (
    CONFIG,
    OUTPUT_DIAGNOSTICS,
    OUTPUT_OVERLAYS,
    OUTPUT_REPORTS,
    OUTPUT_TRANSCRIPTS,
    OUTPUT_VIDEOS,
    ROOT as WORKSPACE_ROOT,
    SCRIPTS,
    SOURCE_AUDIO,
    SOURCE_IMAGES,
    SOURCE_SUBTITLES,
    SOURCE_VIDEO,
    multicam_source_root,
    resolve_project_path,
)
from typing import Any

from transcription_quality import filter_low_confidence_segments, preprocess_audio, transcribe_options
from video_edit_app_config import load_app_config, optional_path

WORK = WORKSPACE_ROOT
APP_CONFIG = load_app_config()
FFMPEG = optional_path(APP_CONFIG, "tools", "ffmpeg", default=Path(r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"))
RAW_SRT = SOURCE_SUBTITLES / "video_original_audio" / "ST7_7550_overlap_5min_original_audio.srt"
CORRECTIONS_JSON = CONFIG / "subtitle_corrections.json"
CORRECTED_SRT = SOURCE_SUBTITLES / "video_original_audio" / "ST7_7550_overlap_5min_original_audio_corrected.srt"
SOUND_OFFSET_JSON = OUTPUT_TRANSCRIPTS / "sound2" / "sound2_audio_offset_refined.json"
REVIEW_DIR = OUTPUT_DIAGNOSTICS / "subtitle_review"
REPORT = REVIEW_DIR / "subtitle_review_report.md"

SUSPICIOUS_PATTERNS = [
    r"話になったのが",
    r"一応ちょっとしたい",
    r"そもそも論争",
    r"論争がなっちゃう",
    r"伺いできて",
    r"セミオゴー",
    r"スケルメリット",
    r"採用救人",
    r"家事ある面談",
    r"通用見",
    r"必要されて",
    r"ミスリート",
]


@dataclass
class Caption:
    index: int
    start_raw: str
    end_raw: str
    start: float
    end: float
    text: str


def parse_time(value: str) -> float:
    hours, minutes, rest = value.replace(",", ".").split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(rest)


def format_time(seconds: float) -> str:
    ms = round(seconds * 1000)
    hours, rem = divmod(ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def parse_srt(path: Path) -> list[Caption]:
    blocks = re.split(r"\n\s*\n", path.read_text(encoding="utf-8-sig").strip())
    captions: list[Caption] = []
    for block in blocks:
        rows = [row.strip() for row in block.splitlines() if row.strip()]
        if len(rows) < 3 or "-->" not in rows[1]:
            continue
        start_raw, end_raw = [part.strip() for part in rows[1].split("-->")]
        captions.append(
            Caption(
                index=int(rows[0]),
                start_raw=start_raw,
                end_raw=end_raw,
                start=parse_time(start_raw),
                end=parse_time(end_raw),
                text=" ".join(rows[2:]).strip(),
            )
        )
    return captions


def write_srt(path: Path, captions: list[Caption]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[str] = []
    for caption in captions:
        rows.extend(
            [
                str(caption.index),
                f"{format_time(caption.start)} --> {format_time(caption.end)}",
                caption.text,
                "",
            ]
        )
    path.write_text("\n".join(rows), encoding="utf-8")


def read_corrections(path: Path) -> dict[int, dict[str, Any]]:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[]\n", encoding="utf-8")
    data = json.loads(path.read_text(encoding="utf-8"))
    return {int(item["index"]): item for item in data}


def apply_corrections(captions: list[Caption], corrections: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    applied: list[dict[str, Any]] = []
    for caption in captions:
        correction = corrections.get(caption.index)
        if not correction:
            continue
        before = caption.text
        caption.text = str(correction["corrected_text"]).strip()
        applied.append(
            {
                "index": caption.index,
                "start": caption.start,
                "end": caption.end,
                "before": before,
                "after": caption.text,
                "reason": correction.get("reason", ""),
            }
        )
    return applied


def suspicious_captions(captions: list[Caption], corrected_indexes: set[int]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for caption in captions:
        if caption.index in corrected_indexes:
            continue
        matched = [pattern for pattern in SUSPICIOUS_PATTERNS if re.search(pattern, caption.text)]
        if matched:
            results.append(
                {
                    "index": caption.index,
                    "start": caption.start,
                    "end": caption.end,
                    "text": caption.text,
                    "matched_patterns": matched,
                }
            )
    return results


def sound2_audio() -> tuple[Path, float] | None:
    if not SOUND_OFFSET_JSON.exists():
        return None
    data = json.loads(SOUND_OFFSET_JSON.read_text(encoding="utf-8"))
    return resolve_project_path(data["sound_file"]), float(data["refined_offset"])


def extract_audio_clips(items: list[dict[str, Any]], pad: float = 1.0) -> list[dict[str, Any]]:
    source = sound2_audio()
    if source is None:
        return []
    sound_path, offset = source
    clips_dir = REVIEW_DIR / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    extracted: list[dict[str, Any]] = []
    for item in items:
        start = max(0.0, float(item["start"]) - pad)
        duration = max(0.2, float(item["end"]) - float(item["start"]) + pad * 2)
        sound_start = offset + start
        clip_path = clips_dir / f"caption_{int(item['index']):03d}_{start:.2f}_{start + duration:.2f}.wav"
        command = [
            str(FFMPEG),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{sound_start:.6f}",
            "-t",
            f"{duration:.6f}",
            "-i",
            str(sound_path),
            "-ar",
            "48000",
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(clip_path),
        ]
        subprocess.run(command, cwd=WORK, check=True)
        extracted.append({**item, "clip": str(clip_path.relative_to(WORK)), "sound_start": sound_start, "duration": duration})
    return extracted


def transcribe_clips(extracted: list[dict[str, Any]], model_name: str) -> list[dict[str, Any]]:
    if not extracted:
        return []
    import whisper

    model = whisper.load_model(model_name)
    options = transcribe_options(
        APP_CONFIG,
        prompt_extra="これは字幕レビュー用の短い音声クリップです。音声にない内容を追加しないでください。",
    )
    reviewed: list[dict[str, Any]] = []
    for item in extracted:
        clip_path = WORK / item["clip"]
        audio_path = preprocess_audio(
            clip_path,
            REVIEW_DIR / "audio_preprocessed",
            f"caption_{int(item['index']):03d}",
            FFMPEG,
            APP_CONFIG,
        )
        result = model.transcribe(str(audio_path), **options)
        result = filter_low_confidence_segments(result, APP_CONFIG)
        reviewed.append({**item, "review_transcript": str(result.get("text", "")).strip()})
    return reviewed


def write_report(applied: list[dict[str, Any]], suspects: list[dict[str, Any]], clips: list[dict[str, Any]]) -> None:
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Subtitle Review Report",
        "",
        "## Applied Corrections",
        "",
    ]
    if applied:
        for item in applied:
            lines.extend(
                [
                    f"### Caption {item['index']} ({item['start']:.3f}-{item['end']:.3f})",
                    "",
                    f"- Before: {item['before']}",
                    f"- After: {item['after']}",
                    f"- Reason: {item['reason']}",
                    "",
                ]
            )
    else:
        lines.extend(["No manual corrections were applied.", ""])

    lines.extend(["## Suspect Captions To Recheck", ""])
    if suspects:
        clip_by_index = {int(item["index"]): item for item in clips}
        for item in suspects:
            clip = clip_by_index.get(int(item["index"]), {})
            lines.extend(
                [
                    f"### Caption {item['index']} ({item['start']:.3f}-{item['end']:.3f})",
                    "",
                    f"- Current: {item['text']}",
                    f"- Matched patterns: {', '.join(item['matched_patterns'])}",
                    f"- Review clip: {clip.get('clip', 'not generated')}",
                ]
            )
            if "review_transcript" in clip:
                lines.append(f"- High-quality audio retranscript: {clip['review_transcript']}")
            lines.append("")
    else:
        lines.extend(["No suspicious captions matched the current heuristic patterns.", ""])

    REPORT.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply reviewed subtitle corrections and create a high-quality audio recheck report."
    )
    parser.add_argument("--input", type=Path, default=RAW_SRT)
    parser.add_argument("--output", type=Path, default=CORRECTED_SRT)
    parser.add_argument("--corrections", type=Path, default=CORRECTIONS_JSON)
    parser.add_argument("--no-audio-clips", action="store_true")
    parser.add_argument("--transcribe-review", action="store_true")
    parser.add_argument("--review-model", default="large-v3")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    captions = parse_srt(args.input)
    corrections = read_corrections(args.corrections)
    applied = apply_corrections(captions, corrections)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_srt(args.output, captions)

    suspects = suspicious_captions(captions, set(corrections))
    review_items = applied + suspects
    clips: list[dict[str, Any]] = []
    if not args.no_audio_clips:
        clips = extract_audio_clips(review_items)
    if args.transcribe_review:
        clips = transcribe_clips(clips, args.review_model)
    write_report(applied, suspects, clips)
    print(
        json.dumps(
            {
                "corrected_srt": str(args.output),
                "report": str(REPORT),
                "applied_corrections": len(applied),
                "suspect_captions": len(suspects),
                "audio_clips": len(clips),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
