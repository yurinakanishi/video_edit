# Video Edit Common Workflow

This document is the app-level contract. It must stay project-neutral. Put project goals, source notes, QA findings, one-off commands, and custom scripts under `projects/<project-id>/`.

## Source Of Truth

- Editable project state: `projects/<project-id>/project_state.json`.
- Runtime config snapshot: `projects/<project-id>/output/app/video_edit_app_config.runtime.json`, passed through `VIDEO_EDIT_APP_CONFIG`.
- Command-line project context: `VIDEO_EDIT_PROJECT=<project-id>` or `VIDEO_EDIT_PROJECT_ROOT=<absolute-project-root>`.
- Media manifest: `assets.mediaManifest` or `assets.mediaManifestPath`.
- Normalized timeline: `projects/<project-id>/output/timelines/current.timeline.json`, validated by `config/timeline.schema.json`.
- Generated reports, transcripts, overlays, and renders stay under the active project's `output` tree.

Shared scripts must fail with a clear error when project context or required inputs are missing. They must not read old root-level `source` or `output` folders, stale `.video-edit` runtime config, or another project's reports.

## Project Layout

Each project may include Codex-readable instructions and project-local automation:

```text
projects/<project-id>/
  VIDEO_EDITING_INSTRUCTIONS.md
  scripts/
  config/
  source/   # ignored media
  output/   # ignored generated artifacts
```

- `VIDEO_EDITING_INSTRUCTIONS.md` describes the project's goal, materials, edit policy, one-off scripts, and verification checklist.
- `projects/<project-id>/scripts` is for project-specific automation that composes shared app tools.
- Shared app code under `scripts`, `app`, `remotion`, `config`, and `docs` must remain reusable across projects.
- Electron does not run project-local scripts directly. Codex or the CLI should run them after reading the project instructions.
- Shared workflow actions and Python script allowlists live in `config/workflow_actions.json`; update that manifest instead of adding separate action lists in Python or Electron.

## Common Commands

Set the active project first:

```powershell
$env:VIDEO_EDIT_PROJECT = "<project-id>"
```

Then run shared app actions through the generic runner:

```powershell
python .\scripts\video_edit_run.py --action transcribe-dropped
python .\scripts\video_edit_run.py --action transcribe-dropped-faster
python .\scripts\video_edit_run.py --action auto-sync-dropped
python .\scripts\video_edit_run.py --action compare-transcripts
python .\scripts\video_edit_run.py --action review-subtitles
python .\scripts\video_edit_run.py --action apply-subtitle-corrections
python .\scripts\video_edit_run.py --action classify-subtitle-speakers
python .\scripts\video_edit_run.py --action classify-subtitle-speakers-audio
python .\scripts\video_edit_run.py --action analyze-person-edit-metadata
python .\scripts\video_edit_run.py --action analyze-blocking
python .\scripts\video_edit_run.py --action generate-music-bed
python .\scripts\video_edit_run.py --action replace-audio
python .\scripts\video_edit_run.py --action generate-thumbnail
python .\scripts\video_edit_run.py --action generate-thumbnail-candidates
python .\scripts\video_edit_run.py --action build-timeline
python .\scripts\video_edit_run.py --action validate-timeline
python .\scripts\video_edit_run.py --action export-ffmpeg-command
python .\scripts\video_edit_run.py --action render-timeline-ffmpeg
python .\scripts\video_edit_run.py --action render-selected
```

Use `--dry-run` to inspect the resolved command without running it.

## Timeline And Rendering Contract

- AI/operator edit decisions should be expressed as project state or renderer-agnostic timeline JSON.
- `scripts/build_edit_timeline.py` converts current project config, media manifest, sync offsets, transcript selections, camera plans, analysis reports, and style settings into `output/timelines/current.timeline.json`.
- `scripts/timeline_validate.py` must pass before renderer adapters run.
- `scripts/ffmpeg_timeline_adapter.py` exports audited FFmpeg argv/filter-graph artifacts and can execute validated full, preview, proxy, and changed-region renders.
- `scripts/timeline_graphics_adapter.py` exports Remotion, HyperFrames, and Blender layer/job manifests plus audited renderer argv reports.
- `remotion/index.tsx` is the bundled transparent overlay renderer scaffold. Base camera/audio assembly remains FFmpeg's job.
- `scripts/render_multicam.py` is the generic legacy FFmpeg-backed renderer entry point. `scripts/render_app_interview.py` remains as a compatibility alias target for existing project states.

Audit artifacts should remain traceable: timeline JSON, validation reports, renderer commands/filter graphs, analysis reports, and render logs.

## Shared Behaviors

- Sync: `auto-sync-dropped` writes current-project waveform offsets under `output/reports/app_sync_offsets.json`; transcript comparison is only a fallback when the report fingerprint matches the active project.
- Transcription: transcript actions write under `output/transcripts/manifest_sources` and must not reuse transcripts from another project.
- Subtitles: full subtitle overlays use the selected project transcript and speaker-role reports. If no current transcript exists, generation should fail.
- Music: `generate-music-bed` writes a project-local music bed under `output/audio`; renderers use `music.*` config for whole-video or range-scoped mixing.
- Audio replacement: `replace-audio` uses the selected current-project input video, external audio, sync offsets, and render output path.
- Omission cards: omission replacement is driven by `omissionCard.*` runtime config and writes project-local overlay artifacts.
- Thumbnails: thumbnail actions read project media and style settings, then write project-local images and reports.
- Person/camera analysis: analysis scripts write reports under `output/reports` and should be consumed through project state or timeline effects.

## Script Guidelines

- Shared script names should describe reusable behavior, not a specific clip, person, event, source camera, date, or client.
- Defaults must be generic. Project-specific values belong in project state, project instructions, project config, media manifests, or project-local scripts.
- Prefer structured project state and timeline JSON over hand-written FFmpeg commands.
- Add a shared abstraction only when it removes reusable complexity across projects.
- If a project needs one-off ordering, selection, tuning, or QA logic, create a project-local script that imports or invokes shared tools instead of editing shared app code.
- Run `pnpm run arch:check` after adding or moving shared workflow actions, scripts, or project-boundary rules.
