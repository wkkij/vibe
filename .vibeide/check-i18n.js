/* Проверка перевода IDE: каждая строка в tr('…') в renderer.js / main.js и каждый русский текст в index.html должны быть в locale-en.js.
   Запуск: node check-i18n.js */
const fs = require('fs');
const path = require('path');
const EN = require('./renderer/locale-en.js');
const CYR = /[\u0400-\u04FF]/;
const missing = new Set();
for (const f of ['renderer/renderer.js', 'main.js']) {
  const src = fs.readFileSync(path.join(__dirname, f), 'utf8');
  for (const m of src.matchAll(/\btr\((['"])((?:\\.|(?!\1).)*)\1\)/g)) if (!(m[2] in EN)) missing.add(f + ': ' + m[2]);
}
const html = fs.readFileSync(path.join(__dirname, 'renderer/index.html'), 'utf8');
for (const m of html.matchAll(/(?:title|placeholder)="([^"]*)"/g)) if (CYR.test(m[1]) && !(m[1] in EN)) missing.add('index.html: ' + m[1]);
for (const m of html.matchAll(/>([^<>]+)</g)) { const s = m[1].trim(); if (s && CYR.test(s) && !(s in EN)) missing.add('index.html: ' + s); }
const bad = Object.entries(EN).filter(([k, v]) => k !== v && CYR.test(v)).map(([k]) => k);
if (missing.size || bad.length) {
  console.error('Missing English text:\n' + [...missing].join('\n'));
  if (bad.length) console.error('Cyrillic left in English text:\n' + bad.join('\n'));
  process.exit(1);
}
console.log('i18n ok: ' + Object.keys(EN).length + ' strings');

