import { extensionLabel, isMissingPreview, previewKindLabel } from "../preview.js";

export function MediaThumbnail({ preview }: { readonly preview: any }) {
	const missing = isMissingPreview(preview);
	const className = `media-thumb ${preview?.kind || "empty"} ${missing ? "missing" : ""}`.trim();

	if (preview?.kind === "folder" && preview.previewThumbnails?.length) {
		return (
			<div className={className}>
				<div className="folder-preview-stack">
					{preview.previewThumbnails.slice(0, 3).map((thumbnail: string) => (
						<img key={thumbnail} src={thumbnail} alt="" />
					))}
				</div>
			</div>
		);
	}

	return (
		<div className={className}>
			{preview?.thumbnailDataUrl ? (
				<img src={preview.thumbnailDataUrl} alt="" />
			) : (
				<span>{preview?.kind ? extensionLabel(preview.extension) || previewKindLabel(preview.kind) : "-"}</span>
			)}
			{missing ? <span className="missing-thumb-icon">×</span> : null}
		</div>
	);
}
