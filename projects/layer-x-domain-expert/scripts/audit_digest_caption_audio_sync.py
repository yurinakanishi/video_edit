from __future__ import annotations

import json
import math
import sys
import wave
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import render_test_project1_style_preview as renderer


PROJECT_DIR = Path(__file__).resolve().parents[1]
REPORTS_DIR = PROJECT_DIR / "output" / "reports"
AUDIO_DIR = PROJECT_DIR / "output" / "audio"
VIDEOS_DIR = PROJECT_DIR / "output" / "videos"
EDIT_PLAN_PATH = REPORTS_DIR / "edit_plan.json"
APP_SYNC_OFFSETS_PATH = REPORTS_DIR / "app_sync_offsets.json"
REPORT_PATH = REPORTS_DIR / "digest_caption_audio_sync_audit.json"

MASTER_WAV = AUDIO_DIR / "group_wide_mono_16k.wav"
INTERVIEW_WAV = AUDIO_DIR / "cam_person_02_mono_16k.wav"
SEGMENT_DIR = VIDEOS_DIR / "preview_test_project1_style_segments"

JST = timezone(timedelta(hours=9))
SAMPLE_RATE = 16_000
MAX_ALLOWED_CAPTION_DELTA_SEC = 0.12
MAX_ALLOWED_AUDIO_RESIDUAL_SEC = 0.10


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_wav_window(path: Path, start_sec: float, duration_sec: float) -> np.ndarray:
    with wave.open(str(path), "rb") as wav:
        sample_rate = wav.getframerate()
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        if sample_rate != SAMPLE_RATE or channels != 1 or sample_width != 2:
            raise RuntimeError(f"Unexpected wav format for {path}: {sample_rate=} {channels=} {sample_width=}")
        start_frame = max(0, int(round(start_sec * sample_rate)))
        frame_count = max(1, int(round(duration_sec * sample_rate)))
        wav.setpos(min(start_frame, wav.getnframes()))
        raw = wav.readframes(frame_count)
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if len(data) < frame_count:
        data = np.pad(data, (0, frame_count - len(data)))
    return data


def normalize_audio(data: np.ndarray) -> np.ndarray:
    if data.size == 0:
        return data
    data = data.astype(np.float32)
    data = data - float(np.mean(data))
    peak = float(np.max(np.abs(data))) if data.size else 0.0
    if peak > 0:
        data = data / peak
    return data


def fft_correlation_lag(reference: np.ndarray, candidate: np.ndarray, max_lag_sec: float = 0.5) -> dict[str, Any]:
    reference = normalize_audio(reference)
    candidate = normalize_audio(candidate)
    length = min(len(reference), len(candidate))
    reference = reference[:length]
    candidate = candidate[:length]
    if length < SAMPLE_RATE:
        return {"status": "too_short", "lag_sec": None, "correlation": 0.0}

    n = len(reference) + len(candidate) - 1
    nfft = 1 << (n - 1).bit_length()
    corr = np.fft.irfft(np.fft.rfft(candidate, nfft) * np.conj(np.fft.rfft(reference, nfft)), nfft)
    corr = np.concatenate((corr[-(len(reference) - 1) :], corr[: len(candidate)]))
    lags = np.arange(-len(reference) + 1, len(candidate))
    max_lag_samples = int(round(max_lag_sec * SAMPLE_RATE))
    mask = np.abs(lags) <= max_lag_samples
    scoped_corr = corr[mask]
    scoped_lags = lags[mask]
    if scoped_corr.size == 0:
        return {"status": "no_lag_scope", "lag_sec": None, "correlation": 0.0}
    best_index = int(np.argmax(np.abs(scoped_corr)))
    best_lag = int(scoped_lags[best_index])
    overlap = max(1, length - abs(best_lag))
    denom = math.sqrt(float(np.sum(reference * reference)) * float(np.sum(candidate * candidate)))
    coeff = 0.0 if denom == 0.0 else float(scoped_corr[best_index] / denom)
    return {
        "status": "ok",
        "lag_sec": round(best_lag / SAMPLE_RATE, 4),
        "lag_ms": round(best_lag / SAMPLE_RATE * 1000, 1),
        "correlation": round(coeff, 4),
        "overlap_samples": overlap,
    }


