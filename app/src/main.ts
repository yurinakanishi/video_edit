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
	const starts = [__dirname, process.cwd(), path.dirname(process.execPath)];
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
const OUTPUT_THUMBNAILS_ROOT = path.join(OUTPUT_ROOT, "thumbnails");
const SCRIPTS_ROOT = path.join(VIDEO_EDIT_ROOT, "scripts");
const OUTPUT_APP_ROOT = path.join(OUTPUT_ROOT, "app");
const APP_CONFIG_PATH = path.join(OUTPUT_APP_ROOT, "video_edit_app_config.runtime.json");
const ICON_PATH = path.join(APP_ROOT, "build", "icon.ico");
const SYNC_REPORT_PATH = path.join(OUTPUT_ROOT, "reports", "app_sync_offsets.json");
const PYTHON_EXE = path.join(
	process.env.LOCALAPPDATA || "C:\\Users\\yurin\\AppData\\Local",
	"Python",
	"pythoncore-3.14-64",
	"python.exe",
);

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
			streamStdoutStderr: false,
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
		methodDoc: METHOD_DOC,
		appConfigPath: APP_CONFIG_PATH,
		syncReportPath: SYNC_REPORT_PATH,
		methodDocExists: fs.existsSync(METHOD_DOC),
		codexAppServerDoc: path.join(VIDEO_EDIT_ROOT, "docs", "codex-app-server.md"),
		scriptsRoot: SCRIPTS_ROOT,
		outputRoot: OUTPUT_ROOT,
		outputThumbnailsRoot: OUTPUT_THUMBNAILS_ROOT,
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

ipcMain.handle("dialog:pick-output", async (_event, suggestedName) => {
	const result = await dialog.showSaveDialog(mainWindow, {
		title: "Select output video",
		defaultPath: path.join(OUTPUT_ROOT, "videos", suggestedName || "codex_edit_output.mp4"),
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

ipcMain.handle("report:sync", async () => {
	if (!fs.existsSync(SYNC_REPORT_PATH)) {
		return null;
	}
	return JSON.parse(fs.readFileSync(SYNC_REPORT_PATH, "utf8"));
});

ipcMain.handle("shell:show-path", async (_event, targetPath) => {
	if (!targetPath) {
		return;
	}
	await shell.showItemInFolder(targetPath);
});
