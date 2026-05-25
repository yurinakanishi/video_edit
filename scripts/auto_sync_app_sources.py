from __future__ import annotations

import json
import subprocess
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

import numpy as np

from video_edit_app_config import load_app_config, nested, optional_path


WORK = WORKSPACE_ROOT
APP_CONFIG = load_app_config()
FFMPEG = optional_path(APP_CONFIG, "tools", "ffmpeg", default=Path(r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"))
OUT = OUTPUT_REPORTS / "app_sync_offsets.json"
SAMPLE_RATE = 8000
FRAME_SECONDS = 0.05
WINDOW_SECONDS = 10.0
HOP_SECONDS = 5.0


def source_path(name: str) -> Path | None:
    value = nested(APP_CONFIG, "assets", name, default="")
    return Path(value) if value else None


def decode_audio(path: Path) -> np.ndarray:
    command = [
        str(FFMPEG),
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(SAMPLE_RATE),
        "-f",
        "s16le",
        "-",
    ]
    raw = subprocess.check_output(command, cwd=WORK)
    if not raw:
        raise RuntimeError(f"No audio decoded from {path}")
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    return audio


def envelope(audio: np.ndarray) -> np.ndarray:
    frame = max(1, round(SAMPLE_RATE * FRAME_SECONDS))
    usable = len(audio) // frame * frame
    if usable == 0:
        raise RuntimeError("Audio is too short to sync")
    framed = audio[:usable].reshape(-1, frame)
    env = np.sqrt(np.mean(framed * framed, axis=1))
    env = np.log1p(env * 50.0)
    env -= np.mean(env)
    std = np.std(env)
    if std > 1e-8:
        env /= std
    return env.astype(np.float32)


def fft_correlate(alt: np.ndarray, master: np.ndarray) -> tuple[int, float]:
    if len(alt) < len(master):
        raise RuntimeError("Alternate audio is shorter than the sync window.")
    master = master - float(np.mean(master))
    m = len(master)
    valid = np.correlate(alt, master, mode="valid")
    ones = np.ones(m, dtype=np.float32)
    alt_sum = np.convolve(alt, ones, mode="valid")
    alt_sum2 = np.convolve(alt * alt, ones, mode="valid")
    alt_energy = np.maximum(alt_sum2 - (alt_sum * alt_sum / m), 1e-9)
    master_energy = float(np.sum(master * master))
    denom = np.sqrt(np.maximum(alt_energy * master_energy, 1e-9))
    ncc = valid / denom
    best = int(np.argmax(ncc))
    score = float(ncc[best])
    return best, score


def best_window_offset(alt_env: np.ndarray, master_env: np.ndarray) -> tuple[float, float, float]:
    window = max(8, round(WINDOW_SECONDS / FRAME_SECONDS))
    hop = max(1, round(HOP_SECONDS / FRAME_SECONDS))
    if len(master_env) <= window:
        lag, score = fft_correlate(alt_env, master_env)
        return lag * FRAME_SECONDS, 0.0, score

    best_offset = 0.0
    best_master_start = 0.0
    best_score = -1e9
    for start in range(0, len(master_env) - window + 1, hop):
        chunk = master_env[start : start + window]
        if float(np.std(chunk)) < 0.05:
            continue
        lag, score = fft_correlate(alt_env, chunk)
        if score > best_score:
            best_score = score
            best_master_start = start * FRAME_SECONDS
            best_offset = lag * FRAME_SECONDS - best_master_start
    return best_offset, best_master_start, best_score


def main() -> None:
    master = source_path("masterVideo")
    if not master:
        raise RuntimeError("Set a master video before running auto sync.")

    master_env = envelope(decode_audio(master))
    offsets: dict[str, dict[str, object]] = {
        "master": {
            "path": str(master),
            "offsetSeconds": 0.0,
            "score": 1.0,
            "note": "timeline reference",
        }
    }

    for role, key in (("right", "rightCloseVideo"), ("left", "leftCloseVideo")):
        path = source_path(key)
        if not path:
            continue
        alt_env = envelope(decode_audio(path))
        offset_seconds, master_start, score = best_window_offset(alt_env, master_env)
        offsets[role] = {
            "path": str(path),
            "offsetSeconds": offset_seconds,
            "score": score,
            "matchedMasterStartSeconds": master_start,
            "note": "alt source time corresponding to master timeline 0",
        }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"offsets": offsets}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(OUT), "offsets": offsets}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
