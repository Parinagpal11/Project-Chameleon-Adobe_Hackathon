/* Chameleon Studio v3 — home: new campaign, templates, recents. Boots the app. */
'use strict';
(function () {
  function thumb(design, assets, box = [210, 132]) {
    const c = el('canvas', { 'aria-hidden': 'true' }), d = ensureBrand(clone(design));
    R.draw(c, d, { assets: assets || {}, scale: Math.min(box[0] / d.canvas.width, box[1] / d.canvas.height), dpr: DPR });
    return c;
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
    if (!list.length) { host.replaceChildren(el('div', { class: 'empty-card', text: 'No campaigns yet. Start from a template or drop in your brand images.' })); return; }
    host.replaceChildren(...list.slice(0, 12).map(p => {
      const th = el('div', { class: 'card-thumb' });
      const menuBtn = el('button', { class: 'icon-btn sm', 'aria-label': `Delete ${p.name}`, title: 'Delete campaign', onclick: async ev => {
        ev.stopPropagation(); if (!confirm(`Delete “${p.name}” and its rules? This can’t be undone.`)) return;
        await api('/project?campaign=' + p.campaign, 'DELETE'); renderRecents();
      } }, ic('trash'));
      api('/project?campaign=' + p.campaign).then(full => th.append(thumb(full.design, full.assets))).catch(() => {});
      return el('div', { class: 'card' }, th,
        el('div', { class: 'card-body' }, el('div', { style: 'min-width:0' }, el('div', { class: 'card-title', text: p.name }), el('div', { class: 'card-sub', text: `${p.rules} rule${p.rules === 1 ? '' : 's'} · edited ${relTime(p.updated)}` })), el('span', { class: 'card-menu' }, menuBtn)),
        el('button', { class: 'card-open', 'aria-label': `Open ${p.name}`, onclick: () => openProject(p.campaign) }));
    }));
  }
  App.renderHome = function () {
    renderTemplates(); renderRecents();
    App.mountDemo($('home-demo'), 'teach');
  };
  $('new-sample').onclick = () => startTemplate('coffee_ad');
  $('home-files').addEventListener('change', e => { const files = [...e.target.files]; e.target.value = ''; App.handleFiles(files); });
  $('home-drop').addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); $('home-files').click(); } });
  $('home-json').addEventListener('change', e => { const f = e.target.files[0]; e.target.value = ''; if (f) importJsonFile(f); });
  const tourFromHome = async () => { store.set('chameleon.tour.v3', '1'); await startTemplate('coffee_ad'); setTimeout(() => App.startTour(0), 500); };
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
