from __future__ import annotations

import json
import re
from collections import defaultdict
from difflib import SequenceMatcher
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
from statistics import median


WORK = WORKSPACE_ROOT
MASTER = SOURCE_SUBTITLES / "video_original_audio" / "ST7_7550_overlap_5min_original_audio.srt"
SOUND_TRANSCRIPTS = OUTPUT_TRANSCRIPTS / "sound2"
OUTPUT = OUTPUT_TRANSCRIPTS / "sound2" / "sound2_master_matches.json"


def normalize(text: str) -> str:
    return re.sub(r"[\s、。,.!?！？「」『』（）()・ー\-]", "", text)


def ts_to_seconds(ts: str) -> float:
    ts = ts.replace(",", ".")
    h, m, s = ts.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def read_srt(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8-sig")
    blocks = re.split(r"\n\s*\n", text.strip())
    rows: list[dict] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 3 or "-->" not in lines[1]:
            continue
        start_raw, end_raw = [part.strip() for part in lines[1].split("-->")]
        body = " ".join(lines[2:])
        rows.append(
            {
                "start": ts_to_seconds(start_raw),
                "end": ts_to_seconds(end_raw),
                "text": body,
                "norm": normalize(body),
            }
        )
    return rows


def main() -> None:
    master = [row for row in read_srt(MASTER) if len(row["norm"]) >= 6]
    candidates = []
    by_file: dict[str, list[dict]] = defaultdict(list)
    for srt in sorted(SOUND_TRANSCRIPTS.glob("*.srt")):
        sound = [row for row in read_srt(srt) if len(row["norm"]) >= 6]
        for m in master:
            best = None
            for s in sound:
                ratio = SequenceMatcher(None, m["norm"], s["norm"]).ratio()
                if best is None or ratio > best["score"]:
                    best = {
                        "file": srt.name,
                        "score": ratio,
                        "master_start": m["start"],
                        "master_end": m["end"],
                        "sound_start": s["start"],
                        "sound_end": s["end"],
                        "offset": s["start"] - m["start"],
                        "master_text": m["text"],
                        "sound_text": s["text"],
                    }
            if best and best["score"] >= 0.72:
                candidates.append(best)
                by_file[best["file"]].append(best)

    summary = []
    for file, matches in by_file.items():
        strong = [m for m in matches if m["score"] >= 0.82]
        offsets = [m["offset"] for m in strong] or [m["offset"] for m in matches]
        summary.append(
            {
                "file": file,
                "match_count": len(matches),
                "strong_count": len(strong),
                "median_offset": median(offsets),
                "avg_score": sum(m["score"] for m in matches) / len(matches),
                "first_sound_start": min(m["sound_start"] for m in matches),
                "last_sound_start": max(m["sound_start"] for m in matches),
            }
        )
    summary.sort(key=lambda item: (item["strong_count"], item["match_count"], item["avg_score"]), reverse=True)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps({"summary": summary, "matches": candidates}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary:
        best_file = summary[0]["file"]
        best_matches = sorted(by_file[best_file], key=lambda item: item["score"], reverse=True)[:12]
        print("\nTop matches:")
        for item in best_matches:
            print(
                f"{item['file']} score={item['score']:.3f} "
                f"master={item['master_start']:.2f} sound={item['sound_start']:.2f} "
                f"offset={item['offset']:.2f} text={item['master_text']}"
            )


if __name__ == "__main__":
    main()
