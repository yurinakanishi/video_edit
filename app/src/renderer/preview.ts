import { editApp } from "./api.js";
import { messages, t } from "./i18n.js";
import { log } from "./log.js";
import { fileFilterSpecs, state } from "./state.js";
import { getAppState, patchAppState } from "./store/app-store.js";

const fileSlotLabelKeys = {
	masterVideo: "asset.master",
	rightCloseVideo: "asset.rightClose",
	leftCloseVideo: "asset.leftClose",
	referenceVideo: "asset.referenceVideo",
	externalAudio: "asset.externalAudio",
	logo: "asset.logo",
	stillImages: "asset.stillImages",
};

export function fileSlotLabel(slot: string) {
	return t(fileSlotLabelKeys[slot] || slot);
}

export function filtersForSlot(slot: string) {
	const filters = fileFilterSpecs[slot] || [{ nameKey: "filter.allFiles", extensions: ["*"] }];
	return filters.map((filter) => ({
		name: t(filter.nameKey),
		extensions: filter.extensions,
	}));
}

export function shortPath(value) {
	if (!value) {
		return t("label.notSelected");
	}
	const parts = value.split(/[\\/]/);
	return parts.length > 2 ? `${parts.at(-2)}\\${parts.at(-1)}` : value;
}

export function joinPath(root: string, ...parts: string[]) {
	return [root.replace(/[\\/]+$/, ""), ...parts.map((part) => part.replace(/^[\\/]+|[\\/]+$/g, ""))].join("\\");
}

export function formatBytes(value: any) {
	const bytes = Number(value || 0);
	if (!Number.isFinite(bytes) || bytes <= 0) {
		return "";
	}
	const units = ["B", "KB", "MB", "GB", "TB"];
	let size = bytes;
	let unitIndex = 0;
	while (size >= 1024 && unitIndex < units.length - 1) {
		size /= 1024;
		unitIndex += 1;
	}
	return `${size >= 10 || unitIndex === 0 ? size.toFixed(0) : size.toFixed(1)} ${units[unitIndex]}`;
}

export function formatDuration(value: any) {
	const seconds = Number(value || 0);
	if (!Number.isFinite(seconds) || seconds <= 0) {
		return "";
	}
	const total = Math.round(seconds);
	const hours = Math.floor(total / 3600);
	const minutes = Math.floor((total % 3600) / 60);
	const rest = total % 60;
	if (hours) {
		return `${hours}:${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`;
	}
	return `${minutes}:${String(rest).padStart(2, "0")}`;
}

export function outputPreviewTarget(_kind = state.outputPreviewKind) {
	return getAppState().outputPath || activeOutputRoot();
}

export function outputPreviewTitle(kind = state.outputPreviewKind) {
	if (kind === "output") {
		return t("preview.outputTitle");
	}
	return t("preview.heading");
}

export function previewKindLabel(kind: string) {
	const key = `preview.${kind}`;
	return messages[state.language]?.[key] || messages.en[key] || t("preview.file");
}

export function previewEntryMeta(entry: any) {
	if (entry.kind === "folder") {
		return [
			t("preview.folderCounts", { files: entry.fileCount || 0, folders: entry.folderCount || 0 }),
			entry.mediaCount ? t("preview.mediaCount", { count: entry.mediaCount }) : "",
		].filter(Boolean);
	}
	const resolution = entry.width && entry.height ? `${entry.width}x${entry.height}` : "";
	return [
		entry.duration ? formatDuration(entry.duration) : "",
		entry.extension || previewKindLabel(entry.kind),
		resolution,
		entry.videoCodec || entry.audioCodec || "",
		formatBytes(entry.sizeBytes),
	].filter(Boolean);
}

export function mediaRoleLabel(role: string) {
	for (const [value, label] of [
		["master", t("role.master")],
		["camera2", t("role.camera2")],
		["camera3", t("role.camera3")],
		["camera4", t("role.camera4")],
		["camera5", t("role.camera5")],
		["external", t("role.externalAudio")],
		["external2", t("role.externalAudio2")],
		["still", t("role.stillInsert")],
		["logo", t("role.logo")],
		["subtitle", t("role.subtitle")],
		["ignore", t("role.ignore")],
	]) {
		if (value === role) {
			return label;
		}
	}
	return role;
}

export function fileNameFromPath(filePath: string) {
	return (
		String(filePath || "")
			.split(/[\\/]/)
			.filter(Boolean)
			.at(-1) || ""
	);
}

export function extensionLabel(value: string) {
	const text = String(value || "");
	return (
		text.startsWith(".") ? text.slice(1) : text.includes(".") ? text.split(".").at(-1) || text : text
	).toUpperCase();
}

export function extensionFromPath(filePath: string) {
	const name = fileNameFromPath(filePath);
	return name.includes(".") ? name.split(".").at(-1) || "" : "";
}

export function previewKindFromPath(filePath: string) {
	const extension = extensionFromPath(filePath).toLowerCase();
	if (["mp4", "mov", "m4v", "mkv", "avi", "mts", "m2ts", "webm"].includes(extension)) {
		return "video";
	}
	if (["png", "jpg", "jpeg", "webp", "gif", "bmp"].includes(extension)) {
		return "image";
	}
	if (["wav", "mp3", "aac", "m4a", "flac", "aiff", "aif"].includes(extension)) {
		return "audio";
	}
	if (["srt", "ass", "vtt"].includes(extension)) {
		return "subtitle";
	}
	return "other";
}

