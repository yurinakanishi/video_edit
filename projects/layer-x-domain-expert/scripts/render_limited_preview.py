from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parents[1]
REPORTS = PROJECT_ROOT / "output" / "reports"
VIDEOS = PROJECT_ROOT / "output" / "videos"
DIAGNOSTICS = PROJECT_ROOT / "output" / "diagnostics"
FFMPEG_DEFAULT = Path(r"C:\ProgramData\chocolatey\bin\ffmpeg.exe")
FONT_FILE = Path(r"C:\Windows\Fonts\YuGothB.ttc")
LOGO_PATH = PROJECT_ROOT / "source" / "assets" / "LayerX_Logo_Horizontal_RGB_Color.png"
TARGET_AUDIO_LUFS = -17.0
INTERVIEW_AUDIO_MEDIA_IDS = {"group_wide", "cam_person_01", "cam_person_02", "cam_person_03"}
INTERVIEW_MAIN_AUDIO_MEDIA_ID = "cam_person_02"


MEDIA_PATHS = {
    "group_wide": PROJECT_ROOT / "source" / "video" / "three people.mp4",
    "cam_person_01": PROJECT_ROOT / "source" / "video" / "person-left.mp4",
    "cam_person_02": PROJECT_ROOT / "source" / "video" / "person-middle.mp4",
    "cam_person_03": PROJECT_ROOT / "source" / "video" / "person-right.mp4",
    "company_movie": PROJECT_ROOT / "source" / "video" / "company-movie.mp4",
}

MEDIA_TO_ROLE = {
    "cam_person_01": "camera2",
    "cam_person_02": "camera3",
    "cam_person_03": "camera4",
    "group_wide": "master",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def ffmpeg_path() -> str:
    state_path = PROJECT_ROOT / "project_state.json"
    if state_path.exists():
        state = read_json(state_path)
        configured = str(((state.get("tools") or {}).get("ffmpeg")) or "").strip()
        if configured and Path(configured).exists():
            return configured
    if FFMPEG_DEFAULT.exists():
        return str(FFMPEG_DEFAULT)
    return "ffmpeg"


def app_offsets() -> dict[str, float]:
    path = REPORTS / "app_sync_offsets.json"
    if not path.exists():
        return {"master": 0.0}
    payload = read_json(path)
    offsets = payload.get("offsets") if isinstance(payload.get("offsets"), dict) else {}
    result = {"master": 0.0}
    for key, value in offsets.items():
        try:
            result[str(key)] = float(value)
        except (TypeError, ValueError):
            pass
    return result


def topic_titles() -> dict[str, str]:
    path = REPORTS / "semantic_marks.json"
    if not path.exists():
        return {}
    payload = read_json(path)
    result = {}
    for topic in payload.get("topics", []):
        if isinstance(topic, dict) and topic.get("topic_id") and topic.get("title"):
            result[str(topic["topic_id"])] = str(topic["title"])
    return result


def people_map() -> dict[str, dict[str, Any]]:
    path = REPORTS / "people_map.json"
    if not path.exists():
        return {}
    payload = read_json(path)
    return {
        str(person.get("person_id")): person
        for person in payload.get("people", [])
        if isinstance(person, dict) and person.get("person_id")
    }


def duration(event: dict[str, Any]) -> float:
    return max(0.01, float(event["timeline_end"]) - float(event["timeline_start"]))


def clip_source(event: dict[str, Any]) -> dict[str, Any]:
    source = event.get("source")
    if not isinstance(source, dict):
        raise ValueError(f"event {event.get('event_id')} has no source")
    return source


def audio_source(event: dict[str, Any]) -> dict[str, Any]:
    source = event.get("source") if isinstance(event.get("source"), dict) else {}
    reference = event.get("reference_source") if isinstance(event.get("reference_source"), dict) else {}
    if str(event.get("section") or "") == "bridge" or str(source.get("media_id") or "") == "company_movie":
        return source
    clock_source = reference if reference else source
    clock_media_id = str(clock_source.get("media_id") or source.get("media_id") or "group_wide")
    clock_in = float(clock_source.get("in") or source.get("in") or 0.0)
    offsets = app_offsets()
    source_role = MEDIA_TO_ROLE.get(clock_media_id, "master")
    target_role = MEDIA_TO_ROLE.get(INTERVIEW_MAIN_AUDIO_MEDIA_ID, "master")
    source_clock = clock_in - offsets.get(source_role, 0.0)
    audio_in = max(0.0, source_clock + offsets.get(target_role, 0.0))
    return {
        "media_id": INTERVIEW_MAIN_AUDIO_MEDIA_ID,
        "in": audio_in,
        "out": audio_in + duration(event),
        "policy": "single_interview_audio_source",
        "reference_media_id": clock_media_id,
    }


def segment_audio_filter_chain(media_id: str) -> str:
    if media_id not in INTERVIEW_AUDIO_MEDIA_IDS:
        return "aresample=48000"
    return (
        "highpass=f=85,"
        "lowpass=f=10500,"
        "afftdn=nr=18:nf=-32:tn=1:rf=-44,"
        "anlmdn=s=0.00035:p=0.002:r=0.006:m=11,"
        "acompressor=threshold=-30dB:ratio=2.4:attack=6:release=130:makeup=3,"
        "dynaudnorm=f=180:g=7:p=0.90:m=8,"
        "aresample=48000"
    )


def final_audio_filter_chain() -> str:
    loudnorm = f"loudnorm=I={TARGET_AUDIO_LUFS}:TP=-1.5:LRA=11"
    return (
        "highpass=f=70,"
        "lowpass=f=12000,"
        "afftdn=nr=10:nf=-38:tn=1:rf=-48,"
        "acompressor=threshold=-26dB:ratio=2.2:attack=5:release=140:makeup=2,"
        "dynaudnorm=f=180:g=7:p=0.90:m=8,"
        f"{loudnorm}"
    )


def ffmpeg_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace(",", "\\,")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("%", "\\%")
    )


