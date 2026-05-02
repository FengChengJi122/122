/**
 * Electron Main Process
 *
 * Creates a frameless, always-on-top desktop overlay window that hosts the
 * cyberpunk companion UI.  The window is transparent so NPCs appear to "live"
 * on the user's desktop.
 */

const { app, BrowserWindow, ipcMain, screen } = require("electron");
const path = require("path");

let mainWindow = null;

function createWindow() {
  const { width, height } = screen.getPrimaryDisplay().workAreaSize;

  mainWindow = new BrowserWindow({
    width,
    height,
    x: 0,
    y: 0,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    skipTaskbar: false,
    resizable: false,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, "preload.js"),
    },
  });

  mainWindow.loadFile(path.join(__dirname, "renderer", "index.html"));

  // Allow clicking through transparent areas.
  mainWindow.setIgnoreMouseEvents(false);

  mainWindow.on("closed", () => {
    mainWindow = null;
  });

  // Open DevTools in dev mode.
  if (process.argv.includes("--dev")) {
    mainWindow.webContents.openDevTools({ mode: "detach" });
  }
}

// -----------------------------------------------------------------------
// IPC: allow renderer to toggle click-through for desktop passthrough
// -----------------------------------------------------------------------
ipcMain.on("set-ignore-mouse-events", (_event, ignore, options) => {
  if (mainWindow) {
    mainWindow.setIgnoreMouseEvents(ignore, options || { forward: true });
  }
});

ipcMain.on("quit-app", () => {
  app.quit();
});

// -----------------------------------------------------------------------
// App lifecycle
// -----------------------------------------------------------------------
app.whenReady().then(() => {
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
