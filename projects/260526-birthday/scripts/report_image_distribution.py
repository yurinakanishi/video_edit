from __future__ import annotations

import argparse
import json
import math
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


LANE_SECONDS = 300.0


@dataclass
class Block:
    kind: str
    start: float
    end: float
    label: str
    source_key: str
    labels: list[str]

    @property
    def count(self) -> int:
        return len(self.labels)


def mmss(seconds: float) -> str:
    total = int(round(seconds))
    return f"{total // 60:02d}:{total % 60:02d}"


def media_label(item: dict) -> str:
    return str(item.get("sourceLabel") or Path(str(item.get("path", ""))).name)


def video_source_key(item: dict) -> str:
    stem = Path(media_label(item)).stem
    match = re.search(r"_clip(?:_|[0-9])", stem, re.IGNORECASE)
    if match:
        stem = stem[: match.start()]
    return stem


def image_short_name(label: str) -> str:
    stem = Path(label).stem
    stem = re.sub(r"^photo_\d+_", "", stem, flags=re.IGNORECASE)
    return stem


def short_video_name(label: str) -> str:
    stem = Path(label).stem
    stem = re.sub(r"_clip.*$", "", stem, flags=re.IGNORECASE)
    return stem


def compact_label(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max(1, max_chars - 1)] + "..."


