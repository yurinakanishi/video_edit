# ST7_7550 Video Edit Method

This document describes the current working method for editing the `ST7_7550` 5-minute multicam video.

The current preferred outputs are the PNG-overlay renders. Long silent sections are shortened automatically by the render scripts.

```text
output\videos\ST7_7550_multicam_cut_5min_png_titles_punchlines.mp4
output\videos\ST7_7550_multicam_cut_5min_png_titles_full_transcript.mp4
output\videos\ST7_7550_multicam_cut_1min_multi_cut_sound2_audio_color_matched_full_transcript.mp4
```

The strict transcript-match base remains the camera-sync source, but the older `*_logo_text_subtitled.mp4` ASS-burned output is no longer the preferred final.

## Working Folder

```text
C:\Users\yurin\Desktop\video_edit
```

## Project Layout

```text
scripts\                  Python pipeline and render tools
source\video\             Local source camera/video files
source\audio\             Local source recorder/audio files
source\images\            Logo and source image assets
source\subtitles\         Source and hand-corrected subtitle files
source\thumbnail\         Thumbnail frame assets and visual references
source\text\              Source text assets
output\videos\            Rendered MP4 outputs and previews
output\overlays\          Generated PNG/ASS overlay assets
output\thumbnails\        Generated thumbnail candidates and analysis JSON
output\transcripts\       Generated transcript and sync artifacts
output\audio\             Extracted audio outputs
output\diagnostics\       Review clips and diagnostic artifacts
output\reports\           Generated JSON reports
config\                   Project configuration and correction data
docs\                     Method notes and reference docs
app\                      Electron UI source
```

Raw camera source files are intentionally not committed. Scripts use this default source root for `2cam` / `3cam` inputs:

```text
C:\Users\yurin\Downloads\cdc260515 mov\cdc260515 mov
```

Override it when needed:

```powershell
$env:VIDEO_EDIT_SOURCE_ROOT='D:\path\to\cdc260515 mov'
```

## Key Decision

Use the original `1cam` video audio as the master audio.

Do not use the external WAV as the final audio source for this edit. The WAV metadata was not reliably synced to the camera clocks, and waveform matching against the external WAV produced visible timeline drift.

## Main Inputs

```text
source\video\1cam\ST7_7550_overlap_5min.mp4
..\2cam\0H4A7192.MP4
..\2cam\0H4A7193.MP4
..\3cam\IMG_2316.MP4
source\images\type-logo-transparent-cropped.png
source\thumbnail\etype260515_p_takei\ST-*.jpg
source\thumbnail\references\*.png
output\overlays\ai_engineer_now_title.ass
output\overlays\ai_engineer_now_title.png
scripts\generate_title_png_overlay.py
scripts\generate_thumbnail_candidates.py
output\overlays\punchline_subtitles.ass
scripts\generate_punchline_subtitles.py
output\overlays\punchline_png_overlays\*.png
scripts\generate_punchline_png_overlays.py
output\overlays\full_transcript_png_overlays\*.png
scripts\generate_full_transcript_png_overlays.py
scripts\subtitle_png_style.py
scripts\apply_st7_7550_subtitle_corrections.py
config\subtitle_corrections.json
scripts\subtitle_review_cycle.py
scripts\render_final_png_overlays.py
scripts\shorten_silences.py
scripts\transcribe_sound2.py
scripts\compare_sound2_transcripts.py
scripts\refine_sound2_audio_offset.py
scripts\replace_audio_with_sound2.py
```

## Tool Paths

Use the user-installed Python directly:

```powershell
$env:PYTHONUTF8='1'
& 'C:\Users\yurin\AppData\Local\Python\pythoncore-3.14-64\python.exe' -c "import sys; print(sys.executable)"
```

`ffmpeg` and `ffprobe` are available at:

```text
C:\ProgramData\chocolatey\bin\ffmpeg.exe
C:\ProgramData\chocolatey\bin\ffprobe.exe
```

## Step 1: Make The 5-Minute Master Clip

The master clip is:

```text
1cam\ST7_7550_overlap_5min.mp4
```

This is the 5-minute section cut from `1cam\ST7_7550.MP4`.

The audio from this clip is used as the timeline master for every later render.

## Step 2: Transcribe The Master Audio

The subtitle used for the final edit was generated from the original video audio, not the external WAV.

Output files:

```text
video_original_audio\ST7_7550_overlap_5min_original_audio.wav
subs_video_original_audio\ST7_7550_overlap_5min_original_audio.srt
subs_video_original_audio\ST7_7550_overlap_5min_original_audio_corrected.srt
```

Whisper command pattern:

```powershell
$env:PYTHONUTF8='1'
& 'C:\Users\yurin\AppData\Local\Python\pythoncore-3.14-64\python.exe' `
  -m whisper `
  '.\video_original_audio\ST7_7550_overlap_5min_original_audio.wav' `
  --model small `
  --language ja `
  --task transcribe `
  --output_dir '.\subs_video_original_audio' `
  --output_format srt `
  --verbose False
```

## Step 2A: Review And Correct Transcript Naturalness

Do not feed the raw Whisper SRT directly into final subtitle rendering. After transcription, run a review pass that applies known corrections, flags unnatural-looking Japanese, and exports high-quality `sound-2` audio clips for rechecking.

Correction file:

```text
subtitle_corrections.json
```

This video's fixed, hardcoded subtitle corrections live in a separate script:

```text
apply_st7_7550_subtitle_corrections.py
```

Review script:

```text
subtitle_review_cycle.py
```

Run:

```powershell
Set-Location 'C:\Users\yurin\Desktop\video_edit'
$env:PYTHONUTF8='1'
& 'C:\Users\yurin\AppData\Local\Python\pythoncore-3.14-64\python.exe' .\subtitle_review_cycle.py
```

For this video, `render_1min_color_matched.py --mode full` and `render_final_png_overlays.py --mode full` run `apply_st7_7550_subtitle_corrections.py` before generating full transcript PNG overlays.

