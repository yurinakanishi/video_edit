from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "source"
OUTPUT_ROOT = PROJECT_ROOT / "output"
REPORTS = OUTPUT_ROOT / "reports"
STATE_PATH = PROJECT_ROOT / "project_state.json"
FFMPEG_DEFAULT = Path(r"C:\ProgramData\chocolatey\bin\ffmpeg.exe")
JST = timezone(timedelta(hours=9))

MEDIA = [
    ("master", "group_wide", SOURCE_ROOT / "video" / "three people.mp4"),
    ("camera2", "cam_person_01", SOURCE_ROOT / "video" / "person-left.mp4"),
    ("camera3", "cam_person_02", SOURCE_ROOT / "video" / "person-middle.mp4"),
    ("camera4", "cam_person_03", SOURCE_ROOT / "video" / "person-right.mp4"),
]

ROLE_MEDIA_ID = {role: media_id for role, media_id, _ in MEDIA}


def now_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def ffmpeg_path() -> str:
    state = read_json(STATE_PATH, {})
    configured = str(((state.get("tools") or {}).get("ffmpeg")) or "").strip()
    if configured and Path(configured).exists():
        return configured
    if FFMPEG_DEFAULT.exists():
        return str(FFMPEG_DEFAULT)
    return "ffmpeg"


