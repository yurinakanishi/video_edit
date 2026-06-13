import { createAnalysisStateController } from "./analysis-state.js";
import { editApp } from "./api.js";
import { createAppSessionController } from "./app-session.js";
import { syncAppStoreFromLegacyState } from "./app-store-sync.js";
import { createAssetFileController } from "./asset-files.js";
import { codexErrorMessage } from "./codex-error.js";
import { createCodexModelController } from "./codex-models.js";
import { createConfirmDialogController } from "./confirm-dialog.js";
import { createGlossaryStateController } from "./glossary-state.js";
import { applyTranslations } from "./i18n.js";
import { log } from "./log.js";
import { createMaterialAnalysisController } from "./material-analysis.js";
import { createMaterialManifestController } from "./material-manifest.js";
import { createMaterialSourceController } from "./material-sources.js";
import { outputPathValue, setInputVideoPathValue, setOutputPathValue } from "./media-state.js";
import { loadOutputPreview, outputPreviewTarget, renderOutputPreview } from "./preview.js";
import { createProjectController } from "./project-controller.js";
import { createProjectStateController } from "./project-state.js";
import { bindRendererEvents } from "./renderer-events.js";
import { bindRendererIpcEvents } from "./renderer-ipc.js";
import { createRunStateController } from "./run-state.js";
import { state } from "./state.js";
import { getAppState, patchAppState } from "./store/app-store.js";
import { syncReportPath } from "./sync-report.js";
import type { MediaManifest, ProjectInfo } from "./types.js";
import { createWorkflowController } from "./workflow.js";

let workflowController: ReturnType<typeof createWorkflowController>;
let saveCurrentState = () => {};
let persistCurrentAnalysisState = () => {};
let schedulePersistCurrentProjectState = () => {};
let currentDirectRunLabel = (_action: string) => "";
let currentFfprobeExe = () => "";
let currentRefreshPrompt = () => {};
let currentRenderMediaManifest = () => {};
let currentLoadAnalysisStateFile = async (_project?: ProjectInfo | null) => false;
let currentLoadProjectStateFile = async (_project?: ProjectInfo | null) => false;
let currentPersistProjectStateFileNow = async () => {};
let currentRefreshSyncReport = async () => {};
let currentRefreshTextOverlayFromAnalysis = async (_manifest?: MediaManifest | null) => null;
let currentRestoreAnalysisResultsFromOutputs = async (_manifest?: MediaManifest | null) => null;
let currentRestoreProgressFromOutputs = async (_options?: any) => null;
let currentRenderSyncReport = () => {};
let currentRefreshCommand = () => {};
let currentUpdateRunSummary = () => {};

const codexModelController = createCodexModelController({
	saveState: () => saveCurrentState(),
});

const {
	loadCodexModels,
	renderCodexModelOptions,
	renderCodexModelStatus,
	selectedCodexModelForRun,
	selectedCodexReasoningEffort,
} = codexModelController;

const runStateController = createRunStateController({
	directRunLabel: (action) => currentDirectRunLabel(action),
	schedulePersistProjectStateFile: () => schedulePersistCurrentProjectState(),
	syncMaterialStore: () => currentRenderMediaManifest(),
});

const {
	progressPercent,
	setAppLocked,
	setCodexTurnRunning,
	setDirectRunRunning,
	setIngestProgress,
	setIngestRunning,
	setStatus,
	updateCodexRunControls,
} = runStateController;

const analysisStateController = createAnalysisStateController({
	persistAnalysisStateFile: () => persistCurrentAnalysisState(),
	saveState: () => saveCurrentState(),
});

const {
	notifyAnalysisComplete,
	renderAnalysisResults,
	removeMaterialAnalysisStatus,
	setAnalysisResult,
	setAnalysisResults,
	setAnalysisTitleText,
	setMaterialAnalysisRunning,
	setMaterialAnalysisStatusMap,
} = analysisStateController;

