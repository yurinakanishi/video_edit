import { localizePlainText, t } from "../i18n.js";
import { shortPath } from "../preview.js";
import { useAppStore } from "../store/app-store.js";
import { Progress } from "./ui/progress.js";

function progressPercent(value: number) {
	return Math.max(0, Math.min(100, Math.round(Number(value || 0) * 100)));
}

export function MaterialIngestProgress() {
	const ingestProgress = useAppStore((store) => store.ingestProgress);
	const percent = progressPercent(ingestProgress.progress);
	const count = ingestProgress.total > 0 ? ` (${ingestProgress.current || 0}/${ingestProgress.total})` : "";
	const message = `${localizePlainText(ingestProgress.message || t("progress.waitingAnalysis"))}${count}`;
	const pathLabel = ingestProgress.path ? shortPath(ingestProgress.path) : "-";

	return (
		<div className="grid gap-2" id="ingestProgress">
			<Progress value={percent} fillId="ingestProgressFill" />
			<div className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
				<strong id="ingestProgressPercent" className="text-accent-foreground">
					{percent}%
				</strong>
				<span id="ingestProgressText" className="min-w-0 truncate">
					{message}
				</span>
			</div>
			<code id="ingestProgressPath" className="truncate text-[11px] text-muted-foreground" title={ingestProgress.path}>
				{pathLabel}
			</code>
		</div>
	);
}
