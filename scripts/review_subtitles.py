from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from video_edit_core.paths import OUTPUT_DIAGNOSTICS, OUTPUT_REPORTS, OUTPUT_TRANSCRIPTS
from video_edit_core.transcription_quality import filter_low_confidence_segments, transcribe_model_name, transcribe_options
from video_edit_core.app_config import load_app_config, nested, optional_path, transcript_manifest_fingerprint


APP_CONFIG = load_app_config()
TRANSCRIPT_MANIFEST = OUTPUT_TRANSCRIPTS / "manifest_sources" / "manifest_transcripts.json"
REVIEW_DIR = OUTPUT_DIAGNOSTICS / "subtitle_review"
FFMPEG = optional_path(APP_CONFIG, "tools", "ffmpeg", default=Path(r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"))


def float_value(*keys: str, default: float) -> float:
    value = nested(APP_CONFIG, *keys, default=default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def text_value(*keys: str, default: str = "") -> str:
    value = nested(APP_CONFIG, *keys, default=default)
    return str(value) if value is not None else default


def bool_value(*keys: str, default: bool = False) -> bool:
    value = nested(APP_CONFIG, *keys, default=default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Required subtitle review input is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def primary_transcript() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    manifest = load_json(TRANSCRIPT_MANIFEST)
    expected = transcript_manifest_fingerprint(APP_CONFIG)
    actual = manifest.get("manifestFingerprint")
    if expected and actual and expected != actual:
        raise SystemExit("Transcript manifest does not match the current media manifest. Run transcription again.")
    transcripts = manifest.get("transcripts", [])
    if not isinstance(transcripts, list) or not transcripts:
        raise SystemExit("No transcript entries found for subtitle review.")
    primary = next((item for item in transcripts if isinstance(item, dict) and item.get("primary")), transcripts[0])
    payload = load_json(Path(str(primary.get("json") or "")))
    return manifest, payload, primary


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def suspicious_patterns() -> list[str]:
    patterns: list[str] = []
    configured = nested(APP_CONFIG, "subtitleReview", "suspiciousPatterns", default=[])
    if isinstance(configured, list):
        patterns.extend(str(item).strip() for item in configured if str(item).strip())
    raw = text_value("subtitleReview", "suspiciousPatternsText")
    for line in raw.splitlines():
        text = line.strip()
        if text and not text.startswith("#"):
            patterns.append(text)
    seen: set[str] = set()
    unique: list[str] = []
    for pattern in patterns:
        if pattern in seen:
            continue
        seen.add(pattern)
        unique.append(pattern)
    return unique


def pattern_matches(text: str, patterns: list[str]) -> list[str]:
    matched: list[str] = []
    for pattern in patterns:
        try:
            if re.search(pattern, text):
                matched.append(pattern)
        except re.error:
            if pattern in text:
                matched.append(pattern)
    return matched


def segment_issues(segment: dict[str, Any]) -> list[str]:
    issues = []
    text = clean_text(segment.get("text"))
    start = float(segment.get("start") or 0)
    end = float(segment.get("end") or start)
    duration = max(0.0, end - start)
    no_speech = float(segment.get("no_speech_prob") or 0)
    avg_logprob = float(segment.get("avg_logprob") or 0)
    compression = float(segment.get("compression_ratio") or 0)
    if not text:
        issues.append("empty_text")
    if no_speech >= float_value("subtitleReview", "noSpeechThreshold", default=0.6):
        issues.append("high_no_speech")
    if avg_logprob <= float_value("subtitleReview", "avgLogprobThreshold", default=-1.0):
        issues.append("low_avg_logprob")
    if compression >= float_value("subtitleReview", "compressionRatioThreshold", default=2.4):
        issues.append("high_compression")
    if duration >= float_value("subtitleReview", "maxDuration", default=8.0):
        issues.append("long_segment")
    if text and duration > 0:
        chars_per_second = len(text) / duration
        if chars_per_second >= float_value("subtitleReview", "maxCharsPerSecond", default=18.0):
            issues.append("fast_reading")
    if re.search(r"(.)\1{7,}", text):
        issues.append("repeated_character")
    return issues


def fmt_time(value: float) -> str:
    total_ms = round(value * 1000)
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{ms:03d}"


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    rows = [
        "# Subtitle Review",
        "",
        f"- segments: {report['segmentCount']}",
        f"- flagged: {report['flaggedCount']}",
        f"- configured patterns: {report['configuredPatternCount']}",
        f"- source: `{report['source']}`",
        "",
    ]
    if not report["flagged"]:
        rows.append("No subtitle QA issues were flagged.")
    else:
        rows.append("| time | issues | text |")
        rows.append("| --- | --- | --- |")
        for item in report["flagged"]:
            text = str(item["text"]).replace("|", "\\|")
            issues = ", ".join(item["issues"])
            patterns = ", ".join(item.get("matchedPatterns") or [])
            clip = f" / clip: `{item['clip']}`" if item.get("clip") else ""
            review_text = str(item.get("reviewTranscript") or "").replace("|", "\\|")
            review = f" / review transcript: {review_text}" if review_text else ""
            suffix = f" / patterns: {patterns}" if patterns else ""
            rows.append(f"| {item['time']} | {issues}{suffix}{clip}{review} | {text} |")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def review_audio_path(primary: dict[str, Any]) -> Path | None:
    for key in ("audio", "path"):
        value = str(primary.get(key) or "")
        if not value:
            continue
        path = Path(value)
        if path.exists() and path.is_file():
            return path
    return None


def extract_audio_clips(flagged: list[dict[str, Any]], primary: dict[str, Any], pad: float) -> list[dict[str, Any]]:
    audio = review_audio_path(primary)
    if not audio:
        return [{**item, "clipError": "review audio source not found"} for item in flagged]
    clips_dir = REVIEW_DIR / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    output: list[dict[str, Any]] = []
    for item in flagged:
        start = max(0.0, float(item["start"]) - pad)
        duration = max(0.2, float(item["end"]) - float(item["start"]) + pad * 2.0)
        clip_path = clips_dir / f"caption_{int(item['index']):04d}_{start:.2f}_{start + duration:.2f}.wav"
        command = [
            str(FFMPEG),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{start:.6f}",
            "-t",
            f"{duration:.6f}",
            "-i",
            str(audio),
            "-ar",
            "48000",
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(clip_path),
        ]
        try:
            subprocess.run(command, check=True)
            output.append({**item, "clip": str(clip_path), "clipStart": round(start, 3), "clipDuration": round(duration, 3)})
        except Exception as error:
            output.append({**item, "clipError": str(error)})
    return output


def transcribe_review_clips(flagged: list[dict[str, Any]], model_name: str) -> list[dict[str, Any]]:
    clips = [item for item in flagged if item.get("clip")]
    if not clips:
        return flagged
    import whisper

    model = whisper.load_model(model_name)
    options = transcribe_options(
        APP_CONFIG,
        prompt_extra="これは字幕レビュー用の短い音声クリップです。音声にない内容を追加しないでください。",
    )
    reviewed: list[dict[str, Any]] = []
    for item in flagged:
        clip = item.get("clip")
        if not clip:
            reviewed.append(item)
            continue
        try:
            result = model.transcribe(str(clip), **options)
            result = filter_low_confidence_segments(result, APP_CONFIG)
            reviewed.append({**item, "reviewTranscript": clean_text(result.get("text"))})
        except Exception as error:
            reviewed.append({**item, "reviewTranscriptError": str(error)})
    return reviewed


def main() -> None:
    parser = argparse.ArgumentParser(description="Review the current project transcript for subtitle QA issues.")
    parser.add_argument("--output", type=Path, default=Path(text_value("subtitleReview", "outputPath", default=str(OUTPUT_REPORTS / "subtitle_review.json"))))
    parser.add_argument(
        "--extract-audio-clips",
        dest="extract_audio_clips",
        action="store_true",
        default=bool_value("subtitleReview", "extractAudioClips", default=False),
        help="Extract short WAV clips around flagged subtitle rows.",
    )
    parser.add_argument("--no-audio-clips", dest="extract_audio_clips", action="store_false")
    parser.add_argument(
        "--transcribe-review",
        action="store_true",
        default=bool_value("subtitleReview", "transcribeReview", default=False),
        help="Re-transcribe extracted review clips with Whisper.",
    )
    parser.add_argument(
        "--review-model",
        default=text_value("subtitleReview", "reviewModel", default=transcribe_model_name(APP_CONFIG)),
    )
    parser.add_argument("--clip-pad", type=float, default=float_value("subtitleReview", "clipPadSeconds", default=1.0))
    args = parser.parse_args()

    manifest, transcript, primary = primary_transcript()
    configured_patterns = suspicious_patterns()
    segments = transcript.get("segments", [])
    if not isinstance(segments, list):
        raise SystemExit("Transcript JSON has no segments array.")
    flagged = []
    for index, segment in enumerate(segments, start=1):
        if not isinstance(segment, dict):
            continue
        issues = segment_issues(segment)
        matches = pattern_matches(clean_text(segment.get("text")), configured_patterns)
        if matches:
            issues.append("configured_pattern")
        if not issues:
            continue
        start = float(segment.get("start") or 0)
        end = float(segment.get("end") or start)
        flagged.append(
            {
                "index": index,
                "start": round(start, 3),
                "end": round(end, 3),
                "time": f"{fmt_time(start)}-{fmt_time(end)}",
                "issues": issues,
                "matchedPatterns": matches,
                "text": clean_text(segment.get("text")),
            }
        )
    if args.extract_audio_clips and flagged:
        flagged = extract_audio_clips(flagged, primary, max(0.0, args.clip_pad))
    if args.transcribe_review and flagged:
        if not args.extract_audio_clips:
            flagged = extract_audio_clips(flagged, primary, max(0.0, args.clip_pad))
        flagged = transcribe_review_clips(flagged, args.review_model)

    report = {
        "source": manifest.get("primarySrt") or manifest.get("outputDir") or str(TRANSCRIPT_MANIFEST),
        "segmentCount": len(segments),
        "flaggedCount": len(flagged),
        "configuredPatternCount": len(configured_patterns),
        "audioClipsEnabled": bool(args.extract_audio_clips),
        "reviewTranscribeEnabled": bool(args.transcribe_review),
        "reviewDir": str(REVIEW_DIR),
        "flagged": flagged,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(args.output.with_suffix(".md"), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
