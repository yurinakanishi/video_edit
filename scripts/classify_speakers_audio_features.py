from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from project_paths import OUTPUT_REPORTS
from video_edit_app_config import load_app_config, nested, selected_subtitle_path


APP_CONFIG = load_app_config()
DEFAULT_SAMPLE_RATE = 16000


@dataclass(frozen=True)
class Caption:
    index: int
    start_raw: str
    end_raw: str
    start: float
    end: float
    text: str


def parse_time(value: str) -> float | None:
    text = value.strip().replace(",", ".")
    parts = text.split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        return float(text)
    except ValueError:
        return None


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
            index = len(captions) + 1
        start_raw, end_raw = [part.strip() for part in rows[1].split("-->", 1)]
        start = parse_time(start_raw)
        end = parse_time(end_raw)
        if start is None or end is None or end <= start:
            continue
        captions.append(Caption(index=index, start_raw=start_raw, end_raw=end_raw, start=start, end=end, text="".join(rows[2:])))
    return captions


def configured_audio_path() -> Path | None:
    for keys in (
        ("subtitleSpeakers", "audioFeaturePath"),
        ("workflow", "inputVideoPath"),
        ("render", "outputPath"),
        ("render", "baseOutputPath"),
    ):
        value = nested(APP_CONFIG, *keys, default="")
        if value:
            path = Path(str(value))
            if path.exists():
                return path
    manifest = nested(APP_CONFIG, "assets", "mediaManifest", default={})
    files = manifest.get("files", []) if isinstance(manifest, dict) else []
    if isinstance(files, list):
        external = next(
            (
                item
                for item in files
                if isinstance(item, dict)
                and item.get("kind") == "audio"
                and item.get("role") == "external"
                and item.get("path")
            ),
            None,
        )
        if isinstance(external, dict):
            path = Path(str(external.get("path") or ""))
            if path.exists():
                return path
    return None


def decode_audio(path: Path, sample_rate: int) -> np.ndarray:
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(path),
        "-vn",
        "-acodec",
        "pcm_f32le",
        "-ar",
        str(sample_rate),
        "-ac",
        "2",
        "-f",
        "f32le",
        "pipe:1",
    ]
    raw = subprocess.check_output(command)
    if not raw:
        raise RuntimeError(f"no audio decoded from {path}")
    audio = np.frombuffer(raw, dtype=np.float32)
    usable = len(audio) - (len(audio) % 2)
    if usable <= 0:
        raise RuntimeError(f"decoded audio has no stereo samples: {path}")
    return audio[:usable].reshape(-1, 2)


def safe_db(value: float) -> float:
    return 20.0 * math.log10(max(value, 1e-12))


def frame_audio(segment: np.ndarray, sample_rate: int) -> list[np.ndarray]:
    frame = max(160, int(sample_rate * 0.02))
    hop = max(80, int(sample_rate * 0.01))
    if len(segment) < frame:
        return [segment]
    return [segment[start : start + frame] for start in range(0, len(segment) - frame + 1, hop)]


def active_voice_audio(segment: np.ndarray, sample_rate: int) -> np.ndarray:
    frames = frame_audio(segment, sample_rate)
    if not frames:
        return segment
    energies = np.array([float(np.sqrt(np.mean(frame * frame) + 1e-12)) for frame in frames], dtype=np.float64)
    if len(energies) == 0:
        return segment
    threshold = max(float(np.percentile(energies, 55)), float(np.max(energies)) * 0.12)
    active = [frame for frame, energy in zip(frames, energies) if float(energy) >= threshold]
    if not active:
        active = frames
    return np.concatenate(active, axis=0)


