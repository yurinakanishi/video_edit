import { editApp } from "./api.js";
import { t } from "./i18n.js";
import { log } from "./log.js";
import { projectIdFromName } from "./preview.js";
import { state } from "./state.js";
import { getAppState } from "./store/app-store.js";
import type { MediaManifest, ProjectInfo } from "./types.js";

type MaterialAnalysisControllerOptions = {
	readonly blockingMetricsOutputPath: () => string;
	readonly buildActionCommand: (action: string) => string;
	readonly buildAppConfig: () => any;
	readonly compactOutput: (output: string) => string;
	readonly createProjectFromForm: () => Promise<void>;
	readonly ffprobeExe: () => string;
	readonly hasSyncTargets: (manifest?: MediaManifest | null) => boolean;
	readonly notifyAnalysisComplete: (message: string) => Promise<void>;
	readonly personEditPlansDir: () => string;
	readonly referenceEditProfilePath: () => string;
	readonly refreshPrompt: () => void;
	readonly refreshSyncReport: () => Promise<void>;
	readonly refreshTextOverlayFromAnalysis: (manifest?: MediaManifest | null) => Promise<any>;
	readonly renderAnalysisResults: () => void;
	readonly setAnalysisResult: (key: string, label: string, status: string, detail: string, path?: string) => void;
	readonly setAppLocked: (locked: boolean, message?: string, title?: string) => void;
	readonly setDefaultProjectOutput: (preserveExisting?: boolean) => void;
	readonly setIngestProgress: (payload: any, options?: { persist?: boolean }) => void;
	readonly setIngestRunning: (running: boolean) => void;
	readonly setMaterialSources: (paths: string[]) => void;
	readonly setMediaManifest: (manifest: MediaManifest | null) => void;
	readonly setProject: (project: ProjectInfo | null) => void;
	readonly setStatus: (text: string, kind?: string) => void;
	readonly syncReportPath: () => string;
	readonly transcriptComparisonOutputPath: () => string;
	readonly transcriptManifestOutputPath: () => string;
};

function isMaterialAnalysisCanceled(error: unknown) {
	const message = String((error as Error)?.message || error || "");
	return message.includes("キャンセル") || message.toLowerCase().includes("cancel");
}

function throwIfMaterialAnalysisCanceled() {
	if (state.materialAnalysisCancelRequested) {
		throw new Error(t("progress.analysisCanceled"));
	}
}

