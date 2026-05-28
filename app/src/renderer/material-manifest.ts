import { editApp } from "./api.js";
import { t } from "./i18n.js";
import { log } from "./log.js";
import { syncMaterialStore } from "./media-state.js";
import {
	fallbackPreviewForPath,
	fileNameFromPath,
	isMissingPreview,
	loadedMaterialPreviewForPath,
	manifestFiles,
	manifestImagesByRole,
	shortPath,
} from "./preview.js";
import { state } from "./state.js";
import { getAppState } from "./store/app-store.js";
import type { MediaItem, MediaManifest } from "./types.js";

type ConfirmActionOptions = {
	title: string;
	message: string;
	detail?: string;
	confirmLabel?: string;
	cancelLabel?: string;
};

type MaterialManifestControllerOptions = {
	readonly confirmAction: (options: ConfirmActionOptions) => Promise<boolean>;
	readonly loadFilePreviews: (paths: string[]) => void;
	readonly refreshPrompt: () => void;
	readonly refreshMaterialAnalysisStatus: () => Promise<void>;
	readonly removeMaterialAnalysisStatus: (paths: string[]) => void;
	readonly saveState: () => void;
	readonly setFile: (slot: string, filePath: string) => void;
	readonly setMaterialSources: (paths: string[]) => void;
	readonly setStillImages: (paths: string[]) => void;
};

function roleSortValue(role: string) {
	if (role === "master") {
		return 1;
	}
	if (role.startsWith("camera")) {
		return Number(role.replace("camera", "")) || 50;
	}
	return 100;
}

