from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any


DEFAULT_TRANSCRIBE_MODEL = "large-v3"
DEFAULT_TRANSCRIBE_LANGUAGE = "ja"
DEFAULT_BEAM_SIZE = 5
DEFAULT_NO_SPEECH_THRESHOLD = 0.6
DEFAULT_AVG_LOGPROB_THRESHOLD = -1.0


def bool_config(config: dict[str, Any], *keys: str, default: bool = False) -> bool:
    value: Any = config
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            return default
        value = value[key]
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def nested(config: dict[str, Any], *keys: str, default: Any = None) -> Any:
    value: Any = config
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            return default
        value = value[key]
    return value


def int_config(config: dict[str, Any], *keys: str, default: int) -> int:
    value = nested(config, *keys, default=default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def float_config(config: dict[str, Any], *keys: str, default: float) -> float:
    value = nested(config, *keys, default=default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def transcribe_model_name(config: dict[str, Any], *, fallback: str = DEFAULT_TRANSCRIBE_MODEL) -> str:
    return str(nested(config, "analysis", "transcribeModel", default=fallback) or fallback)


def transcribe_language(config: dict[str, Any]) -> str:
    return str(nested(config, "analysis", "transcribeLanguage", default=DEFAULT_TRANSCRIBE_LANGUAGE) or DEFAULT_TRANSCRIBE_LANGUAGE)


def normalize_terms(raw_terms: Any) -> list[str]:
    terms: list[str] = []
    if isinstance(raw_terms, str):
        terms.extend(part.strip() for part in re.split(r"[,、\n]", raw_terms) if part.strip())
    elif isinstance(raw_terms, list):
        for item in raw_terms:
            if isinstance(item, str):
                terms.extend(normalize_terms(item))
            elif isinstance(item, dict):
                terms.extend(normalize_terms(item.get("label", "")))
                terms.extend(normalize_terms(item.get("patterns", "")))
    return terms


def glossary_terms(config: dict[str, Any]) -> list[str]:
    terms = nested(config, "glossary", "terms", default=[])
    if not isinstance(terms, list):
        return []
    enabled_terms: list[str] = []
    for term in terms:
        if not isinstance(term, dict) or term.get("enabled") is False:
            continue
        enabled_terms.extend(normalize_terms(term.get("label", "")))
        enabled_terms.extend(normalize_terms(term.get("patterns", "")))
    return enabled_terms


def prompt_terms(config: dict[str, Any]) -> list[str]:
    terms = [
        *normalize_terms(nested(config, "analysis", "transcribePromptTerms", default="")),
        *glossary_terms(config),
    ]
    seen: set[str] = set()
    unique: list[str] = []
    for term in terms:
        key = term.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(term)
    return unique


def initial_prompt(config: dict[str, Any], *, extra: str = "") -> str:
    user_prompt = str(nested(config, "analysis", "transcribeInitialPrompt", default="") or "").strip()
    terms = prompt_terms(config)
    parts = [
        "これは日本語のインタビュー音声です。音声に忠実に文字起こししてください。",
        "聞き取れない部分は推測で補完しないでください。",
    ]
    if terms:
        parts.append(f"以下の語が出る可能性があります：{'、'.join(terms)}。")
    if user_prompt:
        parts.append(user_prompt)
    if extra:
        parts.append(extra.strip())
    return "\n".join(part for part in parts if part)


def transcribe_options(config: dict[str, Any], *, prompt_extra: str = "") -> dict[str, Any]:
    options: dict[str, Any] = {
        "language": transcribe_language(config),
        "task": "transcribe",
        "fp16": False,
        "verbose": False,
        "temperature": float_config(config, "analysis", "transcribeTemperature", default=0.0),
        "beam_size": max(1, int_config(config, "analysis", "transcribeBeamSize", default=DEFAULT_BEAM_SIZE)),
        "condition_on_previous_text": bool_config(config, "analysis", "conditionOnPreviousText", default=False),
        "initial_prompt": initial_prompt(config, extra=prompt_extra),
        "no_speech_threshold": float_config(
            config,
            "analysis",
            "transcribeNoSpeechThreshold",
            default=DEFAULT_NO_SPEECH_THRESHOLD,
        ),
        "logprob_threshold": float_config(config, "analysis", "transcribeLogprobThreshold", default=-1.0),
        "compression_ratio_threshold": float_config(config, "analysis", "transcribeCompressionRatioThreshold", default=2.4),
    }
    return options


def safe_stem(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_") or "audio"


def should_normalize_audio(config: dict[str, Any]) -> bool:
    return bool_config(config, "analysis", "transcribeNormalizeAudio", default=True)


def ffmpeg_audio_filter(config: dict[str, Any]) -> str:
    if not should_normalize_audio(config):
        return "anull"
    return str(
        nested(
            config,
            "analysis",
            "transcribeAudioFilter",
            default="loudnorm=I=-16:TP=-1.5:LRA=11",
        )
        or "anull"
    )


def preprocessed_audio_path(source: Path, out_dir: Path, label: str, config: dict[str, Any]) -> Path:
    suffix = "norm" if should_normalize_audio(config) else "raw"
    filter_key = hashlib.sha256(ffmpeg_audio_filter(config).encode("utf-8")).hexdigest()[:10]
    return out_dir / f"{safe_stem(label)}_16k_mono_{suffix}_{filter_key}.wav"


def preprocess_audio(source: Path, out_dir: Path, label: str, ffmpeg: Path, config: dict[str, Any]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    output = preprocessed_audio_path(source, out_dir, label, config)
    if output.exists() and output.stat().st_mtime >= source.stat().st_mtime:
        return output
    command = [
        str(ffmpeg),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-af",
        ffmpeg_audio_filter(config),
        "-c:a",
        "pcm_s16le",
        str(output),
    ]
    subprocess.run(command, check=True)
    return output


def should_filter_low_confidence(config: dict[str, Any]) -> bool:
    return bool_config(config, "analysis", "transcribeFilterLowConfidence", default=True)


def filter_low_confidence_segments(result: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    if not should_filter_low_confidence(config):
        return result
    no_speech_threshold = float_config(
        config,
        "analysis",
        "transcribeNoSpeechThreshold",
        default=DEFAULT_NO_SPEECH_THRESHOLD,
    )
    avg_logprob_threshold = float_config(
        config,
        "analysis",
        "transcribeAvgLogprobFilterThreshold",
        default=DEFAULT_AVG_LOGPROB_THRESHOLD,
    )
    segments = result.get("segments", [])
    if not isinstance(segments, list):
        return result
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        text = str(segment.get("text", "")).strip()
        no_speech = float(segment.get("no_speech_prob", 0.0) or 0.0)
        avg_logprob = float(segment.get("avg_logprob", 0.0) or 0.0)
        is_likely_hallucination = no_speech >= no_speech_threshold and avg_logprob <= avg_logprob_threshold
        if not text or is_likely_hallucination:
            dropped.append(segment)
            continue
        kept.append(segment)
    next_result = dict(result)
    next_result["segments"] = kept
    next_result["text"] = "".join(str(segment.get("text", "")) for segment in kept).strip()
    next_result["filtered_segments"] = dropped
    return next_result


def settings_payload(source: Path, model_name: str, audio_path: Path, options: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    relevant = {
        "normalize_audio": should_normalize_audio(config),
        "audio_filter": ffmpeg_audio_filter(config),
        "filter_low_confidence": should_filter_low_confidence(config),
        "source_mtime": source.stat().st_mtime,
    }
    prompt = str(options.get("initial_prompt", ""))
    return {
        "source": str(source),
        "model": model_name,
        "audio": str(audio_path),
        "options": {**options, "initial_prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest()},
        "prompt": prompt,
        "quality": relevant,
    }


def settings_match(path: Path, payload: dict[str, Any]) -> bool:
    if not path.exists():
        return False
    try:
        return json.loads(path.read_text(encoding="utf-8")) == payload
    except (OSError, json.JSONDecodeError):
        return False


def format_srt_time(seconds: float) -> str:
    ms = round(seconds * 1000)
    hours, rem = divmod(ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def write_srt(path: Path, segments: list[dict[str, Any]]) -> None:
    rows: list[str] = []
    index = 1
    for segment in segments:
        text = str(segment.get("text", "")).strip()
        if not text:
            continue
        rows.extend(
            [
                str(index),
                f"{format_srt_time(float(segment['start']))} --> {format_srt_time(float(segment['end']))}",
                text,
                "",
            ]
        )
        index += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(rows), encoding="utf-8")
