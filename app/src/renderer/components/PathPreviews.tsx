import { t } from "../i18n.js";
import {
	extensionFromPath,
	fileNameFromPath,
	mediaMetaBadges,
	parentDirectoryFromPath,
	previewKindFromPath,
	previewKindLabel,
	shortPath,
} from "../preview.js";
import { useAppStore } from "../store/app-store.js";
import type { MediaManifest } from "../types.js";
import { MediaThumbnail } from "./MediaThumbnail.js";

function manifestPreviewForPath(mediaManifest: MediaManifest | null, filePath: string) {
	const resolved = String(filePath || "");
	return (mediaManifest?.files || []).find((item) => item.path === resolved || item.originalPath === resolved) || null;
}

function fallbackPreview(filePath: string, kind = previewKindFromPath(filePath)) {
	return {
		path: filePath,
		name: fileNameFromPath(filePath),
		kind,
		extension: extensionFromPath(filePath),
	};
}

function AssetPreviewDetail({
	preview,
	filePath,
	meta,
}: {
	readonly preview: any;
	readonly filePath: string;
	readonly meta: string;
}) {
	return (
		<span className="asset-preview-detail">
			<strong>{preview.name || fileNameFromPath(filePath)}</strong>
			<small>{meta}</small>
		</span>
	);
}

export function WorkflowInputVideoPreview() {
	const language = useAppStore((store) => store.language);
	const inputVideoPath = useAppStore((store) => store.inputVideoPath);
	const filePreviews = useAppStore((store) => store.filePreviews);
	const mediaManifest = useAppStore((store) => store.mediaManifest);

	const preview =
		(inputVideoPath && (filePreviews[inputVideoPath] || manifestPreviewForPath(mediaManifest, inputVideoPath))) ||
		(inputVideoPath ? fallbackPreview(inputVideoPath, "video") : null);

	if (!preview) {
		return (
			<div id="inputVideoPathPreview" className="asset-preview workflow-media-preview empty" data-locale={language}>
				{t("materials.unselected")}
			</div>
		);
	}

	return (
		<div
			id="inputVideoPathPreview"
			className="asset-preview workflow-media-preview"
			title={inputVideoPath}
			data-locale={language}
		>
			<MediaThumbnail preview={preview} />
			<AssetPreviewDetail
				preview={preview}
				filePath={inputVideoPath}
				meta={mediaMetaBadges(preview).join(" / ") || previewKindLabel(preview.kind || "video")}
			/>
		</div>
	);
}

export function OutputTargetPreview() {
	const language = useAppStore((store) => store.language);
	const outputPath = useAppStore((store) => store.outputPath);
	const filePreviews = useAppStore((store) => store.filePreviews);
	const preview = outputPath ? filePreviews[outputPath] || fallbackPreview(outputPath) : null;

	if (!preview) {
		return (
			<div id="outputPathPreview" className="asset-preview output-target-preview empty" data-locale={language}>
				{t("materials.unselected")}
			</div>
		);
	}

	const folder = parentDirectoryFromPath(outputPath);
	const metaItems = [
		...mediaMetaBadges(preview),
		preview.sizeBytes ? "" : t("output.pending"),
		folder ? t("output.destination", { folder: shortPath(folder) }) : "",
	].filter(Boolean);

	return (
		<div
			id="outputPathPreview"
			className="asset-preview output-target-preview"
			title={outputPath}
			data-locale={language}
		>
			<MediaThumbnail preview={preview} />
			<AssetPreviewDetail
				preview={preview}
				filePath={outputPath}
				meta={metaItems.join(" / ") || previewKindLabel(preview.kind || "video")}
			/>
		</div>
	);
}
