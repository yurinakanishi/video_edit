import { create } from "zustand";
import { initialLanguage } from "../state.js";
import type {
	AnalysisResult,
	CodexModel,
	GlossaryTerm,
	Locale,
	MaterialAnalysisStatus,
	MediaManifest,
	ProjectInfo,
	ProjectListEntry,
} from "../types.js";

export type WorkflowSection = "assets" | "edit" | "style" | "workflow" | "run";
export type SubtitleMode = "full" | "punchline" | "none";

export type AppFiles = {
	masterVideo: string;
	rightCloseVideo: string;
	leftCloseVideo: string;
	referenceVideo: string;
	externalAudio: string;
	logo: string;
	stillImages: string[];
};

export type AppRunFlags = {
	appLocked: boolean;
	ingestRunning: boolean;
	directRunRunning: boolean;
	codexTurnRunning: boolean;
	codexInterruptRequested: boolean;
};

export type AppStatus = {
	statusText: string;
	statusKind: string;
};

export type RunChecklistItem = {
	text: string;
	kind: "error" | "warn" | "ok";
};

export type ConfirmDialogState = {
	open: boolean;
	title: string;
	message: string;
	detail: string;
	confirmLabel: string;
	cancelLabel: string;
};

export type GlossaryDraft = {
	label: string;
	patterns: string;
	description: string;
};

export type ProjectDraft = {
	name: string;
	id: string;
	root: string;
	sourceRoot: string;
	outputRoot: string;
};

export type WorkflowSettings = {
	editPreset: string;
	workflowAction: string;
	renderScript: string;
	previewDuration: string;
};

export type RenderSettings = {
	multicamMode: string;
	audioSource: string;
	audioDenoise: boolean;
	audioDenoiseStrength: string;
	audioMastering: boolean;
	encoderPreset: string;
	renderCrf: string;
	colorMatchCameras: boolean;
	globalVideoZoom: string;
	usePersonEditPlans: boolean;
	useTranscriptComparisonSync: boolean;
	naturalDialogueCuts: boolean;
	previewStart: string;
	shortenSilence: boolean;
	minSilence: string;
	keepSilence: string;
	silenceNoise: string;
	keepUncut: boolean;
};

export type MusicSettings = {
	musicEnabled: boolean;
	musicScope: string;
	musicRangeSource: string;
	musicPrompt: string;
	musicVolume: string;
	musicRangesText: string;
};

export type OmissionCardSettings = {
	omissionCardEnabled: boolean;
	omissionCardDuration: string;
	omissionCardLabel: string;
	omissionCardText: string;
	omissionCardRangesText: string;
};

export type StyleSettings = {
	subtitleSize: string;
	highlightColor: string;
	boxOpacity: string;
	titleSize: string;
	logoHeight: string;
	termExplanations: boolean;
};

export type AnalysisSettings = {
	transcribeModel: string;
	transcribeLanguage: string;
	transcribeBeamSize: string;
	transcribeTemperature: string;
	transcribePromptTerms: string;
	transcribeNormalizeAudio: boolean;
	transcribeFilterLowConfidence: boolean;
	conditionOnPreviousText: boolean;
	stillTime: string;
	personFpsSample: string;
	personModel: string;
	personConfidence: string;
	personMaxSeconds: string;
	personLimit: string;
	personNoMulticamRoot: boolean;
};

export type ThumbnailSettings = {
	thumbnailTime: string;
	thumbnailTitle: string;
	thumbnailSubtitle: string;
	thumbnailCandidateCount: string;
	thumbnailMode: string;
	thumbnailMainColor: string;
	thumbnailCandidateTimes: string;
	thumbnailDebugFaces: boolean;
};

export type SubtitleReviewSettings = {
	subtitleReviewMaxDuration: string;
	subtitleReviewMaxCharsPerSecond: string;
	subtitleSuspiciousPatterns: string;
	subtitleReviewExtractClips: boolean;
	subtitleReviewTranscribeClips: boolean;
	subtitleCorrectionsText: string;
};

