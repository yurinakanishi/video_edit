import { activeOutputRoot, joinPath } from "./preview.js";

export type SyncReportRow = {
	role: string;
	score: number;
	offset: number;
	path: string;
};

export type SyncTimelineItem = {
	role: string;
	kind: string;
	path: string;
	duration: number;
	offset: number;
	timelineStart: number;
	timelineEnd: number;
	score: number;
	selectedEvidence: string;
};

export type SyncOverlapSegment = {
	start: number;
	end: number;
	activeRoles: string[];
};

export function describeSyncReportRows(syncReport: any | null): SyncReportRow[] {
	const offsets = (syncReport?.offsets || {}) as Record<string, any>;
	const timelineRole = String(syncReport?.timelineRole || "master");
	return Object.entries(offsets)
		.filter(([role]) => role !== timelineRole)
		.map(([role, item]) => ({
			role,
			score: Number(item.score),
			offset: Number(item.offsetSeconds),
			path: item.path || "",
		}));
}

function roleSortValue(role: string) {
	if (role === "master") {
		return 0;
	}
	if (role.startsWith("camera")) {
		return Number(role.replace("camera", "")) || 50;
	}
	if (role.startsWith("external")) {
		const suffix = role.replace("external", "");
		return 100 + (suffix ? Number(suffix) || 50 : 1);
	}
	return 200;
}

export function describeSyncTimeline(syncReport: any | null): SyncTimelineItem[] {
	const timeline = Array.isArray(syncReport?.timeline) ? syncReport.timeline : [];
	return timeline
		.map((item: any) => ({
			role: String(item.role || ""),
			kind: String(item.kind || ""),
			path: String(item.path || ""),
			duration: Number(item.durationSeconds),
			offset: Number(item.offsetSeconds),
			timelineStart: Number(item.timelineStartSeconds),
			timelineEnd: Number(item.timelineEndSeconds),
			score: Number(item.score),
			selectedEvidence: String(item.selectedEvidence || ""),
		}))
		.filter(
			(item) =>
				item.role &&
				Number.isFinite(item.timelineStart) &&
				Number.isFinite(item.timelineEnd) &&
				item.timelineEnd > item.timelineStart,
		)
		.sort((a, b) => roleSortValue(a.role) - roleSortValue(b.role));
}

export function syncTimelineBounds(items: SyncTimelineItem[]) {
	const starts = items.map((item) => item.timelineStart);
	const ends = items.map((item) => item.timelineEnd);
	const min = starts.length ? Math.min(...starts) : 0;
	const max = ends.length ? Math.max(...ends) : 0;
	return { min, max, span: Math.max(max - min, 0.001) };
}

export function describeSyncOverlapSegments(
	syncReport: any | null,
	items: SyncTimelineItem[] = describeSyncTimeline(syncReport),
): SyncOverlapSegment[] {
	const fromReport = Array.isArray(syncReport?.overlapSegments) ? syncReport.overlapSegments : null;
	if (fromReport) {
		return fromReport
			.map((item: any) => ({
				start: Number(item.startSeconds),
				end: Number(item.endSeconds),
				activeRoles: Array.isArray(item.activeRoles) ? item.activeRoles.map(String) : [],
			}))
			.filter((item) => Number.isFinite(item.start) && Number.isFinite(item.end) && item.end > item.start);
	}

	const events = items
		.flatMap((item) => [
			{ time: item.timelineStart, type: "start", role: item.role },
			{ time: item.timelineEnd, type: "end", role: item.role },
		])
		.sort((a, b) => a.time - b.time);
	const output: SyncOverlapSegment[] = [];
	const active = new Set<string>();
	let previous = events[0]?.time ?? 0;
	let index = 0;
	while (index < events.length) {
		const current = events[index].time;
		if (current > previous && active.size >= 2) {
			output.push({
				start: previous,
				end: current,
				activeRoles: [...active].sort((a, b) => roleSortValue(a) - roleSortValue(b)),
			});
		}
		while (index < events.length && events[index].time === current) {
			const event = events[index];
			if (event.type === "end") {
				active.delete(event.role);
			} else {
				active.add(event.role);
			}
			index += 1;
		}
		previous = current;
	}
	return output;
}

export function formatSyncSeconds(value: number) {
	if (!Number.isFinite(value)) {
		return "n/a";
	}
	return `${value.toFixed(Math.abs(value) < 10 ? 2 : 1)}s`;
}

export function syncScoreKind(score: number) {
	if (typeof score !== "number" || Number.isNaN(score)) {
		return "bad";
	}
	if (score >= 0.82) {
		return "good";
	}
	if (score >= 0.65) {
		return "warn";
	}
	return "bad";
}

export function syncReportPath() {
	return joinPath(activeOutputRoot(), "reports", "app_sync_offsets.json");
}
