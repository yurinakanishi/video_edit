from __future__ import annotations

import json
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

import whisper


WORK = WORKSPACE_ROOT
SOUND_DIR = SOURCE_AUDIO / "sound-2"
OUT_DIR = OUTPUT_TRANSCRIPTS / "sound2"
MODEL_NAME = "base"


def format_ts(seconds: float) -> str:
    ms = round(seconds * 1000)
    h, rem = divmod(ms, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(path: Path, segments: list[dict]) -> None:
    rows: list[str] = []
    for index, segment in enumerate(segments, start=1):
        text = segment.get("text", "").strip()
        if not text:
            continue
        rows.extend(
            [
                str(index),
                f"{format_ts(float(segment['start']))} --> {format_ts(float(segment['end']))}",
                text,
                "",
            ]
        )
    path.write_text("\n".join(rows), encoding="utf-8")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    model = whisper.load_model(MODEL_NAME)
    for wav in sorted(SOUND_DIR.glob("*.WAV")):
        json_path = OUT_DIR / f"{wav.stem}.json"
        srt_path = OUT_DIR / f"{wav.stem}.srt"
        if json_path.exists() and srt_path.exists():
            print(f"skip existing: {wav.name}", flush=True)
            continue
        print(f"transcribing: {wav.name}", flush=True)
        result = model.transcribe(
            str(wav),
            language="ja",
            task="transcribe",
            fp16=False,
            verbose=False,
            condition_on_previous_text=False,
        )
        json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        write_srt(srt_path, result["segments"])
        print(f"wrote: {json_path.name}, {srt_path.name}", flush=True)


if __name__ == "__main__":
    main()