export type SubtitleSpeakerSettings = {
	subtitleInterviewerRanges: string;
	subtitleInterviewerPatterns: string;
	subtitleManualRoles: string;
	subtitleMouthMotionDiagnostics: boolean;
};

export type ToolPaths = {
	pythonPath: string;
	ffmpegPath: string;
	ffprobePath: string;
};

export type AppState = AppRunFlags &
	AppStatus & {
		env: any | null;
		project: ProjectInfo | null;
		projectDraft: ProjectDraft;
		workflowSettings: WorkflowSettings;
		renderSettings: RenderSettings;
		musicSettings: MusicSettings;
		omissionCardSettings: OmissionCardSettings;
		styleSettings: StyleSettings;
		analysisSettings: AnalysisSettings;
		thumbnailSettings: ThumbnailSettings;
		subtitleReviewSettings: SubtitleReviewSettings;
		subtitleSpeakerSettings: SubtitleSpeakerSettings;
		toolPaths: ToolPaths;
		projectStatePath: string;
		projectStateRevision: number;
		projectStateApplying: boolean;
		projectStatePersistTimer: number;
		projectList: ProjectListEntry[];
		projectListLoading: boolean;
		mediaManifest: MediaManifest | null;
		mediaDirectory: string;
		materialPaths: string[];
		materialSourcePreviews: any[];
		materialSourcePreviewLoading: boolean;
		materialSourcePreviewRequestId: number;
		materialAnalysisCancelable: boolean;
		materialAnalysisCancelRequested: boolean;
		fullAnalysisRunning: boolean;
		ingestProgress: {
			progress: number;
			message: string;
			path: string;
			current: number;
			total: number;
		};
		runningAction: string;
		directRunLabel: string;
		lastWorkflowProgressLog: number;
		lastWorkflowStage: string;
		appBusyTitle: string;
		appBusyMessage: string;
		languageMenuOpen: boolean;
		projectDialogOpen: boolean;
		projectDialogName: string;
		confirmDialog: ConfirmDialogState;
		runChecklist: RunChecklistItem[];
		eventLogLines: string[];
		commandPreviewText: string;
		promptPreviewText: string;
		punchlineText: string;
		analysisResults: AnalysisResult[];
		materialAnalysisStatus: Record<string, MaterialAnalysisStatus>;
		analysisTitleText: string;
		files: AppFiles;
		subtitleMode: SubtitleMode;
		syncReport: any | null;
		glossaryTerms: GlossaryTerm[];
		glossaryDraft: GlossaryDraft;
		outputPreview: any | null;
		outputPreviewKind: string;
		outputPreviewLoading: boolean;
		inputVideoPath: string;
		outputPath: string;
		filePreviews: Record<string, any>;
		codexModels: CodexModel[];
		codexModelsLoading: boolean;
		codexModel: string;
		codexModelStatusKey: string;
		codexModelStatusValues: Record<string, string | number>;
		activeSection: WorkflowSection;
		language: Locale;
	};

