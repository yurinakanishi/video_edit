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


WORK = WORKSPACE_ROOT
FFMPEG = Path(r"C:\ProgramData\chocolatey\bin\ffmpeg.exe")
VIDEO = OUTPUT_VIDEOS / "ST7_7550_multicam_cut_5min_png_titles_punchlines.mp4"
SOUND = SOURCE_AUDIO / "sound-2" / "140101-003.WAV"
MATCHES = OUTPUT_TRANSCRIPTS / "sound2" / "sound2_master_matches.json"
OUTPUT = OUTPUT_TRANSCRIPTS / "sound2" / "sound2_audio_offset_refined.json"
SR = 16_000


def read_audio(path: Path, start: float, duration: float) -> np.ndarray:
    command = [
        str(FFMPEG),
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
        str(SR),
        "-f",
        "f32le",
        "-",
    ]
    data = subprocess.check_output(command, cwd=WORK)
    return np.frombuffer(data, dtype=np.float32)


def envelope(audio: np.ndarray) -> np.ndarray:
    audio = np.abs(audio)
    frame = int(SR * 0.02)
    usable = len(audio) // frame * frame
    rms = np.sqrt(np.mean(audio[:usable].reshape(-1, frame) ** 2, axis=1))
    rms = np.log1p(rms * 100)
    rms -= rms.mean()
    std = rms.std()
    if std > 1e-8:
        rms /= std
    return rms


def best_lag(reference: np.ndarray, candidate: np.ndarray, search_seconds: float) -> tuple[float, float]:
    ref = envelope(reference)
    cand = envelope(candidate)
    max_lag = int(search_seconds / 0.02)
    best_score = -1e9
    best = 0
    for lag in range(-max_lag, max_lag + 1):
        if lag < 0:
            a = ref[-lag:]
            b = cand[: len(a)]
        elif lag > 0:
            a = ref[: len(ref) - lag]
            b = cand[lag : lag + len(a)]
        else:
            a = ref
            b = cand[: len(a)]
        if len(a) < 100:
            continue
        score = float(np.dot(a, b) / len(a))
        if score > best_score:
            best_score = score
            best = lag
    return best * 0.02, best_score


def main() -> None:
    data = json.loads(MATCHES.read_text(encoding="utf-8"))
    best = data["summary"][0]
    rough_offset = float(best["median_offset"])
    windows = [
        (20.0, 50.0),
        (80.0, 60.0),
        (150.0, 60.0),
        (230.0, 50.0),
    ]
    results = []
    for video_start, duration in windows:
        sound_start = rough_offset + video_start - 4.0
        ref = read_audio(VIDEO, video_start, duration)
        cand = read_audio(SOUND, sound_start, duration + 8.0)
        lag, score = best_lag(ref, cand, 4.0)
        offset = sound_start + lag - video_start
        results.append(
            {
                "video_start": video_start,
                "duration": duration,
                "sound_window_start": sound_start,
                "lag": lag,
                "score": score,
                "offset": offset,
            }
        )
    offsets = np.array([item["offset"] for item in results], dtype=float)
    refined = float(np.median(offsets))
    payload = {
        "sound_file": str(SOUND.relative_to(WORK)),
        "video_file": str(VIDEO.relative_to(WORK)),
        "rough_offset": rough_offset,
        "refined_offset": refined,
        "windows": results,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
