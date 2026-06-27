from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageEnhance, ImageOps


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "assets" / "tokyo_oasis_youtube_original_photos_stacked_16x9.png"
PREVIEW = ROOT / "output" / "assets" / "tokyo_oasis_youtube_original_photos_stacked_16x9_matched_faces.png"

HANAOKA_SOURCE = (
    ROOT.parents[0]
    / "hanaoka_hiroyuki_tokyo_oasis_radio"
    / "source"
    / "images"
    / "東京オアシス20260205_img1.jpg"
)
YURI_SOURCE = (
    ROOT.parents[0]
    / "yuri_nakanishi_tokyo_oasis_radio"
    / "source"
    / "thumbnail_yuri_nakanishi.jpg"
)


def crop_band(
    image: Image.Image,
    *,
    out_width: int,
    out_height: int,
    zoom: float,
    focus_x: float,
    focus_y: float,
) -> Image.Image:
    base_scale = out_width / image.width
    scale = base_scale * zoom
    resized = image.resize(
        (round(image.width * scale), round(image.height * scale)),
        Image.Resampling.LANCZOS,
    )
    max_left = max(0, resized.width - out_width)
    max_top = max(0, resized.height - out_height)
    left = round(max_left * max(0.0, min(1.0, focus_x)))
    top = round(max_top * max(0.0, min(1.0, focus_y)))
    return resized.crop((left, top, left + out_width, top + out_height))


def open_photo(path: Path) -> Image.Image:
    return ImageOps.exif_transpose(Image.open(path)).convert("RGB")


def main() -> None:
    canvas_width, canvas_height = 1920, 1080
    band_height = canvas_height // 2

    hanaoka = open_photo(HANAOKA_SOURCE)
    yuri = open_photo(YURI_SOURCE)

    top_band = crop_band(
        hanaoka,
        out_width=canvas_width,
        out_height=band_height,
        zoom=1.58,
        focus_x=0.537,
        focus_y=0.40,
    )
    bottom_band = crop_band(
        yuri,
        out_width=canvas_width,
        out_height=band_height,
        zoom=1.02,
        focus_x=0.958,
        focus_y=0.19,
    )

    canvas = Image.new("RGB", (canvas_width, canvas_height), (255, 255, 255))
    canvas.paste(top_band, (0, 0))
    canvas.paste(bottom_band, (0, band_height))
    canvas = ImageEnhance.Color(canvas).enhance(0.96)
    canvas = ImageEnhance.Contrast(canvas).enhance(1.02)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(OUTPUT, format="PNG", optimize=False)
    canvas.save(PREVIEW, format="PNG", optimize=False)
    print(OUTPUT)
    print(PREVIEW)
    print(f"{canvas.width}x{canvas.height}")


if __name__ == "__main__":
    main()
