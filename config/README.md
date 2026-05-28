# App Config

Reserved for app-level defaults and portable configuration files.

Project-specific media, transcripts, manifests, and generated outputs belong under `projects/<project-id>/`.

Thumbnail, thumbnail-candidate, BGM, render, transcription, transcript-comparison sync, subtitle-QA, subtitle-correction, and subtitle-speaker-role settings are written by the Electron app into the project runtime config. They should remain project-config driven rather than pointing at historical root-level `source/` or `output/` files.