Outputs:

```text
subs_video_original_audio\ST7_7550_overlap_5min_original_audio_corrected.srt
subtitle_review\subtitle_review_report.md
subtitle_review\clips\caption_*.wav
```

The review clips are extracted from the aligned `sound-2` WAV using `sound2_transcripts\sound2_audio_offset_refined.json`, with 1 second of padding before and after the caption. Use these clips to recheck suspicious subtitles against the higher-quality recorder audio.

Optional high-resolution retranscription of the review clips:

```powershell
& 'C:\Users\yurin\AppData\Local\Python\pythoncore-3.14-64\python.exe' .\subtitle_review_cycle.py `
  --transcribe-review `
  --review-model medium
```

Current manual corrections include:

```text
スケルメリット -> スケールメリット
ある程度先ほどの話になったのが -> ある程度先ほどの話の中からもお伺い
一応ちょっとしたいんですが -> もう一度ちょっと聞きたいんですが
そもそも論争について -> そもそもあの論争について
論争がなっちゃうのかな -> 論争になっちゃうのかな
```

`generate_full_transcript_png_overlays.py` and `classify_full_transcript_speakers.py` automatically prefer the corrected SRT when it exists. If a subtitle correction is added later, rerun:

```powershell
& 'C:\Users\yurin\AppData\Local\Python\pythoncore-3.14-64\python.exe' .\subtitle_review_cycle.py
& 'C:\Users\yurin\AppData\Local\Python\pythoncore-3.14-64\python.exe' .\render_1min_color_matched.py --mode full --skip-base
```

## Step 3: Analyze Camera Blocking With OpenCV

OpenCV was used to compare representative frames and understand camera roles.

Script:

```text
.\analyze_multicam_blocking.py
```

Run:

```powershell
Set-Location 'C:\Users\yurin\Desktop\video_edit'
$env:PYTHONUTF8='1'
& 'C:\Users\yurin\AppData\Local\Python\pythoncore-3.14-64\python.exe' .\analyze_multicam_blocking.py
```

Camera roles:

- `1cam`: stable master shot
- `2cam`: tighter same-axis shot
- `3cam`: later-section alternate angle

## Step 4: Strict Strong-Match Cut Plan

Only strong transcript matches are used for sub-camera cuts. Everything else stays on the `1cam` master.

```text
00:00.000-00:09.000  1cam  ST7_7550_overlap_5min.mp4
00:09.000-00:21.500  2cam  0H4A7192.MP4  source 18:31.710
00:21.500-01:25.000  1cam  ST7_7550_overlap_5min.mp4
01:25.000-02:32.000  2cam  0H4A7193.MP4  source 00:59.640
02:32.000-03:33.000  1cam  ST7_7550_overlap_5min.mp4
03:33.000-04:17.000  3cam  IMG_2316.MP4  source 01:43.820
04:17.000-05:00.000  1cam  ST7_7550_overlap_5min.mp4
```

`0H4A7192.MP4` is limited to `00:09.000-00:21.500` on the master timeline because the matching source section is near the end of that camera file.

## Step 5: Why Metadata And Full Waveform Sync Were Not Enough

The first multicam attempts used camera metadata and then whole-track waveform matching.

That was not reliable enough:

- Camera `creation_time` values are not a shared absolute clock.
- The external WAV recorder was not jam-synced with the cameras.
- Camera audio differs by camera position, so full-track waveform correlation can pick the wrong offset.
- Long-GOP H.264 clips can also behave poorly when cut only with input-side `-ss`.

The better approach is:

1. Transcribe each camera's internal audio.
2. Use matching transcript segments to find the same spoken phrase.
3. Run waveform matching only near that text-matched anchor.
4. Render with `trim` / `atrim`, not only input-side `-ss`.

## Step 6: Transcript-Guided Sync

Script:

```text
.\transcribe_align_st7_7550_multicam.py
```

Run:

```powershell
Set-Location 'C:\Users\yurin\Desktop\video_edit'
$env:PYTHONUTF8='1'
& 'C:\Users\yurin\AppData\Local\Python\pythoncore-3.14-64\python.exe' .\transcribe_align_st7_7550_multicam.py
```

Outputs:

```text
transcript_sync\1cam_master_ST7_7550_overlap_5min.json
transcript_sync\2cam_0H4A7189.json
transcript_sync\3cam_IMG_2316.json
transcript_sync\transcript_wave_sync_offsets.json
```

Final sync offsets from this method:

```text
2cam/0H4A7189 offset: -207.90s  <- weak transcript match; do not use automatically
3cam/IMG_2316 offset:  109.18s  <- strong transcript match
```

Interpretation:

```text
alt_video_start = master_timeline_start - offset
```

Example:

```text
3cam segment at master 227.000s:
3cam video start = 227.000 - 109.180 = 117.820s
```

## Step 6A: Strict All-Camera Transcript Comparison

After the first transcript-guided edit still looked out of sync, all `2cam` and `3cam` videos were transcribed and compared against the 5-minute `1cam` master. Weak transcript matches must not be used for automatic multicam switching.

Script:

```text
.\transcribe_compare_all_st7_7550_multicam.py
```

Run:

```powershell
Set-Location 'C:\Users\yurin\Desktop\video_edit'
$env:PYTHONUTF8='1'
& 'C:\Users\yurin\AppData\Local\Python\pythoncore-3.14-64\python.exe' .\transcribe_compare_all_st7_7550_multicam.py
```

Outputs:

```text
transcript_sync_all\all_multicam_transcript_comparison.json
transcript_sync_all\all_multicam_transcript_comparison.md
```

Automatic-use threshold:

```text
strong: score >= 0.82
usable_review: score >= 0.70, manual review required
weak: score < 0.70, do not use
```

Strong matches found:

```text
2cam\0H4A7192.MP4  score 0.926  offset -1103.000s  master 00:09-00:15  alt 18:32-18:38
2cam\0H4A7193.MP4  score 1.000  offset    26.000s  master 01:25-02:32  alt 00:59-02:07
3cam\IMG_2316.MP4  score 1.000  offset   109.000s  master 03:33-04:17  alt 01:44-02:28
```

