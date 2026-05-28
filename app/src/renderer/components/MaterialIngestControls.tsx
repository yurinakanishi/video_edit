import {
	MATERIAL_ANALYZE_EVENT,
	MATERIAL_CANCEL_ANALYSIS_EVENT,
	MATERIAL_PICK_DIRECTORY_EVENT,
	MATERIAL_PICK_FILES_EVENT,
	MATERIAL_SYNC_EVENT,
} from "../events.js";
import { localizePlainText, t } from "../i18n.js";
import { shortPath } from "../preview.js";
import { useAppStore } from "../store/app-store.js";

function progressPercent(value: number) {
	return Math.max(0, Math.min(100, Math.round(Number(value || 0) * 100)));
}

function dispatchMaterialAction(eventName: string) {
	document.dispatchEvent(new CustomEvent(eventName));
}

function analyzedTimeSourceCount(mediaManifest: any | null) {
	const files = Array.isArray(mediaManifest?.files) ? mediaManifest.files : [];
	return files.filter((item: any) => {
		const kind = String(item?.kind || "");
		const role = String(item?.role || "");
		const duration = Number(item?.metadata?.duration || 0);
		return (kind === "video" || kind === "audio") && role !== "ignore" && duration > 0;
	}).length;
}

export function MaterialIngestActions() {
	const appLocked = useAppStore((store) => store.appLocked);
	const ingestRunning = useAppStore((store) => store.ingestRunning);
	const materialPaths = useAppStore((store) => store.materialPaths);
	const mediaManifest = useAppStore((store) => store.mediaManifest);
	const materialAnalysisCancelable = useAppStore((store) => store.materialAnalysisCancelable);
	const materialAnalysisCancelRequested = useAppStore((store) => store.materialAnalysisCancelRequested);
	const hasMaterialSources = Boolean(materialPaths.length || mediaManifest?.files?.length);
	const canSyncMaterial = analyzedTimeSourceCount(mediaManifest) >= 2;
	const cancelRequested = ingestRunning && materialAnalysisCancelRequested;
	const canCancelAnalysis = ingestRunning && materialAnalysisCancelable && !cancelRequested;
	const canClearSources = !ingestRunning && hasMaterialSources && !appLocked;
	const cancelLabel = cancelRequested
		? t("action.canceling")
		: canCancelAnalysis
			? t("action.cancel")
			: t("action.clear");

	return (
		<div className="folder-actions">
			<button
				type="button"
				id="pickMaterialDirectory"
				disabled={ingestRunning || appLocked}
				onClick={() => dispatchMaterialAction(MATERIAL_PICK_DIRECTORY_EVENT)}
			>
				Folder
			</button>
			<button
				type="button"
				id="pickMaterialFiles"
				disabled={ingestRunning || appLocked}
				onClick={() => dispatchMaterialAction(MATERIAL_PICK_FILES_EVENT)}
			>
				Files
			</button>
			<button
				type="button"
				className="primary-button"
				id="analyzeMaterialDirectory"
				hidden={!hasMaterialSources}
				disabled={ingestRunning || appLocked || !hasMaterialSources}
				onClick={() => dispatchMaterialAction(MATERIAL_ANALYZE_EVENT)}
			>
				解析
			</button>
			<button
				type="button"
				id="syncMaterial"
				hidden={!canSyncMaterial}
				disabled={ingestRunning || appLocked || !canSyncMaterial}
				onClick={() => dispatchMaterialAction(MATERIAL_SYNC_EVENT)}
			>
				{t("action.syncMaterial")}
			</button>
			<button
				type="button"
				id="cancelMaterialAnalysis"
				hidden={!canCancelAnalysis && !canClearSources && !cancelRequested}
				disabled={(!canCancelAnalysis && !canClearSources) || cancelRequested}
				onClick={() => dispatchMaterialAction(MATERIAL_CANCEL_ANALYSIS_EVENT)}
			>
				{cancelLabel}
			</button>
		</div>
	);
}

export function MaterialIngestProgress() {
	const ingestProgress = useAppStore((store) => store.ingestProgress);
	const percent = progressPercent(ingestProgress.progress);
	const count = ingestProgress.total > 0 ? ` (${ingestProgress.current || 0}/${ingestProgress.total})` : "";
	const message = `${localizePlainText(ingestProgress.message || t("progress.waitingAnalysis"))}${count}`;
	const pathLabel = ingestProgress.path ? shortPath(ingestProgress.path) : "-";

	return (
		<div className="ingest-progress" id="ingestProgress">
			<div className="ingest-progress-bar">
				<span id="ingestProgressFill" style={{ width: `${percent}%` }}></span>
			</div>
			<div className="ingest-progress-meta">
				<strong id="ingestProgressPercent">{percent}%</strong>
				<span id="ingestProgressText">{message}</span>
			</div>
			<code id="ingestProgressPath" title={ingestProgress.path}>
				{pathLabel}
			</code>
		</div>
	);
}
