import { editApp } from "./api.js";
import { t } from "./i18n.js";
import { log } from "./log.js";
import {
	inputVideoPathValue,
	outputPathValue,
	setInputVideoPathValue,
	setOutputPathValue,
	syncFilesStore,
	syncPathPreviewStore,
} from "./media-state.js";
import { activeOutputRoot, fileSlotLabel, filtersForSlot } from "./preview.js";
import { state } from "./state.js";
import { getAppState, patchAppState } from "./store/app-store.js";

type AssetFileControllerOptions = {
	readonly refreshPrompt: () => void;
	readonly renderMediaManifest: () => void;
};

export function createAssetFileController({ refreshPrompt, renderMediaManifest }: AssetFileControllerOptions) {
	function renderFileSlot(slot: string) {
		if (slot in state.files) {
			syncFilesStore();
		}
	}

	function renderFileSlots() {
		syncFilesStore();
	}

	function renderWorkflowMediaPreviews() {
		syncPathPreviewStore();
	}

	function renderOutputTargetPreview() {
		syncPathPreviewStore();
	}

	async function loadFilePreviews(paths: string[]) {
		const missing = [...new Set(paths.filter(Boolean))].filter((filePath) => !state.filePreviews[filePath]);
		if (!missing.length) {
			return;
		}
		try {
			const previews = await editApp.describeMediaPaths({ paths: missing });
			for (const preview of previews || []) {
				if (preview?.path) {
					state.filePreviews[preview.path] = preview;
				}
			}
			patchAppState({ filePreviews: { ...state.filePreviews } });
			renderMediaManifest();
			renderFileSlots();
			renderStillImageList();
			renderWorkflowMediaPreviews();
			renderOutputTargetPreview();
		} catch (error) {
			log("media preview failed", { message: error.message });
		}
	}

	function loadWorkflowMediaPreviews() {
		const paths = [inputVideoPathValue()].filter(Boolean);
		loadFilePreviews(paths);
		renderWorkflowMediaPreviews();
	}

	function loadOutputTargetPreview() {
		const path = outputPathValue();
		if (path) {
			loadFilePreviews([path]);
		}
		renderOutputTargetPreview();
	}

	function setFile(slot: string, filePath: string) {
		state.files[slot] = filePath || "";
		renderFileSlot(slot);
		if (filePath) {
			loadFilePreviews([filePath]);
		}
		refreshPrompt();
	}

	function setStillImages(paths: string[]) {
		state.files.stillImages = [...new Set(paths.filter(Boolean))];
		renderStillImageList();
		loadFilePreviews(state.files.stillImages);
		refreshPrompt();
	}

	function addStillImages(paths: string[]) {
		setStillImages([...state.files.stillImages, ...paths]);
	}

	function clearSelectedAssets() {
		setFile("masterVideo", "");
		setFile("rightCloseVideo", "");
		setFile("leftCloseVideo", "");
		setFile("referenceVideo", "");
		setFile("externalAudio", "");
		setFile("logo", "");
		setStillImages([]);
	}

	function renderStillImageList() {
		syncFilesStore();
	}

	async function pickFile(slot: string) {
		if (slot === "stillImages") {
			const selected = await editApp.pickFile({
				title: t("dialog.selectStillImages"),
				filters: filtersForSlot("stillImages"),
				multi: true,
			});
			if (Array.isArray(selected)) {
				addStillImages(selected);
			} else if (selected) {
				addStillImages([selected]);
			}
			return;
		}
		const selected = await editApp.pickFile({
			title: t("dialog.selectSlot", { slot: fileSlotLabel(slot) }),
			filters: filtersForSlot(slot),
		});
		if (selected) {
			setFile(slot, Array.isArray(selected) ? selected[0] : selected);
		}
	}

	async function pickTool(id: string) {
		const selected = await editApp.pickFile({
			title: t("dialog.selectTool", { id }),
			filters: [{ name: t("filter.allFiles"), extensions: ["*"] }],
		});
		if (selected) {
			const selectedPath = Array.isArray(selected) ? selected[0] : selected;
			if (id === "inputVideoPath") {
				setInputVideoPathValue(selectedPath);
				loadWorkflowMediaPreviews();
			} else if (id === "pythonPath") {
				getAppState().setToolPaths({ pythonPath: selectedPath });
			} else if (id === "ffmpegPath") {
				getAppState().setToolPaths({ ffmpegPath: selectedPath });
			} else if (id === "ffprobePath") {
				getAppState().setToolPaths({ ffprobePath: selectedPath });
			} else {
				log("tool picker ignored unknown target", { id });
			}
			refreshPrompt();
		}
	}

	async function pickOutput() {
		const mode = state.subtitleMode === "punchline" ? "punchline" : "full_transcript";
		const selected = await editApp.pickOutput({
			title: t("dialog.selectOutputVideo"),
			suggestedName: `codex_edit_${mode}.mp4`,
			outputRoot: activeOutputRoot(),
			filterName: t("filter.mp4Video"),
			language: state.language,
		});
		if (selected) {
			setOutputPathValue(selected);
			loadOutputTargetPreview();
			refreshPrompt();
		}
	}

	return {
		addStillImages,
		clearSelectedAssets,
		loadFilePreviews,
		loadOutputTargetPreview,
		loadWorkflowMediaPreviews,
		pickFile,
		pickOutput,
		pickTool,
		renderFileSlot,
		renderFileSlots,
		renderOutputTargetPreview,
		renderStillImageList,
		renderWorkflowMediaPreviews,
		setFile,
		setStillImages,
	};
}
