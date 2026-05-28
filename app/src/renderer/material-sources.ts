import { editApp } from "./api.js";
import { t } from "./i18n.js";
import { log } from "./log.js";
import { state } from "./state.js";
import { getAppState } from "./store/app-store.js";

type MaterialSourceControllerOptions = {
	readonly ffprobeExe: () => string;
	readonly refreshPrompt: () => void;
	readonly renderFileSlots: () => void;
	readonly renderMediaManifest: () => void;
	readonly renderStillImageList: () => void;
	readonly renderWorkflowMediaPreviews: () => void;
	readonly resetAnalysisForMaterialChange: (path?: string) => void;
	readonly setIngestRunning: (running: boolean) => void;
};

export function createMaterialSourceController({
	ffprobeExe,
	refreshPrompt,
	renderFileSlots,
	renderMediaManifest,
	renderStillImageList,
	renderWorkflowMediaPreviews,
	resetAnalysisForMaterialChange,
	setIngestRunning,
}: MaterialSourceControllerOptions) {
	function materialSourceLabel() {
		if (!state.materialPaths.length) {
			return "";
		}
		return state.materialPaths.length === 1 ? state.materialPaths[0] : `${state.materialPaths.length} selected item(s)`;
	}

	async function loadMaterialSourcePreviews(paths: string[]) {
		const selectedPaths = [
			...new Set(
				paths
					.map(String)
					.map((item) => item.trim())
					.filter(Boolean),
			),
		];
		const requestId = state.materialSourcePreviewRequestId + 1;
		state.materialSourcePreviewRequestId = requestId;
		state.materialSourcePreviewLoading = Boolean(selectedPaths.length);
		state.materialSourcePreviews = [];
		renderMediaManifest();
		if (!selectedPaths.length) {
			state.materialSourcePreviewLoading = false;
			renderMediaManifest();
			return;
		}
		try {
			const previews = await editApp.describeMediaPaths({
				paths: selectedPaths,
				expandDirectories: true,
				thumbnailLimit: 1000,
				tools: {
					ffprobe: ffprobeExe(),
				},
			});
			if (requestId !== state.materialSourcePreviewRequestId) {
				return;
			}
			state.materialSourcePreviews = previews || [];
			renderMediaManifest();
			for (const preview of state.materialSourcePreviews) {
				if (preview?.path) {
					state.filePreviews[preview.path] = preview;
				}
			}
		} catch (error) {
			log("material preview failed", { message: error.message });
		} finally {
			if (requestId === state.materialSourcePreviewRequestId) {
				state.materialSourcePreviewLoading = false;
				renderMediaManifest();
				renderFileSlots();
				renderStillImageList();
				renderWorkflowMediaPreviews();
			}
		}
	}

	function setMaterialSources(paths: string[]) {
		const selected = [
			...new Set(
				paths
					.map(String)
					.map((item) => item.trim())
					.filter(Boolean),
			),
		];
		state.materialPaths = selected;
		state.mediaDirectory = selected[0] || "";
		state.mediaManifest = null;
		state.materialSourcePreviews = [];
		state.materialAnalysisCancelable = false;
		state.materialAnalysisCancelRequested = false;
		getAppState().setMediaManifest(null, {
			mediaDirectory: state.mediaDirectory,
			materialPaths: state.materialPaths,
			materialSourcePreviews: state.materialSourcePreviews,
		});
		resetAnalysisForMaterialChange(materialSourceLabel());
		setIngestRunning(state.ingestRunning);
		renderMediaManifest();
		void loadMaterialSourcePreviews(state.materialPaths);
		refreshPrompt();
	}

	function setMaterialDirectory(directoryPath: string) {
		setMaterialSources(directoryPath ? [directoryPath] : []);
	}

	function addMaterialSources(paths: string[]) {
		setMaterialSources([...state.materialPaths, ...paths]);
	}

	async function pickMaterialDirectory() {
		const selected = await editApp.pickDirectory({ title: t("dialog.selectMaterialFolder") });
		if (selected) {
			setMaterialDirectory(selected);
		}
	}

	async function pickMaterialFiles() {
		const selected = await editApp.pickFile({
			title: t("dialog.selectMaterialFiles"),
			filters: [
				{
					name: t("filter.mediaAndSubtitles"),
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
				{ name: t("filter.allFiles"), extensions: ["*"] },
			],
			multi: true,
		});
		if (Array.isArray(selected)) {
			addMaterialSources(selected);
		} else if (selected) {
			addMaterialSources([selected]);
		}
	}

	return {
		addMaterialSources,
		loadMaterialSourcePreviews,
		materialSourceLabel,
		pickMaterialDirectory,
		pickMaterialFiles,
		setMaterialDirectory,
		setMaterialSources,
	};
}
