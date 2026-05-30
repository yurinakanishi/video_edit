import path from "node:path";

export const VIDEO_EXTENSIONS = new Set([".mp4", ".mov", ".m4v", ".mkv", ".avi", ".mts", ".m2ts"]);
export const AUDIO_EXTENSIONS = new Set([".wav", ".mp3", ".aac", ".m4a", ".flac", ".aiff", ".aif"]);
export const IMAGE_EXTENSIONS = new Set([".png", ".jpg", ".jpeg", ".webp"]);
export const SUBTITLE_EXTENSIONS = new Set([".srt", ".ass", ".vtt"]);

export type MediaKind = "video" | "audio" | "image" | "subtitle" | "other";

export type MediaItem = {
	id: string;
	kind: MediaKind;
	role: string;
	label: string;
	path: string;
	originalPath?: string;
	relativePath: string;
	name: string;
	extension: string;
	sizeBytes: number;
	confidence: number;
	reason: string;
	metadata: Record<string, any>;
	proxy?: {
		path: string;
		profile: string;
		sourceSignature: string;
		generatedAt?: string;
		metadata?: Record<string, any>;
	};
	thumbnailDataUrl?: string;
};

export type MediaManifest = {
	version: number;
	sourceDirectory: string;
	sourcePaths?: string[];
	generatedAt: string;
	manifestPath?: string;
	files: MediaItem[];
	cameras: MediaItem[];
	audio: MediaItem[];
	images: MediaItem[];
	subtitles: MediaItem[];
	other: MediaItem[];
	selected: Record<string, any>;
};

export function sourceBucketForSlot(slot: string, filePath: string) {
	const ext = path.extname(filePath).toLowerCase();
	if (slot === "externalAudio" || AUDIO_EXTENSIONS.has(ext)) {
		return "audio";
	}
	if (slot === "logo" || slot === "stillImages" || IMAGE_EXTENSIONS.has(ext)) {
		return "images";
	}
	if (SUBTITLE_EXTENSIONS.has(ext)) {
		return "subtitles";
	}
	return "video";
}

export function mediaKindForPath(filePath: string): MediaKind {
	const ext = path.extname(filePath).toLowerCase();
	if (VIDEO_EXTENSIONS.has(ext)) {
		return "video";
	}
	if (AUDIO_EXTENSIONS.has(ext)) {
		return "audio";
	}
	if (IMAGE_EXTENSIONS.has(ext)) {
		return "image";
	}
	if (SUBTITLE_EXTENSIONS.has(ext)) {
		return "subtitle";
	}
	return "other";
}

function textForScoring(item: MediaItem) {
	return `${item.relativePath} ${item.name}`.toLowerCase();
}

function roleScore(item: MediaItem, patterns: RegExp[]) {
	const text = textForScoring(item);
	return patterns.reduce((score, pattern) => score + (pattern.test(text) ? 1 : 0), 0);
}

function cameraOrderScore(item: MediaItem) {
	const text = textForScoring(item);
	if (/(^|[\\/_\-\s])(1cam|cam1|camera1|カメラ1|メイン|main|master|wide|引き|全体)/i.test(text)) {
		return 1;
	}
	if (/(^|[\\/_\-\s])(2cam|cam2|camera2|カメラ2|right|右)/i.test(text)) {
		return 2;
	}
	if (/(^|[\\/_\-\s])(3cam|cam3|camera3|カメラ3|left|左)/i.test(text)) {
		return 3;
	}
	const match = text.match(/(?:cam|camera|カメラ)[\s_-]*(\d+)/i);
	return match ? Number(match[1]) : 50;
}

function chooseMasterCamera(cameras: MediaItem[]) {
	return [...cameras].sort((a, b) => {
		const masterPatterns = [
			/(^|[\\/_\-\s])(1cam|cam1|camera1|カメラ1)([\\/_\-\s.]|$)/i,
			/(master|main|メイン|wide|引き|全体)/i,
		];
		const scoreA = roleScore(a, masterPatterns) * 100000 + Number(a.metadata.duration || 0);
		const scoreB = roleScore(b, masterPatterns) * 100000 + Number(b.metadata.duration || 0);
		return scoreB - scoreA;
	})[0];
}

export function selectedFilesFromManifest(manifest: MediaManifest) {
	const byRole = (role: string) => manifest.files.find((item) => item.role === role)?.path || "";
	return {
		masterVideo: byRole("master"),
		rightCloseVideo: byRole("camera2"),
		leftCloseVideo: byRole("camera3"),
		externalAudio: manifest.audio[0]?.path || "",
		logo: byRole("logo"),
		stillImages: manifest.images.filter((item) => item.role === "still").map((item) => item.path),
	};
}

