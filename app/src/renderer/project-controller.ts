import { editApp } from "./api.js";
import { t } from "./i18n.js";
import { log } from "./log.js";
import { outputPathValue, setInputVideoPathValue, setOutputPathValue } from "./media-state.js";
import { joinPath, projectIdFromName } from "./preview.js";
import { state } from "./state.js";
import { getAppState, patchAppState } from "./store/app-store.js";
import type { MediaManifest, ProjectInfo, ProjectListEntry } from "./types.js";

type ProjectControllerOptions = {
	readonly clearSelectedAssets: () => void;
	readonly loadAnalysisStateFile: (project?: ProjectInfo | null) => Promise<boolean>;
	readonly loadOutputTargetPreview: () => void;
	readonly loadProjectStateFile: (project?: ProjectInfo | null) => Promise<boolean>;
	readonly loadWorkflowMediaPreviews: () => void;
	readonly persistProjectStateFileNow: () => Promise<void>;
	readonly refreshPrompt: () => void;
	readonly refreshMaterialAnalysisStatus: () => Promise<void>;
	readonly refreshSyncReport: () => Promise<void>;
	readonly refreshTextOverlayFromAnalysis: (manifest?: MediaManifest | null) => Promise<any>;
	readonly restoreAnalysisResultsFromOutputs: (manifest?: MediaManifest | null) => Promise<any>;
	readonly restoreProgressFromOutputs: (options?: any) => Promise<any>;
	readonly setAnalysisResults: (results: any[], options?: { persistFile?: boolean }) => void;
	readonly setAnalysisTitleText: (title: string) => void;
	readonly setFile: (slot: string, filePath: string) => void;
	readonly setIngestProgress: (payload: any, options?: { persist?: boolean }) => void;
	readonly setMediaManifest: (manifest: MediaManifest | null) => void;
	readonly setStillImages: (paths: string[]) => void;
};

