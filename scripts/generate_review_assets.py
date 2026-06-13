from __future__ import annotations

import hashlib
import json
import math
import subprocess
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from video_edit_core.app_config import load_app_config, nested, optional_path
from video_edit_core.paths import OUTPUT


APP_CONFIG = load_app_config()
FFMPEG = optional_path(APP_CONFIG, "tools", "ffmpeg", default=Path(r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"))
FFPROBE = optional_path(APP_CONFIG, "tools", "ffprobe", default=Path(r"C:\ProgramData\chocolatey\bin\ffprobe.exe"))
SCHEMA_VERSION = "review-timeline.v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def output_root() -> Path:
    configured = nested(APP_CONFIG, "project", "outputRoot", default="")
    return Path(str(configured)) if configured else Path(OUTPUT)


def project_id() -> str:
    return str(nested(APP_CONFIG, "project", "id", default="") or Path(output_root()).parent.name)


def preview_path() -> Path:
    candidates = [
        nested(APP_CONFIG, "review", "previewVideoPath", default=""),
        nested(APP_CONFIG, "editRequest", "lastPreviewPath", default=""),
        nested(APP_CONFIG, "editRequest", "requestedPreviewPath", default=""),
        nested(APP_CONFIG, "render", "outputPath", default=""),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(str(candidate))
        if path.exists() and path.is_file():
            return path
    raise SystemExit("No preview video was found for review asset generation.")


def probe_video(path: Path) -> dict[str, Any]:
    completed = subprocess.run(
        [
            str(FFPROBE),
            "-v",
            "error",
            "-show_entries",
            "format=duration,size:stream=codec_type,codec_name,width,height,avg_frame_rate,sample_rate,channels",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    metadata: dict[str, Any] = {}
    fmt = payload.get("format", {}) if isinstance(payload, dict) else {}
    if isinstance(fmt, dict):
        metadata["duration"] = float(fmt.get("duration") or 0)
        metadata["size"] = int(float(fmt.get("size") or path.stat().st_size))
    streams = payload.get("streams", []) if isinstance(payload, dict) else []
    if isinstance(streams, list):
        video = next((item for item in streams if isinstance(item, dict) and item.get("codec_type") == "video"), {})
        audio = next((item for item in streams if isinstance(item, dict) and item.get("codec_type") == "audio"), {})
        if isinstance(video, dict):
            metadata["width"] = int(video.get("width") or 0)
            metadata["height"] = int(video.get("height") or 0)
            metadata["videoCodec"] = str(video.get("codec_name") or "")
            metadata["avgFrameRate"] = str(video.get("avg_frame_rate") or "")
            metadata["fps"] = parse_fps(metadata["avgFrameRate"])
        if isinstance(audio, dict):
            metadata["audioCodec"] = str(audio.get("codec_name") or "")
            metadata["sampleRate"] = int(audio.get("sample_rate") or 0)
            metadata["channels"] = int(audio.get("channels") or 0)
    return metadata


def parse_fps(value: str) -> float:
    if not value:
        return 0.0
    if "/" not in value:
        try:
            return float(value)
        except ValueError:
            return 0.0
    num, den = value.split("/", 1)
    try:
        denominator = float(den)
        return float(num) / denominator if denominator else 0.0
    except ValueError:
        return 0.0


def preview_signature(path: Path) -> str:
    stat = path.stat()
    payload = json.dumps(
        {
            "path": str(path.resolve()).lower(),
            "size": stat.st_size,
            "mtimeNs": stat.st_mtime_ns,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def assets_ready(review_timeline_path: Path, signature: str) -> bool:
    timeline = load_json(review_timeline_path)
    if timeline.get("previewFingerprint") != signature:
        return False
    for key in ("thumbnailStripPath", "waveformPath"):
        path = Path(str(timeline.get(key) or ""))
        if not path.exists() or path.stat().st_size <= 0:
            return False
    return True


def thumbnail_count(duration: float) -> int:
    if duration <= 0:
        return 1
    return max(6, min(96, math.ceil(duration / 15)))


def generate_thumbnails(path: Path, out_dir: Path, duration: float) -> dict[str, Any]:
    thumbs_dir = out_dir / "thumbnails"
    thumbs_dir.mkdir(parents=True, exist_ok=True)
    count = thumbnail_count(duration)
    interval = max(0.5, duration / count) if duration > 0 else 1.0
    existing = sorted(thumbs_dir.glob("thumb_*.jpg"))
    if len(existing) >= count:
        return thumbnail_manifest(path, thumbs_dir, duration, interval)
    for stale in existing:
        stale.unlink(missing_ok=True)
    subprocess.run(
        [
            str(FFMPEG),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(path),
            "-vf",
            f"fps=1/{interval:.6f},scale=180:102:force_original_aspect_ratio=decrease,pad=180:102:(ow-iw)/2:(oh-ih)/2",
            "-frames:v",
            str(count),
            "-q:v",
            "5",
            str(thumbs_dir / "thumb_%05d.jpg"),
        ],
        check=True,
    )
    return thumbnail_manifest(path, thumbs_dir, duration, interval)


def thumbnail_manifest(path: Path, thumbs_dir: Path, duration: float, interval: float) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    files = sorted(thumbs_dir.glob("thumb_*.jpg"))
    for index, file_path in enumerate(files):
        items.append(
            {
                "index": index,
                "time": round(min(duration, index * interval), 6),
                "path": str(file_path),
            }
        )
    return {
        "schemaVersion": "review-thumbnail-strip.v1",
        "source": str(path),
        "duration": duration,
        "items": items,
        "generatedAt": utc_now(),
    }


def generate_waveform(path: Path, out_dir: Path, duration: float) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    wav_path = out_dir / "waveform_source.wav"
    try:
        subprocess.run(
            [
                str(FFMPEG),
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(path),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "800",
                "-f",
                "wav",
                str(wav_path),
            ],
            check=True,
        )
        values = waveform_values(wav_path, target_bins=max(120, min(2400, math.ceil(duration * 2))))
        wav_path.unlink(missing_ok=True)
        return {
            "schemaVersion": "review-waveform.v1",
            "source": str(path),
            "duration": duration,
            "sampleCount": len(values),
            "peaks": values,
            "generatedAt": utc_now(),
        }
    except (OSError, subprocess.CalledProcessError, wave.Error) as error:
        return {
            "schemaVersion": "review-waveform.v1",
            "source": str(path),
            "duration": duration,
            "sampleCount": 0,
            "peaks": [],
            "error": str(error),
            "generatedAt": utc_now(),
        }


def waveform_values(path: Path, *, target_bins: int) -> list[float]:
    with wave.open(str(path), "rb") as source:
        frames = source.getnframes()
        if frames <= 0:
            return []
        raw = source.readframes(frames)
    sample_count = len(raw) // 2
    if sample_count <= 0:
        return []
    bin_size = max(1, math.ceil(sample_count / max(1, target_bins)))
    values: list[float] = []
    max_abs = 1
    for offset in range(0, sample_count, bin_size):
        peak = 0
        end = min(sample_count, offset + bin_size)
        for sample_index in range(offset, end):
            byte_index = sample_index * 2
            sample = int.from_bytes(raw[byte_index : byte_index + 2], "little", signed=True)
            peak = max(peak, abs(sample))
        max_abs = max(max_abs, peak)
        values.append(float(peak))
    return [round(value / max_abs, 4) for value in values]


def main() -> None:
    preview = preview_path()
    metadata = probe_video(preview)
    duration = float(metadata.get("duration") or 0)
    fingerprint = preview_signature(preview)
    app_dir = output_root() / "app"
    assets_dir = app_dir / "review_assets" / fingerprint
    review_timeline_path = app_dir / "review_timeline.json"
    thumbnail_strip_path = assets_dir / "thumbnail_strip.json"
    waveform_path = assets_dir / "waveform.json"

    if not assets_ready(review_timeline_path, fingerprint):
        thumbnails = generate_thumbnails(preview, assets_dir, duration)
        waveform_payload = generate_waveform(preview, assets_dir, duration)
        assets_dir.mkdir(parents=True, exist_ok=True)
        thumbnail_strip_path.write_text(json.dumps(thumbnails, ensure_ascii=False, indent=2), encoding="utf-8")
        waveform_path.write_text(json.dumps(waveform_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        review_timeline = {
            "schemaVersion": SCHEMA_VERSION,
            "projectId": project_id(),
            "duration": duration,
            "fps": float(metadata.get("fps") or 0),
            "previewVideoPath": str(preview),
            "previewFingerprint": fingerprint,
            "thumbnailStripPath": str(thumbnail_strip_path),
            "waveformPath": str(waveform_path),
            "markers": [],
            "revision": int(nested(APP_CONFIG, "revision", default=0) or 0),
            "generatedAt": utc_now(),
            "metadata": metadata,
        }
        app_dir.mkdir(parents=True, exist_ok=True)
        review_timeline_path.write_text(json.dumps(review_timeline, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "reviewTimelinePath": str(review_timeline_path),
                "thumbnailStripPath": str(thumbnail_strip_path),
                "waveformPath": str(waveform_path),
                "previewVideoPath": str(preview),
                "previewFingerprint": fingerprint,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
