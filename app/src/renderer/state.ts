import type {
	AnalysisResult,
	CodexModel,
	GlossaryTerm,
	Locale,
	MaterialAnalysisStatus,
	MediaManifest,
	ProjectInfo,
	ProjectListEntry,
} from "./types.js";

export const LANGUAGE_STORAGE_KEY = "video-edit-app-language-v1";

export function normalizeLanguage(value: any): Locale {
	return value === "en" ? "en" : "ja";
}

export function initialLanguage(): Locale {
	try {
		const saved = localStorage.getItem(LANGUAGE_STORAGE_KEY);
		if (saved) {
			return normalizeLanguage(saved);
		}
	} catch {
		// localStorage can be unavailable in unusual renderer contexts.
	}
	return navigator.language?.toLowerCase().startsWith("ja") ? "ja" : "en";
}

export const state: any = {
	env: null,
	project: null as ProjectInfo | null,
	projectStatePath: "",
	projectStateRevision: 0,
	projectStateApplying: false,
	projectStatePersistTimer: 0,
	projectList: [] as ProjectListEntry[],
	projectListLoading: false,
	mediaManifest: null as MediaManifest | null,
	mediaDirectory: "",
	materialPaths: [] as string[],
	materialSourcePreviews: [] as any[],
	materialSourcePreviewLoading: false,
	materialSourcePreviewRequestId: 0,
	ingestRunning: false,
	materialAnalysisCancelable: false,
	materialAnalysisCancelRequested: false,
	fullAnalysisRunning: false,
	directRunRunning: false,
	codexTurnRunning: false,
	codexInterruptRequested: false,
	ingestProgress: {
		progress: 0,
		message: "",
		path: "",
		current: 0,
		total: 0,
	},
	runningAction: "",
	lastWorkflowProgressLog: 0,
	lastWorkflowStage: "",
	appLocked: false,
	appBusyTitle: "",
	appBusyMessage: "",
	analysisResults: [] as AnalysisResult[],
	materialAnalysisStatus: {} as Record<string, MaterialAnalysisStatus>,
	analysisTitleText: "",
	files: {
		masterVideo: "",
		rightCloseVideo: "",
		leftCloseVideo: "",
		referenceVideo: "",
		externalAudio: "",
		logo: "",
		stillImages: [] as string[],
	},
	subtitleMode: "full",
	syncReport: null,
	glossaryTerms: [],
	outputPreview: null,
	outputPreviewKind: "",
	outputPreviewLoading: false,
	filePreviews: {} as Record<string, any>,
	codexModels: [] as CodexModel[],
	codexModel: "",
	codexModelStatusKey: "codex.modelNotLoaded",
	codexModelStatusValues: {} as Record<string, string | number>,
	activeSection: "assets",
	language: initialLanguage(),
	statusText: "AI idle",
	statusKind: "idle",
};

export const defaultPunchlines = "";

export const fileFilterSpecs = {
	masterVideo: [{ nameKey: "filter.video", extensions: ["mp4", "mov", "m4v"] }],
	rightCloseVideo: [{ nameKey: "filter.video", extensions: ["mp4", "mov", "m4v"] }],
	leftCloseVideo: [{ nameKey: "filter.video", extensions: ["mp4", "mov", "m4v"] }],
	referenceVideo: [{ nameKey: "filter.video", extensions: ["mp4", "mov", "m4v"] }],
	externalAudio: [{ nameKey: "filter.audioOrVideo", extensions: ["wav", "mp3", "aac", "m4a", "mp4", "mov"] }],
	logo: [{ nameKey: "filter.image", extensions: ["png", "jpg", "jpeg", "webp"] }],
	stillImages: [{ nameKey: "filter.stillImages", extensions: ["png", "jpg", "jpeg", "webp"] }],
};

export const STORAGE_KEY = "video-edit-app-state-v1";
export const DEFAULT_FFMPEG_EXE = "C:\\ProgramData\\chocolatey\\bin\\ffmpeg.exe";
export const DEFAULT_FFPROBE_EXE = "C:\\ProgramData\\chocolatey\\bin\\ffprobe.exe";
export const defaultGlossaryTerms: GlossaryTerm[] = [];
