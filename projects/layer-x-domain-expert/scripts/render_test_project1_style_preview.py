from __future__ import annotations

import argparse
import json
import math
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parents[1]
REPORTS = PROJECT_ROOT / "output" / "reports"
VIDEOS = PROJECT_ROOT / "output" / "videos"
OVERLAYS = PROJECT_ROOT / "output" / "overlays" / "test_project1_style"
DIAGNOSTICS = PROJECT_ROOT / "output" / "diagnostics"
FFMPEG_DEFAULT = Path(r"C:\ProgramData\chocolatey\bin\ffmpeg.exe")
FONT_FILE = Path(r"C:\Windows\Fonts\YuGothB.ttc")
LOGO_PATH = PROJECT_ROOT / "source" / "assets" / "LayerX_Logo_Horizontal_RGB_Color.png"

WIDTH = 1280
HEIGHT = 720
FPS = 30

PURPLE_DARK = "#4D15D7"
PURPLE_MID = "#5A2DEF"
PURPLE_LIGHT = "#7863F3"
TOP_STOPS = ["#5A51FE", "#5A51FD", "#5D60FE"]
BOTTOM_STOPS = ["#5B59FD", "#656AFD", "#747FFC"]
TITLE_STOPS = ["#4D15D7", "#5A2DEF", "#7863F3"]
DIVIDER_COLOR = "0x58B9FF"

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


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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
    result = {"master": 0.0}
    for key, value in (payload.get("offsets") or {}).items():
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
    return {
        str(topic["topic_id"]): str(topic["title"])
        for topic in payload.get("topics", [])
        if isinstance(topic, dict) and topic.get("topic_id") and topic.get("title")
    }


