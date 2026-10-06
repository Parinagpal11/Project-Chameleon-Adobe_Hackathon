/* Chameleon Studio v3 — product tour with looping example animations, plus per-feature guides. */
'use strict';
(function () {
  const F = (cls, inner = '', style = '') => `<div class="mf ${cls}" style="${style}">${inner}</div>`;
  const ADS = '<i class="im"></i><i class="lg"></i><i class="hd"></i><i class="hd s"></i><i class="bt"></i>';
  const CURSOR = '<svg class="cur" viewBox="0 0 24 24"><path d="M5 3l14 7-6 2-2 6z"/></svg>';
  const STAGES = {
    canvas: () => `<div class="st st-canvas"><div class="world">${F('f1 tall', ADS)}${F('f2 sq', ADS)}${F('f3 wide', ADS)}${F('f4 ban', ADS)}</div><span class="lbl l1">Story</span><span class="lbl l2">Post</span><span class="lbl l3">Feed</span><span class="lbl l4">Banner</span>${CURSOR}</div>`,
    teach: () => `<div class="st st-teach">${F('big sq', ADS)}${F('s1 tall', ADS)}${F('s2 wide', ADS)}${F('s3 ban', ADS)}<div class="pop"><b>Make this a rule?</b><span class="pbtn">All frames</span><span class="pbtn2">This frame</span></div>${CURSOR}</div>`,
    scope: () => `<div class="st st-scope">${F('big sq', ADS)}${F('s1 tall', ADS)}${F('s2 wide', ADS)}<div class="pop"><b>Make this a rule?</b><span class="pbtn">All frames</span><span class="pbtn2">This frame</span></div><span class="lock">This frame only</span>${CURSOR}</div>`,
    inspector: () => `<div class="st st-insp"><div class="panel-mock"><div class="scope-mock"><span class="a">All frames</span><span class="b">This frame</span><i class="knob"></i></div><div class="pin-mock">${'<i></i>'.repeat(9)}<b class="dot"></b></div><div class="seg-mock"><i></i><i></i><i></i><b class="segsel"></b></div><div class="step-mock"><i>−</i><span>×1.25</span><i>+</i></div></div>${F('big sq', ADS)}</div>`,
    type: () => `<div class="st st-type"><div class="input-mock"><span class="typed">hide the offer on small banners</span><i class="caret"></i></div><div class="chip-mock">Hide offer under 200px</div>${F('s1 sq', ADS)}${F('s2 ban', ADS)}</div>`,
    bubbles: () => `<div class="st st-bub"><div class="tray"><span class="b0">Pin top-left</span><span class="b1">Center</span><span class="b2">Bigger</span></div>${F('big sq', ADS)}<span class="fly">Pin top-right</span>${CURSOR}</div>`,
    drop: () => `<div class="st st-drop"><div class="file f-photo"></div><div class="file f-logo"></div>${F('s1 tall', ADS)}${F('s2 sq', ADS)}${F('s3 wide', ADS)}</div>`,
    checks: () => `<div class="st st-checks"><div class="layers-mock"><i class="r">Story</i><i class="r warn">Leaderboard</i><i class="r">Post</i><i class="r">Feed</i></div><div class="opts"><b class="o o1"></b><b class="o o2"></b><b class="o o3"></b><i class="ring"></i></div></div>`,
    export: () => `<div class="st st-export"><div class="exp-btn">Export</div>${'<i class="png p1"></i><i class="png p2"></i><i class="png p3"></i><i class="png p4"></i>'}<div class="zip">ZIP<span>6 PNGs</span></div></div>`,
  };
  const STEPS = [
    { stage: 'canvas', title: 'All your formats on one canvas', text: 'Every format is a frame on one canvas. Each frame is laid out for its size automatically.', try: 'Try it: scroll to pan, ⌘/Ctrl + scroll to zoom, ⇧1 to fit everything.', anchor: () => $('viewport'), spot: false },
    { stage: 'teach', title: 'Fix one frame, teach all of them', text: 'Drag, resize or nudge any text, button or logo. Chameleon works out the rule you meant, such as “logo pinned top-right”, and offers to apply it to every frame.', try: 'Try it: drag the logo into a corner of any frame.', anchor: () => $('viewport'), spot: false },
    { stage: 'scope', title: 'Or keep it to one frame', text: 'Choose “This frame only” for a one-off. The frame gets a lock icon, and you can reset its tweaks from the inspector.', try: 'Press Esc or Undo if you change your mind.', anchor: () => $('viewport'), spot: false },
    { stage: 'inspector', title: 'The inspector', text: 'Select an element to pin it to a corner, align it, resize it or hide it. The switch at the top decides whether the change is a rule for all frames or a tweak for this frame.', try: 'Try it: click an element, then use the 9-dot pin picker.', anchor: () => $('right'), before: () => { App.setRightTab('design'); const k = activeFormats()[1]?.key || activeFormats()[0]?.key; const d = k && display(k); const lg = d?.elements.find(e => e.type === 'logo' || e.type === 'button'); if (lg) App.select({ key: k, id: lg.id }); } },
    { stage: 'type', title: 'Describe a rule in plain English', text: 'Type things like “logo top-left”, “make the CTA bigger” or “hide the offer on small banners”. You can check what Chameleon understood before you add it.', try: 'Try it: press ⌘K (Ctrl+K) anywhere.', anchor: () => $('rule-form'), before: () => App.setRightTab('rules') },
    { stage: 'bubbles', title: 'Rule bubbles', text: 'Drag a bubble onto an element to apply that rule. Or select an element and click a bubble.', try: 'Try it: drag “Pin top-right” onto a logo.', anchor: () => $('bubbles'), before: () => App.setRightTab('rules') },
    { stage: 'drop', title: 'Drop in your brand', text: 'Drag your product photo and logo from your desktop onto the canvas. Chameleon tells them apart (transparent or wide images become the logo) and updates every frame. Drop onto the image or logo to replace just that one.', try: 'Colors, typeface and copy are under Assets.', anchor: () => $('left'), before: () => App.setLeftTab('assets') },
    { stage: 'checks', title: 'Layers, checks and layout options', text: 'Layers lists every frame and its elements. A yellow dot means a check failed, such as overlapping elements or text under 12px. Select a frame to see what failed and to pick one of three layouts.', try: 'Try it: click a frame’s name on the canvas.', anchor: () => $('left'), before: () => App.setLeftTab('layers') },
    { stage: 'export', title: 'Export every size at once', text: 'One click gives you a ZIP with a PNG for every frame, plus a manifest of the rules and any warnings.', try: 'Shortcut: ⌘E. Replay this tour or any single guide from the main menu.', anchor: () => $('export-all') },
  ];
  App.TOUR_STEPS = STEPS;

  let idx = 0, paused = false, single = false;
  const T = $('tour'), SPOT = $('tour-spot');
  function mountStage(host, name) {
    host.innerHTML = STAGES[name]();
    host.classList.toggle('still', REDUCED.matches || paused);
  }
  App.mountDemo = (host, name = 'teach') => { host.innerHTML = STAGES[name](); host.classList.add('tour-stage', 'mini'); if (REDUCED.matches) host.classList.add('still'); };

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
