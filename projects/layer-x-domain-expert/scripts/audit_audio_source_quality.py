from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path
from typing import Any

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parents[1]
REPORTS = PROJECT_ROOT / "output" / "reports"
FFMPEG_DEFAULT = Path(r"C:\ProgramData\chocolatey\lib\ffmpeg\tools\ffmpeg\bin\ffmpeg.exe")
FFPROBE_DEFAULT = Path(r"C:\ProgramData\chocolatey\lib\ffmpeg\tools\ffmpeg\bin\ffprobe.exe")
SAMPLE_RATE = 16000

MEDIA = {
    "group_wide": {
        "role": "three_person_wide",
        "path": PROJECT_ROOT / "source" / "video" / "three people.mp4",
        "sync_role": "master",
    },
    "cam_person_01": {
        "role": "left_interviewer_camera",
        "path": PROJECT_ROOT / "source" / "video" / "person-left.mp4",
        "sync_role": "camera2",
    },
    "cam_person_02": {
        "role": "middle_interviewee_camera",
        "path": PROJECT_ROOT / "source" / "video" / "person-middle.mp4",
        "sync_role": "camera3",
    },
    "cam_person_03": {
        "role": "right_interviewee_camera",
        "path": PROJECT_ROOT / "source" / "video" / "person-right.mp4",
        "sync_role": "camera4",
    },
}

MASTER_WINDOWS = [
    {"label": "intro", "start": 519.14, "end": 560.0},
    {"label": "digest_question", "start": 1500.72, "end": 1508.76},
    {"label": "mid_interview", "start": 1983.1, "end": 2045.0},
    {"label": "late_interview", "start": 2926.04, "end": 2985.48},
]

CLOSING_REFERENCE_MEDIA_ID = "cam_person_02"
CLOSING_REFERENCE_WINDOWS = [
    {"label": "closing_thanks_01", "start": 3561.915, "end": 3580.865},
    {"label": "closing_thanks_02", "start": 3581.615, "end": 3586.350},
    {"label": "closing_thanks_03_left_speaker_camera", "start": 3591.150, "end": 3601.150},
    {"label": "closing_thanks_04_final_response", "start": 3606.700, "end": 3608.050},
]


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def ffmpeg_path() -> str:
    return str(FFMPEG_DEFAULT) if FFMPEG_DEFAULT.exists() else "ffmpeg"


def ffprobe_path() -> str:
    return str(FFPROBE_DEFAULT) if FFPROBE_DEFAULT.exists() else "ffprobe"


