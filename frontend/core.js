/* Chameleon Studio v3 — core: state, server sync, rules, history, projects, assets, export, theme. */
'use strict';
const $ = id => document.getElementById(id);
const R = window.ChameleonRender;
const clone = o => JSON.parse(JSON.stringify(o));
const DPR = Math.min(2, window.devicePixelRatio || 1);
const REDUCED = matchMedia('(prefers-reduced-motion: reduce)');

/* ───────── catalog ───────── */
const CATALOG = [
  { group: 'Social', items: [
    ['ig-story', 'Instagram Story', 1080, 1920], ['ig-post', 'Instagram Post', 1080, 1080], ['ig-portrait', 'Instagram Portrait', 1080, 1350],
    ['feed', 'Feed post (FB · LinkedIn)', 1200, 628], ['x-post', 'X post', 1600, 900], ['pin', 'Pinterest pin', 1000, 1500],
    ['yt', 'YouTube thumbnail', 1280, 720], ['li-banner', 'LinkedIn banner', 1584, 396]] },
  { group: 'Display ads', items: [
    ['leaderboard', 'Leaderboard', 728, 90], ['mrec', 'Medium rectangle', 300, 250], ['sky', 'Wide skyscraper', 160, 600],
    ['billboard', 'Billboard', 970, 250], ['interstitial', 'Mobile interstitial', 320, 480], ['mobile-lg', 'Large mobile banner', 320, 100]] },
];
const DEFAULT_SELECTED = ['ig-story', 'ig-post', 'feed', 'li-banner', 'mrec', 'leaderboard'];
const ROLES = ['headline', 'subtitle', 'offer', 'body', 'cta', 'logo', 'legal', 'hero', 'decoration'];
const ROLE_ICON = { headline: 'type', subtitle: 'type', offer: 'type', body: 'type', legal: 'type', cta: 'target', logo: 'sparkle', hero: 'image', decoration: 'sparkle' };
const RULE_ICON = { order: 'order', pin: 'pin', align: 'alignCenter', emphasis: 'size', hide_small: 'eyeOff' };
const STRATEGY = { hero_top: 'Image top', hero_small: 'Small image', stacked: 'Image bottom', text_left: 'Text left', text_right: 'Text right', row: 'One row', banner: 'Banner' };

/* ───────── state ───────── */
const S = {
  view: 'home', campaign: null, name: '', design: null, assets: {}, custom: [], selected: new Set(DEFAULT_SELECTED),
  results: {}, rules: [], roles: [], roleMap: {}, choices: {}, overrides: {}, metrics: {},
  sel: null, edit: null, pending: null, history: [], future: [], seq: 0, scope: 'frame', tool: 'move',
};
const App = { painters: [], paint(what) { for (const p of this.painters) p(what); } };

