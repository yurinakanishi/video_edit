# Video Edit Project

## Layout

```text
scripts/                  Python pipeline and render tools
source/video/             Local source camera/video files
source/audio/             Local source recorder/audio files
source/images/            Logo and source image assets
source/subtitles/         Source and corrected subtitle files
source/text/              Source text assets
output/videos/            Rendered MP4 outputs and previews
output/overlays/          Generated PNG/ASS overlay assets
output/transcripts/       Generated transcript and sync artifacts
output/audio/             Extracted audio outputs
output/diagnostics/       Review clips and diagnostic artifacts
output/reports/           Generated JSON reports
config/                   Project configuration and correction data
docs/                     Method notes and reference docs
app/                      Electron UI source
```

Large source media and all generated outputs are ignored by Git.

## Current Render Entry Points

```powershell
python .\scripts\render_1min_onepass_ffmpeg.py --mode full --output .\output\videos\ST7_7550_multicam_cut_1min_onepass_full_transcript.mp4
python .\scripts\render_final_png_overlays.py --mode punchline --output .\output\videos\ST7_7550_multicam_cut_5min_png_titles_punchlines.mp4
```

Electron direct actions and command-line automation can also use the shared runtime-config runner:

```powershell
python .\scripts\video_edit_run.py --action generate-thumbnails
python .\scripts\video_edit_run.py --action render-selected
```

The runner reads `output\app\video_edit_app_config.runtime.json` or `VIDEO_EDIT_APP_CONFIG`, then delegates to the existing render, thumbnail, analysis, FFmpeg, and ffprobe commands.

## Source Video Person Analysis

Generate per-video person bbox metadata before editing:

```powershell
python .\scripts\analyze_person_edit_metadata.py --fps-sample 1
```

Or run the two steps separately:

```powershell
python .\scripts\analyze_person_bboxes.py --fps-sample 1
python .\scripts\build_person_edit_plan.py
```

`analyze_person_bboxes.py` writes frame-level YOLO person detections to `output/reports/person_bboxes`.
`build_person_edit_plan.py` converts those detections into segment-level guidance for crop, zoom, cut, and wide-shot decisions under `output/reports/person_edit_plans`.
Composition guidance uses shared mathematical anchors from `scripts/composition_rules.py`: golden-ratio lines, thirds, silver-ratio lines, and outer-golden anchors for stronger thumbnail side placement. The generated analysis includes target subject x/y ratios and anchor names so renderers and thumbnail generation can use the same placement rules.

The detector uses Ultralytics YOLO. Install it in the project Python environment if needed:

```powershell
python -m pip install ultralytics
```

For a short style reference video, keep the video under 60 seconds and generate a reference profile:

```powershell
python .\scripts\analyze_person_edit_metadata.py `
  --input .\source\video\reference.mp4 `
  --fps-sample 1 `
  --max-duration 60 `
  --output-dir .\output\reports\reference_person_bboxes `
  --plan-output-dir .\output\reports\reference_edit_plans `
  --reference-profile-output .\output\reports\reference_edit_profile.json
```

The reference profile is used by the Electron dropped-file interview renderer as a target for person size, crop placement, and simple visual tone.

Electron dropped-file interview renders can also accept multiple still-image inserts. Text/diagram images are shown static near matching transcript text when possible; photo-like images are analyzed for faces or visual focus and get subtle person-, landscape-, or object-appropriate pan/zoom with fade in/out.

For the detailed workflow, see `docs/video_edit_method.md`.
