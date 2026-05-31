import { editApp } from "./api.js";
import {
	ENCODER_PRESETS,
	selectOptionLabel,
	THUMBNAIL_COLOR_OPTIONS,
	THUMBNAIL_MODES,
	WORKFLOW_ACTIONS,
} from "./form-options.js";
import { localizePlainText, t } from "./i18n.js";
import { log } from "./log.js";
import { setOutputPathValue } from "./media-state.js";
import {
	activeOutputRoot,
	activeProjectVideoSourceRoot,
	activeSourceRoot,
	joinPath,
	manifestAudioSources,
	manifestCameras,
	mediaManifestPath,
	selectedMasterVideoPath,
	shortPath,
} from "./preview.js";
import { DEFAULT_FFMPEG_EXE, DEFAULT_FFPROBE_EXE, state } from "./state.js";
import { getAppState, patchAppState, type RunChecklistItem } from "./store/app-store.js";
import { readAppFormField } from "./store/form-fields.js";
import { describeSyncReportRows, syncScoreKind } from "./sync-report.js";
import type { AnalysisResult, MediaManifest } from "./types.js";

type WorkflowControllerDeps = {
	createProjectFromForm: (...args: any[]) => any;
	copyAssetsToProject: (...args: any[]) => any;
	setStatus: (...args: any[]) => any;
	syncReportPath: (...args: any[]) => any;
	termsFromGlossaryManifest: (...args: any[]) => any;
	normalizeGlossaryTerm: (...args: any[]) => any;
	setGlossaryTerms: (...args: any[]) => any;
	setAnalysisTitleText: (...args: any[]) => any;
	progressPercent: (...args: any[]) => any;
	renderAnalysisResults: (...args: any[]) => any;
	setAnalysisResults: (...args: any[]) => any;
	setIngestProgress: (...args: any[]) => any;
	setAppLocked: (...args: any[]) => any;
	setDirectRunRunning: (...args: any[]) => any;
	setMediaManifest: (...args: any[]) => any;
	notifyAnalysisComplete: (...args: any[]) => any;
	refreshMaterialAnalysisStatus: (...args: any[]) => any;
	setCodexTurnRunning: (...args: any[]) => any;
	updateCodexRunControls: (...args: any[]) => any;
	codexErrorMessage: (...args: any[]) => any;
	selectedCodexModelForRun: (...args: any[]) => any;
	selectedCodexReasoningEffort: (...args: any[]) => any;
	persistProjectStateFileNow: (...args: any[]) => any;
	saveState: (...args: any[]) => any;
	glossaryTerms: (...args: any[]) => any;
};