/* ───────── utils ───────── */
async function api(path, method = 'GET', data) {
  let r;
  try { r = await fetch(path, { method, headers: { 'Content-Type': 'application/json' }, body: data ? JSON.stringify(data) : undefined }); }
  catch { throw Error('Can’t reach the Chameleon server. Is `python run.py` still running?'); }
  let v = null; try { v = await r.json(); } catch { /* empty */ }
  if (!r.ok) throw Error((v && (typeof v.detail === 'string' ? v.detail : JSON.stringify(v.detail))) || `Request failed (${r.status})`);
  return v;
}
function el(tag, attrs = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false && !k.startsWith('aria-')) continue;
    if (k === 'class') n.className = v; else if (k === 'text') n.textContent = v; else if (k === 'style') n.style.cssText = v;
    else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
    else if (k.startsWith('aria-') && typeof v === 'boolean') n.setAttribute(k, String(v));
    else n.setAttribute(k, v === true ? '' : v);
  }
  for (const c of kids.flat()) if (c != null && c !== false) n.append(c);
  return n;
}
const ic = (name, cls) => window.Icon(name, cls);
const slug = s => String(s || 'design').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 40) || 'design';
const debounce = (fn, ms) => { let t; const d = (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; d.cancel = () => clearTimeout(t); return d; };
const store = { get(k) { try { return localStorage.getItem(k); } catch { return null; } }, set(k, v) { try { localStorage.setItem(k, v); } catch { /* private mode */ } } };
const roleOf = e => (e && e.genome && e.genome.role) || 'body';
const niceRole = r => ({ cta: 'CTA', hero: 'Photo' }[r] || (r ? r[0].toUpperCase() + r.slice(1) : ''));
const lowerRole = r => (r === 'cta' ? 'CTA' : niceRole(r).toLowerCase());
function elName(e) {
  if (!e) return '';
  if (e.type === 'image') return 'Photo';
  if (e.type === 'logo' && e.src) return 'Logo';
  const t = (e.text || '').trim();
  return t ? `${niceRole(roleOf(e))} · ${t.length > 22 ? t.slice(0, 21) + '…' : t}` : niceRole(roleOf(e));
}
function relTime(sec) {
  const d = Date.now() / 1000 - sec;
  if (d < 60) return 'just now'; if (d < 3600) return `${Math.floor(d / 60)} min ago`;
  if (d < 86400) return `${Math.floor(d / 3600)} h ago`; return new Date(sec * 1000).toLocaleDateString();
}
function busy(on) { document.body.classList.toggle('is-busy', !!on); }

function toast(msg, { action, onAction, error, strip, ms = 4200 } = {}) {
  const t = el('div', { class: 'toast' + (error ? ' err' : ''), role: error ? 'alert' : 'status' });
  const body = el('div', {}, el('div', { text: msg }));
  if (strip && strip.length) body.append(el('div', { class: 't-strip' }, strip.map(s => el('span', { text: s }))));
  t.append(body);
  if (action) t.append(el('button', { text: action, onclick: () => { onAction(); t.remove(); } }));
  $('toasts').append(t);
  setTimeout(() => t.remove(), ms);
  while ($('toasts').children.length > 2) $('toasts').firstChild.remove();
}

/* ───────── formats ───────── */
function allFormats() {
  const out = [];
  for (const g of CATALOG) for (const [key, name, width, height] of g.items) out.push({ key, name, width, height, group: g.group });
  for (const c of S.custom) out.push({ ...c, group: 'Custom' });
  return out;
}
const fmt = key => allFormats().find(f => f.key === key);
const activeFormats = () => allFormats().filter(f => S.selected.has(f.key));
function addFrame(key, quiet) {
  if (S.selected.has(key)) { if (!quiet) toast(`${fmt(key).name} is already on the canvas`); return; }
  const before = snapshot(); S.selected.add(key); recordDesignChange(`add ${fmt(key).name}`, before);
  refresh().then(() => { App.focusFrame?.(key); }); save();
  if (!quiet) toast(`Added ${fmt(key).name} · ${fmt(key).width}×${fmt(key).height}`);
}
function removeFrame(key) {
  if (S.selected.size <= 1) { toast('A campaign needs at least one frame.', { error: true }); return; }
  const before = snapshot(), f = fmt(key); S.selected.delete(key);
  if (S.sel && S.sel.key === key) S.sel = null;
  recordDesignChange(`remove ${f.name}`, before); refresh(); save();
  toast(`Removed ${f.name}`, { action: 'Undo', onAction: undo });
}

/* ───────── history ───────── */
function pushHistory(entry) { S.history.push(entry); if (S.history.length > 80) S.history.shift(); S.future = []; syncUndo(); }
function syncUndo() {
  $('undo').disabled = !S.history.length; $('redo').disabled = !S.future.length;
  $('undo').title = S.history.length ? `Undo ${S.history.at(-1).label} (⌘Z)` : 'Undo (⌘Z)';
  $('redo').title = S.future.length ? `Redo ${S.future.at(-1).label} (⇧⌘Z)` : 'Redo (⇧⌘Z)';
}
async function undo() { if (S.pending) { cancelEdit(); return; } const h = S.history.pop(); if (!h) return; try { await h.undo(); S.future.push(h); toast(`Undid ${h.label}`); } catch (e) { toast(e.message, { error: true }); } syncUndo(); }
async function redo() { const h = S.future.pop(); if (!h) return; try { await h.redo(); S.history.push(h); toast(`Redid ${h.label}`); } catch (e) { toast(e.message, { error: true }); } syncUndo(); }
function snapshot() { return { design: clone(S.design), assets: { ...S.assets }, overrides: clone(S.overrides), choices: { ...S.choices }, selected: [...S.selected], custom: clone(S.custom) }; }
function restore(s) {
  S.design = clone(s.design); S.assets = { ...s.assets }; S.overrides = clone(s.overrides); S.choices = { ...s.choices };
  S.selected = new Set(s.selected); S.custom = clone(s.custom);
  if (S.sel && !S.selected.has(S.sel.key)) S.sel = null;
  refresh(); save();
}
function recordDesignChange(label, before) { const after = snapshot(); pushHistory({ label, undo: async () => restore(before), redo: async () => restore(after) }); }

/* ───────── projects ───────── */
async function saveNow() {
  if (!S.campaign) return;
  $('save-state').textContent = 'Saving…';
  try {
    await api('/project?campaign=' + S.campaign, 'PUT', {
      name: S.name, design: S.design, assets: S.assets,
      formats: activeFormats().map(f => ({ width: f.width, height: f.height, name: f.name })),
      state: { selected: [...S.selected], custom: S.custom, choices: S.choices, overrides: S.overrides },
    });
    $('save-state').textContent = 'Saved';
  } catch (e) { $('save-state').textContent = 'Not saved'; toast('Could not save: ' + e.message, { error: true }); }
}
const save = debounce(saveNow, 600);

/** Projects keep their design in the engine's graph format; older studio designs are converted once. */
async function toGraph(d) {
  if (d && Array.isArray(d.nodes)) return d;
  return (await api('/convert', 'POST', { design: d })).design;
}
const textNodes = d => (d?.nodes || []).filter(n => n.type === 'text');
function mainFont(d) { const t = textNodes(d)[0]; return (t && t.style && t.style.fontFamily) || 'Inter'; }
async function uniqueName(name) {
  try { const names = new Set((await api('/projects')).map(p => p.name)); name = name.replace(/ \d+$/, ''); let n = name, i = 2; while (names.has(n)) n = `${name} ${i++}`; return n; }
  catch { return name; }
}
async function newProject(design, { name = 'Untitled campaign', assets = {}, state = null, rules = [] } = {}) {
  S.campaign = 'c-' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
  S.name = await uniqueName(name); S.design = await toGraph(design); S.assets = assets;
  S.custom = state?.custom || []; S.selected = new Set(state?.selected || DEFAULT_SELECTED);
  S.choices = state?.choices || {}; S.overrides = state?.overrides || {}; S.history = []; S.future = []; S.results = {}; S.metrics = {}; S.sel = null;
  for (const r of rules) { try { await api('/rules', 'POST', { campaign: S.campaign, rule: { type: r.type, params: r.params, label: r.label || '', source: r.source || 'manual', evidence: r.evidence || {} } }); } catch { /* skip invalid */ } }
  await api('/project?campaign=' + S.campaign, 'PUT', { name: S.name, design: S.design, assets: S.assets, formats: [], state: { selected: [...S.selected], custom: S.custom, choices: S.choices, overrides: S.overrides } }).catch(() => {});
  enterEditor();
}
async function openProject(campaign) {
  try {
    const p = await api('/project?campaign=' + encodeURIComponent(campaign));
    S.campaign = campaign; S.name = p.name; S.design = await toGraph(p.design); S.assets = p.assets || {};
    const st = p.state || {};
    S.custom = st.custom || []; S.selected = new Set(st.selected || DEFAULT_SELECTED); S.choices = st.choices || {}; S.overrides = st.overrides || {};
    S.history = []; S.future = []; S.results = {}; S.metrics = {}; S.sel = null;
    enterEditor();
  } catch (e) { toast('Could not open campaign: ' + e.message, { error: true }); }
}
async function startTemplate(id = 'snow_cabins', extra = {}) {
  // "Try it on a sample" reopens the sample campaign it made before (if it still exists) instead of piling up copies
  const reuse = !extra.assets && !extra.state && store.get('chameleon.sample.' + id);
  if (reuse) { try { await api('/project?campaign=' + encodeURIComponent(reuse)); return openProject(reuse); } catch { /* deleted: make a new one */ } }
  try {
    const [d, list] = await Promise.all([api('/example?name=' + id), api('/templates')]);
    const t = list.find(x => x.id === id);
    await newProject(d, { name: t ? t.name : 'Untitled campaign', ...extra });
    if (!extra.assets && !extra.state) store.set('chameleon.sample.' + id, S.campaign);
  } catch (e) { toast('Could not load the template: ' + e.message, { error: true }); }
}

/* ───────── views ───────── */
function showHome() {
  S.view = 'home'; $('home').hidden = false; $('editor').hidden = true; document.title = 'Chameleon Studio';
  if (location.hash) history.pushState(null, '', location.pathname);
  App.closeTour?.(); App.renderHome?.();
}
function enterEditor() {
  S.view = 'editor'; $('home').hidden = true; $('editor').hidden = false;
  $('project-name').value = S.name; document.title = `${S.name} · Chameleon`;
  if (location.hash !== '#c=' + S.campaign) history.pushState(null, '', '#c=' + S.campaign);
  S.edit = null; S.pending = null; hideNoticed(); syncUndo();
  App.paintAssets?.();
  refresh(true).then(() => {
    App.zoomFit?.(false);
    if (!store.get('chameleon.tour.v3')) setTimeout(() => App.startTour?.(0), 450);
  });
}

/* ───────── server sync ───────── */
let refreshTimer = null;
function refresh(now) {
  clearTimeout(refreshTimer);
  return new Promise(resolve => { refreshTimer = setTimeout(async () => { await doRefresh(); resolve(); }, now ? 0 : 140); });
}
async function doRefresh() {
  const formats = activeFormats(), seq = ++S.seq;
  if (!formats.length) { S.results = {}; App.paint('all'); return; }
  busy(true);
  try {
    const r = await api('/adapt', 'POST', { design: GV.resolved(S.design, S.assets), targets: formats.map(f => ({ width: f.width, height: f.height, name: f.key })) });
    if (seq !== S.seq) return;
    S.results = {}; r.results.forEach(x => { S.results[x.name] = asResult(x); });
    const firstRoles = !Object.keys(S.roleMap).length;
    S.roleMap = r.roles || {}; S.rules = []; S.roles = [...new Set(Object.values(S.roleMap))];
    if (firstRoles) App.paintAssets?.();
    App.paint('all');
  } catch (e) { toast(e.message, { error: true }); }
  finally { if (seq === S.seq) busy(false); }
}
/** One engine result as the Studio's layout options: the engine's choice first, then the layouts it also tried. */
function asResult(x) {
  const opt = (label, r) => ({ strategy: label, design: r.design, reasons: r.reasons || [], checks: r.checks || {}, score: r.score || {} });
  const first = opt(x.layout_label || 'Chameleon layout', x);
  return { candidates: [first, ...(x.alternatives || []).map(a => opt(a.label, a))], baseline: x.baselines, tier: x.tier, tier_name: x.tier_name };
}
function chosen(key) {
  const res = S.results[key]; if (!res) return null;
  return res.candidates.find(c => c.strategy === S.choices[key]) || res.candidates[0];
}
/** What a frame shows: the chosen layout's graph (base) plus the editable items with this frame's tweaks. */
function displayOf(c, key) {
  const g = GV.withSrc(clone(c.design), S.design, S.assets);
  const base = GV.items(g, S.roleMap), els = clone(base);
  const ov = (key && S.overrides[key]) || {};
  for (const e of els) if (ov[e.id]) Object.assign(e, ov[e.id]);
  return { canvas: { width: g.page.width, height: g.page.height }, elements: els, base: g, baseItems: base };
}
function display(key) { const c = chosen(key); return c ? displayOf(c, key) : null; }

/** Issues for a frame. Text size is checked against what was actually drawn (S.metrics), not the server estimate. */
function issuesOf(key, cand) {
  const c = cand || chosen(key); if (!c) return [];
  const d = cand ? displayOf(c) : display(key), byId = Object.fromEntries((d?.elements || []).map(e => [e.id, e]));
  const out = [], seen = new Set();
  const add = (type, text, id) => { const k = type + text; if (!seen.has(k)) { seen.add(k); out.push({ type, text, id }); } };
  // the engine's checks name graph nodes: map a button's shape or label to the button the designer sees
  const owner = {};
  for (const n of c.design.nodes) if (n.type === 'group') for (const k of n.children || []) owner[k] = n.id;
  const name = id => elName(byId[owner[id] || id]) || 'An element';
  const ch = c.checks || {};
  for (const [a, b] of ch.overlaps || []) add('OVERLAP', `${name(a)} overlaps ${name(b)}`, owner[a] || a);
  for (const id of ch.off_canvas || []) add('OUT_OF_BOUNDS', `${name(id)} is outside the frame`, owner[id] || id);
  for (const id of ch.small_text || []) add('TEXT_TOO_SMALL', `${name(id)} is under 12px`, owner[id] || id);
  for (const id of ch.low_contrast || []) add('LOW_CONTRAST', `${name(id)} is hard to read on its background`, owner[id] || id);
  if (!cand) {   // a frame-only tweak can push something off the frame, or onto another element
    const W = d.canvas.width, H = d.canvas.height, ov = S.overrides[key] || {};
    for (const e of d.elements) if (!e.hidden && e.type !== 'decoration' && (e.x < -1 || e.y < -1 || e.x + e.width > W + 1 || e.y + e.height > H + 1)) add('OUT_OF_BOUNDS', `${elName(e)} is outside the frame`, e.id);
    const solid = d.elements.filter(e => !e.hidden && e.width > 0 && ['text', 'button', 'logo'].includes(e.type));
    for (const e of solid) {
      if (!ov[e.id]) continue;               // only what the designer moved; the engine's own result is checked above
      for (const f of solid) {
        if (f === e) continue;
        const ix = Math.min(e.x + e.width, f.x + f.width) - Math.max(e.x, f.x), iy = Math.min(e.y + e.height, f.y + f.height) - Math.max(e.y, f.y);
        if (ix > 2 && iy > 2 && ix * iy > Math.min(e.width * e.height, f.width * f.height) * .08) add('OVERLAP', `${elName(e)} overlaps ${elName(f)}`, e.id);
      }
    }
  }
  return out;
}
function ruleResult(key, ruleId) { return (chosen(key)?.rule_results || []).find(x => x.id === ruleId); }
function ruleCoverage(rule) {
  let met = 0, applies = 0;
  for (const f of activeFormats()) { const rr = ruleResult(f.key, rule.id); if (rr && rr.applies) { applies++; if (rr.satisfied) met++; } }
  return { met, applies, n: activeFormats().length };
}
function hasTweaks(key) { return Object.keys(S.overrides[key] || {}).length > 0; }

/* ───────── rules ───────── */
function sameKey(a, b) {
  if (a.type !== b.type) return false;
  if (a.type === 'order') return [a.params.source_role, a.params.target_role].sort().join() === [b.params.source_role, b.params.target_role].sort().join();
  return a.params.role === b.params.role;
}
const ruleBody = r => ({ campaign: S.campaign, rule: { type: r.type, params: r.params, label: r.label || '', source: r.source || 'manual', evidence: r.evidence || {} } });
function trackRuleAdd(rule, replaced) {
  let id = rule.id;
  pushHistory({
    label: `rule “${rule.label}”`,
    undo: async () => { await api(`/rules/${id}?campaign=${S.campaign}`, 'DELETE'); if (replaced) await api('/rules', 'POST', ruleBody(replaced)); await refresh(true); },
    redo: async () => { id = (await api('/rules', 'POST', ruleBody(rule))).id; await refresh(true); },
  });
}
/** Save a rule (manual/bubble/inspector/text). Clears a conflicting manual tweak so the rule is visible. */
async function addRule(type, params, { source = 'manual', evidence = {}, label = '', clearTweak } = {}) {
  const replaced = S.rules.find(r => sameKey(r, { type, params }));
  const rule = await api('/rules', 'POST', { campaign: S.campaign, rule: { type, params, label, source, evidence } });
  if (clearTweak && S.overrides[clearTweak.key]) delete S.overrides[clearTweak.key][clearTweak.id];
  trackRuleAdd(rule, replaced);
  App.newRuleId = rule.id;
  await refresh(true);
  announceRule(rule); save();
  return rule;
}
function announceRule(rule) {
  const strip = activeFormats().map(f => {
    const rr = ruleResult(f.key, rule.id);
    return `${f.width}×${f.height} ${!rr ? '–' : !rr.applies ? 'n/a' : rr.satisfied ? '✓' : '!'}`;
  });
  toast(`Rule saved: ${rule.label}`, { strip, action: 'Undo', onAction: undo, ms: 6000 });
  App.flashFrames?.();
}
async function toggleRule(r) {
  const flip = async v => { await api(`/rules/${r.id}?campaign=${S.campaign}`, 'PATCH', { enabled: v }); await refresh(true); };
  try { await flip(!r.enabled); pushHistory({ label: `${r.enabled ? 'turn off' : 'turn on'} rule`, undo: () => flip(r.enabled), redo: () => flip(!r.enabled) }); }
  catch (e) { toast(e.message, { error: true }); }
}
async function deleteRule(r) {
  let id = r.id;
  try {
    await api(`/rules/${id}?campaign=${S.campaign}`, 'DELETE'); await refresh(true);
    pushHistory({ label: 'delete rule', undo: async () => { id = (await api('/rules', 'POST', ruleBody(r))).id; await refresh(true); }, redo: async () => { await api(`/rules/${id}?campaign=${S.campaign}`, 'DELETE'); await refresh(true); } });
    toast(`Deleted: ${r.label}`, { action: 'Undo', onAction: undo });
  } catch (e) { toast(e.message, { error: true }); }
}
function currentWeight(role) { const r = S.rules.find(x => x.type === 'emphasis' && x.params.role === role && x.enabled); return r ? r.params.weight : 1; }
function ruleFor(type, role) { return S.rules.find(x => x.type === type && x.enabled && (x.params.role === role)); }
function rulesForRole(role) { return S.rules.filter(r => r.enabled && (r.params.role === role || r.params.source_role === role || r.params.target_role === role || r.params.role === '*')); }

/* ───────── overrides (this frame only) ───────── */
function setOverride(key, id, patch, label = 'frame tweak') {
  const before = snapshot();
  S.overrides[key] = S.overrides[key] || {};
  S.overrides[key][id] = Object.assign({}, S.overrides[key][id] || {}, patch);
  recordDesignChange(label, before); App.paint('all'); save();
}
function clearOverrides(key) { const before = snapshot(); delete S.overrides[key]; recordDesignChange('reset tweaks', before); App.paint('all'); save(); }

/* ───────── direct-manipulation edit flow ───────── */
function beginEdit(kind, key, id) { const base = display(key); S.edit = { kind, key, id, before: clone(base), after: clone(base) }; }
function cancelEdit(repaint = true) { S.edit = null; S.pending = null; hideNoticed(); if (repaint) App.paint('canvas'); }
/** A drag or nudge on the canvas is a tweak to that frame only (the other sizes keep their own layout). */
async function inferEdit() { if (S.edit) keepNoticedForFrame(); }
function describe(p) {
  const n = activeFormats().length;
  if (p.type === 'hide_small') {
    const hit = activeFormats().filter(f => Math.min(f.width, f.height) < p.params.below).length;
    return `Hides it in ${hit} of ${n} frames (this size and smaller)`;
  }
  return `Applies to all ${n} frames and future ones`;
}
function showNoticed(proposals, via) {
  S.pending = { proposals, via };
  const f = fmt(S.edit.key), t = S.edit.after.elements.find(x => x.id === S.edit.id);
  const has = proposals.length > 0;
  $('noticed-title').textContent = has ? 'Make this a rule?' : 'Keep this change?';
  $('noticed-desc').textContent = has ? `You changed the ${lowerRole(roleOf(t))} in ${f.name}.` : 'This change doesn’t match a reusable rule. Keep it for this frame only?';
  $('noticed-options').replaceChildren(...proposals.map((p, i) => el('label', { class: 'opt' },
    el('input', { type: 'radio', name: 'proposal', value: i, checked: i === 0 }),
    el('span', {}, el('b', { text: p.label }), el('small', { text: describe(p) })))));
  $('noticed-all').hidden = !has;
  $('noticed').hidden = false;
  App.positionNoticed?.();
  (has ? $('noticed-all') : $('noticed-one')).focus({ preventScroll: true });
}
function hideNoticed() { $('noticed').hidden = true; }
async function saveNoticedRule() {
  const P = S.pending, E = S.edit; if (!P || !E || !P.proposals.length) return;
  const p = P.proposals[+(document.querySelector('input[name=proposal]:checked')?.value || 0)];
  busy(true);
  try {
    const replaced = S.rules.find(r => sameKey(r, p));
    const rule = (await api('/learn', 'POST', { before: E.before, after: E.after, moved_id: E.id, kind: E.kind, campaign: S.campaign, rule_type: p.type, params: p.params })).learned;
    if (S.overrides[E.key]) delete S.overrides[E.key][E.id];
    cancelEdit(false);
    trackRuleAdd(rule, replaced); App.newRuleId = rule.id;
    await refresh(true); announceRule(rule); save();
  } catch (err) { toast(err.message, { error: true }); }
  finally { busy(false); }
}
function keepNoticedForFrame() {
  const E = S.edit; if (!E) return;
  const t = E.after.elements.find(x => x.id === E.id);
  const patch = { x: t.x, y: t.y, width: t.width, height: t.height, hidden: !!t.hidden };
  if (t.align) patch.align = t.align;
  if (t.fontSize) patch.fontSize = t.fontSize;
  cancelEdit(false);
  setOverride(E.key, E.id, patch, E.kind === 'resize' ? 'resize' : 'move');
  toast(`Changed in ${fmt(E.key).name} only. The other sizes keep their own layout.`, { action: 'Undo', onAction: undo });
}
$('noticed-all').onclick = saveNoticedRule;
$('noticed-one').onclick = keepNoticedForFrame;
$('noticed-undo').onclick = () => cancelEdit();
$('noticed').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.target.closest('button')) { e.preventDefault(); if (S.pending?.proposals.length) saveNoticedRule(); else keepNoticedForFrame(); }
  if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); cancelEdit(); }
});

