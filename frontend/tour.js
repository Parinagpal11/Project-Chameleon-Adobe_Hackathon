/* Chameleon Studio — guided tour. It drives the real product: each step does something on the canvas
   (selects a size, swaps a layout, marks a focus area, nudges a headline) and points at it.
   Everything the tour changes is put back when it ends. */
'use strict';
(function () {
  const T = $('tour'), SPOT = $('tour-spot');
  const sleep = ms => new Promise(r => setTimeout(r, REDUCED.matches ? Math.min(ms, 60) : ms));
  const groupByLabel = text => [...document.querySelectorAll('#pane-design .group')].find(g => (g.querySelector('.label')?.textContent || '').startsWith(text)) || null;
  const frameEl = key => document.querySelector(`.frame[data-key="${key}"]`);
  const key = (want) => (activeFormats().find(f => f.key === want) || activeFormats()[0])?.key;
  async function ready() {
    for (let i = 0; i < 200; i++) {
      if (activeFormats().every(f => S.results[f.key]) && !document.body.classList.contains('is-busy')) return;
      await sleep(100);
    }
  }
  async function relayout() { await sleep(160); await ready(); }

  let saved = null;
  function remember() {
    const p = photoNode();
    saved = { choices: clone(S.choices), overrides: clone(S.overrides), meta: p ? clone(p.meta || {}) : null, sel: S.sel,
      history: S.history.length, left: $('left').classList.contains('open'), right: $('right').classList.contains('open'),
      tab: $('pane-assets').hidden ? 'layers' : 'assets' };
  }
  async function restore() {
    if (!saved) return;
    const p = photoNode(), changedPhoto = p && JSON.stringify(p.meta || {}) !== JSON.stringify(saved.meta || {});
    S.choices = saved.choices; S.overrides = saved.overrides;
    if (p && saved.meta) p.meta = saved.meta;
    S.history.length = Math.min(S.history.length, saved.history); S.future = []; syncUndo();   // the tour's own clicks leave no undo steps
    App.openPanel?.('left', saved.left); App.openPanel?.('right', saved.right); App.setLeftTab(saved.tab);
    App.select(null); App.zoomFit();
    saved = null;
    if (changedPhoto) await refresh(true); else App.paint('all');
    save();
  }

  const STEPS = [
    { title: 'One design, every size', text: 'This is a single design. Chameleon laid it out for six sizes, moving and re-sizing the photo and text for each shape instead of cropping or stretching.',
      run: async () => { App.select(null); App.zoomFit(); await sleep(250); App.flashFrames(); }, spot: () => null, place: 'top' },
    { title: 'Every size explains itself', text: 'Click a size’s name to see what Chameleon did there, in plain words. Here is the Story.',
      run: async () => { const k = key('ig-story'); App.openPanel?.('right', true); App.select({ key: k, id: null }); App.focusFrame(k); await sleep(250); }, spot: () => groupByLabel('Why it looks like this') },
    { title: 'It shows the layouts it tried', text: 'Each option was built and scored. We just switched the Story to another one; watch the canvas. Click any option to use it.',
      run: async () => {
        const k = key('ig-story'); App.select({ key: k, id: null }); await sleep(200);
        const opts = document.querySelectorAll('#pane-design .layout-opt'), cands = S.results[k]?.candidates || [];
        let best = -1;     // the best-scoring alternative, so the switch is a good-looking one
        cands.forEach((c, i) => { if (i > 0 && (best < 0 || (c.score.overall || 0) > (cands[best].score.overall || 0))) best = i; });
        if (best > 0 && opts[best]) { await sleep(500); opts[best].click(); await sleep(350); }
      }, spot: () => groupByLabel('Layouts tried') || groupByLabel('Layout') },
    { title: 'Tell it what matters in the photo', text: 'Photo framing applies to every size. We marked the dog as the focus area, and every size now keeps it in view. “Whole photo” never crops it.',
      run: async () => {
        const k = key('feed'); App.select({ key: k, id: null }); App.zoomFit();
        const p = photoNode();
        if (p && p.src) { p.meta = { ...(p.meta || {}), focus: [0.42, 0.62, 0.2, 0.25] }; delete p.meta.keepWhole; S.choices = {}; await refresh(true); await relayout(); App.select({ key: k, id: null }); }
        App.flashFrames(); await sleep(200);
      }, spot: () => groupByLabel('Photo framing') },
    { title: 'Adjust any size by hand', text: 'Drag, resize or nudge anything. Only that size changes, marked with a lock, and the others keep their own layout. We just moved the Post’s logo to the top-right corner. ⌘Z undoes a change.',
      run: async () => {
        const k = key('ig-post'), d = display(k), lg = d && d.elements.find(e => roleOf(e) === 'logo' && !e.hidden);
        App.focusFrame(k);
        if (lg) { const m = Math.min(d.canvas.width, d.canvas.height) * .06;
          S.overrides[k] = { ...(S.overrides[k] || {}), [lg.id]: { x: d.canvas.width - m - lg.width, y: lg.y, width: lg.width, height: lg.height, hidden: false } }; App.paint('all'); }
        await sleep(250); App.select({ key: k, id: lg ? lg.id : null });
      }, spot: () => frameEl(key('ig-post')) },
    { title: 'Every size is checked', text: 'Overlaps, anything off the edge, text under 12 px and hard-to-read text are flagged on the size and here. A green tick means it passed.',
      run: async () => { const k = key('feed'); App.select({ key: k, id: null }); App.focusFrame(k); await sleep(200); }, spot: () => groupByLabel('Checks') },
    { title: 'Bring your own photo and logo', text: 'Drop them onto the canvas or here. Chameleon finds the subject in your photo and lays out every size again. Text and typeface are here too.',
      run: async () => { App.openPanel?.('left', true); App.setLeftTab('assets'); App.select(null); await sleep(150); }, spot: () => $('pane-assets') },
    { title: 'See how it works', text: 'How it works walks through what Chameleon did on your design: what it recognised, the layouts it tried and how every size scored against a plain resize.',
      run: async () => { App.setLeftTab('layers'); App.zoomFit(); await sleep(100); }, spot: () => $('think-btn') },
    { title: 'Export every size at once', text: 'One click gives you a ZIP with a PNG for every size. That’s the tour. We’ll put back everything we changed.',
      run: async () => {}, spot: () => $('export-all') },
  ];
  App.TOUR_STEPS = STEPS;

  let idx = 0, busyStep = false;
  function place(s) {
    const a = s.spot?.(), w = T.offsetWidth, h = T.offsetHeight, W = innerWidth, H = innerHeight;
    let x = (W - w) / 2, y = s.place === 'top' ? 64 : H - h - 96;
    if (a && a.scrollIntoView && a.closest?.('.pane')) a.scrollIntoView({ block: 'nearest' });
    SPOT.hidden = true;
    if (a && a.getBoundingClientRect) {
      const r = a.getBoundingClientRect();
      if (r.width > 0 && r.height > 0) {
        const pad = 6, rr = { l: Math.max(4, r.left - pad), t: Math.max(4, r.top - pad), r: Math.min(W - 4, r.right + pad), b: Math.min(H - 4, r.bottom + pad) };
        Object.assign(SPOT.style, { left: rr.l + 'px', top: rr.t + 'px', width: rr.r - rr.l + 'px', height: rr.b - rr.t + 'px' }); SPOT.hidden = false;
        if (s.place !== 'center') {
          if (rr.l > w + 30) { x = rr.l - w - 16; y = Math.min(H - h - 10, Math.max(10, rr.t)); }
          else if (W - rr.r > w + 30) { x = rr.r + 16; y = Math.min(H - h - 10, Math.max(10, rr.t)); }
          else { y = rr.b + 14 + h < H ? rr.b + 14 : Math.max(10, rr.t - h - 14); x = Math.min(W - w - 10, Math.max(10, rr.r - w)); }
        }
      }
    }
    T.style.left = Math.max(10, Math.min(W - w - 10, x)) + 'px'; T.style.top = Math.max(10, Math.min(H - h - 10, y)) + 'px';
  }
  async function show(i) {
    if (busyStep) return;
    busyStep = true; idx = i; const s = STEPS[i];
    $('tour-step').textContent = `Step ${i + 1} of ${STEPS.length}`;
    $('tour-title').textContent = s.title; $('tour-text').textContent = s.text; $('tour-try').textContent = '';
    $('tour-back').disabled = i === 0; $('tour-next').disabled = true;
    $('tour-next').textContent = i === STEPS.length - 1 ? 'Finish' : 'Next';
    $('tour-dots').replaceChildren(...STEPS.map((x, j) => el('button', { role: 'tab', 'aria-selected': j === i, 'aria-label': `Step ${j + 1}: ${x.title}`, onclick: () => show(j) })));
    T.hidden = false; T.classList.add('working');
    try { await s.run?.(); } catch { /* a step that can't run on this design just points */ }
    T.classList.remove('working'); $('tour-next').disabled = false; busyStep = false;
    requestAnimationFrame(() => place(s));
    $('tour-next').focus({ preventScroll: true });
  }
  async function close(done = true) {
    T.hidden = true; SPOT.hidden = true;
    if (done) store.set('chameleon.tour.v3', '1');
    await restore();
  }
  App.startTour = async (i = 0) => {
    if (S.view !== 'editor') return;
    T.hidden = false; T.classList.add('working'); $('tour-title').textContent = 'Getting the sizes ready…'; $('tour-text').textContent = ''; place({});
    await ready();
    if (!saved) remember();
    show(i);
  };
  App.closeTour = () => { if (!T.hidden) close(false); };
  App.tourOpen = () => !T.hidden;
  App.mountDemo = () => {};
  $('tour-next').onclick = () => { if (idx === STEPS.length - 1) close(); else show(idx + 1); };
  $('tour-back').onclick = () => { if (idx > 0) show(idx - 1); };
  $('tour-skip').onclick = () => close();
  $('tour-pause').hidden = true;
  T.addEventListener('keydown', e => {
    if (e.key === 'Escape') { e.stopPropagation(); close(); }
    if (e.key === 'ArrowRight' && e.target.tagName !== 'INPUT') { e.preventDefault(); if (!$('tour-next').disabled) $('tour-next').click(); }
    if (e.key === 'ArrowLeft' && e.target.tagName !== 'INPUT') { e.preventDefault(); $('tour-back').click(); }
  });
  window.addEventListener('resize', debounce(() => { if (!T.hidden) place(STEPS[idx]); }, 80));
  $('tour-btn').onclick = () => App.startTour(0);
  App.openGuides = () => App.startTour(0);
})();