def caption_alignment_issues(event: dict[str, Any]) -> list[dict[str, Any]]:
    reference = event.get("reference_source") if isinstance(event.get("reference_source"), dict) else event.get("source")
    ref_in = float((reference or {}).get("in") or 0.0)
    issues = []
    for overlay in event.get("overlays", []):
        if not isinstance(overlay, dict) or overlay.get("type") != "caption":
            continue
        audio_alignment = overlay.get("audio_alignment") if isinstance(overlay.get("audio_alignment"), dict) else {}
        speech_window = audio_alignment.get("speech_window_sec")
        if not isinstance(speech_window, list) or len(speech_window) != 2:
            issues.append({"text": overlay.get("text"), "issue": "missing_speech_window"})
            continue
        expected_start = round(float(speech_window[0]) - ref_in, 3)
        expected_end = round(float(speech_window[1]) - ref_in, 3)
        actual_start = round(float(overlay.get("start") or 0.0), 3)
        actual_end = round(float(overlay.get("end") or 0.0), 3)
        start_delta = round(actual_start - expected_start, 3)
        end_delta = round(actual_end - expected_end, 3)
        # Starts should align tightly with the spoken phrase. Ends may hold
        # briefly after speech so the caption does not feel like it disappears
        # before the utterance finishes.
        ends_too_early = actual_end < expected_end - MAX_ALLOWED_CAPTION_DELTA_SEC
        starts_misaligned = abs(start_delta) > MAX_ALLOWED_CAPTION_DELTA_SEC
        hold_after = round(actual_end - expected_end, 3)
        excessive_hold = hold_after > 0.7
        if starts_misaligned or ends_too_early or excessive_hold:
            issues.append(
                {
                    "text": overlay.get("text"),
                    "expected_local": [expected_start, expected_end],
                    "actual_local": [actual_start, actual_end],
                    "delta": [start_delta, end_delta],
                    "hold_after_speech_sec": hold_after,
                    "matched_phrase": (audio_alignment.get("diagnostics") or {}).get("matched_phrase"),
                }
            )
    return issues


def stale_digest_segments(plan: dict[str, Any]) -> list[dict[str, Any]]:
    stale = []
    for index, event in enumerate(plan.get("timeline", []), start=1):
        if event.get("section") != "digest":
            continue
        segment = SEGMENT_DIR / f"segment_{index:03d}_{event.get('event_id', 'event')}.mp4"
        reusable, reason = renderer.segment_cache_status(segment, event)
        if not reusable:
            stale.append(
                {
                    "index": index,
                    "event_id": event.get("event_id"),
                    "status": reason,
                    "segment": str(segment),
                    "manifest": str(renderer.segment_manifest_path(segment)),
                }
            )
    return stale


def main() -> None:
    plan = read_json(EDIT_PLAN_PATH)
    offsets = read_json(APP_SYNC_OFFSETS_PATH).get("offsets") or {}
    cam_person_02_offset = float(offsets.get("camera3", 7.467854))

    digest_events = [event for event in plan.get("timeline", []) if isinstance(event, dict) and event.get("section") == "digest"]
    event_reports = []
    caption_issue_count = 0
    audio_issue_count = 0

    for event in digest_events:
        reference = event.get("reference_source") if isinstance(event.get("reference_source"), dict) else event.get("source")
        ref_in = float((reference or {}).get("in") or 0.0)
        ref_out = float((reference or {}).get("out") or ref_in)
        duration = max(0.5, ref_out - ref_in)
        pad = 0.4
        master_window_start = max(0.0, ref_in - pad)
        cam_window_start = max(0.0, ref_in + cam_person_02_offset - pad)
        window_duration = duration + pad * 2
        master_audio = read_wav_window(MASTER_WAV, master_window_start, window_duration)
        cam_audio = read_wav_window(INTERVIEW_WAV, cam_window_start, window_duration)
        correlation = fft_correlation_lag(master_audio, cam_audio)
        audio_ok = correlation.get("status") == "ok" and abs(float(correlation.get("lag_sec") or 0.0)) <= MAX_ALLOWED_AUDIO_RESIDUAL_SEC
        if not audio_ok:
            audio_issue_count += 1

        caption_issues = caption_alignment_issues(event)
        caption_issue_count += len(caption_issues)
        event_reports.append(
            {
                "event_id": event.get("event_id"),
                "timeline": [event.get("timeline_start"), event.get("timeline_end")],
                "reference_source": reference,
                "render_audio_expected_source": {
                    "media_id": "cam_person_02",
                    "source_window_sec": [round(ref_in + cam_person_02_offset, 3), round(ref_out + cam_person_02_offset, 3)],
                    "sync_offset_sec": cam_person_02_offset,
                },
                "caption_issue_count": len(caption_issues),
                "caption_issues": caption_issues,
                "audio_sync_residual": correlation,
                "audio_sync_ok": audio_ok,
            }
        )

    stale_segments = stale_digest_segments(plan)
    report = {
        "schema_version": "digest_caption_audio_sync_audit.v1",
        "generated_at": datetime.now(JST).isoformat(timespec="seconds"),
        "method": [
            "Compare each digest caption's local display window with its keyword-derived speech_window_sec.",
            "Cross-correlate group_wide master audio against the render audio source cam_person_02 at the expected app sync offset.",
            "Check whether existing rendered digest segments are reusable under the new fingerprint cache policy.",
        ],
        "digest_event_count": len(digest_events),
        "caption_issue_count": caption_issue_count,
        "audio_sync_issue_count": audio_issue_count,
        "stale_or_unfingerprinted_digest_segment_count": len(stale_segments),
        "stale_or_unfingerprinted_digest_segments": stale_segments,
        "ready_in_edit_plan": caption_issue_count == 0 and audio_issue_count == 0,
        "rendered_preview_reliable": len(stale_segments) == 0,
        "events": event_reports,
    }
    write_json(REPORT_PATH, report)
    print(json.dumps({k: report[k] for k in ("digest_event_count", "caption_issue_count", "audio_sync_issue_count", "stale_or_unfingerprinted_digest_segment_count", "ready_in_edit_plan", "rendered_preview_reliable")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
