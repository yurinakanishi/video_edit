import { editApp } from "./api.js";
import { t } from "./i18n.js";
import { log } from "./log.js";
import { mediaManifestPath } from "./preview.js";
import { LANGUAGE_STORAGE_KEY, normalizeLanguage, STORAGE_KEY, state } from "./state.js";
import { getAppState } from "./store/app-store.js";
import { appFormFieldIds, readAppFormField, writeAppFormField } from "./store/form-fields.js";
import type { ProjectInfo } from "./types.js";

type ProjectStateControllerDeps = {
	setProject: (...args: any[]) => any;
	applyManifestSelections: (...args: any[]) => any;
	renderMediaManifest: (...args: any[]) => any;
	loadFilePreviews: (...args: any[]) => any;
	setIngestProgress: (...args: any[]) => any;
	materialSourceLabel: (...args: any[]) => any;
	loadMaterialSourcePreviews: (...args: any[]) => any;
	setStillImages: (...args: any[]) => any;
	setFile: (...args: any[]) => any;
	renderCodexModelOptions: (...args: any[]) => any;
	loadWorkflowMediaPreviews: (...args: any[]) => any;
	loadOutputTargetPreview: (...args: any[]) => any;
	setAnalysisResults: (...args: any[]) => any;
	renderGlossaryList: (...args: any[]) => any;
	buildAppConfig: (...args: any[]) => any;
	setAnalysisTitleText: (...args: any[]) => any;
	rebuildMediaManifestGroups: (...args: any[]) => any;
	setActiveSection: (...args: any[]) => any;
	setLanguage: (...args: any[]) => any;
	setSubtitleMode: (...args: any[]) => any;
	renderFileSlots: (...args: any[]) => any;
	renderStillImageList: (...args: any[]) => any;
	updateRunSummary: (...args: any[]) => any;
	refreshCommand: (...args: any[]) => any;
	refreshPrompt: (...args: any[]) => any;
};