def people_map() -> dict[str, dict[str, Any]]:
    path = REPORTS / "people_map.json"
    if not path.exists():
        return {}
    payload = read_json(path)
    return {
        str(person["person_id"]): person
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
    reference = event.get("reference_source")
    if isinstance(reference, dict):
        return reference
    return clip_source(event)


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    text = value.lstrip("#")
    return int(text[:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def gradient_image(size: tuple[int, int], stops: list[str], alpha: int = 255) -> Image.Image:
    width, height = size
    colors = [hex_to_rgb(stop) for stop in stops]
    image = Image.new("RGBA", (max(1, width), max(1, height)), (0, 0, 0, 0))
    pixels = image.load()
    for x in range(max(1, width)):
        t = 0.0 if width <= 1 else x / (width - 1)
        segment = min(len(colors) - 2, int(t * (len(colors) - 1)))
        local_start = segment / (len(colors) - 1)
        local_end = (segment + 1) / (len(colors) - 1)
        local_t = 0.0 if local_end == local_start else (t - local_start) / (local_end - local_start)
        c0 = colors[segment]
        c1 = colors[segment + 1]
        color = tuple(round(c0[i] + (c1[i] - c0[i]) * local_t) for i in range(3)) + (alpha,)
        for y in range(max(1, height)):
            pixels[x, y] = color
    return image


def rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return mask


def paste_gradient_box(canvas: Image.Image, box: tuple[int, int, int, int], stops: list[str], radius: int, alpha: int = 255, shadow: bool = True) -> None:
    x0, y0, x1, y1 = box
    width = max(1, x1 - x0)
    height = max(1, y1 - y0)
    mask = rounded_mask((width, height), radius)
    if shadow:
        shadow_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        shadow_rect = Image.new("RGBA", (width, height), (0, 0, 0, 48))
        shadow_layer.paste(shadow_rect, (x0, y0 + 4), mask)
        canvas.alpha_composite(shadow_layer.filter(ImageFilter.GaussianBlur(7)))
    rect = gradient_image((width, height), stops, alpha)
    canvas.paste(rect, (x0, y0), mask)


def paste_slanted_gradient(canvas: Image.Image, polygon: list[tuple[int, int]], stops: list[str], alpha: int = 255) -> None:
    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    mask = Image.new("L", (x1 - x0, y1 - y0), 0)
    local = [(x - x0, y - y0) for x, y in polygon]
    ImageDraw.Draw(mask).polygon(local, fill=255)
    rect = gradient_image((x1 - x0, y1 - y0), stops, alpha)
    canvas.paste(rect, (x0, y0), mask)


def fit_font(text: str, max_width: int, size: int, min_size: int) -> ImageFont.FreeTypeFont:
    probe = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    draw = ImageDraw.Draw(probe)
    for font_size in range(size, min_size - 1, -2):
        font = ImageFont.truetype(str(FONT_FILE), font_size)
        bbox = draw.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= max_width:
            return font
    return ImageFont.truetype(str(FONT_FILE), min_size)


def wrap_caption_text(text: str, max_chars: int = 18) -> list[str]:
    text = " ".join(str(text).split())
    if len(text) <= max_chars:
        return [text]
    break_chars = "、。！？ "
    best = -1
    for char in break_chars:
        best = max(best, text.rfind(char, 0, max_chars + 1))
    if best >= 7:
        return [text[:best].strip(" 、。！？"), text[best + 1 :].strip()][:2]
    return [text[:max_chars].strip(), text[max_chars:].strip()][:2]


def draw_gradient_text(layer: Image.Image, position: tuple[int, int], text: str, font: ImageFont.FreeTypeFont, fill: str) -> None:
    ImageDraw.Draw(layer).text(position, text, font=font, fill=fill)


def ease_out_cubic(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return 1.0 - (1.0 - value) ** 3


def title_text(event: dict[str, Any]) -> str:
    titles = topic_titles()
    semantic = read_json(REPORTS / "semantic_marks.json") if (REPORTS / "semantic_marks.json").exists() else {}
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
        return "Domain Expert Digest"
    if section == "main":
        ref = event.get("reference_source") if isinstance(event.get("reference_source"), dict) else {}
        ref_time = float(ref.get("in") or 0.0)
        for topic in semantic.get("topics", []):
            if float(topic.get("start") or 0.0) <= ref_time < float(topic.get("end") or 0.0):
                return str(topic.get("title") or "")
        topics = semantic.get("topics") if isinstance(semantic.get("topics"), list) else []
        if topics:
            return str(topics[0].get("title") or "")
    return ""


def draw_logo(canvas: Image.Image, section: str) -> None:
    if not LOGO_PATH.exists():
        return
    logo = Image.open(LOGO_PATH).convert("RGBA")
    if section == "digest":
        logo_w = 300
        pos = (10, 20)
    else:
        logo_w = 405
        pos = (2, 2)
    logo_h = round(logo.height * logo_w / logo.width)
    logo = logo.resize((logo_w, logo_h), Image.Resampling.LANCZOS)
    canvas.alpha_composite(logo, pos)


def draw_style_overlay(event: dict[str, Any], output: Path) -> None:
    section = str(event.get("section") or "")
    canvas = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    if section == "digest":
        canvas.alpha_composite(gradient_image((WIDTH, 102), TOP_STOPS, 255), (0, 0))
        canvas.alpha_composite(gradient_image((WIDTH, 20), BOTTOM_STOPS, 255), (0, HEIGHT - 20))
        draw.polygon([(0, 0), (380, 0), (350, 102), (0, 102)], fill=(255, 255, 255, 255))

    if section != "bridge":
        draw_logo(canvas, section)
        title = title_text(event).strip()
        if title:
            font = fit_font(title, 680, 45, 34)
            bbox = draw.textbbox((0, 0), title, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            pad_x = 18
            box_h = 72
            box_w = min(720, text_w + pad_x * 2 + 32)
            x1 = WIDTH - 22
            x0 = x1 - box_w
            y0 = 16
            y1 = y0 + box_h
            if section != "digest":
                paste_slanted_gradient(canvas, [(x0 + 18, y0), (x1, y0), (x1 - 18, y1), (x0, y1)], TITLE_STOPS, 244)
            draw = ImageDraw.Draw(canvas)
            draw.text((x0 + (box_w - text_w) / 2, y0 + (box_h - text_h) / 2 - 4), title, font=font, fill=(255, 255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0, 110))
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)


def person_label(person_id: str) -> str:
    person = people_map().get(person_id, {})
    company = str(person.get("company") or "LayerX")
    role = str(person.get("role_title") or "").strip()
    name = str(person.get("display_name") or person_id)
    return f"{company} {role}  {name}".replace("  ", " ").strip()


def draw_caption(canvas: Image.Image, text: str, now: float, start: float, end: float) -> None:
    lines = wrap_caption_text(text)
    line_height = 84
    y_positions = [510] if len(lines) == 1 else [472, 590]
    draw = ImageDraw.Draw(canvas)
    for index, line in enumerate(lines):
        line_start = start + index * 0.18
        if now < line_start or now > end + 0.1:
            continue
        reveal = ease_out_cubic((now - line_start) / 0.583)
        opacity = min(1.0, max(0.0, (now - line_start) / 0.12))
        if now > end:
            opacity *= max(0.0, 1.0 - (now - end) / 0.1)
        font = fit_font(line, 1100, 58, 42)
        bbox = draw.textbbox((0, 0), line, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        box_w = min(1180, text_w + 72)
        box_h = line_height
        x0 = round((WIDTH - box_w) / 2)
        y0 = y_positions[index]
        line_layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        paste_gradient_box(line_layer, (x0, y0, x0 + box_w, y0 + box_h), [PURPLE_DARK, PURPLE_MID, PURPLE_LIGHT], 7, round(255 * opacity), True)
        text_x = x0 + (box_w - text_w) / 2
        text_y = y0 + (box_h - text_h) / 2 - 6
        ImageDraw.Draw(line_layer).text((text_x, text_y), line, font=font, fill=(255, 255, 255, round(255 * opacity)), stroke_width=1, stroke_fill=(0, 0, 0, round(80 * opacity)))
        visible_w = round(WIDTH * reveal)
        mask = Image.new("L", (WIDTH, HEIGHT), 0)
        ImageDraw.Draw(mask).rectangle((0, 0, visible_w, HEIGHT), fill=255)
        canvas.alpha_composite(Image.composite(line_layer, Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0)), mask))


def draw_nameplate(canvas: Image.Image, person_id: str, start: float, end: float, now: float) -> None:
    if not (start <= now <= end):
        return
    label = person_label(person_id)
    font = fit_font(label, 1080, 48, 36)
    draw = ImageDraw.Draw(canvas)
    bbox = draw.textbbox((0, 0), label, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    box_w = min(1160, text_w + 76)
    box_h = 78
    x0 = 52
    y0 = 510
    paste_gradient_box(canvas, (x0, y0, x0 + box_w, y0 + box_h), [PURPLE_DARK, PURPLE_MID, PURPLE_LIGHT], 4, 244, True)
    draw.text((x0 + 38, y0 + (box_h - text_h) / 2 - 6), label, font=font, fill=(255, 255, 255, 255), stroke_width=1, stroke_fill=(0, 0, 0, 80))


def render_text_overlay(ffmpeg: str, event: dict[str, Any], output: Path) -> bool:
    captions = [overlay for overlay in event.get("overlays", []) if isinstance(overlay, dict) and overlay.get("type") == "caption" and overlay.get("text")]
    nameplates = [overlay for overlay in event.get("overlays", []) if isinstance(overlay, dict) and overlay.get("type") == "lower_third_person" and overlay.get("person_id")]
    if not captions and not nameplates:
        return False
    dur = duration(event)
    total_frames = math.ceil(dur * FPS)
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "warning",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgba",
        "-s",
        f"{WIDTH}x{HEIGHT}",
        "-r",
        str(FPS),
        "-i",
        "-",
        "-an",
        "-c:v",
        "qtrle",
        str(output),
    ]
    process = subprocess.Popen(command, cwd=WORKSPACE_ROOT, stdin=subprocess.PIPE)
    assert process.stdin is not None
    try:
        for frame_index in range(total_frames):
            now = frame_index / FPS
            canvas = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
            for overlay in captions:
                draw_caption(canvas, str(overlay["text"]), now, float(overlay.get("start") or 0.0), float(overlay.get("end") or dur))
            for overlay in nameplates:
                draw_nameplate(canvas, str(overlay["person_id"]), float(overlay.get("start") or 0.0), float(overlay.get("end") or dur), now)
            process.stdin.write(canvas.tobytes())
    finally:
        process.stdin.close()
    if process.wait() != 0:
        raise subprocess.CalledProcessError(process.returncode, command)
    return True


def base_video_filter(event: dict[str, Any]) -> str:
    section = str(event.get("section") or "")
    if section == "bridge":
        return "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1"
    if section == "digest":
        return "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,setsar=1[scaled];color=c=black:s=1280x720:r=30:d={dur}[canvas];[canvas][scaled]overlay=0:69:format=auto"
    return "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,setsar=1"


def synced_media_start(media_id: str, master_time: float, offsets: dict[str, float]) -> float:
    role = MEDIA_TO_ROLE.get(media_id, "master")
    return max(0.0, master_time + offsets.get(role, 0.0))


def split_media_ids(event: dict[str, Any]) -> list[str]:
    layout = event.get("layout") if isinstance(event.get("layout"), dict) else {}
    media_ids = layout.get("media_ids")
    if isinstance(media_ids, list):
        return [str(media_id) for media_id in media_ids if str(media_id) in MEDIA_PATHS]
    return []


def split_divider_chain(media_count: int) -> str:
    width = 12
    if media_count == 2:
        return f",drawbox=x={640 - width // 2}:y=0:w={width}:h=720:color={DIVIDER_COLOR}@1:t=fill"
    if media_count == 3:
        return f",drawbox=x={426 - width // 2}:y=0:w={width}:h=720:color={DIVIDER_COLOR}@1:t=fill,drawbox=x={853 - width // 2}:y=0:w={width}:h=720:color={DIVIDER_COLOR}@1:t=fill"
    return ""


SPLIT_FACE_PROFILES = {
    # Original 1920x1080 ROI centers from the synced split-grid edit events.
    # These values keep faces close in size and on the same vertical band while
    # preserving enough shoulder room for the reference split composition.
    "cam_person_01": {"scale_h": 740, "face_center_x": 811, "face_center_y": 392, "target_face_y": 260},
    "cam_person_02": {"scale_h": 770, "face_center_x": 1058.5, "face_center_y": 333, "target_face_y": 225},
    "cam_person_03": {"scale_h": 730, "face_center_x": 1148.5, "face_center_y": 288.5},
}


def even_width_for_height(height: int) -> int:
    width = round(height * 16 / 9)
    return width if width % 2 == 0 else width + 1


def split_crop_profile(media_id: str, panel_width: int) -> tuple[int, int, int]:
    profile = SPLIT_FACE_PROFILES.get(media_id, {"scale_h": 720, "face_center_x": 960, "face_center_y": 330})
    scale_h = int(profile["scale_h"])
    scale = scale_h / 1080
    scaled_w = even_width_for_height(scale_h)
    target_face_x = panel_width / 2
    target_face_y = float(profile.get("target_face_y", 205))
    crop_x = round(float(profile["face_center_x"]) * scale - target_face_x)
    crop_y = round(float(profile["face_center_y"]) * scale - target_face_y)
    crop_x = max(0, min(crop_x, max(0, scaled_w - panel_width)))
    crop_y = max(0, min(crop_y, max(0, scale_h - 720)))
    return scale_h, crop_x, crop_y


def split_panel_filter(index: int, media_id: str, panel_width: int) -> str:
    scale_h, crop_x, crop_y = split_crop_profile(media_id, panel_width)
    if scale_h < 720:
        y_pad = (720 - scale_h) // 2
        return (
            f"[{index}:v]scale=-2:{scale_h}:force_original_aspect_ratio=increase,"
            f"crop={panel_width}:{scale_h}:{crop_x}:0,"
            f"pad={panel_width}:720:0:{y_pad},setsar=1[v{index}]"
        )
    return (
        f"[{index}:v]scale=-2:{scale_h}:force_original_aspect_ratio=increase,"
        f"crop={panel_width}:720:{crop_x}:{crop_y},setsar=1[v{index}]"
    )


def overlay_assets(ffmpeg: str, event: dict[str, Any], segment_id: str) -> tuple[Path, Path | None]:
    style_path = OVERLAYS / f"{segment_id}_style.png"
    text_path = OVERLAYS / f"{segment_id}_text.mov"
    draw_style_overlay(event, style_path)
    has_text = render_text_overlay(ffmpeg, event, text_path)
    return style_path, text_path if has_text else None


def render_segment(ffmpeg: str, event: dict[str, Any], output: Path, segment_id: str) -> None:
    layout = event.get("layout") if isinstance(event.get("layout"), dict) else {}
    if layout.get("type") == "split_grid" and split_media_ids(event):
        render_split_segment(ffmpeg, event, output, segment_id)
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
    style_path, text_path = overlay_assets(ffmpeg, event, segment_id)
    filter_base = base_video_filter(event).format(dur=f"{dur:.3f}")
    inputs = [
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
        str(style_path),
    ]
    if text_path:
        inputs.extend(["-i", str(text_path)])
    if text_path:
        filter_complex = f"[0:v]{filter_base}[base];[base][2:v]overlay=0:0:format=auto[styled];[styled][3:v]overlay=0:0:format=auto[vout]"
    else:
        filter_complex = f"[0:v]{filter_base}[base];[base][2:v]overlay=0:0:format=auto[vout]"
    command = inputs + [
        "-filter_complex",
        filter_complex,
        "-map",
        "[vout]",
        "-map",
        "1:a:0?",
        "-r",
        str(FPS),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "24",
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


def render_split_segment(ffmpeg: str, event: dict[str, Any], output: Path, segment_id: str) -> None:
    aud = audio_source(event)
    audio_path = MEDIA_PATHS.get(str(aud.get("media_id")))
    if audio_path is None or not audio_path.exists():
        raise FileNotFoundError(f"Audio media not available for preview: {aud.get('media_id')}")
    media_ids = split_media_ids(event)
    dur = duration(event)
    master_in = float((event.get("reference_source") or {}).get("in") or (event.get("source") or {}).get("in") or 0.0)
    offsets = app_offsets()
    style_path, text_path = overlay_assets(ffmpeg, event, segment_id)
    command = [ffmpeg, "-hide_banner", "-loglevel", "warning", "-y"]
    for media_id in media_ids:
        command.extend(["-ss", f"{synced_media_start(media_id, master_in, offsets):.3f}", "-t", f"{dur:.3f}", "-i", str(MEDIA_PATHS[media_id])])
    command.extend(["-ss", f"{float(aud.get('in') or master_in):.3f}", "-t", f"{dur:.3f}", "-i", str(audio_path)])
    command.extend(["-loop", "1", "-i", str(style_path)])
    if text_path:
        command.extend(["-i", str(text_path)])

    filters = []
    if len(media_ids) == 2:
        for index, media_id in enumerate(media_ids):
            filters.append(split_panel_filter(index, media_id, 640))
        stack = "[v0][v1]hstack=inputs=2"
    elif len(media_ids) == 3:
        for index, media_id in enumerate(media_ids):
            filters.append(split_panel_filter(index, media_id, 426))
        stack = "[v0][v1][v2]hstack=inputs=3,pad=1280:720:1:0"
    else:
        raise ValueError(f"Unsupported split media count: {len(media_ids)}")
    filters.append(f"{stack}{split_divider_chain(len(media_ids))}[base]")
    style_index = len(media_ids) + 1
    if text_path:
        text_index = style_index + 1
        filters.append(f"[base][{style_index}:v]overlay=0:0:format=auto[styled]")
        filters.append(f"[styled][{text_index}:v]overlay=0:0:format=auto[vout]")
    else:
        filters.append(f"[base][{style_index}:v]overlay=0:0:format=auto[vout]")
    command.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[vout]",
            "-map",
            f"{len(media_ids)}:a:0?",
            "-r",
            str(FPS),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "24",
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
    list_path = DIAGNOSTICS / "test_project1_style_preview_concat.txt"
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
            "24",
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Render LayerX preview with test-project-1 style overlays.")
    parser.add_argument("--max-events", type=int, default=12)
    parser.add_argument("--output", type=Path, default=VIDEOS / "preview_test_project1_style.mp4")
    args = parser.parse_args()
    plan = read_json(REPORTS / "edit_plan.json")
    if not (plan.get("validation") or {}).get("ready_for_preview"):
        raise SystemExit("edit_plan.json is not marked ready_for_preview")
    events = [event for event in plan.get("timeline", []) if isinstance(event, dict)]
    if args.max_events:
        events = events[: args.max_events]
    segment_dir = VIDEOS / "preview_test_project1_style_segments"
    segment_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg = ffmpeg_path()
    rendered = []
    for index, event in enumerate(events, start=1):
        segment_id = f"segment_{index:03d}_{event.get('event_id', 'event')}"
        segment_path = segment_dir / f"{segment_id}.mp4"
        render_segment(ffmpeg, event, segment_path, segment_id)
        rendered.append(segment_path)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    concat_segments(ffmpeg, rendered, args.output)
    report = {
        "schema_version": "test_project1_style_preview_report.v1",
        "output": str(args.output),
        "segments": len(rendered),
        "style_reference": "projects/test-project-1 styled preview: sample-11 frame overlay + sample-1 catchphrase subtitle style",
        "notes": [
            "Digest uses opaque top/bottom bands and slanted white LayerX logo panel.",
            "Main section removes the full-width top/bottom bands completely.",
            "Captions are rendered as animated RGBA overlays with horizontal reveal and quick fade.",
            "Split dividers use a bluer color and 3x the previous width.",
            "Split crops align face scale and vertical head height across participants.",
        ],
    }
    write_json(REPORTS / "test_project1_style_preview_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
