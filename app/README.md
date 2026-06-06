# Video Edit Electron App

Electron UI for operating the shared `video_edit` project pipeline.

## Run

```powershell
Set-Location .\app
pnpm install
pnpm start
```

Build a portable Windows app and installer:

```powershell
Set-Location .\app
pnpm run dist
```

Build artifacts are written to `..\release`. TypeScript sources live under `src`; the renderer is a React + Vite app built into `dist\renderer` before Electron starts.

## What It Does

- Creates and selects per-video projects under `projects\<project-id>`.
- Keeps smoke-test projects under named test roots such as `projects\__smoke__\simple-ui-drop\<run-id>` when `VIDEO_EDIT_PROJECTS_ROOT` is set.
- Maintains project-local source/output roots, media manifests, runtime config snapshots, and AI-editable project state.
- Accepts selected media for master/camera sources, external audio, logos, still images, subtitles, and output paths.
- Runs shared workflow actions through `scripts\video_edit_run.py` with `VIDEO_EDIT_APP_CONFIG`; reusable Python implementation lives in `video_edit_core`.
- Builds and validates renderer-agnostic timelines under the active project's `output\timelines`.
- Exports or executes audited FFmpeg, Remotion, HyperFrames, Blender, and OTIO adapter commands from validated timelines.
- Provides reusable controls for transcription, subtitle QA/corrections, speaker roles, sync, person/camera analysis, thumbnails, music beds, omission cards, audio replacement, color matching, crop/framing, denoise/mastering, encoding, and verification.
- Starts `codex app-server` and sends Codex a structured request that points to the active project.

## Project Boundary

Before asking Codex to perform project-specific editing, the app prompt tells Codex to read:

```text
projects\<project-id>\VIDEO_EDITING_INSTRUCTIONS.md
projects\<project-id>\scripts\
projects\<project-id>\config\
```

Electron only allowlists shared scripts. Project-local scripts are intentionally run by Codex or CLI, not directly by the app UI. One-off project behavior should stay in those project files instead of changing shared app code.

Shared `scripts\*.py` files are stable CLI entry points and compatibility wrappers. Put reusable Python logic in `video_edit_core` and import it from project-local scripts when needed.

## Direct Project Runs

Project separation also works without Electron. From the repository root:

```powershell
$env:VIDEO_EDIT_PROJECT = '<project-id>'
python scripts\video_edit_run.py --action render-selected
```

For custom absolute roots, use `VIDEO_EDIT_PROJECT_ROOT`, or override only one side with `VIDEO_EDIT_PROJECT_SOURCE` / `VIDEO_EDIT_PROJECT_OUTPUT`.

## Development

```powershell
pnpm run lint
pnpm run typecheck
pnpm run check
```

`pnpm run smoke:simple-ui-drop` creates fixtures in `app\smoke_outputs` and creates app projects under `projects\__smoke__\simple-ui-drop\<run-id>` via `VIDEO_EDIT_PROJECTS_ROOT`. Keep any test-generated projects under a named test directory instead of the top-level `projects` list.

The Windows build uses `app\build\icon.ico` and disables executable resource editing with `signAndEditExecutable: false`.
