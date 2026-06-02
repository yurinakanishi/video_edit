from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from video_edit_core.paths import OUTPUT_REPORTS, OUTPUT_TRANSCRIPTS
from video_edit_core.app_config import load_app_config, nested, transcript_manifest_fingerprint


APP_CONFIG = load_app_config()
TRANSCRIPT_MANIFEST = OUTPUT_TRANSCRIPTS / "manifest_sources" / "manifest_transcripts.json"


@dataclass
class Caption:
    index: int
    timing: str
    text: str


def text_value(*keys: str, default: str = "") -> str:
    value = nested(APP_CONFIG, *keys, default=default)
    return str(value) if value is not None else default


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Required subtitle correction input is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_manifest() -> dict[str, Any]:
    manifest = load_json(TRANSCRIPT_MANIFEST)
    expected = transcript_manifest_fingerprint(APP_CONFIG)
    actual = manifest.get("manifestFingerprint")
    if expected and actual and expected != actual:
        raise SystemExit("Transcript manifest does not match the current media manifest. Run transcription again.")
    return manifest


def primary_entry(manifest: dict[str, Any]) -> dict[str, Any]:
    transcripts = manifest.get("transcripts", [])
    if not isinstance(transcripts, list) or not transcripts:
        raise SystemExit("No transcript entries found for subtitle correction.")
    entry = next((item for item in transcripts if isinstance(item, dict) and item.get("primary")), transcripts[0])
    if not isinstance(entry, dict):
        raise SystemExit("Primary transcript entry is invalid.")
    return entry


def parse_srt(path: Path) -> list[Caption]:
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        return []
    captions: list[Caption] = []
    for block in re.split(r"\n\s*\n", text):
        rows = [row.strip() for row in block.splitlines() if row.strip()]
        if len(rows) < 3 or "-->" not in rows[1]:
            continue
        try:
            index = int(rows[0])
        except ValueError:
            continue
        captions.append(Caption(index=index, timing=rows[1], text=" ".join(rows[2:])))
    return captions


