import { Ban, Upload } from "lucide-react";
import { MATERIAL_CANCEL_ANALYSIS_EVENT } from "../events.js";
import { localizePlainText, t } from "../i18n.js";
import { useAppStore } from "../store/app-store.js";
import { Button } from "./ui/button.js";
import { Progress } from "./ui/progress.js";

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
		<div
			className="app-busy-overlay fixed inset-0 z-[1000] grid place-items-center bg-background/80 p-5 backdrop-blur-sm"
			id="appBusyOverlay"
			hidden={!appLocked}
		>
			<div className="grid min-w-72 gap-2 rounded-lg border border-border bg-card p-5 text-card-foreground shadow-xl">
				<strong id="appBusyTitle" className="text-base text-accent-foreground">
					{localizePlainText(appBusyTitle || t("busy.processing"))}
				</strong>
				<span id="appBusyMessage" className="text-sm text-muted-foreground">
					{appBusyMessage ? localizePlainText(appBusyMessage) : t("busy.wait")}
				</span>
				<div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 pt-1">
					<Progress value={percent} fillId="appBusyProgressFill" />
					<small id="appBusyProgressPercent" className="text-xs font-semibold text-accent-foreground">
						{percent}%
					</small>
				</div>
				{showCancel ? (
					<div className="flex justify-end pt-2">
						<Button
							type="button"
							variant="destructive"
							size="sm"
							disabled={!canCancelAnalysis}
							onClick={dispatchMaterialAnalysisCancel}
						>
							<Ban className="size-4" aria-hidden="true" />
							{materialAnalysisCancelRequested ? t("action.canceling") : t("action.cancel")}
						</Button>
					</div>
				) : null}
			</div>
		</div>
	);
}

export function Overlays() {
	return (
		<>
			<div
				className="pointer-events-none invisible fixed inset-x-4 bottom-4 top-20 z-[800] grid place-items-center opacity-0 transition"
				id="globalDropOverlay"
				aria-hidden="true"
			>
				<div className="grid w-[min(560px,calc(100vw-40px))] grid-cols-[52px_minmax(0,1fr)] items-center gap-4 rounded-lg border border-primary bg-card/95 p-4 shadow-2xl">
					<span
						className="grid size-12 place-items-center rounded-full border border-primary/25 bg-accent text-accent-foreground"
						aria-hidden="true"
					>
						<Upload className="size-5" />
					</span>
					<div className="min-w-0">
						<strong className="block text-base text-accent-foreground">ファイルをドロップできます</strong>
						<span className="text-sm text-muted-foreground">素材または音声のエリアへドロップできます</span>
					</div>
				</div>
			</div>
			<AppBusyOverlay />
		</>
	);
}
