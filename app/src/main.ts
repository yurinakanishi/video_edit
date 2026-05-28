import { type ChildProcessWithoutNullStreams, spawn } from "node:child_process";
import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import readline from "node:readline";
import { Worker } from "node:worker_threads";
import { app, BrowserWindow, dialog, ipcMain, nativeImage, shell } from "electron";
import {
	classifyManifest,
	IMAGE_EXTENSIONS,
	type MediaItem,
	type MediaKind,
	type MediaManifest,
	mediaKindForPath,
	rebuildManifestGroups,
	SUBTITLE_EXTENSIONS,
	sourceBucketForSlot,
	VIDEO_EXTENSIONS,
} from "./media-manifest";

function hasProjectMarkers(candidate) {
	return (
		fs.existsSync(path.join(candidate, "scripts")) &&
		fs.existsSync(path.join(candidate, "docs", "video_edit_method.md"))
	);
}

function findVideoEditRoot() {
	const configuredRoot = process.env.VIDEO_EDIT_ROOT;
	if (configuredRoot && hasProjectMarkers(configuredRoot)) {
		return path.resolve(configuredRoot);
	}
	const starts = [
		__dirname,
		process.cwd(),
		path.dirname(process.execPath),
		process.resourcesPath,
		path.join(process.resourcesPath || "", "app"),
	].filter(Boolean);
	for (const start of starts) {
		let current = path.resolve(start);
		for (let depth = 0; depth < 10; depth += 1) {
			if (hasProjectMarkers(current)) {
				return current;
			}
			const parent = path.dirname(current);
			if (parent === current) {
				break;
			}
			current = parent;
		}
	}
	return path.resolve(__dirname, "..", "..");
}

const VIDEO_EDIT_ROOT = findVideoEditRoot();
const APP_ROOT = path.resolve(__dirname, "..");
const METHOD_DOC = path.join(VIDEO_EDIT_ROOT, "docs", "video_edit_method.md");
const APP_STATE_ROOT = path.join(VIDEO_EDIT_ROOT, ".video-edit");
const ELECTRON_PROFILE_ROOT = path.join(APP_STATE_ROOT, "electron-profile");
const ELECTRON_CACHE_ROOT = path.join(APP_STATE_ROOT, "electron-cache");
const OUTPUT_ROOT = APP_STATE_ROOT;
const PROJECTS_ROOT = path.join(VIDEO_EDIT_ROOT, "projects");
const SCRIPTS_ROOT = path.join(VIDEO_EDIT_ROOT, "scripts");
const OUTPUT_APP_ROOT = path.join(OUTPUT_ROOT, "app");
const DEFAULT_APP_CONFIG_PATH = path.join(OUTPUT_APP_ROOT, "video_edit_app_config.runtime.json");
const RESOURCE_ICON_PATH = path.join(process.resourcesPath || "", "build", "icon.ico");
const ICON_PATH = fs.existsSync(RESOURCE_ICON_PATH) ? RESOURCE_ICON_PATH : path.join(APP_ROOT, "build", "icon.ico");
const SYNC_REPORT_PATH = path.join(OUTPUT_ROOT, "reports", "app_sync_offsets.json");
const MEDIA_MANIFEST_NAME = "media_manifest.json";
const ANALYSIS_STATE_NAME = "analysis_state.json";
const PROJECT_STATE_NAME = "project_state.json";
const DEFAULT_FFMPEG_EXE = "C:\\ProgramData\\chocolatey\\bin\\ffmpeg.exe";
const DEFAULT_FFPROBE_EXE = "C:\\ProgramData\\chocolatey\\bin\\ffprobe.exe";
const PYTHON_EXE = process.env.VIDEO_EDIT_PYTHON || "python";
const CODEX_EXE_NAME = process.platform === "win32" ? "codex.exe" : "codex";
const SMOKE_QUIT_MS = Math.max(0, Number(process.env.VIDEO_EDIT_SMOKE_QUIT_MS || 0));

function configureElectronStorage() {
	try {
		fs.mkdirSync(ELECTRON_PROFILE_ROOT, { recursive: true });
		fs.mkdirSync(ELECTRON_CACHE_ROOT, { recursive: true });
		app.setPath("userData", ELECTRON_PROFILE_ROOT);
		app.commandLine.appendSwitch("disk-cache-dir", ELECTRON_CACHE_ROOT);
	} catch (error) {
		console.warn("Unable to configure Electron storage paths", error);
	}
}

configureElectronStorage();

type Locale = "ja" | "en";

const mainMessages: Record<Locale, Record<string, string>> = {
	ja: {
		"dialog.selectProjectFolder": "プロジェクトフォルダを選択",
		"dialog.deleteProjectTitle": "プロジェクト削除",
		"dialog.deleteProjectMessage": "プロジェクト「{name}」を削除しますか？",
		"dialog.deleteProjectDetail": "この操作は取り消せません。\n{path}",
		"dialog.deleteProjectConfirm": "削除する",
		"dialog.cancel": "キャンセル",
		"dialog.selectOutputVideo": "出力動画を選択",
		"filter.mp4Video": "MP4 動画",
	},
	en: {
		"dialog.selectProjectFolder": "Select project folder",
		"dialog.deleteProjectTitle": "Delete project",
		"dialog.deleteProjectMessage": 'Delete project "{name}"?',
		"dialog.deleteProjectDetail": "This cannot be undone.\n{path}",
		"dialog.deleteProjectConfirm": "Delete",
		"dialog.cancel": "Cancel",
		"dialog.selectOutputVideo": "Select output video",
		"filter.mp4Video": "MP4 video",
	},
};

function normalizeLocale(value: unknown): Locale {
	return value === "en" ? "en" : "ja";
}

function mt(locale: Locale, key: string, values: Record<string, string | number> = {}) {
	const template = mainMessages[locale]?.[key] || mainMessages.en[key] || key;
	return Object.entries(values).reduce(
		(result, [name, value]) => result.replaceAll(`{${name}}`, String(value)),
		template,
	);
}

function pathEnvValue(env = process.env) {
	const key = Object.keys(env).find((name) => name.toLowerCase() === "path") || "PATH";
	return env[key] || "";
}

function isWindowsAppsCandidate(candidate: string) {
	return process.platform === "win32" && candidate.toLowerCase().includes(`${path.sep}windowsapps${path.sep}`);
}

function normalizeCodexCandidate(candidate: string) {
	const trimmed = candidate.trim().replace(/^"|"$/g, "");
	if (!trimmed) {
		return null;
	}
	try {
		if (fs.existsSync(trimmed) && fs.statSync(trimmed).isDirectory()) {
			return path.join(trimmed, CODEX_EXE_NAME);
		}
	} catch {
		return null;
	}
	return trimmed;
}

function codexStandaloneReleaseCandidates() {
	const home = process.env.USERPROFILE || process.env.HOME;
	if (!home) {
		return [];
	}
	const releasesRoot = path.join(home, ".codex", "packages", "standalone", "releases");
	try {
		return fs
			.readdirSync(releasesRoot, { withFileTypes: true })
			.filter((entry) => entry.isDirectory())
			.map((entry) => {
				const codexPath = path.join(releasesRoot, entry.name, "bin", CODEX_EXE_NAME);
				const stat = fs.existsSync(codexPath) ? fs.statSync(codexPath) : null;
				return { codexPath, mtimeMs: stat?.mtimeMs || 0 };
			})
			.filter((entry) => entry.mtimeMs > 0)
			.sort((left, right) => right.mtimeMs - left.mtimeMs)
			.map((entry) => entry.codexPath);
	} catch {
		return [];
	}
}

function resolveCodexExecutable() {
	const candidates = [
		process.env.VIDEO_EDIT_CODEX_CLI || "",
		process.env.CODEX_CLI || "",
		...pathEnvValue()
			.split(path.delimiter)
			.filter(Boolean)
			.map((entry) => path.join(entry, CODEX_EXE_NAME)),
		...codexStandaloneReleaseCandidates(),
	];
	for (const rawCandidate of candidates) {
		const candidate = normalizeCodexCandidate(rawCandidate);
		if (!candidate || isWindowsAppsCandidate(candidate)) {
			continue;
		}
		try {
			if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) {
				return candidate;
			}
		} catch {}
	}
	return CODEX_EXE_NAME;
}

type ProjectInfo = {
	id: string;
	name: string;
	root: string;
	sourceRoot: string;
	outputRoot: string;
};

const PROJECT_SUBDIRS = [
	"source/video",
	"source/audio",
	"source/images",
	"source/subtitles",
	"output/videos",
	"output/overlays",
	"output/reports",
	"output/transcripts",
	"output/audio",
	"output/images",
	"output/diagnostics",
	"output/app",
];

type IngestProgress = {
	stage: string;
	current: number;
	total: number;
	progress: number;
	message: string;
	path?: string;
};

type IngestProgressEmitter = (payload: IngestProgress) => void;
type WorkflowProgress = {
	action: string;
	stage: string;
	progress: number;
	message: string;
	text?: string;
};
type WorkflowProgressEmitter = (payload: WorkflowProgress) => void;
type ActiveWorkflowProcess = {
	proc: ChildProcessWithoutNullStreams;
	action: string;
	cancelRequested: boolean;
};

type SubtitleCaption = {
	start: number;
	end: number;
	text: string;
};

function slugifyProjectId(value: string) {
	const slug = value
		.trim()
		.toLowerCase()
		.replace(/[^a-z0-9._-]+/g, "-")
		.replace(/^-+|-+$/g, "");
	return slug || `project-${new Date().toISOString().slice(0, 10)}`;
}

function safeProjectId(value: string) {
	const id = slugifyProjectId(value);
	if (id === "." || id === ".." || id.includes("..")) {
		throw new Error("invalid project id");
	}
	return id;
}

function projectInfo(id: string, name?: string): ProjectInfo {
	const safeId = safeProjectId(id);
	const root = path.join(PROJECTS_ROOT, safeId);
	return {
		id: safeId,
		name: name?.trim() || safeId,
		root,
		sourceRoot: path.join(root, "source"),
		outputRoot: path.join(root, "output"),
	};
}

function ensureProjectDirs(project: ProjectInfo) {
	for (const subdir of PROJECT_SUBDIRS) {
		fs.mkdirSync(path.join(project.root, subdir), { recursive: true });
	}
	fs.writeFileSync(
		path.join(project.root, "project.json"),
		JSON.stringify(
			{
				id: project.id,
				name: project.name,
				sourceRoot: project.sourceRoot,
				outputRoot: project.outputRoot,
				updatedAt: new Date().toISOString(),
			},
			null,
			2,
		),
		"utf8",
	);
}

function assertProjectRootInProjects(rootPath: string) {
	const projectsRoot = path.resolve(PROJECTS_ROOT);
	const root = path.resolve(rootPath);
	const relative = path.relative(projectsRoot, root);
	if (!relative || relative.startsWith("..") || path.isAbsolute(relative)) {
		throw new Error("project folder must be inside the projects directory");
	}
	return root;
}

function childPathOrDefault(root: string, configured: unknown, fallback: string) {
	const candidate = typeof configured === "string" && configured ? path.resolve(configured) : fallback;
	const relative = path.relative(root, candidate);
	if (!relative || relative.startsWith("..") || path.isAbsolute(relative)) {
		return fallback;
	}
	return candidate;
}

function readJsonFile(filePath: string) {
	try {
		return JSON.parse(fs.readFileSync(filePath, "utf8"));
	} catch {
		return null;
	}
}

function projectInfoFromRoot(rootPath: string, fallbackName?: string): ProjectInfo {
	const root = assertProjectRootInProjects(rootPath);
	const metadata = readJsonFile(path.join(root, "project.json")) || {};
	const id = safeProjectId(path.basename(root));
	const name = String(metadata.name || fallbackName || id).trim() || id;
	return {
		id,
		name,
		root,
		sourceRoot: childPathOrDefault(root, metadata.sourceRoot, path.join(root, "source")),
		outputRoot: childPathOrDefault(root, metadata.outputRoot, path.join(root, "output")),
	};
}

function projectInfoFromPayload(project: any): ProjectInfo {
	if (project?.root) {
		return projectInfoFromRoot(project.root, project.name);
	}
	if (project?.id) {
		return projectInfo(project.id, project.name);
	}
	throw new Error("project is required");
}

function readProjectMediaManifest(project: ProjectInfo) {
	const candidate = path.join(project.outputRoot, "reports", MEDIA_MANIFEST_NAME);
	const manifest = readJsonFile(candidate);
	if (manifest?.files && Array.isArray(manifest.files)) {
		manifest.manifestPath = manifest.manifestPath || candidate;
		return manifest;
	}
	return null;
}

