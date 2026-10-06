"""Find the part of a photo that matters, so crops keep it.

Order of preference:
  1. a subject box given in the design (author knows best)
  2. faces, when OpenCV is installed (people are almost always the subject)
  3. saliency: colour contrast + spectral residual on a small copy, then the strongest region
  4. centre box fallback (flagged `assumed`)

Pillow is needed for 2–3; numpy makes 3 exact, and without it a gradient-energy map is used.
Only data: URIs are decoded (the server never opens paths or URLs from a design). Images over
40 megapixels are refused; everything else is analysed on a copy of at most 800 px. Results are
cached per image.
Returned boxes are image-relative, 0..1: [x, y, w, h].
"""
from __future__ import annotations

import base64
import io
import math
import hashlib
import warnings

CENTRE = [0.2, 0.2, 0.6, 0.6]


MAX_PIXELS = 40_000_000     # refuse decompression bombs before decoding
WORK_SIZE = 800             # analyse a copy no larger than this
_cache: dict[str, dict] = {}


def _open(src: str):
    """Decode a data: URI image into a small RGB copy. Local paths and URLs are never read."""
    try:
        from PIL import Image
    except ImportError:
        return None
    if not isinstance(src, str) or not src.startswith('data:') or ',' not in src:
        return None
    try:
        raw = base64.b64decode(src.split(',', 1)[1], validate=False)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            im = Image.open(io.BytesIO(raw))
        if im.size[0] * im.size[1] > MAX_PIXELS or min(im.size) < 1:
            return None
        im.draft('RGB', (WORK_SIZE, WORK_SIZE))   # JPEG: decode at reduced size directly
        im = im.convert('RGBA') if im.mode in ('P', 'LA', 'PA') else im
        if im.mode == 'RGBA':   # transparent areas count as white paper
            bg = Image.new('RGB', im.size, (255, 255, 255)); bg.paste(im, mask=im.split()[-1]); im = bg
        im = im.convert('RGB')
        im.thumbnail((WORK_SIZE, WORK_SIZE))
        return im
    except Exception:
        return None


