from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parents[1]
TRANSCRIPTS = PROJECT / "output" / "transcripts" / "manifest_sources"
REPORTS = PROJECT / "output" / "reports"

TARGET_VIDEO = PROJECT / "source" / "video" / "20260529_214344_trimmed_final.mp4"
SOURCE_TRANSCRIPT = TRANSCRIPTS / "external_140101-003.reviewed.json"
SPEAKER_ROLES = REPORTS / "full_transcript_speaker_roles_audio_lr.json"

TRANSCRIPT_OUT = PROJECT / "transcript_trimmed_final.json"
REVIEW_OUT = PROJECT / "review_result_revised.md"

# The reviewed MP4 was created from the project timeline with the first 85.5s
# removed. Project subtitle/transcript timestamps are 8.7s ahead of the source
# timeline, so transcript_time - 94.2 gives reviewed-video time.
REVIEWED_VIDEO_START_TRIM_SECONDS = 85.5
SUBTITLE_SOURCE_OFFSET_SECONDS = 8.7
TRANSCRIPT_TO_REVIEWED_VIDEO_SHIFT = REVIEWED_VIDEO_START_TRIM_SECONDS + SUBTITLE_SOURCE_OFFSET_SECONDS


def ffprobe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nokey=1:noprint_wrappers=1",
            str(path),
        ],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return float(result.stdout.strip())


def timestamp(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    whole = int(seconds)
    millis = int(round((seconds - whole) * 1000))
    if millis == 1000:
        whole += 1
        millis = 0
    hours = whole // 3600
    minutes = (whole % 3600) // 60
    secs = whole % 60
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}.{millis:03d}"
    return f"{minutes}:{secs:02d}.{millis:03d}"


