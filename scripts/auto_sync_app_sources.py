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
FINE_FRAME_SECONDS = 0.01
FINE_WINDOW_SECONDS = 24.0
FINE_SEARCH_RADIUS = 0.75


def media_manifest() -> dict[str, object]:
    manifest = nested(APP_CONFIG, "assets", "mediaManifest", default={})
    if isinstance(manifest, dict) and manifest.get("files"):
        return manifest
    path = nested(APP_CONFIG, "assets", "mediaManifestPath", default="")
    if path and Path(path).exists():
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return {}


def manifest_items(kind: str | None = None) -> list[dict[str, object]]:
    manifest = media_manifest()
    files = manifest.get("files", []) if isinstance(manifest, dict) else []
    if not isinstance(files, list):
        return []
    items = [item for item in files if isinstance(item, dict)]
    if kind is not None:
        items = [item for item in items if item.get("kind") == kind]
    return items


def source_entries() -> tuple[tuple[str, Path] | None, list[tuple[str, Path]]]:
    camera_roles = {"master", "camera2", "camera3", "camera4", "camera5", "camera6"}
    cameras = [
        (str(item.get("role") or ""), Path(str(item.get("path") or "")))
        for item in manifest_items("video")
        if item.get("role") in camera_roles and item.get("path")
    ]
    cameras = [(role, path) for role, path in cameras if path.exists()]
    master = next(((role, path) for role, path in cameras if role == "master"), None)
    if master:
        alternates = [(role, path) for role, path in cameras if role != "master"]
    else:
        configured_master = source_path("masterVideo")
        master = ("master", configured_master) if configured_master else (cameras[0] if cameras else None)
        alternates = cameras[1:] if cameras and master == cameras[0] else cameras

    audio_sources = [
        (str(item.get("role") or "external"), Path(str(item.get("path") or "")))
        for item in manifest_items("audio")
        if str(item.get("role") or "").startswith("external") and item.get("path")
    ]
    audio_sources = [(role, path) for role, path in audio_sources if path.exists()]
    if not audio_sources:
        external = source_path("externalAudio")
        if external:
            audio_sources = [("external", external)]
    if not alternates and not media_manifest():
        for role, key in (("camera2", "rightCloseVideo"), ("camera3", "leftCloseVideo")):
            path = source_path(key)
            if path:
                alternates.append((role, path))
    return master, alternates + audio_sources


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


def envelope(audio: np.ndarray, frame_seconds: float = FRAME_SECONDS, emphasize_changes: bool = False) -> np.ndarray:
    frame = max(1, round(SAMPLE_RATE * frame_seconds))
    usable = len(audio) // frame * frame
    if usable == 0:
        raise RuntimeError("Audio is too short to sync")
    framed = audio[:usable].reshape(-1, frame)
    env = np.sqrt(np.mean(framed * framed, axis=1))
    env = np.log1p(env * 50.0)
    if emphasize_changes:
        smooth = np.convolve(env, np.ones(9, dtype=np.float32) / 9.0, mode="same")
        feature = np.diff(smooth, prepend=smooth[0])
    else:
        feature = env
    feature -= np.mean(feature)
    std = np.std(feature)
    if std > 1e-8:
        feature /= std
    return feature.astype(np.float32)


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


def corr(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) != len(b) or len(a) < 100:
        return -1.0
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom <= 1e-8:
        return -1.0
    return float(np.dot(a, b) / denom)


