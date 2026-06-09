from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "source"
REPORTS = PROJECT_ROOT / "output" / "reports"
STATE_PATH = PROJECT_ROOT / "project_state.json"
FFMPEG_DEFAULT = Path(r"C:\ProgramData\chocolatey\bin\ffmpeg.exe")
FFPROBE_DEFAULT = Path(r"C:\ProgramData\chocolatey\bin\ffprobe.exe")
JST = timezone(timedelta(hours=9))

MEDIA = [
    ("master", "group_wide", SOURCE_ROOT / "video" / "three people.mp4"),
    ("camera2", "cam_person_01", SOURCE_ROOT / "video" / "person-left.mp4"),
    ("camera3", "cam_person_02", SOURCE_ROOT / "video" / "person-middle.mp4"),
    ("camera4", "cam_person_03", SOURCE_ROOT / "video" / "person-right.mp4"),
]


def now_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def tool_path(name: str, fallback: Path) -> str:
    state = read_json(STATE_PATH, {})
    configured = str(((state.get("tools") or {}).get(name)) or "").strip()
    if configured and Path(configured).exists():
        return configured
    if fallback.exists():
        return str(fallback)
    return name


def ffprobe(path: Path) -> dict[str, Any]:
    command = [
        tool_path("ffprobe", FFPROBE_DEFAULT),
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=index,codec_type,codec_name,channels,sample_rate,start_time,duration:stream_tags:format_tags",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def volumedetect(path: Path) -> dict[str, Any]:
    command = [
        tool_path("ffmpeg", FFMPEG_DEFAULT),
        "-hide_banner",
        "-i",
        str(path),
        "-map",
        "0:a:0",
        "-af",
        "volumedetect",
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    text = f"{result.stdout}\n{result.stderr}"
    def value(pattern: str) -> float | None:
        match = re.search(pattern, text)
        return float(match.group(1)) if match else None

    return {
        "returncode": result.returncode,
        "mean_volume_db": value(r"mean_volume:\s*([\-0-9.]+)\s*dB"),
        "max_volume_db": value(r"max_volume:\s*([\-0-9.]+)\s*dB"),
        "histogram_available": "histogram_" in text,
    }


def audio_streams(probe: dict[str, Any]) -> list[dict[str, Any]]:
    return [stream for stream in probe.get("streams", []) if stream.get("codec_type") == "audio"]


def classify(volume: dict[str, Any]) -> dict[str, Any]:
    mean_db = volume.get("mean_volume_db")
    max_db = volume.get("max_volume_db")
    usable = bool(mean_db is not None and max_db is not None and mean_db > -60.0 and max_db > -25.0)
    near_silent = bool((mean_db is not None and mean_db <= -75.0) or (max_db is not None and max_db <= -60.0))
    return {
        "usable_for_waveform_sync": usable,
        "near_silence": near_silent,
        "recommended_sync_method": "audio_waveform_or_clap" if usable else "visual_anchor_required",
    }


def main() -> None:
    results = []
    for role, media_id, path in MEDIA:
        if not path.exists():
            continue
        probe = ffprobe(path)
        volume = volumedetect(path)
        results.append(
            {
                "role": role,
                "media_id": media_id,
                "path": str(path),
                "probe": probe,
                "audio_streams": audio_streams(probe),
                "volumedetect": volume,
                "classification": classify(volume),
            }
        )
    payload = {
        "schema_version": "audio_track_analysis.v1",
        "project_id": "layer-x-domain-expert",
        "generated_at": now_iso(),
        "method": "ffprobe stream inspection plus ffmpeg volumedetect",
        "media": results,
    }
    output = REPORTS / "audio_track_analysis.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "media": len(results)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
