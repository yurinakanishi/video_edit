import { type AppStore, getAppState } from "./app-store.js";

type StoreFieldGroup = {
	readonly stateKey: keyof AppStore;
	readonly actionKey: keyof AppStore;
	readonly fields: readonly string[];
	readonly booleanFields?: readonly string[];
};

type FormFieldResult = {
	readonly found: boolean;
	readonly value?: string | boolean;
};

const storeFieldGroups: StoreFieldGroup[] = [
	{
		stateKey: "workflowSettings",
		actionKey: "setWorkflowSettings",
		fields: ["editPreset", "workflowAction", "renderScript", "previewDuration"],
	},
	{
		stateKey: "renderSettings",
		actionKey: "setRenderSettings",
		fields: [
			"renderProfile",
			"rangeMode",
			"multicamMode",
			"audioSource",
			"audioDenoise",
			"audioDenoiseStrength",
			"audioMastering",
			"encoderPreset",
			"renderCrf",
			"colorMatchCameras",
			"globalVideoZoom",
			"usePersonEditPlans",
			"useTranscriptComparisonSync",
			"naturalDialogueCuts",
			"previewStart",
			"shortenSilence",
			"minSilence",
			"keepSilence",
			"silenceNoise",
			"keepUncut",
		],
		booleanFields: [
			"audioDenoise",
			"audioMastering",
			"colorMatchCameras",
			"usePersonEditPlans",
			"useTranscriptComparisonSync",
			"naturalDialogueCuts",
			"shortenSilence",
			"keepUncut",
		],
	},
	{
		stateKey: "musicSettings",
		actionKey: "setMusicSettings",
		fields: ["musicEnabled", "musicScope", "musicRangeSource", "musicPrompt", "musicVolume", "musicRangesText"],
		booleanFields: ["musicEnabled"],
	},
	{
		stateKey: "omissionCardSettings",
		actionKey: "setOmissionCardSettings",
		fields: [
			"omissionCardEnabled",
			"omissionCardDuration",
			"omissionCardLabel",
			"omissionCardText",
			"omissionCardRangesText",
		],
		booleanFields: ["omissionCardEnabled"],
	},
	{
		stateKey: "styleSettings",
		actionKey: "setStyleSettings",
		fields: ["subtitleSize", "highlightColor", "boxOpacity", "titleSize", "logoHeight", "termExplanations"],
		booleanFields: ["termExplanations"],
	},
	{
		stateKey: "analysisSettings",
		actionKey: "setAnalysisSettings",
		fields: [
			"transcribeModel",
			"transcribeLanguage",
			"transcribeBeamSize",
			"transcribeTemperature",
			"transcribePromptTerms",
			"transcribeNormalizeAudio",
			"transcribeFilterLowConfidence",
			"conditionOnPreviousText",
			"stillTime",
			"personFpsSample",
			"personModel",
			"personConfidence",
			"personMaxSeconds",
			"personLimit",
			"personNoMulticamRoot",
		],
		booleanFields: [
			"transcribeNormalizeAudio",
			"transcribeFilterLowConfidence",
			"conditionOnPreviousText",
			"personNoMulticamRoot",
		],
	},
	{
		stateKey: "thumbnailSettings",
		actionKey: "setThumbnailSettings",
		fields: [
			"thumbnailTime",
			"thumbnailTitle",
			"thumbnailSubtitle",
			"thumbnailCandidateCount",
			"thumbnailMode",
			"thumbnailMainColor",
			"thumbnailCandidateTimes",
			"thumbnailDebugFaces",
		],
		booleanFields: ["thumbnailDebugFaces"],
	},
	{
		stateKey: "subtitleReviewSettings",
		actionKey: "setSubtitleReviewSettings",
		fields: [
			"subtitleReviewMaxDuration",
			"subtitleReviewMaxCharsPerSecond",
			"subtitleSuspiciousPatterns",
			"subtitleReviewExtractClips",
			"subtitleReviewTranscribeClips",
			"subtitleCorrectionsText",
		],
		booleanFields: ["subtitleReviewExtractClips", "subtitleReviewTranscribeClips"],
	},
	{
		stateKey: "subtitleSpeakerSettings",
		actionKey: "setSubtitleSpeakerSettings",
		fields: [
			"subtitleInterviewerRanges",
			"subtitleInterviewerPatterns",
			"subtitleManualRoles",
			"subtitleMouthMotionDiagnostics",
		],
		booleanFields: ["subtitleMouthMotionDiagnostics"],
	},
	{
		stateKey: "toolPaths",
		actionKey: "setToolPaths",
		fields: ["pythonPath", "ffmpegPath", "ffprobePath"],
	},
];