const glossaryStateController = createGlossaryStateController({
	refreshPrompt: () => currentRefreshPrompt(),
});

const { glossaryTerms, normalizeGlossaryTerm, renderGlossaryList, setGlossaryTerms, termsFromGlossaryManifest } =
	glossaryStateController;

const assetFileController = createAssetFileController({
	refreshPrompt: () => currentRefreshPrompt(),
	renderMediaManifest: () => currentRenderMediaManifest(),
});

const {
	clearSelectedAssets,
	loadFilePreviews,
	loadOutputTargetPreview,
	loadWorkflowMediaPreviews,
	renderFileSlots,
	renderOutputTargetPreview,
	renderStillImageList,
	renderWorkflowMediaPreviews,
	setFile,
	setStillImages,
} = assetFileController;

const materialSourceController = createMaterialSourceController({
	ffprobeExe: () => currentFfprobeExe(),
	refreshPrompt: () => currentRefreshPrompt(),
	renderFileSlots,
	renderMediaManifest: () => currentRenderMediaManifest(),
	renderStillImageList,
	renderWorkflowMediaPreviews,
	resetAnalysisForMaterialChange: (path) => resetAnalysisForMaterialChange(path),
	setIngestRunning,
});

const { loadMaterialSourcePreviews, materialSourceLabel, setMaterialSources, setMaterialSourcesFromPreviews } =
	materialSourceController;

const { closeConfirmDialog, confirmAction } = createConfirmDialogController();

const materialManifestController = createMaterialManifestController({
	confirmAction,
	loadFilePreviews,
	refreshPrompt: () => currentRefreshPrompt(),
	refreshMaterialAnalysisStatus,
	removeMaterialAnalysisStatus,
	saveState: () => saveCurrentState(),
	setFile,
	setMaterialSources: (paths) => setMaterialSources(paths),
	setMaterialSourcesFromPreviews,
	setStillImages,
});

const { applyManifestSelections, rebuildMediaManifestGroups, renderMediaManifest, setMediaManifest } =
	materialManifestController;
currentRenderMediaManifest = renderMediaManifest;

const { restoreDefaultTextDrafts, setActiveSection, setLanguage, setSubtitleMode, setWaitingAnalysisProgress } =
	createAppSessionController({
		directRunLabel: (action) => currentDirectRunLabel(action),
		refreshCommand: () => currentRefreshCommand(),
		renderAnalysisResults,
		renderCodexModelOptions,
		renderCodexModelStatus,
		renderFileSlots,
		renderGlossaryList,
		renderMediaManifest,
		renderOutputPreview,
		renderOutputTargetPreview,
		renderProjectDialogList: () => renderProjectDialogList(),
		renderStillImageList,
		renderSyncReport: () => currentRenderSyncReport(),
		renderWorkflowMediaPreviews,
		setDirectRunRunning,
		setStatus,
		updateRunSummary: () => currentUpdateRunSummary(),
	});

const projectController = createProjectController({
	clearSelectedAssets,
	loadAnalysisStateFile: (project) => currentLoadAnalysisStateFile(project),
	loadOutputTargetPreview,
	loadProjectStateFile: (project) => currentLoadProjectStateFile(project),
	loadWorkflowMediaPreviews,
	persistProjectStateFileNow: () => currentPersistProjectStateFileNow(),
	refreshPrompt: () => currentRefreshPrompt(),
	refreshMaterialAnalysisStatus,
	refreshSyncReport: () => currentRefreshSyncReport(),
	refreshTextOverlayFromAnalysis: (manifest) => currentRefreshTextOverlayFromAnalysis(manifest),
	restoreAnalysisResultsFromOutputs: (manifest) => currentRestoreAnalysisResultsFromOutputs(manifest),
	restoreProgressFromOutputs: (options) => currentRestoreProgressFromOutputs(options),
	setAnalysisResults,
	setAnalysisTitleText,
	setFile,
	setIngestProgress,
	setMediaManifest,
	setStillImages,
});

