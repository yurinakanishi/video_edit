# ST7_7550 Video Edit Method

This document describes the current working method for editing the `ST7_7550` 5-minute multicam video.

The current preferred output is the strict transcript-match edit:

```text
ST7_7550_multicam_cut_5min_strong_transcript_wave_refined_logo_text_subtitled.mp4
```

The previous transcript-synced output is treated as a diagnostic output, not the final preferred output, because it used a weak `2cam` transcript match.

## Working Folder

```text
C:\Users\yurin\Desktop\video_edit
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
1cam\ST7_7550_overlap_5min.mp4
..\2cam\0H4A7192.MP4
..\2cam\0H4A7193.MP4
..\3cam\IMG_2316.MP4
subs_video_original_audio\ST7_7550_overlap_5min_original_audio.srt
header_site_id_logo01.png
ai_engineer_now_title.ass
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
- adds the right-top logo
- burns the copied left-top ASS title file `ai_engineer_now_title.ass`
- burns the SRT subtitles from the original video audio

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

## Final Outputs

Intermediate:

```text
ST7_7550_multicam_cut_5min_strong_transcript_wave_refined.mp4
```

Final:

```text
ST7_7550_multicam_cut_5min_strong_transcript_wave_refined_logo_text_subtitled.mp4
```

Verified properties:

```text
duration: 300.082433s
audio: AAC / 48000 Hz / stereo
```

## Verification Commands

Check duration:

```powershell
& 'C:\ProgramData\chocolatey\bin\ffprobe.exe' `
  -v error `
  -show_entries format=duration `
  -of default=noprint_wrappers=1:nokey=1 `
  '.\ST7_7550_multicam_cut_5min_strong_transcript_wave_refined_logo_text_subtitled.mp4'
```

Check audio stream:

```powershell
& 'C:\ProgramData\chocolatey\bin\ffprobe.exe' `
  -v error `
  -select_streams a:0 `
  -show_entries stream=codec_name,sample_rate,channels `
  -of json `
  '.\ST7_7550_multicam_cut_5min_strong_transcript_wave_refined_logo_text_subtitled.mp4'
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
