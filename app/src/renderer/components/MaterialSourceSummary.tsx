import { t } from "../i18n.js";
import { shortPath } from "../preview.js";
import { useAppStore } from "../store/app-store.js";

function imageRoleCount(mediaManifest: any, role: string) {
	return (mediaManifest?.images || []).filter((item: any) => item.role === role).length;
}

export function MaterialManifestSummary() {
	const language = useAppStore((store) => store.language);
	const mediaManifest = useAppStore((store) => store.mediaManifest);
	const materialPaths = useAppStore((store) => store.materialPaths);
	const materialSourcePreviews = useAppStore((store) => store.materialSourcePreviews);

	if (!mediaManifest) {
		const text = materialSourcePreviews.length
			? t("materials.detectedCount", { count: materialSourcePreviews.length })
			: materialPaths.length
				? t("materials.selectedWaiting")
				: t("materials.notAnalyzed");
		return (
			<span id="mediaManifestSummary" data-locale={language}>
				{text}
			</span>
		);
	}

	return (
		<span id="mediaManifestSummary" data-locale={language}>
			{t("label.filesSummary", {
				files: mediaManifest.files.length,
				cameras: mediaManifest.cameras?.length || 0,
				audio: mediaManifest.audio?.length || 0,
				stills: imageRoleCount(mediaManifest, "still"),
				subtitles: mediaManifest.subtitles?.length || 0,
			})}
		</span>
	);
}

export function MaterialSourceLabel() {
	const language = useAppStore((store) => store.language);
	const materialPaths = useAppStore((store) => store.materialPaths);
	const label = materialPaths.length
		? materialPaths.length === 1
			? shortPath(materialPaths[0])
			: t("label.selectedItems", { count: materialPaths.length })
		: t("label.notSelected");

	return (
		<code id="mediaDirectoryLabel" title={materialPaths.join("\n")} data-locale={language}>
			{label}
		</code>
	);
}
