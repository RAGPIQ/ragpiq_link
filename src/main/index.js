const { app, BrowserWindow, ipcMain, shell } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const https = require('https');
const http = require('http');
const { URL } = require('url');

let win;
let splash;
let watcherProcess = null;
let printerWatcherProcess = null;
let storedCameraId = null;
let isQuitting = false;

icon: path.join(__dirname, '..', '..', 'resources', 'icon.ico')

// 🔗 Send camera ID to server on app exit
function sendCameraIdToServer(cameraId) {
  if (!cameraId) return;

  const url = new URL('https://n8n2.ragpiq.com/6315c648-8d7e-4273-8c8b-669164a2fce3');
  url.searchParams.append('camera_id', cameraId);

  const lib = url.protocol === 'https:' ? https : http;
  const req = lib.get(url.toString(), (res) => {
    console.log(`📡 Camera ID sent. Status: ${res.statusCode}`);
  });

  req.on('error', (err) => {
    console.error("❌ Failed to send camera ID:", err);
  });

  req.end();
}

function createWindow() {
  // Create splash screen window
  const splash = new BrowserWindow({
    width: 500,
    height: 300,
    frame: false,
    alwaysOnTop: true,
    transparent: false,
    resizable: false,
    backgroundColor: '#000000',
    show: true
  });

  splash.loadFile(path.join(__dirname, '..', 'ui', 'splash.html'));

  // Create main app window (initially hidden)
  win = new BrowserWindow({
    width: 1200,
    height: 800,
    frame: false, // hides native controls
    titleBarStyle: 'hidden',
    icon: path.join(__dirname, '..', '..', 'resources', 'icon.ico'),
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      preload: path.join(__dirname, '..', 'preload.js'),
      sandbox: false
    },
    backgroundColor: '#121212',
    show: false
  });

  win.loadURL('https://ragpiq.com/version-test/ragpiq_link_desktop');

  // Wait for the main window to finish loading, then show it
  win.webContents.once('did-finish-load', () => {
    setTimeout(() => {
      splash.close();
      win.show();
    }, 1000); // you can tweak the delay
  });
}

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('will-quit', (event) => {
  if (isQuitting) return;

  if (printerWatcherProcess && storedCameraId) {
    console.log("🛑 App closing, printer watcher running — sending camera ID...");

    event.preventDefault();
    isQuitting = true;

    const url = new URL('https://n8n2.ragpiq.com/6315c648-8d7e-4273-8c8b-669164a2fce3');
    url.searchParams.append('camera_id', storedCameraId);

    const lib = url.protocol === 'https:' ? https : http;
    const req = lib.get(url.toString(), (res) => {
      console.log(`📡 Camera ID sent. Status: ${res.statusCode}`);
      app.quit();
    });

    req.on('error', (err) => {
      console.error("❌ Failed to send camera ID:", err);
      app.quit();
    });

    req.end();
  } else {
    console.log("ℹ️ Skipping camera ID webhook (either printer watcher not running or camera ID not set)");
  }
});

ipcMain.on('app-exit', () => {
  app.quit();
});

ipcMain.on('open-external', (event, url) => {
  shell.openExternal(url);
});

// 📸 Start camera image watcher
ipcMain.handle('start-watcher', async (event, cameraId) => {
  storedCameraId = cameraId;
  if (watcherProcess) {
    console.log("⚠️ Watcher already running.");
    return 'already running';
  }

  const watcherPath = path.join(__dirname, '..', 'scripts', 'watcher.py');
  watcherProcess = spawn('python', [watcherPath, cameraId]);

  watcherProcess.stdout.on('data', (data) => {
    const msg = data.toString().trim();
    console.log(`[WATCHER] ${msg}`);

    if (msg.startsWith('[WATCHER_SUCCESS]')) {
      win.webContents.send('watcher-log', {
        type: 'success',
        message: msg.replace('[WATCHER_SUCCESS]', '').trim()
      });
    } else if (msg.startsWith('[WATCHER_ERROR]')) {
      win.webContents.send('watcher-log', {
        type: 'error',
        message: msg.replace('[WATCHER_ERROR]', '').trim()
      });
    }
  });

  watcherProcess.stderr.on('data', (data) => {
    console.error(`[WATCHER ERROR] ${data}`);
  });

  watcherProcess.on('close', (code) => {
    console.log(`[WATCHER EXIT] Code ${code}`);
    watcherProcess = null;
  });

  return 'started';
});

ipcMain.handle('stop-watcher', async () => {
  if (watcherProcess) {
    console.log("🛑 Stopping watcher...");
    watcherProcess.kill();
    watcherProcess = null;
    return 'stopped';
  } else {
    console.log("⚠️ No watcher running to stop.");
    return 'not running';
  }
});

// 🖨️ Start continuous printer watcher
ipcMain.handle('start-printer-watcher', async () => {
  if (printerWatcherProcess) {
    console.log("⚠️ Printer watcher already running.");
    return 'already running';
  }

  const detectPrinterPath = path.join(__dirname, '..', 'scripts', 'detect_printer.py');
  printerWatcherProcess = spawn('python', [detectPrinterPath]);

  printerWatcherProcess.stdout.on('data', (data) => {
    try {
      const msg = data.toString().trim();
      console.log(`[PRINTER WATCHER] ${msg}`);
      const parsed = JSON.parse(msg);

      win.webContents.send('printer-status', {
        printer_name: parsed.printer_name || "",
        setup_required: parsed.setup_required,
      });
    } catch (err) {
      console.error("❌ Failed to parse printer update:", data.toString());
    }
  });

  printerWatcherProcess.stderr.on('data', (data) => {
    console.error(`[PRINTER WATCHER ERROR] ${data}`);
  });

  printerWatcherProcess.on('close', (code) => {
    console.log(`[PRINTER WATCHER EXIT] Code ${code}`);
    printerWatcherProcess = null;
  });

  return 'started';
});

ipcMain.handle('stop-printer-watcher', async () => {
  if (printerWatcherProcess) {
    console.log("🛑 Stopping printer watcher...");
    printerWatcherProcess.kill();
    printerWatcherProcess = null;
    return 'stopped';
  } else {
    console.log("⚠️ No printer watcher running.");
    return 'not running';
  }
});

// 🏷️ Label printer
ipcMain.handle('print-label', async (event, label) => {
  return new Promise((resolve) => {
    const labelPrintPath = path.join(__dirname, '..', 'scripts', 'label_print.py');
    const python = spawn('python', [labelPrintPath, label.qr, label.barcode, label.created]);

    let stdoutBuffer = '';
    let stderrBuffer = '';

    python.stdout.on('data', (data) => {
      stdoutBuffer += data.toString();
    });

    python.stderr.on('data', (data) => {
      stderrBuffer += data.toString();
    });

    python.on('close', (code) => {
      if (code === 0) {
        win.webContents.send('label-log', {
          type: 'success',
          message: stdoutBuffer.trim()
        });
      } else {
        let errorMessage = "Failed to print label.";
        if (stderrBuffer.includes("Device not found")) {
          errorMessage = "Label printer not connected.";
        }

        win.webContents.send('label-log', {
          type: 'error',
          message: errorMessage
        });
      }

      resolve();
    });
  });
});