const {
	changeProject,
	copyAssetsToProject,
	createProjectFromDialog,
	createProjectFromForm,
	openProject,
	renderProjectDialogList,
	restoreStartupProjectFromDisk,
	setDefaultProjectOutput,
	setProject,
	setProjectDialogOpen,
} = projectController;

const {
	saveState,
	loadState,
	schedulePersistProjectStateFile,
	persistProjectStateFileNow,
	loadProjectStateFile,
	persistAnalysisStateFile,
	loadAnalysisStateFile,
} = createProjectStateController({
	setProject,
	applyManifestSelections,
	renderMediaManifest,
	loadFilePreviews,
	setIngestProgress,
	materialSourceLabel,
	loadMaterialSourcePreviews,
	setStillImages,
	setFile,
	renderCodexModelOptions,
	loadWorkflowMediaPreviews,
	loadOutputTargetPreview,
	setAnalysisResults,
	renderGlossaryList,
	buildAppConfig: () => workflowController.buildAppConfig(),
	setAnalysisTitleText,
	rebuildMediaManifestGroups,
	setActiveSection,
	setLanguage,
	setSubtitleMode,
	renderFileSlots,
	renderStillImageList,
	updateRunSummary: () => workflowController.updateRunSummary(),
	refreshCommand: () => workflowController.refreshCommand(),
	refreshPrompt: () => workflowController.refreshPrompt(),
});

saveCurrentState = saveState;
persistCurrentAnalysisState = persistAnalysisStateFile;
schedulePersistCurrentProjectState = schedulePersistProjectStateFile;
currentLoadAnalysisStateFile = loadAnalysisStateFile;
currentLoadProjectStateFile = loadProjectStateFile;
currentPersistProjectStateFileNow = persistProjectStateFileNow;

workflowController = createWorkflowController({
	createProjectFromForm,
	copyAssetsToProject,
	setStatus,
	syncReportPath,
	termsFromGlossaryManifest,
	normalizeGlossaryTerm,
	setGlossaryTerms,
	setAnalysisTitleText,
	progressPercent,
	renderAnalysisResults,
	setAnalysisResults,
	setIngestProgress,
	setAppLocked,
	setDirectRunRunning,
	setMediaManifest,
	notifyAnalysisComplete,
	refreshMaterialAnalysisStatus,
	setCodexTurnRunning,
	updateCodexRunControls,
	codexErrorMessage,
	selectedCodexModelForRun,
	selectedCodexReasoningEffort,
	persistProjectStateFileNow,
	saveState,
	glossaryTerms,
});

const {
	renderSyncReport,
	refreshSyncReport,
	refreshTextOverlayFromAnalysis,
	refreshAnalysisTitleFromAnalysis,
	ffprobeExe,
	personEditPlansDir,
	referenceEditProfilePath,
	transcriptComparisonOutputPath,
	transcriptManifestOutputPath,
	blockingMetricsOutputPath,
	restoreAnalysisResultsFromOutputs,
	restoreProgressFromOutputs,
	buildActionCommand,
	hasSyncTargets,
	compactOutput,
	directRunLabel,
	handleWorkflowProgress,
	refreshCommand,
	updateRunSummary,
	buildAppConfig,
	refreshPrompt,
	runSimpleTranscription,
	sendSimpleEditRequest,
	handleNotification,
} = workflowController;
currentDirectRunLabel = directRunLabel;
currentFfprobeExe = ffprobeExe;
currentRefreshPrompt = refreshPrompt;
currentRefreshSyncReport = refreshSyncReport;
currentRefreshTextOverlayFromAnalysis = refreshTextOverlayFromAnalysis;
currentRestoreAnalysisResultsFromOutputs = restoreAnalysisResultsFromOutputs;
currentRestoreProgressFromOutputs = restoreProgressFromOutputs;
currentRenderSyncReport = renderSyncReport;
currentRefreshCommand = refreshCommand;
currentUpdateRunSummary = updateRunSummary;

