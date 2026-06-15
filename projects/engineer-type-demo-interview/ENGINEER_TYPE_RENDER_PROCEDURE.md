# Engineer Type Render Procedure

This file is the handoff procedure for another AI/engineer to reproduce the same output style and render behavior used in this repository. Follow this when the user says: "フルレンダーして" or "full render".

## Project

- Workspace root: `C:\Users\yurin\Desktop\video_edit`
- Active project id: `new-folder-2`
- Project config: `projects/new-folder-2/project_state.json`
- Main render action: `python .\scripts\video_edit_run.py --action render-selected`
- Main render script: `scripts/render_multicam.py`

Do not use the Electron UI for this workflow. Operate from scripts and project files.

## Non-Negotiable Defaults

Keep these settings unless the user explicitly asks to change them.

- Use existing transcript files. Do not re-run Whisper for a normal full render.
- Use the selected external WAV audio, not camera audio, when `render.audioSource` is `external-if-selected`.
- Use `render.subtitleMode = "full"` for full transcript subtitles.
- Use PNG subtitle overlays, not simplified ASS, for the normal full render.
- Use `render.multicamMode = "manual-plan"` and `render.cameraPlanPath`.
- Use `render.outputFps = "30000/1001"`.
- Use `render.videoEncoder = "h264_nvenc"`, `render.nvencPreset = "p4"`, and `render.cq = 19`.
- Keep `render.shortenSilence = true`, `render.minSilence = 3.0`, and `render.keepSilence = 2.0`.
- Keep `render.colorMatchCameras = true`.
- Keep the reviewed-video source trim in project state: `render.previewStart = 85.0` and `render.previewDuration = master duration - 85.0 - 20.0`.
  The review was made against a derived file with the first `1:25` and final `0:20` removed.
- Keep the shared post-match output look in `render.outputLookFilter`; do not replace it with a master-only extra filter.
- Keep the current camera5 color correction unless the user requests another color pass:
  `colorchannelmixer=rr=1.06500:gg=0.98500:bb=1.00000,eq=brightness=-0.0140:contrast=1.0000:saturation=1.1200`

Current important inputs:

- Media sources must be project-local:
  `projects/new-folder-2/source/video/*.MP4` and `projects/new-folder-2/source/audio/*.WAV`.
- Subtitle SRT: `projects/new-folder-2/output/transcripts/manifest_sources/external_140101-003.reviewed.srt`
- Speaker roles: `projects/new-folder-2/output/reports/full_transcript_speaker_roles_audio_lr.json`
- Manual camera plan: `projects/new-folder-2/output/reports/manual_camera_plan.json`
- Right logo: configured in `project_state.json`
- Chapter titles: `projects/new-folder-2/output/reports/chapter_titles_from_full_transcript.json`

Do not read active render media from `Downloads` or any folder outside `C:\Users\yurin\Desktop\video_edit`. If a source file is outside the project, move it into the matching project source folder first, then update `project_state.json` and `output/reports/media_manifest.json`.

## Before Rendering

1. Check that no old render is running.

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match 'video_edit_run|render_multicam|render_app_interview|ffmpeg' } |
  Select-Object ProcessId,Name,CommandLine
```

If an old render is running and the user has not authorized stopping it, do not kill it. Ask or wait. If the user says an existing render can be stopped, stop the `python.exe`/`ffmpeg.exe` render processes for that job only.

2. Generate a timestamp.

```powershell
Get-Date -Format 'yyyyMMdd_HHmmss'
```

3. Update `projects/new-folder-2/project_state.json`.

Set all three render output fields to the same timestamped final path:

```json
{
  "render": {
    "outputPath": "C:\\Users\\yurin\\Desktop\\video_edit\\projects\\new-folder-2\\output\\videos\\YYYYMMDD_HHMMSS.mp4",
    "finalOutputPath": "C:\\Users\\yurin\\Desktop\\video_edit\\projects\\new-folder-2\\output\\videos\\YYYYMMDD_HHMMSS.mp4",
    "baseOutputPath": "C:\\Users\\yurin\\Desktop\\video_edit\\projects\\new-folder-2\\output\\videos\\YYYYMMDD_HHMMSS.mp4"
  }
}
```

Also update `updatedAt`.

Use `apply_patch` for this edit. Do not overwrite unrelated user changes.

4. If subtitle wrapping code or subtitle text changed since the last render, regenerate and audit full subtitle overlays before the full render.

```powershell
$env:VIDEO_EDIT_PROJECT='new-folder-2'
python .\scripts\generate_full_transcript_png_overlays.py
Remove-Item Env:\VIDEO_EDIT_PROJECT
```

The full render will also regenerate overlays automatically, but doing it before a full render catches line-break issues cheaply.

The current subtitle line-break rule must avoid:

- protected terms like `FDE`, `PDM`, `SaaS`, `SIer`, `Claude Code`;
- katakana/Latin technical terms;
- common Japanese chunks like `ということ`, `みたいな`, `している`;
- okurigana word splits such as `務|まらない`, `受|け入れ`, `限|られている`.

## Start Full Render

Prefer a background process so progress can be monitored.

```powershell
$root='C:\Users\yurin\Desktop\video_edit'
$ts='YYYYMMDD_HHMMSS'
$logDir=Join-Path $root 'projects\new-folder-2\output\logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$outLog=Join-Path $logDir "$ts.render.stdout.log"
$errLog=Join-Path $logDir "$ts.render.stderr.log"
$env:VIDEO_EDIT_PROJECT='new-folder-2'
$p=Start-Process -FilePath 'python' `
  -ArgumentList @('.\scripts\video_edit_run.py','--action','render-selected') `
  -WorkingDirectory $root `
  -RedirectStandardOutput $outLog `
  -RedirectStandardError $errLog `
  -WindowStyle Hidden `
  -PassThru