def title_text(event: dict[str, Any]) -> str:
    titles = topic_titles()
    video_title = read_json(REPORTS / "video_title.json") if (REPORTS / "video_title.json").exists() else {}
    for overlay in event.get("overlays", []):
        if not isinstance(overlay, dict) or overlay.get("type") != "topic_title":
            continue
        if overlay.get("text"):
            return str(overlay["text"])
        topic_id = overlay.get("topic_id")
        if topic_id and str(topic_id) in titles:
            return titles[str(topic_id)]
    section = str(event.get("section") or "")
    if section == "digest":
        display = video_title.get("display") if isinstance(video_title.get("display"), dict) else {}
        return str(display.get("digest_top_right") or video_title.get("title") or "AI時代のドメインエキスパート論")
    return ""


def title_filter(event: dict[str, Any]) -> list[str]:
    if str(event.get("section") or "") == "bridge":
        return []
    text = title_text(event).strip()
    if not text:
        return []
    font = FONT_FILE.as_posix().replace(":", "\\:")
    return [
        "drawtext="
        f"fontfile='{font}':"
        f"text='{ffmpeg_text(text)}':"
        "x=w-text_w-34:"
        "y=24:"
        "fontsize=30:"
        "fontcolor=white:"
        "borderw=1:"
        "bordercolor=black@0.25:"
        "box=1:"
        "boxcolor=0x5F5AF5@0.94:"
        "boxborderw=13"
    ]


def nameplate_text(person_id: str) -> str:
    person = people_map().get(person_id, {})
    company = str(person.get("company") or "LayerX")
    role = str(person.get("role_title") or "TBD")
    name = str(person.get("display_name") or person_id)
    if name.startswith("Placeholder "):
        position = str(person.get("screen_position") or person_id).title()
        name = f"{position} Participant"
    if role == "TBD":
        return f"{company}  {name}"
    return f"{company} {role}  {name}"


