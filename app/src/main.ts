import { type ChildProcessWithoutNullStreams, spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import readline from "node:readline";
import { app, BrowserWindow, dialog, ipcMain, shell } from "electron";

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
const OUTPUT_ROOT = path.join(VIDEO_EDIT_ROOT, "output");
const PROJECTS_ROOT = path.join(VIDEO_EDIT_ROOT, "projects");
const OUTPUT_THUMBNAILS_ROOT = path.join(OUTPUT_ROOT, "thumbnails");
const SCRIPTS_ROOT = path.join(VIDEO_EDIT_ROOT, "scripts");
const OUTPUT_APP_ROOT = path.join(OUTPUT_ROOT, "app");
const APP_CONFIG_PATH = path.join(OUTPUT_APP_ROOT, "video_edit_app_config.runtime.json");
const RESOURCE_ICON_PATH = path.join(process.resourcesPath || "", "build", "icon.ico");
const ICON_PATH = fs.existsSync(RESOURCE_ICON_PATH) ? RESOURCE_ICON_PATH : path.join(APP_ROOT, "build", "icon.ico");
const SYNC_REPORT_PATH = path.join(OUTPUT_ROOT, "reports", "app_sync_offsets.json");
const PYTHON_EXE = path.join(
	process.env.LOCALAPPDATA || "C:\\Users\\yurin\\AppData\\Local",
	"Python",
	"pythoncore-3.14-64",
	"python.exe",
);

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
	"source/text",
	"source/thumbnail",
	"output/videos",
	"output/overlays",
	"output/reports",
	"output/transcripts",
	"output/audio",
	"output/diagnostics",
	"output/thumbnails",
	"output/app",
];

