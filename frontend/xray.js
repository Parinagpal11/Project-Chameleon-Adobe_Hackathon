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
    const g = svg('g', { class: 'pill' }, parent);
    svg('rect', { x, y: ty, width: w, height: h, rx: h / 2 }, g);
    svg('circle', { cx: x + padX + dot / 2, cy: ty + h / 2, r: dot / 2 }, g);
    const t = svg('text', { x: x + padX + dot + 5 * k, y: ty + h / 2 + fs * .36, 'font-size': fs }, g);
    t.textContent = text;
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
      // one clean frame per subject (each face separately), label outside so it never covers the subject
      const frames = [];
      for (const [id, s] of Object.entries(a.subjects)) {
        const boxes = s.page_parts && s.page_parts.length ? s.page_parts : [s.page_box];
        const many = boxes.length > 1;
        boxes.forEach((b, i) => frames.push({ b, text: s.source === 'faces' ? (many ? `Face ${i + 1}` : 'Face') : s.source === 'people' ? (many ? `Person ${i + 1}` : 'Person') : (s.source === 'assumed' ? 'Centre (no subject found)' : 'Subject'), dim: s.source === 'assumed' }));
      }
      // labels avoid the design's other elements (logo, text, buttons) and each other
      const photoIds = new Set(Object.keys(a.subjects));
      const avoid = a.groups.filter(g => !g.members.some(m => photoIds.has(m))).map(g => g.box);
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
        pill(G, sx, sy, text, k, { below: true });
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
    if (S.on.order) {
      const byId = Object.fromEntries(a.groups.map((g, i) => [g.id, { g, i }]));
      const pts = a.reading_order.map(id => byId[id]).filter(Boolean);
      pts.forEach(({ g, i }, n) => {
        const r = 11 * k, cx = g.box[0] + r * .2, cy = g.box[1] + r * .2;
        svg('circle', { cx, cy, r, fill: color(i), stroke: '#fff', 'stroke-width': 2 }, o);
        const t = svg('text', { x: cx, y: cy + 4 * k, 'font-size': 12 * k, fill: '#fff', 'text-anchor': 'middle' }, o);
        t.textContent = n + 1;

      });
    }
  }

  function setHot(id) {
    const changed = S.hot !== id;
    S.hot = id;
    if (changed) drawOverlay();
    document.querySelectorAll('.xr-overlay .grp').forEach(g => g.classList.toggle('on', g.dataset.id === id));
    document.querySelectorAll('.xr-group').forEach(b => b.classList.toggle('on', b.dataset.id === id));
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
        text: `Your photo: subject ${({ saliency: 'found by saliency', faces: 'found by face detection', people: 'found by person detection', assumed: 'not found, centre assumed', given: 'given' })[a.subjects[S.mine].source]} · confidence ${Math.round(a.subjects[S.mine].confidence * 100)}% ${a.subjects[S.mine].source !== 'assumed' && a.subjects[S.mine].kept != null ? ` · ${Math.round(a.subjects[S.mine].kept * 100)}% of it kept in the crop` : ''}` }) : null].filter(Boolean));
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
      return el('li', { class: 'xr-tier' },
        el('span', { class: 'xr-shape', 'aria-hidden': 'true' }, el('i', { style: `width:${Math.max(3, t.width * k)}px;height:${Math.max(3, t.height * k)}px` })),
        el('span', {}, el('b', { text: t.name || `${t.width}×${t.height}` }),
          el('small', { text: `${t.width}×${t.height} · ${t.reasons.join(' · ')}` })),
        el('span', { class: `xr-badge t${t.tier}`, text: `Tier ${t.tier} · ${t.tier_name}` }));
    }));
  }

  // ---------------------------------------------------------------- data flow
  async function show(design) {
    const ticket = (S.ticket = (S.ticket || 0) + 1);
    try {
      const analysis = await api('/analyze', { design });
      if (ticket !== S.ticket) return false;   // a newer design was picked meanwhile
      for (const [id, s] of Object.entries(analysis.subjects || {})) {   // draw photos with the engine's crop
        const node = design.nodes.find(n => n.id === id);
        if (node && node.src && s.crop) node.crop = s.crop;
      }
      S.design = design; S.analysis = analysis; S.hot = null;
      if (document.fonts && document.fonts.ready) await document.fonts.ready;
      renderPanel(); fit();
      return true;
    } catch (e) { if (ticket === S.ticket) showError(e.message); return false; }
  }
  async function pick(id) {
    S.mine = null;
    try { await show(await api('/testset/' + encodeURIComponent(id))); history.replaceState(null, '', '#d=' + id); }
    catch (e) { showError(e.message); }
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
        URL.revokeObjectURL(url); resolve(c.toDataURL('image/jpeg', .88));
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
      target.src = await fileToDataURL(file);
      delete target.crop;
      delete target.subject;                 // make the engine find it
      target.meta = { ...(target.meta || {}), label: 'your photo' };
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
    $('xr-photo-icon').replaceChildren(Icon('image'));
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