export function parentDirectoryFromPath(filePath: string) {
	return String(filePath || "").replace(/[\\/][^\\/]*$/, "");
}

export function metadataForPreview(preview: any) {
	return preview?.metadata || preview || {};
}

export function isMissingPreview(preview: any) {
	return Boolean(preview?.missing || preview?.exists === false || preview?.metadata?.missing);
}

export function mediaMetaBadges(preview: any) {
	const metadata = metadataForPreview(preview);
	const resolution = metadata.width && metadata.height ? `${metadata.width}x${metadata.height}` : "";
	const duration = metadata.duration || preview?.duration;
	const motionType = metadata.cameraMotionType || metadata.personAnalysis?.cameraMotionType || "";
	const fixedCamera =
		typeof metadata.isFixedCamera === "boolean"
			? metadata.isFixedCamera
			: typeof metadata.personAnalysis?.isFixedCamera === "boolean"
				? metadata.personAnalysis.isFixedCamera
				: null;
	const faceDirection = metadata.fixedCameraFaceDirection || metadata.personAnalysis?.fixedCameraFaceDirection || "";
	const motionBadge =
		fixedCamera === true
			? "Fixed camera"
			: fixedCamera === false
				? "Moving camera"
				: motionType
					? `Camera ${motionType}`
					: "";
	const directionBadge = faceDirection ? `Look ${faceDirection}` : "";
	return [
		isMissingPreview(preview) ? t("materials.missingFile") : "",
		duration ? formatDuration(duration) : "",
		extensionLabel(preview?.extension || preview?.name || ""),
		resolution,
		motionBadge,
		directionBadge,
		metadata.videoCodec || preview?.videoCodec || metadata.audioCodec || preview?.audioCodec || "",
		formatBytes(preview?.sizeBytes),
	].filter(Boolean);
}

export function fallbackPreviewForPath(filePath: string) {
	const extension = extensionFromPath(filePath);
	const kind = extension ? previewKindFromPath(filePath) : "folder";
	return {
		path: filePath,
		name: fileNameFromPath(filePath) || shortPath(filePath),
		kind,
		extension,
	};
}

export function loadedMaterialPreviewForPath(filePath: string) {
	const normalized = String(filePath || "").toLowerCase();
	return (
		state.filePreviews[filePath] ||
		(Object.values(state.filePreviews) as any[]).find(
			(preview) => String(preview?.path || "").toLowerCase() === normalized,
		) ||
		null
	);
}

export function manifestPreviewForPath(filePath: string) {
	const resolved = String(filePath || "");
	return manifestFiles().find((item) => item.path === resolved || item.originalPath === resolved) || null;
}

export function previewForSlot(slot: string) {
	const value = state.files[slot];
	if (!value) {
		return null;
	}
	return (
		state.filePreviews[value] ||
		manifestPreviewForPath(value) || {
			path: value,
			name: fileNameFromPath(value),
			kind: "other",
			extension: value.includes(".") ? value.split(".").at(-1) : "",
		}
	);
}

export function renderOutputPreview() {
	patchAppState({
		outputPreview: state.outputPreview,
		outputPreviewKind: state.outputPreviewKind,
		outputPreviewLoading: state.outputPreviewLoading,
	});
}

export async function loadOutputPreview(kind: string) {
	state.outputPreviewKind = kind;
	state.outputPreviewLoading = true;
	renderOutputPreview();
	try {
		state.outputPreview = await editApp.listDirectory({
			targetPath: outputPreviewTarget(kind),
			maxEntries: 96,
		});
	} catch (error) {
		state.outputPreview = {
			ok: false,
			reason: error.message || "error",
			targetPath: outputPreviewTarget(kind),
			path: "",
			entries: [],
		};
		log("preview error", { message: error.message });
	} finally {
		state.outputPreviewLoading = false;
		renderOutputPreview();
	}
}

export function projectIdFromName(name: string) {
	const id = name
		.trim()
		.toLowerCase()
		.replace(/[^a-z0-9._-]+/g, "-")
		.replace(/^-+|-+$/g, "");
	return id || `project-${new Date().toISOString().slice(0, 10)}`;
}

export function activeOutputRoot() {
	return state.project?.outputRoot || state.env?.outputRoot || "";
}

export function activeSourceRoot() {
	if (state.project?.sourceRoot) {
		return state.project.sourceRoot;
	}
	return "";
}

export function activeProjectVideoSourceRoot() {
	return state.project ? joinPath(state.project.sourceRoot, "video") : "";
}

export function mediaManifestPath() {
	return (
		state.mediaManifest?.manifestPath ||
		(activeOutputRoot() ? joinPath(activeOutputRoot(), "reports", "media_manifest.json") : "")
	);
}

export function manifestFiles() {
	return state.mediaManifest?.files || [];
}

export function manifestCameras() {
	return state.mediaManifest?.cameras || [];
}

export function manifestAudioSources() {
	return state.mediaManifest?.audio || [];
}

export function manifestImagesByRole(role: string) {
	return (state.mediaManifest?.images || []).filter((item) => item.role === role);
}

export function selectedMasterVideoPath() {
	return manifestCameras().find((item) => item.role === "master")?.path || state.files.masterVideo;
}