const SHARED_SOURCE_SUBDIRS = ["images", "subtitles", "text"];

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
	for (const subdir of SHARED_SOURCE_SUBDIRS) {
		const source = path.join(VIDEO_EDIT_ROOT, "source", subdir);
		const target = path.join(project.sourceRoot, subdir);
		const targetIsEmpty = !fs.existsSync(target) || fs.readdirSync(target).length === 0;
		if (fs.existsSync(source) && targetIsEmpty) {
			fs.cpSync(source, target, { recursive: true });
		}
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

function sourceBucketForSlot(slot: string, filePath: string) {
	const ext = path.extname(filePath).toLowerCase();
	if (slot === "externalAudio" || [".wav", ".mp3", ".aac", ".m4a"].includes(ext)) {
		return "audio";
	}
	if (slot === "logo" || [".png", ".jpg", ".jpeg", ".webp"].includes(ext)) {
		return "images";
	}
	if ([".srt", ".ass", ".vtt"].includes(ext)) {
		return "subtitles";
	}
	return "video";
}

function copyProjectAssets(project: ProjectInfo, files: Record<string, string>) {
	const copied: Record<string, string> = {};
	for (const [slot, source] of Object.entries(files || {})) {
		if (!source || !path.isAbsolute(source) || !fs.existsSync(source)) {
			continue;
		}
		const relative = path.relative(project.sourceRoot, source);
		if (relative && !relative.startsWith("..") && !path.isAbsolute(relative)) {
			copied[slot] = source;
			continue;
		}
		const bucket = sourceBucketForSlot(slot, source);
		const ext = path.extname(source) || "";
		const basename = path.basename(source, ext).replace(/[^a-zA-Z0-9._-]+/g, "_");
		const target = path.join(project.sourceRoot, bucket, `${slot}_${basename}${ext}`);
		fs.mkdirSync(path.dirname(target), { recursive: true });
		fs.copyFileSync(source, target);
		copied[slot] = target;
	}
	return copied;
}

function outputRootFromConfig(appConfig: any) {
	const configured = appConfig?.project?.outputRoot;
	return configured ? path.resolve(String(configured)) : OUTPUT_ROOT;
}
const ALLOWED_PYTHON_SCRIPTS = new Set([
	"analyze_multicam_blocking.py",
	"auto_sync_app_sources.py",
	"build_st7_7550_strong_transcript_multicam.py",
	"compare_sound2_transcripts.py",
	"generate_full_transcript_png_overlays.py",
	"generate_glossary_term_overlays.py",
	"generate_punchline_png_overlays.py",
	"generate_thumbnail_candidates.py",
	"refine_sound2_audio_offset.py",
	"refine_st7_7550_strong_wave_offsets.py",
	"render_1min_color_matched.py",
	"render_1min_onepass_ffmpeg.py",
	"render_app_interview.py",
	"render_final_png_overlays.py",
	"replace_audio_with_sound2.py",
	"shorten_silences.py",
	"subtitle_review_cycle.py",
	"transcribe_align_st7_7550_multicam.py",
	"transcribe_compare_all_st7_7550_multicam.py",
	"transcribe_sound2.py",
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
	if (appConfig) {
		fs.mkdirSync(path.dirname(APP_CONFIG_PATH), { recursive: true });
		fs.writeFileSync(APP_CONFIG_PATH, JSON.stringify(appConfig, null, 2), "utf8");
	}
	return new Promise((resolve, reject) => {
		const proc = spawn(PYTHON_EXE, [path.join(SCRIPTS_ROOT, scriptName)], {
			cwd: VIDEO_EDIT_ROOT,
			env: { ...process.env, PYTHONUTF8: "1", VIDEO_EDIT_APP_CONFIG: APP_CONFIG_PATH },
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

		const command = process.platform === "win32" ? "cmd.exe" : "codex";
		const args = process.platform === "win32" ? ["/d", "/s", "/c", "codex app-server"] : ["app-server"];
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
				sandbox: "workspaceWrite",
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
				type: "workspaceWrite",
				writableRoots: [VIDEO_EDIT_ROOT],
				networkAccess: true,
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

	async execCommand(command: unknown[], timeoutMs = 60 * 60 * 1000, appConfig: unknown = null) {
		await this.ensureStarted();
		if (!Array.isArray(command) || command.length === 0) {
			throw new Error("command must be a non-empty argv array");
		}
		if (!isAllowedCommand(command)) {
			throw new Error("command is not allowed by the Video Edit preset allowlist");
		}
		if (appConfig) {
			fs.mkdirSync(path.dirname(APP_CONFIG_PATH), { recursive: true });
			fs.writeFileSync(APP_CONFIG_PATH, JSON.stringify(appConfig, null, 2), "utf8");
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

function createWindow() {
	mainWindow = new BrowserWindow({
		width: 1360,
		height: 900,
		minWidth: 1120,
		minHeight: 760,
		backgroundColor: "#f6f4ef",
		title: "Video Edit",
		icon: ICON_PATH,
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
}

app.whenReady().then(createWindow);

app.on("window-all-closed", () => {
	if (codex) {
		codex.stop();
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
		appConfigPath: APP_CONFIG_PATH,
		syncReportPath: SYNC_REPORT_PATH,
		methodDocExists: fs.existsSync(METHOD_DOC),
		codexAppServerDoc: path.join(VIDEO_EDIT_ROOT, "docs", "codex-app-server.md"),
		scriptsRoot: SCRIPTS_ROOT,
		outputRoot: OUTPUT_ROOT,
		outputThumbnailsRoot: OUTPUT_THUMBNAILS_ROOT,
		thumbnailSourceRoot: path.join(VIDEO_EDIT_ROOT, "source", "thumbnail", "etype260515_p_takei"),
		thumbnailContactSheet: path.join(OUTPUT_THUMBNAILS_ROOT, "thumbnail_standard_candidates_contact_sheet.jpg"),
		outputAppRoot: OUTPUT_APP_ROOT,
		pythonExe: PYTHON_EXE,
		knownOutputs: [
			"ST7_7550_multicam_cut_1min_onepass_full_transcript.mp4",
			"ST7_7550_multicam_cut_1min_onepass_punchline.mp4",
			"ST7_7550_multicam_cut_5min_png_titles_punchlines.mp4",
			"ST7_7550_multicam_cut_5min_png_titles_full_transcript.mp4",
		].map((name) => path.join(OUTPUT_ROOT, "videos", name)),
	};
});

ipcMain.handle("project:create", async (_event, { name, id }) => {
	const project = projectInfo(id || name || "", name);
	ensureProjectDirs(project);
	return project;
});

ipcMain.handle("project:copy-assets", async (_event, { project, files }) => {
	if (!project?.id) {
		throw new Error("project is required");
	}
	const info = projectInfo(project.id, project.name);
	ensureProjectDirs(info);
	return {
		project: info,
		files: copyProjectAssets(info, files || {}),
	};
});

ipcMain.handle("dialog:pick-file", async (_event, options = {}) => {
	const result = await dialog.showOpenDialog(mainWindow, {
		title: options.title || "Select file",
		properties: ["openFile"],
		filters: options.filters || [{ name: "All files", extensions: ["*"] }],
	});
	if (result.canceled) {
		return null;
	}
	return result.filePaths[0];
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
	const result = await dialog.showSaveDialog(mainWindow, {
		title: "Select output video",
		defaultPath: path.join(outputRoot, "videos", suggestedName || "codex_edit_output.mp4"),
		filters: [{ name: "MP4 video", extensions: ["mp4"] }],
	});
	if (result.canceled) {
		return null;
	}
	return result.filePath;
});

ipcMain.handle("codex:start-turn", async (_event, { settings, prompt }) => {
	return codex.startTurn(settings || {}, prompt);
});

ipcMain.handle("codex:exec-command", async (_event, { command, timeoutMs, appConfig }) => {
	return codex.execCommand(command, timeoutMs, appConfig);
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

ipcMain.handle("shell:show-path", async (_event, targetPath) => {
	if (!targetPath) {
		return;
	}
	await shell.showItemInFolder(targetPath);
});
