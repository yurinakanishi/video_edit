from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from faster_whisper import WhisperModel

from project_paths import OUTPUT_TRANSCRIPTS
from transcribe_manifest_sources import choose_primary, manifest_sources
from transcription_quality import (
    filter_low_confidence_segments,
    float_config,
    initial_prompt,
    int_config,
    preprocess_audio,
    settings_match,
    settings_payload,
    should_filter_low_confidence,
    transcribe_language,
    transcribe_model_name,
    write_srt,
)
from video_edit_app_config import load_app_config, nested, optional_path, transcript_manifest_fingerprint


APP_CONFIG = load_app_config()
OUT = OUTPUT_TRANSCRIPTS / "manifest_sources"
FFMPEG = optional_path(APP_CONFIG, "tools", "ffmpeg", default=Path(r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"))


def reset_current_primary_outputs() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for filename in ("primary.srt", "primary.json", "manifest_transcripts.json"):
        path = OUT / filename
        if path.exists() and path.is_file():
            path.unlink()


def faster_options(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "language": transcribe_language(config),
        "task": "transcribe",
        "beam_size": max(1, int_config(config, "analysis", "transcribeBeamSize", default=5)),
        "temperature": float_config(config, "analysis", "transcribeTemperature", default=0.0),
        "condition_on_previous_text": bool(nested(config, "analysis", "conditionOnPreviousText", default=False)),
        "initial_prompt": initial_prompt(config),
        "no_speech_threshold": float_config(config, "analysis", "transcribeNoSpeechThreshold", default=0.6),
        "log_prob_threshold": float_config(config, "analysis", "transcribeLogprobThreshold", default=-1.0),
        "compression_ratio_threshold": float_config(config, "analysis", "transcribeCompressionRatioThreshold", default=2.4),
    }


def segment_to_dict(index: int, segment: Any) -> dict[str, Any]:
    payload = {
        "id": index,
        "seek": int(round(float(getattr(segment, "start", 0.0)) * 100)),
        "start": float(getattr(segment, "start", 0.0)),
        "end": float(getattr(segment, "end", 0.0)),
        "text": str(getattr(segment, "text", "")).strip(),
    }
    for source_key, target_key in (
        ("avg_logprob", "avg_logprob"),
        ("compression_ratio", "compression_ratio"),
        ("no_speech_prob", "no_speech_prob"),
    ):
        value = getattr(segment, source_key, None)
        if value is not None:
            try:
                payload[target_key] = float(value)
            except (TypeError, ValueError):
                pass
    return payload


def transcribe_source(model: WhisperModel, source: dict[str, Any], model_name: str, options: dict[str, Any], backend: dict[str, Any]) -> dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    media_path = Path(source["path"])
    label = str(source["label"])
    audio_path = preprocess_audio(media_path, OUT / "audio_preprocessed", label, FFMPEG, APP_CONFIG)
    json_path = OUT / f"{label}.json"
    srt_path = OUT / f"{label}.srt"
    settings_path = OUT / f"{label}.settings.json"
    settings = settings_payload(media_path, model_name, audio_path, {**options, **backend}, APP_CONFIG)
    if json_path.exists() and srt_path.exists() and settings_match(settings_path, settings):
        result = json.loads(json_path.read_text(encoding="utf-8"))
    else:
        segments_iter, info = model.transcribe(str(audio_path), **options)
        segments = [segment_to_dict(index, segment) for index, segment in enumerate(segments_iter)]
        result = {
            "text": "".join(str(segment.get("text", "")) for segment in segments).strip(),
            "segments": segments,
            "language": getattr(info, "language", options["language"]),
            "duration": getattr(info, "duration", None),
            "backend": backend,
        }
        result = filter_low_confidence_segments(result, APP_CONFIG) if should_filter_low_confidence(APP_CONFIG) else result
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
    options = faster_options(APP_CONFIG)
    device = str(nested(APP_CONFIG, "analysis", "transcribeDevice", default="cuda") or "cuda")
    compute_type = str(nested(APP_CONFIG, "analysis", "fasterWhisperComputeType", default="float16") or "float16")
    backend = {"backend": "faster-whisper", "device": device, "compute_type": compute_type}
    model = WhisperModel(model_name, device=device, compute_type=compute_type)
    primary = choose_primary(sources)
    transcripts: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for source in sources:
        try:
            item = transcribe_source(model, source, model_name, options, backend)
            item["primary"] = source is primary
            transcripts.append(item)
            if source is primary:
                shutil.copyfile(item["srt"], OUT / "primary.srt")
                shutil.copyfile(item["json"], OUT / "primary.json")
        except Exception as error:
            errors.append({"role": str(source["role"]), "path": str(source["path"]), "error": str(error)})
    payload = {
        "model": model_name,
        "language": options["language"],
        "beamSize": options.get("beam_size"),
        "conditionOnPreviousText": options.get("condition_on_previous_text"),
        "normalizeAudio": nested(APP_CONFIG, "analysis", "transcribeNormalizeAudio", default=True),
        "filterLowConfidence": nested(APP_CONFIG, "analysis", "transcribeFilterLowConfidence", default=True),
        "manifestFingerprint": transcript_manifest_fingerprint(APP_CONFIG),
        "backend": backend,
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