Important rejected matches:

```text
2cam\0H4A7189.MP4  best score 0.596  weak
2cam\0H4A7190.MP4  best score 0.525  weak
3cam files except IMG_2316.MP4 are weak for this 5-minute master
```

Current rule:

```text
Do not cut to 0H4A7189.MP4 or 0H4A7190.MP4 based on transcript sync.
Use only 0H4A7192.MP4, 0H4A7193.MP4, and IMG_2316.MP4 for automatic multicam switching, then refine locally with waveform if needed.
```

## Step 6B: Local Waveform Refinement

The strong transcript matches get the camera to the correct phrase, but they are not precise enough for `0.1s-0.5s` lip/audio alignment. For final timing, run local waveform correlation only around the already confirmed strong transcript windows.

Script:

```text
.\refine_st7_7550_strong_wave_offsets.py
```

Run:

```powershell
Set-Location 'C:\Users\yurin\Desktop\video_edit'
$env:PYTHONUTF8='1'
& 'C:\Users\yurin\AppData\Local\Python\pythoncore-3.14-64\python.exe' .\refine_st7_7550_strong_wave_offsets.py
```

Output:

```text
transcript_sync_all\strong_local_wave_refine.json
```

Applied local waveform corrections:

```text
2cam\0H4A7192.MP4  1112.000s -> 1111.710s  shift -0.290s  score 0.121
2cam\0H4A7193.MP4    59.000s ->   59.640s  shift +0.640s  score 0.837
3cam\IMG_2316.MP4   104.000s ->  103.820s  shift -0.180s  score 0.769
```

Note: `0H4A7192.MP4` has a weaker waveform score because the usable cut is short and near the tail of the long source file. It is still transcript-strong, but it should be visually checked.

## Step 7: Render The Strict Strong-Match Multicam Edit

Script:

```text
.\build_st7_7550_strong_transcript_multicam.py
```

Run:

```powershell
Set-Location 'C:\Users\yurin\Desktop\video_edit'
$env:PYTHONUTF8='1'
& 'C:\Users\yurin\AppData\Local\Python\pythoncore-3.14-64\python.exe' .\build_st7_7550_strong_transcript_multicam.py
```

This script:

- cuts video segments using `trim`
- cuts master audio using `atrim`
- keeps `1cam\ST7_7550_overlap_5min.mp4` as the only audio master
- concatenates the segments
- outputs the clean multicam base video before final graphic/subtitle overlays

The left-top title ASS file was copied from:

```text
C:\Users\yurin\Downloads\ai_engineer_now_title.ass
```

For the final render, the copied ASS file was normalized to the video resolution to avoid subtitle scaling blur:

```text
PlayResX: 1920
PlayResY: 1080
Fontname: Yu Gothic UI Semibold
```

## Step 8: Graphic And Subtitle Overlay Method

Final graphics and subtitles are applied as overlay layers after the clean multicam base is rendered. This keeps camera blocking and visual typography separate.

Layer order:

```text
1. base multicam video
2. right-top logo: type-logo-transparent-cropped.png, scaled to 48px height
3. persistent title: ai_engineer_now_title.png
4. one subtitle mode only:
   - punchline mode: punchline_png_overlays\*.png
   - full transcript mode: full_transcript_png_overlays\*.png
```

Current title treatment:

```text
ai_engineer_now_title.png
text: AIエンジニアの今
position: top-left
background: tight Pillow-generated white to light-purple caption bar matched to actual rendered text pixels
accent: purple lower stripe
text color: purple
font: Yu Gothic UI Semibold, rendered into a PNG layer
tracking: 4px between characters
note: use PNG overlay for final renders instead of ASS when precise box fit is required
```

Subtitle modes:

```text
mode: punchline
purpose: show only selected important utterances
generator: generate_punchline_png_overlays.py
manifest: punchline_png_overlays\manifest.json
style: white tight text box + red bold text + sharp red lower-right shadow
animation: fade in/out + pop scale + upward slide
text rule: use exact SRT utterance text only; do not summarize or rewrite
font sizing rule: keep a fixed font size; do not shrink text to fit
line break rule: if text is too long, wrap into 2 or 3 natural Japanese lines; never leave a tiny one-character or few-character leftover line
output, 5min: ST7_7550_multicam_cut_5min_png_titles_punchlines.mp4
output, 1min color matched: ST7_7550_multicam_cut_1min_multi_cut_sound2_audio_color_matched.mp4

mode: full
purpose: show every caption from the full transcription
generator: generate_full_transcript_png_overlays.py
manifest: full_transcript_png_overlays\manifest.json
style, onscreen speaker: light purple rounded box + thin white text
style, offscreen interviewer: black rounded box + thin white text
font sizing rule: keep a fixed font size; do not shrink text to fit
line break rule: if text is too long, wrap into natural Japanese lines; never leave a tiny one-character or few-character leftover line
animation: none
speaker role data: full_transcript_speaker_roles.json
speaker role script: classify_full_transcript_speakers.py
output, 5min: ST7_7550_multicam_cut_5min_png_titles_full_transcript.mp4
output, 1min color matched: ST7_7550_multicam_cut_1min_multi_cut_sound2_audio_color_matched_full_transcript.mp4
```

Current punchline treatment details:

```text
generated by: generate_punchline_png_overlays.py
font: Yu Gothic UI Semibold / measured with C:\Windows\Fonts\YuGothB.ttc
font size: 100 fixed
text color: red, thickened with same-color outline
tracking: 4px between characters
position: lower, similar to normal full subtitles, with 36px bottom margin before shadow
background: separate white rectangle per subtitle line, dynamically measured from that line's text width
padding: Pillow PNG box, 18px horizontal and 8px vertical
shadow: sharp red rectangle per line, same shape as the white rectangle, offset to lower-right
animation: fade + pop scale + upward slide; box and shadow slide with the text
wrapping: long exact utterances are split into natural Japanese line breaks instead of reducing font size; avoid tiny leftover lines
```