export type AppActions = {
	setActiveSection: (section: string) => void;
	setLanguage: (language: Locale) => void;
	setSubtitleMode: (mode: string) => void;
	setStatus: (status: Partial<AppStatus>) => void;
	setRunFlags: (flags: Partial<AppRunFlags & Pick<AppState, "runningAction" | "directRunLabel">>) => void;
	setProject: (
		project: ProjectInfo | null,
		metadata?: Partial<Pick<AppState, "projectStatePath" | "projectStateRevision">>,
	) => void;
	setProjectDraft: (draft: Partial<ProjectDraft>) => void;
	setWorkflowSettings: (settings: Partial<WorkflowSettings>) => void;
	setRenderSettings: (settings: Partial<RenderSettings>) => void;
	setMusicSettings: (settings: Partial<MusicSettings>) => void;
	setOmissionCardSettings: (settings: Partial<OmissionCardSettings>) => void;
	setStyleSettings: (settings: Partial<StyleSettings>) => void;
	setAnalysisSettings: (settings: Partial<AnalysisSettings>) => void;
	setThumbnailSettings: (settings: Partial<ThumbnailSettings>) => void;
	setSubtitleReviewSettings: (settings: Partial<SubtitleReviewSettings>) => void;
	setSubtitleSpeakerSettings: (settings: Partial<SubtitleSpeakerSettings>) => void;
	setToolPaths: (paths: Partial<ToolPaths>) => void;
	setFiles: (files: Partial<AppFiles>) => void;
	setAnalysisResults: (results: AnalysisResult[]) => void;
	setMaterialAnalysisStatus: (status: Record<string, MaterialAnalysisStatus>) => void;
	setLanguageMenuOpen: (open: boolean) => void;
	setProjectDialogOpen: (open: boolean) => void;
	setProjectDialogName: (name: string) => void;
	setConfirmDialog: (dialog: Partial<ConfirmDialogState>) => void;
	setRunChecklist: (items: RunChecklistItem[]) => void;
	appendEventLogLine: (line: string) => void;
	setRunPreviewText: (preview: Partial<Pick<AppState, "commandPreviewText" | "promptPreviewText">>) => void;
	setPunchlineText: (text: string) => void;
	setGlossaryDraft: (draft: Partial<GlossaryDraft>) => void;
	setPathPreviews: (paths: Partial<Pick<AppState, "inputVideoPath" | "outputPath">>) => void;
	setMediaManifest: (
		manifest: MediaManifest | null,
		metadata?: Partial<Pick<AppState, "mediaDirectory" | "materialPaths" | "materialSourcePreviews">>,
	) => void;
	patchState: (patch: Partial<AppState>) => void;
};

export type AppStore = AppState & AppActions;

const defaultFiles = (): AppFiles => ({
	masterVideo: "",
	rightCloseVideo: "",
	leftCloseVideo: "",
	referenceVideo: "",
	externalAudio: "",
	logo: "",
	stillImages: [],
});

const projectDraftFromProject = (project: ProjectInfo | null): ProjectDraft => ({
	name: project?.name || "",
	id: project?.id || "",
	root: project?.root || "",
	sourceRoot: project?.sourceRoot || "",
	outputRoot: project?.outputRoot || "",
});

const defaultWorkflowSettings = (): WorkflowSettings => ({
	editPreset: "new-interview",
	workflowAction: "render-selected",
	renderScript: "render_app_interview.py",
	previewDuration: "60",
});

const defaultRenderSettings = (): RenderSettings => ({
	multicamMode: "speaker-aware",
	audioSource: "external-if-selected",
	audioDenoise: true,
	audioDenoiseStrength: "10",
	audioMastering: true,
	encoderPreset: "veryfast",
	renderCrf: "18",
	colorMatchCameras: true,
	globalVideoZoom: "1.2",
	usePersonEditPlans: true,
	useTranscriptComparisonSync: true,
	naturalDialogueCuts: false,
	previewStart: "0",
	shortenSilence: true,
	minSilence: "3.0",
	keepSilence: "2.0",
	silenceNoise: "-30dB",
	keepUncut: false,
});

const defaultMusicSettings = (): MusicSettings => ({
	musicEnabled: false,
	musicScope: "full",
	musicRangeSource: "auto",
	musicPrompt: "",
	musicVolume: "14",
	musicRangesText: "",
});

const defaultOmissionCardSettings = (): OmissionCardSettings => ({
	omissionCardEnabled: false,
	omissionCardDuration: "5",
	omissionCardLabel: "SUMMARY",
	omissionCardText: "",
	omissionCardRangesText: "",
});

const defaultStyleSettings = (): StyleSettings => ({
	subtitleSize: "80",
	highlightColor: "#ae48e0",
	boxOpacity: "73",
	titleSize: "48",
	logoHeight: "48",
	termExplanations: true,
});

const defaultAnalysisSettings = (): AnalysisSettings => ({
	transcribeModel: "large-v3",
	transcribeLanguage: "ja",
	transcribeBeamSize: "5",
	transcribeTemperature: "0",
	transcribePromptTerms: "",
	transcribeNormalizeAudio: true,
	transcribeFilterLowConfidence: true,
	conditionOnPreviousText: false,
	stillTime: "00:00:25",
	personFpsSample: "1",
	personModel: "yolov8n.pt",
	personConfidence: "0.35",
	personMaxSeconds: "",
	personLimit: "",
	personNoMulticamRoot: false,
});

