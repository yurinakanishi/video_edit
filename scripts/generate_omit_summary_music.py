from __future__ import annotations

import argparse
import math
import random
import wave
from array import array
from pathlib import Path

from project_paths import OUTPUT_AUDIO


SAMPLE_RATE = 48_000
DURATION = 5.0
DEFAULT_OUTPUT = OUTPUT_AUDIO / "omit_summary_card_music_5s.wav"


def smoothstep(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def fade_envelope(t: float, duration: float) -> float:
    fade_in = smoothstep(t / 0.35)
    fade_out = smoothstep((duration - t) / 0.9)
    return fade_in * fade_out


def sine(freq: float, t: float, phase: float = 0.0) -> float:
    return math.sin((2.0 * math.pi * freq * t) + phase)


def pluck(freq: float, t: float, start: float, length: float, level: float) -> float:
    local = t - start
    if local < 0.0 or local > length:
        return 0.0
    attack = smoothstep(local / 0.018)
    decay = math.exp(-local * 5.2)
    tone = (
        0.72 * sine(freq, local)
        + 0.22 * sine(freq * 2.0, local, 0.4)
        + 0.08 * sine(freq * 3.01, local, 1.1)
    )
    return tone * attack * decay * level


def render_sample(t: float, noise: float) -> tuple[float, float]:
    env = fade_envelope(t, DURATION)

    # D major/add9 pad with pentatonic motion: clean, open, and suited to an explanatory card.
    pad = 0.0
    for freq, level, phase in (
        (73.416, 0.13, 0.1),   # D2
        (110.000, 0.07, 1.7),   # A2
        (146.832, 0.09, 0.4),   # D3
        (184.997, 0.055, 2.2),  # F#3
        (220.000, 0.045, 1.1),  # A3
        (293.665, 0.030, 0.6),  # D4
        (329.628, 0.032, 0.8),  # E4/add9
    ):
        slow_motion = 1.0 + 0.0025 * sine(0.18 + freq * 0.0002, t, phase)
        pad += level * sine(freq * slow_motion, t, phase)
        pad += level * 0.32 * sine(freq * 2.002, t, phase + 0.6)
    pad *= env

    arp = 0.0
    for start, freq, level in (
        (0.16, 587.330, 0.070),  # D5
        (0.74, 659.255, 0.052),  # E5
        (1.30, 739.989, 0.050),  # F#5
        (1.92, 880.000, 0.048),  # A5
        (2.64, 987.767, 0.042),  # B5
        (3.34, 880.000, 0.044),  # A5
        (4.08, 659.255, 0.034),  # E5
    ):
        arp += pluck(freq, t, start, 1.05, level)

    noise_env = smoothstep(t / 0.2) * smoothstep((0.95 - t) / 0.65)
    noise_layer = noise * 0.010 * noise_env

    sample = math.tanh((pad + arp + noise_layer) * 1.45)
    width = 0.12 * sine(0.28, t)
    left = sample * (1.0 - width)
    right = sample * (1.0 + width)
    return left, right


def write_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rng = random.Random(7550)
    frames = array("h")
    peak = 0.0
    rendered: list[tuple[float, float]] = []

    for index in range(round(SAMPLE_RATE * DURATION)):
        t = index / SAMPLE_RATE
        noise = rng.uniform(-1.0, 1.0)
        left, right = render_sample(t, noise)
        rendered.append((left, right))
        peak = max(peak, abs(left), abs(right))

    target_peak = 0.34
    gain = target_peak / peak if peak else 1.0
    for left, right in rendered:
        frames.append(max(-32768, min(32767, round(left * gain * 32767))))
        frames.append(max(-32768, min(32767, round(right * gain * 32767))))

    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(frames.tobytes())


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the 5-second omit-mode summary-card music.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    write_wav(args.output)
    print(args.output)


if __name__ == "__main__":
    main()
