import { log } from "./log.js";
import { state } from "./state.js";
import { getAppState, patchAppState } from "./store/app-store.js";
import type { AnalysisResult, MaterialAnalysisProgress } from "./types.js";

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

function materialProgressKey(filePath: string) {
	return String(filePath || "").trim().toLowerCase();
}

function normalizeProgressStatus(value: any): MaterialAnalysisProgress["status"] {
	return ["waiting", "running", "done", "error"].includes(String(value))
		? (String(value) as MaterialAnalysisProgress["status"])
		: "waiting";
}

function normalizeProgressValue(value: any) {
	const number = Number(value);
	if (!Number.isFinite(number)) {
		return 0;
	}
	return Math.max(0, Math.min(1, number));
}

function normalizeMaterialAnalysisProgress(item: any): MaterialAnalysisProgress | null {
	const path = String(item?.path || "").trim();
	const key = materialProgressKey(item?.key || path);
	if (!path || !key) {
		return null;
	}
	return {
		key,
		path,
		progress: normalizeProgressValue(item?.progress),
		status: normalizeProgressStatus(item?.status),
		message: String(item?.message || ""),
		updatedAt: String(item?.updatedAt || new Date().toISOString()),
	};
}

function normalizeMaterialAnalysisProgressMap(value: any): Record<string, MaterialAnalysisProgress> {
	const entries = Array.isArray(value)
		? value
		: value && typeof value === "object"
			? Object.values(value)
			: [];
	return Object.fromEntries(
		entries
			.map(normalizeMaterialAnalysisProgress)
			.filter((item): item is MaterialAnalysisProgress => Boolean(item))
			.map((item) => [item.key, item]),
	);
}

export function createAnalysisStateController({ persistAnalysisStateFile, saveState }: AnalysisStateControllerOptions) {
	function renderAnalysisResults() {
		patchAppState({ analysisResults: state.analysisResults.map((item) => ({ ...item })) });
	}

	function renderMaterialAnalysisProgress() {
		patchAppState({ materialAnalysisProgress: { ...state.materialAnalysisProgress } });
	}

	function commitMaterialAnalysisProgress(options: { persistFile?: boolean; saveState?: boolean } = {}) {
		renderMaterialAnalysisProgress();
		if (options.saveState !== false) {
			saveState();
		}
		if (options.persistFile !== false) {
			persistAnalysisStateFile();
		}
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

	function setMaterialAnalysisProgress(
		filePath: string,
		progress: Partial<MaterialAnalysisProgress>,
		options: { persistFile?: boolean; saveState?: boolean } = {},
	) {
		const path = String(progress.path || filePath || "").trim();
		const key = materialProgressKey(progress.key || path);
		if (!path || !key) {
			return;
		}
		const current = state.materialAnalysisProgress[key] || {
			key,
			path,
			progress: 0,
			status: "waiting",
			message: "",
			updatedAt: "",
		};
		state.materialAnalysisProgress[key] = {
			...current,
			...progress,
			key,
			path,
			progress: normalizeProgressValue(progress.progress ?? current.progress),
			status: normalizeProgressStatus(progress.status ?? current.status),
			message: String(progress.message ?? current.message ?? ""),
			updatedAt: new Date().toISOString(),
		};
		commitMaterialAnalysisProgress(options);
	}

	function setMaterialAnalysisProgressForPaths(
		paths: string[],
		progress: Partial<MaterialAnalysisProgress>,
		options: { persistFile?: boolean; saveState?: boolean } = {},
	) {
		const uniquePaths = [...new Set(paths.map(String).map((item) => item.trim()).filter(Boolean))];
		for (const filePath of uniquePaths) {
			const key = materialProgressKey(filePath);
			const current = state.materialAnalysisProgress[key] || {
				key,
				path: filePath,
				progress: 0,
				status: "waiting",
				message: "",
				updatedAt: "",
			};
			state.materialAnalysisProgress[key] = {
				...current,
				...progress,
				key,
				path: filePath,
				progress: normalizeProgressValue(progress.progress ?? current.progress),
				status: normalizeProgressStatus(progress.status ?? current.status),
				message: String(progress.message ?? current.message ?? ""),
				updatedAt: new Date().toISOString(),
			};
		}
		commitMaterialAnalysisProgress(options);
	}

	function setMaterialAnalysisProgressMap(
		progress: any,
		options: { persistFile?: boolean; saveState?: boolean } = {},
	) {
		state.materialAnalysisProgress = normalizeMaterialAnalysisProgressMap(progress);
		getAppState().setMaterialAnalysisProgress(state.materialAnalysisProgress);
		commitMaterialAnalysisProgress(options);
	}

	function removeMaterialAnalysisProgress(
		paths: string[],
		options: { persistFile?: boolean; saveState?: boolean } = {},
	) {
		const keys = new Set(paths.map(materialProgressKey).filter(Boolean));
		if (!keys.size) {
			return;
		}
		state.materialAnalysisProgress = Object.fromEntries(
			Object.entries(state.materialAnalysisProgress).filter(([key]) => !keys.has(key)),
		);
		commitMaterialAnalysisProgress(options);
	}

	function retainMaterialAnalysisProgress(
		paths: string[],
		options: { persistFile?: boolean; saveState?: boolean } = {},
	) {
		const keys = new Set(paths.map(materialProgressKey).filter(Boolean));
		state.materialAnalysisProgress = Object.fromEntries(
			Object.entries(state.materialAnalysisProgress).filter(([key]) => keys.has(key)),
		);
		commitMaterialAnalysisProgress(options);
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
		renderMaterialAnalysisProgress,
		setAnalysisResult,
		setAnalysisResults,
		setMaterialAnalysisProgress,
		setMaterialAnalysisProgressForPaths,
		setMaterialAnalysisProgressMap,
		removeMaterialAnalysisProgress,
		retainMaterialAnalysisProgress,
		setAnalysisTitleText,
	};
}
