import { t } from "./i18n.js";
import { state } from "./state.js";
import { getAppState, patchAppState } from "./store/app-store.js";

type RunStateControllerOptions = {
	readonly directRunLabel: (action: string) => string;
	readonly schedulePersistProjectStateFile: () => void;
	readonly syncMaterialStore: () => void;
};

export function createRunStateController({
	directRunLabel,
	schedulePersistProjectStateFile,
	syncMaterialStore,
}: RunStateControllerOptions) {
	function progressPercent(value: any) {
		const number = Number(value);
		if (!Number.isFinite(number)) {
			return 0;
		}
		return Math.max(0, Math.min(100, Math.round(number * 100)));
	}

	function normalizedProgress(payload: any) {
		const rawProgress = Number(payload?.progress);
		return {
			progress: Number.isFinite(rawProgress) ? Math.max(0, Math.min(1, rawProgress)) : 0,
			message: String(payload?.message || ""),
			path: String(payload?.path || ""),
			current: Number(payload?.current || 0),
			total: Number(payload?.total || 0),
		};
	}

	function setStatus(text: string, kind = "idle") {
		state.statusText = text;
		state.statusKind = kind;
		getAppState().setStatus({ statusText: text, statusKind: kind });
	}

	function setIngestProgress(payload: any, options: { persist?: boolean } = {}) {
		const normalized = normalizedProgress(payload);
		state.ingestProgress = normalized;
		if (normalized.message) {
			state.appBusyMessage = normalized.message;
		}
		patchAppState({
			ingestProgress: normalized,
			appBusyMessage: state.appBusyMessage,
		});
		if (options.persist !== false) {
			schedulePersistProjectStateFile();
		}
	}

	function updateCodexRunControls() {
		getAppState().setRunFlags({
			appLocked: state.appLocked,
			directRunRunning: state.directRunRunning,
			codexTurnRunning: state.codexTurnRunning,
			codexInterruptRequested: state.codexInterruptRequested,
			runningAction: state.directRunRunning ? state.runningAction : "",
		});
	}

	function setDirectRunRunning(running: boolean, label = "") {
		state.directRunRunning = running;
		getAppState().setRunFlags({
			directRunRunning: running,
			runningAction: running ? state.runningAction : "",
			directRunLabel: running ? label : "",
		});
		updateCodexRunControls();
	}

	function setCodexTurnRunning(running: boolean, interruptRequested = false) {
		state.codexTurnRunning = running;
		state.codexInterruptRequested = running && interruptRequested;
		updateCodexRunControls();
	}

	function setIngestRunning(running: boolean) {
		state.ingestRunning = running;
		getAppState().setRunFlags({ ingestRunning: running });
		syncMaterialStore();
	}

	function setAppLocked(locked: boolean, message = "", title = t("busy.processing")) {
		state.appLocked = locked;
		state.appBusyTitle = title;
		state.appBusyMessage = message || t("busy.wait");
		patchAppState({
			appLocked: locked,
			appBusyTitle: state.appBusyTitle,
			appBusyMessage: state.appBusyMessage,
		});
		setIngestRunning(state.ingestRunning);
		setDirectRunRunning(state.directRunRunning, state.runningAction ? directRunLabel(state.runningAction) : "");
		updateCodexRunControls();
	}

	return {
		progressPercent,
		setAppLocked,
		setCodexTurnRunning,
		setDirectRunRunning,
		setIngestProgress,
		setIngestRunning,
		setStatus,
		updateCodexRunControls,
	};
}
