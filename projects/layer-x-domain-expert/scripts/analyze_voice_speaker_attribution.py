from __future__ import annotations

import json
import math
import wave
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT_ROOT / "output" / "reports"
AUDIO_PATH = PROJECT_ROOT / "output" / "audio" / "group_wide_mono_16k.wav"
JST = timezone(timedelta(hours=9))

PEOPLE = {
    "person_01": {"name": "矢野", "screen_position": "left", "role": "interviewer"},
    "person_02": {"name": "根本", "screen_position": "middle", "role": "interviewee"},
    "person_03": {"name": "村田", "screen_position": "right", "role": "interviewee"},
}

# Conservative identity anchors from explicit self-introductions and long, contiguous sections.
# These are used to learn voice-quality centroids from the shared master audio.
VOICE_ANCHORS = {
    "person_01": [
        (519.14, 623.52, "left interviewer opening and setup"),
        (727.46, 786.20, "left interviewer self-introduction"),
        (1500.72, 1521.00, "left interviewer asks development difficulty question"),
        (1973.10, 2004.10, "left interviewer asks AI-era role question"),
    ],
    "person_02": [
        (623.52, 671.06, "middle interviewee self-introduction"),
        (869.44, 1048.00, "middle interviewee career and accounting background"),
        (1251.52, 1321.16, "middle interviewee PDM role discussion"),
        (2276.04, 2307.04, "middle interviewee future career answer"),
    ],
    "person_03": [
        (675.06, 721.30, "right interviewee self-introduction"),
        (1054.28, 1244.00, "right interviewee HR and labor background"),
        (1344.92, 1424.00, "right interviewee domain expert work discussion"),
        (1535.30, 1666.72, "right interviewee development challenge answer"),
    ],
}

FORCED_WINDOWS = [
    (519.14, 623.52, "person_01", "opening interviewer setup"),
    (623.52, 671.06, "person_02", "middle self-introduction"),
    (671.06, 675.06, "person_01", "interviewer hands off to right interviewee"),
    (675.06, 722.50, "person_03", "right self-introduction"),
    (727.46, 786.20, "person_01", "interviewer self-introduction"),
]

QUESTION_MARKERS = (
    "ですか",
    "ますか",
    "でしょうか",
    "聞いていきます",
    "伺え",
    "お願いします",
    "どう思って",
    "お二人",
    "根本さん",
    "根元さん",
    "村田さん",
)

PERSON_KEYWORDS = {
    "person_01": ("矢野", "聞いて", "質問", "お二人", "どうですか", "ありますか"),
    "person_02": ("経理", "PDM", "プロダクトマネージャー", "決算", "会計", "バクラク", "バックオフィス"),
    "person_03": ("労務", "人事", "HR", "勤怠", "給与", "社会保険", "社労士", "村田"),
}


def now_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_audio() -> tuple[int, np.ndarray]:
    with wave.open(str(AUDIO_PATH), "rb") as wav:
        sample_rate = wav.getframerate()
        channels = wav.getnchannels()
        frames = wav.readframes(wav.getnframes())
        audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    return sample_rate, audio


def normalize_text(text: str) -> str:
    return "".join(str(text).replace("、", "").replace("。", "").split())


def segment_audio(audio: np.ndarray, sample_rate: int, start: float, end: float) -> np.ndarray:
    start_i = max(0, min(len(audio), int(start * sample_rate)))
    end_i = max(start_i, min(len(audio), int(end * sample_rate)))
    return audio[start_i:end_i]


def frame_audio(samples: np.ndarray, sample_rate: int) -> np.ndarray:
    frame_size = max(256, int(sample_rate * 0.04))
    hop = max(128, int(sample_rate * 0.02))
    if len(samples) < frame_size:
        return np.empty((0, frame_size), dtype=np.float32)
    count = 1 + (len(samples) - frame_size) // hop
    frames = np.empty((count, frame_size), dtype=np.float32)
    window = np.hanning(frame_size).astype(np.float32)
    for index in range(count):
        start = index * hop
        frames[index] = samples[start : start + frame_size] * window
    return frames