def layout_people(event: dict[str, Any]) -> list[tuple[str, int, int, int, int, float, float]]:
    section = str(event.get("section") or "")
    if section != "main":
        return []
    layout = event.get("layout") if isinstance(event.get("layout"), dict) else {}
    layout_type = str(layout.get("type") or "")
    if layout_type == "split_grid":
        return []
    result = []
    for overlay in event.get("overlays", []):
        if not isinstance(overlay, dict):
            continue
        start = float(overlay.get("start") or 0.0)
        end = float(overlay.get("end") or duration(event))
        if overlay.get("type") == "lower_third_person" and overlay.get("person_id"):
            result.append((str(overlay["person_id"]), 74, 520, 1130, 42, start, end))
        elif overlay.get("type") == "lower_third_people" and layout_type != "split_grid":
            result.extend(
                [
                    ("person_01", 70, 500, 330, 22, start, end),
                    ("person_02", 475, 500, 330, 22, start, end),
                    ("person_03", 870, 500, 330, 22, start, end),
                ]
            )
    return result


def nameplate_filter_list(event: dict[str, Any]) -> list[str]:
    filters = []
    font = FONT_FILE.as_posix().replace(":", "\\:")
    for person_id, x, y, width, font_size, start, end in layout_people(event):
        text = ffmpeg_text(nameplate_text(person_id))
        filters.append(
            "drawtext="
            f"fontfile='{font}':"
            f"text='{text}':"
            f"x={x}:"
            f"y={y}:"
            f"fontsize={font_size}:"
            "fontcolor=white:"
            "borderw=2:"
            "bordercolor=black@0.45:"
            "box=1:"
            "boxcolor=0x5F5AF5@0.88:"
            "boxborderw=18:"
            f"enable='between(t\\,{start:.3f}\\,{end:.3f})'"
        )
    return filters


def caption_filter_list(event: dict[str, Any]) -> list[str]:
    filters = []
    for overlay in event.get("overlays", []):
        if not isinstance(overlay, dict) or overlay.get("type") != "caption":
            continue
        text = str(overlay.get("text") or "").strip()
        if not text:
            continue
        start = float(overlay.get("start") or 0.0)
        end = float(overlay.get("end") or duration(event))
        font = FONT_FILE.as_posix().replace(":", "\\:")
        filters.append(
            "drawtext="
            f"fontfile='{font}':"
            f"text='{ffmpeg_text(text)}':"
            "x=(w-text_w)/2:"
            "y=h-104:"
            "fontsize=38:"
            "fontcolor=white:"
            "borderw=2:"
            "bordercolor=black@0.65:"
            "box=1:"
            "boxcolor=0x5F5AF5@0.88:"
            "boxborderw=18:"
            f"enable='between(t\\,{start:.3f}\\,{end:.3f})'"
        )
    return filters


def overlay_chain(event: dict[str, Any]) -> str:
    filters = title_filter(event) + nameplate_filter_list(event) + caption_filter_list(event)
    return "," + ",".join(filters) if filters else ""


def brand_base_chain(event: dict[str, Any]) -> str:
    if str(event.get("section") or "") != "digest":
        return ""
    return (
        ",drawbox=x=0:y=0:w=1280:h=102:color=0x5F5AF5@1:t=fill"
        ",drawbox=x=0:y=700:w=1280:h=20:color=0x5F5AF5@1:t=fill"
        ",drawbox=x=0:y=0:w=286:h=102:color=white@1:t=fill"
    )


def logo_width(event: dict[str, Any]) -> int:
    return 173 if str(event.get("section") or "") == "digest" else 168


def logo_position(event: dict[str, Any]) -> tuple[int, int]:
    return (43, 31) if str(event.get("section") or "") == "digest" else (26, 22)


def base_video_filter(event: dict[str, Any]) -> str:
    section = str(event.get("section") or "")
    if section == "bridge":
        return "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1"
    return "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,setsar=1"


