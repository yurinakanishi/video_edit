from __future__ import annotations

import json
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRANSCRIPTS_DIR = PROJECT_ROOT / "output" / "transcripts" / "manifest_sources"
REPORTS_DIR = PROJECT_ROOT / "output" / "reports"

# Longer phrases first so partial replacements do not corrupt longer matches.
REPLACEMENTS: list[tuple[str, str]] = [
    # Company / brand (word-dictionary.md)
    ("バックラック授業部", "バクラク事業部"),
    ("バックラック", "バクラク"),
    ("爆落インテリジェンス", "バクラクインテリジェンス"),
    ("バクランク", "バクラク"),
    ("爆落", "バクラク"),
    ("レイヤーエクセロー", "LayerX"),
    ("レイヤーエクセ", "LayerX"),
    ("レイアイクス", "LayerX"),
    ("レイアックス", "LayerX"),
    ("レイアクセ", "LayerX"),
    ("AIXのYouTube", "LayerXのYouTube"),
    ("AXのYouTube", "LayerXのYouTube"),
    ("AXに全職", "LayerXに前職"),
    ("AXを使ったバクラク", "バクラク"),
    ("AXを使った爆落", "バクラク"),
    ("たまたまAXを使った", "たまたまバクラクを"),
    ("フェイレックス", "LayerX"),
    ("楽のプロダクト", "バクラクのプロダクト"),
    ("レイヤーさん入ってて", "LayerXに入ってて"),
    # Domain expert spellings
    ("ドミニクスパート", "ドメインエキスパート"),
    ("ドミニエキスパート", "ドメインエキスパート"),
    ("ドミニキスパート", "ドメインエキスパート"),
    ("ドメイキスパート", "ドメインエキスパート"),
    ("ドミンエキスポート", "ドメインエキスパート"),
    ("ドメインスパーク", "ドメインエキスパート"),
    ("免疫スパーの指揮官", "ドメインエキスパートの指揮官"),
    # Labor / HR terms
    ("ロームメイン", "労務メイン"),
    ("ローム同士", "労務同士"),
    ("ロームだけ", "労務だけ"),
    ("ロームとして", "労務として"),
    ("ロームで開発", "労務で開発"),
    ("ロームで", "労務で"),
    ("ロームを", "労務を"),
    ("ロームと", "労務と"),
    ("ロームだって", "労務だって"),
    ("ローム経営", "労務経験"),
    ("ローン経営", "労務経験者"),
    ("ローンとして", "労務として"),
    ("ローマです", "労務です"),
    ("ローンとか", "労務とか"),
    ("ローム", "労務"),
    ("ローン", "労務"),
    ("ローマ", "労務"),
    # People
    ("モラットさん", "村田さん"),
    ("ネモさん", "根元さん"),
    ("NEMOさん", "根元さん"),
    ("Memoさん", "根元さん"),
    ("エモさん", "根元さん"),
    ("ヤナさん", "矢野さん"),
    ("バクラク事業部のヤナ", "バクラク事業部の矢野"),
    ("ヤナと申します", "矢野と申します"),
    ("ヤナです", "矢野です"),
    ("岩田さん", "村田さん"),
    ("本田さんと一緒に", "本当は一緒に"),
    # Business / accounting terms
    ("社会保険法の司法人", "社会保険労務士"),
    ("司法人", "社労士"),
    ("コンフォレント全般", "コンプライアンス全般"),
    ("全職のメンバー", "前職のメンバー"),
    ("バネジメント", "マネジメント"),
    ("仕分けを打つ", "仕訳を打つ"),
    ("自動仕分け", "自動仕訳"),
    ("夜長払いで", "夜遅くまで"),
    ("月次申し込み", "月次申告"),
    ("金太郎", "勤怠"),
    ("金貸", "勤怠"),
    ("自治企画", "人事企画"),
    ("サースだと", "SaaSだと"),
    ("HCL、HR", "HR"),
    # Role / product wording
    ("PTDM", "PDM"),
    ("PTM", "PDM"),
    ("仮フォード", "軽い"),
    ("行動覚醒", "行動決断"),
    ("ケーブルの視点", "ユーザー視点"),
    ("選挙が", "境界が"),
    ("演じり", "エンジニア"),
    ("通貨で流しちゃう", "慣習で流しちゃう"),
    ("激化されて成長", "磨かれて成長"),
    ("休憩室のチェック", "就業時間のチェック"),
    ("調整器になる", "突合する"),
    ("コンプになる", "コンプラになる"),
    ("QKさん", "エンジニアさん"),
    ("エースが詰まってる", "エッセンスが詰まってる"),
    ("トレンチャー", "トレーナー"),
    ("マクロフィス", "属人化"),
    ("フラッグオフィス", "バックオフィス"),
    ("裁判員がいて", "判例や"),
    ("AIが逃げない", "AIに逃げない"),
    ("頭書きにしている", "限定的に考えている"),
    ("スキボーで喋っても", "素振りで喋っても"),
    ("観光でやっていた", "慣行でやっていた"),
    ("暗黙地とか", "暗黙知とか"),
    ("店長を務めた", "転職を決めた"),
    ("4歳くらい", "40歳くらい"),
    ("例書考えてない", "転職考えてない"),
    ("薄毛みたいな", "モヤモヤみたいな"),
    ("ドバイシして", "ドライにして"),
    ("先生コミュニティ", "支援コミュニティ"),
    ("仕上げたり", "勤めたり"),
    ("ひもが", "根元が"),
    ("スラッグネーム", "通称・ニックネーム"),
    ("ホームネーム", "呼び名"),
    ("社内の2店舗", "社内のハンドルネーム"),
    ("会社名は根本", "社内では根本"),
    ("大きい部の形", "大きな部の形"),
    ("入手はされた", "入社された"),
    # Rehearsal / setup dialogue
    ("修理構成すぎる", "司会構成すぎる"),
    ("修理で大丈夫", "司会で大丈夫"),
    ("修理すごい", "司会すごい"),
    ("修理じゃない", "司会じゃない"),
    ("一隣りが、最初春入る", "一連が最初入る"),
    ("すい出し", "スイ出し"),
    ("信仰かも", "神回かも"),
    ("長尻喋っていけば", "長々喋っていけば"),
    ("お尻も後で", "締めも後で"),
    ("あいさんと", "挨拶を"),
    ("法的に話された", "一方的に話された"),
    ("感情になっちゃう", "単調になっちゃう"),
    ("異常な緊張感", "以上な緊張感"),
    ("開けないくらい", "遠慮しないくらい"),
    ("徳がすごい好き", "LayerXがすごい好き"),
    ("やっぱり徳と", "やっぱりLayerXと"),
    ("すごく個人的に徳が", "すごく個人的にLayerXが"),
    # Additional contextual fixes
    ("壁打ちだとさせて", "壁打ち相手としてさせて"),
    ("本当は一緒に労務だけやると全職", "本当は労務だけやると専職"),
    ("これだったらいけないんじゃないか", "これだったらいけるんじゃないか"),
    ("コードをかけなくて", "コードを書けなくて"),
    ("コードをかけって", "コードを書けって"),
    ("プロダクト マネージャーメイン", "プロダクトマネージャーがメイン"),
    ("なんかん?", "なんで?"),
    ("おやおやみたいな", "もやもやみたいな"),
    ("落とし込んでもらえるっていうんですかね", "落とし込んでもらえるっていうんですね"),
    ("すごく大変な人としてあって", "すごくいい文化としてあって"),
    ("悪いとかたいなと", "違うとかタイミングよく"),
    ("伝説的な議論", "建設的な議論"),
    ("税理さん", "税理士さん"),
    ("どんなかの判断", "どんな下級審の判断"),
    ("お会いをするために", "合意をするために"),
    ("間違いは選んでいない", "間違いなく選んでいない"),
    ("強烈に作ることができます", "強烈に突きつけられることができます"),
    ("気合が結構自信作ですね", "気合が結構自信作りですね"),
    ("また4年も", "またこういう"),
    ("俗人性", "属人性"),
    ("俗人化", "属人化"),
    ("音で飛び合わせ", "雑に飛び合わせ"),
    ("課長できてない", "確信持ててない"),
    ("メディアできてない", "イメージできてない"),
    ("人席に向き合う", "現場に向き合う"),
    ("削るのめちゃめちゃ", "学ぶの、めちゃめちゃ"),
    ("向けようが変わる", "向き合い方が変わる"),
    ("経験を張ると", "経験を積むと"),
    ("コーポレート真面目", "コーポレートっぽく真面目"),
    ("役回り", "役割"),
    ("AXのYouTube", "LayerXのYouTube"),
    ("AIXのYouTube", "LayerXのYouTube"),
    ("だいぶ書いてやってました", "だいぶ経理やってました"),
    ("もともと趣味がある", "もともと実務がある"),
    ("前衛というか先進", "先端というか先進"),
    ("ちょっとやってしまいそうな気がする", "ちょっと長くなってしまいそうな気がする"),
    ("人間によるための話", "人間による手作業の話"),
    ("村瀬さん", "村田さん"),
    ("どっちの方が弱くなっているのか", "どっちの方が喋れなくなっているのか"),
    ("緑です", "了解です"),
    ("お水をお借りお願いします", "お水をお借り願いします"),
]


