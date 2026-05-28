import { applyTranslations, t } from "./i18n.js";
import { defaultGlossaryTerms, defaultPunchlines, LANGUAGE_STORAGE_KEY, normalizeLanguage, state } from "./state.js";
import { getAppState, normalizeSubtitleMode, normalizeWorkflowSection } from "./store/app-store.js";
import type { Locale } from "./types.js";

type AppSessionControllerOptions = {
	readonly directRunLabel: (action: string) => string;
	readonly renderAnalysisResults: () => void;
	readonly renderCodexModelOptions: () => void;
	readonly renderCodexModelStatus: () => void;
	readonly renderFileSlots: () => void;
	readonly renderGlossaryList: () => void;
	readonly renderMediaManifest: () => void;
	readonly renderOutputPreview: () => void;
	readonly renderOutputTargetPreview: () => void;
	readonly renderProjectDialogList: () => void;
	readonly renderStillImageList: () => void;
	readonly renderSyncReport: () => void;
	readonly renderWorkflowMediaPreviews: () => void;
	readonly refreshCommand: () => void;
	readonly setDirectRunRunning: (running: boolean, label?: string) => void;
	readonly setStatus: (text: string, kind?: string) => void;
	readonly updateRunSummary: () => void;
};

export function createAppSessionController({
	directRunLabel,
	renderAnalysisResults,
	renderCodexModelOptions,
	renderCodexModelStatus,
	renderFileSlots,
	renderGlossaryList,
	renderMediaManifest,
	renderOutputPreview,
	renderOutputTargetPreview,
	renderProjectDialogList,
	renderStillImageList,
	renderSyncReport,
	renderWorkflowMediaPreviews,
	refreshCommand,
	setDirectRunRunning,
	setStatus,
	updateRunSummary,
}: AppSessionControllerOptions) {
	function setActiveSection(section: string) {
		state.activeSection = normalizeWorkflowSection(section);
		getAppState().setActiveSection(state.activeSection);
	}

	function setLanguage(language: Locale) {
		state.language = normalizeLanguage(language);
		getAppState().setLanguage(state.language);
		localStorage.setItem(LANGUAGE_STORAGE_KEY, state.language);
		getAppState().setLanguageMenuOpen(false);
		applyTranslations();
		setStatus(state.statusText, state.statusKind);
		setDirectRunRunning(state.directRunRunning, state.runningAction ? directRunLabel(state.runningAction) : "");
		renderGlossaryList();
		renderFileSlots();
		renderWorkflowMediaPreviews();
		renderOutputTargetPreview();
		renderMediaManifest();
		renderStillImageList();
		renderAnalysisResults();
		renderProjectDialogList();
		renderSyncReport();
		renderOutputPreview();
		renderCodexModelOptions();
		renderCodexModelStatus();
		updateRunSummary();
		refreshCommand();
	}

	function setSubtitleMode(mode: string | undefined) {
		state.subtitleMode = normalizeSubtitleMode(mode);
		getAppState().setSubtitleMode(state.subtitleMode);
	}

	function restoreDefaultTextDrafts() {
		getAppState().setPunchlineText(defaultPunchlines);
		state.glossaryTerms = defaultGlossaryTerms;
	}

	function setWaitingAnalysisProgress(setIngestProgress: (payload: any) => void, path: string) {
		setIngestProgress({
			progress: 0,
			message:
				state.materialPaths.length || state.mediaManifest?.files?.length
					? t("progress.pressAnalyze")
					: t("progress.waitingAnalysis"),
			path,
		});
	}

	return {
		restoreDefaultTextDrafts,
		setActiveSection,
		setLanguage,
		setSubtitleMode,
		setWaitingAnalysisProgress,
	};
}
