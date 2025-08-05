// 🔍 async_hooks logger for SIGTRAP debugging
const async_hooks = require('async_hooks');
const fs = require('fs');

const logFile = fs.openSync('async-debug.log', 'w');

const hook = async_hooks.createHook({
  init(asyncId, type, triggerAsyncId) {
    fs.writeSync(logFile, `INIT ${asyncId} ${type} triggered by ${triggerAsyncId}\n`);
  },
  before(asyncId) {
    fs.writeSync(logFile, `BEFORE ${asyncId}\n`);
  },
  after(asyncId) {
    fs.writeSync(logFile, `AFTER ${asyncId}\n`);
  },
  destroy(asyncId) {
    fs.writeSync(logFile, `DESTROY ${asyncId}\n`);
  }
});

hook.enable();

const { app, BrowserWindow, ipcMain, shell } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const https = require('https');
const http = require('http');
const { URL } = require('url');
const isMac = process.platform === 'darwin';
const isWin = process.platform === 'win32';

if (isMac) {
  app.commandLine.appendSwitch('js-flags', '--max-old-space-size=4096');
}

let win;
let splash;
let printerWatcherProcess = null;
let storedCameraId = null;
let isQuitting = false;


const getPythonPath = () => {
  if (isMac) {
    return isDev
      ? path.join(__dirname, '..', '..', 'portable-python', 'mac', 'Library', 'Frameworks', '3.13', 'bin', 'python3')
      : path.join(process.resourcesPath, 'python', 'mac', 'Library', 'Frameworks', '3.13', 'bin', 'python3');
  }

  if (isWin) {
    return isDev
      ? path.join(__dirname, '..', '..', 'portable-python', 'win', 'python.exe')
      : path.join(process.resourcesPath, 'python', 'win', 'python.exe');
  }

  return 'python3';
};

// 🎯 Determine correct script path based on env
const isDev = !app.isPackaged;
const getScriptPath = (scriptName) => {
  return isDev
    ? path.join(__dirname, '..', 'scripts', scriptName)
    : path.join(process.resourcesPath, 'app.asar.unpacked', 'src', 'scripts', scriptName);
};

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
  splash = new BrowserWindow({
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

  win = new BrowserWindow({
    width: 1200,
    height: 800,
    resizable: false,
    frame: false,
    titleBarStyle: 'hidden',
    icon: process.platform === 'darwin'
      ? path.join(__dirname, '..', '..', 'resources', 'iconMac.icns')
      : path.join(__dirname, '..', '..', 'resources', 'icon.ico'),
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      preload: path.join(__dirname, '..', 'preload.js'),
      sandbox: false
    },
    backgroundColor: '#121212',
    show: false
  });

  win.loadURL('https://ragpiq.com/ragpiq_link_desktop');

  win.webContents.once('did-finish-load', () => {
    setTimeout(() => {
      splash.close();
      win.show();
    }, 1000);
  });

  // Handle close event for macOS to quit app
  win.on('close', () => {
    app.quit();
    app.exit(); // Quit the app when the window is closed
  });
}

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('will-quit', (event) => {
  if (isQuitting) return;

  event.preventDefault();
  isQuitting = true;

  // Stop printer watcher
  if (printerWatcherProcess) {
    console.log("🛑 Terminating printer watcher...");
    printerWatcherProcess.kill();
    printerWatcherProcess.on('close', () => {
      printerWatcherProcess = null;
      console.log("✅ Printer watcher closed cleanly.");
      
      // Send camera ID before quitting
      if (storedCameraId) {
        console.log("📡 Sending camera ID before quit...");

        const url = new URL('https://n8n2.ragpiq.com/6315c648-8d7e-4273-8c8b-669164a2fce3');
        url.searchParams.append('camera_id', storedCameraId);

        const lib = url.protocol === 'https:' ? https : http;
        const req = lib.get(url.toString(), (res) => {
          console.log(`✅ Camera ID sent. Status: ${res.statusCode}`);
          app.quit(); // Safe to call now
        });

        req.on('error', (err) => {
          console.error("❌ Failed to send camera ID:", err);
          app.quit(); // Still proceed to quit
        });

        req.end();
      } else {
        console.log("ℹ️ No camera ID set, quitting immediately.");
        app.quit();
      }
    });
  } else {
    // No printer watcher, quit immediately
    // Send camera ID before quitting
    if (storedCameraId) {
      console.log("📡 Sending camera ID before quit...");

      const url = new URL('https://n8n2.ragpiq.com/6315c648-8d7e-4273-8c8b-669164a2fce3');
      url.searchParams.append('camera_id', storedCameraId);

      const lib = url.protocol === 'https:' ? https : http;
      const req = lib.get(url.toString(), (res) => {
        console.log(`✅ Camera ID sent. Status: ${res.statusCode}`);
        app.quit(); // Safe to call now
      });

      req.on('error', (err) => {
        console.error("❌ Failed to send camera ID:", err);
        app.quit(); // Still proceed to quit
      });

      req.end();
    } else {
      console.log("ℹ️ No camera ID set, quitting immediately.");
      app.quit();
    }
  }
});