def fix_text(text: str) -> str:
    updated = text
    for old, new in REPLACEMENTS:
        updated = updated.replace(old, new)
    return updated


def fix_transcript_payload(payload: dict) -> tuple[dict, int]:
    changes = 0
    segments = payload.get("segments")
    if isinstance(segments, list):
        for segment in segments:
            if not isinstance(segment, dict):
                continue
            original = str(segment.get("text", ""))
            corrected = fix_text(original)
            if corrected != original:
                segment["text"] = corrected
                changes += 1
    if "text" in payload and isinstance(segments, list):
        payload["text"] = "".join(str(segment.get("text", "")) for segment in segments).strip()
    return payload, changes


def fix_srt(path: Path) -> int:
    content = path.read_text(encoding="utf-8")
    blocks = re.split(r"\n\s*\n", content.strip(), flags=re.MULTILINE)
    changes = 0
    fixed_blocks: list[str] = []
    time_line = re.compile(r"^\d{2}:\d{2}:\d{2},\d{3}\s+-->\s+\d{2}:\d{2}:\d{2},\d{3}$")

    for block in blocks:
        lines = block.splitlines()
        if not lines:
            continue
        out_lines: list[str] = []
        for line in lines:
            if line.isdigit() or time_line.match(line):
                out_lines.append(line)
                continue
            corrected = fix_text(line)
            if corrected != line:
                changes += 1
            out_lines.append(corrected)
        fixed_blocks.append("\n".join(out_lines))

    path.write_text("\n\n".join(fixed_blocks) + "\n", encoding="utf-8")
    return changes