/* ───────── element actions (inspector, bubbles, keyboard) ───────── */
const CORNERS = ['top-left', 'top-right', 'bottom-left', 'bottom-right'];
/** Apply an action to element `id` in frame `key`. scope 'all' → rule; 'frame' → tweak for this frame only. */
async function applyAction(key, id, action, value, scope = S.scope) {
  const d = display(key), t = d && d.elements.find(e => e.id === id); if (!t) return;
  const role = roleOf(t), short = Math.min(d.canvas.width, d.canvas.height);
  if (scope === 'all') {
    try {
      const ev = { canvas: d.canvas, element: id, via: action };
      if (action === 'align') return await addRule('align', { role, align: value }, { source: 'edit', evidence: ev, clearTweak: { key, id } });
      if (action === 'pin') {
        if (value === 'none') { const r = ruleFor('pin', role); if (r) return await deleteRule(r); return toast('Not pinned'); }
        return await addRule('pin', { role, corner: value }, { source: 'edit', evidence: ev, clearTweak: { key, id } });
      }
      if (action === 'size') {
        const w = Math.round(Math.min(2, Math.max(.5, value)) * 100) / 100;
        if (Math.abs(w - 1) < .01) { const r = ruleFor('emphasis', role); if (r) return await deleteRule(r); return; }
        return await addRule('emphasis', { role, weight: w }, { source: 'edit', evidence: ev, clearTweak: { key, id } });
      }
      if (action === 'hide') {
        if (value === false) { const r = ruleFor('hide_small', role); if (r) return await deleteRule(r); return; }
        return await addRule('hide_small', { role, below: short + 1 }, { source: 'edit', evidence: ev, clearTweak: { key, id } });
      }
    } catch (e) { toast(e.message, { error: true }); }
    return;
  }
  // this frame only
  const W = d.canvas.width, H = d.canvas.height, m = short * .06;
  if (action === 'align') {
    const patch = { align: value };
    if (t.type !== 'text') { const col = columnOf(d); patch.x = value === 'left' ? col.x : value === 'right' ? col.x + col.w - t.width : col.x + (col.w - t.width) / 2; }
    return setOverride(key, id, patch, `align ${value} (this frame)`);
  }
  if (action === 'pin') {
    if (value === 'none') { const ov = { ...(S.overrides[key] || {})[id] }; delete ov.x; delete ov.y; return setOverride(key, id, ov, 'unpin (this frame)'); }
    const [v, h] = value.split('-');
    return setOverride(key, id, { x: h === 'left' ? m : W - m - t.width, y: v === 'top' ? m : H - m - t.height, align: h }, `pin ${value} (this frame)`);
  }
  if (action === 'size') {
    const k = value; const nw = Math.min(W - t.x, t.width * k), nh = Math.min(H - t.y, t.height * k);
    const patch = { width: nw, height: nh }; if (t.fontSize) patch.fontSize = t.fontSize * Math.min(nw / t.width, nh / t.height);
    return setOverride(key, id, patch, 'resize (this frame)');
  }
  if (action === 'hide') return setOverride(key, id, value === false ? { hidden: false } : { hidden: true }, value === false ? 'show (this frame)' : 'hide (this frame)');
}
function columnOf(d) {
  const texts = d.elements.filter(e => e.type === 'text' && !e.hidden && e.width > 0);
  if (!texts.length) return { x: d.canvas.width * .06, w: d.canvas.width * .88 };
  const x = Math.min(...texts.map(e => e.x)); return { x, w: Math.max(...texts.map(e => e.x + e.width)) - x };
}

