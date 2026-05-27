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
from transcription_quality import (
    filter_low_confidence_segments,
    preprocess_audio,
    settings_match,
    settings_payload,
    transcribe_model_name,
    transcribe_options,
    write_srt as write_quality_srt,
)
from video_edit_app_config import load_app_config, optional_path


WORK = WORKSPACE_ROOT
SOUND_DIR = SOURCE_AUDIO / "sound-2"
OUT_DIR = OUTPUT_TRANSCRIPTS / "sound2"
APP_CONFIG = load_app_config()
FFMPEG = optional_path(APP_CONFIG, "tools", "ffmpeg", default=Path(r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"))


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    model_name = transcribe_model_name(APP_CONFIG)
    options = transcribe_options(APP_CONFIG)
    model = whisper.load_model(model_name)
    for wav in sorted(SOUND_DIR.glob("*.WAV")):
        audio_path = preprocess_audio(wav, OUT_DIR / "audio_preprocessed", wav.stem, FFMPEG, APP_CONFIG)
        json_path = OUT_DIR / f"{wav.stem}.json"
        srt_path = OUT_DIR / f"{wav.stem}.srt"
        settings_path = OUT_DIR / f"{wav.stem}.settings.json"
        settings = settings_payload(wav, model_name, audio_path, options, APP_CONFIG)
        if json_path.exists() and srt_path.exists() and settings_match(settings_path, settings):
            print(f"skip existing: {wav.name}", flush=True)
            continue
        print(f"transcribing: {wav.name} with {model_name}", flush=True)
        result = model.transcribe(str(audio_path), **options)
        result = filter_low_confidence_segments(result, APP_CONFIG)
        json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        write_quality_srt(srt_path, result["segments"])
        settings_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote: {json_path.name}, {srt_path.name}", flush=True)


if __name__ == "__main__":
    main()
