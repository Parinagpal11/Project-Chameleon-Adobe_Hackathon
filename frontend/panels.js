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
            ic(ROLE_ICON[roleOf(e)] || 'type', 'i row-icon'),
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
    const b = S.design.brand;
    $('swatches').replaceChildren(...SWATCHES.map(([k, label]) => {
      let before = null;
      const small = el('small', { text: b[k] });
      return el('label', { class: 'swatch' },
        el('input', { type: 'color', value: b[k], 'aria-label': `${label} color`,
          onfocus: () => { before = snapshot(); }, onclick: () => { before = before || snapshot(); },
          oninput: e => { S.design.brand[k] = e.target.value; small.textContent = e.target.value; App.paint('canvas'); },
          onchange: () => { if (before) recordDesignChange(`${label.toLowerCase()} color`, before); before = null; save(); } }),
        el('span', {}, el('b', { text: label }), small));
    }));
    $('brand-font').value = b.font;
    const textEls = S.design.elements.filter(e => e.type === 'text' || e.type === 'button' || (e.type === 'logo' && !e.src));
    $('copy-fields').replaceChildren(...textEls.map(e => copyField(e)));
    for (const kind of ['hero', 'logo']) {
      const t = kind === 'hero' ? S.design.elements.find(e => e.type === 'image') : S.design.elements.find(e => e.type === 'logo');
      const src = t && t.src && t.src.startsWith('asset:') ? S.assets[t.src.slice(6)] : null;
      $('thumb-' + kind).style.backgroundImage = src ? `url("${src}")` : '';
      $('thumb-' + kind).classList.toggle('has', !!src);
      $('rm-' + kind).hidden = !src;
    }
  };
  function copyField(e, compact) {
    let before = null;
    const long = (e.text || '').length > 28 && e.type === 'text';
    const input = el(long ? 'textarea' : 'input', { maxlength: 200, rows: long ? 2 : null, 'aria-label': `${niceRole(roleOf(e))} copy`,
      onfocus: () => { before = snapshot(); },
      oninput: ev => { const src = S.design.elements.find(x => x.id === e.id); if (src) src.text = ev.target.value; refresh(); },
      onchange: () => { if (before) recordDesignChange(`${lowerRole(roleOf(e))} copy`, before); before = null; save(); App.paintAssets(); } });
    input.value = e.text || '';
    return compact ? input : el('label', {}, `${niceRole(roleOf(e))}${e.type === 'logo' ? ' (text logo)' : ''}`, input);
  }
  $('brand-font').addEventListener('change', async e => {
    const before = snapshot(); S.design.brand.font = e.target.value;
    try { await document.fonts.load(`800 40px "${e.target.value}"`); } catch { /* offline */ }
    recordDesignChange('typeface', before); App.paint('canvas'); save();
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
        el('div', { class: 'stat' }, el('b', { text: S.rules.filter(r => r.enabled).length }), el('span', { text: 'Active rules' })),
        el('div', { class: 'stat' }, el('b', { text: all.length }), el('span', { text: 'Warnings' })))),
      group('Needs attention', all.length
        ? el('ul', { class: 'issue-list' }, all.slice(0, 12).map(i => el('li', { class: 'issue' }, ic('alert'), el('span', { text: `${i.f.name}: ${i.text}` }),
          el('button', { class: 'btn ghost sm', text: 'Show', onclick: () => { App.select({ key: i.key, id: i.id || null }); App.focusFrame(i.key); } }))))
        : el('div', { class: 'issue ok' }, ic('check'), el('span', { text: 'Every frame passes the checks' }))),
      group('Get started', el('p', { class: 'hint', text: 'Click any element on the canvas to edit it. Choose whether a change applies to all frames (a rule) or just one.' }),
        el('div', { style: 'display:flex;gap:6px;flex-wrap:wrap' },
          el('button', { class: 'btn sm', onclick: () => App.openAddFrame?.() }, ic('plus'), 'Add frame'),
          el('button', { class: 'btn sm', onclick: () => App.startTour?.(0) }, ic('play'), 'Take the tour'))),
    ];
  }
  function frameView(key, d) {
    const f = fmt(key), res = S.results[key], issues = issuesOf(key), tweaks = Object.keys(S.overrides[key] || {}).length;
    return [
      el('div', { class: 'insp-head' }, el('span', { class: 'role-chip' }, ic('frame')), el('div', {}, el('b', { text: f.name }), el('small', { text: `${f.width} × ${f.height} px · ${f.group}` }))),
      group('Layout', el('div', { class: 'layouts', role: 'radiogroup', 'aria-label': 'Layout options' }, (res?.candidates || []).map(c => {
        const on = c === chosen(key), cv = el('canvas', { 'aria-hidden': 'true' }), dd = clone(c.design); dd.brand = S.design.brand;
        R.draw(cv, dd, { assets: S.assets, scale: Math.min(76 / f.width, 52 / f.height), dpr: DPR });
        const n = issuesOf(key, c).length;
        return el('button', { class: 'layout-opt', role: 'radio', 'aria-checked': on, 'aria-label': `${STRATEGY[c.strategy] || c.strategy}${n ? `, ${n} warnings` : ''}`, onclick: () => {
          if (on) return; const before = snapshot(); S.choices[key] = c.strategy; recordDesignChange('layout choice', before); App.paint('all'); save();
        } }, cv, el('span', { text: STRATEGY[c.strategy] || c.strategy }), n ? el('span', { class: 'warnmark', text: `${n} warning${n > 1 ? 's' : ''}` }) : el('span', { class: 'okmark', text: '✓ No issues' }));
      }))),
      group('Checks', issues.length
        ? el('ul', { class: 'issue-list' }, issues.map(i => el('li', { class: 'issue' }, ic('alert'), el('span', { text: i.text }), i.id ? el('button', { class: 'btn ghost sm', text: 'Select', onclick: () => App.select({ key, id: i.id }) }) : null)))
        : el('div', { class: 'issue ok' }, ic('check'), el('span', { text: 'No overlaps, nothing outside the frame, text 12px or larger, rules met' }))),
      tweaks ? group('Frame-only tweaks', el('div', { class: 'ctrl-row' }, el('span', { class: 'muted', text: `${tweaks} element${tweaks > 1 ? 's' : ''} changed only here` }), el('button', { class: 'btn sm', text: 'Reset', onclick: () => clearOverrides(key) }))) : null,
      group('Frame', el('div', { style: 'display:flex;gap:6px;flex-wrap:wrap' },
        el('button', { class: 'btn sm', onclick: () => exportPng(key) }, ic('download'), 'Export PNG'),
        el('button', { class: 'btn sm', onclick: () => App.focusFrame(key) }, ic('zoomIn'), 'Zoom to frame'),
        el('button', { class: 'btn sm danger', onclick: () => removeFrame(key) }, ic('trash'), 'Remove'))),
    ];
  }
  function elementView(key, d, e) {
    const f = fmt(key), role = roleOf(e), isImg = e.type === 'image', all = S.scope === 'all';
    const short = Math.min(f.width, f.height);
    const scope = el('div', { class: 'scope', role: 'radiogroup', 'aria-label': 'Apply changes to' },
      el('button', { role: 'radio', 'aria-checked': all, onclick: () => { S.scope = 'all'; paintDesign(); } }, 'All frames'),
      el('button', { role: 'radio', 'aria-checked': !all, onclick: () => { S.scope = 'frame'; paintDesign(); } }, 'This frame'));
    const pinRule = ruleFor('pin', role), alignNow = e.align || 'left';
    const pinVal = all ? (pinRule ? pinRule.params.corner : 'none') : cornerOf(e, d);
    const cells = ['top-left', 'top-center', 'top-right', 'mid-left', 'none', 'mid-right', 'bottom-left', 'bottom-center', 'bottom-right'];
    const pinGrid = el('div', { class: 'pin-grid', role: 'group', 'aria-label': 'Pin to corner' }, cells.map(c => {
      const usable = CORNERS.includes(c) || c === 'none';
      return el('button', { class: c === 'none' ? 'center' : usable ? '' : 'na', tabindex: usable ? null : '-1', 'aria-hidden': usable ? null : 'true', disabled: !usable || null,
        'aria-pressed': usable ? pinVal === c : null, 'aria-label': usable ? (c === 'none' ? 'Not pinned' : `Pin ${c.replace('-', ' ')}`) : null, title: usable ? (c === 'none' ? 'Not pinned (follows layout)' : `Pin ${c.replace('-', ' ')}`) : null,
        onclick: usable ? () => applyAction(key, e.id, 'pin', c) : null });
    }));
    const weight = all ? currentWeight(role) : 1;
    const hiddenHere = !!e.hidden, hideRule = ruleFor('hide_small', role);
    const visible = all ? !(hideRule && short < hideRule.params.below) : !hiddenHere;
    const ov = (S.overrides[key] || {})[e.id];
    const rel = rulesForRole(role);
    const content = (e.type === 'text' || e.type === 'button' || (e.type === 'logo' && !e.src)) ? S.design.elements.find(x => x.id === e.id) : null;
    return [
      el('div', { class: 'insp-head' }, el('span', { class: 'role-chip' }, ic(ROLE_ICON[role] || 'type')), el('div', {}, el('b', { text: elName(e) }), el('small', { text: `in ${f.name} · ${Math.round(e.width)}×${Math.round(e.height)}` }))),
      group(null, scope, el('p', { class: 'hint', text: all ? 'Changes are saved as campaign rules and update every frame.' : `Changes only affect ${f.name}.` })),
      group('Role', el('select', { 'aria-label': 'Semantic role', onchange: ev => {
        const src = S.design.elements.find(x => x.id === e.id); if (!src) return; const before = snapshot();
        src.genome = Object.assign(src.genome || { importance: .5, removable: false, scalable: true, reflow: false, relationships: [] }, { role: ev.target.value, removable: ev.target.value === 'decoration' });
        recordDesignChange('role change', before); refresh(); save();
      } }, ROLES.map(r => el('option', { value: r, selected: r === role, text: niceRole(r) }))), el('p', { class: 'hint', text: 'Rules follow roles, so they work on any design.' })),
      content ? group('Content', copyField(content, true), el('p', { class: 'hint', text: 'Copy is shared by every frame.' })) : null,
      !isImg ? group('Layout',
        el('div', { class: 'ctrl-row' }, el('span', { class: 'label', text: 'Pin' }), pinGrid),
        el('div', { class: 'ctrl-row' }, el('span', { class: 'label', text: 'Align' }), el('div', { class: 'seg', role: 'group', 'aria-label': 'Alignment' },
          [['left', 'alignLeft'], ['center', 'alignCenter'], ['right', 'alignRight']].map(([a, icn]) => el('button', { 'aria-pressed': alignNow === a, 'aria-label': `Align ${a}`, title: `Align ${a}`, onclick: () => applyAction(key, e.id, 'align', a) }, ic(icn))))),
        el('div', { class: 'ctrl-row' }, el('span', { class: 'label', text: 'Size' }), el('div', { class: 'stepper' },
          el('button', { 'aria-label': 'Smaller', title: 'Smaller', onclick: () => applyAction(key, e.id, 'size', all ? weight * .8 : .87) }, '−'),
          el('output', { 'aria-live': 'polite', text: all ? `×${(Math.round(weight * 100) / 100).toFixed(2)}` : `${Math.round(e.fontSize || e.height)}px` }),
          el('button', { 'aria-label': 'Bigger', title: 'Bigger', onclick: () => applyAction(key, e.id, 'size', all ? weight * 1.25 : 1.15) }, '+'))),
      ) : null,
      group('Visibility', el('div', { class: 'ctrl-row' },
        el('span', { text: all ? `Show in frames ${short}px and smaller` : `Show in ${f.name}` }),
        el('button', { class: 'toggle', role: 'switch', 'aria-checked': visible, 'aria-label': 'Visible', onclick: () => applyAction(key, e.id, 'hide', visible) })),
        all && hideRule ? el('p', { class: 'hint', text: `Rule: hidden when the short side is under ${hideRule.params.below}px.` }) : null),
      ov ? group('Frame tweak', el('div', { class: 'ctrl-row' }, el('span', { class: 'muted', text: 'This element is adjusted only in this frame.' }),
        el('button', { class: 'btn sm', text: 'Reset', onclick: () => { const before = snapshot(); delete S.overrides[key][e.id]; recordDesignChange('reset tweak', before); App.paint('all'); save(); } }))) : null,
      group('Rules for this role', rel.length ? el('ul', { class: 'mini-rules' }, rel.map(r => el('li', {}, ic(RULE_ICON[r.type]), el('span', { text: r.label })))) : el('p', { class: 'hint', text: 'None yet. Drag it on the canvas or use the controls above.' })),
      el('div', { class: 'group' }, el('button', { class: 'btn sm', onclick: () => App.select({ key, id: null }) }, ic('chevronLeft'), `Back to ${f.name}`)),
    ];
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
