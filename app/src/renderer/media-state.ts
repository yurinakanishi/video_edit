import { state } from "./state.js";
import { getAppState, patchAppState } from "./store/app-store.js";
import type { MediaManifest } from "./types.js";

export function mediaManifestSnapshot(manifest: MediaManifest | null = state.mediaManifest): MediaManifest | null {
	if (!manifest) {
		return null;
	}
	return {
		...manifest,
		sourcePaths: manifest.sourcePaths ? [...manifest.sourcePaths] : manifest.sourcePaths,
		files: [...(manifest.files || [])],
		cameras: [...(manifest.cameras || [])],
		audio: [...(manifest.audio || [])],
		images: [...(manifest.images || [])],
		subtitles: [...(manifest.subtitles || [])],
		other: [...(manifest.other || [])],
		selected: { ...(manifest.selected || {}) },
	};
}

export function syncMaterialStore() {
	patchAppState({
		mediaManifest: mediaManifestSnapshot(),
		mediaDirectory: state.mediaDirectory,
		materialPaths: [...state.materialPaths],
		materialSourcePreviews: [...state.materialSourcePreviews],
		materialSourcePreviewLoading: state.materialSourcePreviewLoading,
		materialSourcePreviewRequestId: state.materialSourcePreviewRequestId,
		materialAnalysisCancelable: state.materialAnalysisCancelable,
		materialAnalysisCancelRequested: state.materialAnalysisCancelRequested,
		fullAnalysisRunning: state.fullAnalysisRunning,
		ingestRunning: state.ingestRunning,
		filePreviews: { ...state.filePreviews },
	});
}

export function filesSnapshot() {
	return { ...state.files, stillImages: [...state.files.stillImages] };
}

export function syncFilesStore() {
	patchAppState({
		files: filesSnapshot(),
		filePreviews: { ...state.filePreviews },
		mediaManifest: mediaManifestSnapshot(),
	});
}

export function inputVideoPathValue() {
	return getAppState().inputVideoPath;
}

export function outputPathValue() {
	return getAppState().outputPath;
}

export function setInputVideoPathValue(inputVideoPath: string) {
	patchAppState({ inputVideoPath });
}

export function setOutputPathValue(outputPath: string) {
	patchAppState({ outputPath: outputPath.trim() });
}

export function syncPathPreviewStore() {
	patchAppState({
		inputVideoPath: inputVideoPathValue(),
		outputPath: outputPathValue(),
		filePreviews: { ...state.filePreviews },
		mediaManifest: mediaManifestSnapshot(),
	});
}
