from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parents[1]
TRANSCRIPTS = PROJECT / "output" / "transcripts" / "manifest_sources"
REPORTS = PROJECT / "output" / "reports"
OVERLAYS = PROJECT / "output" / "overlays" / "review_fixes"
STATE = PROJECT / "project_state.json"

SUBTITLE_SOURCE_OFFSET = 8.7
OLD_TEXT = "ここのカスタマイズ"
NEW_TEXT = "個々のカスタマイズ"
REVIEWED_VIDEO_SOURCE_START_CUT_SECONDS = 85.0
REVIEWED_VIDEO_SOURCE_END_CUT_SECONDS = 20.0


def reviewed_time_to_source_time(reviewed_seconds: float) -> float:
    return REVIEWED_VIDEO_SOURCE_START_CUT_SECONDS + reviewed_seconds


def subtitle_time_to_source_time(subtitle_seconds: float) -> float:
    return subtitle_seconds - SUBTITLE_SOURCE_OFFSET


def timestamp(total_seconds: float) -> str:
    total_seconds = max(0.0, float(total_seconds))
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = total_seconds - hours * 3600 - minutes * 60
    return f"{hours}:{minutes:02d}:{seconds:06.3f}"


def backup_once(path: Path) -> None:
    backup = path.with_suffix(path.suffix + ".before_review_fix")
    if path.exists() and not backup.exists():
        backup.write_bytes(path.read_bytes())


def replace_text_recursive(value: Any) -> Any:
    if isinstance(value, str):
        return value.replace(OLD_TEXT, NEW_TEXT)
    if isinstance(value, list):
        return [replace_text_recursive(item) for item in value]
    if isinstance(value, dict):
        return {key: replace_text_recursive(item) for key, item in value.items()}
    return value