ipcMain.on('app-exit', () => {
  console.log("🛑 Exiting application...");

  // Terminate the printer watcher before quitting
  if (printerWatcherProcess) {
    console.log("🛑 Terminating printer watcher...");
    printerWatcherProcess.kill();
    printerWatcherProcess.on('close', () => {
      printerWatcherProcess = null;
      console.log("✅ Printer watcher closed cleanly.");
      app.quit();  // After cleanup, quit the app
      app.exit();  // Forcefully exit the app
    });
  } else {
    // No printer watcher, quit immediately
    app.quit();
    app.exit();  // Forcefully exit the app
  }
});

ipcMain.on('open-external', (event, url) => {
  shell.openExternal(url);
});

// 🖨️ Start continuous printer watcher
ipcMain.handle('start-printer-watcher', async () => {
  if (printerWatcherProcess) {
    console.log("⚠️ Printer watcher already running.");
    return 'already running';
  }

  const detectPrinterPath = getScriptPath('detect_printer.py');
  console.log("🧩 Starting printer watcher from path:", detectPrinterPath);

  printerWatcherProcess = spawn(getPythonPath(), [detectPrinterPath], {
  env: {
    ...process.env,
    ...(isMac && !isDev ? {
      DYLD_LIBRARY_PATH: path.join(process.resourcesPath)
    } : {})
  }
});


  printerWatcherProcess.on('error', (err) => {
    console.error("❌ Spawn error (printer watcher):", err);
  });

  printerWatcherProcess.stdout.on('data', (data) => {
  try {
    const msg = data.toString().trim();
    console.log(`[PRINTER WATCHER] ${msg}`);
    const parsed = JSON.parse(msg);

    if (win && !win.isDestroyed()) {
      win.webContents.send('printer-status', {
        printer_name: parsed.printer_name || "",
        setup_required: parsed.setup_required,
      });
    }
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
    const labelPrintPath = getScriptPath('label_print.py');
    console.log("🏷️ Printing label via:", labelPrintPath);

    const python = spawn(getPythonPath(), [labelPrintPath, label.qr, label.barcode, label.created], {
  env: {
    ...process.env,
    ...(isMac && !isDev ? {
      DYLD_LIBRARY_PATH: path.join(process.resourcesPath)
    } : {})
  }
});


    python.on('error', (err) => {
      console.error("❌ Spawn error (label print):", err);
    });

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
    if (win && !win.isDestroyed()) {
      win.webContents.send('label-log', {
        type: 'success',
        message: stdoutBuffer.trim()
      });
    }
  } else {
    let errorMessage = "Failed to print label.";
    if (stderrBuffer.includes("Device not found")) {
      errorMessage = "Label printer not connected.";
    }

    if (win && !win.isDestroyed()) {
      win.webContents.send('label-log', {
        type: 'error',
        message: errorMessage
      });
    }
  }

  resolve();
});
  });
});