from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


PROJECT = Path(__file__).resolve().parents[1]
STATE = PROJECT / "project_state.json"
VIDEOS = PROJECT / "output" / "videos"
REPORTS = PROJECT / "output" / "reports"
DEFAULT_OUTPUT = VIDEOS / "preview_240p.mp4"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Configure engineer-type project_state for fast 240p preview renders.")
    parser.add_argument("--height", type=int, default=240, help="Preview output height.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Preview output path.")
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Optional previewDuration override. Omit to keep the reviewed-video full range.",
    )
    parser.add_argument(
        "--start",
        type=float,
        default=None,
        help="Optional absolute source previewStart override. Omit to keep the reviewed-video start trim.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    state = read_json(STATE)
    render = state.setdefault("render", {})
    reviewed_trim = render.get("reviewedVideoSourceTrim") if isinstance(render.get("reviewedVideoSourceTrim"), dict) else {}
    source_duration = float(reviewed_trim.get("sourceDurationSeconds") or 0.0)
    start_trim = float(reviewed_trim.get("startSeconds") or render.get("previewStart") or 0.0)
    end_trim = float(reviewed_trim.get("endSeconds") or 0.0)

    render["renderProfile"] = "preview"
    render["rangeMode"] = "range"
    render["outputHeight"] = int(args.height)
    render["outputPath"] = str(args.output)
    render["previewStart"] = float(args.start) if args.start is not None else start_trim
    if args.duration is not None:
        render["previewDuration"] = max(0.1, float(args.duration))
    elif source_duration > 0:
        render["previewDuration"] = max(0.1, source_duration - start_trim - end_trim)
    render["subtitleOverlayFormat"] = "png"
    render["previewPreset"] = {
        "name": "fast-240p-proxy",
        "usesRenderProfile": "preview",
        "outputHeight": int(args.height),
        "proxyProfile": "h264-960p-ultrafast-crf28",
        "notes": [
            "Preview profile uses generated media proxies when available.",
            "Preview profile skips silence shortening inside render_multicam.py.",
            "Full transcript PNG overlays are generated through the cached generator.",
        ],
    }

    proxy = state.setdefault("proxy", {})
    proxy.setdefault("outputDir", str(PROJECT / "output" / "proxy"))
    REPORTS.mkdir(parents=True, exist_ok=True)
    write_json(STATE, state)
    print(
        json.dumps(
            {
                "projectState": str(STATE),
                "renderProfile": render.get("renderProfile"),
                "outputHeight": render.get("outputHeight"),
                "outputPath": render.get("outputPath"),
                "previewStart": render.get("previewStart"),
                "previewDuration": render.get("previewDuration"),
                "proxyOutputDir": proxy.get("outputDir"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
