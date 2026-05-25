from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
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

import whisper
from whisper.utils import get_writer


WORK = WORKSPACE_ROOT
ROOT = multicam_source_root()
OUT = OUTPUT_TRANSCRIPTS / "transcript_sync_all"
MASTER = SOURCE_VIDEO / "1cam" / "ST7_7550_overlap_5min.mp4"


@dataclass
class Match:
    score: float
    offset: float
    master_start: float
    master_end: float
    alt_start: float
    alt_end: float
    master_text: str
    alt_text: str


def normalize(text: str) -> str:
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[、。,.!?！？「」『』（）()［］\[\]・…:：;；\-ー_]", "", text)
    return text.lower()


def transcribe(model: Any, media_path: Path, label: str) -> dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    json_path = OUT / f"{label}.json"
    if json_path.exists():
        return json.loads(json_path.read_text(encoding="utf-8"))

    result = model.transcribe(
        str(media_path),
        language="ja",
        task="transcribe",
        verbose=False,
        fp16=False,
    )
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    srt_writer = get_writer("srt", str(OUT))
    srt_writer(result, str(media_path), {"max_line_width": None, "max_line_count": None, "highlight_words": False})
    generated_srt = OUT / f"{media_path.stem}.srt"
    if generated_srt.exists():
        generated_srt.replace(OUT / f"{label}.srt")
    return result


def windows(result: dict[str, Any], sizes: tuple[int, ...] = (2, 3, 4, 5)) -> list[tuple[float, float, str, str]]:
    segments = result.get("segments", [])
    output: list[tuple[float, float, str, str]] = []
    for size in sizes:
        for index in range(0, max(len(segments) - size + 1, 0)):
            selected = segments[index : index + size]
            raw = "".join(str(segment.get("text", "")) for segment in selected).strip()
            norm = normalize(raw)
            if len(norm) >= 22:
                output.append(
                    (
                        float(selected[0]["start"]),
                        float(selected[-1]["end"]),
                        raw,
                        norm,
                    )
                )
    return output


def top_matches(master: dict[str, Any], alt: dict[str, Any], limit: int = 12) -> list[Match]:
    master_windows = windows(master)
    alt_windows = windows(alt)
    matches: list[Match] = []
    for alt_start, alt_end, alt_raw, alt_norm in alt_windows:
        best: Match | None = None
        for master_start, master_end, master_raw, master_norm in master_windows:
            score = SequenceMatcher(None, alt_norm, master_norm).ratio()
            if best is None or score > best.score:
                best = Match(
                    score=score,
                    offset=master_start - alt_start,
                    master_start=master_start,
                    master_end=master_end,
                    alt_start=alt_start,
                    alt_end=alt_end,
                    master_text=master_raw,
                    alt_text=alt_raw,
                )
        if best is not None:
            matches.append(best)

    matches.sort(key=lambda item: item.score, reverse=True)
    filtered: list[Match] = []
    seen: set[tuple[int, int]] = set()
    for match in matches:
        key = (round(match.master_start), round(match.alt_start))
        if key in seen:
            continue
        seen.add(key)
        filtered.append(match)
        if len(filtered) >= limit:
            break
    return filtered


def classify(score: float) -> str:
    if score >= 0.82:
        return "strong"
    if score >= 0.70:
        return "usable_review"
    return "weak"


def match_to_dict(match: Match) -> dict[str, Any]:
    return {
        "score": match.score,
        "class": classify(match.score),
        "offset": match.offset,
        "master_start": match.master_start,
        "master_end": match.master_end,
        "alt_start": match.alt_start,
        "alt_end": match.alt_end,
        "master_text": match.master_text,
        "alt_text": match.alt_text,
    }


def write_markdown(report: list[dict[str, Any]]) -> None:
    lines = [
        "# ST7_7550 All Multicam Transcript Comparison",
        "",
        "Master: `1cam\\ST7_7550_overlap_5min.mp4`",
        "",
        "Only `strong` matches should be used automatically. `usable_review` requires manual review. `weak` should not be used for multicam switching.",
        "",
        "## Summary",
        "",
        "| camera | file | best score | class | offset | master time | alt time |",
        "|---|---|---:|---|---:|---:|---:|",
    ]
    for item in report:
        best = item["matches"][0] if item["matches"] else None
        if best is None:
            lines.append(f"| {item['camera']} | `{item['file']}` | - | no_match | - | - | - |")
            continue
        lines.append(
            "| {camera} | `{file}` | {score:.3f} | {cls} | {offset:.3f}s | {ms:.3f}s | {alts:.3f}s |".format(
                camera=item["camera"],
                file=item["file"],
                score=best["score"],
                cls=best["class"],
                offset=best["offset"],
                ms=best["master_start"],
                alts=best["alt_start"],
            )
        )
    lines.extend(["", "## Strong Matches", ""])
    strong_found = False
    for item in report:
        strong = [match for match in item["matches"] if match["class"] == "strong"]
        if not strong:
            continue
        strong_found = True
        lines.append(f"### {item['camera']} `{item['file']}`")
        lines.append("")
        for match in strong[:5]:
            lines.append(f"- score `{match['score']:.3f}`, offset `{match['offset']:.3f}s`, master `{match['master_start']:.3f}-{match['master_end']:.3f}s`, alt `{match['alt_start']:.3f}-{match['alt_end']:.3f}s`")
            lines.append(f"  - master: {match['master_text']}")
            lines.append(f"  - alt: {match['alt_text']}")
        lines.append("")
    if not strong_found:
        lines.append("No strong matches found.")
        lines.append("")

    (OUT / "all_multicam_transcript_comparison.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    model = whisper.load_model("small")
    master = transcribe(model, MASTER, "1cam_master_ST7_7550_overlap_5min")

    report: list[dict[str, Any]] = []
    targets: list[tuple[str, Path]] = []
    targets.extend(("2cam", path) for path in sorted((ROOT / "2cam").glob("*.MP4")))
    targets.extend(("3cam", path) for path in sorted((ROOT / "3cam").glob("*.MP4")))

    for camera, path in targets:
        label = f"{camera}_{path.stem}"
        result = transcribe(model, path, label)
        matches = [match_to_dict(match) for match in top_matches(master, result)]
        report.append(
            {
                "camera": camera,
                "file": path.name,
                "path": str(path),
                "matches": matches,
            }
        )

    (OUT / "all_multicam_transcript_comparison.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_markdown(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
