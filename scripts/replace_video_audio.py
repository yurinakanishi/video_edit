from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from video_edit_core.paths import OUTPUT_REPORTS, ROOT as WORKSPACE_ROOT
from video_edit_core.audio.silence import DEFAULT_KEEP_SILENCE, DEFAULT_MIN_SILENCE, DEFAULT_NOISE, SilenceShortenConfig, shorten_silences
from video_edit_core.app_config import load_app_config, media_manifest, nested, optional_path


WORK = WORKSPACE_ROOT
APP_CONFIG = load_app_config()
FFMPEG = optional_path(APP_CONFIG, "tools", "ffmpeg", default=Path(r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"))
FFPROBE = optional_path(APP_CONFIG, "tools", "ffprobe", default=Path(r"C:\ProgramData\chocolatey\bin\ffprobe.exe"))
DEFAULT_SYNC = OUTPUT_REPORTS / "app_sync_offsets.json"
REPORT = OUTPUT_REPORTS / "audio_replacement.json"


def bool_value(*keys: str, default: bool = False) -> bool:
    value = nested(APP_CONFIG, *keys, default=default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return bool(value)


def text_value(*keys: str, default: str = "") -> str:
    value = nested(APP_CONFIG, *keys, default=default)
    return str(value) if value is not None else default


def path_value(*keys: str) -> Path | None:
    value = text_value(*keys).strip()
    return Path(value) if value else None


def manifest_external_audio() -> tuple[str, Path] | None:
    manifest = media_manifest(APP_CONFIG)
    files = manifest.get("files", []) if isinstance(manifest, dict) else []
    if not isinstance(files, list):
        return None
    for item in files:
        if not isinstance(item, dict) or item.get("kind") != "audio":
            continue
        role = str(item.get("role") or "external")
        path = Path(str(item.get("path") or ""))
        if role.startswith("external") and path.exists():
            return role, path
    return None


def selected_audio() -> tuple[str, Path]:
    configured = path_value("replaceAudio", "audioPath") or path_value("assets", "externalAudio")
    if configured and configured.exists():
        return "external", configured
    manifest_audio = manifest_external_audio()
    if manifest_audio:
        return manifest_audio
    raise SystemExit("Select an external audio file before replacing video audio.")


def selected_input_video() -> Path:
    configured = path_value("replaceAudio", "inputVideoPath") or path_value("workflow", "inputVideoPath")
    if configured and configured.exists():
        return configured
    raise SystemExit("workflow.inputVideoPath is required before replacing video audio.")


def selected_output_path(input_video: Path) -> Path:
    output = path_value("replaceAudio", "outputPath") or path_value("render", "outputPath")
    if not output:
        raise SystemExit("render.outputPath is required before replacing video audio.")
    try:
        if output.resolve() == input_video.resolve():
            raise SystemExit("Choose an output path different from the input video before replacing audio.")
    except OSError:
        pass
    return output


def probe_duration(input_path: Path) -> float:
    completed = subprocess.run(
        [
            str(FFPROBE),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(input_path),
        ],
        cwd=WORK,
        check=True,
        text=True,
        capture_output=True,
    )
    return float(completed.stdout.strip())


def paths_match(left: Any, right: Path) -> bool:
    if not left:
        return False
    try:
        return Path(str(left)).resolve() == right.resolve()
    except OSError:
        return str(left).lower() == str(right).lower()


def sync_offset_for(role: str, audio_path: Path) -> tuple[float, dict[str, Any]]:
    sync_path = path_value("replaceAudio", "syncOffsetsPath") or path_value("render", "syncOffsetsPath") or DEFAULT_SYNC
    details: dict[str, Any] = {"path": str(sync_path), "role": role, "source": "default", "offsetSeconds": 0.0}
    if not sync_path.exists():
        details["reason"] = "sync report missing"
        return 0.0, details
    try:
        payload = json.loads(sync_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        details["reason"] = f"sync report unreadable: {error}"
        return 0.0, details
    offsets = payload.get("offsets", {}) if isinstance(payload, dict) else {}
    if not isinstance(offsets, dict):
        details["reason"] = "sync report has no offsets object"
        return 0.0, details
    candidates = []
    role_item = offsets.get(role)
    if isinstance(role_item, dict):
        candidates.append(role_item)
    candidates.extend(item for item in offsets.values() if isinstance(item, dict) and paths_match(item.get("path"), audio_path))
    for item in candidates:
        try:
            offset = float(item.get("offsetSeconds", 0.0))
        except (TypeError, ValueError):
            continue
        details.update({"source": "waveform", "offsetSeconds": offset, "score": item.get("score"), "matchedPath": item.get("path")})
        return offset, details
    details["reason"] = "selected audio was not found in sync report"
    return 0.0, details


def replacement_audio_filter(offset: float, duration: float) -> str:
    if offset >= 0:
        return f"[1:a]atrim=start={offset:.6f},asetpts=PTS-STARTPTS,apad,atrim=start=0:duration={duration:.6f}[a]"
    delay_ms = round(abs(offset) * 1000)
    return f"[1:a]atrim=start=0,asetpts=PTS-STARTPTS,adelay={delay_ms}:all=1,apad,atrim=start=0:duration={duration:.6f}[a]"


def replace_audio(input_video: Path, audio_path: Path, output_path: Path, offset: float, duration: float) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            str(FFMPEG),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(input_video),
            "-i",
            str(audio_path),
            "-filter_complex",
            replacement_audio_filter(offset, duration),
            "-map",
            "0:v:0",
            "-map",
            "[a]",
            "-map_metadata",
            "0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-ac",
            "2",
            str(output_path),
        ],
        cwd=WORK,
        check=True,
    )


def main() -> None:
    input_video = selected_input_video()
    role, audio = selected_audio()
    output = selected_output_path(input_video)
    duration = probe_duration(input_video)
    offset, sync_details = sync_offset_for(role, audio)

    render_output = output
    if bool_value("render", "shortenSilence", default=False):
        render_output = output.with_name(f"{output.stem}_audio_replaced_uncut{output.suffix}")

    replace_audio(input_video, audio, render_output, offset, duration)
    silence_report = None
    if render_output != output:
        silence_report = shorten_silences(
            render_output,
            output,
            SilenceShortenConfig(
                min_silence=float(nested(APP_CONFIG, "render", "minSilence", default=DEFAULT_MIN_SILENCE)),
                keep_silence=float(nested(APP_CONFIG, "render", "keepSilence", default=DEFAULT_KEEP_SILENCE)),
                noise=str(nested(APP_CONFIG, "render", "silenceNoise", default=DEFAULT_NOISE)),
            ),
        )
        if not bool_value("render", "keepUncut", default=False):
            render_output.unlink(missing_ok=True)

    payload = {
        "input": str(input_video),
        "audio": str(audio),
        "audioRole": role,
        "output": str(output),
        "sourceDuration": duration,
        "sync": sync_details,
        "silence_shortening": silence_report,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "report": str(REPORT), **payload}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
