import { activeOutputRoot, joinPath } from "./preview.js";

export type SyncReportRow = {
	role: string;
	score: number;
	offset: number;
	path: string;
};

export function describeSyncReportRows(syncReport: any | null): SyncReportRow[] {
	const offsets = (syncReport?.offsets || {}) as Record<string, any>;
	return Object.entries(offsets)
		.filter(([role]) => role !== "master")
		.map(([role, item]) => ({
			role,
			score: Number(item.score),
			offset: Number(item.offsetSeconds),
			path: item.path || "",
		}));
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
