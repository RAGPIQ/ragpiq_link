const { contextBridge, ipcRenderer, shell } = require('electron');

contextBridge.exposeInMainWorld('ragpiqBridge', {
  exitApp: () => ipcRenderer.send('app-exit'),
  openExternal: (url) => ipcRenderer.send('open-external', url),
  startWatcher: (cameraId) => ipcRenderer.invoke('start-watcher', cameraId),
  stopWatcher: () => ipcRenderer.invoke('stop-watcher'),
  startPrinter: () => ipcRenderer.invoke('start-printer-watcher'),
  stopPrinter: () => ipcRenderer.invoke('stop-printer-watcher'),

  printLabel: async (labelDataArray) => {
    for (const label of labelDataArray) {
      await ipcRenderer.invoke('print-label', label);
    }
  },

  onWatcherLog: (callback) => {
    ipcRenderer.on('watcher-log', (_event, args) => callback(args));
  },

  onLabelLog: (callback) => {
    ipcRenderer.on('label-log', (_event, args) => callback(args));
  },

  onPrinterStatus: (callback) => {
    ipcRenderer.on('printer-status', (_event, args) => callback(args));
  }
});
