/* Chameleon X-ray — draw a design, ask /analyze what it sees, and overlay the findings. */
'use strict';
(function () {
  const $ = id => document.getElementById(id);
  const NS = 'http://www.w3.org/2000/svg';
  const PALETTE = ['#7c3aed', '#0284c7', '#d97706', '#059669', '#dc2626', '#db2777', '#0d9488', '#4f46e5', '#65a30d', '#ea580c'];
  const LAYERS = [
    { key: 'groups', label: 'Groups', on: true, swatch: '#7c3aed' },
    { key: 'roles', label: 'Roles', on: false, swatch: '#0284c7' },
    { key: 'lines', label: 'Alignment lines', on: true, swatch: '#06b6d4' },
    { key: 'margins', label: 'Margins', on: false, swatch: '#f97316' },
    { key: 'anchors', label: 'Anchors', on: false, swatch: '#22c55e' },
    { key: 'order', label: 'Reading order', on: true, swatch: '#94a3b8' },
    { key: 'subjects', label: 'Photo subjects', on: true, swatch: '#eab308' },
    { key: 'layers', label: 'Background & decoration', on: false, swatch: '#64748b' },
  ];
  const ROLE_NAMES = { cta: 'button', headline: 'headline', subhead: 'subhead', eyebrow: 'eyebrow', body: 'body', offer: 'offer',
    legal: 'legal', logo: 'logo', hero: 'hero image', image: 'image', caption: 'caption', price: 'price', item: 'list item',
    badge: 'badge', background: 'background', decoration: 'decoration', panel: 'panel', shape: 'shape' };
  const S = { design: null, analysis: null, scale: 1, on: Object.fromEntries(LAYERS.map(l => [l.key, l.on])), hot: null, sizes: [] };

  // ---------------------------------------------------------------- helpers
  function el(tag, attrs = {}, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === 'text') n.textContent = v; else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
      else if (k === 'html') n.innerHTML = v; else n.setAttribute(k, v === true ? '' : String(v));
    }
    for (const k of kids.flat()) if (k != null) n.append(k);
    return n;
  }
  function svg(tag, attrs = {}, parent) {
    const n = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) if (v != null) n.setAttribute(k, String(v));
    if (parent) parent.append(n);
    return n;
  }
  async function api(path, body) {
    const r = await fetch(path, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {});
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.detail || `Request failed (${r.status})`);
    return data;
  }
  function showError(msg) { const e = $('xr-error'); e.textContent = msg; e.hidden = false; clearTimeout(showError.t); showError.t = setTimeout(() => (e.hidden = true), 6000); }
  const color = i => PALETTE[i % PALETTE.length];
  const label = r => ROLE_NAMES[r] || r;
  const title = g => (g.kind === label(g.role) ? g.kind : `${g.kind} · ${label(g.role)}`);

  // ---------------------------------------------------------------- layout
  function fit() {
    if (!S.design) return;
    const stage = document.querySelector('.xr-stage');
    const meta = $('xr-meta'), tog = document.querySelector('.xr-toggles');
    const cs = getComputedStyle(stage);
    const padX = parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight);
    const padY = parseFloat(cs.paddingTop) + parseFloat(cs.paddingBottom);
    const availW = stage.clientWidth - padX;
    let availH = stage.clientHeight - padY - meta.offsetHeight - tog.offsetHeight - 24;
    if (window.innerWidth <= 920) availH = Math.max(260, window.innerHeight * .55);
    const { width: W, height: H } = S.design.page;
    S.scale = Math.max(.05, Math.min(availW / W, availH / H));
    GR.draw($('xr-canvas'), S.design, { scale: S.scale });
    const o = $('xr-overlay');
    o.setAttribute('viewBox', `0 0 ${W} ${H}`);
    drawOverlay();
  }

  // ---------------------------------------------------------------- overlay
  function tag(parent, x, y, text, fill, k, opts = {}) {
    const fs = 11 * k, padX = 5 * k, h = fs + 6 * k;
    const w = text.length * fs * .58 + padX * 2;
    const g = svg('g', {}, parent);
    const ty = opts.below ? y : y - h;
    svg('rect', { x, y: ty, width: w, height: h, rx: 3 * k, fill }, g);
    const t = svg('text', { x: x + padX, y: ty + h - 4.2 * k, 'font-size': fs, fill: '#fff' }, g);
    t.textContent = text;
    return g;
  }

  function drawOverlay() {
    const o = $('xr-overlay'); o.replaceChildren();
    const a = S.analysis; if (!a) return;
    const { width: W, height: H } = S.design.page;
    const k = 1 / S.scale;
    const nodes = Object.fromEntries(S.design.nodes.map(n => [n.id, n]));
    const groupIndex = {}; a.groups.forEach((g, i) => g.members.forEach(m => (groupIndex[m] = i)));
    const defs = svg('defs', {}, o);
    const pat = svg('pattern', { id: 'xr-hatch', width: 10 * k, height: 10 * k, patternUnits: 'userSpaceOnUse', patternTransform: 'rotate(45)' }, defs);
    svg('rect', { width: 4 * k, height: 10 * k, fill: 'rgba(15,23,42,.35)' }, pat);

    if (S.on.layers) {
      for (const id of [...a.layers.background, ...a.layers.decoration, ...(a.layers.panels || [])]) {
        const n = nodes[id]; if (!n) continue;
        const [x, y, w, h] = n.box;
        const cx = Math.max(0, x), cy = Math.max(0, y), cw = Math.min(W, x + w) - cx, ch = Math.min(H, y + h) - cy;
        if (cw <= 0 || ch <= 0) continue;
        svg('rect', { x: cx, y: cy, width: cw, height: ch, fill: 'url(#xr-hatch)' }, o);
        tag(o, cx + 4 * k, cy + 4 * k, label(a.roles[id].role), '#475569', k, { below: true });
      }
    }
    if (S.on.margins) {
      const m = a.grid.margins;
      svg('path', { d: `M0 0H${W}V${H}H0Z M${m.left} ${m.top}V${H - m.bottom}H${W - m.right}V${m.top}Z`, fill: 'rgba(249,115,22,.16)', 'fill-rule': 'evenodd' }, o);
      svg('rect', { x: m.left, y: m.top, width: W - m.left - m.right, height: H - m.top - m.bottom, fill: 'none', stroke: '#f97316', 'stroke-width': 1.5, 'stroke-dasharray': '5 4' }, o);
    }
    if (S.on.lines) {
      for (const l of a.grid.lines) {
        const c = l.axis === 'x' ? (l.page_centre ? '#f43f5e' : '#06b6d4') : '#d946ef';
        if (l.axis === 'x') svg('line', { x1: l.pos, x2: l.pos, y1: 0, y2: H, stroke: c, 'stroke-width': 1.2, 'stroke-dasharray': '4 4', opacity: .9 }, o);
        else if (l.members.length >= 3) svg('line', { y1: l.pos, y2: l.pos, x1: 0, x2: W, stroke: c, 'stroke-width': 1, 'stroke-dasharray': '2 5', opacity: .7 }, o);
      }
    }
    if (S.on.subjects) {
      for (const [id, s] of Object.entries(a.subjects)) {
        const [x, y, w, h] = s.page_box, c = '#facc15', L = Math.min(w, h) * .18;
        const p = `M${x} ${y + L}V${y}H${x + L} M${x + w - L} ${y}H${x + w}V${y + L} M${x + w} ${y + h - L}V${y + h}H${x + w - L} M${x + L} ${y + h}H${x}V${y + h - L}`;
        svg('path', { d: p, stroke: '#000', 'stroke-width': 5, fill: 'none', opacity: .35 }, o);
        svg('path', { d: p, stroke: c, 'stroke-width': 3, fill: 'none' }, o);
        svg('circle', { cx: x + w / 2, cy: y + h / 2, r: 4 * k, fill: c, stroke: '#000', 'stroke-width': 1 }, o);
        tag(o, x + 4 * k, y + h - 4 * k, `subject · ${s.source}`, '#a16207', k);
      }
    }
    if (S.on.groups) {
      a.groups.forEach((g, i) => {
        const [x, y, w, h] = g.box, c = color(i), pad = 4 * k;
        const G = svg('g', { class: 'grp' + (S.hot === g.id ? ' on' : ''), 'data-id': g.id }, o);
        svg('rect', { class: 'fill', x: x - pad, y: y - pad, width: w + pad * 2, height: h + pad * 2, fill: c }, G);
        svg('rect', { class: 'box', x: x - pad, y: y - pad, width: w + pad * 2, height: h + pad * 2, rx: 4 * k, stroke: c }, G);
        if (!S.on.order) tag(G, x - pad, y - pad, title(g), c, k);
      });
    }
    if (S.on.roles) {
      for (const [id, r] of Object.entries(a.roles)) {
        if (['background', 'decoration', 'panel', 'shape'].includes(r.role)) continue;
        const n = nodes[id]; if (!n || (n.type === 'shape')) continue;
        const i = groupIndex[id] ?? 0;
        tag(o, n.box[0], n.box[1] + 2 * k, label(r.role) + (r.source === 'given' ? ' ✓' : ''), color(i), k, { below: true });
      }
    }
    if (S.on.anchors) {
      for (const g of a.groups) {
        const [x, y, w, h] = g.box, c = '#16a34a', cx = x + w / 2, cy = y + h / 2;
        const arrows = { left: [x, cy, 0, cy], right: [x + w, cy, W, cy], top: [cx, y, cx, 0], bottom: [cx, y + h, cx, H] };
        for (const an of g.anchors) {
          if (arrows[an]) {
            const [x1, y1, x2, y2] = arrows[an];
            svg('line', { x1, y1, x2, y2, stroke: c, 'stroke-width': 2 }, o);
            svg('circle', { cx: x2, cy: y2, r: 4 * k, fill: c }, o);
          } else if (an === 'center-x') {
            svg('line', { x1: W / 2, x2: W / 2, y1: y - 10 * k, y2: y + h + 10 * k, stroke: c, 'stroke-width': 2, 'stroke-dasharray': '6 3' }, o);
            svg('path', { d: `M${W / 2} ${y - 16 * k}l${6 * k} ${6 * k}l${-6 * k} ${6 * k}l${-6 * k} ${-6 * k}Z`, fill: c }, o);
          }
        }
      }
    }
    if (S.on.order) {
      const byId = Object.fromEntries(a.groups.map((g, i) => [g.id, { g, i }]));
      const pts = a.reading_order.map(id => byId[id]).filter(Boolean);
      svg('polyline', { points: pts.map(({ g }) => `${g.box[0] + g.box[2] / 2},${g.box[1] + g.box[3] / 2}`).join(' '),
        fill: 'none', stroke: 'rgba(255,255,255,.85)', 'stroke-width': 4 }, o);
      svg('polyline', { points: pts.map(({ g }) => `${g.box[0] + g.box[2] / 2},${g.box[1] + g.box[3] / 2}`).join(' '),
        fill: 'none', stroke: '#111827', 'stroke-width': 1.5, 'stroke-dasharray': '6 4' }, o);
      pts.forEach(({ g, i }, n) => {
        const r = 11 * k, cx = g.box[0] + r * .2, cy = g.box[1] + r * .2;
        svg('circle', { cx, cy, r, fill: color(i), stroke: '#fff', 'stroke-width': 2 }, o);
        const t = svg('text', { x: cx, y: cy + 4 * k, 'font-size': 12 * k, fill: '#fff', 'text-anchor': 'middle' }, o);
        t.textContent = n + 1;
        if (S.on.groups) tag(o, cx + r + 3 * k, cy + 6 * k, title(g), color(i), k);
      });
    }
  }

  function setHot(id) {
    S.hot = id;
    document.querySelectorAll('.xr-overlay .grp').forEach(g => g.classList.toggle('on', g.dataset.id === id));
    document.querySelectorAll('.xr-group').forEach(b => b.classList.toggle('on', b.dataset.id === id));
  }

  // ---------------------------------------------------------------- panel
  function renderPanel() {
    const a = S.analysis, d = S.design;
    const meta = d.meta || {};
    $('xr-meta').replaceChildren(
      el('strong', { text: d.name || 'Untitled design' }),
      el('span', { class: 'xr-pill', text: `${d.page.width}×${d.page.height}` }),
      el('span', { class: 'xr-pill', text: a.page.orientation }),
      el('span', { class: 'xr-pill', text: a.style.structure.replace('-', ' ') }),
      el('span', { class: 'xr-pill', text: `${a.grid.alignment} aligned` }),
      meta.level ? el('span', { class: 'xr-pill', text: meta.level }) : null);
    $('xr-notes').replaceChildren(...a.notes.map(n => el('li', { text: n })));
    $('xr-gcount').textContent = a.groups.length;
    const orderPos = Object.fromEntries(a.reading_order.map((id, i) => [id, i + 1]));
    const idx = Object.fromEntries(a.groups.map((g, i) => [g.id, i]));
    $('xr-groups').replaceChildren(...a.reading_order.map(id => [a.groups[idx[id]], idx[id]]).map(([g, i]) => {
      const roles = [...new Set(g.members.map(m => label(a.roles[m]?.role || '?')).filter(r => r !== 'shape'))];
      const b = el('button', { class: 'xr-group', type: 'button', 'data-id': g.id,
        'aria-label': `Group ${orderPos[g.id]}: ${g.kind}, ${label(g.role)}. Contains ${roles.join(', ')}. Anchored ${g.anchors.join(', ') || 'nowhere'}.`,
        onmouseenter: () => setHot(g.id), onfocus: () => setHot(g.id), onmouseleave: () => setHot(null), onblur: () => setHot(null) },
      el('span', { class: 'n', style: `background:${color(i)}`, text: orderPos[g.id] }),
      el('span', { class: 't' }, el('b', { text: title(g) }), el('small', { text: roles.join(', ') })),
      el('span', { class: 'a', text: g.anchors.join(' ') }));
      return el('li', {}, b);
    }));
    $('xr-tiers').replaceChildren(...(a.targets || []).map(t => {
      const k = Math.min(40 / t.width, 32 / t.height);
      return el('li', { class: 'xr-tier', title: t.strategy },
        el('span', { class: 'xr-shape', 'aria-hidden': 'true' }, el('i', { style: `width:${Math.max(3, t.width * k)}px;height:${Math.max(3, t.height * k)}px` })),
        el('span', {}, el('b', { text: t.name || `${t.width}×${t.height}` }),
          el('small', { text: `${t.width}×${t.height} · ${t.reasons.join(' · ')}` })),
        el('span', { class: `xr-badge t${t.tier}`, text: `Tier ${t.tier} · ${t.tier_name}` }));
    }));
  }

  // ---------------------------------------------------------------- data flow
  async function show(design) {
    try {
      const analysis = await api('/analyze', { design });
      S.design = design; S.analysis = analysis; S.hot = null;
      if (document.fonts && document.fonts.ready) await document.fonts.ready;
      renderPanel(); fit();
    } catch (e) { showError(e.message); }
  }
  async function pick(id) {
    try { await show(await api('/testset/' + encodeURIComponent(id))); history.replaceState(null, '', '#d=' + id); }
    catch (e) { showError(e.message); }
  }

  function hitTest(ev) {
    if (!S.analysis) return;
    const r = $('xr-art').getBoundingClientRect();
    const x = (ev.clientX - r.left) / S.scale, y = (ev.clientY - r.top) / S.scale;
    const hits = S.analysis.groups.filter(g => x >= g.box[0] && x <= g.box[0] + g.box[2] && y >= g.box[1] && y <= g.box[1] + g.box[3]);
    hits.sort((p, q) => p.box[2] * p.box[3] - q.box[2] * q.box[3]);
    const id = hits[0] ? hits[0].id : null;
    if (id !== S.hot) setHot(id);
  }

  function boot() {
    $('xr-file-icon').replaceChildren(Icon('upload')); $('xr-home-icon').replaceChildren(Icon('home'));
    const themeBtn = $('xr-theme');
    const paintTheme = () => themeBtn.replaceChildren(Icon(document.documentElement.dataset.theme === 'dark' ? 'sun' : 'moon'));
    themeBtn.onclick = () => { const t = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
      document.documentElement.dataset.theme = t; try { localStorage.setItem('chameleon.theme', t); } catch (e) {} paintTheme(); };
    paintTheme();
    const fs = document.querySelector('.xr-toggles');
    for (const l of LAYERS) {
      const input = el('input', { type: 'checkbox', id: 'xr-l-' + l.key, checked: S.on[l.key],
        onchange: e => { S.on[l.key] = e.target.checked; drawOverlay(); } });
      fs.append(el('label', { class: 'xr-toggle', style: `--swatch:${l.swatch}` }, input, el('span', { text: l.label })));
    }
    $('xr-art').addEventListener('pointermove', hitTest);
    $('xr-art').addEventListener('pointerleave', () => setHot(null));
    $('xr-design').addEventListener('change', e => { if (e.target.value && !e.target.value.startsWith('import:')) pick(e.target.value); });
    $('xr-file').addEventListener('change', async e => {
      const f = e.target.files[0]; e.target.value = ''; if (!f) return;
      try {
        const d = JSON.parse(await f.text());
        const opt = el('option', { value: 'import:' + f.name, text: 'Imported · ' + f.name });
        $('xr-design').append(opt); $('xr-design').value = opt.value;
        if (!d.nodes && d.elements) { showError('This is a studio file. Open it in the studio, or convert it to chameleon-graph/1.'); return; }
        await show(d);
      } catch (err) { showError('Could not read that file: ' + err.message); }
    });
    new ResizeObserver(() => fit()).observe(document.querySelector('.xr-stage'));
    api('/testset').then(ts => {
      S.sizes = ts.sizes;
      const groups = {};
      ts.designs.forEach(d => (groups[d.level] = groups[d.level] || []).push(d));
      for (const lvl of ['simple', 'medium', 'hard', ...Object.keys(groups).filter(x => !['simple', 'medium', 'hard'].includes(x))]) {
        if (!groups[lvl]) continue;
        $('xr-design').append(el('optgroup', { label: lvl[0].toUpperCase() + lvl.slice(1) },
          ...groups[lvl].map(d => el('option', { value: d.id, text: `${d.name} · ${d.width}×${d.height}` }))));
      }
      const m = location.hash.match(/d=([\w-]+)/);
      const first = (m && ts.designs.find(d => d.id === m[1])) ? m[1] : ts.designs[0]?.id;
      if (first) { $('xr-design').value = first; pick(first); }
    }).catch(e => showError(e.message));
  }
  boot();
  window.XR = { S, show, pick };
})();