def apply_subtitle_wording() -> None:
    for path in (
        TRANSCRIPTS / "external_140101-003.reviewed.srt",
        TRANSCRIPTS / "external_140101-003.reviewed.json",
    ):
        backup_once(path)
    srt = TRANSCRIPTS / "external_140101-003.reviewed.srt"
    srt.write_text(srt.read_text(encoding="utf-8").replace(OLD_TEXT, NEW_TEXT), encoding="utf-8")

    reviewed_json = TRANSCRIPTS / "external_140101-003.reviewed.json"
    payload = json.loads(reviewed_json.read_text(encoding="utf-8"))
    payload = replace_text_recursive(payload)
    reviewed_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def apply_chapter_titles() -> None:
    path = REPORTS / "chapter_titles_from_full_transcript.json"
    backup_once(path)

    # Review timestamps are based on the reviewed video, which already removed
    # the first 1:25 and final 0:20 from the source render. The renderer stores
    # overlay times as source timeline positions, then subtracts the external
    # subtitle sync offset while loading overlays.
    rows = [
        (0.0, 245.0, "強いプロダクト", "強いプロダクトの条件とFDEの前提を整理する導入。"),
        (245.0, 390.0, "既にFDE的に働く人", "既存職種の中にあるFDE的な働き方を整理する。"),
        (390.0, 592.0, "FDEブームの正体", "FDE流行の背景と採用マーケティングの文脈。"),
        (628.0, 904.0, "FDE向きプロダクト", "FDEが必要になるプロダクト条件とカスタマイズ性。"),
        (904.0, 1037.0, "日本企業でワークするか", "日本企業・SI文化・受託文化との相性。"),
        (1037.0, 1346.0, "PDM vs FDE論争", "PDM廃止論とFDE化の論点整理。"),
        (1346.0, 1680.0, "日本の職種設計", "ジョブディスクリプションと職種設計の違い。"),
        (1680.0, 1920.0, "職種分化と再統合", "AI時代の職種分化と再統合。"),
        (1920.0, 2160.0, "PMの本質は統合", "プロダクトマネージャーのコア価値を整理する。"),
        (2160.0, 2400.0, "FDE導入の条件", "FDEを導入すべき事業条件を整理する。"),
        (2400.0, 2640.0, "仕事の対価を考える", "仕事の価値と対価を収益から捉え直す。"),
        (2640.0, 2880.0, "FDEに向く人", "FDEに向く人のマインドセット。"),
        (2880.0, 3178.0, "AI時代の人の価値", "AI時代に残るエンジニア経験と人の価値。"),
    ]
    payload = {
        "sourceSubtitle": str(TRANSCRIPTS / "external_140101-003.reviewed.srt"),
        "method": "review_result.md corrections applied; stored times include subtitle sync offset for chapter overlay rendering.",
        "chapters": [
            {
                "start": timestamp(reviewed_time_to_source_time(start) + SUBTITLE_SOURCE_OFFSET),
                "end": timestamp(end + REVIEWED_VIDEO_SOURCE_START_CUT_SECONDS + SUBTITLE_SOURCE_OFFSET),
                "title": title,
                "topic": topic,
            }
            for start, end, title, topic in rows
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def font_path() -> Path:
    for candidate in (
        Path(r"C:\Windows\Fonts\YuGothB.ttc"),
        Path(r"C:\Windows\Fonts\meiryob.ttc"),
        Path(r"C:\Windows\Fonts\meiryo.ttc"),
    ):
        if candidate.exists():
            return candidate
    raise RuntimeError("Japanese font not found")


def generate_extra_text_overlay() -> Path:
    OVERLAYS.mkdir(parents=True, exist_ok=True)
    output = OVERLAYS / "fde_needed_product.png"
    font = ImageFont.truetype(str(font_path()), 43)
    text = "FDEが必要なプロダクトか"
    pad_x = 22
    pad_y = 12
    stripe = 7
    probe = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    draw = ImageDraw.Draw(probe)
    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0] + pad_x * 2
    height = bbox[3] - bbox[1] + pad_y * 2 + stripe
    image = Image.new("RGBA", (width, height), (255, 255, 255, 235))
    draw = ImageDraw.Draw(image)
    accent = (31, 135, 116, 245)
    draw.rectangle((0, height - stripe, width, height), fill=accent)
    draw.text((pad_x - bbox[0], pad_y - bbox[1]), text, font=font, fill=accent)
    image.save(output)
    return output


def write_extra_overlay_manifest(overlay: Path) -> Path:
    manifest = REPORTS / "review_extra_text_overlay_manifest.json"
    payload = [
        {
            "start": timestamp(reviewed_time_to_source_time(633.0)),
            "end": timestamp(reviewed_time_to_source_time(639.0)),
            "text": "FDEが必要なプロダクトか",
            "file": str(overlay),
        }
    ]
    manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def review_cut_ranges() -> list[dict[str, Any]]:
    def review_range(start: float, end: float, label: str) -> tuple[float, float, str]:
        return reviewed_time_to_source_time(start), reviewed_time_to_source_time(end), label

    def srt_range(start: float, end: float, label: str) -> tuple[float, float, str]:
        return subtitle_time_to_source_time(start), subtitle_time_to_source_time(end), label

    ranges = [
        srt_range(299.400, 302.000, "subtitle-only filler: 確かに"),
        srt_range(402.020, 403.940, "subtitle-only filler: なるほど確かに"),
        srt_range(421.120, 423.060, "subtitle-only filler: 確かに"),
        srt_range(483.180, 484.200, "review cut: 6:29 確かに prefix"),
        srt_range(553.720, 556.100, "review cut: 7:40 確かにありがとうございます"),
        review_range(626.000, 627.000, "review cut: 10:26-10:27"),
        review_range(679.000, 780.000, "review cut: 11:19-13:00"),
        review_range(805.000, 904.000, "review cut: 13:25-15:04, including 確かに確かに"),
        srt_range(970.880, 974.860, "subtitle-only filler: 確かに確かに"),
        srt_range(1269.760, 1271.040, "subtitle-only filler: 確かに"),
        srt_range(1314.640, 1317.400, "subtitle-only filler: 確かに"),
        srt_range(1458.680, 1462.100, "review cut: 22:47 確かにな"),
        srt_range(1511.920, 1513.080, "review cut: 23:39 確かにな"),
        review_range(1419.000, 1452.000, "review cut: 23:39-24:12"),
        srt_range(1746.980, 1748.480, "subtitle-only filler: 確かに"),
        srt_range(1808.400, 1810.380, "subtitle-only filler: 確かに"),
        srt_range(2023.280, 2024.840, "subtitle-only filler: 確かに確かに"),
        review_range(2137.000, 2248.000, "review cut: 35:37-37:28"),
        srt_range(2191.300, 2193.000, "subtitle-only filler: 確かに"),
        (
            reviewed_time_to_source_time(2542.000),
            subtitle_time_to_source_time(2681.260),
            "review cut: 42:22 to actual FDEに向いている人 start",
        ),
        srt_range(2812.460, 2814.900, "review cut: 45:17 確かに確かに"),
    ]
    return [{"start": start, "end": end, "label": label} for start, end, label in sorted(ranges, key=lambda item: item[0])]


def source_master_duration(state: dict[str, Any]) -> float:
    manifest = state.get("assets", {}).get("mediaManifest", {})
    candidates: list[dict[str, Any]] = []
    for key in ("items", "files"):
        value = manifest.get(key)
        if isinstance(value, list):
            candidates.extend(item for item in value if isinstance(item, dict))
    for item in candidates:
        if item.get("kind") != "video" or item.get("role") != "master":
            continue
        try:
            return float(item.get("metadata", {}).get("duration"))
        except (TypeError, ValueError):
            pass

    render = state.get("render", {})
    try:
        return (
            float(render.get("previewStart", 0.0) or 0.0)
            + float(render.get("previewDuration", 0.0) or 0.0)
            + REVIEWED_VIDEO_SOURCE_END_CUT_SECONDS
        )
    except (TypeError, ValueError):
        raise RuntimeError("Unable to determine master source duration for reviewed-video trim.")


def apply_reviewed_video_source_trim(state: dict[str, Any]) -> None:
    render = state.setdefault("render", {})
    master_duration = source_master_duration(state)
    trimmed_duration = master_duration - REVIEWED_VIDEO_SOURCE_START_CUT_SECONDS - REVIEWED_VIDEO_SOURCE_END_CUT_SECONDS
    if trimmed_duration <= 0:
        raise RuntimeError(
            "Reviewed-video trim is longer than the master source duration: "
            f"start={REVIEWED_VIDEO_SOURCE_START_CUT_SECONDS}, "
            f"end={REVIEWED_VIDEO_SOURCE_END_CUT_SECONDS}, duration={master_duration}"
        )
    render["previewStart"] = REVIEWED_VIDEO_SOURCE_START_CUT_SECONDS
    render["previewDuration"] = round(trimmed_duration, 6)
    render["reviewedVideoSourceTrim"] = {
        "startSeconds": REVIEWED_VIDEO_SOURCE_START_CUT_SECONDS,
        "endSeconds": REVIEWED_VIDEO_SOURCE_END_CUT_SECONDS,
        "sourceDurationSeconds": round(master_duration, 6),
        "reason": "Review was made against the derived file with the first 1m25s and last 20s removed.",
    }


def update_project_state(extra_manifest: Path) -> None:
    backup_once(STATE)
    state = json.loads(STATE.read_text(encoding="utf-8"))
    render = state.setdefault("render", {})
    apply_reviewed_video_source_trim(state)
    render["cutRanges"] = review_cut_ranges()
    render["extraOverlayManifests"] = [
        {
            "path": str(extra_manifest),
            "x_expr": "70",
            "y_expr": "310",
            "sourceOffsetSeconds": 0,
        }
    ]
    style = state.setdefault("style", {})
    style["chapterTitlesEnabled"] = True
    style["chapterTitlesPath"] = str(REPORTS / "chapter_titles_from_full_transcript.json")
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    apply_subtitle_wording()
    apply_chapter_titles()
    overlay = generate_extra_text_overlay()
    manifest = write_extra_overlay_manifest(overlay)
    update_project_state(manifest)
    (REPORTS / "review_cut_ranges.json").write_text(json.dumps(review_cut_ranges(), ensure_ascii=False, indent=2), encoding="utf-8")
    state = json.loads(STATE.read_text(encoding="utf-8"))
    reviewed_trim = state.get("render", {}).get("reviewedVideoSourceTrim", {})
    print(
        json.dumps(
            {
                "subtitleCorrection": f"{OLD_TEXT} -> {NEW_TEXT}",
                "reviewedVideoSourceTrim": reviewed_trim,
                "chapterTitles": str(REPORTS / "chapter_titles_from_full_transcript.json"),
                "extraOverlay": str(manifest),
                "cutRanges": str(REPORTS / "review_cut_ranges.json"),
                "projectState": str(STATE),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
