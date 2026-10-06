/* Canvas renderer shared by the board, the editor and exports. */
(function (root) {
  'use strict';
  const DEFAULT_BRAND = { background: '#e6b56e', text: '#2b1d14', primary: '#26402f', accent: '#cc874e', font: 'Inter' };
  const images = new Map();   // src → HTMLImageElement
  let onImageLoad = () => {};

  function image(src) {
    if (!src) return null;
    let img = images.get(src);
    if (!img) {
      img = new Image();
      img.onload = () => onImageLoad();
      img.src = src;
      images.set(src, img);
    }
    return img.complete && img.naturalWidth ? img : null;
  }

  function luminance(hex) {
    const n = parseInt(hex.slice(1), 16), c = [n >> 16, (n >> 8) & 255, n & 255].map(v => {
      v /= 255; return v <= .03928 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4;
    });
    return .2126 * c[0] + .7152 * c[1] + .0722 * c[2];
  }
  function onColor(hex) { return luminance(hex) > .42 ? '#14110f' : '#fffaf0'; }
  function shade(hex, amt) {
    const n = parseInt(hex.slice(1), 16);
    const f = v => Math.max(0, Math.min(255, Math.round(v + amt * 255)));
    return '#' + [f(n >> 16), f((n >> 8) & 255), f(n & 255)].map(v => v.toString(16).padStart(2, '0')).join('');
  }

  function wrap(c, text, maxW) {
    const words = String(text || '').split(/\s+/).filter(Boolean), lines = [];
    let cur = '';
    for (const w of words) {
      const t = cur ? cur + ' ' + w : w;
      if (c.measureText(t).width <= maxW || !cur) cur = t; else { lines.push(cur); cur = w; }
    }
    if (cur) lines.push(cur);
    return lines.length ? lines : [''];
  }

  function weight(e) {
    const r = e.genome && e.genome.role;
    return r === 'headline' || r === 'offer' ? 800 : r === 'legal' || r === 'body' ? 500 : 700;
  }

  /** Draw text fitted inside the element box (wraps, then shrinks until it fits). */
  function fitText(c, e, text, font, color, align) {
    let fs = e.fontSize || Math.min(e.height * .6, 40);
    const maxLines = e.type === 'button' || e.type === 'logo' ? 1 : 6;
    let lines;
    for (let i = 0; i < 30; i++) {
      c.font = `${weight(e)} ${fs}px "${font}", Inter, system-ui, sans-serif`;
      lines = wrap(c, text, e.width - (e.type === 'button' ? fs * 1.2 : 0));
      const tooWide = lines.some(l => c.measureText(l).width > e.width + .5);
      if (lines.length <= maxLines && lines.length * fs * 1.14 <= e.height + .5 && !tooWide) break;
      if (maxLines === 1 && lines.length > 1) lines = [String(text)];
      fs *= .92;
    }
    c.fillStyle = color;
    c.textBaseline = 'middle';
    c.textAlign = align === 'center' ? 'center' : align === 'right' ? 'right' : 'left';
    const lh = fs * 1.14, total = lines.length * lh;
    const x = align === 'center' ? e.x + e.width / 2 : align === 'right' ? e.x + e.width : e.x;
    let y = e.y + (e.height - total) / 2 + lh / 2;
    for (const l of lines) { c.fillText(l, x, y); y += lh; }
    return fs;
  }

  function roundRect(c, x, y, w, h, r) {
    r = Math.min(r, w / 2, h / 2);
    c.beginPath(); c.moveTo(x + r, y); c.arcTo(x + w, y, x + w, y + h, r); c.arcTo(x + w, y + h, x, y + h, r);
    c.arcTo(x, y + h, x, y, r); c.arcTo(x, y, x + w, y, r); c.closePath();
  }

  function drawCup(c, e, brand) {
    c.fillStyle = brand.accent; c.fillRect(e.x, e.y, e.width, e.height);
    const g = c.createLinearGradient(e.x, e.y, e.x, e.y + e.height);
    g.addColorStop(0, 'rgba(255,255,255,.12)'); g.addColorStop(1, 'rgba(0,0,0,.12)');
    c.fillStyle = g; c.fillRect(e.x, e.y, e.width, e.height);
    const cx = e.x + e.width / 2, cy = e.y + e.height / 2, r = Math.min(e.width * .3, e.height * .26);
    c.fillStyle = shade(brand.accent, -.25);
    c.beginPath(); c.ellipse(cx, cy + r * .6, r * 1.12, r * .36, 0, 0, Math.PI * 2); c.fill();
    c.fillStyle = '#fcf1d5'; c.fillRect(cx - r * .7, cy - r * .6, r * 1.4, r * 1.2);
    c.beginPath(); c.ellipse(cx, cy + r * .6, r * .7, r * .2, 0, 0, Math.PI * 2); c.fill();
    c.beginPath(); c.ellipse(cx, cy - r * .6, r * .7, r * .2, 0, 0, Math.PI * 2); c.fill();
    c.strokeStyle = '#fcf1d5'; c.lineWidth = r * .13;
    c.beginPath(); c.arc(cx + r * .8, cy, r * .33, -Math.PI / 2, Math.PI / 2); c.stroke();
    c.fillStyle = '#543528'; c.beginPath(); c.ellipse(cx, cy - r * .6, r * .57, r * .12, 0, 0, Math.PI * 2); c.fill();
  }

  function drawSneaker(c, e, brand) {
    c.fillStyle = brand.accent; c.fillRect(e.x, e.y, e.width, e.height);
    const g = c.createRadialGradient(e.x + e.width * .5, e.y + e.height * .45, 0, e.x + e.width * .5, e.y + e.height * .45, Math.max(e.width, e.height) * .7);
    g.addColorStop(0, 'rgba(255,255,255,.25)'); g.addColorStop(1, 'rgba(0,0,0,.25)'); c.fillStyle = g; c.fillRect(e.x, e.y, e.width, e.height);
    const s = Math.min(e.width, e.height * 1.6) * .8, x = e.x + (e.width - s) / 2, y = e.y + e.height / 2 - s * .22;
    c.fillStyle = '#f5f5f0';
    c.beginPath(); c.moveTo(x, y + s * .38); c.quadraticCurveTo(x + s * .05, y + s * .1, x + s * .32, y + s * .08);
    c.lineTo(x + s * .48, y + s * .22); c.quadraticCurveTo(x + s * .8, y + s * .2, x + s, y + s * .34); c.lineTo(x + s, y + s * .44); c.lineTo(x, y + s * .44); c.closePath(); c.fill();
    c.fillStyle = brand.primary; c.fillRect(x, y + s * .42, s, s * .07);
    c.strokeStyle = 'rgba(0,0,0,.35)'; c.lineWidth = s * .012;
    for (let i = 0; i < 4; i++) { c.beginPath(); c.moveTo(x + s * (.36 + i * .05), y + s * .16 + i * s * .025); c.lineTo(x + s * (.42 + i * .05), y + s * .24 + i * s * .02); c.stroke(); }
  }
  function drawScreen(c, e, brand) {
    c.fillStyle = brand.accent; c.fillRect(e.x, e.y, e.width, e.height);
    const pad = Math.min(e.width, e.height) * .1, w = e.width - pad * 2, h = Math.min(e.height - pad * 2, w * .7), x = e.x + pad, y = e.y + (e.height - h) / 2;
    c.fillStyle = '#ffffff'; roundRect(c, x, y, w, h, Math.min(w, h) * .04); c.fill();
    c.fillStyle = 'rgba(20,26,51,.08)'; c.fillRect(x, y, w, h * .1);
    const bars = [.45, .7, .55, .9, .65, .8], bw = w * .08;
    bars.forEach((v, i) => { c.fillStyle = i === 3 ? brand.primary : 'rgba(59,91,253,.35)'; const bh = (h * .6) * v; c.fillRect(x + w * .08 + i * bw * 1.6, y + h * .85 - bh, bw, bh); });
    c.strokeStyle = brand.primary; c.lineWidth = Math.max(1, h * .012); c.beginPath();
    for (let i = 0; i <= 6; i++) { const px = x + w * .08 + i * w * .14, py = y + h * (.5 - Math.sin(i * .9) * .12); i ? c.lineTo(px, py) : c.moveTo(px, py); } c.stroke();
  }
  function drawArt(c, e, brand) {
    if (e.art === 'sneaker') return drawSneaker(c, e, brand);
    if (e.art === 'screen') return drawScreen(c, e, brand);
    return drawCup(c, e, brand);
  }

  function drawCover(c, img, e) {
    const s = Math.max(e.width / img.naturalWidth, e.height / img.naturalHeight);
    const w = img.naturalWidth * s, h = img.naturalHeight * s;
    c.drawImage(img, e.x + (e.width - w) / 2, e.y + (e.height - h) / 2, w, h);
  }
  function drawContain(c, img, e, align) {
    const s = Math.min(e.width / img.naturalWidth, e.height / img.naturalHeight);
    const w = img.naturalWidth * s, h = img.naturalHeight * s;
    const x = align === 'center' ? e.x + (e.width - w) / 2 : align === 'right' ? e.x + e.width - w : e.x;
    c.drawImage(img, x, e.y + (e.height - h) / 2, w, h);
  }

  /**
   * Draw a design. opts: {assets, scale (css px per design px), dpr, radius}
   * Canvas is resized to design size × scale × dpr.
   */
  function draw(canvas, d, opts = {}) {
    const brand = Object.assign({}, DEFAULT_BRAND, d.brand || {}, opts.brand || {});
    const scale = opts.scale || 1, dpr = opts.dpr || 1;
    const W = d.canvas.width, H = d.canvas.height;
    let k = scale * dpr;
    const maxSide = opts.maxPixels || 4096;
    if (Math.max(W, H) * k > maxSide) k = maxSide / Math.max(W, H);
    canvas.width = Math.max(1, Math.round(W * k));
    canvas.height = Math.max(1, Math.round(H * k));
    if (opts.css !== false) { canvas.style.width = W * scale + 'px'; canvas.style.height = H * scale + 'px'; }
    const c = canvas.getContext('2d');
    c.setTransform(k, 0, 0, k, 0, 0);
    c.fillStyle = brand.background; c.fillRect(0, 0, W, H);
    const resolve = src => (src && src.startsWith('asset:') ? (opts.assets || {})[src.slice(6)] : src);
    const metrics = {};
    const order = [...d.elements].sort((a, b) => (a.type === 'image' ? 0 : 1) - (b.type === 'image' ? 0 : 1));
    for (const e of order) {
      if (e.hidden || e.width <= 0 || e.height <= 0) continue;
      c.save();
      c.beginPath(); c.rect(e.x - 1, e.y - 1, e.width + 2, e.height + 2); c.clip();
      const src = resolve(e.src), img = image(src);
      if (e.type === 'image') {
        if (img) { roundRect(c, e.x, e.y, e.width, e.height, Math.min(e.width, e.height) * .04); c.clip(); drawCover(c, img, e); }
        else drawArt(c, e, brand);
      } else if (e.type === 'decoration') {
        c.fillStyle = shade(brand.background, -.3);
        c.font = `${e.height * .8}px serif`; c.textBaseline = 'alphabetic'; c.fillText('✦', e.x, e.y + e.height * .8);
      } else if (e.type === 'logo' && src) {
        if (img) drawContain(c, img, e, e.align || 'left');
      } else if (e.type === 'button') {
        c.fillStyle = brand.primary;
        roundRect(c, e.x, e.y, e.width, e.height, e.height * .22); c.fill();
        metrics[e.id] = fitText(c, e, e.text || 'SHOP NOW', brand.font, onColor(brand.primary), 'center');
      } else {
        const text = e.text || (e.type === 'logo' ? 'LOGO' : '');
        metrics[e.id] = fitText(c, e, text, brand.font, e.genome && e.genome.role === 'legal' ? shade(brand.text, .25) : brand.text, e.align || 'left');
      }
      c.restore();
    }
    canvas._metrics = metrics;   // fitted font size per text element, in design px
    return canvas;
  }

  root.ChameleonRender = { draw, DEFAULT_BRAND, onColor, setImageListener: fn => { onImageLoad = fn; } };
})(window);