Current full transcript treatment details:

```text
generated by: generate_full_transcript_png_overlays.py
font: Yu Gothic UI Semibold / measured with C:\Windows\Fonts\YuGothB.ttc
font size: 80 fixed
onscreen speaker: light purple rounded box + thin white text
offscreen interviewer: black rounded box + thin white text
wrapping: measure rendered pixel width; keep one line when it fits within the 1760px overlay max width; otherwise wrap into balanced natural Japanese line breaks instead of reducing font size
minimum line rule: do not produce very short leftover lines; prefer a balanced 2-line split near particles, punctuation, or phrase boundaries
speaker role data: full_transcript_speaker_roles.json
speaker role script: classify_full_transcript_speakers.py
red shadow: none
animation: none
mode command, 5min: render_final_png_overlays.py --mode full
mode command, 1min color matched: render_1min_color_matched.py --mode full --skip-base
```

The interviewer detection uses turn structure as the primary signal and stores OpenCV mouth-motion diagnostic scores. Mouth motion alone is not used as the final classifier because the visible speaker can nod or move while listening, which creates false positives.

Only one subtitle mode should be rendered at a time. Punchline subtitles and full transcript subtitles are mutually exclusive layers.

Punchline subtitles must use actual utterance text from `subs_video_original_audio\ST7_7550_overlap_5min_original_audio.srt`. Do not summarize, rewrite, correct, or invent wording. If a punchline spans multiple SRT items, concatenate only exact SRT text and use `\N` for line breaks.

Do not force a fixed number of punchlines. It is valid to have many, few, or none.

Regenerate the PNG overlays after changing punchline timing, text, or style:

```powershell
Set-Location 'C:\Users\yurin\Desktop\video_edit'
$env:PYTHONUTF8='1'
& 'C:\Users\yurin\AppData\Local\Python\pythoncore-3.14-64\python.exe' .\generate_punchline_png_overlays.py
```

Regenerate the full transcript PNG overlays after changing full-caption style or speaker roles:

```powershell
Set-Location 'C:\Users\yurin\Desktop\video_edit'
$env:PYTHONUTF8='1'
& 'C:\Users\yurin\AppData\Local\Python\pythoncore-3.14-64\python.exe' .\classify_full_transcript_speakers.py
& 'C:\Users\yurin\AppData\Local\Python\pythoncore-3.14-64\python.exe' .\generate_full_transcript_png_overlays.py
```

Current punchline lines:

```text
00:00-00:04  定義で言うと強いプロダクトというか / プロダクトが中心にあって
00:09-00:13  届けるというところだと思っているので
00:15-00:20  そこで一定なスケルメリットが / 出るということが大事だと思いますね
01:11-01:13  過剰反応されてるだけな気がしますけどね
01:27-01:33  さすがに薄々AIによって / 何かが変わるなっていうのは
01:37-01:41  どうなるんだろうっていう / 漠然とした不安がある中で
01:56-02:02  あなたの仕事例えばライターの仕事 / 明日から亡くなりますよって言われたら
02:17-02:24  会社がわざわざ / PDM配信してフリーEにしましたみたいなのは
02:24-02:29  基本的な採用候補というか / 採用におけるマーケティングの一環なのかなと思いますね
02:29-02:37  同じような職種名だと埋もれるんで / 興味持ってもらうっていうのは
03:01-03:07  採用救人状の話だったけで / 家事ある面談とか面接を通して
03:07-03:13  なるほどこういう役割を求めてるの / すり合うパターンもあるかもしれないし
03:41-03:49  会社によってビジネスのモデルとか / 通用見とかっていうのは / かなり多種多様なんですよね
03:57-04:04  各会社さんとかの / 勝ち方というか
04:06-04:13  なんでユーザーさんに必要されているか / みたいなところって / 多様性もあるし
04:25-04:35  大まかな専門職的な / この仕事が必要というのは / もちろんありますと
04:40-04:46  専門職という言葉が / 結構ミスリートというか / エンジニアとか
04:46-04:51  分かりやすすぎるだけなんですよね / 話として
```

## Step 9: Preview Before Full Render

Do not do a full 5-minute render for subtitle position tuning. Use a 1-second preview clip first, then render the full video only once after the layout is approved.

Legacy preview output files:

```text
preview_title_punchline_position_1s.mp4
preview_title_punchline_position_1s.png
```

The older ASS preview command below is superseded for final renders. Current final subtitle rendering uses PNG overlays through `render_final_png_overlays.py` or `render_1min_color_matched.py`.

For current subtitle mode verification, render the smallest practical target and extract a still:

```powershell
Set-Location 'C:\Users\yurin\Desktop\video_edit'

# Full transcript mode check on the 1-minute color-matched version.
& 'C:\Users\yurin\AppData\Local\Python\pythoncore-3.14-64\python.exe' .\render_1min_color_matched.py --mode full --skip-base
& 'C:\ProgramData\chocolatey\bin\ffmpeg.exe' -y -ss 00:00:25 `
  -i '.\ST7_7550_multicam_cut_1min_multi_cut_sound2_audio_color_matched_full_transcript.mp4' `
  -frames:v 1 -update 1 '.\speaker_style_check_0025_interviewer.png'

# Punchline mode check on the same 1-minute base.
& 'C:\Users\yurin\AppData\Local\Python\pythoncore-3.14-64\python.exe' .\render_1min_color_matched.py --mode punchline --skip-base
& 'C:\ProgramData\chocolatey\bin\ffmpeg.exe' -y -ss 00:00:10 `
  -i '.\ST7_7550_multicam_cut_1min_multi_cut_sound2_audio_color_matched.mp4' `
  -frames:v 1 -update 1 '.\speaker_style_check_0010_punchline.png'
```

Legacy 1-second ASS preview command pattern:

```powershell
Set-Location 'C:\Users\yurin\Desktop\video_edit'

$ffmpeg='C:\ProgramData\chocolatey\bin\ffmpeg.exe'
$work='C:\Users\yurin\Desktop\video_edit'
$input=Join-Path $work 'ST7_7550_multicam_cut_5min_strong_transcript_wave_refined.mp4'
$logo=Join-Path $work 'type-logo-transparent-cropped.png'
$output=Join-Path $work 'preview_title_punchline_position_1s.mp4'
$title=(Join-Path $work 'ai_engineer_now_title.ass').Replace('\','/').Replace(':','\:')
$punch=(Join-Path $work 'punchline_subtitles.ass').Replace('\','/').Replace(':','\:')
$filter="[1:v]scale=-1:48[logo];[0:v][logo]overlay=W-w-40:40[v1];[v1]subtitles='$title'[v2];[v2]subtitles='$punch'[v3]"

& $ffmpeg -y -t 1 -i $input -i $logo `
  -filter_complex $filter `
  -map '[v3]' -map '0:a:0' -t 1 `
  -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p `
  -c:a aac -b:a 128k `
  $output
```

Preview still command:

```powershell
& 'C:\ProgramData\chocolatey\bin\ffmpeg.exe' `
  -y `
  -ss 00:00:00.50 `
  -i '.\preview_title_punchline_position_1s.mp4' `
  -frames:v 1 `
  -update 1 `
  '.\preview_title_punchline_position_1s.png'
```

## Step 10: Final Overlay Render

After the 1-second preview is approved, render the final output with one of the subtitle modes.

These render commands shorten long no-speech gaps by default. Any detected silent section of 3 seconds or longer is reduced to 2 seconds after the normal overlay render.

5-minute render:

```powershell
Set-Location 'C:\Users\yurin\Desktop\video_edit'

# Punchline mode: selected important utterances only.
& 'C:\Users\yurin\AppData\Local\Python\pythoncore-3.14-64\python.exe' .\render_final_png_overlays.py --mode punchline

# Full transcript mode: every caption from the full transcription.
& 'C:\Users\yurin\AppData\Local\Python\pythoncore-3.14-64\python.exe' .\render_final_png_overlays.py --mode full
```

Default for `render_final_png_overlays.py` is `punchline`:

```powershell
& 'C:\Users\yurin\AppData\Local\Python\pythoncore-3.14-64\python.exe' .\render_final_png_overlays.py
```

1-minute color-matched render:

```powershell
# Full transcript mode: full captions, speaker-aware background, no animation.
& 'C:\Users\yurin\AppData\Local\Python\pythoncore-3.14-64\python.exe' .\render_1min_color_matched.py --mode full --skip-base

# Punchline mode: selected exact utterances, animated red/white style.
& 'C:\Users\yurin\AppData\Local\Python\pythoncore-3.14-64\python.exe' .\render_1min_color_matched.py --mode punchline --skip-base
```

Default for `render_1min_color_matched.py` is `full` because the current 1-minute deliverable expects full transcription subtitles unless otherwise specified.

Use `--skip-base` when only subtitle style or mode changed. Omit `--skip-base` when the 1-minute base video, color matching, camera cut, or timing changed.

Silence-shortening controls:

```powershell
# Keep the original timing for a render.
& 'C:\Users\yurin\AppData\Local\Python\pythoncore-3.14-64\python.exe' .\render_1min_color_matched.py --mode full --skip-base --no-shorten-silence

# Keep the temporary uncut render next to the final shortened output.
& 'C:\Users\yurin\AppData\Local\Python\pythoncore-3.14-64\python.exe' .\render_1min_color_matched.py --mode full --skip-base --keep-uncut

# Tune silence sensitivity if room tone hides pauses.
& 'C:\Users\yurin\AppData\Local\Python\pythoncore-3.14-64\python.exe' .\render_1min_color_matched.py --mode full --skip-base --silence-noise=-25dB
```

## Final Outputs

Intermediate:

```text
ST7_7550_multicam_cut_5min_strong_transcript_wave_refined.mp4
```

Final:

```text
ST7_7550_multicam_cut_5min_png_titles_punchlines.mp4
ST7_7550_multicam_cut_5min_png_titles_full_transcript.mp4
ST7_7550_multicam_cut_5min_png_titles_punchlines_sound2_audio.mp4
ST7_7550_multicam_cut_1min_multi_cut_sound2_audio.mp4
ST7_7550_multicam_cut_1min_multi_cut_sound2_audio_color_matched.mp4
ST7_7550_multicam_cut_1min_multi_cut_sound2_audio_color_matched_full_transcript.mp4
```

## 1-Minute Short Version

Use `00:00:00-00:01:00` from the sound-2 audio final because this range includes multiple camera changes:

```text
old exploratory cut:
00:00.0-00:09.0   1cam
00:09.0-00:21.5   2cam 0H4A7192
00:21.5-00:60.0   1cam
```

Render command:

```powershell
Set-Location 'C:\Users\yurin\Desktop\video_edit'
$ffmpeg='C:\ProgramData\chocolatey\bin\ffmpeg.exe'
& $ffmpeg -y `
  -ss 00:00:00 -t 00:01:00 `
  -i '.\ST7_7550_multicam_cut_5min_png_titles_punchlines_sound2_audio.mp4' `
  -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p `
  -c:a aac -b:a 192k -ar 48000 -ac 2 `
  '.\ST7_7550_multicam_cut_1min_multi_cut_sound2_audio.mp4'
```

Current 1-minute camera blocking rule:

```text
1cam = wide shot
2cam 0H4A7192 = zoom shot

00:00.0-00:20.0   2cam zoom
reason: onscreen speaker is answering, so use the zoom cut.

00:20.0-00:60.0   1cam wide
reason: offscreen interviewer is speaking, so use the wide shot.
note: keep the final short onscreen-speaker reply in the wide shot. A cut back to zoom for only the last 3 seconds feels unnatural.
```

