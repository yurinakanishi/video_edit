from __future__ import annotations

import json
import os
import re
import subprocess
import wave
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

import numpy as np
import whisper

from transcription_quality import (
    filter_low_confidence_segments,
    preprocess_audio,
    settings_match,
    settings_payload,
    transcribe_model_name,
    transcribe_options,
    write_srt,
)
from video_edit_app_config import load_app_config, optional_path

APP_CONFIG = load_app_config()
FFMPEG = optional_path(APP_CONFIG, "tools", "ffmpeg", default=Path(r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"))
WORK = WORKSPACE_ROOT
ROOT = multicam_source_root()
OUT = OUTPUT_TRANSCRIPTS / "transcript_sync"

MASTER = SOURCE_VIDEO / "1cam" / "ST7_7550_overlap_5min.mp4"
ALT_2CAM = ROOT / "2cam" / "0H4A7189.MP4"
ALT_3CAM = ROOT / "3cam" / "IMG_2316.MP4"


@dataclass
class WindowMatch:
    score: float
    offset: float
    master_start: float
    alt_start: float
    master_text: str
    alt_text: str


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def transcribe(model: Any, media_path: Path, label: str, model_name: str, options: dict[str, Any]) -> dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    audio_path = preprocess_audio(media_path, OUT / "audio_preprocessed", label, FFMPEG, APP_CONFIG)
    json_path = OUT / f"{label}.json"
    srt_path = OUT / f"{label}.srt"
    settings_path = OUT / f"{label}.settings.json"
    settings = settings_payload(media_path, model_name, audio_path, options, APP_CONFIG)
    if json_path.exists() and srt_path.exists() and settings_match(settings_path, settings):
        return json.loads(json_path.read_text(encoding="utf-8"))

    result = model.transcribe(str(audio_path), **options)
    result = filter_low_confidence_segments(result, APP_CONFIG)
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    write_srt(srt_path, result.get("segments", []))
    settings_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def normalize(text: str) -> str:
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[、。,.!?！？「」『』（）()［］\[\]・…:：;；\-ー_]", "", text)
    return text.lower()


def segment_windows(result: dict[str, Any], size: int = 3) -> list[tuple[float, str, str]]:
    segments = result.get("segments", [])
    windows: list[tuple[float, str, str]] = []
    for index in range(len(segments)):
        selected = segments[index : index + size]
        raw = "".join(str(segment.get("text", "")) for segment in selected).strip()
        norm = normalize(raw)
        if len(norm) >= 12:
            windows.append((float(selected[0]["start"]), raw, norm))
    return windows


def find_text_matches(master: dict[str, Any], alt: dict[str, Any]) -> list[WindowMatch]:
    master_windows = segment_windows(master)
    alt_windows = segment_windows(alt)
    matches: list[WindowMatch] = []
    for alt_start, alt_raw, alt_norm in alt_windows:
        best: WindowMatch | None = None
        for master_start, master_raw, master_norm in master_windows:
            score = SequenceMatcher(None, alt_norm, master_norm).ratio()
            if best is None or score > best.score:
                best = WindowMatch(
                    score=score,
                    offset=master_start - alt_start,
                    master_start=master_start,
                    alt_start=alt_start,
                    master_text=master_raw,
                    alt_text=alt_raw,
                )
        if best is not None and best.score >= 0.38:
            matches.append(best)
    matches.sort(key=lambda item: item.score, reverse=True)
    return matches[:20]


def extract_audio(media_path: Path, wav_path: Path) -> None:
    if wav_path.exists():
        return
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            str(FFMPEG),
            "-y",
            "-i",
            str(media_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-acodec",
            "pcm_s16le",
            str(wav_path),
        ]
    )


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as wav:
        data = wav.readframes(wav.getnframes())
    audio = np.frombuffer(data, dtype=np.int16).astype(np.float32)
    return audio / 32768.0


def envelope(audio: np.ndarray, sample_rate: int = 16000, frame_seconds: float = 0.02) -> np.ndarray:
    frame = int(sample_rate * frame_seconds)
    usable = (len(audio) // frame) * frame
    framed = audio[:usable].reshape(-1, frame)
    env = np.sqrt(np.mean(framed * framed, axis=1) + 1e-12)
    env = np.log1p(env * 50.0)
    env = env - env.mean()
    std = env.std()
    return (env / std).astype(np.float32) if std > 1e-8 else env.astype(np.float32)


def score_at_offset(
    master_env: np.ndarray,
    alt_env: np.ndarray,
    offset: float,
    alt_anchor: float,
    window_seconds: float,
    step: float,
) -> tuple[float, float]:
    alt_start = max(0.0, alt_anchor - 4.0)
    alt_end = alt_start + window_seconds
    master_start = alt_start + offset
    if master_start < 0:
        return -1.0, 0.0
    a0 = int(round(alt_start / step))
    a1 = int(round(alt_end / step))
    m0 = int(round(master_start / step))
    m1 = m0 + (a1 - a0)
    if a0 < 0 or m0 < 0 or a1 > len(alt_env) or m1 > len(master_env):
        return -1.0, 0.0
    a = alt_env[a0:a1]
    m = master_env[m0:m1]
    if len(a) < 100:
        return -1.0, 0.0
    denom = float(np.linalg.norm(a) * np.linalg.norm(m))
    if denom <= 1e-8:
        return -1.0, len(a) * step
    return float(np.dot(a, m) / denom), len(a) * step


def refine_with_waveform(
    master_audio: np.ndarray,
    alt_audio: np.ndarray,
    match: WindowMatch,
    radius: float = 2.5,
    window_seconds: float = 22.0,
) -> dict[str, float]:
    step = 0.02
    master_env = envelope(master_audio, frame_seconds=step)
    alt_env = envelope(alt_audio, frame_seconds=step)
    candidates: list[tuple[float, float, float]] = []
    center = match.offset
    for delta in np.arange(-radius, radius + step, step):
        offset = float(center + delta)
        score, overlap = score_at_offset(master_env, alt_env, offset, match.alt_start, window_seconds, step)
        candidates.append((score, offset, overlap))
    candidates.sort(reverse=True, key=lambda item: item[0])
    best_score, best_offset, overlap = candidates[0]
    return {
        "text_offset": match.offset,
        "wave_refined_offset": best_offset,
        "wave_score": best_score,
        "overlap_seconds": overlap,
        "master_anchor": match.master_start,
        "alt_anchor": match.alt_start,
        "text_score": match.score,
    }


def choose_offset(matches: list[WindowMatch], master_audio: np.ndarray, alt_audio: np.ndarray) -> dict[str, Any]:
    refined = [
        refine_with_waveform(master_audio, alt_audio, match)
        for match in matches[:8]
    ]
    refined.sort(key=lambda item: (item["wave_score"], item["text_score"]), reverse=True)
    return {
        "best": refined[0] if refined else None,
        "refined_candidates": refined,
        "text_matches": [
            {
                "score": match.score,
                "offset": match.offset,
                "master_start": match.master_start,
                "alt_start": match.alt_start,
                "master_text": match.master_text,
                "alt_text": match.alt_text,
            }
            for match in matches
        ],
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    model_name = transcribe_model_name(APP_CONFIG)
    options = transcribe_options(APP_CONFIG)
    model = whisper.load_model(model_name)

    master = transcribe(model, MASTER, "1cam_master_ST7_7550_overlap_5min", model_name, options)
    alt2 = transcribe(model, ALT_2CAM, "2cam_0H4A7189", model_name, options)
    alt3 = transcribe(model, ALT_3CAM, "3cam_IMG_2316", model_name, options)

    master_wav = OUT / "wav" / "1cam_master.wav"
    alt2_wav = OUT / "wav" / "2cam_0H4A7189.wav"
    alt3_wav = OUT / "wav" / "3cam_IMG_2316.wav"
    extract_audio(MASTER, master_wav)
    extract_audio(ALT_2CAM, alt2_wav)
    extract_audio(ALT_3CAM, alt3_wav)

    master_audio = read_wav(master_wav)
    output = {
        "2cam_0H4A7189": choose_offset(find_text_matches(master, alt2), master_audio, read_wav(alt2_wav)),
        "3cam_IMG_2316": choose_offset(find_text_matches(master, alt3), master_audio, read_wav(alt3_wav)),
    }
    (OUT / "transcript_wave_sync_offsets.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
