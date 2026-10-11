/* Chameleon Studio v3 — infinite canvas: frames, pan/zoom, selection, drag/resize, keyboard. */
'use strict';
(function () {
  const VP = $('viewport'), WORLD = $('world'), OV = $('overlay');
  const V = { zoom: .25, x: 0, y: 0, layout: {}, frames: {}, labels: {}, renderedZoom: 0 };
  const GAP = 140, ROW_MAX = 4400, MIN_Z = .02, MAX_Z = 8;
  let space = false, drag = null, nudgeTimer = null;

  /* ── layout of frames in world space (shelf packing in catalog order) ── */
  function layoutFrames() {
    const L = {}; let x = 0, y = 0, rowH = 0;
    for (const f of activeFormats()) {
      if (x > 0 && x + f.width > ROW_MAX) { x = 0; y += rowH + GAP; rowH = 0; }
      L[f.key] = { x, y, w: f.width, h: f.height };
      x += f.width + GAP; rowH = Math.max(rowH, f.height);
    }
    V.layout = L;
  }
  function bounds() {
    const ls = Object.values(V.layout); if (!ls.length) return { x: 0, y: 0, w: 1000, h: 1000 };
    const x1 = Math.min(...ls.map(l => l.x)), y1 = Math.min(...ls.map(l => l.y));
    const x2 = Math.max(...ls.map(l => l.x + l.w)), y2 = Math.max(...ls.map(l => l.y + l.h));
    return { x: x1, y: y1, w: x2 - x1, h: y2 - y1 };
  }
  /** Visible canvas area (excludes floating panels, top bar and dock). */
  function safeArea() {
    const r = VP.getBoundingClientRect();
    let left = 16, right = 16;
    const lp = $('left').getBoundingClientRect(), rp = $('right').getBoundingClientRect();
    if (lp.right > 0 && lp.left >= -2) left = lp.right + 16;
    if (rp.left < r.width && rp.right <= r.width + 2) right = r.width - rp.left + 16;
    return { x: left, y: 48 + 40 + 16, w: Math.max(100, r.width - left - right), h: Math.max(100, r.height - 104 - 80) };
  }

  /* ── transforms ── */
  const toWorld = (sx, sy) => ({ x: (sx - V.x) / V.zoom, y: (sy - V.y) / V.zoom });
  const toScreen = (wx, wy) => ({ x: wx * V.zoom + V.x, y: wy * V.zoom + V.y });
  function vpPoint(ev) { const r = VP.getBoundingClientRect(); return { x: ev.clientX - r.left, y: ev.clientY - r.top }; }
  function apply(rerender = true) {
    WORLD.style.transform = `translate(${V.x}px, ${V.y}px) scale(${V.zoom})`;
    $('hover-box').hidden = true;
    $('zoom-val').textContent = Math.round(V.zoom * 100) + '%';
    positionOverlay();
    if (rerender) rerenderSoon();
  }
  const rerenderSoon = debounce(() => { if (Math.abs(V.renderedZoom - V.zoom) / V.zoom > .15) drawAll(); }, 140);
  function zoomAt(z, sx, sy) {
    z = Math.min(MAX_Z, Math.max(MIN_Z, z));
    const w = toWorld(sx, sy); V.zoom = z; V.x = sx - w.x * z; V.y = sy - w.y * z; apply();
  }
  function zoomToRect(b, pad = .9, max = 2) {
    const a = safeArea(); const z = Math.min(max, a.w / b.w * pad, a.h / b.h * pad);
    V.zoom = Math.max(MIN_Z, z); V.x = a.x + (a.w - b.w * V.zoom) / 2 - b.x * V.zoom; V.y = a.y + (a.h - b.h * V.zoom) / 2 - b.y * V.zoom; apply();
  }
  App.zoomFit = () => { layoutFrames(); zoomToRect(bounds(), .92, 1); };
  App.focusFrame = key => { const l = V.layout[key]; if (l) zoomToRect({ x: l.x, y: l.y, w: l.w, h: l.h }, .8, 2); };
  function zoomToSelection() {
    if (!S.sel) return App.zoomFit();
    const l = V.layout[S.sel.key]; if (!l) return;
    if (S.sel.id) { const e = curDesign(S.sel.key)?.elements.find(x => x.id === S.sel.id); if (e && e.width) return zoomToRect({ x: l.x + e.x, y: l.y + e.y, w: e.width, h: e.height }, .5, 4); }
    App.focusFrame(S.sel.key);
  }
  App.zoomToSelection = zoomToSelection;
  App.view = V;

  /* ── drawing ── */
  const curDesign = key => (S.edit && S.edit.key === key ? S.edit.after : display(key));
  App.curDesign = curDesign;
  function drawFrame(key) {
    const fr = V.frames[key], d = curDesign(key); if (!fr || !d) return;
    GV.draw(fr.canvas, d, { scale: Math.min(V.zoom, 4), dpr: DPR, css: false });
  }
  function drawAll() {
    V.renderedZoom = V.zoom;
    for (const key of Object.keys(V.frames)) drawFrame(key);
    App.paint('metrics');
  }
  function buildFrames() {
    layoutFrames();
    const keys = new Set(Object.keys(V.layout));
    for (const k of Object.keys(V.frames)) if (!keys.has(k)) { V.frames[k].div.remove(); V.labels[k]?.remove(); delete V.frames[k]; delete V.labels[k]; }
    for (const [k, l] of Object.entries(V.layout)) {
      if (!V.frames[k]) {
        const canvas = el('canvas', { 'aria-hidden': 'true' }), div = el('div', { class: 'frame', 'data-key': k }, canvas);
        WORLD.append(div); V.frames[k] = { div, canvas };
        const lab = el('div', { class: 'frame-label', 'data-key': k, role: 'button', tabindex: '-1' });
        lab.addEventListener('pointerdown', e => { e.stopPropagation(); select({ key: k, id: null }); });
        lab.addEventListener('dblclick', e => { e.stopPropagation(); App.focusFrame(k); });
        OV.append(lab); V.labels[k] = lab;
      }
      Object.assign(V.frames[k].div.style, { left: l.x + 'px', top: l.y + 'px', width: l.w + 'px', height: l.h + 'px' });
    }
  }
  function paintLabels() {
    for (const [k, lab] of Object.entries(V.labels)) {
      const f = fmt(k); if (!f) continue;
      const issues = issuesOf(k), tw = hasTweaks(k);
      lab.replaceChildren(...[el('b', { text: f.name }), el('span', { class: 'dim', text: `${f.width}×${f.height}` }),
        issues.length ? el('span', { class: 'flag warn', title: issues.map(i => i.text).join('\n') }, ic('alert'), String(issues.length)) : null,
        tw ? el('span', { class: 'flag tw', title: 'Has frame-only tweaks' }, ic('lock')) : null].filter(Boolean));
      lab.setAttribute('aria-label', `${f.name} ${f.width} by ${f.height}${issues.length ? `, ${issues.length} warnings` : ''}`);
      lab.classList.toggle('sel', !!(S.sel && S.sel.key === k));
    }
  }
  function positionOverlay() {
    for (const [k, lab] of Object.entries(V.labels)) {
      const l = V.layout[k]; if (!l) continue; const p = toScreen(l.x, l.y);
      lab.style.left = p.x + 'px'; lab.style.top = (p.y - 4) + 'px'; lab.style.maxWidth = Math.max(60, l.w * V.zoom) + 'px';
      lab.style.display = l.w * V.zoom < 26 ? 'none' : '';
    }
    // selected frame outline
    let fo = OV.querySelector('.frame-outline');
    if (S.sel && !S.sel.id && V.layout[S.sel.key]) {
      if (!fo) { fo = el('div', { class: 'frame-outline' }); OV.append(fo); }
      const l = V.layout[S.sel.key], p = toScreen(l.x, l.y);
      Object.assign(fo.style, { left: p.x - 1 + 'px', top: p.y - 1 + 'px', width: l.w * V.zoom + 2 + 'px', height: l.h * V.zoom + 2 + 'px' });
    } else fo?.remove();
    // element selection
    const sb = $('sel-box');
    const e = S.sel && S.sel.id && curDesign(S.sel.key)?.elements.find(x => x.id === S.sel.id);
    if (e && !e.hidden && e.width > 0 && V.layout[S.sel.key]) {
      const b = elBox(S.sel.key, e); Object.assign(sb.style, { left: b.x + 'px', top: b.y + 'px', width: b.w + 'px', height: b.h + 'px' });
      $('sel-tag').textContent = niceRole(roleOf(e));
      sb.querySelectorAll('.handle').forEach(h => { h.hidden = e.type === 'image'; });
      sb.hidden = false;
    } else sb.hidden = true;
  }
  function elBox(key, e) { const l = V.layout[key], p = toScreen(l.x + e.x, l.y + e.y); return { x: p.x, y: p.y, w: e.width * V.zoom, h: e.height * V.zoom }; }
  App.flashFrames = () => {
    Object.values(V.frames).forEach((f, i) => setTimeout(() => { f.div.classList.remove('flash'); void f.div.offsetWidth; f.div.classList.add('flash'); }, i * 50));
  };

  /* ── painter ── */
  App.painters.push(what => {
    if (S.view !== 'editor') return;
    if (what === 'metrics') { paintLabels(); return; }
    if (what === 'theme') { paintLabels(); return; }
    if (what === 'selection') { paintLabels(); positionOverlay(); return; }
    $('hover-box').hidden = true;
    buildFrames(); drawAll(); paintLabels(); positionOverlay(); $('export-count').textContent = activeFormats().length;
  });

  /* ── selection ── */
  function select(sel) {
    if (S.edit) cancelEdit(false);
    S.sel = sel; App.paint('selection');
  }
  App.select = select;
  function hit(sx, sy) {
    const w = toWorld(sx, sy);
    for (const [k, l] of Object.entries(V.layout)) {
      if (w.x < l.x || w.y < l.y || w.x > l.x + l.w || w.y > l.y + l.h) continue;
      const d = curDesign(k); if (!d) return { key: k, id: null };
      const px = w.x - l.x, py = w.y - l.y;
      const hits = d.elements.filter(e => !e.hidden && e.width > 0 && e.height > 0 && e.type !== 'decoration' && px >= e.x && px <= e.x + e.width && py >= e.y && py <= e.y + e.height);
      const e = hits.find(x => x.type !== 'image') || hits[0];
      return { key: k, id: e ? e.id : null, el: e || null };
    }
    return null;
  }
  App.hitTest = (cx, cy) => { const r = VP.getBoundingClientRect(); return hit(cx - r.left, cy - r.top); };
  App.elBoxClient = (key, id) => {
    const e = curDesign(key)?.elements.find(x => x.id === id); if (!e) return null;
    const r = VP.getBoundingClientRect(), b = elBox(key, e); return { x: b.x + r.left, y: b.y + r.top, w: b.w, h: b.h };
  };
  /* ── pointer ── */
  VP.addEventListener('wheel', e => {
    if (S.view !== 'editor') return;
    e.preventDefault();
    const p = vpPoint(e);
    if (e.ctrlKey || e.metaKey) zoomAt(V.zoom * Math.exp(-e.deltaY * (e.ctrlKey && !e.metaKey && Math.abs(e.deltaY) < 50 ? .02 : .0025)), p.x, p.y);
    else { V.x -= e.shiftKey && !e.deltaX ? e.deltaY : e.deltaX; V.y -= e.shiftKey && !e.deltaX ? 0 : e.deltaY; apply(false); }
  }, { passive: false });

  VP.addEventListener('pointerdown', e => {
    if (e.target.closest('.frame-label, .handle')) return;
    VP.focus({ preventScroll: true });
    closeMenus(); App.closeAddFrame?.();
    const p = vpPoint(e);
    if (e.button === 1 || S.tool === 'hand' || space) { startPan(e, p); return; }
    if (e.button !== 0) return;
    const h = hit(p.x, p.y);
    if (!h) { select(null); startPan(e, p); return; }
    if (!h.id) { select({ key: h.key, id: null }); return; }
    select({ key: h.key, id: h.id });
    if (h.el.type === 'image') return;
    const base = (S.edit && S.edit.key === h.key ? S.edit.after : display(h.key)).elements.find(x => x.id === h.id);
    drag = { kind: 'move', key: h.key, id: h.id, sx: p.x, sy: p.y, ox: base.x, oy: base.y, moved: false, pid: e.pointerId };
    VP.setPointerCapture(e.pointerId);
  });
  function startPan(e, p) { drag = { kind: 'pan', sx: p.x, sy: p.y, ox: V.x, oy: V.y, pid: e.pointerId }; VP.classList.add('panning'); VP.setPointerCapture(e.pointerId); }
  $('sel-box').addEventListener('pointerdown', e => {
    const h = e.target.closest('.handle'); if (!h || !S.sel?.id) return;
    e.stopPropagation(); e.preventDefault();
    if (!S.edit) beginEdit('resize', S.sel.key, S.sel.id);
    const t = S.edit.after.elements.find(x => x.id === S.sel.id), p = vpPoint(e);
    drag = { kind: 'resize', corner: h.dataset.h, key: S.sel.key, id: S.sel.id, sx: p.x, sy: p.y, x: t.x, y: t.y, w: t.width, h: t.height, fs: t.fontSize, moved: false, pid: e.pointerId };
    h.setPointerCapture(e.pointerId);
    h.onpointermove = onMove; h.onpointerup = onUp; h.onpointercancel = onCancel;
  });
  VP.addEventListener('pointermove', onMove);
  VP.addEventListener('pointerup', onUp);
  VP.addEventListener('pointercancel', onCancel);
  function onMove(e) {
    const p = vpPoint(e);
    if (!drag) { hover(p); return; }
    if (drag.kind === 'pan') { V.x = drag.ox + p.x - drag.sx; V.y = drag.oy + p.y - drag.sy; apply(false); return; }
    const dx = (p.x - drag.sx) / V.zoom, dy = (p.y - drag.sy) / V.zoom;
    if (!drag.moved && Math.hypot(p.x - drag.sx, p.y - drag.sy) < 3) return;
    if (!drag.moved) { drag.moved = true; $('hover-box').hidden = true; if (!S.edit) beginEdit('move', drag.key, drag.id); }
    const t = S.edit.after.elements.find(x => x.id === drag.id), W = S.edit.after.canvas.width, H = S.edit.after.canvas.height;
    if (drag.kind === 'move') {
      t.x = Math.max(0, Math.min(W - t.width, drag.ox + dx)); t.y = Math.max(0, Math.min(H - t.height, drag.oy + dy));
    } else {
      const sxn = drag.corner.includes('w') ? -1 : 1, syn = drag.corner.includes('n') ? -1 : 1;
      let k = Math.max((drag.w + sxn * dx) / drag.w, (drag.h + syn * dy) / drag.h);
      const maxK = Math.min((sxn > 0 ? W - drag.x : drag.x + drag.w) / drag.w, (syn > 0 ? H - drag.y : drag.y + drag.h) / drag.h);
      k = Math.max(.3, Math.min(k, maxK, 3));
      t.width = drag.w * k; t.height = drag.h * k; if (drag.fs) t.fontSize = drag.fs * k;
      t.x = sxn > 0 ? drag.x : drag.x + drag.w - t.width; t.y = syn > 0 ? drag.y : drag.y + drag.h - t.height;
    }
    drawFrame(drag.key); positionOverlay();
  }
  function onUp() {
    if (!drag) return;
    const d = drag; drag = null; VP.classList.remove('panning');
    if (d.kind === 'pan') return;
    if (!d.moved) { if (S.edit) cancelEdit(false); return; }
    if (d.kind === 'resize') S.edit.kind = 'resize';
    inferEdit();
  }
  function onCancel() { if (drag && drag.kind !== 'pan') cancelEdit(); drag = null; VP.classList.remove('panning'); }
  function hover(p) {
    const hb = $('hover-box');
    if (S.tool === 'hand' || space) { hb.hidden = true; return; }
    const h = hit(p.x, p.y);
    if (h && h.id && !(S.sel && S.sel.key === h.key && S.sel.id === h.id)) {
      const b = elBox(h.key, h.el); Object.assign(hb.style, { left: b.x + 'px', top: b.y + 'px', width: b.w + 'px', height: b.h + 'px' }); hb.hidden = false;
      VP.style.cursor = h.el.type === 'image' ? 'default' : 'move';
    } else { hb.hidden = true; VP.style.cursor = ''; }
  }
  VP.addEventListener('pointerleave', () => { $('hover-box').hidden = true; });
  VP.addEventListener('dblclick', e => { const p = vpPoint(e), h = hit(p.x, p.y); if (h && !h.id) App.focusFrame(h.key); });

  /* ── tools & zoom controls ── */
  function setTool(t) { S.tool = t; $('tool-move').setAttribute('aria-pressed', t === 'move'); $('tool-hand').setAttribute('aria-pressed', t === 'hand'); VP.classList.toggle('tool-hand', t === 'hand'); }
  App.setTool = setTool;
  $('tool-move').onclick = () => setTool('move'); $('tool-hand').onclick = () => setTool('hand');
  const centerZoom = k => { const a = safeArea(); zoomAt(V.zoom * k, a.x + a.w / 2, a.y + a.h / 2); };
  $('zoom-in').onclick = () => centerZoom(1.25); $('zoom-out').onclick = () => centerZoom(.8);
  registerMenu('zoom-val', 'zoom-menu');
  $('zoom-menu').addEventListener('click', e => {
    const b = e.target.closest('[data-zoom]'); if (!b) return; closeMenus();
    const z = b.dataset.zoom;
    if (z === 'fit') App.zoomFit(); else if (z === 'sel') zoomToSelection(); else { const a = safeArea(); zoomAt(+z, a.x + a.w / 2, a.y + a.h / 2); }
  });
  window.addEventListener('resize', debounce(() => { if (S.view === 'editor') positionOverlay(); }, 60));

  /* ── keyboard ── */
  function nudge(dx, dy) {
    const key = S.sel.key, id = S.sel.id;
    const cur = curDesign(key).elements.find(x => x.id === id); if (!cur || cur.type === 'image' || cur.hidden) return;
    if (!S.edit) beginEdit('move', key, id);
    const t = S.edit.after.elements.find(x => x.id === id);
    t.x = Math.max(0, Math.min(S.edit.after.canvas.width - t.width, t.x + dx));
    t.y = Math.max(0, Math.min(S.edit.after.canvas.height - t.height, t.y + dy));
    drawFrame(key); positionOverlay();
    clearTimeout(nudgeTimer); nudgeTimer = setTimeout(() => { if (S.edit) inferEdit(); }, 650);
  }
  /** Tab / Shift+Tab move through a frame's elements; past the last (or first) one, focus leaves the canvas. */
  function cycle(dir) {
    const key = S.sel?.key || activeFormats()[0]?.key; if (!key) return false;
    const els = curDesign(key).elements.filter(e => !e.hidden && e.width > 0 && e.type !== 'decoration');
    if (!els.length) return false;
    const i = S.sel?.id ? els.findIndex(e => e.id === S.sel.id) : -1;
    const j = i + dir;
    if (i >= 0 && (j < 0 || j >= els.length)) { select({ key, id: null }); return false; }
    select({ key, id: els[(j + els.length) % els.length].id });
    return true;
  }
  document.addEventListener('keydown', e => {
    if (S.view !== 'editor') return;
    const tag = document.activeElement?.tagName, typing = /INPUT|SELECT|TEXTAREA/.test(tag) || document.activeElement?.isContentEditable;
    const mod = e.metaKey || e.ctrlKey, k = e.key.toLowerCase();
    if (document.querySelector('dialog[open]')) return;
    if (mod && k === 'z' && !typing) { e.preventDefault(); e.shiftKey ? redo() : undo(); return; }
    if (mod && k === 'y' && !typing) { e.preventDefault(); redo(); return; }
    if (mod && k === 'e') { e.preventDefault(); exportZip(); return; }
    if (typing) return;
    if (mod && (k === '=' || k === '+')) { e.preventDefault(); centerZoom(1.25); return; }
    if (mod && k === '-') { e.preventDefault(); centerZoom(.8); return; }
    if (mod && k === '0') { e.preventDefault(); const a = safeArea(); zoomAt(1, a.x + a.w / 2, a.y + a.h / 2); return; }
    if (e.shiftKey && (e.code === 'Digit1')) { e.preventDefault(); App.zoomFit(); return; }
    if (e.shiftKey && (e.code === 'Digit2')) { e.preventDefault(); zoomToSelection(); return; }
    if (e.key === '?') { e.preventDefault(); $('shortcuts').showModal(); return; }
    if (e.key === ' ' && !space) { space = true; VP.classList.add('space'); e.preventDefault(); return; }
    if (k === 'v' && !mod) { setTool('move'); return; }
    if (k === 'h' && !mod) { setTool('hand'); return; }
    if (e.key === 'Escape') {
      if (S.edit) { cancelEdit(); return; }
      if (App.tourOpen?.()) return;
      if (S.sel?.id) select({ key: S.sel.key, id: null }); else if (S.sel) select(null);
      return;
    }
    if (e.key === 'Tab' && document.activeElement === VP) { if (cycle(e.shiftKey ? -1 : 1)) e.preventDefault(); return; }
    if (e.key === 'Enter' && S.sel && !S.sel.id && document.activeElement === VP) { e.preventDefault(); cycle(1); return; }
    if (!S.sel?.id) return;
    if (e.key === 'Delete' || e.key === 'Backspace') {
      e.preventDefault();
      const key = S.sel.key, id = S.sel.id, f = fmt(key);
      applyAction(key, id, 'hide', true);
      toast(`Hidden in ${f.name} only`, { action: 'Undo', onAction: undo, ms: 6000 });
      select({ key, id: null });
      return;
    }
    const dir = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[e.key];
    if (dir) { e.preventDefault(); const step = e.shiftKey ? 10 : 1; nudge(dir[0] * step, dir[1] * step); }
  });
  document.addEventListener('keyup', e => { if (e.key === ' ') { space = false; VP.classList.remove('space'); } });
})();