Remove-Item Env:\VIDEO_EDIT_PROJECT
$p.Id
```

Expected internal steps:

1. `render_multicam.py` starts.
2. `generate_full_transcript_png_overlays.py` regenerates full subtitle PNGs.
3. `generate_chapter_title_png_overlays.py` regenerates top-left chapter titles.
4. Long subtitle PNGs are precomposed into `output/overlays/precomposed/<timestamp>_full_subtitles.mov`.
5. FFmpeg renders `output/videos/<timestamp>_uncut.mp4`.
6. Silence shortening creates final `output/videos/<timestamp>.mp4`.
7. The intermediate uncut file may be deleted after final output.

## Monitor Render

Use process checks. On Windows, the `.mp4` size can show `0` until the mux closes, so do not assume it is stuck only because file size is zero.

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match 'video_edit_run|render_multicam|render_app_interview|ffmpeg' } |
  Select-Object ProcessId,Name,CommandLine
```

Check FFmpeg CPU activity:

```powershell
Get-Process -Name ffmpeg -ErrorAction SilentlyContinue |
  Select-Object Id,ProcessName,CPU,WorkingSet64,StartTime
```

Check output candidates:

```powershell
Get-ChildItem -LiteralPath 'C:\Users\yurin\Desktop\video_edit\projects\new-folder-2\output\videos' `
  -Filter 'YYYYMMDD_HHMMSS*' |
  Select-Object Name,Length,LastWriteTime
```

Expected duration is long. For the reviewed-video source range with PNG subtitles, chapter overlays, color matching, audio mastering, and silence shortening, it can take around 45-60 minutes even with NVENC because the filter graph is CPU-heavy.

## Verify Final Output

Run `ffprobe`.

```powershell
ffprobe -v error `
  -show_entries format=duration,size `
  -show_streams `
  -of json `
  'C:\Users\yurin\Desktop\video_edit\projects\new-folder-2\output\videos\YYYYMMDD_HHMMSS.mp4'
