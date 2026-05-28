import { STILL_IMAGE_REMOVE_EVENT } from "../events.js";
import { t } from "../i18n.js";
import {
	fileNameFromPath,
	manifestPreviewForPath,
	mediaMetaBadges,
	previewKindFromPath,
	previewKindLabel,
} from "../preview.js";
import type { AppFiles } from "../store/app-store.js";
import { useAppStore } from "../store/app-store.js";
import { MediaThumbnail } from "./MediaThumbnail.js";

type ManualFileSlot = Exclude<keyof AppFiles, "stillImages">;

function dispatchStillImageRemove(index: number) {
	document.dispatchEvent(new CustomEvent(STILL_IMAGE_REMOVE_EVENT, { detail: { index } }));
}

function fallbackPreviewForFile(filePath: string, fallbackKind = "other") {
	const detectedKind = previewKindFromPath(filePath);
	return {
		path: filePath,
		name: fileNameFromPath(filePath),
		kind: detectedKind === "other" ? fallbackKind : detectedKind,
		extension: filePath.includes(".") ? filePath.split(".").at(-1) : "",
	};
}

function previewForPath(filePath: string, filePreviews: Record<string, any>, fallbackKind = "other") {
	if (!filePath) {
		return null;
	}
	return filePreviews[filePath] || manifestPreviewForPath(filePath) || fallbackPreviewForFile(filePath, fallbackKind);
}

function fallbackKindForSlot(slot: ManualFileSlot) {
	if (slot === "externalAudio") {
		return "audio";
	}
	if (slot === "logo") {
		return "image";
	}
	return "video";
}

function AssetPreviewDetail({ preview, filePath }: { readonly preview: any; readonly filePath: string }) {
	return (
		<span className="asset-preview-detail">
			<strong>{preview.name || fileNameFromPath(filePath)}</strong>
			<small>{mediaMetaBadges(preview).join(" / ") || previewKindLabel(preview.kind || "other")}</small>
		</span>
	);
}

export function FileSlotPreview({ id, slot }: { readonly id: string; readonly slot: ManualFileSlot }) {
	const language = useAppStore((store) => store.language);
	const filePath = useAppStore((store) => store.files[slot]);
	const filePreviews = useAppStore((store) => store.filePreviews);
	const preview = previewForPath(filePath, filePreviews, fallbackKindForSlot(slot));

	if (!preview) {
		return (
			<div id={id} className="asset-preview empty" data-locale={language}>
				{t("materials.unselected")}
			</div>
		);
	}

	return (
		<div id={id} className="asset-preview" title={preview.path || filePath} data-locale={language}>
			<MediaThumbnail preview={preview} />
			<AssetPreviewDetail preview={preview} filePath={filePath} />
		</div>
	);
}

export function StillImagesLabel({ id }: { readonly id: string }) {
	const language = useAppStore((store) => store.language);
	const stillImages = useAppStore((store) => store.files.stillImages);
	return (
		<code id={id} title={stillImages.join("\n")} data-locale={language}>
			{stillImages.length ? t("label.imageCount", { count: stillImages.length }) : t("materials.unselected")}
		</code>
	);
}

export function StillImagesList() {
	const language = useAppStore((store) => store.language);
	const stillImages = useAppStore((store) => store.files.stillImages);
	const filePreviews = useAppStore((store) => store.filePreviews);

	if (!stillImages.length) {
		return (
			<div id="stillImagesList" className="asset-list" data-locale={language}>
				{t("materials.unselected")}
			</div>
		);
	}

	return (
		<div id="stillImagesList" className="asset-list" data-locale={language}>
			{stillImages.map((filePath, index) => {
				const preview = previewForPath(filePath, filePreviews, "image");
				return (
					<div className="still-card" key={filePath}>
						<MediaThumbnail preview={preview} />
						<div className="asset-preview-detail">
							<strong title={filePath}>
								{index + 1}. {preview?.name || fileNameFromPath(filePath)}
							</strong>
							<small>{mediaMetaBadges(preview).join(" / ") || previewKindLabel(preview?.kind || "image")}</small>
						</div>
						<button type="button" onClick={() => dispatchStillImageRemove(index)}>
							{t("action.remove")}
						</button>
					</div>
				);
			})}
		</div>
	);
}