def spectral_features(samples: np.ndarray, sample_rate: int) -> np.ndarray | None:
    samples = samples.astype(np.float32)
    if len(samples) < int(sample_rate * 0.35):
        return None
    samples = samples - float(np.mean(samples))
    rms = float(np.sqrt(np.mean(samples * samples)) + 1e-8)
    if rms < 0.0008:
        return None
    frames = frame_audio(samples, sample_rate)
    if len(frames) == 0:
        return None
    spectrum = np.abs(np.fft.rfft(frames, axis=1)) + 1e-8
    freqs = np.fft.rfftfreq(frames.shape[1], 1.0 / sample_rate)
    power = spectrum * spectrum
    total = np.sum(power, axis=1) + 1e-8
    centroid = np.sum(power * freqs, axis=1) / total
    spread = np.sqrt(np.sum(power * (freqs[None, :] - centroid[:, None]) ** 2, axis=1) / total)
    cumulative = np.cumsum(power, axis=1)
    rolloff_index = np.argmax(cumulative >= (total[:, None] * 0.85), axis=1)
    rolloff = freqs[rolloff_index]
    flatness = np.exp(np.mean(np.log(spectrum), axis=1)) / (np.mean(spectrum, axis=1) + 1e-8)
    zcr = np.mean(np.abs(np.diff(np.signbit(frames), axis=1)), axis=1)
    bands = []
    for low, high in ((80, 180), (180, 320), (320, 650), (650, 1200), (1200, 2500), (2500, 5000)):
        mask = (freqs >= low) & (freqs < high)
        bands.append(np.mean(power[:, mask], axis=1) / total if np.any(mask) else np.zeros(len(frames)))
    values = [
        math.log10(rms + 1e-8),
        float(np.mean(centroid)) / 5000.0,
        float(np.std(centroid)) / 3000.0,
        float(np.mean(spread)) / 5000.0,
        float(np.mean(rolloff)) / 8000.0,
        float(np.mean(flatness)),
        float(np.mean(zcr)),
    ]
    values.extend(float(np.mean(band)) for band in bands)
    return np.asarray(values, dtype=np.float32)


def build_voice_models(audio: np.ndarray, sample_rate: int) -> dict[str, dict[str, Any]]:
    raw: dict[str, list[np.ndarray]] = {person_id: [] for person_id in PEOPLE}
    anchor_report: dict[str, list[dict[str, Any]]] = {person_id: [] for person_id in PEOPLE}
    for person_id, windows in VOICE_ANCHORS.items():
        for start, end, reason in windows:
            chunks = []
            cursor = start
            while cursor < end - 1.0:
                chunk_end = min(end, cursor + 6.0)
                feature = spectral_features(segment_audio(audio, sample_rate, cursor, chunk_end), sample_rate)
                if feature is not None:
                    raw[person_id].append(feature)
                    chunks.append({"start": round(cursor, 3), "end": round(chunk_end, 3)})
                cursor += 6.0
            anchor_report[person_id].append({"start": start, "end": end, "reason": reason, "usable_chunks": chunks})
    all_vectors = [vector for vectors in raw.values() for vector in vectors]
    if not all_vectors:
        raise RuntimeError("No usable voice anchor vectors were extracted.")
    matrix = np.vstack(all_vectors)
    mean = np.mean(matrix, axis=0)
    std = np.std(matrix, axis=0) + 1e-6
    models = {}
    for person_id, vectors in raw.items():
        if not vectors:
            continue
        normalized = (np.vstack(vectors) - mean) / std
        models[person_id] = {
            "centroid": np.mean(normalized, axis=0),
            "samples": len(vectors),
            "anchors": anchor_report[person_id],
        }
    return {"models": models, "feature_mean": mean, "feature_std": std}


def voice_scores(feature: np.ndarray | None, model_payload: dict[str, Any]) -> list[dict[str, Any]]:
    if feature is None:
        return []
    mean = model_payload["feature_mean"]
    std = model_payload["feature_std"]
    normalized = (feature - mean) / std
    scores = []
    for person_id, model in model_payload["models"].items():
        centroid = model["centroid"]
        distance = float(np.linalg.norm(normalized - centroid))
        scores.append({"person_id": person_id, "distance": round(distance, 4), "score": round(1.0 / (1.0 + distance), 4)})
    scores.sort(key=lambda item: item["score"], reverse=True)
    return scores


