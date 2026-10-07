/* Chameleon evaluation report: GET /eval, then tiles, a parts table, the design × size grid and the lowest cases. */
(function () {
  const $ = id => document.getElementById(id);
  function el(tag, attrs = {}, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === 'text') n.textContent = v;
      else if (k === 'style') n.setAttribute('style', v);
      else if (k.startsWith('on')) n[k] = v;
      else n.setAttribute(k, v === true ? '' : v);
    }
    for (const c of kids.flat()) if (c != null) n.append(c);
    return n;
  }
  const NAMES = { chameleon: 'Chameleon', stretch: 'Stretch', crop: 'Centre crop', letterbox: 'Letterbox' };
  const METHODS = ['chameleon', 'letterbox', 'crop', 'stretch'];
  const DIMS = [['overall', 'Overall'], ['content', 'Content'], ['legibility', 'Legibility'], ['faithfulness', 'Faithfulness'],
    ['composition', 'Composition'], ['subject', 'Photo subject']];
  const fmt = v => v == null ? '–' : (Math.round(v * 10) / 10).toFixed(1).replace(/\.0$/, '');
  const best = r => Math.max(r.stretch.overall, r.crop.overall, r.letterbox.overall);
  const bestName = r => ['stretch', 'crop', 'letterbox'].reduce((a, m) => r[m].overall > r[a].overall ? m : a, 'stretch');

  function render(rep) {
    const s = rep.summary;
    $('ev-sub').textContent = `${rep.designs.length} test designs × ${rep.sizes.length} sizes = ${rep.cases} cases, scored the same way for Chameleon and for plain stretch, centre crop and letterbox.`;
    const tile = m => el('div', { class: 'ev-tile' + (m === 'chameleon' ? ' win' : '') },
      el('small', { text: NAMES[m] }), el('b', { text: fmt(s[m].overall) }), el('span', { text: 'average score / 100' }));
    const fact = (n, label) => el('span', { class: 'ev-fact' }, el('b', { text: n }), ' ' + label);
    $('ev-tiles').replaceChildren(...METHODS.map(tile), el('div', { class: 'ev-facts' },
      fact(`${rep.wins}`, `cases where Chameleon scores highest`),
      fact(`${rep.ties}`, `ties (the original size, or a shape so close that a plain resize already works)`),
      fact(`${rep.losses}`, `cases where a naive resize scores higher`),
      fact(`${rep.checks_ok}/${rep.cases}`, `pass every check (no overlap, all inside, text ≥ 12 px)`)));

    const head = el('tr', {}, el('th', { text: 'Part' }), ...METHODS.map(m => el('th', { class: m === 'chameleon' ? 'c' : null, text: NAMES[m] })));
    const rows = DIMS.map(([k, label]) => el('tr', {}, el('th', { scope: 'row', text: label }),
      ...METHODS.map(m => el('td', { class: 'val' }, el('div', { class: 'ev-bar' + (m === 'chameleon' ? ' c' : ''), title: `${NAMES[m]} · ${label}: ${fmt(s[m][k])}` },
        el('span', { text: fmt(s[m][k]) }), el('i', { style: `--v:${s[m][k] == null ? 0 : s[m][k]}%`, 'aria-hidden': 'true' }))))));
    $('ev-dims').replaceChildren(el('thead', {}, head), el('tbody', {}, ...rows));

    const sizes = rep.sizes;
    const gh = el('tr', {}, el('th', { text: 'Design' }),
      ...sizes.map(z => el('th', {}, z.name, el('span', { class: 'dim', text: `${z.width}×${z.height}` }))));
    const grows = rep.designs.map(d => el('tr', {},
      el('td', { class: 'name' }, el('b', { text: d.name }), el('span', { text: `${d.width}×${d.height} · ${d.level || ''}` })),
      ...d.results.map(r => {
        const c = r.chameleon.overall, b = best(r), diff = c - b;
        const cls = Math.abs(diff) <= .05 ? 'tie' : diff < 0 ? 'lose' : '';
        const label = Math.abs(diff) <= .05 ? 'tie' : `${diff > 0 ? '+' : ''}${fmt(diff)}`;
        const tip = `${d.name} at ${r.width}×${r.height} (tier ${r.tier})\nChameleon ${fmt(c)} · ${NAMES.stretch} ${fmt(r.stretch.overall)} · ${NAMES.crop} ${fmt(r.crop.overall)} · ${NAMES.letterbox} ${fmt(r.letterbox.overall)}` +
          (r.chameleon.notes.length ? '\n' + r.chameleon.notes.join(' ') : '');
        return el('td', {}, el('a', { class: 'ev-cell' + (c < 85 ? ' low' : ''), href: `/xray#d=${d.id}&v=resize`, title: tip,
          'aria-label': `${d.name} ${r.width} by ${r.height}: Chameleon ${fmt(c)}, ${label} against the best naive resize (${NAMES[bestName(r)]})` },
          el('b', { text: fmt(c) }), el('small', { class: cls, text: label })));
      })));
    $('ev-grid').replaceChildren(el('thead', {}, gh), el('tbody', {}, ...grows));

    const all = rep.designs.flatMap(d => d.results.map(r => ({ d, r })));
    all.sort((p, q) => p.r.chameleon.overall - q.r.chameleon.overall);
    $('ev-worst').replaceChildren(...all.slice(0, 10).map(({ d, r }) => el('li', {},
      el('a', { href: `/xray#d=${d.id}&v=resize`, text: `${d.name} · ${r.name || ''} ${r.width}×${r.height}` }),
      el('span', { class: 'n', text: `  ${fmt(r.chameleon.overall)} (best naive: ${NAMES[bestName(r)]} ${fmt(best(r))})` }),
      el('p', { text: r.chameleon.notes.join(' ') || 'No issues noted.' }))));
  }

  const themeBtn = $('ev-theme');
  const paint = () => themeBtn.replaceChildren(Icon(document.documentElement.dataset.theme === 'dark' ? 'sun' : 'moon'));
  themeBtn.onclick = () => { const t = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = t; try { localStorage.setItem('chameleon.theme', t); } catch (e) {} paint(); };
  paint();
  $('ev-json-icon').replaceChildren(Icon('download')); $('ev-xray-icon').replaceChildren(Icon('layers')); $('ev-home-icon').replaceChildren(Icon('home'));
  fetch('/eval').then(r => r.ok ? r.json() : r.json().then(j => Promise.reject(new Error(j.detail || r.statusText))))
    .then(rep => { window.EV = rep; render(rep); })
    .catch(e => { $('ev-error').hidden = false; $('ev-error').textContent = 'Could not build the report: ' + e.message; $('ev-tiles').replaceChildren(); });
})();
