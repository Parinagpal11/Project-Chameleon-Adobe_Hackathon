/* Chameleon Studio v3 — product tour with looping example animations, plus per-feature guides. */
'use strict';
(function () {
  const F = (cls, inner = '', style = '') => `<div class="mf ${cls}" style="${style}">${inner}</div>`;
  const ADS = '<i class="im"></i><i class="lg"></i><i class="hd"></i><i class="hd s"></i><i class="bt"></i>';
  const CURSOR = '<svg class="cur" viewBox="0 0 24 24"><path d="M5 3l14 7-6 2-2 6z"/></svg>';
  const PHOTO = '<i class="ph"><b class="p1"></b><b class="p2"></b><b class="dog"></b></i>';
  const STAGES = {
    canvas: () => `<div class="st st-canvas"><div class="world">${F('f1 tall', ADS)}${F('f2 sq', ADS)}${F('f3 wide', ADS)}${F('f4 ban', ADS)}</div><span class="lbl l1">Story</span><span class="lbl l2">Post</span><span class="lbl l3">Feed</span><span class="lbl l4">Banner</span>${CURSOR}</div>`,
    checks: () => `<div class="st st-checks"><div class="layers-mock"><i class="r">Story</i><i class="r warn">Leaderboard</i><i class="r">Post</i><i class="r">Feed</i></div><div class="opts"><b class="o o1"></b><b class="o o2"></b><b class="o o3"></b><i class="ring"></i></div></div>`,
    framing: () => `<div class="st st-frame"><div class="big-photo">${PHOTO}<i class="fbox"></i></div>${F('s1 tall', '<i class="ph sm"><b class="dog"></b></i>')}${F('s2 wide', '<i class="ph sm"><b class="dog"></b></i>')}${F('s3 ban', '<i class="ph sm"><b class="dog"></b></i>')}${CURSOR}</div>`,
    tweak: () => `<div class="st st-scope">${F('big sq', ADS)}${F('s1 tall', ADS)}${F('s2 wide', ADS)}<span class="lock">Only this size</span>${CURSOR}</div>`,
    drop: () => `<div class="st st-drop"><div class="file f-photo"></div><div class="file f-logo"></div>${F('s1 tall', ADS)}${F('s2 sq', ADS)}${F('s3 wide', ADS)}</div>`,
    xray: () => `<div class="st st-xray">${F('big sq', ADS)}<i class="xb b1"></i><i class="xb b2"></i><i class="xb b3"></i><i class="xb b4"></i><span class="xl">Subject · headline · button</span></div>`,
    export: () => `<div class="st st-export"><div class="exp-btn">Export</div>${'<i class="png p1"></i><i class="png p2"></i><i class="png p3"></i><i class="png p4"></i>'}<div class="zip">ZIP<span>6 PNGs</span></div></div>`,
  };
  const firstFrame = () => activeFormats()[0]?.key;
  const STEPS = [
    { stage: 'canvas', title: 'Every size on one canvas', text: 'Chameleon lays out each size from your design. It rearranges the photo and text for the shape instead of cropping or stretching them.', try: 'Try it: scroll to pan, ⌘/Ctrl + scroll to zoom, ⇧1 to fit everything.', anchor: () => $('viewport'), spot: false },
    { stage: 'checks', title: 'Why a size looks the way it does', text: 'Click a size’s name. The inspector explains what Chameleon did there and shows the other layouts it tried. Click one to use it instead.', try: 'Try it: click the name above any size.', anchor: () => $('right'), before: () => { App.setRightTab('design'); const k = firstFrame(); if (k) App.select({ key: k, id: null }); } },
    { stage: 'framing', title: 'Tell it what matters in the photo', text: 'Photo framing applies to every size. Auto finds faces, people and products. Focus area keeps the part you mark in view. Whole photo never crops it.', try: 'Try it: choose Focus area, then drag a box on the photo.', anchor: () => $('right'), before: () => { const k = firstFrame(); if (k) App.select({ key: k, id: null }); } },
    { stage: 'tweak', title: 'Adjust one size by hand', text: 'Drag, resize or nudge any text, button or logo. Only that size changes; the others keep their own layout. A lock marks sizes you changed, and Reset undoes it.', try: 'Try it: drag a headline, then press ⌘Z to undo.', anchor: () => $('viewport'), spot: false },
    { stage: 'drop', title: 'Use your own photo and logo', text: 'Drop your photo and logo onto the canvas. Chameleon tells them apart and finds the subject in your photo, then lays out every size again.', try: 'Text and typeface are under Assets.', anchor: () => $('left'), before: () => App.setLeftTab('assets') },
    { stage: 'xray', title: 'See how it thinks', text: 'How it thinks opens the X-ray: what Chameleon recognised in your design (the photo’s subject, the headline, the button, the reading order) and how each size scores.', try: 'It opens in a new tab, so your work stays here.', anchor: () => $('think-btn') },
    { stage: 'export', title: 'Export every size at once', text: 'One click gives you a ZIP with a PNG for every size, plus a list of any warnings.', try: 'Shortcut: ⌘E. Replay this tour from the main menu.', anchor: () => $('export-all') },
  ];
  App.TOUR_STEPS = STEPS;

  let idx = 0, paused = false, single = false;
  const T = $('tour'), SPOT = $('tour-spot');
  function mountStage(host, name) {
    host.innerHTML = STAGES[name]();
    host.classList.toggle('still', REDUCED.matches || paused);
  }
  App.mountDemo = (host, name = 'canvas') => { host.innerHTML = STAGES[name](); host.classList.add('tour-stage', 'mini'); if (REDUCED.matches) host.classList.add('still'); };

  function show(i) {
    idx = i; const s = STEPS[i];
    if (S.view === 'editor') s.before?.();
    mountStage($('tour-stage'), s.stage);
    $('tour-step').textContent = single ? 'Feature guide' : `Step ${i + 1} of ${STEPS.length}`;
    $('tour-title').textContent = s.title; $('tour-text').textContent = s.text; $('tour-try').textContent = s.try || '';
    $('tour-back').disabled = i === 0 || single; $('tour-back').hidden = single;
    $('tour-next').textContent = single ? 'Done' : i === STEPS.length - 1 ? 'Finish' : 'Next';
    $('tour-skip').hidden = single;
    $('tour-dots').replaceChildren(...(single ? [] : STEPS.map((x, j) => el('button', { role: 'tab', 'aria-selected': j === i, 'aria-label': `Step ${j + 1}: ${x.title}`, onclick: () => show(j) }))));
    T.hidden = false;
    requestAnimationFrame(() => place(s));
    $('tour-next').focus({ preventScroll: true });
  }
  function place(s) {
    const a = S.view === 'editor' ? s.anchor?.() : null, w = T.offsetWidth, h = T.offsetHeight, W = innerWidth, H = innerHeight;
    if (a && window.innerWidth <= 900 && (a.id === 'left' || a.closest?.('#left'))) App.openPanel?.('left', true);
    if (a && window.innerWidth <= 900 && (a.id === 'right' || a.closest?.('#right'))) App.openPanel?.('right', true);
    let x = (W - w) / 2, y = H - h - 90;
    SPOT.hidden = true;
    if (a && s.spot !== false) {
      const r = a.getBoundingClientRect();
      Object.assign(SPOT.style, { left: r.left - 4 + 'px', top: r.top - 4 + 'px', width: r.width + 8 + 'px', height: r.height + 8 + 'px' }); SPOT.hidden = false;
      if (r.left > w + 30) { x = r.left - w - 18; y = r.top; }
      else if (W - r.right > w + 30) { x = r.right + 18; y = r.top; }
      else { y = r.bottom + 14 + h < H ? r.bottom + 14 : Math.max(10, r.top - h - 14); x = Math.min(W - w - 10, Math.max(10, r.right - w)); }
    }
    T.style.left = Math.max(10, Math.min(W - w - 10, x)) + 'px'; T.style.top = Math.max(10, Math.min(H - h - 10, y)) + 'px';
  }
  function close(done = true) { T.hidden = true; SPOT.hidden = true; if (done) store.set('chameleon.tour.v3', '1'); single = false; }
  App.startTour = (i = 0) => { single = false; paused = false; syncPause(); show(i); };
  App.showGuide = i => { single = true; paused = false; syncPause(); show(i); };
  App.closeTour = () => close(false);
  App.tourOpen = () => !T.hidden;
  $('tour-next').onclick = () => { if (single || idx === STEPS.length - 1) close(); else show(idx + 1); };
  $('tour-back').onclick = () => { if (idx > 0) show(idx - 1); };
  $('tour-skip').onclick = () => close();
  function syncPause() {
    $('tour-pause').replaceChildren(ic(paused ? 'play' : 'pause'));
    $('tour-pause').setAttribute('aria-label', paused ? 'Play animation' : 'Pause animation');
    $('tour-stage').classList.toggle('still', paused || REDUCED.matches);
  }
  $('tour-pause').onclick = () => { paused = !paused; syncPause(); };
  T.addEventListener('keydown', e => {
    if (e.key === 'Escape') { e.stopPropagation(); close(); }
    if (e.key === 'ArrowRight' && !single && e.target.tagName !== 'INPUT') { e.preventDefault(); $('tour-next').click(); }
    if (e.key === 'ArrowLeft' && !single && e.target.tagName !== 'INPUT') { e.preventDefault(); $('tour-back').click(); }
  });
  window.addEventListener('resize', debounce(() => { if (!T.hidden) place(STEPS[idx]); }, 80));
  $('tour-btn').onclick = () => App.startTour(0);

  /* feature guides list */
  App.openGuides = function () {
    let dlg = $('guides');
    if (!dlg) {
      dlg = el('dialog', { id: 'guides', class: 'modal', 'aria-labelledby': 'guides-title' },
        el('div', { class: 'modal-head' }, el('h2', { id: 'guides-title', text: 'Feature guides' }), el('button', { class: 'icon-btn', 'aria-label': 'Close', onclick: () => dlg.close() }, ic('x'))),
        el('div', { class: 'guide-list' }, STEPS.map((s, i) => el('button', { class: 'guide-item', onclick: () => { dlg.close(); App.showGuide(i); } },
          el('span', { class: 'guide-thumb tour-stage mini still' }), el('span', {}, el('b', { text: s.title }), el('small', { text: (s.text.match(/^.*?\.(\s|$)/) || [s.text])[0].trim() }))))));
      document.body.append(dlg);
      dlg.querySelectorAll('.guide-thumb').forEach((t, i) => { t.innerHTML = STAGES[STEPS[i].stage](); });
    }
    dlg.showModal();
  };
})();