export function createProjectStateController(deps: ProjectStateControllerDeps) {
	const {
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
		buildAppConfig,
		setAnalysisTitleText,
		rebuildMediaManifestGroups,
		setActiveSection,
		setLanguage,
		setSubtitleMode,
		renderFileSlots,
		renderStillImageList,
		updateRunSummary,
		refreshCommand,
		refreshPrompt,
	} = deps;

	function saveState() {
		if (!state.env) {
			return;
		}
		const fields: Record<string, string | boolean> = {};
		fields.modelName = getAppState().codexModel;
		for (const id of appFormFieldIds) {
			const appField = readAppFormField(id);
			if (!appField.found) {
				continue;
			}
			fields[id] = appField.value;
		}
		localStorage.setItem(
			STORAGE_KEY,
			JSON.stringify({
				project: state.project,
				mediaManifest: state.mediaManifest,
				mediaDirectory: state.mediaDirectory,
				materialPaths: state.materialPaths,
				files: state.files,
				subtitleMode: state.subtitleMode,
				analysisResults: state.analysisResults,
				ingestProgress: state.ingestProgress,
				editRequest: state.editRequest,
				glossaryTerms: state.glossaryTerms,
				language: state.language,
				activeSection: state.activeSection,
				fields,
			}),
		);
		schedulePersistProjectStateFile();
	}

	function loadState() {
		const raw = localStorage.getItem(STORAGE_KEY);
		if (!raw) {
			return;
		}
		const previousApplying = state.projectStateApplying;
		state.projectStateApplying = true;
		try {
			const saved = JSON.parse(raw);
			if (saved.language) {
				state.language = normalizeLanguage(saved.language);
				localStorage.setItem(LANGUAGE_STORAGE_KEY, state.language);
			}
			if (saved.activeSection) {
				state.activeSection = String(saved.activeSection);
			}
			if (saved.project) {
				setProject(saved.project);
			}
			if (saved.mediaManifest) {
				state.mediaManifest = saved.mediaManifest;
				state.mediaDirectory = saved.mediaDirectory || saved.mediaManifest.sourceDirectory || "";
				state.materialPaths =
					saved.materialPaths ||
					saved.mediaManifest.sourcePaths ||
					(state.mediaDirectory ? [state.mediaDirectory] : []);
				applyManifestSelections();
				renderMediaManifest();
				void loadFilePreviews((state.mediaManifest?.files || []).map((item) => item.path).filter(Boolean));
			} else if (saved.materialPaths?.length || saved.mediaDirectory) {
				state.mediaDirectory = saved.mediaDirectory;
				state.materialPaths = saved.materialPaths || (saved.mediaDirectory ? [saved.mediaDirectory] : []);
				setIngestProgress({
					progress: 0,
					message: t("progress.pressAnalyze"),
					path: materialSourceLabel(),
				});
				renderMediaManifest();
				void loadMaterialSourcePreviews(state.materialPaths);
			}
			if (saved.files) {
				Object.entries(saved.files).forEach(([slot, filePath]) => {
					if (slot === "stillImages" && Array.isArray(filePath)) {
						setStillImages(filePath.map(String));
						return;
					}
					if (slot in state.files) {
						setFile(slot, filePath);
					}
				});
			}
			if (saved.fields) {
				Object.entries(saved.fields).forEach(([id, value]) => {
					if (id === "titleText") {
						return;
					}
					if (id === "modelName") {
						state.codexModel = String(value ?? "");
						renderCodexModelOptions();
						return;
					}
					if (writeAppFormField(id, value)) {
						return;
					}
				});
				loadWorkflowMediaPreviews();
				loadOutputTargetPreview();
			}
			if (saved.subtitleMode) {
				setSubtitleMode(saved.subtitleMode);
			}
			if (Array.isArray(saved.analysisResults)) {
				setAnalysisResults(saved.analysisResults, { persistFile: false });
			}
			if (saved.ingestProgress) {
				setIngestProgress(saved.ingestProgress, { persist: false });
			}
			if (saved.editRequest && typeof saved.editRequest === "object") {
				state.editRequest = normalizeEditRequest(saved.editRequest);
				getAppState().setEditRequest(state.editRequest);
			}
			if (Array.isArray(saved.glossaryTerms)) {
				state.glossaryTerms = saved.glossaryTerms;
				renderGlossaryList();
			}
		} catch (error) {
			log("saved state ignored", { message: error.message });
		} finally {
			state.projectStateApplying = previousApplying;
		}
	}

	const projectStateFieldMap = [
		["render", "editPreset", "editPreset"],
		["render", "workflowAction", "workflowAction"],
		["render", "renderScript", "renderScript"],
		["render", "outputPath", "outputPath"],
		["render", "renderProfile", "renderProfile"],
		["render", "rangeMode", "rangeMode"],
		["render", "multicamMode", "multicamMode"],
		["render", "audioSource", "audioSource"],
		["render", "audioDenoise", "audioDenoise"],
		["render", "audioDenoiseStrength", "audioDenoiseStrength"],
		["render", "audioMastering", "audioMastering"],
		["render", "encoderPreset", "encoderPreset"],
		["render", "crf", "renderCrf"],
		["render", "colorMatchCameras", "colorMatchCameras"],
		["render", "globalVideoZoom", "globalVideoZoom"],
		["render", "usePersonEditPlans", "usePersonEditPlans"],
		["render", "useTranscriptComparisonSync", "useTranscriptComparisonSync"],
		["render", "naturalDialogueCuts", "naturalDialogueCuts"],
		["render", "previewStart", "previewStart"],
		["render", "previewDuration", "previewDuration"],
		["render", "termExplanations", "termExplanations"],
		["render", "shortenSilence", "shortenSilence"],
		["render", "minSilence", "minSilence"],
		["render", "keepSilence", "keepSilence"],
		["render", "silenceNoise", "silenceNoise"],
		["render", "keepUncut", "keepUncut"],
		["music", "enabled", "musicEnabled"],
		["music", "scope", "musicScope"],
		["music", "rangeSource", "musicRangeSource"],
		["music", "prompt", "musicPrompt"],
		["music", "volume", "musicVolume"],
		["music", "rangesText", "musicRangesText"],
		["omissionCard", "enabled", "omissionCardEnabled"],
		["omissionCard", "duration", "omissionCardDuration"],
		["omissionCard", "label", "omissionCardLabel"],
		["omissionCard", "text", "omissionCardText"],
		["omissionCard", "rangesText", "omissionCardRangesText"],
		["thumbnail", "inputVideoPath", "inputVideoPath"],
		["thumbnail", "time", "thumbnailTime"],
		["thumbnail", "title", "thumbnailTitle"],
		["thumbnail", "subtitle", "thumbnailSubtitle"],
		["thumbnail", "candidateCount", "thumbnailCandidateCount"],
		["thumbnail", "mode", "thumbnailMode"],
		["thumbnail", "mainColor", "thumbnailMainColor"],
		["thumbnail", "candidateTimesText", "thumbnailCandidateTimes"],
		["thumbnail", "debugFaces", "thumbnailDebugFaces"],
		["subtitleReview", "maxDuration", "subtitleReviewMaxDuration"],
		["subtitleReview", "maxCharsPerSecond", "subtitleReviewMaxCharsPerSecond"],
		["subtitleReview", "suspiciousPatternsText", "subtitleSuspiciousPatterns"],
		["subtitleReview", "extractAudioClips", "subtitleReviewExtractClips"],
		["subtitleReview", "transcribeReview", "subtitleReviewTranscribeClips"],
		["subtitleReview", "correctionsText", "subtitleCorrectionsText"],
		["subtitleSpeakers", "interviewerRangesText", "subtitleInterviewerRanges"],
		["subtitleSpeakers", "interviewerPatternsText", "subtitleInterviewerPatterns"],
		["subtitleSpeakers", "manualRolesText", "subtitleManualRoles"],
		["subtitleSpeakers", "mouthMotionDiagnostics", "subtitleMouthMotionDiagnostics"],
		["workflow", "inputVideoPath", "inputVideoPath"],
		["workflow", "stillTime", "stillTime"],
		["analysis", "transcribeModel", "transcribeModel"],
		["analysis", "transcribeLanguage", "transcribeLanguage"],
		["analysis", "transcribeBeamSize", "transcribeBeamSize"],
		["analysis", "transcribeTemperature", "transcribeTemperature"],
		["analysis", "transcribePromptTerms", "transcribePromptTerms"],
		["analysis", "transcribeNormalizeAudio", "transcribeNormalizeAudio"],
		["analysis", "transcribeFilterLowConfidence", "transcribeFilterLowConfidence"],
		["analysis", "conditionOnPreviousText", "conditionOnPreviousText"],
		["analysis", "personFpsSample", "personFpsSample"],
		["analysis", "personModel", "personModel"],
		["analysis", "personConfidence", "personConfidence"],
		["analysis", "personMaxSeconds", "personMaxSeconds"],
		["analysis", "personLimit", "personLimit"],
		["analysis", "personNoMulticamRoot", "personNoMulticamRoot"],
		["style", "subtitleSize", "subtitleSize"],
		["style", "highlightColor", "highlightColor"],
		["style", "boxOpacity", "boxOpacity"],
		["style", "titleSize", "titleSize"],
		["style", "logoHeight", "logoHeight"],
		["style", "punchlineText", "punchlineText"],
		["glossary", "enabled", "termExplanations"],
		["tools", "python", "pythonPath"],
		["tools", "ffmpeg", "ffmpegPath"],
		["tools", "ffprobe", "ffprobePath"],
	];

	function nestedValue(source: any, section: string, key: string) {
		const parent = source?.[section];
		if (!parent || typeof parent !== "object" || !(key in parent)) {
			return undefined;
		}
		return parent[key];
	}

	function setFormControlValue(id: string, value: any) {
		writeAppFormField(id, value);
	}

	function buildProjectStateSnapshot() {
		return {
			version: 1,
			revision: state.projectStateRevision || 0,
			updatedAt: new Date().toISOString(),
			...buildAppConfig(),
			editRequest: state.editRequest,
			ui: {
				activeSection: state.activeSection,
				codexModel: state.codexModel,
				language: state.language,
				progress: state.ingestProgress,
			},
		};
	}

	function normalizeEditRequest(value: any) {
		const history = Array.isArray(value?.instructionHistory)
			? value.instructionHistory
					.map((item: any) => ({
						id: String(item?.id || ""),
						mode: item?.mode === "final" ? "final" : "preview",
						text: String(item?.text || ""),
						targetPath: String(item?.targetPath || ""),
						createdAt: String(item?.createdAt || ""),
					}))
					.filter((item: any) => item.text)
			: [];
		return {
			instructionDraft: String(value?.instructionDraft || ""),
			instructionHistory: history,
			lastPreviewPath: String(value?.lastPreviewPath || ""),
			lastFinalPath: String(value?.lastFinalPath || ""),
		};
	}

	let projectStateWriteQueue: Promise<any> = Promise.resolve(null);

	function schedulePersistProjectStateFile() {
		if (!state.project || state.projectStateApplying || !state.env) {
			return;
		}
		if (state.projectStatePersistTimer) {
			window.clearTimeout(state.projectStatePersistTimer);
		}
		state.projectStatePersistTimer = window.setTimeout(() => {
			state.projectStatePersistTimer = 0;
			void persistProjectStateFileNow();
		}, 250);
	}

	async function persistProjectStateFileNow() {
		if (!state.project || state.projectStateApplying || !state.env) {
			return null;
		}
		if (state.projectStatePersistTimer) {
			window.clearTimeout(state.projectStatePersistTimer);
			state.projectStatePersistTimer = 0;
		}
		const project = { ...state.project };
		projectStateWriteQueue = projectStateWriteQueue
			.catch(() => undefined)
			.then(async () => {
				if (!state.project || state.project.id !== project.id || state.projectStateApplying || !state.env) {
					return null;
				}
				const baseRevision = Number(state.projectStateRevision || 0);
				const snapshot = buildProjectStateSnapshot();
				const saved = await editApp.saveProjectState({
					project,
					state: snapshot,
					baseRevision,
				});
				if (state.project?.id === project.id) {
					state.projectStateRevision = Number(saved?.revision || state.projectStateRevision || 0);
					state.projectStatePath = saved?.path || state.projectStatePath;
				}
				return saved;
			})
			.catch((error) => {
				log("project state save failed", { message: error.message });
				if (String(error?.message || "").includes("revision mismatch") && state.project?.id === project.id) {
					void loadProjectStateFile(project);
				}
				return null;
			});
		return projectStateWriteQueue;
	}

	function applyProjectStatePayload(payload: any) {
		if (!payload || typeof payload !== "object") {
			return false;
		}
		state.projectStateApplying = true;
		try {
			state.projectStatePath = String(payload.path || state.projectStatePath || "");
			state.projectStateRevision = Number(payload.revision || state.projectStateRevision || 0);
			const assets = payload.assets || {};
			if (Array.isArray(assets.materialPaths)) {
				state.materialPaths = assets.materialPaths.map(String).filter(Boolean);
				state.materialSourcePreviews = [];
				state.materialSourcePreviewLoading = false;
			}
			state.mediaDirectory = String(assets.mediaDirectory || state.materialPaths[0] || "");
			if (assets.mediaManifest && typeof assets.mediaManifest === "object") {
				state.mediaManifest = assets.mediaManifest;
				if (state.mediaManifest) {
					rebuildMediaManifestGroups();
				}
			}
			const selected = state.mediaManifest?.selected || {};
			state.files.masterVideo = String(assets.masterVideo || selected.masterVideo || "");
			state.files.rightCloseVideo = String(assets.rightCloseVideo || selected.rightCloseVideo || "");
			state.files.leftCloseVideo = String(assets.leftCloseVideo || selected.leftCloseVideo || "");
			state.files.referenceVideo = String(assets.referenceVideo || "");
			state.files.externalAudio = String(assets.externalAudio || selected.externalAudio || "");
			state.files.logo = String(assets.logo || selected.logo || "");
			state.files.stillImages = Array.isArray(assets.stillImages)
				? [...new Set<string>(assets.stillImages.map(String).filter((item) => Boolean(item)))]
				: Array.isArray(selected.stillImages)
					? selected.stillImages.map(String).filter(Boolean)
					: [];

			for (const [section, key, id] of projectStateFieldMap) {
				setFormControlValue(id, nestedValue(payload, section, key));
			}
			if (payload.render?.subtitleMode) {
				setSubtitleMode(String(payload.render.subtitleMode));
			}
			if (payload.style && "titleText" in payload.style) {
				setAnalysisTitleText(String(payload.style.titleText || ""));
			}
			if (payload.editRequest && typeof payload.editRequest === "object") {
				state.editRequest = normalizeEditRequest(payload.editRequest);
				getAppState().setEditRequest(state.editRequest);
			}
			if (Array.isArray(payload.glossary?.terms)) {
				state.glossaryTerms = payload.glossary.terms;
			}
			if (payload.ui?.activeSection) {
				setActiveSection(String(payload.ui.activeSection));
			}
			if (payload.ui?.codexModel !== undefined) {
				state.codexModel = String(payload.ui.codexModel || "");
				renderCodexModelOptions();
			}
			if (payload.ui?.language) {
				setLanguage(normalizeLanguage(payload.ui.language));
			}
			if (payload.ui?.progress) {
				setIngestProgress(payload.ui.progress, { persist: false });
			}

			renderFileSlots();
			renderStillImageList();
			renderMediaManifest();
			if (state.mediaManifest) {
				loadFilePreviews((state.mediaManifest.files || []).map((item) => item.path).filter(Boolean));
			} else if (state.materialPaths.length) {
				loadMaterialSourcePreviews(state.materialPaths);
			}
			renderGlossaryList();
			loadFilePreviews([
				state.files.masterVideo,
				state.files.rightCloseVideo,
				state.files.leftCloseVideo,
				state.files.referenceVideo,
				state.files.externalAudio,
				state.files.logo,
				...state.files.stillImages,
			]);
			loadWorkflowMediaPreviews();
			loadOutputTargetPreview();
			updateRunSummary();
			refreshCommand();
			refreshPrompt();
			return true;
		} finally {
			state.projectStateApplying = false;
		}
	}

	async function loadProjectStateFile(project: ProjectInfo | null = state.project) {
		if (!project) {
			return false;
		}
		try {
			const payload = await editApp.loadProjectState({ project });
			if (!payload) {
				return false;
			}
			const applied = applyProjectStatePayload(payload);
			if (applied) {
				log("project state loaded", {
					path: payload.path || "",
					revision: payload.revision || 0,
				});
			}
			return applied;
		} catch (error) {
			log("project state load failed", { message: error.message });
			return false;
		}
	}

	let analysisStateWriteQueue: Promise<void> = Promise.resolve();

	function analysisStateSnapshot() {
		return {
			version: 1,
			updatedAt: new Date().toISOString(),
			mediaManifestPath: mediaManifestPath(),
			mediaManifestGeneratedAt: state.mediaManifest?.generatedAt || "",
			mediaManifestFileCount: state.mediaManifest?.files?.length || 0,
			results: state.analysisResults.map((item) => ({ ...item })),
		};
	}

	function persistAnalysisStateFile() {
		if (!state.project) {
			return;
		}
		const project = { ...state.project };
		const snapshot = analysisStateSnapshot();
		analysisStateWriteQueue = analysisStateWriteQueue
			.catch(() => undefined)
			.then(async () => {
				await editApp.saveAnalysisState({ project, state: snapshot });
			})
			.catch((error) => {
				log("analysis state save failed", { message: error.message });
			});
	}

	async function loadAnalysisStateFile(project: ProjectInfo | null = state.project) {
		if (!project) {
			return false;
		}
		try {
			const payload = await editApp.loadAnalysisState({ project });
			if (!Array.isArray(payload?.results) || !payload.results.length) {
				return false;
			}
			setAnalysisResults(payload.results, { persistFile: false });
			log("analysis state loaded", {
				path: payload.path || "",
				results: state.analysisResults.length,
			});
			return state.analysisResults.length > 0;
		} catch (error) {
			log("analysis state load failed", { message: error.message });
			return false;
		}
	}

	return {
		saveState,
		loadState,
		schedulePersistProjectStateFile,
		persistProjectStateFileNow,
		applyProjectStatePayload,
		loadProjectStateFile,
		persistAnalysisStateFile,
		loadAnalysisStateFile,
	};
}
