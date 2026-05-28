import { contextBridge, ipcRenderer, webUtils } from "electron";

const on = (channel, callback) => {
	const listener = (_event, payload) => callback(payload);
	ipcRenderer.on(channel, listener);
	return () => ipcRenderer.removeListener(channel, listener);
};

contextBridge.exposeInMainWorld("editApp", {
	getEnvironment: () => ipcRenderer.invoke("environment:get"),
	createProject: (payload) => ipcRenderer.invoke("project:create", payload),
	pickProject: () => ipcRenderer.invoke("project:pick-existing"),
	deleteProject: (payload) => ipcRenderer.invoke("project:delete", payload),
	copyProjectAssets: (payload) => ipcRenderer.invoke("project:copy-assets", payload),
	ingestDirectory: (payload) => ipcRenderer.invoke("project:ingest-directory", payload),
	cancelIngest: () => ipcRenderer.invoke("project:ingest-cancel"),
	pickFile: (options) => ipcRenderer.invoke("dialog:pick-file", options),
	pickDirectory: (options) => ipcRenderer.invoke("dialog:pick-directory", options),
	pickOutput: (options) => ipcRenderer.invoke("dialog:pick-output", options),
	startCodexTurn: (payload) => ipcRenderer.invoke("codex:start-turn", payload),
	listCodexModels: (options) => ipcRenderer.invoke("codex:list-models", options),
	execCodexCommand: (payload) => ipcRenderer.invoke("codex:exec-command", payload),
	runWorkflowAction: (payload) => ipcRenderer.invoke("workflow:run-action", payload),
	interruptCodex: () => ipcRenderer.invoke("codex:interrupt"),
	loadAnalysisState: (payload) => ipcRenderer.invoke("analysis-state:load", payload),
	saveAnalysisState: (payload) => ipcRenderer.invoke("analysis-state:save", payload),
	getSyncReport: (appConfig) => ipcRenderer.invoke("report:sync", appConfig),
	loadGlossaryCandidates: (appConfig) => ipcRenderer.invoke("glossary:load-candidates", appConfig),
	loadTextOverlayCandidates: (payload) => ipcRenderer.invoke("text-overlay:load-candidates", payload),
	listDirectory: (payload) => ipcRenderer.invoke("directory:list", payload),
	describeMediaPaths: (payload) => ipcRenderer.invoke("media:describe-paths", payload),
	showPath: (targetPath) => ipcRenderer.invoke("shell:show-path", targetPath),
	filePath: (file) => webUtils.getPathForFile(file),
	onServerReady: (callback) => on("server:ready", callback),
	onServerError: (callback) => on("server:error", callback),
	onServerExit: (callback) => on("server:exit", callback),
	onServerStderr: (callback) => on("server:stderr", callback),
	onServerNotification: (callback) => on("server:notification", callback),
	onIngestProgress: (callback) => on("project:ingest-progress", callback),
	onWorkflowProgress: (callback) => on("workflow:progress", callback),
});
