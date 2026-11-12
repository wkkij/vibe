const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron');
const os = require('os');
const fs = require('fs');
const path = require('path');
const http = require('http');
const { spawn, execFile } = require('child_process');

/* ---------------- язык интерфейса (ru / en) ----------------
   Строки в коде русские и служат ключами; английский — в renderer/locale-en.js (его же грузит окно).
   Язык присылает окно при старте (set-lang) и вместе с запуском сессии. */
const EN = require('./renderer/locale-en.js');
let LANG = /^ru/i.test(app.getLocale() || '') ? 'ru' : 'en';
const tr = (s) => (LANG === 'en' && Object.prototype.hasOwnProperty.call(EN, s) ? EN[s] : s);
const cliLang = () => ({ VIBE_LANG: LANG });

const OUT_NAME = '.vibe_context_bundle.txt';
const SKIP_NAMES = new Set([OUT_NAME, '.vibe_backups', '.vibe_last_screenshot.png']);
const MAX_LIST = 3000;
const MAX_FILE_KB = 250;
const MARK_BEGIN = '# >>> vibe-ide managed block (edit in Vibe IDE)';
const MARK_END = '# <<< vibe-ide managed block';

// Копия DEFAULT_IGNORE_PATTERNS из core/config.py (для оценки контекста и пометок в дереве)
const BUILTIN = [
  '.git/', '.svn/', '.hg/', 'node_modules/', 'venv/', '.venv/', 'env/', '__pycache__/',
  '*.pyc', '*.pyo', '*.pyd', '.DS_Store', 'dist/', 'build/', '.next/', '.nuxt/', 'target/',
  'out/', 'coverage/', '*.lock', 'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml',
  'poetry.lock', 'Cargo.lock', '*.min.js', '*.min.css', '*.map', '*.png', '*.jpg', '*.jpeg',
  '*.gif', '*.ico', '*.svg', '*.webp', '*.mp4', '*.mp3', '*.wav', '*.pdf', '*.zip', '*.tar',
  '*.gz', '*.woff', '*.woff2', '*.ttf', '*.eot'
];

let win = null;
let proc = null;
let starting = false;
let sessionSeq = 0;
let stopFile = '';
const EV_PREFIX = '@@VIBE ';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const emit = (ch, payload) => {
  if (win && !win.isDestroyed()) win.webContents.send(ch, payload);
};
const log = (level, text) => emit('log', { level, text });

/* ---------------- окно ---------------- */

function createWindow() {
  win = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1100,
    minHeight: 700,
    backgroundColor: '#0b0d12',
    title: 'Vibe IDE',
    icon: path.join(__dirname, 'build', 'icon.png'),
    autoHideMenuBar: true,
    titleBarStyle: 'hidden',
    titleBarOverlay: { color: '#0b0d12', symbolColor: '#e8eaf0', height: 44 },
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    }
  });
  win.loadFile(path.join(__dirname, 'renderer', 'index.html'));
  win.on('closed', () => { win = null; });
}

