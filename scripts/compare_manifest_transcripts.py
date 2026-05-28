from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from project_paths import OUTPUT_REPORTS, OUTPUT_TRANSCRIPTS
from video_edit_app_config import load_app_config, nested, transcript_manifest_fingerprint


APP_CONFIG = load_app_config()
TRANSCRIPT_MANIFEST = OUTPUT_TRANSCRIPTS / "manifest_sources" / "manifest_transcripts.json"


@dataclass
class TranscriptWindow:
    start: float
    end: float
    text: str
    normalized: str


@dataclass
class Match:
    score: float
    offset_seconds: float
    primary_start: float
    primary_end: float
    source_start: float
    source_end: float
    primary_text: str
    source_text: str


def text_value(*keys: str, default: str = "") -> str:
    value = nested(APP_CONFIG, *keys, default=default)
    return str(value) if value is not None else default


def int_value(*keys: str, default: int) -> int:
    value = nested(APP_CONFIG, *keys, default=default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def float_value(*keys: str, default: float) -> float:
    value = nested(APP_CONFIG, *keys, default=default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        raise SystemExit(f"Required transcript comparison input is missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"Transcript comparison input is not a JSON object: {path}")
    return payload


def load_manifest(path: Path) -> dict[str, Any]:
    manifest = load_json(path)
    expected = transcript_manifest_fingerprint(APP_CONFIG)
    actual = manifest.get("manifestFingerprint")
    if expected and actual and expected != actual:
        raise SystemExit("Transcript manifest does not match the current media manifest. Run transcription again.")
    return manifest


def normalize_text(text: str) -> str:
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[、。,.!?！？「」『』（）()［］\[\]・…:：;；\-ー_\"'`~]", "", text)
    return text.lower()


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def timestamp_to_seconds(value: str) -> float:
    text = value.strip().replace(",", ".")
    hours, minutes, seconds = text.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def read_srt_segments(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig")
    segments: list[dict[str, Any]] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        rows = [line.strip() for line in block.splitlines() if line.strip()]
        if len(rows) < 3 or "-->" not in rows[1]:
            continue
        start_raw, end_raw = [part.strip() for part in rows[1].split("-->", 1)]
        segments.append(
            {
                "start": timestamp_to_seconds(start_raw),
                "end": timestamp_to_seconds(end_raw),
                "text": " ".join(rows[2:]),
            }
        )
    return segments


def transcript_segments(item: dict[str, Any]) -> list[dict[str, Any]]:
    json_value = str(item.get("json") or "")
    json_path = Path(json_value) if json_value else None
    if json_path and json_path.exists() and json_path.is_file():
        payload = load_json(json_path)
        segments = payload.get("segments", [])
        if isinstance(segments, list):
            return [segment for segment in segments if isinstance(segment, dict)]
    srt_value = str(item.get("srt") or "")
    srt_path = Path(srt_value) if srt_value else None
    if srt_path and srt_path.exists() and srt_path.is_file():
        return read_srt_segments(srt_path)
    raise FileNotFoundError(f"Transcript source has no readable JSON or SRT: {source_name(item)}")


def configured_window_sizes() -> tuple[int, ...]:
    raw = nested(APP_CONFIG, "transcriptComparison", "windowSizes", default=None)
    values: list[int] = []
    if isinstance(raw, list):
        for item in raw:
            try:
                value = int(item)
            except (TypeError, ValueError):
                continue
            if value > 0:
                values.append(value)
    if not values:
        return (2, 3, 4, 5)
    return tuple(sorted(set(values)))


def windows(segments: list[dict[str, Any]], sizes: tuple[int, ...], min_chars: int) -> list[TranscriptWindow]:
    output: list[TranscriptWindow] = []
    for size in sizes:
        for index in range(0, max(len(segments) - size + 1, 0)):
            selected = segments[index : index + size]
            text = clean_text("".join(str(segment.get("text", "")) for segment in selected))
            normalized = normalize_text(text)
            if len(normalized) < min_chars:
                continue
            try:
                start = float(selected[0].get("start") or 0)
                end = float(selected[-1].get("end") or start)
            except (TypeError, ValueError):
                continue
            output.append(TranscriptWindow(start=start, end=end, text=text, normalized=normalized))
    return output


def classify(score: float, strong_threshold: float, usable_threshold: float) -> str:
    if score >= strong_threshold:
        return "strong"
    if score >= usable_threshold:
        return "usable_review"
    return "weak"


def top_matches(
    primary_windows: list[TranscriptWindow],
    source_windows: list[TranscriptWindow],
    *,
    limit: int,
) -> list[Match]:
    matches: list[Match] = []
    for source in source_windows:
        best: Match | None = None
        for primary in primary_windows:
            score = SequenceMatcher(None, source.normalized, primary.normalized).ratio()
            if best is None or score > best.score:
                best = Match(
                    score=score,
                    offset_seconds=primary.start - source.start,
                    primary_start=primary.start,
                    primary_end=primary.end,
                    source_start=source.start,
                    source_end=source.end,
                    primary_text=primary.text,
                    source_text=source.text,
                )
        if best is not None:
            matches.append(best)

    matches.sort(key=lambda item: item.score, reverse=True)
    filtered: list[Match] = []
    seen: set[tuple[int, int]] = set()
    for match in matches:
        key = (round(match.primary_start), round(match.source_start))
        if key in seen:
            continue
        seen.add(key)
        filtered.append(match)
        if len(filtered) >= limit:
            break
    return filtered


def source_name(item: dict[str, Any]) -> str:
    path = str(item.get("path") or item.get("srt") or item.get("json") or "")
    role = str(item.get("role") or "source")
    return f"{role}:{Path(path).name if path else str(item.get('label') or 'unknown')}"


def transcript_summary(item: dict[str, Any], segments: list[dict[str, Any]], window_count: int | None = None) -> dict[str, Any]:
    summary = {
        "role": item.get("role") or "",
        "kind": item.get("kind") or "",
        "path": item.get("path") or "",
        "label": item.get("label") or "",
        "json": item.get("json") or "",
        "srt": item.get("srt") or "",
        "primary": bool(item.get("primary")),
        "segmentCount": len(segments),
        "textLength": sum(len(clean_text(segment.get("text"))) for segment in segments),
    }
    if window_count is not None:
        summary["windowCount"] = window_count
    return summary


def match_to_dict(match: Match, *, strong_threshold: float, usable_threshold: float) -> dict[str, Any]:
    return {
        "score": round(match.score, 6),
        "class": classify(match.score, strong_threshold, usable_threshold),
        "offsetSeconds": round(match.offset_seconds, 3),
        "primaryStart": round(match.primary_start, 3),
        "primaryEnd": round(match.primary_end, 3),
        "sourceStart": round(match.source_start, 3),
        "sourceEnd": round(match.source_end, 3),
        "primaryText": match.primary_text,
        "sourceText": match.source_text,
    }


def compact_markdown_text(value: str, limit: int = 120) -> str:
    text = clean_text(value).replace("|", "\\|")
    return text if len(text) <= limit else f"{text[: limit - 3]}..."


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Transcript Source Comparison",
        "",
        f"- primary: `{source_name(report['primary'])}`",
        f"- compared sources: {report['comparedCount']}",
        "- offsetSeconds means source timestamp + offsetSeconds = primary timestamp.",
        "",
        "## Summary",
        "",
        "| role | file | best score | class | offsetSeconds | primary time | source time |",
        "| --- | --- | ---: | --- | ---: | ---: | ---: |",
    ]
    for item in report["items"]:
        best = item.get("bestMatch")
        file_name = Path(str(item.get("path") or item.get("srt") or item.get("json") or item.get("label") or "")).name
        if not best:
            lines.append(f"| {item.get('role') or ''} | `{file_name}` | - | no_match | - | - | - |")
            continue
        lines.append(
            "| {role} | `{file}` | {score:.3f} | {cls} | {offset:.3f}s | {ps:.3f}s | {ss:.3f}s |".format(
                role=item.get("role") or "",
                file=file_name,
                score=float(best["score"]),
                cls=best["class"],
                offset=float(best["offsetSeconds"]),
                ps=float(best["primaryStart"]),
                ss=float(best["sourceStart"]),
            )
        )
    lines.extend(["", "## Top Matches", ""])
    for item in report["items"]:
        best_matches = item.get("matches") or []
        if not best_matches:
            continue
        lines.append(f"### {source_name(item)}")
        lines.append("")
        for match in best_matches[:5]:
            lines.append(
                "- score `{score:.3f}`, class `{cls}`, offset `{offset:.3f}s`, primary `{ps:.3f}-{pe:.3f}s`, source `{ss:.3f}-{se:.3f}s`".format(
                    score=float(match["score"]),
                    cls=match["class"],
                    offset=float(match["offsetSeconds"]),
                    ps=float(match["primaryStart"]),
                    pe=float(match["primaryEnd"]),
                    ss=float(match["sourceStart"]),
                    se=float(match["sourceEnd"]),
                )
            )
            lines.append(f"  - primary: {compact_markdown_text(match['primaryText'])}")
            lines.append(f"  - source: {compact_markdown_text(match['sourceText'])}")
        lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare transcript timing/text matches between current project sources.")
    parser.add_argument("--manifest", type=Path, default=TRANSCRIPT_MANIFEST)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(text_value("transcriptComparison", "outputPath", default=str(OUTPUT_REPORTS / "transcript_comparison.json"))),
    )
    parser.add_argument("--limit", type=int, default=int_value("transcriptComparison", "matchLimit", default=12))
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    transcripts = manifest.get("transcripts", [])
    if not isinstance(transcripts, list) or not transcripts:
        raise SystemExit("No transcript entries found for transcript comparison. Run transcription first.")
    primary_item = next((item for item in transcripts if isinstance(item, dict) and item.get("primary")), None)
    if primary_item is None:
        primary_item = next((item for item in transcripts if isinstance(item, dict)), None)
    if primary_item is None:
        raise SystemExit("No usable primary transcript entry was found.")

    window_sizes = configured_window_sizes()
    min_chars = int_value("transcriptComparison", "minNormalizedChars", default=22)
    strong_threshold = float_value("transcriptComparison", "strongThreshold", default=0.82)
    usable_threshold = float_value("transcriptComparison", "usableThreshold", default=0.70)
    try:
        primary_segments = transcript_segments(primary_item)
    except Exception as error:
        raise SystemExit(str(error)) from error
    primary_windows = windows(primary_segments, window_sizes, min_chars)
    if not primary_windows:
        raise SystemExit("Primary transcript is too short for comparison.")

    items: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for item in transcripts:
        if not isinstance(item, dict) or item is primary_item:
            continue
        try:
            source_segments = transcript_segments(item)
            source_windows = windows(source_segments, window_sizes, min_chars)
            matches = [
                match_to_dict(match, strong_threshold=strong_threshold, usable_threshold=usable_threshold)
                for match in top_matches(primary_windows, source_windows, limit=max(1, int(args.limit)))
            ]
            summary = transcript_summary(item, source_segments, len(source_windows))
            summary["matches"] = matches
            summary["bestMatch"] = matches[0] if matches else None
            summary["bestScore"] = matches[0]["score"] if matches else 0
            summary["bestClass"] = matches[0]["class"] if matches else "no_match"
            summary["suggestedOffsetSeconds"] = matches[0]["offsetSeconds"] if matches else None
            items.append(summary)
        except Exception as error:
            errors.append({"source": source_name(item), "error": str(error)})

    report = {
        "source": str(args.manifest),
        "manifestFingerprint": manifest.get("manifestFingerprint") or "",
        "primary": transcript_summary(primary_item, primary_segments, len(primary_windows)),
        "thresholds": {
            "strong": strong_threshold,
            "usableReview": usable_threshold,
            "minNormalizedChars": min_chars,
            "windowSizes": list(window_sizes),
        },
        "comparedCount": len(items),
        "strongCount": sum(1 for item in items if item.get("bestClass") == "strong"),
        "usableReviewCount": sum(1 for item in items if item.get("bestClass") == "usable_review"),
        "items": items,
        "errors": errors,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(args.output.with_suffix(".md"), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
