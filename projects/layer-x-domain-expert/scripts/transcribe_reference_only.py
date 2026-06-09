from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_TRANSCRIPTS = PROJECT_ROOT / "output" / "transcripts"
OUT = OUTPUT_TRANSCRIPTS / "manifest_sources"

sys.path.insert(0, str(WORKSPACE_ROOT))
sys.path.insert(0, str(WORKSPACE_ROOT / "scripts"))
os.environ.setdefault("VIDEO_EDIT_PROJECT", "layer-x-domain-expert")

from video_edit_core.app_config import load_app_config, nested, optional_path, transcript_manifest_fingerprint  # noqa: E402
from video_edit_core.transcription_quality import (  # noqa: E402
    filter_low_confidence_segments,
    initial_prompt,
    int_config,
    float_config,
    preprocess_audio,
    settings_match,
    settings_payload,
    should_filter_low_confidence,
    transcribe_language,
    transcribe_model_name,
    write_srt,
)
from transcribe_manifest_sources import choose_primary, manifest_sources  # noqa: E402


APP_CONFIG = load_app_config()
FFMPEG = optional_path(APP_CONFIG, "tools", "ffmpeg", default=Path(r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"))


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
    for key in ("avg_logprob", "compression_ratio", "no_speech_prob"):
        value = getattr(segment, key, None)
        if value is not None:
            payload[key] = float(value)
    return payload


def reference_source(reference_role: str) -> dict[str, Any]:
    sources = manifest_sources()
    source = next((item for item in sources if item.get("role") == reference_role), None)
    if source is None:
        primary = choose_primary(sources)
        if primary is None:
            raise SystemExit("No audio-bearing reference source found.")
        return primary
    return source


def transcribe_reference(source: dict[str, Any], *, device: str, compute_type: str) -> dict[str, Any]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as error:
        raise SystemExit("faster_whisper is required. Run this with .video-edit/venvs/whisper-cu128/Scripts/python.exe") from error

    OUT.mkdir(parents=True, exist_ok=True)
    media_path = Path(source["path"])
    label = str(source["label"])
    model_name = transcribe_model_name(APP_CONFIG)
    options = faster_options(APP_CONFIG)
    backend = {"backend": "faster-whisper", "device": device, "compute_type": compute_type}
    audio_path = preprocess_audio(media_path, OUT / "audio_preprocessed", label, FFMPEG, APP_CONFIG)
    json_path = OUT / f"{label}.json"
    srt_path = OUT / f"{label}.srt"
    settings_path = OUT / f"{label}.settings.json"
    settings = settings_payload(media_path, model_name, audio_path, {**options, **backend}, APP_CONFIG)
    if json_path.exists() and srt_path.exists() and settings_match(settings_path, settings):
        result = json.loads(json_path.read_text(encoding="utf-8"))
    else:
        model = WhisperModel(model_name, device=device, compute_type=compute_type)
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
    shutil.copyfile(json_path, OUT / "primary.json")
    shutil.copyfile(srt_path, OUT / "primary.srt")
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
        "primary": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Transcribe only the synced reference source for this project.")
    parser.add_argument("--reference-role", default="master")
    parser.add_argument("--device", default=str(nested(APP_CONFIG, "analysis", "transcribeDevice", default="cuda") or "cuda"))
    parser.add_argument("--compute-type", default=str(nested(APP_CONFIG, "analysis", "fasterWhisperComputeType", default="float16") or "float16"))
    args = parser.parse_args()

    source = reference_source(args.reference_role)
    item = transcribe_reference(source, device=args.device, compute_type=args.compute_type)
    payload = {
        "model": transcribe_model_name(APP_CONFIG),
        "language": transcribe_language(APP_CONFIG),
        "singleReferenceOnly": True,
        "referenceRole": args.reference_role,
        "manifestFingerprint": transcript_manifest_fingerprint(APP_CONFIG),
        "outputDir": str(OUT),
        "primarySrt": str(OUT / "primary.srt"),
        "transcripts": [item],
        "errors": [],
    }
    write_path = OUT / "manifest_transcripts.json"
    write_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
