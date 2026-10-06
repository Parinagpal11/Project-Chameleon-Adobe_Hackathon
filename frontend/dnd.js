/* Chameleon Studio v3 — drag & drop: files from the desktop, rule bubbles, frame presets.
   Every drag has a click/keyboard equivalent (WCAG 2.2 "dragging movements"). */
'use strict';
(function () {
  const overlay = $('drop-overlay'), hint = $('drop-hint'), ghost = $('drag-ghost');
  let depth = 0;

  /* ───────── files ───────── */
  const hasFiles = e => [...(e.dataTransfer?.types || [])].includes('Files');
  function showHint(target, text) {
    if (!target) { hint.hidden = true; return; }
    const vr = $('viewport').getBoundingClientRect();
    Object.assign(hint.style, { left: target.x - vr.left - 3 + 'px', top: target.y - vr.top - 3 + 'px', width: target.w + 6 + 'px', height: target.h + 6 + 'px' });
    hint.replaceChildren(el('span', { text })); hint.hidden = false;
  }
  function fileTarget(e) {
    if (S.view !== 'editor') return null;
    const h = App.hitTest?.(e.clientX, e.clientY);
    if (!h || !h.el) return null;
    if (h.el.type === 'image') return { kind: 'hero', box: App.elBoxClient(h.key, h.id), text: 'Replace product image in every frame' };
    if (h.el.type === 'logo') return { kind: 'logo', box: App.elBoxClient(h.key, h.id), text: 'Replace logo in every frame' };
    return null;
  }
  window.addEventListener('dragenter', e => { if (!hasFiles(e)) return; e.preventDefault(); depth++; overlay.hidden = false; });
  window.addEventListener('dragover', e => {
    if (!hasFiles(e)) return; e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
    const t = fileTarget(e);
    overlay.classList.toggle('on-target', !!t);
    showHint(t && t.box, t && t.text);
    $('home-drop').classList.toggle('over', S.view === 'home');
  });
  window.addEventListener('dragleave', e => { if (!hasFiles(e)) return; depth = Math.max(0, depth - 1); if (!depth) endFileDrag(); });
  function endFileDrag() { depth = 0; overlay.hidden = true; overlay.classList.remove('on-target'); hint.hidden = true; $('home-drop').classList.remove('over'); }
  window.addEventListener('drop', async e => {
    if (!hasFiles(e)) return; e.preventDefault();
    const t = fileTarget(e); endFileDrag();
    await handleFiles([...e.dataTransfer.files], t && t.kind);
  });

  /** Sort dropped files: JSON opens a project; images are classified (logo vs product photo) unless dropped on a slot. */
  async function handleFiles(files, forcedKind) {
    if (!files.length) return;
    const json = files.find(f => /json$/i.test(f.type) || /\.json$/i.test(f.name));
    if (json) return importJsonFile(json);
    const imgs = files.filter(f => f.type.startsWith('image/')).slice(0, 2);
    if (!imgs.length) return toast('Drop a JPG, PNG, SVG or WebP image, or a Chameleon JSON file.', { error: true });
    let infos;
    try { infos = await Promise.all(imgs.map(f => readImage(f, forcedKind || 'hero').then(info => ({ info, file: f, kind: forcedKind || classify(info, f) })))); }
    catch (err) { return toast(err.message, { error: true }); }
    if (infos.length === 2 && infos[0].kind === infos[1].kind) {
      // two images of the same guessed kind: the more logo-like one becomes the logo
      const score = x => x.info.alpha * 2 + Math.min(3, x.info.w / x.info.h) / 3;
      infos.sort((a, b) => score(b) - score(a)); infos[0].kind = 'logo'; infos[1].kind = 'hero';
    }
    if (S.view === 'home') {
      await startTemplate('coffee_ad');
      store.set('chameleon.tour.v3', store.get('chameleon.tour.v3') || 'deferred');
    }
    for (const x of infos) await useImage(x.info, x.kind, { quiet: infos.length > 1 });
    if (infos.length > 1) toast('Logo and product image applied to every frame', { action: 'Swap them', onAction: async () => { await undo(); await undo(); for (const x of infos) await useImage(x.info, x.kind === 'logo' ? 'hero' : 'logo', { quiet: true }); } });
  }
  App.handleFiles = handleFiles;

  // asset slots in the Assets panel accept drops directly
  for (const kind of ['hero', 'logo']) {
    const slot = $('drop-' + kind);
    slot.addEventListener('dragover', e => { if (hasFiles(e)) { e.preventDefault(); slot.classList.add('over'); } });
    slot.addEventListener('dragleave', () => slot.classList.remove('over'));
    slot.addEventListener('drop', e => { if (!hasFiles(e)) return; e.preventDefault(); e.stopPropagation(); slot.classList.remove('over'); endFileDrag(); handleFiles([...e.dataTransfer.files].slice(0, 1), kind); });
  }

  /* ───────── pointer drags: bubbles and presets ───────── */
  function pointerDrag(selector, { makeGhost, onOver, onDrop, onClick }) {
    document.addEventListener('pointerdown', e => {
      const src = e.target.closest(selector); if (!src || e.button !== 0) return;
      const start = { x: e.clientX, y: e.clientY }; let dragging = false;
      const move = ev => {
        if (!dragging && Math.hypot(ev.clientX - start.x, ev.clientY - start.y) < 5) return;
        if (!dragging) { dragging = true; ghost.replaceChildren(makeGhost(src)); ghost.hidden = false; document.body.style.cursor = 'grabbing'; }
        ghost.style.left = ev.clientX + 'px'; ghost.style.top = ev.clientY + 'px';
        onOver(src, ev);
      };
      const up = ev => {
        document.removeEventListener('pointermove', move); document.removeEventListener('pointerup', up); document.removeEventListener('pointercancel', cancel);
        document.body.style.cursor = '';
        if (dragging) { ghost.hidden = true; hint.hidden = true; src.dataset.dragged = '1'; setTimeout(() => delete src.dataset.dragged, 0); onDrop(src, ev); }
        else onClick?.(src);
      };
      const cancel = () => { document.removeEventListener('pointermove', move); document.removeEventListener('pointerup', up); document.removeEventListener('pointercancel', cancel); ghost.hidden = true; hint.hidden = true; document.body.style.cursor = ''; };
      document.addEventListener('pointermove', move); document.addEventListener('pointerup', up); document.addEventListener('pointercancel', cancel);
    });
  }
  const overViewport = ev => { const r = $('viewport').getBoundingClientRect(), lp = $('left').getBoundingClientRect(), rp = $('right').getBoundingClientRect();
    const inPanel = (p) => ev.clientX >= p.left && ev.clientX <= p.right && ev.clientY >= p.top && ev.clientY <= p.bottom && p.width > 0 && p.left > -10 && p.right < r.width + 10;
    return ev.clientX >= r.left && ev.clientX <= r.right && ev.clientY >= r.top && ev.clientY <= r.bottom && !inPanel(lp) && !inPanel(rp); };

  // rule bubbles → drop onto an element
  pointerDrag('.bubble', {
    makeGhost: src => { const g = src.cloneNode(true); g.classList.add('ghost'); g.removeAttribute('data-b'); return g; },
    onOver: (src, ev) => {
      const h = overViewport(ev) ? App.hitTest(ev.clientX, ev.clientY) : null;
      if (h && h.el) showHint(App.elBoxClient(h.key, h.id), `${App.BUBBLES[+src.dataset.b][0]} → ${niceRole(roleOf(h.el))}`); else hint.hidden = true;
    },
    onDrop: (src, ev) => {
      const h = overViewport(ev) ? App.hitTest(ev.clientX, ev.clientY) : null;
      if (!h || !h.el) return toast('Drop the bubble onto an element on the canvas.');
      if (S.pending) return App.flagPending();
      App.select({ key: h.key, id: h.id });
      App.applyBubble(+src.dataset.b, h.key, h.id);
    },
  });

  // frame presets → drop onto the canvas (or click)
  pointerDrag('.preset', {
    makeGhost: src => el('div', { class: 'bubble ghost' }, ic('frame'), src.querySelector('.nm').textContent),
    onOver: () => {},
    onDrop: (src, ev) => { if (overViewport(ev)) { App.presetClick(src.dataset.key); App.closeAddFrame(); } },
    onClick: src => App.presetClick(src.dataset.key),
  });
  document.addEventListener('keydown', e => { const p = e.target.closest?.('.preset'); if (p && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); App.presetClick(p.dataset.key); } });
})();