def decode_audio(path: Path, *, sample_rate: int, duration: float, start: float = 0.0) -> np.ndarray:
    if not path.exists():
        raise FileNotFoundError(path)
    command = [
        ffmpeg_path(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{start:.6f}",
        "-t",
        f"{duration:.6f}",
        "-i",
        str(path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "s16le",
        "-",
    ]
    raw = subprocess.check_output(command, cwd=PROJECT_ROOT.parents[1])
    if not raw:
        raise RuntimeError(f"No audio decoded from {path}")
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def moving_average(values: np.ndarray, window: int) -> np.ndarray:
    window = max(1, int(window))
    if window <= 1:
        return values
    kernel = np.ones(window, dtype=np.float32) / float(window)
    return np.convolve(values, kernel, mode="same")


def transient_envelope(audio: np.ndarray, *, sample_rate: int, hop_ms: float, frame_ms: float) -> np.ndarray:
    hop = max(1, round(sample_rate * hop_ms / 1000.0))
    frame = max(hop, round(sample_rate * frame_ms / 1000.0))
    squared = audio * audio
    energy = np.convolve(squared, np.ones(frame, dtype=np.float32), mode="valid")[::hop]
    energy = np.sqrt(np.maximum(energy / frame, 0.0))
    local_floor = moving_average(energy, max(25, round(250.0 / hop_ms)))
    onset = np.maximum(0.0, energy - local_floor)
    return onset.astype(np.float32)


def clap_candidates(
    envelope: np.ndarray,
    *,
    hop_seconds: float,
    count: int,
    min_separation_seconds: float,
) -> list[dict[str, float]]:
    if envelope.size == 0:
        return []
    floor = float(np.median(envelope))
    spread = float(np.median(np.abs(envelope - floor))) or float(np.std(envelope)) or 1e-6
    score = (envelope - floor) / max(spread, 1e-6)
    separation = max(1, round(min_separation_seconds / hop_seconds))
    ranked = np.argsort(score)[::-1]
    chosen: list[int] = []
    for index in ranked:
        if float(score[index]) <= 0:
            break
        if all(abs(int(index) - prior) >= separation for prior in chosen):
            chosen.append(int(index))
        if len(chosen) >= count:
            break
    return [
        {
            "time": round(index * hop_seconds, 6),
            "score": round(float(score[index]), 4),
            "envelope": round(float(envelope[index]), 8),
        }
        for index in sorted(chosen)
    ]


def normalized_clip(audio: np.ndarray, center_sample: int, radius_samples: int) -> np.ndarray:
    start = max(0, center_sample - radius_samples)
    end = min(len(audio), center_sample + radius_samples)
    clip = np.asarray(audio[start:end], dtype=np.float32)
    clip = clip - float(np.mean(clip))
    norm = float(np.linalg.norm(clip))
    return clip / norm if norm > 1e-9 else clip


def best_lag(reference: np.ndarray, candidate: np.ndarray, *, max_lag_samples: int) -> tuple[int, float]:
    if len(reference) < 64 or len(candidate) < 64:
        return 0, -1.0
    max_lag_samples = max(1, min(max_lag_samples, min(len(reference), len(candidate)) // 2))
    best = (0, -1.0)
    for lag in range(-max_lag_samples, max_lag_samples + 1):
        if lag < 0:
            left = reference[-lag:]
            right = candidate[: len(left)]
        elif lag > 0:
            left = reference[: len(reference) - lag]
            right = candidate[lag : lag + len(left)]
        else:
            left = reference
            right = candidate[: len(left)]
        usable = min(len(left), len(right))
        if usable < 64:
            continue
        left = left[:usable]
        right = right[:usable]
        denom = float(np.linalg.norm(left) * np.linalg.norm(right))
        score = float(np.dot(left, right) / denom) if denom > 1e-9 else -1.0
        if score > best[1]:
            best = (lag, score)
    return best


def normalized(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float32)
    values = values - float(np.mean(values))
    norm = float(np.linalg.norm(values))
    return values / norm if norm > 1e-9 else values


def waveform_envelope(audio: np.ndarray, *, sample_rate: int, hop_ms: float, frame_ms: float) -> np.ndarray:
    hop = max(1, round(sample_rate * hop_ms / 1000.0))
    frame = max(hop, round(sample_rate * frame_ms / 1000.0))
    usable = ((len(audio) - frame) // hop) * hop if len(audio) >= frame else 0
    if usable <= 0:
        return np.array([], dtype=np.float32)
    squared = audio * audio
    energy = np.convolve(squared, np.ones(frame, dtype=np.float32), mode="valid")[:usable:hop]
    rms = np.sqrt(np.maximum(energy / frame, 0.0))
    rms = np.log1p(rms * 40.0)
    # Mix sustained speech energy and transient changes so both speech and clap evidence count.
    transient = np.maximum(0.0, np.diff(rms, prepend=rms[0]))
    mixed = normalized(rms) * 0.55 + normalized(transient) * 0.45
    return normalized(mixed)


def waveform_match(
    reference_audio: np.ndarray,
    source_audio: np.ndarray,
    *,
    sample_rate: int,
    hop_ms: float,
    frame_ms: float,
    max_offset_seconds: float,
) -> dict[str, Any]:
    reference = waveform_envelope(reference_audio, sample_rate=sample_rate, hop_ms=hop_ms, frame_ms=frame_ms)
    source = waveform_envelope(source_audio, sample_rate=sample_rate, hop_ms=hop_ms, frame_ms=frame_ms)
    usable = min(len(reference), len(source))
    if usable < 100:
        return {"status": "unavailable", "reason": "not enough decoded audio for waveform comparison"}
    reference = reference[:usable]
    source = source[:usable]
    max_lag_frames = round(max_offset_seconds * 1000.0 / hop_ms)
    lag_frames, score = best_lag(reference, source, max_lag_samples=max_lag_frames)
    offset = lag_frames * hop_ms / 1000.0
    return {
        "status": "matched" if score >= 0.35 else "weak_match",
        "offsetSeconds": round(offset, 6),
        "offsetMilliseconds": round(offset * 1000.0, 3),
        "lagFrames": int(lag_frames),
        "hopMilliseconds": hop_ms,
        "correlation": round(score, 6),
    }


def audio_statistics(audio: np.ndarray) -> dict[str, Any]:
    if len(audio) == 0:
        return {"rms": 0.0, "peak": 0.0, "peakDbfs": None, "rmsDbfs": None}
    rms = float(np.sqrt(np.mean(audio * audio)))
    peak = float(np.max(np.abs(audio)))

    def dbfs(value: float) -> float | None:
        if value <= 1e-12:
            return None
        return round(20.0 * float(np.log10(value)), 2)

    return {
        "rms": round(rms, 8),
        "peak": round(peak, 8),
        "rmsDbfs": dbfs(rms),
        "peakDbfs": dbfs(peak),
        "likelySilent": bool(rms < 0.0005 and peak < 0.01),
        "usableForWaveformSync": bool(rms >= 0.0005 and peak >= 0.01),
    }


def combine_sync(clap: dict[str, Any], waveform: dict[str, Any]) -> dict[str, Any]:
    clap_ok = clap.get("status") == "matched"
    waveform_ok = waveform.get("status") == "matched"
    if clap_ok and waveform_ok:
        delta = abs(float(clap["offsetSeconds"]) - float(waveform["offsetSeconds"]))
        return {
            "status": "confirmed" if delta <= 0.05 else "conflict",
            "preferred": "clap" if delta <= 0.05 else "manual_review",
            "offsetSeconds": round(float(clap["offsetSeconds"]), 6),
            "offsetMilliseconds": round(float(clap["offsetSeconds"]) * 1000.0, 3),
            "waveformClapDeltaMilliseconds": round(delta * 1000.0, 3),
        }
    if clap_ok:
        return {
            "status": "clap_only",
            "preferred": "clap",
            "offsetSeconds": round(float(clap["offsetSeconds"]), 6),
            "offsetMilliseconds": round(float(clap["offsetSeconds"]) * 1000.0, 3),
        }
    if waveform_ok:
        return {
            "status": "waveform_only",
            "preferred": "waveform",
            "offsetSeconds": round(float(waveform["offsetSeconds"]), 6),
            "offsetMilliseconds": round(float(waveform["offsetSeconds"]) * 1000.0, 3),
        }
    return {"status": "unconfirmed", "preferred": "none"}


def failed_audio_result(stats: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "failed",
        "reason": "audio_track_near_silence",
        "rmsDbfs": stats.get("rmsDbfs"),
        "peakDbfs": stats.get("peakDbfs"),
        "confidence": 0.0,
    }


def sync_status_for_combined(combined: dict[str, Any]) -> str:
    if combined.get("status") in {"confirmed", "clap_only", "waveform_only"}:
        return "synced"
    if combined.get("status") == "conflict":
        return "needs_review"
    return "needs_review"


def sync_map_entry(role: str, match: dict[str, Any], stats: dict[str, Any], *, analysis_start: float) -> dict[str, Any]:
    media_id = ROLE_MEDIA_ID.get(role, role)
    audio_analysis = {
        "rms_dbfs": stats.get("rmsDbfs"),
        "max_dbfs": stats.get("peakDbfs"),
        "usable_for_waveform_sync": bool(stats.get("usableForWaveformSync")),
    }
    if role == "master":
        return {
            "media_id": media_id,
            "role": role,
            "sync_status": "master",
            "sync_model": "identity",
            "offset_sec": 0.0,
            "app_offset_sec": 0.0,
            "rate": 1.0,
            "confidence": 1.0,
            "audio_analysis": audio_analysis,
            "anchors": [],
        }

    combined = match.get("combined") if isinstance(match.get("combined"), dict) else {}
    clap = match.get("clap") if isinstance(match.get("clap"), dict) else {}
    waveform = match.get("waveform") if isinstance(match.get("waveform"), dict) else {}
    preferred = str(combined.get("preferred") or "none")
    app_offset = combined.get("offsetSeconds")
    mapped_offset = round(-float(app_offset), 6) if isinstance(app_offset, (int, float)) else None
    confidence = 0.0 if mapped_offset is None else 0.9 if combined.get("status") == "confirmed" else 0.75
    anchors: list[dict[str, Any]] = []
    if preferred == "clap" and isinstance(clap.get("offsetSeconds"), (int, float)):
        anchors.append(
            {
                "anchor_id": f"{role}_audio_clap_001",
                "camera_time": clap.get("sourceClapTime"),
                "master_time": clap.get("referenceClapTime"),
                "method": "audio_clap_transient_cross_correlation",
                "confidence": clap.get("correlation"),
                "lag_milliseconds": clap.get("lagMilliseconds"),
            }
        )
    if preferred == "waveform" and isinstance(waveform.get("offsetSeconds"), (int, float)):
        camera_time = round(analysis_start + float(waveform["offsetSeconds"]), 6)
        anchors.append(
            {
                "anchor_id": f"{role}_waveform_corr_001",
                "camera_time": camera_time,
                "master_time": round(analysis_start, 6),
                "method": "broad_waveform_cross_correlation",
                "confidence": waveform.get("correlation"),
            }
        )

    needs_visual = mapped_offset is None or combined.get("status") in {"unconfirmed", "conflict"} or confidence < 0.9
    return {
        "media_id": media_id,
        "role": role,
        "sync_status": sync_status_for_combined(combined),
        "sync_model": "offset_only",
        "offset_sec": mapped_offset,
        "app_offset_sec": app_offset,
        "rate": 1.0,
        "method": "not_yet_determined" if needs_visual else preferred,
        "confidence": confidence,
        "audio_analysis": audio_analysis,
        "anchors": anchors,
        "manual_review_required": bool(needs_visual),
        "recommended_next_methods": []
        if not needs_visual
        else [
            "timecode_or_ltc_metadata",
            "visual_clap_frame",
            "mouth_movement_phrase_match",
            "hand_gesture_anchor",
            "manual_marker",
        ],
        "failed_audio_correlation": failed_audio_result(stats) if not stats.get("usableForWaveformSync") else None,
    }


def build_sync_map(matches: dict[str, Any], stats: dict[str, dict[str, Any]], *, analysis_start: float) -> dict[str, Any]:
    return {
        "schema_version": "sync_map.v1",
        "project_id": "layer-x-domain-expert",
        "generated_at": now_iso(),
        "master_clock": {
            "media_id": "group_wide",
            "role": "master",
            "reason": "best available scratch audio and wide reference",
        },
        "time_mapping": {
            "formula": "master_time = camera_time * rate + offset_sec",
            "app_offsets_formula": "source_time = master_timeline_time + app_offset_sec",
        },
        "media_sync": [
            sync_map_entry(role, matches.get(role, {}), stats.get(role, {}), analysis_start=analysis_start)
            for role in ("master", "camera2", "camera3", "camera4")
        ],
        "rules": {
            "do_not_use_failed_audio_correlation": True,
            "require_two_anchors_for_clips_longer_than_20_minutes": True,
            "manual_review_if_confidence_below": 0.9,
            "preferred_method_order": [
                "timecode_ltc_metadata",
                "usable_scratch_audio_waveform",
                "audio_or_visual_clap_slate",
                "visual_mouth_hand_scene_events",
                "transcript_rough_sync",
                "manual_anchors_with_drift_correction",
            ],
        },
    }


def match_source_to_reference(
    reference_audio: np.ndarray,
    source_audio: np.ndarray,
    reference_candidates: list[dict[str, float]],
    source_candidates: list[dict[str, float]],
    *,
    sample_rate: int,
    max_candidate_delta: float,
    window_seconds: float,
    max_lag_ms: float,
    analysis_start: float,
) -> dict[str, Any]:
    radius = round(window_seconds * sample_rate / 2.0)
    max_lag = round(max_lag_ms * sample_rate / 1000.0)
    best: dict[str, Any] | None = None
    for ref in reference_candidates:
        ref_time = float(ref["time"])
        ref_clip = normalized_clip(reference_audio, round((ref_time - analysis_start) * sample_rate), radius)
        for cand in source_candidates:
            cand_time = float(cand["time"])
            if abs(cand_time - ref_time) > max_candidate_delta:
                continue
            cand_clip = normalized_clip(source_audio, round((cand_time - analysis_start) * sample_rate), radius)
            lag_samples, score = best_lag(ref_clip, cand_clip, max_lag_samples=max_lag)
            refined_source_time = cand_time + lag_samples / sample_rate
            offset = refined_source_time - ref_time
            item = {
                "referenceClapTime": round(ref_time, 6),
                "sourceClapTime": round(cand_time, 6),
                "lagSamples": int(lag_samples),
                "lagMilliseconds": round(lag_samples * 1000.0 / sample_rate, 3),
                "offsetSeconds": round(offset, 6),
                "offsetMilliseconds": round(offset * 1000.0, 3),
                "correlation": round(score, 6),
                "referenceCandidateScore": ref.get("score"),
                "sourceCandidateScore": cand.get("score"),
            }
            if best is None or item["correlation"] > best["correlation"]:
                best = item
    if best is None:
        return {"status": "unmatched", "reason": "no clap candidates matched within the search delta"}
    best["status"] = "matched" if best["correlation"] >= 0.35 else "weak_match"
    return best


def main() -> None:
    parser = argparse.ArgumentParser(description="Find clap-like transients and confirm camera sync at millisecond precision.")
    parser.add_argument("--reference-role", default="master")
    parser.add_argument("--duration", type=float, default=180.0, help="Seconds to scan from the start of each interview source.")
    parser.add_argument("--start", type=float, default=0.0)
    parser.add_argument("--sample-rate", type=int, default=48000)
    parser.add_argument("--hop-ms", type=float, default=1.0)
    parser.add_argument("--frame-ms", type=float, default=4.0)
    parser.add_argument("--candidate-count", type=int, default=8)
    parser.add_argument("--candidate-delta", type=float, default=5.0)
    parser.add_argument("--window-seconds", type=float, default=0.35)
    parser.add_argument("--max-lag-ms", type=float, default=80.0)
    parser.add_argument("--waveform-hop-ms", type=float, default=10.0)
    parser.add_argument("--waveform-frame-ms", type=float, default=40.0)
    parser.add_argument("--waveform-max-offset", type=float, default=10.0)
    parser.add_argument("--output", type=Path, default=REPORTS / "audio_sync_clap_analysis.json")
    parser.add_argument("--offset-output", type=Path, default=REPORTS / "app_sync_offsets.json")
    parser.add_argument("--sync-map-output", type=Path, default=REPORTS / "sync_map.json")
    args = parser.parse_args()

    sources = [
        {"role": role, "media_id": media_id, "path": path}
        for role, media_id, path in MEDIA
        if path.exists()
    ]
    reference = next((item for item in sources if item["role"] == args.reference_role), None)
    if reference is None:
        raise SystemExit(f"Reference role not found: {args.reference_role}")

    decoded: dict[str, np.ndarray] = {}
    candidates: dict[str, list[dict[str, float]]] = {}
    stats: dict[str, dict[str, Any]] = {}
    hop_seconds = args.hop_ms / 1000.0
    for item in sources:
        audio = decode_audio(item["path"], sample_rate=args.sample_rate, start=args.start, duration=args.duration)
        decoded[item["role"]] = audio
        stats[item["role"]] = audio_statistics(audio)
        envelope = transient_envelope(audio, sample_rate=args.sample_rate, hop_ms=args.hop_ms, frame_ms=args.frame_ms)
        candidates[item["role"]] = clap_candidates(
            envelope,
            hop_seconds=hop_seconds,
            count=args.candidate_count,
            min_separation_seconds=0.4,
        )
        for candidate in candidates[item["role"]]:
            candidate["time"] = round(float(candidate["time"]) + args.start, 6)

    reference_candidates = candidates[reference["role"]]
    matches: dict[str, Any] = {}
    offsets: dict[str, float] = {reference["role"]: 0.0}
    for item in sources:
        if item["role"] == reference["role"]:
            matches[item["role"]] = {
                "status": "reference",
                "offsetSeconds": 0.0,
                "offsetMilliseconds": 0.0,
                "referenceClapCandidates": reference_candidates,
            }
            continue
        if not stats[item["role"]].get("usableForWaveformSync"):
            clap_match = failed_audio_result(stats[item["role"]])
            broad_match = failed_audio_result(stats[item["role"]])
        else:
            clap_match = match_source_to_reference(
                decoded[reference["role"]],
                decoded[item["role"]],
                reference_candidates,
                candidates[item["role"]],
                sample_rate=args.sample_rate,
            max_candidate_delta=args.candidate_delta,
            window_seconds=args.window_seconds,
            max_lag_ms=args.max_lag_ms,
            analysis_start=args.start,
        )
            broad_match = waveform_match(
                decoded[reference["role"]],
                decoded[item["role"]],
                sample_rate=args.sample_rate,
                hop_ms=args.waveform_hop_ms,
                frame_ms=args.waveform_frame_ms,
                max_offset_seconds=args.waveform_max_offset,
            )
        combined = combine_sync(clap_match, broad_match)
        matches[item["role"]] = {
            "combined": combined,
            "clap": clap_match,
            "waveform": broad_match,
        }
        if combined.get("preferred") in {"clap", "waveform"}:
            offsets[item["role"]] = float(combined["offsetSeconds"])

    usable = [
        item
        for role, item in matches.items()
        if role != reference["role"] and (item.get("combined") or {}).get("status") == "confirmed"
    ]
    usable_fallback = [
        item
        for role, item in matches.items()
        if role != reference["role"] and (item.get("combined") or {}).get("preferred") in {"clap", "waveform"}
    ]
    payload = {
        "schema_version": "audio_sync_clap_analysis.v1",
        "project_id": "layer-x-domain-expert",
        "generated_at": now_iso(),
        "time_unit": "seconds",
        "sample_rate": args.sample_rate,
        "analysis_range": {"start": args.start, "duration": args.duration},
        "method": {
            "clap_detection": "short-window transient energy with local floor subtraction",
            "confirmation": "normalized waveform cross-correlation around candidate clap windows",
            "waveform_check": "broad waveform/transient-envelope cross-correlation across the scanned range",
            "precision": "sample lag reported in milliseconds",
        },
        "reference_role": reference["role"],
        "reference_media_id": reference["media_id"],
        "sources": [
            {
                "role": item["role"],
                "media_id": item["media_id"],
                "path": str(item["path"]),
                "audio_statistics": stats[item["role"]],
                "clap_candidates": candidates[item["role"]],
            }
            for item in sources
        ],
        "matches": matches,
        "offsets": offsets,
        "status": "confirmed"
        if len(usable) == len(sources) - 1
        else "partial"
        if usable_fallback
        else "unconfirmed",
    }
    write_json(args.output, payload)
    sync_map = build_sync_map(matches, stats, analysis_start=args.start)
    write_json(args.sync_map_output, sync_map)
    write_json(
        args.offset_output,
        {
            "version": 1,
            "schema_version": "app_sync_offsets.v1",
            "generatedAt": now_iso(),
            "source": str(args.output),
            "method": "clap_plus_waveform_cross_correlation",
            "referenceRole": reference["role"],
            "offsets": offsets,
            "matches": matches,
        },
    )
    print(
        json.dumps(
            {
                "analysis": str(args.output),
                "offsets": str(args.offset_output),
                "sync_map": str(args.sync_map_output),
                "status": payload["status"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
