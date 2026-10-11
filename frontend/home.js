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
  /** The sample design laid out by the engine for four sizes, shown one after another. */
  let demoDone = false;
  async function mountResizeDemo(host) {
    if (demoDone && host.children.length) return;
    demoDone = true;
    try {
      const d = await api('/example?name=snow_cabins');
      const sizes = [[1080, 1350, 'Original'], [1080, 1920, 'Story'], [1200, 628, 'Feed post'], [1584, 396, 'LinkedIn banner'], [300, 250, 'Medium rectangle']];
      const r = await api('/adapt', 'POST', { design: d, targets: sizes.slice(1).map(([width, height, name]) => ({ width, height, name })) });
      const designs = [d, ...r.results.map(x => GV.withSrc(x.design, d, {}))];
      const slides = designs.map((g, i) => {
        const c = el('canvas', { 'aria-hidden': 'true' });
        window.GR.draw(c, g, { scale: Math.min(150 / g.page.width, 104 / g.page.height), dpr: DPR });
        return el('figure', { class: 'rd-slide', style: `--i:${i}` }, c, el('figcaption', { text: `${sizes[i][2]} · ${sizes[i][0]}×${sizes[i][1]}` }));
      });
      host.replaceChildren(...slides);
      host.style.setProperty('--n', slides.length);
      if (REDUCED.matches) host.classList.add('still');
    } catch { host.replaceChildren(); demoDone = false; }
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
    mountResizeDemo($('home-demo'));
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