The current 1-minute base is built directly from source clips by `render_1min_color_matched.py`, not by simply cutting the old 5-minute multicam render. This lets the 1-minute edit use a different, more natural camera plan.

## Color Grade Matching

When cameras have different white balance or color response, avoid hand-tuning a global filter first. Use OpenCV to sample comparable visual features, estimate a small channel correction, then apply the correction only to the affected camera segment.

For the current 1-minute cut, 1cam is the yellow/warm camera and 2cam is the color reference. Correct only the 1cam wide-shot section:

```text
00:00.0-00:20.0   2cam zoom, no correction
00:20.0-00:60.0   1cam wide, skin-tone matched toward 2cam
```

The lightweight method is:

```text
1. Detect the visible speaker face on a few representative 1cam and 2cam frames.
2. Sample only the lower/central face area to avoid hair, glasses, wall, and clothing.
3. Filter likely skin pixels in YCrCb/HSV.
4. Compare median BGR skin values.
5. Save the measured ratio once.
6. During render, use only the fixed gain; do not run heavy detection per frame.
```

Measured 1cam-to-2cam skin gain:

```text
B gain: 0.90265487
G gain: 0.93055556
R gain: 0.95431472
gain strength: 0.82
1cam saturation scale: 0.94
```

This intentionally cools and darkens the yellow 1cam section without changing the 2cam zoom section. The full render remains relatively light because the expensive skin detection is not part of the frame loop.

```powershell
Set-Location 'C:\Users\yurin\Desktop\video_edit'
& 'C:\Users\yurin\AppData\Local\Python\pythoncore-3.14-64\python.exe' .\render_1min_color_matched.py
```

Current color matching settings:

```text
reference camera: 2cam 0H4A7192
target camera: 1cam ST7_7550_overlap_5min
corrected range: 00:20.0-00:60.0
method: one-time OpenCV face/skin median comparison + fixed BGR gain during render
skin comparison report: skin_face_compare_1min_light.json
report: color_match_1min_report.json
full output: ST7_7550_multicam_cut_1min_multi_cut_sound2_audio_color_matched_full_transcript.mp4
punchline output: ST7_7550_multicam_cut_1min_multi_cut_sound2_audio_color_matched.mp4
```

## Step 11: Replace Audio With `sound-2`

External audio replacement uses transcription first, then waveform refinement.

```powershell
Set-Location 'C:\Users\yurin\Desktop\video_edit'

# Transcribe all WAV files under sound-2.
& 'C:\Users\yurin\AppData\Local\Python\pythoncore-3.14-64\python.exe' .\transcribe_sound2.py

# Compare sound-2 transcripts against the 5-minute video transcript.
& 'C:\Users\yurin\AppData\Local\Python\pythoncore-3.14-64\python.exe' .\compare_sound2_transcripts.py

# Refine the offset with waveform correlation.
& 'C:\Users\yurin\AppData\Local\Python\pythoncore-3.14-64\python.exe' .\refine_sound2_audio_offset.py

# Replace the audio track, then shorten long silent sections by default.
& 'C:\Users\yurin\AppData\Local\Python\pythoncore-3.14-64\python.exe' .\replace_audio_with_sound2.py
```

Current matching result:

```text
source audio: sound-2\140101-003.WAV
rough transcript offset: 1108.68s
refined waveform offset: 1108.62s
output: ST7_7550_multicam_cut_5min_png_titles_punchlines_sound2_audio.mp4
note: pass --no-shorten-silence when the original 5-minute timing must be preserved exactly
```

Verified properties:

```text
duration before silence shortening: 300.082433s
audio: AAC / 48000 Hz / stereo
```

## YouTube Audio Leveling

The 1-minute one-pass render applies YouTube-oriented speech processing inside the ffmpeg filter graph. This is needed because the onscreen speaker and offscreen interviewer can have different recorded loudness.

Current audio filter in `render_1min_onepass_ffmpeg.py`:

```text
highpass=f=80
dynaudnorm=f=250:g=15:p=0.95:m=8
acompressor=threshold=-20dB:ratio=2.8:attack=5:release=120:makeup=4
loudnorm=I=-14:TP=-1.5:LRA=9
```

Purpose:

```text
highpass: reduce low-frequency rumble
dynaudnorm: even out speaker-to-speaker loudness differences
acompressor: control speech peaks and improve density
loudnorm: target YouTube-style loudness around -14 LUFS with true peak safety
```

The pre-processing 1-minute output measured roughly `-32.5 LUFS`, which is too quiet. A 12-second processed preview measured roughly `-15.6 LUFS` with true peak around `-1.0 dB`, which is close to YouTube delivery loudness.

Preview command:

```powershell
Set-Location 'C:\Users\yurin\Desktop\video_edit'
& 'C:\Users\yurin\AppData\Local\Python\pythoncore-3.14-64\python.exe' .\render_1min_onepass_ffmpeg.py `
  --mode full `
  --skip-subtitle-regeneration `
  --preview-start 15 `
  --preview-duration 12 `
  --output .\onepass_audio_preview_15s_12s.mp4
