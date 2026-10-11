/* Chameleon — "How it works": the engine runs on a real design and each step shows what it did. */
'use strict';
(function () {
  const $ = id => document.getElementById(id);
  const DPR = Math.min(2, window.devicePixelRatio || 1);
  const REDUCED = matchMedia('(prefers-reduced-motion: reduce)');
  function el(tag, attrs = {}, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === 'class') n.className = v; else if (k === 'text') n.textContent = v; else if (k === 'style') n.style.cssText = v;
      else if (k.startsWith('on')) n.addEventListener(k.slice(2), v); else n.setAttribute(k, v === true ? '' : v);
    }
    for (const c of kids.flat()) if (c != null && c !== false) n.append(c);
    return n;
  }
  async function api(path, data) {
    let r;
    try { r = await fetch(path, data ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) } : {}); }
    catch { throw Error('Can’t reach the Chameleon server. Is it still running?'); }
    const v = await r.json().catch(() => null);
    if (!r.ok) throw Error((v && v.detail) || `Request failed (${r.status})`);
    return v;
  }
  function err(msg) { const e = $('how-error'); e.textContent = msg; e.hidden = false; setTimeout(() => { e.hidden = true; }, 7000); }
  const draw = (g, w, h) => { const c = el('canvas', { 'aria-hidden': 'true' }); window.GR.draw(c, g, { scale: Math.min(w / g.page.width, h / g.page.height), dpr: DPR }); return c; };
  const plain = rs => (rs || []).filter(r => !/^Tier \d/.test(r));
  const SIZES = [['Instagram Post', 1080, 1080], ['Instagram Story', 1080, 1920], ['Feed post', 1200, 628], ['LinkedIn banner', 1584, 396], ['Leaderboard', 728, 90], ['Medium rectangle', 300, 250]];
  const TIER = { 1: ['Keep the layout', 'Close to the original shape: everything stays where you put it, scaled and re-wrapped.'],
    2: ['Re-flow it', 'A new orientation: photo and copy are re-arranged (beside, above, or around the subject).'],
    3: ['Rebuild it', 'An extreme shape: the layout is rebuilt for it, and secondary text may be left out.'] };
  const ROLE = { headline: 'Headline', subhead: 'Subhead', body: 'Body text', cta: 'Button', logo: 'Logo', legal: 'Legal line', eyebrow: 'Eyebrow', offer: 'Offer', hero: 'Photo', image: 'Photo', photo: 'Photo' };

  /* theme */
  function paintTheme() { const b = $('how-theme'); b.replaceChildren(window.Icon(document.documentElement.dataset.theme === 'dark' ? 'sun' : 'moon')); }
  $('how-theme').onclick = () => { const t = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'; document.documentElement.dataset.theme = t; try { localStorage.setItem('chameleon.theme', t); } catch { /* private */ } paintTheme(); };
  paintTheme();

  /* where we came from: the Studio (back to that campaign) or the home page */
  const fromStudio = /from=studio/.test(location.hash);
  let studioDesign = null;
  if (fromStudio) {
    try { studioDesign = JSON.parse(localStorage.getItem('chameleon.xray.design') || 'null'); } catch { /* none */ }
    const back = localStorage.getItem('chameleon.how.back');
    if (back && /^\/(#c=[\w-]+)?$/.test(back)) $('how-back').href = back;
    $('how-back-label').textContent = 'Back to your campaign';
    for (const id of ['engine-link', 'engine-link-2']) $(id).href = '/xray#from=studio';
    $('how-open').href = $('how-back').href; $('how-open').querySelector('span').textContent = 'Back to your campaign';
  }

  let state = null, sizeIdx = 1;
  async function run(design) {
    document.body.classList.add('loading');
    try {
      const [a, r] = await Promise.all([api('/analyze', { design }),
        api('/adapt', { design, targets: SIZES.map(([name, width, height]) => ({ name, width, height })) })]);
      const src = {};
      for (const n of design.nodes) if (n.src) src[n.id] = n.src;
      const fix = g => { for (const n of g.nodes) if (!n.src && n.srcFrom && src[n.srcFrom]) n.src = src[n.srcFrom]; return g; };
      r.results.forEach(x => { fix(x.design); (x.alternatives || []).forEach(o => fix(o.design)); });
      state = { design, a, r };
      paintRead(); paintPlan(); paintTry(); paintScores();
    } catch (e) { err(e.message); }
    finally { document.body.classList.remove('loading'); }
  }

  /* 1 · what it sees */
  function paintRead() {
    const { design, a } = state, host = $('read-art');
    const W = design.page.width, H = design.page.height;
    const maxW = Math.min(420, (host.clientWidth || 468) - 48), k = Math.min(maxW / W, 460 / H);
    const art = el('div', { class: 'art', style: `width:${W * k}px;height:${H * k}px` }, draw(design, W * k, H * k));
    const tags = [];
    for (const g of a.groups) {
      if (['background', 'panel', 'decoration'].includes(g.role)) continue;
      const [x, y, w, h] = g.box, name = ROLE[g.role] || g.role;
      tags.push(el('div', { class: 'gbox', style: `left:${x * k}px;top:${y * k}px;width:${w * k}px;height:${h * k}px;--d:${tags.length * 160}ms` }, el('span', { text: name })));
    }
    for (const s of Object.values(a.subjects || {})) {
      if (s.source === 'assumed') continue;
      const parts = s.page_parts && s.page_parts.length ? s.page_parts : [s.page_box];
      const name = { faces: 'Face', people: 'Person', focus: 'Your focus area', whole: 'Whole photo' }[s.source] || 'Main subject';
      parts.forEach(([x, y, w, h], i) => tags.push(el('div', { class: 'sbox', style: `left:${x * k}px;top:${y * k}px;width:${w * k}px;height:${h * k}px;--d:${tags.length * 160}ms` },
        el('span', { text: parts.length > 1 ? `${name} ${i + 1}` : name }))));
    }
    art.append(...tags);
    host.replaceChildren(art);
    const fig = $('read-photo'), sub = Object.values(a.subjects || {}).find(x => x.source !== 'assumed'), photo = design.nodes.find(n => n.type === 'image' && n.src && a.subjects[n.id]);
    fig.hidden = !(sub && photo);
    fig.querySelectorAll('.pwrap').forEach(n => n.remove());
    if (sub && photo) {
      const pw = Math.min(300, (fig.clientWidth || 300)), ph = pw / (sub.aspect || 1.5);
      const wrap = el('div', { class: 'pwrap', style: `width:${pw}px;height:${ph}px` }, el('img', { src: photo.src, alt: 'The whole photo', style: `width:${pw}px;height:${ph}px` }));
      const name = { faces: 'Face', people: 'Person', focus: 'Your focus area', whole: 'Whole photo' }[sub.source] || 'Subject';
      const parts = sub.parts && sub.parts.length ? sub.parts : [sub.box];
      parts.forEach(([x, y, w, h], i) => wrap.append(el('div', { class: 'sbox', style: `left:${x * pw}px;top:${y * ph}px;width:${w * pw}px;height:${h * ph}px;--d:${i * 160}ms` }, el('span', { text: parts.length > 1 ? `${name} ${i + 1}` : name }))));
      if (sub.crop) { const [cx, cy, cw, ch] = sub.crop; wrap.append(el('div', { class: 'cbox', style: `left:${cx * pw}px;top:${cy * ph}px;width:${cw * pw}px;height:${ch * ph}px` }, el('span', { text: 'Shown in your design' }))); }
      fig.append(wrap);
    }
    const facts = [];
    const roles = [...new Set(a.groups.map(g => ROLE[g.role]).filter(Boolean))];
    if (roles.length) facts.push(['Elements', roles.join(', ')]);
    for (const s of Object.values(a.subjects || {})) {
      const how = { faces: 'face detection', people: 'person detection', objects: 'object detection', saliency: 'what stands out', given: 'the designer', focus: 'your focus area', whole: 'your choice: keep the whole photo', assumed: 'nothing found, the centre is used' }[s.source] || s.source;
      facts.push(['Photo subject', `found by ${how}`]);
    }
    for (const n of a.notes.filter(n => /full-bleed|aligned|Copy block|airy|dense/i.test(n)).slice(0, 3)) facts.push(['Layout', n]);
    $('read-facts').replaceChildren(...facts.map(([t, v]) => el('li', {}, el('b', { text: t }), el('span', { text: v }))));
  }

  /* 2 · how much each size changes */
  function paintPlan() {
    const { design, r } = state, W0 = design.page.width, H0 = design.page.height;
    $('plan-row').replaceChildren(...r.results.map((x, i) => {
      const [name, w, h] = SIZES[i], s = Math.min(92 / w, 92 / h);
      let [t, d] = TIER[x.tier] || ['', ''];
      if (x.tier === 1 && (x.reasons || []).some(r => /layout was rebuilt/.test(r))) { t = 'Keep → rebuilt'; d = 'Keeping the layout would have hidden too much of the photo’s subject, so Chameleon rebuilt it.'; }
      return el('button', { class: 'plan-card t' + x.tier, onclick: () => { sizeIdx = i; paintTry(); $('step-try').scrollIntoView({ behavior: REDUCED.matches ? 'auto' : 'smooth', block: 'start' }); },
        'aria-label': `${name}, ${w} by ${h}: ${t}. Show the layouts tried for this size.` },
        el('span', { class: 'plan-shape' }, el('i', { style: `width:${w * s}px;height:${h * s}px` }), el('i', { class: 'orig', style: `width:${W0 * Math.min(92 / W0, 92 / H0) * .5}px;height:${H0 * Math.min(92 / W0, 92 / H0) * .5}px` })),
        el('b', { text: name }), el('small', { text: `${w}×${h}` }), el('span', { class: 'tier-chip', text: t }), el('span', { class: 'plan-d', text: d }));
    }));
  }

  /* 3 · the layouts tried for one size */
  function paintTry() {
    const { r } = state, x = r.results[sizeIdx], [, w, h] = SIZES[sizeIdx];
    $('try-tabs').replaceChildren(...SIZES.map(([name], i) => el('button', { role: 'tab', 'aria-selected': String(i === sizeIdx), tabindex: i === sizeIdx ? '0' : '-1', text: name,
      onclick: () => { sizeIdx = i; paintTry(); }, onkeydown: e => {
        if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
        sizeIdx = (sizeIdx + (e.key === 'ArrowRight' ? 1 : SIZES.length - 1)) % SIZES.length; paintTry(); $('try-tabs').children[sizeIdx].focus(); } })));
    const opts = [{ label: x.layout_label || 'Chameleon’s layout', g: x.design, s: x.score.overall, on: true, ok: x.checks.ok },
      ...(x.alternatives || []).map(o => ({ label: o.label, g: o.design, s: o.score_overall, ok: o.checks.ok }))];
    const big = opts.length <= 2, bw = w / h > 2 ? (big ? 420 : 300) : (big ? 220 : 150), bh = w / h > 2 ? 110 : (big ? 260 : 190);
    $('try-opts').replaceChildren(...opts.map(o => el('figure', { class: 'opt' + (o.on ? ' on' : '') }, draw(o.g, bw, bh),
      el('figcaption', {}, el('b', { text: o.label }), el('span', { class: 'score-chip' + (o.on ? ' good' : ''), text: `${o.on ? 'Picked · ' : ''}score ${Math.round(o.s)}` })))));
    if (opts.length === 1) $('try-opts').append(el('p', { class: 'small muted', text: 'At this size the first layout already scored best, so there was nothing better to show.' }));
    const tie = opts.slice(1).find(o => Math.round(o.s) === Math.round(opts[0].s));
    if (tie) $('try-opts').append(el('p', { class: 'small muted tie', text: `“${tie.label}” scored the same. On a tie Chameleon keeps the layout it built first, the one closest to your design; you can still pick the other in the Studio.` }));
    $('try-why').replaceChildren(...plain(x.reasons).slice(0, 6).map(t => el('li', {}, el('span', { text: t }))));
  }

  /* 4 · checks and scores vs plain resizes */
  function paintScores() {
    const { r } = state;
    const head = el('div', { class: 'srow head' }, el('span', { text: 'Size' }), el('span', { text: 'Checks' }), el('span', { text: 'Chameleon' }), el('span', { text: 'Centre crop' }), el('span', { text: 'Stretch' }));
    const bar = (v, cls, label) => el('span', { class: 'bar ' + cls, 'data-label': label }, el('i', { style: `width:${Math.max(2, v)}%` }), el('b', { text: Math.round(v) }));
    const rows = r.results.map((x, i) => {
      const c = x.checks, sc = x.score, fails = [c.overlaps.length && 'overlap', c.off_canvas.length && 'off the edge', c.small_text.length && 'small text', (c.low_contrast || []).length && 'contrast'].filter(Boolean);
      const parts = [['Kept', sc.content], ['Readable', sc.legibility], ['Faithful', sc.faithfulness], ['Composition', sc.composition], ['Subject', sc.subject]].filter(([, v]) => v != null);
      return el('div', { class: 'srow-wrap' },
        el('div', { class: 'srow' }, el('span', { class: 'sname' }, el('b', { text: SIZES[i][0] }), el('small', { text: `${SIZES[i][1]}×${SIZES[i][2]}` })),
          el('span', { class: 'score-chip ' + (fails.length ? 'bad' : 'good'), text: fails.length ? fails.join(', ') : '✓ all pass' }),
          bar(sc.overall, 'c', 'Chameleon'), bar(x.baselines.crop.score.overall, 'n', 'Centre crop'), bar(x.baselines.stretch.score.overall, 'n', 'Stretch')),
        el('div', { class: 'subscores' }, ...parts.map(([k, v]) => el('span', {}, `${k} `, el('b', { text: Math.round(v) }))),
          c.subject_kept != null ? el('span', {}, 'Photo subject in view ', el('b', { text: Math.round(c.subject_kept * 100) + '%' })) : null,
          (sc.notes || []).length ? el('span', { class: 'note', text: sc.notes[0] }) : null));
    });
    const avg = f => Math.round(r.results.reduce((n, x) => n + f(x), 0) / r.results.length);
    const sum = el('p', { class: 'score-sum' }, el('b', { text: `Average: Chameleon ${avg(x => x.score.overall)}` }), ` · centre crop ${avg(x => x.baselines.crop.score.overall)} · stretch ${avg(x => x.baselines.stretch.score.overall)} (out of 100).`,
      el('span', { class: 'muted', text: ' The overall score weighs what’s kept (25%), readability (25%), faithfulness to your design (20%), composition (20%) and the photo subject (10%). “Photo subject in view” is measured against what your original design showed of it. A size scores 100 only when every part does; the parts are shown under each row.' }));
    $('score-table').replaceChildren(head, ...rows, sum);
  }

  /* the design picker: your Studio design (if you came from it) and the templates */
  async function boot() {
    const sel = $('how-design');
    let list = [];
    try { list = await api('/templates'); } catch (e) { err(e.message); }
    if (studioDesign && Array.isArray(studioDesign.nodes)) sel.append(el('option', { value: 'studio', text: 'Your design · ' + (studioDesign.name || 'from the Studio') }));
    for (const t of list) sel.append(el('option', { value: t.id, text: t.name }));
    const load = async v => run(v === 'studio' ? studioDesign : await api('/example?name=' + encodeURIComponent(v)));
    sel.onchange = () => load(sel.value);
    if (sel.options.length) load(sel.value);
  }
  let rt; window.addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(() => state && paintRead(), 150); });
  boot();
})();
