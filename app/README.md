# Video Edit Electron App

Electron UI for operating the `C:\Users\yurin\Desktop\video_edit` editing pipeline through `codex app-server`.

## Run

```powershell
Set-Location 'C:\Users\yurin\Desktop\video_edit\app'
pnpm install
pnpm start
```

Build a portable Windows app and installer:

```powershell
Set-Location 'C:\Users\yurin\Desktop\video_edit\app'
pnpm run dist
```

Build artifacts are written to `C:\Users\yurin\Desktop\video_edit\release`.

TypeScript sources live under `src`. Electron main/preload compile with `tsc`; the renderer is a React + Vite app built into `dist\renderer` before Electron starts.

Use Biome for formatting and linting:

```powershell
pnpm run lint
pnpm run format
pnpm run check
```

## What It Does

- Creates/selects per-video projects under `C:\Users\yurin\Desktop\video_edit\projects\<project-id>`, stores media manifests and lightweight imported assets inside the project, and sends project-specific `source` / `output` roots to the Python scripts.
- Accepts drag-and-drop or picker-based inputs for master video, right close-up, left close-up, external audio, logo, and output path.
- Accepts multiple drag-and-drop still images for interview renders. Text/diagram stills are inserted without motion near matching transcript text when possible; photo-like stills are analyzed for faces or visual focus, then get person-, landscape-, or object-appropriate pan/zoom with fade in/out.
- Uses the selected media manifest as the source of truth for cameras, audio, still images, subtitles, and output roots.
- Provides tool-path controls for Python, FFmpeg, and FFprobe. Project source/output roots are created by the project manager.
- Exposes subtitle mode selection: full transcript, catchy/punchline, or none.
- Exposes automatic interview camera cuts based on selected media, sync metadata, subtitle speaker roles, rhythmic punch-in cuts, source coverage, and saved manual camera plans.
- Captures title, subtitle, color, opacity, logo-size, punchline-list, output-duration, audio-noise-reduction, and silence-shortening settings.
- Captures audio mastering and natural-dialogue camera-cut settings so the old one-off render's loudness/dynamics chain and low-energy cut adjustment are available per project.
- Captures camera color-match settings so multicam close-ups can be normalized to the master camera before render, including generic white-balance channel gains.
- Captures person-aware crop settings so `reports\person_edit_plans` generated during analysis are applied during the production renderer, and face-center crop reports can be embedded into timeline `scaleCrop` effects for adapter renders.
- Captures transcript-comparison sync fallback settings so current-project transcript matches can correct missing or low-score waveform offsets, with usage written to `reports\sync_offset_usage.json`.
- Captures background-music settings: generate on/off, placement across the whole video or only omission/title-card ranges, automatic/manual range source, direction prompt, and mix level.
- Provides a project-level audio replacement workflow for selected input videos, using the selected external audio and current sync report instead of old fixed `sound2` files.
- Captures omission-card settings: replace configured interviewer/omission ranges with a generated summary card, set card duration/text/label, and reuse BGM omission ranges when desired.
- Captures render encoding settings so the app runtime config, not old CLI flags, controls x264 preset and CRF for both render and silence-shortening output.
- Captures project-thumbnail and subtitle-QA settings, including thumbnail time/title/subtitle, multi-candidate thumbnail layout/color/timing, optional thumbnail face-box debug output, subtitle readability thresholds, suspicious subtitle patterns, flagged-caption audio clips/re-transcription, manual subtitle correction rows, interviewer ranges/patterns/manual overrides for subtitle speaker roles, and optional mouth-motion, mouth-opening, audio RMS, and mouth/audio correlation diagnostics.
- Shows a preflight checklist for missing output paths, required camera files, audio fallbacks, silence-shortening state, and recommended auto-sync steps.
- Shows the latest dropped-camera sync score from `output\reports\app_sync_offsets.json` and refreshes it after auto-sync runs.
- Provides direct workflow actions for overlay regeneration, background music generation, audio replacement, project thumbnail generation, thumbnail candidate contact sheets, subtitle QA review, subtitle correction application, subtitle speaker-role classification, source transcript comparison, camera analysis, transcription, camera/audio sync, silence shortening, and ffprobe verification.
- Provides timeline workflow actions that build and validate `output\timelines\current.timeline.json` from the current project config and analysis reports, diff it against a baseline timeline to identify changed regions, export/import OpenTimelineIO-style JSON, then export or execute audited FFmpeg command/filter-graph artifacts, including preview/proxy and changed-region commands, from that validated timeline. It can also export and execute audited Remotion, HyperFrames, and Blender layer/job command artifacts from the same validated timeline, explicitly render Remotion overlay layers, and run staged changed-region, preview, or final renders that composite validated Remotion and Blender PNG-sequence overlay artifacts back into the FFmpeg base render.
- Starts `codex app-server` from the Electron main process and sends a structured edit request with `C:\Users\yurin\Desktop\video_edit` as the working directory.
- Runs direct workflow actions through `scripts\video_edit_run.py`, which reads the runtime app config and delegates to common Python render, analysis, FFmpeg, and ffprobe commands.
- Includes `render_app_interview.py`, a generic dropped-file interview renderer for master/right/left camera files and optional external audio.
- Includes `auto_sync_app_sources.py`, which creates `app_sync_offsets.json` from dropped camera audio before the generic renderer runs, with a local fine waveform pass after the coarse match. Full material analysis also runs source transcript comparison so the renderer has a current-project fallback when waveform sync is weak or missing.

