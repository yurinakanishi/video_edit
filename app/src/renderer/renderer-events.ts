import { editApp } from "./api.js";
import {
	CODEX_MODEL_CHANGE_EVENT,
	CODEX_MODELS_REFRESH_EVENT,
	CODEX_SEND_REQUEST_EVENT,
	CODEX_STOP_EVENT,
	CONFIRM_DIALOG_CLOSE_EVENT,
	FILE_DROP_EVENT,
	FILE_PICK_EVENT,
	GLOSSARY_ADD_TERM_EVENT,
	GLOSSARY_LOAD_CANDIDATES_EVENT,
	GLOSSARY_TERM_CHANGE_EVENT,
	GLOSSARY_TERM_REMOVE_EVENT,
	LANGUAGE_CHANGE_EVENT,
	MATERIAL_ANALYZE_EVENT,
	MATERIAL_CANCEL_ANALYSIS_EVENT,
	MATERIAL_DROP_EVENT,
	MATERIAL_ITEM_REANALYZE_EVENT,
	MATERIAL_ITEM_REMOVE_EVENT,
	MATERIAL_PICK_DIRECTORY_EVENT,
	MATERIAL_PICK_FILES_EVENT,
	MATERIAL_ROLE_CHANGE_EVENT,
	MATERIAL_SOURCE_REMOVE_EVENT,
	OUTPUT_OPEN_EVENT,
	OUTPUT_PICK_EVENT,
	OUTPUT_PREVIEW_ENTRY_OPEN_EVENT,
	OUTPUT_PREVIEW_OPEN_FOLDER_EVENT,
	OUTPUT_PREVIEW_REFRESH_EVENT,
	PROJECT_CHANGE_EVENT,
	PROJECT_COPY_ASSETS_EVENT,
	PROJECT_CREATE_EVENT,
	PROJECT_DELETE_EVENT,
	PROJECT_DIALOG_CLOSE_EVENT,
	PROJECT_DIALOG_CREATE_EVENT,
	PROJECT_DIALOG_OPEN_PROJECT_EVENT,
	PROJECT_FORM_CHANGE_EVENT,
	RUN_PRESET_EVENT,
	RUN_REFRESH_COMMAND_EVENT,
	RUN_REFRESH_PROMPT_EVENT,
	STILL_IMAGE_REMOVE_EVENT,
	SUBTITLE_MODE_CHANGE_EVENT,
	SYNC_REPORT_REFRESH_EVENT,
	TOOL_PICK_EVENT,
	WORKFLOW_SECTION_CHANGE_EVENT,
} from "./events.js";
import { normalizeLanguage, state } from "./state.js";
import { getAppState, normalizeWorkflowSection } from "./store/app-store.js";
import type { ProjectListEntry } from "./types.js";

type RendererEventBindings = {
	readonly addGlossaryTerm: () => void;
	readonly addMaterialSources: (paths: string[]) => void;
	readonly addStillImages: (paths: string[]) => void;
	readonly cancelMaterialAnalysis: () => Promise<void>;
	readonly changeProject: () => void;
	readonly closeConfirmDialog: (confirmed: boolean) => void;
	readonly copyAssetsToProject: () => Promise<boolean>;
	readonly createProjectFromDialog: () => Promise<void>;
	readonly createProjectFromForm: () => Promise<void>;
	readonly deleteCurrentProject: () => Promise<void>;
	readonly handleGlossaryTermChange: (event: Event) => void;
	readonly handleGlossaryTermRemove: (event: Event) => void;
	readonly handleMaterialItemRemove: (event: Event) => void;
	readonly handleMaterialRoleChange: (event: Event) => void;
	readonly handleMaterialSourceRemove: (event: Event) => void;
	readonly reanalyzeMaterialItem: (event: Event) => Promise<boolean>;
	readonly handleNotification: (payload: any) => void;
	readonly handleStillImageRemove: (event: Event) => void;
	readonly ingestMaterialDirectory: (directoryPath?: string) => Promise<boolean>;
	readonly loadCodexModels: () => Promise<void>;
	readonly loadGlossaryCandidates: () => Promise<void>;
	readonly loadOutputPreview: (kind: string) => Promise<any>;
	readonly openProject: (entry: ProjectListEntry) => Promise<void>;
	readonly outputPreviewTarget: () => string;
	readonly pickFile: (slot: string) => Promise<void>;
	readonly pickMaterialDirectory: () => Promise<void>;
	readonly pickMaterialFiles: () => Promise<void>;
	readonly pickOutput: () => Promise<void>;
	readonly pickTool: (id: string) => Promise<void>;
	readonly refreshCommand: () => void;
	readonly refreshPrompt: () => void;
	readonly refreshSyncReport: () => Promise<void>;
	readonly runPreset: () => Promise<any>;
	readonly saveState: () => void;
	readonly sendRequest: () => Promise<void>;
	readonly setActiveSection: (section: string) => void;
	readonly setFile: (slot: string, filePath: string) => void;
	readonly setLanguage: (language: "ja" | "en") => void;
	readonly setProjectDialogOpen: (open: boolean) => void;
	readonly setSelectedCodexModel: (model: string) => void;
	readonly setSubtitleMode: (mode: string | undefined) => void;
	readonly stopCodexTurn: () => Promise<void>;
};

