export type SelectOption = readonly [value: string, label: string];

export const EDIT_PRESETS = [["new-interview", "New interview edit from selected media"]] as const;

export const MULTICAM_MODES = [
	["speaker-aware", "Speaker-aware interview cuts"],
	["dynamic-cuts", "Rhythmic punch-in cuts"],
	["manual-plan", "Use saved manual plan"],
	["master-first", "Master first, close-ups for emphasis"],
] as const;

export const AUDIO_SOURCES = [
	["external-if-selected", "Use external audio if selected"],
	["masterVideo", "Use master video audio"],
	["rightCloseVideo", "Use right close-up audio"],
	["leftCloseVideo", "Use left close-up audio"],
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
	["export-ffmpeg-command", "Export FFmpeg command from timeline"],
	["export-ffmpeg-preview-command", "Export FFmpeg preview command"],
	["render-timeline-ffmpeg", "Render timeline with FFmpeg adapter"],
	["generate-proxies", "Generate proxy videos"],
	["generate-punchlines", "Create catchy subtitle images"],
	["generate-full-overlays", "Create full subtitle images"],
	["generate-glossary-overlays", "Create glossary explanation images"],
	["generate-music-bed", "Generate background music"],
	["replace-audio", "Replace video audio"],
	["generate-thumbnail", "Generate thumbnail image"],
	["generate-thumbnail-candidates", "Generate thumbnail candidates"],
	["review-subtitles", "Review subtitle quality"],
	["apply-subtitle-corrections", "Apply subtitle corrections"],
	["classify-subtitle-speakers", "Classify subtitle speakers"],
	["compare-transcripts", "Compare source transcripts"],
	["analyze-blocking", "Analyze camera framing"],
	["analyze-person-edit-metadata", "Analyze people for camera cuts"],
	["analyze-reference-video", "Analyze reference video"],
	["auto-sync-dropped", "Sync selected camera files"],
	["transcribe-dropped", "Transcribe selected media"],
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
