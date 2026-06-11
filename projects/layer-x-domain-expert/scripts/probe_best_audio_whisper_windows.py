from __future__ import annotations

import json
import subprocess
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT_DIR / "output" / "transcripts" / "best_audio_large_v3" / "window_probe"
SOURCE_MEDIA = PROJECT_DIR / "source" / "video" / "person-middle.mp4"


WINDOWS = [
    ("intro", 526.608, 18.0),
    ("digest_question", 1508.188, 12.0),
    ("digest_answer", 1540.888, 18.0),
    ("ai_section", 1990.568, 18.0),
    ("career", 2933.508, 18.0),
]


def extract_window(label: str, start: float, duration: float) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    wav = OUT_DIR / f"{label}.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{duration:.3f}",
            "-i",
            str(SOURCE_MEDIA),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-af",
            "highpass=f=70,lowpass=f=7600,loudnorm=I=-18:TP=-2:LRA=11",
            str(wav),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return wav


def transcribe_window(model, wav: Path, *, condition_on_previous_text: bool, vad_filter: bool) -> str:
    segments, _ = model.transcribe(
        str(wav),
        language="ja",
        task="transcribe",
        beam_size=5,
        best_of=5,
        temperature=0.0,
        condition_on_previous_text=condition_on_previous_text,
        vad_filter=vad_filter,
        initial_prompt=(
            "LayerX、バクラク、ドメインエキスパート、バックオフィス、PDM、プロダクトマネージャー、"
            "経理、労務、人事労務、エンジニア、AI、プロダクト開発についての日本語インタビュー。"
        ),
    )
    return "".join(segment.text.strip() for segment in segments)


def main() -> None:
    from faster_whisper import WhisperModel

    model = WhisperModel("large-v3", device="cuda", compute_type="float16")
    rows = []
    for label, start, duration in WINDOWS:
        wav = extract_window(label, start, duration)
        for condition in (False, True):
            for vad in (False, True):
                rows.append(
                    {
                        "label": label,
                        "source_start": start,
                        "duration": duration,
                        "condition_on_previous_text": condition,
                        "vad_filter": vad,
                        "text": transcribe_window(
                            model,
                            wav,
                            condition_on_previous_text=condition,
                            vad_filter=vad,
                        ),
                    }
                )
    out = OUT_DIR / "window_probe_results.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(out), "rows": rows}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
