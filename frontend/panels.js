/* Chameleon Studio v3 — panels: layers & assets (left), design & rules inspector (right), add-frame popover. */
'use strict';
(function () {
  const expanded = new Set();

  /* ── tabs ── */
  function tabs(ids, onChange) {
    ids.forEach((t, i) => {
      $('tab-' + t).addEventListener('click', () => setTab(t));
      $('tab-' + t).addEventListener('keydown', e => {
        if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
        const n = ids[(i + (e.key === 'ArrowRight' ? 1 : ids.length - 1)) % ids.length]; setTab(n); $('tab-' + n).focus();
      });
    });
    function setTab(name) {
      for (const t of ids) { const on = t === name; $('tab-' + t).setAttribute('aria-selected', on); $('tab-' + t).tabIndex = on ? 0 : -1; $('pane-' + t).hidden = !on; }
      onChange?.(name);
    }
    return setTab;
  }
  const setLeftTab = tabs(['layers', 'assets']);
  const setRightTab = tabs(['design', 'rules']);
  App.setLeftTab = setLeftTab; App.setRightTab = setRightTab;

  /* ═════════ LAYERS ═════════ */
  function paintLayers() {
    const tree = $('layers'), items = [];
    for (const f of activeFormats()) {
      const issues = issuesOf(f.key), open = expanded.has(f.key) || (S.sel && S.sel.key === f.key);
      const selFrame = S.sel && S.sel.key === f.key && !S.sel.id;
      const row = el('div', { class: 'row' + (selFrame ? ' sel' : ''), role: 'treeitem', 'aria-expanded': open, 'aria-selected': selFrame, tabindex: '0', 'data-key': f.key, 'aria-label': `${f.name}, ${f.width} by ${f.height}${issues.length ? `, ${issues.length} warnings` : ''}` },
        el('button', { class: 'twisty', tabindex: '-1', 'aria-label': open ? 'Collapse' : 'Expand', onclick: ev => { ev.stopPropagation(); toggle(f.key); } }, ic('chevronRight')),
        ic('frame', 'i row-icon'),
        el('span', { class: 'row-name', text: f.name }),
        el('span', { class: 'status-dot' + (issues.length ? ' warn' : ''), title: issues.length ? issues.map(i => i.text).join('\n') : 'All checks pass' }),
        el('span', { class: 'row-meta', text: `${f.width}×${f.height}` }),
        el('button', { class: 'icon-btn sm row-act', tabindex: '-1', 'aria-label': `Remove ${f.name}`, title: 'Remove frame', onclick: ev => { ev.stopPropagation(); removeFrame(f.key); } }, ic('trash')));
      row.addEventListener('click', () => { if (S.pending) return App.flagPending(); App.select({ key: f.key, id: null }); App.focusFrame(f.key); });
      row.addEventListener('keydown', e => treeKeys(e, f.key, null));
      const li = el('li', { role: 'none' }, row);
      if (open) {
        const d = App.curDesign?.(f.key) || display(f.key);
        const kids = (d?.elements || []).filter(e => e.type !== 'decoration').map(e => {
          const isSel = S.sel && S.sel.key === f.key && S.sel.id === e.id, hidden = e.hidden || e.width <= 0;
          const r = el('div', { class: 'row child' + (isSel ? ' sel' : '') + (hidden ? ' is-hidden' : ''), role: 'treeitem', 'aria-selected': isSel, tabindex: '0', 'data-key': f.key, 'data-id': e.id },
            ic(e.type === 'image' ? 'image' : ROLE_ICON[roleOf(e)] || 'type', 'i row-icon'),
            el('span', { class: 'row-name', text: elName(e), title: elName(e) }),
            el('button', { class: 'icon-btn sm row-act' + (hidden ? ' on' : ''), tabindex: '-1', 'aria-label': hidden ? `Show ${elName(e)} in ${f.name}` : `Hide ${elName(e)} in ${f.name}`, title: hidden ? 'Show in this frame' : 'Hide in this frame',
              onclick: ev => { ev.stopPropagation(); applyAction(f.key, e.id, 'hide', !hidden, 'frame'); } }, ic(hidden ? 'eyeOff' : 'eye')));
          r.addEventListener('click', () => { if (S.pending) return App.flagPending(); if (hidden) { App.select({ key: f.key, id: e.id }); return; } App.select({ key: f.key, id: e.id }); });
          r.addEventListener('keydown', ev => treeKeys(ev, f.key, e.id));
          return el('li', { role: 'none' }, r);
        });
        li.append(el('ul', { role: 'group' }, kids));
      }
      items.push(li);
    }
    tree.replaceChildren(...items);
  }
  function toggle(key) { expanded.has(key) ? expanded.delete(key) : expanded.add(key); paintLayers(); }
  function treeKeys(e, key, id) {
    const rows = [...$('layers').querySelectorAll('.row')], i = rows.indexOf(e.currentTarget);
    if (e.key === 'ArrowDown') { e.preventDefault(); rows[i + 1]?.focus(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); rows[i - 1]?.focus(); }
    else if (e.key === 'ArrowRight' && !id) { e.preventDefault(); expanded.add(key); paintLayers(); $('layers').querySelector(`.row[data-key="${key}"]:not(.child)`)?.focus(); }
    else if (e.key === 'ArrowLeft' && !id) { e.preventDefault(); expanded.delete(key); paintLayers(); $('layers').querySelector(`.row[data-key="${key}"]:not(.child)`)?.focus(); }
    else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.currentTarget.click(); }
  }

  /* ═════════ ASSETS ═════════ */
  const SWATCHES = [['background', 'Background'], ['text', 'Text'], ['primary', 'Button'], ['accent', 'Image backdrop']];
  App.paintAssets = function () {
    if (!S.design) return;
    $('swatches').closest('.group').hidden = true;      // colours come from the design itself
    const fam = mainFont(S.design), sel = $('brand-font');
    if (![...sel.options].some(o => o.value === fam)) sel.append(el('option', { value: fam, text: fam }));
    sel.value = fam;
    $('copy-fields').replaceChildren(...textNodes(S.design).filter(n => (n.text || '').trim()).map(n => copyField(n)));
    for (const kind of ['hero', 'logo']) {
      const t = kind === 'hero' ? photoNode() : logoNode();
      const src = t && t.src ? GV.resolve(t.src, S.assets) : null;
      $('thumb-' + kind).style.backgroundImage = src ? `url("${src}")` : '';
      $('thumb-' + kind).classList.toggle('has', !!src);
      $('rm-' + kind).hidden = !src;
    }
  };
  /** A text node of the source design (n), or the label of a button group: its copy, shared by every size. */
  function textTarget(id) {
    const n = S.design.nodes.find(x => x.id === id); if (!n) return null;
    if (n.type === 'text') return n;
    if (n.type === 'group') return S.design.nodes.find(x => (n.children || []).includes(x.id) && x.type === 'text') || null;
    return null;
  }
  App.textTarget = textTarget;
  function copyField(n, compact) {
    let before = null;
    const owner = S.design.nodes.find(g => g.type === 'group' && (g.children || []).includes(n.id));
    const role = S.roleMap[n.id] || n.role || (owner && (S.roleMap[owner.id] || owner.role)) || 'body';
    const long = (n.text || '').length > 28;
    const input = el(long ? 'textarea' : 'input', { maxlength: 200, rows: long ? 2 : null, 'aria-label': `${niceRole(role)} copy`,
      onfocus: () => { before = snapshot(); },
      oninput: ev => { n.text = ev.target.value; refresh(); },
      onchange: () => { if (before) recordDesignChange(`${lowerRole(role)} copy`, before); before = null; save(); App.paintAssets(); } });
    input.value = n.text || '';
    return compact ? input : el('label', {}, `${niceRole(role)}${role === 'logo' ? ' (text logo)' : ''}`, input);
  }
  $('brand-font').addEventListener('change', async e => {
    const before = snapshot();
    for (const n of textNodes(S.design)) n.style = { ...(n.style || {}), fontFamily: e.target.value };
    try { await document.fonts.load(`800 40px "${e.target.value}"`); } catch { /* offline */ }
    recordDesignChange('typeface', before); refresh(); save();
  });
  for (const kind of ['hero', 'logo']) {
    $('up-' + kind).addEventListener('change', e => { if (e.target.files[0]) useUpload(e.target.files[0], kind); e.target.value = ''; });
    $('rm-' + kind).addEventListener('click', e => { e.preventDefault(); e.stopPropagation(); removeAsset(kind); });
    $('drop-' + kind).addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); $('up-' + kind).click(); } });
  }

  /* ═════════ INSPECTOR: DESIGN ═════════ */
  const group = (label, ...kids) => el('div', { class: 'group' }, label ? el('span', { class: 'label', text: label }) : null, ...kids);
  let lastSel = '';
  function paintDesign() {
    const pane = $('pane-design');
    if (!S.design) return;
    const selKey = S.sel ? S.sel.key + '/' + (S.sel.id || '') + '/' + S.scope : '';
    const a = document.activeElement;
    // don't rebuild under the user's cursor while they type in the inspector
    if (selKey === lastSel && pane.contains(a) && /INPUT|TEXTAREA|SELECT/.test(a.tagName)) return;
    lastSel = selKey;
    const sel = S.sel, d = sel ? (App.curDesign?.(sel.key) || display(sel.key)) : null;
    const put = arr => pane.replaceChildren(...arr.filter(Boolean));
    if (!sel || !d) return put(campaignView());
    if (!sel.id) return put(frameView(sel.key, d));
    const e = d.elements.find(x => x.id === sel.id);
    if (!e) { S.sel = { key: sel.key, id: null }; return put(frameView(sel.key, d)); }
    put(elementView(sel.key, d, e));
  }
  function campaignView() {
    const frames = activeFormats(), all = frames.flatMap(f => issuesOf(f.key).map(i => ({ ...i, key: f.key, f })));
    return [
      el('div', { class: 'insp-head' }, el('span', { class: 'role-chip' }, ic('grid')), el('div', {}, el('b', { text: S.name }), el('small', { text: 'Nothing selected · campaign overview' }))),
      group(null, el('div', { class: 'stat-grid' },
        el('div', { class: 'stat' }, el('b', { text: frames.length }), el('span', { text: 'Frames' })),
        el('div', { class: 'stat' }, el('b', { text: frames.reduce((n, f) => n + Object.keys(S.overrides[f.key] || {}).length, 0) }), el('span', { text: 'Your tweaks' })),
        el('div', { class: 'stat' }, el('b', { text: all.length }), el('span', { text: 'Warnings' })))),
      group('Needs attention', all.length
        ? el('ul', { class: 'issue-list' }, all.slice(0, 12).map(i => el('li', { class: 'issue' }, ic('alert'), el('span', { text: `${i.f.name}: ${i.text}` }),
          el('button', { class: 'btn ghost sm', text: 'Show', onclick: () => { App.select({ key: i.key, id: i.id || null }); App.focusFrame(i.key); } }))))
        : el('div', { class: 'issue ok' }, ic('check'), el('span', { text: 'Every frame passes the checks' }))),
      group('Get started', el('p', { class: 'hint', text: 'Click a size to see why it looks the way it does and the other layouts Chameleon tried. Drag anything to adjust that size only.' }),
        el('div', { style: 'display:flex;gap:6px;flex-wrap:wrap' },
          el('button', { class: 'btn sm', onclick: () => App.openAddFrame?.() }, ic('plus'), 'Add frame'),
          el('button', { class: 'btn sm', onclick: () => App.startTour?.(0) }, ic('play'), 'Take the tour'))),
    ];
  }
  function frameView(key, d) {
    const f = fmt(key), res = S.results[key], issues = issuesOf(key), tweaks = Object.keys(S.overrides[key] || {}).length;
    return [
      el('div', { class: 'insp-head' }, el('span', { class: 'role-chip' }, ic('frame')), el('div', {}, el('b', { text: f.name }), el('small', { text: `${f.width} × ${f.height} px · ${f.group}` }))),
      whyGroup(key),
      framingGroup(),
      group(res?.candidates?.length > 1 ? 'Layouts tried' : 'Layout', el('div', { class: 'layouts', role: 'radiogroup', 'aria-label': 'Layout options' }, (res?.candidates || []).map(c => {
        const on = c === chosen(key), cv = el('canvas', { 'aria-hidden': 'true' });
        GV.draw(cv, displayOf(c), { scale: Math.min(76 / f.width, 52 / f.height), dpr: DPR });
        const n = issuesOf(key, c).length;
        return el('button', { class: 'layout-opt', role: 'radio', 'aria-checked': on, 'aria-label': `${STRATEGY[c.strategy] || c.strategy}${n ? `, ${n} warnings` : ''}`, onclick: () => {
          if (on) return; const before = snapshot(); S.choices[key] = c.strategy; recordDesignChange('layout choice', before); App.paint('all'); save();
        } }, cv, el('span', { text: STRATEGY[c.strategy] || c.strategy }), n ? el('span', { class: 'warnmark', text: `${n} warning${n > 1 ? 's' : ''}` }) : el('span', { class: 'okmark', text: '✓ No issues' }));
      }))),
      group('Checks', issues.length
        ? el('ul', { class: 'issue-list' }, issues.map(i => el('li', { class: 'issue' }, ic('alert'), el('span', { text: i.text }), i.id ? el('button', { class: 'btn ghost sm', text: 'Select', onclick: () => App.select({ key, id: i.id }) }) : null)))
        : el('div', { class: 'issue ok' }, ic('check'), el('span', { text: 'No overlaps, nothing outside the frame, text 12px or larger, readable contrast' }))),
      tweaks ? group('Frame-only tweaks', el('div', { class: 'ctrl-row' }, el('span', { class: 'muted', text: `${tweaks} element${tweaks > 1 ? 's' : ''} changed only here` }), el('button', { class: 'btn sm', text: 'Reset', onclick: () => clearOverrides(key) }))) : null,
      group('Frame', el('div', { style: 'display:flex;gap:6px;flex-wrap:wrap' },
        el('button', { class: 'btn sm', onclick: () => exportPng(key) }, ic('download'), 'Export PNG'),
        el('button', { class: 'btn sm', onclick: () => App.focusFrame(key) }, ic('zoomIn'), 'Zoom to frame'),
        el('button', { class: 'btn sm danger', onclick: () => removeFrame(key) }, ic('trash'), 'Remove'))),
    ];
  }
  function elementView(key, d, e) {
    const f = fmt(key), role = roleOf(e), isImg = e.type === 'image';
    const alignNow = e.align || 'left';
    const pinVal = cornerOf(e, d);
    const cells = ['top-left', 'top-center', 'top-right', 'mid-left', 'none', 'mid-right', 'bottom-left', 'bottom-center', 'bottom-right'];
    const pinGrid = el('div', { class: 'pin-grid', role: 'group', 'aria-label': 'Pin to corner' }, cells.map(c => {
      const usable = CORNERS.includes(c) || c === 'none';
      return el('button', { class: c === 'none' ? 'center' : usable ? '' : 'na', tabindex: usable ? null : '-1', 'aria-hidden': usable ? null : 'true', disabled: !usable || null,
        'aria-pressed': usable ? pinVal === c : null, 'aria-label': usable ? (c === 'none' ? 'Not pinned' : `Pin ${c.replace('-', ' ')}`) : null, title: usable ? (c === 'none' ? 'Back to the layout position' : `Pin ${c.replace('-', ' ')}`) : null,
        onclick: usable ? () => applyAction(key, e.id, 'pin', c, 'frame') : null });
    }));
    const visible = !e.hidden;
    const ov = (S.overrides[key] || {})[e.id];
    const content = App.textTarget(e.id);
    return [
      el('div', { class: 'insp-head' }, el('span', { class: 'role-chip' }, ic(ROLE_ICON[role] || 'type')), el('div', {}, el('b', { text: elName(e) }), el('small', { text: `in ${f.name} · ${Math.round(e.width)}×${Math.round(e.height)}` }))),
      content ? group('Text', copyField(content, true), el('p', { class: 'hint', text: 'Text is shared by every size.' })) : null,
      !isImg ? group(`Adjust in ${f.name}`,
        el('div', { class: 'ctrl-row' }, el('span', { class: 'label', text: 'Pin' }), pinGrid),
        e.type === 'text' || e.type === 'logo' && !e.src ? el('div', { class: 'ctrl-row' }, el('span', { class: 'label', text: 'Align' }), el('div', { class: 'seg', role: 'group', 'aria-label': 'Alignment' },
          [['left', 'alignLeft'], ['center', 'alignCenter'], ['right', 'alignRight']].map(([a, icn]) => el('button', { 'aria-pressed': alignNow === a, 'aria-label': `Align ${a}`, title: `Align ${a}`, onclick: () => applyAction(key, e.id, 'align', a, 'frame') }, ic(icn))))) : null,
        el('div', { class: 'ctrl-row' }, el('span', { class: 'label', text: 'Size' }), el('div', { class: 'stepper' },
          el('button', { 'aria-label': 'Smaller', title: 'Smaller', onclick: () => applyAction(key, e.id, 'size', .87, 'frame') }, '−'),
          el('output', { 'aria-live': 'polite', text: e.fontSize ? `${Math.round(e.fontSize)}px` : `${Math.round(e.height)}px` }),
          el('button', { 'aria-label': 'Bigger', title: 'Bigger', onclick: () => applyAction(key, e.id, 'size', 1.15, 'frame') }, '+'))),
        el('p', { class: 'hint', text: `Only ${f.name} changes. You can also drag it on the canvas.` }),
      ) : group('Photo', el('p', { class: 'hint', text: 'Chameleon frames the photo for each size. To choose what must stay in view, use Photo framing on the size.' }),
        el('button', { class: 'btn sm', onclick: () => App.select({ key, id: null }) }, ic('image'), 'Photo framing')),
      group('Visibility', el('div', { class: 'ctrl-row' },
        el('span', { text: `Show in ${f.name}` }),
        el('button', { class: 'toggle', role: 'switch', 'aria-checked': visible, 'aria-label': 'Visible', onclick: () => applyAction(key, e.id, 'hide', visible, 'frame') }))),
      ov ? group('Your tweak', el('div', { class: 'ctrl-row' }, el('span', { class: 'muted', text: 'Changed by you in this size.' }),
        el('button', { class: 'btn sm', text: 'Reset', onclick: () => { const before = snapshot(); delete S.overrides[key][e.id]; recordDesignChange('reset tweak', before); App.paint('all'); save(); } }))) : null,
      el('div', { class: 'group' }, el('button', { class: 'btn sm', onclick: () => App.select({ key, id: null }) }, ic('chevronLeft'), `Back to ${f.name}`)),
    ];
  }

  /* why a size looks the way it does, in the engine's own words (minus its internal tier label) */
  function whyGroup(key) {
    const c = chosen(key); if (!c) return null;
    const why = (c.reasons || []).filter(r => !/^Tier \d/.test(r));
    if (!why.length) return null;
    return group('Why it looks like this', el('ul', { class: 'why-list' }, why.slice(0, 6).map(r => el('li', { text: r }))));
  }

  /* photo framing: Auto / Whole photo / Focus area (drag on the photo); it applies to every size */
  let framingMode = null;
  function framingGroup() {
    const p = photoNode(); if (!p) return null;
    const meta = p.meta || {}, mode = framingMode || (meta.keepWhole ? 'whole' : meta.focus ? 'focus' : 'auto');
    const set = (m, focus) => {
      const before = snapshot(), mt = { ...(p.meta || {}) };
      delete mt.keepWhole; delete mt.focus;
      if (m === 'whole') mt.keepWhole = true;
      if (m === 'focus') mt.focus = focus.map(v => Math.round(v * 1e4) / 1e4);
      p.meta = mt; framingMode = null;
      recordDesignChange(m === 'auto' ? 'photo framing: auto' : m === 'whole' ? 'keep whole photo' : 'focus area', before);
      refresh(true); save();
    };
    const seg = el('div', { class: 'seg seg3', role: 'radiogroup', 'aria-label': 'How every size frames the photo' },
      [['auto', 'Auto'], ['focus', 'Focus area'], ['whole', 'Whole photo']].map(([m, label]) => el('button', { role: 'radio', 'aria-checked': mode === m, text: label,
        onclick: () => { if (m === 'focus') { framingMode = 'focus'; paintDesign(true); if (meta.focus) return; return; } set(m); } })));
    const hint = { auto: 'Chameleon finds the subject (faces, people, objects) and frames every size around it.',
      whole: 'Every size shows the entire photo, never cropped. Space around it is filled, not left blank.',
      focus: meta.focus ? 'Every size keeps your focus area in view. Drag on the photo to redraw it.' : 'Drag on the photo to mark what must stay in view at every size.' }[mode];
    const kids = [seg, el('p', { class: 'hint', text: hint })];
    const src = p.src ? GV.resolve(p.src, S.assets) : null;
    if (mode === 'focus' && src) kids.push(focusPicker(src, meta.focus, box => set('focus', box)));
    return group('Photo framing', ...kids);
  }
  function focusPicker(src, focus, done) {
    const wrap = el('div', { class: 'focus-pick' }), img = el('img', { src, alt: 'The whole photo. Drag to mark the focus area.', draggable: 'false' });
    const box = el('div', { class: 'focus-box' });
    wrap.append(img, box);
    const show = b => { if (!b) { box.hidden = true; return; } box.hidden = false; Object.assign(box.style, { left: b[0] * 100 + '%', top: b[1] * 100 + '%', width: b[2] * 100 + '%', height: b[3] * 100 + '%' }); };
    show(focus);
    wrap.addEventListener('pointerdown', ev => {
      ev.preventDefault(); wrap.setPointerCapture(ev.pointerId);
      const r = wrap.getBoundingClientRect(), pt = e2 => [Math.min(1, Math.max(0, (e2.clientX - r.left) / r.width)), Math.min(1, Math.max(0, (e2.clientY - r.top) / r.height))];
      const p0 = pt(ev); let b = null;
      const move = e2 => { const p = pt(e2); b = [Math.min(p0[0], p[0]), Math.min(p0[1], p[1]), Math.abs(p[0] - p0[0]), Math.abs(p[1] - p0[1])]; show(b); };
      const up = () => { wrap.removeEventListener('pointermove', move); wrap.removeEventListener('pointerup', up); wrap.removeEventListener('pointercancel', up);
        if (b && b[2] > .03 && b[3] > .03) done(b); else show(focus); };
      wrap.addEventListener('pointermove', move); wrap.addEventListener('pointerup', up); wrap.addEventListener('pointercancel', up);
    });
    return wrap;
  }
  function cornerOf(e, d) {
    const W = d.canvas.width, H = d.canvas.height, t = Math.min(W, H) * .1;
    const v = e.y <= t ? 'top' : e.y + e.height >= H - t ? 'bottom' : null, h = e.x <= t ? 'left' : e.x + e.width >= W - t ? 'right' : null;
    return v && h ? `${v}-${h}` : 'none';
  }

  /* ═════════ INSPECTOR: RULES ═════════ */
  function paintRules() {
    const rules = S.rules || [];
    $('rules-count').textContent = rules.length;
    $('rules-empty').hidden = rules.length > 0;
    $('rules-list').replaceChildren(...rules.map(r => {
      const cov = ruleCoverage(r);
      const src = r.source === 'text' ? `Typed: “${r.evidence?.text || ''}”` : r.source === 'edit' ? `From your edit${r.evidence?.canvas ? ` in a ${r.evidence.canvas.width}×${r.evidence.canvas.height} frame` : ''}` : 'Added manually';
      let status = null;
      if (r.enabled) {
        if (r.type === 'hide_small') status = el('div', { class: 'rule-status ' + (cov.applies ? 'ok' : 'na') }, ic(cov.applies ? 'eyeOff' : 'eye'), cov.applies ? `Hidden in ${cov.applies} of ${cov.n} frames` : 'No frame is that small');
        else if (cov.applies) status = el('div', { class: 'rule-status ' + (cov.met === cov.applies ? 'ok' : 'warn') }, ic(cov.met === cov.applies ? 'check' : 'alert'), cov.met === cov.applies ? `Met in all ${cov.applies} frames` : `Met in ${cov.met} of ${cov.applies} frames`);
        else status = el('div', { class: 'rule-status na' }, 'No matching element in this design');
      }
      return el('li', { class: 'rule' + (r.enabled ? '' : ' off') + (r.id === App.newRuleId ? ' new' : '') },
        el('span', { class: 'rule-ic' }, ic(RULE_ICON[r.type] || 'sparkle')),
        el('div', {}, el('div', { class: 'rule-label', text: r.label }), el('div', { class: 'rule-meta', text: src }), status),
        el('div', { class: 'rule-ctrl' },
          el('button', { class: 'toggle', role: 'switch', 'aria-checked': r.enabled, 'aria-label': `${r.enabled ? 'Turn off' : 'Turn on'}: ${r.label}`, onclick: () => toggleRule(r) }),
          el('button', { class: 'icon-btn sm', 'aria-label': `Delete rule: ${r.label}`, title: 'Delete', onclick: () => deleteRule(r) }, ic('x'))));
    }));
    setTimeout(() => { App.newRuleId = null; }, 0);
  }
  App.focusRuleInput = () => { openPanel('right', true); setRightTab('rules'); $('rule-input').focus(); };
  $('dock-cmd').onclick = App.focusRuleInput;
  $('rule-form').addEventListener('submit', async e => {
    e.preventDefault();
    const text = $('rule-input').value.trim(); if (!text) return;
    const out = $('parse-result');
    try {
      const r = await api('/parse-rule', 'POST', { text, roles: S.roles });
      if (!r.rules.length) {
        out.replaceChildren(el('div', { class: 'pr-miss', text: 'I couldn’t turn that into a rule yet.' }),
          el('div', { class: 'hint', text: 'Name an element (logo, headline, offer, CTA, image, legal) and what it should do: top-left, center, bigger, below the offer, hide on small banners.' }));
        return;
      }
      const boxes = r.rules.map((x, i) => el('input', { type: 'checkbox', checked: true, id: 'pr-' + i }));
      out.replaceChildren(...[
        el('div', { class: 'label', text: r.rules.length > 1 ? `Understood ${r.rules.length} rules` : 'Understood' }),
        ...r.rules.map((x, i) => el('label', { class: 'pr-row', for: 'pr-' + i }, boxes[i], el('span', { class: 'rule-ic' }, ic(RULE_ICON[x.type])), el('span', { text: x.label }))),
        r.unmatched.length ? el('div', { class: 'pr-miss', text: `Skipped: “${r.unmatched.join('”, “')}”` }) : null,
        el('div', { class: 'pr-actions' },
          el('button', { type: 'button', class: 'btn ghost sm', text: 'Cancel', onclick: () => out.replaceChildren() }),
          el('button', { type: 'button', class: 'btn primary sm', id: 'pr-add', text: r.rules.length > 1 ? 'Add rules' : 'Add rule', onclick: async () => {
            const picked = r.rules.filter((_, i) => boxes[i].checked); if (!picked.length) return;
            try {
              for (const x of picked) await addRule(x.type, x.params, { source: 'text', evidence: x.evidence, label: x.label });
              out.replaceChildren(); $('rule-input').value = '';
            } catch (err) { toast(err.message, { error: true }); await refresh(true); }
          } }))].filter(Boolean));
      $('pr-add').focus();
    } catch (err) { toast(err.message, { error: true }); }
  });
  $('examples').addEventListener('click', e => { const b = e.target.closest('button'); if (!b) return; $('rule-input').value = b.textContent; $('rule-form').requestSubmit(); });

  /* rule bubbles (drag handled in dnd.js; click = apply to selection) */
  const BUBBLES = [
    ['Pin top-left', 'pin', 'pin', 'top-left'], ['Pin top-right', 'pin', 'pin', 'top-right'], ['Pin bottom-left', 'pin', 'pin', 'bottom-left'], ['Pin bottom-right', 'pin', 'pin', 'bottom-right'],
    ['Align left', 'alignLeft', 'align', 'left'], ['Center', 'alignCenter', 'align', 'center'], ['Align right', 'alignRight', 'align', 'right'],
    ['Bigger', 'size', 'size', 'up'], ['Smaller', 'size', 'size', 'down'], ['Hide when small', 'eyeOff', 'hide', true],
  ];
  App.BUBBLES = BUBBLES;
  $('bubbles').replaceChildren(...BUBBLES.map(([label, icon, action, value], i) => el('button', { type: 'button', class: 'bubble', 'data-b': i, 'aria-label': `${label}: apply to the selected element, or drag onto an element` }, ic(icon), label)));
  App.applyBubble = function (i, key, id) {
    const [label, , action, value] = BUBBLES[i];
    const d = display(key), t = d?.elements.find(x => x.id === id); if (!t) return;
    if (t.type === 'image' && action !== 'hide') return toast(`“${label}” works on text, buttons and logos.`, { error: true });
    const v = action === 'size' ? currentWeight(roleOf(t)) * (value === 'up' ? 1.25 : .8) : value;
    applyAction(key, id, action, v, 'all');
  };
  $('bubbles').addEventListener('click', e => {
    const b = e.target.closest('.bubble'); if (!b || b.dataset.dragged) { if (b) delete b.dataset.dragged; return; }
    if (!S.sel?.id) return toast('Select an element on the canvas first, or drag the bubble onto one.');
    App.applyBubble(+b.dataset.b, S.sel.key, S.sel.id);
  });

  /* ═════════ ADD FRAME ═════════ */
  function paintPresets() {
    const groups = CATALOG.map(g => ({ group: g.group, items: g.items.map(([key, name, width, height]) => ({ key, name, width, height })) }));
    if (S.custom.length) groups.push({ group: 'Custom', items: S.custom });
    $('preset-list').replaceChildren(...groups.map(g => el('div', { class: 'preset-group' }, el('span', { class: 'label', text: g.group }),
      ...g.items.map(f => {
        const r = f.width / f.height, sw = r >= 1 ? 18 : Math.max(5, 18 * r), sh = r >= 1 ? Math.max(4, 18 / r) : 18, on = S.selected.has(f.key);
        return el('button', { class: 'preset', type: 'button', 'data-key': f.key, 'aria-pressed': on, 'aria-label': `${f.name} ${f.width} by ${f.height}${on ? ', on canvas' : ''}` },
          el('span', { class: 'shape', 'aria-hidden': 'true' }, el('i', { style: `width:${sw}px;height:${sh}px` })),
          el('span', { class: 'nm', text: f.name }), el('span', { class: 'sz', text: `${f.width}×${f.height}` }), on ? ic('check', 'i chk') : null);
      }))));
  }
  App.presetClick = key => { if (S.selected.has(key)) { App.focusFrame(key); App.select({ key, id: null }); } else addFrame(key); paintPresets(); };
  App.openAddFrame = function () {
    const pop = $('add-frame'), b = $('add-frame-btn').getBoundingClientRect();
    paintPresets(); pop.hidden = false; $('add-frame-btn').setAttribute('aria-expanded', 'true');
    pop.style.left = Math.min(window.innerWidth - 310, b.right + 8) + 'px'; pop.style.top = Math.max(8, Math.min(window.innerHeight - pop.offsetHeight - 8, b.top - 8)) + 'px';
    pop.querySelector('.preset')?.focus();
  };
  App.closeAddFrame = () => { $('add-frame').hidden = true; $('add-frame-btn').setAttribute('aria-expanded', 'false'); };
  $('add-frame-btn').onclick = e => { e.stopPropagation(); $('add-frame').hidden ? App.openAddFrame() : App.closeAddFrame(); };
  document.addEventListener('pointerdown', e => { if (!$('add-frame').hidden && !e.target.closest('#add-frame, #add-frame-btn')) App.closeAddFrame(); });
  $('add-frame').addEventListener('keydown', e => { if (e.key === 'Escape') { e.stopPropagation(); App.closeAddFrame(); $('add-frame-btn').focus(); } });
  $('custom-form').addEventListener('submit', e => {
    e.preventDefault();
    const w = +$('custom-w').value, h = +$('custom-h').value;
    if (!(w >= 64 && w <= 8192 && h >= 64 && h <= 8192)) return toast('Use sizes between 64 and 8192 px.', { error: true });
    const key = `custom-${w}x${h}-${Date.now().toString(36)}`;
    const before = snapshot();
    S.custom.push({ key, name: $('custom-name').value.trim() || `Custom ${w}×${h}`, width: w, height: h });
    S.selected.add(key); recordDesignChange('add custom frame', before);
    $('custom-name').value = ''; paintPresets(); refresh().then(() => App.focusFrame(key)); save();
    toast(`Added ${w}×${h}`);
  });

  /* ═════════ narrow-screen panel toggles ═════════ */
  function openPanel(side, force) {
    const p = $(side), b = $('toggle-' + side), open = force ?? !p.classList.contains('open');
    p.classList.toggle('open', open); b.setAttribute('aria-expanded', open);
  }
  App.openPanel = openPanel;
  $('toggle-left').onclick = () => openPanel('left'); $('toggle-right').onclick = () => openPanel('right');

  /* ── painter ── */
  App.painters.push(what => {
    if (S.view !== 'editor') return;
    if (what === 'canvas') return;
    paintLayers();
    if (what !== 'metrics' || !S.sel || !S.sel.id) paintDesign();
    if (what !== 'selection') paintRules();
    if (!$('add-frame').hidden) paintPresets();
    if (what === 'selection' && S.sel?.id && window.innerWidth <= 900) { /* keep panels closed on phones */ }
  });
})();
