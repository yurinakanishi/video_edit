import { t } from "../i18n.js";
import { shortPath } from "../preview.js";
import { useAppStore } from "../store/app-store.js";
import {
	describeSyncOverlapSegments,
	describeSyncReportRows,
	describeSyncTimeline,
	formatSyncSeconds,
	type SyncOverlapSegment,
	type SyncTimelineItem,
	syncScoreKind,
	syncTimelineBounds,
} from "../sync-report.js";

function percent(start: number, end: number, min: number, span: number) {
	const left = ((start - min) / span) * 100;
	const width = ((end - start) / span) * 100;
	return {
		left: `${Math.max(0, Math.min(100, left)).toFixed(3)}%`,
		width: `${Math.max(0.5, Math.min(100, width)).toFixed(3)}%`,
	};
}

function SyncTimelineTrack({
	item,
	overlaps,
	min,
	span,
}: {
	readonly item: SyncTimelineItem;
	readonly overlaps: SyncOverlapSegment[];
	readonly min: number;
	readonly span: number;
}) {
	const barStyle = percent(item.timelineStart, item.timelineEnd, min, span);
	return (
		<div className="sync-track-row">
			<div className="sync-track-label">
				<strong>{item.role}</strong>
				<span>{item.kind}</span>
			</div>
			<div className="sync-track" title={item.path}>
				<div className="sync-track-overlaps" aria-hidden="true">
					{overlaps.map((segment) => (
						<span
							key={`${segment.start}-${segment.end}`}
							className="sync-overlap"
							style={percent(segment.start, segment.end, min, span)}
							title={segment.activeRoles.join(", ")}
						></span>
					))}
				</div>
				<span className={`sync-bar ${syncScoreKind(item.score)}`} style={barStyle}></span>
			</div>
			<div className="sync-track-meta">
				<strong>{formatSyncSeconds(item.offset)}</strong>
				<span>
					{item.selectedEvidence || "default"} · {shortPath(item.path)}
				</span>
			</div>
		</div>
	);
}

function SyncTimelineView({ syncReport }: { readonly syncReport: any }) {
	const items = describeSyncTimeline(syncReport);
	const overlaps = describeSyncOverlapSegments(syncReport, items);
	const { min, max, span } = syncTimelineBounds(items);

	return (
		<div className="sync-timeline-view">
			<div className="sync-timeline-scale" aria-hidden="true">
				<span>{formatSyncSeconds(min)}</span>
				<span>{formatSyncSeconds((min + max) / 2)}</span>
				<span>{formatSyncSeconds(max)}</span>
			</div>
			<div className="sync-timeline">
				{items.map((item) => (
					<SyncTimelineTrack key={`${item.role}-${item.path}`} item={item} overlaps={overlaps} min={min} span={span} />
				))}
			</div>
			{overlaps.length ? null : <div className="sync-no-overlap">{t("sync.noOverlap")}</div>}
		</div>
	);
}

export function SyncReportList() {
	const language = useAppStore((store) => store.language);
	const syncReport = useAppStore((store) => store.syncReport);
	const timeline = describeSyncTimeline(syncReport);
	const rows = describeSyncReportRows(syncReport);

	if (timeline.length) {
		return (
			<div id="syncReportList" className="sync-report-list" data-locale={language}>
				<SyncTimelineView syncReport={syncReport} />
			</div>
		);
	}

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
