import { log } from "./log.js";
import { state } from "./state.js";
import { getAppState, patchAppState } from "./store/app-store.js";
import type { AnalysisResult } from "./types.js";

type AnalysisStateControllerOptions = {
	readonly persistAnalysisStateFile: () => void;
	readonly saveState: () => void;
};

function normalizeAnalysisResult(item: any): AnalysisResult | null {
	const key = String(item?.key || "").trim();
	if (!key) {
		return null;
	}
	const status = ["done", "error", "running"].includes(String(item?.status)) ? String(item.status) : "done";
	return {
		key,
		label: String(item?.label || ""),
		status,
		detail: String(item?.detail || ""),
		path: String(item?.path || ""),
	};
}

export function createAnalysisStateController({ persistAnalysisStateFile, saveState }: AnalysisStateControllerOptions) {
	function renderAnalysisResults() {
		patchAppState({ analysisResults: state.analysisResults.map((item) => ({ ...item })) });
	}

	function setAnalysisResult(key: string, label: string, status: string, detail: string, path = "") {
		const next = { key, label, status, detail, path };
		const index = state.analysisResults.findIndex((item) => item.key === key);
		if (index >= 0) {
			state.analysisResults[index] = next;
		} else {
			state.analysisResults.push(next);
		}
		renderAnalysisResults();
		saveState();
		persistAnalysisStateFile();
	}

	function setAnalysisResults(results: any[], options: { persistFile?: boolean } = {}) {
		state.analysisResults = results
			.map(normalizeAnalysisResult)
			.filter((item): item is AnalysisResult => Boolean(item));
		getAppState().setAnalysisResults(state.analysisResults);
		renderAnalysisResults();
		saveState();
		if (options.persistFile !== false) {
			persistAnalysisStateFile();
		}
	}

	function setAnalysisTitleText(title: string) {
		state.analysisTitleText = String(title || "").trim();
		patchAppState({ analysisTitleText: state.analysisTitleText });
	}

	async function notifyAnalysisComplete(message: string) {
		if (!("Notification" in window)) {
			return;
		}
		try {
			if (Notification.permission === "default") {
				await Notification.requestPermission();
			}
			if (Notification.permission === "granted") {
				new Notification("Video Edit", { body: message });
			}
		} catch (error) {
			log("notification skipped", { message: error.message });
		}
	}

	return {
		notifyAnalysisComplete,
		renderAnalysisResults,
		setAnalysisResult,
		setAnalysisResults,
		setAnalysisTitleText,
	};
}
