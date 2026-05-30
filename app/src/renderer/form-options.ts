export type SelectOption = readonly [value: string, label: string];

export const EDIT_PRESETS = [
	["multicam-edit", "Multicam edit from selected media"],
	["new-interview", "Compatibility saved preset"],
] as const;

export const MULTICAM_MODES = [
	["speaker-aware", "Speaker-aware dialogue cuts"],
	["dynamic-cuts", "Rhythmic punch-in cuts"],
	["manual-plan", "Use saved manual plan"],
	["master-first", "Master first, close-ups for emphasis"],
] as const;

export const AUDIO_SOURCES = [
	["external-if-selected", "Use external audio if selected"],
	["masterVideo", "Use master video audio"],
	["rightCloseVideo", "Use camera 2 audio"],
	["leftCloseVideo", "Use camera 3 audio"],
] as const;

export const ENCODER_PRESETS = [
	["ultrafast", "Fastest preview (ultrafast)"],
	["superfast", "Very fast preview (superfast)"],
	["veryfast", "Fast draft (veryfast)"],
	["faster", "Faster encode (faster)"],
	["fast", "Fast encode (fast)"],
	["medium", "Balanced quality (medium)"],
	["slow", "High quality (slow)"],
	["slower", "Higher quality (slower)"],
	["veryslow", "Maximum quality (veryslow)"],
] as const;

export const RENDER_PROFILES = [
	["preview", "Fast preview"],
	["final", "Final output"],
] as const;

export const RANGE_MODES = [
	["range", "Selected range"],
	["full", "Full timeline"],
] as const;

export const MUSIC_SCOPES = [
	["full", "Whole video"],
	["omission", "Omission title ranges only"],
] as const;

export const MUSIC_RANGE_SOURCES = [
	["auto", "Auto + manual ranges"],
	["manual", "Manual ranges only"],
] as const;

export const WORKFLOW_ACTIONS = [
	["render-selected", "Create video from selected settings"],
	["build-timeline", "Build validated timeline JSON"],
	["validate-timeline", "Validate timeline JSON"],
	["detect-changed-regions", "Detect changed timeline regions"],
	["export-otio", "Export OpenTimelineIO JSON"],
	["import-otio", "Import OpenTimelineIO JSON"],
	["export-ffmpeg-command", "Export FFmpeg command from timeline"],
	["export-ffmpeg-preview-command", "Export FFmpeg preview command"],
	["export-changed-region-commands", "Export changed-region commands"],
	["render-changed-regions", "Render changed timeline regions"],
	["export-changed-region-remotion-commands", "Export changed-region Remotion commands"],
	["render-changed-regions-with-remotion-overlays", "Render changed regions with Remotion"],
	["export-changed-region-blender-commands", "Export changed-region Blender commands"],
	["render-changed-regions-with-blender-elements", "Render changed regions with Blender"],
	["export-changed-region-remotion-and-blender-commands", "Export changed-region Remotion + Blender"],
	["render-changed-regions-with-remotion-and-blender", "Render changed regions with Remotion + Blender"],
	["render-timeline-ffmpeg", "Render timeline with FFmpeg adapter"],
	["export-ffmpeg-preview-with-remotion-overlays", "Export preview with Remotion overlays"],
	["render-preview-with-remotion-overlays", "Render preview with Remotion overlays"],
	["export-ffmpeg-with-remotion-overlays", "Export FFmpeg + Remotion overlay command"],
	["render-final-with-remotion-overlays", "Render final with Remotion overlays"],
	["export-ffmpeg-preview-with-blender-elements", "Export preview with Blender elements"],
	["render-preview-with-blender-elements", "Render preview with Blender elements"],
	["export-ffmpeg-preview-with-remotion-and-blender", "Export preview with Remotion + Blender"],
	["render-preview-with-remotion-and-blender", "Render preview with Remotion + Blender"],
	["export-ffmpeg-with-blender-elements", "Export FFmpeg + Blender command"],
	["render-final-with-blender-elements", "Render final with Blender elements"],
	["export-ffmpeg-with-remotion-and-blender", "Export FFmpeg + Remotion + Blender"],
	["render-final-with-remotion-and-blender", "Render final with Remotion + Blender"],
	["export-remotion-command", "Export Remotion layer command"],
	["render-remotion-layers", "Render Remotion overlay layers"],
	["export-hyperframes-command", "Export HyperFrames layer command"],
	["render-hyperframes-layers", "Render HyperFrames overlay layers"],
	["export-blender-command", "Export Blender job command"],
	["render-blender-elements", "Render Blender elements"],
	["generate-proxies", "Generate proxy videos"],
	["generate-punchlines", "Create catchy subtitle images"],
	["generate-full-overlays", "Create full subtitle images"],
	["precompose-png-overlay-video", "Precompose PNG overlay video"],
	["generate-glossary-overlays", "Create glossary explanation images"],
	["generate-music-bed", "Generate background music"],
	["replace-audio", "Replace video audio"],
	["generate-thumbnail", "Generate thumbnail image"],
	["generate-thumbnail-candidates", "Generate thumbnail candidates"],
	["review-subtitles", "Review subtitle quality"],
	["apply-subtitle-corrections", "Apply subtitle corrections"],
	["classify-subtitle-speakers", "Classify subtitle speakers"],
	["classify-subtitle-speakers-audio", "Classify subtitle speakers from audio"],
	["compare-transcripts", "Compare source transcripts"],
	["analyze-blocking", "Analyze camera framing"],
	["analyze-person-edit-metadata", "Analyze people for camera cuts"],
	["analyze-reference-video", "Analyze reference video"],
	["auto-sync-dropped", "Sync selected camera files"],
	["transcribe-dropped", "Transcribe selected media"],
	["transcribe-dropped-faster", "Transcribe selected media faster"],
	["generate-role-aware-ass", "Generate role-aware ASS subtitles"],
	["shorten-input", "Shorten silence in selected video"],
	["extract-still", "Save a still image"],
	["verify-duration", "Check output duration"],
	["verify-audio", "Check output audio"],
] as const;

export const THUMBNAIL_MODES = [
	["standard", "Standard"],
	["closeup_bottom_title", "Close-up bottom title"],
	["right_face_title_stack", "Face right / title left"],
	["left_face_title_stack", "Face left / title right"],
] as const;

export const THUMBNAIL_COLORS = [
	"Yellow",
	"White",
	"Cyan",
	"Green",
	"Red",
	"Orange",
	"Pink",
	"Purple",
	"Blue",
] as const;

export const THUMBNAIL_COLOR_OPTIONS = THUMBNAIL_COLORS.map((color) => [color.toLowerCase(), color] as const);

export function selectOptionLabel(options: readonly SelectOption[], value: string) {
	return options.find(([optionValue]) => optionValue === value)?.[1] || value;
}
