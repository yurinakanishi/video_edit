from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "source"
REPORTS = PROJECT_ROOT / "output" / "reports"
STATE_PATH = PROJECT_ROOT / "project_state.json"
FFMPEG_DEFAULT = Path(r"C:\ProgramData\chocolatey\bin\ffmpeg.exe")
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


def ffmpeg_path() -> str:
    state = read_json(STATE_PATH, {})
    configured = str(((state.get("tools") or {}).get("ffmpeg")) or "").strip()
    if configured and Path(configured).exists():
        return configured
    if FFMPEG_DEFAULT.exists():
        return str(FFMPEG_DEFAULT)
    return "ffmpeg"


def decode_window(path: Path, start: float, duration: float = 30.0, sample_rate: int = 8000) -> np.ndarray:
    raw = subprocess.check_output(
        [
            ffmpeg_path(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{duration:.3f}",
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
        ],
        cwd=PROJECT_ROOT.parents[1],
    )
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def stats(audio: np.ndarray) -> dict[str, Any]:
    if len(audio) == 0:
        return {"rmsDbfs": None, "peakDbfs": None, "usable": False}
    rms = float(np.sqrt(np.mean(audio * audio)))
    peak = float(np.max(np.abs(audio)))

    def db(value: float) -> float | None:
        return round(20.0 * float(np.log10(value)), 2) if value > 1e-12 else None

    rms_db = db(rms)
    peak_db = db(peak)
    return {
        "rmsDbfs": rms_db,
        "peakDbfs": peak_db,
        "usable": bool(rms_db is not None and peak_db is not None and rms_db > -60.0 and peak_db > -25.0),
    }


def main() -> None:
    windows = [0, 180, 360, 600, 900, 1200, 1500, 1800, 2100, 2400, 2700]
    payload = {
        "schema_version": "audio_window_scan.v1",
        "project_id": "layer-x-domain-expert",
        "generated_at": now_iso(),
        "window_duration": 30.0,
        "media": [],
    }
    for role, media_id, path in MEDIA:
        if not path.exists():
            continue
        rows = []
        for start in windows:
            try:
                rows.append({"start": start, **stats(decode_window(path, float(start)))})
            except subprocess.CalledProcessError as error:
                rows.append({"start": start, "error": str(error), "usable": False})
        payload["media"].append({"role": role, "media_id": media_id, "path": str(path), "windows": rows})
    output = REPORTS / "audio_window_scan.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
