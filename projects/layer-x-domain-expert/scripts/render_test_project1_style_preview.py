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
CAPTION_FONT_FILE = Path(r"C:\Windows\Fonts\BIZ-UDGothicB.ttc")
LOGO_PATH = PROJECT_ROOT / "source" / "assets" / "LayerX_Logo_Horizontal_RGB_Color.png"

WIDTH = 1280
HEIGHT = 720
FPS = 30

PURPLE_DARK = "#4D15D7"
PURPLE_MID = "#5A2DEF"
PURPLE_LIGHT = "#7863F3"
CAPTION_STOPS = ["#4015E8", "#6333F4", "#7B63F7"]
TOP_STOPS = ["#5A51FE", "#5A51FD", "#5D60FE"]
BOTTOM_STOPS = ["#5B59FD", "#656AFD", "#747FFC"]
TITLE_STOPS = ["#4D15D7", "#5A2DEF", "#7863F3"]
DIVIDER_COLOR = "0x5A2DEF"
CAPTION_FONT_SIZE = 76
CAPTION_MAX_TEXT_WIDTH = 1080
TARGET_AUDIO_LUFS = -17.0

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

PERSON_TO_MEDIA = {
    "person_01": "cam_person_01",
    "person_02": "cam_person_02",
    "person_03": "cam_person_03",
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
    source = event.get("source") if isinstance(event.get("source"), dict) else {}
    reference = event.get("reference_source") if isinstance(event.get("reference_source"), dict) else {}
    if str(event.get("section") or "") == "bridge" or str(source.get("media_id") or "") == "company_movie":
        return source
    master_in = float(reference.get("in") or source.get("in") or 0.0)
    return {"media_id": "group_wide", "in": master_in, "out": master_in + duration(event)}


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


def fit_font(text: str, max_width: int, size: int, min_size: int, font_file: Path = FONT_FILE) -> ImageFont.FreeTypeFont:
    probe = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    draw = ImageDraw.Draw(probe)
    for font_size in range(size, min_size - 1, -2):
        font = ImageFont.truetype(str(font_file), font_size)
        bbox = draw.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= max_width:
            return font
    return ImageFont.truetype(str(font_file), min_size)


PROTECTED_CAPTION_TERMS = [
    "ドメインエキスパート",
    "プロダクトマネージャー",
    "バックオフィス",
    "エンジニア",
    "PDM",
    "AI",
    "LayerX",
    "開発",
    "言語化",
    "当たり前",
    "暗黙知",
    "慣行",
    "建設的",
    "プレッシャー",
    "リサーチ",
    "プロダクト",
    "キャリア",
    "引っ張って",
    "使いづらい",
    "めっちゃ",
    "めちゃめちゃ",
    "おすすめ",
    "絶対に逃がして",
    "ある種",
    "っていう",
    "そういう",
    "という",
    "AIを",
    "建設的な",
    "ものすごく",
    "ドメインの方",
    "何でも知ってそう",
    "知ってそうな感じ",
    "知ってるんじゃないか",
    "思われること",
    "ことの難しさ",
    "開発に関わる仕事をする中で",
    "今までやってきたんだな",
    "磨かれて成長",
    "いらないもの",
    "前提になってきている",
    "実現していきたい",
    "研ぎ澄まされてきている",
    "研ぎ澄まされてきているなという",
    "探し出してきてくれる",
    "探し出してきてくれるんですけど",
    "広く見れる",
    "ものすごくこれを言語化するのに",
    "抵抗感っていう",
    "ドメインの方めっちゃ調べてるんですよ",
    "実現していきたいのか",
    "こういう形で広く見れる",
    "めちゃめちゃおすすめだと思います",
]


def protected_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for term in PROTECTED_CAPTION_TERMS:
        start = 0
        while True:
            index = text.find(term, start)
            if index < 0:
                break
            spans.append((index, index + len(term)))
            start = index + len(term)
    return spans


def inside_protected_span(index: int, spans: list[tuple[int, int]]) -> bool:
    return any(start < index < end for start, end in spans)


def caption_cut_candidates(text: str, spans: list[tuple[int, int]]) -> list[int]:
    candidates = set()
    break_after = (
        "、",
        "。",
        "？",
        "！",
        " ",
        "とか",
        "けど",
        "ので",
        "から",
        "って",
        "には",
        "では",
        "とは",
        "という",
        "みたいな",
        "ですけど",
        "ですよ",
        "ですね",
        "ます",
        "ました",
    )
    for phrase in break_after:
        start = 0
        while True:
            index = text.find(phrase, start)
            if index < 0:
                break
            candidates.add(index + len(phrase))
            start = index + len(phrase)
    for start, end in spans:
        candidates.add(start)
        candidates.add(end)
    return sorted(index for index in candidates if 0 < index < len(text) and not inside_protected_span(index, spans))


def wrap_caption_text(text: str, max_chars: int = 13) -> list[str]:
    text = " ".join(str(text).replace("、", "").split())
    if len(text) <= max_chars:
        return [text]
    spans = protected_spans(text)
    candidates = caption_cut_candidates(text, spans)
    lower_bound = max(6, max_chars - 5)
    preferred = [index for index in candidates if lower_bound <= index <= max_chars]
    if preferred:
        cut = preferred[-1]
    else:
        forward = [index for index in candidates if max_chars < index <= max_chars + 9]
        if forward:
            cut = forward[0]
        else:
            cut = max_chars
            while cut < len(text) and inside_protected_span(cut, spans):
                cut += 1
    first = text[:cut].strip(" 、。！？")
    second = text[cut:].strip(" 、。！？")
    if second and len(second) < 5 and len(first) + len(second) <= max_chars + 5:
        return [f"{first}{second}"]
    result = [line for line in (first, second) if line]
    if len(result) == 2 and len(result[1]) <= 3 and len(result[0]) + len(result[1]) <= max_chars + 8:
        return [result[0] + result[1]]
    return result[:2]


def condensed_text_image(text: str, font: ImageFont.FreeTypeFont, fill: tuple[int, int, int, int], scale_x: float = 0.92) -> Image.Image:
    probe = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    draw = ImageDraw.Draw(probe)
    bbox = draw.textbbox((0, 0), text, font=font)
    width = max(1, bbox[2] - bbox[0] + 16)
    height = max(1, bbox[3] - bbox[1] + 14)
    text_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    text_draw = ImageDraw.Draw(text_layer)
    base_x = 8 - bbox[0]
    base_y = 7 - bbox[1]
    for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1), (-1, 0), (2, 0), (0, 2), (2, 1), (1, 2)):
        text_draw.text((base_x + dx, base_y + dy), text, font=font, fill=fill, stroke_width=1, stroke_fill=fill)
    target_width = max(1, round(width * scale_x))
    return text_layer.resize((target_width, height), Image.Resampling.LANCZOS)


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