```

Expected:

- video: 1920x1080
- fps: `30000/1001`
- codec: H.264, usually `h264_nvenc`
- audio: AAC stereo, 48kHz
- duration: based on the reviewed-video source range: master duration minus the first `85s` and final `20s`, then any configured review cut ranges and silence shortening

Check silence-shortening report:

```powershell
Get-Content -LiteralPath 'C:\Users\yurin\Desktop\video_edit\projects\new-folder-2\output\videos\YYYYMMDD_HHMMSS.silence_shortening.json' -Raw
```

## Sync And FPS QA

The important sync bug was on the video side, not the external WAV audio.

Known investigation result:

- External WAV audio vs rendered uncut audio was stable across the timeline, roughly within `-0.025s`.
- Video frame comparison against source footage showed cumulative lag before the fix.
- The old bad pattern produced about `0.4s` video lag around 17 minutes and about `0.8s` later in the render.
- Cause: applying `fps=30000/1001` separately inside every camera segment before `concat`.
- Why it fails: every cut rounds frames independently; audio remains one continuous WAV, so only video gradually drifts.

Required graph rule:

```text
trim/style each camera segment at source timing
concat all camera segments
apply one shared fps=<render.outputFps> to the concatenated base video
then apply title/logo/subtitle overlays
```

Do not use this old graph shape:

```text
segment trim -> fps=30000/1001 -> segment filters -> concat
```

The fixed implementation lives in `scripts/render_multicam.py`: camera segments must not get individual FPS conversion before `concat`; the shared FPS conversion belongs after `[vbase_raw]`.

`scripts/shorten_silences.py` also needs to keep using the configured encoder. When `render.videoEncoder = "h264_nvenc"`, silence shortening should re-encode with `h264_nvenc` rather than falling back to CPU x264.

When checking sync after a render, do not rely only on waveform correlation. Also compare rendered video frames to the source video at multiple timeline points. If audio is aligned but the visible mouth/frame is late, suspect the FPS graph first.

## Visual QA

Always inspect at least these points after a full render:

- Around `11:52`: known good close-up reference.
- Around `26:00`: previously problematic camera5 close-up.
- Around `39:34`: previously problematic camera5 close-up.
- Around any user-reported bad timestamp.

For the camera5 color issue, compare bright low-saturation wall/background pixels, not only face/skin. Target is close to:

- good close-up wall: `R/G ~= 1.05`, `R/B ~= 1.23`
- fixed camera5 wall: approximately `R/G ~= 1.07`, `R/B ~= 1.22`

If the wall reads cyan/green/blue, do not blindly increase saturation. Check wall `R/G` and `R/B`; raise red relative to green only if the measured background supports it.

## Color Matching Procedure

Use this section when the user asks to fix color differences or when changing color-related code/config.

The successful approach is:

- Match sub cameras against the long master camera `ST7_7550.MP4`.
- Build samples only from the final camera plan ranges where that camera is actually used.
- Take sub-camera samples at `timeline timestamp + sync offset`, not generic source timestamps.
- Run matching after manual/dynamic planning, speaker masking, natural dialogue cuts, and source coverage clipping.
- Verify `output/reports/camera_color_match.json` shows `sampleBasis: actual camera plan`.
- Use background/neutral pixels for white-balance channel gains: `backgroundBgr` first, `neutralBgr` second.
- Do not let skin/face samples drive `colorchannelmixer` gains. Skin can help brightness and saturation checks, but skin-driven channel gains previously pushed green/blue too high on close-up cameras.
- Apply the white/clean look as the shared final `render.outputLookFilter` after per-camera matching to every camera. Do not add a master-only white filter after matching, because that changes the reference and reintroduces mismatch.

Current shared post-look:

```text
colorchannelmixer=rr=0.99000:gg=1.00000:bb=1.01200,eq=brightness=0.0140:contrast=0.9850:saturation=0.9600
```

Before a production render after color code/config changes, render a short switching test. The current useful test is the first 95 seconds because it includes master plus sub-camera cuts such as `camera2` and `camera4`.

Temporary 95-second test pattern:

```powershell
$ErrorActionPreference='Stop'
$root='C:\Users\yurin\Desktop\video_edit'
$project=Join-Path $root 'projects\new-folder-2'
$statePath=Join-Path $project 'project_state.json'
$state=Get-Content -Raw -Path $statePath | ConvertFrom-Json -Depth 100
$ts=Get-Date -Format 'yyyyMMdd_HHmmss'
$out=Join-Path $project "output\videos\${ts}_test_95s_color_rework.mp4"
$state.render.previewStart=0
$state.render.previewDuration=95
$state.render.outputPath=$out
$state.render.baseOutputPath=$out
$state.render.finalOutputPath=$out
$state.render.subtitleMode='full'
$state.render.shortenSilence=$false
$state.render.omitInterviewerQuestion=$false
$state.render.closeupsOnlyWhenOnscreenSpeaker=$true
$tmp=Join-Path $project "output\app\${ts}_test_95s_color_rework_runtime.json"
$log=Join-Path $project "output\logs\${ts}_test_95s_color_rework.log"
New-Item -ItemType Directory -Force -Path (Split-Path $tmp),(Split-Path $log),(Split-Path $out) | Out-Null
$state | ConvertTo-Json -Depth 100 | Set-Content -Path $tmp -Encoding UTF8
$env:VIDEO_EDIT_PROJECT='new-folder-2'
$env:VIDEO_EDIT_APP_CONFIG=$tmp
Set-Location $root
python .\scripts\video_edit_run.py --action render-selected *> $log
Remove-Item Env:\VIDEO_EDIT_PROJECT
Remove-Item Env:\VIDEO_EDIT_APP_CONFIG
```

After the test, inspect:

```powershell
Get-Content -Path 'C:\Users\yurin\Desktop\video_edit\projects\new-folder-2\output\reports\camera_color_match.json' -Raw
```

For each used sub camera, check:

- `sampleTimelineSeconds` and `referenceSourceSeconds` are actual used cut ranges.
- `backgroundBgr` and `neutralBgr` are the basis for channel gains.
- `skinBgr` did not dominate channel gains.
- `redGain`, `greenGain`, `blueGain`, and `filter` do not push green/blue enough to make pale walls look cyan.
- The rendered test clip visually matches the master after the shared `outputLookFilter`.

## Subtitle QA

After subtitle text or wrap-rule changes, run a full layout audit before accepting a render. The audit must show:

- `highPenaltyBreaks = 0`
- `warningBreaks = 0`

Current known corrected example:

```text
逆に言うとFDEはエンジニアじゃないと
務まらないような仕事でもありますよね
```

Do not allow:

```text
逆に言うとFDEはエンジニアじゃないと務
まらないような仕事でもありますよね
```

## Final Response To User

When the render finishes, respond with:

- final output path;
- duration/format summary from `ffprobe`;
- whether silence shortening ran;
- any QA checks performed;
- if no visual/audio review was done, say so plainly.

Example:

```text
フルレンダー完了です。

出力:
C:\Users\yurin\Desktop\video_edit\projects\new-folder-2\output\videos\YYYYMMDD_HHMMSS.mp4

確認:
- 1920x1080 / 29.97fps / H.264 NVENC / AAC
- duration: ...
- silence-shortening report: ...
```

Do not claim a quality check was performed unless it actually was.
