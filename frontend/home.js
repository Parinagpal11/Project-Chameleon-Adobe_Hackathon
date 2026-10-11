/* Chameleon Studio v3 — home: new campaign, templates, recents. Boots the app. */
'use strict';
(function () {
  function thumb(design, assets, box = [210, 132]) {
    const c = el('canvas', { 'aria-hidden': 'true' });
    if (Array.isArray(design.nodes)) {
      const d = GV.resolved(design, assets);
      window.GR.draw(c, d, { scale: Math.min(box[0] / d.page.width, box[1] / d.page.height), dpr: DPR });
    } else {   // a campaign saved before the switch to graph designs (it converts when opened)
      const d = clone(design); d.brand = Object.assign({}, R.DEFAULT_BRAND, d.brand || {});
      R.draw(c, d, { assets: assets || {}, scale: Math.min(box[0] / d.canvas.width, box[1] / d.canvas.height), dpr: DPR });
    }
    return c;
  }
  /* ───────── live examples: the engine runs on the sample and the page shows what it did ───────── */
  const plain = rs => (rs || []).filter(r => !/^Tier \d/.test(r));
  const drawG = (g, w, h) => { const c = el('canvas', { 'aria-hidden': 'true' }); window.GR.draw(c, g, { scale: Math.min(w / g.page.width, h / g.page.height), dpr: DPR }); return c; };
  let live = null;
  async function liveSample() {
    if (live) return live;
    live = (async () => {
      const d = await api('/example?name=snow_cabins');
      const sizes = [[1080, 1920, 'Instagram Story'], [1200, 628, 'Feed post'], [1584, 396, 'LinkedIn banner'], [300, 250, 'Medium rectangle'], [1080, 1080, 'Instagram Post'], [728, 90, 'Leaderboard']];
      const r = await api('/adapt', 'POST', { design: d, targets: sizes.map(([width, height, name]) => ({ width, height, name })) });
      r.results.forEach(x => { x.design = GV.withSrc(x.design, d, {}); (x.alternatives || []).forEach(a => { a.design = GV.withSrc(a.design, d, {}); }); });
      return { d, sizes, r };
    })();
    live.catch(() => { live = null; });
    return live;
  }

  /** The sample laid out for several sizes, one after another, with the engine's own reason for each. */
  let demoTimer = null;
  async function mountResizeDemo(host) {
    if (host.querySelector('.rd-slide')) return;
    try {
      const { d, sizes, r } = await liveSample();
      const items = [{ g: d, label: 'Original · 1080×1350', why: 'Your design, as you made it.' },
        ...r.results.slice(0, 4).map((x, i) => ({ g: x.design, label: `${sizes[i][2]} · ${sizes[i][0]}×${sizes[i][1]}`, why: plain(x.reasons)[0] || '' }))];
      const H = host.clientHeight || 360, W = host.clientWidth || 520;
      const slides = items.map(it => el('figure', { class: 'rd-slide' }, drawG(it.g, W * .78, H * .78), el('figcaption', { text: it.label })));
      host.replaceChildren(...slides);
      let i = 0;
      const show = () => {
        slides.forEach((s, j) => s.classList.toggle('on', j === i));
        const why = $('home-demo-why');
        if (why) why.replaceChildren(el('i', { class: 'why-dot', 'aria-hidden': 'true' }), el('span', {}, el('b', { text: items[i].label.split(' · ')[0] + ': ' }), items[i].why));
        i = (i + 1) % slides.length;
      };
      show();
      clearTimeout(demoTimer);
      if (!REDUCED.matches) { const loop = () => { demoTimer = setTimeout(() => { if (S.view === 'home') show(); loop(); }, 3200); }; loop(); }
    } catch { host.replaceChildren(el('span', { class: 'rd-wait', text: 'The live example needs the Chameleon server.' })); }
  }

  /** "What makes Chameleon different": each card is filled with what the engine really did on the sample. */
  async function mountDiff() {
    const grid = $('diff-grid'); if (!grid || grid.dataset.done) return;
    grid.dataset.done = '1';
    try {
      const { d, r } = await liveSample();
      const vis = k => grid.querySelector(`[data-k="${k}"] .dc-vis`);
      const story = r.results[0], feed = r.results[1];
      // 1 · stretch vs crop vs Chameleon on the LinkedIn banner (an extreme shape, where the difference is obvious)
      const W0 = d.page.width, H0 = d.page.height, ban = r.results[2], bw = 300, bh = 75;
      const naive = (view) => { const c = el('canvas', { 'aria-hidden': 'true' }); window.GR.draw(c, d, { scale: bw / 1584, dpr: DPR, view }); return c; };
      const b = ban.baselines, sc = v => Math.round(v);
      const row = (cv, name, score, cls = '') => el('div', { class: 'dc-row ' + cls }, el('span', { class: 'dc-name', text: name }), cv, el('b', { class: 'score-chip ' + (score >= 90 ? 'good' : 'bad'), text: `${score}` }));
      vis('rebuild').replaceChildren(el('div', { class: 'dc-rows' },
        row(naive({ width: 1584, height: 396, sx: 1584 / W0, sy: 396 / H0 }), 'Stretched', sc(b.stretch.score.overall)),
        row(naive({ width: 1584, height: 396, sx: b.crop.scale, sy: b.crop.scale, ox: b.crop.offset[0], oy: b.crop.offset[1] }), 'Cropped', sc(b.crop.score.overall)),
        row(drawG(ban.design, bw, bh), 'Chameleon', sc(ban.score.overall), 'win'),
        el('span', { class: 'dc-cap', text: 'LinkedIn banner 1584×396 · quality score out of 100' })));
      // 2 · what it sees in the photo: the whole picture, with each thing it found
      const a = await api('/analyze', 'POST', { design: d });
      const sub = Object.values(a.subjects || {}).find(x => x.source !== 'assumed'), photo = d.nodes.find(n => n.type === 'image' && n.src);
      if (sub && photo) {
        const pw = 230, ph = pw / (sub.aspect || 1.5);
        const img = el('img', { src: photo.src, alt: '', style: `width:${pw}px;height:${ph}px;object-fit:cover;display:block;border-radius:3px` });
        const wrap = el('div', { class: 'dc-photo', style: `position:relative;width:${pw}px;height:${ph}px` }, img);
        const name = { faces: 'Face', people: 'Person' }[sub.source] || 'Subject';
        const parts = sub.parts && sub.parts.length ? sub.parts : [sub.box];
        parts.forEach(([x, y, w, h], i) => wrap.append(el('div', { class: 'subj-box', style: `left:${x * pw}px;top:${y * ph}px;width:${w * pw}px;height:${h * ph}px` }, el('span', { text: parts.length > 1 ? `${name} ${i + 1}` : name }))));
        vis('sees').replaceChildren(wrap);
      }
      // 3 · why, in its own words
      vis('why').replaceChildren(el('ul', { class: 'dc-why' }, plain(feed.reasons).slice(0, 3).map(t => el('li', { text: t }))));
      // 4 · the layouts it tried
      const src = (feed.alternatives || []).length ? feed : story;
      const opts = [{ label: src.layout_label || 'Chosen', g: src.design, s: src.score.overall, on: true },
        ...(src.alternatives || []).slice(0, 2).map(x => ({ label: x.label, g: x.design, s: x.score_overall }))];
      const tw = src === feed ? 120 : 60, th = src === feed ? 70 : 106;
      vis('tried').replaceChildren(...opts.map(o => el('div', { class: 'dc-col' + (o.on ? ' win' : '') }, drawG(o.g, tw, th), el('span', { text: o.label }), el('b', { class: 'score-chip' + (o.on ? ' good' : ''), text: `Score ${Math.round(o.s)}` }))));
      // 5 · designer intent: whole photo vs focus on the dog, for the feed post
      const withMeta = meta => { const x = JSON.parse(JSON.stringify(d)); const p = x.nodes.find(n => n.id === 'photo'); p.meta = { ...(p.meta || {}), ...meta }; return x; };
      const [fo, wh] = await Promise.all([{ focus: [0.42, 0.62, 0.2, 0.25] }, { keepWhole: true }].map(m =>
        api('/adapt', 'POST', { design: withMeta(m), targets: [{ width: 1200, height: 628, name: 'feed' }] }).then(x => GV.withSrc(x.results[0].design, d, {}))));
      vis('intent').replaceChildren(el('div', { class: 'dc-col' }, drawG(fo, 130, 70), el('span', { text: 'Focus area: the dog' })),
        el('div', { class: 'dc-col' }, drawG(wh, 130, 70), el('span', { text: 'Whole photo' })));
      // 6 · every size checked
      const ok = r.results.every(x => x.checks.ok);
      const avg = f => Math.round(r.results.reduce((n, x) => n + f(x), 0) / r.results.length);
      vis('checks').replaceChildren(el('div', { class: 'dc-col' },
        el('div', { class: 'dc-checks' }, ['No overlaps', 'Nothing off the edge', 'Text 12 px or larger', 'Readable contrast'].map(t => el('b', { class: 'score-chip ' + (ok ? 'good' : ''), text: (ok ? '✓ ' : '') + t }))),
        el('span', { text: `Average over ${r.results.length} sizes, out of 100: Chameleon ${avg(x => x.score.overall)} · crop ${avg(x => x.baselines.crop.score.overall)} · stretch ${avg(x => x.baselines.stretch.score.overall)}` })));
    } catch (e) { grid.dataset.done = ''; }
  }

  async function renderTemplates() {
    const host = $('templates');
    try {
      const list = await api('/templates');
      const designs = await Promise.all(list.map(t => api('/example?name=' + t.id).catch(() => null)));
      host.replaceChildren(...list.map((t, i) => el('div', { class: 'card' },
        el('div', { class: 'card-thumb' }, designs[i] ? thumb(designs[i]) : null),
        el('div', { class: 'card-body' }, el('div', { style: 'min-width:0' }, el('div', { class: 'card-title', text: t.name }), el('div', { class: 'card-sub', text: t.description }))),
        el('button', { class: 'card-open', 'aria-label': `Start from template: ${t.name}`, onclick: () => startTemplate(t.id) }))));
    } catch (e) { host.replaceChildren(el('div', { class: 'empty-card', text: e.message })); }
  }
  async function renderRecents() {
    const host = $('recents');
    let list = [];
    try { list = await api('/projects'); } catch (e) { host.replaceChildren(el('div', { class: 'empty-card', text: e.message })); return; }
    $('recent-count').textContent = list.length ? `${list.length} campaign${list.length > 1 ? 's' : ''}` : '';
    if (!list.length) { host.replaceChildren(el('div', { class: 'empty-card', text: 'No campaigns yet. Start from a template above, or drop in your own photo and logo.' })); return; }
    host.replaceChildren(...list.slice(0, 12).map(p => {
      const th = el('div', { class: 'card-thumb' });
      const menuBtn = el('button', { class: 'icon-btn sm', 'aria-label': `Delete ${p.name}`, title: 'Delete campaign', onclick: async ev => {
        ev.stopPropagation(); if (!confirm(`Delete “${p.name}”? This can’t be undone.`)) return;
        await api('/project?campaign=' + p.campaign, 'DELETE'); renderRecents();
      } }, ic('trash'));
      api('/project?campaign=' + p.campaign).then(full => th.append(thumb(full.design, full.assets))).catch(() => {});
      return el('div', { class: 'card' }, th,
        el('div', { class: 'card-body' }, el('div', { style: 'min-width:0' }, el('div', { class: 'card-title', text: p.name }), el('div', { class: 'card-sub', text: `Edited ${relTime(p.updated)}` })), el('span', { class: 'card-menu' }, menuBtn)),
        el('button', { class: 'card-open', 'aria-label': `Open ${p.name}`, onclick: () => openProject(p.campaign) }));
    }));
  }
  App.renderHome = function () {
    renderTemplates(); renderRecents();
    mountResizeDemo($('home-demo')); mountDiff();
  };
  $('new-sample').onclick = () => startTemplate('snow_cabins');
  $('home-files').addEventListener('change', e => { const files = [...e.target.files]; e.target.value = ''; App.handleFiles(files); });
  $('home-drop').addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); $('home-files').click(); } });
  $('home-json').addEventListener('change', e => { const f = e.target.files[0]; e.target.value = ''; if (f) importJsonFile(f); });
  const tourFromHome = async () => { store.set('chameleon.tour.v3', '1'); await startTemplate('snow_cabins'); setTimeout(() => App.startTour(0), 500); };
  $('home-tour').onclick = tourFromHome; $('home-demo-tour').onclick = tourFromHome;

  // The silk sits behind the content, so forward pointer movement to it for the ripple effect.
  const silk = $('silk-canvas');
  $('home').addEventListener('pointermove', e => { if (silk) silk.dispatchEvent(new PointerEvent('pointermove', { clientX: e.clientX, clientY: e.clientY })); }, { passive: true });
  $('home').addEventListener('pointerleave', () => silk && silk.dispatchEvent(new PointerEvent('pointerleave')));

  // deep link: /#c=<campaign> reopens a campaign (works with browser back)
  const m = location.hash.match(/c=([\w-]+)/);
  if (m) openProject(m[1]); else showHome();
  App.painters.push(what => { if (what === 'theme' && S.view === 'home') App.renderHome(); });
})();