def draw_logo(canvas: Image.Image, section: str, is_split: bool = False) -> None:
    if not LOGO_PATH.exists():
        return
    logo = Image.open(LOGO_PATH).convert("RGBA")
    bbox = logo.getbbox()
    if bbox:
        logo = logo.crop(bbox)
    if section == "digest":
        logo_w = 216
    elif is_split:
        logo_w = 176
    else:
        logo_w = 216
    logo_h = round(logo.height * logo_w / logo.width)
    logo = logo.resize((logo_w, logo_h), Image.Resampling.LANCZOS)
    if section == "digest":
        pos = (18, round((102 - logo_h) / 2))
    else:
        pos = (18, 18)
    canvas.alpha_composite(logo, pos)


def draw_style_overlay(event: dict[str, Any], output: Path) -> None:
    section = str(event.get("section") or "")
    layout = event.get("layout") if isinstance(event.get("layout"), dict) else {}
    is_split = layout.get("type") == "split_grid"
    canvas = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    if section == "digest":
        canvas.alpha_composite(gradient_image((WIDTH, 102), TOP_STOPS, 255), (0, 0))
        canvas.alpha_composite(gradient_image((WIDTH, 20), BOTTOM_STOPS, 255), (0, HEIGHT - 20))
        draw.polygon([(0, 0), (305, 0), (280, 102), (0, 102)], fill=(255, 255, 255, 255))

    if section != "bridge":
        draw_logo(canvas, section, is_split)
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
            draw.text((x0 + (box_w - text_w) / 2, y0 + (box_h - text_h) / 2 - 4), title, font=font, fill=(255, 255, 255, 255))
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)


def person_label(person_id: str) -> str:
    person = people_map().get(person_id, {})
    company = str(person.get("company") or "LayerX")
    role = str(person.get("role_title") or "").strip()
    name = str(person.get("display_name") or person_id)
    return f"{company} {role}  {name}".replace("  ", " ").strip()


def person_intro_lines(person_id: str) -> tuple[str, str]:
    person = people_map().get(person_id, {})
    department = str(person.get("department") or "").strip()
    role = str(person.get("role_title") or "").strip()
    name = str(person.get("display_name") or person_id).strip()
    descriptor = " ".join(part for part in (department, role) if part)
    return descriptor or "LayerX", name


def draw_shadow_text(draw: ImageDraw.ImageDraw, position: tuple[float, float], text: str, font: ImageFont.FreeTypeFont, fill: tuple[int, int, int, int]) -> None:
    x, y = position
    shadow = (80, 80, 80, max(80, fill[3] - 40))
    for dx, dy in ((2, 2), (3, 3)):
        draw.text((x + dx, y + dy), text, font=font, fill=shadow)
    draw.text((x, y), text, font=font, fill=fill)