const defaultThumbnailSettings = (): ThumbnailSettings => ({
	thumbnailTime: "00:00:25",
	thumbnailTitle: "",
	thumbnailSubtitle: "",
	thumbnailCandidateCount: "6",
	thumbnailMode: "standard",
	thumbnailMainColor: "yellow",
	thumbnailCandidateTimes: "",
	thumbnailDebugFaces: false,
});

const defaultSubtitleReviewSettings = (): SubtitleReviewSettings => ({
	subtitleReviewMaxDuration: "8",
	subtitleReviewMaxCharsPerSecond: "18",
	subtitleSuspiciousPatterns: "",
	subtitleReviewExtractClips: false,
	subtitleReviewTranscribeClips: false,
	subtitleCorrectionsText: "",
});

const defaultSubtitleSpeakerSettings = (): SubtitleSpeakerSettings => ({
	subtitleInterviewerRanges: "",
	subtitleInterviewerPatterns: "",
	subtitleManualRoles: "",
	subtitleMouthMotionDiagnostics: false,
});

const defaultToolPaths = (): ToolPaths => ({
	pythonPath: "",
	ffmpegPath: "",
	ffprobePath: "",
});

export function normalizeWorkflowSection(section: string | undefined | null): WorkflowSection {
	return ["assets", "edit", "style", "workflow", "run"].includes(String(section))
		? (section as WorkflowSection)
		: "assets";
}

export function normalizeSubtitleMode(mode: string | undefined | null): SubtitleMode {
	if (mode === "punchline" || mode === "none") {
		return mode;
	}
	return "full";
}