const materialAnalysisController = createMaterialAnalysisController({
	blockingMetricsOutputPath,
	buildActionCommand,
	buildAppConfig,
	compactOutput,
	createProjectFromForm,
	ffprobeExe,
	hasSyncTargets,
	notifyAnalysisComplete,
	personEditPlansDir,
	referenceEditProfilePath,
	refreshPrompt,
	refreshSyncReport,
	refreshTextOverlayFromAnalysis,
	refreshMaterialAnalysisStatus,
	renderAnalysisResults,
	setAnalysisResult,
	setAppLocked,
	setDefaultProjectOutput,
	setIngestProgress,
	setIngestRunning,
	setMaterialAnalysisRunning,
	setMaterialAnalysisStatusMap,
	setMaterialSources,
	setMediaManifest,
	setProject,
	setStatus,
	syncReportPath,
	transcriptComparisonOutputPath,
	transcriptManifestOutputPath,
});

const { cancelMaterialAnalysis } = materialAnalysisController;

function uniquePaths(paths: string[]) {
	return [
		...new Set(
			paths
				.map(String)
				.map((item) => item.trim())
				.filter(Boolean),
		),
	];
}

function selectedItemsLabel(paths: string[]) {
	return paths.length === 1 ? paths[0] : `${paths.length} selected item(s)`;
}

async function ingestSimpleMaterials(paths: string[]) {
	const selected = uniquePaths(paths);
	if (!selected.length) {
		return false;
	}
	if (state.ingestRunning || state.appLocked) {
		log("material import skipped", { reason: "another operation is running" });
		return false;
	}
	const sourceLabel = selectedItemsLabel(selected);
	state.fullAnalysisRunning = false;
	state.materialAnalysisCancelable = true;
	state.materialAnalysisCancelRequested = false;
	setAnalysisResults([], { persistFile: false });
	setAnalysisTitleText("");
	state.syncReport = null;
	renderSyncReport();
	setStatus("素材を保存しています", "busy");
	setIngestRunning(true);
	setAppLocked(true, "プロジェクトを作成し、素材を source ディレクトリへ保存しています");
	setIngestProgress({
		progress: 0,
		message: "素材の保存を開始しました",
		path: sourceLabel,
	});
	log("simple material import", { paths: selected });
	try {
		const result = await editApp.ingestDirectory({
			directory: selected.length === 1 ? selected[0] : "",
			paths: selected,
			tools: {
				ffprobe: ffprobeExe(),
			},
		});
		setProject(result.project);
		clearSelectedAssets();
		setAnalysisResults([], { persistFile: false });
		setMediaManifest(result.manifest);
		setDefaultProjectOutput(false);
		await refreshMaterialAnalysisStatus();
		refreshPrompt();
		setIngestProgress({
			progress: 1,
			message: "素材をプロジェクトへ保存しました",
			path: result.manifest?.manifestPath || sourceLabel,
		});
		setStatus("素材を保存しました", "ready");
		await persistProjectStateFileNow();
		return true;
	} catch (error) {
		setStatus("素材の保存に失敗しました", "idle");
		setIngestProgress({
			progress: 0,
			message: "素材の保存に失敗しました",
			path: sourceLabel,
		});
		log("simple material import failed", { message: error.message });
		return false;
	} finally {
		state.materialAnalysisCancelable = false;
		state.materialAnalysisCancelRequested = false;
		setIngestRunning(false);
		setAppLocked(false);
	}
}

async function pickSimpleMaterialDirectory() {
	const selected = await editApp.pickDirectory({ title: "素材フォルダを選択" });
	if (selected) {
		await ingestSimpleMaterials([selected]);
	}
}