app.whenReady().then(() => {
  createWindow();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('before-quit', () => killProc());
app.on('window-all-closed', () => {
  killProc();
  app.quit();
});

/* ---------------- настройки приложения ---------------- */

function cfgFile() {
  return path.join(app.getPath('userData'), 'vibeide.json');
}
function loadCfg() {
  try { return JSON.parse(fs.readFileSync(cfgFile(), 'utf8')); } catch (_) { return {}; }
}
function saveCfg(patch) {
  const next = Object.assign(loadCfg(), patch);
  try {
    fs.mkdirSync(path.dirname(cfgFile()), { recursive: true });
    fs.writeFileSync(cfgFile(), JSON.stringify(next, null, 2), 'utf8');
  } catch (_) { /* ignore */ }
}

/* ---------------- поиск Vibe CLI ---------------- */

function isVibeRoot(d) {
  try {
    return fs.existsSync(path.join(d, 'vibe.py')) && fs.existsSync(path.join(d, 'core'));
  } catch (_) {
    return false;
  }
}

function findVibeRoot() {
  const cands = [];
  if (process.env.VIBE_ROOT) cands.push(process.env.VIBE_ROOT);
  const cfg = loadCfg();
  if (cfg.vibeRoot) cands.push(cfg.vibeRoot);
  let d = __dirname;
  for (let i = 0; i < 6; i++) {
    cands.push(d);
    const p = path.dirname(d);
    if (p === d) break;
    d = p;
  }
  cands.push(process.cwd());
  for (const c of cands) if (c && isVibeRoot(c)) return c;
  return null;
}

function pythonFor(root) {
  const winPy = path.join(root, '.venv', 'Scripts', 'python.exe');
  if (fs.existsSync(winPy)) return winPy;
  return 'python';
}

/* ---------------- Chrome ---------------- */

function cdpUrls(project, root) {
  const urls = { gemini: 'http://127.0.0.1:9222', claude: 'http://127.0.0.1:9223', aistudio: 'http://127.0.0.1:9222' };
  for (const base of [root, project]) {
    if (!base) continue;
    try {
      const j = JSON.parse(fs.readFileSync(path.join(base, '.vibe.json'), 'utf8'));
      if (j && j.cdp_urls) Object.assign(urls, j.cdp_urls);
    } catch (_) { /* нет файла */ }
  }
  return urls;
}

function probe(url, timeout = 1200) {
  return new Promise((resolve) => {
    let done = false;
    const fin = (v) => { if (!done) { done = true; resolve(v); } };
    try {
      const req = http.get(String(url).replace(/\/+$/, '') + '/json/version', { timeout }, (res) => {
        res.resume();
        fin(res.statusCode === 200);
      });
      req.on('timeout', () => { req.destroy(); fin(false); });
      req.on('error', () => fin(false));
    } catch (_) {
      fin(false);
    }
  });
}

function chromeScript(root, provider) {
  const base = provider === 'claude' ? 'start_chrome_claude_' : 'start_chrome_';
  return path.join(root, 'scripts', base + 'windows.bat');
}

async function launchChrome(provider, project) {
  const root = findVibeRoot();
  if (!root) return { ok: false, error: tr('Не найден Vibe CLI (vibe.py). Укажите папку в настройках.') };
  const url = cdpUrls(project, root)[provider];
  if (await probe(url)) return { ok: true, already: true };

  const script = chromeScript(root, provider);
  if (!fs.existsSync(script)) return { ok: false, error: tr('Нет скрипта запуска Chrome: ') + script };

  log('info', tr('Chrome не запущен — стартую ') + path.basename(script) + ' …');
  let child;
  try {
    child = spawn('cmd.exe', ['/d', '/s', '/c', '"' + script + '"'], {
      cwd: path.dirname(script),
      detached: true,
      stdio: 'ignore',
      windowsVerbatimArguments: true
    });
    child.on('error', (e) => log('err', tr('Не удалось запустить скрипт: ') + e.message));
    child.unref();
  } catch (e) {
    return { ok: false, error: tr('Не удалось запустить скрипт: ') + e.message };
  }

  const t0 = Date.now();
  while (Date.now() - t0 < 45000) {
    await sleep(700);
    if (await probe(url)) {
      log('info', tr('Chrome отвечает на ') + url + tr('. Если это первый запуск — войдите в аккаунт в открывшемся окне.'));
      return { ok: true, started: true };
    }
  }
  return { ok: false, error: tr('Chrome не ответил на ') + url + tr(' за 45 секунд') };
}

function modelsCacheFile() { return path.join(app.getPath('userData'), 'models-cache.json'); }
ipcMain.handle('models-cache-get', () => { try { return JSON.parse(fs.readFileSync(modelsCacheFile(), 'utf8')); } catch (_) { return {}; } });
ipcMain.handle('models-cache-set', (_e, data) => {
  try { fs.mkdirSync(path.dirname(modelsCacheFile()), { recursive: true }); fs.writeFileSync(modelsCacheFile(), JSON.stringify(data || {}, null, 2), 'utf8'); return { ok: true }; } catch (e) { return { ok: false, error: e.message }; }
});

// запуск произвольного батника/скрипта (автозапуск при старте IDE)
ipcMain.handle('run-script', (_e, script) => {
  const root = findVibeRoot();
  let p = String(script || '').trim().replace(/^"|"$/g, '');
  if (!p) return { ok: false, error: tr('Пустой путь') };
  if (!path.isAbsolute(p) && root) p = path.join(root, p);
  if (!fs.existsSync(p)) return { ok: false, error: tr('Скрипт не найден: ') + p };
  try {
    const child = spawn('cmd.exe', ['/d', '/s', '/c', '"' + p + '"'], { cwd: path.dirname(p), detached: true, stdio: 'ignore', windowsVerbatimArguments: true });
    child.on('error', (e) => log('err', tr('Не удалось запустить ') + path.basename(p) + ': ' + e.message));
    child.unref();
    log('info', tr('Запущен ') + path.basename(p));
    return { ok: true };
  } catch (e) { return { ok: false, error: e.message }; }
});

ipcMain.handle('status', async (_e, project) => {
  const root = findVibeRoot();
  const urls = cdpUrls(project, root);
  const [g, c, a] = await Promise.all([probe(urls.gemini), probe(urls.claude), probe(urls.aistudio)]);
  return {
    vibeRoot: root,
    python: root ? pythonFor(root) : null,
    running: !!proc,
    cdp: {
      gemini: { url: urls.gemini, online: g },
      claude: { url: urls.claude, online: c },
      aistudio: { url: urls.aistudio, online: a }
    }
  };
});

ipcMain.handle('launch-chrome', (_e, provider, project) => launchChrome(provider, project));

/* ---------------- сессия Vibe CLI ---------------- */

function clean(s) {
  return String(s)
    .replace(/\x1b\[[0-9;?]*[ -\/]*[@-~]/g, '')
    .replace(/\x1b\][^\x07]*\x07/g, '');
}

function killProc() {
  if (!proc) return;
  const p = proc;
  try {
    execFile('taskkill', ['/pid', String(p.pid), '/T', '/F'], () => {});
  } catch (_) { /* ignore */ }
}

ipcMain.handle('set-lang', (_e, lang) => { LANG = lang === 'ru' ? 'ru' : 'en'; return LANG; });

ipcMain.handle('session-start', async (_e, o) => {
  if (proc || starting) return { ok: false, error: tr('Сессия уже запущена') };
  const root = findVibeRoot();
  if (!root) return { ok: false, error: tr('Не найден vibe.py — укажите папку Vibe CLI в настройках') };
  if (!o || !o.project || !fs.existsSync(o.project)) return { ok: false, error: tr('Не выбрана папка проекта') };

  starting = true;
  try {
    if (o.autoChrome) {
      const r = await launchChrome(o.provider, o.project);
      if (!r.ok) log('warn', r.error);
    }

    const args = [path.join(root, 'vibe.py'), '--dir', o.project, '--provider', o.provider];
    if (o.model) args.push('--model', String(o.model));
    if (o.reasoning) args.push('--reasoning', String(o.reasoning));
    if (o.yolo) args.push('--yolo');
    if (o.transport) args.push('--transport', String(o.transport));
    args.push('--auto-context', o.autoContext ? 'on' : 'off');
    if (o.promptStyle) args.push('--prompt-style', String(o.promptStyle));

    const minutes = Math.min(180, Math.max(1, Number(o.timeoutMin) || 60));
    stopFile = path.join(os.tmpdir(), 'vibe-stop-' + process.pid + '-' + Date.now());
    try { fs.unlinkSync(stopFile); } catch (_) { /* нет файла */ }
    const env = Object.assign({}, process.env, {
      VIBE_STOP_FILE: stopFile,
      PYTHONUNBUFFERED: '1',
      PYTHONIOENCODING: 'utf-8',
      PYTHONUTF8: '1',
      VIBE_IDE: '1',
      VIBE_LANG: LANG,
      VIBE_HUMAN: o.human === 'old' ? 'old' : (o.human ? 'true' : 'false'),
      VIBE_RESPONSE_TIMEOUT: String(minutes * 60),
      COLUMNS: '110',
      TERM: 'dumb',
      NO_COLOR: '1'
    });

    const py = pythonFor(root);
    const id = ++sessionSeq;
    let child;
    try {
      child = spawn(py, args, { cwd: root, env, windowsHide: true });
    } catch (e) {
      return { ok: false, error: tr('Не удалось запустить Python: ') + e.message };
    }
    proc = child;
    log('info', tr('Vibe CLI запущен (') + path.basename(py) + tr(', таймаут ответа ') + minutes + tr(' мин)'));

    child.stdout.setEncoding('utf8');
    child.stderr.setEncoding('utf8');
    let outBuf = '';
    child.stdout.on('data', (d) => {
      outBuf += clean(d);
      let nl;
      while ((nl = outBuf.indexOf('\n')) >= 0) {
        const line = outBuf.slice(0, nl).replace(/\r$/, '');
        outBuf = outBuf.slice(nl + 1);
        if (line.startsWith(EV_PREFIX)) {
          try { emit('vibe-event', Object.assign({ id }, JSON.parse(line.slice(EV_PREFIX.length)))); continue; } catch (_) { /* не JSON — в журнал */ }
        }
        emit('proc-out', { id, text: line + '\n' });
      }
    });
    child.stderr.on('data', (d) => emit('proc-out', { id, text: clean(d) }));
    child.stdin.on('error', () => {});
    child.on('error', (e) => {
      if (proc === child) proc = null;
      emit('proc-exit', { id, code: -1, error: e.message });
    });
    child.on('close', (code, signal) => {
      if (proc === child) proc = null;
      emit('proc-exit', { id, code, signal });
    });
    return { ok: true, id };
  } finally {
    starting = false;
  }
});

ipcMain.handle('session-send', (_e, text) => {
  if (!proc || !proc.stdin || proc.stdin.destroyed) return { ok: false };
  try {
    proc.stdin.write(String(text) + '\n');
    return { ok: true };
  } catch (_) {
    return { ok: false };
  }
});

ipcMain.handle('session-stop', () => {
  killProc();
  return { ok: true };
});

ipcMain.handle('generation-stop', () => {
  if (!proc || !stopFile) return { ok: false };
  try { fs.writeFileSync(stopFile, String(Date.now())); return { ok: true }; } catch (_) { return { ok: false }; }
});

ipcMain.handle('open-external', (_e, url) => {
  if (/^https?:\/\//i.test(String(url))) { shell.openExternal(String(url)); return true; }
  return false;
});

ipcMain.handle('set-theme', (_e, t) => {
  if (!win || win.isDestroyed() || !t) return false;
  try {
    win.setBackgroundColor(String(t.bg || '#0b0d12'));
    if (win.setTitleBarOverlay) win.setTitleBarOverlay({ color: String(t.bg || '#0b0d12'), symbolColor: String(t.fg || '#e8eaf0'), height: 44 });
  } catch (_) { /* платформа без overlay */ }
  return true;
});

// Список моделей: короткий одноразовый запуск CLI (--list-models-json), ответ приходит событием models.
ipcMain.handle('list-models', (_e, o) => new Promise((resolve) => {
  const root = findVibeRoot();
  if (!root || !o || !o.project) return resolve({ ok: false, error: tr('Не найден Vibe CLI или проект') });
  const args = [path.join(root, 'vibe.py'), '--dir', o.project, '--provider', o.provider, '--list-models-json'];
  const env = Object.assign({}, process.env, { PYTHONUNBUFFERED: '1', PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1', VIBE_IDE: '1', NO_COLOR: '1' }, cliLang());
  let child;
  try { child = spawn(pythonFor(root), args, { cwd: root, env, windowsHide: true }); } catch (e) { return resolve({ ok: false, error: e.message }); }
  let buf = '';
  let result = null;
  const timer = setTimeout(() => { try { child.kill(); } catch (_) { /* ignore */ } }, 70000);
  child.stdout.setEncoding('utf8');
  child.stdout.on('data', (d) => {
    buf += d;
    let nl;
    while ((nl = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, nl).trim();
      buf = buf.slice(nl + 1);
      if (line.startsWith(EV_PREFIX)) {
        try { const ev = JSON.parse(line.slice(EV_PREFIX.length)); if (ev.t === 'models') result = ev; } catch (_) { /* ignore */ }
      }
    }
  });
  child.on('error', (e) => { clearTimeout(timer); resolve({ ok: false, error: e.message }); });
  child.on('close', () => {
    clearTimeout(timer);
    resolve(result && !result.error ? { ok: true, models: result } : { ok: false, error: (result && result.error) || tr('Не удалось получить список (запущен ли Chrome и выполнен ли вход?)') });
  });
}));

/* ---------------- диалоги ---------------- */

const ATTACH_EXT = ['zip', 'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'];
ipcMain.handle('pick-files', async () => {
  const res = await dialog.showOpenDialog(win, {
    title: tr('Прикрепить файлы'),
    properties: ['openFile', 'multiSelections'],
    filters: [{ name: tr('ZIP и изображения'), extensions: ATTACH_EXT }, { name: tr('Все файлы'), extensions: ['*'] }]
  });
  if (res.canceled) return [];
  return res.filePaths.map((p) => { let size = 0; try { size = fs.statSync(p).size; } catch (_) { /* ignore */ } return { path: p, name: path.basename(p), size }; });
});

// вставленные из буфера / перетащенные без пути файлы сохраняем во временную папку
ipcMain.handle('save-temp', (_e, name, bytes) => {
  try {
    const dir = path.join(os.tmpdir(), 'vibe-attach');
    fs.mkdirSync(dir, { recursive: true });
    const safe = String(name || 'file').replace(/[^\w.\-]+/g, '_');
    const p = path.join(dir, Date.now() + '-' + safe);
    fs.writeFileSync(p, Buffer.from(bytes));
    return { path: p, name: safe, size: fs.statSync(p).size };
  } catch (e) { return { error: e.message }; }
});

ipcMain.handle('pick-folder', async (_e, title) => {
  const res = await dialog.showOpenDialog(win, {
    title: title || tr('Выберите папку проекта'),
    properties: ['openDirectory']
  });
  if (res.canceled || !res.filePaths.length) return null;
  return res.filePaths[0];
});

ipcMain.handle('pick-vibe-root', async () => {
  const res = await dialog.showOpenDialog(win, {
    title: tr('Папка Vibe CLI (где лежит vibe.py)'),
    properties: ['openDirectory']
  });
  if (res.canceled || !res.filePaths.length) return { ok: false };
  const d = res.filePaths[0];
  if (!isVibeRoot(d)) return { ok: false, error: tr('В этой папке нет vibe.py и core/') };
  saveCfg({ vibeRoot: d });
  return { ok: true, root: d };
});

ipcMain.handle('reveal-ignore', (_e, project) => {
  const f = path.join(project || '', '.vibeignore');
  if (fs.existsSync(f)) {
    shell.showItemInFolder(f);
    return true;
  }
  return false;
});

/* ---------------- исключения и контекст ---------------- */

function readLines(f) {
  try { return fs.readFileSync(f, 'utf8').split(/\r?\n/); } catch (_) { return []; }
}

function globRe(g) {
  let s = '';
  for (let i = 0; i < g.length; i++) {
    const c = g[i];
    if (c === '*') {
      if (g[i + 1] === '*') {
        if (g[i + 2] === '/') { s += '(?:.*/)?'; i += 2; }
        else { s += '.*'; i += 1; }
      } else {
        s += '[^/]*';
      }
    } else if (c === '?') {
      s += '[^/]';
    } else if ('\\^$+.()|{}[]'.includes(c)) {
      s += '\\' + c;
    } else {
      s += c;
    }
  }
  return new RegExp('^' + s + '$');
}

function loadRules(root) {
  const rules = [];
  const add = (lines, tag) => {
    for (const raw of lines) {
      let l = String(raw).trim();
      if (!l || l[0] === '#' || l[0] === '!') continue;
      l = l.replace(/\\/g, '/');
      let dirOnly = false;
      if (l.endsWith('/')) { dirOnly = true; l = l.slice(0, -1); }
      let anchored = false;
      if (l.startsWith('/')) { anchored = true; l = l.slice(1); }
      else if (l.includes('/')) anchored = true;
      if (!l) continue;
      try { rules.push({ re: globRe(l), anchored, dirOnly, tag }); } catch (_) { /* плохой паттерн */ }
    }
  };
  add(BUILTIN, 'builtin');
  add(readLines(path.join(root, '.gitignore')), 'git');
  add(readLines(path.join(root, '.vibeignore')), 'user');
  try {
    const j = JSON.parse(fs.readFileSync(path.join(root, '.vibe.json'), 'utf8'));
    if (Array.isArray(j.ignore)) add(j.ignore, 'user');
  } catch (_) { /* нет файла */ }

  return (rel, name, isDir) => {
    for (const r of rules) {
      if (r.dirOnly && !isDir) continue;
      if (r.re.test(r.anchored ? rel : name)) return r.tag;
    }
    return null;
  };
}

function walk(root, rel, isEx, out) {
  let entries;
  try {
    entries = fs.readdirSync(path.join(root, rel), { withFileTypes: true });
  } catch (_) {
    return;
  }
  entries.sort((a, b) => (b.isDirectory() - a.isDirectory()) || a.name.localeCompare(b.name));
  for (const e of entries) {
    if (e.isSymbolicLink() || SKIP_NAMES.has(e.name)) continue;
    const r = rel ? rel + '/' + e.name : e.name;
    const dir = e.isDirectory();
    if (isEx(r, e.name, dir)) continue;
    if (dir) walk(root, r, isEx, out);
    else if (e.isFile()) out.push(r);
  }
}

function collect(root) {
  const isEx = loadRules(root);
  const files = [];
  walk(root, '', isEx, files);
  const maxBytes = MAX_FILE_KB * 1024;
  const skipped = { binary: 0, large: 0, unreadable: 0 };
  const list = [];
  let bytes = 0;
  for (const rel of files) {
    const full = path.join(root, rel);
    let st;
    try { st = fs.statSync(full); } catch (_) { skipped.unreadable++; continue; }
    if (st.size > maxBytes) { skipped.large++; continue; }
    let bin = false;
    try {
      const fd = fs.openSync(full, 'r');
      const buf = Buffer.alloc(Math.min(2048, st.size));
      fs.readSync(fd, buf, 0, buf.length, 0);
      fs.closeSync(fd);
      bin = buf.includes(0);
    } catch (_) {
      skipped.unreadable++;
      continue;
    }
    if (bin) { skipped.binary++; continue; }
    bytes += st.size;
    list.push({ rel, size: st.size });
  }
  list.sort((a, b) => b.size - a.size);
  return {
    files: list.length,
    bytes,
    tokens: Math.ceil(bytes / 4),
    skipped,
    top: list.slice(0, 6)
  };
}

ipcMain.handle('list-dir', (_e, root, rel) => {
  const abs = path.join(root, rel || '');
  let entries = [];
  try {
    entries = fs.readdirSync(abs, { withFileTypes: true });
  } catch (_) {
    return [];
  }
  const isEx = loadRules(root);
  entries.sort((a, b) => (b.isDirectory() - a.isDirectory()) || a.name.localeCompare(b.name));
  const out = [];
  for (const e of entries.slice(0, MAX_LIST)) {
    if (e.isSymbolicLink() || SKIP_NAMES.has(e.name)) continue;
    const isDir = e.isDirectory();
    const r = rel ? rel + '/' + e.name : e.name;
    let size = 0;
    if (!isDir) {
      try { size = fs.statSync(path.join(abs, e.name)).size; } catch (_) { /* ignore */ }
    }
    out.push({ name: e.name, isDir, size, state: isEx(r, e.name, isDir) });
  }
  return out;
});

ipcMain.handle('preview', (_e, root) => collect(root));

function splitVibeignore(text) {
  const lines = String(text || '').split(/\r?\n/);
  const rest = [];
  const managed = [];
  let inBlock = false;
  for (const l of lines) {
    const t = l.trim();
    if (t === MARK_BEGIN) { inBlock = true; continue; }
    if (t === MARK_END) { inBlock = false; continue; }
    if (inBlock) { if (t) managed.push(t); }
    else rest.push(l);
  }
  while (rest.length && !rest[rest.length - 1].trim()) rest.pop();
  return { managed, rest };
}

ipcMain.handle('ignore-get', (_e, project) => {
  let text = '';
  try { text = fs.readFileSync(path.join(project, '.vibeignore'), 'utf8'); } catch (_) { /* нет файла */ }
  return { managed: splitVibeignore(text).managed };
});

ipcMain.handle('ignore-set', (_e, project, patterns) => {
  const f = path.join(project, '.vibeignore');
  let text = '';
  try { text = fs.readFileSync(f, 'utf8'); } catch (_) { /* нет файла */ }
  const parts = splitVibeignore(text).rest;
  const list = (patterns || []).map((p) => String(p).trim()).filter(Boolean);
  if (list.length) {
    if (parts.length) parts.push('');
    parts.push(MARK_BEGIN, ...list, MARK_END);
  }
  try {
    if (!parts.length) {
      if (fs.existsSync(f)) fs.unlinkSync(f);
    } else {
      fs.writeFileSync(f, parts.join('\n') + '\n', 'utf8');
    }
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e.message };
  }
});

