from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from video_edit_core.paths import OUTPUT_REPORTS, SCRIPTS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate person bbox JSON and segment-level edit plans.")
    parser.add_argument("--input", nargs="*", default=[])
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_REPORTS / "person_bboxes")
    parser.add_argument("--plan-output-dir", type=Path, default=OUTPUT_REPORTS / "person_edit_plans")
    parser.add_argument("--model", default="yolov8n.pt")
    parser.add_argument("--confidence", type=float, default=0.35)
    parser.add_argument("--fps-sample", type=float, default=1.0)
    parser.add_argument("--start", type=float, default=0.0)
    parser.add_argument("--end", type=float, default=None)
    parser.add_argument("--max-seconds", type=float, default=None)
    parser.add_argument("--device", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--max-duration", type=float, default=None)
    parser.add_argument("--merge-gap", type=float, default=1.25)
    parser.add_argument("--min-segment", type=float, default=1.0)
    parser.add_argument("--reference-profile-output", type=Path, default=None)
    parser.add_argument("--no-multicam-root", action="store_true")
    return parser.parse_args()


def append_optional(command: list[str], flag: str, value: object | None) -> None:
    if value is not None and value != "":
        command.extend([flag, str(value)])


def main() -> None:
    args = parse_args()
    analyze_command = [
        sys.executable,
        str(SCRIPTS / "analyze_person_bboxes.py"),
        "--output-dir",
        str(args.output_dir),
        "--model",
        args.model,
        "--confidence",
        str(args.confidence),
        "--fps-sample",
        str(args.fps_sample),
        "--start",
        str(args.start),
    ]
    append_optional(analyze_command, "--end", args.end)
    append_optional(analyze_command, "--max-seconds", args.max_seconds)
    append_optional(analyze_command, "--device", args.device)
    append_optional(analyze_command, "--limit", args.limit)
    append_optional(analyze_command, "--max-duration", args.max_duration)
    if args.no_multicam_root:
        analyze_command.append("--no-multicam-root")
    if args.input:
        analyze_command.append("--input")
        analyze_command.extend(args.input)

    subprocess.run(analyze_command, check=True)

    plan_command = [
        sys.executable,
        str(SCRIPTS / "build_person_edit_plan.py"),
        "--input-dir",
        str(args.output_dir),
        "--output-dir",
        str(args.plan_output_dir),
        "--merge-gap",
        str(args.merge_gap),
        "--min-segment",
        str(args.min_segment),
    ]
    subprocess.run(plan_command, check=True)

    if args.reference_profile_output:
        profile_command = [
            sys.executable,
            str(SCRIPTS / "build_reference_edit_profile.py"),
            "--input-dir",
            str(args.output_dir),
            "--plan-dir",
            str(args.plan_output_dir),
            "--output",
            str(args.reference_profile_output),
        ]
        subprocess.run(profile_command, check=True)


if __name__ == "__main__":
    main()