export function createMaterialAnalysisController({
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
	renderAnalysisResults,
	setAnalysisResult,
	setAppLocked,
	setDefaultProjectOutput,
	setIngestProgress,
	setIngestRunning,
	setMaterialSources,
	setMediaManifest,
	setProject,
	setStatus,
	syncReportPath,
	transcriptComparisonOutputPath,
	transcriptManifestOutputPath,
}: MaterialAnalysisControllerOptions) {
	async function runAnalysisAction(
		action: string,
		label: string,
		progress: number,
		resultPath: string,
		timeoutMs = 6 * 60 * 60 * 1000,
	) {
		throwIfMaterialAnalysisCanceled();
		setAppLocked(true, label);
		setStatus(label, "busy");
		setAnalysisResult(action, label, "running", t("analysis.statusRunning"), resultPath);
		setIngestProgress({
			progress,
			message: t("format.runningMessage", { label }),
			path: resultPath,
		});
		const command = buildActionCommand(action);
		log("analysis/exec", { action, command });
		try {
			const result = await editApp.runWorkflowAction({
				action,
				timeoutMs,
				appConfig: buildAppConfig(),
			});
			if (result?.canceled) {
				throw new Error(t("progress.analysisCanceled"));
			}
			if (result?.stdout) {
				log("stdout", { action, text: compactOutput(result.stdout) });
			}
			if (result?.stderr) {
				log("stderr", { action, text: compactOutput(result.stderr) });
			}
			const ok = result?.exitCode === 0;
			if (ok && action === "analyze-person-edit-metadata" && result?.manifest) {
				setMediaManifest(result.manifest);
			}
			setAnalysisResult(
				action,
				label,
				ok ? "done" : "error",
				ok ? t("analysis.updatedOutput") : t("analysis.checkLogs"),
				resultPath,
			);
			setIngestProgress({
				progress,
				message: ok ? t("format.completeMessage", { label }) : t("format.errorMessage", { label }),
				path: resultPath,
			});
			return ok;
		} catch (error) {
			if (isMaterialAnalysisCanceled(error)) {
				setAnalysisResult(action, label, "error", t("progress.analysisCanceled"), resultPath);
				setIngestProgress({
					progress,
					message: t("progress.analysisCanceled"),
					path: resultPath,
				});
				throw error;
			}
			setAnalysisResult(action, label, "error", error.message, resultPath);
			setIngestProgress({
				progress,
				message: t("format.errorMessage", { label }),
				path: resultPath,
			});
			log("analysis failed", { action, message: error.message });
			return false;
		}
	}

	async function ingestMaterialDirectory(directoryPath = "") {
		const selectedSources = directoryPath
			? [directoryPath]
			: state.materialPaths.length
				? state.materialPaths
				: state.mediaDirectory
					? [state.mediaDirectory]
					: [];
		const sourceLabel =
			selectedSources.length === 1 ? selectedSources[0] : t("label.selectedItems", { count: selectedSources.length });
		if (!selectedSources.length) {
			log("ingest skipped", { reason: t("log.selectMaterialFirst") });
			return false;
		}
		if (!state.project) {
			if (!getAppState().projectDraft.name.trim()) {
				const parts = selectedSources[0].split(/[\\/]/).filter(Boolean);
				const name =
					selectedSources.length === 1
						? parts.at(-1) || `project-${new Date().toISOString().slice(0, 10)}`
						: `materials-${new Date().toISOString().slice(0, 10)}`;
				getAppState().setProjectDraft({ name, id: projectIdFromName(name) });
			}
			await createProjectFromForm();
		}
		if (!state.project) {
			return false;
		}
		state.fullAnalysisRunning = true;
		state.materialAnalysisCancelable = true;
		state.materialAnalysisCancelRequested = false;
		state.analysisResults = [];
		renderAnalysisResults();
		setStatus(t("status.analyzingMaterial"), "busy");
		setIngestRunning(true);
		setAppLocked(true, t("progress.analyzingMaterial"));
		setIngestProgress({
			progress: 0,
			message: t("progress.startingAnalysis"),
			path: sourceLabel,
		});
		log("ingest material", { paths: selectedSources });
		try {
			const result = await editApp.ingestDirectory({
				project: state.project,
				directory: selectedSources.length === 1 ? selectedSources[0] : "",
				paths: selectedSources,
				tools: {
					ffprobe: ffprobeExe(),
				},
			});
			setIngestRunning(state.ingestRunning);
			throwIfMaterialAnalysisCanceled();
			setProject(result.project);
			setMediaManifest(result.manifest);
			getAppState().setWorkflowSettings({
				editPreset: "new-interview",
				renderScript: "render_app_interview.py",
				workflowAction: "auto-sync-dropped",
			});
			setDefaultProjectOutput(false);
			setAnalysisResult(
				"ingest",
				t("analysis.materialClassification"),
				"done",
				`${result.manifest?.files?.length || 0} files / ${result.manifest?.cameras?.length || 0} camera(s)`,
				result.manifest?.manifestPath || sourceLabel,
			);
			setIngestProgress({
				progress: 0.22,
				message: t("progress.materialClassified"),
				path: result.manifest?.manifestPath || sourceLabel,
			});
			log("material manifest ready", {
				manifest: result.manifest?.manifestPath,
				files: result.manifest?.files?.length || 0,
				cameras: result.manifest?.cameras?.length || 0,
				audio: result.manifest?.audio?.length || 0,
			});
			refreshPrompt();
			const checks: boolean[] = [];
			throwIfMaterialAnalysisCanceled();
			if (hasSyncTargets(result.manifest)) {
				checks.push(
					await runAnalysisAction(
						"auto-sync-dropped",
						t("analysis.syncCamerasAudio"),
						0.34,
						syncReportPath(),
						2 * 60 * 60 * 1000,
					),
				);
				await refreshSyncReport();
			} else {
				setAnalysisResult(
					"auto-sync-dropped",
					t("analysis.syncCamerasAudio"),
					"done",
					t("analysis.singleCameraSkipped"),
					syncReportPath(),
				);
			}
			throwIfMaterialAnalysisCanceled();
			checks.push(
				await runAnalysisAction(
					"transcribe-dropped",
					t("analysis.transcription"),
					0.58,
					transcriptManifestOutputPath(),
				),
			);
			throwIfMaterialAnalysisCanceled();
			const textOverlayResult = await refreshTextOverlayFromAnalysis(result.manifest);
			setAnalysisResult(
				"text-overlays",
				t("analysis.subtitleUi"),
				textOverlayResult?.captionCount ? "done" : "error",
				textOverlayResult?.captionCount
					? `${textOverlayResult.captionCount} captions`
					: t("analysis.noSubtitleCandidates"),
				textOverlayResult?.subtitlePath || "",
			);
			throwIfMaterialAnalysisCanceled();
			checks.push(
				await runAnalysisAction(
					"compare-transcripts",
					t("analysis.transcriptComparison"),
					0.68,
					transcriptComparisonOutputPath(),
				),
			);
			throwIfMaterialAnalysisCanceled();
			checks.push(
				await runAnalysisAction("analyze-person-edit-metadata", t("analysis.personOpenCv"), 0.8, personEditPlansDir()),
			);
			throwIfMaterialAnalysisCanceled();
			checks.push(
				await runAnalysisAction("analyze-blocking", t("analysis.blockingOpenCv"), 0.9, blockingMetricsOutputPath()),
			);
			throwIfMaterialAnalysisCanceled();
			if (state.files.referenceVideo) {
				checks.push(
					await runAnalysisAction(
						"analyze-reference-video",
						t("analysis.referenceVideo"),
						0.95,
						referenceEditProfilePath(),
					),
				);
			}
			throwIfMaterialAnalysisCanceled();
			await refreshTextOverlayFromAnalysis(result.manifest);
			await refreshSyncReport();
			getAppState().setWorkflowSettings({
				editPreset: "new-interview",
				renderScript: "render_app_interview.py",
				workflowAction: "render-selected",
			});
			refreshPrompt();
			const allOk = checks.every(Boolean);
			setIngestProgress({
				progress: 1,
				message: allOk ? t("progress.allAnalysisComplete") : t("progress.analysisCompleteWithErrors"),
				path: result.manifest?.manifestPath || sourceLabel,
			});
			setStatus(
				allOk ? t("status.analysisComplete") : t("status.analysisCompletedWithErrors"),
				allOk ? "ready" : "idle",
			);
			state.fullAnalysisRunning = false;
			await notifyAnalysisComplete(
				allOk ? t("notification.analysisComplete") : t("notification.analysisCompleteCheck"),
			);
			return allOk;
		} catch (error) {
			state.materialAnalysisCancelable = false;
			setStatus(t("status.ingestFailed"), "idle");
			setIngestProgress({
				progress: 0,
				message: String(error.message || "").includes("キャンセル")
					? t("progress.analysisCanceled")
					: t("progress.analysisFailed"),
				path: sourceLabel,
			});
			log("ingest failed", { message: error.message });
			return false;
		} finally {
			state.fullAnalysisRunning = false;
			state.materialAnalysisCancelable = false;
			state.materialAnalysisCancelRequested = false;
			setIngestRunning(false);
			setAppLocked(false);
		}
	}

	async function cancelMaterialAnalysis() {
		if (!state.ingestRunning) {
			setMaterialSources([]);
			return;
		}
		if (!state.materialAnalysisCancelable) {
			log("ingest cancel skipped", { reason: t("analysis.statusRunning") });
			return;
		}
		state.materialAnalysisCancelRequested = true;
		setIngestProgress({
			...state.ingestProgress,
			message: t("progress.cancelingAnalysis"),
		});
		setIngestRunning(state.ingestRunning);
		try {
			const result = await editApp.cancelIngest();
			log(result?.canceled ? "analysis cancel requested" : "analysis cancel pending");
		} catch (error) {
			log("ingest cancel failed", { message: error.message });
		}
	}

	return {
		cancelMaterialAnalysis,
		ingestMaterialDirectory,
	};
}
