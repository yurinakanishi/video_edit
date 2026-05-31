import { editApp } from "./api.js";
import {
	CONFIRM_DIALOG_CLOSE_EVENT,
	EDIT_REQUEST_CHANGE_EVENT,
	LANGUAGE_CHANGE_EVENT,
	MATERIAL_CANCEL_ANALYSIS_EVENT,
	OUTPUT_PREVIEW_ENTRY_OPEN_EVENT,
	OUTPUT_PREVIEW_OPEN_FOLDER_EVENT,
	OUTPUT_PREVIEW_REFRESH_EVENT,
	PROJECT_CHANGE_EVENT,
	PROJECT_DIALOG_CLOSE_EVENT,
	PROJECT_DIALOG_CREATE_EVENT,
	PROJECT_DIALOG_OPEN_PROJECT_EVENT,
	SIMPLE_AUDIO_DROP_EVENT,
	SIMPLE_AUDIO_PICK_EVENT,
	SIMPLE_FINAL_RENDER_EVENT,
	SIMPLE_MATERIAL_DROP_EVENT,
	SIMPLE_MATERIAL_PICK_DIRECTORY_EVENT,
	SIMPLE_MATERIAL_PICK_FILES_EVENT,
	SIMPLE_PREVIEW_REQUEST_EVENT,
	SIMPLE_TRANSCRIBE_EVENT,
} from "./events.js";
import { normalizeLanguage, state } from "./state.js";
import { getAppState } from "./store/app-store.js";
import type { ProjectListEntry } from "./types.js";

type RendererEventBindings = {
	readonly cancelMaterialAnalysis: () => Promise<void>;
	readonly changeProject: () => void;
	readonly closeConfirmDialog: (confirmed: boolean) => void;
	readonly createProjectFromDialog: () => Promise<void>;
	readonly handleEditRequestChange: (event: Event) => void;
	readonly ingestSimpleMaterials: (paths: string[]) => Promise<boolean>;
	readonly pickSimpleMaterialDirectory: () => Promise<void>;
	readonly pickSimpleMaterialFiles: () => Promise<void>;
	readonly addSimpleAudioFiles: (paths: string[]) => Promise<boolean>;
	readonly pickSimpleAudioFiles: () => Promise<void>;
	readonly runSimpleTranscription: () => Promise<boolean>;
	readonly sendSimpleEditRequest: (mode: "preview" | "final") => Promise<void>;
	readonly loadOutputPreview: (kind: string) => Promise<any>;
	readonly openProject: (entry: ProjectListEntry) => Promise<void>;
	readonly outputPreviewTarget: () => string;
	readonly setLanguage: (language: "ja" | "en") => void;
	readonly setProjectDialogOpen: (open: boolean) => void;
};

function pathsFromDroppedFiles(files: File[]) {
	return files.map((file) => editApp.filePath(file)).filter(Boolean);
}

function pathsFromDropDetail(detail: any) {
	const explicitPaths = Array.isArray(detail.paths) ? detail.paths.map(String).filter(Boolean) : [];
	if (explicitPaths.length) {
		return explicitPaths;
	}
	return pathsFromDroppedFiles(Array.isArray(detail.files) ? detail.files : []);
}

export function bindRendererEvents(bindings: RendererEventBindings) {
	function handleLanguageChange(event: Event) {
		bindings.setLanguage(normalizeLanguage((event as CustomEvent).detail?.language));
	}

	function handleProjectDialogOpenProject(event: Event) {
		const index = Number((event as CustomEvent).detail?.index);
		if (!Number.isInteger(index) || index < 0) {
			return;
		}
		const entry = state.projectList[index];
		if (entry) {
			void bindings.openProject(entry);
		}
	}

	function handleOutputPreviewRefresh() {
		if (state.outputPreviewKind) {
			void bindings.loadOutputPreview(state.outputPreviewKind);
		}
	}

	function handleOutputPreviewOpenFolder() {
		const previewPath = state.outputPreview?.path || bindings.outputPreviewTarget();
		if (previewPath) {
			editApp.showPath(previewPath);
		}
	}

	function handleOutputPreviewEntryOpen(event: Event) {
		const path = String((event as CustomEvent).detail?.path || "");
		if (path) {
			editApp.showPath(path);
		}
	}

	function handleSimpleMaterialDrop(event: Event) {
		const detail = (event as CustomEvent).detail || {};
		const paths = pathsFromDropDetail(detail);
		if (paths.length) {
			void bindings.ingestSimpleMaterials(paths);
		}
	}

	function handleSimpleAudioDrop(event: Event) {
		const detail = (event as CustomEvent).detail || {};
		const paths = pathsFromDropDetail(detail);
		if (paths.length) {
			void bindings.addSimpleAudioFiles(paths);
		}
	}

	document.addEventListener(OUTPUT_PREVIEW_REFRESH_EVENT, handleOutputPreviewRefresh);
	document.addEventListener(OUTPUT_PREVIEW_OPEN_FOLDER_EVENT, handleOutputPreviewOpenFolder);
	document.addEventListener(OUTPUT_PREVIEW_ENTRY_OPEN_EVENT, handleOutputPreviewEntryOpen);
	document.addEventListener(SIMPLE_MATERIAL_DROP_EVENT, handleSimpleMaterialDrop);
	document.addEventListener(SIMPLE_MATERIAL_PICK_DIRECTORY_EVENT, () => void bindings.pickSimpleMaterialDirectory());
	document.addEventListener(SIMPLE_MATERIAL_PICK_FILES_EVENT, () => void bindings.pickSimpleMaterialFiles());
	document.addEventListener(SIMPLE_AUDIO_DROP_EVENT, handleSimpleAudioDrop);
	document.addEventListener(SIMPLE_AUDIO_PICK_EVENT, () => void bindings.pickSimpleAudioFiles());
	document.addEventListener(SIMPLE_TRANSCRIBE_EVENT, () => void bindings.runSimpleTranscription());
	document.addEventListener(SIMPLE_PREVIEW_REQUEST_EVENT, () => void bindings.sendSimpleEditRequest("preview"));
	document.addEventListener(SIMPLE_FINAL_RENDER_EVENT, () => void bindings.sendSimpleEditRequest("final"));
	document.addEventListener(EDIT_REQUEST_CHANGE_EVENT, bindings.handleEditRequestChange);
	document.addEventListener(MATERIAL_CANCEL_ANALYSIS_EVENT, () => void bindings.cancelMaterialAnalysis());
	document.addEventListener(LANGUAGE_CHANGE_EVENT, handleLanguageChange);
	document.addEventListener(PROJECT_DIALOG_CLOSE_EVENT, () => bindings.setProjectDialogOpen(false));
	document.addEventListener(PROJECT_DIALOG_CREATE_EVENT, () => void bindings.createProjectFromDialog());
	document.addEventListener(PROJECT_DIALOG_OPEN_PROJECT_EVENT, handleProjectDialogOpenProject);
	document.addEventListener(CONFIRM_DIALOG_CLOSE_EVENT, (event) =>
		bindings.closeConfirmDialog(Boolean((event as CustomEvent).detail?.confirmed)),
	);
	document.addEventListener(PROJECT_CHANGE_EVENT, () => bindings.changeProject());
	document.addEventListener("keydown", (event) => {
		const appState = getAppState();
		if (event.key === "Escape" && appState.confirmDialog.open) {
			bindings.closeConfirmDialog(false);
			return;
		}
		if (event.key === "Escape" && appState.projectDialogOpen) {
			bindings.setProjectDialogOpen(false);
		}
	});
}
