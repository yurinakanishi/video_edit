import { editApp } from "./api.js";
import { t } from "./i18n.js";
import { log } from "./log.js";
import { state } from "./state.js";
import type { ProjectInfo } from "./types.js";

type RendererIpcBindings = {
	readonly handleNotification: (payload: any) => void;
	readonly handleWorkflowProgress: (payload: any) => void;
	readonly loadProjectStateFile: (project?: ProjectInfo | null) => Promise<boolean>;
	readonly refreshSyncReport: () => Promise<void>;
	readonly setCodexTurnRunning: (running: boolean, interruptRequested?: boolean) => void;
	readonly setIngestProgress: (payload: any) => void;
	readonly setIngestRunning: (running: boolean) => void;
	readonly setStatus: (text: string, kind?: string) => void;
};

export function bindRendererIpcEvents({
	handleNotification,
	handleWorkflowProgress,
	loadProjectStateFile,
	refreshSyncReport,
	setCodexTurnRunning,
	setIngestProgress,
	setIngestRunning,
	setStatus,
}: RendererIpcBindings) {
	editApp.onServerReady(() => {
		setStatus(t("status.codexReady"), "ready");
		log("server ready");
	});
	editApp.onServerError((payload) => {
		setCodexTurnRunning(false);
		setStatus(t("status.codexError"), "idle");
		log("server error", payload);
	});
	editApp.onServerExit((payload) => {
		setCodexTurnRunning(false);
		setStatus(t("status.codexExited"), "idle");
		log("server exit", payload);
	});
	editApp.onServerStderr((payload) => log("stderr", payload));
	editApp.onServerNotification(handleNotification);
	editApp.onWorkflowProgress(handleWorkflowProgress);
	editApp.onProjectStateChanged(async (payload) => {
		if (!state.project || payload?.project?.id !== state.project.id) {
			return;
		}
		await loadProjectStateFile(state.project);
	});
	editApp.onIngestProgress((payload) => {
		const progressPayload =
			state.fullAnalysisRunning && payload?.stage !== "canceled"
				? {
						...payload,
						progress: 0.02 + Math.min(1, Math.max(0, Number(payload?.progress || 0))) * 0.18,
					}
				: payload;
		setIngestProgress(progressPayload);
		if (payload?.stage === "canceled") {
			state.materialAnalysisCancelable = false;
			setIngestRunning(false);
		}
		const shouldLog = payload?.stage && !["probe", "copy"].includes(payload.stage);
		if (shouldLog && payload?.message) {
			log("ingest progress", {
				stage: payload.stage,
				current: payload.current,
				total: payload.total,
				message: payload.message,
				path: payload.path,
			});
		}
	});
	void refreshSyncReport();
}
