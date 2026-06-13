# Fast Preview Workflow

Use this workflow when iterating on `projects/layer-x-domain-expert` preview edits. Do not start with a final production render.

## Cached Full Preview

Check segment-cache health without rewriting the saved audit report:

```powershell
python projects/layer-x-domain-expert/scripts/audit_render_segment_cache.py --no-write
```

Render the full preview using valid cached segments by default:

```powershell
python projects/layer-x-domain-expert/scripts/render_test_project1_style_preview.py --output projects/layer-x-domain-expert/output/videos/full_preview_1080p.mp4 --output-height 1080
```

`--resume-existing` is still accepted for older command history, but it is no longer required.

Only rebuild every segment intentionally:

```powershell
python projects/layer-x-domain-expert/scripts/render_test_project1_style_preview.py --fresh --output projects/layer-x-domain-expert/output/videos/full_preview_1080p.mp4 --output-height 1080
```

## Spot Checks

Render a short window when only one change area needs review:

```powershell
python projects/layer-x-domain-expert/scripts/render_limited_preview.py
```

Render the tail for end-card or closing checks:

```powershell
python projects/layer-x-domain-expert/scripts/render_tail_preview.py
```

## Proxies

Generate shared preview proxies once per fresh source import:

```powershell
$env:VIDEO_EDIT_PROJECT = "layer-x-domain-expert"
python scripts/video_edit_run.py --action generate-proxies
```

The Electron app supplies project context automatically. Direct terminal/Codex runs should set `VIDEO_EDIT_PROJECT` first.

When `render.renderProfile` is `preview`, `scripts/render_multicam.py` uses proxy metadata from `output/reports/media_manifest.json`. If a preview render falls back to original media, check `output/reports/render_usage.json` for `proxyWarnings`.
