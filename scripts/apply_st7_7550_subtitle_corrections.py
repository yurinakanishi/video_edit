from __future__ import annotations

import re
from dataclasses import dataclass
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


WORK = WORKSPACE_ROOT
RAW_SRT = SOURCE_SUBTITLES / "video_original_audio" / "ST7_7550_overlap_5min_original_audio.srt"
CORRECTED_SRT = SOURCE_SUBTITLES / "video_original_audio" / "ST7_7550_overlap_5min_original_audio_corrected.srt"

SPECIAL_CORRECTIONS = {
    5: "そこで一定なスケールメリットが 出るということが大事だと思いますね",
    9: "ある程度先ほどの話の中からも お伺いできているところがあるので",
    12: "もう一度ちょっと聞きたいんですが",
    13: "そもそもあの論争について",
    15: "どうしてああいう論争になっちゃうのかな というところに関してはどう感じますか",
    18: "そうです、ありがとうございます",
    21: "別になんて言うかな",
}


@dataclass
class Caption:
    index: int
    timing: str
    text: str


def parse_srt(path: Path) -> list[Caption]:
    blocks = re.split(r"\n\s*\n", path.read_text(encoding="utf-8-sig").strip())
    captions: list[Caption] = []
    for block in blocks:
        rows = [row.strip() for row in block.splitlines() if row.strip()]
        if len(rows) < 3 or "-->" not in rows[1]:
            continue
        captions.append(Caption(index=int(rows[0]), timing=rows[1], text=" ".join(rows[2:])))
    return captions


def write_srt(path: Path, captions: list[Caption]) -> None:
    rows: list[str] = []
    for caption in captions:
        rows.extend(
            [
                str(caption.index),
                caption.timing,
                SPECIAL_CORRECTIONS.get(caption.index, caption.text),
                "",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(rows), encoding="utf-8")


def main() -> None:
    captions = parse_srt(RAW_SRT)
    write_srt(CORRECTED_SRT, captions)
    print(f"wrote {CORRECTED_SRT}")


if __name__ == "__main__":
    main()