def split_long_text(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    tokens = re.findall(r".+?[、。！？?]|.+?$", text)
    for token in tokens:
        if not token:
            continue
        if len(token) > limit:
            if current:
                chunks.append(current)
                current = ""
            for index in range(0, len(token), limit):
                chunks.append(token[index : index + limit])
            continue
        if current and len(current) + len(token) > limit:
            chunks.append(current)
            current = token
        else:
            current += token
    if current:
        chunks.append(current)
    return chunks


def caption_lines(text: str, line_limit: int = 18) -> list[str]:
    lines = split_long_text(text, line_limit)
    if len(lines) <= 2:
        return lines
    return [lines[0], "".join(lines[1:])]


def subtitle_units(segment: dict[str, Any], unit_limit: int = 28) -> list[dict[str, Any]]:
    text = str(segment["text"]).strip()
    parts = split_long_text(text, unit_limit)
    if len(parts) <= 1:
        return [
            {
                "start": segment["start"],
                "end": segment["end"],
                "start_hms": segment["start_hms"],
                "end_hms": segment["end_hms"],
                "text": text,
                "lines": caption_lines(text),
            }
        ]

    duration = max(0.01, float(segment["end"]) - float(segment["start"]))
    total_chars = max(1, sum(len(part) for part in parts))
    cursor = float(segment["start"])
    units: list[dict[str, Any]] = []
    for index, part in enumerate(parts):
        if index == len(parts) - 1:
            end = float(segment["end"])
        else:
            end = cursor + duration * (len(part) / total_chars)
        units.append(
            {
                "start": round(cursor, 3),
                "end": round(end, 3),
                "start_hms": timestamp(cursor),
                "end_hms": timestamp(end),
                "text": part,
                "lines": caption_lines(part),
            }
        )
        cursor = end
    return units


def load_roles() -> dict[int, dict[str, Any]]:
    if not SPEAKER_ROLES.exists():
        return {}
    payload = json.loads(SPEAKER_ROLES.read_text(encoding="utf-8"))
    roles: dict[int, dict[str, Any]] = {}
    for caption in payload.get("captions", []):
        try:
            index = int(caption["index"]) - 1
        except (KeyError, TypeError, ValueError):
            continue
        roles[index] = {
            "speaker_role": caption.get("role"),
            "speaker_confidence": caption.get("confidence"),
            "speaker_reason": caption.get("reason"),
            "lr_db": caption.get("audioFeatures", {}).get("lrDb"),
        }
    return roles


def build_segments(duration: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    payload = json.loads(SOURCE_TRANSCRIPT.read_text(encoding="utf-8"))
    roles = load_roles()
    segments: list[dict[str, Any]] = []
    units: list[dict[str, Any]] = []

    for original_index, source_segment in enumerate(payload.get("segments", [])):
        source_start = float(source_segment.get("start", 0.0))
        source_end = float(source_segment.get("end", 0.0))
        reviewed_start = source_start - TRANSCRIPT_TO_REVIEWED_VIDEO_SHIFT
        reviewed_end = source_end - TRANSCRIPT_TO_REVIEWED_VIDEO_SHIFT
        if reviewed_end <= 0 or reviewed_start >= duration:
            continue
        start = max(0.0, reviewed_start)
        end = min(duration, reviewed_end)
        if end <= start:
            continue
        text = str(source_segment.get("text", "")).strip()
        if not text:
            continue
        role = roles.get(original_index, {})
        segment = {
            "id": len(segments) + 1,
            "source_segment_index": original_index,
            "source_transcript_start": round(source_start, 3),
            "source_transcript_end": round(source_end, 3),
            "start": round(start, 3),
            "end": round(end, 3),
            "start_hms": timestamp(start),
            "end_hms": timestamp(end),
            "text": text,
            "subtitle_display": {
                "text": text,
                "lines": caption_lines(text),
            },
            **role,
        }
        segment["subtitle_units"] = subtitle_units(segment)
        for unit in segment["subtitle_units"]:
            units.append({"parent_segment_id": segment["id"], **unit})
        segments.append(segment)

    return segments, units


def find_segments(segments: list[dict[str, Any]], needle: str, near: float | None = None, window: float = 30.0) -> list[dict[str, Any]]:
    matches = [
        {
            "segment_id": segment["id"],
            "start_hms": segment["start_hms"],
            "end_hms": segment["end_hms"],
            "text": segment["text"],
            "speaker_role": segment.get("speaker_role"),
        }
        for segment in segments
        if needle in str(segment.get("text", ""))
        and (
            near is None
            or (
                float(segment["end"]) >= near - window
                and float(segment["start"]) <= near + window
            )
        )
    ]
    return matches


def build_review_alignment(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    specs = [
        {
            "id": "cut_imai_tashikani_arigatou",
            "original_review_reference": "7分40秒",
            "revised_instruction": "「確かにありがとうございます」と話す単独の相づち発話をカット。",
            "anchors": [{"text": "確かにありがとうございます", "near": 460.0}],
        },
        {
            "id": "cut_transition_after_soudesune",
            "original_review_reference": "10分26秒〜10分27秒",
            "revised_instruction": "「そうですね」と言い終わった直後から、「なのでFDEを支える要素というのもあるんですけれども」と話し始める直前までの間を詰める。",
            "anchors": [
                {"text": "そうですね", "near": 625.0},
                {"text": "なのでFDEを支える要素というのもあるんですけれども", "near": 626.0},
            ],
        },
        {
            "id": "cut_external_factor_block",
            "original_review_reference": "「ポイントとしてあるかなと思いますね」後〜「先ほどの話に付属して考えると」前",
            "revised_instruction": "「1アカウントあたりにいただける対価というのが一定規模以上というところがポイントとしてあるかなと思いますね」は残し、その直後から「先ほどの話に付属して考えると」が始まる直前までをカット。「外部要素ですか」はカット範囲に含める。",
            "anchors": [
                {"text": "ポイントとしてあるかなと思いますね", "near": 678.0},
                {"text": "外部要素ですか", "near": 804.0},
                {"text": "先ほどの話に付属して考えると", "near": 835.0},
            ],
        },
        {
            "id": "cut_wait_before_japan_work",
            "original_review_reference": "14分36秒〜15分8秒",
            "revised_instruction": "「確かに確かに」から「日本の中でどのような形であればFDEもワークしていくのかというのが」の発話ブロック終端までをカットし、「徐々に分かってきたかなと思うんですけれども」以降へつなぐ。",
            "anchors": [
                {"text": "確かに確かに", "near": 877.0},
                {"text": "日本の中でどのような形であればFDEもワークしていくのかというのが", "near": 891.0},
                {"text": "徐々に分かってきたかなと思うんですけれども", "near": 913.0},
            ],
        },
        {
            "id": "subtitle_only_tashikani_20m21",
            "original_review_reference": "20分21秒",
            "revised_instruction": "「そうですね」の後、「柳川さんの話ではそもそもどっちが食う食わない」が始まる前に入る単独の「確かに」は、動画・音声は残して字幕だけ削除。",
            "anchors": [{"text": "柳川さんの話ではそもそもどっちが食う食わない", "near": 1223.0}],
        },
        {
            "id": "cut_tashikani_22m47",
            "original_review_reference": "22分47秒",
            "revised_instruction": "「すごく火の玉ストレートみたいな正論ですよね」の直後に入る「確かにな」をカットし、「アメリカの雇用制度というか」へつなぐ。",
            "anchors": [
                {"text": "すごく火の玉ストレートみたいな正論ですよね", "near": 1360.0},
                {"text": "確かにな", "near": 1365.0},
                {"text": "アメリカの雇用制度というか", "near": 1368.0},
            ],
        },
        {
            "id": "cut_think_block",
            "original_review_reference": "23分39秒および「そこをちょっと考えてみたいんですけれども」〜「そもそもFDEとPDMは共存するというか」前",
            "revised_instruction": "「確かにな」に続けて、「そこをちょっと考えてみたいんですけれども」から「そもそもFDEとPDMは共存するというか」が始まる直前までをまとめてカット。",
            "anchors": [
                {"text": "そこをちょっと考えてみたいんですけれども", "near": 1419.0},
                {"text": "そもそもFDEとPDMは共存するというか", "near": 1451.0},
            ],
        },
        {
            "id": "cut_reset_interview_block",
            "original_review_reference": "35分37秒〜37分28秒あたり",
            "revised_instruction": "「分かりましたありがとうございます」の後の進行確認・仕切り直しブロックをカットし、「FDEについていろいろとお話を伺ってきた中で」から再開。",
            "anchors": [
                {"text": "分かりましたありがとうございます", "near": 2134.0},
                {"text": "メッセージとしては大丈夫ですインタビュー", "near": 2167.0},
                {"text": "FDEについていろいろとお話を伺ってきた中で", "near": 2247.0},
            ],
        },
        {
            "id": "cut_after_toraenaosu",
            "original_review_reference": "「そこは改めて捉え直すのが大事なのかなと思います」後〜「FDEに向いている人といいますか」前",
            "revised_instruction": "「そこは改めて捉え直すのが大事なのかなと思います」は残し、その直後から「FDEに向いている人といいますか」が始まる直前までをカット。",
            "anchors": [
                {"text": "そこは改めて捉え直すのが大事なのかなと思います", "near": 2540.0},
                {"text": "FDEに向いている人といいますか", "near": 2587.0},
            ],
        },
        {
            "id": "cut_tashikani_45m17",
            "original_review_reference": "45分17秒",
            "revised_instruction": "「自覚がある人は向いてるんじゃないですかね」の直後に入る「確かに確かに」をカットし、「あとFDEって言うてもエンジニアってついてるじゃないですか」へつなぐ。",
            "anchors": [
                {"text": "自覚がある人は向いてるんじゃないですかね", "near": 2716.0},
                {"text": "あとFDEって言うてもエンジニアってついてるじゃないですか", "near": 2721.0},
            ],
        },
    ]
    for spec in specs:
        spec["matched_segments"] = {
            anchor["text"]: find_segments(segments, anchor["text"], float(anchor["near"]))
            for anchor in spec["anchors"]
        }
    return specs


def write_transcript() -> dict[str, Any]:
    if not TARGET_VIDEO.exists():
        raise FileNotFoundError(f"Target video is missing: {TARGET_VIDEO}")
    duration = ffprobe_duration(TARGET_VIDEO)
    segments, units = build_segments(duration)
    payload = {
        "schema_version": 1,
        "project_id": PROJECT.name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target_video": str(TARGET_VIDEO),
        "target_video_duration_seconds": round(duration, 3),
        "transcription": {
            "engine": "Whisper",
            "model": "large-v3",
            "language": "ja",
            "method": (
                "Derived from the existing project Whisper large-v3 transcription "
                "of the production external audio, shifted to the reviewed MP4 timebase. "
                "This keeps the high-quality Whisper result instead of re-transcribing "
                "the compressed review MP4 on the current CPU-only environment."
            ),
            "source_transcript": str(SOURCE_TRANSCRIPT),
            "timebase_shift_seconds": TRANSCRIPT_TO_REVIEWED_VIDEO_SHIFT,
        },
        "segments": segments,
        "subtitle_units": units,
        "review_alignment": build_review_alignment(segments),
    }
    TRANSCRIPT_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def build_revised_markdown() -> str:
    return """# 動画修正指示一覧（発話アンカー版）

対象動画: `source/video/20260529_214344_trimmed_final.mp4`
参照文字起こしJSON: `transcript_trimmed_final.json`

この版では、カット位置を秒数ではなく発話内容で指定します。秒数は照合用の内部情報として `transcript_trimmed_final.json` に残しています。

## 全体

### 動画冒頭

**【画像差し替え】**
ロゴを差し替え。
データは別送の添付イメージにある「黒ロゴ」を使用。

---

## テロップ変更

### 強いプロダクトの前提整理ブロック

**【テロップ変更】**
冒頭の「FDEがかなり重い役割だというところが分かったのと」から、「こういう人だよっていうふうに言語化するとなると」で次の話題へ移る直前まで、左上の文字を以下に変更。

> 強いプロダクト

---

### 既にFDE的に働く人のブロック

**【テロップ変更】**
「こういう人だよっていうふうに言語化するとなると」から、FDEブームの話題に入る「確かに。アメリカで流行ってるからとはいえ、日本でもFDEっていう動き盛り上がってるじゃないですか。」の直前まで、左上の文字を以下に変更。

> 既にFDE的に働く人

※別指示にある「すでにFDE的な働き方をしている人」は、こちらの表記に統一。

---

### FDEブームの正体ブロック

**【テロップ変更】**
「確かに。アメリカで流行ってるからとはいえ、日本でもFDEっていう動き盛り上がってるじゃないですか。」から、「続いてなんですけど」で次の話題へ移る直前まで、左上の文字を以下に変更。

> FDEブームの正体

---

### FDE向きプロダクトブロック

**【テロップ変更】**
「なのでFDEを支える要素というのもあるんですけれども」から、「日本の中でどのような形であればFDEもワークしていくのかというのが」で日本企業の話題へ移る直前まで、左上の文字を以下に変更。

> FDE向きプロダクト

---

### 字幕内文言の修正

**【テロップ変更】**
「個々のカスタマイズをしていくために人を張っても大丈夫というところが」の字幕で、もし「ここのカスタマイズ」と表示されている場合は以下に修正。

変更前:

> ここのカスタマイズ〜

変更後:

> 個々のカスタマイズ〜

---

### 日本企業でワークするかブロック

**【テロップ変更】**
「日本の中でどのような形であればFDEもワークしていくのかというのが」から、「ちょっと事前の想定ではPDMとFDEに関する論争みたいな感じで」でPDM/FDE論争に入る直前まで、左上の文字を以下に変更。

> 日本企業でワークするか

---

### PDM vs FDE論争ブロック

**【テロップ変更】**
「ちょっと事前の想定ではPDMとFDEに関する論争みたいな感じで」から、「なのでそんな簡単に一枚のジョブディスクリプションで定義できるものではそもそもないと」で次の論点へ移る直前まで、左上の文字を以下に変更。

> PDM vs FDE論争

---

## テキスト追加

### FDE向きプロダクトの説明開始

**【テキスト追加】**
「なのでFDEを支える要素というのもあるんですけれども」から「FDEが必要なプロダクトかどうかというところがポイントとしてあって」にかけて、左の余白に以下のテキストを追加。

> FDEが必要なプロダクトか

---

## 字幕修正

### 表記統一

**【字幕修正】**
以下の字幕表記を修正してください。

- `たまっていく` -> `溜まっていく`
- `それはそれこれはこれって感じ` -> `それはそれ、これはこれ、って感じ`
- `だとはいえAIの力によって` -> `とはいえAIの力によって`
- `なるほどどこまでもプロダクトのパワーというのが` -> `どこまでもプロダクトのパワーというのが`
- `どうしてああいう論争がなっちゃうのかな` -> `どうしてああいう論争になっちゃうのかな`
- `ちょっとしたノートの発言` -> `ちょっとしたnoteの発言`
- `ノートの記事` -> `noteの記事`
- `あなたの仕事例えばライターの仕事` -> `あなたの仕事、例えばライターの仕事`

---

### 字幕文末の句点

**【字幕修正】**
字幕本文の文末にある `。` は削除してください。

---

### 序盤の相づち字幕

**【字幕修正】**
「確かにそうですよね」の字幕は削除してください。

※動画・音声はカットしません。

---

### FDE化質問前の不要字幕

**【字幕修正】**
「これは何でしょうか」の字幕は削除してください。

※動画・音声はカットしません。

---

### 「大規模」字幕のタイミング

**【字幕修正】**
「確かに大規模」と出ている字幕は、表示文言を「大規模」だけにし、表示開始を「大規模」と発話している箇所に合わせてください。

※「確かに」と発話している時点では「大規模」を表示しません。

---

### FDEブームの話題に入る相づち

**【字幕修正】**
「確かに。アメリカで流行ってるからとはいえ、日本でもFDEっていう動き盛り上がってるじゃないですか。」の冒頭に表示される「確かに」は字幕上から削除。

※音声・映像はカットしない。
※同じ指示が重複しているため、1回分として処理。

---

## カット指示

### 「確かにありがとうございます」

**【カット】**
今中さんの単独相づち「確かにありがとうございます」をカットしてください。

---

### 「そうですね」後の短い間

**【カット】**
「FDEを支える要素に関して」に続く「そうですね」と言い終わった直後から、「なのでFDEを支える要素というのもあるんですけれども」と話し始める直前までの間を詰めてください。

※「なのでFDEを支える要素というのもあるんですけれども」以降の説明は残します。

---

### 「ポイントとしてあるかなと思いますね」後のブロック

**【カット】**
「1アカウントあたりにいただける対価というのが一定規模以上というところがポイントとしてあるかなと思いますね」の発話と字幕は残し、その直後から「先ほどの話に付属して考えると」の発話・字幕が始まる直前までを削除してください。

※「外部要素ですか」はカット範囲に含めます。

---

### 「確かに確かに」から日本企業の話題への入り直し

**【カット】**
「業界に特化しないっていう形も考えるかなと思います」に続く「確かに確かに」から、「日本の中でどのような形であればFDEもワークしていくのかというのが」の発話ブロック終端までをカットしてください。

再開位置は「徐々に分かってきたかなと思うんですけれども」以降が自然です。

---

### PDM/FDE論争前の単独「確かに」

**【字幕修正】**
「インプレッション稼ぎやすいですもんね」「そうですね」の後に入る単独の「確かに」は、字幕だけ削除してください。

※動画・音声はカットしません。「確かに」の音声を残したまま、「柳川さんの話ではそもそもどっちが食う食わない」へ続けてください。

---

### 火の玉ストレート後の「確かにな」

**【カット】**
「すごく火の玉ストレートみたいな正論ですよね」の直後に入る「確かにな」をカットし、「アメリカの雇用制度というか」へつないでください。

---

### 「そこをちょっと考えてみたいんですけれども」ブロック

**【カット】**
「もうちょっと考えたほうがいいのかなと思いますね」の後に入る「確かにな」から、「そもそもFDEとPDMは共存するというか」の発話・字幕が始まる直前までを削除してください。

具体的には、「確かにな」に続く「そこをちょっと考えてみたいんですけれども」から始まり、「例えばなんですがプロダクトというものを起点に」「プロダクトを作ることに関わる職種っていくつかあると思うんですけれども」「そのうちの一つがおそらくFDE的なものだと思うんですが」を含むブロックをカット対象にします。

---

### 仕切り直し・進行確認ブロック

**【カット】**
「分かりましたありがとうございます」の後の進行確認・仕切り直しブロック全体をカットしてください。

具体的には、「ありがとうございます」「メッセージとしては大丈夫ですインタビュー」「元も話ばっかりしちゃったけど大丈夫ですか」「いや割とその整理をしたかったというところはあります」から、「このインタビューの締めじゃないですけれども」までをカットし、「FDEについていろいろとお話を伺ってきた中で」から再開してください。

---

### 「そこは改めて捉え直す」後のブロック

**【カット】**
「そこは改めて捉え直すのが大事なのかなと思います」の発話と字幕は残し、その直後から「FDEに向いている人といいますか」の発話・字幕が始まる直前までを削除してください。

---

### FDEに向く人の説明後の「確かに確かに」

**【カット】**
「自覚がある人は向いてるんじゃないですかね」の直後に入る「確かに確かに」をカットし、「あとFDEって言うてもエンジニアってついてるじゃないですか」へつないでください。

---

### 単独相づちブロックの総則

**【カット】**
テロップが「確かに」だけ、または「なるほど確かに」「確かに確かに」「確かにな」だけとなる単独相づちブロックは、全体的に削除対象としてください。

※「確かにそうですよね」「確かに大規模」「確かに本当に前線に配備されるエンジニアですし」など、後続の意味内容を含む発話は、この総則だけでは削除しません。個別指示がある場合のみカットしてください。
"""


def main() -> None:
    payload = write_transcript()
    REVIEW_OUT.write_text(build_revised_markdown(), encoding="utf-8")
    print(
        json.dumps(
            {
                "transcript": str(TRANSCRIPT_OUT),
                "review": str(REVIEW_OUT),
                "segments": len(payload["segments"]),
                "subtitleUnits": len(payload["subtitle_units"]),
                "reviewAlignmentItems": len(payload["review_alignment"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
