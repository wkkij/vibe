/* Vibi — пиксельный кот Vibe в IDE. Кадры сгенерированы из core/sprites.py (16x14 px), анимации — из core/mascot.py. */
(function (root) {
  const PALETTE = {"B": "#7c5cff", "D": "#5a3fd6", "K": "#1b1440", "W": "#f4f1ff", "T": "#14d6c4", "P": "#ff8fb1"};
  const FRAMES = [[".B..........B...",".BB........BB...",".BTB......BTB...","BBBBBBBBBBBBBB..","BBBBBBBBBBBBBB..","BBBWWBBBBWWBBB..","BBBWKBBBBWKBBB..","BBPBBBBBBBBPBB..","BBBBKBKKBKBBBB.B","BBBBBKBBKBBBBBBB","DBBBBBBBBBBBBD..",".DBBBBBBBBBBD...",".BB.BB..BB.BB...",".DD.DD..DD.DD..."],[".B..........B...",".BB........BB...",".BTB......BTB...","BBBBBBBBBBBBBB..","BBBBBBBBBBBBBB..","BBBWWBBBBWWBBB..","BBBWKBBBBWKBBB..","BBPBBBBBBBBPBB.B","BBBBKBKKBKBBBB.B","BBBBBKBBKBBBBBB.","DBBBBBBBBBBBBD..",".DBBBBBBBBBBD...",".BB.BB..BB.BB...",".DD.DD..DD.DD..."],[".B..........B...",".BB........BB...",".BTB......BTB...","BBBBBBBBBBBBBB..","BBBBBBBBBBBBBB..","BBBWWBBBBWWBBB..","BBBWKBBBBWKBBB..","BBPBBBBBBBBPBB..","BBBBKBKKBKBBBB.B","BBBBBKBBKBBBBBBB","DBBBBBBBBBBBBD..",".DBBBBBBBBBBD...",".BB.BB..BB.BB...",".DD.DD..DD.DD..."],[".B..........B...",".BB........BB...",".BTB......BTB...","BBBBBBBBBBBBBB..","BBBBBBBBBBBBBB..","BBBBBBBBBBBBBB..","BBBWWBBBBWWBBB..","BBPBBBBBBBBPBB..","BBBBKBKKBKBBBB..","BBBBBKBBKBBBBB.B","DBBBBBBBBBBBBDBB",".DBBBBBBBBBBD...",".BB.BB..BB.BB...",".DD.DD..DD.DD..."],[".B..........B...",".BB........BB...",".BTB......BTB...","BBBBBBBBBBBBBB..","BBBBBBBBBBBBBB..","BBBWWBBBBWWBBB..","BBBWKBBBBWKBBB..","BBPBBBBBBBBPBB..","BBBBKBKKBKBBBB.B","BBBBBKBBKBBBBBBB","DBBBBBBBBBBBBD..",".DBBBBBBBBBBD...",".BB.BB..BB.BB...",".DD.DD..DD.DD..."],[".B...........B..",".BB.........BB..",".BTB......BTB...","BBBBBBBBBBBBBB..","BBBBBBBBBBBBBB..","BBBWWBBBBWWBBB..","BBBWKBBBBWKBBB..","BBPBBBBBBBBPBB.B","BBBBKBKKBKBBBB.B","BBBBBKBBKBBBBBB.","DBBBBBBBBBBBBD..",".DBBBBBBBBBBD...",".BB.BB..BB.BB...",".DD.DD..DD.DD..."],[".B..........B...",".BB........BB...",".BTB......BTB...","BBBBBBBBBBBBBB..","BBBBBBBBBBBBBB..","BBBWWBBBBWWBBB..","BBBWKBBBBWKBBB..","BBPBBBBBBBBPBB..","BBBBKBKKBKBBBB.B","BBBBBKBBKBBBBBBB","DBBBBBBBBBBBBD..",".DBBBBBBBBBBD...",".BB.BB..BB.BB...",".DD.DD..DD.DD..."],[".B..........B..T",".BB........BB.T.",".BTB......BTB..T","BBBBBBBBBBBBBB..","BBBBBBBBBBBBBB..","BBBWWBBBBWWBBB..","BBBBBBBBBBBBBB..","BBPBBBBBBBBPBB.B","BBBBKBKKBKBBBB.B","BBBBBKBBKBBBBBB.","DBBBBBBBBBBBBD..",".DBBBBBBBBBBD...",".BB.BB..BB.BB...",".DD.DD..DD.DD..."],[".BB........BB...",".BTB......BTB...","BBBBBBBBBBBBBB..","BBBBBBBBBBBBBB..","BBBWWBBBBWWBBB..","BBBBBBBBBBBBBB..","BBPBBBBBBBBPBB.B","BBBBBBKKBBBBBB.B","BBBBBBKKBBBBBBB.","DBBBBBBBBBBBBD..",".DBBBBBBBBBBD...",".BB.BB..BB.BB...",".DD.DD..DD.DD...","................"],[".B..........B..T",".BB........BB.T.",".BTB......BTB..T","BBBBBBBBBBBBBB..","BBBBBBBBBBBBBB..","BBBWWBBBBWWBBB..","BBBBBBBBBBBBBB..","BBPBBBBBBBBPBB..","BBBBKBKKBKBBBB.B","BBBBBKBBKBBBBBBB","DBBBBBBBBBBBBD..",".DBBBBBBBBBBD...",".BB.BB..BB.BB...",".DD.DD..DD.DD..."],[".B..........B...",".BB........BB...",".BTB......BTB...","BBBBBBBBBBBBBB..","BBBBBBBBBBBBBB..","BBBWWBBBBWWBBB..","BBBBBBBBBBBBBB..","BBPBBBBBBBBPBB.B","BBBBKBKKBKBBBB.B","BBBBBKBBKBBBBBB.","DBBBBBBBBBBBBD..",".DBBBBBBBBBBD...",".BB.BB..BB.BB...",".DD.DD..DD.DD..."],[".B..........B.TT",".BB........BB..T",".BTB......BTB...","BBBBBBBBBBBBBB..","BBBBBBBBBBBBBB..","BBBWWBBBBWWBBB..","BBBKWBBBBKWBBB..","BBPBBBBBBBBPBB..","BBBBBBBBBBBBBB.B","BBBBBKKKKBBBBBBB","DBBBBBBBBBBBBD..",".DBBBBBBBBBBD...",".BB.BB..BB.BB...",".DD.DD..DD.DD..."],[".B..........B.TT",".BB........BB..T",".BTB......BTB.T.","BBBBBBBBBBBBBB..","BBBBBBBBBBBBBBT.","BBBWWBBBBWWBBB..","BBBKWBBBBKWBBB..","BBPBBBBBBBBPBB..","BBBBBBBBBBBBBB.B","BBBBBKKKKBBBBBBB","DBBBBBBBBBBBBD..",".DBBBBBBBBBBD...",".BB.BB..BB.BB...",".DD.DD..DD.DD..."],[".B..........B.TT",".BB........BB..T",".BTB......BTB.T.","BBBBBBBBBBBBBB..","BBBBBBBBBBBBBBT.","BBBWWBBBBWWBBB..","BBBWKBBBBWKBBB..","BBPBBBBBBBBPBB..","BBBBBBBBBBBBBB.B","BBBBBKKKKBBBBBBB","DBBBBBBBBBBBBD..",".DBBBBBBBBBBD...",".BB.BB..BB.BB...",".DD.DD..DD.DD..."],[".B..........B...",".BB........BB...",".BTB......BTB...","BBBBBBBBBBBBBB..","BBBBBBBBBBBBBB..","BBBWWBBBBWWBBB..","BBBWKBBBBWKBBB..","BBPBBBBBBBBPBB.B","BBBBKBKKBKBBBB.B","BBBBBKBBKBBBBBB.","DBBBBBBBBBBBBD..",".DBBBBBBBBBBD...",".BB..BB.BB..BB..",".DD..DD.DD..DD.."],[".B..........B...",".BB........BB...",".BTB......BTB...","BBBBBBBBBBBBBB..","BBBBBBBBBBBBBB..","BBBWWBBBBWWBBB..","BBBKWBBBBKWBBB..","BBPBBBBBBBBPBB..","BBBBKBKKBKBBBB.B","BBBBBKBBKBBBBBBB","DBBBBBBBBBBBBD..",".DBBBBBBBBBBD...","BB..BB.BB..BB...","DD..DD.DD..DD..."],[".B..........B...",".BB........BB...",".BTB......BTB...","BBBBBBBBBBBBBB..","BBBBBBBBBBBBBB..","BBBWWBBBBWWBBB..","BBBWKBBBBWKBBB..","BBPBBBBBBBBPBB..","BBBBKBKKBKBBBB..","BBBBBKBBKBBBBB.B","DBBBBBBBBBBBBDBB",".DBBBBBBBBBBD...",".BB..BB.BB..BB..",".DD..DD.DD..DD.."],[".B..........B...",".BB........BB...",".BTB......BTB...","BBBBBBBBBBBBBB..","BBBBBBBBBBBBBB..","BBBBBBBBBBBBBB..","BBBWWBBBBWWBBB..","BBPBBBBBBBBPBB..","BBBBKBKKBKBBBB.B","BBBBBKBBKBBBBBBB","DBBBBBBBBBBBBD..",".DBBBBBBBBBBD...","BB..BB.BB..BB...","DD..DD.DD..DD..."],[".B..........B...",".BB........BB...",".BTB......BTB...","BBBBBBBBBBBBBB..","BBBBBBBBBBBBBB..","BBBWKBBBBKWBBB..","BBBKWBBBBWKBBB..","BBPBBBBBBBBPBB..","BBBBBKKKKBBBBB..","BBBBKBBBBKBBBB.B","DBBBBBBBBBBBBDBB",".DBBBBBBBBBBD...",".BB.BB..BB.BB...",".DD.DD..DD.DD..."],[".B...........B..",".BB.........BB..",".BTB......BTB...","BBBBBBBBBBBBBB..","BBBBBBBBBBBBBB..","BBBWKBBBBKWBBB..","BBBKWBBBBWKBBB..","BBPBBBBBBBBPBB..","BBBBBKKKKBBBBB..","BBBBKBBBBKBBBB.B","DBBBBBBBBBBBBDBB",".DBBBBBBBBBBD...",".BB.BB..BB.BB...",".DD.DD..DD.DD..."],[".B..........B...",".BB........BB.TT",".BTB......BTB...","BBBBBBBBBBBBBB..","BBBBBBBBBBBBBB..","BBBBBBBBBBBBBB..","BBBWWBBBBWWBBB..","BBPBBBBBBBBPBB..","BBBBBBBBBBBBBB..","BBBBBKKKKBBBBB.B","DBBBBBBBBBBBBDBB",".DBBBBBBBBBBD...",".BB.BB..BB.BB...",".DD.DD..DD.DD..."],[".B..........B.TT",".BB........BB..T",".BTB......BTB.TT","BBBBBBBBBBBBBB..","BBBBBBBBBBBBBB..","BBBBBBBBBBBBBB..","BBBWWBBBBWWBBB..","BBPBBBBBBBBPBB..","BBBBBBBBBBBBBB..","BBBBBKKKKBBBBB.B","DBBBBBBBBBBBBDBB",".DBBBBBBBBBBD...",".BB.BB..BB.BB...",".DD.DD..DD.DD..."]];
  const ANIM = {"idle": [[0, 1.4], [3, 0.12], [0, 0.9], [1, 0.45], [2, 0.45], [0, 1.0], [3, 0.12], [0, 0.7], [4, 0.45], [5, 0.45], [6, 0.35], [0, 1.1]], "happy": [[7, 0.3], [8, 0.3], [9, 0.3], [10, 0.3]], "think": [[11, 0.45], [12, 0.45], [13, 0.45]], "work": [[14, 0.35], [15, 0.35], [16, 0.35], [17, 0.35]], "error": [[18, 0.5], [19, 0.5]], "sleep": [[20, 0.8], [21, 0.8]], "wink": [[10, 0.4], [0, 0.4]]};
  const W = 16, H = 14;
  const MOOD_BY_PHASE = { idle: 'idle', packing: 'think', sending: 'work', waiting: 'think', thinking: 'think', answering: 'work', applying: 'work', verifying: 'work', done: 'happy', error: 'error' };

  function draw(ctx, frame, px) {
    ctx.clearRect(0, 0, W * px, H * px);
    const rows = FRAMES[frame];
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
      const c = PALETTE[rows[y][x]];
      if (!c) continue;
      ctx.fillStyle = c;
      ctx.fillRect(x * px, y * px, px, px);
    }
  }

  /* Vibi(canvas, px): рисует кота на canvas, set(mood) меняет настроение, анимация идёт сама. */
  function Vibi(canvas, px) {
    px = px || 4;
    canvas.width = W * px; canvas.height = H * px;
    canvas.style.imageRendering = 'pixelated';
    const ctx = canvas.getContext('2d');
    let mood = 'idle', step = 0, timer = null, animate = true;
    function tick() {
      const seq = ANIM[mood] || ANIM.idle;
      const s = seq[step % seq.length];
      draw(ctx, s[0], px);
      step++;
      if (animate && seq.length > 1) timer = setTimeout(tick, s[1] * 1000);
    }
    const api = {
      set(m) { if (!ANIM[m] || m === mood) return; mood = m; step = 0; clearTimeout(timer); tick(); },
      animate(on) { animate = !!on; clearTimeout(timer); step = 0; tick(); },
      mood() { return mood; }
    };
    tick();
    return api;
  }


  /* VibiPet — кот сидит на верхней кромке поля ввода рядом с кнопкой отправки. Пока модель выполняет задачу, он прыгает на её
     карточку: ходит по краю, пока идёт работа, и стоит («читает»), пока модель думает. Когда задача закончена — прыгает обратно.
     В остальное время кот просто сидит (никаких прогулок), а цикл анимации почти ничего не делает. */
  function VibiPet(o) {
    const px = 4, w = W * px, h = H * px;
    const cv = document.createElement('canvas');
    cv.className = 'vibi-pet vibi-cv';
    document.body.appendChild(cv);
    const vibi = Vibi(cv, px);
    let st = 'perch', x = 0, y = 0, dir = -1, wx = 0, from = null, jt = 0, jd = 650, dest = 'perch', box = null;
    let last = performance.now(), nextIdleCheck = 0, lastT = '', shown = null;

    function place() {
      const t = 'translate3d(' + Math.round(x) + 'px,' + Math.round(y) + 'px,0) scaleX(' + (dir > 0 ? -1 : 1) + ')';
      if (t !== lastT) { cv.style.transform = t; lastT = t; }
    }
    function show(on) { if (shown !== on) { cv.style.display = on ? '' : 'none'; shown = on; } }
    function perchPos() {
      const c = o.composer.getBoundingClientRect(), s = o.send.getBoundingClientRect();
      return { x: s.left + s.width / 2 - w / 2 - 6, y: c.top - h + 4, ctop: c.top, ok: c.width > 0 };
    }
    function cardPos(el, p) {   // положение на верхней кромке карточки или null, если карточку не видно
      if (!el || !el.isConnected) return null;
      const r = el.getBoundingClientRect();
      if (r.height < 20 || r.top < 50 || r.top > p.ctop - h - 8) return null;
      return { min: r.left + 12, max: Math.max(r.left + 12, r.right - w - 12), y: r.top - h + 3 };
    }
    function jump(to, el) { from = { x, y }; dest = to; box = el; jt = 0; jd = 550 + Math.random() * 200; st = 'jump'; vibi.set('work'); }

    function frame(now) {
      requestAnimationFrame(frame);
      const dt = Math.min(0.05, (now - last) / 1000); last = now;
      if (!o.enabled()) { show(false); return; }
      const active = o.target();
      // на месте и ничего не происходит: проверяем только раз в четверть секунды (окно могли растянуть)
      if (st === 'perch' && !active && now < nextIdleCheck) return;
      nextIdleCheck = now + 250;
      const p = perchPos();
      if (!p.ok) { show(false); return; }
      show(true);

      if (st === 'perch') {
        x = p.x; y = p.y; dir = -1;
        if (active && cardPos(active, p)) jump('card', active);
      } else if (st === 'jump') {
        jt += dt * 1000;
        const s = Math.min(1, jt / jd);
        let tg = p;
        if (dest === 'card') {
          const g = cardPos(box, p);
          if (g) tg = { x: Math.min(g.max, Math.max(g.min, wx || g.min)), y: g.y };
          else { dest = 'perch'; box = null; }
        }
        const e = s < .5 ? 2 * s * s : 1 - Math.pow(-2 * s + 2, 2) / 2;
        const arc = 40 + Math.abs(tg.x - from.x) * 0.06 + Math.abs(tg.y - from.y) * 0.2;
        x = from.x + (tg.x - from.x) * e;
        y = from.y + (tg.y - from.y) * e - 4 * arc * s * (1 - s);
        if (tg.x > from.x + 2) dir = 1; else if (tg.x < from.x - 2) dir = -1;
        if (s >= 1) {
          if (dest === 'card') { st = 'walk'; wx = tg.x; if (vibi.mood() === 'idle') vibi.set('work'); }
          else { st = 'perch'; if (!active) vibi.set(vibi.mood() === 'happy' || vibi.mood() === 'error' || vibi.mood() === 'sleep' ? vibi.mood() : 'idle'); }
        }
      } else if (st === 'walk') {
        const g = active === box ? cardPos(box, p) : null;
        if (!g) { jump('perch', null); }
        else {
          const reading = vibi.mood() === 'think';
          if (!reading) {
            wx += dir * 38 * dt;
            if (wx <= g.min) { wx = g.min; dir = 1; }
            if (wx >= g.max) { wx = g.max; dir = -1; }
          }
          x = Math.min(g.max, Math.max(g.min, wx)); y = g.y;
        }
      }
      place();
    }
    cv.style.pointerEvents = 'auto';
    cv.addEventListener('click', () => { const m = vibi.mood(); vibi.set('wink'); setTimeout(() => vibi.set(m), 900); });
    cv.style.display = 'none';
    requestAnimationFrame(frame);
    return { vibi };
  }

  root.Vibi = Vibi;
  root.VibiPet = VibiPet;
  root.VIBI_MOOD_BY_PHASE = MOOD_BY_PHASE;
})(window);