def spectral_features(mono: np.ndarray, sample_rate: int) -> dict[str, float]:
    if len(mono) < 256:
        return {"centroidHz": 0.0, "highRatio": 0.0, "lowRatio": 0.0, "midRatio": 0.0, "zcr": 0.0}
    size = min(len(mono), 4096)
    window = np.hanning(size).astype(np.float32)
    slice_audio = mono[:size] * window
    spectrum = np.abs(np.fft.rfft(slice_audio)).astype(np.float64) + 1e-12
    freqs = np.fft.rfftfreq(size, 1.0 / sample_rate)
    centroid = float(np.sum(freqs * spectrum) / np.sum(spectrum))
    powers = spectrum * spectrum

    def band_power(lo: float, hi: float) -> float:
        mask = (freqs >= lo) & (freqs < hi)
        return float(np.sum(powers[mask]))

    low = band_power(80, 500)
    mid = band_power(500, 2000)
    high = band_power(2000, 7500)
    total = low + mid + high + 1e-12
    zero_crossings = np.count_nonzero(np.diff(np.signbit(mono)))
    return {
        "centroidHz": centroid,
        "highRatio": high / total,
        "lowRatio": low / total,
        "midRatio": mid / total,
        "zcr": float(zero_crossings / max(1, len(mono) - 1)),
    }


def caption_features(caption: Caption, audio: np.ndarray, sample_rate: int) -> dict[str, Any]:
    start = max(0, int(caption.start * sample_rate))
    end = min(len(audio), max(start + 1, int(caption.end * sample_rate)))
    raw = audio[start:end]
    if len(raw) == 0:
        return {"available": False, "reason": "empty audio segment"}
    active = active_voice_audio(raw, sample_rate)
    left = active[:, 0]
    right = active[:, 1]
    mono = active.mean(axis=1)
    rms_l = float(np.sqrt(np.mean(left * left) + 1e-12))
    rms_r = float(np.sqrt(np.mean(right * right) + 1e-12))
    rms_mono = float(np.sqrt(np.mean(mono * mono) + 1e-12))
    peak = float(np.max(np.abs(active))) if active.size else 0.0
    corr = float(np.corrcoef(left, right)[0, 1]) if len(active) > 3 and np.std(left) > 1e-9 and np.std(right) > 1e-9 else 0.0
    spectrum = spectral_features(mono, sample_rate)
    return {
        "available": True,
        "duration": round(caption.end - caption.start, 3),
        "activeDuration": round(len(active) / sample_rate, 3),
        "rmsLeft": round(rms_l, 7),
        "rmsRight": round(rms_r, 7),
        "rmsMono": round(rms_mono, 7),
        "dbfsMono": round(safe_db(rms_mono), 3),
        "peak": round(peak, 7),
        "crestDb": round(safe_db(peak) - safe_db(rms_mono), 3),
        "lrDb": round(safe_db(rms_l) - safe_db(rms_r), 3),
        "lrEnergyRatio": round((rms_l + 1e-12) / (rms_r + 1e-12), 5),
        "lrCorrelation": round(corr, 5),
        **{key: round(value, 6) for key, value in spectrum.items()},
    }


def robust_stats(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"median": None, "mean": None, "p10": None, "p90": None}
    arr = np.array(values, dtype=np.float64)
    return {
        "median": round(float(np.median(arr)), 4),
        "mean": round(float(np.mean(arr)), 4),
        "p10": round(float(np.percentile(arr, 10)), 4),
        "p90": round(float(np.percentile(arr, 90)), 4),
    }


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", text)


def interviewer_text_hint(text: str) -> bool:
    normalized = normalize_text(text)
    if normalized in {"確かに", "確かに確かに", "ありがとうございます", "そうです、ありがとうございます"}:
        return True
    if re.search(r"(でしょうか|何でしょうか|感じますか|思いますか|教えてください|聞かせてください)[？?]?$", normalized):
        return True
    return False


def onscreen_text_hint(text: str) -> bool:
    normalized = normalize_text(text)
    if re.search(r"(と思います|と思うんですよね|という形だと思うので|なんですよね|じゃないですか)$", normalized):
        return True
    return False


def feature_vector(features: dict[str, Any]) -> np.ndarray:
    return np.array(
        [
            float(features.get("lrDb") or 0.0) / 6.0,
            float(features.get("dbfsMono") or -30.0) / 30.0,
            float(features.get("centroidHz") or 0.0) / 3000.0,
            float(features.get("highRatio") or 0.0) * 3.0,
            float(features.get("lowRatio") or 0.0),
            float(features.get("zcr") or 0.0) * 10.0,
        ],
        dtype=np.float64,
    )


