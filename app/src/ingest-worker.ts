import { spawn } from "node:child_process";
import fs from "node:fs";
import { copyFile, mkdir, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { parentPort, workerData } from "node:worker_threads";
import {
	AUDIO_EXTENSIONS,
	classifyManifest,
	type MediaItem,
	type MediaManifest,
	mediaKindForPath,
	rebuildManifestGroups,
} from "./media-manifest";

type ProjectInfo = {
	id: string;
	name: string;
	root: string;
	sourceRoot: string;
	outputRoot: string;
};

const PROBE_TIMEOUT_MS = 30_000;

function emitProgress(payload: Record<string, any>) {
	parentPort?.postMessage({ type: "progress", payload });
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

function projectRelative(project: ProjectInfo, filePath: string) {
	const relative = path.relative(project.sourceRoot, filePath);
	return relative && !relative.startsWith("..") && !path.isAbsolute(relative);
}

function sanitizePathSegment(value: string) {
	return value.replace(/[^a-zA-Z0-9._-]+/g, "_") || "asset";
}

function uniqueTargetPath(targetDir: string, filename: string) {
	const ext = path.extname(filename);
	const stem = sanitizePathSegment(path.basename(filename, ext));
	let candidate = path.join(targetDir, `${stem}${ext}`);
	let index = 2;
	while (fs.existsSync(candidate)) {
		candidate = path.join(targetDir, `${stem}_${String(index).padStart(2, "0")}${ext}`);
		index += 1;
	}
	return candidate;
}

function bucketForMediaItem(item: MediaItem) {
	if (item.kind === "audio") {
		return "audio";
	}
	if (item.kind === "image") {
		return "images";
	}
	if (item.kind === "subtitle") {
		return "subtitles";
	}
	if (item.kind === "other") {
		return "other";
	}
	return "video";
}

function relativeTargetParts(item: MediaItem) {
	const relative = String(item.relativePath || item.name || "")
		.split(/[\\/]+/)
		.filter(Boolean);
	if (!relative.length) {
		return { dirParts: [], filename: item.name || path.basename(item.path) };
	}
	return {
		dirParts: relative.slice(0, -1).map(sanitizePathSegment),
		filename: relative.at(-1) || item.name || path.basename(item.path),
	};
}

function audioAppendItem(item: MediaItem) {
	if (item.kind === "audio" || AUDIO_EXTENSIONS.has(item.extension.toLowerCase())) {
		item.kind = "audio";
		return true;
	}
	if (item.metadata?.hasAudio) {
		item.kind = "audio";
		return true;
	}
	return false;
}

async function importManifest(project: ProjectInfo, manifest: MediaManifest, mediaManifestName: string) {
	const files = manifest.files || [];
	for (const [index, item] of files.entries()) {
		emitProgress({
			stage: "import",
			current: index + 1,
			total: files.length,
			progress: 0.7 + (files.length ? (index / files.length) * 0.18 : 0.18),
			message: "プロジェクトへ素材を保存しています",
			path: item.path,
		});
		item.originalPath = item.originalPath || item.path;
		const alreadyInProject = Boolean(item.path && path.isAbsolute(item.path) && projectRelative(project, item.path));
		if (!item.path || !path.isAbsolute(item.path) || !fs.existsSync(item.path) || alreadyInProject) {
			if (alreadyInProject) {
				item.metadata.storage = "project-source";
			}
			continue;
		}
		const bucket = bucketForMediaItem(item);
		const { dirParts, filename } = relativeTargetParts(item);
		const targetDir = path.join(project.sourceRoot, bucket, ...dirParts);
		await mkdir(targetDir, { recursive: true });
		const target = uniqueTargetPath(targetDir, filename);
		await copyFile(item.path, target);
		item.path = target;
		item.metadata.storage = "copied";
	}

	rebuildManifestGroups(manifest);
	manifest.sourceDirectory = project.sourceRoot;
	const outputManifestPath = path.join(project.outputRoot, "reports", mediaManifestName);
	manifest.manifestPath = outputManifestPath;
	await mkdir(path.dirname(outputManifestPath), { recursive: true });
	const serialized = JSON.stringify(manifest, null, 2);
	await writeFile(outputManifestPath, serialized, "utf8");
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
		audioOnly?: boolean;
	};
	const audioOnly = Boolean((workerData as { audioOnly?: boolean }).audioOnly);
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
	const supported = inputFiles;
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
	const manifestItems = audioOnly ? items.filter(audioAppendItem) : items;
	if (audioOnly && !manifestItems.length) {
		throw new Error("音声として追加できるファイルが見つかりません。");
	}
	const manifest = classifyManifest(root, manifestItems, inputs);
	const imported = await importManifest(project, manifest, mediaManifestName || "media_manifest.json");
	emitProgress({
		stage: "ready",
		current: imported.files.length,
		total: imported.files.length,
		progress: 0.96,
		message: "解析しています",
		path: imported.manifestPath,
	});
	parentPort?.postMessage({ type: "result", payload: imported });
}

main().catch((error) => {
	parentPort?.postMessage({ type: "error", message: error.message || String(error) });
});
