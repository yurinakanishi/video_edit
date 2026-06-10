from __future__ import annotations

import json
import math
import re
import subprocess
import wave
from pathlib import Path
from typing import Any

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parents[1]
REPORTS = PROJECT_ROOT / "output" / "reports"
EDIT_PLAN = REPORTS / "edit_plan.json"
AUDIO_DIR = PROJECT_ROOT / "output" / "audio"
MASTER_WAV = AUDIO_DIR / "group_wide_mono_16k.wav"
SAMPLE_RATE = 16000


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def media_path(media_id: str) -> Path:
    manifest = read_json(REPORTS / "project_manifest.json")
    for item in manifest.get("media", []):
        if item.get("media_id") == media_id:
            return PROJECT_ROOT / str(item["path"])
    raise KeyError(f"media_id not found: {media_id}")


def ensure_master_wav() -> None:
    source = media_path("group_wide")
    if MASTER_WAV.exists() and MASTER_WAV.stat().st_mtime >= source.stat().st_mtime:
        return
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
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
            str(SAMPLE_RATE),
            "-sample_fmt",
            "s16",
            str(MASTER_WAV),
        ],
        cwd=WORKSPACE_ROOT,
        check=True,
    )


def load_audio() -> np.ndarray:
    ensure_master_wav()
    with wave.open(str(MASTER_WAV), "rb") as wav:
        frames = wav.readframes(wav.getnframes())
        audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    return audio


def srt_time_to_seconds(value: str) -> float:
    hours, minutes, rest = value.strip().split(":")
    seconds, millis = rest.split(",")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000.0


def parse_source_timecode(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, str) or "-->" not in value:
        return None
    left, right = [part.strip() for part in value.split("-->", 1)]
    try:
        return srt_time_to_seconds(left), srt_time_to_seconds(right)
    except (ValueError, IndexError):
        return None


def event_reference_in(event: dict[str, Any]) -> float:
    reference = event.get("reference_source") if isinstance(event.get("reference_source"), dict) else {}
    source = event.get("source") if isinstance(event.get("source"), dict) else {}
    return float(reference.get("in") if reference.get("in") is not None else source.get("in") or 0.0)


def event_duration(event: dict[str, Any]) -> float:
    return max(0.0, float(event.get("timeline_end") or 0.0) - float(event.get("timeline_start") or 0.0))


def overlay_source_window(event: dict[str, Any], overlay: dict[str, Any]) -> tuple[float, float] | None:
    parsed = parse_source_timecode(overlay.get("source_timecode"))
    if parsed:
        return parsed
    metadata = overlay.get("metadata") if isinstance(overlay.get("metadata"), dict) else {}
    source_start = metadata.get("source_start_sec")
    source_end = metadata.get("source_end_sec")
    if source_start is not None:
        try:
            start_f = float(source_start)
            end_f = float(source_end) if source_end is not None else start_f + max(1.2, float(overlay.get("end") or 0.0) - float(overlay.get("start") or 0.0))
            return start_f, max(start_f + 0.35, end_f)
        except (TypeError, ValueError):
            pass
    start = metadata.get("caption_start_sec")
    end = metadata.get("caption_end_sec")
    if start is not None:
        try:
            start_f = float(start)
            end_f = float(end) if end is not None else start_f + max(1.2, float(overlay.get("end") or 0.0) - float(overlay.get("start") or 0.0))
            return start_f, max(start_f + 0.35, end_f)
        except (TypeError, ValueError):
            pass
    ref_in = event_reference_in(event)
    try:
        return ref_in + float(overlay.get("start") or 0.0), ref_in + float(overlay.get("end") or 0.0)
    except (TypeError, ValueError):
        return None


def group_key(event: dict[str, Any], overlay: dict[str, Any], source_window: tuple[float, float]) -> tuple[Any, ...]:
    source_srt_index = overlay.get("source_srt_index")
    if source_srt_index is not None:
        return (
            event.get("event_id"),
            "srt",
            source_srt_index,
            round(source_window[0], 3),
            round(source_window[1], 3),
        )
    caption_part = overlay.get("caption_part") if isinstance(overlay.get("caption_part"), dict) else None
    if caption_part and caption_part.get("original_text"):
        return (
            event.get("event_id"),
            "caption_part",
            caption_part.get("original_text"),
            round(source_window[0], 3),
            round(source_window[1], 3),
        )
    caption_id = str(overlay.get("caption_id") or "")
    caption_id = re.sub(r"_part\d+$", "", caption_id)
    return (
        event.get("event_id"),
        "caption",
        caption_id or overlay.get("caption_no"),
        round(source_window[0], 3),
        round(source_window[1], 3),
    )


