from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np


FFMPEG = Path(r"C:\ProgramData\chocolatey\bin\ffmpeg.exe")
WORK = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("VIDEO_EDIT_SOURCE_ROOT", r"C:\Users\yurin\Downloads\cdc260515 mov\cdc260515 mov"))
OUT = WORK / "transcript_sync_all" / "strong_local_wave_refine.json"
SAMPLE_RATE = 16000


@dataclass(frozen=True)
class SyncSegment:
    name: str
    camera: str
    source: Path
    master_start: float
    master_end: float
    alt_start_guess: float
    search_radius: float = 0.9
    pad: float = 0.6

    @property
    def duration(self) -> float:
        return self.master_end - self.master_start


def decode_audio(path: Path, start: float, duration: float) -> np.ndarray:
    start = max(0.0, start)
    cmd = [
        str(FFMPEG),
        "-v",
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
        str(SAMPLE_RATE),
        "-f",
        "s16le",
        "pipe:1",
    ]
    raw = subprocess.check_output(cmd)
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    return audio / 32768.0


def envelope(audio: np.ndarray, frame_seconds: float = 0.010) -> np.ndarray:
    frame = max(1, int(round(SAMPLE_RATE * frame_seconds)))
    usable = (len(audio) // frame) * frame
    if usable <= 0:
        return np.array([], dtype=np.float32)
    framed = audio[:usable].reshape(-1, frame)
    env = np.sqrt(np.mean(framed * framed, axis=1) + 1e-12)
    env = np.log1p(env * 60.0)

    # Emphasize speech timing changes over absolute room tone.
    smooth = np.convolve(env, np.ones(9, dtype=np.float32) / 9.0, mode="same")
    feat = np.diff(smooth, prepend=smooth[0])
    feat = feat - feat.mean()
    std = feat.std()
    if std > 1e-8:
        feat = feat / std
    return feat.astype(np.float32)


def corr(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) != len(b) or len(a) < 100:
        return -1.0
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom <= 1e-8:
        return -1.0
    return float(np.dot(a, b) / denom)


def find_local_shift(segment: SyncSegment) -> dict:
    master_path = WORK / "1cam" / "ST7_7550_overlap_5min.mp4"
    master_start = max(0.0, segment.master_start - segment.pad)
    master_duration = segment.duration + segment.pad * 2.0

    alt_extract_start = max(0.0, segment.alt_start_guess - segment.search_radius - segment.pad)
    alt_duration = segment.duration + segment.pad * 2.0 + segment.search_radius * 2.0

    master = envelope(decode_audio(master_path, master_start, master_duration))
    alt = envelope(decode_audio(segment.source, alt_extract_start, alt_duration))
    step = 0.010
    radius_frames = int(round(segment.search_radius / step))
    base_frames = int(round((segment.alt_start_guess - segment.pad - alt_extract_start) / step))

    candidates: list[tuple[float, float]] = []
    for shift_frame in range(-radius_frames, radius_frames + 1):
        alt_start_frame = base_frames + shift_frame
        alt_end_frame = alt_start_frame + len(master)
        if alt_start_frame < 0 or alt_end_frame > len(alt):
            continue
        score = corr(master, alt[alt_start_frame:alt_end_frame])
        candidates.append((score, shift_frame * step))

    candidates.sort(reverse=True, key=lambda item: item[0])
    best_score, best_shift = candidates[0]
    top = [{"score": round(score, 6), "shift_seconds": round(shift, 3)} for score, shift in candidates[:8]]
    return {
        "camera": segment.camera,
        "source": str(segment.source),
        "master_start": segment.master_start,
        "master_end": segment.master_end,
        "alt_start_guess": segment.alt_start_guess,
        "best_shift_seconds": round(best_shift, 3),
        "corrected_alt_start": round(segment.alt_start_guess + best_shift, 3),
        "best_score": round(best_score, 6),
        "top_candidates": top,
    }


def main() -> None:
    segments = [
        SyncSegment(
            name="2cam_0H4A7192",
            camera="2cam",
            source=ROOT / "2cam" / "0H4A7192.MP4",
            master_start=9.000,
            master_end=21.500,
            alt_start_guess=1112.000,
        ),
        SyncSegment(
            name="2cam_0H4A7193",
            camera="2cam",
            source=ROOT / "2cam" / "0H4A7193.MP4",
            master_start=85.000,
            master_end=152.000,
            alt_start_guess=59.000,
        ),
        SyncSegment(
            name="3cam_IMG_2316",
            camera="3cam",
            source=ROOT / "3cam" / "IMG_2316.MP4",
            master_start=213.000,
            master_end=257.000,
            alt_start_guess=104.000,
        ),
    ]

    results = {segment.name: find_local_shift(segment) for segment in segments}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
