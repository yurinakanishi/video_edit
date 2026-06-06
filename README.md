# Video Edit

Electron operator UI plus shared Python tools for project-based video editing.

## Layout

```text
app/                      Electron UI source
video_edit_core/          Reusable Python package used by shared CLI wrappers
scripts/                  Shared Python render, analysis, transcript, and adapter tools
remotion/                 Shared Remotion overlay scaffold
config/                   App-level schemas and portable config files
docs/                     App architecture and shared workflow notes
projects/<project-id>/    Project instructions, project-local scripts/config, media, and outputs
projects/__smoke__/       Named test project workspaces and legacy smoke artifacts
.video-edit/              Local runtime state, caches, and logs
release/                  Packaged Electron builds
```

Projects use this standard shape:

```text
projects/<project-id>/
  VIDEO_EDITING_INSTRUCTIONS.md
  scripts/
  config/
  source/   # ignored source media
  output/   # ignored generated artifacts
```

Large media, generated outputs, `.video-edit/`, `projects/*/source`, `projects/*/output`, project state snapshots, dependencies, and packaged builds are ignored by Git. Project Markdown, `projects/*/scripts`, and `projects/*/config` are intentionally trackable.

Test-only project workspaces must be grouped under a named test directory, for example `projects/__smoke__/simple-ui-drop/<run-id>/`. Do not leave generated smoke fixtures such as `material-folder` or `material-folder-02` at the top level of `projects/`; top-level entries should represent real user-facing projects.

## App Boundary

The app, shared scripts, and `video_edit_core` provide reusable editing parts:

- project discovery, media manifests, and runtime config snapshots;
- transcription, subtitle QA/correction, speaker classification, and sync analysis;
- person/camera analysis, music-bed generation, thumbnails, and audio replacement;
- timeline building and validation;
- FFmpeg, Remotion, HyperFrames, Blender, and OTIO adapters;
- the generic FFmpeg-backed renderer entry point `scripts/render_multicam.py`.

Project-specific goals, source notes, editing policy, QA findings, custom commands, and one-off automation belong under the project directory. Do not modify shared app code to satisfy a single project's requirement; create `projects/<project-id>/scripts/<task>.py` and call shared tools from there.

Shared workflow actions and script allowlists are defined in `config/workflow_actions.json`. Python, Electron main, and architecture checks read that manifest so new shared actions are registered in one place. Reusable Python implementation should live under `video_edit_core`; `scripts/*.py` files remain stable CLI entry points and compatibility wrappers.

## Common Entry Point

Set the active project, then run a shared action:

```powershell
$env:VIDEO_EDIT_PROJECT = "<project-id>"
python .\scripts\video_edit_run.py --action build-timeline
python .\scripts\video_edit_run.py --action validate-timeline
python .\scripts\video_edit_run.py --action render-selected
```

Use `--dry-run` to inspect the resolved command:

```powershell
python .\scripts\video_edit_run.py --action build-timeline --dry-run
```

The Electron app writes a project-local runtime config under `projects\<project-id>\output\app\video_edit_app_config.runtime.json` and passes it through `VIDEO_EDIT_APP_CONFIG`. Command-line runs can read `project_state.json` when `VIDEO_EDIT_PROJECT` or `VIDEO_EDIT_PROJECT_ROOT` is set and `VIDEO_EDIT_APP_CONFIG` is unset.

Electron development and smoke runs can set `VIDEO_EDIT_PROJECTS_ROOT` to redirect app project discovery and creation to a test-specific root, such as `projects\__smoke__\simple-ui-drop\<run-id>`.

## Timeline Contract

Renderer-agnostic edit decisions should be represented as project state or timeline JSON. `build-timeline` writes `projects\<project-id>\output\timelines\current.timeline.json` and `validate-timeline` validates it with `config\timeline.schema.json`.

Renderer adapters consume validated timelines and write audited command artifacts under the active project's `output\reports` tree. `render-timeline-ffmpeg` executes the FFmpeg adapter. Graphics adapters can export or render Remotion, HyperFrames, and Blender overlay artifacts. `render-selected` uses `scripts/render_multicam.py` by default for the shared FFmpeg-backed path; `scripts/render_app_interview.py` remains as a compatibility shim for existing saved project states.

## Project Instructions

Before doing project-specific work, Codex should read:

```text
projects/<project-id>/VIDEO_EDITING_INSTRUCTIONS.md
projects/<project-id>/scripts/
projects/<project-id>/config/
```

Those files define the project's objective, materials, edit decisions, custom automation, and verification checklist. Shared docs stay generic; project Markdown carries the project-specific knowledge.

## Development

```powershell
pnpm run arch:check
pnpm run typecheck
pnpm run lint
pnpm run build
```

For the detailed shared workflow, see `docs/video_edit_method.md`.
