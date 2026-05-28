import { MATERIAL_CANCEL_ANALYSIS_EVENT } from "../events.js";
import { localizePlainText, t } from "../i18n.js";
import { useAppStore } from "../store/app-store.js";

function progressPercent(value: number) {
	return Math.max(0, Math.min(100, Math.round(Number(value || 0) * 100)));
}

function dispatchMaterialAnalysisCancel() {
	document.dispatchEvent(new CustomEvent(MATERIAL_CANCEL_ANALYSIS_EVENT));
}

function AppBusyOverlay() {
	const appLocked = useAppStore((store) => store.appLocked);
	const appBusyTitle = useAppStore((store) => store.appBusyTitle);
	const appBusyMessage = useAppStore((store) => store.appBusyMessage);
	const progress = useAppStore((store) => store.ingestProgress.progress);
	const ingestRunning = useAppStore((store) => store.ingestRunning);
	const materialAnalysisCancelable = useAppStore((store) => store.materialAnalysisCancelable);
	const materialAnalysisCancelRequested = useAppStore((store) => store.materialAnalysisCancelRequested);
	const percent = progressPercent(progress);
	const canCancelAnalysis = ingestRunning && materialAnalysisCancelable && !materialAnalysisCancelRequested;
	const showCancel = ingestRunning && (materialAnalysisCancelable || materialAnalysisCancelRequested);

	return (
		<div className="app-busy-overlay" id="appBusyOverlay" hidden={!appLocked}>
			<div>
				<strong id="appBusyTitle">{localizePlainText(appBusyTitle || t("busy.processing"))}</strong>
				<span id="appBusyMessage">{appBusyMessage ? localizePlainText(appBusyMessage) : t("busy.wait")}</span>
				<div className="busy-progress">
					<div className="busy-progress-bar">
						<span id="appBusyProgressFill" style={{ width: `${percent}%` }}></span>
					</div>
					<small id="appBusyProgressPercent">{percent}%</small>
				</div>
				{showCancel ? (
					<div className="busy-actions">
						<button
							type="button"
							className="danger-button busy-cancel-button"
							disabled={!canCancelAnalysis}
							onClick={dispatchMaterialAnalysisCancel}
						>
							{materialAnalysisCancelRequested ? t("action.canceling") : t("action.cancel")}
						</button>
					</div>
				) : null}
			</div>
		</div>
	);
}

export function Overlays() {
	return (
		<>
			<div className="global-drop-overlay" id="globalDropOverlay" aria-hidden="true">
				<div className="global-drop-card">
					<span className="drop-target-icon" aria-hidden="true"></span>
					<div>
						<strong>ファイルをドロップできます</strong>
						<span>素材エリアまたは各スロットの上にドロップしてください</span>
					</div>
				</div>
			</div>
			<AppBusyOverlay />
		</>
	);
}