const fileDropSlots = new Set([
	"masterVideo",
	"rightCloseVideo",
	"leftCloseVideo",
	"referenceVideo",
	"externalAudio",
	"logo",
	"stillImages",
]);

function pathsFromDroppedFiles(files: File[]) {
	return files.map((file) => editApp.filePath(file)).filter(Boolean);
}

export function bindRendererEvents(bindings: RendererEventBindings) {
	function handleCodexModelChange(event: Event) {
		bindings.setSelectedCodexModel(String((event as CustomEvent).detail?.model || ""));
		bindings.refreshPrompt();
	}

	function handleLanguageChange(event: Event) {
		bindings.setLanguage(normalizeLanguage((event as CustomEvent).detail?.language));
	}

	function handleSubtitleModeChange(event: Event) {
		bindings.setSubtitleMode((event as CustomEvent).detail?.mode);
		bindings.refreshPrompt();
	}

	function handleWorkflowSectionChange(event: Event) {
		const section = normalizeWorkflowSection((event as CustomEvent).detail?.section);
		bindings.setActiveSection(section);
		bindings.saveState();
		if (section === "run" && !state.codexModels.length) {
			void bindings.loadCodexModels();
		}
		window.scrollTo({ top: 0, behavior: "smooth" });
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

	function handleFilePick(event: Event) {
		const slot = String((event as CustomEvent).detail?.slot || "");
		if (slot) {
			void bindings.pickFile(slot);
		}
	}

	function handleToolPick(event: Event) {
		const id = String((event as CustomEvent).detail?.id || "");
		if (id) {
			void bindings.pickTool(id);
		}
	}

	function handleFileDrop(event: Event) {
		const detail = (event as CustomEvent).detail || {};
		const slot = String(detail.slot || "");
		if (!fileDropSlots.has(slot)) {
			return;
		}
		const paths = pathsFromDroppedFiles(Array.isArray(detail.files) ? detail.files : []);
		if (!paths.length) {
			return;
		}
		if (slot === "stillImages") {
			bindings.addStillImages(paths);
			return;
		}
		bindings.setFile(slot, paths[0]);
	}

	function handleMaterialDrop(event: Event) {
		const detail = (event as CustomEvent).detail || {};
		const paths = pathsFromDroppedFiles(Array.isArray(detail.files) ? detail.files : []);
		if (paths.length) {
			bindings.addMaterialSources(paths);
		}
	}

	document.addEventListener(FILE_PICK_EVENT, handleFilePick);
	document.addEventListener(FILE_DROP_EVENT, handleFileDrop);
	document.addEventListener(TOOL_PICK_EVENT, handleToolPick);
	document.addEventListener(OUTPUT_PICK_EVENT, () => void bindings.pickOutput());
	document.addEventListener(OUTPUT_OPEN_EVENT, () => void bindings.loadOutputPreview("output"));
	document.addEventListener(OUTPUT_PREVIEW_REFRESH_EVENT, handleOutputPreviewRefresh);
	document.addEventListener(OUTPUT_PREVIEW_OPEN_FOLDER_EVENT, handleOutputPreviewOpenFolder);
	document.addEventListener(OUTPUT_PREVIEW_ENTRY_OPEN_EVENT, handleOutputPreviewEntryOpen);
	document.addEventListener(RUN_PRESET_EVENT, () => void bindings.runPreset());
	document.addEventListener(CODEX_SEND_REQUEST_EVENT, () => void bindings.sendRequest());
	document.addEventListener(CODEX_STOP_EVENT, () => void bindings.stopCodexTurn());
	document.addEventListener(RUN_REFRESH_COMMAND_EVENT, () => bindings.refreshCommand());
	document.addEventListener(RUN_REFRESH_PROMPT_EVENT, () => bindings.refreshPrompt());
	document.addEventListener(CODEX_MODELS_REFRESH_EVENT, () => void bindings.loadCodexModels());
	document.addEventListener(SYNC_REPORT_REFRESH_EVENT, () => void bindings.refreshSyncReport());
	document.addEventListener(GLOSSARY_LOAD_CANDIDATES_EVENT, () => void bindings.loadGlossaryCandidates());
	document.addEventListener(GLOSSARY_ADD_TERM_EVENT, () => bindings.addGlossaryTerm());
	document.addEventListener(MATERIAL_ROLE_CHANGE_EVENT, bindings.handleMaterialRoleChange);
	document.addEventListener(MATERIAL_SOURCE_REMOVE_EVENT, bindings.handleMaterialSourceRemove);
	document.addEventListener(MATERIAL_ITEM_REMOVE_EVENT, bindings.handleMaterialItemRemove);
	document.addEventListener(MATERIAL_ITEM_REANALYZE_EVENT, (event) => void bindings.reanalyzeMaterialItem(event));
	document.addEventListener(MATERIAL_DROP_EVENT, handleMaterialDrop);
	document.addEventListener(MATERIAL_PICK_DIRECTORY_EVENT, () => void bindings.pickMaterialDirectory());
	document.addEventListener(MATERIAL_PICK_FILES_EVENT, () => void bindings.pickMaterialFiles());
	document.addEventListener(MATERIAL_ANALYZE_EVENT, () => void bindings.ingestMaterialDirectory());
	document.addEventListener(MATERIAL_CANCEL_ANALYSIS_EVENT, () => void bindings.cancelMaterialAnalysis());
	document.addEventListener(STILL_IMAGE_REMOVE_EVENT, bindings.handleStillImageRemove);
	document.addEventListener(GLOSSARY_TERM_CHANGE_EVENT, bindings.handleGlossaryTermChange);
	document.addEventListener(GLOSSARY_TERM_REMOVE_EVENT, bindings.handleGlossaryTermRemove);
	document.addEventListener(CODEX_MODEL_CHANGE_EVENT, handleCodexModelChange);
	document.addEventListener(WORKFLOW_SECTION_CHANGE_EVENT, handleWorkflowSectionChange);
	document.addEventListener(LANGUAGE_CHANGE_EVENT, handleLanguageChange);
	document.addEventListener(SUBTITLE_MODE_CHANGE_EVENT, handleSubtitleModeChange);
	document.addEventListener(PROJECT_DIALOG_CLOSE_EVENT, () => bindings.setProjectDialogOpen(false));
	document.addEventListener(PROJECT_DIALOG_CREATE_EVENT, () => void bindings.createProjectFromDialog());
	document.addEventListener(PROJECT_DIALOG_OPEN_PROJECT_EVENT, handleProjectDialogOpenProject);
	document.addEventListener(CONFIRM_DIALOG_CLOSE_EVENT, (event) =>
		bindings.closeConfirmDialog(Boolean((event as CustomEvent).detail?.confirmed)),
	);
	document.addEventListener(PROJECT_CREATE_EVENT, () => void bindings.createProjectFromForm());
	document.addEventListener(PROJECT_CHANGE_EVENT, () => bindings.changeProject());
	document.addEventListener(PROJECT_COPY_ASSETS_EVENT, () => void bindings.copyAssetsToProject());
	document.addEventListener(PROJECT_DELETE_EVENT, () => void bindings.deleteCurrentProject());
	document.addEventListener(PROJECT_FORM_CHANGE_EVENT, () => bindings.refreshPrompt());
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
