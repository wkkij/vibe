const { contextBridge, ipcRenderer, webUtils } = require('electron');

const CHANNELS = new Set(['proc-out', 'proc-exit', 'log', 'vibe-event']);

contextBridge.exposeInMainWorld('vibe', {
  status: (project) => ipcRenderer.invoke('status', project),
  launchChrome: (provider, project) => ipcRenderer.invoke('launch-chrome', provider, project),
  sessionStart: (opts) => ipcRenderer.invoke('session-start', opts),
  sessionSend: (text) => ipcRenderer.invoke('session-send', text),
  sessionStop: () => ipcRenderer.invoke('session-stop'),
  generationStop: () => ipcRenderer.invoke('generation-stop'),
  listModels: (opts) => ipcRenderer.invoke('list-models', opts),
  pickFiles: () => ipcRenderer.invoke('pick-files'),
  saveTemp: (name, bytes) => ipcRenderer.invoke('save-temp', name, bytes),
  pathForFile: (f) => { try { return webUtils.getPathForFile(f); } catch (_) { return ''; } },
  modelsCacheGet: () => ipcRenderer.invoke('models-cache-get'),
  modelsCacheSet: (d) => ipcRenderer.invoke('models-cache-set', d),
  runScript: (p) => ipcRenderer.invoke('run-script', p),
  openExternal: (url) => ipcRenderer.invoke('open-external', url),
  setTheme: (t) => ipcRenderer.invoke('set-theme', t),
  pickFolder: (title) => ipcRenderer.invoke('pick-folder', title),
  pickVibeRoot: () => ipcRenderer.invoke('pick-vibe-root'),
  listDir: (root, rel) => ipcRenderer.invoke('list-dir', root, rel),
  preview: (root) => ipcRenderer.invoke('preview', root),
  ignoreGet: (project) => ipcRenderer.invoke('ignore-get', project),
  ignoreSet: (project, patterns) => ipcRenderer.invoke('ignore-set', project, patterns),
  revealIgnore: (project) => ipcRenderer.invoke('reveal-ignore', project),
  on: (channel, fn) => {
    if (!CHANNELS.has(channel)) return () => {};
    const handler = (_e, payload) => fn(payload);
    ipcRenderer.on(channel, handler);
    return () => ipcRenderer.removeListener(channel, handler);
  }
});