def draw_white_intro_label(canvas: Image.Image, person_id: str, x: int, y: int, max_width: int, *, name_size: int, role_size: int, opacity: float = 1.0) -> None:
    role, name = person_intro_lines(person_id)
    draw = ImageDraw.Draw(canvas)
    role_font = fit_font(role, max_width, role_size, max(20, role_size - 10))
    name_font = fit_font(name, max_width, name_size, max(36, name_size - 18))
    alpha = round(255 * max(0.0, min(1.0, opacity)))
    draw_shadow_text(draw, (x, y), role, role_font, (255, 255, 255, alpha))
    draw_shadow_text(draw, (x, y + role_size + 12), name, name_font, (255, 255, 255, alpha))


def draw_caption(canvas: Image.Image, text: str, now: float, start: float, end: float) -> None:
    lines = wrap_caption_text(text)
    line_height = 104
    gap = 10
    stack_h = len(lines) * line_height + (len(lines) - 1) * gap
    y_base = 660 - stack_h
    y_positions = [y_base + index * (line_height + gap) for index in range(len(lines))]
    draw = ImageDraw.Draw(canvas)
    for index, line in enumerate(lines):
        line_start = start + index * 0.12
        if now < line_start or now > end + 0.1:
            continue
        reveal = ease_out_cubic((now - line_start) / 0.583)
        opacity = min(1.0, max(0.0, (now - line_start) / 0.12))
        if now > end:
            opacity *= max(0.0, 1.0 - (now - end) / 0.1)
        font = ImageFont.truetype(str(CAPTION_FONT_FILE), CAPTION_FONT_SIZE)
        bbox = draw.textbbox((0, 0), line, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        scale_x = min(0.98, CAPTION_MAX_TEXT_WIDTH / max(1, text_w + 16))
        text_image = condensed_text_image(line, font, (255, 255, 255, round(255 * opacity)), scale_x)
        text_w = text_image.width
        text_h = text_image.height
        box_w = min(1198, text_w + 66)
        box_h = line_height
        x0 = round((WIDTH - box_w) / 2)
        y0 = y_positions[index]
        line_layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        paste_gradient_box(line_layer, (x0, y0, x0 + box_w, y0 + box_h), CAPTION_STOPS, 5, round(245 * opacity), True)
        text_x = x0 + (box_w - text_w) / 2
        text_y = y0 + (box_h - text_h) / 2
        line_layer.alpha_composite(text_image, (round(text_x), round(text_y)))
        visible_w = round(WIDTH * reveal)
        mask = Image.new("L", (WIDTH, HEIGHT), 0)
        ImageDraw.Draw(mask).rectangle((0, 0, visible_w, HEIGHT), fill=255)
        canvas.alpha_composite(Image.composite(line_layer, Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0)), mask))


def draw_nameplate(canvas: Image.Image, overlay: dict[str, Any], start: float, end: float, now: float) -> None:
    if not (start <= now <= end):
        return
    person_id = str(overlay["person_id"])
    if overlay.get("style_id") == "single_intro_white_text_reference":
        opacity = min(1.0, max(0.0, (now - start) / 0.2))
        draw_white_intro_label(canvas, person_id, 80, 500, 720, name_size=64, role_size=34, opacity=opacity)
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
    draw.text((x0 + 38, y0 + (box_h - text_h) / 2 - 6), label, font=font, fill=(255, 255, 255, 255))


def draw_split_person_labels(canvas: Image.Image, overlay: dict[str, Any], start: float, end: float, now: float) -> None:
    if not (start <= now <= end):
        return
    person_ids = [str(item) for item in overlay.get("person_ids", [])]
    if len(person_ids) != 2:
        return
    opacity = min(1.0, max(0.0, (now - start) / 0.2))
    draw_white_intro_label(canvas, person_ids[0], 52, 500, 520, name_size=56, role_size=28, opacity=opacity)
    draw_white_intro_label(canvas, person_ids[1], 710, 500, 520, name_size=56, role_size=28, opacity=opacity)


def render_text_overlay(ffmpeg: str, event: dict[str, Any], output: Path) -> bool:
    captions = [overlay for overlay in event.get("overlays", []) if isinstance(overlay, dict) and overlay.get("type") == "caption" and overlay.get("text")]
    nameplates = [overlay for overlay in event.get("overlays", []) if isinstance(overlay, dict) and overlay.get("type") == "lower_third_person" and overlay.get("person_id")]
    split_labels = [overlay for overlay in event.get("overlays", []) if isinstance(overlay, dict) and overlay.get("type") == "split_person_labels"]
    if not captions and not nameplates and not split_labels:
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
                draw_nameplate(canvas, overlay, float(overlay.get("start") or 0.0), float(overlay.get("end") or dur), now)
            for overlay in split_labels:
                draw_split_person_labels(canvas, overlay, float(overlay.get("start") or 0.0), float(overlay.get("end") or dur), now)
            process.stdin.write(canvas.tobytes())
    finally:
        process.stdin.close()
    if process.wait() != 0:
        raise subprocess.CalledProcessError(process.returncode, command)
    return True