def split_divider_chain(event: dict[str, Any], media_count: int) -> str:
    layout = event.get("layout") if isinstance(event.get("layout"), dict) else {}
    color = "0xB7E6C1"
    divider = layout.get("divider") if isinstance(layout.get("divider"), dict) else {}
    if str(divider.get("color") or "").upper() == "#8EC6FF":
        color = "0x8EC6FF"
    if media_count == 2:
        return f",drawbox=x=638:y=0:w=4:h=720:color={color}@1:t=fill"
    if media_count == 3:
        return f",drawbox=x=424:y=0:w=4:h=720:color={color}@1:t=fill,drawbox=x=852:y=0:w=4:h=720:color={color}@1:t=fill"
    return ""


def synced_media_start(media_id: str, master_time: float, offsets: dict[str, float]) -> float:
    role = MEDIA_TO_ROLE.get(media_id, "master")
    return max(0.0, master_time + offsets.get(role, 0.0))


def split_media_ids(event: dict[str, Any]) -> list[str]:
    layout = event.get("layout") if isinstance(event.get("layout"), dict) else {}
    media_ids = layout.get("media_ids")
    if isinstance(media_ids, list):
        return [str(media_id) for media_id in media_ids if str(media_id) in MEDIA_PATHS]
    return []


def render_segment(ffmpeg: str, event: dict[str, Any], output: Path) -> None:
    layout = event.get("layout") if isinstance(event.get("layout"), dict) else {}
    if layout.get("type") == "split_grid" and split_media_ids(event):
        render_split_segment(ffmpeg, event, output)
        return
    src = clip_source(event)
    aud = audio_source(event)
    video_path = MEDIA_PATHS.get(str(src.get("media_id")))
    audio_path = MEDIA_PATHS.get(str(aud.get("media_id")))
    if video_path is None or not video_path.exists():
        raise FileNotFoundError(f"Video media not available for preview: {src.get('media_id')}")
    if audio_path is None or not audio_path.exists():
        raise FileNotFoundError(f"Audio media not available for preview: {aud.get('media_id')}")
    dur = duration(event)
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "warning",
        "-y",
        "-ss",
        f"{float(src.get('in') or 0.0):.3f}",
        "-t",
        f"{dur:.3f}",
        "-i",
        str(video_path),
        "-ss",
        f"{float(aud.get('in') or 0.0):.3f}",
        "-t",
        f"{dur:.3f}",
        "-i",
        str(audio_path),
        "-loop",
        "1",
        "-i",
        str(LOGO_PATH),
        "-filter_complex",
        f"[0:v]{base_video_filter(event)}{brand_base_chain(event)}[base];"
        f"[2:v]scale={logo_width(event)}:-1[logo];"
        f"[base][logo]overlay={logo_position(event)[0]}:{logo_position(event)[1]}{overlay_chain(event)}[vout];"
        f"[1:a]{segment_audio_filter_chain(str(aud.get('media_id') or ''))}[aout]",
        "-map",
        "[vout]",
        "-map",
        "[aout]",
        "-r",
        "30",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "28",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-ar",
        "48000",
        "-shortest",
        str(output),
    ]
    subprocess.run(command, cwd=WORKSPACE_ROOT, check=True)