/* ───────── assets ───────── */
function readImage(file, kind) {
  return new Promise((resolve, reject) => {
    if (!file.type.startsWith('image/')) return reject(Error(`“${file.name}” isn’t an image.`));
    if (file.size > 25e6) return reject(Error('Choose an image under 25 MB.'));
    const fr = new FileReader();
    fr.onerror = () => reject(Error('Could not read that file.'));
    fr.onload = () => {
      const img = new Image();
      img.onerror = () => reject(Error('That image could not be opened. Try a JPG or PNG.'));
      img.onload = () => {
        const max = kind === 'hero' ? 1600 : 900, s = Math.min(1, max / Math.max(img.width || 300, img.height || 100));
        const c = document.createElement('canvas'); c.width = Math.max(1, Math.round((img.width || 300) * s)); c.height = Math.max(1, Math.round((img.height || 100) * s));
        const x = c.getContext('2d'); x.drawImage(img, 0, 0, c.width, c.height);
        // transparency check: sample the border for alpha
        let transparent = 0, total = 0;
        try {
          const data = x.getImageData(0, 0, c.width, c.height).data, step = Math.max(1, Math.floor(Math.min(c.width, c.height) / 40));
          for (let px = 0; px < c.width; px += step) for (const py of [0, c.height - 1]) { total++; if (data[(py * c.width + px) * 4 + 3] < 200) transparent++; }
          for (let py = 0; py < c.height; py += step) for (const px of [0, c.width - 1]) { total++; if (data[(py * c.width + px) * 4 + 3] < 200) transparent++; }
        } catch { /* tainted canvas cannot happen for local files */ }
        const alpha = total ? transparent / total : 0;
        const keepAlpha = kind === 'logo' || alpha > .02 || file.type === 'image/png' || file.type === 'image/svg+xml';
        resolve({ url: c.toDataURL(keepAlpha ? 'image/png' : 'image/jpeg', .88), w: c.width, h: c.height, alpha, name: file.name });
      };
      img.src = fr.result;
    };
    fr.readAsDataURL(file);
  });
}
/** Image Playground-style auto sort: transparent edges, SVGs or very wide images are logos; everything else is a product photo. */
function classify(info, file) {
  const aspect = info.w / info.h;
  if (file.type === 'image/svg+xml' || info.alpha > .25 || aspect > 2.4) return 'logo';
  if (/logo|brand|mark/i.test(file.name)) return 'logo';
  return 'hero';
}
/** The design's main photo (the biggest picture that isn't the logo) and its logo node. */
function photoNode(d = S.design) {
  const imgs = d.nodes.filter(n => n.type === 'image' && (S.roleMap[n.id] || n.role) !== 'logo');
  return imgs.sort((a, b) => b.box[2] * b.box[3] - a.box[2] * a.box[3])[0] || null;
}
function logoNode(d = S.design) { return d.nodes.find(n => (S.roleMap[n.id] || n.role) === 'logo') || null; }
async function useImage(info, kind, { quiet } = {}) {
  const before = snapshot();
  const id = kind + '-' + Date.now().toString(36) + Math.random().toString(36).slice(2, 5);
  let target = kind === 'hero' ? photoNode() : logoNode();
  if (!target) {
    const W = S.design.page.width, H = S.design.page.height;
    target = kind === 'hero' ? { id: 'photo', type: 'image', role: 'hero', box: [0, 0, W, H * .5], z: 0 }
                             : { id: 'logo', type: 'image', role: 'logo', box: [W * .06, W * .06, W * .2, W * .08], z: 99 };
    S.design.nodes.push(target);
  }
  if (target.src && target.src.startsWith('asset:')) delete S.assets[target.src.slice(6)];
  S.assets[id] = info.url;
  if (kind === 'logo') {
    // a text logo becomes the uploaded picture, as tall as the text was, in the picture's own shape
    const [x, y, , h] = target.box, hh = Math.max(h, 24);
    if (target.type === 'text') { target._text = { text: target.text, style: target.style }; delete target.text; delete target.style; target.type = 'image'; }
    target.role = 'logo'; target.box = [x, y, Math.round(hh * info.w / info.h), hh];
  } else {
    // a new photo: let the engine find its subject and frame it at every size
    delete target.crop; delete target.subject;
    target.meta = { ...(target.meta || {}), label: 'your photo' }; delete target.meta.focus; delete target.meta.art;
    S.choices = {};       // layouts picked for the old photo may not suit this one
  }
  target.src = 'asset:' + id;
  recordDesignChange(kind === 'hero' ? 'photo' : 'logo', before);
  App.paintAssets?.(); refresh(); save();
  if (!quiet) toast(kind === 'hero' ? 'Photo applied to every size' : 'Logo applied to every size',
    { action: kind === 'hero' ? 'Use as logo' : 'Use as photo', onAction: async () => { await undo(); useImage(info, kind === 'hero' ? 'logo' : 'hero'); } });
}
async function useUpload(file, kind) {
  try { const info = await readImage(file, kind); await useImage(info, kind || classify(info, file)); }
  catch (e) { toast(e.message, { error: true }); }
}
async function removeAsset(kind) {
  const before = snapshot();
  const t = kind === 'hero' ? photoNode() : logoNode();
  if (!t || !t.src || !t.src.startsWith('asset:')) return;
  delete S.assets[t.src.slice(6)]; delete t.src;
  if (kind === 'logo' && t._text) { t.type = 'text'; t.text = t._text.text; t.style = t._text.style; delete t._text; }
  recordDesignChange(kind === 'hero' ? 'remove image' : 'remove logo', before); App.paintAssets?.(); refresh(); save();
}