def classify_rows(
    rows: list[dict[str, Any]],
    interviewer_lr_threshold: float,
    onscreen_lr_threshold: float,
    ambiguous_lr_abs: float,
) -> None:
    for row in rows:
        features = row.get("audioFeatures", {})
        if not features.get("available"):
            row["role"] = "onscreen"
            row["confidence"] = 0.1
            row["reason"] = "audio unavailable; default onscreen"
            continue
        lr_db = float(features.get("lrDb") or 0.0)
        if lr_db >= interviewer_lr_threshold:
            row["role"] = "interviewer"
            row["confidence"] = round(min(0.98, 0.62 + abs(lr_db) / 12.0), 3)
            row["reason"] = f"left-channel dominant voice lrDb={lr_db:.2f}"
        elif lr_db <= onscreen_lr_threshold:
            row["role"] = "onscreen"
            row["confidence"] = round(min(0.98, 0.62 + abs(lr_db) / 12.0), 3)
            row["reason"] = f"right-channel dominant voice lrDb={lr_db:.2f}"
        else:
            row["role"] = "ambiguous"
            row["confidence"] = round(max(0.2, abs(lr_db) / max(ambiguous_lr_abs, 0.1)), 3)
            row["reason"] = f"weak channel separation lrDb={lr_db:.2f}"

    interviewer_vectors = [
        feature_vector(row["audioFeatures"])
        for row in rows
        if row.get("role") == "interviewer" and float(row["audioFeatures"].get("duration") or 0.0) >= 0.4
    ]
    onscreen_vectors = [
        feature_vector(row["audioFeatures"])
        for row in rows
        if row.get("role") == "onscreen" and float(row["audioFeatures"].get("duration") or 0.0) >= 0.4
    ]
    interviewer_centroid = np.median(np.vstack(interviewer_vectors), axis=0) if interviewer_vectors else None
    onscreen_centroid = np.median(np.vstack(onscreen_vectors), axis=0) if onscreen_vectors else None

    for row in rows:
        if row.get("role") != "ambiguous":
            continue
        text = str(row.get("text") or "")
        vector = feature_vector(row["audioFeatures"])
        assigned = None
        if interviewer_centroid is not None and onscreen_centroid is not None:
            interviewer_distance = float(np.linalg.norm(vector - interviewer_centroid))
            onscreen_distance = float(np.linalg.norm(vector - onscreen_centroid))
            row["acousticDistance"] = {
                "interviewer": round(interviewer_distance, 5),
                "onscreen": round(onscreen_distance, 5),
            }
            lr_db = float(row["audioFeatures"].get("lrDb") or 0.0)
            # Acoustic centroids are weaker than channel balance. Use them only when the
            # channel sign also points that way; otherwise short clipped captions drift.
            if abs(interviewer_distance - onscreen_distance) > 0.25 and onscreen_distance < interviewer_distance and lr_db < -0.25:
                assigned = "onscreen"
                row["reason"] += f"; nearest acoustic centroid={assigned}"
                row["confidence"] = max(float(row["confidence"]), 0.55)
        if assigned is None and interviewer_text_hint(text):
            assigned = "interviewer"
            row["reason"] += "; interviewer text hint"
            row["confidence"] = max(float(row["confidence"]), 0.48)
        if assigned is None and onscreen_text_hint(text):
            assigned = "onscreen"
            row["reason"] += "; onscreen text hint"
            row["confidence"] = max(float(row["confidence"]), 0.48)
        row["role"] = assigned or "onscreen"
        if assigned is None:
            row["reason"] += "; default onscreen for ambiguous audio"

    for index, row in enumerate(rows):
        if float(row.get("confidence") or 0.0) >= 0.45:
            continue
        previous_role = next((rows[pos]["role"] for pos in range(index - 1, -1, -1) if rows[pos].get("role") != "ambiguous"), None)
        next_role = next((rows[pos]["role"] for pos in range(index + 1, len(rows)) if rows[pos].get("role") != "ambiguous"), None)
        if previous_role and previous_role == next_role:
            row["role"] = previous_role
            row["reason"] += f"; smoothed between neighboring {previous_role} captions"
            row["confidence"] = max(float(row.get("confidence") or 0.0), 0.5)


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify subtitle speaker roles from stereo audio features.")
    parser.add_argument("--srt", type=Path, default=selected_subtitle_path(APP_CONFIG, extensions=(".srt",)))
    parser.add_argument("--audio", type=Path, default=configured_audio_path())
    parser.add_argument("--output", type=Path, default=Path(str(nested(APP_CONFIG, "subtitleSpeakers", "outputPath", default=str(OUTPUT_REPORTS / "full_transcript_speaker_roles.json")))))
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--sample-rate", type=int, default=DEFAULT_SAMPLE_RATE)
    parser.add_argument("--interviewer-lr-threshold", type=float, default=float(nested(APP_CONFIG, "subtitleSpeakers", "interviewerLrDbThreshold", default=1.5)))
    parser.add_argument("--onscreen-lr-threshold", type=float, default=float(nested(APP_CONFIG, "subtitleSpeakers", "onscreenLrDbThreshold", default=-1.5)))
    args = parser.parse_args()

    if args.srt is None or not args.srt.exists():
        raise SystemExit("SRT file is required. Pass --srt or configure render.subtitlePath.")
    if args.audio is None or not args.audio.exists():
        raise SystemExit("Audio or video file is required. Pass --audio or configure subtitleSpeakers.audioFeaturePath.")
    captions = parse_srt(args.srt)
    if not captions:
        raise SystemExit(f"No captions parsed from {args.srt}")

    audio = decode_audio(args.audio, args.sample_rate)
    rows: list[dict[str, Any]] = []
    for caption in captions:
        rows.append(
            {
                **asdict(caption),
                "audioFeatures": caption_features(caption, audio, args.sample_rate),
            }
        )
    classify_rows(rows, args.interviewer_lr_threshold, args.onscreen_lr_threshold, abs(args.interviewer_lr_threshold))

    roles = {str(row["index"]): row["role"] for row in rows}
    interviewer_rows = [row for row in rows if row["role"] == "interviewer"]
    onscreen_rows = [row for row in rows if row["role"] == "onscreen"]
    payload = {
        "source": str(args.srt),
        "audio": str(args.audio),
        "method": "stereo_lr_balance_plus_acoustic_centroid",
        "thresholds": {
            "interviewerLrDb": args.interviewer_lr_threshold,
            "onscreenLrDb": args.onscreen_lr_threshold,
        },
        "roles": roles,
        "captions": rows,
        "interviewerCount": len(interviewer_rows),
        "onscreenCount": len(onscreen_rows),
        "audioFeatureSummary": {
            "interviewer": {
                "lrDb": robust_stats([float(row["audioFeatures"].get("lrDb") or 0.0) for row in interviewer_rows]),
                "dbfsMono": robust_stats([float(row["audioFeatures"].get("dbfsMono") or 0.0) for row in interviewer_rows]),
            },
            "onscreen": {
                "lrDb": robust_stats([float(row["audioFeatures"].get("lrDb") or 0.0) for row in onscreen_rows]),
                "dbfsMono": robust_stats([float(row["audioFeatures"].get("dbfsMono") or 0.0) for row in onscreen_rows]),
            },
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path = args.report or args.output.with_suffix(".audio_features_report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "output": str(args.output),
        "source": str(args.srt),
        "audio": str(args.audio),
        "interviewerCount": payload["interviewerCount"],
        "onscreenCount": payload["onscreenCount"],
        "audioFeatureSummary": payload["audioFeatureSummary"],
        "lowConfidence": [
            {
                "index": row["index"],
                "start": row["start"],
                "end": row["end"],
                "role": row["role"],
                "confidence": row["confidence"],
                "lrDb": row["audioFeatures"].get("lrDb"),
                "text": row["text"],
                "reason": row["reason"],
            }
            for row in rows
            if float(row.get("confidence") or 0.0) < 0.6
        ],
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "report": str(report_path),
                "interviewerCount": payload["interviewerCount"],
                "onscreenCount": payload["onscreenCount"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        print(error, file=sys.stderr)
        raise SystemExit(error.returncode)
