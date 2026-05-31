import { ExternalLink, FolderOpen, RefreshCw } from "lucide-react";
import {
	OUTPUT_PREVIEW_ENTRY_OPEN_EVENT,
	OUTPUT_PREVIEW_OPEN_FOLDER_EVENT,
	OUTPUT_PREVIEW_REFRESH_EVENT,
} from "../events.js";
import { t } from "../i18n.js";
import { cn } from "../lib/utils.js";
import { outputPreviewTitle, previewEntryMeta, previewKindLabel, shortPath } from "../preview.js";
import { useAppStore } from "../store/app-store.js";
import { Badge } from "./ui/badge.js";
import { Button } from "./ui/button.js";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card.js";

function dispatchOutputPreviewAction(eventName: string) {
	document.dispatchEvent(new CustomEvent(eventName));
}

function dispatchOutputPreviewEntryOpen(path: string) {
	document.dispatchEvent(new CustomEvent(OUTPUT_PREVIEW_ENTRY_OPEN_EVENT, { detail: { path } }));
}

function OutputPreviewThumb({ entry }: { readonly entry: any }) {
	if (entry.kind === "folder" && entry.previewThumbnails?.length) {
		return (
			<div className="grid aspect-video place-items-center overflow-hidden rounded-md bg-muted">
				<div className="grid size-full grid-cols-3 gap-1 p-1">
					{entry.previewThumbnails.slice(0, 3).map((thumbnail: string) => (
						<img key={thumbnail} src={thumbnail} alt="" className="size-full rounded object-cover" />
					))}
				</div>
			</div>
		);
	}

	return (
		<div className="grid aspect-video place-items-center overflow-hidden rounded-md bg-muted text-xs font-semibold uppercase text-muted-foreground">
			{entry.thumbnailDataUrl ? (
				<img src={entry.thumbnailDataUrl} alt="" className="size-full object-cover" />
			) : (
				<span>{entry.kind === "folder" ? "DIR" : entry.extension || previewKindLabel(entry.kind)}</span>
			)}
		</div>
	);
}

function OutputPreviewList({ entries, ok }: { readonly entries: any[]; readonly ok: boolean }) {
	if (!entries.length) {
		return <>{ok ? t("preview.empty") : t("preview.missing")}</>;
	}

	return (
		<>
			{entries.map((entry) => (
				<button
					type="button"
					key={entry.path || entry.name}
					className={cn(
						"grid min-w-0 gap-2 rounded-lg border border-border bg-card p-2 text-left shadow-sm transition-colors",
						"hover:bg-accent/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
					)}
					title={entry.path}
					onClick={() => dispatchOutputPreviewEntryOpen(entry.path)}
				>
					<OutputPreviewThumb entry={entry} />
					<div className="grid min-w-0 gap-1">
						<strong className="truncate text-sm text-foreground">{entry.name}</strong>
						<small className="truncate text-[11px] font-semibold uppercase text-accent-foreground">
							{previewKindLabel(entry.kind)}
						</small>
						<div className="flex flex-wrap gap-1">
							{previewEntryMeta(entry).map((item) => (
								<Badge key={item} variant="secondary" className="truncate">
									{item}
								</Badge>
							))}
						</div>
					</div>
				</button>
			))}
		</>
	);
}

export function OutputPreview() {
	const language = useAppStore((store) => store.language);
	const env = useAppStore((store) => store.env);
	const project = useAppStore((store) => store.project);
	const outputPath = useAppStore((store) => store.outputPath);
	const outputPreview = useAppStore((store) => store.outputPreview);
	const outputPreviewKind = useAppStore((store) => store.outputPreviewKind);
	const outputPreviewLoading = useAppStore((store) => store.outputPreviewLoading);
	const visible = Boolean(outputPreview || outputPreviewLoading);
	const target = outputPath || project?.outputRoot || env?.outputRoot || "";
	const preview = outputPreview || {};
	const entries = Array.isArray(preview.entries) ? preview.entries : [];
	const previewPath = preview.path || preview.targetPath || target;
	const summary = outputPreviewLoading
		? t("preview.loading")
		: preview.ok
			? t("preview.summary", { count: entries.length })
			: preview.reason === "missing-path"
				? t("preview.missing")
				: t("preview.empty");

	return (
		<Card className="output-preview" id="outputPreview" hidden={!visible} data-locale={language}>
			<CardHeader className="flex-row items-start justify-between gap-3 space-y-0">
				<div>
					<CardTitle id="outputPreviewTitle">{outputPreviewTitle(outputPreviewKind)}</CardTitle>
					<CardDescription id="outputPreviewSummary">{summary}</CardDescription>
				</div>
				<div className="flex flex-wrap justify-end gap-2">
					<Button
						type="button"
						id="refreshOutputPreview"
						variant="outline"
						size="sm"
						onClick={() => dispatchOutputPreviewAction(OUTPUT_PREVIEW_REFRESH_EVENT)}
					>
						<RefreshCw className="size-4" aria-hidden="true" />
						Refresh
					</Button>
					<Button
						type="button"
						id="openPreviewFolder"
						variant="outline"
						size="sm"
						onClick={() => dispatchOutputPreviewAction(OUTPUT_PREVIEW_OPEN_FOLDER_EVENT)}
					>
						<FolderOpen className="size-4" aria-hidden="true" />
						Open in Explorer
					</Button>
				</div>
			</CardHeader>
			<CardContent className="grid gap-3">
				<p
					id="outputPreviewPath"
					className="flex min-w-0 items-center gap-2 truncate text-xs text-muted-foreground"
					title={preview.targetPath || preview.path || ""}
				>
					<ExternalLink className="size-3.5 shrink-0" aria-hidden="true" />
					<span className="truncate">{shortPath(previewPath)}</span>
				</p>
				<div
					className="grid max-h-96 grid-cols-[repeat(auto-fill,minmax(170px,1fr))] gap-3 overflow-auto text-sm text-muted-foreground"
					id="outputPreviewList"
				>
					{outputPreviewLoading ? (
						t("preview.loading")
					) : (
						<OutputPreviewList entries={entries} ok={Boolean(preview.ok)} />
					)}
				</div>
			</CardContent>
		</Card>
	);
}