def _faces(img):
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    try:
        grey = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2GRAY)
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        found = cascade.detectMultiScale(grey, 1.1, 5, minSize=(max(24, grey.shape[1] // 30),) * 2)
    except Exception:
        return None
    if len(found) == 0:
        return None
    W, H = img.size
    x0 = min(f[0] for f in found); y0 = min(f[1] for f in found)
    x1 = max(f[0] + f[2] for f in found); y1 = max(f[1] + f[3] for f in found)
    # faces sit in the top of a person: extend down and sideways a little
    fw, fh = x1 - x0, y1 - y0
    x0, x1 = max(0, x0 - fw * .35), min(W, x1 + fw * .35)
    y0, y1 = max(0, y0 - fh * .3), min(H, y1 + fh * 1.2)
    return [x0 / W, y0 / H, (x1 - x0) / W, (y1 - y0) / H]


def _rgb_to_lab(rgb):
    import numpy as np
    lin = np.where(rgb <= .04045, rgb / 12.92, ((rgb + .055) / 1.055) ** 2.4)
    m = np.array([[.4124, .3576, .1805], [.2126, .7152, .0722], [.0193, .1192, .9505]])
    xyz = lin @ m.T / np.array([.95047, 1.0, 1.08883])
    f = np.where(xyz > .008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def saliency_map(img, size: int = 96):
    """Return (grid, w, h): rows of floats in 0..1, larger = more salient.

    With numpy: average of two classic detectors, which fail differently —
      * frequency-tuned colour contrast (Achanta et al. 2009): how far each pixel's Lab colour is
        from the image's mean colour; finds objects that stand out from the background
      * spectral residual (Hou & Zhang 2007): finds unexpected structure
    Without numpy: gradient energy.
    """
    small = img.convert('RGB').resize((size, max(8, round(size * img.size[1] / img.size[0]))))
    w, h = small.size
    try:
        import numpy as np
    except ImportError:
        px = list(small.convert('L').getdata())
        grid = [[0.0] * w for _ in range(h)]
        for y in range(1, h - 1):
            for x in range(1, w - 1):
                gx = px[y * w + x + 1] - px[y * w + x - 1]
                gy = px[(y + 1) * w + x] - px[(y - 1) * w + x]
                grid[y][x] = math.hypot(gx, gy)
        top = max(max(r) for r in grid) or 1.0
        return [[v / top for v in r] for r in grid], w, h

    def blur(a, r):
        pad = np.pad(a, r, mode='edge')
        k = 2 * r + 1
        c = np.cumsum(np.cumsum(pad, 0), 1)
        c = np.pad(c, ((1, 0), (1, 0)))
        return (c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]) / (k * k)

    def norm(a):
        a = a - a.min()
        return a / a.max() if a.max() > 0 else a

    lab = _rgb_to_lab(np.asarray(small, dtype=float) / 255.0)
    if lab.reshape(-1, 3).std(0).max() < 1.5:     # flat image: nothing can stand out
        return [[0.0] * w for _ in range(h)], w, h
    lab_b = np.stack([blur(lab[..., i], 1) for i in range(3)], -1)
    # background colour = median of the outer ring (photos rarely put the subject on every edge);
    # better than the global mean, which a large subject drags towards itself
    ring = max(1, min(w, h) // 12)
    border = np.concatenate([lab_b[:ring].reshape(-1, 3), lab_b[-ring:].reshape(-1, 3),
                             lab_b[:, :ring].reshape(-1, 3), lab_b[:, -ring:].reshape(-1, 3)])
    # background palette = the colours on the photo's border (sky AND ground, wall AND floor);
    # a pixel is salient when it is far from every one of them
    palette = np.unique(np.round(border / 6) * 6, axis=0)
    if len(palette) > 256:
        palette = palette[np.linspace(0, len(palette) - 1, 256).astype(int)]
    px = lab_b.reshape(-1, 1, 3)
    d = np.sqrt(((px - palette.reshape(1, -1, 3)) ** 2).sum(-1))
    ft = np.sort(d, axis=1)[:, :3].mean(1).reshape(h, w) if d.shape[1] >= 3 else d.min(1).reshape(h, w)

    grey = np.asarray(small.convert('L'), dtype=float) / 255.0
    f = np.fft.fft2(grey)
    log_amp = np.log(np.abs(f) + 1e-8)
    sr = np.abs(np.fft.ifft2(np.exp(log_amp - blur(log_amp, 1) + 1j * np.angle(f)))) ** 2
    sr = blur(sr, 2)
    sal = norm(.6 * norm(ft) + .4 * norm(sr))
    return sal.tolist(), w, h


def _otsu(vals, bins: int = 64) -> float:
    """Threshold that best separates salient from non-salient values."""
    top = max(vals) or 1.0
    hist = [0] * bins
    for v in vals:
        hist[min(bins - 1, int(v / top * bins))] += 1
    total, sum_all = len(vals), sum(i * c for i, c in enumerate(hist))
    best, best_t, w0, s0 = -1.0, 0, 0, 0.0
    for i, c in enumerate(hist):
        w0 += c; s0 += i * c
        if w0 == 0 or w0 == total: continue
        m0, m1 = s0 / w0, (sum_all - s0) / (total - w0)
        between = w0 * (total - w0) * (m0 - m1) ** 2
        if between > best: best, best_t = between, i
    return (best_t + 1) / bins * top


def box_from_map(grid, w, h):
    """Box around the strongest salient region, plus a confidence for how concentrated it is."""
    vals = [v for row in grid for v in row]
    total = sum(vals) or 1.0
    mean = total / len(vals)
    sd = (sum((v - mean) ** 2 for v in vals) / len(vals)) ** .5
    if sd < .02 or max(vals) <= 0:      # flat image: nothing stands out
        return list(CENTRE), 0.0
    thr = max(_otsu(vals), max(vals) * .25)
    hot = {(x, y) for y in range(h) for x in range(w) if grid[y][x] >= thr}
    if not hot:
        return list(CENTRE), 0.0
    # connected components (4-neighbour); keep the one with the most salience
    seen, comps = set(), []
    for start in sorted(hot):
        if start in seen: continue
        comp, stack = [], [start]
        seen.add(start)
        while stack:
            x, y = stack.pop(); comp.append((x, y))
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if (nx, ny) in hot and (nx, ny) not in seen:
                    seen.add((nx, ny)); stack.append((nx, ny))
        comps.append((sum(grid[y][x] for x, y in comp), comp))
    comps.sort(key=lambda c: -c[0])
    best_mass, best = comps[0]
    xs = [x for x, _ in best]; ys = [y for _, y in best]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    # merge strong neighbours into the subject (a face above a shirt, a product and its label)
    near_x, near_y = max(2, w * .08), max(2, h * .08)
    changed = True
    while changed:
        changed = False
        best_mean = best_mass / len(best)
        for mass, comp in comps[1:]:
            strong = mass >= best_mass * .5          # an equally important second object, anywhere
            if not strong and (mass < best_mass * .03 or mass / len(comp) < best_mean * .5): continue
            cx0 = min(x for x, _ in comp); cx1 = max(x for x, _ in comp)
            cy0 = min(y for _, y in comp); cy1 = max(y for _, y in comp)
            if cx0 >= x0 and cx1 <= x1 and cy0 >= y0 and cy1 <= y1: continue
            gap_x = max(0, cx0 - x1, x0 - cx1); gap_y = max(0, cy0 - y1, y0 - cy1)
            if strong or (gap_x <= near_x and gap_y <= near_y):
                x0, x1, y0, y1 = min(x0, cx0), max(x1, cx1), min(y0, cy0), max(y1, cy1)
                changed = True
    pad_x, pad_y = max(1, round((x1 - x0 + 1) * .12)), max(1, round((y1 - y0 + 1) * .12))
    x0, x1 = max(0, x0 - pad_x), min(w - 1, x1 + pad_x)
    y0, y1 = max(0, y0 - pad_y), min(h - 1, y1 + pad_y)
    inside = sum(grid[y][x] for y in range(y0, y1 + 1) for x in range(x0, x1 + 1))
    area = (x1 - x0 + 1) * (y1 - y0 + 1) / (w * h)
    concentration = (inside / total) / max(area, .02)   # 1 = no better than random, higher = focused
    conf = max(0.0, min(1.0, (concentration - 1) / 3))
    return [x0 / w, y0 / h, (x1 - x0 + 1) / w, (y1 - y0 + 1) / h], round(conf, 3)


def find_subject(node) -> dict:
    if node.subject is not None:
        return {'box': node.subject.list(), 'source': 'given', 'confidence': 1.0}
    if not node.src:
        return {'box': CENTRE, 'source': 'assumed', 'confidence': 0.0}
    key = hashlib.sha1(node.src.encode('utf-8', 'ignore')).hexdigest()
    if key in _cache:
        return dict(_cache[key])
    out = _detect(node.src)
    if len(_cache) > 128:
        _cache.pop(next(iter(_cache)))
    _cache[key] = out
    return dict(out)


def _detect(src: str) -> dict:
    img = _open(src)
    if img is None:
        return {'box': CENTRE, 'source': 'assumed', 'confidence': 0.0}
    face = _faces(img)
    if face:
        return {'box': [round(v, 4) for v in face], 'source': 'faces', 'confidence': 0.9}
    grid, w, h = saliency_map(img)
    box, conf = box_from_map(grid, w, h)
    if conf < .1:   # nothing clearly stands out: keep the centre rather than a random patch
        return {'box': CENTRE, 'source': 'assumed', 'confidence': conf}
    return {'box': [round(v, 4) for v in box], 'source': 'saliency', 'confidence': conf}
