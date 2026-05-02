/**
 * Electron Preload Script
 *
 * Exposes a safe, minimal API to the renderer process via contextBridge.
 * The renderer uses window.electronAPI.* to communicate with the main process.
 */

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("electronAPI", {
  setIgnoreMouseEvents: (ignore, options) =>
    ipcRenderer.send("set-ignore-mouse-events", ignore, options),
  quit: () => ipcRenderer.send("quit-app"),
});
