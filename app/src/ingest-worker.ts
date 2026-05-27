import { spawn } from "node:child_process";
import fs from "node:fs";
import { copyFile, mkdir, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { parentPort, workerData } from "node:worker_threads";

type MediaKind = "video" | "audio" | "image" | "subtitle" | "other";

type ProjectInfo = {
	id: string;
	name: string;
	root: string;
	sourceRoot: string;
	outputRoot: string;
};

type MediaItem = {
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
};

type MediaManifest = {
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

const VIDEO_EXTENSIONS = new Set([".mp4", ".mov", ".m4v", ".mkv", ".avi", ".mts", ".m2ts"]);
const AUDIO_EXTENSIONS = new Set([".wav", ".mp3", ".aac", ".m4a", ".flac", ".aiff", ".aif"]);
const IMAGE_EXTENSIONS = new Set([".png", ".jpg", ".jpeg", ".webp"]);
const SUBTITLE_EXTENSIONS = new Set([".srt", ".ass", ".vtt"]);
const PROBE_TIMEOUT_MS = 30_000;

function emitProgress(payload: Record<string, any>) {
	parentPort?.postMessage({ type: "progress", payload });
}

function mediaKindForPath(filePath: string): MediaKind {
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

function parseFraction(value: unknown) {
	if (typeof value !== "string" || !value) {
		return 0;
	}
	if (!value.includes("/")) {
		return Number(value) || 0;
	}
	const [num, den] = value.split("/").map(Number);
	return den ? num / den : 0;
}

function runTool(command: string, args: string[], cwd: string): Promise<string> {
	return new Promise((resolve, reject) => {
		const proc = spawn(command, args, { cwd, windowsHide: true });
		let stdout = "";
		let stderr = "";
		const timer = setTimeout(() => {
			proc.kill();
			reject(new Error(`${path.basename(command)} timed out after ${PROBE_TIMEOUT_MS / 1000}s`));
		}, PROBE_TIMEOUT_MS);
		proc.stdout.on("data", (chunk) => {
			stdout += chunk.toString("utf8");
		});
		proc.stderr.on("data", (chunk) => {
			stderr += chunk.toString("utf8");
		});
		proc.on("error", (error) => {
			clearTimeout(timer);
			reject(error);
		});
		proc.on("exit", (code) => {
			clearTimeout(timer);
			if (code === 0) {
				resolve(stdout);
			} else {
				reject(new Error(stderr || stdout || `${command} exited with ${code}`));
			}
		});
	});
}

async function probeMedia(filePath: string, ffprobePath: string, cwd: string) {
	const metadata: Record<string, any> = {};
	try {
		const raw = await runTool(
			ffprobePath,
			[
				"-v",
				"error",
				"-show_entries",
				"format=duration:format_tags=creation_time:stream=index,codec_type,codec_name,width,height,avg_frame_rate,sample_rate,channels",
				"-of",
				"json",
				filePath,
			],
			cwd,
		);
		const info = JSON.parse(raw);
		const streams = Array.isArray(info.streams) ? info.streams : [];
		const videoStream = streams.find((stream) => stream.codec_type === "video");
		const audioStream = streams.find((stream) => stream.codec_type === "audio");
		metadata.duration = Number(info.format?.duration) || 0;
		metadata.creationTime = info.format?.tags?.creation_time || "";
		metadata.hasVideo = Boolean(videoStream);
		metadata.hasAudio = Boolean(audioStream);
		if (videoStream) {
			metadata.width = Number(videoStream.width) || 0;
			metadata.height = Number(videoStream.height) || 0;
			metadata.fps = parseFraction(videoStream.avg_frame_rate);
			metadata.videoCodec = videoStream.codec_name || "";
		}
		if (audioStream) {
			metadata.audioCodec = audioStream.codec_name || "";
			metadata.sampleRate = Number(audioStream.sample_rate) || 0;
			metadata.channels = Number(audioStream.channels) || 0;
		}
	} catch (error) {
		metadata.probeError = error.message;
	}
	return metadata;
}

function probeImage(filePath: string) {
	try {
		const buffer = fs.readFileSync(filePath);
		if (buffer.length >= 24 && buffer.subarray(1, 4).toString("ascii") === "PNG") {
			return {
				width: buffer.readUInt32BE(16),
				height: buffer.readUInt32BE(20),
				hasVideo: false,
				hasAudio: false,
			};
		}
	} catch {
		// Image dimensions are only advisory for ingest.
	}
	return { hasVideo: false, hasAudio: false };
}

async function walkFiles(root: string) {
	const files: string[] = [];
	const stack = [root];
	while (stack.length) {
		const dir = stack.pop();
		if (!dir) {
			continue;
		}
		const entries = await fs.promises.readdir(dir, { withFileTypes: true });
		for (const entry of entries) {
			const fullPath = path.join(dir, entry.name);
			if (entry.isDirectory()) {
				stack.push(fullPath);
			} else if (entry.isFile()) {
				files.push(fullPath);
			}
		}
	}
	return files;
}

function commonParent(paths: string[]) {
	if (!paths.length) {
		return "";
	}
	const resolved = paths.map((item) => path.resolve(item));
	const parts = resolved.map((item) => item.split(/[\\/]+/));
	let index = 0;
	while (parts.every((item) => item[index] && item[index].toLowerCase() === parts[0][index].toLowerCase())) {
		index += 1;
	}
	const joined = parts[0].slice(0, index).join(path.sep);
	return joined || path.parse(resolved[0]).root;
}

function inputRootForPath(inputPath: string) {
	const resolved = path.resolve(inputPath);
	if (!fs.existsSync(resolved)) {
		return path.dirname(resolved);
	}
	return fs.statSync(resolved).isDirectory() ? resolved : path.dirname(resolved);
}

async function collectInputFiles(inputPaths: string[]) {
	const files: string[] = [];
	const seen = new Set<string>();
	for (const inputPath of inputPaths) {
		const resolved = path.resolve(inputPath);
		if (!fs.existsSync(resolved)) {
			continue;
		}
		const itemStat = await stat(resolved);
		const candidates = itemStat.isDirectory() ? await walkFiles(resolved) : itemStat.isFile() ? [resolved] : [];
		for (const candidate of candidates) {
			const key = path.resolve(candidate).toLowerCase();
			if (seen.has(key)) {
				continue;
			}
			seen.add(key);
			files.push(path.resolve(candidate));
		}
	}
	return files;
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

function legacyFilesFromManifest(manifest: MediaManifest) {
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

function rebuildManifestGroups(manifest: MediaManifest) {
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
	manifest.selected = legacyFilesFromManifest(manifest);
}

function classifyManifest(sourceDirectory: string, items: MediaItem[], sourcePaths: string[] = []): MediaManifest {
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

function projectRelative(project: ProjectInfo, filePath: string) {
	const relative = path.relative(project.sourceRoot, filePath);
	return relative && !relative.startsWith("..") && !path.isAbsolute(relative);
}

function uniqueTargetPath(targetDir: string, filename: string) {
	const ext = path.extname(filename);
	const stem = path.basename(filename, ext).replace(/[^a-zA-Z0-9._-]+/g, "_") || "asset";
	let candidate = path.join(targetDir, `${stem}${ext}`);
	let index = 2;
	while (fs.existsSync(candidate)) {
		candidate = path.join(targetDir, `${stem}_${String(index).padStart(2, "0")}${ext}`);
		index += 1;
	}
	return candidate;
}

async function importManifest(project: ProjectInfo, manifest: MediaManifest, mediaManifestName: string) {
	const files = manifest.files || [];
	for (const [index, item] of files.entries()) {
		emitProgress({
			stage: "import",
			current: index + 1,
			total: files.length,
			progress: 0.7 + (files.length ? (index / files.length) * 0.18 : 0.18),
			message:
				item.kind === "video" || item.kind === "audio"
					? "大容量素材はコピーせず参照しています"
					: "軽量素材を取り込んでいます",
			path: item.path,
		});
		item.originalPath = item.originalPath || item.path;
		item.metadata.storage = item.kind === "video" || item.kind === "audio" ? "referenced" : "copied";
		if (item.kind === "video" || item.kind === "audio") {
			continue;
		}
		if (!item.path || !path.isAbsolute(item.path) || !fs.existsSync(item.path) || projectRelative(project, item.path)) {
			continue;
		}
		const bucket = item.kind === "subtitle" ? "subtitles" : "images";
		const prefix = item.role && item.role !== "ignore" ? item.role : item.kind;
		const targetDir = path.join(project.sourceRoot, bucket);
		await mkdir(targetDir, { recursive: true });
		const target = uniqueTargetPath(targetDir, `${prefix}_${item.name}`);
		await copyFile(item.path, target);
		item.path = target;
	}

	rebuildManifestGroups(manifest);
	const outputManifestPath = path.join(project.outputRoot, "reports", mediaManifestName);
	const sourceManifestPath = path.join(project.sourceRoot, mediaManifestName);
	manifest.manifestPath = outputManifestPath;
	await mkdir(path.dirname(outputManifestPath), { recursive: true });
	await mkdir(path.dirname(sourceManifestPath), { recursive: true });
	const serialized = JSON.stringify(manifest, null, 2);
	await writeFile(outputManifestPath, serialized, "utf8");
	await writeFile(sourceManifestPath, serialized, "utf8");
	emitProgress({
		stage: "manifest",
		current: files.length,
		total: files.length,
		progress: 0.94,
		message: "media_manifest.json を保存しました",
		path: outputManifestPath,
	});
	return manifest;
}

async function main() {
	const { sourceDirectory, sourcePaths, project, ffprobePath, mediaManifestName } = workerData as {
		sourceDirectory: string;
		sourcePaths?: string[];
		project: ProjectInfo;
		ffprobePath: string;
		mediaManifestName: string;
	};
	const inputs = (Array.isArray(sourcePaths) && sourcePaths.length ? sourcePaths : [sourceDirectory])
		.filter(Boolean)
		.map((item) => path.resolve(String(item)));
	const inputLabel = inputs.length === 1 ? inputs[0] : `${inputs.length} selected item(s)`;
	const configuredRoot = sourceDirectory
		? path.resolve(sourceDirectory)
		: inputs.length
			? commonParent(inputs.map(inputRootForPath))
			: "";
	emitProgress({
		stage: "start",
		current: 0,
		total: 0,
		progress: 0,
		message: "解析を開始しました",
		path: inputLabel,
	});
	emitProgress({
		stage: "scan",
		current: 0,
		total: 0,
		progress: 0.02,
		message: "素材を走査しています",
		path: inputLabel,
	});
	const inputFiles = await collectInputFiles(inputs);
	const supported = inputFiles.filter((filePath) => mediaKindForPath(filePath) !== "other");
	const root = configuredRoot || commonParent(supported.map((filePath) => path.dirname(filePath)));
	const items: MediaItem[] = [];
	for (const [index, filePath] of supported.entries()) {
		const kind = mediaKindForPath(filePath);
		emitProgress({
			stage: "probe",
			current: index + 1,
			total: supported.length,
			progress: 0.05 + (supported.length ? (index / supported.length) * 0.55 : 0.55),
			message: "素材ファイルを解析しています",
			path: filePath,
		});
		const itemStat = await stat(filePath);
		const item: MediaItem = {
			id: `media-${String(index + 1).padStart(3, "0")}`,
			kind,
			role: "ignore",
			label: "Unclassified",
			path: filePath,
			originalPath: filePath,
			relativePath: path.relative(root, filePath),
			name: path.basename(filePath),
			extension: path.extname(filePath).toLowerCase(),
			sizeBytes: itemStat.size,
			confidence: 0,
			reason: "",
			metadata: {},
		};
		if (kind === "video" || kind === "audio") {
			item.metadata = await probeMedia(filePath, ffprobePath, root);
			if (kind === "video" && item.metadata.hasVideo === undefined) {
				item.metadata.hasVideo = true;
			}
			if (kind === "audio" && item.metadata.hasAudio === undefined) {
				item.metadata.hasAudio = true;
			}
		} else if (kind === "image") {
			item.metadata = probeImage(filePath);
		}
		items.push(item);
	}
	emitProgress({
		stage: "classify",
		current: supported.length,
		total: supported.length,
		progress: 0.65,
		message: "カメラ・音声・画像・字幕を分類しています",
		path: root,
	});
	const manifest = classifyManifest(root, items, inputs);
	const imported = await importManifest(project, manifest, mediaManifestName || "media_manifest.json");
	emitProgress({
		stage: "ready",
		current: imported.files.length,
		total: imported.files.length,
		progress: 0.96,
		message: "分類結果を UI に反映しています",
		path: imported.manifestPath,
	});
	parentPort?.postMessage({ type: "result", payload: imported });
}

main().catch((error) => {
	parentPort?.postMessage({ type: "error", message: error.message || String(error) });
});
