from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from project_paths import OUTPUT_REPORTS, SCRIPTS, resolve_project_path
from timeline_validate import configured_timeline_path, load_timeline, validate_timeline
from video_edit_app_config import load_app_config, nested, optional_path, video_encoder_crf, video_encoder_preset


APP_CONFIG = load_app_config()
FFMPEG = optional_path(APP_CONFIG, "tools", "ffmpeg", default=Path(r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"))
FILTERGRAPH_DIR = OUTPUT_REPORTS / "filtergraphs"
COMMAND_DIR = OUTPUT_REPORTS / "renderer_commands"
RENDER_LOG_DIR = OUTPUT_REPORTS / "render_logs"
PRECOMPOSE_REPORT_DIR = OUTPUT_REPORTS / "renderer_artifacts"
BLENDER_EFFECT_TYPES = {"blenderscene", "3dtext", "threedtext", "extrudetext", "cameramove", "mesh"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def text_value(config: dict[str, Any], *keys: str, default: str = "") -> str:
    value = nested(config, *keys, default=default)
    return str(value) if value is not None else default


def bool_value(config: dict[str, Any], *keys: str, default: bool = False) -> bool:
    value = nested(config, *keys, default=default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return bool(value)


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if result == result and abs(result) != float("inf") else default


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def safe_stem(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._") or "timeline"


def ffmpeg_time(value: Any) -> str:
    return f"{as_float(value):.6f}"


def ffmpeg_filter_path(path: Path) -> str:
    return str(path).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def resolve_existing_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else resolve_project_path(path)


def safe_filter_chain(value: Any) -> str:
    text = str(value or "").strip()
    if not text or any(char in text for char in "\r\n;[]"):
        return ""
    return text


def even_dimension(value: int, minimum: int = 2) -> int:
    return max(minimum, int(round(value / 2) * 2))


def source_by_id(timeline: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(source.get("id")): source for source in timeline.get("sources", []) if isinstance(source, dict)}


def next_source_id(sources: dict[str, dict[str, Any]], prefix: str) -> str:
    base = safe_stem(prefix).lower().replace(".", "_") or "generated_source"
    candidate = base
    index = 2
    while candidate in sources:
        candidate = f"{base}_{index}"
        index += 1
    return candidate


def clips_for_track(timeline: dict[str, Any], track_id: str) -> list[dict[str, Any]]:
    return [
        clip
        for clip in timeline.get("clips", [])
        if isinstance(clip, dict) and str(clip.get("trackId") or "") == track_id
    ]


def wants_blender(clip: dict[str, Any]) -> bool:
    metadata = clip.get("metadata") if isinstance(clip.get("metadata"), dict) else {}
    style = clip.get("style") if isinstance(clip.get("style"), dict) else {}
    renderer = str(metadata.get("renderer") or style.get("renderer") or style.get("engine") or "").lower()
    if renderer == "blender":
        return True
    for effect in clip.get("effects", []):
        if not isinstance(effect, dict):
            continue
        if str(effect.get("type") or "").replace("-", "").lower() in BLENDER_EFFECT_TYPES:
            return True
    return False


def first_target(timeline: dict[str, Any]) -> dict[str, Any]:
    render = timeline.get("render") if isinstance(timeline.get("render"), dict) else {}
    targets = render.get("targets") if isinstance(render.get("targets"), list) else []
    final = next((target for target in targets if isinstance(target, dict) and target.get("id") == "final"), None)
    if isinstance(final, dict):
        return final
    first = next((target for target in targets if isinstance(target, dict)), None)
    if isinstance(first, dict):
        return first
    raise ValueError("timeline has no render target")


def timeline_fps(timeline: dict[str, Any], target: dict[str, Any]) -> str:
    fps = str(target.get("fps") or timeline.get("timebase", {}).get("fps") or "30000/1001")
    return fps if re.fullmatch(r"\d+(?:/\d+)?(?:\.\d+)?", fps) else "30000/1001"


def encoder_args(config: dict[str, Any], target: dict[str, Any]) -> list[str]:
    codec = str(target.get("videoCodec") or nested(config, "render", "videoEncoder", default="libx264") or "libx264").strip().lower()
    if codec == "h264_nvenc":
        preset = str(nested(config, "render", "nvencPreset", default="p4") or "p4").strip().lower()
        cq = max(0, min(51, as_int(nested(config, "render", "cq", default=23), 23)))
        return ["-c:v", "h264_nvenc", "-preset", preset, "-cq", str(cq), "-b:v", "0"]
    preset = video_encoder_preset(config, "render", "encoderPreset")
    crf = video_encoder_crf(config, "render", "crf")
    return ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p"]


def timeline_sources_needed(
    timeline: dict[str, Any],
    *,
    include_visual_overlays: bool = True,
    include_blender_overlays: bool = False,
) -> tuple[list[str], list[dict[str, Any]]]:
    supported_track_ids = {"video.main", "audio.main", "music.bed"}
    if include_visual_overlays:
        supported_track_ids.add("overlay.graphics")
    supported_source_ids: list[str] = []
    unsupported: list[dict[str, Any]] = []
    for clip in timeline.get("clips", []):
        if not isinstance(clip, dict):
            continue
        track_id = str(clip.get("trackId") or "")
        clip_kind = str(clip.get("kind") or "")
        source_id = clip.get("sourceId")
        if include_blender_overlays and wants_blender(clip):
            continue
        if not include_visual_overlays and track_id == "overlay.graphics":
            continue
        if clip_kind == "subtitle":
            if not include_visual_overlays:
                continue
            metadata = clip.get("metadata") if isinstance(clip.get("metadata"), dict) else {}
            precomposed_id = metadata.get("precomposedOverlaySourceId")
            if isinstance(precomposed_id, str) and precomposed_id not in supported_source_ids:
                supported_source_ids.append(precomposed_id)
            continue
        if track_id not in supported_track_ids or clip_kind == "generated":
            unsupported.append({"id": clip.get("id"), "trackId": track_id, "kind": clip_kind, "reason": "not implemented in FFmpeg timeline adapter"})
            continue
        if isinstance(source_id, str) and source_id not in supported_source_ids:
            supported_source_ids.append(source_id)
    return supported_source_ids, unsupported


def build_inputs(
    timeline: dict[str, Any],
    sources: dict[str, dict[str, Any]],
    needed_ids: list[str],
    fps: str,
) -> tuple[list[str], dict[str, int]]:
    argv: list[str] = []
    input_index_by_source: dict[str, int] = {}
    duration = as_float(timeline.get("duration"), 1.0)
    for source_id in needed_ids:
        source = sources[source_id]
        kind = str(source.get("kind") or "")
        path = str(source.get("path") or "")
        input_index_by_source[source_id] = len(input_index_by_source)
        if kind == "image":
            argv.extend(["-loop", "1", "-framerate", fps, "-t", ffmpeg_time(duration), "-i", path])
        else:
            argv.extend(["-i", path])
    return argv, input_index_by_source


def clip_scale(clip: dict[str, Any]) -> float:
    fit = clip.get("fit") if isinstance(clip.get("fit"), dict) else {}
    scale = as_float(fit.get("scale"), 1.0)
    for effect in clip.get("effects", []):
        if not isinstance(effect, dict) or effect.get("type") != "scaleCrop":
            continue
        params = effect.get("params") if isinstance(effect.get("params"), dict) else {}
        scale = as_float(params.get("scale"), scale)
    return max(1.0, scale)


def clip_crop_center(clip: dict[str, Any]) -> tuple[float, float]:
    fit = clip.get("fit") if isinstance(clip.get("fit"), dict) else {}
    crop = fit.get("crop") if isinstance(fit.get("crop"), dict) else {}
    center_x = as_float(crop.get("centerX"), 0.5)
    center_y = as_float(crop.get("centerY"), 0.5)
    for effect in clip.get("effects", []):
        if not isinstance(effect, dict) or effect.get("type") != "scaleCrop":
            continue
        params = effect.get("params") if isinstance(effect.get("params"), dict) else {}
        effect_crop = params.get("crop") if isinstance(params.get("crop"), dict) else {}
        center_x = as_float(effect_crop.get("centerX"), center_x)
        center_y = as_float(effect_crop.get("centerY"), center_y)
    return max(0.0, min(1.0, center_x)), max(0.0, min(1.0, center_y))


def color_effect_filters(clip: dict[str, Any]) -> list[str]:
    filters: list[str] = []
    for effect in clip.get("effects", []):
        if not isinstance(effect, dict) or effect.get("type") != "colorCorrection":
            continue
        params = effect.get("params") if isinstance(effect.get("params"), dict) else {}
        for key in ("filter", "manualFilter", "outputLookFilter"):
            filter_text = safe_filter_chain(params.get(key))
            if filter_text:
                filters.append(filter_text)
    return filters


def video_filter_for_clip(clip: dict[str, Any], input_index: int, label: str, target: dict[str, Any]) -> str:
    width = as_int(target.get("width"), 1920)
    height = as_int(target.get("height"), 1080)
    scale = clip_scale(clip)
    center_x, center_y = clip_crop_center(clip)
    scaled_width = max(2, int(round(width * scale / 2) * 2))
    scaled_height = max(2, int(round(height * scale / 2) * 2))
    crop_x = f"min(max(iw*{center_x:.6f}-{width / 2:.1f}\\,0)\\,iw-{width})"
    crop_y = f"min(max(ih*{center_y:.6f}-{height / 2:.1f}\\,0)\\,ih-{height})"
    visual_filters = [
        f"trim=start={ffmpeg_time(clip.get('sourceIn'))}:end={ffmpeg_time(clip.get('sourceOut'))}",
        "setpts=PTS-STARTPTS",
        f"scale={scaled_width}:{scaled_height}:force_original_aspect_ratio=increase",
        f"crop={width}:{height}:x='{crop_x}':y='{crop_y}'",
        *color_effect_filters(clip),
        "setsar=1",
    ]
    return (
        f"[{input_index}:v]"
        + ",".join(filter_text for filter_text in visual_filters if filter_text)
        + f"[{label}]"
    )


def build_video_filters(
    video_clips: list[dict[str, Any]],
    input_index_by_source: dict[str, int],
    target: dict[str, Any],
    fps: str,
) -> tuple[list[str], str]:
    filters: list[str] = []
    labels: list[str] = []
    for index, clip in enumerate(sorted(video_clips, key=lambda item: as_float(item.get("timelineStart"))), start=1):
        source_id = str(clip.get("sourceId") or "")
        input_index = input_index_by_source[source_id]
        label = f"vclip{index}"
        filters.append(video_filter_for_clip(clip, input_index, label, target))
        labels.append(label)
    if not labels:
        raise ValueError("timeline has no video.main clips")
    if len(labels) == 1:
        filters.append(f"[{labels[0]}]copy[vbase_raw]")
    else:
        filters.append("".join(f"[{label}]" for label in labels) + f"concat=n={len(labels)}:v=1:a=0[vbase_raw]")
    filters.append(f"[vbase_raw]fps={fps}[vbase]")
    return filters, "vbase"


def overlay_position_value(value: Any, default: str | int) -> str:
    if value is None:
        return str(default)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{float(value):.3f}".rstrip("0").rstrip(".")
    return str(value)


def build_overlay_filters(
    overlay_clips: list[dict[str, Any]],
    input_index_by_source: dict[str, int],
    current_label: str,
) -> tuple[list[str], str]:
    filters: list[str] = []
    current = current_label
    for index, clip in enumerate(sorted(overlay_clips, key=lambda item: as_float(item.get("timelineStart"))), start=1):
        source_id = str(clip.get("sourceId") or "")
        if source_id not in input_index_by_source:
            continue
        input_index = input_index_by_source[source_id]
        position = clip.get("position") if isinstance(clip.get("position"), dict) else {}
        height = as_int(position.get("height"), 0)
        overlay_label = f"ov{index}"
        if height > 0:
            filters.append(f"[{input_index}:v]scale=-1:{height},format=rgba[{overlay_label}]")
        else:
            filters.append(f"[{input_index}:v]format=rgba[{overlay_label}]")
        next_label = f"vov{index}"
        x_expr = overlay_position_value(position.get("x"), "(W-w)/2")
        y_expr = overlay_position_value(position.get("y"), "(H-h)/2")
        start = as_float(clip.get("timelineStart"))
        end = as_float(clip.get("timelineEnd"))
        filters.append(
            f"[{current}][{overlay_label}]overlay=x='{x_expr}':y='{y_expr}':enable='between(t,{start:.3f},{end:.3f})'[{next_label}]"
        )
        current = next_label
    return filters, current


def subtitle_force_style(clip: dict[str, Any]) -> str:
    style = clip.get("style") if isinstance(clip.get("style"), dict) else {}
    font_size = max(10, min(140, as_int(style.get("fontSize"), 64)))
    box_opacity = max(0.0, min(100.0, as_float(style.get("boxOpacity"), 65.0)))
    alpha = int(round(255 * (100.0 - box_opacity) / 100.0))
    return (
        "FontName=Yu Gothic UI,"
        f"FontSize={font_size},"
        "PrimaryColour=&H00FFFFFF,"
        f"BackColour=&H{alpha:02X}000000,"
        "OutlineColour=&H80000000,"
        "BorderStyle=4,"
        "Outline=1,"
        "Shadow=0,"
        "Alignment=2,"
        "MarginV=24"
    )


def build_subtitle_filters(
    subtitle_clips: list[dict[str, Any]],
    sources: dict[str, dict[str, Any]],
    input_index_by_source: dict[str, int],
    current_label: str,
) -> tuple[list[str], str, list[dict[str, Any]]]:
    filters: list[str] = []
    unsupported: list[dict[str, Any]] = []
    current = current_label
    for index, clip in enumerate(sorted(subtitle_clips, key=lambda item: as_float(item.get("timelineStart"))), start=1):
        style = clip.get("style") if isinstance(clip.get("style"), dict) else {}
        if str(style.get("mode") or "full") == "none":
            continue
        metadata = clip.get("metadata") if isinstance(clip.get("metadata"), dict) else {}
        precomposed_id = metadata.get("precomposedOverlaySourceId")
        if isinstance(precomposed_id, str) and precomposed_id in input_index_by_source:
            input_index = input_index_by_source[precomposed_id]
            overlay_label = f"subtitle_precomp{index}"
            next_label = f"vsubtitle{index}"
            start = as_float(clip.get("timelineStart"))
            end = as_float(clip.get("timelineEnd"))
            filters.append(f"[{input_index}:v]format=rgba,setpts=PTS-STARTPTS[{overlay_label}]")
            filters.append(f"[{current}][{overlay_label}]overlay=0:0:enable='between(t,{start:.3f},{end:.3f})'[{next_label}]")
            current = next_label
            continue
        source_id = str(clip.get("sourceId") or "")
        source = sources.get(source_id)
        if not source:
            unsupported.append({"id": clip.get("id"), "trackId": clip.get("trackId"), "kind": clip.get("kind"), "reason": "subtitle source missing"})
            continue
        path = Path(str(source.get("path") or ""))
        suffix = path.suffix.lower()
        next_label = f"vsubtitle{index}"
        escaped_path = ffmpeg_filter_path(path)
        if suffix == ".ass":
            filters.append(f"[{current}]ass=filename='{escaped_path}'[{next_label}]")
        elif suffix in {".srt", ".vtt"}:
            force_style = subtitle_force_style(clip).replace("'", r"\'")
            filters.append(f"[{current}]subtitles=filename='{escaped_path}':force_style='{force_style}'[{next_label}]")
        else:
            unsupported.append({"id": clip.get("id"), "trackId": clip.get("trackId"), "kind": clip.get("kind"), "reason": f"unsupported subtitle format: {suffix or '(none)'}"})
            continue
        current = next_label
    return filters, current, unsupported


def timeline_report_ref(path: Path) -> dict[str, Any]:
    return {"path": str(path), "exists": path.exists()}


def prepare_subtitle_precompositions(
    timeline: dict[str, Any],
    sources: dict[str, dict[str, Any]],
    fps: str,
) -> list[dict[str, Any]]:
    generated: list[dict[str, Any]] = []
    duration = as_float(timeline.get("duration"), 0.0)
    for clip in clips_for_track(timeline, "subtitle.main"):
        style = clip.get("style") if isinstance(clip.get("style"), dict) else {}
        metadata = clip.get("metadata") if isinstance(clip.get("metadata"), dict) else {}
        if str(style.get("renderMethod") or "") not in {"precompose-png-overlay", "precomposed-png-overlay"}:
            continue
        manifest_source_id = metadata.get("overlayManifestSourceId")
        manifest_path = Path(str(metadata.get("overlayManifestPath") or ""))
        if isinstance(manifest_source_id, str) and manifest_source_id in sources:
            manifest_path = Path(str(sources[manifest_source_id].get("path") or manifest_path))
        target_path = Path(str(metadata.get("precomposedOverlayTargetPath") or ""))
        existing_source_id = metadata.get("precomposedOverlaySourceId")
        if isinstance(existing_source_id, str) and existing_source_id in sources:
            target_path = Path(str(sources[existing_source_id].get("path") or target_path))
        if not manifest_path.exists() or not target_path:
            continue
        report_path = PRECOMPOSE_REPORT_DIR / f"{safe_stem(target_path.stem)}.precompose.json"
        source_id = existing_source_id if isinstance(existing_source_id, str) and existing_source_id in sources else next_source_id(sources, "src_subtitle_precomposed_overlay")
        if not target_path.exists() or target_path.stat().st_size <= 0:
            PRECOMPOSE_REPORT_DIR.mkdir(parents=True, exist_ok=True)
            sequence_dir = target_path.with_suffix("")
            command = [
                sys.executable,
                str(SCRIPTS / "precompose_png_overlay_video.py"),
                "--manifest",
                str(manifest_path),
                "--output",
                str(target_path),
                "--sequence-dir",
                str(sequence_dir),
                "--duration",
                ffmpeg_time(clip.get("timelineEnd") or duration),
                "--bottom-margin",
                str(as_int(metadata.get("precomposeBottomMargin"), 16)),
                "--fps",
                str(metadata.get("precomposeFps") or fps),
            ]
            completed = subprocess.run(command, capture_output=True, text=True)
            report = {
                "createdAt": now_iso(),
                "clipId": clip.get("id"),
                "kind": "subtitle-precompose",
                "status": "generated" if completed.returncode == 0 else "failed",
                "command": command,
                "manifest": timeline_report_ref(manifest_path),
                "output": str(target_path),
                "returnCode": completed.returncode,
                "stdout": completed.stdout[-4000:],
                "stderr": completed.stderr[-4000:],
            }
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            if completed.returncode:
                raise ValueError(f"subtitle precomposition failed for {clip.get('id')}: {report_path}")
            generated.append({key: report[key] for key in ["clipId", "kind", "status", "output", "returnCode"]})
            generated[-1]["report"] = str(report_path)
        else:
            generated.append(
                {
                    "clipId": clip.get("id"),
                    "kind": "subtitle-precompose",
                    "status": "reused-existing-target",
                    "manifest": str(manifest_path),
                    "output": str(target_path),
                    "report": str(report_path) if report_path.exists() else "",
                }
            )
        sources[source_id] = {
            "id": source_id,
            "kind": "video",
            "role": "subtitle-precomposed-overlay",
            "path": str(target_path),
        }
        metadata["precomposedOverlaySourceId"] = source_id
        metadata["precomposedOverlayPath"] = str(target_path)
        clip["metadata"] = metadata
    return generated


def audio_cleanup_filter(strength: int, mastering: bool = False, denoise: bool = True) -> str:
    nr = max(0, min(30, int(strength)))
    parts = ["highpass=f=80"]
    if denoise and nr > 0:
        parts.extend([f"afftdn=nr={nr}:nf=-35", "lowpass=f=16000"])
    if mastering:
        parts.extend(
            [
                "dynaudnorm=f=250:g=15:p=0.95:m=8",
                "acompressor=threshold=-20dB:ratio=2.8:attack=5:release=120:makeup=4",
                "loudnorm=I=-14:TP=-1.5:LRA=9",
                "alimiter=limit=0.95",
            ]
        )
    return ",".join(parts)


def audio_cleanup_from_clips(config: dict[str, Any], clips: list[dict[str, Any]]) -> str:
    denoise = bool_value(config, "render", "audioDenoise", default=True)
    mastering = bool_value(config, "render", "audioMastering", default=False)
    strength = as_int(nested(config, "render", "audioDenoiseStrength", default=10), 10)
    for clip in clips:
        for effect in clip.get("effects", []):
            if not isinstance(effect, dict) or effect.get("type") != "audioCleanup":
                continue
            params = effect.get("params") if isinstance(effect.get("params"), dict) else {}
            denoise = bool(params.get("denoise", denoise))
            mastering = bool(params.get("mastering", mastering))
            strength = as_int(params.get("strength"), strength)
    if not denoise and not mastering:
        return "anull"
    return audio_cleanup_filter(strength, mastering, denoise)


def build_audio_filters(
    timeline: dict[str, Any],
    config: dict[str, Any],
    input_index_by_source: dict[str, int],
) -> tuple[list[str], str]:
    filters: list[str] = []
    duration = as_float(timeline.get("duration"), 1.0)
    audio_clips = sorted(clips_for_track(timeline, "audio.main"), key=lambda item: as_float(item.get("timelineStart")))
    if not audio_clips:
        filters.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={duration:.6f},asetpts=PTS-STARTPTS[aout]")
        return filters, "aout"

    audio_labels: list[str] = []
    for index, clip in enumerate(audio_clips, start=1):
        source_id = str(clip.get("sourceId") or "")
        input_index = input_index_by_source[source_id]
        label = f"aud{index}"
        filters.append(
            f"[{input_index}:a]atrim=start={ffmpeg_time(clip.get('sourceIn'))}:end={ffmpeg_time(clip.get('sourceOut'))},asetpts=PTS-STARTPTS[{label}]"
        )
        audio_labels.append(label)
    if len(audio_labels) == 1:
        filters.append(f"[{audio_labels[0]}]{audio_cleanup_from_clips(config, audio_clips)}[voice]")
    else:
        filters.append("".join(f"[{label}]" for label in audio_labels) + f"concat=n={len(audio_labels)}:v=0:a=1[voice_raw]")
        filters.append(f"[voice_raw]{audio_cleanup_from_clips(config, audio_clips)}[voice]")

    music_clips = [clip for clip in clips_for_track(timeline, "music.bed") if isinstance(clip.get("sourceId"), str)]
    if not music_clips:
        return filters, "voice"

    mix_labels = ["voice"]
    for index, clip in enumerate(sorted(music_clips, key=lambda item: as_float(item.get("timelineStart"))), start=1):
        source_id = str(clip.get("sourceId") or "")
        input_index = input_index_by_source.get(source_id)
        if input_index is None:
            continue
        level = 1.0
        for effect in clip.get("effects", []):
            if isinstance(effect, dict) and effect.get("type") == "gain":
                params = effect.get("params") if isinstance(effect.get("params"), dict) else {}
                level = as_float(params.get("levelPercent"), 100.0) / 100.0
        label = f"music{index}"
        filters.append(
            f"[{input_index}:a]atrim=start={ffmpeg_time(clip.get('sourceIn'))}:end={ffmpeg_time(clip.get('sourceOut'))},"
            f"asetpts=PTS-STARTPTS,volume={max(0.0, min(1.0, level)):.4f}[{label}]"
        )
        mix_labels.append(label)
    if len(mix_labels) == 1:
        return filters, "voice"
    filters.append("".join(f"[{label}]" for label in mix_labels) + f"amix=inputs={len(mix_labels)}:duration=first:dropout_transition=0,alimiter=limit=0.95[aout]")
    return filters, "aout"


def add_range_filters(filters: list[str], video_label: str, audio_label: str, start: float, end: float) -> tuple[str, str]:
    filters.append(f"[{video_label}]trim=start={start:.6f}:end={end:.6f},setpts=PTS-STARTPTS[vrange]")
    filters.append(f"[{audio_label}]atrim=start={start:.6f}:end={end:.6f},asetpts=PTS-STARTPTS[arange]")
    return "vrange", "arange"


def add_proxy_filter(filters: list[str], video_label: str, width: int, height: int) -> str:
    proxy_width = even_dimension(width)
    proxy_height = even_dimension(height)
    filters.append(
        f"[{video_label}]scale={proxy_width}:{proxy_height}:force_original_aspect_ratio=decrease,"
        f"pad={proxy_width}:{proxy_height}:(ow-iw)/2:(oh-ih)/2,setsar=1[vproxy]"
    )
    return "vproxy"


def preview_output_path(base_output: Path, render_range: tuple[float, float] | None, proxy: bool) -> Path:
    suffixes: list[str] = []
    if render_range is not None:
        suffixes.append(f"range_{int(render_range[0] * 1000):08d}_{int(render_range[1] * 1000):08d}")
    if proxy:
        suffixes.append("proxy")
    if not suffixes:
        return base_output
    return base_output.with_name(f"{base_output.stem}.{'.'.join(suffixes)}{base_output.suffix}")


def default_remotion_overlay_report_path(base_output: Path, render_range: tuple[float, float] | None) -> Path:
    suffix = ""
    if render_range is not None:
        suffix = f"_range_{int(render_range[0] * 1000):08d}_{int(render_range[1] * 1000):08d}"
    return COMMAND_DIR / f"{safe_stem(f'{base_output.stem}{suffix}_remotion_layers')}.remotion.json"


def default_blender_overlay_report_path(base_output: Path, render_range: tuple[float, float] | None) -> Path:
    suffix = ""
    if render_range is not None:
        suffix = f"_range_{int(render_range[0] * 1000):08d}_{int(render_range[1] * 1000):08d}"
    return COMMAND_DIR / f"{safe_stem(f'{base_output.stem}{suffix}_blender_frames')}.blender.json"


def report_range_tuple(artifact: dict[str, Any]) -> tuple[float, float] | None:
    item = artifact.get("range") if isinstance(artifact.get("range"), dict) else {}
    if "start" not in item or "end" not in item:
        return None
    return as_float(item.get("start")), as_float(item.get("end"))


def assert_overlay_compatible(
    timeline: dict[str, Any],
    target: dict[str, Any],
    artifact: dict[str, Any],
    report_path: Path,
    render_range: tuple[float, float] | None,
    renderer: str,
) -> None:
    if artifact.get("renderer") != renderer:
        raise ValueError(f"overlay report is not a {renderer} artifact: {report_path}")
    if artifact.get("format") != "png-sequence":
        raise ValueError(f"FFmpeg overlay composition currently requires a {renderer} png-sequence artifact: {report_path}")
    if artifact.get("alpha") is not True:
        raise ValueError(f"{renderer} overlay artifact must preserve alpha: {report_path}")

    duration = as_float(timeline.get("duration"), 0.0)
    expected = render_range or (0.0, duration)
    actual = report_range_tuple(artifact)
    if actual is None:
        raise ValueError(f"{renderer} overlay report is missing range metadata: {report_path}")
    tolerance = max(0.05, 2.0 / max(as_float(artifact.get("fpsNumber"), 30.0), 1.0))
    if abs(actual[0] - expected[0]) > tolerance or abs(actual[1] - expected[1]) > tolerance:
        raise ValueError(
            f"{renderer} overlay range does not match FFmpeg render range: "
            f"overlay={actual[0]:.3f}-{actual[1]:.3f}, expected={expected[0]:.3f}-{expected[1]:.3f}, report={report_path}"
        )

    expected_width = as_int(target.get("width"), 1920)
    expected_height = as_int(target.get("height"), 1080)
    artifact_width = as_int(artifact.get("width"), expected_width)
    artifact_height = as_int(artifact.get("height"), expected_height)
    if artifact_width != expected_width or artifact_height != expected_height:
        raise ValueError(
            f"{renderer} overlay dimensions do not match FFmpeg target: "
            f"overlay={artifact_width}x{artifact_height}, expected={expected_width}x{expected_height}, report={report_path}"
        )


def assert_remotion_overlay_compatible(
    timeline: dict[str, Any],
    target: dict[str, Any],
    artifact: dict[str, Any],
    report_path: Path,
    render_range: tuple[float, float] | None,
) -> None:
    assert_overlay_compatible(timeline, target, artifact, report_path, render_range, "remotion")


def assert_blender_overlay_compatible(
    timeline: dict[str, Any],
    target: dict[str, Any],
    artifact: dict[str, Any],
    report_path: Path,
    render_range: tuple[float, float] | None,
) -> None:
    assert_overlay_compatible(timeline, target, artifact, report_path, render_range, "blender")


def sequence_file_key(path: Path) -> tuple[str, int, str, str]:
    match = re.match(r"^(.*?)(\d+)(\.[^.]+)$", path.name)
    if not match:
        return path.name, -1, "", path.name
    prefix, number, suffix = match.groups()
    return prefix, int(number), suffix, path.name


def planned_remotion_sequence_pattern(artifact: dict[str, Any]) -> tuple[str, int]:
    duration_frames = max(1, as_int(artifact.get("durationFrames"), 1))
    width = len(str(max(0, duration_frames - 1)))
    frame_pattern = f"%0{width}d" if width > 1 else "%d"
    template = str(artifact.get("imageSequencePattern") or "frame-[frame].[ext]")
    return template.replace("[frame]", frame_pattern).replace("[ext]", str(artifact.get("imageFormat") or "png")), 0


def planned_blender_sequence_pattern(artifact: dict[str, Any]) -> tuple[str, int]:
    template = str(artifact.get("imageSequencePattern") or "frame_[frame].[ext]")
    return template.replace("[frame]", "%04d").replace("[ext]", str(artifact.get("imageFormat") or "png")), 0


def sequence_input_args(
    artifact: dict[str, Any],
    report_path: Path,
    *,
    require_files: bool,
    planned_pattern: tuple[str, int],
) -> tuple[list[str], dict[str, Any]]:
    sequence_dir = resolve_existing_path(str(artifact.get("path") or ""))
    if not sequence_dir.is_dir() and require_files:
        raise ValueError(f"{artifact.get('renderer')} overlay PNG sequence directory does not exist: {sequence_dir}")
    files = sorted(sequence_dir.glob("*.png"), key=sequence_file_key) if sequence_dir.is_dir() else []
    if not files and require_files:
        raise ValueError(f"{artifact.get('renderer')} overlay PNG sequence has no PNG frames: {sequence_dir}")
    if not files:
        pattern_name, start_number = planned_pattern
        fps = str(artifact.get("fps") or artifact.get("fpsNumber") or "30000/1001")
        pattern = str(sequence_dir / pattern_name)
        return (
            ["-framerate", fps, "-start_number", str(start_number), "-i", pattern],
            {
                "path": str(sequence_dir),
                "pattern": pattern,
                "startNumber": start_number,
                "frameCount": 0,
                "expectedFrameCount": as_int(artifact.get("durationFrames"), 0),
                "fps": fps,
                "exists": False,
                "fileCheck": "planned-from-report",
            },
        )

    first_match = re.match(r"^(.*?)(\d+)(\.[^.]+)$", files[0].name)
    if not first_match:
        raise ValueError(f"{artifact.get('renderer')} overlay frame name is not numeric: {files[0].name}")
    prefix, number, suffix = first_match.groups()
    start_number = int(number)
    width = len(number)
    pattern_name = f"{prefix}%0{width}d{suffix}" if width > 1 else f"{prefix}%d{suffix}"
    expected_frames = as_int(artifact.get("durationFrames"), 0)
    if expected_frames > 0 and len(files) != expected_frames:
        raise ValueError(
            f"{artifact.get('renderer')} overlay frame count does not match the command report: "
            f"frames={len(files)}, expected={expected_frames}, dir={sequence_dir}, report={report_path}"
        )

    fps = str(artifact.get("fps") or artifact.get("fpsNumber") or "30000/1001")
    pattern = str(sequence_dir / pattern_name)
    return (
        ["-framerate", fps, "-start_number", str(start_number), "-i", pattern],
        {
            "path": str(sequence_dir),
            "pattern": pattern,
            "startNumber": start_number,
            "frameCount": len(files),
            "expectedFrameCount": expected_frames,
            "fps": fps,
            "exists": True,
            "fileCheck": "derived-from-existing-frames",
            "firstFrame": str(files[0]),
            "lastFrame": str(files[-1]),
        },
    )


def remotion_sequence_input_args(artifact: dict[str, Any], report_path: Path, *, require_files: bool) -> tuple[list[str], dict[str, Any]]:
    return sequence_input_args(artifact, report_path, require_files=require_files, planned_pattern=planned_remotion_sequence_pattern(artifact))


def blender_sequence_input_args(artifact: dict[str, Any], report_path: Path, *, require_files: bool) -> tuple[list[str], dict[str, Any]]:
    return sequence_input_args(artifact, report_path, require_files=require_files, planned_pattern=planned_blender_sequence_pattern(artifact))


def load_remotion_overlay(
    timeline: dict[str, Any],
    config: dict[str, Any],
    target: dict[str, Any],
    base_output_path: Path,
    render_range: tuple[float, float] | None,
    report_path_override: Path | None,
    require_sequence_files: bool,
) -> tuple[list[str], dict[str, Any]]:
    configured = text_value(config, "render", "remotionOverlayReportPath", default="").strip()
    report_path = report_path_override or (Path(configured) if configured else default_remotion_overlay_report_path(base_output_path, render_range))
    report_path = resolve_existing_path(report_path)
    if not report_path.exists():
        raise ValueError(f"Remotion overlay report does not exist: {report_path}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    artifact = report.get("overlayArtifact") if isinstance(report.get("overlayArtifact"), dict) else {}
    if report.get("timelineId") and report.get("timelineId") != timeline.get("id"):
        raise ValueError(
            f"Remotion overlay report was generated for {report.get('timelineId')}, "
            f"but timeline is {timeline.get('id')}: {report_path}"
        )
    assert_remotion_overlay_compatible(timeline, target, artifact, report_path, render_range)
    input_args, sequence = remotion_sequence_input_args(artifact, report_path, require_files=require_sequence_files)
    return input_args, {
        "commandReport": str(report_path),
        "layerManifest": report.get("layerManifest"),
        "artifact": artifact,
        "sequence": sequence,
    }


def load_blender_overlay(
    timeline: dict[str, Any],
    config: dict[str, Any],
    target: dict[str, Any],
    base_output_path: Path,
    render_range: tuple[float, float] | None,
    report_path_override: Path | None,
    require_sequence_files: bool,
) -> tuple[list[str], dict[str, Any]]:
    configured = text_value(config, "render", "blenderOverlayReportPath", default="").strip()
    report_path = report_path_override or (Path(configured) if configured else default_blender_overlay_report_path(base_output_path, render_range))
    report_path = resolve_existing_path(report_path)
    if not report_path.exists():
        raise ValueError(f"Blender overlay report does not exist: {report_path}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    artifact = report.get("overlayArtifact") if isinstance(report.get("overlayArtifact"), dict) else {}
    if report.get("timelineId") and report.get("timelineId") != timeline.get("id"):
        raise ValueError(
            f"Blender overlay report was generated for {report.get('timelineId')}, "
            f"but timeline is {timeline.get('id')}: {report_path}"
        )
    assert_blender_overlay_compatible(timeline, target, artifact, report_path, render_range)
    if artifact.get("noOp") or as_int(artifact.get("jobCount"), 0) <= 0:
        return [], {
            "commandReport": str(report_path),
            "jobsManifest": report.get("jobsManifest"),
            "artifact": artifact,
            "sequence": {"path": str(artifact.get("path") or ""), "frameCount": 0, "exists": False, "fileCheck": "no-blender-jobs"},
            "noOp": True,
        }
    input_args, sequence = blender_sequence_input_args(artifact, report_path, require_files=require_sequence_files)
    return input_args, {
        "commandReport": str(report_path),
        "jobsManifest": report.get("jobsManifest"),
        "artifact": artifact,
        "sequence": sequence,
        "noOp": False,
    }


def add_overlay_filter(filters: list[str], video_label: str, input_index: int, prefix: str) -> str:
    overlay_label = f"{prefix}_overlay"
    next_label = f"v{prefix}"
    filters.append(f"[{input_index}:v]format=rgba,setpts=PTS-STARTPTS[{overlay_label}]")
    filters.append(f"[{video_label}][{overlay_label}]overlay=0:0:shortest=1:format=auto[{next_label}]")
    return next_label


def write_filtergraph(filters: list[str], output_stem: str) -> Path:
    FILTERGRAPH_DIR.mkdir(parents=True, exist_ok=True)
    path = FILTERGRAPH_DIR / f"{safe_stem(output_stem)}.timeline.ffgraph"
    path.write_text(";\n".join(filters) + "\n", encoding="utf-8")
    return path


def write_command_report(report: dict[str, Any], output_stem: str) -> Path:
    COMMAND_DIR.mkdir(parents=True, exist_ok=True)
    path = COMMAND_DIR / f"{safe_stem(output_stem)}.ffmpeg.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def rewrite_command_report(report: dict[str, Any]) -> None:
    path = Path(str(report.get("commandReport") or ""))
    if path:
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def build_ffmpeg_command(
    timeline: dict[str, Any],
    config: dict[str, Any],
    *,
    output_override: Path | None = None,
    render_range: tuple[float, float] | None = None,
    proxy: bool = False,
    proxy_size: tuple[int, int] | None = None,
    with_remotion_overlays: bool = False,
    remotion_report_path: Path | None = None,
    require_remotion_sequence_files: bool = False,
    with_blender_overlays: bool = False,
    blender_report_path: Path | None = None,
    require_blender_sequence_files: bool = False,
) -> tuple[list[str], dict[str, Any]]:
    validation_errors, validation_warnings = validate_timeline(timeline)
    if validation_errors:
        raise ValueError("Timeline validation failed before FFmpeg adapter: " + "; ".join(validation_errors))
    duration = as_float(timeline.get("duration"), 0.0)
    if render_range is not None:
        range_start, range_end = render_range
        if range_start < 0 or range_end <= range_start or range_end > duration:
            raise ValueError(f"render range must be inside timeline duration: start={range_start}, end={range_end}, duration={duration}")

    target = first_target(timeline)
    target_output_path = Path(str(target.get("path") or "timeline_output.mp4"))
    output_path = output_override or preview_output_path(target_output_path, render_range, proxy)
    fps = timeline_fps(timeline, target)
    sources = source_by_id(timeline)
    generated_artifacts = [] if with_remotion_overlays else prepare_subtitle_precompositions(timeline, sources, fps)
    needed_ids, unsupported = timeline_sources_needed(
        timeline,
        include_visual_overlays=not with_remotion_overlays,
        include_blender_overlays=with_blender_overlays,
    )
    input_args, input_index_by_source = build_inputs(timeline, sources, needed_ids, fps)
    remotion_overlay: dict[str, Any] | None = None
    blender_overlay: dict[str, Any] | None = None
    if with_remotion_overlays:
        remotion_input_args, remotion_overlay = load_remotion_overlay(
            timeline,
            config,
            target,
            target_output_path,
            render_range,
            remotion_report_path,
            require_remotion_sequence_files,
        )
        remotion_overlay["inputIndex"] = len(input_index_by_source)
        input_args.extend(remotion_input_args)
    if with_blender_overlays:
        blender_input_args, blender_overlay = load_blender_overlay(
            timeline,
            config,
            target,
            target_output_path,
            render_range,
            blender_report_path,
            require_blender_sequence_files,
        )
        if blender_input_args:
            blender_overlay["inputIndex"] = len(input_index_by_source) + (1 if remotion_overlay is not None else 0)
            input_args.extend(blender_input_args)

    video_filters, video_label = build_video_filters(clips_for_track(timeline, "video.main"), input_index_by_source, target, fps)
    if with_remotion_overlays:
        overlay_filters: list[str] = []
        subtitle_filters: list[str] = []
        output_video_label = video_label
    else:
        overlay_filters, output_video_label = build_overlay_filters(clips_for_track(timeline, "overlay.graphics"), input_index_by_source, video_label)
        subtitle_filters, output_video_label, subtitle_unsupported = build_subtitle_filters(clips_for_track(timeline, "subtitle.main"), sources, input_index_by_source, output_video_label)
        unsupported.extend(subtitle_unsupported)
    audio_filters, output_audio_label = build_audio_filters(timeline, config, input_index_by_source)
    filters = video_filters + overlay_filters + subtitle_filters + audio_filters
    if render_range is not None:
        output_video_label, output_audio_label = add_range_filters(filters, output_video_label, output_audio_label, render_range[0], render_range[1])
    if remotion_overlay is not None:
        output_video_label = add_overlay_filter(filters, output_video_label, as_int(remotion_overlay.get("inputIndex"), 0), "remotion")
    if blender_overlay is not None and not blender_overlay.get("noOp") and "inputIndex" in blender_overlay:
        output_video_label = add_overlay_filter(filters, output_video_label, as_int(blender_overlay.get("inputIndex"), 0), "blender")
    if proxy:
        proxy_width, proxy_height = proxy_size or (960, 540)
        output_video_label = add_proxy_filter(filters, output_video_label, proxy_width, proxy_height)
    filter_script = write_filtergraph(filters, output_path.stem)
    command = [
        str(FFMPEG),
        "-hide_banner",
        "-y",
        *input_args,
        "-filter_complex_script",
        str(filter_script),
        "-map",
        f"[{output_video_label}]",
        "-map",
        f"[{output_audio_label}]",
        *encoder_args(config, target),
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        str(output_path),
    ]
    implemented_scope = [
        "video.main clip concat",
        "audio.main trim/concat",
        "overlay.graphics image overlay",
        "subtitle.main ASS/SRT/VTT rendering through FFmpeg subtitles filters",
        "subtitle.main precomposed rich PNG transparent-video overlay when referenced by timeline",
        "subtitle.main precomposition generation from timeline manifest when target artifact is absent or stale",
        "colorCorrection filter chains embedded in timeline clip effects",
        "scaleCrop zoom and crop-center expressions embedded in timeline clip effects",
        "person edit plan crop intent when embedded as timeline scaleCrop effects",
        "audioCleanup denoise/mastering filter chain",
        "music.bed audio mix when a source file exists",
        "camera-plan and natural-cut decisions already normalized into video.main timeline clips",
        "timeline-range preview export",
        "low-resolution proxy export",
    ]
    not_implemented_scope = [
        "Remotion/HyperFrames overlays",
        "Blender-generated elements",
    ]
    if with_remotion_overlays:
        implemented_scope = [
            item
            for item in implemented_scope
            if item
            not in {
                "overlay.graphics image overlay",
                "subtitle.main ASS/SRT/VTT rendering through FFmpeg subtitles filters",
                "subtitle.main precomposed rich PNG transparent-video overlay when referenced by timeline",
                "subtitle.main precomposition generation from timeline manifest when target artifact is absent or stale",
            }
        ]
        implemented_scope.append("Remotion PNG-sequence overlay artifact composition")
        not_implemented_scope[0] = "HyperFrames overlays"
    if with_blender_overlays:
        implemented_scope.append("Blender PNG-sequence overlay artifact composition")
        not_implemented_scope = [item for item in not_implemented_scope if item != "Blender-generated elements"]

    report = {
        "createdAt": now_iso(),
        "adapter": "ffmpeg",
        "timelineSchemaVersion": timeline.get("schemaVersion"),
        "timelineId": timeline.get("id"),
        "outputPath": str(output_path),
        "filterScript": str(filter_script),
        "argv": command,
        "inputSourceIds": needed_ids,
        "generatedArtifacts": generated_artifacts,
        "remotionOverlay": remotion_overlay,
        "blenderOverlay": blender_overlay,
        "unsupportedClips": unsupported,
        "validationWarnings": validation_warnings,
        "preview": {
            "range": {"start": render_range[0], "end": render_range[1]} if render_range is not None else None,
            "proxy": proxy,
            "proxySize": {"width": proxy_size[0], "height": proxy_size[1]} if proxy_size is not None else ({"width": 960, "height": 540} if proxy else None),
        },
        "scope": {
            "implemented": implemented_scope,
            "notImplemented": not_implemented_scope,
        },
    }
    command_report = write_command_report(report, output_path.stem)
    report["commandReport"] = str(command_report)
    command_report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return command, report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert validated timeline JSON into FFmpeg adapter command artifacts.")
    parser.add_argument("--timeline", type=Path, default=None, help="Timeline JSON path. Defaults to render.timelinePath.")
    parser.add_argument("--output", type=Path, default=None, help="Override render target output path.")
    parser.add_argument("--preview", action="store_true", help="Export the timeline preview range/proxy command instead of the full target command.")
    parser.add_argument("--range-start", type=float, default=None, help="Timeline start time for a partial render command.")
    parser.add_argument("--range-end", type=float, default=None, help="Timeline end time for a partial render command.")
    parser.add_argument("--proxy", action="store_true", help="Export a low-resolution proxy command.")
    parser.add_argument("--proxy-width", type=int, default=960, help="Proxy output width when --proxy or preview proxy is enabled.")
    parser.add_argument("--proxy-height", type=int, default=540, help="Proxy output height when --proxy or preview proxy is enabled.")
    parser.add_argument("--with-remotion-overlays", action="store_true", help="Composite a validated Remotion PNG-sequence overlay artifact into the FFmpeg render.")
    parser.add_argument("--remotion-report", type=Path, default=None, help="Remotion command report containing overlayArtifact metadata. Defaults to render.remotionOverlayReportPath or the target-derived report path.")
    parser.add_argument("--with-blender-overlays", action="store_true", help="Composite a validated Blender PNG-sequence overlay artifact into the FFmpeg render.")
    parser.add_argument("--blender-report", type=Path, default=None, help="Blender command report containing overlayArtifact metadata. Defaults to render.blenderOverlayReportPath or the target-derived report path.")
    parser.add_argument("--execute", action="store_true", help="Execute the generated FFmpeg command after writing audit artifacts.")
    return parser.parse_args()


def resolve_render_range(timeline: dict[str, Any], args: argparse.Namespace) -> tuple[float, float] | None:
    duration = as_float(timeline.get("duration"), 0.0)
    if args.range_start is not None or args.range_end is not None:
        return as_float(args.range_start, 0.0), as_float(args.range_end, duration)
    if not args.preview:
        return None
    render = timeline.get("render") if isinstance(timeline.get("render"), dict) else {}
    preview = render.get("preview") if isinstance(render.get("preview"), dict) else {}
    return as_float(preview.get("rangeStart"), 0.0), as_float(preview.get("rangeEnd"), duration)


def resolve_proxy(timeline: dict[str, Any], args: argparse.Namespace) -> bool:
    if args.proxy:
        return True
    if not args.preview:
        return False
    render = timeline.get("render") if isinstance(timeline.get("render"), dict) else {}
    preview = render.get("preview") if isinstance(render.get("preview"), dict) else {}
    return bool(preview.get("proxy"))


def main() -> None:
    args = parse_args()
    timeline_path = args.timeline or configured_timeline_path(APP_CONFIG)
    timeline = load_timeline(timeline_path)
    render_range = resolve_render_range(timeline, args)
    proxy = resolve_proxy(timeline, args)
    command, report = build_ffmpeg_command(
        timeline,
        APP_CONFIG,
        output_override=args.output,
        render_range=render_range,
        proxy=proxy,
        proxy_size=(args.proxy_width, args.proxy_height) if proxy else None,
        with_remotion_overlays=args.with_remotion_overlays,
        remotion_report_path=args.remotion_report,
        require_remotion_sequence_files=args.execute,
        with_blender_overlays=args.with_blender_overlays,
        blender_report_path=args.blender_report,
        require_blender_sequence_files=args.execute,
    )
    if args.execute:
        output_path = Path(str(report["outputPath"]))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        RENDER_LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_path = RENDER_LOG_DIR / f"{safe_stem(output_path.stem)}.ffmpeg.log"
        report["renderLog"] = str(log_path)
        report["executionStartedAt"] = now_iso()
        with log_path.open("w", encoding="utf-8", errors="replace") as log_file:
            completed = subprocess.run(command, stdout=log_file, stderr=subprocess.STDOUT)
        report["executed"] = True
        report["returnCode"] = completed.returncode
        report["executionEndedAt"] = now_iso()
        rewrite_command_report(report)
        if completed.returncode:
            print(json.dumps({key: report.get(key) for key in ["adapter", "outputPath", "filterScript", "commandReport", "renderLog", "unsupportedClips", "executed", "returnCode"]}, ensure_ascii=False, indent=2))
            raise SystemExit(completed.returncode)
    else:
        report["executed"] = False
        rewrite_command_report(report)
    print(json.dumps({key: report.get(key) for key in ["adapter", "outputPath", "filterScript", "commandReport", "renderLog", "unsupportedClips", "executed", "returnCode"] if key in report}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
