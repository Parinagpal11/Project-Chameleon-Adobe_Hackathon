/* Chameleon — draw a chameleon-graph/1 design onto a canvas.
   GR.draw(canvas, design, { scale, dpr }) — design is the JSON graph (page + nodes). */
'use strict';
(function () {
  const imgCache = new Map();
  function loadImage(src, onload) {
    if (imgCache.has(src)) return imgCache.get(src);
    const im = new Image();
    im.onload = () => onload && onload();
    im.src = src; imgCache.set(src, im);
    return im;
  }

  function roundRect(ctx, x, y, w, h, r) {
    r = Math.max(0, Math.min(r || 0, w / 2, h / 2));
    ctx.beginPath();
    ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
  }

  function shade(hex, amt) {
    const m = /^#?([0-9a-f]{6})$/i.exec(hex || ''); if (!m) return hex || '#999';
    const n = parseInt(m[1], 16), f = c => Math.max(0, Math.min(255, Math.round(c + 255 * amt)));
    return '#' + [(n >> 16) & 255, (n >> 8) & 255, n & 255].map(f).map(v => v.toString(16).padStart(2, '0')).join('');
  }

  function wrap(ctx, text, maxW) {
    const out = [];
    for (const para of String(text || '').split('\n')) {
      let line = '';
      for (const word of para.split(/\s+/).filter(Boolean)) {
        const test = line ? line + ' ' + word : word;
        if (ctx.measureText(test).width <= maxW || !line) line = test;
        else { out.push(line); line = word; }
      }
      out.push(line);
    }
    return out;
  }

  function drawText(ctx, n) {
    const s = n.style || {}, [x, y, w, h] = n.box;
    let size = s.fontSize || h * .7;
    const lh = s.lineHeight || 1.15, fam = s.fontFamily || 'Inter';
    const set = () => { ctx.font = `${s.fontWeight || 400} ${size}px "${fam}", Inter, system-ui, sans-serif`;
      if ('letterSpacing' in ctx) ctx.letterSpacing = (s.letterSpacing || 0) + 'px'; };
    set();
    let lines = wrap(ctx, n.text, w);
    // the box is the truth: shrink until the wrapped text fits it (designs exported at other zoom levels)
    for (let guard = 0; guard < 40 && (lines.length * size * lh > h * 1.08 || lines.some(l => ctx.measureText(l).width > w * 1.02)); guard++) {
      size *= .95; set(); lines = wrap(ctx, n.text, w);
    }
    ctx.fillStyle = s.color || '#111';
    ctx.textBaseline = 'alphabetic';
    const align = s.align || 'left';
    ctx.textAlign = align === 'center' ? 'center' : align === 'right' ? 'right' : 'left';
    const tx = align === 'center' ? x + w / 2 : align === 'right' ? x + w : x;
    lines.forEach((l, i) => ctx.fillText(l, tx, y + size * (i * lh + (lh - 1) / 2 + .8)));
    if ('letterSpacing' in ctx) ctx.letterSpacing = '0px';
    n._fitted = size;
  }

  function drawImage(ctx, n, redraw) {
    const s = n.style || {}, [x, y, w, h] = n.box;
    ctx.save();
    roundRect(ctx, x, y, w, h, s.radius); ctx.clip();
    const im = n.src ? loadImage(n.src, redraw) : null;
    if (im && im.complete && im.naturalWidth) {
      if (n.crop) {   // subject-aware crop chosen by the engine (image-relative x, y, w, h)
        const [cx, cy, cw, ch] = n.crop, iw = im.naturalWidth, ih = im.naturalHeight;
        ctx.drawImage(im, cx * iw, cy * ih, cw * iw, ch * ih, x, y, w, h);
      } else {
        const k = Math.max(w / im.naturalWidth, h / im.naturalHeight);
        const dw = im.naturalWidth * k, dh = im.naturalHeight * k;
        ctx.drawImage(im, x + (w - dw) / 2, y + (h - dh) / 2, dw, dh);
      }
    } else {   // placeholder photo: soft gradient, horizon and a label
      const base = s.fill || '#8a8f99';
      // with a crop, the placeholder "photo" is larger than the slot: draw it at its virtual size and offset
      let vx = x, vy = y, vw = w, vh = h;
      if (n.crop) { const [cx0, cy0, cw0, ch0] = n.crop; vw = w / cw0; vh = h / ch0; vx = x - cx0 * vw; vy = y - cy0 * vh; }
      const g = ctx.createLinearGradient(vx, vy, vx + vw, vy + vh);
      g.addColorStop(0, shade(base, .12)); g.addColorStop(1, shade(base, -.12));
      ctx.fillStyle = g; ctx.fillRect(x, y, w, h);
      if (n.subject) {   // a soft blob where the subject is, so crops visibly keep or lose it
        const [sx, sy, sw0, sh0] = n.subject, sw = sw0, sh = sh0;
        const cx = vx + (sx + sw / 2) * vw, cy = vy + (sy + sh / 2) * vh, r = Math.max(sw * vw, sh * vh) / 2;
        const rg = ctx.createRadialGradient(cx, cy, r * .1, cx, cy, r);
        rg.addColorStop(0, shade(base, .32)); rg.addColorStop(1, shade(base, .02) + '00');
        ctx.fillStyle = rg; ctx.beginPath(); ctx.ellipse(cx, cy, sw * vw / 2, sh * vh / 2, 0, 0, Math.PI * 2); ctx.fill();
      }
      const label = (n.meta && n.meta.label) || n.role || 'image';
      const small = h < 140 || w / h > 2;            // a logo-sized placeholder: label centred and sized to the box
      let fs = small ? h * .5 : Math.max(10, Math.min(w, h) * .09);
      ctx.font = `600 ${fs}px Inter, system-ui, sans-serif`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      if (small) {
        const tw = ctx.measureText(label).width;
        if (tw > w * .8) { fs *= w * .8 / tw; ctx.font = `600 ${fs}px Inter, system-ui, sans-serif`; }
      }
      const hm = /^#?([0-9a-f]{6})$/i.exec(base), hv = hm ? parseInt(hm[1], 16) : 0;
      const lum = hm ? (.299 * ((hv >> 16) & 255) + .587 * ((hv >> 8) & 255) + .114 * (hv & 255)) / 255 : 0;
      ctx.fillStyle = lum > .6 ? (small ? 'rgba(14,34,51,.85)' : 'rgba(0,0,0,.55)') : 'rgba(255,255,255,.8)';   // readable on light and dark placeholders
      ctx.fillText(label, x + w / 2, small ? y + h / 2 : y + h - Math.max(fs * 1.2, h * .1));
    }
    ctx.restore();
  }

  function drawShape(ctx, n) {
    const s = n.style || {}, [x, y, w, h] = n.box;
    ctx.save();
    if (s.opacity != null) ctx.globalAlpha = s.opacity;
    ctx.fillStyle = s.fill || 'transparent';
    if (n.shape === 'ellipse') { ctx.beginPath(); ctx.ellipse(x + w / 2, y + h / 2, w / 2, h / 2, 0, 0, Math.PI * 2); }
    else roundRect(ctx, x, y, w, h, s.radius);
    if (s.fill) ctx.fill();
    if (s.stroke) { ctx.strokeStyle = s.stroke; ctx.lineWidth = s.strokeWidth || 2; ctx.stroke(); }
    ctx.restore();
  }

  // opts.view = { width, height, sx, sy, ox, oy }: draw the design into another canvas size with a plain
  // transform (used to show what naive stretching / centre-cropping would do)
  function draw(canvas, design, opts = {}) {
    const v = opts.view;
    const W = v ? v.width : design.page.width, H = v ? v.height : design.page.height;
    const scale = opts.scale || 1, dpr = opts.dpr || window.devicePixelRatio || 1;
    canvas.width = Math.round(W * scale * dpr); canvas.height = Math.round(H * scale * dpr);
    canvas.style.width = W * scale + 'px'; canvas.style.height = H * scale + 'px';
    const ctx = canvas.getContext('2d');
    ctx.setTransform(scale * dpr, 0, 0, scale * dpr, 0, 0);
    ctx.fillStyle = opts.matte || design.page.background || '#fff'; ctx.fillRect(0, 0, W, H);
    if (v) {
      ctx.beginPath(); ctx.rect(0, 0, W, H); ctx.clip();
      ctx.transform(v.sx, 0, 0, v.sy, v.ox || 0, v.oy || 0);
      ctx.fillStyle = design.page.background || '#fff'; ctx.fillRect(0, 0, design.page.width, design.page.height);
    }
    const redraw = () => draw(canvas, design, opts);
    const bd = design.page.backdrop;   // a photo of the design, blurred and darkened, behind everything
    if (bd && !v) {
      const src = (design.nodes.find(n => n.id === bd.image) || {}).src;
      const im = src ? loadImage(src, redraw) : null;
      if (im && im.complete && im.naturalWidth) {
        const k = Math.max(W / im.naturalWidth, H / im.naturalHeight), dw = im.naturalWidth * k, dh = im.naturalHeight * k;
        ctx.save(); ctx.filter = `blur(${(bd.blur || .04) * Math.max(W, H)}px)`;
        const pad = (bd.blur || .04) * Math.max(W, H) * 2;        // overscan so the blur has no light edge
        ctx.drawImage(im, (W - dw) / 2 - pad, (H - dh) / 2 - pad, dw + 2 * pad, dh + 2 * pad);
        ctx.restore();
        ctx.fillStyle = `rgba(0,0,0,${bd.dim == null ? .5 : bd.dim})`; ctx.fillRect(0, 0, W, H);
      }
    }
    const nodes = design.nodes.filter(n => n.type !== 'group' && !n.hidden)
      .map((n, i) => ({ n, z: n.z != null ? n.z : i })).sort((a, b) => a.z - b.z).map(o => o.n);
    for (const n of nodes) {
      if (n.type === 'text') drawText(ctx, n);
      else if (n.type === 'image') drawImage(ctx, n, redraw);
      else drawShape(ctx, n);
    }
  }

  window.GR = { draw };
})();