def probe_media(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        [
            ffprobe_path(),
            "-v",
            "error",
            "-show_entries",
            "format=duration,size:stream=index,codec_type,codec_name,channels,sample_rate,start_time,duration",
            "-of",
            "json",
            str(path),
        ],
        cwd=WORKSPACE_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


def media_duration(probe: dict[str, Any]) -> float:
    try:
        return float((probe.get("format") or {}).get("duration") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def extract_audio(path: Path, start: float, duration: float) -> np.ndarray:
    start = max(0.0, float(start))
    duration = max(0.05, float(duration))
    result = subprocess.run(
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
            str(SAMPLE_RATE),
            "-f",
            "f32le",
            "-",
        ],
        cwd=WORKSPACE_ROOT,
        check=True,
        capture_output=True,
    )
    return np.frombuffer(result.stdout, dtype=np.float32)


def dbfs(value: float) -> float:
    return 20.0 * math.log10(max(float(value), 1e-9))


def frame_rms(audio: np.ndarray, frame_sec: float = 0.05, hop_sec: float = 0.025) -> np.ndarray:
    frame = max(1, int(frame_sec * SAMPLE_RATE))
    hop = max(1, int(hop_sec * SAMPLE_RATE))
    if audio.size < frame:
        return np.asarray([], dtype=np.float32)
    values = []
    for index in range(0, audio.size - frame + 1, hop):
        window = audio[index : index + frame]
        values.append(math.sqrt(float(np.mean(window * window)) + 1e-12))
    return np.asarray(values, dtype=np.float32)


def audio_metrics(audio: np.ndarray) -> dict[str, Any]:
    if audio.size == 0:
        return {"status": "empty"}
    rms = math.sqrt(float(np.mean(audio * audio)) + 1e-12)
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    frames = frame_rms(audio)
    if frames.size:
        floor = float(np.percentile(frames, 20))
        p50 = float(np.percentile(frames, 50))
        p95 = float(np.percentile(frames, 95))
        threshold = max(floor * 1.8, p95 * 0.16, 0.003)
        active_ratio = float(np.mean(frames >= threshold))
    else:
        floor = p50 = p95 = rms
        threshold = max(rms * 0.5, 0.003)
        active_ratio = 0.0
    clipping_ratio = float(np.mean(np.abs(audio) > 0.98)) if audio.size else 0.0
    return {
        "status": "ok",
        "rms_dbfs": round(dbfs(rms), 2),
        "peak_dbfs": round(dbfs(peak), 2),
        "noise_floor_dbfs_p20": round(dbfs(floor), 2),
        "median_rms_dbfs_p50": round(dbfs(p50), 2),
        "speech_rms_dbfs_p95": round(dbfs(p95), 2),
        "snr_estimate_db_p95_minus_p20": round(dbfs(p95) - dbfs(floor), 2),
        "speech_activity_ratio": round(active_ratio, 3),
        "clipping_ratio": round(clipping_ratio, 6),
    }


def last_active_time(path: Path, duration: float) -> dict[str, Any]:
    chunk_sec = 300.0
    frames_all: list[tuple[float, float]] = []
    cursor = 0.0
    while cursor < duration:
        chunk_dur = min(chunk_sec, duration - cursor)
        audio = extract_audio(path, cursor, chunk_dur)
        rms_values = frame_rms(audio, frame_sec=0.1, hop_sec=0.1)
        for idx, value in enumerate(rms_values):
            frames_all.append((cursor + idx * 0.1, float(value)))
        cursor += chunk_dur
    values = np.asarray([value for _, value in frames_all], dtype=np.float32)
    if values.size == 0:
        return {"status": "no_audio"}
    floor = float(np.percentile(values, 20))
    peak = float(np.percentile(values, 95))
    threshold = max(floor * 1.8, peak * 0.14, 0.003)
    active_times = [time for time, value in frames_all if value >= threshold]
    return {
        "status": "ok",
        "threshold_dbfs": round(dbfs(threshold), 2),
        "last_active_sec": round(active_times[-1], 3) if active_times else None,
        "seconds_from_end": round(duration - active_times[-1], 3) if active_times else None,
        "active_frame_count": len(active_times),
        "floor_dbfs_p20": round(dbfs(floor), 2),
        "peak_dbfs_p95": round(dbfs(peak), 2),
    }


def synced_source_window(media_id: str, master_start: float, master_end: float, offsets: dict[str, float]) -> tuple[float, float]:
    role = MEDIA[media_id]["sync_role"]
    offset = float(offsets.get(role, 0.0))
    return master_start + offset, master_end + offset


def recommendation(media_rows: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = [row for row in media_rows if row["coverage"].get("covers_main_and_closing") and row["coverage"].get("closing_verified_by_synced_window")]
    for row in candidates:
        windows = [w["metrics"] for w in row["windows"] if w.get("metrics", {}).get("status") == "ok"]
        if windows:
            row["_avg_noise"] = sum(w["noise_floor_dbfs_p20"] for w in windows) / len(windows)
            row["_avg_snr"] = sum(w["snr_estimate_db_p95_minus_p20"] for w in windows) / len(windows)
            row["_clip"] = sum(w["clipping_ratio"] for w in windows) / len(windows)
        else:
            row["_avg_noise"] = -999
            row["_avg_snr"] = -999
            row["_clip"] = 1.0
    if not candidates:
        return {
            "main_audio_media_id": "group_wide",
            "confidence": 0.2,
            "reason": "No single source was confirmed to cover both the main interview and closing.",
        }
    candidates.sort(key=lambda row: (row["_avg_snr"], row["_avg_noise"], -row["_clip"]), reverse=True)
    best = candidates[0]
    return {
        "main_audio_media_id": best["media_id"],
        "confidence": 0.86,
        "reason": "Choose one continuous source that covers the full main interview and the synced closing-thanks take; avoid mid-video audio switching.",
        "do_not_patch_missing_tail_from_other_source": True,
        "fallback_policy": "If this source is judged too noisy in review, apply stronger denoise/mastering to this same source instead of switching sources mid-video.",
    }


def build_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Audio Source Quality Audit",
        "",
        "途中で音声素材を差し替えない前提で、全素材を比較した結果です。",
        "",
        "## Recommendation",
        "",
        f"- Main audio media id: `{report['recommendation']['main_audio_media_id']}`",
        f"- Reason: {report['recommendation']['reason']}",
        "",
        "## Summary",
        "",
        "| media_id | role | duration | covers main | synced closing verified | last active | avg noise floor | avg SNR | note |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in report["media"]:
        windows = [w["metrics"] for w in row["windows"] if w.get("metrics", {}).get("status") == "ok"]
        avg_noise = sum(w["noise_floor_dbfs_p20"] for w in windows) / len(windows) if windows else None
        avg_snr = sum(w["snr_estimate_db_p95_minus_p20"] for w in windows) / len(windows) if windows else None
        lines.append(
            "| {media_id} | {role} | {duration:.3f}s | {main} | {closing} | {last} | {noise} | {snr} | {note} |".format(
                media_id=row["media_id"],
                role=row["role"],
                duration=row["duration_sec"],
                main="yes" if row["coverage"].get("covers_main_interview") else "no",
                closing="yes" if row["coverage"].get("closing_verified_by_synced_window") else "no",
                last=row["last_active"].get("last_active_sec"),
                noise=f"{avg_noise:.2f} dBFS" if avg_noise is not None else "n/a",
                snr=f"{avg_snr:.2f} dB" if avg_snr is not None else "n/a",
                note=row["coverage"].get("note", ""),
            )
        )
    lines.extend(["", "## Window Metrics", ""])
    for row in report["media"]:
        lines.extend([f"### {row['media_id']}", "", "| window | source in-out | RMS | noise floor | speech p95 | SNR | activity |", "|---|---:|---:|---:|---:|---:|---:|"])
        for window in row["windows"]:
            metrics = window.get("metrics", {})
            lines.append(
                "| {label} | {start:.3f}-{end:.3f} | {rms} | {noise} | {speech} | {snr} | {activity} |".format(
                    label=window["label"],
                    start=window["source_start_sec"],
                    end=window["source_end_sec"],
                    rms=metrics.get("rms_dbfs"),
                    noise=metrics.get("noise_floor_dbfs_p20"),
                    speech=metrics.get("speech_rms_dbfs_p95"),
                    snr=metrics.get("snr_estimate_db_p95_minus_p20"),
                    activity=metrics.get("speech_activity_ratio"),
                )
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    offsets_payload = read_json(REPORTS / "app_sync_offsets.json", {"offsets": {"master": 0.0}})
    offsets = offsets_payload.get("offsets") if isinstance(offsets_payload.get("offsets"), dict) else {"master": 0.0}
    content_window = read_json(REPORTS / "content_window.json", {})
    main_range = (content_window.get("usable_master_range") or {})
    main_start = float(main_range.get("start_sec") or 519.14)
    main_end = float(main_range.get("end_sec") or 2985.485)
    media_rows = []
    reference_role = MEDIA[CLOSING_REFERENCE_MEDIA_ID]["sync_role"]
    reference_offset = float(offsets.get(reference_role, 0.0))
    closing_windows_by_media: dict[str, list[dict[str, float | str]]] = {}
    for media_id, info in MEDIA.items():
        role_offset = float(offsets.get(info["sync_role"], 0.0))
        converted = []
        for window in CLOSING_REFERENCE_WINDOWS:
            reference_clock_start = float(window["start"]) - reference_offset
            reference_clock_end = float(window["end"]) - reference_offset
            converted.append(
                {
                    "label": str(window["label"]),
                    "start": reference_clock_start + role_offset,
                    "end": reference_clock_end + role_offset,
                }
            )
        closing_windows_by_media[media_id] = converted

    for media_id, info in MEDIA.items():
        path = info["path"]
        probe = probe_media(path)
        duration = media_duration(probe)
        role = info["sync_role"]
        offset = float(offsets.get(role, 0.0))
        master_coverage = {"start_sec": round(-offset, 3), "end_sec": round(duration - offset, 3)}
        windows = []
        for window in MASTER_WINDOWS:
            source_start, source_end = synced_source_window(media_id, window["start"], window["end"], offsets)
            if source_start < 0 or source_end > duration:
                continue
            audio = extract_audio(path, source_start, source_end - source_start)
            windows.append(
                {
                    "label": window["label"],
                    "basis": "master_synced",
                    "master_start_sec": window["start"],
                    "master_end_sec": window["end"],
                    "source_start_sec": round(source_start, 3),
                    "source_end_sec": round(source_end, 3),
                    "metrics": audio_metrics(audio),
                }
            )
        closing_window_metrics = []
        for window in closing_windows_by_media.get(media_id, []):
            if float(window["start"]) < 0 or float(window["end"]) > duration:
                continue
            audio = extract_audio(path, window["start"], window["end"] - window["start"])
            metrics = audio_metrics(audio)
            closing_window_metrics.append(metrics)
            windows.append(
                {
                    "label": window["label"],
                    "basis": f"synced_closing_from_{CLOSING_REFERENCE_MEDIA_ID}",
                    "source_start_sec": window["start"],
                    "source_end_sec": window["end"],
                    "metrics": metrics,
                }
            )
        tail_start = max(0.0, duration - 60.0)
        tail_audio = extract_audio(path, tail_start, duration - tail_start)
        windows.append(
            {
                "label": "last_60_sec",
                "basis": "native_tail",
                "source_start_sec": round(tail_start, 3),
                "source_end_sec": round(duration, 3),
                "metrics": audio_metrics(tail_audio),
            }
        )
        covers_main = master_coverage["start_sec"] <= main_start and master_coverage["end_sec"] >= main_end
        closing_verified = bool(closing_window_metrics) and all(
            metrics.get("status") == "ok" and float(metrics.get("speech_activity_ratio") or 0.0) >= 0.2
            for metrics in closing_window_metrics
        )
        covers_closing = closing_verified
        note = ""
        if media_id == "group_wide":
            note = "Best reference transcript source, but file ends at the master content window and does not include the separate closing take."
        elif media_id == "cam_person_01":
            note = "Only source currently used for the closing take; covers both synced main interview and final thanks as one file."
        else:
            note = "Closing take is verified by syncing from the current cam_person_01 closing edit range."
        media_rows.append(
            {
                "media_id": media_id,
                "role": info["role"],
                "path": str(path),
                "duration_sec": round(duration, 3),
                "audio_streams": [s for s in probe.get("streams", []) if s.get("codec_type") == "audio"],
                "sync_role": role,
                "sync_offset_sec": offset,
                "master_timeline_coverage_sec": master_coverage,
                "coverage": {
                    "covers_main_interview": covers_main,
                    "covers_closing_thanks": covers_closing,
                    "closing_verified_by_synced_window": closing_verified,
                    "covers_main_and_closing": bool(covers_main and covers_closing),
                    "note": note,
                },
                "last_active": last_active_time(path, duration),
                "windows": windows,
            }
        )
    report = {
        "schema_version": "audio_source_quality_audit.v1",
        "project_id": "layer-x-domain-expert",
        "sample_rate_hz": SAMPLE_RATE,
        "policy": {
            "single_audio_source_for_interview": True,
            "no_mid_video_audio_source_switching": True,
            "reason": "Avoid audible noise-floor/timbre changes when the video angle changes or when the closing begins.",
        },
        "content_window_master_sec": {"start": main_start, "end": main_end},
        "sync_offsets": offsets,
        "media": media_rows,
        "recommendation": recommendation(media_rows),
    }
    write_json(REPORTS / "audio_source_quality_audit.json", report)
    write_text(REPORTS / "audio_source_quality_audit.md", build_markdown(report))
    print(json.dumps({"json": str(REPORTS / "audio_source_quality_audit.json"), "markdown": str(REPORTS / "audio_source_quality_audit.md"), "recommendation": report["recommendation"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