def render_split_segment(ffmpeg: str, event: dict[str, Any], output: Path) -> None:
    aud = audio_source(event)
    audio_path = MEDIA_PATHS.get(str(aud.get("media_id")))
    if audio_path is None or not audio_path.exists():
        raise FileNotFoundError(f"Audio media not available for preview: {aud.get('media_id')}")
    media_ids = split_media_ids(event)
    dur = duration(event)
    master_in = float((event.get("reference_source") or {}).get("in") or (event.get("source") or {}).get("in") or 0.0)
    offsets = app_offsets()
    command = [ffmpeg, "-hide_banner", "-loglevel", "warning", "-y"]
    for media_id in media_ids:
        video_path = MEDIA_PATHS[media_id]
        command.extend(["-ss", f"{synced_media_start(media_id, master_in, offsets):.3f}", "-t", f"{dur:.3f}", "-i", str(video_path)])
    command.extend(["-ss", f"{float(aud.get('in') or master_in):.3f}", "-t", f"{dur:.3f}", "-i", str(audio_path)])
    command.extend(["-loop", "1", "-i", str(LOGO_PATH)])

    filters = []
    if len(media_ids) == 2:
        for index in range(2):
            filters.append(f"[{index}:v]scale=640:720:force_original_aspect_ratio=increase,crop=640:720,setsar=1[v{index}]")
        stack = "[v0][v1]hstack=inputs=2[base]"
    elif len(media_ids) == 3:
        for index in range(3):
            filters.append(f"[{index}:v]scale=426:720:force_original_aspect_ratio=increase,crop=426:720,setsar=1[v{index}]")
        stack = "[v0][v1][v2]hstack=inputs=3,pad=1280:720:1:0[base]"
    else:
        raise ValueError(f"Unsupported split media count: {len(media_ids)}")
    logo_index = len(media_ids) + 1
    filters.append(stack.replace("[base]", f"{split_divider_chain(event, len(media_ids))}[base]"))
    filters.append(f"[{logo_index}:v]scale={logo_width(event)}:-1[logo]")
    filters.append(f"[base][logo]overlay={logo_position(event)[0]}:{logo_position(event)[1]}{overlay_chain(event)}[vout]")
    filters.append(f"[{len(media_ids)}:a]{segment_audio_filter_chain(str(aud.get('media_id') or ''))}[aout]")
    command.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[vout]",
            "-map",
            "[aout]",
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "28",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ar",
            "48000",
            "-shortest",
            str(output),
        ]
    )
    subprocess.run(command, cwd=WORKSPACE_ROOT, check=True)


def concat_segments(ffmpeg: str, segments: list[Path], output: Path) -> None:
    list_path = DIAGNOSTICS / "limited_preview_concat.txt"
    temp_output = output.with_name(f"{output.stem}_audio_unprocessed{output.suffix}")
    list_path.parent.mkdir(parents=True, exist_ok=True)
    list_path.write_text("".join(f"file '{path.as_posix()}'\n" for path in segments), encoding="utf-8")
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "warning",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "28",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ar",
            "48000",
            str(temp_output),
        ],
        cwd=WORKSPACE_ROOT,
        check=True,
    )
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "warning",
            "-y",
            "-i",
            str(temp_output),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0",
            "-c:v",
            "copy",
            "-af",
            final_audio_filter_chain(),
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ar",
            "48000",
            str(output),
        ],
        cwd=WORKSPACE_ROOT,
        check=True,
    )
    try:
        temp_output.unlink()
    except OSError:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a lightweight limited preview from edit_plan.json.")
    parser.add_argument("--max-events", type=int, default=8, help="Limit preview length for fast review.")
    parser.add_argument("--output", type=Path, default=VIDEOS / "preview_limited.mp4")
    args = parser.parse_args()

    plan = read_json(REPORTS / "edit_plan.json")
    if not (plan.get("validation") or {}).get("ready_for_preview"):
        raise SystemExit("edit_plan.json is not marked ready_for_preview")
    events = [event for event in plan.get("timeline", []) if isinstance(event, dict)]
    if args.max_events:
        events = events[: args.max_events]
    if not events:
        raise SystemExit("No timeline events to render")

    segment_dir = VIDEOS / "preview_limited_segments"
    segment_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg = ffmpeg_path()
    rendered = []
    for index, event in enumerate(events, start=1):
        segment_path = segment_dir / f"segment_{index:03d}_{event.get('event_id', 'event')}.mp4"
        render_segment(ffmpeg, event, segment_path)
        rendered.append(segment_path)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    concat_segments(ffmpeg, rendered, args.output)
    print(json.dumps({"output": str(args.output), "segments": len(rendered)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