def write_srt(path: Path, captions: list[Caption]) -> None:
    rows: list[str] = []
    for caption in captions:
        rows.extend([str(caption.index), caption.timing, caption.text, ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(rows), encoding="utf-8")


def normalize_correction(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    try:
        index = int(item.get("index"))
    except (TypeError, ValueError):
        return None
    corrected = item.get("corrected_text", item.get("text", item.get("after", "")))
    corrected_text = str(corrected or "").strip()
    if index <= 0 or not corrected_text:
        return None
    return {
        "index": index,
        "corrected_text": corrected_text,
        "reason": str(item.get("reason") or "").strip(),
    }


def parse_corrections_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        if isinstance(payload.get("corrections"), list):
            payload = payload["corrections"]
        else:
            payload = [
                {"index": index, "corrected_text": text}
                for index, text in payload.items()
                if str(index).strip().isdigit()
            ]
    if not isinstance(payload, list):
        return []
    corrections = [item for item in (normalize_correction(item) for item in payload) if item is not None]
    return sorted(corrections, key=lambda item: int(item["index"]))


def parse_corrections_text(text: str) -> list[dict[str, Any]]:
    raw = text.strip()
    if not raw:
        return []
    if raw.startswith("[") or raw.startswith("{"):
        return parse_corrections_payload(json.loads(raw))
    corrections: list[dict[str, Any]] = []
    for row in raw.splitlines():
        line = row.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in re.split(r"\s*\|\s*", line)]
        if len(parts) >= 2 and parts[0].isdigit():
            item = normalize_correction(
                {
                    "index": parts[0],
                    "corrected_text": parts[1],
                    "reason": parts[2] if len(parts) >= 3 else "",
                }
            )
            if item:
                corrections.append(item)
            continue
        match = re.match(r"^(\d+)\s*[:：]\s*(.+)$", line)
        if match:
            item = normalize_correction({"index": match.group(1), "corrected_text": match.group(2)})
            if item:
                corrections.append(item)
    return sorted(corrections, key=lambda item: int(item["index"]))


def configured_corrections() -> list[dict[str, Any]]:
    corrections: list[dict[str, Any]] = []
    raw_items = nested(APP_CONFIG, "subtitleReview", "corrections", default=[])
    corrections.extend(parse_corrections_payload(raw_items))
    path_text = text_value("subtitleReview", "correctionsPath")
    if path_text:
        path = Path(path_text)
        if path.exists():
            corrections.extend(parse_corrections_payload(json.loads(path.read_text(encoding="utf-8"))))
    corrections.extend(parse_corrections_text(text_value("subtitleReview", "correctionsText")))

    by_index: dict[int, dict[str, Any]] = {}
    for item in corrections:
        by_index[int(item["index"])] = item
    return [by_index[index] for index in sorted(by_index)]


def apply_to_captions(captions: list[Caption], corrections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_index = {int(item["index"]): item for item in corrections}
    applied: list[dict[str, Any]] = []
    for caption in captions:
        correction = by_index.get(caption.index)
        if not correction:
            continue
        before = caption.text
        after = str(correction["corrected_text"]).strip()
        if before == after:
            continue
        caption.text = after
        applied.append(
            {
                "index": caption.index,
                "timing": caption.timing,
                "before": before,
                "after": after,
                "reason": correction.get("reason", ""),
            }
        )
    return applied


def apply_to_transcript_json(path: Path, corrections: list[dict[str, Any]], output: Path) -> bool:
    if not path.exists():
        return False
    payload = json.loads(path.read_text(encoding="utf-8"))
    segments = payload.get("segments", [])
    if not isinstance(segments, list):
        return False
    by_index = {int(item["index"]): str(item["corrected_text"]).strip() for item in corrections}
    changed = False
    for index, segment in enumerate(segments, start=1):
        if not isinstance(segment, dict) or index not in by_index:
            continue
        if segment.get("text") == by_index[index]:
            continue
        segment["text"] = by_index[index]
        changed = True
    if changed:
        payload["text"] = "".join(str(segment.get("text", "")) for segment in segments if isinstance(segment, dict)).strip()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return changed


def corrected_path(path: Path) -> Path:
    return path.with_name(f"{path.stem}.corrected{path.suffix}")


def update_manifest(manifest: dict[str, Any], entry: dict[str, Any], srt_path: Path, json_path: Path | None, report_path: Path) -> None:
    original_primary_srt = manifest.get("primarySrt") or entry.get("srt") or ""
    manifest["primarySrt"] = str(srt_path)
    manifest["subtitleCorrectionsReport"] = str(report_path)
    entry.setdefault("originalSrt", original_primary_srt)
    entry["srt"] = str(srt_path)
    if json_path:
        entry.setdefault("originalJson", entry.get("json") or "")
        entry["json"] = str(json_path)
    TRANSCRIPT_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown = [
        "# Subtitle Corrections",
        "",
        f"- applied: {report['appliedCount']}",
        f"- outputSrt: `{report['outputSrt']}`",
        "",
    ]
    if report["applied"]:
        markdown.append("| index | before | after | reason |")
        markdown.append("| --- | --- | --- | --- |")
        for item in report["applied"]:
            before = str(item["before"]).replace("|", "\\|")
            after = str(item["after"]).replace("|", "\\|")
            reason = str(item.get("reason", "")).replace("|", "\\|")
            markdown.append(f"| {item['index']} | {before} | {after} | {reason} |")
    else:
        markdown.append("No subtitle corrections were applied.")
    path.with_suffix(".md").write_text("\n".join(markdown) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply project subtitle corrections from the current app runtime config.")
    parser.add_argument("--output", type=Path, default=Path(text_value("subtitleReview", "correctionsOutputPath", default=str(OUTPUT_REPORTS / "subtitle_corrections_applied.json"))))
    args = parser.parse_args()

    manifest = load_manifest()
    entry = primary_entry(manifest)
    source_srt = Path(str(entry.get("srt") or manifest.get("primarySrt") or ""))
    if not source_srt.exists():
        raise SystemExit("Primary subtitle SRT is missing. Run transcription first.")
    corrections = configured_corrections()
    if not corrections:
        raise SystemExit("No subtitle corrections were provided.")

    captions = parse_srt(source_srt)
    applied = apply_to_captions(captions, corrections)
    output_srt = corrected_path(source_srt)
    write_srt(output_srt, captions)

    source_json_text = str(entry.get("json") or "")
    output_json: Path | None = None
    json_changed = False
    if source_json_text:
        source_json = Path(source_json_text)
        output_json = corrected_path(source_json)
        json_changed = apply_to_transcript_json(source_json, corrections, output_json)
        if not output_json.exists():
            output_json = None

    report = {
        "sourceSrt": str(source_srt),
        "outputSrt": str(output_srt),
        "outputJson": str(output_json) if output_json else "",
        "providedCount": len(corrections),
        "appliedCount": len(applied),
        "jsonChanged": json_changed,
        "applied": applied,
    }
    write_report(args.output, report)
    update_manifest(manifest, entry, output_srt, output_json, args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