export const useAppStore = create<AppStore>((set) => ({
	env: null,
	project: null,
	projectDraft: projectDraftFromProject(null),
	workflowSettings: defaultWorkflowSettings(),
	renderSettings: defaultRenderSettings(),
	musicSettings: defaultMusicSettings(),
	omissionCardSettings: defaultOmissionCardSettings(),
	styleSettings: defaultStyleSettings(),
	analysisSettings: defaultAnalysisSettings(),
	thumbnailSettings: defaultThumbnailSettings(),
	subtitleReviewSettings: defaultSubtitleReviewSettings(),
	subtitleSpeakerSettings: defaultSubtitleSpeakerSettings(),
	toolPaths: defaultToolPaths(),
	projectStatePath: "",
	projectStateRevision: 0,
	projectStateApplying: false,
	projectStatePersistTimer: 0,
	projectList: [],
	projectListLoading: false,
	mediaManifest: null,
	mediaDirectory: "",
	materialPaths: [],
	materialSourcePreviews: [],
	materialSourcePreviewLoading: false,
	materialSourcePreviewRequestId: 0,
	materialAnalysisCancelable: false,
	materialAnalysisCancelRequested: false,
	fullAnalysisRunning: false,
	ingestRunning: false,
	ingestProgress: {
		progress: 0,
		message: "",
		path: "",
		current: 0,
		total: 0,
	},
	runningAction: "",
	directRunLabel: "",
	lastWorkflowProgressLog: 0,
	lastWorkflowStage: "",
	appBusyTitle: "",
	appBusyMessage: "",
	languageMenuOpen: false,
	projectDialogOpen: false,
	projectDialogName: "",
	confirmDialog: {
		open: false,
		title: "",
		message: "",
		detail: "",
		confirmLabel: "",
		cancelLabel: "",
	},
	runChecklist: [],
	eventLogLines: [],
	commandPreviewText: "",
	promptPreviewText: "",
	punchlineText: "",
	appLocked: false,
	analysisResults: [],
	materialAnalysisStatus: {},
	analysisTitleText: "",
	files: defaultFiles(),
	subtitleMode: "full",
	syncReport: null,
	glossaryTerms: [],
	glossaryDraft: {
		label: "",
		patterns: "",
		description: "",
	},
	outputPreview: null,
	outputPreviewKind: "",
	outputPreviewLoading: false,
	inputVideoPath: "",
	outputPath: "",
	filePreviews: {},
	codexModels: [],
	codexModelsLoading: false,
	codexModel: "",
	codexModelStatusKey: "codex.modelNotLoaded",
	codexModelStatusValues: {},
	activeSection: "assets",
	language: initialLanguage(),
	statusText: "AI idle",
	statusKind: "idle",
	directRunRunning: false,
	codexTurnRunning: false,
	codexInterruptRequested: false,
	setActiveSection: (section) => set({ activeSection: normalizeWorkflowSection(section) }),
	setLanguage: (language) => set({ language }),
	setSubtitleMode: (mode) => set({ subtitleMode: normalizeSubtitleMode(mode) }),
	setStatus: (status) => set(status),
	setRunFlags: (flags) => set(flags),
	setProject: (project, metadata = {}) => set({ project, projectDraft: projectDraftFromProject(project), ...metadata }),
	setProjectDraft: (draft) => set((current) => ({ projectDraft: { ...current.projectDraft, ...draft } })),
	setWorkflowSettings: (settings) =>
		set((current) => ({ workflowSettings: { ...current.workflowSettings, ...settings } })),
	setRenderSettings: (settings) => set((current) => ({ renderSettings: { ...current.renderSettings, ...settings } })),
	setMusicSettings: (settings) => set((current) => ({ musicSettings: { ...current.musicSettings, ...settings } })),
	setOmissionCardSettings: (settings) =>
		set((current) => ({ omissionCardSettings: { ...current.omissionCardSettings, ...settings } })),
	setStyleSettings: (settings) => set((current) => ({ styleSettings: { ...current.styleSettings, ...settings } })),
	setAnalysisSettings: (settings) =>
		set((current) => ({ analysisSettings: { ...current.analysisSettings, ...settings } })),
	setThumbnailSettings: (settings) =>
		set((current) => ({ thumbnailSettings: { ...current.thumbnailSettings, ...settings } })),
	setSubtitleReviewSettings: (settings) =>
		set((current) => ({ subtitleReviewSettings: { ...current.subtitleReviewSettings, ...settings } })),
	setSubtitleSpeakerSettings: (settings) =>
		set((current) => ({ subtitleSpeakerSettings: { ...current.subtitleSpeakerSettings, ...settings } })),
	setToolPaths: (paths) => set((current) => ({ toolPaths: { ...current.toolPaths, ...paths } })),
	setFiles: (files) => set((current) => ({ files: { ...current.files, ...files } })),
	setAnalysisResults: (analysisResults) => set({ analysisResults }),
	setMaterialAnalysisStatus: (materialAnalysisStatus) => set({ materialAnalysisStatus }),
	setLanguageMenuOpen: (languageMenuOpen) => set({ languageMenuOpen }),
	setProjectDialogOpen: (projectDialogOpen) => set({ projectDialogOpen }),
	setProjectDialogName: (projectDialogName) => set({ projectDialogName }),
	setConfirmDialog: (dialog) => set((current) => ({ confirmDialog: { ...current.confirmDialog, ...dialog } })),
	setRunChecklist: (runChecklist) => set({ runChecklist }),
	appendEventLogLine: (line) =>
		set((current) => ({
			eventLogLines: [...current.eventLogLines, line].slice(-500),
		})),
	setRunPreviewText: (preview) => set(preview),
	setPunchlineText: (punchlineText) => set({ punchlineText }),
	setGlossaryDraft: (draft) => set((current) => ({ glossaryDraft: { ...current.glossaryDraft, ...draft } })),
	setPathPreviews: (paths) => set(paths),
	setMediaManifest: (mediaManifest, metadata = {}) => set({ mediaManifest, ...metadata }),
	patchState: (patch) => set(patch),
}));

export function getAppState() {
	return useAppStore.getState();
}

export function patchAppState(patch: Partial<AppState>) {
	useAppStore.getState().patchState(patch);
}