```

## Natural Answer Ending And Interviewer Question Omit Mode

The one-pass renderer no longer hard-stops at exactly 60 seconds. Both normal mode and interviewer-question omit mode can extend the output until the onscreen speaker reaches a natural sentence/paragraph break, with a maximum extension target of about 30 seconds.

For the current ST7_7550 edit, the natural break is original source time `01:25`, after the line `フレッシュな話題というか`. This makes the normal output `85.000s`.

Implementation rule:

```text
DEFAULT_OUTPUT_END = 85.0
DURATION = DEFAULT_OUTPUT_END
OMIT_ANSWER_END = DEFAULT_OUTPUT_END
```

Normal-mode camera timeline:

```text
00:00-00:20  2cam zoom 0H4A7192
00:20-01:08  1cam wide
01:08-01:25  2cam zoom 0H4A7193
```

This is an automatic context-aware camera plan, not a purely time-based punch-in rule:

1. Read the full-transcript overlay manifest and speaker roles.
2. Keep the offscreen interviewer question on the wide/master view instead of cutting to the interviewee reaction.
3. Wait through the short confirmation exchange at `01:06-01:08`.
4. Target the camera-2 close shot when the interviewee answer enters the main point at `01:08` (`まあなんか`).
5. Confirm the candidate camera source with OpenCV frame sampling before using it in the final plan.
6. With `--natural-dialogue-cuts`, move that target by only a few hundred milliseconds into the nearest short low-energy dialogue gap. This changes only the camera switch timing; it does not shorten the audio or replace `shorten_silences.py`.

For the current audio, the natural low-energy point near the `01:08` target is around `01:08.000`; the search is intentionally narrow so the cut does not jump back into the previous caption. The renderer writes a sidecar report next to the output:

```text
<output>.natural_dialogue_cuts.json
```

OpenCV check for the late interviewee answer:

```text
output\diagnostics\camera2_after_1min_opencv\analysis.json
output\diagnostics\camera2_after_1min_opencv\cam1_vs_2cam7193_57_84s_contact_sheet.jpg
```

`0H4A7192` is unavailable after about the first 20 seconds of this master timeline. The usable late camera-2 source is `0H4A7193`, with `01:25` on the master timeline corresponding to `00:59.640` in `0H4A7193`. The late switch starts at `01:08`, after the short confirmation exchange, where the answer enters the main point.

Important implementation note: do not leave the normal-mode `1cam` segment capped at `60.0`. The camera plan must still cover through `DURATION`, otherwise the audio/subtitle timeline can extend beyond the intended camera edit.

The renderer can also remove the long offscreen interviewer question and replace it with a short summary card. This is controlled by `--omit-interviewer-question`.

Normal mode:

```powershell
& 'C:\Users\yurin\AppData\Local\Python\pythoncore-3.14-64\python.exe' .\render_1min_onepass_ffmpeg.py `
  --mode full `
  --auto-context-cuts `
  --natural-dialogue-cuts `
  --skip-subtitle-regeneration `
  --output .\ST7_7550_multicam_cut_1min_onepass_full_transcript.mp4
```

Interviewer question omit mode:

```powershell
& 'C:\Users\yurin\AppData\Local\Python\pythoncore-3.14-64\python.exe' .\render_1min_onepass_ffmpeg.py `
  --mode full `
  --auto-context-cuts `
  --natural-dialogue-cuts `
  --skip-subtitle-regeneration `
  --omit-interviewer-question `
  --output .\ST7_7550_multicam_cut_1min_onepass_full_transcript_omit_interviewer.mp4
```

Current omit-mode edit rule:

```text
00:00-00:20  keep onscreen speaker answer
00:20-00:57  remove offscreen interviewer question
00:20-00:25  insert 5-second question summary card
00:25-~00:36.0  resume onscreen speaker answer from original 00:57-~01:08.0 on 1cam wide
~00:36.0-00:53  continue original ~01:08.0-01:25 on 2cam zoom 0H4A7193
```

In omit mode, the same source-context switch is remapped onto the shortened timeline. Original target `01:08` becomes output `00:36`, then `--natural-dialogue-cuts` nudges it only within a narrow nearby short pause. The close camera still begins after the summary-card gap and after the brief confirmation line, at the natural lead-in to the main answer.

App behavior:

```text
app/src/renderer/index.html
Auto cut by subtitle context and speaker: on by default
Place cuts in short dialogue gaps: off by default; enable it when you want `--natural-dialogue-cuts`
```

When enabled, the app passes `--auto-context-cuts` to `render_1min_onepass_ffmpeg.py`. When disabled, it passes `--no-auto-context-cuts` and the renderer falls back to the simple fixed camera plan.
When short-gap placement is enabled, the app also passes `--natural-dialogue-cuts`. When it is off, the renderer keeps camera switches at the exact context target.

Summary card text:

```text
PDMフリー化をめぐる論争について
どう感じますか？
```

Omit mode also adds a dedicated 5-second music cue during the summary card:

```text
output\audio\omit_summary_card_music_5s.wav
```

Current outputs:

```text
output\videos\ST7_7550_multicam_cut_1min_onepass_full_transcript.mp4
duration: 85.000s

output\videos\ST7_7550_multicam_cut_1min_onepass_full_transcript_omit_interviewer.mp4
duration: 53.000s
```

## Step 12: Shorten Long Silent Sections

Final render scripts now shorten long no-speech gaps automatically after the normal render pass.

Rule:

```text
If ffmpeg detects a silent section of 3.0 seconds or longer, keep 2.0 seconds total and cut the middle.
Default silence threshold: -30dB
```

Shared script:

```text
shorten_silences.py
```

Included by default in:

```text
render_final_png_overlays.py
render_1min_color_matched.py
replace_audio_with_sound2.py
```

Useful commands:

```powershell
# Inspect cuts without writing the shortened video.
& 'C:\Users\yurin\AppData\Local\Python\pythoncore-3.14-64\python.exe' .\shorten_silences.py `
  --input '.\ST7_7550_multicam_cut_1min_multi_cut_sound2_audio_color_matched.mp4' `
  --output '.\_dryrun_silence_shortened.mp4' `
  --dry-run

# Disable this behavior for a render.
& 'C:\Users\yurin\AppData\Local\Python\pythoncore-3.14-64\python.exe' .\render_1min_color_matched.py `
  --no-shorten-silence

# Make silence detection more aggressive if room tone hides pauses.
& 'C:\Users\yurin\AppData\Local\Python\pythoncore-3.14-64\python.exe' .\render_1min_color_matched.py `
  --silence-noise=-25dB
