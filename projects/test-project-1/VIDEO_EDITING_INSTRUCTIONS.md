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
- sample-1 参照動画サンプルから検出した上部帯右側の薄い色分割: separator `xNorm=0.952563`, right tint `#5F5AF5`, separator color `#605CF5`
- 白い左上ロゴパネル: slanted polygon
- ロゴ検出 bbox: `[61, 45, 310, 105]`
- 帯の微妙な色差は、検出したRGB stops、下部帯内の軽い色変化、上部帯右側の薄い色分割で再現する
- 下部の紫線は途中で切らず、全幅に対して1本の連続した gradient band として描画する
- 左上ロゴパネルと右側帯の斜め境界は、4倍解像度で描画してから LANCZOS で縮小し、ガタつきを抑える

sample動画へ適用する時は、上部帯と中央下字幕の両方を確認し、人物の顔が字幕にかぶりにくい位置へ調整する。現在の preview では、検出済み上部帯の高さ約102pxより浅い `69px` 下げに変更し、前回より人物表示を約33px上へ戻している。

プレビュー生成後は必ず timeline を検証する。

```powershell
$env:VIDEO_EDIT_PROJECT='test-project-1'
python scripts\timeline_validate.py --timeline projects\test-project-1\output\timelines\sample11_frame_design_preview.timeline.json --output-report projects\test-project-1\output\reports\sample11_frame_design_preview_timeline_validation.json
```

直近の検証結果:

- timeline validation: valid
- errors: 0
- warnings: 0
- preview metadata: 1280x720 / 約60秒 / h264 + aac

## Sample-1 Catchphrase Collection Preview

`reference-assets/library/collections/layer-x/video/sample-1/sample-1.mp4` の前半約10秒は、キャッチフレーズの出し方と構成を把握するための参照として使う。実際に15秒へカット編集する素材は、このプロジェクトの sample video である `source/video/Interview_with_Michael_Eisen_on_Open_Access_middle_1min.mp4` に限定する。抽出結果、参照アセット側のフック、プロジェクト動画側の編集範囲は JSON として保存する。

現在の catchphrase collection preview は project-local script で生成する。

```powershell
python projects\test-project-1\scripts\build_sample1_catchphrase_collection_preview.py
```

生成物:

- Preview video: `output/videos/preview_sample1_catchphrase_collection.mp4`
- Preview still: `output/images/preview_sample1_catchphrase_collection_t0005.jpg`
- Catchphrase JSON: `output/subtitles/sample1_catchphrase_collection.json`
- Timeline: `output/timelines/sample1_catchphrase_collection_preview.timeline.json`
- Report: `output/reports/sample1_catchphrase_collection_preview_report.json`

参照アセット前半10秒から抽出したフック構成:

- `00:00.0-00:03.4`: `元Palantir社員が語る / FDEの正体とは?`
- `00:03.5-00:06.8`: `コンサルティングやSIerとは / 性質が異なる`
- `00:07.0-00:10.0`: `基本はプロジェクトを / 進行していく仕事`

プロジェクト sample video から選定した実カット:

- `00:00.0-00:05.0`: `An eye-opening experience`
- `00:07.34-00:12.34`: `Something that would have negative consequences`
- `00:20.32-00:25.32`: `But now it was completely obvious`

編集方針:

- プロジェクト sample video の3箇所を、それぞれ約5秒の hard cut clip として連結する
- 3本合計で約15秒の preview にする
- 参照アセット動画は編集素材として使わず、`referenceHookPatterns` として JSON に残す
- 参照側の2つ目の OCR 由来表記 `Sler` は、意味上 `SIer` として正規化して JSON に raw / normalized の両方を残す

プレビュー生成後は必ず timeline を検証する。

```powershell
$env:VIDEO_EDIT_PROJECT='test-project-1'
python scripts\timeline_validate.py --timeline projects\test-project-1\output\timelines\sample1_catchphrase_collection_preview.timeline.json --output-report projects\test-project-1\output\reports\sample1_catchphrase_collection_preview_timeline_validation.json
```

直近の検証結果:

- timeline validation: valid
- errors: 0
- warnings: 0
- preview metadata: 1280x720 / 15.00秒 / h264 + aac

この作業は preview 段階。最終 production render は、カット選択、尺、表示位置、帯デザインがユーザー確認済みになってから実行する。

## Sample-1 Catchphrase Collection Styled Preview

`Sample-1 Catchphrase Collection Preview` の15秒カット編集に、これまで作成した字幕スタイルと sample-11 の帯/ロゴデザインを合成する。実際のカット素材は引き続きプロジェクト sample video のみで、参照アセット動画は字幕スタイル、キャッチフレーズ構成、デザイン解析の参照に限定する。

現在の styled preview は project-local script で生成する。

```powershell
python projects\test-project-1\scripts\build_sample1_catchphrase_collection_styled_preview.py
```

生成物:

- Styled preview video: `output/videos/preview_sample1_catchphrase_collection_styled.mp4`
- Styled preview stills: `output/images/preview_sample1_catchphrase_collection_styled_t0001.jpg`, `output/images/preview_sample1_catchphrase_collection_styled_t0006.jpg`, `output/images/preview_sample1_catchphrase_collection_styled_t0011.jpg`
- Styled subtitle profile: `output/subtitles/sample1_catchphrase_collection_styled_profile.json`
- Animated subtitle overlay: `output/subtitles/sample1_catchphrase_collection_subtitle_overlay.mov`
- Frame overlay: `output/overlays/sample11_frame_design/sample11_frame_overlay.png`
- Timeline: `output/timelines/sample1_catchphrase_collection_styled_preview.timeline.json`
- Report: `output/reports/sample1_catchphrase_collection_styled_preview_report.json`

実装方針:

- プロジェクト sample video の3カットを hard cut で連結する
- sample-1 の発話字幕スタイル、色グラデーション、背景グラデーション、横方向 reveal アニメーションを使う
- 英語キャッチフレーズが箱からはみ出さないよう、この15秒版ではフォント上限を `74px` に抑える
- 参照パターンのうち上寄り字幕は、このプロジェクト映像の人物顔にかからないよう下段へ補正する
- sample-11 の上部太帯、下部細帯、左上ロゴパネル、LayerXロゴを合成する
- 映像本体は sample-11 frame design preview と同じく `69px` 下げで配置する
- 字幕テキストは box height と text bbox から上下中央に配置し、以前の上寄せ補正は使わない
- frame overlay は `OVERLAY_RENDER_SCALE=4` で supersampling し、斜め境界と細線を滑らかにする
- Remotion は検討したが、今回の修正は静的 frame overlay と字幕配置計算の改善で完結するため、既存の PIL/ffmpeg project-local pipeline を継続する

プレビュー生成後は必ず timeline を検証する。

```powershell
$env:VIDEO_EDIT_PROJECT='test-project-1'
python scripts\timeline_validate.py --timeline projects\test-project-1\output\timelines\sample1_catchphrase_collection_styled_preview.timeline.json --output-report projects\test-project-1\output\reports\sample1_catchphrase_collection_styled_preview_timeline_validation.json
```

直近の検証結果:

- timeline validation: valid
- errors: 0
- warnings: 0
- preview metadata: 1280x720 / 15.01秒 / h264 + aac
- visual QA stills: 1秒、6秒、11秒で字幕が顔にかからず、2行字幕もボックス内に収まり、下部線が全幅で連続していることを確認

この作業は preview 段階。最終 production render は、styled preview の字幕位置、フォントサイズ、カット選択、帯デザインがユーザー確認済みになってから実行する。
