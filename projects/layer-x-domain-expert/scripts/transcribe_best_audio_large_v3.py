from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[1]
REPORTS_DIR = PROJECT_DIR / "output" / "reports"
OUT_DIR = PROJECT_DIR / "output" / "transcripts" / "best_audio_large_v3"
SOURCE_MEDIA = PROJECT_DIR / "source" / "video" / "person-middle.mp4"
QUALITY_AUDIT = REPORTS_DIR / "audio_source_quality_audit.json"
TRANSCRIPT_JSON = OUT_DIR / "cam_person_02_large_v3.json"
TRANSCRIPT_SRT = OUT_DIR / "cam_person_02_large_v3.srt"
MASTER_ALIGNED_JSON = REPORTS_DIR / "transcript_best_audio_large_v3_master_aligned.json"
MASTER_ALIGNED_SRT = OUT_DIR / "cam_person_02_large_v3_master_aligned.srt"
INPUT_WAV = OUT_DIR / "cam_person_02_whisper_input.wav"
REPORT_PATH = REPORTS_DIR / "best_audio_whisper_transcription_report.json"


MODEL_NAME = "large-v3"
LANGUAGE = "ja"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def srt_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    ms_total = int(round(seconds * 1000))
    hours, rem = divmod(ms_total, 3600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def write_srt(path: Path, segments: list[dict[str, Any]], start_key: str = "start", end_key: str = "end") -> None:
    lines: list[str] = []
    for index, segment in enumerate(segments, 1):
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        lines.extend(
            [
                str(index),
                f"{srt_time(float(segment[start_key]))} --> {srt_time(float(segment[end_key]))}",
                text,
                "",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def cam_person_02_offset() -> float:
    audit = load_json(QUALITY_AUDIT)
    for media in audit.get("media", []):
        if media.get("media_id") == "cam_person_02":
            return float(media.get("sync_offset_sec", 0.0))
    raise RuntimeError("cam_person_02 not found in audio_source_quality_audit.json")


def extract_whisper_wav() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if INPUT_WAV.exists() and INPUT_WAV.stat().st_size > 0:
        return
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(SOURCE_MEDIA),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-af",
        "highpass=f=70,lowpass=f=7600,loudnorm=I=-18:TP=-2:LRA=11",
        str(INPUT_WAV),
    ]
    subprocess.run(command, check=True)


def segment_to_dict(index: int, segment: Any) -> dict[str, Any]:
    payload = {
        "id": index,
        "start": round(float(getattr(segment, "start", 0.0)), 3),
        "end": round(float(getattr(segment, "end", 0.0)), 3),
        "text": str(getattr(segment, "text", "")).strip(),
    }
    for key in ("avg_logprob", "compression_ratio", "no_speech_prob"):
        value = getattr(segment, key, None)
        if value is not None:
            payload[key] = float(value)
    return payload


def transcribe() -> dict[str, Any]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as error:
        raise SystemExit("faster_whisper is required; run with .video-edit/venvs/whisper-cu128/Scripts/python.exe") from error

    if TRANSCRIPT_JSON.exists():
        return load_json(TRANSCRIPT_JSON)

    model = WhisperModel(MODEL_NAME, device="cuda", compute_type="float16")
    segments_iter, info = model.transcribe(
        str(INPUT_WAV),
        language=LANGUAGE,
        task="transcribe",
        beam_size=10,
        best_of=10,
        patience=1.2,
        temperature=0.0,
        condition_on_previous_text=True,
        vad_filter=True,
        vad_parameters={
            "min_silence_duration_ms": 450,
            "speech_pad_ms": 250,
        },
        initial_prompt=(
            "LayerX、バクラク、ドメインエキスパート、バックオフィス、PDM、プロダクトマネージャー、"
            "経理、労務、人事労務、エンジニア、AI、プロダクト開発についての日本語インタビュー。"
        ),
        no_speech_threshold=0.55,
        compression_ratio_threshold=2.4,
        log_prob_threshold=-1.0,
    )
    segments = [segment_to_dict(index, segment) for index, segment in enumerate(segments_iter)]
    result = {
        "schema_version": "best_audio_whisper_transcript.v1",
        "project_id": "layer-x-domain-expert",
        "generated_at": now_iso(),
        "source_audio_media_id": "cam_person_02",
        "source_media_path": str(SOURCE_MEDIA),
        "input_wav": str(INPUT_WAV),
        "model": MODEL_NAME,
        "backend": "faster-whisper",
        "device": "cuda",
        "compute_type": "float16",
        "language": getattr(info, "language", LANGUAGE),
        "duration": getattr(info, "duration", None),
        "options": {
            "beam_size": 10,
            "best_of": 10,
            "patience": 1.2,
            "temperature": 0.0,
            "condition_on_previous_text": True,
            "vad_filter": True,
        },
        "segments": segments,
        "text": "".join(segment.get("text", "") for segment in segments).strip(),
    }
    dump_json(TRANSCRIPT_JSON, result)
    write_srt(TRANSCRIPT_SRT, segments)
    return result


def build_master_aligned(result: dict[str, Any], sync_offset_sec: float) -> dict[str, Any]:
    aligned_segments: list[dict[str, Any]] = []
    for segment in result.get("segments", []):
        source_start = float(segment.get("start", 0.0))
        source_end = float(segment.get("end", source_start))
        next_segment = dict(segment)
        next_segment["source_start"] = round(source_start, 3)
        next_segment["source_end"] = round(source_end, 3)
        next_segment["master_start"] = round(source_start - sync_offset_sec, 3)
        next_segment["master_end"] = round(source_end - sync_offset_sec, 3)
        aligned_segments.append(next_segment)
    aligned = {
        **{key: value for key, value in result.items() if key not in {"segments", "text"}},
        "schema_version": "best_audio_whisper_transcript_master_aligned.v1",
        "source_audio_media_id": "cam_person_02",
        "sync_offset_sec": sync_offset_sec,
        "time_mapping": "master_time = cam_person_02_source_time - sync_offset_sec",
        "segments": aligned_segments,
        "text": "".join(segment.get("text", "") for segment in aligned_segments).strip(),
    }
    return aligned


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sync_offset_sec = cam_person_02_offset()
    extract_whisper_wav()
    result = transcribe()
    aligned = build_master_aligned(result, sync_offset_sec)
    dump_json(MASTER_ALIGNED_JSON, aligned)
    write_srt(MASTER_ALIGNED_SRT, aligned["segments"], start_key="master_start", end_key="master_end")
    report = {
        "generated_at": now_iso(),
        "selected_audio": {
            "media_id": "cam_person_02",
            "path": str(SOURCE_MEDIA),
            "sync_offset_sec": sync_offset_sec,
            "reason": "Best continuous source from audio_source_quality_audit.json; covers main interview and closing without mid-video audio switching.",
        },
        "whisper": {
            "backend": "faster-whisper",
            "model": MODEL_NAME,
            "device": "cuda",
            "compute_type": "float16",
            "quality_settings": "large-v3, beam_size=10, best_of=10, temperature=0.0, VAD enabled",
        },
        "outputs": {
            "source_json": str(TRANSCRIPT_JSON),
            "source_srt": str(TRANSCRIPT_SRT),
            "master_aligned_json": str(MASTER_ALIGNED_JSON),
            "master_aligned_srt": str(MASTER_ALIGNED_SRT),
        },
        "segment_count": len(aligned.get("segments", [])),
    }
    dump_json(REPORT_PATH, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
