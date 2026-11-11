(() => {
  'use strict';
  const canvas = document.getElementById('fx');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  let w = 0, h = 0, dpr = 1, raf = 0, enabled = true;
  let FX = '255,255,255';
  const readFx = () => { const v = getComputedStyle(document.documentElement).getPropertyValue('--fx-rgb').trim(); if (v) FX = v.replace(/\s+/g, ''); };
  const mouse = { x: -9999, y: -9999 };
  let parts = [];

  function make() {
    const a = Math.random() * Math.PI * 2;
    const s = 0.12 + Math.random() * 0.34;
    return {
      x: Math.random() * w,
      y: Math.random() * h,
      vx: Math.cos(a) * s,
      vy: Math.sin(a) * s,
      r: 0.6 + Math.random() * 1.7,
      g: 150 + Math.floor(Math.random() * 105)
    };
  }

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    w = window.innerWidth;
    h = window.innerHeight;
    canvas.width = Math.floor(w * dpr);
    canvas.height = Math.floor(h * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const n = Math.round(Math.min(120, (w * h) / 15000));
    while (parts.length < n) parts.push(make());
    parts.length = n;
  }

  function frame() {
    ctx.clearRect(0, 0, w, h);
    for (const p of parts) {
      const dx = p.x - mouse.x;
      const dy = p.y - mouse.y;
      const d2 = dx * dx + dy * dy;
      if (d2 < 19600 && d2 > 1) {
        const d = Math.sqrt(d2);
        const f = (140 - d) / 140;
        p.x += (dx / d) * f * 1.6;
        p.y += (dy / d) * f * 1.6;
      }
      p.x += p.vx;
      p.y += p.vy;
      if (p.x < -10) p.x = w + 10;
      else if (p.x > w + 10) p.x = -10;
      if (p.y < -10) p.y = h + 10;
      else if (p.y > h + 10) p.y = -10;
    }

    ctx.lineWidth = 1;
    for (let i = 0; i < parts.length; i++) {
      const a = parts[i];
      for (let j = i + 1; j < parts.length; j++) {
        const b = parts[j];
        const dx = a.x - b.x;
        const dy = a.y - b.y;
        const d2 = dx * dx + dy * dy;
        if (d2 < 16900) {
          const alpha = (1 - Math.sqrt(d2) / 130) * 0.2;
          ctx.strokeStyle = 'rgba(' + FX + ',' + alpha.toFixed(3) + ')';
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }
      const mx = a.x - mouse.x;
      const my = a.y - mouse.y;
      const md2 = mx * mx + my * my;
      if (md2 < 28900) {
        const alpha = (1 - Math.sqrt(md2) / 170) * 0.38;
        ctx.strokeStyle = 'rgba(' + FX + ',' + alpha.toFixed(3) + ')';
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(mouse.x, mouse.y);
        ctx.stroke();
      }
    }

    for (const p of parts) {
      ctx.fillStyle = 'rgba(' + FX + ',' + (p.g / 255 * 0.7).toFixed(2) + ')';
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fill();
    }
    raf = requestAnimationFrame(frame);
  }

  function start() {
    if (raf || !enabled || reduce || document.hidden) return;
    raf = requestAnimationFrame(frame);
  }
  function stop() {
    if (raf) cancelAnimationFrame(raf);
    raf = 0;
  }

  window.addEventListener('resize', resize);
  window.addEventListener('mousemove', (e) => { mouse.x = e.clientX; mouse.y = e.clientY; });
  window.addEventListener('mouseout', (e) => { if (!e.relatedTarget) { mouse.x = -9999; mouse.y = -9999; } });
  document.addEventListener('visibilitychange', () => (document.hidden ? stop() : start()));

  window.VibeFX = {
    refresh: readFx,
    set(on) {
      enabled = !!on;
      if (enabled) {
        canvas.style.display = '';
        start();
      } else {
        stop();
        ctx.clearRect(0, 0, w, h);
        canvas.style.display = 'none';
      }
    }
  };

  readFx();
  resize();
  start();
})();