def fix_json_transcript(path: Path) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    updated, changes = fix_transcript_payload(payload)
    path.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
    return changes


def fix_json_text_fields(node: object, changes: list[int]) -> object:
    if isinstance(node, dict):
        return {key: fix_json_text_fields(value, changes) for key, value in node.items()}
    if isinstance(node, list):
        return [fix_json_text_fields(item, changes) for item in node]
    if isinstance(node, str):
        corrected = fix_text(node)
        if corrected != node:
            changes[0] += 1
        return corrected
    return node


def fix_json_report(path: Path) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    changes = [0]
    updated = fix_json_text_fields(payload, changes)
    path.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
    return changes[0]


def main() -> None:
    targets: list[Path] = [
        TRANSCRIPTS_DIR / "primary.srt",
        TRANSCRIPTS_DIR / "master_three_people.srt",
        TRANSCRIPTS_DIR / "primary.json",
        TRANSCRIPTS_DIR / "master_three_people.json",
        REPORTS_DIR / "transcript.json",
        REPORTS_DIR / "semantic_marks.json",
        REPORTS_DIR / "content_window.json",
        REPORTS_DIR / "people_map.json",
    ]
    summary: list[dict[str, str | int]] = []
    for path in targets:
        if not path.exists():
            summary.append({"path": str(path), "status": "missing", "changes": 0})
            continue
        if path.suffix == ".srt":
            changes = fix_srt(path)
        elif path.name in {"semantic_marks.json", "content_window.json", "people_map.json"}:
            changes = fix_json_report(path)
        else:
            changes = fix_json_transcript(path)
        summary.append({"path": str(path), "status": "updated", "changes": changes})

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
