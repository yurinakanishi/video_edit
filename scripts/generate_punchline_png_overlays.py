from __future__ import annotations

import json
from dataclasses import asdict, dataclass
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

from PIL import Image, ImageDraw, ImageFont

from subtitle_png_style import FONT_PATH, render_caption, tracked_text_width
from video_edit_app_config import hex_rgba, int_value, load_app_config, nested, opacity_alpha, parse_punchline_text


WORK = WORKSPACE_ROOT
OUT_DIR = OUTPUT_OVERLAYS / "punchline_png_overlays"
FONT_SIZE = 100
MAX_IMAGE_WIDTH = 1760
PAD_X = 18
STROKE = 2
APP_CONFIG = load_app_config()

@dataclass(frozen=True)
class Punchline:
    start: str
    end: str
    lines: tuple[str, ...]


PUNCHLINES = [
    Punchline("0:00:00.00", "0:00:09.00", ("定義で言うと強いプロダクトというか", "プロダクトが中心にあって", "セミオゴーだとかセミカスタマイズの形で")),
    Punchline("0:00:15.00", "0:00:20.00", ("そこで一定なスケールメリットが", "出るということが大事だと思いますね")),
    Punchline("0:01:27.00", "0:01:37.00", ("さすがに薄々AIによって", "何かが変わるなっていうのは", "みんな覚悟してるというか")),
    Punchline("0:01:41.00", "0:01:53.00", ("ちょっとした会社の発表だったりとか", "ちょっとしたノートの発言だったり", "っていうのに過剰反応しやすいような", "土壌自体は多分ある")),
    Punchline("0:01:56.00", "0:02:02.00", ("あなたの仕事例えばライターの仕事", "明日から亡くなりますよって言われたら")),
    Punchline("0:02:17.00", "0:02:29.00", ("会社がわざわざPDM配信して", "フリーEにしましたみたいなのは", "採用におけるマーケティングの一環なのかなと思いますね")),
    Punchline("0:02:29.00", "0:02:41.00", ("同じような職種名だと埋もれるんで", "興味持ってもらうっていうのは", "そのための一つの工夫なんだろうなと思います")),
    Punchline("0:03:01.00", "0:03:13.00", ("採用救人状の話だったけで", "家事ある面談とか面接を通して", "こういう役割を求めてるのをすり合うパターンもある")),
    Punchline("0:03:41.00", "0:03:49.00", ("会社によってビジネスのモデルとか", "通用見とかっていうのは", "かなり多種多様なんですよね")),
    Punchline("0:04:06.00", "0:04:22.00", ("なんでユーザーさんに必要されているか", "みたいなところって多様性もあるし", "工夫してなかったら生き残っていけない")),
    Punchline("0:04:25.00", "0:04:37.00", ("大まかな専門職的なこの仕事が必要", "というのはもちろんありますと", "その会社の中で何を求められるか", "というのは多様性がありますよ")),
    Punchline("0:04:40.00", "0:04:59.00", ("専門職という言葉が", "結構ミスリートというか", "エンジニアとか分かりやすすぎるだけで", "総合職って全く分からないですよね")),
]


def configured_font_size() -> int:
    return int_value(APP_CONFIG, "style", "subtitleSize", default=FONT_SIZE)


def configured_punchlines() -> list[Punchline]:
    text = nested(APP_CONFIG, "style", "punchlineText", default="")
    if isinstance(text, str) and text.strip():
        parsed = parse_punchline_text(text)
        if parsed:
            return [Punchline(item["start"], item["end"], tuple(item["lines"])) for item in parsed]
    return PUNCHLINES


def line_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=STROKE)
    return tracked_text_width(draw, text, font, STROKE) if len(text) > 1 else bbox[2] - bbox[0]


def split_line_naturally(line: str, draw: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont) -> tuple[str, str]:
    break_chars = "、。，．・／/）)]」』"
    particles = ("は", "が", "を", "に", "で", "と", "も", "へ", "から", "まで", "より", "って", "という", "ので", "けど")
    best_index = max(1, min(len(line) - 1, len(line) // 2))
    best_score = 10**9
    for index in range(1, len(line)):
        left = line[:index].rstrip()
        right = line[index:].lstrip()
        if not left or not right:
            continue
        score = abs(line_width(draw, left, font) - line_width(draw, right, font))
        if line[index - 1] in break_chars:
            score -= 900
        if any(left.endswith(particle) for particle in particles):
            score -= 550
        if line[index:index + 1] in "、。，．・":
            score -= 550
        if score < best_score:
            best_score = score
            best_index = index
    return line[:best_index].rstrip(), line[best_index:].lstrip()


def wrap_lines(lines: tuple[str, ...]) -> tuple[str, ...]:
    font_size = configured_font_size()
    font = ImageFont.truetype(str(FONT_PATH), font_size, index=1)
    probe = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    draw = ImageDraw.Draw(probe)
    max_text_width = MAX_IMAGE_WIDTH - PAD_X * 2
    wrapped = [line.replace(" ", "").replace("\t", "") for line in lines]
    while any(line_width(draw, line, font) > max_text_width for line in wrapped):
        widest_index = max(range(len(wrapped)), key=lambda i: line_width(draw, wrapped[i], font))
        left, right = split_line_naturally(wrapped[widest_index], draw, font)
        if not left or not right:
            break
        wrapped[widest_index:widest_index + 1] = [left, right]
    return tuple(wrapped)


def render_punchline(lines: tuple[str, ...]) -> Image.Image:
    font_size = configured_font_size()
    accent = hex_rgba(nested(APP_CONFIG, "style", "highlightColor"), default=(216, 0, 0, 255))
    alpha = opacity_alpha(nested(APP_CONFIG, "style", "boxOpacity"), 255)
    return render_caption(
        wrap_lines(lines),
        font_size,
        stroke=STROKE,
        pad_x=PAD_X,
        pad_y=8,
        shadow=12,
        line_gap=0,
        box_fill=(255, 255, 255, max(alpha, 180)),
        text_fill=accent,
        shadow_fill=accent,
    )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    for index, punchline in enumerate(configured_punchlines(), start=1):
        image = render_punchline(punchline.lines)
        wrapped_lines = wrap_lines(punchline.lines)
        filename = f"punchline_{index:02d}.png"
        image.save(OUT_DIR / filename)
        manifest.append(
            {
                **asdict(Punchline(punchline.start, punchline.end, wrapped_lines)),
                "file": str((OUT_DIR / filename).relative_to(WORK)),
                "width": image.width,
                "height": image.height,
            }
        )
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