export const appFormFieldIds = [
	"projectName",
	"projectId",
	"outputPath",
	"inputVideoPath",
	"punchlineText",
	"glossaryLabel",
	"glossaryPatterns",
	"glossaryDescription",
	...storeFieldGroups.flatMap((group) => group.fields),
] as const;

function storeFieldGroup(id: string) {
	return storeFieldGroups.find((group) => group.fields.includes(id));
}

function coerceStoreFieldValue(group: StoreFieldGroup, id: string, value: any) {
	if (group.booleanFields?.includes(id)) {
		return value === true || value === "true";
	}
	return value === null || value === undefined ? "" : String(value);
}

export function readAppFormField(id: string): FormFieldResult {
	const appState = getAppState();
	if (id === "projectName") {
		return { found: true, value: appState.projectDraft.name };
	}
	if (id === "projectId") {
		return { found: true, value: appState.projectDraft.id };
	}
	if (id === "outputPath") {
		return { found: true, value: appState.outputPath };
	}
	if (id === "inputVideoPath") {
		return { found: true, value: appState.inputVideoPath };
	}
	if (id === "punchlineText") {
		return { found: true, value: appState.punchlineText };
	}
	if (id === "glossaryLabel" || id === "glossaryPatterns" || id === "glossaryDescription") {
		const draft = appState.glossaryDraft;
		const value =
			id === "glossaryDescription" ? draft.description : id === "glossaryPatterns" ? draft.patterns : draft.label;
		return { found: true, value };
	}
	const group = storeFieldGroup(id);
	if (!group) {
		return { found: false };
	}
	const source = appState[group.stateKey] as Record<string, string | boolean>;
	return { found: true, value: source[id] };
}

export function writeAppFormField(id: string, value: any) {
	const appState = getAppState();
	if (value === undefined) {
		return readAppFormField(id).found;
	}
	if (id === "projectName") {
		appState.setProjectDraft({ name: value === null ? "" : String(value) });
		return true;
	}
	if (id === "projectId") {
		appState.setProjectDraft({ id: value === null ? "" : String(value) });
		return true;
	}
	if (id === "outputPath") {
		appState.setPathPreviews({ outputPath: value === null ? "" : String(value).trim() });
		return true;
	}
	if (id === "inputVideoPath") {
		appState.setPathPreviews({ inputVideoPath: value === null ? "" : String(value) });
		return true;
	}
	if (id === "punchlineText") {
		appState.setPunchlineText(value === null ? "" : String(value));
		return true;
	}
	if (id === "glossaryLabel" || id === "glossaryPatterns" || id === "glossaryDescription") {
		appState.setGlossaryDraft({
			[id === "glossaryDescription" ? "description" : id === "glossaryPatterns" ? "patterns" : "label"]:
				value === null ? "" : String(value),
		});
		return true;
	}
	const group = storeFieldGroup(id);
	if (!group) {
		return false;
	}
	const setter = appState[group.actionKey] as (patch: Record<string, string | boolean>) => void;
	setter({ [id]: coerceStoreFieldValue(group, id, value) });
	return true;
}
