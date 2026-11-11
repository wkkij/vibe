(() => {
  'use strict';

  const api = window.vibe;
  const MD = window.VibeMD;
  const $ = (id) => document.getElementById(id);
  const el = MD.el;
  const LS_KEY = 'vibeide:v2';
  const VERSION = '0.01.3';

  /* ================= данные ================= */

  const PROVIDERS = {
    gemini: { title: 'Gemini', host: 'gemini.google.com' },
    claude: { title: 'Claude', host: 'claude.ai' },
    aistudio: { title: 'AI Studio', host: 'aistudio.google.com' }
  };
  const THEMES = [
    { id: 'system', name: tr('Системная'), sub: tr('авто') },
    { id: 'graphite', name: tr('Графит'), sub: tr('тёмная') },
    { id: 'noir', name: tr('Нуар'), sub: tr('тёмная') },
    { id: 'midnight', name: tr('Полночь'), sub: tr('тёмная') },
    { id: 'aurora', name: tr('Аврора'), sub: tr('тёмная') },
    { id: 'sunset', name: tr('Закат'), sub: tr('тёмная') },
    { id: 'light', name: tr('Светлая'), sub: tr('светлая') },
    { id: 'paper', name: tr('Бумага'), sub: tr('светлая') }
  ];
  const ACCENTS = ['', '#7c5cff', '#4d8dff', '#14d6c4', '#2fe0a5', '#f5b84a', '#ff7a59', '#ff5fa2'];
  const STYLES = [['auto', tr('Авто — каждый раз новый текст')], ['classic', tr('Классика — один и тот же текст')]];
  const TRANSPORTS = [
    ['auto', tr('Авто')], ['file', tr('Файл .txt')], ['paste', tr('Файл вставкой')], ['inline', tr('Текстом в сообщении')], ['zip', tr('ZIP-архив')], ['base64', tr('Base64-файл')]
  ];
  const TRANSPORT_DESC = {
    auto: tr('Пробует по очереди: файл → вставка → ZIP → base64-файл → текст, пока чат не увидит контекст'),
    file: tr('Контекст — обычным файлом через кнопку «+» в чате'),
    paste: tr('Тот же .txt, но вставляется как из буфера обмена (paste/drop) — если кнопка «+» недоступна'),
    inline: tr('Весь контекст — прямо в тексте сообщения, без вложений'),
    zip: tr('Контекст упаковывается в .zip и прикрепляется файлом (меньше размер)'),
    base64: tr('Контекст кодируется в base64 и прикрепляется отдельным .txt-файлом')
  };
  const COMMANDS = [
    ['/plan', tr('сначала план, потом код')], ['/fix', tr('прогнать проверку и починить')], ['/undo', tr('откатить последний патч')],
    ['/context', tr('что попадёт в контекст')], ['/reset', tr('новый чат')], ['/continue', tr('продолжить остановленный ответ')],
    ['/autocontext', tr('on | off — автоподбор файлов')], ['/promptstyle', tr('тексты промптов')], ['/attach', tr('прикрепить файл')], ['/yolo', tr('on | off — без подтверждений')], ['/transport', tr('формат отправки')], ['/model', tr('модель')],
    ['/reasoning', tr('уровень рассуждений')], ['/verify_cmd', tr('команда проверки')], ['/check_ui', tr('проверить фронтенд')], ['/help', tr('справка')], ['/lang', tr('язык интерфейса')]
  ];
  const STEPS = [tr('Контекст'), tr('Отправка'), tr('Размышление'), tr('Ответ'), tr('Применение'), tr('Проверка')];
  const PHASE_STEP = { packing: 0, selecting: 0, sending: 1, waiting: 1, thinking: 2, answering: 3, applying: 4, verifying: 5, healing: 5, checking_ui: 5 };
  const PHASE_TEXT = {
    packing: tr('Собираю контекст…'), selecting: tr('Подбираю файлы под задачу…'), sending: tr('Отправляю в чат…'), waiting: tr('Жду начала ответа…'),
    thinking: tr('Модель думает…'), answering: tr('Модель отвечает…'), applying: tr('Применяю патчи…'), verifying: tr('Проверяю сборку…'),
    healing: tr('Исправляю ошибки…'), checking_ui: tr('Проверяю интерфейс…'), idle: tr('Готово')
  };
  const STEP_ICONS = ['layers', 'send', 'brain', 'chat', 'file', 'shield'];
  const ACTION_TEXT = { MODIFIED: tr('изменён'), CREATED: tr('создан'), DELETED: tr('удалён'), FAILED: tr('ошибка') };

  const ICONS = {
    chat: [['path', 'M21 11.5a8.4 8.4 0 0 1-12.2 7.5L3.5 20.5l1.4-4.8A8.4 8.4 0 1 1 21 11.5z'], ['path', 'M8.5 10.5h7M8.5 13.5h4']],
    folder: [['path', 'M3 7.5A2.5 2.5 0 0 1 5.5 5H9l2 2.2h7.5A2.5 2.5 0 0 1 21 9.7v7.8a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 17.5z']],
    sliders: [['path', 'M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1'], ['circle', 15, 6, 2], ['circle', 9, 12, 2], ['circle', 17, 18, 2]],
    send: [['path', 'M12 19V6M6 11.5l6-6 6 6']],
    stop: [['rect', 6.5, 6.5, 11, 11, 2.5]],
    chev: [['path', 'M6 9.5l6 6 6-6']],
    chevr: [['path', 'M9.5 6l6 6-6 6']],
    corner: [['path', 'M5 5v6a3 3 0 0 0 3 3h11M15 10l4 4-4 4']],
    panel: [['rect', 3, 4.5, 18, 15, 3.5], ['path', 'M15 4.5v15']],
    power: [['path', 'M12 3v8.5'], ['path', 'M6.6 6.8a8 8 0 1 0 10.8 0']],
    spark: [['path', 'M12 3.5l1.9 5.1 5.1 1.9-5.1 1.9L12 17.5l-1.9-5.1L5 10.5l5.1-1.9z'], ['path', 'M19 16.5v3M17.5 18h3']],
    target: [['circle', 12, 12, 8.5], ['circle', 12, 12, 4.5], ['circle', 12, 12, 1]],
    list: [['path', 'M9 6.5h11M9 12h11M9 17.5h11'], ['circle', 4.8, 6.5, .6], ['circle', 4.8, 12, .6], ['circle', 4.8, 17.5, .6]],
    undo: [['path', 'M4 8.5V4M4 8.5h4.5'], ['path', 'M4.6 8.5A8 8 0 1 1 4 12.5']],
    plus: [['path', 'M12 5v14M5 12h14']],
    palette: [['path', 'M12 3.5a8.5 8.5 0 1 0 0 17c1.4 0 2-.9 1.6-1.9-.5-1.1.1-2.1 1.3-2.1H17a3.5 3.5 0 0 0 3.5-3.5C20.5 7.3 16.7 3.5 12 3.5z'], ['circle', 7.6, 11.2, 1], ['circle', 10.2, 7.4, 1], ['circle', 14.6, 7.6, 1]],
    bolt: [['path', 'M13 2.5L4.5 13.5H11l-1 8 8.5-11H12z']],
    plug: [['path', 'M9 2.5v5M15 2.5v5'], ['path', 'M6.5 7.5h11v3.5a5.5 5.5 0 0 1-11 0z'], ['path', 'M12 16.5v5']],
    info: [['circle', 12, 12, 9], ['path', 'M12 11v5.2M12 7.8h.01']],
    file: [['path', 'M14 3H7.5A2.5 2.5 0 0 0 5 5.5v13A2.5 2.5 0 0 0 7.5 21h9a2.5 2.5 0 0 0 2.5-2.5V8z'], ['path', 'M14 3v5h5M9 13h6M9 16.5h4']],
    check: [['path', 'M5 12.5l4.5 4.5L19 7.5']],
    x: [['path', 'M6.5 6.5l11 11M17.5 6.5l-11 11']],
    refresh: [['path', 'M20.5 12a8.5 8.5 0 1 1-2.6-6.1'], ['path', 'M20.5 4v4.5H16']],
    play: [['path', 'M7.5 4.5l11 7.5-11 7.5z']],
    term: [['path', 'M4 6.5A2.5 2.5 0 0 1 6.5 4h11A2.5 2.5 0 0 1 20 6.5v11a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 17.5z'], ['path', 'M8 10l3 2.5L8 15M13 15h3.5']],
    clip: [['path', 'M20 11.5l-7.8 7.8a5 5 0 0 1-7.1-7.1l8-8a3.4 3.4 0 0 1 4.8 4.8l-8 8a1.8 1.8 0 0 1-2.5-2.5l7.3-7.3']],
    image: [['rect', 3.5, 4.5, 17, 15, 3.5], ['circle', 9, 10, 1.6], ['path', 'M20.5 15.5l-4.8-4.8L7 19.5']],
    archive: [['rect', 3.5, 4, 17, 4.5, 1.5], ['path', 'M5 8.5v8.5A2.5 2.5 0 0 0 7.5 19.5h9A2.5 2.5 0 0 0 19 17V8.5M10 12.5h4']],
    trash: [['path', 'M4.5 7h15M9.5 7V4.5h5V7M6.5 7l.8 11.2a2 2 0 0 0 2 1.8h5.4a2 2 0 0 0 2-1.8L17.5 7M10 11v5M14 11v5']],
    copy: [['rect', 8.5, 8.5, 11, 11, 2.5], ['path', 'M15.5 8.5V6.5A2.5 2.5 0 0 0 13 4H6.5A2.5 2.5 0 0 0 4 6.5V13a2.5 2.5 0 0 0 2.5 2.5h2']],
    layers: [['path', 'M12 3.5l8.5 4.5-8.5 4.5L3.5 8z'], ['path', 'M3.5 12.2L12 16.7l8.5-4.5M3.5 16.2L12 20.7l8.5-4.5']],
    brain: [['path', 'M9.5 4.5A3 3 0 0 0 6.6 7 3.2 3.2 0 0 0 4.5 10a3.2 3.2 0 0 0 1.3 2.6A3.3 3.3 0 0 0 7 17.5a3 3 0 0 0 5 1.8V6.2a2.4 2.4 0 0 0-2.5-1.7z'], ['path', 'M14.5 4.5A3 3 0 0 1 17.4 7a3.2 3.2 0 0 1 2.1 3 3.2 3.2 0 0 1-1.3 2.6A3.3 3.3 0 0 1 17 17.5a3 3 0 0 1-5 1.8']],
    shield: [['path', 'M12 3l7.5 3v5.5c0 4.6-3.1 8-7.5 9.5-4.4-1.5-7.5-4.9-7.5-9.5V6z'], ['path', 'M9 12l2.2 2.2L15.5 10']],
    zap: [['path', 'M13 2.5L4.5 13.5H11l-1 8 8.5-11H12z']],
    download: [['path', 'M12 4v11M7 10.5l5 5 5-5M5 19.5h14']]
  };
  function icon(name) {
    const NS = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    for (const part of ICONS[name] || []) {
      const e = document.createElementNS(NS, part[0]);
      if (part[0] === 'path') e.setAttribute('d', part[1]);
      else if (part[0] === 'circle') { e.setAttribute('cx', part[1]); e.setAttribute('cy', part[2]); e.setAttribute('r', part[3]); }
      else { e.setAttribute('x', part[1]); e.setAttribute('y', part[2]); e.setAttribute('width', part[3]); e.setAttribute('height', part[4]); e.setAttribute('rx', part[5]); }
      svg.appendChild(e);
    }
    return svg;
  }
  function fillIcons(root) {
    for (const n of (root || document).querySelectorAll('[data-i]')) {
      if (!n.firstChild) n.appendChild(icon(n.dataset.i));
    }
  }
  const ico = (name, cls) => { const s = el('span', 'ico' + (cls ? ' ' + cls : '')); s.appendChild(icon(name)); return s; };

  /* ================= состояние ================= */

  const vibis = [];
  const S = {
    project: null, provider: 'gemini',
    models: { gemini: '', claude: '', aistudio: '' }, reasonings: { gemini: '', claude: '', aistudio: '' },
    theme: 'graphite', accent: '', density: 'standard', fontSize: 14, radius: 12, chatWidth: 860, fx: true, motion: true, inspector: true,
    autoChrome: true, yolo: false, transport: 'auto', inputMode: 'cdp', attach: [], plan: false, autoContext: false, maxFiles: 24, budget: 30000, promptStyle: 'auto',
    showThink: true, livePreview: true, notify: true, timeoutMin: 60, recents: [], liveModels: {}, autoBat: 'sel', startScripts: '', modelsRefreshMin: 60, lastTry: {}, refreshing: false,
    // служебное (не сохраняется)
    running: false, starting: false, mode: 'off', outbox: [], turn: null, stick: true, vibeRoot: null, python: null,
    cdp: { gemini: { online: false, url: '' }, claude: { online: false, url: '' }, aistudio: { online: false, url: '' } },
    cache: new Map(), expanded: new Set(), managed: new Set(), changes: [], ctxInfo: null, askCard: null, phase: 'idle',
    modelPop: { open: false, provider: 'gemini', q: '' }, logCount: 0
  };
  const PERSIST = ['project', 'provider', 'models', 'reasonings', 'theme', 'accent', 'density', 'fontSize', 'radius', 'chatWidth', 'fx', 'motion', 'inspector',
    'autoChrome', 'yolo', 'plan', 'autoContext', 'maxFiles', 'budget', 'promptStyle', 'transport', 'inputMode', 'autoBat', 'startScripts', 'modelsRefreshMin', 'showThink', 'livePreview', 'notify', 'timeoutMin', 'recents'];

  function loadSettings() {
    try {
      const o = JSON.parse(localStorage.getItem(LS_KEY) || 'null');
      if (o) { for (const k of PERSIST) if (o[k] !== undefined) S[k] = o[k]; return; }
      const old = JSON.parse(localStorage.getItem('vibeide:v1') || '{}');   // миграция со старой версии
      for (const k of ['project', 'provider', 'autoChrome', 'yolo', 'plan', 'fx', 'timeoutMin', 'recents']) if (old[k] !== undefined) S[k] = old[k];
      if (old.model) S.models[S.provider] = old.model;
      if (old.reasoning) S.reasonings[S.provider] = old.reasoning;
    } catch (_) { /* ignore */ }
    if (!PROVIDERS[S.provider]) S.provider = 'gemini';
  }
  function saveSettings() {
    try {
      const o = {};
      for (const k of PERSIST) o[k] = S[k];
      localStorage.setItem(LS_KEY, JSON.stringify(o));
    } catch (_) { /* ignore */ }
  }

  /* ================= утилиты ================= */

  let toastTimer = null;
  function toast(msg, isErr) {
    const t = $('toast');
    t.textContent = msg;
    t.classList.toggle('err', !!isErr);
    t.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove('show'), 3600);
  }
  function fmtBytes(n) {
    if (n < 1024) return n + tr(' Б');
    if (n < 1024 * 1024) return (n / 1024).toFixed(n < 10240 ? 1 : 0) + tr(' КБ');
    return (n / (1024 * 1024)).toFixed(1) + tr(' МБ');
  }
  const fmtNum = (n) => Number(n).toLocaleString('ru-RU');
  const baseName = (p) => String(p).split(/[\\/]/).filter(Boolean).pop() || String(p);
  function fmtTime(ms) {
    const s = Math.floor(ms / 1000), m = Math.floor(s / 60), pad = (x) => String(x).padStart(2, '0');
    return pad(m) + ':' + pad(s % 60);
  }
  const provTitle = () => PROVIDERS[S.provider].title;
  const curModel = () => S.models[S.provider] || '';

  /* ================= тема ================= */

  function resolvedTheme() {
    if (S.theme !== 'system') return S.theme;
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'graphite';
  }
  function lum(hex) {
    const m = /^#?([0-9a-f]{6})$/i.exec(hex);
    if (!m) return 0;
    const n = parseInt(m[1], 16);
    return (0.299 * (n >> 16) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) / 255;
  }
  function applyTheme() {
    const root = document.documentElement;
    root.setAttribute('data-theme', resolvedTheme());
    root.setAttribute('data-density', S.density);
    root.setAttribute('data-motion', S.motion ? 'on' : 'off');
    for (const v of vibis) v.animate(S.motion);
    root.style.setProperty('--fs', S.fontSize + 'px');
    root.style.setProperty('--r', S.radius + 'px');
    root.style.setProperty('--chat-w', S.chatWidth + 'px');
    if (S.accent) {
      root.style.setProperty('--accent', S.accent);
      root.style.setProperty('--accent2', 'color-mix(in srgb, ' + S.accent + ' 55%, white)');
      root.style.setProperty('--accent-fg', lum(S.accent) > 0.62 ? '#14151a' : '#ffffff');
      root.style.setProperty('--fx-rgb', parseInt(S.accent.slice(1, 3), 16) + ',' + parseInt(S.accent.slice(3, 5), 16) + ',' + parseInt(S.accent.slice(5, 7), 16));
    } else {
      for (const k of ['--accent', '--accent2', '--accent-fg', '--fx-rgb']) root.style.removeProperty(k);
    }
    if (window.VibeFX) { window.VibeFX.refresh(); window.VibeFX.set(S.fx); }
    const cs = getComputedStyle(root);
    try { api.setTheme({ bg: cs.getPropertyValue('--bg2').trim(), fg: cs.getPropertyValue('--fg').trim() }); } catch (_) { /* ignore */ }
  }
  if (window.matchMedia) window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', () => { if (S.theme === 'system') applyTheme(); });

  /* ================= лента чата ================= */

  const feed = $('feed');
  feed.addEventListener('scroll', () => { S.stick = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 90; });
  const scrollDown = (force) => { if (force || S.stick) feed.scrollTop = feed.scrollHeight; };
  const hideHero = () => $('hero').classList.add('hidden');

  function addSys(text, level) {
    hideHero();
    const row = el('div', 'sys' + (level ? ' ' + level : ''));
    row.append(ico(level === 'err' ? 'x' : level === 'ok' ? 'check' : level === 'warn' ? 'info' : 'chevr', 'sm'), el('span', null, text));
    feed.appendChild(row);
    scrollDown();
  }
  function addUser(text, files) {
    hideHero();
    const m = el('div', 'user-msg');
    const bub = el('div', 'bubble');
    if (files && files.length) { const row = el('div', 'bub-files'); for (const f of files) row.appendChild(attChip(f)); bub.appendChild(row); }
    bub.appendChild(document.createTextNode(text));
    m.appendChild(bub);
    feed.appendChild(m);
    scrollDown(true);
  }

  function newTurn() {
    finishTurn();
    hideHero();
    const box = el('div', 'turn');
    const head = el('div', 'turn-head');
    const av = el('span', 'avatar'); av.appendChild(ico('spark', 'sm'));
    const status = el('span', 'status');
    const spin = el('span', 'spin');
    const label = el('span', null, tr('Запускаю…'));
    status.append(spin, label);
    const timer = el('span', 'timer', '00:00');
    const actions = el('div', 'turn-actions');
    head.append(av, el('span', 'turn-title', 'Vibe'), status, timer, actions);
    const stepper = el('div', 'stepper');
    const steps = STEPS.map((n, i) => { const s = el('div', 'step'); s.append(ico(STEP_ICONS[i], 'sm'), el('span', null, n)); stepper.appendChild(s); return s; });
    const body = el('div', 'turn-body');
    const ctxline = el('div', 'ctxline hidden');
    const live = el('div', 'live hidden');
    const liveMeta = el('div', 'live-meta');
    const liveText = el('span');
    live.append(liveMeta, liveText);
    const answers = el('div', 'answers');
    const patches = el('div', 'rowlist');
    const asks = el('div', 'asks');
    const logBox = el('details', 'logbox hidden');
    logBox.appendChild(el('summary', null, tr('Журнал запуска')));
    const logPre = el('pre');
    logBox.appendChild(logPre);
    body.append(ctxline, live, answers, patches, asks, logBox);
    box.append(head, stepper, body);
    feed.appendChild(box);
    const T = { box, status, spin, label, timer, actions, steps, ctxline, live, liveMeta, liveText, answers, patches, asks, logBox, logPre, start: Date.now(), done: false, phase: '', ops: {}, stopBtn: null };
    const sb = el('button', 'btn small danger', tr('Остановить'));
    sb.addEventListener('click', stopGeneration);
    T.stopBtn = sb;
    actions.appendChild(sb);
    S.turn = T;
    setPhase('packing');
    scrollDown(true);
    return T;
  }

  function vibiMood(m) { for (const v of vibis) v.set(m); }
  function initVibi() {
    try { const pet = VibiPet({ composer: document.querySelector('.composer'), send: $('send'), feed: $('feed'), enabled: () => S.motion, target: () => (S.turn && !S.turn.done ? S.turn.box : null) }); vibis.push(pet.vibi); } catch (_) { /* без кота */ }
    for (const [id, px] of [['heroVibi', 7]]) {
      const c = $(id); if (!c) continue;
      const v = Vibi(c, px); v.animate(S.motion); vibis.push(v);
      if (id === 'heroVibi') c.addEventListener('click', () => { v.set('wink'); setTimeout(() => v.set(S.mode === 'busy' ? 'work' : 'idle'), 900); });
    }
  }

  function setPhase(ph) {
    S.phase = ph;
    vibiMood(window.VIBI_MOOD_BY_PHASE[ph] || 'work');
    updateStatusBar();
    renderSession();
    const T = S.turn;
    if (!T || T.done) return;
    T.phase = ph;
    let text = PHASE_TEXT[ph] || ph;
    if (ph === 'thinking' && !S.showThink) text = tr('Модель работает…');
    T.label.textContent = text;
    T.status.querySelector('.think') && T.status.querySelector('.think').remove();
    if (ph === 'thinking' && S.showThink) { const t = el('span', 'think'); t.append(el('i'), el('i'), el('i')); T.status.appendChild(t); }
    const cur = PHASE_STEP[ph];
    if (cur !== undefined) T.steps.forEach((s, i) => { s.classList.toggle('done', i < cur); s.classList.toggle('cur', i === cur); });
    T.stopBtn.classList.toggle('hidden', !['sending', 'waiting', 'thinking', 'answering'].includes(ph));
  }

  setInterval(() => {
    const T = S.turn;
    if (T && !T.done) {
      T.timer.textContent = fmtTime(Date.now() - T.start);
      $('sbPhase').textContent = (PHASE_TEXT[S.phase] || tr('работает')) + ' · ' + fmtTime(Date.now() - T.start);
    }
  }, 1000);

  function finishTurn(opts) {
    const T = S.turn;
    if (!T || T.done) return;
    T.done = true;
    const o = opts || {};
    vibiMood(o.failed ? 'error' : o.stopped ? 'sleep' : 'happy');
    setTimeout(() => { if (S.mode !== 'busy') vibiMood('idle'); }, 3500);
    T.timer.textContent = fmtTime(Date.now() - T.start);
    T.spin.remove();
    T.status.querySelector('.think') && T.status.querySelector('.think').remove();
    T.label.textContent = o.stopped ? tr('Остановлено') : o.failed ? tr('Ошибка') : tr('Готово за ') + fmtTime(Date.now() - T.start);
    T.steps.forEach((s) => { s.classList.remove('cur'); if (!o.stopped) s.classList.add('done'); });
    T.live.classList.add('hidden');
    T.stopBtn.remove();
    if (o.stopped) {
      const cont = el('button', 'btn small primary');
      cont.append(ico('play', 'sm'), document.createTextNode(tr(' Продолжить')));
      cont.addEventListener('click', () => { cont.remove(); enqueue('/continue', { label: tr('↻ Продолжить ответ') }); });
      T.actions.appendChild(cont);
    }
    if (S.notify && document.hidden && 'Notification' in window) {
      try { new Notification('Vibe IDE', { body: o.stopped ? tr('Ответ остановлен') : tr('Задача завершена') }); } catch (_) { /* ignore */ }
    }
  }

  /* ---- карточки операций ---- */

  function opCard(seg) {
    const op = el('div', 'op');
    const head = el('div', 'op-head');
    const kinds = { edit: [tr('ПРАВКА'), 'edit', 'file'], create: [tr('НОВЫЙ'), 'create', 'plus'], delete: [tr('УДАЛЕНИЕ'), 'delete', 'x'], cmd: [tr('КОМАНДА'), 'cmd', 'term'] };
    const k = kinds[seg.type];
    head.append(ico(k[2], 'sm'), el('span', 'op-kind ' + k[1], k[0]), el('span', 'op-path', seg.path || seg.command));
    const state = el('span', 'op-state');
    head.appendChild(state);
    const body = el('div', 'op-body');
    const addLine = (cls, sign, t) => { const l = el('div', 'dl ' + cls); l.append(el('span', 'sg', sign), document.createTextNode(t)); body.appendChild(l); };
    if (seg.type === 'edit') {
      seg.blocks.forEach((b, i) => {
        if (i) addLine('sep', '', '· · ·');
        b.search.split('\n').forEach((t) => addLine('del', '−', t));
        b.replace.split('\n').forEach((t) => addLine('add', '+', t));
      });
      if (!seg.blocks.length) addLine('sep', '', tr('нет SEARCH/REPLACE-блоков'));
    } else if (seg.type === 'create') seg.content.split('\n').forEach((t) => addLine('add', '+', t));
    else if (seg.type === 'cmd') addLine('', '$', seg.command);
    else addLine('del', '−', tr('файл будет удалён'));
    head.addEventListener('click', () => op.classList.toggle('open'));
    if (seg.type === 'delete' || seg.type === 'cmd') op.classList.add('open');
    op.append(head, body);
    return { op, state };
  }

  function addAnswer(ev) {
    const T = S.turn && !S.turn.done ? S.turn : newTurn();
    T.live.classList.add('hidden');
    const box = el('div', 'answer');
    const title = el('div', 'answer-title' + (ev.kind === 'partial' ? ' partial' : ''));
    title.textContent = String(ev.title || tr('Ответ')).replace(/^[^\p{L}\p{N}]+/u, '');
    box.appendChild(title);
    for (const seg of MD.parseOps(ev.text || '')) {
      if (seg.type === 'text') box.appendChild(MD.render(seg.text, (u) => api.openExternal(u)));
      else {
        const c = opCard(seg);
        box.appendChild(c.op);
        if (seg.path) (T.ops[seg.path] = T.ops[seg.path] || []).push(c.state);
      }
    }
    T.answers.appendChild(box);
    scrollDown();
  }

  function addPatch(ev) {
    const T = S.turn && !S.turn.done ? S.turn : newTurn();
    const failed = ev.action === 'FAILED';
    const row = el('div', 'item ' + (failed ? 'fail' : 'good'));
    row.append(ico(failed ? 'x' : 'check', 'sm'), el('span', 'nm', ev.file), el('span', 'st', (ACTION_TEXT[ev.action] || ev.action) + (ev.message ? ' · ' + ev.message : '')));
    T.patches.appendChild(row);
    for (const st of T.ops[ev.file] || []) { st.textContent = failed ? tr('не применено') : tr('применено'); st.className = 'op-state ' + (failed ? 'err' : 'ok'); }
    S.changes.unshift({ file: ev.file, action: ev.action, message: ev.message, at: new Date() });
    renderChanges();
    scrollDown();
  }

  function addNote(kind, text, details) {
    const T = S.turn && !S.turn.done ? S.turn : newTurn();
    const row = el('div', 'item ' + (kind === 'ok' ? 'good' : kind === 'err' ? 'fail' : ''));
    row.append(ico(kind === 'ok' ? 'check' : kind === 'err' ? 'x' : 'term', 'sm'), el('span', 'nm', text));
    T.patches.appendChild(row);
    if (details) {
      const d = el('details', 'logbox'); d.appendChild(el('summary', null, tr('Вывод'))); d.appendChild(el('pre', null, details));
      T.patches.appendChild(d);
    }
    scrollDown();
  }

  function addAsk(ev) {
    if (S.yolo) { api.sessionSend(ev.kind === 'confirm' ? 'y' : (ev.default || 'y')); addSys(tr('Авто-подтверждение: ') + ev.text, 'ok'); return; }
    const T = S.turn && !S.turn.done ? S.turn : newTurn();
    const card = el('div', 'ask');
    card.appendChild(el('div', null, ev.text));
    const btns = el('div', 'ask-btns');
    const done = (txt) => { card.textContent = ''; { const rw = el('div', 'sys'); rw.append(ico('corner', 'sm'), el('span', null, txt)); card.appendChild(rw); } S.askCard = null; };
    if (ev.kind === 'confirm') {
      const yes = el('button', 'btn small primary', tr('Да'));
      const no = el('button', 'btn small', tr('Нет'));
      yes.addEventListener('click', () => { api.sessionSend('y'); done(tr('да')); });
      no.addEventListener('click', () => { api.sessionSend('n'); done(tr('нет')); });
      btns.append(yes, no);
    } else {
      const inp = el('input'); inp.placeholder = tr('y — кодить, n — отмена, или уточнения к плану');
      const ok = el('button', 'btn small primary', tr('Ответить'));
      const go = () => { const v = inp.value.trim() || ev.default || 'y'; api.sessionSend(v); done(v); };
      ok.addEventListener('click', go);
      inp.addEventListener('keydown', (e) => { if (e.key === 'Enter') go(); });
      btns.append(inp, ok);
      setTimeout(() => inp.focus(), 50);
    }
    card.appendChild(btns);
    T.asks.appendChild(card);
    S.askCard = card;
    scrollDown(true);
  }

  /* ================= события CLI ================= */

  function onEvent(ev) {
    switch (ev.t) {
      case 'hello':
        S.hello = ev;
        updateStatusBar();
        break;
      case 'phase':
        if (ev.phase === 'idle') {
          if (S.mode === 'busy' || S.mode === 'booting') {
            if (S.cur && S.cur.silent) { /* служебная команда */ } else finishTurn(S.turn && S.turn.stoppedFlag ? { stopped: true } : undefined);
          }
          S.mode = 'idle'; S.cur = null; S.phase = 'idle';
          renderSession(); updateStatusBar();
          pump();
        } else setPhase(ev.phase);
        break;
      case 'context': onContext(ev); break;
      case 'progress': onProgress(ev); break;
      case 'answer': addAnswer(ev); break;
      case 'patch': addPatch(ev); break;
      case 'cmd':
        if (ev.status === 'run') addNote('', '$ ' + ev.command);
        else if (ev.status === 'ok') addNote('ok', tr('Команда выполнена: ') + ev.command);
        else if (ev.status === 'fail') addNote('err', tr('Команда завершилась с ошибкой (') + ev.code + '): ' + ev.command, ev.output);
        else addNote('', tr('Команда пропущена: ') + ev.command);
        break;
      case 'verify':
        addNote(ev.ok ? 'ok' : 'err', (ev.ok ? tr('Проверка пройдена') : tr('Проверка не пройдена')) + ' · ' + ev.command + ' (' + ev.attempt + '/' + ev.total + ')', ev.output);
        break;
      case 'ask': addAsk(ev); break;
      case 'models': onModels(ev); break;
      case 'stopped':
        if (S.turn) S.turn.stoppedFlag = true;
        finishTurn({ stopped: true });
        break;
      case 'error':
        addSys(ev.text, 'err');
        finishTurn({ failed: true });
        break;
      case 'setting': break;
      case 'attachments': break;
      case 'log': onLog(ev); break;
      default: break;
    }
  }

  function onContext(ev) {
    const T = S.turn && !S.turn.done ? S.turn : newTurn();
    if (ev.mode === 'extra') {
      T.ctxline.classList.remove('hidden');
      T.ctxline.appendChild(el('span', 'tag acc', tr('+ по запросу модели: ') + (ev.extra || []).join(', ')));
      return;
    }
    S.ctxInfo = ev;
    renderContextInspector();
    T.ctxline.textContent = '';
    T.ctxline.classList.remove('hidden');
    const auto = ev.mode === 'auto';
    T.ctxline.appendChild(el('span', 'tag ' + (auto ? 'acc' : ''), auto ? tr('Автоподбор контекста') : tr('Весь проект')));
    T.ctxline.appendChild(el('span', 'tag', fmtNum(ev.files) + (ev.total_files ? tr(' из ') + fmtNum(ev.total_files) : '') + tr(' файлов')));
    if (ev.tokens) T.ctxline.appendChild(el('span', 'tag', '≈ ' + fmtNum(ev.tokens) + tr(' токенов')));
    if (ev.fallback) T.ctxline.appendChild(el('span', 'tag warn', tr('описание неточное — ключевые файлы')));
    $('ctxMini').textContent = '≈ ' + fmtNum(ev.tokens || 0) + tr(' ток. · ') + fmtNum(ev.files || 0) + tr(' файлов');
  }

  function onProgress(ev) {
    const T = S.turn;
    if (!T || T.done || !S.livePreview) return;
    T.live.classList.remove('hidden');
    T.liveMeta.textContent = fmtNum(ev.chars) + tr(' симв. · ') + ev.elapsed + tr(' с');
    const t = String(ev.text || '');
    T.liveText.textContent = t.length > 900 ? '…' + t.slice(-900) : t;
    scrollDown();
  }

  function onLog(ev) {
    addLogLine(ev.level, ev.text);
    const T = S.turn;
    if (T && !T.done) {
      T.logBox.classList.remove('hidden');
      T.logPre.textContent += ev.text + '\n';
    }
    if (ev.level === 'err') addSys(ev.text, 'err');
    else if (ev.level === 'warn') addSys(ev.text, 'warn');
  }

  function addLogLine(level, text) {
    const box = $('iLog');
    const l = el('div', 'logline' + (level ? ' ' + level : ''), text);
    box.appendChild(l);
    if (++S.logCount > 400) { box.firstChild.remove(); S.logCount--; }
    box.scrollTop = box.scrollHeight;
  }

  /* ================= инспектор ================= */

  function renderChanges() {
    const box = $('iChanges');
    box.textContent = '';
    if (!S.changes.length) { box.appendChild(el('div', 'empty', tr('Здесь появятся файлы, которые изменила модель. Откатить последний патч — кнопка «Откат» под полем ввода.'))); return; }
    const list = el('div', 'rowlist');
    for (const c of S.changes.slice(0, 80)) {
      const failed = c.action === 'FAILED';
      const row = el('div', 'item ' + (failed ? 'fail' : 'good'));
      row.append(el('span', 'nm', c.file), el('span', 'st', ACTION_TEXT[c.action] || c.action));
      row.title = c.message || '';
      list.appendChild(row);
    }
    box.appendChild(list);
  }

  function renderContextInspector() {
    const box = $('iContext');
    box.textContent = '';
    const ev = S.ctxInfo;
    if (!ev) { box.appendChild(el('div', 'empty', tr('После первой задачи здесь будет видно, какие файлы ушли в чат и почему.'))); return; }
    box.appendChild(el('div', 'empty', (ev.mode === 'auto' ? tr('Автоподбор: ') : tr('Весь проект: ')) + ev.files + tr(' файл(ов), ≈ ') + fmtNum(ev.tokens || 0) + tr(' токенов') + (ev.note ? '. ' + ev.note : '')));
    for (const f of ev.selected || []) {
      const r = el('div', 'sel-row');
      r.append(el('span', 'nm', f.path), el('span', 'why', f.reason || ''));
      box.appendChild(r);
    }
  }

  /* ================= сессия ================= */

  function renderSession() {
    const pill = $('sessionPill');
    let mode = S.starting ? 'starting' : S.mode;
    pill.classList.remove('on', 'off', 'busy');
    pill.classList.add(mode === 'off' ? 'off' : mode === 'idle' ? 'on' : 'busy');
    const txt = { off: tr('сессия не запущена'), starting: tr('запуск…'), booting: tr('загрузка CLI…'), idle: tr('готов к задаче'), busy: PHASE_TEXT[S.phase] && S.phase !== 'idle' ? PHASE_TEXT[S.phase].replace('…', '') : tr('работает') };
    $('sessionText').textContent = txt[mode];
    $('endSession').classList.toggle('hidden', !S.running);
    const send = $('send');
    const busy = S.mode === 'busy' && !S.askCard;
    send.classList.toggle('stop', busy);
    send.title = busy ? tr('Остановить ответ (Esc)') : tr('Отправить');
    send.textContent = '';
    send.appendChild(icon(busy ? 'stop' : 'send'));
    send.firstChild.setAttribute('class', 'ico');
    send.firstChild.style.width = '18px';
    send.firstChild.style.height = '18px';
    send.disabled = S.starting;
    $('prompt').placeholder = S.askCard ? tr('Ответ для CLI (y / n / текст)…') : tr('Опиши задачу…  (/ — команды)');
  }

  async function startSession() {
    if (!S.project) { toast(tr('Сначала выберите папку проекта'), true); return false; }
    if (S.starting) return false;
    S.starting = true; renderSession();
    addSys(tr('Запуск Vibe CLI…'));
    const r = await api.sessionStart({
      project: S.project, provider: S.provider, model: curModel().trim(), reasoning: S.reasonings[S.provider] || '', yolo: S.yolo, transport: S.transport, human: S.inputMode === 'human',
      autoChrome: S.autoChrome, timeoutMin: S.timeoutMin, autoContext: S.autoContext, promptStyle: S.promptStyle
    });
    S.starting = false;
    if (!r || !r.ok) { addSys((r && r.error) || tr('Не удалось запустить сессию'), 'err'); renderSession(); return false; }
    S.running = true; S.mode = 'booting';
    api.sessionSend('/human ' + (S.inputMode === 'human' ? 'on' : 'off'));
    if (S.autoContext) { api.sessionSend('/autocontext_set ' + S.maxFiles + ' ' + S.budget); }
    renderSession();
    return true;
  }

  function enqueue(text, o) {
    S.outbox.push(Object.assign({ text }, o || {}));
    if (S.mode === 'busy' || S.mode === 'booting') { if (!(o && o.silent)) addSys(tr('Сообщение в очереди — дождёмся завершения текущего шага')); }
    pump();
  }
  function pump() {
    if (S.mode !== 'idle' || !S.outbox.length) return;
    const it = S.outbox.shift();
    S.cur = it;
    S.mode = 'busy';
    if (!it.silent) {
      addUser(it.label || it.text, it.attach);
      newTurn();
    }
    const isCmd = it.text.startsWith('/');
    let out = it.text.replace(/\r?\n/g, ' ⏎ ');
    if (!isCmd && S.plan) out = '/plan ' + out;
    renderSession();
    api.sessionSend(out);
  }
  function silent(cmd) { if (S.running) enqueue(cmd, { silent: true }); }

  /* ================= вложения ================= */

  const ATT_OK = /\.(zip|png|jpe?g|gif|webp|bmp)$/i;
  function attChip(f, onRemove) {
    const c = el('span', 'att');
    c.appendChild(ico(/\.zip$/i.test(f.name) ? 'archive' : 'image', 'sm'));
    c.appendChild(el('span', 'att-n', f.name));
    if (f.size) c.appendChild(el('span', 'att-s', fmtBytes(f.size)));
    if (onRemove) { const x = el('button', 'att-x'); x.title = tr('Убрать'); x.appendChild(ico('x', 'sm')); x.addEventListener('click', onRemove); c.appendChild(x); }
    return c;
  }
  function renderAttach() {
    const t = $('attachTray');
    t.textContent = '';
    t.classList.toggle('hidden', !S.attach.length);
    S.attach.forEach((f, i) => t.appendChild(attChip(f, () => { S.attach.splice(i, 1); renderAttach(); })));
    $('cAttach').classList.toggle('on', S.attach.length > 0);
  }
  function addAttachments(list) {
    for (const f of list) {
      if (!f || !f.path) continue;
      if (!ATT_OK.test(f.name)) { toast(tr('Нельзя прикрепить «') + f.name + tr('»: только zip и изображения'), true); continue; }
      if (f.size > 25 * 1048576) { toast('«' + f.name + tr('» больше 25 МБ'), true); continue; }
      if (!S.attach.some((a) => a.path === f.path)) S.attach.push({ path: f.path, name: f.name, size: f.size || 0 });
    }
    renderAttach();
  }
  async function ingestFiles(fileList) {
    const out = [];
    for (const f of fileList) {
      let p = api.pathForFile(f);
      if (!p) { const r = await api.saveTemp(f.name || ('image-' + Date.now() + '.png'), new Uint8Array(await f.arrayBuffer())); p = r && r.path; }
      if (p) out.push({ path: p, name: f.name || p.split(/[\\/]/).pop(), size: f.size });
    }
    addAttachments(out);
  }
  function initAttach() {
    $('cAttach').addEventListener('click', async () => { addAttachments(await api.pickFiles()); });
    const wrap = document.querySelector('.composer-wrap'), comp = document.querySelector('.composer');
    let depth = 0;
    window.addEventListener('dragenter', (e) => { if (e.dataTransfer && [...e.dataTransfer.types].includes('Files')) { depth++; comp.classList.add('drag'); } });
    window.addEventListener('dragleave', () => { depth = Math.max(0, depth - 1); if (!depth) comp.classList.remove('drag'); });
    window.addEventListener('dragover', (e) => e.preventDefault());
    window.addEventListener('drop', (e) => { e.preventDefault(); depth = 0; comp.classList.remove('drag'); if (e.dataTransfer && e.dataTransfer.files.length) ingestFiles([...e.dataTransfer.files]); });
    $('prompt').addEventListener('paste', (e) => {
      const files = [...(e.clipboardData ? e.clipboardData.files : [])];
      if (files.length) { e.preventDefault(); ingestFiles(files); }
    });
    void wrap;
  }

  async function send(raw) {
    const text = String(raw || '').replace(/\s+$/, '');
    if (!text.trim()) return;
    if (S.askCard && S.mode === 'busy') { api.sessionSend(text); S.askCard.textContent = ''; { const rw = el('div', 'sys'); rw.append(ico('corner', 'sm'), el('span', null, text)); S.askCard.appendChild(rw); } S.askCard = null; renderSession(); return; }
    if (!S.running && !(await startSession())) return;
    const files = S.attach.splice(0); renderAttach();
    for (const f of files) enqueue('/attach ' + f.path, { silent: true });
    enqueue(text, files.length ? { attach: files } : null);
  }

  function stopGeneration() {
    if (S.mode !== 'busy') return;
    api.generationStop();
    if (S.turn && !S.turn.done) { S.turn.label.textContent = tr('Останавливаю…'); S.turn.stopBtn.disabled = true; }
  }

  function onExit(p) {
    finishTurn({ failed: !!(p && p.code) });
    S.running = false; S.starting = false; S.mode = 'off'; S.outbox = []; S.askCard = null; S.phase = 'idle';
    renderSession(); updateStatusBar();
    addSys(tr('Сессия завершена') + (p && p.code != null ? tr(' (код ') + p.code + ')' : '') + (p && p.error ? ': ' + p.error : ''), p && p.code ? 'err' : '');
    if (S.reloadOnExit) { location.reload(); return; }
    if (p && p.code) addSys(tr('Если CLI закрылся при старте — проверьте зависимости: pip install -r requirements.txt'), 'warn');
  }

  /* ================= статус Chrome ================= */

  const portOf = (url) => { try { return new URL(url).port || ''; } catch (_) { return ''; } };

  function renderStatus(s) {
    S.vibeRoot = s.vibeRoot; S.python = s.python;
    for (const k of Object.keys(PROVIDERS)) S.cdp[k] = s.cdp[k] || S.cdp[k];
    updateStatusBar();
    if ($('sConnect').firstChild) buildConnect();
  }
  /* ================= списки моделей: кэш в JSON + автообновление ================= */

  const agoText = (t) => { const m = Math.round((Date.now() - t) / 60000); return m < 1 ? tr('только что') : m < 60 ? m + tr(' мин назад') : Math.round(m / 60) + tr(' ч назад'); };

  async function refreshModels(provider, quiet) {
    if (!S.project) { if (!quiet) toast(tr('Сначала выберите папку проекта'), true); return false; }
    if (!(S.cdp[provider] || {}).online) { if (!quiet) toast(tr('Chrome для ') + PROVIDERS[provider].title + tr(' не запущен'), true); return false; }
    S.lastTry[provider] = Date.now();
    const r = await api.listModels({ project: S.project, provider });
    if (r && r.ok && r.models && r.models.entries && r.models.entries.length) { onModels(r.models); return true; }
    if (!quiet) toast((r && (r.error || (r.models && r.models.error))) || tr('Не удалось прочитать список моделей'), true);
    return false;
  }
  async function refreshAllModels(force, quiet) {
    if (S.refreshing || !S.project || S.mode === 'busy' || S.mode === 'booting') return;
    S.refreshing = true;
    try {
      for (const p of Object.keys(PROVIDERS)) {
        const c = S.liveModels[p];
        const stale = !c || (S.modelsRefreshMin > 0 && Date.now() - c.at > S.modelsRefreshMin * 60000);
        if (!force && (!stale || Date.now() - (S.lastTry[p] || 0) < 300000)) continue;
        await refreshModels(p, quiet);
      }
    } finally {
      S.refreshing = false;
      if (S.modelPop.open) renderModelPop();
    }
  }

  // автозапуск батников при старте IDE
  async function autoStart() {
    if (!S.vibeRoot) return;
    if (S.autoBat !== 'off') {
      const provs = S.autoBat === 'all' ? ['gemini', 'claude'] : [S.provider === 'claude' ? 'claude' : 'gemini'];
      for (const p of provs) if (!(S.cdp[p] || {}).online) api.launchChrome(p, S.project);
    }
    for (const line of String(S.startScripts || '').split('\n').map((x) => x.trim()).filter(Boolean)) {
      const r = await api.runScript(line);
      if (r && !r.ok) addSys(r.error, 'warn');
    }
    setTimeout(pollStatus, 4000);
  }

  async function pollStatus() {
    if (document.hidden) return;
    try { renderStatus(await api.status(S.project)); } catch (_) { /* ignore */ }
  }
  async function launchChrome(provider) {
    if (!S.vibeRoot) { toast(tr('Не найден Vibe CLI — укажите папку в Настройки → Подключение'), true); return; }
    toast(tr('Запускаю Chrome…'));
    const r = await api.launchChrome(provider, S.project);
    if (r && r.ok) toast(r.already ? tr('Chrome уже запущен') : tr('Chrome запущен — войдите в аккаунт, если нужно'));
    else toast((r && r.error) || tr('Не удалось запустить Chrome'), true);
    pollStatus();
  }

  function updateStatusBar() {
    const online = S.cdp[S.provider] && S.cdp[S.provider].online;
    $('chipText').textContent = provTitle() + ' · ' + (curModel() || tr('авто'));
    $('chipDot').className = 'dot ' + (online ? 'on' : 'off');
    $('cModelText').textContent = curModel() || provTitle();
    $('cAuto').classList.toggle('on', S.autoContext);
    $('cPlan').classList.toggle('on', S.plan);
    $('sbChrome').firstChild.className = 'dot ' + (online ? 'on' : 'off');
    $('sbChrome').lastChild.textContent = 'Chrome ' + (online ? tr('подключён') : tr('не запущен'));
    $('sbModel').textContent = provTitle() + ' · ' + (curModel() || tr('модель по умолчанию'));
    $('sbAuto').textContent = tr('Автоконтекст: ') + (S.autoContext ? tr('вкл') : tr('выкл'));
    if (S.mode !== 'busy') $('sbPhase').textContent = S.running ? tr('готов') : tr('сессия не запущена');
    $('sbPath').textContent = S.project || '';
    $('modelChip').classList.toggle('on', S.modelPop.open);
  }

  /* ================= модели ================= */

  const DEFAULT_LEVELS = [['', tr('авто')], ['low', 'low'], ['medium', 'mid'], ['high', 'high'], ['off', 'off']];
  // уровни рассуждений: если список прочитан с сайта — показываем именно его, а не запомненный
  function levelOptions(provider) {
    const lv = (S.liveModels[provider] || {}).levels;
    return lv && lv.length ? [['', tr('авто')]].concat(lv.map((l) => [l, l])) : DEFAULT_LEVELS;
  }

  // Только то, что прочитано с сайта. Запомненного списка нет — до первой загрузки список пуст.
  function modelEntries(provider) {
    const live = S.liveModels[provider];
    return live && live.entries ? live.entries.map((e) => ({ id: e.name, name: e.name, desc: e.desc || '', live: true })) : [];
  }

  function onModels(ev) {
    if (ev.entries && ev.entries.length) { S.liveModels[ev.provider] = { entries: ev.entries, levels: ev.levels || [], at: Date.now() }; api.modelsCacheSet(S.liveModels); if (S.modelPop.open) renderModelPop(); }
  }

  let popAbove = true;
  function openModelPop(anchor, above) {
    popAbove = above;
    S.modelPop = { open: true, provider: S.provider, q: '' };
    renderModelPop();
    const pop = $('modelPop');
    pop.classList.remove('hidden');
    const r = anchor.getBoundingClientRect();
    const h = pop.getBoundingClientRect().height;
    pop.style.left = Math.max(8, Math.min(r.left, window.innerWidth - 412)) + 'px';
    pop.style.top = (above ? Math.max(8, r.top - h - 8) : r.bottom + 8) + 'px';
    updateStatusBar();
    const si = pop.querySelector('.pop-search input');
    if (si) si.focus();
  }
  function closeModelPop() { S.modelPop.open = false; $('modelPop').classList.add('hidden'); updateStatusBar(); }

  function renderModelPop() {
    const pop = $('modelPop');
    pop.textContent = '';
    const P = S.modelPop;
    const tabs = el('div', 'pop-tabs');
    for (const k of Object.keys(PROVIDERS)) {
      const b = el('button', 'pop-tab' + (k === P.provider ? ' active' : ''), PROVIDERS[k].title);
      b.addEventListener('click', () => { P.provider = k; P.q = ''; renderModelPop(); });
      tabs.appendChild(b);
    }
    const search = el('div', 'pop-search');
    const inp = el('input'); inp.placeholder = P.provider === 'aistudio' ? tr('Поиск модели (список — с сайта)…') : tr('Поиск модели…'); inp.value = P.q;
    inp.addEventListener('input', () => { P.q = inp.value; renderList(); });
    inp.addEventListener('keydown', (e) => { if (e.key === 'Enter') { const f = list.querySelector('.mrow:nth-child(2)'); if (f) f.click(); } if (e.key === 'Escape') closeModelPop(); });
    search.appendChild(inp);
    const list = el('div', 'pop-list');
    function renderList() {
      list.textContent = '';
      const q = P.q.trim().toLowerCase();
      const items = modelEntries(P.provider).filter((m) => !q || (m.name + ' ' + m.id + ' ' + m.desc).toLowerCase().includes(q));
      const sel = S.models[P.provider];
      list.appendChild(rowFor({ id: '', name: tr('По умолчанию'), desc: tr('Модель, выбранная на сайте') }, !sel && P.provider === S.provider));
      for (const m of items) list.appendChild(rowFor(m, sel === m.id && P.provider === S.provider));
      if (!items.length) {
        const e = el('div', 'pop-empty');
        const on = (S.cdp[P.provider] || {}).online;
        e.appendChild(el('b', null, q ? tr('Ничего не найдено') : tr('Список моделей ещё не загружен')));
        e.appendChild(el('span', null, q ? tr('Проверьте запрос') : (on ? tr('Читаю список с сайта… можно нажать «Обновить с сайта»') : tr('Запустите Chrome для ') + PROVIDERS[P.provider].title + tr(' (Настройки → Подключение) — список загрузится сам'))));
        list.appendChild(e);
      }
    }
    function rowFor(m, selected) {
      const b = el('button', 'mrow' + (selected ? ' sel' : ''));
      const info = el('div', 'mi');
      info.append(el('div', 'mn', m.name));
      if (m.desc) info.appendChild(el('div', 'md2', m.desc));
      if (m.id && m.id !== m.name) info.appendChild(el('div', 'mid', m.id));
      b.appendChild(info);
      if (selected) b.appendChild(ico('check', 'sm'));
      b.addEventListener('click', () => pickModel(P.provider, m.id));
      return b;
    }
    renderList();
    const foot = el('div', 'pop-foot');
    const refresh = el('button', 'btn small');
    refresh.append(ico('refresh', 'sm'), document.createTextNode(tr(' Обновить с сайта')));
    refresh.addEventListener('click', async () => {
      refresh.disabled = true;
      toast(tr('Читаю список моделей со страницы…'));
      const ok = await refreshModels(P.provider, false);
      if (ok) toast(tr('Список моделей обновлён'));
      refresh.disabled = false;
      if (S.modelPop.open) renderModelPop();
    });
    foot.appendChild(refresh);
    const at = (S.liveModels[P.provider] || {}).at;
    if (at) foot.appendChild(el('span', 'hint', tr('обновлено ') + agoText(at)));
    {
      foot.appendChild(el('span', 'hint', tr('Рассуждения:')));
      const seg = el('div', 'seg');
      for (const [v, n] of levelOptions(P.provider)) {
        const b = el('button', (S.reasonings[P.provider] || '') === v ? 'active' : '', n);
        b.addEventListener('click', () => {
          S.reasonings[P.provider] = v; saveSettings();
          if (P.provider === S.provider && v) silent('/reasoning ' + v);
          renderModelPop();
        });
        seg.appendChild(b);
      }
      foot.appendChild(seg);
    }
    pop.append(tabs, search, list, foot);
  }

  function pickModel(provider, id) {
    const providerChanged = provider !== S.provider;
    S.provider = provider;
    S.models[provider] = id;
    saveSettings();
    closeModelPop();
    updateStatusBar(); buildConnect(); syncControls();
    if (providerChanged && S.running) {
      api.sessionStop();
      toast(tr('Сессия перезапустится с провайдером ') + provTitle());
    } else if (S.running && id) silent('/model ' + id + ((S.reasonings[provider] || '') ? ' ' + S.reasonings[provider] : ''));
    pollStatus(); schedulePreview();
  }

  /* ================= проект и контекст (дерево) ================= */

  function renderRecents() { /* список последних проектов — в меню проекта (по клику на пилюлю) */ }

  async function openProject(root) {
    if (S.running) { await api.sessionStop(); toast(tr('Сессия остановлена — сменился проект')); }
    S.project = root;
    S.recents = [root, ...S.recents.filter((x) => x !== root)].slice(0, 8);
    S.cache = new Map(); S.expanded = new Set(); S.changes = [];
    saveSettings();
    $('projectName').textContent = baseName(root);
    $('projectPill').title = root;
    renderChanges(); updateStatusBar();
    await loadIgnore(); await refreshTree(); schedulePreview(); pollStatus();
  }
  async function chooseFolder() {
    const folder = await api.pickFolder();
    if (folder) await openProject(folder);
  }

  async function loadDir(rel, force) {
    if (!force && S.cache.has(rel)) return S.cache.get(rel);
    let list = [];
    try { list = await api.listDir(S.project, rel); } catch (_) { list = []; }
    S.cache.set(rel, list);
    return list;
  }
  async function refreshTree() {
    if (!S.project) return;
    await loadDir('', true);
    await Promise.all([...S.expanded].map((r) => loadDir(r, true)));
    renderTree();
  }
  function renderTree() {
    const tree = $('tree'), scroll = tree.scrollTop;
    tree.textContent = '';
    if (!S.project) { tree.appendChild(el('div', 'hint', tr('Выберите папку проекта'))); return; }
    const frag = document.createDocumentFragment();
    addLevel('', 0, false, frag);
    tree.appendChild(frag);
    tree.scrollTop = scroll;
  }
  function addLevel(rel, depth, parentOff, frag) {
    const entries = S.cache.get(rel);
    if (!entries) return;
    if (!entries.length && depth === 0) { frag.appendChild(el('div', 'hint', tr('Папка пуста'))); return; }
    for (const e of entries) {
      const r = rel ? rel + '/' + e.name : e.name;
      const off = parentOff || !!e.state;
      frag.appendChild(buildRow(e, r, depth, off, parentOff));
      if (e.isDir && S.expanded.has(r)) addLevel(r, depth + 1, off, frag);
    }
  }
  const TAGS = { builtin: tr('АВТО'), git: 'GIT', user: tr('ИСКЛ.') };
  function buildRow(e, r, depth, off, parentOff) {
    const row = el('div', 'row' + (e.isDir ? ' dir' : '') + (off ? ' off' : ''));
    row.style.paddingLeft = (10 + depth * 18) + 'px';
    const caret = el('span', 'caret' + (e.isDir ? '' : ' none'), e.isDir ? (S.expanded.has(r) ? '▾' : '▸') : '▸');
    if (e.isDir) caret.addEventListener('click', () => toggleExpand(r));
    const cb = el('span', 'cb'); cb.appendChild(ico('check', 'sm'));
    cb.title = off ? tr('Включить в контекст') : tr('Исключить из контекста');
    cb.addEventListener('click', () => toggleExclude(e, r, parentOff));
    const name = el('span', 'name', e.name);
    name.title = r;
    name.addEventListener('click', () => (e.isDir ? toggleExpand(r) : toggleExclude(e, r, parentOff)));
    row.append(caret, cb, el('span', 'ico2', e.isDir ? (S.expanded.has(r) ? '📂' : '📁') : '📄'), name);
    if (e.state) row.appendChild(el('span', 'rtag', TAGS[e.state] || tr('ИСКЛ.')));
    if (!e.isDir) row.appendChild(el('span', 'size', fmtBytes(e.size)));
    return row;
  }
  async function toggleExpand(r) {
    if (S.expanded.has(r)) S.expanded.delete(r); else { S.expanded.add(r); await loadDir(r); }
    renderTree();
  }
  async function toggleExclude(e, r, parentOff) {
    if (parentOff && !e.state) { toast(tr('Родительская папка исключена — сначала включите её'), true); return; }
    if (e.state === 'builtin') { toast(tr('Встроенное правило Vibe CLI — его нельзя снять здесь'), true); return; }
    if (e.state === 'git') { toast(tr('Исключено через .gitignore проекта'), true); return; }
    const key = '/' + r + (e.isDir ? '/' : '');
    if (e.state === 'user') {
      const hit = [key, e.name + (e.isDir ? '/' : ''), e.name, '/' + r].find((a) => S.managed.has(a));
      if (!hit) { toast(tr('Правило задано вручную в .vibeignore или .vibe.json'), true); return; }
      S.managed.delete(hit);
    } else S.managed.add(key);
    await saveManaged();
  }
  async function loadIgnore() {
    let r = { managed: [] };
    try { r = await api.ignoreGet(S.project); } catch (_) { /* ignore */ }
    S.managed = new Set(r.managed || []);
    renderChips();
  }
  async function saveManaged() {
    const r = await api.ignoreSet(S.project, [...S.managed]);
    if (!r || !r.ok) toast(tr('Не удалось записать .vibeignore: ') + ((r && r.error) || ''), true);
    renderChips(); await refreshTree(); schedulePreview();
  }
  const SUGGEST = ['*.log', '*.csv', '*.md', 'docs/', 'tests/', '.vibeide/'];
  function renderChips() {
    const box = $('chips');
    box.textContent = '';
    for (const p of [...S.managed].sort()) {
      const chip = el('span', 'chipx');
      chip.appendChild(el('span', null, p));
      const x = el('button', null, '×'); x.type = 'button'; x.title = tr('Убрать правило');
      x.addEventListener('click', () => { S.managed.delete(p); saveManaged(); });
      chip.appendChild(x); box.appendChild(chip);
    }
    if (!S.managed.size) box.appendChild(el('span', 'hint', tr('Своих правил пока нет')));
    const sug = $('suggest');
    sug.textContent = '';
    for (const s of SUGGEST.filter((x) => !S.managed.has(x))) {
      const b = el('button', 'sug', '+ ' + s); b.type = 'button';
      b.addEventListener('click', () => { S.managed.add(s); saveManaged(); });
      sug.appendChild(b);
    }
  }
  let previewTimer = null, previewSeq = 0;
  function schedulePreview() { clearTimeout(previewTimer); previewTimer = setTimeout(runPreview, 200); }
  async function runPreview() {
    if (!S.project) return;
    const seq = ++previewSeq;
    let info;
    try { info = await api.preview(S.project); } catch (_) { return; }
    if (seq === previewSeq) renderInfo(info);
  }
  function renderInfo(info) {
    $('stFiles').textContent = fmtNum(info.files);
    $('stSize').textContent = fmtBytes(info.bytes);
    $('stTokens').textContent = fmtNum(info.tokens);
    const limit = S.provider === 'claude' ? 200000 : 1000000;
    const ratio = info.tokens / limit;
    const fill = $('meterFill');
    fill.style.width = Math.min(100, ratio * 100).toFixed(1) + '%';
    fill.classList.toggle('warn', ratio >= 0.6 && ratio < 1);
    fill.classList.toggle('bad', ratio >= 1);
    $('meterNote').textContent = '≈ ' + Math.round(ratio * 100) + tr('% окна ') + (S.provider === 'claude' ? 'Claude' : 'Gemini') + ' (' + fmtNum(limit / 1000) + tr('k токенов)');
    const s = info.skipped || {}, parts = [];
    if (s.binary) parts.push(tr('бинарных: ') + s.binary);
    if (s.large) parts.push(tr('больших: ') + s.large);
    if (s.unreadable) parts.push(tr('нечитаемых: ') + s.unreadable);
    $('stSkipped').textContent = parts.length ? tr('Пропущено — ') + parts.join(' · ') : '';
    $('autoNote').textContent = S.autoContext
      ? tr('Автоподбор включён: в чат уходят не все файлы, а до ') + S.maxFiles + tr(' файлов (≈ ') + fmtNum(S.budget) + tr(' токенов), нужных для задачи.')
      : '';
    if (!S.ctxInfo) $('ctxMini').textContent = '≈ ' + fmtNum(info.tokens) + tr(' ток. · ') + fmtNum(info.files) + tr(' файлов');
    const top = $('top');
    top.textContent = '';
    const max = info.top.length ? info.top[0].size : 1;
    for (const t of info.top) {
      const item = el('div', 'top-item'), line = el('div', 'top-name');
      const a = el('span', null, t.rel); a.title = t.rel;
      line.append(a, el('span', null, fmtBytes(t.size)));
      const bar = el('div', 'top-bar'), f = el('div');
      f.style.width = Math.max(3, (t.size / max) * 100).toFixed(1) + '%';
      bar.appendChild(f); item.append(line, bar); top.appendChild(item);
    }
  }

  /* ================= настройки ================= */

  function group(title, sub) {
    const g = el('div', 'sgroup');
    g.appendChild(el('h3', null, title));
    if (sub) g.appendChild(el('div', 'sub', sub));
    return g;
  }
  function srow(title, desc, control, cls) {
    const r = el('div', 'srow' + (cls ? ' ' + cls : ''));
    const t = el('div', 't'); t.appendChild(el('b', null, title)); if (desc) t.appendChild(el('span', null, desc));
    r.append(t, control);
    return r;
  }
  function toggleCtl(key, onchange) {
    const w = el('label', 'switch');
    const i = el('input'); i.type = 'checkbox'; i.checked = !!S[key];
    i.addEventListener('change', () => { S[key] = i.checked; saveSettings(); if (onchange) onchange(i.checked); });
    w.append(i, el('i'));
    return w;
  }
  function selectCtl(key, options, onchange) {
    const s = el('select');
    for (const [v, n] of options) { const o = el('option', null, n); o.value = v; s.appendChild(o); }
    s.value = String(S[key]);
    s.addEventListener('change', () => { S[key] = s.value; saveSettings(); if (onchange) onchange(s.value); });
    return s;
  }
  function numberCtl(key, min, max, step, onchange) {
    const i = el('input'); i.type = 'number'; i.min = min; i.max = max; i.step = step; i.value = S[key];
    i.addEventListener('change', () => { S[key] = Math.min(max, Math.max(min, Number(i.value) || min)); i.value = S[key]; saveSettings(); if (onchange) onchange(S[key]); });
    return i;
  }
  function rangeCtl(key, min, max, step, fmt, onchange) {
    const w = el('div'); w.style.display = 'flex'; w.style.alignItems = 'center'; w.style.gap = '10px';
    const i = el('input'); i.type = 'range'; i.min = min; i.max = max; i.step = step; i.value = S[key];
    const v = el('span', 'val', fmt(S[key]));
    i.addEventListener('input', () => { S[key] = Number(i.value); v.textContent = fmt(S[key]); if (onchange) onchange(S[key]); });
    i.addEventListener('change', saveSettings);
    w.append(i, v);
    return w;
  }

  function buildLook() {
    const box = $('sLook');
    box.textContent = '';
    const g1 = group(tr('Тема'), tr('Светлые и тёмные темы. «Системная» следует настройкам операционной системы.'));
    const grid = el('div', 'theme-grid');
    for (const t of THEMES) {
      const b = el('button', 'tcard' + (S.theme === t.id ? ' active' : ''));
      b.setAttribute('data-theme', t.id === 'system' ? resolvedTheme() : t.id);
      const prev = el('div', 'tprev');
      prev.append(el('div', 'a'));
      const bb = el('div', 'b'); bb.append(el('i'), el('i'), el('i'));
      prev.appendChild(bb);
      const nm = el('div', 'tname', t.name); nm.appendChild(el('span', null, t.sub));
      b.append(prev, nm);
      b.addEventListener('click', () => { S.theme = t.id; saveSettings(); applyTheme(); buildLook(); });
      grid.appendChild(b);
    }
    g1.appendChild(grid);
    const g2 = group(tr('Акцентный цвет'), tr('Цвет кнопок, выделений и логотипа. «Авто» — цвет выбранной темы.'));
    const sw = el('div', 'swatches');
    for (const c of ACCENTS) {
      const b = el('button', 'sw' + (S.accent === c ? ' active' : '') + (c ? '' : ' auto'));
      if (c) b.style.background = c;
      b.title = c || tr('Авто');
      b.addEventListener('click', () => { S.accent = c; saveSettings(); applyTheme(); buildLook(); });
      sw.appendChild(b);
    }
    g2.appendChild(sw);
    const g3 = group(tr('Интерфейс'));
    g3.appendChild(srow(tr('Плотность'), tr('Расстояния между элементами'), selectCtl('density', [['compact', tr('Компактная')], ['standard', tr('Обычная')], ['cozy', tr('Просторная')]], applyTheme)));
    g3.appendChild(srow(tr('Размер шрифта'), tr('Основной текст интерфейса'), rangeCtl('fontSize', 12, 18, 1, (v) => v + ' px', () => applyTheme())));
    g3.appendChild(srow(tr('Скругление углов'), tr('Карточки, кнопки и поля'), rangeCtl('radius', 4, 20, 1, (v) => v + ' px', () => applyTheme())));
    g3.appendChild(srow(tr('Ширина чата'), tr('Максимальная ширина колонки с сообщениями'), rangeCtl('chatWidth', 640, 1200, 20, (v) => v + ' px', () => applyTheme())));
    const g4 = group(tr('Эффекты'));
    g4.appendChild(srow(tr('Фон с частицами'), tr('Лёгкая анимация на заднем плане'), toggleCtl('fx', applyTheme)));
    g4.appendChild(srow(tr('Анимации интерфейса'), tr('Плавные переходы, пульсация статуса'), toggleCtl('motion', applyTheme)));
    const g0 = group(tr('Язык'), tr('Язык интерфейса IDE и сообщений Vibe CLI. Применяется сразу.'));
    const ls = el('select');
    for (const [v, n] of [['en', 'English'], ['ru', tr('Русский')]]) { const o = el('option', null, n); o.value = v; ls.appendChild(o); }
    ls.value = window.VIBE_LANG;
    ls.addEventListener('change', () => applyLanguage(ls.value));
    g0.appendChild(srow(tr('Язык'), '', ls));
    box.append(g0, g1, g2, g3, g4);
  }

  // Смена языка: CLI переключается сразу командой /lang, окно перезагружается (если идёт сессия — после её завершения).
  function applyLanguage(v) {
    window.setLang(v);
    api.setLang(v);
    silent('/lang ' + v);
    if (S.running) { S.reloadOnExit = true; toast(tr('Язык сменится после завершения сессии')); } else location.reload();
  }

  function buildFeatures() {
    const box = $('sFeatures');
    box.textContent = '';
    const g1 = group(tr('Контекст'), tr('Что именно уходит в чат вместе с задачей.'));
    g1.appendChild(srow(tr('Автоматический подбор контекста по описанию'), tr('В чат отправляются не все файлы проекта, а только те, что нужны для правки: по словам из задачи, именам файлов и импортам. Если модели не хватит файла, она сама его запросит.'),
      toggleCtl('autoContext', (v) => { silent('/autocontext ' + (v ? 'on' : 'off')); buildFeatures(); updateStatusBar(); schedulePreview(); })));
    const dis = S.autoContext ? '' : 'disabled';
    g1.appendChild(srow(tr('Максимум файлов'), tr('Верхняя граница числа файлов в контексте'), numberCtl('maxFiles', 3, 120, 1, () => silent('/autocontext_set ' + S.maxFiles + ' ' + S.budget)), 'sub ' + dis));
    g1.appendChild(srow(tr('Бюджет контекста, токенов'), tr('Подбор остановится, когда лимит будет исчерпан'), numberCtl('budget', 5000, 400000, 5000, () => silent('/autocontext_set ' + S.maxFiles + ' ' + S.budget)), 'sub ' + dis));
    const g2 = group(tr('Работа модели'));
    g2.appendChild(srow(tr('Показывать ход работы модели'), tr('Статусы «думает», «отвечает», шаги и таймер в карточке ответа'), toggleCtl('showThink', () => setPhase(S.phase))));
    g2.appendChild(srow(tr('Живой предпросмотр ответа'), tr('Показывать текст по мере генерации, до применения патчей'), toggleCtl('livePreview')));
    g2.appendChild(srow(tr('Сначала план'), tr('Перед кодом модель составляет план, и вы его утверждаете'), toggleCtl('plan', updateStatusBar)));
    g2.appendChild(srow(tr('Без подтверждений'), tr('Планы утверждаются, а команды выполняются автоматически. Применяется сразу, без перезапуска'), toggleCtl('yolo', (v) => { silent('/yolo ' + (v ? 'on' : 'off')); })));
    g2.appendChild(srow(tr('Уведомлять о завершении'), tr('Системное уведомление, когда окно свёрнуто'), toggleCtl('notify')));
    g2.appendChild(srow(tr('Ждать ответ ИИ, минут'), tr('До 180. Действует с новой сессии'), numberCtl('timeoutMin', 1, 180, 5, () => { if (S.running) toast(tr('Применится после перезапуска сессии')); })));
    const g3 = group(tr('Промпты и отправка'), tr('Текст сообщения для чата каждый раз другой и зависит от типа задачи (баг, фича, рефакторинг…). Формат патчей всегда один.'));
    g3.appendChild(srow(tr('Тексты промптов'), tr('«Авто» — новые формулировки на каждый запрос; «Классика» — фиксированный текст'), selectCtl('promptStyle', STYLES, (v) => silent('/promptstyle ' + v))));
    g3.appendChild(srow(tr('Формат отправки контекста'), (TRANSPORT_DESC[S.transport] || '') + tr('. Действует с нового чата'), selectCtl('transport', TRANSPORTS, (v) => { silent('/transport ' + v); buildFeatures(); })));
    const g4 = group(tr('Подключение'));
    g4.appendChild(srow(tr('Автозапуск Chrome при старте сессии'), tr('Если Chrome с отладкой не запущен — стартует батник'), toggleCtl('autoChrome')));
    g4.appendChild(srow(tr('Автозапуск батников при старте IDE'), tr('Сразу после открытия IDE запускается scripts/start_chrome_*.bat'), selectCtl('autoBat', [['off', tr('Выключен')], ['sel', tr('Chrome выбранного провайдера')], ['all', tr('Chrome Gemini и Claude')]])));
    g4.appendChild(srow(tr('Способ подключения к чату'), S.inputMode === 'human'
      ? tr('Humanize: курсор идёт по кривой, текст печатается с неровным ритмом, перед отправкой есть пауза. Сообщение занимает на несколько секунд дольше. Связь с Chrome по-прежнему CDP, но это не гарантия, что сервис не заметит автоматизацию')
      : tr('CDP: быстрое управление страницей, как в Playwright (курсор прыгает в центр кнопки, текст вставляется целиком)'),
      selectCtl('inputMode', [['cdp', tr('CDP (быстро)')], ['human', tr('Humanize (человекоподобно)')]], (v) => { silent('/human ' + (v === 'human' ? 'on' : 'off')); if (S.running) toast(tr('Применено к текущей сессии')); buildFeatures(); })));
    const ta = el('textarea'); ta.rows = 3; ta.placeholder = 'scripts/my.bat\nC:\\tools\\run.bat'; ta.value = S.startScripts || ''; ta.className = 'input';
    ta.addEventListener('change', () => { S.startScripts = ta.value; saveSettings(); });
    g4.appendChild(srow(tr('Свои скрипты при старте IDE'), tr('По одному пути в строке (.bat). Относительные пути — от папки Vibe'), ta, 'col'));
    const g5 = group(tr('Списки моделей'), tr('Названия моделей и уровней рассуждений всегда читаются с сайта и сохраняются в models-cache.json — перезагружать их вручную не нужно.'));
    g5.appendChild(srow(tr('Автообновление, минут'), tr('0 — не обновлять автоматически. Для этого Chrome должен быть запущен'), numberCtl('modelsRefreshMin', 0, 1440, 5)));
    const rb = el('button', 'btn small', tr('Обновить сейчас'));
    rb.addEventListener('click', async () => { rb.disabled = true; toast(tr('Читаю списки моделей со страниц…')); await refreshAllModels(true, false); rb.disabled = false; toast(tr('Готово')); });
    g5.appendChild(srow(tr('Обновить списки сейчас'), tr('Gemini, Claude и AI Studio по очереди'), rb));
    box.append(g1, g2, g3, g4, g5);
  }

  function buildConnect() {
    const box = $('sConnect');
    box.textContent = '';
    const g = group(tr('Браузеры ИИ'), tr('Vibe управляет вашим Chrome: вход в аккаунт нужен один раз. Gemini и AI Studio используют один Google-аккаунт и по умолчанию один Chrome (порт 9222).'));
    for (const k of Object.keys(PROVIDERS)) {
      const info = S.cdp[k] || {};
      const c = el('div', 'conn');
      c.appendChild(el('i', 'dot ' + (info.online ? 'on' : 'off')));
      const t = el('div', 't'); t.append(el('b', null, PROVIDERS[k].title + (S.provider === k ? tr(' · выбран') : '')), el('span', null, (info.url || '') + (info.online ? tr(' · подключён') : tr(' · не запущен'))));
      const b = el('button', 'btn small', info.online ? tr('Подключён') : tr('Запустить Chrome'));
      b.disabled = !!info.online;
      b.addEventListener('click', () => launchChrome(k));
      const sel = el('button', 'btn small ghost', tr('Выбрать'));
      sel.addEventListener('click', () => { if (S.provider !== k) pickModel(k, S.models[k] || ''); });
      c.append(t, sel, b);
      g.appendChild(c);
    }
    const g2 = group('Vibe CLI');
    const c2 = el('div', 'conn');
    const t2 = el('div', 't'); t2.append(el('b', null, S.vibeRoot || tr('не найден')), el('span', null, S.python ? 'Python: ' + S.python : tr('Укажите папку, где лежит vibe.py')));
    const pb = el('button', 'btn small', tr('Указать папку'));
    pb.addEventListener('click', async () => { const r = await api.pickVibeRoot(); if (r && r.ok) { toast('Vibe CLI: ' + r.root); pollStatus(); } else if (r && r.error) toast(r.error, true); });
    c2.append(t2, pb);
    g2.appendChild(c2);
    box.append(g, g2);
  }

  function buildAbout() {
    const box = $('sAbout');
    box.textContent = '';
    const a = el('div', 'about');
    const logo = el('canvas', 'vibi-cv'); Vibi(logo, 8).animate(S.motion);
    a.append(logo, el('h2', null, 'Vibe IDE ' + VERSION), el('div', 'hint', tr('Оболочка для Vibe CLI: чат с ИИ по подписке (Gemini, Claude, Google AI Studio), подбор контекста, патчи и проверка сборки.')));
    box.appendChild(a);
  }

  /* ================= привязка интерфейса ================= */

  function switchView(v) {
    for (const b of document.querySelectorAll('.act')) b.classList.toggle('active', b.dataset.view === v);
    $('viewChat').classList.toggle('active', v === 'chat');
    $('viewCtx').classList.toggle('active', v === 'ctx');
    $('viewSettings').classList.toggle('active', v === 'settings');
    if (v === 'ctx') { refreshTree(); schedulePreview(); }
    if (v === 'settings') { buildLook(); buildFeatures(); buildConnect(); buildAbout(); }
  }

  function syncControls() {
    updateStatusBar();
    $('inspector').classList.toggle('collapsed', !S.inspector);
    $('toggleInspector').classList.toggle('on', S.inspector);
  }

  function slashUpdate() {
    const ta = $('prompt'), menu = $('slashMenu');
    const v = ta.value;
    if (!v.startsWith('/') || v.includes(' ') || v.includes('\n')) { menu.classList.add('hidden'); return; }
    const items = COMMANDS.filter((c) => c[0].startsWith(v.toLowerCase()));
    if (!items.length) { menu.classList.add('hidden'); return; }
    menu.textContent = '';
    items.slice(0, 8).forEach((c, i) => {
      const r = el('div', 'sl' + (i === 0 ? ' sel' : ''));
      r.append(el('b', null, c[0]), el('span', null, c[1]));
      r.addEventListener('mousedown', (e) => { e.preventDefault(); ta.value = c[0] + ' '; menu.classList.add('hidden'); ta.focus(); });
      menu.appendChild(r);
    });
    menu.classList.remove('hidden');
  }

  function bind() {
    $('projectPill').addEventListener('click', chooseFolder);
    $('heroPick').addEventListener('click', chooseFolder);
    for (const b of document.querySelectorAll('.act')) b.addEventListener('click', () => switchView(b.dataset.view));
    for (const b of document.querySelectorAll('.stab')) b.addEventListener('click', () => {
      for (const x of document.querySelectorAll('.stab')) x.classList.toggle('active', x === b);
      for (const [k, id] of [['look', 'sLook'], ['features', 'sFeatures'], ['connect', 'sConnect'], ['about', 'sAbout']]) $(id).classList.toggle('active', b.dataset.stab === k);
    });
    for (const b of document.querySelectorAll('.itab')) b.addEventListener('click', () => {
      for (const x of document.querySelectorAll('.itab')) x.classList.toggle('active', x === b);
      for (const [k, id] of [['changes', 'iChanges'], ['context', 'iContext'], ['log', 'iLog']]) $(id).classList.toggle('active', b.dataset.itab === k);
    });
    $('toggleInspector').addEventListener('click', () => { S.inspector = !S.inspector; saveSettings(); syncControls(); });
    $('endSession').addEventListener('click', () => api.sessionStop());
    $('modelChip').addEventListener('click', (e) => { e.stopPropagation(); S.modelPop.open ? closeModelPop() : openModelPop($('modelChip'), false); });
    $('cModel').addEventListener('click', (e) => { e.stopPropagation(); S.modelPop.open ? closeModelPop() : openModelPop($('cModel'), true); });
    document.addEventListener('mousedown', (e) => { if (S.modelPop.open && !$('modelPop').contains(e.target) && !e.target.closest('#modelChip, #cModel')) closeModelPop(); });
    $('cAuto').addEventListener('click', () => { S.autoContext = !S.autoContext; saveSettings(); silent('/autocontext ' + (S.autoContext ? 'on' : 'off')); updateStatusBar(); schedulePreview(); toast(tr('Автоподбор контекста: ') + (S.autoContext ? tr('включён') : tr('выключен'))); });
    $('cPlan').addEventListener('click', () => { S.plan = !S.plan; saveSettings(); updateStatusBar(); });
    $('undoBtn').addEventListener('click', () => { if (!S.running) { toast(tr('Сессия не запущена'), true); return; } enqueue('/undo'); });
    $('resetBtn').addEventListener('click', () => { if (!S.running) { toast(tr('Чат и так пустой — сессия не запущена')); return; } enqueue('/reset'); });

    const ta = $('prompt');
    const resize = () => { ta.style.height = 'auto'; ta.style.height = Math.min(ta.scrollHeight, 190) + 'px'; };
    const doSend = () => {
      if (S.mode === 'busy' && !S.askCard && !ta.value.trim()) { stopGeneration(); return; }
      const v = ta.value;
      if (!v.trim()) return;
      ta.value = ''; resize(); $('slashMenu').classList.add('hidden');
      send(v);
    };
    ta.addEventListener('input', () => { resize(); slashUpdate(); });
    ta.addEventListener('keydown', (ev) => {
      const menu = $('slashMenu');
      if (!menu.classList.contains('hidden')) {
        const rows = [...menu.children];
        let i = rows.findIndex((r) => r.classList.contains('sel'));
        if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') { ev.preventDefault(); rows[i].classList.remove('sel'); i = (i + (ev.key === 'ArrowDown' ? 1 : rows.length - 1)) % rows.length; rows[i].classList.add('sel'); return; }
        if (ev.key === 'Tab' || (ev.key === 'Enter' && !ev.shiftKey && ta.value.length < rows[i].firstChild.textContent.length)) { ev.preventDefault(); ta.value = rows[i].firstChild.textContent + ' '; menu.classList.add('hidden'); return; }
        if (ev.key === 'Escape') { menu.classList.add('hidden'); return; }
      }
      if (ev.key === 'Enter' && !ev.shiftKey && !ev.isComposing) { ev.preventDefault(); doSend(); }
    });
    initAttach();
    $('send').addEventListener('click', () => { if (S.mode === 'busy' && !S.askCard) stopGeneration(); else doSend(); });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && S.mode === 'busy' && !S.modelPop.open && !S.askCard) stopGeneration(); });

    $('ruleInput').addEventListener('keydown', (ev) => {
      if (ev.key !== 'Enter') return;
      const v = $('ruleInput').value.trim().replace(/\\/g, '/');
      $('ruleInput').value = '';
      if (v && !v.startsWith('#')) { S.managed.add(v); saveManaged(); }
    });
    $('refreshCtx').addEventListener('click', () => { refreshTree(); schedulePreview(); });
    $('openIgnore').addEventListener('click', async () => { if (!(await api.revealIgnore(S.project))) toast(tr('Файла .vibeignore ещё нет — добавьте правило'), true); });

    api.on('vibe-event', onEvent);
    api.on('proc-out', (p) => { for (const l of String(p.text).split('\n')) if (l.trim()) addLogLine('', l); });
    api.on('proc-exit', onExit);
    api.on('log', (p) => { addSys(p.text, p.level === 'err' ? 'err' : p.level === 'warn' ? 'warn' : ''); addLogLine(p.level, p.text); });
  }

  function buildHero() {
    const box = $('heroCards');
    for (const [t, d, text] of [
      [tr('Исправить ошибку'), tr('Найдёт причину и поправит код'), tr('Найди и исправь ошибку: ')],
      [tr('Новая функция'), tr('Добавит возможность в проект'), tr('Добавь функцию: ')],
      [tr('Рефакторинг'), tr('Приведёт код в порядок без смены поведения'), tr('Отрефактори и упрости: ')]
    ]) {
      const b = el('button', 'hcard');
      b.append(el('b', null, t), document.createTextNode(d));
      b.addEventListener('click', () => { $('prompt').value = text; $('prompt').focus(); });
      box.appendChild(b);
    }
  }

  /* ================= старт ================= */

  async function init() {
    api.setLang(window.VIBE_LANG);
    loadSettings();
    initVibi();
    fillIcons();
    applyTheme();
    bind();
    buildHero();
    syncControls();
    renderSession();
    renderChanges();
    renderContextInspector();
    renderChips();
    renderTree();
    if (S.project) { $('projectName').textContent = baseName(S.project); $('projectPill').title = S.project; }
    S.liveModels = (await api.modelsCacheGet()) || {};
    await pollStatus();
    autoStart();
    setInterval(pollStatus, 3000);
    setTimeout(() => refreshAllModels(false, true), 5000);
    setInterval(() => refreshAllModels(false, true), 60000);
    if (S.project) await openProject(S.project);
  }

  init();
})();
