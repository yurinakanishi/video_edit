from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[1]
REPORTS_DIR = PROJECT_DIR / "output" / "reports"
OUT_DIR = PROJECT_DIR / "output" / "transcripts" / "best_audio_large_v3_chunked"
CHUNK_DIR = OUT_DIR / "chunks"
SOURCE_MEDIA = PROJECT_DIR / "source" / "video" / "person-middle.mp4"
QUALITY_AUDIT = REPORTS_DIR / "audio_source_quality_audit.json"
SOURCE_JSON = OUT_DIR / "cam_person_02_large_v3_chunked.json"
SOURCE_SRT = OUT_DIR / "cam_person_02_large_v3_chunked.srt"
MASTER_JSON = REPORTS_DIR / "transcript_best_audio_large_v3_chunked_master_aligned.json"
MASTER_SRT = OUT_DIR / "cam_person_02_large_v3_chunked_master_aligned.srt"
REPORT_PATH = REPORTS_DIR / "best_audio_whisper_chunked_transcription_report.json"


MODEL_NAME = "large-v3"
LANGUAGE = "ja"
CHUNK_SEC = 30.0
PAD_SEC = 1.0


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


def ffprobe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    return float(result.stdout.strip())


def cam_person_02_offset() -> float:
    audit = load_json(QUALITY_AUDIT)
    for media in audit.get("media", []):
        if media.get("media_id") == "cam_person_02":
            return float(media.get("sync_offset_sec", 0.0))
    raise RuntimeError("cam_person_02 not found in audio_source_quality_audit.json")


def extract_chunk(chunk_index: int, start: float, end: float, duration: float) -> Path:
    CHUNK_DIR.mkdir(parents=True, exist_ok=True)
    padded_start = max(0.0, start - PAD_SEC)
    padded_end = min(duration, end + PAD_SEC)
    wav = CHUNK_DIR / f"chunk_{chunk_index:04d}_{start:08.3f}.wav"
    if wav.exists() and wav.stat().st_size > 0:
        return wav
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{padded_start:.3f}",
            "-t",
            f"{padded_end - padded_start:.3f}",
            "-i",
            str(SOURCE_MEDIA),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-af",
            "highpass=f=70,lowpass=f=7600,loudnorm=I=-18:TP=-2:LRA=11",
            str(wav),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return wav


def segment_to_dict(segment_id: int, segment: Any, chunk_start: float, padded_start: float) -> dict[str, Any] | None:
    rel_start = float(getattr(segment, "start", 0.0))
    rel_end = float(getattr(segment, "end", rel_start))
    source_start = padded_start + rel_start
    source_end = padded_start + rel_end
    midpoint = (source_start + source_end) / 2
    if midpoint < chunk_start or midpoint >= chunk_start + CHUNK_SEC:
        return None
    text = str(getattr(segment, "text", "")).strip()
    if not text:
        return None
    payload = {
        "id": segment_id,
        "source_start": round(source_start, 3),
        "source_end": round(source_end, 3),
        "start": round(source_start, 3),
        "end": round(source_end, 3),
        "text": text,
    }
    for key in ("avg_logprob", "compression_ratio", "no_speech_prob"):
        value = getattr(segment, key, None)
        if value is not None:
            payload[key] = float(value)
    return payload


def transcribe_chunk(model: Any, wav: Path, chunk_start: float, padded_start: float, next_id: int) -> list[dict[str, Any]]:
    segments_iter, _ = model.transcribe(
        str(wav),
        language=LANGUAGE,
        task="transcribe",
        beam_size=10,
        best_of=10,
        patience=1.2,
        temperature=0.0,
        condition_on_previous_text=False,
        vad_filter=False,
        initial_prompt=(
            "LayerX、バクラク、ドメインエキスパート、バックオフィス、PDM、プロダクトマネージャー、"
            "経理、労務、人事労務、エンジニア、AI、プロダクト開発についての日本語インタビュー。"
        ),
        no_speech_threshold=0.55,
        compression_ratio_threshold=2.4,
        log_prob_threshold=-1.0,
    )
    rows: list[dict[str, Any]] = []
    for segment in segments_iter:
        row = segment_to_dict(next_id + len(rows), segment, chunk_start, padded_start)
        if row is not None:
            rows.append(row)
    return rows