function listProjects() {
	fs.mkdirSync(PROJECTS_ROOT, { recursive: true });
	return fs
		.readdirSync(PROJECTS_ROOT, { withFileTypes: true })
		.filter((entry) => entry.isDirectory() && !entry.name.startsWith(".") && !entry.name.startsWith("__"))
		.map((entry) => {
			try {
				const root = path.join(PROJECTS_ROOT, entry.name);
				const metadata = readJsonFile(path.join(root, "project.json")) || {};
				if (!metadata.id && !fs.existsSync(path.join(root, "source")) && !fs.existsSync(path.join(root, "output"))) {
					return null;
				}
				const project = projectInfoFromRoot(root, entry.name);
				const manifest = readProjectMediaManifest(project);
				const stat = fs.statSync(root);
				const updatedAt = String(metadata.updatedAt || new Date(stat.mtimeMs).toISOString());
				return {
					project,
					updatedAt,
					lastModifiedAt: new Date(stat.mtimeMs).toISOString(),
					hasManifest: Boolean(manifest),
					manifestPath: manifest?.manifestPath || "",
					mediaCount: Array.isArray(manifest?.files) ? manifest.files.length : 0,
				};
			} catch {
				return null;
			}
		})
		.filter(Boolean)
		.sort((left: any, right: any) => String(right.updatedAt).localeCompare(String(left.updatedAt)));
}

function analysisStatePathForProject(project: ProjectInfo) {
	return path.join(project.outputRoot, "app", ANALYSIS_STATE_NAME);
}

function normalizeAnalysisStateResult(item: any) {
	const key = String(item?.key || "").trim();
	if (!key) {
		return null;
	}
	const status = ["done", "error", "running"].includes(String(item?.status)) ? String(item.status) : "done";
	return {
		key,
		label: String(item?.label || ""),
		status,
		detail: String(item?.detail || ""),
		path: String(item?.path || ""),
	};
}

function readProjectAnalysisState(project: ProjectInfo) {
	const statePath = analysisStatePathForProject(project);
	const payload = readJsonFile(statePath);
	if (!payload || typeof payload !== "object") {
		return null;
	}
	return {
		...payload,
		path: statePath,
		results: Array.isArray(payload.results) ? payload.results.map(normalizeAnalysisStateResult).filter(Boolean) : [],
	};
}

function writeProjectAnalysisState(project: ProjectInfo, payload: any) {
	const statePath = analysisStatePathForProject(project);
	const results = Array.isArray(payload?.results)
		? payload.results.map(normalizeAnalysisStateResult).filter(Boolean)
		: [];
	const normalized = {
		version: 1,
		updatedAt: new Date().toISOString(),
		project: {
			id: project.id,
			name: project.name,
			root: project.root,
			outputRoot: project.outputRoot,
		},
		mediaManifestPath: String(payload?.mediaManifestPath || ""),
		mediaManifestGeneratedAt: String(payload?.mediaManifestGeneratedAt || ""),
		mediaManifestFileCount: Number(payload?.mediaManifestFileCount || 0),
		results,
	};
	fs.mkdirSync(path.dirname(statePath), { recursive: true });
	fs.writeFileSync(statePath, JSON.stringify(normalized, null, 2), "utf8");
	return { ...normalized, path: statePath };
}

function normalizedFileKey(value: unknown) {
	const text = String(value || "").trim();
	if (!text) {
		return "";
	}
	try {
		return path.resolve(text).toLowerCase();
	} catch {
		return text.toLowerCase();
	}
}

function fileExists(filePath: string) {
	return Boolean(filePath && fs.existsSync(filePath) && fs.statSync(filePath).isFile());
}

function safeAnalysisLabel(value: string) {
	return value.replace(/[^A-Za-z0-9._-]+/g, "_").replace(/^_+|_+$/g, "") || "source";
}

function withoutExtensionParts(filePath: string) {
	const parsed = path.parse(filePath);
	return path.join(parsed.dir, parsed.name);
}

function safePersonStem(value: string) {
	return safeAnalysisLabel(
		value
			.split(/[\\/]+/)
			.filter(Boolean)
			.join("_"),
	);
}

function relativePathIfInside(root: string, filePath: string) {
	if (!root || !filePath) {
		return "";
	}
	const relative = path.relative(path.resolve(root), path.resolve(filePath));
	if (!relative || relative.startsWith("..") || path.isAbsolute(relative)) {
		return "";
	}
	return relative;
}

function outputStatus(key: string, labelKey: string, candidates: string[], existsOverride?: boolean) {
	const existing = candidates.find(fileExists) || candidates.find(Boolean) || "";
	return {
		key,
		label: labelKey,
		labelKey,
		path: existing,
		exists: existsOverride === undefined ? fileExists(existing) : Boolean(existsOverride),
	};
}

function mediaManifestFromAppConfig(appConfig: any): MediaManifest | null {
	const manifest = appConfig?.assets?.mediaManifest;
	if (manifest && typeof manifest === "object" && Array.isArray(manifest.files)) {
		return manifest as MediaManifest;
	}
	const manifestPath = String(appConfig?.assets?.mediaManifestPath || "");
	const loaded = manifestPath ? readJsonFile(manifestPath) : null;
	return loaded && Array.isArray(loaded.files) ? (loaded as MediaManifest) : null;
}

function jsonFilesByVideoPath(directory: string, suffix: string) {
	const byPath = new Map<string, string>();
	if (!directory || !fs.existsSync(directory)) {
		return byPath;
	}
	for (const name of fs.readdirSync(directory)) {
		if (!name.endsWith(suffix)) {
			continue;
		}
		const filePath = path.join(directory, name);
		const payload = readJsonFile(filePath);
		const videoPath = normalizedFileKey(payload?.video_path);
		if (videoPath) {
			byPath.set(videoPath, filePath);
		}
	}
	return byPath;
}

function transcriptEntriesByPath(outputRoot: string) {
	const manifestPath = path.join(outputRoot, "transcripts", "manifest_sources", "manifest_transcripts.json");
	const manifest = readJsonFile(manifestPath);
	const byPath = new Map<string, any>();
	const transcripts = Array.isArray(manifest?.transcripts) ? manifest.transcripts : [];
	for (const item of transcripts) {
		const key = normalizedFileKey(item?.path);
		if (key) {
			byPath.set(key, item);
		}
	}
	return byPath;
}

function pathsInJsonList(filePath: string) {
	const payload = readJsonFile(filePath);
	const items = Array.isArray(payload) ? payload : Array.isArray(payload?.items) ? payload.items : [];
	return new Set(items.map((item: any) => normalizedFileKey(item?.path)).filter(Boolean));
}

function transcriptComparisonPaths(filePath: string) {
	const payload = readJsonFile(filePath);
	const paths = new Set<string>();
	for (const item of [payload?.primary, ...(Array.isArray(payload?.items) ? payload.items : [])]) {
		const key = normalizedFileKey(item?.path);
		if (key) {
			paths.add(key);
		}
	}
	return paths;
}

function syncReportPaths(filePath: string) {
	const payload = readJsonFile(filePath);
	const offsets = payload?.offsets && typeof payload.offsets === "object" ? payload.offsets : {};
	const paths = new Set<string>();
	for (const item of Object.values(offsets) as any[]) {
		const key = normalizedFileKey(item?.path);
		if (key) {
			paths.add(key);
		}
	}
	return paths;
}

function personOutputCandidates(item: MediaItem, appConfig: any, outputRoot: string, kind: "bboxes" | "plan") {
	const directory =
		kind === "bboxes"
			? String(appConfig?.analysis?.personBboxesDir || path.join(outputRoot, "reports", "person_bboxes"))
			: String(appConfig?.analysis?.personEditPlansDir || path.join(outputRoot, "reports", "person_edit_plans"));
	const suffix = kind === "bboxes" ? "_person_bboxes.json" : "_person_edit_plan.json";
	const stems = new Set<string>();
	const itemPath = String(item.path || "");
	if (itemPath) {
		stems.add(safePersonStem(path.parse(itemPath).name));
	}
	if (item.relativePath) {
		stems.add(safePersonStem(withoutExtensionParts(item.relativePath)));
	}
	const sourceRoot = String(appConfig?.project?.sourceRoot || "");
	for (const root of [sourceRoot ? path.join(sourceRoot, "video") : "", String(appConfig?.assets?.sourceRoot || "")]) {
		const relative = relativePathIfInside(root, itemPath);
		if (relative) {
			stems.add(safePersonStem(withoutExtensionParts(relative)));
		}
	}
	return [...stems].map((stem) => path.join(directory, `${stem}${suffix}`));
}

function transcriptOutputCandidates(item: MediaItem, outputRoot: string, entry: any | null) {
	if (entry) {
		return [String(entry.json || ""), String(entry.srt || ""), String(entry.settings || "")].filter(Boolean);
	}
	const label = safeAnalysisLabel(`${item.role || "source"}_${path.parse(String(item.path || item.name || "")).name}`);
	const directory = path.join(outputRoot, "transcripts", "manifest_sources");
	return [path.join(directory, `${label}.json`), path.join(directory, `${label}.srt`)];
}

function materialAnalysisStatuses(appConfig: any) {
	const manifest = mediaManifestFromAppConfig(appConfig);
	const outputRoot = outputRootFromConfig(appConfig);
	const files = Array.isArray(manifest?.files) ? manifest.files : [];
	const cameraRoles = new Set(["master", "camera2", "camera3", "camera4", "camera5", "camera6"]);
	const transcriptRoles = new Set(["master", "camera2", "camera3", "camera4", "camera5", "camera6"]);
	const personBboxes = jsonFilesByVideoPath(
		String(appConfig?.analysis?.personBboxesDir || path.join(outputRoot, "reports", "person_bboxes")),
		"_person_bboxes.json",
	);
	const personPlans = jsonFilesByVideoPath(
		String(appConfig?.analysis?.personEditPlansDir || path.join(outputRoot, "reports", "person_edit_plans")),
		"_person_edit_plan.json",
	);
	const transcripts = transcriptEntriesByPath(outputRoot);
	const syncPath = path.join(outputRoot, "reports", "app_sync_offsets.json");
	const syncedPaths = syncReportPaths(syncPath);
	const blockingPath = path.join(outputRoot, "diagnostics", "opencv_blocking_analysis", "clip_metrics.json");
	const blockedPaths = pathsInJsonList(blockingPath);
	const comparisonPath = String(
		appConfig?.transcriptComparison?.outputPath || path.join(outputRoot, "reports", "transcript_comparison.json"),
	);
	const comparedPaths = transcriptComparisonPaths(comparisonPath);
	const statuses: Record<string, any> = {};
	for (const item of files) {
		const itemPath = String(item.path || "");
		const key = normalizedFileKey(itemPath);
		if (!key) {
			continue;
		}
		const outputs: any[] = [];
		const isCameraVideo = item.kind === "video" && cameraRoles.has(item.role);
		const isTranscriptSource =
			(item.kind === "audio" && String(item.role || "").startsWith("external")) ||
			(item.kind === "video" && transcriptRoles.has(item.role) && item.metadata?.hasAudio !== false);
		if (isCameraVideo) {
			outputs.push(
				outputStatus("person-bboxes", "analysis.output.personBboxes", [
					personBboxes.get(key) || "",
					...personOutputCandidates(item, appConfig, outputRoot, "bboxes"),
				]),
				outputStatus("person-edit-plan", "analysis.output.personEditPlan", [
					personPlans.get(key) || "",
					...personOutputCandidates(item, appConfig, outputRoot, "plan"),
				]),
				outputStatus("blocking-metrics", "analysis.output.blockingMetrics", [blockingPath], blockedPaths.has(key)),
			);
		}
		if (isTranscriptSource) {
			const entry = transcripts.get(key) || null;
			outputs.push(
				outputStatus(
					"transcript-json",
					"analysis.output.transcriptJson",
					transcriptOutputCandidates(item, outputRoot, entry).filter((candidate) => candidate.endsWith(".json")),
				),
				outputStatus(
					"transcript-srt",
					"analysis.output.transcriptSrt",
					transcriptOutputCandidates(item, outputRoot, entry).filter((candidate) => candidate.endsWith(".srt")),
				),
				outputStatus(
					"transcript-comparison",
					"analysis.output.transcriptComparison",
					[comparisonPath],
					comparedPaths.has(key),
				),
			);
		}
		if (
			(item.kind === "video" && cameraRoles.has(item.role)) ||
			(item.kind === "audio" && String(item.role || "").startsWith("external"))
		) {
			outputs.push(outputStatus("sync-offset", "analysis.output.syncOffset", [syncPath], syncedPaths.has(key)));
		}
		const completed = outputs.filter((output) => output.exists).length;
		const total = outputs.length;
		const state = total === 0 ? "none" : completed === total ? "done" : completed > 0 ? "partial" : "none";
		statuses[key] = {
			key,
			path: itemPath,
			state,
			completed,
			total,
			outputs,
			message: total ? `${completed}/${total}` : "",
			updatedAt: new Date().toISOString(),
		};
	}
	return { statuses, updatedAt: new Date().toISOString() };
}

