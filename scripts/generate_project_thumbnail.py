from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from project_paths import OUTPUT_IMAGES
from video_edit_app_config import hex_rgba, load_app_config, nested, optional_path


APP_CONFIG = load_app_config()
FFMPEG = optional_path(APP_CONFIG, "tools", "ffmpeg", default=Path(r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"))
FONT_PATH = Path(r"C:\Windows\Fonts\YuGothB.ttc")
TARGET_SIZE = (1280, 720)


def text_value(config: dict[str, Any], *keys: str, default: str = "") -> str:
    value = nested(config, *keys, default=default)
    return str(value) if value is not None else default


def media_manifest() -> dict[str, Any]:
    manifest = nested(APP_CONFIG, "assets", "mediaManifest", default={})
    if isinstance(manifest, dict) and manifest.get("files"):
        return manifest
    path = text_value(APP_CONFIG, "assets", "mediaManifestPath")
    if path and Path(path).exists():
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return {}


def manifest_cameras() -> list[Path]:
    files = media_manifest().get("files", [])
    if not isinstance(files, list):
        return []
    camera_roles = {"master", "camera2", "camera3", "camera4", "camera5", "camera6"}
    cameras = [
        Path(str(item.get("path") or ""))
        for item in files
        if isinstance(item, dict) and item.get("kind") == "video" and item.get("role") in camera_roles
    ]
    return [path for path in cameras if path.exists()]


def source_video() -> Path:
    candidates = [
        text_value(APP_CONFIG, "thumbnail", "inputVideoPath"),
        text_value(APP_CONFIG, "workflow", "inputVideoPath"),
        text_value(APP_CONFIG, "assets", "masterVideo"),
        text_value(APP_CONFIG, "render", "outputPath"),
    ]
    for value in candidates:
        path = Path(value) if value else None
        if path and path.exists():
            return path
    for path in manifest_cameras():
        return path
    raise SystemExit("No input video found for thumbnail generation.")


def output_path() -> Path:
    configured = text_value(APP_CONFIG, "thumbnail", "outputPath")
    return Path(configured) if configured else OUTPUT_IMAGES / "thumbnail.png"


def extract_frame(video: Path, timestamp: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(FFMPEG),
        "-hide_banner",
        "-y",
        "-ss",
        timestamp,
        "-i",
        str(video),
        "-frames:v",
        "1",
        "-update",
        "1",
        str(target),
    ]
    subprocess.run(command, check=True)


def cover(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    image = image.convert("RGB")
    scale = max(size[0] / image.width, size[1] / image.height)
    resized = image.resize((round(image.width * scale), round(image.height * scale)), Image.LANCZOS)
    left = max(0, (resized.width - size[0]) // 2)
    top = max(0, (resized.height - size[1]) // 2)
    return resized.crop((left, top, left + size[0], top + size[1])).convert("RGBA")


def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_PATH), size, index=1)


def wrap_text(text: str, draw: ImageDraw.ImageDraw, text_font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    text = " ".join(text.split())
    if not text:
        return []
    lines: list[str] = []
    current = ""
    for char in text:
        candidate = current + char
        if current and draw.textbbox((0, 0), candidate, font=text_font, stroke_width=2)[2] > max_width:
            lines.append(current)
            current = char
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines[:3]


def paste_logo(canvas: Image.Image) -> None:
    logo_path = text_value(APP_CONFIG, "assets", "logo")
    if not logo_path or not Path(logo_path).exists():
        return
    try:
        logo = Image.open(logo_path).convert("RGBA")
    except Exception:
        return
    target_h = 58
    scale = target_h / max(1, logo.height)
    logo = logo.resize((round(logo.width * scale), target_h), Image.LANCZOS)
    canvas.alpha_composite(logo, (TARGET_SIZE[0] - logo.width - 44, 36))


def render_thumbnail(frame_path: Path, output: Path) -> dict[str, Any]:
    base = cover(Image.open(frame_path), TARGET_SIZE)
    overlay = Image.new("RGBA", TARGET_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for y in range(TARGET_SIZE[1]):
        alpha = round(168 * (y / TARGET_SIZE[1]) ** 1.8)
        draw.line((0, y, TARGET_SIZE[0], y), fill=(0, 0, 0, alpha))
    base.alpha_composite(overlay)

    title = text_value(APP_CONFIG, "thumbnail", "title") or text_value(APP_CONFIG, "style", "titleText") or text_value(APP_CONFIG, "project", "name")
    subtitle = text_value(APP_CONFIG, "thumbnail", "subtitle")
    accent = hex_rgba(nested(APP_CONFIG, "style", "highlightColor"), default=(15, 118, 110, 255))
    title_font = font(74)
    subtitle_font = font(30)
    draw = ImageDraw.Draw(base)
    title_lines = wrap_text(title, draw, title_font, TARGET_SIZE[0] - 140)
    y = 430 - (len(title_lines) - 1) * 42
    draw.rectangle((0, 0, 12, TARGET_SIZE[1]), fill=accent)
    for line in title_lines:
        draw.text((64, y), line, font=title_font, fill=(255, 255, 255, 255), stroke_width=3, stroke_fill=(0, 0, 0, 185))
        y += 84
    if subtitle:
        draw.text((68, min(y + 10, 650)), subtitle, font=subtitle_font, fill=(255, 255, 255, 230), stroke_width=2, stroke_fill=(0, 0, 0, 160))
    paste_logo(base)
    output.parent.mkdir(parents=True, exist_ok=True)
    base.convert("RGB").save(output, quality=94)
    return {"title": title, "subtitle": subtitle, "width": TARGET_SIZE[0], "height": TARGET_SIZE[1]}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a project thumbnail from the current app runtime config.")
    parser.add_argument("--time", default=text_value(APP_CONFIG, "thumbnail", "time", default=text_value(APP_CONFIG, "workflow", "stillTime", default="00:00:25")))
    parser.add_argument("--output", type=Path, default=output_path())
    args = parser.parse_args()

    video = source_video()
    with tempfile.TemporaryDirectory(prefix="video_edit_thumbnail_") as tmp:
        frame_path = Path(tmp) / "frame.png"
        extract_frame(video, args.time, frame_path)
        render_info = render_thumbnail(frame_path, args.output)
    report = {"output": str(args.output), "input": str(video), "time": args.time, **render_info}
    report_path = args.output.with_suffix(".json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