/* ───────── export ───────── */
async function preload() {
  await Promise.all(Object.values(S.assets).map(src => new Promise(res => { const i = new Image(); i.onload = i.onerror = () => res(); i.src = src; })));
  try { await document.fonts.load(`800 40px "${mainFont(S.design)}"`); } catch { /* fallback font */ }
  const c = document.createElement('canvas');
  for (const f of activeFormats()) { const d = display(f.key); if (d) GV.draw(c, d, { scale: .05, dpr: 1, css: false }); }
  await new Promise(r => setTimeout(r, 60));
}
function renderBlob(key) {
  const d = display(key), c = document.createElement('canvas');
  GV.draw(c, d, { scale: 1, dpr: 1, css: false });
  return new Promise(res => c.toBlob(res, 'image/png'));
}
function download(blob, name) { const u = URL.createObjectURL(blob), a = el('a', { href: u, download: name }); document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(u), 2000); }
async function exportZip() {
  const formats = activeFormats(); if (!formats.length) return toast('Add at least one frame first.', { error: true });
  busy(true);
  try {
    await preload();
    const files = [];
    for (const f of formats) files.push({ name: `${slug(S.name)}_${slug(f.name)}_${f.width}x${f.height}.png`, data: new Uint8Array(await (await renderBlob(f.key)).arrayBuffer()) });
    const manifest = { campaign: S.name, exported: new Date().toISOString(),
      formats: formats.map(f => ({ name: f.name, width: f.width, height: f.height, layout: chosen(f.key)?.strategy, warnings: issuesOf(f.key).map(i => i.text), frameTweaks: Object.keys(S.overrides[f.key] || {}).length })) };
    files.push({ name: 'manifest.json', data: new TextEncoder().encode(JSON.stringify(manifest, null, 2)) });
    download(window.ChameleonZip.makeZip(files), `${slug(S.name)}-${formats.length}-formats.zip`);
    toast(`Exported ${formats.length} PNGs in one ZIP. Check your Downloads folder.`);
  } catch (e) { toast('Export failed: ' + e.message, { error: true }); }
  finally { busy(false); }
}
async function exportPng(key) {
  key = key || S.sel?.key || activeFormats()[0]?.key; if (!key) return;
  await preload(); const f = fmt(key);
  download(await renderBlob(key), `${slug(S.name)}_${slug(f.name)}_${f.width}x${f.height}.png`);
  toast(`Exported ${f.name} as PNG`);
}
function exportJson() {
  const data = { chameleon: 'project', version: 4, name: S.name, design: S.design, assets: S.assets,
    state: { selected: [...S.selected], custom: S.custom, choices: S.choices, overrides: S.overrides } };
  download(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }), `${slug(S.name)}.chameleon.json`);
  toast('Project file downloaded');
}
async function importJsonFile(f) {
  try {
    if (f.size > 25e6) throw Error('Choose a file under 25 MB.');
    const data = JSON.parse(await f.text());
    if (data.chameleon === 'project') await newProject(data.design, { name: data.name, assets: data.assets || {}, state: data.state });
    else if (Array.isArray(data.nodes) || (data.canvas && Array.isArray(data.elements))) {
      await newProject(await toGraph(data), { name: data.name || f.name.replace(/\.json$/i, '') });
    } else throw Error('This isn’t a Chameleon design or project file.');
  } catch (err) { toast('Could not open: ' + err.message, { error: true, ms: 7000 }); }
}

