from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import wave
from array import array
from pathlib import Path
from typing import Any

from project_paths import OUTPUT_AUDIO, OUTPUT_TRANSCRIPTS
from video_edit_app_config import load_app_config, nested, transcript_manifest_fingerprint


SAMPLE_RATE = 48_000
DEFAULT_DURATION = 60.0


def bool_value(config: dict[str, Any], *keys: str, default: bool = False) -> bool:
    value = nested(config, *keys, default=default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def float_value(config: dict[str, Any], *keys: str, default: float) -> float:
    value = nested(config, *keys, default=default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def text_value(config: dict[str, Any], *keys: str, default: str = "") -> str:
    value = nested(config, *keys, default=default)
    return str(value) if value is not None else default


def transcript_context() -> str:
    manifest_path = OUTPUT_TRANSCRIPTS / "manifest_sources" / "manifest_transcripts.json"
    if not manifest_path.exists():
        return ""
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    expected = transcript_manifest_fingerprint()
    if expected and manifest.get("manifestFingerprint") != expected:
        return ""
    transcripts = manifest.get("transcripts", [])
    if not isinstance(transcripts, list):
        return ""
    primary = next((item for item in transcripts if isinstance(item, dict) and item.get("primary")), None)
    item = primary or next((item for item in transcripts if isinstance(item, dict)), None)
    if not item:
        return ""
    json_path = Path(str(item.get("json") or ""))
    if json_path.exists():
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        text = str(payload.get("text") or "").strip()
        if text:
            return text
    return ""


def smoothstep(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def sine(freq: float, t: float, phase: float = 0.0) -> float:
    return math.sin((2.0 * math.pi * freq * t) + phase)


def envelope(t: float, duration: float) -> float:
    return smoothstep(t / 0.7) * smoothstep((duration - t) / 1.2)


def note_freq(midi: int) -> float:
    return 440.0 * (2.0 ** ((midi - 69) / 12.0))


def infer_mood(prompt: str, configured: str) -> str:
    if configured and configured != "auto":
        return configured
    text = prompt.lower()
    if any(word in text for word in ("calm", "quiet", "gentle", "soft", "落ち着", "穏やか", "静か")):
        return "calm"
    if any(word in text for word in ("bright", "uplift", "positive", "fresh", "明る", "前向き", "軽快")):
        return "bright"
    if any(word in text for word in ("serious", "deep", "documentary", "緊張", "真面目", "重め")):
        return "serious"
    return "neutral"


def palette_for_mood(mood: str) -> dict[str, Any]:
    if mood == "bright":
        return {"root": 62, "scale": [0, 2, 4, 7, 9], "bpm": 104, "pad": 0.11, "pluck": 0.095}
    if mood == "serious":
        return {"root": 57, "scale": [0, 3, 5, 7, 10], "bpm": 78, "pad": 0.13, "pluck": 0.045}
    if mood == "calm":
        return {"root": 60, "scale": [0, 2, 4, 7, 11], "bpm": 72, "pad": 0.10, "pluck": 0.050}
    return {"root": 60, "scale": [0, 2, 5, 7, 9], "bpm": 88, "pad": 0.12, "pluck": 0.065}


def stable_seed(prompt: str, mood: str, title: str) -> int:
    payload = f"{mood}\n{title}\n{prompt}".encode("utf-8", errors="ignore")
    return int(hashlib.sha256(payload).hexdigest()[:16], 16)


def pluck(freq: float, t: float, start: float, length: float, level: float) -> float:
    local = t - start
    if local < 0.0 or local > length:
        return 0.0
    attack = smoothstep(local / 0.025)
    decay = math.exp(-local * 4.9)
    tone = 0.72 * sine(freq, local) + 0.20 * sine(freq * 2.0, local, 0.7) + 0.08 * sine(freq * 3.01, local, 1.3)
    return tone * attack * decay * level


def render_sample(t: float, duration: float, rng: random.Random, palette: dict[str, Any]) -> tuple[float, float]:
    root = int(palette["root"])
    scale = list(palette["scale"])
    beat = 60.0 / float(palette["bpm"])
    bar = beat * 4.0
    env = envelope(t, duration)

    section = int(t // max(bar * 2.0, 0.1))
    chord_steps = [0, 3, 4, 1]
    chord_root = root + scale[chord_steps[section % len(chord_steps)] % len(scale)]
    chord = [chord_root - 24, chord_root - 12, chord_root - 5, chord_root, chord_root + 7, chord_root + 14]

    pad = 0.0
    for index, midi in enumerate(chord):
        freq = note_freq(midi)
        phase = 0.35 * index
        motion = 1.0 + 0.0022 * sine(0.11 + index * 0.03, t, phase)
        level = float(palette["pad"]) * (0.72 if index < 2 else 1.0)
        pad += level * sine(freq * motion, t, phase)
        pad += level * 0.28 * sine(freq * 2.002, t, phase + 0.5)

    arp = 0.0
    step = int(t / max(beat / 2.0, 0.1))
    step_time = step * beat / 2.0
    if step % 2 == 0:
        degree = scale[(step + section) % len(scale)]
        octave = 12 * (1 + ((step // 8) % 2))
        arp += pluck(note_freq(root + degree + octave), t, step_time, beat * 1.4, float(palette["pluck"]))

    shimmer = 0.0
    if int(t * 2.0) % 7 == 0:
        shimmer += pluck(note_freq(root + scale[(section + 2) % len(scale)] + 24), t, math.floor(t * 2.0) / 2.0, 0.8, 0.018)

    noise = rng.uniform(-1.0, 1.0) * 0.004 * smoothstep(t / 0.25) * smoothstep((duration - t) / 0.4)
    sample = math.tanh((pad + arp + shimmer + noise) * env * 1.35)
    width = 0.12 * sine(0.21, t)
    return sample * (1.0 - width), sample * (1.0 + width)


def write_wav(path: Path, duration: float, prompt: str, mood: str, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    palette = palette_for_mood(mood)
    rng = random.Random(stable_seed(prompt, mood, title))
    frame_count = max(1, round(SAMPLE_RATE * duration))
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        chunk = array("h")
        gain = 0.34
        for index in range(frame_count):
            left, right = render_sample(index / SAMPLE_RATE, duration, rng, palette)
            chunk.append(max(-32768, min(32767, round(left * gain * 32767))))
            chunk.append(max(-32768, min(32767, round(right * gain * 32767))))
            if len(chunk) >= SAMPLE_RATE * 2:
                wav.writeframes(chunk.tobytes())
                chunk = array("h")
        if chunk:
            wav.writeframes(chunk.tobytes())


def main() -> None:
    config = load_app_config()
    parser = argparse.ArgumentParser(description="Generate a generic project music bed from the runtime app config.")
    parser.add_argument("--duration", type=float, default=float_value(config, "render", "previewDuration", default=DEFAULT_DURATION))
    parser.add_argument("--output", type=Path, default=Path(text_value(config, "music", "outputPath", default=str(OUTPUT_AUDIO / "music_bed.wav"))))
    parser.add_argument("--prompt", default=text_value(config, "music", "prompt", default=""))
    parser.add_argument("--mood", default=text_value(config, "music", "mood", default="auto"))
    args = parser.parse_args()

    title = text_value(config, "style", "titleText", default="")
    context = transcript_context()
    prompt = args.prompt or title or context[:500]
    seed_prompt = "\n".join(part for part in (prompt, context[:1200]) if part)
    mood = infer_mood(seed_prompt, args.mood)
    duration = max(1.0, min(float(args.duration), 60.0 * 60.0))
    write_wav(args.output, duration, seed_prompt, mood, title)
    report = {
        "output": str(args.output),
        "duration": duration,
        "mood": mood,
        "prompt": prompt,
        "usedTranscriptContext": bool(context),
        "enabled": bool_value(config, "music", "enabled", default=False),
        "scope": text_value(config, "music", "scope", default="full"),
    }
    report_path = args.output.with_suffix(".json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
