from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps


TARGET_SIZE = (1280, 720)
ORANGE = "#F28C28"
WHITE = (255, 255, 255, 255)
BLACK = (0, 0, 0, 255)
CHARCOAL = (34, 32, 29, 255)
MUTED = (100, 92, 82, 255)


FONT_CANDIDATES_BOLD = [
    Path(r"C:\Windows\Fonts\YuGothB.ttc"),
    Path(r"C:\Windows\Fonts\meiryob.ttc"),
    Path(r"C:\Windows\Fonts\YuGothM.ttc"),
    Path(r"C:\Windows\Fonts\meiryo.ttc"),
]
FONT_CANDIDATES_REGULAR = [
    Path(r"C:\Windows\Fonts\YuGothM.ttc"),
    Path(r"C:\Windows\Fonts\meiryo.ttc"),
    Path(r"C:\Windows\Fonts\YuGothB.ttc"),
]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def hex_rgb(value: str, default: str = "#FFFFFF") -> tuple[int, int, int]:
    text = str(value or default).strip().lstrip("#")
    if not re.fullmatch(r"[0-9A-Fa-f]{6}", text):
        text = default.lstrip("#")
    return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))


def font(size: int, *, bold: bool = True) -> ImageFont.ImageFont:
    candidates = FONT_CANDIDATES_BOLD if bold else FONT_CANDIDATES_REGULAR
    for path in candidates:
        if not path.exists():
            continue
        for index in (1, 0):
            try:
                return ImageFont.truetype(str(path), size, index=index)
            except OSError:
                continue
    return ImageFont.load_default()