function projectStatePathForProject(project: ProjectInfo) {
	return path.join(project.root, PROJECT_STATE_NAME);
}

const PROJECT_STATE_SECTIONS = new Set([
	"assets",
	"render",
	"music",
	"omissionCard",
	"thumbnail",
	"subtitleReview",
	"subtitleSpeakers",
	"transcriptComparison",
	"workflow",
	"replaceAudio",
	"analysis",
	"style",
	"glossary",
	"tools",
	"ui",
]);

function normalizeProjectState(project: ProjectInfo, payload: any, revision: number) {
	const source = payload && typeof payload === "object" ? payload : {};
	const normalized: Record<string, any> = {
		version: 1,
		revision,
		updatedAt: new Date().toISOString(),
		project: {
			id: project.id,
			name: project.name,
			root: project.root,
			sourceRoot: project.sourceRoot,
			outputRoot: project.outputRoot,
		},
	};
	for (const key of PROJECT_STATE_SECTIONS) {
		const value = source[key];
		if (value === undefined) {
			continue;
		}
		normalized[key] = value;
	}
	return normalized;
}

function readProjectState(project: ProjectInfo) {
	const statePath = projectStatePathForProject(project);
	const payload = readJsonFile(statePath);
	if (!payload || typeof payload !== "object") {
		return null;
	}
	const revision = Math.max(1, Number(payload.revision || 1));
	return {
		...normalizeProjectState(project, payload, revision),
		path: statePath,
	};
}

function writeProjectState(project: ProjectInfo, payload: any, options: { baseRevision?: number | null } = {}) {
	const statePath = projectStatePathForProject(project);
	const current = readJsonFile(statePath);
	const currentRevision = Math.max(0, Number(current?.revision || 0));
	const baseRevision = options.baseRevision;
	if (baseRevision !== undefined && baseRevision !== null && Number(baseRevision) !== currentRevision) {
		throw new Error(`project state revision mismatch: expected ${baseRevision}, found ${currentRevision}`);
	}
	const nextRevision = currentRevision + 1;
	const normalized = normalizeProjectState(project, payload, nextRevision);
	fs.mkdirSync(path.dirname(statePath), { recursive: true });
	fs.writeFileSync(statePath, JSON.stringify(normalized, null, 2), "utf8");
	return { ...normalized, path: statePath };
}

function decodeJsonPointerPart(value: string) {
	return value.replace(/~1/g, "/").replace(/~0/g, "~");
}

function pointerParts(pointer: string) {
	if (pointer === "") {
		return [];
	}
	if (!pointer.startsWith("/")) {
		throw new Error(`invalid JSON pointer: ${pointer}`);
	}
	return pointer.slice(1).split("/").map(decodeJsonPointerPart);
}

function containerForPatch(root: any, pathParts: string[]) {
	let container = root;
	for (const part of pathParts.slice(0, -1)) {
		if (Array.isArray(container)) {
			const index = Number(part);
			if (!Number.isInteger(index) || index < 0 || index >= container.length) {
				throw new Error(`invalid array path segment: ${part}`);
			}
			container = container[index];
			continue;
		}
		if (!container || typeof container !== "object" || !(part in container)) {
			throw new Error(`missing object path segment: ${part}`);
		}
		container = container[part];
	}
	return { container, key: pathParts[pathParts.length - 1] };
}

function applyProjectStatePatchDocument(document: any, operations: any[]) {
	if (!Array.isArray(operations)) {
		throw new Error("patch operations must be an array");
	}
	const root = structuredClone(document || {});
	for (const operation of operations) {
		const op = String(operation?.op || "");
		const pathValue = String(operation?.path || "");
		const parts = pointerParts(pathValue);
		if (!parts.length) {
			if (op === "replace" || op === "add") {
				if (!operation.value || typeof operation.value !== "object" || Array.isArray(operation.value)) {
					throw new Error("root replacement must be an object");
				}
				for (const key of Object.keys(root)) {
					delete root[key];
				}
				Object.assign(root, operation.value);
				continue;
			}
			throw new Error(`unsupported root patch operation: ${op}`);
		}
		const { container, key } = containerForPatch(root, parts);
		if (Array.isArray(container)) {
			if (op === "add" && key === "-") {
				container.push(operation.value);
				continue;
			}
			const index = Number(key);
			if (!Number.isInteger(index) || index < 0 || index > container.length) {
				throw new Error(`invalid array index: ${key}`);
			}
			if (op === "remove") {
				if (index >= container.length) {
					throw new Error(`array index out of range: ${key}`);
				}
				container.splice(index, 1);
			} else if (op === "replace") {
				if (index >= container.length) {
					throw new Error(`array index out of range: ${key}`);
				}
				container[index] = operation.value;
			} else if (op === "add") {
				container.splice(index, 0, operation.value);
			} else {
				throw new Error(`unsupported patch operation: ${op}`);
			}
			continue;
		}
		if (!container || typeof container !== "object") {
			throw new Error(`patch target is not an object: ${pathValue}`);
		}
		if (op === "remove") {
			delete container[key];
		} else if (op === "replace") {
			if (!(key in container)) {
				throw new Error(`replace target does not exist: ${pathValue}`);
			}
			container[key] = operation.value;
		} else if (op === "add") {
			container[key] = operation.value;
		} else {
			throw new Error(`unsupported patch operation: ${op}`);
		}
	}
	return root;
}

function patchProjectState(project: ProjectInfo, operations: any[], baseRevision?: number | null) {
	const current: any = readProjectState(project) || normalizeProjectState(project, {}, 0);
	if (baseRevision !== undefined && baseRevision !== null && Number(baseRevision) !== Number(current.revision || 0)) {
		throw new Error(`project state revision mismatch: expected ${baseRevision}, found ${current.revision || 0}`);
	}
	const patched = applyProjectStatePatchDocument(current, operations);
	return writeProjectState(project, patched, { baseRevision: Number(current.revision || 0) });
}

function cleanSubtitleText(value: string) {
	return value
		.replace(/\{\\[^}]+}/g, "")
		.replace(/<[^>]+>/g, "")
		.replace(/\\N/g, " ")
		.replace(/\s+/g, " ")
		.trim();
}

function parseSubtitleTime(value: string) {
	const parts = value.trim().replace(",", ".").split(":").map(Number);
	if (parts.some((part) => !Number.isFinite(part))) {
		return 0;
	}
	if (parts.length === 3) {
		return parts[0] * 3600 + parts[1] * 60 + parts[2];
	}
	if (parts.length === 2) {
		return parts[0] * 60 + parts[1];
	}
	return Number(value) || 0;
}

