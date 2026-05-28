import { editApp } from "./api.js";
import { log } from "./log.js";
import { state } from "./state.js";
import { getAppState, patchAppState } from "./store/app-store.js";
import type { CodexModel } from "./types.js";

type CodexModelControllerOptions = {
	readonly saveState: () => void;
};

export function codexModelValue(model: CodexModel) {
	return String(model.model || model.id || "").trim();
}

function normalizeCodexModel(item: any): CodexModel | null {
	const id = String(item?.id || item?.model || "").trim();
	const model = String(item?.model || item?.id || "").trim();
	if (!id || !model) {
		return null;
	}
	return {
		id,
		model,
		displayName: String(item?.displayName || item?.name || model),
		defaultReasoningEffort: item?.defaultReasoningEffort ? String(item.defaultReasoningEffort) : "",
		isDefault: Boolean(item?.isDefault),
		hidden: Boolean(item?.hidden),
	};
}

export function createCodexModelController({ saveState }: CodexModelControllerOptions) {
	function syncCodexModelStore() {
		patchAppState({
			codexModels: [...state.codexModels],
			codexModel: state.codexModel,
			codexModelStatusKey: state.codexModelStatusKey,
			codexModelStatusValues: { ...state.codexModelStatusValues },
		});
	}

	function renderCodexModelStatus() {
		syncCodexModelStore();
	}

	function setCodexModelStatus(key: string, values: Record<string, string | number> = {}) {
		state.codexModelStatusKey = key;
		state.codexModelStatusValues = values;
		renderCodexModelStatus();
	}

	function renderCodexModelOptions() {
		let selected = state.codexModel || getAppState().codexModel || "";
		const seen = new Set([""]);
		for (const model of state.codexModels) {
			const value = codexModelValue(model);
			if (!value || seen.has(value)) {
				continue;
			}
			seen.add(value);
		}

		if (selected && !seen.has(selected)) {
			if (state.codexModels.length) {
				log("saved model unavailable; using Codex default", { model: selected });
				selected = "";
				state.codexModel = "";
			}
		}
		state.codexModel = selected;
		syncCodexModelStore();
	}

	async function loadCodexModels() {
		patchAppState({ codexModelsLoading: true });
		setCodexModelStatus("codex.modelLoading");
		try {
			const result = await editApp.listCodexModels({ limit: 100, includeHidden: false });
			state.codexModels = (Array.isArray(result?.data) ? result.data : [])
				.map(normalizeCodexModel)
				.filter((item): item is CodexModel => Boolean(item));
			renderCodexModelOptions();
			setCodexModelStatus("codex.modelLoaded", { count: state.codexModels.length });
		} catch (error) {
			state.codexModels = [];
			renderCodexModelOptions();
			setCodexModelStatus("codex.modelLoadFailed");
			log("model/list error", { message: error.message });
		} finally {
			patchAppState({ codexModelsLoading: false });
		}
	}

	function selectedCodexReasoningEffort() {
		const selected = state.codexModel || getAppState().codexModel || "";
		const model = state.codexModels.find((item) => codexModelValue(item) === selected);
		return model?.defaultReasoningEffort || "medium";
	}

	function selectedCodexModelForRun() {
		const selected = String(state.codexModel || getAppState().codexModel || "").trim();
		if (selected && state.codexModels.length && !state.codexModels.some((item) => codexModelValue(item) === selected)) {
			log("selected model unavailable; using Codex default", { model: selected });
			state.codexModel = "";
			syncCodexModelStore();
			saveState();
			return "";
		}
		return selected;
	}

	function setSelectedCodexModel(model: string) {
		state.codexModel = String(model || "");
		syncCodexModelStore();
	}

	return {
		loadCodexModels,
		renderCodexModelOptions,
		renderCodexModelStatus,
		selectedCodexModelForRun,
		selectedCodexReasoningEffort,
		setSelectedCodexModel,
		syncCodexModelStore,
	};
}
