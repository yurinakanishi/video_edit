from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


FFMPEG = Path(r"C:\ProgramData\chocolatey\bin\ffmpeg.exe")
WORK = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("VIDEO_EDIT_SOURCE_ROOT", r"C:\Users\yurin\Downloads\cdc260515 mov\cdc260515 mov"))


@dataclass(frozen=True)
class Segment:
    timeline_start: float
    timeline_end: float
    video_path: Path
    video_start: float

    @property
    def duration(self) -> float:
        return self.timeline_end - self.timeline_start


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def n(value: float) -> str:
    return f"{value:.3f}"


def build_segment(segment: Segment, audio_master: Path, output_path: Path) -> None:
    filters = (
        f"[0:v]trim=start={n(segment.video_start)}:duration={n(segment.duration)},"
        "setpts=PTS-STARTPTS[v];"
        f"[1:a]atrim=start={n(segment.timeline_start)}:duration={n(segment.duration)},"
        "asetpts=PTS-STARTPTS[a]"
    )
    run(
        [
            str(FFMPEG),
            "-y",
            "-i",
            str(segment.video_path),
            "-i",
            str(audio_master),
            "-filter_complex",
            filters,
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(output_path),
        ]
    )


def concat_segments(segment_paths: list[Path], output_path: Path) -> None:
    list_path = output_path.with_suffix(".concat.txt")
    list_path.write_text(
        "".join(f"file '{path.as_posix()}'\n" for path in segment_paths),
        encoding="utf-8",
    )
    run(
        [
            str(FFMPEG),
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-c",
            "copy",
            str(output_path),
        ]
    )


def subtitles_path(path: Path) -> str:
    return str(path).replace("\\", "/").replace(":", "\\:")


def add_branding_and_subtitles(input_path: Path, output_path: Path) -> None:
    logo = WORK / "header_site_id_logo01.png"
    title_ass = WORK / "ai_engineer_now_title.ass"
    subtitles = WORK / "subs_video_original_audio" / "ST7_7550_overlap_5min_original_audio.srt"
    title = subtitles_path(title_ass)
    srt = subtitles_path(subtitles)
    filters = [
        "[0:v][1:v]overlay=W-w-40:40[v1]",
        "[v1]subtitles="
        f"'{title}'[v2]",
        "[v2]subtitles="
        f"'{srt}':"
        "force_style='FontName=Yu Gothic,FontSize=20,PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H80000000,BackColour=&H80000000,BorderStyle=3,Outline=1,"
        "Shadow=0,MarginV=34,Alignment=2'[v3]",
    ]
    run(
        [
            str(FFMPEG),
            "-y",
            "-i",
            str(input_path),
            "-i",
            str(logo),
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[v3]",
            "-map",
            "0:a:0",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            str(output_path),
        ]
    )


def main() -> None:
    audio_master = WORK / "1cam" / "ST7_7550_overlap_5min.mp4"
    cam1 = audio_master
    cam2_7192 = ROOT / "2cam" / "0H4A7192.MP4"
    cam2_7193 = ROOT / "2cam" / "0H4A7193.MP4"
    cam3_2316 = ROOT / "3cam" / "IMG_2316.MP4"

    # Use only strong transcript matches. The sub-camera starts are locally
    # waveform-refined against the 1cam master audio.
    segments = [
        Segment(0.000, 9.000, cam1, 0.000),
        Segment(9.000, 21.500, cam2_7192, 1111.710),
        Segment(21.500, 85.000, cam1, 21.500),
        Segment(85.000, 152.000, cam2_7193, 59.640),
        Segment(152.000, 213.000, cam1, 152.000),
        Segment(213.000, 257.000, cam3_2316, 103.820),
        Segment(257.000, 300.000, cam1, 257.000),
    ]

    seg_dir = WORK / "segments_multicam_strong_transcript_wave_refined"
    seg_dir.mkdir(parents=True, exist_ok=True)
    built_segments: list[Path] = []
    for index, segment in enumerate(segments, start=1):
        output_path = seg_dir / f"seg_{index:02d}.mp4"
        build_segment(segment, audio_master, output_path)
        built_segments.append(output_path)

    joined = WORK / "ST7_7550_multicam_cut_5min_strong_transcript_wave_refined.mp4"
    concat_segments(built_segments, joined)

    final = WORK / "ST7_7550_multicam_cut_5min_strong_transcript_wave_refined_logo_text_subtitled.mp4"
    add_branding_and_subtitles(joined, final)


if __name__ == "__main__":
    main()
