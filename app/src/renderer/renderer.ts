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
import { setInputVideoPathValue, setOutputPathValue } from "./media-state.js";
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
	setSelectedCodexModel,
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

const {
	glossaryTerms,
	handleGlossaryTermChange,
	handleGlossaryTermRemove,
	normalizeGlossaryTerm,
	renderGlossaryList,
	setGlossaryTerms,
	termsFromGlossaryManifest,
} = glossaryStateController;

const assetFileController = createAssetFileController({
	refreshPrompt: () => currentRefreshPrompt(),
	renderMediaManifest: () => currentRenderMediaManifest(),
});

const {
	addStillImages,
	clearSelectedAssets,
	loadFilePreviews,
	loadOutputTargetPreview,
	loadWorkflowMediaPreviews,
	pickFile,
	pickOutput,
	pickTool,
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

const {
	addMaterialSources,
	loadMaterialSourcePreviews,
	materialSourceLabel,
	pickMaterialDirectory,
	pickMaterialFiles,
	setMaterialSources,
	setMaterialSourcesFromPreviews,
} = materialSourceController;

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

const {
	applyManifestSelections,
	handleMaterialItemRemove,
	handleMaterialRoleChange,
	handleMaterialSourceRemove,
	handleStillImageRemove,
	rebuildMediaManifestGroups,
	renderMediaManifest,
	setMediaManifest,
} = materialManifestController;
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
	deleteCurrentProject,
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
	loadGlossaryCandidates,
	refreshTextOverlayFromAnalysis,
	refreshAnalysisTitleFromAnalysis,
	addGlossaryTerm,
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
	runPreset,
	sendRequest,
	stopCodexTurn,
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

const { cancelMaterialAnalysis, ingestMaterialDirectory, reanalyzeMaterialItem, syncMaterialSources } =
	materialAnalysisController;

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
		addGlossaryTerm,
		addMaterialSources,
		addStillImages,
		cancelMaterialAnalysis,
		changeProject,
		closeConfirmDialog,
		copyAssetsToProject,
		createProjectFromDialog,
		createProjectFromForm,
		deleteCurrentProject,
		handleGlossaryTermChange,
		handleGlossaryTermRemove,
		handleMaterialItemRemove,
		handleMaterialRoleChange,
		handleMaterialSourceRemove,
		reanalyzeMaterialItem,
		syncMaterialSources,
		handleNotification,
		handleStillImageRemove,
		ingestMaterialDirectory,
		loadCodexModels,
		loadGlossaryCandidates,
		loadOutputPreview,
		openProject,
		outputPreviewTarget,
		pickFile,
		pickMaterialDirectory,
		pickMaterialFiles,
		pickOutput,
		pickTool,
		refreshCommand,
		refreshPrompt,
		refreshSyncReport,
		runPreset,
		saveState,
		sendRequest,
		setActiveSection,
		setFile,
		setLanguage,
		setProjectDialogOpen,
		setSelectedCodexModel,
		setSubtitleMode,
		stopCodexTurn,
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
}
