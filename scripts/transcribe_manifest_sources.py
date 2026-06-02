from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import whisper

from video_edit_core.paths import OUTPUT_TRANSCRIPTS
from video_edit_core.transcription_quality import (
    filter_low_confidence_segments,
    preprocess_audio,
    settings_match,
    settings_payload,
    transcribe_model_name,
    transcribe_options,
    write_srt,
)
from video_edit_core.app_config import load_app_config, nested, optional_path, transcript_manifest_fingerprint


APP_CONFIG = load_app_config()
OUT = OUTPUT_TRANSCRIPTS / "manifest_sources"
FFMPEG = optional_path(APP_CONFIG, "tools", "ffmpeg", default=Path(r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"))
CAMERA_ROLES = {"master", "camera2", "camera3", "camera4", "camera5", "camera6"}


def media_manifest() -> dict[str, Any]:
    manifest = nested(APP_CONFIG, "assets", "mediaManifest", default={})
    if isinstance(manifest, dict) and manifest.get("files"):
        return manifest
    path = str(nested(APP_CONFIG, "assets", "mediaManifestPath", default="") or "")
    if path and Path(path).exists():
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return {}


def role_order(role: str) -> int:
    if role == "external":
        return 0
    if role.startswith("external"):
        try:
            return int(role.replace("external", "")) - 1
        except ValueError:
            return 20
    if role == "master":
        return 30
    if role.startswith("camera"):
        try:
            return 30 + int(role.replace("camera", ""))
        except ValueError:
            return 80
    return 100


def safe_label(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_") or "source"


def manifest_sources() -> list[dict[str, Any]]:
    files = media_manifest().get("files", [])
    if not isinstance(files, list):
        return []
    sources: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in files:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "")
        kind = str(item.get("kind") or "")
        path = Path(str(item.get("path") or ""))
        if not path.exists() or str(path.resolve()).lower() in seen:
            continue
        if kind == "audio" and role.startswith("external"):
            pass
        elif kind == "video" and role in CAMERA_ROLES and item.get("metadata", {}).get("hasAudio", True) is not False:
            pass
        else:
            continue
        seen.add(str(path.resolve()).lower())
        label = safe_label(f"{role}_{path.stem}")
        sources.append({"role": role, "kind": kind, "path": path, "label": label})
    return sorted(sources, key=lambda item: (role_order(str(item["role"])), str(item["path"]).lower()))


def choose_primary(sources: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next((item for item in sources if str(item["role"]).startswith("external")), None) or next(
        (item for item in sources if item["role"] == "master"),
        None,
    ) or (sources[0] if sources else None)


def reset_current_primary_outputs() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for filename in ("primary.srt", "primary.json", "manifest_transcripts.json"):
        path = OUT / filename
        if path.exists() and path.is_file():
            path.unlink()


def transcribe_source(model: Any, source: dict[str, Any], model_name: str, options: dict[str, Any]) -> dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    media_path = Path(source["path"])
    label = str(source["label"])
    audio_path = preprocess_audio(media_path, OUT / "audio_preprocessed", label, FFMPEG, APP_CONFIG)
    json_path = OUT / f"{label}.json"
    srt_path = OUT / f"{label}.srt"
    settings_path = OUT / f"{label}.settings.json"
    settings = settings_payload(media_path, model_name, audio_path, options, APP_CONFIG)
    if json_path.exists() and srt_path.exists() and settings_match(settings_path, settings):
        result = json.loads(json_path.read_text(encoding="utf-8"))
    else:
        result = model.transcribe(str(audio_path), **options)
        result = filter_low_confidence_segments(result, APP_CONFIG)
        json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        write_srt(srt_path, result.get("segments", []))
        settings_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "role": source["role"],
        "kind": source["kind"],
        "path": str(media_path),
        "audio": str(audio_path),
        "label": label,
        "json": str(json_path),
        "srt": str(srt_path),
        "segmentCount": len(result.get("segments", [])),
        "filteredSegmentCount": len(result.get("filtered_segments", [])),
        "textLength": len(str(result.get("text", ""))),
    }


def main() -> None:
    reset_current_primary_outputs()
    sources = manifest_sources()
    if not sources:
        raise SystemExit("No audio-bearing manifest video/audio sources were found.")
    model_name = transcribe_model_name(APP_CONFIG)
    options = transcribe_options(APP_CONFIG)
    language = str(options["language"])
    model = whisper.load_model(model_name)
    primary = choose_primary(sources)
    transcripts: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for source in sources:
        try:
            item = transcribe_source(model, source, model_name, options)
            item["primary"] = source is primary
            transcripts.append(item)
            if source is primary:
                shutil.copyfile(item["srt"], OUT / "primary.srt")
                shutil.copyfile(item["json"], OUT / "primary.json")
        except Exception as error:
            errors.append({"role": str(source["role"]), "path": str(source["path"]), "error": str(error)})
    payload = {
        "model": model_name,
        "language": language,
        "beamSize": options.get("beam_size"),
        "conditionOnPreviousText": options.get("condition_on_previous_text"),
        "normalizeAudio": nested(APP_CONFIG, "analysis", "transcribeNormalizeAudio", default=True),
        "filterLowConfidence": nested(APP_CONFIG, "analysis", "transcribeFilterLowConfidence", default=True),
        "manifestFingerprint": transcript_manifest_fingerprint(APP_CONFIG),
        "outputDir": str(OUT),
        "primarySrt": str(OUT / "primary.srt") if (OUT / "primary.srt").exists() else "",
        "transcripts": transcripts,
        "errors": errors,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "manifest_transcripts.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not transcripts:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