def forced_person(start: float, end: float) -> tuple[str, str] | None:
    midpoint = (start + end) / 2.0
    for win_start, win_end, person_id, reason in FORCED_WINDOWS:
        if win_start <= midpoint < win_end:
            return person_id, reason
    return None


def text_person(text: str) -> tuple[str | None, float, list[str]]:
    norm = normalize_text(text)
    if any(marker in norm for marker in QUESTION_MARKERS):
        return "person_01", 0.74, ["question/interviewer phrase"]
    matches = []
    for person_id, keywords in PERSON_KEYWORDS.items():
        hit_count = sum(1 for keyword in keywords if keyword in norm)
        if hit_count:
            matches.append((hit_count, person_id))
    if not matches:
        return None, 0.0, []
    matches.sort(reverse=True)
    confidence = min(0.72, 0.48 + matches[0][0] * 0.08)
    return matches[0][1], confidence, [f"keyword_hits={matches[0][0]}"]


def choose_person(
    start: float,
    end: float,
    text: str,
    scores: list[dict[str, Any]],
) -> tuple[str | None, float, str, list[str]]:
    forced = forced_person(start, end)
    if forced:
        return forced[0], 0.97, "forced_known_intro_window", [forced[1]]
    text_id, text_conf, evidence = text_person(text)
    voice_id = scores[0]["person_id"] if scores else None
    voice_conf = 0.0
    if scores:
        top = scores[0]["score"]
        second = scores[1]["score"] if len(scores) > 1 else 0.0
        voice_conf = max(0.34, min(0.84, 0.38 + (top - second) * 4.0))
    if text_id and voice_id == text_id:
        return text_id, round(min(0.94, max(text_conf, voice_conf) + 0.12), 3), "voice_and_text_agree", evidence
    if text_id and text_conf >= 0.7:
        return text_id, round(text_conf, 3), "text_role_override_voice", evidence
    if voice_id:
        return voice_id, round(voice_conf, 3), "voice_quality_nearest_anchor", []
    if text_id:
        return text_id, round(text_conf, 3), "text_keyword_only", evidence
    return None, 0.0, "unknown", []


def main() -> None:
    sample_rate, audio = read_audio()
    transcript = read_json(REPORTS / "transcript.json", {})
    model_payload = build_voice_models(audio, sample_rate)
    segments = []
    for segment in transcript.get("segments", []):
        text = str(segment.get("text") or "").strip()
        if not text or text == "音声に忠実に文字起こしないでください。":
            continue
        start = float(segment.get("start") or 0.0)
        end = float(segment.get("end") or start)
        if end <= start:
            continue
        feature = spectral_features(segment_audio(audio, sample_rate, start, end), sample_rate)
        scores = voice_scores(feature, model_payload)
        person_id, confidence, method, evidence = choose_person(start, end, text, scores)
        segments.append(
            {
                "segment_id": segment.get("segment_id"),
                "start": round(start, 3),
                "end": round(end, 3),
                "duration": round(end - start, 3),
                "text": text,
                "speaker_person_id": person_id,
                "speaker_name": PEOPLE.get(str(person_id), {}).get("name") if person_id else None,
                "confidence": confidence,
                "method": method,
                "evidence": evidence,
                "voice_scores": scores,
            }
        )
    payload = {
        "schema_version": "voice_speaker_attribution.v1",
        "project_id": "layer-x-domain-expert",
        "generated_at": now_iso(),
        "source_audio": str(AUDIO_PATH),
        "method": "voice-quality nearest-anchor classification plus transcript role/keyword constraints",
        "people": PEOPLE,
        "voice_anchor_windows": VOICE_ANCHORS,
        "limitations": [
            "This uses lightweight spectral voice features, not a neural diarization model.",
            "Known self-introduction and topic windows are used as supervised voice anchors.",
            "Question/interviewer text markers can override weak voice matches.",
        ],
        "model_summary": {
            person_id: {"samples": model["samples"], "anchors": model["anchors"]}
            for person_id, model in model_payload["models"].items()
        },
        "segments": segments,
    }
    write_json(REPORTS / "voice_speaker_attribution.json", payload)
    print(json.dumps({"output": str(REPORTS / "voice_speaker_attribution.json"), "segments": len(segments)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