async function pickSimpleMaterialFiles() {
	const selected = await editApp.pickFile({
		title: "素材ファイルを選択",
		filters: [
			{
				name: "Media and subtitles",
				extensions: [
					"mp4",
					"mov",
					"m4v",
					"mkv",
					"avi",
					"mts",
					"m2ts",
					"wav",
					"mp3",
					"aac",
					"m4a",
					"flac",
					"aiff",
					"aif",
					"png",
					"jpg",
					"jpeg",
					"webp",
					"srt",
					"ass",
					"vtt",
				],
			},
			{ name: "All files", extensions: ["*"] },
		],
		multi: true,
	});
	if (Array.isArray(selected)) {
		await ingestSimpleMaterials(selected);
	} else if (selected) {
		await ingestSimpleMaterials([selected]);
	}
}

async function addSimpleAudioFiles(paths: string[]) {
	const selected = uniquePaths(paths);
	if (!selected.length) {
		return false;
	}
	if (!state.project) {
		setStatus("先に素材を投入してプロジェクトを作成してください", "idle");
		log("audio import skipped", { reason: "project is required" });
		return false;
	}
	if (state.ingestRunning || state.appLocked) {
		log("audio import skipped", { reason: "another operation is running" });
		return false;
	}
	const sourceLabel = selectedItemsLabel(selected);
	state.materialAnalysisCancelable = true;
	state.materialAnalysisCancelRequested = false;
	setStatus("音声ファイルを追加しています", "busy");
	setIngestRunning(true);
	setAppLocked(true, "音声ファイルを source ディレクトリへ保存しています");
	setIngestProgress({
		progress: 0,
		message: "音声ファイルの保存を開始しました",
		path: sourceLabel,
	});
	log("simple audio import", { paths: selected, project: state.project.id });
	try {
		const result = await editApp.ingestDirectory({
			project: state.project,
			directory: selected.length === 1 ? selected[0] : "",
			paths: selected,
			append: true,
			tools: {
				ffprobe: ffprobeExe(),
			},
		});
		setProject(result.project);
		setMediaManifest(result.manifest);
		await refreshMaterialAnalysisStatus();
		refreshPrompt();
		setIngestProgress({
			progress: 1,
			message: "音声ファイルを追加しました",
			path: result.manifest?.manifestPath || sourceLabel,
		});
		setStatus("音声ファイルを追加しました", "ready");
		await persistProjectStateFileNow();
		return true;
	} catch (error) {
		setStatus("音声ファイルの追加に失敗しました", "idle");
		setIngestProgress({
			progress: 0,
			message: "音声ファイルの追加に失敗しました",
			path: sourceLabel,
		});
		log("simple audio import failed", { message: error.message });
		return false;
	} finally {
		state.materialAnalysisCancelable = false;
		state.materialAnalysisCancelRequested = false;
		setIngestRunning(false);
		setAppLocked(false);
	}
}

async function pickSimpleAudioFiles() {
	const selected = await editApp.pickFile({
		title: "音声ファイルを選択",
		filters: [
			{
				name: "Audio files",
				extensions: ["wav", "mp3", "aac", "m4a", "flac", "aiff", "aif", "mp4", "mov"],
			},
			{ name: "All files", extensions: ["*"] },
		],
		multi: true,
	});
	if (Array.isArray(selected)) {
		await addSimpleAudioFiles(selected);
	} else if (selected) {
		await addSimpleAudioFiles([selected]);
	}
}

function handleEditRequestChange(event: Event) {
	const instructionDraft = String((event as CustomEvent).detail?.instructionDraft || "");
	state.editRequest = {
		instructionDraft,
		instructionHistory: [...(state.editRequest?.instructionHistory || [])],
		requestedPreviewPath: state.editRequest?.requestedPreviewPath || "",
		requestedFinalPath: state.editRequest?.requestedFinalPath || "",
		lastPreviewPath: state.editRequest?.lastPreviewPath || "",
		lastFinalPath: state.editRequest?.lastFinalPath || "",
	};
	getAppState().setEditRequest(state.editRequest);
	refreshPrompt();
	schedulePersistCurrentProjectState();
	saveState();
}