def align_to_master(source_payload: dict[str, Any], sync_offset_sec: float) -> dict[str, Any]:
    aligned_segments = []
    for segment in source_payload.get("segments", []):
        next_segment = dict(segment)
        next_segment["master_start"] = round(float(segment["source_start"]) - sync_offset_sec, 3)
        next_segment["master_end"] = round(float(segment["source_end"]) - sync_offset_sec, 3)
        aligned_segments.append(next_segment)
    return {
        **{key: value for key, value in source_payload.items() if key not in {"segments", "text"}},
        "schema_version": "best_audio_whisper_transcript_chunked_master_aligned.v1",
        "sync_offset_sec": sync_offset_sec,
        "time_mapping": "master_time = cam_person_02_source_time - sync_offset_sec",
        "segments": aligned_segments,
        "text": "".join(segment.get("text", "") for segment in aligned_segments).strip(),
    }


def main() -> None:
    from faster_whisper import WhisperModel

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    duration = ffprobe_duration(SOURCE_MEDIA)
    sync_offset_sec = cam_person_02_offset()
    model = WhisperModel(MODEL_NAME, device="cuda", compute_type="float16")
    segments: list[dict[str, Any]] = []
    chunk_reports = []
    chunk_index = 0
    start = 0.0
    while start < duration:
        end = min(duration, start + CHUNK_SEC)
        padded_start = max(0.0, start - PAD_SEC)
        wav = extract_chunk(chunk_index, start, end, duration)
        rows = transcribe_chunk(model, wav, start, padded_start, len(segments))
        segments.extend(rows)
        chunk_reports.append(
            {
                "chunk_index": chunk_index,
                "source_start": round(start, 3),
                "source_end": round(end, 3),
                "segment_count": len(rows),
                "wav": str(wav),
            }
        )
        progress = {"chunk": chunk_index, "source_start": round(start, 3), "segments_total": len(segments)}
        print(json.dumps(progress, ensure_ascii=False), flush=True)
        chunk_index += 1
        start += CHUNK_SEC

    source_payload = {
        "schema_version": "best_audio_whisper_transcript_chunked.v1",
        "project_id": "layer-x-domain-expert",
        "generated_at": now_iso(),
        "source_audio_media_id": "cam_person_02",
        "source_media_path": str(SOURCE_MEDIA),
        "model": MODEL_NAME,
        "backend": "faster-whisper",
        "device": "cuda",
        "compute_type": "float16",
        "language": LANGUAGE,
        "chunk_sec": CHUNK_SEC,
        "pad_sec": PAD_SEC,
        "options": {
            "beam_size": 10,
            "best_of": 10,
            "patience": 1.2,
            "temperature": 0.0,
            "condition_on_previous_text": False,
            "vad_filter": False,
        },
        "segments": segments,
        "text": "".join(segment.get("text", "") for segment in segments).strip(),
    }
    dump_json(SOURCE_JSON, source_payload)
    write_srt(SOURCE_SRT, segments)
    aligned = align_to_master(source_payload, sync_offset_sec)
    dump_json(MASTER_JSON, aligned)
    write_srt(MASTER_SRT, aligned["segments"], start_key="master_start", end_key="master_end")
    report = {
        "generated_at": now_iso(),
        "selected_audio": {
            "media_id": "cam_person_02",
            "path": str(SOURCE_MEDIA),
            "sync_offset_sec": sync_offset_sec,
            "reason": "Best continuous source from audio_source_quality_audit.json; chunked transcription avoids long-form Whisper hallucination.",
        },
        "whisper": {
            "backend": "faster-whisper",
            "model": MODEL_NAME,
            "device": "cuda",
            "compute_type": "float16",
            "quality_settings": "large-v3, beam_size=10, best_of=10, temperature=0.0, chunked 30s, no previous-text conditioning",
        },
        "outputs": {
            "source_json": str(SOURCE_JSON),
            "source_srt": str(SOURCE_SRT),
            "master_aligned_json": str(MASTER_JSON),
            "master_aligned_srt": str(MASTER_SRT),
        },
        "chunk_count": len(chunk_reports),
        "segment_count": len(segments),
        "chunks": chunk_reports,
    }
    dump_json(REPORT_PATH, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
