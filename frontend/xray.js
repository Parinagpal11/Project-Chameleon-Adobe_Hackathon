/* Chameleon X-ray — draw a design, ask /analyze what it sees, and overlay the findings. */
'use strict';
(function () {
  const $ = id => document.getElementById(id);
  const NS = 'http://www.w3.org/2000/svg';
  // every colour carries white 11px labels at ≥ 4.5:1
  const PALETTE = ['#6d28d9', '#0369a1', '#b45309', '#047857', '#b91c1c', '#be185d', '#0f766e', '#4338ca', '#4d7c0f', '#c2410c'];
  const LAYERS = [
    { key: 'groups', label: 'Groups', on: true, swatch: '#7c3aed' },
    { key: 'roles', label: 'Roles', on: false, swatch: '#0284c7' },
    { key: 'lines', label: 'Alignment lines', on: false, swatch: '#06b6d4' },
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

  function pill(parent, x, y, text, k, opts = {}) {   // compact dark label with a yellow dot
    const fs = 11 * k, padX = 7 * k, h = fs + 9 * k, dot = 6 * k;
    const w = text.length * fs * .56 + padX * 2 + dot + 5 * k;
    const ty = opts.below ? y : y - h;
    const g = svg('g', { class: 'pill' + (opts.kind ? ' ' + opts.kind : '') }, parent);
    svg('rect', { x, y: ty, width: w, height: h, rx: h / 2 }, g);
    svg('circle', { cx: x + padX + dot / 2, cy: ty + h / 2, r: dot / 2 }, g);
    const t = svg('text', { x: x + padX + dot + 5 * k, y: ty + h / 2 + fs * .36, 'font-size': fs }, g);
    t.textContent = text;
  }

  function drawOverlay() {
    const o = $('xr-overlay'); o.replaceChildren();
    const late = [];
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
      // one clean frame per subject (each face separately), label outside so it never covers the subject
      const frames = [];
      for (const [id, s] of Object.entries(a.subjects)) {
        const boxes = s.page_parts && s.page_parts.length ? s.page_parts : [s.page_box];
        const many = boxes.length > 1;
        boxes.forEach((b, i) => frames.push({ b, text: s.source === 'focus' ? 'Your focus area' : s.source === 'whole' ? 'Whole photo' : s.source === 'faces' ? (many ? `Face ${i + 1}` : 'Face') : s.source === 'people' ? (many ? `Person ${i + 1}` : 'Person') : (s.source === 'assumed' ? 'Centre (no subject found)' : (many ? `Subject ${i + 1}` : 'Subject')), dim: s.source === 'assumed' }));
      }
      // labels avoid the design's other elements (logo, text, buttons) and each other
      const photoIds = new Set(Object.keys(a.subjects));
      const r0 = 12 * k;
      const avoid = a.groups.filter(g => !g.members.some(m => photoIds.has(m))).map(g => g.box)
        .concat(a.groups.map(g => [g.box[0] - 2 * r0, g.box[1] - 2 * r0, 3 * r0, 3 * r0]));   // number badges
      const placed = [];
      const hits = (bx, by, bw, bh) => [...avoid, ...placed].some(([ax, ay, aw, ah]) => bx < ax + aw && bx + bw > ax && by < ay + ah && by + bh > ay);
      for (const { b: [x, y, w, h], text, dim } of frames) {
        const r = Math.min(10 * k, w / 6, h / 6);
        const G = svg('g', { class: 'subj' + (dim ? ' dim' : '') }, o);
        svg('rect', { x, y, width: w, height: h, rx: r, class: 'halo' }, G);
        svg('rect', { x, y, width: w, height: h, rx: r, class: 'frame' }, G);
        const ph = 20 * k, pw = text.length * 11 * k * .56 + 25 * k, gap = 6 * k;
        const spots = [                                   // [x, top-of-pill]
          [x, y - gap - ph], [x, y + h + gap], [x + 6 * k, y + 6 * k], [x + w - pw, y - gap - ph], [x + w - pw, y + h + gap],
        ].filter(([sx, sy]) => sy >= 0 && sy + ph <= H && sx >= 0 && sx + pw <= W + 1);
        const [sx, sy] = spots.find(([sx, sy]) => !hits(sx, sy, pw, ph)) || spots[0] || [x + 6 * k, y + 6 * k];
        placed.push([sx, sy, pw, ph]);
        late.push(() => pill(o, sx, sy, text, k, { below: true }));   // drawn last so frames and badges never hide it
      }
    }
    if (S.on.groups) {
      a.groups.forEach((g, i) => {
        const [x, y, w, h] = g.box, c = color(i), pad = 4 * k;
        const G = svg('g', { class: 'grp' + (S.hot === g.id ? ' on' : ''), 'data-id': g.id }, o);
        svg('rect', { class: 'fill', x: x - pad, y: y - pad, width: w + pad * 2, height: h + pad * 2, fill: c }, G);
        svg('rect', { class: 'box', x: x - pad, y: y - pad, width: w + pad * 2, height: h + pad * 2, rx: 4 * k, stroke: c }, G);
        if (S.hot === g.id || (!S.on.order && a.groups.length <= 4)) tag(G, x - pad, y - pad, title(g), c, k);
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
        const [c0, c1] = g.column || [0, W];   // groups beside a tall photo are anchored within their column
        const arrows = { left: [x, cy, c0, cy], right: [x + w, cy, c1, cy], top: [cx, y, cx, 0], bottom: [cx, y + h, cx, H] };
        for (const an of g.anchors) {
          if (arrows[an]) {
            const [x1, y1, x2, y2] = arrows[an];
            svg('line', { x1, y1, x2, y2, stroke: c, 'stroke-width': 2 }, o);
            svg('circle', { cx: x2, cy: y2, r: 4 * k, fill: c }, o);
          } else if (an === 'center-x') {
            const mid = (c0 + c1) / 2;
            svg('line', { x1: mid, x2: mid, y1: y - 10 * k, y2: y + h + 10 * k, stroke: c, 'stroke-width': 2, 'stroke-dasharray': '6 3' }, o);
            svg('path', { d: `M${mid} ${y - 16 * k}l${6 * k} ${6 * k}l${-6 * k} ${6 * k}l${-6 * k} ${-6 * k}Z`, fill: c }, o);
          }
        }
      }
    }
    const hotBlock = (a.blocks || []).find(b => b.id === S.hot);
    if (hotBlock) {
      const [x, y, w, h] = hotBlock.box, pad = 12 * k;
      svg('rect', { x: x - pad, y: y - pad, width: w + pad * 2, height: h + pad * 2, rx: 10 * k, class: 'blk' }, o);
      pill(o, x - pad, y - pad - 6 * k, ({ copy: 'Copy block', repeat: 'Repeated items', stack: 'Stack' })[hotBlock.kind], k, { kind: 'block' });
    }
    if (S.on.order) {
      const byId = Object.fromEntries(a.groups.map((g, i) => [g.id, { g, i }]));
      const pts = a.reading_order.map(id => byId[id]).filter(Boolean);
      pts.forEach(({ g, i }, n) => {
        const r = 10 * k, out = g.box[0] - r - 2 * k > 0 && g.box[1] - r - 2 * k > 0;
        const cx = out ? g.box[0] - r * .35 : g.box[0] + r, cy = out ? g.box[1] - r * .35 : g.box[1] + r;
        svg('circle', { cx, cy, r, fill: color(i), stroke: '#fff', 'stroke-width': 1.5 }, o);
        const t = svg('text', { x: cx, y: cy + 4 * k, 'font-size': 11 * k, fill: '#fff', 'text-anchor': 'middle' }, o);
        t.textContent = n + 1;

      });
    }
    late.forEach(f => f());
  }

  function setHot(id) {
    const changed = S.hot !== id;
    S.hot = id;
    if (changed) drawOverlay();
    const bl = (S.analysis?.blocks || []).find(b => b.id === id);
    const on = new Set(bl ? bl.groups : [id]);
    document.querySelectorAll('.xr-overlay .grp').forEach(g => g.classList.toggle('on', on.has(g.dataset.id)));
    document.querySelectorAll('.xr-group').forEach(b => b.classList.toggle('on', on.has(b.dataset.id)));
    document.querySelectorAll('.xr-block').forEach(b => b.classList.toggle('on', b.dataset.id === id));
  }

  // ---------------------------------------------------------------- panel
  function renderPanel() {
    const a = S.analysis, d = S.design;
    const meta = d.meta || {};
    $('xr-meta').replaceChildren(...[
      el('strong', { text: d.name || 'Untitled design' }),
      el('span', { class: 'xr-pill', text: `${d.page.width}×${d.page.height}` }),
      el('span', { class: 'xr-pill', text: a.page.orientation }),
      el('span', { class: 'xr-pill', text: a.style.structure.replace('-', ' ') }),
      el('span', { class: 'xr-pill', text: `${a.grid.alignment} aligned` }),
      meta.level ? el('span', { class: 'xr-pill', text: meta.level }) : null,
      S.mine && a.subjects[S.mine] ? el('span', { class: 'xr-pill mine', role: 'status',
        text: `Your photo: subject ${({ focus: 'set by your focus area', whole: 'is the whole photo', saliency: 'found by saliency', faces: 'found by face detection', people: 'found by person detection', objects: 'found by object detection', assumed: 'not found, centre assumed', given: 'given' })[a.subjects[S.mine].source]} · confidence ${Math.round(a.subjects[S.mine].confidence * 100)}% ${a.subjects[S.mine].source !== 'assumed' && a.subjects[S.mine].kept != null ? ` · ${Math.round(a.subjects[S.mine].kept * 100)}% of it kept in the crop` : ''}` }) : null].filter(Boolean));
    $('xr-notes').replaceChildren(...a.notes.map(n => el('li', { text: n })));
    renderFraming();
    $('xr-gcount').textContent = a.groups.length;
    const orderPos = Object.fromEntries(a.reading_order.map((id, i) => [id, i + 1]));
    const idx = Object.fromEntries(a.groups.map((g, i) => [g.id, i]));
    const groupItem = (g, i) => {
      const roles = [...new Set(g.members.map(m => label(a.roles[m]?.role || '?')).filter(r => r !== 'shape'))];
      const b = el('button', { class: 'xr-group', type: 'button', 'data-id': g.id,
        'aria-label': `Group ${orderPos[g.id]}: ${g.kind}, ${label(g.role)}. Contains ${roles.join(', ')}. Anchored ${g.anchors.join(', ') || 'nowhere'}.`,
        onmouseenter: () => setHot(g.id), onfocus: () => setHot(g.id), onmouseleave: () => setHot(null), onblur: () => setHot(null) },
      el('span', { class: 'n', style: `background:${color(i)}`, text: orderPos[g.id] }),
      el('span', { class: 't' }, el('b', { text: title(g) }), el('small', { text: roles.join(', ') })),
      el('span', { class: 'a', text: g.anchors.join(' ') }));
      return el('li', {}, b);
    };
    const BLOCK = { copy: 'Copy block', repeat: 'Repeated items', stack: 'Stack' };
    const items = [];
    for (const bl of (a.blocks || a.groups.map(g => ({ id: g.id, kind: 'single', groups: [g.id] })))) {
      const gs = bl.groups.map(id => [a.groups[idx[id]], idx[id]]).sort((p, q) => orderPos[p[0].id] - orderPos[q[0].id]);
      if (bl.kind === 'single') { items.push(groupItem(...gs[0])); continue; }
      const what = [...new Set(gs.map(([g]) => label(g.role)))].join(' + ');
      const head = el('button', { class: 'xr-block', type: 'button', 'data-id': bl.id,
        'aria-label': `${BLOCK[bl.kind]}: ${what}. These groups move together when the design is resized.`,
        onmouseenter: () => setHot(bl.id), onfocus: () => setHot(bl.id), onmouseleave: () => setHot(null), onblur: () => setHot(null) },
        el('span', { class: 'bk', text: BLOCK[bl.kind] }), el('small', { text: what }));
      items.push(el('li', { class: 'xr-block-li' }, head, el('ol', { class: 'xr-groups nested' }, ...gs.map(([g, i]) => groupItem(g, i)))));
    }
    $('xr-groups').replaceChildren(...items);
    $('xr-tiers').replaceChildren(...(a.targets || []).map(t => {
      const k = Math.min(40 / t.width, 32 / t.height);
      return el('li', { class: 'xr-tier' },
        el('span', { class: 'xr-shape', 'aria-hidden': 'true' }, el('i', { style: `width:${Math.max(3, t.width * k)}px;height:${Math.max(3, t.height * k)}px` })),
        el('span', {}, el('b', { text: t.name || `${t.width}×${t.height}` }),
          el('small', { text: `${t.width}×${t.height} · ${t.reasons.join(' · ')}` })),
        el('span', { class: `xr-badge t${t.tier}`, text: `Tier ${t.tier} · ${t.tier_name}` }));
    }));
  }

  // ---------------------------------------------------------------- resize view
  S.view = 'understand';
  function setView(v) {
    S.view = v;
    $('tab-understand').setAttribute('aria-selected', String(v === 'understand'));
    $('tab-resize').setAttribute('aria-selected', String(v === 'resize'));
    $('tab-understand').tabIndex = v === 'understand' ? 0 : -1;   // roving tabindex: one tab stop for the tab list
    $('tab-resize').tabIndex = v === 'resize' ? 0 : -1;
    $('xr-main').hidden = v !== 'understand';
    $('xr-resize').hidden = v !== 'resize';
    const dm = location.hash.match(/d=([\w-]+)/);
    if (dm) history.replaceState(null, '', '#d=' + dm[1] + (v === 'resize' ? '&v=resize' : ''));
    if (v === 'resize') runAdapt(); else fit();
  }
  function fitScale(w, h, box = 260, boxH = 220) { return Math.min(box / w, boxH / h); }
  // the other layouts Chameleon tried for this size, scored; select one to see it (with its checks and reasons)
  function altStrip(r, onPick) {
    if (!r.alternatives || !r.alternatives.length) return null;
    const options = [{ label: r.layout_label || 'Chosen layout', design: r.design, score: r.score, checks: r.checks, reasons: r.reasons, chosen: true },
      ...r.alternatives.map(x => ({ label: x.label, design: x.design, score: x.score, checks: x.checks, reasons: x.reasons }))];
    const btns = options.map((o, i) => {
      const cv = el('canvas', { 'aria-hidden': 'true' });
      GR.draw(cv, o.design, { scale: fitScale(r.width, r.height, 96, 64) });
      const b = el('button', { class: 'rz-alt' + (i === 0 ? ' on' : ''), type: 'button', 'aria-pressed': String(i === 0),
        title: o.chosen ? 'The layout Chameleon chose' : 'Another layout Chameleon tried' },
        cv, el('span', {}, el('b', { text: o.label }), el('small', { text: `${o.chosen ? 'Chosen · ' : ''}score ${Math.round(o.score.overall)}` })));
      b.onclick = () => {
        onPick(o);
        btns.forEach(x => { x.classList.toggle('on', x === b); x.setAttribute('aria-pressed', String(x === b)); });
      };
      return b;
    });
    return el('div', { class: 'rz-alts', role: 'group', 'aria-label': 'Layouts Chameleon tried' },
      el('span', { class: 'rz-alts-h', text: 'Layouts tried' }), ...btns);
  }
  async function runAdapt() {
    if (!S.design) return;
    const ticket = (S.rzTicket = (S.rzTicket || 0) + 1);
    $('rz-list').replaceChildren(el('p', { class: 'xr-hint', text: 'Laying out every size…' }));
    let res;
    try { res = await api('/adapt', { design: S.design }); } catch (e) { showError(e.message); return; }
    if (ticket !== S.rzTicket) return;
    if (document.fonts && document.fonts.ready) await document.fonts.ready;
    const src = Object.fromEntries(S.design.nodes.filter(n => n.src).map(n => [n.id, n.src]));
    const d0 = S.design, W0 = d0.page.width, H0 = d0.page.height;
    $('rz-title').textContent = `Resize · ${d0.name || 'design'}`;
    let ok = 0, keptAll = 0, nKept = 0, cropCut = 0, stretched = 0, sumC = 0, sumB = 0, nS = 0;
    const rows = res.results.map(r => {
      for (const d of [r.design, ...(r.alternatives || []).map(x => x.design)])
        for (const n of d.nodes) if (n.srcFrom && src[n.srcFrom]) n.src = src[n.srcFrom];
      const c = r.checks, b = r.baselines;
      if (c.ok) ok++;
      if (c.subject_kept != null) { keptAll += c.subject_kept; nKept++; }
      if (b.crop.cut.length) cropCut++;
      if (b.stretch.distortion > 1.15) stretched++;
      const sc = fitScale(r.width, r.height);
      const mk = (draw) => { const cv = el('canvas', { role: 'img' }); draw(cv); return cv; };
      const stretch = mk(cv => { cv.setAttribute('aria-label', `Stretched to ${r.width} by ${r.height}`);
        GR.draw(cv, d0, { scale: sc, view: { width: r.width, height: r.height, sx: r.width / W0, sy: r.height / H0 } }); });
      const crop = mk(cv => { cv.setAttribute('aria-label', `Centre-cropped to ${r.width} by ${r.height}`);
        GR.draw(cv, d0, { scale: sc, view: { width: r.width, height: r.height, sx: b.crop.scale, sy: b.crop.scale, ox: b.crop.offset[0], oy: b.crop.offset[1] } }); });
      const cham = mk(cv => { cv.setAttribute('aria-label', `Chameleon layout at ${r.width} by ${r.height}`); GR.draw(cv, r.design, { scale: sc }); });
      const tag = (text, kind) => el('span', { class: 'rz-tag' + (kind ? ' ' + kind : ''), text });
      const col = (title, canvas, tags, win) => el('div', { class: 'rz-col' + (win ? ' win' : '') },
        el('h3', { text: title }), el('div', { class: 'rz-cell' }, canvas), el('div', { class: 'rz-tags' }, ...tags.filter(Boolean)));
      const checkTags = (c) => {
        const t = [
          tag(c.overlaps.length ? `${c.overlaps.length} overlap${c.overlaps.length > 1 ? 's' : ''}` : 'No overlaps', c.overlaps.length ? 'bad' : 'good'),
          tag(c.off_canvas.length ? `${c.off_canvas.length} off canvas` : 'All inside', c.off_canvas.length ? 'bad' : 'good'),
          tag(c.small_text.length ? `${c.small_text.length} text under 12px` : 'Text ≥ 12px', c.small_text.length ? 'bad' : 'good'),
        ];
        if (c.subject_kept != null) t.push(tag(`Subject ${Math.round(c.subject_kept * 100)}% kept`, c.subject_kept >= .95 ? 'good' : ''));
        return t;
      };
      const chamTags = checkTags(c);
      const scoreTag = (sc) => {
        if (!sc) return null;
        const t = tag(`Score ${Math.round(sc.overall)}`, 'score');
        t.tabIndex = 0;
        t.title = `Content ${Math.round(sc.content)} · Legibility ${Math.round(sc.legibility)} · Faithfulness ${Math.round(sc.faithfulness)} · Composition ${Math.round(sc.composition)}` +
          (sc.subject != null ? ` · Subject ${Math.round(sc.subject)}` : '') + (sc.notes.length ? '\n' + sc.notes.join(' ') : '');
        t.setAttribute('aria-label', `Score ${Math.round(sc.overall)} out of 100. ` + t.title.replace(/\n/g, ' '));
        t.onclick = () => { const open = t.dataset.open === '1'; t.dataset.open = open ? '' : '1';
          t.textContent = open ? `Score ${Math.round(sc.overall)}` : t.title.split('\n')[0]; };   // touch: tap to see the parts
        t.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); t.onclick(); } };
        return t;
      };
      if (r.score) { chamTags.unshift(scoreTag(r.score)); sumC += r.score.overall; sumB += Math.max(b.stretch.score.overall, b.crop.score.overall); nS++; }
      const stretchTags = [scoreTag(b.stretch.score), tag(b.stretch.distortion > 1.02 ? `Distorted ${b.stretch.distortion.toFixed(2)}×` : 'No distortion', b.stretch.distortion > 1.15 ? 'bad' : '')];
      const cropTags = [scoreTag(b.crop.score), tag(b.crop.cut.length ? `${b.crop.cut.length} element${b.crop.cut.length > 1 ? 's' : ''} cut off` : 'Nothing cut off', b.crop.cut.length ? 'bad' : '')];
      if (b.crop.subject_kept != null) cropTags.push(tag(`Subject ${Math.round(b.crop.subject_kept * 100)}% kept`, b.crop.subject_kept < .95 ? 'bad' : ''));
      const why = el('ul', { class: 'rz-why' }, ...r.reasons.map(x => el('li', { text: x })));
      const chamCol = col('Chameleon', cham, chamTags, true);
      // picking another layout swaps the frame, its score, its checks and its reasons together
      const strip = altStrip(r, o => {
        GR.draw(cham, o.design, { scale: sc });
        chamCol.querySelector('.rz-tags').replaceChildren(...[scoreTag(o.score), ...checkTags(o.checks)].filter(Boolean));
        why.replaceChildren(...o.reasons.map(x => el('li', { text: x })));
      });
      if (strip) chamCol.append(strip);
      return el('article', { class: 'rz-row', 'aria-label': `${r.name || ''} ${r.width} by ${r.height}` },
        el('div', { class: 'rz-row-head' }, el('b', { text: r.name || `${r.width}×${r.height}` }),
          el('span', { class: 'dim', text: `${r.width}×${r.height}` }),
          el('span', { class: `xr-badge t${r.tier}`, text: `Tier ${r.tier} · ${r.tier_name}` })),
        el('div', { class: 'rz-cols' }, col('Stretch', stretch, stretchTags), col('Centre crop', crop, cropTags), chamCol),
        why);
    });
    const stat = (n, label) => el('div', { class: 'rz-stat' }, el('b', { text: n }), el('small', { text: label }));
    $('rz-score').replaceChildren(...(nS ? [stat(`${Math.round(sumC / nS)} vs ${Math.round(sumB / nS)}`, 'avg score: Chameleon vs better of stretch / crop')] : []),
      stat(`${ok}/${res.results.length}`, 'sizes pass every check'),
      stat(`${stretched}`, 'sizes distorted by stretching'), stat(`${cropCut}`, 'sizes where cropping cuts content'),
      ...(nKept ? [stat(`${Math.round(keptAll / nKept * 100)}%`, 'photo subject kept (avg)')] : []));
    $('rz-list').replaceChildren(...rows);
  }

  // ---------------------------------------------------------------- data flow
  async function show(design) {
    const ticket = (S.ticket = (S.ticket || 0) + 1);
    try {
      const analysis = await api('/analyze', { design });
      if (ticket !== S.ticket) return false;   // a newer design was picked meanwhile
      for (const [id, s] of Object.entries(analysis.subjects || {})) {   // draw photos with the engine's crop
        const node = design.nodes.find(n => n.id === id);
        if (node && node.src && s.crop) {
          if (!node.crop || autoCropped.has(node)) autoCropped.add(node);   // the engine's framing, not the designer's
          node.crop = s.crop;
        }
      }
      if (design !== S.design) S.frameMode = null;
      S.design = design; S.analysis = analysis; S.hot = null;
      if (document.fonts && document.fonts.ready) await document.fonts.ready;
      renderPanel(); fit();
      if (S.view === 'resize') runAdapt();
      return true;
    } catch (e) { if (ticket === S.ticket) showError(e.message); return false; }
  }
  async function pick(id) {
    S.mine = null;
    try { await show(await api('/testset/' + encodeURIComponent(id))); history.replaceState(null, '', '#d=' + id + (S.view === 'resize' ? '&v=resize' : '')); }
    catch (e) { showError(e.message); }
  }

  // ---------------------------------------------------------------- photo framing (auto / focus area / whole photo)
  const autoCropped = new WeakSet();
  const FRAME_HINT = {
    auto: 'Chameleon finds the subject (faces, people, objects) and frames every size around it.',
    focusNew: 'Drag on the photo to mark what must stay in view at every size.',
    focus: 'Every size keeps your focus area in view. Drag on the photo to redraw it.',
    whole: 'Every size shows the entire photo, never cropped. Space around it is filled, not left blank.',
  };
  function framingOf(t) {
    const m = (t && t.meta) || {};
    return m.keepWhole ? 'whole' : m.focus ? 'focus' : 'auto';
  }
  function renderFraming() {
    const card = $('xr-frame-card');
    const t = S.design && S.analysis && photoTarget(S.design, S.analysis);
    card.hidden = !(t && t.src && S.analysis.subjects[t.id]);
    if (card.hidden) { $('xr-art').classList.remove('drawing'); return; }
    const mode = S.frameMode || framingOf(t);
    card.querySelectorAll('[data-mode]').forEach(b => { b.setAttribute('aria-checked', String(b.dataset.mode === mode)); b.tabIndex = b.dataset.mode === mode ? 0 : -1; });
    $('xr-frame-hint').textContent = mode === 'focus' ? (t.meta && t.meta.focus ? FRAME_HINT.focus : FRAME_HINT.focusNew) : FRAME_HINT[mode];
    $('xr-art').classList.toggle('drawing', mode === 'focus');
  }
  async function setFraming(mode, focus) {
    const t0 = photoTarget(S.design, S.analysis);
    if (!t0) return;
    if (mode === 'focus' && !focus) {             // wait for the designer to draw the box
      S.frameMode = 'focus'; renderFraming();
      if (!(t0.meta && t0.meta.focus)) return;
      focus = t0.meta.focus;
    }
    const d = JSON.parse(JSON.stringify(S.design));
    S.design.nodes.forEach((n, i) => { if (autoCropped.has(n)) delete d.nodes[i].crop; });   // let the engine re-frame
    const t = d.nodes.find(n => n.id === t0.id);
    const meta = { ...(t.meta || {}) };
    delete meta.focus; delete meta.keepWhole;
    if (mode === 'focus') meta.focus = focus.map(v => Math.round(v * 1e4) / 1e4);
    if (mode === 'whole') meta.keepWhole = true;
    t.meta = meta;
    const btns = $('xr-frame-card').querySelectorAll('button');
    btns.forEach(b => (b.disabled = true));
    const mine = S.mine;
    try { if (await show(d)) S.mine = mine; } finally { btns.forEach(b => (b.disabled = false)); S.frameMode = null; renderFraming(); }
  }
  function artPoint(ev) {
    const r = $('xr-art').getBoundingClientRect();
    return [(ev.clientX - r.left) / S.scale, (ev.clientY - r.top) / S.scale];
  }
  function startFocusDraw(ev) {
    if (!$('xr-art').classList.contains('drawing') || ev.button !== 0) return;
    const t = photoTarget(S.design, S.analysis);
    if (!t) return;
    const [bx, by, bw, bh] = t.box;
    const W = S.design.page.width, H = S.design.page.height;
    const vis = [Math.max(0, bx), Math.max(0, by), Math.min(W, bx + bw), Math.min(H, by + bh)];
    const clamp = ([x, y]) => [Math.min(vis[2], Math.max(vis[0], x)), Math.min(vis[3], Math.max(vis[1], y))];
    const p0 = artPoint(ev);
    if (p0[0] < vis[0] || p0[0] > vis[2] || p0[1] < vis[1] || p0[1] > vis[3]) return;
    ev.preventDefault();
    const art = $('xr-art'); art.setPointerCapture(ev.pointerId);
    const draft = svg('rect', { class: 'focus-draft', x: p0[0], y: p0[1], width: 0, height: 0 }, $('xr-overlay'));
    let box = null;
    const move = e => {
      const p = clamp(artPoint(e));
      box = [Math.min(p0[0], p[0]), Math.min(p0[1], p[1]), Math.abs(p[0] - p0[0]), Math.abs(p[1] - p0[1])];
      draft.setAttribute('x', box[0]); draft.setAttribute('y', box[1]); draft.setAttribute('width', box[2]); draft.setAttribute('height', box[3]);
    };
    const up = () => {
      art.removeEventListener('pointermove', move); art.removeEventListener('pointerup', up); art.removeEventListener('pointercancel', up);
      draft.remove();
      const min = 12 / S.scale;                          // ignore a click or a tiny accidental drag
      if (!box || box[2] < min || box[3] < min) return;
      const [cx, cy, cw, ch] = t.crop || [0, 0, 1, 1];   // canvas → image: through the crop the photo is drawn with
      const u = v => Math.min(1, Math.max(0, v));
      const x0 = u(cx + (box[0] - bx) / bw * cw), y0 = u(cy + (box[1] - by) / bh * ch);
      const x1 = u(cx + (box[0] + box[2] - bx) / bw * cw), y1 = u(cy + (box[1] + box[3] - by) / bh * ch);
      setFraming('focus', [x0, y0, x1 - x0, y1 - y0]);
    };
    art.addEventListener('pointermove', move); art.addEventListener('pointerup', up); art.addEventListener('pointercancel', up);
  }

  // ---------------------------------------------------------------- your photo
  function photoTarget(d, a) {
    const imgs = d.nodes.filter(n => n.type === 'image' && !['logo', 'decoration'].includes(a?.roles[n.id]?.role));
    const rank = n => ({ background: 3, hero: 2 }[a?.roles[n.id]?.role] || 1) * 1e9 + n.box[2] * n.box[3];
    return imgs.sort((p, q) => rank(q) - rank(p))[0] || null;
  }
  function fileToDataURL(file, maxSide = 1600) {
    // send the WHOLE photo: the engine finds the subject first, then chooses the crop around it
    return new Promise((resolve, reject) => {
      const url = URL.createObjectURL(file), im = new Image();
      im.onload = () => {
        const sw = im.naturalWidth, sh = im.naturalHeight, sx = 0, sy = 0;
        const k = Math.min(1, maxSide / Math.max(sw, sh));
        const c = document.createElement('canvas'); c.width = Math.round(sw * k); c.height = Math.round(sh * k);
        c.getContext('2d').drawImage(im, sx, sy, sw, sh, 0, 0, c.width, c.height);
        URL.revokeObjectURL(url); resolve({ src: c.toDataURL('image/jpeg', .88), aspect: sw / sh });
      };
      im.onerror = () => { URL.revokeObjectURL(url); reject(new Error('That file is not an image this browser can open.')); };
      im.src = url;
    });
  }
  async function usePhoto(file) {
    if (!file || !S.design) return;
    if (!/^image\/(png|jpeg|webp)$/.test(file.type)) return showError('Use a PNG, JPG or WebP image.');
    if (file.size > 25e6) return showError('That image is over 25 MB. Try a smaller one.');
    const d = JSON.parse(JSON.stringify(S.design));
    const target = photoTarget(d, S.analysis);
    if (!target) return showError('This design has no photo to replace. Pick one with a photo, e.g. “Travel overlay”.');
    try {
      const img = await fileToDataURL(file);
      target.src = img.src;
      // a new photo: Chameleon frames it around its subject at every size, the original size included.
      // A design can pin its framing instead (meta.fixedCrop, e.g. the comparison ad that must start from the
      // same frame as the other editors): then the photo is placed centred, filling the slot, at the original size.
      if (target.meta && target.meta.fixedCrop) {
        const slot = target.box[2] / Math.max(1, target.box[3]);
        target.crop = img.aspect > slot ? [(1 - slot / img.aspect) / 2, 0, slot / img.aspect, 1]
                                        : [0, (1 - img.aspect / slot) / 2, 1, img.aspect / slot];
      } else delete target.crop;
      delete target.subject;                 // make the engine find it
      target.meta = { ...(target.meta || {}), label: 'your photo' };
      delete target.meta.focus;              // a focus area drawn on the previous photo means nothing on this one
      S.mine = target.id;
      await show(d);
    } catch (e) { showError(e.message); }
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
    $('xr-report-icon').replaceChildren(Icon('chart'));
    $('xr-photo-icon').replaceChildren(Icon('image'));
    $('tab-understand').onclick = () => setView('understand');
    $('tab-resize').onclick = () => setView('resize');
    for (const id of ['tab-understand', 'tab-resize']) $(id).addEventListener('keydown', e => {
      if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') { const o = id === 'tab-understand' ? 'tab-resize' : 'tab-understand'; $(o).focus(); $(o).click(); }
    });
    $('xr-photo').addEventListener('change', e => { const f = e.target.files[0]; e.target.value = ''; usePhoto(f); });
    const stage = document.querySelector('.xr-stage');
    let depth = 0;
    const hasFile = e => [...(e.dataTransfer?.types || [])].includes('Files');
    stage.addEventListener('dragenter', e => { if (!hasFile(e)) return; e.preventDefault(); depth++; $('xr-drop').hidden = false; });
    stage.addEventListener('dragover', e => { if (hasFile(e)) e.preventDefault(); });
    stage.addEventListener('dragleave', () => { if (--depth <= 0) { depth = 0; $('xr-drop').hidden = true; } });
    stage.addEventListener('drop', e => { if (!hasFile(e)) return; e.preventDefault(); depth = 0; $('xr-drop').hidden = true; usePhoto(e.dataTransfer.files[0]); });
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
    $('xr-art').addEventListener('pointerdown', startFocusDraw);
    const seg = $('xr-frame-card').querySelector('.xr-seg');
    seg.addEventListener('click', e => { const b = e.target.closest('[data-mode]'); if (b && !b.disabled) setFraming(b.dataset.mode); });
    seg.addEventListener('keydown', e => {                 // radio group: arrows move the choice
      if (!['ArrowRight', 'ArrowLeft', 'ArrowDown', 'ArrowUp'].includes(e.key)) return;
      e.preventDefault();
      const bs = [...seg.querySelectorAll('[data-mode]')], i = bs.findIndex(b => b.getAttribute('aria-checked') === 'true');
      const n = bs[(i + (e.key === 'ArrowRight' || e.key === 'ArrowDown' ? 1 : bs.length - 1)) % bs.length];
      n.focus(); setFraming(n.dataset.mode);
    });
    $('xr-art').addEventListener('pointerleave', () => setHot(null));
    $('xr-design').addEventListener('change', e => { if (e.target.value && !e.target.value.startsWith('import:')) pick(e.target.value); });
    $('xr-file').addEventListener('change', async e => {
      const f = e.target.files[0]; e.target.value = ''; if (!f) return;
      try {
        const d = JSON.parse(await f.text());
        if (!d || typeof d !== 'object' || Array.isArray(d)) throw new Error('expected a design object');
        if (!d.nodes && d.elements) { showError('This is a studio file. Open it in the studio, or convert it to chameleon-graph/1.'); return; }
        const prevMine = S.mine; S.mine = null;
        if (await show(d)) {
          const opt = el('option', { value: 'import:' + f.name, text: 'Imported · ' + f.name });
          $('xr-design').append(opt); $('xr-design').value = opt.value;
        } else S.mine = prevMine;
      } catch (err) { showError('Could not read that file: ' + err.message); }
    });
    new ResizeObserver(() => fit()).observe(document.querySelector('.xr-stage'));
    window.addEventListener('hashchange', () => {
      const m = location.hash.match(/d=([\w-]+)/);
      if (m && [...$('xr-design').options].some(o => o.value === m[1]) && $('xr-design').value !== m[1]) { $('xr-design').value = m[1]; pick(m[1]); }
    });
    api('/testset').then(ts => {
      S.sizes = ts.sizes;
      const groups = {};
      ts.designs.forEach(d => (groups[d.level] = groups[d.level] || []).push(d));
      for (const lvl of ['simple', 'medium', 'hard', ...Object.keys(groups).filter(x => !['simple', 'medium', 'hard'].includes(x))]) {
        if (!groups[lvl]) continue;
        $('xr-design').append(el('optgroup', { label: 'Test designs · ' + lvl },
          ...groups[lvl].map(d => el('option', { value: d.id, text: `${d.name} · ${d.width}×${d.height}` }))));
      }
      const m = location.hash.match(/d=([\w-]+)/);
      let fromStudio = null;
      if (/from=studio/.test(location.hash)) { try { fromStudio = JSON.parse(localStorage.getItem('chameleon.xray.design') || 'null'); } catch { /* none */ } }
      if (fromStudio) $('xr-back').href = '/how#from=studio';
      if (fromStudio && Array.isArray(fromStudio.nodes)) {        // opened from the Studio (via How it works)
        const opt = el('option', { value: 'import:studio', text: 'From the Studio · ' + (fromStudio.name || 'your design') });
        $('xr-design').prepend(opt); $('xr-design').value = opt.value;
        show(fromStudio);
      } else {
        const first = (m && ts.designs.find(d => d.id === m[1])) ? m[1] : ts.designs[0]?.id;
        if (first) { $('xr-design').value = first; pick(first); }
      }
      if (/v=resize/.test(location.hash)) setView('resize');
    }).catch(e => showError(e.message));
  }
  boot();
  window.XR = { S, show, pick, setView, runAdapt };
})();