function normalizeReviewSelection(value: any) {
	if (!value || typeof value !== "object") {
		return null;
	}
	const start = Number(value.start);
	const end = Number(value.end);
	if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) {
		return null;
	}
	return { start, end };
}

function handleReviewStateChange(event: Event) {
	const detail = (event as CustomEvent).detail || {};
	const patch: Record<string, any> = {};
	if ("previewVideoPath" in detail) {
		patch.previewVideoPath = String(detail.previewVideoPath || "");
	}
	if ("currentTime" in detail) {
		patch.currentTime = Math.max(0, Number(detail.currentTime) || 0);
	}
	if ("selectedRange" in detail) {
		patch.selectedRange = normalizeReviewSelection(detail.selectedRange);
	}
	if ("zoom" in detail) {
		patch.zoom = Math.max(1, Math.min(24, Number(detail.zoom) || 1));
	}
	if ("scrollStart" in detail) {
		patch.scrollStart = Math.max(0, Number(detail.scrollStart) || 0);
	}
	if ("reviewTimelinePath" in detail) {
		patch.reviewTimelinePath = String(detail.reviewTimelinePath || "");
	}
	state.review = {
		previewVideoPath: "",
		currentTime: 0,
		selectedRange: null,
		zoom: 1,
		scrollStart: 0,
		reviewTimelinePath: "",
		...(state.review || {}),
		...patch,
	};
	getAppState().setReview(state.review);
	refreshPrompt();
	schedulePersistCurrentProjectState();
	saveState();
}

function reviewPreviewCandidate() {
	return (
		state.review?.previewVideoPath ||
		state.editRequest?.lastPreviewPath ||
		state.editRequest?.requestedPreviewPath ||
		outputPathValue() ||
		""
	);
}

async function loadReviewPreview(previewPath = "") {
	if (!state.project) {
		return null;
	}
	state.reviewPreviewLoading = true;
	state.reviewPreviewError = "";
	patchAppState({ reviewPreviewLoading: true, reviewPreviewError: "" });
	try {
		const result = await editApp.loadReviewPreview({
			project: state.project,
			previewPath: previewPath || reviewPreviewCandidate(),
		});
		if (!result?.ok) {
			state.reviewPreviewUrl = "";
			state.reviewTimeline = null;
			state.reviewThumbnailStrip = null;
			state.reviewWaveform = null;
			state.reviewPreviewMetadata = null;
			state.reviewPreviewError = String(result?.reason || "preview unavailable");
			patchAppState({
				reviewPreviewUrl: "",
				reviewTimeline: null,
				reviewThumbnailStrip: null,
				reviewWaveform: null,
				reviewPreviewMetadata: null,
				reviewPreviewError: state.reviewPreviewError,
			});
			return result;
		}
		state.review = {
			...(state.review || {}),
			previewVideoPath: String(result.previewVideoPath || ""),
			reviewTimelinePath: String(result.reviewTimelinePath || ""),
		};
		state.reviewPreviewUrl = String(result.videoUrl || "");
		state.reviewTimeline = result.reviewTimeline || null;
		state.reviewThumbnailStrip = result.thumbnailStrip || null;
		state.reviewWaveform = result.waveform || null;
		state.reviewPreviewMetadata = result.metadata || null;
		state.reviewPreviewError = "";
		getAppState().setReview(state.review);
		patchAppState({
			reviewPreviewUrl: state.reviewPreviewUrl,
			reviewTimeline: state.reviewTimeline,
			reviewThumbnailStrip: state.reviewThumbnailStrip,
			reviewWaveform: state.reviewWaveform,
			reviewPreviewMetadata: state.reviewPreviewMetadata,
			reviewPreviewError: "",
		});
		schedulePersistCurrentProjectState();
		saveState();
		return result;
	} catch (error) {
		state.reviewPreviewError = (error as Error).message;
		patchAppState({ reviewPreviewError: state.reviewPreviewError });
		log("review preview load failed", { message: state.reviewPreviewError });
		return null;
	} finally {
		state.reviewPreviewLoading = false;
		patchAppState({ reviewPreviewLoading: false });
	}
}

