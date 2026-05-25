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

For the detailed workflow, see `docs/video_edit_method.md`.

