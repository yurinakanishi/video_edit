from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REFERENCE = PROJECT_ROOT / "reference"
REPORTS = PROJECT_ROOT / "output" / "reports"
ANALYSIS_DIR = REPORTS / "reference_image_analysis"
JST = timezone(timedelta(hours=9))


def now_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def image_info(path: Path) -> dict:
    with Image.open(path).convert("RGBA") as image:
        return {"width": image.width, "height": image.height}


def main() -> None:
    refs = [
        {
            "id": "caption_style_gradient_large_two_line_reference_a",
            "path": REFERENCE / "caption-style-gradient-large-two-line-reference-a.png",
            "observed_caption_lines": 1,
            "observed_text": "論点にこだわり続けられる人",
            "caption_box_norm": {"x": 0.034, "y": 0.786, "w": 0.929, "h": 0.139},
        },
        {
            "id": "caption_style_gradient_large_two_line_reference_b",
            "path": REFERENCE / "caption-style-gradient-large-two-line-reference-b.png",
            "observed_caption_lines": 2,
            "observed_text": "より自律的に動ける人かが / すごく大事になってきている",
            "caption_box_norm": {"x": 0.067, "y": 0.624, "w": 0.871, "h": 0.281},
        },
    ]
    analyses = []
    for ref in refs:
        info = image_info(ref["path"])
        analysis = {
            "schema_version": "reference_image_analysis.v1",
            "reference_id": ref["id"],
            "source_image": str(ref["path"].relative_to(PROJECT_ROOT)),
            "generated_at": now_iso(),
            "image": info,
            "purpose": "Caption subtitle style reference for all editorial captions in digest and main sections.",
            "caption_style": {
                "text_color": "#FFFFFF",
                "font_family": "Yu Gothic / Japanese bold sans-serif",
                "font_weight": "heavy_bold",
                "black_stroke": False,
                "shadow": "none or extremely subtle; no visible black outline",
                "font_size_ratio_to_720p_height": 0.083,
                "target_font_size_720p": 60,
                "min_font_size_720p": 46,
                "line_height_720p": 76,
                "inter_line_gap_720p": 8,
                "box_padding_x_720p": 30,
                "box_padding_y_720p": 8,
                "box_radius_720p": 5,
                "box_gradient": {
                    "direction": "left_to_right",
                    "stops": ["#4015E8", "#6333F4", "#7B63F7"],
                    "opacity": 0.96,
                },
                "placement": {
                    "lower_third_centered": True,
                    "bottom_safe_margin_720p": 54,
                    "two_line_stack_uses_independent_boxes": True,
                    "vertical_gap_between_boxes_720p": 8,
                },
                "animation": {
                    "entry": "horizontal_reveal",
                    "secondary_line_stagger_sec": 0.12,
                    "fade_out_sec": 0.10,
                },
            },
            "observations": {
                "observed_caption_lines": ref["observed_caption_lines"],
                "observed_text": ref["observed_text"],
                "caption_box_norm": ref["caption_box_norm"],
                "top_band": "blue-purple gradient header with white slanted logo panel",
                "topic_title": "white bold text in the top-right header",
            },
            "renderer_requirements": [
                "Use this caption style for all caption overlays, not only digest captions.",
                "Use large heavy white text without black stroke.",
                "Use tight stacked boxes for two-line captions.",
                "Match the blue-purple gradient and box padding from this reference.",
            ],
        }
        out = ANALYSIS_DIR / f"{ref['id']}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
        analyses.append({"reference_id": ref["id"], "analysis_path": str(out)})
    manifest = {
        "schema_version": "caption_reference_manifest.v1",
        "generated_at": now_iso(),
        "references": analyses,
    }
    (ANALYSIS_DIR / "caption-style-gradient-large-two-line-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