def build_blocks(media: list[dict]) -> list[Block]:
    blocks: list[Block] = []
    for item in media:
        kind = str(item.get("kind"))
        start = float(item.get("timelineStart", 0.0))
        end = float(item.get("timelineEnd", start))
        label = media_label(item)
        if kind == "video":
            key = video_source_key(item)
            display = short_video_name(key)
            if blocks and blocks[-1].kind == "video" and blocks[-1].source_key == key and abs(blocks[-1].end - start) < 0.08:
                blocks[-1].end = end
                blocks[-1].labels.append(label)
                continue
            blocks.append(Block("video", start, end, display, key, [label]))
        elif kind == "image":
            key = image_short_name(label)
            if blocks and blocks[-1].kind == "image" and abs(blocks[-1].end - start) < 0.08:
                blocks[-1].end = end
                blocks[-1].labels.append(label)
                blocks[-1].source_key += f",{key}"
                continue
            blocks.append(Block("image", start, end, key, key, [label]))
    return blocks


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def draw_fit(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, fill: str, fnt: ImageFont.ImageFont, width: int) -> None:
    if width <= 12:
        return
    avg = max(4, int(fnt.size * 0.54)) if hasattr(fnt, "size") else 7
    text = compact_label(text, max(1, width // avg))
    draw.text(xy, text, fill=fill, font=fnt)


def render_png(blocks: list[Block], duration: float, output: Path) -> None:
    width = 1800
    left = 92
    right = 48
    lane_width = width - left - right
    row_height = 156
    header = 92
    rows = max(1, math.ceil(duration / LANE_SECONDS))
    height = header + rows * row_height + 44
    image = Image.new("RGB", (width, height), "#fbfaf7")
    draw = ImageDraw.Draw(image)
    title_font = font(25, bold=True)
    body_font = font(15)
    small_font = font(12)
    label_font = font(13, bold=True)

    draw.text((34, 24), "Image distribution timeline", fill="#24201c", font=title_font)
    draw.text((34, 58), "Videos are grouped by original source; cut clips from the same source use the same video label.", fill="#5d5750", font=body_font)
    draw.rectangle((1020, 28, 1054, 48), fill="#7fa8cc")
    draw.text((1064, 24), "video source", fill="#332f2a", font=body_font)
    draw.rectangle((1195, 28, 1229, 48), fill="#eba75d")
    draw.text((1239, 24), "image block", fill="#332f2a", font=body_font)

    video_fill = "#7fa8cc"
    image_fill = "#eba75d"
    video_outline = "#4f789d"
    image_outline = "#ad6a24"
    grid = "#d8d2ca"
    text_dark = "#26221f"

    for row in range(rows):
        row_start = row * LANE_SECONDS
        row_end = min(duration, row_start + LANE_SECONDS)
        y = header + row * row_height
        draw.text((26, y + 18), f"{mmss(row_start)}", fill=text_dark, font=label_font)
        draw.line((left, y + 50, left + lane_width, y + 50), fill="#bdb6ad", width=2)
        tick = math.ceil(row_start / 60.0) * 60.0
        while tick <= row_end + 0.01:
            x = int(left + ((tick - row_start) / LANE_SECONDS) * lane_width)
            draw.line((x, y + 36, x, y + 132), fill=grid, width=1)
            draw.text((x - 15, y + 18), mmss(tick), fill="#6c655d", font=small_font)
            tick += 60.0
        draw.text((left - 56, y + 64), "VIDEO", fill="#4f789d", font=small_font)
        draw.text((left - 52, y + 104), "IMAGE", fill="#ad6a24", font=small_font)

        for block in blocks:
            if block.end <= row_start or block.start >= row_end:
                continue
            seg_start = max(block.start, row_start)
            seg_end = min(block.end, row_end)
            x1 = int(left + ((seg_start - row_start) / LANE_SECONDS) * lane_width)
            x2 = int(left + ((seg_end - row_start) / LANE_SECONDS) * lane_width)
            x2 = max(x1 + 3, x2)
            if block.kind == "video":
                y1, y2 = y + 60, y + 88
                draw.rectangle((x1, y1, x2, y2), fill=video_fill, outline=video_outline)
                draw_fit(draw, (x1 + 4, y1 + 5), block.label, "#10283a", small_font, x2 - x1 - 8)
            else:
                y1, y2 = y + 98, y + 130
                draw.rectangle((x1, y1, x2, y2), fill=image_fill, outline=image_outline)
                short_names = [image_short_name(label) for label in block.labels]
                label = f"IMG x{block.count}: " + ", ".join(short_names)
                draw_fit(draw, (x1 + 4, y1 + 7), label, "#40250b", small_font, x2 - x1 - 8)
                draw.line((x1, y1 - 8, x1, y2 + 6), fill=image_outline, width=2)

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)


def write_markdown(blocks: list[Block], duration: float, output: Path) -> None:
    image_blocks = [block for block in blocks if block.kind == "image"]
    single_between = []
    for index, block in enumerate(blocks):
        if block.kind == "image" and block.count == 1:
            prev_block = blocks[index - 1] if index > 0 else None
            next_block = blocks[index + 1] if index + 1 < len(blocks) else None
            if prev_block and next_block and prev_block.kind == "video" and next_block.kind == "video":
                single_between.append(block)

    lines = [
        "# Image Distribution Report",
        "",
        f"- Timeline duration: `{mmss(duration)}`",
        f"- Image blocks: `{len(image_blocks)}`",
        f"- Total images in timeline: `{sum(block.count for block in image_blocks)}`",
        f"- Single-image gaps between videos: `{len(single_between)}`",
        "",
        "## Image Blocks",
        "",
        "| # | Time | Count | Images | Previous Video | Next Video |",
        "|---:|---|---:|---|---|---|",
    ]
    for image_index, block in enumerate(image_blocks, start=1):
        block_index = blocks.index(block)
        prev_video = next((blocks[i] for i in range(block_index - 1, -1, -1) if blocks[i].kind == "video"), None)
        next_video = next((blocks[i] for i in range(block_index + 1, len(blocks)) if blocks[i].kind == "video"), None)
        images = ", ".join(image_short_name(label) for label in block.labels)
        lines.append(
            "| {idx} | `{start}-{end}` | {count} | {images} | {prev} | {next} |".format(
                idx=image_index,
                start=mmss(block.start),
                end=mmss(block.end),
                count=block.count,
                images=images,
                prev=prev_video.label if prev_video else "(start)",
                next=next_video.label if next_video else "(end)",
            )
        )

    lines.extend(["", "## Full Block Sequence", "", "| # | Time | Type | Details |", "|---:|---|---|---|"])
    for index, block in enumerate(blocks, start=1):
        if block.kind == "image":
            details = f"{block.count} images: " + ", ".join(image_short_name(label) for label in block.labels)
        else:
            clip_note = f" ({block.count} connected cuts)" if block.count > 1 else ""
            details = f"{block.label}{clip_note}"
        wrapped = "<br>".join(textwrap.wrap(details, width=88)) if len(details) > 88 else details
        lines.append(f"| {index} | `{mmss(block.start)}-{mmss(block.end)}` | {block.kind} | {wrapped} |")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--timeline", type=Path)
    args = parser.parse_args()
    project_root = args.project_root
    timeline = args.timeline or project_root / "output" / "reports" / "birthday_preview" / "birthday_preview_timeline.json"
    data = json.loads(timeline.read_text(encoding="utf-8"))
    media = list(data.get("media", []))
    duration = float(data.get("duration", 0.0))
    blocks = build_blocks(media)
    output_dir = project_root / "output" / "reports" / "birthday_preview"
    png = output_dir / "image_distribution_timeline.png"
    markdown = output_dir / "image_distribution_report.md"
    render_png(blocks, duration, png)
    write_markdown(blocks, duration, markdown)
    print(json.dumps({"png": str(png), "markdown": str(markdown), "blocks": len(blocks)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