def text_size(draw: ImageDraw.ImageDraw, text: str, text_font: ImageFont.ImageFont, stroke: int = 0) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=text_font, stroke_width=stroke)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def fit_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    max_height: int,
    *,
    start: int,
    minimum: int,
    bold: bool = True,
    stroke_ratio: int = 12,
) -> tuple[ImageFont.ImageFont, int]:
    for size in range(start, minimum - 1, -4):
        text_font = font(size, bold=bold)
        stroke = max(2, size // stroke_ratio)
        width, height = text_size(draw, text, text_font, stroke)
        if width <= max_width and height <= max_height:
            return text_font, stroke
    text_font = font(minimum, bold=bold)
    return text_font, max(2, minimum // stroke_ratio)


def open_image(path: Path) -> Image.Image:
    return ImageOps.exif_transpose(Image.open(path)).convert("RGB")


def cover_crop(
    image: Image.Image,
    size: tuple[int, int],
    *,
    focus_x: float = 0.5,
    focus_y: float = 0.5,
) -> Image.Image:
    scale = max(size[0] / image.width, size[1] / image.height)
    resized = image.resize((round(image.width * scale), round(image.height * scale)), Image.Resampling.LANCZOS)
    max_left = max(0, resized.width - size[0])
    max_top = max(0, resized.height - size[1])
    left = round(max_left * max(0.0, min(1.0, focus_x)))
    top = round(max_top * max(0.0, min(1.0, focus_y)))
    return resized.crop((left, top, left + size[0], top + size[1]))


def fit_width_crop(image: Image.Image, size: tuple[int, int], *, y_offset: int) -> Image.Image:
    scale = size[0] / image.width
    resized = image.resize((size[0], round(image.height * scale)), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", size, (0, 0, 0))
    canvas.paste(resized, (0, y_offset))
    return canvas


def zoom_crop(
    image: Image.Image,
    size: tuple[int, int],
    *,
    zoom: float,
    focus_x: float,
    focus_y: float,
) -> Image.Image:
    scale = max(size[0] / image.width, size[1] / image.height) * zoom
    resized = image.resize((round(image.width * scale), round(image.height * scale)), Image.Resampling.LANCZOS)
    max_left = max(0, resized.width - size[0])
    max_top = max(0, resized.height - size[1])
    left = round(max_left * max(0.0, min(1.0, focus_x)))
    top = round(max_top * max(0.0, min(1.0, focus_y)))
    return resized.crop((left, top, left + size[0], top + size[1]))


def rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return mask


def paste_rounded(canvas: Image.Image, image: Image.Image, xy: tuple[int, int], radius: int) -> None:
    rounded = image.convert("RGBA")
    rounded.putalpha(rounded_mask(image.size, radius))
    canvas.alpha_composite(rounded, xy)


def draw_shadow(
    canvas: Image.Image,
    rect: tuple[int, int, int, int],
    *,
    radius: int = 10,
    blur: int = 18,
    alpha: int = 110,
) -> None:
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(shadow)
    x1, y1, x2, y2 = rect
    draw.rounded_rectangle((x1, y1, x2, y2), radius=radius, fill=(0, 0, 0, alpha))
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    canvas.alpha_composite(shadow)


def draw_top_label(draw: ImageDraw.ImageDraw, label: str, accent: tuple[int, int, int]) -> tuple[int, int, int, int]:
    label_font = font(38, bold=True)
    bbox = draw.textbbox((0, 0), label, font=label_font)
    pad_x, pad_y = 18, 10
    x, y = 32, 32
    width = bbox[2] - bbox[0] + pad_x * 2
    height = bbox[3] - bbox[1] + pad_y * 2
    draw.rectangle((x, y, x + width, y + height), fill=(255, 255, 255, 238))
    draw.text((x + pad_x - bbox[0], y + pad_y - bbox[1]), label, font=label_font, fill=CHARCOAL)
    return (x, y, x + width, y + height)


def paste_logo(canvas: Image.Image, logo_path: Path | None) -> str:
    if not logo_path or not logo_path.exists():
        return ""
    logo = Image.open(logo_path).convert("RGBA")
    alpha_bbox = logo.getbbox()
    if alpha_bbox:
        logo = logo.crop(alpha_bbox)
    target_h = 58
    logo = logo.resize((round(logo.width * target_h / max(1, logo.height)), target_h), Image.Resampling.LANCZOS)
    pad_x, pad_y = 14, 10
    plate = Image.new("RGBA", (logo.width + pad_x * 2, logo.height + pad_y * 2), (255, 255, 255, 244))
    ImageDraw.Draw(plate).rounded_rectangle((0, 0, plate.width - 1, plate.height - 1), radius=8, fill=(255, 255, 255, 244))
    plate.alpha_composite(logo, (pad_x, pad_y))
    canvas.alpha_composite(plate, (TARGET_SIZE[0] - plate.width - 32, 32))
    return str(logo_path)


def draw_headline(draw: ImageDraw.ImageDraw, headline: str, accent: tuple[int, int, int]) -> None:
    lines = [line.strip() for line in headline.splitlines() if line.strip()]
    if not lines:
        return
    max_width, max_height = 1120, 170
    line_heights: list[tuple[str, ImageFont.ImageFont, int, tuple[int, int], tuple[int, int, int, int]]] = []
    remaining_height = max_height
    for index, line in enumerate(lines[:3]):
        start = 146 if len(lines) <= 2 else 118
        text_font, stroke = fit_font(draw, line, max_width, remaining_height, start=start, minimum=88, stroke_ratio=60)
        width, height = text_size(draw, line, text_font, stroke)
        fill = WHITE
        line_heights.append((line, text_font, stroke, (width, height), fill))
        remaining_height -= height + 12

    total_height = sum(size[1] for _, _, _, size, _ in line_heights) + max(0, len(line_heights) - 1) * 12
    current_y = TARGET_SIZE[1] - total_height - 58
    for line, text_font, stroke, (_, height), fill in line_heights:
        bbox = draw.textbbox((0, 0), line, font=text_font)
        x = round((TARGET_SIZE[0] - (bbox[2] - bbox[0])) / 2)
        draw.text((x, current_y), line, font=text_font, fill=fill, stroke_width=stroke, stroke_fill=fill)
        current_y += height + 12


def project_text(config: dict[str, Any], project_root: Path) -> dict[str, str]:
    project_id = str(config.get("project", {}).get("id") or project_root.name)
    title_text = str(config.get("radioEdit", {}).get("titleText") or "")
    guest = ""
    match = re.search(r"】(.+?さん)出演", title_text)
    if match:
        guest = match.group(1)
    elif "hanaoka" in project_id:
        guest = "花岡洋行さん"
    elif "nakanishi" in project_id:
        guest = "中西裕理さん"
    else:
        guest = str(config.get("project", {}).get("name") or project_id)

    if "hanaoka" in project_id:
        headline = "Kiitosの新理事"
        topic = "青少年の居場所 Kiitos"
    elif "nakanishi" in project_id:
        headline = "居場所支援について"
        topic = "青少年の居場所 Kiitos"
    else:
        headline = "Kiitosを\n語る"
        topic = "青少年の居場所 Kiitos"

    return {
        "projectId": project_id,
        "guest": guest,
        "headline": headline,
        "topic": topic,
        "label": f"東京オアシス {guest}出演会",
    }


def project_accent(config: dict[str, Any], project_id: str) -> tuple[int, int, int]:
    edit = config.get("radioEdit", {})
    if "hanaoka" in project_id:
        return hex_rgb(str(edit.get("hanaokaSubtitleBoxColor") or "#2FAE66"))
    if "nakanishi" in project_id:
        return hex_rgb(str(edit.get("nakanishiSubtitleBoxColor") or "#2F80ED"))
    return hex_rgb(ORANGE)


def path_from_config(value: Any) -> Path | None:
    if not value:
        return None
    path = Path(str(value))
    return path if path.exists() else None


def render_thumbnail(project_root: Path, output: Path, *, headline: str | None, topic: str | None) -> dict[str, Any]:
    config = load_json(project_root / "project_state.json")
    text = project_text(config, project_root)
    if headline:
        text["headline"] = headline.replace("\\n", "\n")
    if topic:
        text["topic"] = topic

    assets = config.get("assets", {})
    bg_path = (
        path_from_config(assets.get("thumbnailImage"))
        or path_from_config(assets.get("mainImage"))
        or path_from_config(assets.get("alternateImage"))
    )
    logo_path = path_from_config(config.get("radioEdit", {}).get("logoPath")) or path_from_config(assets.get("logo"))
    if bg_path is None:
        raise SystemExit(f"No project image found in {project_root / 'project_state.json'}")

    accent = hex_rgb(ORANGE)

    source_image = open_image(bg_path)
    if "nakanishi" in text["projectId"]:
        background = fit_width_crop(source_image, TARGET_SIZE, y_offset=-38)
    else:
        background = zoom_crop(source_image, TARGET_SIZE, zoom=1.24, focus_x=0.54, focus_y=0.47)
    background = ImageEnhance.Color(background).enhance(0.82)
    background = ImageEnhance.Contrast(background).enhance(1.03)
    background = ImageEnhance.Brightness(background).enhance(0.96)
    canvas = background.convert("RGBA")

    overlay = Image.new("RGBA", TARGET_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for y in range(420, TARGET_SIZE[1]):
        alpha = round(48 * max(0.0, (y - 420) / 300))
        draw.line((0, y, TARGET_SIZE[0], y), fill=(0, 0, 0, alpha))
    canvas.alpha_composite(overlay)
    draw = ImageDraw.Draw(canvas)

    draw_top_label(draw, text["label"], accent)
    paste_logo(canvas, logo_path)
    draw_headline(draw, text["headline"], accent)

    draw.rectangle((0, 0, TARGET_SIZE[0] - 1, TARGET_SIZE[1] - 1), outline=(*accent, 230), width=16)

    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output, quality=95)
    report = {
        "projectId": text["projectId"],
        "output": str(output),
        "backgroundImage": str(bg_path),
        "portraitImage": "",
        "logo": str(logo_path) if logo_path else "",
        "headline": text["headline"],
        "guest": text["guest"],
        "topic": text["topic"],
        "width": TARGET_SIZE[0],
        "height": TARGET_SIZE[1],
        "style": {
            "programAccent": ORANGE,
            "guestAccent": "",
            "layout": "single photo background, restrained left text panel, top-left episode label, top-right logo",
        },
    }
    report_path = output.with_suffix(".json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a Tokyo Oasis YouTube thumbnail from a project_state.json.")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--headline", default=None)
    parser.add_argument("--topic", default=None)
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    default_output = project_root / "output" / "thumbnails" / "youtube_thumbnail_v1.jpg"
    output = (args.output or default_output).resolve()
    report = render_thumbnail(project_root, output, headline=args.headline, topic=args.topic)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
