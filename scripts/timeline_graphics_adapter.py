from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from project_paths import OUTPUT_REPORTS, ROOT as WORK
from timeline_validate import configured_timeline_path, load_timeline, validate_timeline
from video_edit_app_config import load_app_config, nested


APP_CONFIG = load_app_config()
COMMAND_DIR = OUTPUT_REPORTS / "renderer_commands"
ARTIFACT_DIR = OUTPUT_REPORTS / "renderer_artifacts"
RENDER_LOG_DIR = OUTPUT_REPORTS / "render_logs"
REMOTION_PUBLIC_ASSET_DIR = WORK / "public" / "adapter-assets"

HTML_LAYER_TRACKS = {"video.main", "overlay.graphics", "subtitle.main", "audio.main", "music.bed"}
BLENDER_EFFECT_TYPES = {"blenderscene", "3dtext", "threedtext", "extrudetext", "cameramove", "mesh"}
MEDIA_SUFFIXES = {".mp4", ".mov", ".webm", ".mkv"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


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


def seconds_from_timestamp(value: Any) -> float:
    text = str(value or "").strip().replace(",", ".")
    if not text:
        return 0.0
    if ":" not in text:
        return as_float(text, 0.0)
    parts = text.split(":")
    try:
        seconds = float(parts[-1])
        minutes = int(parts[-2]) if len(parts) >= 2 else 0
        hours = int(parts[-3]) if len(parts) >= 3 else 0
    except ValueError:
        return 0.0
    return hours * 3600 + minutes * 60 + seconds


def text_value(config: dict[str, Any], *keys: str, default: str = "") -> str:
    value = nested(config, *keys, default=default)
    return str(value) if value is not None else default


def safe_stem(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._") or "timeline"


def output_artifact_stem(path: Path) -> str:
    return path.stem if path.suffix.lower() in MEDIA_SUFFIXES else path.name


def fps_number(value: Any) -> float:
    text = str(value or "30000/1001")
    if "/" in text:
        top, bottom = text.split("/", 1)
        denominator = as_float(bottom, 1.0)
        return as_float(top, 30.0) / denominator if denominator else 30.0
    return as_float(text, 30.0)


def frame_at(seconds: float, fps: float) -> int:
    return max(0, int(round(seconds * fps)))


def resolve_path(value: str | Path) -> Path:
    path = Path(str(value))
    return path if path.is_absolute() else WORK / path


def source_by_id(timeline: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(source.get("id")): source for source in timeline.get("sources", []) if isinstance(source, dict)}


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


def target_fps(timeline: dict[str, Any], target: dict[str, Any]) -> str:
    return str(target.get("fps") or timeline.get("timebase", {}).get("fps") or "30000/1001")


def source_ref(source: dict[str, Any] | None) -> dict[str, Any] | None:
    if not source:
        return None
    path = Path(str(source.get("path") or ""))
    return {
        "id": source.get("id"),
        "kind": source.get("kind"),
        "role": source.get("role"),
        "path": str(path),
        "exists": path.exists(),
        "duration": source.get("duration"),
        "width": source.get("width"),
        "height": source.get("height"),
        "fps": source.get("fps"),
    }


def copied_asset_name(prefix: str, path: Path) -> str:
    digest = hashlib.sha1(str(path).encode("utf-8", errors="ignore")).hexdigest()[:10]
    return f"{safe_stem(prefix)}_{digest}{path.suffix.lower()}"


def copy_public_asset(path: Path, asset_dir: Path, public_prefix: str, prefix: str) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False, "publicPath": ""}
    asset_dir.mkdir(parents=True, exist_ok=True)
    filename = copied_asset_name(prefix, path)
    target = asset_dir / filename
    if not target.exists() or target.stat().st_size != path.stat().st_size:
        try:
            shutil.copy2(path, target)
        except PermissionError:
            if not target.exists() or target.stat().st_size != path.stat().st_size:
                raise
    return {
        "path": str(path),
        "exists": True,
        "publicPath": f"{public_prefix}/{filename}".replace("\\", "/"),
        "copiedPath": str(target),
    }


def materialize_remotion_assets(manifest: dict[str, Any], stem: str) -> list[dict[str, Any]]:
    asset_dir = REMOTION_PUBLIC_ASSET_DIR / stem
    public_prefix = f"adapter-assets/{stem}"
    assets: list[dict[str, Any]] = []
    layers = manifest.get("layers") if isinstance(manifest.get("layers"), list) else []
    for layer_index, layer in enumerate(layers, start=1):
        if not isinstance(layer, dict):
            continue
        source = layer.get("source") if isinstance(layer.get("source"), dict) else {}
        if layer.get("layerKind") == "image" and source.get("path"):
            copied = copy_public_asset(Path(str(source["path"])), asset_dir, public_prefix, f"layer_{layer_index}")
            source.update({key: copied[key] for key in ("publicPath", "copiedPath") if copied.get(key)})
            assets.append({"layerId": layer.get("id"), "kind": "image", **copied})
        overlay_manifest = layer.get("overlayManifest") if isinstance(layer.get("overlayManifest"), dict) else {}
        items = overlay_manifest.get("items") if isinstance(overlay_manifest.get("items"), list) else []
        for item_index, item in enumerate(items, start=1):
            if not isinstance(item, dict) or not item.get("file"):
                continue
            copied = copy_public_asset(Path(str(item["file"])), asset_dir, public_prefix, f"{layer_index}_{item_index}")
            item.update({key: copied[key] for key in ("publicPath", "copiedPath") if copied.get(key)})
            assets.append({"layerId": layer.get("id"), "kind": "subtitle-image", **copied})
    return assets


def overlay_manifest_items(path: Path, render_start: float, render_end: float) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    items: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        start = seconds_from_timestamp(item.get("start"))
        end = seconds_from_timestamp(item.get("end"))
        visible_start = max(start, render_start)
        visible_end = min(end, render_end)
        if visible_end <= visible_start:
            continue
        file_path = resolve_path(str(item.get("file") or ""))
        items.append(
            {
                "start": start,
                "end": end,
                "visibleStart": visible_start,
                "visibleEnd": visible_end,
                "relativeStart": visible_start - render_start,
                "relativeEnd": visible_end - render_start,
                "file": str(file_path),
                "exists": file_path.exists(),
                "width": as_int(item.get("width"), 0),
                "height": as_int(item.get("height"), 0),
                "lines": item.get("lines") if isinstance(item.get("lines"), list) else [],
                "speakerRole": item.get("speaker_role") or item.get("speakerRole") or "",
            }
        )
    return items


def resolve_render_range(timeline: dict[str, Any], args: argparse.Namespace) -> tuple[float, float]:
    duration = as_float(timeline.get("duration"), 0.0)
    if args.range_start is not None or args.range_end is not None:
        start = as_float(args.range_start, 0.0)
        end = as_float(args.range_end, duration)
        return max(0.0, start), min(duration, end)
    if args.preview:
        render = timeline.get("render") if isinstance(timeline.get("render"), dict) else {}
        preview = render.get("preview") if isinstance(render.get("preview"), dict) else {}
        return max(0.0, as_float(preview.get("rangeStart"), 0.0)), min(duration, as_float(preview.get("rangeEnd"), duration))
    return 0.0, duration


def layer_kind(clip: dict[str, Any]) -> str:
    track_id = str(clip.get("trackId") or "")
    kind = str(clip.get("kind") or "")
    if track_id == "video.main":
        return "video-reference"
    if track_id in {"audio.main", "music.bed"}:
        return "audio-reference"
    if track_id == "subtitle.main" or kind == "subtitle":
        return "subtitle"
    if kind == "image":
        return "image"
    if kind == "generated":
        return "generated"
    return kind or "unknown"


def clip_layer(
    clip: dict[str, Any],
    sources: dict[str, dict[str, Any]],
    *,
    fps: float,
    render_start: float,
    render_end: float,
) -> dict[str, Any] | None:
    start = as_float(clip.get("timelineStart"))
    end = as_float(clip.get("timelineEnd"))
    visible_start = max(start, render_start)
    visible_end = min(end, render_end)
    if visible_end <= visible_start:
        return None
    relative_start = visible_start - render_start
    relative_end = visible_end - render_start
    source = sources.get(str(clip.get("sourceId") or ""))
    source_offset = visible_start - start
    source_in = as_float(clip.get("sourceIn"), 0.0) + source_offset if "sourceIn" in clip else None
    source_out = as_float(clip.get("sourceOut"), 0.0) + source_offset + (visible_end - visible_start) if "sourceOut" in clip else None
    layer: dict[str, Any] = {
        "id": clip.get("id"),
        "trackId": clip.get("trackId"),
        "kind": clip.get("kind"),
        "layerKind": layer_kind(clip),
        "timelineStart": start,
        "timelineEnd": end,
        "visibleStart": visible_start,
        "visibleEnd": visible_end,
        "relativeStart": relative_start,
        "relativeEnd": relative_end,
        "startFrame": frame_at(relative_start, fps),
        "endFrame": frame_at(relative_end, fps),
        "durationFrames": max(1, frame_at(relative_end, fps) - frame_at(relative_start, fps)),
        "source": source_ref(source),
        "position": clip.get("position") if isinstance(clip.get("position"), dict) else {},
        "fit": clip.get("fit") if isinstance(clip.get("fit"), dict) else {},
        "style": clip.get("style") if isinstance(clip.get("style"), dict) else {},
        "effects": clip.get("effects") if isinstance(clip.get("effects"), list) else [],
        "metadata": clip.get("metadata") if isinstance(clip.get("metadata"), dict) else {},
    }
    if source_in is not None:
        layer["sourceIn"] = source_in
    if source_out is not None:
        layer["sourceOut"] = source_out
    metadata = layer["metadata"] if isinstance(layer.get("metadata"), dict) else {}
    manifest_path = metadata.get("overlayManifestPath")
    if manifest_path and layer["layerKind"] == "subtitle":
        layer["overlayManifest"] = {
            "path": str(resolve_path(str(manifest_path))),
            "items": overlay_manifest_items(resolve_path(str(manifest_path)), render_start, render_end),
        }
    return layer


def target_payload(target: dict[str, Any], fps: str, fps_value: float, render_range: tuple[float, float]) -> dict[str, Any]:
    duration = max(0.0, render_range[1] - render_range[0])
    return {
        "id": target.get("id"),
        "path": target.get("path"),
        "format": target.get("format"),
        "width": as_int(target.get("width"), 1920),
        "height": as_int(target.get("height"), 1080),
        "fps": fps,
        "fpsNumber": fps_value,
        "profile": target.get("profile"),
        "range": {"start": render_range[0], "end": render_range[1], "duration": duration},
        "durationFrames": frame_at(duration, fps_value),
    }


def html_layers_manifest(
    adapter: str,
    timeline: dict[str, Any],
    timeline_path: Path,
    target: dict[str, Any],
    render_range: tuple[float, float],
) -> dict[str, Any]:
    fps_text = target_fps(timeline, target)
    fps_value = fps_number(fps_text)
    sources = source_by_id(timeline)
    layers = [
        layer
        for clip in timeline.get("clips", [])
        if isinstance(clip, dict) and str(clip.get("trackId") or "") in HTML_LAYER_TRACKS
        if not wants_blender(clip)
        for layer in [clip_layer(clip, sources, fps=fps_value, render_start=render_range[0], render_end=render_range[1])]
        if layer is not None
    ]
    return {
        "schemaVersion": f"video-edit-{adapter}-layers/v1",
        "createdAt": now_iso(),
        "adapter": adapter,
        "timelineId": timeline.get("id"),
        "timelinePath": str(timeline_path),
        "target": target_payload(target, fps_text, fps_value, render_range),
        "layers": layers,
        "transitions": timeline.get("transitions") if isinstance(timeline.get("transitions"), list) else [],
    }


def executable_status(executable: str) -> tuple[str, bool]:
    if not executable:
        return "", False
    path = Path(executable)
    if path.exists():
        return str(path), True
    found = shutil.which(executable)
    return found or executable, bool(found)


def range_stem_suffix(render_range: tuple[float, float], duration: float) -> str:
    return f"_range_{int(render_range[0] * 1000):08d}_{int(render_range[1] * 1000):08d}"


def default_layer_output_path(
    adapter: str,
    target: dict[str, Any],
    output_format: str = "video",
    render_range: tuple[float, float] | None = None,
    duration: float = 0.0,
) -> Path:
    target_path = Path(str(target.get("path") or "render.mp4"))
    stem = f"{target_path.stem}{range_stem_suffix(render_range, duration)}" if render_range is not None else target_path.stem
    if adapter == "remotion" and output_format == "png-sequence":
        return target_path.with_name(f"{stem}_remotion_layers")
    if adapter == "blender":
        return target_path.with_name(f"{stem}_blender_frames")
    return target_path.with_name(f"{stem}.{adapter}_layers.mov")


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def command_report_path(output_path: Path, adapter: str) -> Path:
    return COMMAND_DIR / f"{safe_stem(output_artifact_stem(output_path))}.{adapter}.json"


def write_command_report(report: dict[str, Any], output_path: Path, adapter: str) -> Path:
    path = command_report_path(output_path, adapter)
    report["commandReport"] = str(path)
    return write_json(path, report)


def build_html_adapter_report(
    adapter: str,
    timeline: dict[str, Any],
    timeline_path: Path,
    config: dict[str, Any],
    args: argparse.Namespace,
    validation_warnings: list[str],
) -> dict[str, Any]:
    target = first_target(timeline)
    render_range = resolve_render_range(timeline, args)
    output_format = str(args.output_format or text_value(config, "render", f"{adapter}OutputFormat", default="")).strip().lower()
    if adapter == "remotion":
        output_format = output_format if output_format in {"png-sequence", "video"} else "png-sequence"
    else:
        output_format = "video"
    configured_output = text_value(config, "render", f"{adapter}OutputPath", default="").strip()
    range_for_output_name = render_range if args.preview or args.range_start is not None or args.range_end is not None else None
    output_path = args.output or (
        Path(configured_output)
        if configured_output
        else default_layer_output_path(adapter, target, output_format, range_for_output_name, as_float(timeline.get("duration"), 0.0))
    )
    output_path = resolve_path(output_path)
    stem = safe_stem(output_artifact_stem(output_path))
    manifest_path = ARTIFACT_DIR / f"{stem}.{adapter}.layers.json"
    manifest = html_layers_manifest(adapter, timeline, timeline_path, target, render_range)
    manifest["outputPath"] = str(output_path)
    if adapter == "remotion":
        manifest["publicAssets"] = materialize_remotion_assets(manifest, stem)
    write_json(manifest_path, manifest)

    if adapter == "remotion":
        executable, executable_ready = executable_status(text_value(config, "tools", "npx", default="npx"))
        entry = resolve_path(text_value(config, "render", "remotionEntry", default="remotion/index.tsx"))
        composition = text_value(config, "render", "remotionComposition", default="VideoEditTimeline")
        packages = [
            text_value(config, "render", "remotionPackage", default="@remotion/cli"),
            text_value(config, "render", "remotionReactPackage", default="react"),
            text_value(config, "render", "remotionReactDomPackage", default="react-dom"),
        ]
        sequence = output_format == "png-sequence"
        image_sequence_pattern = text_value(config, "render", "remotionImageSequencePattern", default="frame-[frame].[ext]")
        argv = [
            executable,
            "--yes",
            *[item for package in packages for item in ("--package", package) if package],
            "remotion",
            "render",
            str(entry),
            composition,
            str(output_path),
            f"--props={manifest_path}",
            "--fps",
            str(manifest["target"]["fpsNumber"]),
            "--width",
            str(manifest["target"]["width"]),
            "--height",
            str(manifest["target"]["height"]),
            *(["--sequence", "--image-format", "png", "--image-sequence-pattern", image_sequence_pattern, "--muted"] if sequence else []),
        ]
        overlay_artifact = {
            "renderer": "remotion",
            "format": output_format,
            "path": str(output_path),
            "alpha": sequence,
            "width": manifest["target"]["width"],
            "height": manifest["target"]["height"],
            "fps": manifest["target"]["fps"],
            "fpsNumber": manifest["target"]["fpsNumber"],
            "range": manifest["target"]["range"],
            "durationFrames": manifest["target"]["durationFrames"],
            "sourceLayerIds": [
                str(layer.get("id"))
                for layer in manifest.get("layers", [])
                if isinstance(layer, dict) and layer.get("layerKind") not in {"video-reference", "audio-reference"}
            ],
        }
        if sequence:
            overlay_artifact.update(
                {
                    "imageFormat": "png",
                    "imageSequencePattern": image_sequence_pattern,
                    "ffmpegGlob": str(output_path / "*.png"),
                }
            )
        missing = []
        if not executable_ready:
            missing.append("npx executable")
        if not entry.exists():
            missing.append(f"Remotion entry file: {entry}")
        ready = not missing
        scope = {
            "implemented": [
                "bundled Remotion composition scaffold for overlay-layer rendering",
                "Remotion public-asset materialization for image and subtitle PNG layers",
                "Remotion PNG-sequence overlay artifact export with alpha",
                "FFmpeg composition handoff metadata through overlayArtifact",
                "React layer manifest for timeline video/audio references",
                "React layer manifest for subtitle, image, and generated overlay clips",
                "partial timeline-range layer export",
                "audited Remotion render argv export",
            ],
            "notImplemented": [
                "full source media playback inside Remotion; FFmpeg remains responsible for base media assembly",
                "single-file alpha video overlay artifact export",
            ],
        }
    else:
        executable, executable_ready = executable_status(text_value(config, "tools", "hyperframes", default="hyperframes"))
        argv = [
            executable,
            "render",
            "--timeline",
            str(manifest_path),
            "--output",
            str(output_path),
            "--fps",
            str(manifest["target"]["fps"]),
            "--width",
            str(manifest["target"]["width"]),
            "--height",
            str(manifest["target"]["height"]),
        ]
        overlay_artifact = {
            "renderer": "hyperframes",
            "format": output_format,
            "path": str(output_path),
            "alpha": False,
            "width": manifest["target"]["width"],
            "height": manifest["target"]["height"],
            "fps": manifest["target"]["fps"],
            "fpsNumber": manifest["target"]["fpsNumber"],
            "range": manifest["target"]["range"],
            "durationFrames": manifest["target"]["durationFrames"],
        }
        missing = [] if executable_ready else ["hyperframes executable"]
        ready = executable_ready
        scope = {
            "implemented": [
                "HTML layer manifest for timeline video/audio references",
                "HTML layer manifest for subtitle, image, and generated overlay clips",
                "partial timeline-range layer export",
                "audited HyperFrames render argv export",
            ],
            "notImplemented": [
                "bundled HyperFrames renderer project",
                "installed HyperFrames executable when not configured in tools.hyperframes",
            ],
        }

    return {
        "createdAt": now_iso(),
        "adapter": adapter,
        "timelineSchemaVersion": timeline.get("schemaVersion"),
        "timelineId": timeline.get("id"),
        "timelinePath": str(timeline_path),
        "outputPath": str(output_path),
        "layerManifest": str(manifest_path),
        "overlayArtifact": overlay_artifact,
        "argv": argv,
        "readyToExecute": ready,
        "missingDependencies": missing,
        "unsupportedClips": [],
        "validationWarnings": validation_warnings,
        "preview": {"range": {"start": render_range[0], "end": render_range[1]}, "proxy": bool(args.proxy)},
        "scope": scope,
    }


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


def blender_jobs_manifest(
    timeline: dict[str, Any],
    timeline_path: Path,
    target: dict[str, Any],
    render_range: tuple[float, float],
    output_dir: Path,
) -> dict[str, Any]:
    fps_text = target_fps(timeline, target)
    fps_value = fps_number(fps_text)
    sources = source_by_id(timeline)
    jobs = []
    for clip in timeline.get("clips", []):
        if not isinstance(clip, dict) or not wants_blender(clip):
            continue
        layer = clip_layer(clip, sources, fps=fps_value, render_start=render_range[0], render_end=render_range[1])
        if layer is None:
            continue
        jobs.append(
            {
                "id": f"blender_job_{len(jobs) + 1:04d}",
                "clipId": clip.get("id"),
                "layer": layer,
                "jobType": "generated-3d-layer",
            }
        )
    return {
        "schemaVersion": "video-edit-blender-jobs/v1",
        "createdAt": now_iso(),
        "adapter": "blender",
        "timelineId": timeline.get("id"),
        "timelinePath": str(timeline_path),
        "target": target_payload(target, fps_text, fps_value, render_range),
        "outputSequenceDir": str(output_dir),
        "jobs": jobs,
    }


def blender_script_text() -> str:
    return r'''from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy


def args_after_double_dash() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


def add_camera() -> None:
    bpy.ops.object.light_add(type="AREA", location=(0, -3, 4))
    bpy.context.object.data.energy = 450
    bpy.context.object.data.size = 5
    bpy.ops.object.camera_add(location=(0, -7, 2.2), rotation=(1.309, 0, 0))
    bpy.context.scene.camera = bpy.context.object


def add_text_job(job: dict, index: int) -> None:
    layer = job.get("layer") if isinstance(job.get("layer"), dict) else {}
    style = layer.get("style") if isinstance(layer.get("style"), dict) else {}
    text = str(style.get("text") or style.get("title") or layer.get("id") or job.get("clipId") or "")
    bpy.ops.object.text_add(location=(-2.8, 0, 0.2 + index * 0.18), rotation=(1.2, 0, 0))
    obj = bpy.context.object
    obj.name = str(job.get("id") or f"job_{index}")
    obj.data.body = text[:180]
    obj.data.align_x = "CENTER"
    obj.data.align_y = "CENTER"
    obj.data.size = float(style.get("fontSize") or 0.42) / 100.0
    obj.data.extrude = float(style.get("extrude") or 0.02)
    material = bpy.data.materials.new(f"{obj.name}_material")
    material.diffuse_color = (1.0, 1.0, 1.0, 1.0)
    obj.data.materials.append(material)
    start = int(layer.get("startFrame") or 0)
    end = max(start + 1, int(layer.get("endFrame") or start + 1))
    obj.hide_render = True
    obj.keyframe_insert(data_path="hide_render", frame=max(0, start - 1))
    obj.hide_render = False
    obj.keyframe_insert(data_path="hide_render", frame=start)
    obj.keyframe_insert(data_path="hide_render", frame=end)
    obj.hide_render = True
    obj.keyframe_insert(data_path="hide_render", frame=end + 1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(args_after_double_dash())
    payload = json.loads(Path(args.jobs).read_text(encoding="utf-8"))
    target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
    jobs = payload.get("jobs") if isinstance(payload.get("jobs"), list) else []
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    clear_scene()
    add_camera()
    scene = bpy.context.scene
    scene.frame_start = 0
    scene.frame_end = max(1, int(target.get("durationFrames") or 1))
    scene.render.resolution_x = int(target.get("width") or 1920)
    scene.render.resolution_y = int(target.get("height") or 1080)
    scene.render.fps = int(round(float(target.get("fpsNumber") or 30)))
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(output_dir / "frame_")
    for index, job in enumerate(jobs):
        if isinstance(job, dict):
            add_text_job(job, index)
    bpy.ops.render.render(animation=True)


if __name__ == "__main__":
    main()
'''


def build_blender_report(
    timeline: dict[str, Any],
    timeline_path: Path,
    config: dict[str, Any],
    args: argparse.Namespace,
    validation_warnings: list[str],
) -> dict[str, Any]:
    target = first_target(timeline)
    render_range = resolve_render_range(timeline, args)
    target_path = Path(str(target.get("path") or "render.mp4"))
    configured_output = text_value(config, "render", "blenderOutputDir", default="").strip()
    range_for_output_name = render_range if args.preview or args.range_start is not None or args.range_end is not None else None
    output_dir = args.output or (
        Path(configured_output)
        if configured_output
        else default_layer_output_path("blender", target, "png-sequence", range_for_output_name, as_float(timeline.get("duration"), 0.0))
    )
    output_dir = resolve_path(output_dir)
    stem = safe_stem(output_dir.name)
    jobs_path = ARTIFACT_DIR / f"{stem}.blender.jobs.json"
    script_path = ARTIFACT_DIR / f"{stem}.blender.py"
    jobs_manifest = blender_jobs_manifest(timeline, timeline_path, target, render_range, output_dir)
    write_json(jobs_path, jobs_manifest)
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(blender_script_text(), encoding="utf-8")

    executable, executable_ready = executable_status(text_value(config, "tools", "blender", default="blender"))
    has_jobs = bool(jobs_manifest["jobs"])
    argv = [
        executable,
        "--background",
        "--python",
        str(script_path),
        "--",
        "--jobs",
        str(jobs_path),
        "--output-dir",
        str(output_dir),
    ] if has_jobs else []
    missing = []
    if has_jobs and not executable_ready:
        missing.append("blender executable")
    overlay_artifact = {
        "renderer": "blender",
        "format": "png-sequence",
        "path": str(output_dir),
        "alpha": True,
        "width": jobs_manifest["target"]["width"],
        "height": jobs_manifest["target"]["height"],
        "fps": jobs_manifest["target"]["fps"],
        "fpsNumber": jobs_manifest["target"]["fpsNumber"],
        "range": jobs_manifest["target"]["range"],
        "durationFrames": jobs_manifest["target"]["durationFrames"],
        "sourceLayerIds": [
            str(job.get("clipId"))
            for job in jobs_manifest.get("jobs", [])
            if isinstance(job, dict) and job.get("clipId")
        ],
        "imageFormat": "png",
        "imageSequencePattern": "frame_[frame].[ext]",
        "ffmpegGlob": str(output_dir / "*.png"),
        "jobCount": len(jobs_manifest["jobs"]),
        "noOp": not has_jobs,
    }
    return {
        "createdAt": now_iso(),
        "adapter": "blender",
        "timelineSchemaVersion": timeline.get("schemaVersion"),
        "timelineId": timeline.get("id"),
        "timelinePath": str(timeline_path),
        "outputPath": str(output_dir),
        "jobsManifest": str(jobs_path),
        "script": str(script_path),
        "overlayArtifact": overlay_artifact,
        "jobCount": len(jobs_manifest["jobs"]),
        "argv": argv,
        "readyToExecute": has_jobs and not missing,
        "noOp": not has_jobs,
        "missingDependencies": missing,
        "unsupportedClips": [],
        "validationWarnings": validation_warnings,
        "preview": {"range": {"start": render_range[0], "end": render_range[1]}, "proxy": bool(args.proxy)},
        "scope": {
            "implemented": [
                "Blender job manifest for clips explicitly marked renderer=blender",
                "Blender Python script generation for transparent PNG 3D text layers",
                "Blender PNG-sequence overlay artifact export with alpha",
                "FFmpeg composition handoff metadata through overlayArtifact",
                "partial timeline-range job export",
                "audited Blender background argv export when jobs exist",
            ],
            "notImplemented": [
                "automatic selection of Blender for ordinary 2D overlay clips",
            ],
        },
    }


def execute_report(report: dict[str, Any], adapter: str) -> None:
    argv = report.get("argv") if isinstance(report.get("argv"), list) else []
    if not argv:
        report["executed"] = False
        report["returnCode"] = 0
        return
    if not report.get("readyToExecute"):
        report["executed"] = False
        report["returnCode"] = 1
        report["executionError"] = f"{adapter} command is not ready to execute: {report.get('missingDependencies')}"
        raise SystemExit(1)
    RENDER_LOG_DIR.mkdir(parents=True, exist_ok=True)
    output_path = Path(str(report.get("outputPath") or adapter))
    log_path = RENDER_LOG_DIR / f"{safe_stem(output_artifact_stem(output_path))}.{adapter}.log"
    report["renderLog"] = str(log_path)
    report["executionStartedAt"] = now_iso()
    try:
        with log_path.open("w", encoding="utf-8", errors="replace") as log_file:
            completed = subprocess.run([str(item) for item in argv], cwd=WORK, stdout=log_file, stderr=subprocess.STDOUT)
    except OSError as error:
        report["executed"] = False
        report["returnCode"] = 1
        report["executionEndedAt"] = now_iso()
        report["executionError"] = str(error)
        raise SystemExit(1)
    report["executed"] = True
    report["returnCode"] = completed.returncode
    report["executionEndedAt"] = now_iso()
    if completed.returncode:
        raise SystemExit(completed.returncode)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export non-FFmpeg renderer adapter artifacts from a validated timeline.")
    parser.add_argument("--adapter", choices=["remotion", "hyperframes", "blender"], required=True)
    parser.add_argument("--timeline", type=Path, default=None, help="Timeline JSON path. Defaults to render.timelinePath.")
    parser.add_argument("--output", type=Path, default=None, help="Override adapter layer/job output path.")
    parser.add_argument("--preview", action="store_true", help="Export the timeline preview range instead of the full target.")
    parser.add_argument("--range-start", type=float, default=None, help="Timeline start time for a partial adapter export.")
    parser.add_argument("--range-end", type=float, default=None, help="Timeline end time for a partial adapter export.")
    parser.add_argument("--proxy", action="store_true", help="Mark the adapter export as a low-resolution/proxy pass.")
    parser.add_argument("--output-format", choices=["png-sequence", "video"], default=None, help="Remotion overlay output format. Defaults to png-sequence.")
    parser.add_argument("--execute", action="store_true", help="Execute the generated command if dependencies are available.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    timeline_path = args.timeline or configured_timeline_path(APP_CONFIG)
    timeline = load_timeline(timeline_path)
    errors, warnings = validate_timeline(timeline)
    if errors:
        raise SystemExit(json.dumps({"valid": False, "errors": errors, "warnings": warnings}, ensure_ascii=False, indent=2))
    if args.adapter in {"remotion", "hyperframes"}:
        report = build_html_adapter_report(args.adapter, timeline, timeline_path, APP_CONFIG, args, warnings)
    else:
        report = build_blender_report(timeline, timeline_path, APP_CONFIG, args, warnings)
    exit_code = 0
    if args.execute:
        try:
            execute_report(report, args.adapter)
        except SystemExit as error:
            exit_code = int(error.code) if isinstance(error.code, int) else 1
            if "executed" not in report:
                report["executed"] = False
            if "returnCode" not in report:
                report["returnCode"] = exit_code
    else:
        report["executed"] = False
    output_path = Path(str(report.get("outputPath") or args.adapter))
    write_command_report(report, output_path, args.adapter)
    keys = [
        "adapter",
        "outputPath",
        "layerManifest",
        "jobsManifest",
        "script",
        "commandReport",
        "jobCount",
        "noOp",
        "readyToExecute",
        "missingDependencies",
        "executed",
        "returnCode",
        "executionError",
    ]
    print(json.dumps({key: report.get(key) for key in keys if key in report}, ensure_ascii=False, indent=2))
    if exit_code:
        raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