export function createProjectController({
	clearSelectedAssets,
	loadAnalysisStateFile,
	loadOutputTargetPreview,
	loadProjectStateFile,
	loadWorkflowMediaPreviews,
	persistProjectStateFileNow,
	refreshPrompt,
	refreshMaterialAnalysisStatus,
	refreshSyncReport,
	refreshTextOverlayFromAnalysis,
	restoreAnalysisResultsFromOutputs,
	restoreProgressFromOutputs,
	setAnalysisResults,
	setAnalysisTitleText,
	setFile,
	setIngestProgress,
	setMediaManifest,
	setStillImages,
}: ProjectControllerOptions) {
	function projectDraftName() {
		return getAppState().projectDraft.name.trim();
	}

	function projectDraftId() {
		return getAppState().projectDraft.id.trim();
	}

	function renderProjectDialogList() {
		patchAppState({
			project: state.project,
			projectList: state.projectList,
			projectListLoading: state.projectListLoading,
			language: state.language,
		});
	}

	function normalizeProjectRoot(value: string) {
		return String(value || "")
			.replace(/[\\/]+/g, "/")
			.replace(/\/+$/g, "")
			.toLowerCase();
	}

	function isProjectUnderActiveProjectsRoot(project: ProjectInfo | null) {
		const projectsRoot = normalizeProjectRoot(state.env?.projectsRoot || "");
		const projectRoot = normalizeProjectRoot(project?.root || "");
		return Boolean(projectRoot && (!projectsRoot || projectRoot.startsWith(`${projectsRoot}/`)));
	}

	function setDefaultProjectOutput(preserveExisting = true) {
		if (!state.project) {
			return;
		}
		const current = outputPathValue();
		if (preserveExisting && current) {
			return;
		}
		const mode = state.subtitleMode === "punchline" ? "punchline" : "full_transcript";
		setOutputPathValue(joinPath(state.project.outputRoot, "videos", `codex_edit_${mode}.mp4`));
		loadOutputTargetPreview();
	}

	function setProject(project: ProjectInfo | null) {
		const previousProjectId = state.project?.id || "";
		state.project = project;
		state.projectStatePath = project ? joinPath(project.root, "project_state.json") : "";
		if (!project || project.id !== previousProjectId) {
			state.projectStateRevision = 0;
		}
		if (project?.id !== previousProjectId) {
			state.editRequest = {
				instructionDraft: "",
				instructionHistory: [],
				requestedPreviewPath: "",
				requestedFinalPath: "",
				lastPreviewPath: "",
				lastFinalPath: "",
			};
			state.review = {
				previewVideoPath: "",
				currentTime: 0,
				selectedRange: null,
				zoom: 1,
				scrollStart: 0,
				reviewTimelinePath: "",
			};
			state.reviewTimeline = null;
			state.reviewThumbnailStrip = null;
			state.reviewWaveform = null;
			state.reviewPreviewUrl = "";
			state.reviewPreviewMetadata = null;
			state.reviewPreviewLoading = false;
			state.reviewPreviewError = "";
			getAppState().setEditRequest(state.editRequest);
			getAppState().setReview(state.review);
			getAppState().patchState({
				reviewTimeline: null,
				reviewThumbnailStrip: null,
				reviewWaveform: null,
				reviewPreviewUrl: "",
				reviewPreviewMetadata: null,
				reviewPreviewLoading: false,
				reviewPreviewError: "",
			});
			void editApp.resetCodexThread().catch((error) => log("codex thread reset failed", { message: error.message }));
		}
		getAppState().setProject(project, {
			projectStatePath: state.projectStatePath,
			projectStateRevision: state.projectStateRevision,
		});
		setAnalysisTitleText("");
		setDefaultProjectOutput(false);
		renderProjectDialogList();
		refreshPrompt();
	}

	async function loadProjectList() {
		state.projectListLoading = true;
		patchAppState({ projectListLoading: state.projectListLoading });
		renderProjectDialogList();
		try {
			const result = await editApp.listProjects();
			state.projectList = Array.isArray(result?.projects) ? result.projects : [];
		} catch (error) {
			state.projectList = [];
			log("project list failed", { message: error.message });
		} finally {
			state.projectListLoading = false;
			patchAppState({ projectList: state.projectList, projectListLoading: state.projectListLoading });
			renderProjectDialogList();
		}
	}

	function setProjectDialogOpen(open: boolean) {
		getAppState().setProjectDialogOpen(open);
		if (open) {
			getAppState().setProjectDialogName(projectDraftName() && !state.project ? projectDraftName() : "");
			void loadProjectList();
		}
	}

	async function activateProject(project: ProjectInfo, manifest: MediaManifest | null = null) {
		const previousApplying = state.projectStateApplying;
		state.projectStateApplying = true;
		try {
			setProject(project);
			clearSelectedAssets();
			setAnalysisResults([], { persistFile: false });
			setMediaManifest(manifest || null);
		} finally {
			state.projectStateApplying = previousApplying;
		}
		const loadedProjectState = await loadProjectStateFile(project);
		if (!loadedProjectState) {
			await persistProjectStateFileNow();
		}
		await refreshTextOverlayFromAnalysis(state.mediaManifest || manifest || null);
		if (!(await loadAnalysisStateFile(project))) {
			await restoreAnalysisResultsFromOutputs(state.mediaManifest || manifest || null);
		}
		const restoredProgress = await restoreProgressFromOutputs({ preserveExisting: true });
		if (!state.mediaManifest && !restoredProgress) {
			setIngestProgress({
				progress: 0,
				message: t("materials.folderNotAnalyzed"),
				path: "",
			});
		}
		await refreshSyncReport();
		await refreshMaterialAnalysisStatus();
		refreshPrompt();
	}

	async function restoreStartupProjectFromDisk() {
		try {
			const result = await editApp.listProjects();
			const entries = Array.isArray(result?.projects) ? result.projects : [];
			state.projectList = entries;
			patchAppState({ projectList: state.projectList });
			renderProjectDialogList();
			const currentProject =
				state.project && isProjectUnderActiveProjectsRoot(state.project)
					? entries.find((candidate) => candidate?.project?.id === state.project?.id)?.project || state.project
					: null;
			const latestProject =
				entries.find((candidate) => candidate?.project?.id && candidate.hasManifest)?.project ||
				entries.find((candidate) => candidate?.project?.id)?.project ||
				null;
			const candidates = [currentProject, latestProject].filter(
				(project, index, projects): project is ProjectInfo =>
					Boolean(project?.id) && projects.findIndex((item) => item?.id === project?.id) === index,
			);
			if (!candidates.length) {
				if (state.project) {
					setProject(null);
				}
				return false;
			}
			for (const project of candidates) {
				let loaded: Awaited<ReturnType<typeof editApp.loadProject>> | null = null;
				try {
					loaded = await editApp.loadProject({ project });
				} catch (error) {
					log("project restore candidate skipped", {
						id: project.id,
						root: project.root,
						message: (error as Error).message,
					});
					continue;
				}
				if (!loaded?.project) {
					continue;
				}
				await activateProject(loaded.project, loaded.manifest || null);
				log("project restored from disk", {
					id: loaded.project.id,
					root: loaded.project.root,
					manifest: loaded.manifest?.manifestPath || null,
				});
				return true;
			}
			if (state.project) {
				setProject(null);
			}
			return false;
		} catch (error) {
			log("project restore failed", { message: error.message });
			if (state.project) {
				setProject(null);
			}
			return false;
		}
	}

	async function openProject(entry: ProjectListEntry) {
		if (state.ingestRunning) {
			log("project switch skipped", { reason: t("log.cannotSwitchDuringIngest") });
			return;
		}
		try {
			const result = await editApp.loadProject({ project: entry.project });
			if (!result?.project) {
				return;
			}
			setProjectDialogOpen(false);
			await activateProject(result.project, result.manifest || null);
			log("project switched", {
				id: result.project.id,
				root: result.project.root,
				manifest: result.manifest?.manifestPath || null,
			});
			void loadProjectList();
		} catch (error) {
			log("project switch failed", { message: error.message });
		}
	}

	async function createProjectFromForm() {
		const name = projectDraftName() || `project-${new Date().toISOString().slice(0, 10)}`;
		const id = projectDraftId() || projectIdFromName(name);
		try {
			const project = await editApp.createProject({ name, id });
			setProject(project);
			await persistProjectStateFileNow();
			void loadProjectList();
			log("project ready", { id: project.id, root: project.root });
		} catch (error) {
			log("project create failed", { message: error.message });
		}
	}

	function changeProject() {
		setProjectDialogOpen(true);
	}

	async function createProjectFromDialog() {
		if (state.ingestRunning) {
			log("project create skipped", { reason: t("log.cannotSwitchDuringIngest") });
			return;
		}
		const formName = getAppState().projectDialogName.trim();
		const name = formName || projectDraftName() || `project-${new Date().toISOString().slice(0, 10)}`;
		const id = projectIdFromName(name);
		try {
			const project = await editApp.createProject({ name, id });
			setProjectDialogOpen(false);
			await activateProject(project, null);
			log("project ready", { id: project.id, root: project.root });
			void loadProjectList();
		} catch (error) {
			log("project create failed", { message: error.message });
		}
	}

	async function deleteCurrentProject() {
		if (!state.project) {
			log("project delete skipped", { reason: t("log.projectNotSelected") });
			return;
		}
		if (state.ingestRunning) {
			log("project delete skipped", { reason: t("log.cannotDeleteDuringIngest") });
			return;
		}
		const deletedProject = state.project;
		try {
			const result = await editApp.deleteProject({ project: deletedProject, language: state.language });
			if (!result?.deleted) {
				log(result?.canceled ? "project delete canceled" : "project delete skipped", {
					id: deletedProject.id,
					missing: Boolean(result?.missing),
				});
				return;
			}
			setProject(null);
			clearSelectedAssets();
			setMediaManifest(null);
			setAnalysisResults([]);
			setIngestProgress({
				progress: 0,
				message: t("progress.waitingAnalysis"),
				path: "",
			});
			setOutputPathValue("");
			setInputVideoPathValue("");
			loadWorkflowMediaPreviews();
			loadOutputTargetPreview();
			log("project deleted", { id: deletedProject.id, root: deletedProject.root });
			await refreshSyncReport();
			refreshPrompt();
		} catch (error) {
			log("project delete failed", { message: error.message });
		}
	}

	async function copyAssetsToProject() {
		if (!state.project) {
			await createProjectFromForm();
		}
		if (!state.project) {
			return false;
		}
		try {
			const result = await editApp.copyProjectAssets({
				project: state.project,
				files: state.files,
			});
			setProject(result.project);
			Object.entries(result.files || {}).forEach(([slot, filePath]) => {
				if (slot === "stillImages" && Array.isArray(filePath)) {
					setStillImages(filePath.map(String));
					return;
				}
				if (slot in state.files) {
					setFile(slot, String(filePath || ""));
				}
			});
			log("assets copied", { project: state.project.id });
			return true;
		} catch (error) {
			log("copy assets failed", { message: error.message });
			return false;
		}
	}

	return {
		activateProject,
		changeProject,
		copyAssetsToProject,
		createProjectFromDialog,
		createProjectFromForm,
		deleteCurrentProject,
		loadProjectList,
		openProject,
		projectDraftName,
		projectDraftId,
		renderProjectDialogList,
		restoreStartupProjectFromDisk,
		setDefaultProjectOutput,
		setProject,
		setProjectDialogOpen,
	};
}