```

The script writes a JSON report next to the output:

```text
<output>.silence_shortening.json
```

Report fields include detected silent ranges, removed ranges, kept ranges, source duration, and expected output duration.

## Thumbnail Candidate Workflow

Generate thumbnail candidates with:

```powershell
python .\scripts\generate_thumbnail_candidates.py --import-assets
```

Use this mode for face-centered close-ups with a one-line bottom title:

```powershell
python .\scripts\generate_thumbnail_candidates.py --import-assets --closeup-bottom-title
```

Use this mode for a tight right-side interviewee close-up with the hook stacked above the wrapped title on the left:

```powershell
python .\scripts\generate_thumbnail_candidates.py --import-assets --right-face-title-stack
```

Use this mode for a tight left-side interviewee close-up with the hook stacked above the wrapped title on the right:

```powershell
python .\scripts\generate_thumbnail_candidates.py --import-assets --left-face-title-stack
```

Default imported still assets:

```text
C:\Users\yurin\Downloads\etype260515 p-takei\etype260515 p-takei\ST-*.jpg
```

The script copies those files into:

```text
source\thumbnail\etype260515_p_takei\
```

Reference thumbnails are kept in:

```text
source\thumbnail\references\
```

The current thumbnail copy is intentionally fixed across all candidates:

```text
Main title: フリーPdMは
            通用する？
Corner hook: AI時代のキャリア論
```

Vary the selected still, palette, title placement, hook corner, logo corner, and crop feel. Do not vary the main title or hook unless the video topic changes.

Mode switch:

- Default mode keeps the previous thumbnail composition: two-line title placement varies by image while avoiding faces.
- `--closeup-bottom-title` centers the detected interviewee face, uses a strong close-up crop, renders `フリーPdMは通用する？` as a single line at the bottom, and places the hook in the opposite top corner from the logo.
- `--right-face-title-stack` places the detected interviewee face as a very tight crop on the right, then places the hook directly above the wrapped title in the left-side negative space.
- `--left-face-title-stack` places the detected interviewee face as a very tight crop on the left, then places the hook directly above the wrapped title in the right-side negative space. It changes crop position only; it does not horizontally flip the image.

Current visual rules:

- Use `source\images\type-logo-transparent-cropped.png` for the Engineer Type logo.
- Crop transparent logo margins before placing it.
- Add only a small, even white padding around the logo; do not use a large white logo box.
- Place the logo in the least-overlapping corner after avoiding faces, title text, and the corner hook.
- Do not draw a video-duration chip in the bottom-right corner.
- Keep the main title large, stroked, and close to the chosen edge.
- Keep the main title to two lines where possible; for tight face-layout modes, a small overlap with hair/shoulder is acceptable if it keeps the title readable and large.
- Fit the main title dynamically to the available title box so it grows when there is more safe whitespace, while still wrapping before it clips or covers the face.
- Keep ASCII word groups such as `PdM` intact when wrapping mixed Japanese/English title text.
- Place the corner hook/subtitle directly above the main title, not isolated elsewhere on the canvas.
- Leave only a small bottom margin under the title.
- Use measured text bounds for wrapped title lines so line spacing does not overlap.
- Center the corner hook text inside its colored box using measured text bounds, with even horizontal and vertical padding.
- Keep title and hook text clear of detected faces. The generated analysis JSON records face boxes and chosen layout boxes.

Generated outputs:

```text
output\thumbnails\thumbnail_standard_candidate_01.png
...
output\thumbnails\thumbnail_standard_candidate_20.png
output\thumbnails\thumbnail_standard_candidates_contact_sheet.jpg
output\thumbnails\thumbnail_standard_asset_analysis.json
output\thumbnails\thumbnail_closeup_bottom_title_candidate_01.png
output\thumbnails\thumbnail_right_face_title_stack_candidate_01.png
output\thumbnails\thumbnail_left_face_title_stack_candidate_01.png
output\thumbnails\thumbnail_reference_style.json
source\text\thumbnail_title_pdm_freelance.txt
```

Validation:

```powershell
python -m py_compile .\scripts\generate_thumbnail_candidates.py
python .\scripts\generate_thumbnail_candidates.py --import-assets
```

After generating, inspect the mode-specific contact sheet, for example `output\thumbnails\thumbnail_standard_candidates_contact_sheet.jpg`, and confirm the title, hook, and logo do not cover faces or look padded unevenly. Mode names are included in generated PNG, contact sheet, and analysis JSON filenames so different layout options do not overwrite each other.

## Verification Commands

Check duration:

```powershell
& 'C:\ProgramData\chocolatey\bin\ffprobe.exe' `
  -v error `
  -show_entries format=duration `
  -of default=noprint_wrappers=1:nokey=1 `
  '.\ST7_7550_multicam_cut_1min_multi_cut_sound2_audio_color_matched_full_transcript.mp4'
```

Check audio stream:

```powershell
& 'C:\ProgramData\chocolatey\bin\ffprobe.exe' `
  -v error `
  -select_streams a:0 `
  -show_entries stream=codec_name,sample_rate,channels `
  -of json `
  '.\ST7_7550_multicam_cut_1min_multi_cut_sound2_audio_color_matched_full_transcript.mp4'
```

Check the silence-shortening report:

```powershell
Get-Content '.\ST7_7550_multicam_cut_1min_multi_cut_sound2_audio_color_matched_full_transcript.silence_shortening.json'
```

## Older Outputs To Treat As Superseded

These were useful during the investigation, but should not be treated as the current preferred final:

```text
ST7_7550_overlap_5min_logo_text_subtitled.mp4
ST7_7550_overlap_5min_external_audio_logo_text_subtitled_corrected.mp4
ST7_7550_multicam_cut_5min_logo_text_subtitled.mp4
ST7_7550_multicam_cut_5min_wave_synced_logo_text_subtitled.mp4
ST7_7550_multicam_cut_5min_transcript_synced_logo_text_subtitled.mp4
```

## Notes

- If sync still looks off, do not go back to metadata-only sync.
- Use only strong transcript matches first, then waveform matching around the matched phrase.
- Weak transcript matches are not reliable enough for automatic camera switching.
- For future shoots, use shared timecode, a slate, or a clear hand clap visible/audible to all cameras.
