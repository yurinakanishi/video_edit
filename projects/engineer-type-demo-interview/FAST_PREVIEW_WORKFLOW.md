# Fast Preview Workflow

Use this workflow for quick `engineer-type-demo-interview` review renders.

## One-Time Proxy Setup

Generate or refresh camera proxies:

```powershell
$env:VIDEO_EDIT_PROJECT = "engineer-type-demo-interview"
python scripts/video_edit_run.py --action generate-proxies
```

The renderer uses these proxies only when `render.renderProfile` is `preview`.

## 240p Preview Project Setting

Apply the 240p preview preset to `project_state.json`:

```powershell
python projects/engineer-type-demo-interview/scripts/configure_preview_240p.py
```

This sets:

- `render.renderProfile = "preview"`
- `render.outputHeight = 240`
- `render.outputPath = projects/engineer-type-demo-interview/output/videos/preview_240p.mp4`
- `render.subtitleOverlayFormat = "png"`

Preview profile also skips silence shortening in `scripts/render_multicam.py`.

## Spot Preview

Render a short window from the reviewed-video baseline:

```powershell
python projects/engineer-type-demo-interview/scripts/render_spot_preview.py --review-start 4:00 --duration 20 --label timing-check
```

Render from an absolute source timeline position:

```powershell
python projects/engineer-type-demo-interview/scripts/render_spot_preview.py --source-start 325.5 --duration 20 --label source-check
```

Use `--dry-run` to write the temporary config and print the command without rendering.

## Subtitle PNG Cache

Full subtitle PNG overlays now keep a fingerprint cache:

```powershell
$env:VIDEO_EDIT_PROJECT = "engineer-type-demo-interview"
python scripts/generate_full_transcript_png_overlays.py --format png
```

Use `--fresh` only when intentionally rebuilding every subtitle PNG.