export function createWorkflowController(deps: WorkflowControllerDeps) {
	const {
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
	} = deps;

	async function prepareProjectForRun() {
		const projectDraft = getAppState().projectDraft;
		if (!state.project && !projectDraft.name && !projectDraft.id) {
			log("project required before run");
			setStatus(t("status.projectRequired"), "idle");
			return false;
		}
		if (!state.project) {
			await createProjectFromForm();
		}
		if (state.mediaManifest) {
			return true;
		}
		if (state.project) {
			return copyAssetsToProject();
		}
		return false;
	}

	function formValue(id): any {
		const appField = readAppFormField(id);
		if (appField.found) {
			return appField.value;
		}
		return "";
	}

	function inputVideoPathValue() {
		return getAppState().inputVideoPath;
	}

	function outputPathValue() {
		return getAppState().outputPath;
	}

	function selectedLabel(id) {
		const value = String(formValue(id) || "");
		if (id === "workflowAction") {
			return selectOptionLabel(WORKFLOW_ACTIONS, value);
		}
		if (id === "thumbnailMode") {
			return selectOptionLabel(THUMBNAIL_MODES, value);
		}
		if (id === "thumbnailMainColor") {
			return selectOptionLabel(THUMBNAIL_COLOR_OPTIONS, value);
		}
		if (id === "encoderPreset") {
			return selectOptionLabel(ENCODER_PRESETS, value);
		}
		return value;
	}

	function subtitleModeLabel() {
		if (state.subtitleMode === "punchline") {
			return t("style.catchy");
		}
		if (state.subtitleMode === "none") {
			return t("style.none");
		}
		return t("style.full");
	}

	function analysisLabel(key: string, fallback = "") {
		const labels = {
			ingest: "analysis.materialClassification",
			"auto-sync-dropped": "analysis.syncCamerasAudio",
			"transcribe-dropped": "analysis.transcription",
			"compare-transcripts": "analysis.transcriptComparison",
			"text-overlays": "analysis.subtitleUi",
			"analyze-person-edit-metadata": "analysis.personOpenCv",
			"analyze-blocking": "analysis.blockingOpenCv",
			"analyze-reference-video": "analysis.referenceVideo",
		};
		return labels[key] ? t(labels[key]) : localizePlainText(fallback || key);
	}

	function scoreKind(score) {
		return syncScoreKind(score);
	}

	function describeSyncReport() {
		return describeSyncReportRows(state.syncReport);
	}

	function renderSyncReport() {
		patchAppState({ syncReport: state.syncReport });
	}

	async function refreshSyncReport() {
		try {
			state.syncReport = await editApp.getSyncReport(buildAppConfig());
		} catch (error) {
			state.syncReport = null;
			log("sync report error", { message: error.message });
		}
		renderSyncReport();
		updateRunSummary();
	}

	async function loadGlossaryCandidates() {
		try {
			const manifest = await editApp.loadGlossaryCandidates(buildAppConfig());
			let candidates = termsFromGlossaryManifest(manifest);
			if (!candidates.length) {
				const overlayCandidates = await editApp.loadTextOverlayCandidates({
					manifest: state.mediaManifest,
					appConfig: buildAppConfig(),
				});
				candidates = overlayCandidates?.glossaryTerms || [];
			}
			setGlossaryTerms(candidates);
			log("glossary candidates loaded", { count: candidates.length });
		} catch (error) {
			try {
				const overlayCandidates = await editApp.loadTextOverlayCandidates({
					manifest: state.mediaManifest,
					appConfig: buildAppConfig(),
				});
				const candidates = overlayCandidates?.glossaryTerms || [];
				setGlossaryTerms(candidates);
				log("glossary candidates loaded from subtitles", { count: candidates.length });
			} catch (fallbackError) {
				log("glossary load failed", { message: fallbackError.message || error.message });
			}
		}
	}

	async function refreshTextOverlayFromAnalysis(manifest: MediaManifest | null) {
		try {
			const result = await editApp.loadTextOverlayCandidates({
				manifest,
				appConfig: buildAppConfig(),
			});
			setAnalysisTitleText(result?.titleText || "");
			getAppState().setPunchlineText(result?.punchlineText || "");
			setGlossaryTerms(Array.isArray(result?.glossaryTerms) ? result.glossaryTerms : []);
			log("text overlays refreshed", {
				subtitle: result?.subtitlePath || null,
				captions: result?.captionCount || 0,
				title: result?.titleText || "",
				glossary: result?.glossaryTerms?.length || 0,
			});
			refreshPrompt();
			return result;
		} catch (error) {
			log("text overlay refresh failed", { message: error.message });
			return null;
		}
	}

	async function refreshAnalysisTitleFromAnalysis(manifest: MediaManifest | null) {
		try {
			const result = await editApp.loadTextOverlayCandidates({
				manifest,
				appConfig: buildAppConfig(),
			});
			setAnalysisTitleText(result?.titleText || "");
			log("analysis title refreshed", {
				subtitle: result?.subtitlePath || null,
				captions: result?.captionCount || 0,
				title: result?.titleText || "",
			});
			refreshPrompt();
		} catch (error) {
			setAnalysisTitleText("");
			log("analysis title refresh failed", { message: error.message });
		}
	}

	function addGlossaryTerm() {
		const draft = getAppState().glossaryDraft;
		const term = normalizeGlossaryTerm({
			label: draft.label,
			patterns: draft.patterns,
			description: draft.description,
			enabled: true,
		});
		if (!term) {
			log("glossary add skipped", { reason: t("log.glossaryRequired") });
			return;
		}
		setGlossaryTerms([...glossaryTerms(), term]);
		getAppState().setGlossaryDraft({ label: "", patterns: "", description: "" });
	}

	function pythonExe() {
		return formValue("pythonPath") || state.env?.pythonExe || "python";
	}

	function ffmpegExe() {
		return formValue("ffmpegPath") || state.env?.ffmpegExe || DEFAULT_FFMPEG_EXE;
	}

	function ffprobeExe() {
		return formValue("ffprobePath") || state.env?.ffprobeExe || DEFAULT_FFPROBE_EXE;
	}

	function stillOutputPath(inputVideo, outputPath) {
		if (outputPath && /\.(png|jpg|jpeg)$/i.test(outputPath)) {
			return outputPath;
		}
		const source = inputVideo || outputPath || "preview";
		return `${source.replace(/\.[^.\\/]+$/, "")}_still.png`;
	}

	function personBboxesDir() {
		return joinPath(activeOutputRoot() || "output", "reports", "person_bboxes");
	}

	function personEditPlansDir() {
		return joinPath(activeOutputRoot() || "output", "reports", "person_edit_plans");
	}

	function referencePersonBboxesDir() {
		return joinPath(activeOutputRoot() || "output", "reports", "reference_person_bboxes");
	}

	function referenceEditPlansDir() {
		return joinPath(activeOutputRoot() || "output", "reports", "reference_edit_plans");
	}

	function referenceEditProfilePath() {
		return joinPath(activeOutputRoot() || "output", "reports", "reference_edit_profile.json");
	}

	function musicBedPath() {
		return activeOutputRoot() ? joinPath(activeOutputRoot(), "audio", "music_bed.wav") : "";
	}

	function omissionCardOutputPath() {
		return activeOutputRoot() ? joinPath(activeOutputRoot(), "overlays", "omission_card.png") : "";
	}

	function thumbnailOutputPath() {
		return activeOutputRoot() ? joinPath(activeOutputRoot(), "images", "thumbnail.png") : "";
	}

	function thumbnailCandidatesOutputPath() {
		return activeOutputRoot() ? joinPath(activeOutputRoot(), "images", "thumbnail_candidates") : "";
	}

	function proxyOutputPath() {
		return activeOutputRoot() ? joinPath(activeOutputRoot(), "proxy") : "";
	}

	function subtitleReviewOutputPath() {
		return activeOutputRoot() ? joinPath(activeOutputRoot(), "reports", "subtitle_review.json") : "";
	}

	function subtitleReviewClipsPath() {
		return activeOutputRoot() ? joinPath(activeOutputRoot(), "diagnostics", "subtitle_review", "clips") : "";
	}

	function subtitleCorrectionsOutputPath() {
		return activeOutputRoot() ? joinPath(activeOutputRoot(), "reports", "subtitle_corrections_applied.json") : "";
	}

	function subtitleSpeakerRolesOutputPath() {
		return activeOutputRoot() ? joinPath(activeOutputRoot(), "reports", "full_transcript_speaker_roles.json") : "";
	}

	function transcriptComparisonOutputPath() {
		return activeOutputRoot() ? joinPath(activeOutputRoot(), "reports", "transcript_comparison.json") : "";
	}

	function transcriptManifestOutputPath() {
		return activeOutputRoot()
			? joinPath(activeOutputRoot(), "transcripts", "manifest_sources", "manifest_transcripts.json")
			: "";
	}

	function timelineOutputPath() {
		return activeOutputRoot() ? joinPath(activeOutputRoot(), "timelines", "current.timeline.json") : "";
	}

	function rendererCommandOutputPath() {
		return activeOutputRoot() ? joinPath(activeOutputRoot(), "reports", "renderer_commands") : "";
	}

	function blockingMetricsOutputPath() {
		return activeOutputRoot()
			? joinPath(activeOutputRoot(), "diagnostics", "opencv_blocking_analysis", "clip_metrics.json")
			: "";
	}

	function analysisOutputCandidates(manifest: MediaManifest | null = state.mediaManifest) {
		const candidates: Array<AnalysisResult & { requirePath?: boolean }> = [];
		if (!activeOutputRoot()) {
			return candidates;
		}
		const manifestPath = mediaManifestPath();
		if (manifestPath) {
			candidates.push({
				key: "ingest",
				label: t("analysis.materialClassification"),
				status: "done",
				detail: manifest?.files
					? `${manifest.files.length || 0} files / ${manifest.cameras?.length || 0} camera(s)`
					: t("analysis.updatedOutput"),
				path: manifestPath,
				requirePath: true,
			});
		}
		if (manifest && !hasSyncTargets(manifest)) {
			candidates.push({
				key: "auto-sync-dropped",
				label: t("analysis.syncCamerasAudio"),
				status: "done",
				detail: t("analysis.singleCameraSkipped"),
				path: syncReportPath(),
				requirePath: false,
			});
		} else if (syncReportPath()) {
			candidates.push({
				key: "auto-sync-dropped",
				label: t("analysis.syncCamerasAudio"),
				status: "done",
				detail: t("analysis.updatedOutput"),
				path: syncReportPath(),
				requirePath: true,
			});
		}
		const transcriptPath = transcriptManifestOutputPath();
		if (transcriptPath) {
			candidates.push(
				{
					key: "transcribe-dropped",
					label: t("analysis.transcription"),
					status: "done",
					detail: t("analysis.updatedOutput"),
					path: transcriptPath,
					requirePath: true,
				},
				{
					key: "text-overlays",
					label: t("analysis.subtitleUi"),
					status: "done",
					detail: t("analysis.updatedOutput"),
					path: transcriptPath,
					requirePath: true,
				},
			);
		}
		if (timelineOutputPath()) {
			candidates.push({
				key: "build-timeline",
				label: "Timeline JSON",
				status: "done",
				detail: t("analysis.updatedOutput"),
				path: timelineOutputPath(),
				requirePath: true,
			});
		}
		for (const item of [
			["compare-transcripts", t("analysis.transcriptComparison"), transcriptComparisonOutputPath()],
			["analyze-person-edit-metadata", t("analysis.personOpenCv"), personEditPlansDir()],
			["analyze-blocking", t("analysis.blockingOpenCv"), blockingMetricsOutputPath()],
		] as const) {
			if (item[2]) {
				candidates.push({
					key: item[0],
					label: item[1],
					status: "done",
					detail: t("analysis.updatedOutput"),
					path: item[2],
					requirePath: true,
				});
			}
		}
		if (state.files.referenceVideo && referenceEditProfilePath()) {
			candidates.push({
				key: "analyze-reference-video",
				label: t("analysis.referenceVideo"),
				status: "done",
				detail: t("analysis.updatedOutput"),
				path: referenceEditProfilePath(),
				requirePath: true,
			});
		}
		return candidates;
	}

	async function restoreAnalysisResultsFromOutputs(
		manifest: MediaManifest | null = state.mediaManifest,
		options: { preserveExisting?: boolean } = {},
	) {
		if (options.preserveExisting && state.analysisResults.length) {
			renderAnalysisResults();
			return;
		}
		const candidates = analysisOutputCandidates(manifest);
		if (!candidates.length) {
			setAnalysisResults([]);
			return;
		}
		const paths = [
			...new Set(
				candidates
					.filter((item) => item.requirePath !== false)
					.map((item) => item.path)
					.filter(Boolean),
			),
		];
		let existing = new Set<string>();
		if (paths.length) {
			try {
				const entries = await editApp.describeMediaPaths({ paths });
				existing = new Set(
					(entries || [])
						.filter((entry) => entry?.path && entry.missing !== true && entry.exists !== false)
						.map((entry) => String(entry.path || "").toLowerCase()),
				);
			} catch (error) {
				log("analysis restore failed", { message: error.message });
			}
		}
		setAnalysisResults(
			candidates.filter(
				(item) => item.requirePath === false || (item.path && existing.has(String(item.path).toLowerCase())),
			),
		);
	}

	async function restoreProgressFromOutputs(options: { preserveExisting?: boolean } = {}) {
		if (!state.project) {
			return false;
		}
		if (options.preserveExisting && Number(state.ingestProgress.progress || 0) > 0) {
			return false;
		}
		const action = formValue("workflowAction") || "render-selected";
		const path = directRunOutputPath(action);
		if (!path || path === activeOutputRoot()) {
			return false;
		}
		try {
			const entries = await editApp.describeMediaPaths({ paths: [path] });
			if (!entries?.some((entry) => entry?.path && entry.missing !== true && entry.exists !== false)) {
				return false;
			}
			const label = directRunLabel(action);
			setIngestProgress({
				progress: 1,
				message: t("format.completeMessage", { label }),
				path,
			});
			return true;
		} catch (error) {
			log("progress restore failed", { message: error.message });
			return false;
		}
	}

	function hasMusicRanges() {
		return Boolean(String(formValue("musicRangesText") || "").trim());
	}

	function hasOmissionCardRanges() {
		return Boolean(
			String(formValue("omissionCardRangesText") || "").trim() || String(formValue("musicRangesText") || "").trim(),
		);
	}

	function hasSubtitleCorrections() {
		return Boolean(String(formValue("subtitleCorrectionsText") || "").trim());
	}

	function hasSubtitleSpeakerRules() {
		return Boolean(
			String(formValue("subtitleInterviewerRanges") || "").trim() ||
				String(formValue("subtitleInterviewerPatterns") || "").trim() ||
				String(formValue("subtitleManualRoles") || "").trim(),
		);
	}

	function thumbnailInputPath() {
		return inputVideoPathValue() || selectedMasterVideoPath() || manifestCameras()[0]?.path || outputPathValue() || "";
	}

	function thumbnailCandidateImageCount() {
		const paths = new Set<string>();
		(state.mediaManifest?.images || []).forEach((item) => {
			if (item.role !== "logo") {
				paths.add(item.path);
			}
		});
		state.files.stillImages.forEach((path) => {
			paths.add(path);
		});
		return paths.size;
	}

	function hasThumbnailCandidateSource() {
		return Boolean(thumbnailInputPath() || thumbnailCandidateImageCount());
	}

	function selectedAnalysisVideos() {
		const manifestVideos = manifestCameras()
			.map((item) => item.path)
			.filter(Boolean);
		return manifestVideos.length
			? manifestVideos
			: [state.files.masterVideo, state.files.rightCloseVideo, state.files.leftCloseVideo].filter(Boolean);
	}

	function withRuntimeConfig(command) {
		return command;
	}

	function scriptPath(scriptName) {
		return state.env?.scriptsRoot ? `${state.env.scriptsRoot}\\${scriptName}` : scriptName;
	}

	function buildPresetCommand() {
		const action = formValue("workflowAction");
		return {
			command: withRuntimeConfig([pythonExe(), scriptPath("video_edit_run.py"), "--action", action]),
			reason: "",
		};
	}

	function buildActionCommand(action: string) {
		return withRuntimeConfig([pythonExe(), scriptPath("video_edit_run.py"), "--action", action]);
	}

	function hasSyncTargets(manifest: MediaManifest | null) {
		const cameraCount = (manifest?.cameras || []).filter((item) => item.role !== "master").length;
		const audioCount = manifest?.audio?.length || 0;
		return (
			cameraCount + audioCount > 0 ||
			Boolean(state.files.rightCloseVideo || state.files.leftCloseVideo || state.files.externalAudio)
		);
	}

	function compactOutput(value: string) {
		const text = String(value || "");
		return text.length > 4000 ? `${text.slice(0, 1200)}\n...\n${text.slice(-2400)}` : text;
	}

	function timestampSlug() {
		return new Date().toISOString().replace(/[:.]/g, "-").replace("T", "_").replace("Z", "");
	}

	function simpleEditOutputPath(mode: "preview" | "final") {
		const root = activeOutputRoot();
		if (!root) {
			return "";
		}
		const filename = `${mode}_${timestampSlug()}.mp4`;
		return mode === "preview" ? joinPath(root, "videos", "previews", filename) : joinPath(root, "videos", filename);
	}

	function setEditRequestState(patch: Record<string, any>) {
		state.editRequest = {
			instructionDraft: "",
			lastPreviewPath: "",
			lastFinalPath: "",
			...(state.editRequest || {}),
			...patch,
			instructionHistory:
				patch.instructionHistory ||
				(state.editRequest?.instructionHistory ? [...state.editRequest.instructionHistory] : []),
		};
		getAppState().setEditRequest(state.editRequest);
	}

	function instructionHistoryLines(history = state.editRequest?.instructionHistory || []) {
		if (!history.length) {
			return "- (none)";
		}
		return history
			.map((item, index) => {
				const label = item.mode === "final" ? "final" : "preview";
				return `- ${index + 1}. [${label}] ${item.text}\n  target: ${item.targetPath || "(not set)"}`;
			})
			.join("\n");
	}

	function mediaManifestSummaryLines() {
		const manifest = state.mediaManifest;
		if (!manifest?.files?.length) {
			return ["- (no media manifest yet)"];
		}
		return [
			`- Manifest: ${mediaManifestPath() || "(not saved)"}`,
			`- Cameras: ${
				manifestCameras()
					.map((item) => `${item.role}: ${item.path}`)
					.join("; ") || "(none)"
			}`,
			`- Audio: ${
				manifestAudioSources()
					.map((item) => `${item.role}: ${item.path}`)
					.join("; ") || "(none)"
			}`,
			`- Images: ${(manifest.images || []).map((item) => `${item.role}: ${item.path}`).join("; ") || "(none)"}`,
			`- Subtitles: ${(manifest.subtitles || []).map((item) => item.path).join("; ") || "(none)"}`,
		];
	}

	function buildSimplePrompt(
		mode: "preview" | "final",
		targetPath: string,
		context: {
			history?: any[];
			currentInstruction?: string;
			previousPreviewPath?: string;
			previousFinalPath?: string;
		} = {},
	) {
		const history = context.history || state.editRequest?.instructionHistory || [];
		const currentInstruction = String(
			context.currentInstruction ?? state.editRequest?.instructionDraft ?? history.at(-1)?.text ?? "",
		).trim();
		const modeLabel = mode === "preview" ? "preview video" : "final full render";
		const transcriptPath = transcriptManifestOutputPath();
		const previousPreview = context.previousPreviewPath ?? state.editRequest?.lastPreviewPath ?? "";
		const previousFinal = context.previousFinalPath ?? state.editRequest?.lastFinalPath ?? "";
		const lines = [
			"You are working in C:\\Users\\yurin\\Desktop\\video_edit.",
			`Create the requested ${modeLabel} for the active video-edit project.`,
			"",
			"Use the repository's existing video-edit pipeline and keep generated artifacts inside the active project's output directory.",
			"Do not ask the operator to use hidden UI controls. Interpret the natural language instructions below and update project-local state, timelines, scripts, or render commands as needed.",
			"Prefer timeline JSON plus validation before rendering. If rendering is blocked, report the missing input or validation issue clearly.",
			"",
			"Active project:",
			`- Name: ${state.project?.name || "(none)"}`,
			`- Root: ${state.project?.root || "(none)"}`,
			`- Source root: ${activeSourceRoot() || "(none)"}`,
			`- Output root: ${activeOutputRoot() || "(none)"}`,
			`- Runtime config: ${activeOutputRoot() ? joinPath(activeOutputRoot(), "app", "video_edit_app_config.runtime.json") : "(none)"}`,
			"",
			"Media:",
			...mediaManifestSummaryLines(),
			`- Transcript manifest: ${transcriptPath || "(not generated yet)"}`,
			"",
			"Instruction history:",
			instructionHistoryLines(history),
			"",
			"Current operator instruction:",
			currentInstruction || "(continue from the instruction history and current project state)",
			"",
			"Requested output:",
			`- Mode: ${mode}`,
			`- Target output path: ${targetPath}`,
			`- Previous preview: ${previousPreview || "(none)"}`,
			`- Previous final render: ${previousFinal || "(none)"}`,
			"",
			"Execution requirements:",
			"- For preview mode, create a short preview render at the target output path.",
			"- For final mode, render the complete final video at the target output path.",
			"- Use current-project source files from the media manifest. The manifest paths are the copied project-local source paths.",
			"- If transcription is needed and missing, run the existing transcription workflow for the active manifest.",
			"- Report the output file path and any limitations when finished.",
		];
		return lines.join("\n");
	}

	function directRunLabel(action: string) {
		if (action === "render-selected") {
			return t("runLabel.render");
		}
		if (action === "auto-sync-dropped") {
			return t("runLabel.sync");
		}
		if (action.startsWith("transcribe")) {
			return t("runLabel.transcribe");
		}
		if (action === "generate-music-bed") {
			return t("option.generateMusicBed");
		}
		if (action === "replace-audio") {
			return t("option.replaceAudio");
		}
		if (action === "generate-thumbnail") {
			return t("option.generateThumbnail");
		}
		if (action === "generate-thumbnail-candidates") {
			return t("option.generateThumbnailCandidates");
		}
		if (action === "generate-proxies") {
			return selectedLabel("workflowAction") || "Generate proxies";
		}
		if (action === "review-subtitles") {
			return t("option.reviewSubtitles");
		}
		if (action === "apply-subtitle-corrections") {
			return t("option.applySubtitleCorrections");
		}
		if (action === "classify-subtitle-speakers") {
			return t("option.classifySubtitleSpeakers");
		}
		if (action === "compare-transcripts") {
			return t("option.compareTranscripts");
		}
		if (action.startsWith("analyze-")) {
			return t("runLabel.analyze");
		}
		return selectedLabel("workflowAction") || t("runLabel.run");
	}

	function directRunOutputPath(action: string) {
		if (action === "analyze-person-edit-metadata") {
			return personEditPlansDir();
		}
		if (action === "analyze-reference-video") {
			return referenceEditProfilePath();
		}
		if (action === "auto-sync-dropped") {
			return syncReportPath();
		}
		if (action === "transcribe-dropped") {
			return joinPath(activeOutputRoot() || "output", "transcripts", "manifest_sources");
		}
		if (action === "build-timeline" || action === "validate-timeline") {
			return timelineOutputPath() || activeOutputRoot();
		}
		if (action === "export-otio" || action === "import-otio") {
			return joinPath(activeOutputRoot() || "output", "timelines");
		}
		if (
			action === "detect-changed-regions" ||
			action === "export-changed-region-commands" ||
			action === "export-changed-region-remotion-commands" ||
			action === "export-changed-region-blender-commands" ||
			action === "export-changed-region-remotion-and-blender-commands"
		) {
			return rendererCommandOutputPath() || activeOutputRoot();
		}
		if (
			action === "export-ffmpeg-command" ||
			action === "export-ffmpeg-preview-command" ||
			action === "export-ffmpeg-preview-with-remotion-overlays" ||
			action === "export-ffmpeg-with-remotion-overlays" ||
			action === "export-ffmpeg-preview-with-blender-elements" ||
			action === "export-ffmpeg-preview-with-remotion-and-blender" ||
			action === "export-ffmpeg-with-blender-elements" ||
			action === "export-ffmpeg-with-remotion-and-blender" ||
			action === "export-remotion-command" ||
			action === "render-remotion-layers" ||
			action === "export-hyperframes-command" ||
			action === "render-hyperframes-layers" ||
			action === "export-blender-command" ||
			action === "render-blender-elements"
		) {
			return rendererCommandOutputPath() || activeOutputRoot();
		}
		if (
			action === "render-timeline-ffmpeg" ||
			action === "render-changed-regions" ||
			action === "render-changed-regions-with-remotion-overlays" ||
			action === "render-changed-regions-with-blender-elements" ||
			action === "render-changed-regions-with-remotion-and-blender" ||
			action === "render-preview-with-remotion-overlays" ||
			action === "render-final-with-remotion-overlays" ||
			action === "render-preview-with-blender-elements" ||
			action === "render-preview-with-remotion-and-blender" ||
			action === "render-final-with-blender-elements" ||
			action === "render-final-with-remotion-and-blender"
		) {
			return outputPathValue() || activeOutputRoot();
		}
		if (action === "generate-proxies") {
			return proxyOutputPath() || joinPath(activeOutputRoot() || "output", "proxy");
		}
		if (action === "generate-music-bed") {
			return musicBedPath();
		}
		if (action === "replace-audio") {
			return outputPathValue() || activeOutputRoot();
		}
		if (action === "generate-thumbnail") {
			return thumbnailOutputPath();
		}
		if (action === "generate-thumbnail-candidates") {
			return thumbnailCandidatesOutputPath();
		}
		if (action === "review-subtitles") {
			return subtitleReviewOutputPath();
		}
		if (action === "apply-subtitle-corrections") {
			return subtitleCorrectionsOutputPath();
		}
		if (action === "classify-subtitle-speakers") {
			return subtitleSpeakerRolesOutputPath();
		}
		if (action === "compare-transcripts") {
			return transcriptComparisonOutputPath();
		}
		return outputPathValue() || activeOutputRoot();
	}

	function handleWorkflowProgress(payload: any) {
		if (!state.directRunRunning || payload?.action !== state.runningAction) {
			return;
		}
		const path = directRunOutputPath(state.runningAction);
		setIngestProgress({
			progress: Number(payload.progress) || 0,
			message: payload.message || t("format.runningMessage", { label: directRunLabel(state.runningAction) }),
			path,
		});
		const progress = Number(payload.progress) || 0;
		if (
			payload.stage !== state.lastWorkflowStage ||
			progress - state.lastWorkflowProgressLog >= 0.05 ||
			progress >= 1
		) {
			state.lastWorkflowStage = payload.stage || "";
			state.lastWorkflowProgressLog = progress;
			log("workflow progress", {
				action: payload.action,
				stage: payload.stage,
				progress: progressPercent(progress),
				message: payload.message,
			});
		}
	}

	function quoteArg(arg) {
		if (/^[A-Za-z0-9_./:=+-]+$/.test(arg)) {
			return arg;
		}
		return `"${arg.replace(/"/g, '\\"')}"`;
	}

	function refreshCommand() {
		const { command, reason } = buildPresetCommand();
		getAppState().setRunPreviewText({
			commandPreviewText: command ? command.map(quoteArg).join(" ") : reason,
		});
	}

	function validateSelections() {
		const errors = [];
		const warnings = [];
		const ok = [];
		const action = formValue("workflowAction");
		const script = formValue("renderScript");
		const outputPath = outputPathValue();
		const inputVideo = inputVideoPathValue().trim();
		const cameras = manifestCameras();
		const audioSources = manifestAudioSources();
		const masterVideo = selectedMasterVideoPath();

		const projectDraft = getAppState().projectDraft;
		if (!state.project && !projectDraft.name && !projectDraft.id) {
			errors.push(t("validation.projectRequired"));
		}

		if (action === "render-selected") {
			if (!outputPath) {
				errors.push(t("validation.outputRequired"));
			} else {
				ok.push(t("validation.output", { path: shortPath(outputPath) }));
			}
			if (script === "render_multicam.py" || script === "render_app_interview.py") {
				if (!masterVideo) {
					errors.push(t("validation.masterRequiredForMulticam"));
				}
				if (cameras.length <= 1 && !state.files.rightCloseVideo && !state.files.leftCloseVideo) {
					warnings.push(t("validation.singleCameraWarning"));
				}
				if (cameras.length > 1 || state.files.rightCloseVideo || state.files.leftCloseVideo) {
					warnings.push(t("validation.syncFirstWarning"));
				}
			}
			if (formValue("shortenSilence")) {
				warnings.push(t("validation.shortenSilenceWarning"));
			}
		}

		if (action === "generate-proxies") {
			if (!activeOutputRoot()) {
				errors.push(t("validation.projectRequired"));
			}
			if (!cameras.length) {
				errors.push("Generate proxies requires an ingested media manifest with camera videos.");
			}
			if (proxyOutputPath()) {
				ok.push(`Proxy output: ${shortPath(proxyOutputPath())}`);
			}
			if (cameras.length) {
				ok.push(`Proxy targets: ${cameras.length} camera video(s)`);
			}
		}

		if (action === "auto-sync-dropped") {
			if (!masterVideo) {
				errors.push(t("validation.masterRequiredForSync"));
			}
			if (
				cameras.length <= 1 &&
				!state.files.rightCloseVideo &&
				!state.files.leftCloseVideo &&
				!state.files.externalAudio &&
				!audioSources.length
			) {
				errors.push(t("validation.syncTargetsRequired"));
			}
			ok.push(t("validation.syncSaved"));
		}

		if (state.files.stillImages.length) {
			ok.push(t("validation.stillCount", { count: state.files.stillImages.length }));
			ok.push(t("validation.stillMotion"));
		}

		if (action === "analyze-person-edit-metadata") {
			const videos = selectedAnalysisVideos();
			ok.push(t("validation.personBbox", { path: shortPath(personBboxesDir()) }));
			ok.push(t("validation.editPlan", { path: shortPath(personEditPlansDir()) }));
			ok.push(t("validation.analysisFps", { fps: formValue("personFpsSample") }));
			if (videos.length) {
				ok.push(t("validation.selectedVideos", { count: videos.length }));
			} else {
				ok.push(t("validation.sourceRoots"));
			}
			if (formValue("personMaxSeconds")) {
				warnings.push(t("validation.testAnalysis"));
			}
		}

		if (action === "analyze-reference-video") {
			if (!state.files.referenceVideo) {
				errors.push(t("validation.referenceRequired"));
			}
			ok.push(t("validation.referenceShort"));
			ok.push(t("validation.referenceProfile", { path: shortPath(referenceEditProfilePath()) }));
			ok.push(t("validation.referenceBbox", { path: shortPath(referencePersonBboxesDir()) }));
			ok.push(t("validation.referenceEditPlan", { path: shortPath(referenceEditPlansDir()) }));
		}

		if (action === "shorten-input" && (!inputVideo || !outputPath)) {
			errors.push(t("validation.shortenNeedsInputOutput"));
		}
		if (["extract-still", "verify-duration", "verify-audio"].includes(action) && !inputVideo) {
			errors.push(t("validation.verificationNeedsInput"));
		}
		if (action === "generate-thumbnail") {
			if (!thumbnailInputPath()) {
				errors.push(t("validation.thumbnailNeedsInput"));
			}
			if (thumbnailOutputPath()) {
				ok.push(t("validation.thumbnailOutput", { path: shortPath(thumbnailOutputPath()) }));
			}
		}
		if (action === "generate-thumbnail-candidates") {
			if (!hasThumbnailCandidateSource()) {
				errors.push(t("validation.thumbnailCandidatesNeedsInput"));
			}
			if (thumbnailCandidatesOutputPath()) {
				ok.push(t("validation.thumbnailCandidatesOutput", { path: shortPath(thumbnailCandidatesOutputPath()) }));
				ok.push(
					t("validation.thumbnailCandidateSettings", {
						count: formValue("thumbnailCandidateCount") || 6,
						mode: selectedLabel("thumbnailMode") || formValue("thumbnailMode"),
						color: selectedLabel("thumbnailMainColor") || formValue("thumbnailMainColor"),
					}),
				);
				if (formValue("thumbnailDebugFaces")) {
					ok.push(t("validation.thumbnailDebugFaces"));
				}
			}
		}
		if (action === "review-subtitles") {
			if (!activeOutputRoot()) {
				errors.push(t("validation.subtitleReviewNeedsProject"));
			} else {
				ok.push(t("validation.subtitleReviewOutput", { path: shortPath(subtitleReviewOutputPath()) }));
				if (formValue("subtitleReviewExtractClips") || formValue("subtitleReviewTranscribeClips")) {
					ok.push(t("validation.subtitleReviewClips", { path: shortPath(subtitleReviewClipsPath()) }));
				}
				if (formValue("subtitleReviewTranscribeClips")) {
					ok.push(t("validation.subtitleReviewRetranscribe"));
				}
			}
		}
		if (action === "apply-subtitle-corrections") {
			if (!activeOutputRoot()) {
				errors.push(t("validation.subtitleReviewNeedsProject"));
			}
			if (!hasSubtitleCorrections()) {
				errors.push(t("validation.subtitleCorrectionsMissing"));
			}
			if (subtitleCorrectionsOutputPath()) {
				ok.push(t("validation.subtitleCorrectionsOutput", { path: shortPath(subtitleCorrectionsOutputPath()) }));
			}
		}
		if (action === "classify-subtitle-speakers") {
			if (!activeOutputRoot()) {
				errors.push(t("validation.subtitleReviewNeedsProject"));
			}
			if (!hasSubtitleSpeakerRules()) {
				warnings.push(t("validation.subtitleSpeakerRulesMissing"));
			}
			if (subtitleSpeakerRolesOutputPath()) {
				ok.push(t("validation.subtitleSpeakerRolesOutput", { path: shortPath(subtitleSpeakerRolesOutputPath()) }));
			}
			if (String(formValue("subtitleManualRoles") || "").trim()) {
				ok.push(t("validation.subtitleSpeakerManualRoles"));
			}
			if (formValue("subtitleMouthMotionDiagnostics")) {
				ok.push(t("validation.subtitleSpeakerMouthMotion"));
			}
		}
		if (action === "compare-transcripts") {
			if (!activeOutputRoot()) {
				errors.push(t("validation.subtitleReviewNeedsProject"));
			}
			if (transcriptComparisonOutputPath()) {
				ok.push(t("validation.transcriptComparisonOutput", { path: shortPath(transcriptComparisonOutputPath()) }));
			}
		}
		if (action === "replace-audio") {
			const replacementAudio = audioSources[0]?.path || state.files.externalAudio;
			if (!inputVideo || !outputPath) {
				errors.push(t("validation.replaceAudioNeedsInputOutput"));
			} else {
				ok.push(t("validation.replaceAudioOutput", { path: shortPath(outputPath) }));
				if (inputVideo === outputPath) {
					errors.push(t("validation.replaceAudioSamePath"));
				}
			}
			if (!replacementAudio) {
				errors.push(t("validation.replaceAudioNeedsExternal"));
			} else {
				ok.push(t("validation.replaceAudioSource", { path: shortPath(replacementAudio) }));
			}
		}

		const audioSource = formValue("audioSource");
		if (audioSource === "external-if-selected") {
			const external = audioSources[0]?.path || state.files.externalAudio;
			if (external) {
				ok.push(t("validation.audioExternal", { path: shortPath(external) }));
			} else {
				warnings.push(t("validation.audioFallbackMaster"));
			}
		}
		if (audioSource === "rightCloseVideo" && !state.files.rightCloseVideo) {
			warnings.push(t("validation.rightAudioFallback"));
		}
		if (audioSource === "leftCloseVideo" && !state.files.leftCloseVideo) {
			warnings.push(t("validation.leftAudioFallback"));
		}

		ok.push(t("validation.workflow", { label: selectedLabel("workflowAction") }));
		ok.push(
			t("validation.transcribe", {
				model: formValue("transcribeModel") || "large-v3",
				language: formValue("transcribeLanguage") || "ja",
			}),
		);
		ok.push(t("validation.subtitle", { mode: subtitleModeLabel() }));
		ok.push(
			formValue("termExplanations")
				? t("validation.termsOn", { count: glossaryTerms().filter((term) => term.enabled).length })
				: t("validation.termsOff"),
		);
		ok.push(
			formValue("audioDenoise")
				? t("validation.denoiseOn", { strength: formValue("audioDenoiseStrength") })
				: t("validation.denoiseOff"),
		);
		ok.push(formValue("colorMatchCameras") ? t("validation.colorMatchOn") : t("validation.colorMatchOff"));
		ok.push(formValue("usePersonEditPlans") ? t("validation.personCropOn") : t("validation.personCropOff"));
		ok.push(
			formValue("useTranscriptComparisonSync") ? t("validation.transcriptSyncOn") : t("validation.transcriptSyncOff"),
		);
		ok.push(formValue("naturalDialogueCuts") ? t("validation.naturalCutsOn") : t("validation.naturalCutsOff"));
		ok.push(formValue("audioMastering") ? t("validation.audioMasteringOn") : t("validation.audioMasteringOff"));
		ok.push(
			t("validation.encoder", {
				preset: selectedLabel("encoderPreset") || formValue("encoderPreset") || "veryfast",
				crf: formValue("renderCrf") || 18,
			}),
		);
		if (formValue("musicEnabled")) {
			const volume = Number(formValue("musicVolume") || 14);
			if (formValue("musicScope") === "omission") {
				ok.push(t("validation.musicOmission", { volume }));
				if (formValue("musicRangeSource") === "manual") {
					ok.push(t("validation.musicManualRanges"));
				} else {
					ok.push(t("validation.musicAutoRanges"));
				}
				if (formValue("musicRangeSource") === "manual" && !hasMusicRanges()) {
					warnings.push(t("validation.musicRangesMissing"));
				}
			} else {
				ok.push(t("validation.musicFull", { volume }));
			}
		} else {
			ok.push(t("validation.musicOff"));
		}
		if (formValue("omissionCardEnabled")) {
			ok.push(t("validation.omissionCardOn", { duration: formValue("omissionCardDuration") || 5 }));
			if (!hasOmissionCardRanges()) {
				warnings.push(t("validation.omissionCardMissingRanges"));
			}
		} else {
			ok.push(t("validation.omissionCardOff"));
		}
		ok.push(formValue("shortenSilence") ? t("validation.silenceOn") : t("validation.silenceOff"));
		const syncRows = describeSyncReport();
		if (syncRows.length) {
			const weakest = syncRows.reduce((min, row) => (row.score < min.score ? row : min), syncRows[0]);
			ok.push(t("validation.previousSync", { role: weakest.role, score: weakest.score.toFixed(3) }));
			if (weakest.score < 0.65) {
				warnings.push(t("validation.lowSyncScore"));
			}
		}
		return { errors, warnings, ok };
	}

	function updateRunSummary() {
		const validation = validateSelections();
		const items: RunChecklistItem[] = [
			...validation.errors.map((text) => ({ text: String(text), kind: "error" as const })),
			...validation.warnings.map((text) => ({ text: String(text), kind: "warn" as const })),
			...validation.ok.slice(0, 5).map((text) => ({ text: String(text), kind: "ok" as const })),
		];
		patchAppState({ runChecklist: items });
	}

	function buildPrompt() {
		const outputPath = outputPathValue() || "(choose an output path under the video_edit folder)";
		const lines = [
			"You are working in C:\\Users\\yurin\\Desktop\\video_edit.",
			"Create or run the video edit requested by the Electron operator UI.",
			"",
			"Use the existing pipeline and docs first:",
			"- Use the selected media manifest as the source of truth for cameras, audio, images, and subtitles.",
			"- Use scripts\\build_edit_timeline.py to express edit decisions as renderer-agnostic timeline JSON.",
			"- Use scripts\\timeline_validate.py before rendering; invalid timelines must be fixed before adapters run.",
			"- Use scripts\\ffmpeg_timeline_adapter.py to export audited FFmpeg commands, including preview/proxy commands, from a validated timeline.",
			"- Use scripts\\timeline_graphics_adapter.py to export audited Remotion, HyperFrames, or Blender layer/job commands from a validated timeline.",
			"- Use scripts\\render_multicam.py as the shared FFmpeg-backed fallback when a timeline adapter path cannot cover the requested workflow.",
			"- Before project-specific editing, read the active project's VIDEO_EDITING_INSTRUCTIONS.md and inspect projects\\<project-id>\\scripts for project-local automation.",
			"- Do not change shared app scripts to satisfy a one-off project requirement; put project-specific code under the active project's scripts directory.",
			"- Use scripts\\analyze_person_edit_metadata.py before edit planning when person position/crop decisions matter.",
			"- If a reference video is selected, analyze it first and use output\\reports\\reference_edit_profile.json as the style/layout target.",
			"- Treat the material directory as cameras/audio/images/logo/subtitles only; reference video is selected separately.",
			"- Keep existing user changes in the repo; do not revert unrelated files.",
			"",
			"Operator selections:",
			`- Edit preset: ${formValue("editPreset")}`,
			`- Direct workflow action: ${formValue("workflowAction")}`,
			`- Transcribe settings: model ${formValue("transcribeModel") || "large-v3"}, language ${formValue("transcribeLanguage") || "ja"}, beam ${formValue("transcribeBeamSize") || "5"}, temperature ${formValue("transcribeTemperature") || "0"}, loudnorm ${formValue("transcribeNormalizeAudio")}, low-confidence filter ${formValue("transcribeFilterLowConfidence")}, previous-text context ${formValue("conditionOnPreviousText")}`,
			`- Transcribe prompt terms: ${formValue("transcribePromptTerms") || "(use glossary terms only)"}`,
			`- Person analysis: ${formValue("personFpsSample")} fps, model ${formValue("personModel")}, confidence ${formValue("personConfidence")}, max seconds ${formValue("personMaxSeconds") || "all"}, limit ${formValue("personLimit") || "all"}`,
			`- Reference video: ${state.files.referenceVideo || "(not selected)"}`,
			`- Reference profile: ${referenceEditProfilePath()}`,
			`- Render script: ${formValue("renderScript")}`,
			`- Render profile: ${formValue("renderProfile") || "final"}`,
			`- Render range mode: ${formValue("rangeMode") || "range"}`,
			`- Multicam mode: ${formValue("multicamMode")}`,
			`- Subtitle mode: ${state.subtitleMode}`,
			`- Audio source: ${formValue("audioSource")}`,
			`- Audio denoise: ${formValue("audioDenoise")} strength ${formValue("audioDenoiseStrength")}`,
			`- Audio mastering: ${formValue("audioMastering")}`,
			`- Encoder: preset ${formValue("encoderPreset") || "veryfast"}, CRF ${formValue("renderCrf") || "18"}`,
			`- Camera color match: ${formValue("colorMatchCameras")}`,
			`- Global video zoom: ${formValue("globalVideoZoom") || "1.2"}x`,
			`- Person-aware crop from analysis: ${formValue("usePersonEditPlans")}`,
			`- Transcript comparison sync fallback: ${formValue("useTranscriptComparisonSync")}`,
			`- Natural dialogue camera cuts: ${formValue("naturalDialogueCuts")}`,
			`- Music: enabled ${formValue("musicEnabled")}, placement ${formValue("musicScope")}, range source ${formValue("musicRangeSource") || "auto"}, level ${formValue("musicVolume")}%, direction ${formValue("musicPrompt") || "(auto from title/transcript)"}`,
			`- Music omission ranges: ${formValue("musicRangesText") || "(none)"}`,
			`- Omission card replacement: enabled ${formValue("omissionCardEnabled")}, duration ${formValue("omissionCardDuration") || "5"}s, label ${formValue("omissionCardLabel") || "SUMMARY"}`,
			`- Omission card text: ${formValue("omissionCardText") || "(default)"}`,
			`- Omission card replacement ranges: ${formValue("omissionCardRangesText") || formValue("musicRangesText") || "(none)"}`,
			`- Thumbnail: input ${thumbnailInputPath() || "(auto from current project)"}, time ${formValue("thumbnailTime") || formValue("stillTime") || "00:00:25"}, title ${formValue("thumbnailTitle") || state.analysisTitleText || "(analysis empty)"}, subtitle ${formValue("thumbnailSubtitle") || "(none)"}`,
			`- Thumbnail candidates: count ${formValue("thumbnailCandidateCount") || "6"}, mode ${formValue("thumbnailMode") || "standard"}, color ${formValue("thumbnailMainColor") || "yellow"}, debug faces ${formValue("thumbnailDebugFaces")}, times ${formValue("thumbnailCandidateTimes") || "(auto from project images/video)"}`,
			`- Subtitle QA thresholds: max segment ${formValue("subtitleReviewMaxDuration") || "8"}s, max reading speed ${formValue("subtitleReviewMaxCharsPerSecond") || "18"} chars/s`,
			`- Subtitle suspicious patterns: ${formValue("subtitleSuspiciousPatterns") || "(none)"}`,
			`- Subtitle QA audio clips: extract ${formValue("subtitleReviewExtractClips")}, re-transcribe ${formValue("subtitleReviewTranscribeClips")}`,
			`- Subtitle corrections: ${formValue("subtitleCorrectionsText") || "(none)"}`,
			`- Subtitle offscreen-speaker ranges: ${formValue("subtitleInterviewerRanges") || "(none)"}`,
			`- Subtitle offscreen-speaker patterns: ${formValue("subtitleInterviewerPatterns") || "(none)"}`,
			`- Subtitle manual speaker roles: ${formValue("subtitleManualRoles") || "(none)"}`,
			`- Subtitle mouth-motion diagnostic: ${formValue("subtitleMouthMotionDiagnostics")}`,
			`- Transcript comparison report: ${transcriptComparisonOutputPath() || "(project output not set)"}`,
			`- Timeline JSON: ${timelineOutputPath() || "(project output not set)"}`,
			"- Timeline schema: config\\timeline.schema.json",
			`- Preview start: ${formValue("previewStart")} seconds`,
			`- Output duration: ${formValue("previewDuration")} seconds`,
			`- Shorten long silence: ${formValue("shortenSilence")}`,
			`- Silence options: min ${formValue("minSilence")}s, keep ${formValue("keepSilence")}s, noise ${formValue("silenceNoise")}, keep uncut ${formValue("keepUncut")}`,
			"- Regenerate text overlays from current analysis: true",
			`- Term explanations: ${formValue("termExplanations")} (${
				glossaryTerms()
					.filter((term) => term.enabled)
					.map((term) => term.label)
					.join(", ") || "none"
			})`,
			`- Output path: ${outputPath}`,
			`- Active project: ${state.project ? `${state.project.name} (${state.project.root})` : "(none; using workspace defaults)"}`,
			`- AI-editable project state: ${state.projectStatePath || "(project not saved yet)"}`,
			`- Project source root: ${activeSourceRoot() || "(not set)"}`,
			`- Project output root: ${activeOutputRoot() || "(not set)"}`,
			`- Material sources: ${state.materialPaths.length ? state.materialPaths.join("; ") : state.mediaDirectory || "(not ingested)"}`,
			`- Media manifest: ${mediaManifestPath() || "(not generated)"}`,
			`- Manifest cameras: ${
				manifestCameras()
					.map((item) => `${item.role}=${item.path}`)
					.join("; ") || "(none)"
			}`,
			`- Manifest audio: ${
				manifestAudioSources()
					.map((item) => `${item.role}=${item.path}`)
					.join("; ") || "(none)"
			}`,
			`- Still extraction time: ${formValue("stillTime") || "00:00:25"}`,
			`- Person bbox output: ${personBboxesDir()}`,
			`- Person edit plan output: ${personEditPlansDir()}`,
			`- Reference person edit plan output: ${referenceEditPlansDir()}`,
			`- Python: ${pythonExe()}`,
			`- FFmpeg: ${ffmpegExe()}`,
			`- FFprobe: ${ffprobeExe()}`,
			"",
			"Dropped assets:",
			`- Master/day video: ${state.files.masterVideo || "(none)"}`,
			`- Right close-up/person 1: ${state.files.rightCloseVideo || "(none)"}`,
			`- Left close-up/person 2: ${state.files.leftCloseVideo || "(none)"}`,
			`- Reference style video: ${state.files.referenceVideo || "(not selected)"}`,
			`- External audio: ${state.files.externalAudio || "(not selected)"}`,
			`- Logo: ${state.files.logo || "(none)"}`,
			`- Still image inserts: ${state.files.stillImages.length ? state.files.stillImages.join(", ") : "(none)"}`,
			"",
			"Style selections:",
			`- Subtitle font size target: ${formValue("subtitleSize")}`,
			`- Subtitle highlight color: ${formValue("highlightColor")}`,
			`- Subtitle box opacity: ${formValue("boxOpacity")} percent`,
			`- Top-left text: ${state.analysisTitleText}`,
			`- Top-left text size: ${formValue("titleSize")}`,
			`- Right-top logo height: ${formValue("logoHeight")} px`,
			`- Punchline list:\n${getAppState().punchlineText || "(empty)"}`,
			"",
			"Expected behavior:",
			"- To change operator options, update the AI-editable project_state.json file. The app treats it as the project-level source of truth and reloads it while this project is active.",
			"- Keep generated reports, transcripts, and media files in their existing output folders; keep project_state.json focused on options and selected project state.",
			"- If external audio is selected, sync it or clearly report if existing offset data cannot be reused.",
			"- If no external audio is selected, use the selected camera audio source.",
			"- Prefer the media manifest for source roles. Support variable dialogue/multicam camera roles: master, camera2, camera3, camera4+.",
			"- For person-aware crop/cut planning, analyze source videos first, then use output\\reports\\person_edit_plans as metadata for camera/crop decisions.",
			"- When multicam mode is dynamic-cuts, build short current-project camera segments and punch-in reframes; do not use historical fixed camera timings.",
			"- Respect each camera source's synced coverage; do not use alternate-camera clips outside their valid timeline range.",
			"- For weak or missing waveform sync, use only the current transcript comparison report when its media-manifest fingerprint matches the active project.",
			"- When natural dialogue cuts are enabled, move camera boundaries only to nearby low-energy dialogue gaps; do not change audio timing.",
			"- When audio mastering is enabled, apply the common high-pass, noise reduction, dynamics, and loudness chain to the selected project audio.",
			"- When replacing video audio, copy the selected input video's video stream and use only the current project external audio plus current sync report.",
			"- Reflect the reference profile in the edit: match person size, layout, face direction when possible, and visual tone (brightness, contrast, saturation, warmth).",
			"- For full subtitles, use only the current transcription result for the selected media manifest.",
			"- For source transcript comparison, compare only the current project transcript manifest and write the report under output\\reports.",
			"- For subtitle QA audio clips, use only the current project primary transcript/audio and write clips under output\\diagnostics.",
			"- For catchy subtitles, use the punchline overlay mode.",
			"- Editing decisions must be expressed as validated timeline JSON, not raw FFmpeg commands.",
			"- Build or update the timeline JSON first, validate it, then let renderer adapters generate technical commands.",
			"- If rendering is blocked, report the validation error or missing input instead of hand-writing a renderer command.",
			"- Report the output file path and any limitations.",
		];
		return lines.join("\n");
	}

	function buildAppConfig() {
		const analysisTitleText = state.analysisTitleText;
		return {
			project: {
				id: state.project?.id || "",
				name: state.project?.name || "",
				root: state.project?.root || "",
				sourceRoot: activeSourceRoot(),
				outputRoot: activeOutputRoot(),
			},
			assets: {
				mediaDirectory: state.mediaDirectory,
				materialPaths: state.materialPaths,
				mediaManifestPath: mediaManifestPath(),
				mediaManifest: state.mediaManifest,
				masterVideo: state.files.masterVideo,
				rightCloseVideo: state.files.rightCloseVideo,
				leftCloseVideo: state.files.leftCloseVideo,
				referenceVideo: state.files.referenceVideo,
				externalAudio: state.files.externalAudio,
				logo: state.files.logo,
				stillImages: state.files.stillImages,
				sourceRoot: activeProjectVideoSourceRoot(),
			},
			render: {
				editPreset: formValue("editPreset"),
				workflowAction: formValue("workflowAction"),
				renderScript: formValue("renderScript"),
				outputPath: outputPathValue(),
				timelinePath: timelineOutputPath(),
				syncOffsetsPath: syncReportPath(),
				subtitleMode: state.subtitleMode,
				renderProfile: formValue("renderProfile") || "final",
				rangeMode: formValue("rangeMode") || "range",
				multicamMode: formValue("multicamMode"),
				audioSource: formValue("audioSource"),
				audioDenoise: formValue("audioDenoise"),
				audioDenoiseStrength: Number(formValue("audioDenoiseStrength") || 10),
				audioMastering: formValue("audioMastering"),
				encoderPreset: formValue("encoderPreset") || "veryfast",
				crf: Number(formValue("renderCrf") || 18),
				colorMatchCameras: formValue("colorMatchCameras"),
				globalVideoZoom: Number(formValue("globalVideoZoom") || 1.2),
				usePersonEditPlans: formValue("usePersonEditPlans"),
				useTranscriptComparisonSync: formValue("useTranscriptComparisonSync"),
				naturalDialogueCuts: formValue("naturalDialogueCuts"),
				previewStart: Number(formValue("previewStart") || 0),
				previewDuration: Number(formValue("previewDuration") || 60),
				termExplanations: formValue("termExplanations"),
				shortenSilence: formValue("shortenSilence"),
				minSilence: Number(formValue("minSilence") || 3),
				keepSilence: Number(formValue("keepSilence") || 2),
				silenceNoise: formValue("silenceNoise") || "-30dB",
				keepUncut: formValue("keepUncut"),
			},
			music: {
				enabled: formValue("musicEnabled"),
				scope: formValue("musicScope") || "full",
				rangeSource: formValue("musicRangeSource") || "auto",
				prompt: formValue("musicPrompt"),
				mood: "auto",
				volume: Number(formValue("musicVolume") || 14),
				rangesText: formValue("musicRangesText"),
				regenerate: true,
				outputPath: musicBedPath(),
			},
			omissionCard: {
				enabled: formValue("omissionCardEnabled"),
				duration: Number(formValue("omissionCardDuration") || 5),
				label: formValue("omissionCardLabel") || "SUMMARY",
				text: formValue("omissionCardText"),
				rangesText: formValue("omissionCardRangesText") || formValue("musicRangesText"),
				useMusicRanges: true,
				outputPath: omissionCardOutputPath(),
			},
			thumbnail: {
				inputVideoPath: thumbnailInputPath(),
				time: formValue("thumbnailTime") || formValue("stillTime") || "00:00:25",
				title: formValue("thumbnailTitle") || analysisTitleText,
				subtitle: formValue("thumbnailSubtitle"),
				outputPath: thumbnailOutputPath(),
				candidatesOutputDir: thumbnailCandidatesOutputPath(),
				candidateCount: Number(formValue("thumbnailCandidateCount") || 6),
				mode: formValue("thumbnailMode") || "standard",
				mainColor: formValue("thumbnailMainColor") || "yellow",
				candidateTimesText: formValue("thumbnailCandidateTimes"),
				debugFaces: formValue("thumbnailDebugFaces"),
			},
			subtitleReview: {
				outputPath: subtitleReviewOutputPath(),
				maxDuration: Number(formValue("subtitleReviewMaxDuration") || 8),
				maxCharsPerSecond: Number(formValue("subtitleReviewMaxCharsPerSecond") || 18),
				suspiciousPatternsText: formValue("subtitleSuspiciousPatterns"),
				extractAudioClips: formValue("subtitleReviewExtractClips") || formValue("subtitleReviewTranscribeClips"),
				transcribeReview: formValue("subtitleReviewTranscribeClips"),
				reviewModel: formValue("transcribeModel") || "large-v3",
				correctionsText: formValue("subtitleCorrectionsText"),
				correctionsOutputPath: subtitleCorrectionsOutputPath(),
			},
			subtitleSpeakers: {
				outputPath: subtitleSpeakerRolesOutputPath(),
				interviewerRangesText: formValue("subtitleInterviewerRanges"),
				interviewerPatternsText: formValue("subtitleInterviewerPatterns"),
				manualRolesText: formValue("subtitleManualRoles"),
				mouthMotionDiagnostics: formValue("subtitleMouthMotionDiagnostics"),
				motionVideoPath: inputVideoPathValue() || outputPathValue() || selectedMasterVideoPath(),
			},
			transcriptComparison: {
				outputPath: transcriptComparisonOutputPath(),
				strongThreshold: 0.82,
				usableThreshold: 0.7,
				matchLimit: 12,
			},
			workflow: {
				inputVideoPath: inputVideoPathValue(),
				stillTime: formValue("stillTime") || "00:00:25",
				stillOutputPath: stillOutputPath(inputVideoPathValue() || outputPathValue(), outputPathValue()),
			},
			replaceAudio: {
				inputVideoPath: inputVideoPathValue(),
				audioPath: state.files.externalAudio || manifestAudioSources()[0]?.path || "",
				outputPath: outputPathValue(),
				syncOffsetsPath: syncReportPath(),
			},
			analysis: {
				transcribeModel: formValue("transcribeModel") || "large-v3",
				transcribeLanguage: formValue("transcribeLanguage") || "ja",
				transcribeBeamSize: Number(formValue("transcribeBeamSize") || 5),
				transcribeTemperature: Number(formValue("transcribeTemperature") || 0),
				transcribePromptTerms: formValue("transcribePromptTerms"),
				transcribeNormalizeAudio: formValue("transcribeNormalizeAudio"),
				transcribeFilterLowConfidence: formValue("transcribeFilterLowConfidence"),
				conditionOnPreviousText: formValue("conditionOnPreviousText"),
				personFpsSample: Number(formValue("personFpsSample") || 1),
				personModel: formValue("personModel") || "yolov8n.pt",
				personConfidence: Number(formValue("personConfidence") || 0.35),
				personMaxSeconds: formValue("personMaxSeconds") ? Number(formValue("personMaxSeconds")) : null,
				personLimit: formValue("personLimit") ? Number(formValue("personLimit")) : null,
				personNoMulticamRoot: formValue("personNoMulticamRoot"),
				personBboxesDir: personBboxesDir(),
				personEditPlansDir: personEditPlansDir(),
				referencePersonBboxesDir: referencePersonBboxesDir(),
				referenceEditPlansDir: referenceEditPlansDir(),
				referenceEditProfilePath: referenceEditProfilePath(),
			},
			style: {
				subtitleSize: Number(formValue("subtitleSize") || 80),
				highlightColor: formValue("highlightColor"),
				boxOpacity: Number(formValue("boxOpacity") || 72),
				titleText: analysisTitleText,
				titleSize: Number(formValue("titleSize") || 64),
				logoHeight: Number(formValue("logoHeight") || 48),
				punchlineText: getAppState().punchlineText,
			},
			glossary: {
				enabled: formValue("termExplanations"),
				terms: glossaryTerms(),
			},
			editRequest: {
				...(state.editRequest || {}),
				instructionHistory: [...(state.editRequest?.instructionHistory || [])],
			},
			tools: {
				python: pythonExe(),
				ffmpeg: ffmpegExe(),
				ffprobe: ffprobeExe(),
			},
		};
	}

	function refreshPrompt() {
		refreshCommand();
		updateRunSummary();
		getAppState().setRunPreviewText({ promptPreviewText: buildPrompt() });
		saveState();
	}

	async function runSimpleTranscription() {
		if (!(await prepareProjectForRun())) {
			setStatus(t("status.projectError"), "idle");
			return false;
		}
		if (!state.mediaManifest?.files?.length) {
			setStatus("文字起こし対象の素材がありません", "idle");
			log("transcription skipped", { reason: "media manifest is empty" });
			return false;
		}
		const action = "transcribe-dropped";
		const label = directRunLabel(action);
		state.runningAction = action;
		state.lastWorkflowProgressLog = 0;
		state.lastWorkflowStage = "";
		getAppState().setWorkflowSettings({ workflowAction: action });
		await persistProjectStateFileNow();
		setDirectRunRunning(true, label);
		setAppLocked(true, t("format.runningMessage", { label }), t("analysis.statusRunning"));
		setStatus(t("status.presetRunning"), "busy");
		setIngestProgress({
			progress: 0.01,
			message: t("format.startingMessage", { label }),
			path: directRunOutputPath(action),
		});
		log("workflow/transcribe", { action });
		try {
			const result = await editApp.runWorkflowAction({
				action,
				timeoutMs: 6 * 60 * 60 * 1000,
				appConfig: buildAppConfig(),
			});
			if (result?.stdout) {
				log("stdout", { text: compactOutput(result.stdout) });
			}
			if (result?.stderr) {
				log("stderr", { text: compactOutput(result.stderr) });
			}
			const ok = result?.exitCode === 0;
			if (ok) {
				await restoreAnalysisResultsFromOutputs(state.mediaManifest);
				await refreshTextOverlayFromAnalysis(state.mediaManifest);
				await refreshMaterialAnalysisStatus();
			}
			setIngestProgress({
				progress: ok ? 1 : state.lastWorkflowProgressLog || 0,
				message: ok ? t("format.completeMessage", { label }) : t("format.errorMessage", { label }),
				path: directRunOutputPath(action),
			});
			setStatus(ok ? t("status.runComplete") : t("status.commandFailed"), ok ? "ready" : "idle");
			await persistProjectStateFileNow();
			saveState();
			return ok;
		} catch (error) {
			setStatus(t("status.commandError"), "idle");
			setIngestProgress({
				progress: state.lastWorkflowProgressLog || 0,
				message: t("format.errorMessage", { label }),
				path: directRunOutputPath(action),
			});
			log("transcription error", { message: error.message });
			return false;
		} finally {
			setAppLocked(false);
			setDirectRunRunning(false);
			state.runningAction = "";
		}
	}

	async function sendSimpleEditRequest(mode: "preview" | "final") {
		if (!(await prepareProjectForRun())) {
			setStatus(t("status.projectError"), "idle");
			return;
		}
		if (!state.mediaManifest?.files?.length) {
			setStatus("編集対象の素材がありません", "idle");
			log("codex request blocked", { reason: "media manifest is empty" });
			return;
		}
		const draft = String(state.editRequest?.instructionDraft || "").trim();
		const history = state.editRequest?.instructionHistory || [];
		const previousPreviewPath = state.editRequest?.lastPreviewPath || "";
		const previousFinalPath = state.editRequest?.lastFinalPath || "";
		if (!draft && !history.length) {
			setStatus("自然言語の編集指示を入力してください", "idle");
			log("codex request blocked", { reason: "instruction is empty" });
			return;
		}
		const targetPath = simpleEditOutputPath(mode);
		if (!targetPath) {
			setStatus(t("status.projectError"), "idle");
			log("codex request blocked", { reason: "output root is empty" });
			return;
		}
		setOutputPathValue(targetPath);
		getAppState().setWorkflowSettings({ workflowAction: "render-selected" });
		getAppState().setRenderSettings({
			renderProfile: mode === "preview" ? "preview" : "final",
			rangeMode: mode === "preview" ? "range" : "full",
		});
		const nextHistory = draft
			? [
					...history,
					{
						id: `${mode}-${Date.now()}`,
						mode,
						text: draft,
						targetPath,
						createdAt: new Date().toISOString(),
					},
				]
			: history;
		const prompt = buildSimplePrompt(mode, targetPath, {
			history: nextHistory,
			currentInstruction: draft || history.at(-1)?.text || "",
			previousPreviewPath,
			previousFinalPath,
		});
		setEditRequestState({
			instructionDraft: "",
			instructionHistory: nextHistory,
			...(mode === "preview" ? { lastPreviewPath: targetPath } : { lastFinalPath: targetPath }),
		});
		getAppState().setRunPreviewText({ promptPreviewText: prompt });
		refreshCommand();
		await persistProjectStateFileNow();
		saveState();
		setStatus(t("status.codexRunning"), "busy");
		setCodexTurnRunning(true);
		log("turn/start", { mode, targetPath });
		try {
			state.codexModel = selectedCodexModelForRun();
			await editApp.startCodexTurn({
				settings: {
					model: state.codexModel,
					effort: selectedCodexReasoningEffort(),
				},
				prompt,
			});
		} catch (error) {
			setCodexTurnRunning(false);
			setStatus(t("status.codexError"), "idle");
			log("error", { message: error.message });
		}
	}

	async function runPreset() {
		if (!(await prepareProjectForRun())) {
			setStatus(t("status.projectError"), "idle");
			return false;
		}
		refreshCommand();
		const validation = validateSelections();
		if (validation.errors.length) {
			updateRunSummary();
			setStatus(t("status.checkRequiredFields"), "idle");
			log("direct run blocked", { errors: validation.errors });
			return false;
		}
		const { command, reason } = buildPresetCommand();
		if (!command) {
			log("direct run unavailable", { reason });
			return false;
		}
		await persistProjectStateFileNow();
		const action = formValue("workflowAction");
		const label = directRunLabel(action);
		state.runningAction = action;
		state.lastWorkflowProgressLog = 0;
		state.lastWorkflowStage = "";
		setDirectRunRunning(true, label);
		setAppLocked(
			true,
			t("format.runningMessage", { label }),
			action === "render-selected" ? t("status.rendering") : t("analysis.statusRunning"),
		);
		setStatus(action === "render-selected" ? t("status.rendering") : t("status.presetRunning"), "busy");
		setIngestProgress({
			progress: 0.01,
			message: t("format.startingMessage", { label }),
			path: directRunOutputPath(action),
		});
		log("command/exec", { command });
		try {
			const result = await editApp.runWorkflowAction({
				action,
				timeoutMs: 6 * 60 * 60 * 1000,
				appConfig: buildAppConfig(),
			});
			if (result?.stdout) {
				log("stdout", { text: compactOutput(result.stdout) });
			}
			if (result?.stderr) {
				log("stderr", { text: compactOutput(result.stderr) });
			}
			log("command completed", { exitCode: result?.exitCode });
			if (action === "auto-sync-dropped" && result?.exitCode === 0) {
				await refreshSyncReport();
			}
			if (action === "analyze-person-edit-metadata" && result?.exitCode === 0) {
				log("person analysis outputs", { bboxes: personBboxesDir(), plans: personEditPlansDir() });
				if (result?.manifest) {
					setMediaManifest(result.manifest);
				}
			}
			if (action === "generate-proxies" && result?.exitCode === 0) {
				log("proxy outputs", { output: proxyOutputPath() });
				if (result?.manifest) {
					setMediaManifest(result.manifest);
					await refreshMaterialAnalysisStatus();
				}
			}
			if (action === "analyze-reference-video" && result?.exitCode === 0) {
				log("reference analysis output", { profile: referenceEditProfilePath() });
			}
			const ok = result?.exitCode === 0;
			if (
				ok &&
				[
					"auto-sync-dropped",
					"transcribe-dropped",
					"compare-transcripts",
					"analyze-person-edit-metadata",
					"analyze-blocking",
					"analyze-reference-video",
				].includes(action)
			) {
				await restoreAnalysisResultsFromOutputs(state.mediaManifest);
				await refreshMaterialAnalysisStatus();
			}
			setIngestProgress({
				progress: ok ? 1 : state.lastWorkflowProgressLog || 0,
				message: ok ? t("format.completeMessage", { label }) : t("format.errorMessage", { label }),
				path: directRunOutputPath(action),
			});
			setStatus(ok ? t("status.runComplete") : t("status.commandFailed"), ok ? "ready" : "idle");
			if (ok && action === "render-selected") {
				await notifyAnalysisComplete(t("notification.renderComplete"));
			}
			return ok;
		} catch (error) {
			setStatus(t("status.commandError"), "idle");
			setIngestProgress({
				progress: state.lastWorkflowProgressLog || 0,
				message: t("format.errorMessage", { label }),
				path: directRunOutputPath(action),
			});
			log("command error", { message: error.message });
			return false;
		} finally {
			setAppLocked(false);
			setDirectRunRunning(false);
			state.runningAction = "";
		}
	}

	async function sendRequest() {
		if (!(await prepareProjectForRun())) {
			setStatus(t("status.projectError"), "idle");
			return;
		}
		refreshPrompt();
		await persistProjectStateFileNow();
		setStatus(t("status.codexRunning"), "busy");
		setCodexTurnRunning(true);
		log("turn/start");
		try {
			state.codexModel = selectedCodexModelForRun();
			await editApp.startCodexTurn({
				settings: {
					model: state.codexModel,
					effort: selectedCodexReasoningEffort(),
				},
				prompt: getAppState().promptPreviewText,
			});
		} catch (error) {
			setCodexTurnRunning(false);
			setStatus(t("status.codexError"), "idle");
			log("error", { message: error.message });
		}
	}

	async function stopCodexTurn() {
		if (!state.codexTurnRunning || state.codexInterruptRequested) {
			return;
		}
		state.codexInterruptRequested = true;
		updateCodexRunControls();
		setStatus(t("status.codexStopping"), "busy");
		try {
			await editApp.interruptCodex();
			log("turn/interrupt requested");
		} catch (error) {
			state.codexInterruptRequested = false;
			updateCodexRunControls();
			setStatus(t("status.codexError"), "idle");
			log("turn/interrupt failed", { message: error.message });
		}
	}

	function handleNotification(message) {
		const method = message.method || "notification";
		const params = message.params || {};
		if (method === "item/agentMessage/delta") {
			log("agent", { delta: params.delta || params.text || params });
			return;
		}
		if (method === "item/commandExecution/outputDelta") {
			log("command", { text: params.delta || params.text || params });
			return;
		}
		if (method === "command/exec/outputDelta") {
			log("command", { text: params.delta || params.text || params });
			return;
		}
		if (method === "thread/status/changed" && params.status?.type === "systemError") {
			setCodexTurnRunning(false);
			setStatus(t("status.codexError"), "idle");
			log(method, params);
			return;
		}
		if (method === "turn/completed") {
			const turn = params.turn || {};
			setCodexTurnRunning(false);
			if (turn.status === "failed") {
				setStatus(t("status.codexError"), "idle");
				log("turn failed", { message: codexErrorMessage(turn.error) || "Codex turn failed" });
				return;
			}
			if (turn.status === "interrupted") {
				setStatus(t("status.codexStopped"), "ready");
				log(method, params);
				return;
			}
			setStatus(t("status.codexIdle"), "ready");
			log(method, params);
			return;
		}
		log(method, params);
	}

	return {
		prepareProjectForRun,
		formValue,
		selectedLabel,
		subtitleModeLabel,
		analysisLabel,
		scoreKind,
		describeSyncReport,
		renderSyncReport,
		refreshSyncReport,
		loadGlossaryCandidates,
		refreshTextOverlayFromAnalysis,
		refreshAnalysisTitleFromAnalysis,
		addGlossaryTerm,
		pythonExe,
		ffmpegExe,
		ffprobeExe,
		stillOutputPath,
		personBboxesDir,
		personEditPlansDir,
		referencePersonBboxesDir,
		referenceEditPlansDir,
		referenceEditProfilePath,
		musicBedPath,
		omissionCardOutputPath,
		thumbnailOutputPath,
		thumbnailCandidatesOutputPath,
		subtitleReviewOutputPath,
		subtitleReviewClipsPath,
		subtitleCorrectionsOutputPath,
		subtitleSpeakerRolesOutputPath,
		transcriptComparisonOutputPath,
		transcriptManifestOutputPath,
		blockingMetricsOutputPath,
		analysisOutputCandidates,
		restoreAnalysisResultsFromOutputs,
		restoreProgressFromOutputs,
		hasMusicRanges,
		hasOmissionCardRanges,
		hasSubtitleCorrections,
		hasSubtitleSpeakerRules,
		thumbnailInputPath,
		thumbnailCandidateImageCount,
		hasThumbnailCandidateSource,
		selectedAnalysisVideos,
		withRuntimeConfig,
		scriptPath,
		buildPresetCommand,
		buildActionCommand,
		hasSyncTargets,
		compactOutput,
		directRunLabel,
		directRunOutputPath,
		handleWorkflowProgress,
		quoteArg,
		refreshCommand,
		validateSelections,
		updateRunSummary,
		buildPrompt,
		buildAppConfig,
		refreshPrompt,
		runSimpleTranscription,
		sendSimpleEditRequest,
		runPreset,
		sendRequest,
		stopCodexTurn,
		handleNotification,
	};
}
