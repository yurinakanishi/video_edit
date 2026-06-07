# Test Project 1

このプロジェクトは、`Interview_with_Michael_Eisen_on_Open_Access.webm` の中央付近から1分を切り出したテストプロジェクトです。

- 元ファイル: `C:\Users\yurin\Downloads\Interview_with_Michael_Eisen_on_Open_Access.webm`
- 切り出し範囲: `00:07:55.220` から約60秒
- Source video: `source/video/Interview_with_Michael_Eisen_on_Open_Access_middle_1min.mp4`

プロジェクト固有の追加処理が必要な場合は、`scripts/` 配下に project-local script として追加してください。生成物は `output/` 配下に保存してください。

## Sample-1 Speech Subtitle Preview

このプロジェクトでは、`reference-assets/library/collections/layer-x/video/sample-1/analysis.json` の `role == "subtitle"` のみを参照し、発話字幕スタイルを再現する。上部ロゴ、上部タイトル、その他の `logo_text` / `title` / `small_text` は字幕スタイル対象外。

現在の字幕プレビューは project-local script で生成する。

```powershell
python projects\test-project-1\scripts\build_sample1_speech_subtitle_preview.py
```

生成物:

- Preview video: `output/videos/preview_sample1_speech_subtitles.mp4`
- Style + animation profile JSON: `output/subtitles/sample1_speech_subtitle_style_profile.json`
- Extracted reference pattern library JSON: `output/subtitles/sample1_speech_subtitle_pattern_library.json`
- Overlay manifest JSON: `output/subtitles/sample1_speech_subtitle_overlays.json`
- Animated alpha overlay video: `output/subtitles/sample1_speech_subtitle_overlay.mov`
- Corrected transcript text: `output/transcripts/manifest_sources/primary_corrected.txt`
- Corrected subtitle SRT: `output/transcripts/manifest_sources/primary_corrected.srt`
- Timeline: `output/timelines/sample1_speech_subtitle_preview.timeline.json`
- Report: `output/reports/sample1_speech_subtitle_preview_report.json`

字幕スタイルは ASS ではなく、透明 overlay として描画する。理由は、sample-1 の発話字幕が大きな太字、紫/白のグラデーション背景、白/紫の文字色、横方向 reveal アニメーション、2行目の遅延表示を含み、ASS の単純な字幕背景では再現しづらいため。

sample-1 の発話字幕は、常に中央寄せ・固定色順ではない。`sample1_speech_subtitle_pattern_library.json` では、参照動画の整数秒サンプルフレームを走査し、各字幕行の位置、横アンカー、幅、背景色種別、背景グラデーション、文字色種別を抽出する。パターンは `lineCount + rowBand + anchor + widthBucket + backgroundKind + textKind` でクラスタリングする。

プレビューでは、抽出済みパターンから字幕チャンクごとに決定的ランダムで1つを選ぶ。毎フレーム完全ランダムにはせず、同一字幕の表示中は同じパターンを維持してちらつきを避ける。

現在の抽出結果:

- 参照対象: `reference-assets/library/collections/layer-x/video/sample-1/analysis.json`
- 参照サンプル: 整数秒フレームのみ
- 解析済み参照フレーム数: 53
- 抽出済み字幕パターン数: 16
- パターン例: 左寄せ紫背景/白文字、中央寄せ紫背景/白文字、右寄せ白背景/紫グラデーション文字、1行/2行/3行構成
- 現在の確認済み preview: `output/videos/preview_sample1_speech_subtitles.mp4`
- 確認用 still: `output/images/preview_sample1_speech_subtitles_t0005.jpg`
- 白背景 + 紫グラデーション文字の確認用 still: `output/images/preview_sample1_speech_subtitles_t0010_5.jpg`

`sample1_speech_subtitle_style_profile.json` には以下を含める。

