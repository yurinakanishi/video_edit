# Reference Assets

This directory stores shared visual reference material for multiple video projects.

It is not an editing project. Do not treat it as an active `projects/<project-id>/` workspace.

## Purpose

- Keep common reference videos and screenshots available outside project-specific workspaces.
- Preserve the original Downloads paths in manifests.
- Produce one structured `analysis.json` for every source asset.
- Use these materials as composition, layout, subtitle, logo, annotation, and visual-style references for future video generation and editing.

## Boundaries

- Do not change shared app code, `video_edit_core/`, or root `scripts/` for this library.
- Put one-off ingest, analysis, QA, and validation logic under `reference-assets/scripts/`.
- Keep copied source media under `reference-assets/library/`.
- Use one directory per copied asset, such as `reference-assets/library/collections/layer-x/video/sample-1/`.
- Use short copied asset IDs and filenames such as `sample-1.mp4` and `sample-2.png`; keep the original Downloads filenames only in manifest metadata.
- Keep each asset's `analysis.json`, sampled frames, and debug overlays beside the copied media file.
- Keep aggregate manifests, QA reports, summaries, and contact sheets under `reference-assets/output/reports/`.
- Downloads-side files are retained; this library uses copied source material.

## Expected Workflow

1. Run `python reference-assets/scripts/ingest_reference_assets.py --dry-run`.
2. Run `python reference-assets/scripts/ingest_reference_assets.py`.
3. Prepare the analysis environment using `config/requirements.analysis.txt`.
4. Run `python reference-assets/scripts/analyze_reference_assets.py`.
5. Run `python reference-assets/scripts/validate_reference_assets.py`.

For quick checks, use `--limit 1` on ingest and analysis before processing all assets.
