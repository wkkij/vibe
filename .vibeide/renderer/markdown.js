/* Лёгкий и безопасный Markdown → DOM (без innerHTML) + разбор блоков операций Vibe. */
(() => {
  'use strict';
  const el = (tag, cls, text) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  };

  const INLINE = /(`[^`\n]+`)|(\*\*[^*\n]+\*\*)|(__[^_\n]+__)|(\*[^*\n]+\*)|(\[[^\]\n]+\]\(https?:\/\/[^)\s]+\))|(https?:\/\/[^\s)<]+)/g;

  function inline(parent, text, onLink) {
    let last = 0;
    const re = new RegExp(INLINE.source, 'g');  // свой экземпляр: вложенные вызовы не должны сбрасывать lastIndex
    let m;
    while ((m = re.exec(text))) {
      if (m.index > last) parent.appendChild(document.createTextNode(text.slice(last, m.index)));
      const t = m[0];
      if (m[1]) parent.appendChild(el('code', null, t.slice(1, -1)));
      else if (m[2] || m[3]) { const b = el('strong'); inline(b, t.slice(2, -2), onLink); parent.appendChild(b); }
      else if (m[4]) { const i = el('em'); inline(i, t.slice(1, -1), onLink); parent.appendChild(i); }
      else if (m[5]) {
        const mm = /^\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)$/.exec(t);
        parent.appendChild(link(mm[1], mm[2], onLink));
      } else parent.appendChild(link(t, t, onLink));
      last = m.index + t.length;
    }
    if (last < text.length) parent.appendChild(document.createTextNode(text.slice(last)));
  }

  function link(label, url, onLink) {
    const a = el('a', null, label);
    a.title = url;
    a.addEventListener('click', (e) => { e.preventDefault(); if (onLink) onLink(url); });
    return a;
  }

  function render(src, onLink) {
    const root = el('div', 'md');
    const lines = String(src || '').replace(/\r\n?/g, '\n').split('\n');
    let i = 0;
    const para = [];
    const flush = () => {
      if (!para.length) return;
      const p = el('p');
      inline(p, para.join(' '), onLink);
      root.appendChild(p);
      para.length = 0;
    };
    while (i < lines.length) {
      const l = lines[i];
      let m;
      if ((m = /^\s*```(\S*)\s*$/.exec(l))) {
        flush();
        const buf = [];
        i++;
        while (i < lines.length && !/^\s*```\s*$/.test(lines[i])) buf.push(lines[i++]);
        i++;
        const pre = el('pre');
        pre.appendChild(el('code', m[1] ? 'lang-' + m[1] : null, buf.join('\n')));
        root.appendChild(pre);
        continue;
      }
      if (!l.trim()) { flush(); i++; continue; }
      if ((m = /^(#{1,3})\s+(.*)$/.exec(l))) { flush(); const h = el('h' + m[1].length); inline(h, m[2], onLink); root.appendChild(h); i++; continue; }
      if (/^\s*([-*_])\1{2,}\s*$/.test(l)) { flush(); root.appendChild(el('hr')); i++; continue; }
      if (/^\s*>/.test(l)) {
        flush();
        const buf = [];
        while (i < lines.length && /^\s*>/.test(lines[i])) buf.push(lines[i++].replace(/^\s*>\s?/, ''));
        const q = el('blockquote'); inline(q, buf.join(' '), onLink); root.appendChild(q); continue;
      }
      if (/^\s*([-*+]|\d+[.)])\s+/.test(l)) {
        flush();
        const ordered = /^\s*\d/.test(l);
        const list = el(ordered ? 'ol' : 'ul');
        while (i < lines.length && /^\s*([-*+]|\d+[.)])\s+/.test(lines[i])) {
          const li = el('li');
          inline(li, lines[i].replace(/^\s*([-*+]|\d+[.)])\s+/, ''), onLink);
          list.appendChild(li);
          i++;
        }
        root.appendChild(list); continue;
      }
      if (/^\s*\|.*\|\s*$/.test(l) && i + 1 < lines.length && /^\s*\|?[\s:|-]+\|[\s:|-]*$/.test(lines[i + 1])) {
        flush();
        const cells = (s) => s.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim());
        const table = el('table');
        const thead = el('thead'); const tr = el('tr');
        for (const c of cells(l)) { const th = el('th'); inline(th, c, onLink); tr.appendChild(th); }
        thead.appendChild(tr); table.appendChild(thead);
        i += 2;
        const tb = el('tbody');
        while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) {
          const r = el('tr');
          for (const c of cells(lines[i])) { const td = el('td'); inline(td, c, onLink); r.appendChild(td); }
          tb.appendChild(r); i++;
        }
        table.appendChild(tb); root.appendChild(table); continue;
      }
      para.push(l.trim());
      i++;
    }
    flush();
    return root;
  }

  /* ---- блоки операций из ответа модели ---- */
  const OPS = /<<<FILE:\s*(.+?)\s*>>>([\s\S]*?)<<<END_FILE>>>|<<<CREATE:\s*(.+?)\s*>>>([\s\S]*?)<<<END_CREATE>>>|<<<DELETE:\s*(.+?)\s*>>>|<<<RUN_CMD>>>([\s\S]*?)<<<END_CMD>>>/g;
  const SR = /<<<<<<<\s*SEARCH\r?\n([\s\S]*?)\r?\n?=======\r?\n([\s\S]*?)\r?\n?>>>>>>>\s*REPLACE/g;

  function stripFences(t) {
    return t.replace(/^\s*```[a-z]*\s*$/gim, '').replace(/^\s*(text|Copy code|Копировать код)\s*$/gim, '');
  }

  function parseOps(text) {
    const out = [];
    let last = 0;
    OPS.lastIndex = 0;
    let m;
    const pushText = (s) => { const t = stripFences(s).trim(); if (t) out.push({ type: 'text', text: t }); };
    while ((m = OPS.exec(text))) {
      pushText(text.slice(last, m.index));
      if (m[1] !== undefined) {
        const blocks = [];
        SR.lastIndex = 0;
        let b;
        while ((b = SR.exec(m[2]))) blocks.push({ search: b[1], replace: b[2] });
        out.push({ type: 'edit', path: m[1].trim(), blocks });
      } else if (m[3] !== undefined) out.push({ type: 'create', path: m[3].trim(), content: m[4].replace(/^\r?\n/, '').replace(/\r?\n$/, '') });
      else if (m[5] !== undefined) out.push({ type: 'delete', path: m[5].trim() });
      else out.push({ type: 'cmd', command: m[6].trim() });
      last = m.index + m[0].length;
    }
    pushText(text.slice(last));
    return out;
  }

  window.VibeMD = { render, parseOps, el };
})();