def speech_bounds(audio: np.ndarray, start: float, end: float) -> tuple[float, float, dict[str, Any]]:
    start = max(0.0, start)
    end = min(len(audio) / SAMPLE_RATE, max(start + 0.1, end))
    sample_start = int(start * SAMPLE_RATE)
    sample_end = int(end * SAMPLE_RATE)
    clip = audio[sample_start:sample_end]
    if len(clip) < int(0.08 * SAMPLE_RATE):
        return start, end, {"status": "too_short"}

    frame = int(0.02 * SAMPLE_RATE)
    hop = int(0.01 * SAMPLE_RATE)
    if len(clip) < frame:
        return start, end, {"status": "too_short"}
    rms = []
    for index in range(0, len(clip) - frame + 1, hop):
        window = clip[index : index + frame]
        rms.append(float(math.sqrt(float(np.mean(window * window)) + 1e-12)))
    values = np.asarray(rms, dtype=np.float32)
    if values.size == 0:
        return start, end, {"status": "no_frames"}

    floor = float(np.percentile(values, 20))
    peak = float(np.percentile(values, 95))
    threshold = max(floor * 1.8, peak * 0.16, 0.003)
    active = np.flatnonzero(values >= threshold)
    if active.size == 0:
        return start, end, {"status": "no_active_frames", "floor": floor, "peak": peak, "threshold": threshold}

    active_start = start + max(0.0, (int(active[0]) * hop) / SAMPLE_RATE - 0.06)
    active_end = start + min(end - start, ((int(active[-1]) * hop) + frame) / SAMPLE_RATE + 0.12)
    if active_end - active_start < 0.28:
        center = (active_start + active_end) / 2.0
        active_start = max(start, center - 0.18)
        active_end = min(end, center + 0.18)
    return active_start, active_end, {
        "status": "snapped",
        "floor": round(floor, 6),
        "peak": round(peak, 6),
        "threshold": round(threshold, 6),
        "active_frame_count": int(active.size),
    }


def text_weight(text: Any) -> float:
    text_value = re.sub(r"\s+", "", str(text or ""))
    return max(1.0, float(len(text_value)))


def assign_group_timings(
    event: dict[str, Any],
    group: list[tuple[int, dict[str, Any], tuple[float, float]]],
    audio: np.ndarray,
) -> dict[str, Any]:
    ref_in = event_reference_in(event)
    duration = event_duration(event)
    source_start = min(item[2][0] for item in group)
    source_end = max(item[2][1] for item in group)
    speech_start, speech_end, diagnostics = speech_bounds(audio, source_start, source_end)
    local_start = max(0.0, min(duration, speech_start - ref_in))
    local_end = max(local_start + 0.2, min(duration, speech_end - ref_in))
    if local_start >= duration:
        local_start = max(0.0, duration - 0.45)
        local_end = duration
    elif local_end > duration:
        local_end = duration
    min_total = min(duration, max(0.9, 0.8 * len(group)))
    if local_end - local_start < min_total:
        center = (local_start + local_end) / 2.0
        local_start = max(0.0, min(duration - min_total, center - min_total / 2.0))
        local_end = min(duration, local_start + min_total)
    total = max(0.2, local_end - local_start)
    weights = [text_weight(item[1].get("text")) for item in group]
    weight_sum = sum(weights) or 1.0
    cursor = local_start
    changed = 0
    for index, (_, overlay, _) in enumerate(group):
        part_duration = total * (weights[index] / weight_sum)
        next_start = cursor
        next_end = local_end if index == len(group) - 1 else cursor + part_duration
        if index < len(group) - 1 and next_end - next_start > 0.35:
            next_end -= 0.04
        old = (round(float(overlay.get("start") or 0.0), 3), round(float(overlay.get("end") or 0.0), 3))
        next_start = max(0.0, min(duration, next_start))
        min_part_duration = min(0.55, max(0.2, duration - next_start))
        next_end = min(duration, max(next_start + min_part_duration, next_end))
        overlay["start"] = round(next_start, 3)
        overlay["end"] = round(next_end, 3)
        overlay["audio_alignment"] = {
            "method": "master_audio_rms_speech_bounds",
            "source_audio_media_id": "group_wide",
            "source_window_sec": [round(source_start, 3), round(source_end, 3)],
            "speech_window_sec": [round(speech_start, 3), round(speech_end, 3)],
            "diagnostics": diagnostics,
        }
        new = (overlay["start"], overlay["end"])
        if old != new:
            changed += 1
        cursor = next_end + 0.04
    return {
        "event_id": event.get("event_id"),
        "group_size": len(group),
        "source_window_sec": [round(source_start, 3), round(source_end, 3)],
        "speech_window_sec": [round(speech_start, 3), round(speech_end, 3)],
        "changed_overlays": changed,
        "diagnostics": diagnostics,
    }