def color_match_filter(media_id: str) -> str:
    if media_id in {"cam_person_01", "cam_person_02", "cam_person_03"}:
        return ",eq=saturation=0.72:contrast=0.92:brightness=0.025:gamma=1.03"
    return ""


def source_skip_sec(event: dict[str, Any]) -> float:
    if str(event.get("event_id") or "") == "digest_001":
        return 0.45
    return 0.0


def audio_filter_chain(media_id: str) -> str:
    loudnorm = f"loudnorm=I={TARGET_AUDIO_LUFS}:TP=-1.5:LRA=11"
    if media_id == "company_movie":
        return loudnorm
    return (
        "highpass=f=80,"
        "lowpass=f=12000,"
        "afftdn=nf=-25,"
        "acompressor=threshold=-28dB:ratio=3.2:attack=5:release=140:makeup=5,"
        "dynaudnorm=f=150:g=9:p=0.95:m=8,"
        f"{loudnorm}"
    )


def base_video_filter(event: dict[str, Any], media_id: str) -> str:
    section = str(event.get("section") or "")
    if section == "bridge":
        return "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,setpts=PTS-STARTPTS"
    if section == "digest":
        return f"scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720{color_match_filter(media_id)},setsar=1,setpts=PTS-STARTPTS[scaled];color=c=black:s=1280x720:r=30:d={{dur}}[canvas];[canvas][scaled]overlay=0:69:format=auto"
    return f"scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720{color_match_filter(media_id)},setsar=1,setpts=PTS-STARTPTS"


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
    width = 8
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
            f"pad={panel_width}:720:0:{y_pad}{color_match_filter(media_id)},setsar=1,setpts=PTS-STARTPTS[v{index}]"
        )
    return (
        f"[{index}:v]scale=-2:{scale_h}:force_original_aspect_ratio=increase,"
        f"crop={panel_width}:720:{crop_x}:{crop_y}{color_match_filter(media_id)},setsar=1,setpts=PTS-STARTPTS[v{index}]"
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
    skip = source_skip_sec(event)
    style_path, text_path = overlay_assets(ffmpeg, event, segment_id)
    filter_base = base_video_filter(event, str(src.get("media_id"))).format(dur=f"{dur:.3f}")
    inputs = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "warning",
        "-y",
        "-ss",
        f"{float(src.get('in') or 0.0) + skip:.3f}",
        "-t",
        f"{dur:.3f}",
        "-i",
        str(video_path),
        "-ss",
        f"{float(aud.get('in') or 0.0) + skip:.3f}",
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
    audio_filter = audio_filter_chain(str(aud.get("media_id") or ""))
    if text_path:
        filter_complex = f"[0:v]{filter_base}[base];[base][2:v]overlay=0:0:format=auto[styled];[styled][3:v]overlay=0:0:format=auto[vout];[1:a]{audio_filter}[aout]"
    else:
        filter_complex = f"[0:v]{filter_base}[base];[base][2:v]overlay=0:0:format=auto[vout];[1:a]{audio_filter}[aout]"
    command = inputs + [
        "-filter_complex",
        filter_complex,
        "-map",
        "[vout]",
        "-map",
        "[aout]",
        "-t",
        f"{dur:.3f}",
        "-r",
        str(FPS),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "24",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-ar",
        "48000",
        "-shortest",
        "-movflags",
        "+faststart",
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
    filters.append(f"[{len(media_ids)}:a]{audio_filter_chain(str(aud.get('media_id') or ''))}[aout]")
    command.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[vout]",
            "-map",
            "[aout]",
            "-t",
            f"{dur:.3f}",
            "-r",
            str(FPS),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "24",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ar",
            "48000",
            "-shortest",
            "-movflags",
            "+faststart",
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
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ar",
            "48000",
            "-movflags",
            "+faststart",
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
    for old_segment in segment_dir.glob("*.mp4"):
        old_segment.unlink()
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
            "Split dividers use the theme purple color and a thinner rule.",
            "Split crops align face scale and vertical head height across participants.",
            "White overlay text is rendered without black stroke outlines.",
            "Interview audio uses one continuous group_wide reference source across all video cuts.",
        ],
    }
    write_json(REPORTS / "test_project1_style_preview_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
