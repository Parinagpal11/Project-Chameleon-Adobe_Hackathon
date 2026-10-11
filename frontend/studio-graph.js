/* Chameleon Studio — the bridge between the Studio's editor and the layout engine's graph designs.

   The engine returns every size as a chameleon-graph/1 design (page + nodes, groups for buttons).
   The editor works with a flat list of "items" (one per thing a designer can pick: a text, a button,
   the logo, the photo), each with x / y / width / height. GV turns a graph into items, and draws a
   graph with the items' edits applied (moved, resized, hidden), so the canvas always shows exactly
   what the engine made plus the designer's frame-only tweaks. */
'use strict';
(function () {
  const clone = o => JSON.parse(JSON.stringify(o));
  const NOT_PICKABLE = new Set(['panel', 'decoration']);

  function byId(g) { const m = {}; for (const n of g.nodes) m[n.id] = n; return m; }
  function childSet(g) { const s = new Set(); for (const n of g.nodes) if (n.type === 'group') (n.children || []).forEach(c => s.add(c)); return s; }
  function union(boxes) {
    const bs = boxes.filter(b => b && b[2] > 0 && b[3] > 0); if (!bs.length) return null;
    const x = Math.min(...bs.map(b => b[0])), y = Math.min(...bs.map(b => b[1]));
    return [x, y, Math.max(...bs.map(b => b[0] + b[2])) - x, Math.max(...bs.map(b => b[1] + b[3])) - y];
  }
  function leaves(g, n, idx) {
    if (n.type !== 'group') return [n];
    return (n.children || []).flatMap(c => idx[c] ? leaves(g, idx[c], idx) : []);
  }

  /** The things a designer can pick in this design, in drawing order. roles: {id: role} from the engine. */
  function items(g, roles = {}) {
    const idx = byId(g), kids = childSet(g), out = [];
    for (const n of g.nodes) {
      if (kids.has(n.id)) continue;
      const role = roles[n.id] || n.role || null;
      let box = n.box, type, text = null, fontSize = null;
      if (n.type === 'group') {
        const ls = leaves(g, n, idx);
        box = union(ls.filter(l => !l.hidden).map(l => l.box)) || n.box;
        const label = ls.find(l => l.type === 'text');
        text = label ? label.text : null; fontSize = label ? (label.style || {}).fontSize : null;
        type = ls.some(l => l.type === 'shape') && label ? 'button' : 'group';
      } else if (n.type === 'text') {
        type = role === 'logo' ? 'logo' : 'text'; text = n.text; fontSize = (n.style || {}).fontSize;
      } else if (n.type === 'image') {
        type = role === 'logo' ? 'logo' : 'image';
      } else {
        type = NOT_PICKABLE.has(role) || role === 'background' ? 'decoration' : 'shape';
      }
      if (NOT_PICKABLE.has(role)) type = 'decoration';
      if (!box) continue;
      out.push({ id: n.id, node: n.type, type, x: box[0], y: box[1], width: box[2], height: box[3],
                 fontSize, text, hidden: !!n.hidden, align: (n.style || {}).align || null,
                 src: n.type === 'image' ? (n.src || null) : null, genome: { role: role || (type === 'button' ? 'cta' : 'body') } });
    }
    return out;
  }

  /** The graph with the items' edits applied: each changed item's node (and a group's children) moved,
      scaled and hidden to match. base: the engine's graph; baseItems: items(base); now: the edited items. */
  function apply(base, baseItems, now) {
    const g = clone(base), idx = byId(g), was = {};
    for (const it of baseItems) was[it.id] = it;
    for (const it of now) {
      const b = was[it.id], n = idx[it.id]; if (!b || !n) continue;
      const moved = Math.abs(it.x - b.x) > .01 || Math.abs(it.y - b.y) > .01 || Math.abs(it.width - b.width) > .01 || Math.abs(it.height - b.height) > .01;
      const ls = leaves(g, n, idx);
      if (it.hidden !== b.hidden) { n.hidden = !!it.hidden; ls.forEach(l => { l.hidden = !!it.hidden; }); }
      if (it.align && it.align !== b.align && n.type === 'text') n.style = { ...(n.style || {}), align: it.align };
      if (moved && b.width > 0 && b.height > 0) {
        const sx = it.width / b.width, sy = it.height / b.height, k = Math.min(sx, sy);
        for (const l of ls) {
          const [x, y, w, h] = l.box;
          l.box = [it.x + (x - b.x) * sx, it.y + (y - b.y) * sy, w * sx, h * sy];
          if (l.type === 'text' && l.style && l.style.fontSize) l.style = { ...l.style, fontSize: l.style.fontSize * k };
        }
        if (n.type === 'group') n.box = [it.x, it.y, it.width, it.height];
      }
      if (it.fontSize && b.fontSize && Math.abs(it.fontSize - b.fontSize) > .01 && !moved) {
        const k = it.fontSize / b.fontSize;
        for (const l of ls) if (l.type === 'text' && l.style) l.style = { ...l.style, fontSize: l.style.fontSize * k };
      }
    }
    return g;
  }

  /** Photos are not repeated in every result: put each node's picture back (from the source design),
      turning the Studio's own uploads (asset:id) into data URLs the canvas can draw. */
  function withSrc(g, source, assets) {
    const src = {};
    for (const n of source.nodes) if (n.src) src[n.id] = n.src;
    for (const n of g.nodes) {
      const s = n.src || (n.srcFrom ? src[n.srcFrom] : null);
      if (s) n.src = resolve(s, assets);
    }
    return g;
  }
  function resolve(s, assets) { return s && s.startsWith('asset:') ? (assets || {})[s.slice(6)] || null : s; }

  /** The source design with uploads resolved, as the engine needs to see the real photo. */
  function resolved(design, assets) {
    const d = clone(design);
    for (const n of d.nodes) if (n.src && n.src.startsWith('asset:')) { const s = resolve(n.src, assets); if (s) n.src = s; else delete n.src; }
    return d;
  }

  /** A display design (see display() in core.js) drawn on a canvas. */
  function draw(canvas, d, opts = {}) {
    const g = d.base ? apply(d.base, d.baseItems, d.elements) : d;
    window.GR.draw(canvas, g, { ...opts });
    return g;
  }

  window.GV = { items, apply, withSrc, resolved, resolve, draw, union };
})();
