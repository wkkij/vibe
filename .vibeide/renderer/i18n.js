/* Язык интерфейса Vibe IDE (ru / en).
   Исходные строки в коде — русские и служат ключами: tr('Русский текст') -> английский из locale-en.js.
   Нет перевода — показывается исходный текст. Язык хранится в localStorage ('vibeide:lang'); по умолчанию — язык системы. */
(function () {
  const KEY = 'vibeide:lang';
  const CYR = /[\u0400-\u04FF]/;
  function detect() {
    try {
      const saved = localStorage.getItem(KEY);
      if (saved === 'en' || saved === 'ru') return saved;
    } catch (_) { /* ignore */ }
    return /^ru/i.test(navigator.language || '') ? 'ru' : 'en';
  }
  const lang = detect();
  const EN = window.VIBE_EN || {};
  window.VIBE_LANG = lang;
  window.tr = (s) => (lang === 'en' && Object.prototype.hasOwnProperty.call(EN, s) ? EN[s] : s);
  window.setLang = (l) => {
    try { localStorage.setItem(KEY, l === 'ru' ? 'ru' : 'en'); } catch (_) { /* ignore */ }
  };

  // Статичный HTML: переводим текстовые узлы и атрибуты title / placeholder один раз при загрузке.
  function translateDom(root) {
    document.documentElement.lang = lang;
    if (lang !== 'en') return;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    for (const n of nodes) {
      const raw = n.nodeValue;
      const s = raw.trim();
      if (s && CYR.test(s)) n.nodeValue = raw.replace(s, window.tr(s));
    }
    for (const e of root.querySelectorAll('[title],[placeholder]')) {
      for (const a of ['title', 'placeholder']) {
        const v = e.getAttribute(a);
        if (v && CYR.test(v)) e.setAttribute(a, window.tr(v));
      }
    }
  }
  translateDom(document.body || document.documentElement);
})();