function resetAnalysisForMaterialChange(path = materialSourceLabel()) {
	setAnalysisResults([]);
	setMaterialAnalysisStatusMap({});
	setAnalysisTitleText("");
	state.syncReport = null;
	renderSyncReport();
	setWaitingAnalysisProgress(setIngestProgress, path);
}

async function refreshMaterialAnalysisStatus() {
	try {
		const result = await editApp.getMaterialAnalysisStatus({ appConfig: buildAppConfig() });
		setMaterialAnalysisStatusMap(result?.statuses || {});
	} catch (error) {
		log("material analysis status refresh failed", { message: (error as Error).message });
	}
}

function bindEvents() {
	bindRendererEvents({
		cancelMaterialAnalysis,
		changeProject,
		closeConfirmDialog,
		createProjectFromDialog,
		handleEditRequestChange,
		handleReviewStateChange,
		ingestSimpleMaterials,
		pickSimpleMaterialDirectory,
		pickSimpleMaterialFiles,
		addSimpleAudioFiles,
		pickSimpleAudioFiles,
		runSimpleTranscription,
		sendSimpleEditRequest,
		loadReviewPreview,
		loadOutputPreview,
		openProject,
		outputPreviewTarget,
		setLanguage,
		setProjectDialogOpen,
	});
}

let rendererStarted = false;

export async function startRenderer() {
	if (rendererStarted) {
		return;
	}
	rendererStarted = true;
	try {
		await init();
	} catch (error) {
		log("init error", { message: (error as Error).message });
	}
}

async function init() {
	state.env = await editApp.getEnvironment();
	patchAppState({ env: state.env });
	getAppState().setToolPaths({
		pythonPath: state.env.pythonExe || "",
		ffmpegPath: state.env.ffmpegExe || "",
		ffprobePath: state.env.ffprobeExe || "",
	});
	setOutputPathValue(state.env.knownOutputs?.[0] || "");
	setInputVideoPathValue(state.env.knownOutputs?.[0] || "");
	loadWorkflowMediaPreviews();
	loadOutputTargetPreview();
	restoreDefaultTextDrafts();
	loadState();
	const restoredProject = await restoreStartupProjectFromDisk();
	if (!restoredProject) {
		await loadProjectStateFile();
	}
	syncAppStoreFromLegacyState();
	renderGlossaryList();
	renderMediaManifest();
	bindEvents();
	applyTranslations();
	renderCodexModelOptions();
	renderCodexModelStatus();
	updateCodexRunControls();
	setActiveSection(state.activeSection);
	setStatus(state.statusText, state.statusKind);
	refreshPrompt();

	bindRendererIpcEvents({
		handleNotification,
		handleWorkflowProgress,
		loadProjectStateFile,
		refreshSyncReport,
		setCodexTurnRunning,
		setIngestProgress,
		setIngestRunning,
		setStatus,
	});
	if (state.activeSection === "run") {
		void loadCodexModels();
	}
	const loadedAnalysisState = await loadAnalysisStateFile();
	if (!loadedAnalysisState) {
		await restoreAnalysisResultsFromOutputs(state.mediaManifest);
	}
	await restoreProgressFromOutputs({ preserveExisting: true });
	if (state.mediaManifest) {
		await refreshAnalysisTitleFromAnalysis(state.mediaManifest);
		await refreshMaterialAnalysisStatus();
	}
	if (state.project) {
		void loadReviewPreview();
	}
	(window as unknown as Record<string, any>).__videoEditRendererReady = true;
}