The app intentionally keeps the Python pipeline as the execution source of truth. Direct command actions require an active project, write a runtime app config under the active project output, then call `scripts\video_edit_run.py` with `VIDEO_EDIT_APP_CONFIG`. The shared runner converts that config into script inputs. Edit intent is now represented by `config\timeline.schema.json` plus `output\timelines\current.timeline.json`; renderers should consume a validated timeline and generate FFmpeg/Remotion/HyperFrames/Blender commands themselves. `scripts\ffmpeg_timeline_adapter.py` exports argv/filter-graph artifacts, preview/proxy command artifacts, clip scale/crop-center filters, legacy precomposed PNG subtitle overlays when a PNG manifest is selected, optional Remotion/Blender PNG-sequence overlay composition, and optional render logs while the older `render_app_interview.py` path remains available as a fallback. `scripts\timeline_graphics_adapter.py` exports Remotion/HyperFrames layer manifests and Blender job manifests plus audited renderer argv reports; `scripts\timeline_otio_adapter.py` exports/imports OpenTimelineIO-style JSON. The Remotion scaffold in `remotion\index.tsx` renders overlay layers from that manifest, renders full subtitles from structured HTML/CSS layout JSON by default, and materializes only needed image/logo assets under ignored `public\adapter-assets`. The config drives the active project roots, title text/size, logo path/height, subtitle size/color/opacity, punchline text/timing, music generation/mix settings, omission-card replacement settings, person-aware and face-center crop usage, transcript sync fallback, camera color-match and natural-cut settings, thumbnail and thumbnail-candidate settings, subtitle-QA/correction/comparison/speaker-diagnostic settings, Python/FFmpeg/FFprobe paths, analysis settings, and generic-render audio denoise/mastering/encoding settings.

## Direct Project Runs

Project separation also works without Electron. From `C:\Users\yurin\Desktop\video_edit`, set `VIDEO_EDIT_PROJECT` before running Python scripts:

```powershell
Set-Location 'C:\Users\yurin\Desktop\video_edit'
$env:VIDEO_EDIT_PROJECT = 'client-a-interview'
python scripts\video_edit_run.py --action render-selected
```

With that variable set, shared script paths resolve to:

- `source`: `projects\client-a-interview\source`
- `output`: `projects\client-a-interview\output`

For custom absolute roots, use `VIDEO_EDIT_PROJECT_ROOT`, or override only one side with `VIDEO_EDIT_PROJECT_SOURCE` / `VIDEO_EDIT_PROJECT_OUTPUT`.

Audio noise reduction is user-selectable. When enabled, the common interview renderer applies a high-pass filter and FFmpeg `afftdn`.

Direct preset runs use app-server `command/exec` with `dangerFullAccess` because the configured Python and FFmpeg executables live outside the workspace. Project and source-root choices are passed through the runtime app config before running the script.

The Windows build uses `app\build\icon.ico` and disables executable resource editing with `signAndEditExecutable: false`; this avoids the local `rcedit` commit failure while preserving portable and installer output generation.