function formatSubtitleTime(seconds: number) {
	const safe = Math.max(0, Math.floor(seconds));
	const hours = Math.floor(safe / 3600);
	const minutes = Math.floor((safe % 3600) / 60);
	const secs = safe % 60;
	if (hours > 0) {
		return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
	}
	return `${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

function parseBlockSubtitle(raw: string) {
	const captions: SubtitleCaption[] = [];
	for (const block of raw.replace(/\r/g, "").split(/\n\s*\n/)) {
		const lines = block
			.split("\n")
			.map((line) => line.trim())
			.filter(Boolean);
		const timeIndex = lines.findIndex((line) => line.includes("-->"));
		if (timeIndex < 0) {
			continue;
		}
		const [startRaw, endPart = ""] = lines[timeIndex].split("-->");
		const endRaw = endPart.trim().split(/\s+/)[0] || "";
		const text = cleanSubtitleText(lines.slice(timeIndex + 1).join(" / "));
		if (!text) {
			continue;
		}
		captions.push({
			start: parseSubtitleTime(startRaw.trim().split(/\s+/)[0] || "0"),
			end: parseSubtitleTime(endRaw),
			text,
		});
	}
	return captions;
}

function parseAssSubtitle(raw: string) {
	const captions: SubtitleCaption[] = [];
	for (const line of raw.replace(/\r/g, "").split("\n")) {
		if (!line.startsWith("Dialogue:")) {
			continue;
		}
		const parts = line.slice("Dialogue:".length).split(",");
		if (parts.length < 10) {
			continue;
		}
		const text = cleanSubtitleText(parts.slice(9).join(","));
		if (!text) {
			continue;
		}
		captions.push({
			start: parseSubtitleTime(parts[1] || "0"),
			end: parseSubtitleTime(parts[2] || "0"),
			text,
		});
	}
	return captions;
}

function parseSubtitleFile(filePath: string) {
	const raw = fs.readFileSync(filePath, "utf8");
	const ext = path.extname(filePath).toLowerCase();
	if (ext === ".ass") {
		return parseAssSubtitle(raw);
	}
	return parseBlockSubtitle(raw);
}

function subtitlePathsFromConfig(appConfig: any) {
	const outputRoot = outputRootFromConfig(appConfig);
	const reportPath = path.join(outputRoot, "transcripts", "manifest_sources", "manifest_transcripts.json");
	if (!fs.existsSync(reportPath)) {
		return [];
	}
	const report = JSON.parse(fs.readFileSync(reportPath, "utf8"));
	if (report?.manifestFingerprint !== transcriptManifestFingerprint(appConfig)) {
		return [];
	}
	const paths: string[] = [];
	if (report.primarySrt) {
		paths.push(String(report.primarySrt));
	}
	if (Array.isArray(report.transcripts)) {
		for (const item of report.transcripts) {
			if (item?.srt) {
				paths.push(String(item.srt));
			}
		}
	}
	return paths.filter((filePath) => SUBTITLE_EXTENSIONS.has(path.extname(filePath).toLowerCase()));
}

function manifestForConfig(appConfig: any) {
	const manifest = appConfig?.assets?.mediaManifest;
	if (manifest?.files) {
		return manifest;
	}
	const manifestPath = appConfig?.assets?.mediaManifestPath;
	if (manifestPath && fs.existsSync(String(manifestPath))) {
		return JSON.parse(fs.readFileSync(String(manifestPath), "utf8"));
	}
	return {};
}

function transcriptManifestFingerprint(appConfig: any) {
	const manifest = manifestForConfig(appConfig);
	const cameraRoles = new Set(["master", "camera2", "camera3", "camera4", "camera5", "camera6"]);
	const entries = (Array.isArray(manifest?.files) ? manifest.files : [])
		.filter((item: any) => {
			const kind = String(item?.kind || "");
			const role = String(item?.role || "");
			if (kind === "audio" && role.startsWith("external")) {
				return true;
			}
			return kind === "video" && cameraRoles.has(role) && item?.metadata?.hasAudio !== false;
		})
		.map((item: any) => {
			const filePath = path.resolve(String(item.path || ""));
			if (!fs.existsSync(filePath)) {
				return null;
			}
			const stat = fs.statSync(filePath);
			return {
				kind: String(item.kind || ""),
				role: String(item.role || ""),
				path: filePath.toLowerCase(),
				size: stat.size,
				mtimeMs: Math.round(stat.mtimeMs),
			};
		})
		.filter(Boolean)
		.sort((a: any, b: any) => `${a.kind}\0${a.role}\0${a.path}`.localeCompare(`${b.kind}\0${b.role}\0${b.path}`));
	if (!entries.length) {
		return "";
	}
	return createHash("sha256").update(JSON.stringify(entries)).digest("hex");
}

function loadSubtitleCaptions(_manifest: any, appConfig: any) {
	const candidates = subtitlePathsFromConfig(appConfig);
	const seen = new Set<string>();
	for (const candidate of candidates) {
		const filePath = path.resolve(candidate);
		if (seen.has(filePath) || !fs.existsSync(filePath) || !fs.statSync(filePath).isFile()) {
			continue;
		}
		seen.add(filePath);
		const captions = parseSubtitleFile(filePath);
		if (captions.length) {
			return { path: filePath, captions };
		}
	}
	return { path: "", captions: [] as SubtitleCaption[] };
}

function punchlineTextFromCaptions(captions: SubtitleCaption[]) {
	return captions
		.filter((caption) => caption.text)
		.slice(0, 40)
		.map((caption) => `${formatSubtitleTime(caption.start)}-${formatSubtitleTime(caption.end)}  ${caption.text}`)
		.join("\n");
}

function titleTextFromCaptions(captions: SubtitleCaption[]) {
	const text = captions
		.map((caption) => caption.text)
		.join(" ")
		.replace(/\s+/g, " ")
		.trim();
	if (!text) {
		return "";
	}
	const fragments = text
		.split(/[。．！？!?、，,\n]/)
		.map((item) => item.trim())
		.filter((item) => item.length >= 6);
	const candidates = (fragments.length ? fragments : [text]).map((item) => item.replace(/\s+/g, ""));
	const best = candidates
		.filter((item) => item.length >= 6)
		.sort((left, right) => Math.abs(left.length - 16) - Math.abs(right.length - 16))[0];
	return (best || candidates[0] || "").slice(0, 24);
}

function glossaryTermsFromCaptions(captions: SubtitleCaption[]) {
	const counts = new Map<string, number>();
	const stopWords = new Set(["the", "and", "for", "with", "this", "that", "you", "your", "from"]);
	const addTerm = (term: string) => {
		const normalized = term.trim().replace(/^[-_]+|[-_]+$/g, "");
		if (normalized.length < 2 || stopWords.has(normalized.toLowerCase())) {
			return;
		}
		counts.set(normalized, (counts.get(normalized) || 0) + 1);
	};
	for (const caption of captions) {
		for (const match of caption.text.matchAll(/[A-Za-z][A-Za-z0-9.+#-]{1,}/g)) {
			const term = match[0];
			if (/[A-Z0-9]/.test(term)) {
				addTerm(term);
			}
		}
		for (const match of caption.text.matchAll(/[ァ-ヴー]{4,}/g)) {
			addTerm(match[0]);
		}
	}
	return [...counts.entries()]
		.sort((a, b) => b[1] - a[1] || b[0].length - a[0].length || a[0].localeCompare(b[0]))
		.slice(0, 12)
		.map(([label]) => ({
			label,
			patterns: label,
			description: "解析された字幕から検出された候補語。説明を確認してください。",
			enabled: true,
		}));
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

function runTool(command: string, args: string[], cwd = VIDEO_EDIT_ROOT): Promise<string> {
	return new Promise((resolve, reject) => {
		const proc = spawn(command, args, {
			cwd,
			windowsHide: true,
		});
		let stdout = "";
		let stderr = "";
		proc.stdout.on("data", (chunk) => {
			stdout += chunk.toString("utf8");
		});
		proc.stderr.on("data", (chunk) => {
			stderr += chunk.toString("utf8");
		});
		proc.on("error", reject);
		proc.on("exit", (code) => {
			if (code === 0) {
				resolve(stdout);
			} else {
				reject(new Error(stderr || stdout || `${command} exited with ${code}`));
			}
		});
	});
}

async function probeMedia(filePath: string, ffprobePath: string) {
	const metadata: Record<string, any> = {};
	try {
		const raw = await runTool(ffprobePath, [
			"-v",
			"error",
			"-show_entries",
			"format=duration:format_tags=creation_time:stream=index,codec_type,codec_name,width,height,avg_frame_rate,sample_rate,channels",
			"-of",
			"json",
			filePath,
		]);
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
	const image = nativeImage.createFromPath(filePath);
	if (image.isEmpty()) {
		return {};
	}
	const size = image.getSize();
	return {
		width: size.width,
		height: size.height,
		hasVideo: false,
		hasAudio: false,
	};
}

type DirectoryPreviewEntry = {
	name: string;
	path: string;
	sourcePath?: string;
	relativePath?: string;
	kind: MediaKind | "folder";
	extension: string;
	exists?: boolean;
	missing?: boolean;
	sizeBytes: number;
	modifiedAt: string;
	fileCount?: number;
	folderCount?: number;
	mediaCount?: number;
	duration?: number;
	width?: number;
	height?: number;
	videoCodec?: string;
	audioCodec?: string;
	thumbnailDataUrl?: string;
	previewThumbnails?: string[];
};

const PREVIEWABLE_EXTENSIONS = new Set([...IMAGE_EXTENSIONS, ...VIDEO_EXTENSIONS]);

function closestExistingDirectory(targetPath: string) {
	let candidate = path.resolve(targetPath);
	if (fs.existsSync(candidate)) {
		const stat = fs.statSync(candidate);
		return stat.isDirectory() ? candidate : path.dirname(candidate);
	}
	candidate = path.dirname(candidate);
	while (!fs.existsSync(candidate)) {
		const parent = path.dirname(candidate);
		if (parent === candidate) {
			return "";
		}
		candidate = parent;
	}
	return fs.statSync(candidate).isDirectory() ? candidate : path.dirname(candidate);
}

async function previewThumbnail(filePath: string) {
	const ext = path.extname(filePath).toLowerCase();
	if (!PREVIEWABLE_EXTENSIONS.has(ext)) {
		return "";
	}
	try {
		const thumbnail = await nativeImage.createThumbnailFromPath(filePath, { width: 180, height: 102 });
		if (!thumbnail.isEmpty()) {
			return thumbnail.toDataURL();
		}
	} catch {
		// Fall back to direct image decoding below.
	}
	if (IMAGE_EXTENSIONS.has(ext)) {
		const image = nativeImage.createFromPath(filePath);
		if (!image.isEmpty()) {
			return image.resize({ width: 180, height: 102, quality: "good" }).toDataURL();
		}
	}
	return "";
}

function summarizeDirectory(directoryPath: string) {
	const summary = {
		fileCount: 0,
		folderCount: 0,
		mediaCount: 0,
		previewFiles: [] as string[],
	};
	try {
		for (const entry of fs.readdirSync(directoryPath, { withFileTypes: true })) {
			const fullPath = path.join(directoryPath, entry.name);
			if (entry.isDirectory()) {
				summary.folderCount += 1;
				continue;
			}
			if (!entry.isFile()) {
				continue;
			}
			summary.fileCount += 1;
			const ext = path.extname(entry.name).toLowerCase();
			if (PREVIEWABLE_EXTENSIONS.has(ext)) {
				summary.mediaCount += 1;
				if (summary.previewFiles.length < 3) {
					summary.previewFiles.push(fullPath);
				}
			}
		}
	} catch {
		// Unreadable folders still render as folders without counts.
	}
	return summary;
}

async function describeDirectoryEntry(
	fullPath: string,
	entry: fs.Dirent,
	index: number,
): Promise<DirectoryPreviewEntry> {
	const stat = fs.statSync(fullPath);
	if (entry.isDirectory()) {
		const summary = summarizeDirectory(fullPath);
		const previewThumbnails = (
			await Promise.all(summary.previewFiles.map((previewPath) => previewThumbnail(previewPath)))
		).filter(Boolean);
		return {
			name: entry.name,
			path: fullPath,
			kind: "folder",
			extension: "",
			sizeBytes: 0,
			modifiedAt: stat.mtime.toISOString(),
			fileCount: summary.fileCount,
			folderCount: summary.folderCount,
			mediaCount: summary.mediaCount,
			previewThumbnails,
		};
	}

	const ext = path.extname(entry.name).toLowerCase();
	const kind = mediaKindForPath(fullPath);
	const metadata: Record<string, any> =
		kind === "video" || kind === "audio"
			? await probeMedia(fullPath, DEFAULT_FFPROBE_EXE)
			: kind === "image"
				? probeImage(fullPath)
				: {};
	return {
		name: entry.name,
		path: fullPath,
		kind,
		extension: ext.replace(/^\./, "").toUpperCase(),
		sizeBytes: stat.size,
		modifiedAt: stat.mtime.toISOString(),
		duration: Number(metadata.duration || 0),
		width: Number(metadata.width || 0),
		height: Number(metadata.height || 0),
		videoCodec: metadata.videoCodec || "",
		audioCodec: metadata.audioCodec || "",
		thumbnailDataUrl: index < 48 ? await previewThumbnail(fullPath) : "",
	};
}

async function describePathPreview(
	filePath: string,
	index = 0,
	thumbnailLimit = 48,
	ffprobePath = DEFAULT_FFPROBE_EXE,
): Promise<DirectoryPreviewEntry | null> {
	const resolvedPath = path.resolve(filePath);
	if (!fs.existsSync(resolvedPath)) {
		const extension = path.extname(resolvedPath);
		const kind = extension ? mediaKindForPath(resolvedPath) : "folder";
		return {
			name: path.basename(resolvedPath) || resolvedPath,
			path: resolvedPath,
			kind,
			extension: extension.replace(/^\./, "").toUpperCase(),
			exists: false,
			missing: true,
			sizeBytes: 0,
			modifiedAt: "",
		};
	}
	const stat = fs.statSync(resolvedPath);
	const name = path.basename(resolvedPath);
	if (stat.isDirectory()) {
		const summary = summarizeDirectory(resolvedPath);
		const previewThumbnails = (
			await Promise.all(summary.previewFiles.map((previewPath) => previewThumbnail(previewPath)))
		).filter(Boolean);
		return {
			name,
			path: resolvedPath,
			kind: "folder",
			extension: "",
			exists: true,
			sizeBytes: 0,
			modifiedAt: stat.mtime.toISOString(),
			fileCount: summary.fileCount,
			folderCount: summary.folderCount,
			mediaCount: summary.mediaCount,
			previewThumbnails,
		};
	}
	if (!stat.isFile()) {
		return null;
	}
	const ext = path.extname(name).toLowerCase();
	const kind = mediaKindForPath(resolvedPath);
	const metadata: Record<string, any> =
		kind === "video" || kind === "audio"
			? await probeMedia(resolvedPath, ffprobePath)
			: kind === "image"
				? probeImage(resolvedPath)
				: {};
	return {
		name,
		path: resolvedPath,
		kind,
		extension: ext.replace(/^\./, "").toUpperCase(),
		exists: true,
		sizeBytes: stat.size,
		modifiedAt: stat.mtime.toISOString(),
		duration: Number(metadata.duration || 0),
		width: Number(metadata.width || 0),
		height: Number(metadata.height || 0),
		videoCodec: metadata.videoCodec || "",
		audioCodec: metadata.audioCodec || "",
		thumbnailDataUrl: index < thumbnailLimit ? await previewThumbnail(resolvedPath) : "",
	};
}

async function describeExpandedPathPreviews(
	inputPath: string,
	startIndex = 0,
	thumbnailLimit = 48,
	ffprobePath = DEFAULT_FFPROBE_EXE,
) {
	const resolvedPath = path.resolve(inputPath);
	if (!fs.existsSync(resolvedPath)) {
		const entry = await describePathPreview(resolvedPath, startIndex, thumbnailLimit, ffprobePath);
		return entry ? [entry] : [];
	}
	const inputStat = fs.statSync(resolvedPath);
	if (!inputStat.isDirectory()) {
		const entry = await describePathPreview(resolvedPath, startIndex, thumbnailLimit, ffprobePath);
		return entry ? [entry] : [];
	}
	const files = walkFiles(resolvedPath)
		.filter((filePath) => mediaKindForPath(filePath) !== "other")
		.sort((left, right) => left.localeCompare(right));
	const entries: DirectoryPreviewEntry[] = [];
	for (const [index, filePath] of files.entries()) {
		const entry = await describePathPreview(filePath, startIndex + index, thumbnailLimit, ffprobePath);
		if (!entry) {
			continue;
		}
		entry.sourcePath = resolvedPath;
		entry.relativePath = path.relative(resolvedPath, filePath);
		entries.push(entry);
	}
	if (entries.length) {
		return entries;
	}
	const folderEntry = await describePathPreview(resolvedPath, startIndex, thumbnailLimit, ffprobePath);
	return folderEntry ? [folderEntry] : [];
}

async function listDirectoryPreview(targetPath: string, maxEntries = 80) {
	const resolvedPath = path.resolve(targetPath || OUTPUT_ROOT);
	const directoryPath = closestExistingDirectory(resolvedPath);
	if (!directoryPath) {
		return {
			ok: false,
			reason: "missing-path",
			targetPath: resolvedPath,
			path: "",
			entries: [] as DirectoryPreviewEntry[],
		};
	}
	const entries = fs
		.readdirSync(directoryPath, { withFileTypes: true })
		.filter((entry) => entry.isDirectory() || entry.isFile())
		.map((entry) => {
			const fullPath = path.join(directoryPath, entry.name);
			const stat = fs.statSync(fullPath);
			return { entry, fullPath, modifiedTime: stat.mtimeMs };
		})
		.sort((a, b) => {
			if (a.entry.isDirectory() !== b.entry.isDirectory()) {
				return a.entry.isDirectory() ? -1 : 1;
			}
			return b.modifiedTime - a.modifiedTime || a.entry.name.localeCompare(b.entry.name);
		})
		.slice(0, Math.max(1, Math.min(200, Number(maxEntries) || 80)));
	return {
		ok: true,
		targetPath: resolvedPath,
		path: directoryPath,
		entries: await Promise.all(
			entries.map(({ entry, fullPath }, index) => describeDirectoryEntry(fullPath, entry, index)),
		),
	};
}

function walkFiles(root: string) {
	const files: string[] = [];
	const visit = (dir: string) => {
		for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
			const fullPath = path.join(dir, entry.name);
			if (entry.isDirectory()) {
				visit(fullPath);
				continue;
			}
			if (entry.isFile()) {
				files.push(fullPath);
			}
		}
	};
	visit(root);
	return files;
}

async function _buildMediaManifest(sourceDirectory: string, ffprobePath: string, emit?: IngestProgressEmitter) {
	const root = path.resolve(sourceDirectory);
	emit?.({
		stage: "scan",
		current: 0,
		total: 0,
		progress: 0.02,
		message: "素材フォルダを走査しています",
		path: root,
	});
	const supported = walkFiles(root).filter((filePath) => mediaKindForPath(filePath) !== "other");
	const items: MediaItem[] = [];
	for (const [index, filePath] of supported.entries()) {
		emit?.({
			stage: "probe",
			current: index + 1,
			total: supported.length,
			progress: 0.05 + (supported.length ? (index / supported.length) * 0.55 : 0.55),
			message: "素材ファイルを解析しています",
			path: filePath,
		});
		const kind = mediaKindForPath(filePath);
		const stat = fs.statSync(filePath);
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
			sizeBytes: stat.size,
			confidence: 0,
			reason: "",
			metadata: {},
		};
		if (kind === "video" || kind === "audio") {
			item.metadata = await probeMedia(filePath, ffprobePath);
			if (kind === "video" && item.metadata.hasVideo === undefined) {
				item.metadata.hasVideo = true;
			}
			if (kind === "audio" && item.metadata.hasAudio === undefined) {
				item.metadata.hasAudio = true;
			}
		} else if (kind === "image") {
			item.metadata = probeImage(filePath);
		}
		item.thumbnailDataUrl = await previewThumbnail(filePath);
		items.push(item);
	}
	emit?.({
		stage: "classify",
		current: supported.length,
		total: supported.length,
		progress: 0.65,
		message: "カメラ・音声・画像・字幕を分類しています",
		path: root,
	});
	return classifyManifest(root, items);
}

async function enrichMediaManifestPreviews(manifest: MediaManifest) {
	for (const item of manifest.files || []) {
		if (item.thumbnailDataUrl || !item.path || !fs.existsSync(item.path)) {
			continue;
		}
		if (item.kind === "video" || item.kind === "image") {
			item.thumbnailDataUrl = await previewThumbnail(item.path);
		}
	}
	return manifest;
}

function persistMediaManifest(manifest: MediaManifest) {
	if (!manifest.manifestPath) {
		return;
	}
	fs.mkdirSync(path.dirname(manifest.manifestPath), { recursive: true });
	fs.writeFileSync(manifest.manifestPath, JSON.stringify(manifest, null, 2), "utf8");
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
	return "video";
}

function _importMediaManifest(project: ProjectInfo, manifest: MediaManifest, emit?: IngestProgressEmitter) {
	const files = manifest.files || [];
	for (const [index, item] of files.entries()) {
		emit?.({
			stage: "copy",
			current: index + 1,
			total: files.length,
			progress: 0.7 + (files.length ? (index / files.length) * 0.2 : 0.2),
			message: "プロジェクトへ素材を取り込んでいます",
			path: item.path,
		});
		if (!item.path || !path.isAbsolute(item.path) || !fs.existsSync(item.path)) {
			continue;
		}
		if (projectRelative(project, item.path)) {
			continue;
		}
		const bucket = bucketForMediaItem(item);
		const prefix = item.role && item.role !== "ignore" ? item.role : item.kind;
		const targetDir = path.join(project.sourceRoot, bucket);
		fs.mkdirSync(targetDir, { recursive: true });
		const target = uniqueTargetPath(targetDir, `${prefix}_${item.name}`);
		fs.copyFileSync(item.path, target);
		item.originalPath = item.originalPath || item.path;
		item.path = target;
	}
	rebuildManifestGroups(manifest);
	const outputManifestPath = path.join(project.outputRoot, "reports", MEDIA_MANIFEST_NAME);
	manifest.manifestPath = outputManifestPath;
	fs.mkdirSync(path.dirname(outputManifestPath), { recursive: true });
	const serialized = JSON.stringify(manifest, null, 2);
	fs.writeFileSync(outputManifestPath, serialized, "utf8");
	emit?.({
		stage: "manifest",
		current: files.length,
		total: files.length,
		progress: 0.94,
		message: "media_manifest.json を保存しました",
		path: outputManifestPath,
	});
	return manifest;
}

function copyProjectAssets(project: ProjectInfo, files: Record<string, string>) {
	const copied: Record<string, string> = {};
	for (const [slot, item] of Object.entries(files || {})) {
		const sources = Array.isArray(item) ? item : [item];
		const copiedItems: string[] = [];
		for (const [index, source] of sources.entries()) {
			if (!source || !path.isAbsolute(source) || !fs.existsSync(source)) {
				continue;
			}
			const relative = path.relative(project.sourceRoot, source);
			if (relative && !relative.startsWith("..") && !path.isAbsolute(relative)) {
				copiedItems.push(source);
				continue;
			}
			const bucket = sourceBucketForSlot(slot, source);
			const ext = path.extname(source) || "";
			const basename = path.basename(source, ext).replace(/[^a-zA-Z0-9._-]+/g, "_");
			const prefix = slot === "stillImages" ? `${slot}_${String(index + 1).padStart(2, "0")}` : slot;
			const target = path.join(project.sourceRoot, bucket, `${prefix}_${basename}${ext}`);
			fs.mkdirSync(path.dirname(target), { recursive: true });
			fs.copyFileSync(source, target);
			copiedItems.push(target);
		}
		if (Array.isArray(item)) {
			copied[slot] = copiedItems as any;
		} else if (copiedItems[0]) {
			copied[slot] = copiedItems[0];
		}
	}
	return copied;
}

function outputRootFromConfig(appConfig: any) {
	const configured = appConfig?.project?.outputRoot;
	return configured ? path.resolve(String(configured)) : OUTPUT_ROOT;
}

function pythonExecutableFor(appConfig: any) {
	const configured = appConfig?.tools?.python;
	return typeof configured === "string" && configured.trim() ? configured.trim() : PYTHON_EXE;
}

function runtimeConfigPathFor(appConfig: any) {
	return path.join(outputRootFromConfig(appConfig), "app", "video_edit_app_config.runtime.json");
}

function writeRuntimeMediaManifest(appConfig: any) {
	const manifest = appConfig?.assets?.mediaManifest;
	const manifestPath = appConfig?.assets?.mediaManifestPath || manifest?.manifestPath;
	if (!manifest || !manifestPath) {
		return;
	}
	const resolved = path.resolve(String(manifestPath));
	fs.mkdirSync(path.dirname(resolved), { recursive: true });
	fs.writeFileSync(resolved, JSON.stringify({ ...manifest, manifestPath: resolved }, null, 2), "utf8");
}

function writeRuntimeAppConfig(appConfig: any) {
	const configPath = runtimeConfigPathFor(appConfig);
	fs.mkdirSync(path.dirname(configPath), { recursive: true });
	writeRuntimeMediaManifest(appConfig);
	fs.writeFileSync(configPath, JSON.stringify(appConfig, null, 2), "utf8");
	return configPath;
}

function stripAnalysisSuffix(value: string) {
	return value
		.replace(/_person_edit_plan$/i, "")
		.replace(/_person_bboxes$/i, "")
		.toLowerCase();
}

function planMatchKeys(plan: Record<string, any>, planPath: string) {
	const keys = new Set<string>();
	const addValue = (value: unknown) => {
		if (!value) {
			return;
		}
		const text = String(value);
		keys.add(text.toLowerCase());
		const parsed = path.parse(text);
		if (parsed.base) {
			keys.add(parsed.base.toLowerCase());
		}
		if (parsed.name) {
			keys.add(parsed.name.toLowerCase());
			keys.add(stripAnalysisSuffix(parsed.name));
		}
		if (path.isAbsolute(text)) {
			keys.add(path.resolve(text).toLowerCase());
		}
	};
	addValue(planPath);
	addValue(plan.video_path);
	addValue(plan.video);
	return keys;
}

function mediaItemMatchKeys(item: MediaItem) {
	const keys = new Set<string>();
	for (const value of [item.path, item.originalPath, item.relativePath, item.name]) {
		if (!value) {
			continue;
		}
		const text = String(value);
		keys.add(text.toLowerCase());
		const parsed = path.parse(text);
		if (parsed.base) {
			keys.add(parsed.base.toLowerCase());
		}
		if (parsed.name) {
			keys.add(parsed.name.toLowerCase());
			keys.add(stripAnalysisSuffix(parsed.name));
		}
		if (path.isAbsolute(text)) {
			keys.add(path.resolve(text).toLowerCase());
		}
	}
	return keys;
}

function enrichMediaManifestWithPersonAnalysis(appConfig: any) {
	const manifest = appConfig?.assets?.mediaManifest as MediaManifest | undefined;
	if (!manifest?.files?.length) {
		return null;
	}
	const planDir = path.resolve(
		String(
			appConfig?.analysis?.personEditPlansDir ||
				path.join(outputRootFromConfig(appConfig), "reports", "person_edit_plans"),
		),
	);
	if (!fs.existsSync(planDir)) {
		return null;
	}
	const planPaths = fs
		.readdirSync(planDir)
		.filter((name) => name.endsWith("_person_edit_plan.json"))
		.map((name) => path.join(planDir, name));
	let matched = 0;
	for (const planPath of planPaths) {
		const plan = readJsonFile(planPath);
		if (!plan || typeof plan !== "object") {
			continue;
		}
		const planKeys = planMatchKeys(plan, planPath);
		const item = manifest.files.find((candidate) => {
			if (candidate.kind !== "video") {
				return false;
			}
			const itemKeys = mediaItemMatchKeys(candidate);
			return [...itemKeys].some((key) => planKeys.has(key));
		});
		if (!item) {
			continue;
		}
		const metadata = item.metadata || {};
		const cameraMotion = plan.camera_motion || plan.summary?.camera_motion || null;
		item.metadata = {
			...metadata,
			cameraMotionType: plan.camera_motion_type || cameraMotion?.camera_motion_type || "",
			isFixedCamera:
				typeof plan.is_fixed_camera === "boolean"
					? plan.is_fixed_camera
					: typeof cameraMotion?.is_fixed_camera === "boolean"
						? cameraMotion.is_fixed_camera
						: null,
			fixedCameraFaceDirection: plan.fixed_camera_face_direction || "",
			personAnalysisPlanPath: planPath,
			personAnalysis: {
				cameraMotion,
				cameraMotionType: plan.camera_motion_type || cameraMotion?.camera_motion_type || "",
				isFixedCamera:
					typeof plan.is_fixed_camera === "boolean"
						? plan.is_fixed_camera
						: typeof cameraMotion?.is_fixed_camera === "boolean"
							? cameraMotion.is_fixed_camera
							: null,
				fixedCameraFaceDirection: plan.fixed_camera_face_direction || "",
				faceDirectionCounts: plan.summary?.face_direction_counts || {},
				updatedAt: new Date().toISOString(),
			},
		};
		matched += 1;
	}
	if (!matched) {
		return null;
	}
	rebuildManifestGroups(manifest);
	writeRuntimeMediaManifest(appConfig);
	return manifest;
}

function numericConfig(value: unknown, fallback: number) {
	const number = Number(value);
	return Number.isFinite(number) && number > 0 ? number : fallback;
}

function secondsFromFfmpegTimestamp(value: string) {
	const match = value.match(/(\d{1,2}):(\d{2}):(\d{2}(?:\.\d+)?)/);
	if (!match) {
		return null;
	}
	return Number(match[1]) * 3600 + Number(match[2]) * 60 + Number(match[3]);
}

function lastFfmpegTimeSeconds(text: string) {
	const matches = [...text.matchAll(/time=\s*(\d{1,2}:\d{2}:\d{2}(?:\.\d+)?)/g)];
	if (!matches.length) {
		return null;
	}
	return secondsFromFfmpegTimestamp(matches[matches.length - 1][1]);
}

function workflowProgressFromText(
	action: string,
	text: string,
	appConfig: any,
	currentProgress: number,
): WorkflowProgress | null {
	if (action !== "render-selected") {
		return null;
	}
	const targetSeconds = numericConfig(appConfig?.render?.previewDuration, 60);
	const renderedSeconds = lastFfmpegTimeSeconds(text);
	if (renderedSeconds !== null) {
		const ratio = Math.max(0, Math.min(1, renderedSeconds / targetSeconds));
		return {
			action,
			stage: "render",
			progress: Math.max(currentProgress, Math.min(0.94, 0.08 + ratio * 0.84)),
			message: `レンダー中 ${Math.min(Math.round(renderedSeconds), Math.round(targetSeconds))}/${Math.round(targetSeconds)}秒`,
			text,
		};
	}
	if (/silence|無音|shorten/i.test(text)) {
		return {
			action,
			stage: "postprocess",
			progress: Math.max(currentProgress, 0.94),
			message: "無音詰めを処理しています",
			text,
		};
	}
	if (/"output"\s*:/.test(text)) {
		return {
			action,
			stage: "finalize",
			progress: Math.max(currentProgress, 0.98),
			message: "出力ファイルを書き出しました",
			text,
		};
	}
	return null;
}

function existingInputPaths(directory: unknown, paths: unknown) {
	const raw = [...(Array.isArray(paths) ? paths : []), ...(directory ? [directory] : [])]
		.map((item) => path.resolve(String(item)))
		.filter((item) => fs.existsSync(item));
	return [...new Set(raw.map((item) => path.normalize(item)))];
}

function inputRootForPath(inputPath: string) {
	const resolved = path.resolve(inputPath);
	if (!fs.existsSync(resolved)) {
		return path.dirname(resolved);
	}
	return fs.statSync(resolved).isDirectory() ? resolved : path.dirname(resolved);
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

function sourceRootForInputs(inputPaths: string[]) {
	return commonParent(inputPaths.map(inputRootForPath)) || inputRootForPath(inputPaths[0]);
}

function runIngestWorker(payload: Record<string, any>, emit: IngestProgressEmitter) {
	if (activeIngestWorker) {
		return Promise.reject(new Error("素材解析はすでに実行中です。"));
	}
	return new Promise<any>((resolve, reject) => {
		const workerPath = path.join(__dirname, "ingest-worker.js");
		const worker = new Worker(workerPath, {
			workerData: payload,
		});
		activeIngestWorker = worker;
		let settled = false;
		const cleanup = () => {
			if (activeIngestWorker === worker) {
				activeIngestWorker = null;
			}
		};
		worker.on("message", (message: any) => {
			if (message?.type === "progress") {
				emit(message.payload);
				return;
			}
			if (message?.type === "result") {
				settled = true;
				cleanup();
				resolve(message.payload);
				return;
			}
			if (message?.type === "error") {
				settled = true;
				cleanup();
				reject(new Error(message.message || "素材解析に失敗しました。"));
			}
		});
		worker.on("error", (error) => {
			if (!settled) {
				settled = true;
				cleanup();
				reject(error);
			}
		});
		worker.on("exit", (code) => {
			if (!settled) {
				settled = true;
				const wasCanceled = activeIngestWorker !== worker && activeIngestWorker === null;
				cleanup();
				reject(
					new Error(
						wasCanceled
							? "素材解析をキャンセルしました。"
							: code === 0
								? "素材解析が完了前に終了しました。"
								: `素材解析 worker exited with ${code}`,
					),
				);
			}
		});
	});
}

const ALLOWED_PYTHON_SCRIPTS = new Set([
	"analyze_person_bboxes.py",
	"analyze_person_edit_metadata.py",
	"analyze_multicam_blocking.py",
	"build_reference_edit_profile.py",
	"apply_subtitle_corrections.py",
	"auto_sync_app_sources.py",
	"build_person_edit_plan.py",
	"classify_subtitle_speakers.py",
	"compare_manifest_transcripts.py",
	"generate_full_transcript_png_overlays.py",
	"generate_glossary_term_overlays.py",
	"generate_music_bed.py",
	"generate_omission_card.py",
	"generate_project_thumbnail.py",
	"generate_thumbnail_candidates.py",
	"generate_punchline_png_overlays.py",
	"replace_video_audio.py",
	"render_app_interview.py",
	"review_subtitles.py",
	"shorten_silences.py",
	"transcribe_manifest_sources.py",
	"video_edit_run.py",
]);

const ALLOWED_WORKFLOW_ACTIONS = new Set([
	"generate-punchlines",
	"generate-full-overlays",
	"generate-glossary-overlays",
	"generate-music-bed",
	"generate-thumbnail",
	"generate-thumbnail-candidates",
	"replace-audio",
	"review-subtitles",
	"apply-subtitle-corrections",
	"classify-subtitle-speakers",
	"compare-transcripts",
	"analyze-blocking",
	"auto-sync-dropped",
	"transcribe-dropped",
	"render-selected",
	"analyze-person-edit-metadata",
	"analyze-reference-video",
	"shorten-input",
	"extract-still",
	"verify-duration",
	"verify-audio",
]);

function executableName(value: string) {
	return path.basename(value).toLowerCase();
}

function isAllowedScriptPath(value: string) {
	const scriptName = path.basename(value);
	if (!ALLOWED_PYTHON_SCRIPTS.has(scriptName)) {
		return false;
	}
	if (!path.isAbsolute(value)) {
		return true;
	}
	const relative = path.relative(SCRIPTS_ROOT, path.resolve(value));
	return Boolean(relative) && !relative.startsWith("..") && !path.isAbsolute(relative);
}

function isPythonExecutable(value: string) {
	return /^(python(\d+(\.\d+)?)?|py)(\.exe)?$/.test(executableName(value));
}

function isFfmpegCommand(command: string[]) {
	return executableName(command[0]) === "ffmpeg.exe" || executableName(command[0]) === "ffmpeg";
}

function isFfprobeCommand(command: string[]) {
	return executableName(command[0]) === "ffprobe.exe" || executableName(command[0]) === "ffprobe";
}

function isAllowedDirectCommand(command: string[]) {
	if (command.length < 1) {
		return false;
	}
	if (isPythonExecutable(command[0])) {
		return command.length >= 2 && isAllowedScriptPath(command[1]);
	}
	if (isFfmpegCommand(command)) {
		return command.includes("-frames:v") && command.includes("1") && command.includes("-update");
	}
	if (isFfprobeCommand(command)) {
		return (
			command.includes("-show_entries") &&
			(command.includes("format=duration") || command.includes("stream=codec_name,sample_rate,channels"))
		);
	}
	return false;
}

function isAllowedCommand(command: unknown[]) {
	if (!command.every((arg) => typeof arg === "string")) {
		return false;
	}
	const argv = command as string[];
	if (isAllowedDirectCommand(argv)) {
		return true;
	}
	return false;
}

function runLocalPythonScript(
	scriptName: string,
	appConfig: unknown = null,
): Promise<{ stdout: string; stderr: string }> {
	if (!ALLOWED_PYTHON_SCRIPTS.has(scriptName)) {
		return Promise.reject(new Error(`script is not allowlisted: ${scriptName}`));
	}
	const appConfigPath = appConfig ? writeRuntimeAppConfig(appConfig) : "";
	const pythonExe = pythonExecutableFor(appConfig);
	return new Promise((resolve, reject) => {
		const proc = spawn(pythonExe, [path.join(SCRIPTS_ROOT, scriptName)], {
			cwd: VIDEO_EDIT_ROOT,
			env: { ...process.env, PYTHONUTF8: "1", ...(appConfigPath ? { VIDEO_EDIT_APP_CONFIG: appConfigPath } : {}) },
			windowsHide: true,
		});
		let stdout = "";
		let stderr = "";
		proc.stdout.on("data", (chunk) => {
			stdout += chunk.toString("utf8");
		});
		proc.stderr.on("data", (chunk) => {
			stderr += chunk.toString("utf8");
		});
		proc.on("error", reject);
		proc.on("exit", (code) => {
			if (code === 0) {
				resolve({ stdout, stderr });
			} else {
				reject(new Error(`${scriptName} exited with ${code}: ${stderr || stdout}`));
			}
		});
	});
}

function runAllowedPythonScript(
	scriptName: string,
	args: string[] = [],
	appConfig: unknown = null,
	timeoutMs = 6 * 60 * 60 * 1000,
	options: { action?: string; onProgress?: WorkflowProgressEmitter } = {},
): Promise<{ stdout: string; stderr: string; exitCode: number | null; canceled?: boolean }> {
	if (!ALLOWED_PYTHON_SCRIPTS.has(scriptName)) {
		return Promise.reject(new Error(`script is not allowlisted: ${scriptName}`));
	}
	if (!args.every((arg) => typeof arg === "string")) {
		return Promise.reject(new Error("script arguments must be strings"));
	}
	if (options.action && activeWorkflowProcess) {
		return Promise.reject(new Error("別の解析がすでに実行中です。"));
	}
	const appConfigPath = appConfig ? writeRuntimeAppConfig(appConfig) : "";
	const pythonExe = pythonExecutableFor(appConfig);
	return new Promise((resolve, reject) => {
		const action = options.action || "";
		let bestProgress = 0;
		const emitProgress = (payload: WorkflowProgress) => {
			bestProgress = Math.max(bestProgress, Number(payload.progress) || 0);
			options.onProgress?.({ ...payload, progress: bestProgress });
		};
		if (action) {
			emitProgress({
				action,
				stage: "start",
				progress: 0.02,
				message: action === "render-selected" ? "レンダーを開始しています" : "処理を開始しています",
			});
		}
		const proc = spawn(pythonExe, [path.join(SCRIPTS_ROOT, scriptName), ...args], {
			cwd: VIDEO_EDIT_ROOT,
			env: { ...process.env, PYTHONUTF8: "1", ...(appConfigPath ? { VIDEO_EDIT_APP_CONFIG: appConfigPath } : {}) },
			windowsHide: true,
		});
		if (action) {
			activeWorkflowProcess = { proc, action, cancelRequested: false };
		}
		const clearActiveWorkflowProcess = () => {
			if (activeWorkflowProcess?.proc === proc) {
				activeWorkflowProcess = null;
			}
		};
		let stdout = "";
		let stderr = "";
		let settled = false;
		const handleChunk = (stream: "stdout" | "stderr", chunk: Buffer) => {
			const text = chunk.toString("utf8");
			if (stream === "stdout") {
				stdout += text;
			} else {
				stderr += text;
			}
			if (!action) {
				return;
			}
			const parsed = workflowProgressFromText(action, text, appConfig, bestProgress);
			if (parsed) {
				emitProgress(parsed);
			} else if (bestProgress < 0.08) {
				emitProgress({
					action,
					stage: stream,
					progress: 0.05,
					message: action === "render-selected" ? "レンダー準備中です" : "処理中です",
					text,
				});
			}
		};
		const timer = setTimeout(() => {
			if (settled) {
				return;
			}
			settled = true;
			void terminateProcessTree(proc);
			clearActiveWorkflowProcess();
			if (action) {
				emitProgress({
					action,
					stage: "timeout",
					progress: bestProgress,
					message: "実行がタイムアウトしました",
				});
			}
			resolve({ stdout, stderr: stderr || `${scriptName} timed out`, exitCode: 124 });
		}, timeoutMs);
		proc.stdout.on("data", (chunk) => {
			handleChunk("stdout", chunk);
		});
		proc.stderr.on("data", (chunk) => {
			handleChunk("stderr", chunk);
		});
		proc.on("error", (error) => {
			if (settled) {
				return;
			}
			settled = true;
			clearTimeout(timer);
			clearActiveWorkflowProcess();
			reject(error);
		});
		proc.on("exit", (code) => {
			if (settled) {
				return;
			}
			settled = true;
			clearTimeout(timer);
			const canceled = activeWorkflowProcess?.proc === proc && activeWorkflowProcess.cancelRequested;
			clearActiveWorkflowProcess();
			if (action) {
				emitProgress({
					action,
					stage: canceled ? "canceled" : code === 0 ? "complete" : "error",
					progress: canceled ? bestProgress : code === 0 ? 1 : bestProgress,
					message: canceled
						? "解析をキャンセルしました"
						: code === 0
							? "処理が完了しました"
							: "処理でエラーが発生しました",
				});
			}
			resolve({ stdout, stderr, exitCode: canceled ? 130 : code, canceled });
		});
	});
}

type SendEvent = (channel: string, payload: unknown) => void;
type PendingRequest = {
	resolve: (value: unknown) => void;
	reject: (error: Error) => void;
	method: string;
};

class CodexAppServer {
	private sendEvent: SendEvent;
	private proc: ChildProcessWithoutNullStreams | null;
	private rl: readline.Interface | null;
	private nextId: number;
	private pending: Map<number, PendingRequest>;
	private threadId: string | null;

	constructor(sendEvent: SendEvent) {
		this.sendEvent = sendEvent;
		this.proc = null;
		this.rl = null;
		this.nextId = 1;
		this.pending = new Map();
		this.threadId = null;
	}

	async ensureStarted() {
		if (this.proc && !this.proc.killed) {
			return;
		}

		const command = resolveCodexExecutable();
		const args = ["app-server"];
		this.proc = spawn(command, args, {
			cwd: VIDEO_EDIT_ROOT,
			env: { ...process.env, PYTHONUTF8: "1" },
			stdio: ["pipe", "pipe", "pipe"],
			windowsHide: true,
		});

		this.proc.on("error", (error) => {
			this.sendEvent("server:error", { message: error.message });
			this.rejectAll(error);
		});

		this.proc.on("exit", (code, signal) => {
			this.sendEvent("server:exit", { code, signal });
			this.rejectAll(new Error(`codex app-server exited (${code ?? signal})`));
			this.proc = null;
			this.rl = null;
			this.threadId = null;
		});

		this.proc.stderr.on("data", (chunk) => {
			const text = chunk.toString("utf8").trim();
			if (text) {
				this.sendEvent("server:stderr", { text });
			}
		});

		this.rl = readline.createInterface({ input: this.proc.stdout });
		this.rl.on("line", (line) => this.handleLine(line));

		await this.request("initialize", {
			clientInfo: {
				name: "video_edit_electron",
				title: "Video Edit",
				version: "0.1.0",
			},
			capabilities: {
				experimentalApi: true,
			},
		});
		this.notify("initialized", {});
		this.sendEvent("server:ready", {});
	}

	async startTurn(settings: Record<string, any>, prompt: string) {
		await this.ensureStarted();
		if (!this.threadId) {
			const threadParams: Record<string, any> = {
				cwd: VIDEO_EDIT_ROOT,
				approvalPolicy: "never",
				sandbox: "danger-full-access",
				serviceName: "video_edit_electron",
			};
			if (settings.model) {
				threadParams.model = settings.model;
			}
			const response = await this.request("thread/start", threadParams);
			this.threadId = response?.thread?.id;
			if (!this.threadId) {
				throw new Error("app-server did not return a thread id");
			}
		}

		const turnParams: Record<string, any> = {
			threadId: this.threadId,
			cwd: VIDEO_EDIT_ROOT,
			approvalPolicy: "never",
			sandboxPolicy: {
				type: "dangerFullAccess",
			},
			input: [{ type: "text", text: prompt }],
		};
		if (settings.model) {
			turnParams.model = settings.model;
		}
		if (settings.effort) {
			turnParams.effort = settings.effort;
		}
		return this.request("turn/start", turnParams);
	}

	async listModels(options: Record<string, any> = {}) {
		await this.ensureStarted();
		const data: any[] = [];
		let nextCursor: string | null = null;
		for (let page = 0; page < 10; page += 1) {
			const params: Record<string, any> = {
				limit: Number(options.limit) || 100,
				includeHidden: Boolean(options.includeHidden),
			};
			if (nextCursor) {
				params.cursor = nextCursor;
			}
			const response = await this.request("model/list", params);
			if (Array.isArray(response?.data)) {
				data.push(...response.data);
			}
			nextCursor = response?.nextCursor || null;
			if (!nextCursor) {
				break;
			}
		}
		return { data, nextCursor };
	}

	async execCommand(command: unknown[], timeoutMs = 60 * 60 * 1000, appConfig: unknown = null) {
		await this.ensureStarted();
		if (!Array.isArray(command) || command.length === 0) {
			throw new Error("command must be a non-empty argv array");
		}
		if (!isAllowedCommand(command)) {
			throw new Error("command is not allowed by the Video Edit preset allowlist");
		}
		if (appConfig) {
			writeRuntimeAppConfig(appConfig);
		}
		return this.request("command/exec", {
			command,
			cwd: VIDEO_EDIT_ROOT,
			sandboxPolicy: {
				type: "dangerFullAccess",
			},
			timeoutMs,
			streamStdoutStderr: true,
		});
	}

	interrupt() {
		if (!this.threadId) {
			return Promise.resolve(null);
		}
		return this.request("turn/interrupt", { threadId: this.threadId });
	}

	stop() {
		if (this.proc && !this.proc.killed) {
			this.proc.kill();
		}
	}

	request(method: string, params: unknown): Promise<any> {
		const id = this.nextId++;
		const message = { method, id, params };
		return new Promise((resolve, reject) => {
			this.pending.set(id, { resolve, reject, method });
			this.write(message);
		});
	}

	notify(method: string, params: unknown) {
		this.write({ method, params });
	}

	write(message: unknown) {
		if (!this.proc?.stdin.writable) {
			throw new Error("codex app-server is not running");
		}
		this.proc.stdin.write(`${JSON.stringify(message)}\n`);
	}

	handleLine(line: string) {
		if (!line.trim()) {
			return;
		}
		let message: any;
		try {
			message = JSON.parse(line);
		} catch (error) {
			this.sendEvent("server:parse-error", { line, message: error.message });
			return;
		}

		if (message.id !== undefined) {
			const pending = this.pending.get(message.id);
			if (!pending) {
				this.sendEvent("server:unmatched-response", message);
				return;
			}
			this.pending.delete(message.id);
			if (message.error) {
				pending.reject(new Error(message.error.message || "app-server request failed"));
			} else {
				pending.resolve(message.result);
			}
			return;
		}

		this.sendEvent("server:notification", message);
	}

	rejectAll(error: Error) {
		for (const { reject } of this.pending.values()) {
			reject(error);
		}
		this.pending.clear();
	}
}

let mainWindow = null;
let codex = null;
let activeIngestWorker: Worker | null = null;
let activeWorkflowProcess: ActiveWorkflowProcess | null = null;
let watchedProjectStatePath = "";
let projectStateWatcher: fs.FSWatcher | null = null;
let projectStateWatchTimer: NodeJS.Timeout | null = null;

function terminateProcessTree(proc: ChildProcessWithoutNullStreams) {
	if (!proc.pid) {
		proc.kill();
		return Promise.resolve();
	}
	if (process.platform !== "win32") {
		proc.kill();
		return Promise.resolve();
	}
	return new Promise<void>((resolve) => {
		const killer = spawn("taskkill", ["/pid", String(proc.pid), "/t", "/f"], { windowsHide: true });
		killer.on("error", () => {
			proc.kill();
			resolve();
		});
		killer.on("exit", () => resolve());
	});
}

function watchProjectState(project: ProjectInfo) {
	const statePath = projectStatePathForProject(project);
	if (watchedProjectStatePath === statePath && projectStateWatcher) {
		return;
	}
	if (projectStateWatcher) {
		projectStateWatcher.close();
		projectStateWatcher = null;
	}
	watchedProjectStatePath = statePath;
	try {
		fs.mkdirSync(project.root, { recursive: true });
		projectStateWatcher = fs.watch(project.root, { persistent: false }, (_eventType, filename) => {
			if (String(filename || "") !== PROJECT_STATE_NAME) {
				return;
			}
			if (projectStateWatchTimer) {
				clearTimeout(projectStateWatchTimer);
			}
			projectStateWatchTimer = setTimeout(() => {
				if (!mainWindow || mainWindow.isDestroyed()) {
					return;
				}
				const payload: any = readProjectState(project);
				mainWindow.webContents.send("project-state:changed", {
					project,
					path: statePath,
					revision: payload?.revision || 0,
					updatedAt: payload?.updatedAt || "",
				});
			}, 80);
		});
	} catch {
		projectStateWatcher = null;
	}
}

function createWindow() {
	mainWindow = new BrowserWindow({
		width: 1360,
		height: 900,
		minWidth: 1120,
		minHeight: 760,
		backgroundColor: "#f6f4ef",
		title: "Video Edit",
		icon: ICON_PATH,
		show: process.env.VIDEO_EDIT_SMOKE !== "1",
		webPreferences: {
			preload: path.join(__dirname, "preload.js"),
			contextIsolation: true,
			nodeIntegration: false,
		},
	});

	codex = new CodexAppServer((channel, payload) => {
		if (mainWindow && !mainWindow.isDestroyed()) {
			mainWindow.webContents.send(channel, payload);
		}
	});

	mainWindow.loadFile(path.join(__dirname, "renderer", "index.html"));
	if (SMOKE_QUIT_MS > 0) {
		mainWindow.webContents.once("did-finish-load", () => {
			setTimeout(() => app.quit(), SMOKE_QUIT_MS);
		});
	}
}

const singleInstanceLock = app.requestSingleInstanceLock();

if (!singleInstanceLock) {
	app.quit();
} else {
	app.on("second-instance", () => {
		if (!mainWindow || mainWindow.isDestroyed()) {
			return;
		}
		if (mainWindow.isMinimized()) {
			mainWindow.restore();
		}
		mainWindow.show();
		mainWindow.focus();
	});

	app.whenReady().then(createWindow);
}

app.on("window-all-closed", () => {
	if (codex) {
		codex.stop();
	}
	if (projectStateWatcher) {
		projectStateWatcher.close();
		projectStateWatcher = null;
	}
	if (process.platform !== "darwin") {
		app.quit();
	}
});

app.on("activate", () => {
	if (BrowserWindow.getAllWindows().length === 0) {
		createWindow();
	}
});

ipcMain.handle("environment:get", async () => {
	return {
		appRoot: APP_ROOT,
		videoEditRoot: VIDEO_EDIT_ROOT,
		projectsRoot: PROJECTS_ROOT,
		methodDoc: METHOD_DOC,
		appConfigPath: DEFAULT_APP_CONFIG_PATH,
		projectStateName: PROJECT_STATE_NAME,
		syncReportPath: SYNC_REPORT_PATH,
		methodDocExists: fs.existsSync(METHOD_DOC),
		codexAppServerDoc: path.join(VIDEO_EDIT_ROOT, "docs", "codex-app-server.md"),
		scriptsRoot: SCRIPTS_ROOT,
		appStateRoot: APP_STATE_ROOT,
		outputRoot: "",
		outputAppRoot: OUTPUT_APP_ROOT,
		pythonExe: PYTHON_EXE,
		ffmpegExe: DEFAULT_FFMPEG_EXE,
		ffprobeExe: DEFAULT_FFPROBE_EXE,
		knownOutputs: [],
	};
});

ipcMain.handle("project:create", async (_event, { name, id }) => {
	const project = projectInfo(id || name || "", name);
	ensureProjectDirs(project);
	watchProjectState(project);
	return project;
});

ipcMain.handle("project:list", async () => {
	return { projects: listProjects() };
});

ipcMain.handle("project:load", async (_event, { project } = {}) => {
	const info = projectInfoFromPayload(project);
	ensureProjectDirs(info);
	watchProjectState(info);
	return {
		project: info,
		manifest: readProjectMediaManifest(info),
	};
});

ipcMain.handle("project:pick-existing", async (_event, options: any = {}) => {
	const locale = normalizeLocale(options?.language);
	fs.mkdirSync(PROJECTS_ROOT, { recursive: true });
	const result = await dialog.showOpenDialog(mainWindow, {
		title: mt(locale, "dialog.selectProjectFolder"),
		defaultPath: PROJECTS_ROOT,
		properties: ["openDirectory"],
	});
	if (result.canceled || !result.filePaths[0]) {
		return null;
	}
	const project = projectInfoFromRoot(result.filePaths[0]);
	ensureProjectDirs(project);
	watchProjectState(project);
	return {
		project,
		manifest: readProjectMediaManifest(project),
	};
});

ipcMain.handle("project:delete", async (_event, payload: any = {}) => {
	const { project } = payload;
	const locale = normalizeLocale(payload?.language);
	const info = projectInfoFromPayload(project);
	const root = assertProjectRootInProjects(info.root);
	if (!fs.existsSync(root)) {
		return { deleted: false, missing: true, project: info };
	}
	const result = await dialog.showMessageBox(mainWindow, {
		type: "warning",
		title: mt(locale, "dialog.deleteProjectTitle"),
		message: mt(locale, "dialog.deleteProjectMessage", { name: info.name }),
		detail: mt(locale, "dialog.deleteProjectDetail", { path: root }),
		buttons: [mt(locale, "dialog.deleteProjectConfirm"), mt(locale, "dialog.cancel")],
		defaultId: 1,
		cancelId: 1,
		noLink: true,
	});
	if (result.response !== 0) {
		return { deleted: false, canceled: true, project: info };
	}
	fs.rmSync(root, { recursive: true, force: true });
	return { deleted: true, project: info };
});

ipcMain.handle("project:copy-assets", async (_event, { project, files }) => {
	if (!project?.id) {
		throw new Error("project is required");
	}
	const info = projectInfoFromPayload(project);
	ensureProjectDirs(info);
	return {
		project: info,
		files: copyProjectAssets(info, files || {}),
	};
});

ipcMain.handle("analysis-state:load", async (_event, { project } = {}) => {
	const info = projectInfoFromPayload(project);
	ensureProjectDirs(info);
	return readProjectAnalysisState(info);
});

ipcMain.handle("analysis-state:save", async (_event, { project, state } = {}) => {
	const info = projectInfoFromPayload(project);
	ensureProjectDirs(info);
	return writeProjectAnalysisState(info, state || {});
});

ipcMain.handle("analysis:material-status", async (_event, { appConfig } = {}) => {
	return materialAnalysisStatuses(appConfig || {});
});

ipcMain.handle("media-manifest:save", async (_event, { project, manifest } = {}) => {
	const info = projectInfoFromPayload(project);
	ensureProjectDirs(info);
	if (!manifest || !Array.isArray(manifest.files)) {
		throw new Error("media manifest is required");
	}
	const manifestPath = String(manifest.manifestPath || path.join(info.outputRoot, "reports", MEDIA_MANIFEST_NAME));
	const normalized: MediaManifest = {
		...manifest,
		sourceDirectory: String(manifest.sourceDirectory || info.sourceRoot),
		sourcePaths: Array.isArray(manifest.sourcePaths) ? manifest.sourcePaths.map(String) : [],
		generatedAt: String(manifest.generatedAt || new Date().toISOString()),
		manifestPath,
		files: manifest.files,
		cameras: Array.isArray(manifest.cameras) ? manifest.cameras : [],
		audio: Array.isArray(manifest.audio) ? manifest.audio : [],
		images: Array.isArray(manifest.images) ? manifest.images : [],
		subtitles: Array.isArray(manifest.subtitles) ? manifest.subtitles : [],
		other: Array.isArray(manifest.other) ? manifest.other : [],
		selected: manifest.selected || {},
	};
	rebuildManifestGroups(normalized);
	fs.mkdirSync(path.dirname(manifestPath), { recursive: true });
	fs.writeFileSync(manifestPath, JSON.stringify(normalized, null, 2), "utf8");
	return normalized;
});

ipcMain.handle("project-state:load", async (_event, { project } = {}) => {
	const info = projectInfoFromPayload(project);
	ensureProjectDirs(info);
	watchProjectState(info);
	return readProjectState(info);
});

ipcMain.handle("project-state:save", async (_event, { project, state, baseRevision } = {}) => {
	const info = projectInfoFromPayload(project);
	ensureProjectDirs(info);
	watchProjectState(info);
	return writeProjectState(info, state || {}, { baseRevision });
});

ipcMain.handle("project-state:patch", async (_event, { project, operations, baseRevision } = {}) => {
	const info = projectInfoFromPayload(project);
	ensureProjectDirs(info);
	watchProjectState(info);
	return patchProjectState(info, operations || [], baseRevision);
});

ipcMain.handle("project:ingest-directory", async (_event, { project, directory, paths, tools } = {}) => {
	const sourcePaths = existingInputPaths(directory, paths);
	if (!sourcePaths.length) {
		throw new Error("A material folder or file is required.");
	}
	const sourceDirectory = sourceRootForInputs(sourcePaths);
	const info = project?.id
		? projectInfoFromPayload(project)
		: projectInfo(
				path.basename(sourcePaths.length === 1 ? sourcePaths[0] : sourceDirectory),
				path.basename(sourceDirectory),
			);
	ensureProjectDirs(info);
	watchProjectState(info);
	const ffprobePath = String(tools?.ffprobe || DEFAULT_FFPROBE_EXE);
	const emit = (payload: IngestProgress) => {
		_event.sender.send("project:ingest-progress", payload);
	};
	const importedManifest = await runIngestWorker(
		{
			sourceDirectory,
			sourcePaths,
			project: info,
			ffprobePath,
			mediaManifestName: MEDIA_MANIFEST_NAME,
		},
		emit,
	);
	await enrichMediaManifestPreviews(importedManifest);
	persistMediaManifest(importedManifest);
	return {
		project: info,
		manifest: importedManifest,
		files: importedManifest.selected,
	};
});

ipcMain.handle("project:ingest-cancel", async () => {
	let canceled = false;
	if (activeIngestWorker) {
		const worker = activeIngestWorker;
		activeIngestWorker = null;
		await worker.terminate();
		canceled = true;
	}
	if (activeWorkflowProcess) {
		const workflow = activeWorkflowProcess;
		workflow.cancelRequested = true;
		await terminateProcessTree(workflow.proc);
		canceled = true;
	}
	if (mainWindow && !mainWindow.isDestroyed()) {
		mainWindow.webContents.send("project:ingest-progress", {
			stage: "canceled",
			current: 0,
			total: 0,
			progress: 0,
			message: "解析をキャンセルしました",
		});
	}
	return { canceled };
});

ipcMain.handle("dialog:pick-file", async (_event, options = {}) => {
	const properties: ("openFile" | "multiSelections")[] = options.multi ? ["openFile", "multiSelections"] : ["openFile"];
	const result = await dialog.showOpenDialog(mainWindow, {
		title: options.title || "Select file",
		properties,
		filters: options.filters || [{ name: "All files", extensions: ["*"] }],
	});
	if (result.canceled) {
		return null;
	}
	return options.multi ? result.filePaths : result.filePaths[0];
});

ipcMain.handle("dialog:pick-directory", async (_event, options = {}) => {
	const result = await dialog.showOpenDialog(mainWindow, {
		title: options.title || "Select folder",
		properties: ["openDirectory"],
	});
	if (result.canceled) {
		return null;
	}
	return result.filePaths[0];
});

ipcMain.handle("dialog:pick-output", async (_event, options) => {
	const suggestedName = typeof options === "string" ? options : options?.suggestedName;
	const outputRoot = typeof options === "object" && options?.outputRoot ? options.outputRoot : OUTPUT_ROOT;
	const locale = normalizeLocale(typeof options === "object" ? options?.language : null);
	const result = await dialog.showSaveDialog(mainWindow, {
		title: typeof options === "object" && options?.title ? options.title : mt(locale, "dialog.selectOutputVideo"),
		defaultPath: path.join(outputRoot, "videos", suggestedName || "codex_edit_output.mp4"),
		filters: [
			{
				name: typeof options === "object" && options?.filterName ? options.filterName : mt(locale, "filter.mp4Video"),
				extensions: ["mp4"],
			},
		],
	});
	if (result.canceled) {
		return null;
	}
	return result.filePath;
});

ipcMain.handle("codex:start-turn", async (_event, { settings, prompt }) => {
	return codex.startTurn(settings || {}, prompt);
});

ipcMain.handle("codex:list-models", async (_event, options = {}) => {
	return codex.listModels(options || {});
});

ipcMain.handle("codex:exec-command", async (_event, { command, timeoutMs, appConfig }) => {
	return codex.execCommand(command, timeoutMs, appConfig);
});

ipcMain.handle("workflow:run-action", async (event, { action, appConfig, timeoutMs } = {}) => {
	const resolvedAction = String(action || "");
	if (!ALLOWED_WORKFLOW_ACTIONS.has(resolvedAction)) {
		throw new Error(`workflow action is not allowlisted: ${resolvedAction}`);
	}
	const result = await runAllowedPythonScript(
		"video_edit_run.py",
		["--action", resolvedAction],
		appConfig || null,
		Number(timeoutMs) || undefined,
		{
			action: resolvedAction,
			onProgress: (payload) => {
				if (!event.sender.isDestroyed()) {
					event.sender.send("workflow:progress", payload);
				}
			},
		},
	);
	const updatedManifest =
		resolvedAction === "analyze-person-edit-metadata" && result.exitCode === 0
			? enrichMediaManifestWithPersonAnalysis(appConfig || null)
			: null;
	return updatedManifest ? { ...result, manifest: updatedManifest } : result;
});

ipcMain.handle("codex:interrupt", async () => {
	return codex.interrupt();
});

ipcMain.handle("report:sync", async (_event, appConfig) => {
	const syncReportPath = path.join(outputRootFromConfig(appConfig), "reports", "app_sync_offsets.json");
	if (!fs.existsSync(syncReportPath)) {
		return null;
	}
	return JSON.parse(fs.readFileSync(syncReportPath, "utf8"));
});

ipcMain.handle("glossary:load-candidates", async (_event, appConfig) => {
	await runLocalPythonScript("generate_glossary_term_overlays.py", appConfig || null);
	const manifestPath = path.join(
		outputRootFromConfig(appConfig),
		"overlays",
		"glossary_term_overlays",
		"manifest.json",
	);
	if (!fs.existsSync(manifestPath)) {
		return [];
	}
	return JSON.parse(fs.readFileSync(manifestPath, "utf8"));
});

ipcMain.handle("text-overlay:load-candidates", async (_event, { manifest, appConfig } = {}) => {
	const { path: subtitlePath, captions } = loadSubtitleCaptions(
		manifest || appConfig?.assets?.mediaManifest,
		appConfig || {},
	);
	return {
		subtitlePath,
		captionCount: captions.length,
		titleText: titleTextFromCaptions(captions),
		punchlineText: punchlineTextFromCaptions(captions),
		glossaryTerms: glossaryTermsFromCaptions(captions),
	};
});

ipcMain.handle("directory:list", async (_event, { targetPath, maxEntries } = {}) => {
	return listDirectoryPreview(targetPath || OUTPUT_ROOT, maxEntries);
});

ipcMain.handle(
	"media:describe-paths",
	async (_event, { paths, expandDirectories, thumbnailLimit, tools, ffprobe } = {}) => {
		const selectedPaths = Array.isArray(paths) ? paths.map(String).filter(Boolean) : [];
		const ffprobePath = String(ffprobe || tools?.ffprobe || DEFAULT_FFPROBE_EXE);
		if (expandDirectories) {
			const entries: DirectoryPreviewEntry[] = [];
			const limit = Math.max(0, Math.min(1000, Number(thumbnailLimit) || 48));
			for (const filePath of selectedPaths) {
				entries.push(...(await describeExpandedPathPreviews(filePath, entries.length, limit, ffprobePath)));
			}
			return entries;
		}
		const limit = Math.max(0, Math.min(1000, Number(thumbnailLimit) || 48));
		const entries = await Promise.all(
			selectedPaths.map((filePath, index) => describePathPreview(filePath, index, limit, ffprobePath)),
		);
		return entries.filter(Boolean);
	},
);

ipcMain.handle("shell:show-path", async (_event, targetPath) => {
	if (typeof targetPath !== "string" || !targetPath.trim()) {
		return { ok: false, reason: "empty-path" };
	}
	const resolvedPath = path.resolve(targetPath);
	if (fs.existsSync(resolvedPath)) {
		shell.showItemInFolder(resolvedPath);
		return { ok: true, mode: "show-item", path: resolvedPath };
	}

	let fallbackPath = path.dirname(resolvedPath);
	while (!fs.existsSync(fallbackPath)) {
		const parent = path.dirname(fallbackPath);
		if (parent === fallbackPath) {
			return { ok: false, reason: "missing-path", path: resolvedPath };
		}
		fallbackPath = parent;
	}
	const error = await shell.openPath(fallbackPath);
	if (error) {
		throw new Error(error);
	}
	return { ok: true, mode: "open-parent", path: fallbackPath, missingPath: resolvedPath };
});
