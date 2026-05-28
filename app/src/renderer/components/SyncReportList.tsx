import { t } from "../i18n.js";
import { shortPath } from "../preview.js";
import { useAppStore } from "../store/app-store.js";
import { describeSyncReportRows, syncScoreKind } from "../sync-report.js";

export function SyncReportList() {
	const language = useAppStore((store) => store.language);
	const syncReport = useAppStore((store) => store.syncReport);
	const rows = describeSyncReportRows(syncReport);

	if (!rows.length) {
		return (
			<div id="syncReportList" className="sync-report-list" data-locale={language}>
				{t("sync.noReport")}
			</div>
		);
	}

	return (
		<div id="syncReportList" className="sync-report-list" data-locale={language}>
			{rows.map((row) => (
				<div key={row.role} className={`sync-row ${syncScoreKind(row.score)}`}>
					<strong>{row.role}</strong>
					<span>
						{Number.isFinite(row.offset) ? `${row.offset.toFixed(3)}s` : t("label.offsetUnknown")} ·{" "}
						{shortPath(row.path)}
					</span>
					<span className="score">{Number.isFinite(row.score) ? row.score.toFixed(3) : "n/a"}</span>
				</div>
			))}
		</div>
	);
}