def align_plan(plan: dict[str, Any], audio: np.ndarray) -> dict[str, Any]:
    events = plan["timeline"]["events"] if isinstance(plan.get("timeline"), dict) else plan.get("timeline", [])
    report_groups = []
    changed_events = set()
    overlap_adjustments = []
    for event in events:
        overlays = event.get("overlays") if isinstance(event.get("overlays"), list) else []
        groups: dict[tuple[Any, ...], list[tuple[int, dict[str, Any], tuple[float, float]]]] = {}
        for index, overlay in enumerate(overlays):
            if not isinstance(overlay, dict) or overlay.get("type") != "caption":
                continue
            source_window = overlay_source_window(event, overlay)
            if source_window is None:
                continue
            key = group_key(event, overlay, source_window)
            groups.setdefault(key, []).append((index, overlay, source_window))
        for group in groups.values():
            group.sort(key=lambda item: (float(item[1].get("start") or 0.0), item[0]))
            result = assign_group_timings(event, group, audio)
            if result["changed_overlays"]:
                changed_events.add(str(event.get("event_id")))
            report_groups.append(result)

        event_duration_value = event_duration(event)
        caption_overlays = sorted(
            [overlay for overlay in overlays if isinstance(overlay, dict) and overlay.get("type") == "caption"],
            key=lambda overlay: (float(overlay.get("start") or 0.0), float(overlay.get("end") or 0.0)),
        )
        cursor = 0.0
        for overlay in caption_overlays:
            start = float(overlay.get("start") or 0.0)
            end = float(overlay.get("end") or 0.0)
            if start < cursor - 0.001:
                old = [round(start, 3), round(end, 3)]
                original_duration = max(0.45, end - start)
                start = min(max(0.0, cursor), max(0.0, event_duration_value - 0.45))
                end = min(event_duration_value, max(start + 0.45, start + original_duration))
                overlay["start"] = round(start, 3)
                overlay["end"] = round(end, 3)
                changed_events.add(str(event.get("event_id")))
                overlap_adjustments.append(
                    {
                        "event_id": event.get("event_id"),
                        "text": overlay.get("text"),
                        "old": old,
                        "new": [overlay["start"], overlay["end"]],
                    }
                )
            cursor = max(cursor, float(overlay.get("end") or 0.0) + 0.04)

    plan["caption_audio_alignment"] = {
        "schema_version": "caption_audio_alignment.v1",
        "method": "RMS energy speech bounds from group_wide master audio, applied after caption splitting",
        "audio_source": str(MASTER_WAV),
        "aligned_group_count": len(report_groups),
        "changed_event_count": len(changed_events),
        "changed_events": sorted(changed_events),
        "overlap_adjustment_count": len(overlap_adjustments),
    }
    write_json(
        REPORTS / "caption_audio_alignment_report.json",
        {"summary": plan["caption_audio_alignment"], "groups": report_groups, "overlap_adjustments": overlap_adjustments},
    )
    return plan


def main() -> None:
    audio = load_audio()
    plan = read_json(EDIT_PLAN)
    plan = align_plan(plan, audio)
    write_json(EDIT_PLAN, plan)
    print(json.dumps(plan["caption_audio_alignment"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