/* ───────── theme ───────── */
function setTheme(t) { document.documentElement.dataset.theme = t; store.set('chameleon.theme', t); App.paint('theme'); }
document.querySelectorAll('.theme-toggle').forEach(b => b.addEventListener('click', () => setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark')));
matchMedia('(prefers-color-scheme: light)').addEventListener?.('change', e => { if (!store.get('chameleon.theme')) document.documentElement.dataset.theme = e.matches ? 'light' : 'dark'; });

/* ───────── menus ───────── */
const MENUS = [];
function registerMenu(btn, menu, build) {
  MENUS.push([btn, menu]);
  $(btn).addEventListener('click', async e => {
    e.stopPropagation();
    const open = $(menu).hidden; closeMenus();
    if (!open) return;
    if (build) await build();
    $(menu).hidden = false; $(btn).setAttribute('aria-expanded', 'true');
    $(menu).querySelector('button')?.focus();
  });
  $(menu).addEventListener('keydown', e => {
    const items = [...$(menu).querySelectorAll('button:not([disabled])')], i = items.indexOf(document.activeElement);
    if (e.key === 'ArrowDown') { e.preventDefault(); items[(i + 1) % items.length]?.focus(); }
    if (e.key === 'ArrowUp') { e.preventDefault(); items[(i - 1 + items.length) % items.length]?.focus(); }
    if (e.key === 'Escape') { e.stopPropagation(); closeMenus(); $(btn).focus(); }
  });
}
function closeMenus() { for (const [b, m] of MENUS) { $(m).hidden = true; $(b).setAttribute('aria-expanded', 'false'); } }
document.addEventListener('pointerdown', e => { if (!e.target.closest('.menu') && !MENUS.some(([b]) => e.target.closest('#' + b))) closeMenus(); });
const mi = (icon, label, onclick, kbd) => el('button', { role: 'menuitem', onclick: () => { closeMenus(); onclick(); } }, icon ? ic(icon) : null, el('span', { text: label }), kbd ? el('kbd', { text: kbd }) : null);
registerMenu('main-menu-btn', 'main-menu', async () => {
  let tpls = []; try { tpls = await api('/templates'); } catch { /* offline */ }
  $('main-menu').replaceChildren(
    mi('home', 'Back to home', showHome),
    el('div', { class: 'menu-sep' }), el('div', { class: 'menu-label', text: 'New campaign' }),
    ...tpls.map(t => mi('plus', t.name, () => startTemplate(t.id))),
    mi('file', 'Import JSON…', () => $('home-json').click()),
    el('div', { class: 'menu-sep' }),
    mi('download', 'Export all frames', exportZip, '⌘E'), mi('file', 'Download project file', exportJson),
    el('div', { class: 'menu-sep' }),
    mi(document.documentElement.dataset.theme === 'dark' ? 'sun' : 'moon', document.documentElement.dataset.theme === 'dark' ? 'Light theme' : 'Dark theme', () => setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark')),
    mi('play', 'Product tour', () => App.startTour?.(0)),
    mi('keyboard', 'Keyboard shortcuts', () => $('shortcuts').showModal(), '?'),
    mi('target', 'How it works', () => $('think-btn').click()),
    el('div', { class: 'menu-sep' }),
    mi('trash', 'Delete this campaign…', async () => { if (!confirm(`Delete “${S.name}”? This can’t be undone.`)) return; await api('/project?campaign=' + S.campaign, 'DELETE'); showHome(); }),
  );
});
registerMenu('export-menu-btn', 'export-menu');
$('export-menu').addEventListener('click', e => { const b = e.target.closest('[data-export]'); if (!b) return; closeMenus(); ({ zip: exportZip, png: () => exportPng(), json: exportJson })[b.dataset.export](); });
$('export-all').onclick = exportZip;
$('undo').onclick = undo; $('redo').onclick = redo;
/** "How it works": the engine explained step by step on this campaign's design (with a way back here). */
$('think-btn').onclick = async () => {
  try {
    localStorage.setItem('chameleon.xray.design', JSON.stringify({ ...GV.resolved(S.design, S.assets), name: S.name }));
    localStorage.setItem('chameleon.how.back', '/#c=' + S.campaign);
  } catch { return toast('This design is too big to hand over. Use Export → project file instead.', { error: true }); }
  save.cancel(); await saveNow(); location.href = '/how#from=studio';
};
$('sc-close').onclick = () => $('shortcuts').close();
$('bench-close').onclick = () => $('bench').close();
$('project-name').addEventListener('change', e => { S.name = e.target.value.trim() || 'Untitled campaign'; e.target.value = S.name; document.title = `${S.name} · Chameleon`; save(); });
$('project-name').addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === 'Escape') e.target.blur(); });
async function runBench() {
  $('bench').showModal(); const out = $('bench-out'); out.textContent = 'Running 96 held-out cases…';
  try {
    const b = await api('/benchmark');
    const rows = Object.entries(b.totals).map(([k, m]) => el('tr', {}, el('td', { text: k.replaceAll('_', ' ') }), el('td', { text: `${m.relationships_preserved}/${m.relationships_total}` }), el('td', { text: m.small_text }), el('td', { text: m.overlaps })));
    out.replaceChildren(el('table', {}, el('thead', {}, el('tr', {}, ...['Method', 'Taught rule kept', 'Text <12px', 'Overlaps'].map(h => el('th', { text: h })))), el('tbody', {}, rows)),
      el('p', { text: `${b.cases} synthetic cases (${b.designs} variants × ${b.formats} formats). A regression check of rule transfer, not a study of design quality.` }));
  } catch (e) { out.textContent = e.message; }
}

window.addEventListener('popstate', () => {
  const m = location.hash.match(/c=([\w-]+)/);
  if (m && m[1] !== S.campaign) openProject(m[1]);
  else if (!m && S.view === 'editor') { S.view = 'home'; $('home').hidden = false; $('editor').hidden = true; document.title = 'Chameleon Studio'; App.closeTour?.(); App.renderHome?.(); }
});
