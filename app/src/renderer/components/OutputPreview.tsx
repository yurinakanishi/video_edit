import {
	OUTPUT_PREVIEW_ENTRY_OPEN_EVENT,
	OUTPUT_PREVIEW_OPEN_FOLDER_EVENT,
	OUTPUT_PREVIEW_REFRESH_EVENT,
} from "../events.js";
import { t } from "../i18n.js";
import { outputPreviewTitle, previewEntryMeta, previewKindLabel, shortPath } from "../preview.js";
import { useAppStore } from "../store/app-store.js";

function dispatchOutputPreviewAction(eventName: string) {
	document.dispatchEvent(new CustomEvent(eventName));
}

function dispatchOutputPreviewEntryOpen(path: string) {
	document.dispatchEvent(new CustomEvent(OUTPUT_PREVIEW_ENTRY_OPEN_EVENT, { detail: { path } }));
}

function OutputPreviewThumb({ entry }: { readonly entry: any }) {
	if (entry.kind === "folder" && entry.previewThumbnails?.length) {
		return (
			<div className={`preview-thumb ${entry.kind}`}>
				<div className="folder-preview-stack">
					{entry.previewThumbnails.slice(0, 3).map((thumbnail: string) => (
						<img key={thumbnail} src={thumbnail} alt="" />
					))}
				</div>
			</div>
		);
	}

	return (
		<div className={`preview-thumb ${entry.kind}`}>
			{entry.thumbnailDataUrl ? (
				<img src={entry.thumbnailDataUrl} alt="" />
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
					className={`preview-card ${entry.kind}`}
					title={entry.path}
					onClick={() => dispatchOutputPreviewEntryOpen(entry.path)}
				>
					<OutputPreviewThumb entry={entry} />
					<div className="preview-detail">
						<strong>{entry.name}</strong>
						<small>{previewKindLabel(entry.kind)}</small>
						<div className="preview-meta">
							{previewEntryMeta(entry).map((item) => (
								<span key={item}>{item}</span>
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
		<section className="output-preview" id="outputPreview" hidden={!visible} data-locale={language}>
			<div className="output-preview-heading">
				<div>
					<h3 id="outputPreviewTitle">{outputPreviewTitle(outputPreviewKind)}</h3>
					<p id="outputPreviewSummary">{summary}</p>
				</div>
				<div className="output-preview-actions">
					<button
						type="button"
						id="refreshOutputPreview"
						onClick={() => dispatchOutputPreviewAction(OUTPUT_PREVIEW_REFRESH_EVENT)}
					>
						Refresh
					</button>
					<button
						type="button"
						id="openPreviewFolder"
						onClick={() => dispatchOutputPreviewAction(OUTPUT_PREVIEW_OPEN_FOLDER_EVENT)}
					>
						Open in Explorer
					</button>
				</div>
			</div>
			<p id="outputPreviewPath" className="output-preview-location" title={preview.targetPath || preview.path || ""}>
				{shortPath(previewPath)}
			</p>
			<div className="output-preview-list" id="outputPreviewList">
				{outputPreviewLoading ? t("preview.loading") : <OutputPreviewList entries={entries} ok={Boolean(preview.ok)} />}
			</div>
		</section>
	);
}