- 参照解析ファイルと対象 role
- 発話字幕 bbox / font size / row position の測定値
- 1秒ごとの参照フレームから抽出したレイアウト/背景/文字色パターン
- 文字色、背景グラデーション、角丸、padding、shadow
- 白背景に載る紫文字の左から右への薄い文字色グラデーション
- `horizontal-reveal` アニメーション
- 2行目の stagger
- 短い fade out
- 解析上の observation

プレビュー生成後は必ず timeline を検証する。

```powershell
$env:VIDEO_EDIT_PROJECT='test-project-1'
python scripts\timeline_validate.py --timeline projects\test-project-1\output\timelines\sample1_speech_subtitle_preview.timeline.json --output-report projects\test-project-1\output\reports\sample1_speech_subtitle_preview_timeline_validation.json
```

直近の検証結果:

- timeline validation: valid
- errors: 0
- warnings: 0
- preview metadata: 1280x720 / 60.06秒 / h264 + aac

この作業は preview 段階。最終 production render は、字幕のサイズ、位置、グラデーション、タイミング、アニメーションがユーザー確認済みになってから実行する。

## Sample-11 Frame Design Preview

`C:\Users\yurin\Downloads\Screenshot 2026-06-07 101542.png` は、`layer-x/images/sample-11` の新しい参照アセットとして登録する。参照ライブラリ側では Downloads の元画像を保持し、コピーを以下に置く。

- Reference asset: `reference-assets/library/collections/layer-x/images/sample-11/sample-11.png`
- Reference analysis: `reference-assets/library/collections/layer-x/images/sample-11/analysis.json`
- Debug overlay: `reference-assets/library/collections/layer-x/images/sample-11/debug-overlays/frame_0000_debug.jpg`

作業プロジェクト側にも同じ参照画像をコピーする。

- Project reference image: `source/reference/sample-11-reference.png`

ロゴは、ユーザー指定どおり Downloads からプロジェクト内へ移動してから使用する。

- Project logo: `source/assets/LayerX_Logo_Horizontal_RGB_Color.png`

現在の frame design preview は project-local script で生成する。

```powershell
python projects\test-project-1\scripts\build_sample11_frame_design_preview.py
```

生成物:

- Preview video: `output/videos/preview_sample11_frame_design.mp4`
- Preview still: `output/images/preview_sample11_frame_design_t0005.jpg`
- Design profile JSON: `output/subtitles/sample11_frame_design_profile.json`
- Frame overlay PNG: `output/overlays/sample11_frame_design/sample11_frame_overlay.png`
- Timeline: `output/timelines/sample11_frame_design_preview.timeline.json`
- Report: `output/reports/sample11_frame_design_preview_report.json`

解析内容:

- 上部帯: 146px / 1034px
- 下部帯: 28px / 1034px
- 上部帯 RGB stops: `#5A51FE`, `#5A51FD`, `#5D60FE`
- 下部帯 RGB stops: `#5B59FD`, `#656AFD`, `#747FFC`
- 白い左上ロゴパネル: slanted polygon
- ロゴ検出 bbox: `[61, 45, 310, 105]`
- 帯の微妙な色差は、検出したRGB stopsと下部帯内の軽い色変化で再現する

sample動画へ適用する時は、人物の顔が上部帯にかからないよう、映像を検出済み上部帯の高さ分だけ下げる。現在の preview では 1280x720 上で約102px下げている。

プレビュー生成後は必ず timeline を検証する。

```powershell
$env:VIDEO_EDIT_PROJECT='test-project-1'
python scripts\timeline_validate.py --timeline projects\test-project-1\output\timelines\sample11_frame_design_preview.timeline.json --output-report projects\test-project-1\output\reports\sample11_frame_design_preview_timeline_validation.json
```

直近の検証結果:

- reference asset validation: ok
- timeline validation: valid
- errors: 0
- warnings: 0
- preview metadata: 1280x720 / 約60秒 / h264 + aac
