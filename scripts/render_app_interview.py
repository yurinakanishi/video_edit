from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from project_paths import (
    CONFIG,
    OUTPUT_DIAGNOSTICS,
    OUTPUT_OVERLAYS,
    OUTPUT_REPORTS,
    OUTPUT_TRANSCRIPTS,
    OUTPUT_VIDEOS,
    ROOT as WORKSPACE_ROOT,
    SCRIPTS,
    SOURCE_AUDIO,
    SOURCE_IMAGES,
    SOURCE_SUBTITLES,
    SOURCE_VIDEO,
    multicam_source_root,
    resolve_project_path,
)

from shorten_silences import DEFAULT_KEEP_SILENCE, DEFAULT_MIN_SILENCE, DEFAULT_NOISE, SilenceShortenConfig, shorten_silences
from video_edit_app_config import int_value, load_app_config, nested, optional_path
from composition_rules import crop_window_center_for_subject, subject_target_for_face, visible_ratio_for_area


WORK = WORKSPACE_ROOT
APP_CONFIG = load_app_config()
FFMPEG = optional_path(APP_CONFIG, "tools", "ffmpeg", default=Path(r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"))
TITLE = OUTPUT_OVERLAYS / "ai_engineer_now_title.png"
DEFAULT_LOGO = SOURCE_IMAGES / "type-logo-transparent-cropped.png"
DEFAULT_SYNC = OUTPUT_REPORTS / "app_sync_offsets.json"
DEFAULT_DENOISE_STRENGTH = 10
DEFAULT_REFERENCE_PROFILE = OUTPUT_REPORTS / "reference_edit_profile.json"


def seconds(timestamp: str) -> float:
    hours, minutes, rest = timestamp.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(rest)


def path_value(*keys: str) -> Path | None:
    value = nested(APP_CONFIG, *keys, default="")
    return Path(value) if value else None


def bool_value(*keys: str, default: bool = False) -> bool:
    value = nested(APP_CONFIG, *keys, default=default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return bool(value)


def audio_cleanup_filter(strength: int) -> str:
    nr = max(0, min(30, int(strength)))
    if nr <= 0:
        return "highpass=f=80"
    return f"highpass=f=80,afftdn=nr={nr}:nf=-35"


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def load_reference_profile() -> dict[str, object]:
    if not path_value("assets", "referenceVideo"):
        return {}
    path = Path(nested(APP_CONFIG, "analysis", "referenceEditProfilePath", default=str(DEFAULT_REFERENCE_PROFILE)))
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def reference_video_filter(profile: dict[str, object]) -> str:
    target = profile.get("target") if isinstance(profile.get("target"), dict) else {}
    center = target.get("person_center_ratio") if isinstance(target.get("person_center_ratio"), list) else None
    area = target.get("person_area_ratio")
    face_direction = str(target.get("dominant_face_direction") or "unknown")
    desired_subject_x = target.get("desired_subject_x_ratio")
    desired_subject_y = target.get("desired_subject_y_ratio")
    visual = target.get("visual_style") if isinstance(target.get("visual_style"), dict) else {}

    center_x = clamp(float(center[0]), 0.2, 0.8) if center and center[0] is not None else 0.5
    center_y = clamp(float(center[1]), 0.25, 0.75) if center and center[1] is not None else 0.5
    area_ratio = float(area) if area is not None else 0.0
    visible_ratio = visible_ratio_for_area(area_ratio)

    if desired_subject_x is None:
        desired_subject_x = subject_target_for_face(face_direction).x
    if desired_subject_y is None:
        desired_subject_y = subject_target_for_face(face_direction).y
    desired_subject_x = clamp(float(desired_subject_x), 0.35, 0.65)
    desired_subject_y = clamp(float(desired_subject_y), 0.30, 0.52)
    center_x = crop_window_center_for_subject(center_x, desired_subject_x, visible_ratio)
    center_y = crop_window_center_for_subject(center_y, desired_subject_y, visible_ratio)

    brightness = visual.get("brightness")
    contrast = visual.get("contrast")
    saturation = visual.get("saturation")
    brightness_adj = clamp((float(brightness) - 0.48) * 0.22, -0.08, 0.08) if brightness is not None else 0.0
    contrast_adj = clamp(0.88 + float(contrast) * 1.15, 0.88, 1.24) if contrast is not None else 1.0
    saturation_adj = clamp(0.78 + float(saturation) * 1.15, 0.78, 1.34) if saturation is not None else 1.0

    scale_w = round(1920 / visible_ratio / 2) * 2
    scale_h = round(1080 / visible_ratio / 2) * 2
    crop_x = f"min(max(iw*{center_x:.4f}-960\\,0)\\,iw-1920)"
    crop_y = f"min(max(ih*{center_y:.4f}-540\\,0)\\,ih-1080)"
    return (
        f"scale={scale_w}:{scale_h},crop=1920:1080:x='{crop_x}':y='{crop_y}',"
        f"eq=brightness={brightness_adj:.4f}:contrast={contrast_adj:.4f}:saturation={saturation_adj:.4f}"
    )


def run(command: list[str]) -> None:
    subprocess.run(command, check=True, cwd=WORK)


def load_sync_offsets(sources: list[tuple[str, Path]]) -> dict[str, float]:
    sync_path = Path(nested(APP_CONFIG, "render", "syncOffsetsPath", default=str(DEFAULT_SYNC)))
    offsets = {"master": 0.0, "right": 0.0, "left": 0.0, "external": 0.0}
    if not sync_path.exists():
        return offsets
    data = json.loads(sync_path.read_text(encoding="utf-8")).get("offsets", {})
    for role, path in sources:
        item = data.get(role)
        if item and Path(item.get("path", "")) == path:
            offsets[role] = float(item.get("offsetSeconds", 0.0))
    return offsets


def build_segments(duration: float, cameras: list[tuple[str, int]]) -> list[tuple[str, int, float, float]]:
    if not cameras:
        raise RuntimeError("At least one camera input is required.")
    mode = nested(APP_CONFIG, "render", "multicamMode", default="master-first")
    if mode == "master-first" or len(cameras) == 1:
        if len(cameras) == 1:
            return [(cameras[0][0], cameras[0][1], 0.0, duration)]
        segments = [(cameras[0][0], cameras[0][1], 0.0, min(8.0, duration))]
        t = 8.0
        closeups = cameras[1:] or cameras[:1]
        index = 0
        while t < duration:
            end = min(duration, t + 12.0)
            role, input_index = closeups[index % len(closeups)]
            segments.append((role, input_index, t, end))
            t = end
            index += 1
        return segments

    # For speaker-aware/manual requests without transcript data, use deterministic
    # close-up rotation and keep the master as fallback.
    order = cameras[1:] + cameras[:1] if len(cameras) > 1 else cameras
    segments = []
    t = 0.0
    index = 0
    while t < duration:
        end = min(duration, t + 15.0)
        role, input_index = order[index % len(order)]
        segments.append((role, input_index, t, end))
        t = end
        index += 1
    return segments


def subtitle_mode() -> str:
    mode = nested(APP_CONFIG, "render", "subtitleMode", default="none")
    return mode if mode in {"full", "punchline"} else "none"


def subtitle_manifest(mode: str) -> tuple[Path, dict[str, object]]:
    modes = {
        "full": {
            "generator": SCRIPTS / "generate_full_transcript_png_overlays.py",
            "manifest": OUTPUT_OVERLAYS / "full_transcript_png_overlays" / "manifest.json",
            "bottom_margin": 16,
            "slide_px": 0,
            "pop": False,
            "animate": False,
        },
        "punchline": {
            "generator": SCRIPTS / "generate_punchline_png_overlays.py",
            "manifest": OUTPUT_OVERLAYS / "punchline_png_overlays" / "manifest.json",
            "bottom_margin": 12,
            "slide_px": 44,
            "pop": True,
            "animate": True,
        },
    }
    config = modes[mode]
    run([sys.executable, str(SCRIPTS / "generate_title_png_overlay.py")])
    if mode == "full":
        run([sys.executable, str(SCRIPTS / "apply_st7_7550_subtitle_corrections.py")])
    run([sys.executable, str(config["generator"])])
    return Path(config["manifest"]), config


def main() -> None:
    master = path_value("assets", "masterVideo")
    right = path_value("assets", "rightCloseVideo")
    left = path_value("assets", "leftCloseVideo")
    external_audio = path_value("assets", "externalAudio")
    logo = optional_path(APP_CONFIG, "assets", "logo", default=DEFAULT_LOGO)
    output = Path(nested(APP_CONFIG, "render", "outputPath", default=OUTPUT_VIDEOS / "app_interview_output.mp4"))
    start = float(nested(APP_CONFIG, "render", "previewStart", default=0.0) or 0.0)
    duration = float(nested(APP_CONFIG, "render", "previewDuration", default=60.0) or 60.0)
    logo_height = int_value(APP_CONFIG, "style", "logoHeight", default=48)
    audio_denoise = bool_value("render", "audioDenoise", default=True)
    audio_denoise_strength = int_value(APP_CONFIG, "render", "audioDenoiseStrength", default=DEFAULT_DENOISE_STRENGTH)
    output.parent.mkdir(parents=True, exist_ok=True)
    reference_profile = load_reference_profile()
    reference_filter = reference_video_filter(reference_profile) if reference_profile else "scale=1920:1080"

    cameras: list[tuple[str, Path]] = []
    if master:
        cameras.append(("master", master))
    if right:
        cameras.append(("right", right))
    if left:
        cameras.append(("left", left))
    if not cameras:
        raise RuntimeError("Drop or select at least a master video before running render_app_interview.py.")
    sync_sources = cameras + ([("external", external_audio)] if external_audio else [])
    sync_offsets = load_sync_offsets(sync_sources)
    run([sys.executable, str(SCRIPTS / "generate_title_png_overlay.py")])

    mode = subtitle_mode()
    captions = []
    caption_config: dict[str, object] = {}
    if mode != "none":
        manifest, caption_config = subtitle_manifest(mode)
        captions = [
            item
            for item in json.loads(manifest.read_text(encoding="utf-8"))
            if seconds(item["start"]) < start + duration and seconds(item["end"]) > start
        ]

    audio_source = nested(APP_CONFIG, "render", "audioSource", default="external-if-selected")
    audio_input_index = 0
    if audio_source == "rightCloseVideo" and right:
        audio_input_index = next((i for i, (name, _) in enumerate(cameras) if name == "right"), 0)
    elif audio_source == "leftCloseVideo" and left:
        audio_input_index = next((i for i, (name, _) in enumerate(cameras) if name == "left"), 0)
    elif audio_source == "external-if-selected" and external_audio:
        audio_input_index = len(cameras) + 2 + len(captions)

    camera_indexes = [(name, index) for index, (name, _) in enumerate(cameras)]
    timeline_segments = build_segments(duration, camera_indexes)
    source_ranges: dict[int, list[float]] = {}
    for role, input_index, seg_start, seg_end in timeline_segments:
        source_start = max(0.0, sync_offsets.get(role, 0.0) + start + seg_start)
        source_end = max(source_start, sync_offsets.get(role, 0.0) + start + seg_end)
        current_range = source_ranges.setdefault(input_index, [source_start, source_end])
        current_range[0] = min(current_range[0], source_start)
        current_range[1] = max(current_range[1], source_end)

    if audio_input_index < len(cameras):
        audio_role = cameras[audio_input_index][0]
        audio_start = max(0.0, sync_offsets.get(audio_role, 0.0) + start)
        audio_end = audio_start + duration
        current_range = source_ranges.setdefault(audio_input_index, [audio_start, audio_end])
        current_range[0] = min(current_range[0], audio_start)
        current_range[1] = max(current_range[1], audio_end)

    input_seek: dict[int, float] = {}
    command = [str(FFMPEG), "-hide_banner", "-y"]
    for index, (_, camera_path) in enumerate(cameras):
        range_start, range_end = source_ranges.get(index, [start, start + duration])
        input_seek[index] = range_start
        command.extend(["-ss", f"{range_start:.6f}", "-t", f"{max(0.1, range_end - range_start):.6f}", "-i", str(camera_path)])

    logo_index = len(cameras)
    command.extend(["-i", str(logo)])
    title_index = len(cameras) + 1
    command.extend(["-i", str(TITLE)])
    for item in captions:
        command.extend(["-loop", "1", "-framerate", "60", "-t", f"{duration:.3f}", "-i", str(WORK / item["file"])])
    if audio_source == "external-if-selected" and external_audio:
        external_audio_start = max(0.0, sync_offsets.get("external", 0.0) + start)
        command.extend(["-ss", f"{external_audio_start:.6f}", "-t", f"{duration:.6f}", "-i", str(external_audio)])

    filters: list[str] = []
    segment_labels: list[str] = []
    for segment_index, (role, input_index, seg_start, seg_end) in enumerate(timeline_segments):
        label = f"seg{segment_index}"
        source_start = max(0.0, sync_offsets.get(role, 0.0) + start + seg_start)
        source_end = max(source_start, sync_offsets.get(role, 0.0) + start + seg_end)
        local_start = max(0.0, source_start - input_seek.get(input_index, 0.0))
        local_end = max(local_start, source_end - input_seek.get(input_index, 0.0))
        filters.append(
            f"[{input_index}:v]setpts=PTS-STARTPTS,trim=start={local_start:.6f}:end={local_end:.6f},"
            f"setpts=PTS-STARTPTS,{reference_filter}[{label}]"
        )
        segment_labels.append(label)

    if len(segment_labels) == 1:
        filters.append(f"[{segment_labels[0]}]copy[vbase]")
    else:
        filters.append("".join(f"[{label}]" for label in segment_labels) + f"concat=n={len(segment_labels)}:v=1:a=0[vbase]")

    filters.extend(
        [
            f"[{logo_index}:v]scale=-1:{logo_height}[logo]",
            "[vbase][logo]overlay=W-w-40:40[vlogo]",
            f"[vlogo][{title_index}:v]overlay=42:42[vtitle]",
        ]
    )

    current = "vtitle"
    first_caption_index = len(cameras) + 2
    for index, item in enumerate(captions, start=1):
        stream_index = first_caption_index + index - 1
        start_t = max(0.0, seconds(item["start"]) - start)
        end_t = min(duration, seconds(item["end"]) - start)
        fade_out = max(start_t, end_t - 0.18)
        base_scale = "if(gt(iw,1760),1760/iw,1)"
        if caption_config.get("pop"):
            pop_scale = f"if(between(t,{start_t:.3f},{start_t + 0.22:.3f}),0.88+0.12*(t-{start_t:.3f})/0.22,1)"
        else:
            pop_scale = "1"
        if caption_config.get("animate"):
            y_expr = (
                f"H-h-{caption_config['bottom_margin']}+"
                f"if(between(t,{start_t:.3f},{start_t + 0.26:.3f}),"
                f"{caption_config['slide_px']}*(1-(t-{start_t:.3f})/0.26),0)"
            )
            filters.append(
                f"[{stream_index}:v]format=rgba,"
                f"fade=t=in:st={start_t:.3f}:d=0.16:alpha=1,"
                f"fade=t=out:st={fade_out:.3f}:d=0.18:alpha=1,"
                f"scale=w='iw*{base_scale}*{pop_scale}':h='ih*{base_scale}*{pop_scale}':eval=frame[p{index}]"
            )
        else:
            y_expr = f"H-h-{caption_config['bottom_margin']}"
            filters.append(f"[{stream_index}:v]format=rgba,scale=w='iw*{base_scale}':h='ih*{base_scale}':eval=init[p{index}]")
        next_label = f"vsub{index}"
        filters.append(f"[{current}][p{index}]overlay=x='(W-w)/2':y='{y_expr}':enable='between(t,{start_t:.3f},{end_t:.3f})'[{next_label}]")
        current = next_label

    audio_role = cameras[audio_input_index][0] if audio_input_index < len(cameras) else "external"
    audio_start = max(0.0, sync_offsets.get(audio_role, 0.0) + start)
    audio_local_start = 0.0 if audio_role == "external" else max(0.0, audio_start - input_seek.get(audio_input_index, 0.0))
    audio_filters = f"atrim=start={audio_local_start:.6f}:duration={duration:.6f},asetpts=PTS-STARTPTS"
    if audio_denoise:
        audio_filters += f",{audio_cleanup_filter(audio_denoise_strength)}"
    filters.append(f"[{audio_input_index}:a]{audio_filters}[a]")

    render_output = output
    if nested(APP_CONFIG, "render", "shortenSilence", default=True):
        render_output = output.with_name(f"{output.stem}_uncut{output.suffix}")

    command.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            f"[{current}]",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            str(render_output),
        ]
    )
    run(command)

    if nested(APP_CONFIG, "render", "shortenSilence", default=True):
        report = shorten_silences(
            render_output,
            output,
            SilenceShortenConfig(
                min_silence=float(nested(APP_CONFIG, "render", "minSilence", default=DEFAULT_MIN_SILENCE)),
                keep_silence=float(nested(APP_CONFIG, "render", "keepSilence", default=DEFAULT_KEEP_SILENCE)),
                noise=str(nested(APP_CONFIG, "render", "silenceNoise", default=DEFAULT_NOISE)),
            ),
        )
        if not nested(APP_CONFIG, "render", "keepUncut", default=False):
            render_output.unlink(missing_ok=True)
        print(json.dumps({"output": str(output), "audio_denoise": audio_denoise, "silence_shortening": report}, ensure_ascii=False, indent=2))
    else:
        print(json.dumps({"output": str(output), "audio_denoise": audio_denoise}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
