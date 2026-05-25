const { contextBridge, ipcRenderer, webUtils } = require("electron");

const on = (channel, callback) => {
  const listener = (_event, payload) => callback(payload);
  ipcRenderer.on(channel, listener);
  return () => ipcRenderer.removeListener(channel, listener);
};

contextBridge.exposeInMainWorld("editApp", {
  getEnvironment: () => ipcRenderer.invoke("environment:get"),
  pickFile: (options) => ipcRenderer.invoke("dialog:pick-file", options),
  pickDirectory: (options) => ipcRenderer.invoke("dialog:pick-directory", options),
  pickOutput: (suggestedName) => ipcRenderer.invoke("dialog:pick-output", suggestedName),
  startCodexTurn: (payload) => ipcRenderer.invoke("codex:start-turn", payload),
  execCodexCommand: (payload) => ipcRenderer.invoke("codex:exec-command", payload),
  interruptCodex: () => ipcRenderer.invoke("codex:interrupt"),
  getSyncReport: () => ipcRenderer.invoke("report:sync"),
  showPath: (targetPath) => ipcRenderer.invoke("shell:show-path", targetPath),
  filePath: (file) => webUtils.getPathForFile(file),
  onServerReady: (callback) => on("server:ready", callback),
  onServerError: (callback) => on("server:error", callback),
  onServerExit: (callback) => on("server:exit", callback),
  onServerStderr: (callback) => on("server:stderr", callback),
  onServerNotification: (callback) => on("server:notification", callback),
});
