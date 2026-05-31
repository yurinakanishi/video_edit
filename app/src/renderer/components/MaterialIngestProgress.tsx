import { localizePlainText, t } from "../i18n.js";
import { shortPath } from "../preview.js";
import { useAppStore } from "../store/app-store.js";

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
