import { log } from "./log.js";
import { state } from "./state.js";
import { getAppState, patchAppState } from "./store/app-store.js";
import type { AnalysisResult, MaterialAnalysisOutputStatus, MaterialAnalysisStatus } from "./types.js";

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

function materialStatusKey(filePath: string) {
	return String(filePath || "")
		.trim()
		.toLowerCase();
}

function normalizeMaterialAnalysisState(value: any): MaterialAnalysisStatus["state"] {
	return ["none", "partial", "done", "running", "error"].includes(String(value))
		? (String(value) as MaterialAnalysisStatus["state"])
		: "none";
}

function normalizeOutputStatus(item: any): MaterialAnalysisOutputStatus | null {
	const key = String(item?.key || "").trim();
	if (!key) {
		return null;
	}
	return {
		key,
		label: String(item?.label || key),
		labelKey: String(item?.labelKey || ""),
		path: String(item?.path || ""),
		exists: Boolean(item?.exists),
	};
}

function normalizeMaterialAnalysisStatus(item: any): MaterialAnalysisStatus | null {
	const path = String(item?.path || "").trim();
	const key = materialStatusKey(item?.key || path);
	if (!path || !key) {
		return null;
	}
	const outputs = (Array.isArray(item?.outputs) ? item.outputs : [])
		.map(normalizeOutputStatus)
		.filter((output): output is MaterialAnalysisOutputStatus => Boolean(output));
	const completed = Number.isFinite(Number(item?.completed))
		? Number(item.completed)
		: outputs.filter((output) => output.exists).length;
	const total = Number.isFinite(Number(item?.total)) ? Number(item.total) : outputs.length;
	return {
		key,
		path,
		state: normalizeMaterialAnalysisState(item?.state),
		completed,
		total,
		message: String(item?.message || ""),
		outputs,
		updatedAt: String(item?.updatedAt || new Date().toISOString()),
	};
}

function normalizeMaterialAnalysisStatusMap(value: any): Record<string, MaterialAnalysisStatus> {
	const entries = Array.isArray(value) ? value : value && typeof value === "object" ? Object.values(value) : [];
	return Object.fromEntries(
		entries
			.map(normalizeMaterialAnalysisStatus)
			.filter((item): item is MaterialAnalysisStatus => Boolean(item))
			.map((item) => [item.key, item]),
	);
}

export function createAnalysisStateController({ persistAnalysisStateFile, saveState }: AnalysisStateControllerOptions) {
	function renderAnalysisResults() {
		patchAppState({ analysisResults: state.analysisResults.map((item) => ({ ...item })) });
	}

	function renderMaterialAnalysisStatus() {
		patchAppState({ materialAnalysisStatus: { ...state.materialAnalysisStatus } });
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

	function setMaterialAnalysisStatusMap(status: any) {
		state.materialAnalysisStatus = normalizeMaterialAnalysisStatusMap(status);
		getAppState().setMaterialAnalysisStatus(state.materialAnalysisStatus);
		renderMaterialAnalysisStatus();
	}

	function removeMaterialAnalysisStatus(paths: string[]) {
		const keys = new Set(paths.map(materialStatusKey).filter(Boolean));
		if (!keys.size) {
			return;
		}
		state.materialAnalysisStatus = Object.fromEntries(
			Object.entries(state.materialAnalysisStatus).filter(([key]) => !keys.has(key)),
		);
		renderMaterialAnalysisStatus();
	}

	function setMaterialAnalysisRunning(filePath: string, message = "") {
		const path = String(filePath || "").trim();
		const key = materialStatusKey(path);
		if (!path || !key) {
			return;
		}
		const current = state.materialAnalysisStatus[key] || {
			key,
			path,
			state: "none",
			completed: 0,
			total: 0,
			message: "",
			outputs: [],
			updatedAt: "",
		};
		state.materialAnalysisStatus[key] = {
			...current,
			key,
			path,
			state: "running",
			message: message || current.message,
			updatedAt: new Date().toISOString(),
		};
		renderMaterialAnalysisStatus();
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
		renderMaterialAnalysisStatus,
		setAnalysisResult,
		setAnalysisResults,
		setMaterialAnalysisRunning,
		setMaterialAnalysisStatusMap,
		removeMaterialAnalysisStatus,
		setAnalysisTitleText,
	};
}