def fine_refine_offset(
    alt_audio: np.ndarray,
    master_audio: np.ndarray,
    coarse_offset: float,
    master_start: float,
) -> dict[str, object]:
    frame_seconds = float(nested(APP_CONFIG, "analysis", "syncFineFrameSeconds", default=FINE_FRAME_SECONDS) or FINE_FRAME_SECONDS)
    window_seconds = float(nested(APP_CONFIG, "analysis", "syncFineWindowSeconds", default=FINE_WINDOW_SECONDS) or FINE_WINDOW_SECONDS)
    search_radius = float(nested(APP_CONFIG, "analysis", "syncFineSearchRadius", default=FINE_SEARCH_RADIUS) or FINE_SEARCH_RADIUS)
    frame_seconds = max(0.005, min(frame_seconds, 0.05))
    window_seconds = max(4.0, window_seconds)
    search_radius = max(0.0, min(search_radius, 3.0))

    master_env = envelope(master_audio, frame_seconds=frame_seconds, emphasize_changes=True)
    alt_env = envelope(alt_audio, frame_seconds=frame_seconds, emphasize_changes=True)
    master_duration = len(master_env) * frame_seconds
    alt_duration = len(alt_env) * frame_seconds
    master_start = max(0.0, min(master_start, max(0.0, master_duration - 1.0)))
    window_seconds = min(window_seconds, max(1.0, master_duration - master_start))
    window_frames = max(100, round(window_seconds / frame_seconds))
    master_start = max(0.0, min(master_start, max(0.0, master_duration - window_frames * frame_seconds)))
    m0 = round(master_start / frame_seconds)
    m1 = min(len(master_env), m0 + window_frames)
    master_slice = master_env[m0:m1]
    if len(master_slice) < 100:
        return {
            "offsetSeconds": coarse_offset,
            "coarseOffsetSeconds": coarse_offset,
            "refined": False,
            "reason": "master window too short",
        }

    best: tuple[float, float] | None = None
    step_count = round(search_radius / frame_seconds)
    for shift_frame in range(-step_count, step_count + 1):
        shift = shift_frame * frame_seconds
        alt_start = coarse_offset + master_start + shift
        if alt_start < 0 or alt_start + len(master_slice) * frame_seconds > alt_duration:
            continue
        a0 = round(alt_start / frame_seconds)
        a1 = a0 + len(master_slice)
        score = corr(master_slice, alt_env[a0:a1])
        if best is None or score > best[0]:
            best = (score, shift)

    if best is None:
        return {
            "offsetSeconds": coarse_offset,
            "coarseOffsetSeconds": coarse_offset,
            "refined": False,
            "reason": "no valid fine-search window",
        }
    score, shift = best
    return {
        "offsetSeconds": coarse_offset + shift,
        "coarseOffsetSeconds": coarse_offset,
        "refinedShiftSeconds": shift,
        "refinedScore": score,
        "refined": True,
        "refinedFrameSeconds": frame_seconds,
        "refinedWindowSeconds": len(master_slice) * frame_seconds,
        "refinedMasterStartSeconds": master_start,
    }


def main() -> None:
    master_entry, alternate_entries = source_entries()
    if not master_entry:
        raise RuntimeError("Set a Camera 1 / master video before running auto sync.")
    master_role, master = master_entry

    master_audio = decode_audio(master)
    master_env = envelope(master_audio)
    offsets: dict[str, dict[str, object]] = {
        master_role: {
            "path": str(master),
            "offsetSeconds": 0.0,
            "score": 1.0,
            "note": "timeline reference",
        }
    }

    for role, path in alternate_entries:
        try:
            alt_audio = decode_audio(path)
            alt_env = envelope(alt_audio)
            offset_seconds, master_start, score = best_window_offset(alt_env, master_env)
            refined = fine_refine_offset(alt_audio, master_audio, offset_seconds, master_start)
            refined_offset = float(refined.get("offsetSeconds", offset_seconds))
            offsets[role] = {
                "path": str(path),
                "offsetSeconds": refined_offset,
                "coarseOffsetSeconds": offset_seconds,
                "score": score,
                "matchedMasterStartSeconds": master_start,
                "fineRefinement": refined,
                "note": "alt source time corresponding to master timeline 0; fine refinement preserves the same timeline convention",
            }
        except Exception as error:
            offsets[role] = {
                "path": str(path),
                "offsetSeconds": 0.0,
                "score": 0.0,
                "matchedMasterStartSeconds": 0.0,
                "note": f"sync failed: {error}",
            }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timelineRole": master_role,
        "manifestPath": nested(APP_CONFIG, "assets", "mediaManifestPath", default=""),
        "offsets": offsets,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(OUT), **payload}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
