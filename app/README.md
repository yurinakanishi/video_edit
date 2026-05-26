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

Build artifacts are written to `C:\Users\yurin\Desktop\video_edit\output\app\dist`.

TypeScript sources live under `src` and compile to `dist` before Electron starts. Static renderer files are copied by `scripts\copy-static.mjs`.

Use Biome for formatting and linting:

```powershell
pnpm run lint
pnpm run format
pnpm run check
```

## What It Does

- Accepts drag-and-drop or picker-based inputs for master video, right close-up, left close-up, external audio, logo, and output path.
- Lets you choose current preset scripts or a new interview multicam request.
- Provides source-root and tool-path controls for the paths described in `docs\video_edit_method.md`.
- Exposes subtitle mode selection: full transcript, catchy/punchline, or none.
- Exposes automatic context/speaker camera cuts for the current one-pass preset, passing `--auto-context-cuts` so subtitle speaker roles and answer context can drive camera changes.
- Exposes natural short-dialogue-gap cut placement, passing `--natural-dialogue-cuts` so camera changes can move a few hundred milliseconds into nearby low-energy pauses without shortening the audio.
- Captures title, subtitle, color, opacity, logo-size, punchline-list, output-duration, audio-noise-reduction, and silence-shortening settings.
- Shows a preflight checklist for missing output paths, required camera files, audio fallbacks, silence-shortening state, and recommended auto-sync steps.
- Shows the latest dropped-camera sync score from `output\reports\app_sync_offsets.json` and refreshes it after auto-sync runs.
- Provides direct method workflow actions for subtitle review, overlay regeneration, thumbnail candidate generation, camera analysis, transcript sync, waveform refinement, multicam base build, sound-2 audio replacement, silence shortening, and ffprobe verification.
- Runs `scripts\generate_thumbnail_candidates.py --import-assets` from the workflow action menu, supports the standard, center-face bottom-title, right-face stacked-title, and left-face stacked-title thumbnail modes, and opens the selected mode's contact sheet from the top bar.
- Starts `codex app-server` from the Electron main process and sends a structured edit request with `C:\Users\yurin\Desktop\video_edit` as the working directory.
- Can run the current known render scripts directly through `command/exec` when the selected preset maps cleanly to an existing script.
- Includes `render_app_interview.py`, a generic dropped-file interview renderer for master/right/left camera files and optional external audio.
- Includes `auto_sync_app_sources.py`, which creates `app_sync_offsets.json` from dropped camera audio before the generic renderer runs.

The app intentionally keeps the Python render scripts as the source of truth. Direct command actions run existing script CLI flags and write a runtime app config under `output\app` consumed by the Python scripts. The config currently drives title text/size, logo path/height, subtitle size/color/opacity, punchline text/timing, source root, FFmpeg path, and generic-render audio denoise settings.

Audio noise reduction is user-selectable. When enabled, direct render scripts apply a high-pass filter and FFmpeg `afftdn`; the one-pass YouTube preset keeps its existing normalization chain and makes the denoise stage configurable.

Direct preset runs use app-server `command/exec` with `dangerFullAccess` because the configured Python and FFmpeg executables live outside the workspace. When the source-root field is set, the app wraps direct commands in PowerShell and sets `VIDEO_EDIT_SOURCE_ROOT` before running the script.

The Windows build uses `app\build\icon.ico` and disables executable resource editing with `signAndEditExecutable: false`; this avoids the local `rcedit` commit failure while preserving portable and installer output generation.