export function createMaterialManifestController({
	confirmAction,
	loadFilePreviews,
	refreshPrompt,
	refreshMaterialAnalysisStatus,
	removeMaterialAnalysisStatus,
	saveState,
	setFile,
	setMaterialSources,
	setStillImages,
}: MaterialManifestControllerOptions) {
	function rebuildMediaManifestGroups() {
		if (!state.mediaManifest) {
			return;
		}
		const files = state.mediaManifest.files || [];
		for (const item of files) {
			if (item.kind === "video" && item.role === "reference") {
				item.role = "ignore";
				item.label = t("role.ignore");
				item.reason = "reference video is selected manually outside the material folder";
			}
		}
		const cameraRoles = new Set(["master", "camera2", "camera3", "camera4", "camera5", "camera6"]);
		state.mediaManifest.cameras = files
			.filter((item) => item.kind === "video" && cameraRoles.has(item.role))
			.sort((a, b) => roleSortValue(a.role) - roleSortValue(b.role));
		state.mediaManifest.audio = files.filter((item) => item.kind === "audio" && item.role.startsWith("external"));
		state.mediaManifest.images = files.filter((item) => item.kind === "image" && ["logo", "still"].includes(item.role));
		state.mediaManifest.subtitles = files.filter((item) => item.kind === "subtitle" && item.role === "subtitle");
		state.mediaManifest.other = files.filter(
			(item) =>
				!state.mediaManifest.cameras.includes(item) &&
				!state.mediaManifest.audio.includes(item) &&
				!state.mediaManifest.images.includes(item) &&
				!state.mediaManifest.subtitles.includes(item),
		);
		state.mediaManifest.selected = {
			masterVideo: state.mediaManifest.cameras.find((item) => item.role === "master")?.path || "",
			rightCloseVideo: state.mediaManifest.cameras.find((item) => item.role === "camera2")?.path || "",
			leftCloseVideo: state.mediaManifest.cameras.find((item) => item.role === "camera3")?.path || "",
			externalAudio: state.mediaManifest.audio[0]?.path || "",
			logo: manifestImagesByRole("logo")[0]?.path || "",
			stillImages: manifestImagesByRole("still").map((item) => item.path),
		};
	}

	function applyManifestSelections() {
		if (!state.mediaManifest) {
			return;
		}
		rebuildMediaManifestGroups();
		const selected = state.mediaManifest.selected || {};
		setFile("masterVideo", selected.masterVideo || "");
		setFile("rightCloseVideo", selected.rightCloseVideo || "");
		setFile("leftCloseVideo", selected.leftCloseVideo || "");
		setFile("externalAudio", selected.externalAudio || "");
		setFile("logo", selected.logo || "");
		setStillImages(Array.isArray(selected.stillImages) ? selected.stillImages.map(String) : []);
	}

	function materialDisplayName(preview: any, fallbackPath = "") {
		return preview?.relativePath || preview?.name || fileNameFromPath(fallbackPath) || shortPath(fallbackPath);
	}

	async function confirmRemoveMaterial(name: string, filePath: string, missing = false) {
		return confirmAction({
			title: missing ? t("confirm.removeMissingMaterialTitle") : t("confirm.removeMaterialTitle"),
			message: missing ? t("confirm.removeMissingMaterialBody") : t("confirm.removeMaterialBody"),
			detail: `${name}\n${filePath}`,
			confirmLabel: t("confirm.removeMaterialConfirm"),
			cancelLabel: t("confirm.cancel"),
		});
	}

	async function persistCurrentMediaManifest() {
		if (!state.project || !state.mediaManifest) {
			return;
		}
		try {
			const saved = await editApp.saveMediaManifest({
				project: state.project,
				manifest: state.mediaManifest,
			});
			if (saved?.files) {
				state.mediaManifest = saved;
			}
		} catch (error) {
			log("media manifest save failed", { message: error.message });
		}
	}

	function sourcePathsAfterRemoving(sourcePath: string) {
		const normalized = sourcePath.toLowerCase();
		if (state.materialSourcePreviews.length) {
			return state.materialSourcePreviews
				.map((preview) => String(preview?.path || ""))
				.filter((filePath) => filePath && filePath.toLowerCase() !== normalized);
		}
		return state.materialPaths.filter((filePath) => filePath.toLowerCase() !== normalized);
	}

	async function removeMaterialSource(sourcePath: string, preview: any) {
		if (
			!(await confirmRemoveMaterial(materialDisplayName(preview, sourcePath), sourcePath, isMissingPreview(preview)))
		) {
			return;
		}
		state.filePreviews = Object.fromEntries(
			Object.entries(state.filePreviews).filter(([filePath]) => filePath !== sourcePath),
		);
		setMaterialSources(sourcePathsAfterRemoving(sourcePath));
		log("material removed", { path: sourcePath });
	}

	async function removeManifestItem(item: MediaItem, preview: any) {
		if (!state.mediaManifest) {
			return;
		}
		const filePath = item.path || preview?.path || "";
		if (
			!(await confirmRemoveMaterial(
				materialDisplayName(preview || item, filePath),
				filePath,
				isMissingPreview(preview),
			))
		) {
			return;
		}
		state.mediaManifest.files = (state.mediaManifest.files || []).filter((candidate) => candidate.id !== item.id);
		delete state.filePreviews[item.path];
		if (item.originalPath) {
			delete state.filePreviews[item.originalPath];
		}
		rebuildMediaManifestGroups();
		applyManifestSelections();
		removeMaterialAnalysisStatus([item.path, item.originalPath || ""]);
		renderMediaManifest();
		refreshPrompt();
		void refreshMaterialAnalysisStatus();
		saveState();
		await persistCurrentMediaManifest();
		log("manifest material removed", { path: filePath, id: item.id });
	}

	function materialSourcePreview(sourcePath: string) {
		return loadedMaterialPreviewForPath(sourcePath) || fallbackPreviewForPath(sourcePath);
	}

	function handleMaterialRoleChange(event: Event) {
		const detail = (event as CustomEvent).detail || {};
		const item = manifestFiles().find((candidate) => candidate.id === String(detail.id || ""));
		if (!item) {
			return;
		}
		item.role = String(detail.role || "ignore");
		item.label = String(detail.label || item.role);
		item.reason = t("role.overrideReason");
		item.confidence = 1.0;
		applyManifestSelections();
		renderMediaManifest();
		void refreshMaterialAnalysisStatus();
		refreshPrompt();
	}

	function handleMaterialSourceRemove(event: Event) {
		const sourcePath = String((event as CustomEvent).detail?.path || "");
		if (!sourcePath) {
			return;
		}
		void removeMaterialSource(sourcePath, materialSourcePreview(sourcePath));
	}

	function handleMaterialItemRemove(event: Event) {
		if (!state.mediaManifest) {
			return;
		}
		const item = manifestFiles().find((candidate) => candidate.id === String((event as CustomEvent).detail?.id || ""));
		if (!item) {
			return;
		}
		const preview = state.filePreviews[item.path] || state.filePreviews[item.originalPath || ""] || item;
		void removeManifestItem(item, preview);
	}

	function handleStillImageRemove(event: Event) {
		const index = Number((event as CustomEvent).detail?.index);
		if (!Number.isInteger(index) || index < 0) {
			return;
		}
		setStillImages(state.files.stillImages.filter((_, itemIndex) => itemIndex !== index));
	}

	function renderMediaManifest() {
		syncMaterialStore();
	}

	function setMediaManifest(manifest: MediaManifest | null) {
		state.mediaManifest = manifest;
		state.mediaDirectory = manifest?.sourceDirectory || "";
		state.materialPaths = manifest?.sourcePaths?.length
			? manifest.sourcePaths
			: manifest?.sourceDirectory
				? [manifest.sourceDirectory]
				: [];
		state.materialSourcePreviews = [];
		state.materialSourcePreviewLoading = false;
		getAppState().setMediaManifest(manifest, {
			mediaDirectory: state.mediaDirectory,
			materialPaths: state.materialPaths,
			materialSourcePreviews: state.materialSourcePreviews,
		});
		applyManifestSelections();
		renderMediaManifest();
		void loadFilePreviews((manifest?.files || []).map((item) => item.path).filter(Boolean));
		refreshPrompt();
	}

	return {
		applyManifestSelections,
		handleMaterialItemRemove,
		handleMaterialRoleChange,
		handleMaterialSourceRemove,
		handleStillImageRemove,
		rebuildMediaManifestGroups,
		renderMediaManifest,
		setMediaManifest,
	};
}