export function rebuildManifestGroups(manifest: MediaManifest) {
	const files = manifest.files || [];
	const cameraRoles = new Set(["master", "camera2", "camera3", "camera4", "camera5", "camera6"]);
	manifest.cameras = files
		.filter((item) => item.kind === "video" && cameraRoles.has(item.role))
		.sort((a, b) => {
			if (a.role === "master") {
				return -1;
			}
			if (b.role === "master") {
				return 1;
			}
			return Number(a.role.replace("camera", "")) - Number(b.role.replace("camera", ""));
		});
	manifest.audio = files.filter((item) => item.kind === "audio" && item.role.startsWith("external"));
	manifest.images = files.filter((item) => item.kind === "image" && ["logo", "still"].includes(item.role));
	manifest.subtitles = files.filter((item) => item.kind === "subtitle" && item.role === "subtitle");
	manifest.other = files.filter(
		(item) =>
			!manifest.cameras.includes(item) &&
			!manifest.audio.includes(item) &&
			!manifest.images.includes(item) &&
			!manifest.subtitles.includes(item),
	);
	manifest.selected = selectedFilesFromManifest(manifest);
}

export function classifyManifest(
	sourceDirectory: string,
	items: MediaItem[],
	sourcePaths: string[] = [],
): MediaManifest {
	const manifest: MediaManifest = {
		version: 1,
		sourceDirectory,
		sourcePaths,
		generatedAt: new Date().toISOString(),
		files: items,
		cameras: [],
		audio: [],
		images: [],
		subtitles: [],
		other: [],
		selected: {},
	};
	const cameras = items.filter((item) => item.kind === "video" && item.metadata.hasVideo);
	const master = chooseMasterCamera(cameras);
	const orderedCameras = [...cameras]
		.filter((item) => item !== master)
		.sort((a, b) => {
			const order = cameraOrderScore(a) - cameraOrderScore(b);
			if (order !== 0) {
				return order;
			}
			const time = String(a.metadata.creationTime || "").localeCompare(String(b.metadata.creationTime || ""));
			return time || a.name.localeCompare(b.name);
		});
	if (master) {
		master.role = "master";
		master.label = "Camera 1 / master";
		master.confidence = roleScore(master, [/1cam|cam1|camera1|master|main|メイン|wide|引き|全体/i]) ? 0.92 : 0.72;
		master.reason =
			master.confidence >= 0.9
				? "filename indicates the main/wide camera"
				: "chosen as the most likely timeline master";
	}
	orderedCameras.forEach((item, index) => {
		item.role = `camera${index + 2}`;
		item.label = `Camera ${index + 2}`;
		item.confidence = cameraOrderScore(item) < 50 ? 0.84 : 0.68;
		item.reason =
			item.confidence >= 0.8 ? "filename indicates camera order" : "additional video source ordered by metadata/name";
	});

	const audioFiles = items.filter((item) => item.kind === "audio");
	audioFiles
		.sort((a, b) => {
			const scoreA =
				roleScore(a, [/sound|audio|wav|rec|録音|音声|external|外部|別録/i]) * 100000 + Number(a.metadata.duration || 0);
			const scoreB =
				roleScore(b, [/sound|audio|wav|rec|録音|音声|external|外部|別録/i]) * 100000 + Number(b.metadata.duration || 0);
			return scoreB - scoreA;
		})
		.forEach((item, index) => {
			item.role = index === 0 ? "external" : `external${index + 1}`;
			item.label = index === 0 ? "External audio" : `External audio ${index + 1}`;
			item.confidence = roleScore(item, [/sound|audio|wav|rec|録音|音声|external|外部|別録/i]) ? 0.9 : 0.74;
			item.reason = "standalone audio source";
		});

	const imageFiles = items.filter((item) => item.kind === "image");
	const logo = [...imageFiles].sort((a, b) => {
		const logoPatterns = [/logo|ロゴ|mark|symbol|type-logo|brand/i];
		return roleScore(b, logoPatterns) - roleScore(a, logoPatterns);
	})[0];
	for (const item of imageFiles) {
		if (item === logo && roleScore(item, [/logo|ロゴ|mark|symbol|type-logo|brand/i]) > 0) {
			item.role = "logo";
			item.label = "Logo";
			item.confidence = 0.88;
			item.reason = "filename indicates a logo/brand mark";
		} else {
			item.role = "still";
			item.label = "Still insert";
			item.confidence = 0.76;
			item.reason = "image asset for inserts or visual material";
		}
	}

	items
		.filter((item) => item.kind === "subtitle")
		.forEach((item) => {
			item.role = "subtitle";
			item.label = "Subtitle";
			item.confidence = 0.82;
			item.reason = "subtitle file";
		});
	items
		.filter((item) => item.kind === "other")
		.forEach((item) => {
			item.role = "ignore";
			item.label = "Other";
			item.confidence = 0.2;
			item.reason = "unsupported file type";
		});
	rebuildManifestGroups(manifest);
	return manifest;
}
