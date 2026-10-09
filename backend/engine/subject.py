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
        if max(im.size) < WORK_SIZE:   # small uploads: enlarge to the working size so results don't depend on it
            k = WORK_SIZE / max(im.size)
            im = im.resize((max(1, round(im.size[0] * k)), max(1, round(im.size[1] * k))), Image.LANCZOS)
        return im
    except Exception:
        return None


_models: dict = {}


def _model(kind: str):
    """OpenCV detectors are loaded once per process (loading the XML each time cost ~0.3 s per photo)."""
    if kind not in _models:
        import cv2
        if kind == 'people':
            m = cv2.HOGDescriptor()
            m.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        else:
            name = {'face': 'haarcascade_frontalface_default.xml', 'eye': 'haarcascade_eye.xml'}[kind]
            m = cv2.CascadeClassifier(cv2.data.haarcascades + name)
        _models[kind] = m
    return _models[kind]


def _looks_like_skin(img, face, need: float = .3) -> bool:
    """A real face has a decent share of skin-coloured pixels (YCrCb range works across skin tones)."""
    import numpy as np
    x, y, w, h = (int(v) for v in face)
    core = img.crop((x + w // 5, y + h // 5, x + w - w // 5, y + h - h // 5)).convert('YCbCr')
    a = np.asarray(core, dtype=int)
    if a.size == 0:
        return False
    cb, cr = a[..., 1], a[..., 2]
    skin = (cr >= 133) & (cr <= 180) & (cb >= 75) & (cb <= 130)
    return skin.mean() >= need


def _is_monochrome(img) -> bool:
    """Greyscale, sepia-free duotone or tinted photos: chroma barely varies across the image."""
    import numpy as np
    a = np.asarray(img.convert('YCbCr').resize((64, 64)), dtype=float)
    return a[..., 1].std() < 4 and a[..., 2].std() < 4


def _faces(img, omap=None):
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    if not hasattr(cv2, 'CascadeClassifier'):   # OpenCV 5 dropped it; requirements pin 4.x
        return None
    try:
        grey = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2GRAY)
        cascade = _model('face')
        side = max(24, min(grey.shape) // 20)          # ignore "faces" smaller than 5% of the photo
        found = cascade.detectMultiScale(grey, 1.1, 6, minSize=(side, side))
    except Exception:
        return None
    if _is_monochrome(img):
        # black-and-white / duotone: skin colour can't be judged, so demand much stronger Haar evidence
        found = cascade.detectMultiScale(grey, 1.1, 10, minSize=(side, side))
    else:
        found = [f for f in found if _looks_like_skin(img, f)]   # Haar alone fires on grass, rocks, fabric
    # and a face must show at least one eye in its upper half: ice cubes in a caramel latte pass the
    # face and skin tests, but have no eyes (Pari's round-3 false positive)
    eyes = _model('eye')
    def has_eye(f):
        x, y, w, h = (int(v) for v in f)
        roi = grey[y:y + int(h * .6), x:x + w]
        return len(eyes.detectMultiScale(roi, 1.1, 3, minSize=(max(8, w // 10),) * 2)) >= 1
    # faces too small for reliable eye detection must instead survive a much stricter face pass
    strict = cascade.detectMultiScale(grey, 1.1, 9, minSize=(side, side))
    def strong(f):
        return any(_iou([*f], [*s]) >= .5 for s in strict)
    def on_subject(f, need=.35):   # a real face is part of a person the object model sees as a subject
        if omap is None:
            return True
        x, y, w, h = (int(v) for v in f)
        return float(omap[y:y + h, x:x + w].mean()) >= need
    found = [f for f in found if on_subject(f) and (has_eye(f) or (f[2] < 60 and strong(f)))]
    if len(found):
        # faces under half the main face's size are usually blurred background people; keep them only
        # when both eyes are clearly visible (the third friend walking behind is sharp, a stranger isn't)
        biggest = max(f[2] for f in found)
        def eyes_n(f):
            x, y, w, h = (int(v) for v in f)
            return len(eyes.detectMultiScale(grey[y:y + int(h * .6), x:x + w], 1.1, 3, minSize=(max(8, w // 10),) * 2))
        # (when the object model confirms the face sits on a salient person, one eye is enough: small, slightly
        # soft faces of people walking behind lose the second eye at lower resolutions)
        found = [f for f in found if f[2] >= biggest * .5
                 or (f[2] >= biggest * .3 and (eyes_n(f) >= 2 or (omap is not None and on_subject(f, .6) and eyes_n(f) >= 1)))]
    if len(found) == 0:
        return None
    W, H = img.size
    # each face gets its own box: the detected face plus modest padding for hair and chin, the way
    # face-aware croppers frame a face (focus on the head, not the torso). The union is only used to
    # describe "everyone"; crops and markers use the separate faces.
    boxes = []
    for fx, fy, fw, fh in sorted(found, key=lambda f: f[0]):        # numbered left to right
        boxes.append((max(0, fx - fw * .25), max(0, fy - fh * .3), min(W, fx + fw * 1.25), min(H, fy + fh * 1.3)))
    parts = [[float(b[0] / W), float(b[1] / H), float((b[2] - b[0]) / W), float((b[3] - b[1]) / H)] for b in boxes]
    x0 = min(b[0] for b in boxes); y0 = min(b[1] for b in boxes)
    x1 = max(b[2] for b in boxes); y1 = max(b[3] for b in boxes)
    return [float(x0 / W), float(y0 / H), float((x1 - x0) / W), float((y1 - y0) / H)], parts


def _people(img, min_score: float = 1.3) -> list:
    """Full-body people (OpenCV HOG). The image is enlarged so small figures reach the 64x128 window."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return []
    if not hasattr(cv2, 'HOGDescriptor'):
        return []
    W, H = img.size
    s = 1800 / max(W, H)
    grey = cv2.cvtColor(np.asarray(img.resize((int(W * s), int(H * s)))), cv2.COLOR_RGB2GRAY)
    hog = _model('people')
    try:
        rects, weights = hog.detectMultiScale(grey, winStride=(8, 8), padding=(8, 8), scale=1.05)
    except Exception:
        return []
    out = []
    for (x, y, w, h), q in zip(rects, np.ravel(weights)):
        if q >= min_score:
            out.append([float(x / s / W), float(y / s / H), float(w / s / W), float(h / s / H)])
    return out


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
    px = lab_b.reshape(-1, 3)
    # squared distances via |p|^2 + |q|^2 - 2 p.q (one matrix multiply instead of a big broadcast)
    d = np.maximum((px ** 2).sum(1)[:, None] + (palette ** 2).sum(1)[None, :] - 2 * px @ palette.T, 0)
    k = min(3, d.shape[1])
    ft = np.sqrt(np.partition(d, k - 1, axis=1)[:, :k]).mean(1).reshape(h, w)

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
            # an equally important second object, anywhere: as much salience AND as intense
            strong = mass >= best_mass * .5 and mass / len(comp) >= best_mean * .75
            if not strong and (mass < best_mass * .03 or mass / len(comp) < best_mean * .5): continue
            cx0 = min(x for x, _ in comp); cx1 = max(x for x, _ in comp)
            cy0 = min(y for _, y in comp); cy1 = max(y for _, y in comp)
            if cx0 >= x0 and cx1 <= x1 and cy0 >= y0 and cy1 <= y1: continue
            gap_x = max(0, cx0 - x1, x0 - cx1); gap_y = max(0, cy0 - y1, y0 - cy1)
            if strong or (gap_x <= near_x and gap_y <= near_y):
                x0, x1, y0, y1 = min(x0, cx0), max(x1, cx1), min(y0, cy0), max(y1, cy1)
                changed = True
    # hysteresis: grow into weaker but connected salience (a white toe cap, a pale sleeve)
    low = thr * .5
    frontier = [(x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1) if (x, y) in hot]
    grown = set(frontier)
    while frontier:
        x, y = frontier.pop()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in grown and grid[ny][nx] >= low:
                grown.add((nx, ny)); frontier.append((nx, ny))
    gx0, gx1 = min(x0, min(x for x, _ in grown)), max(x1, max(x for x, _ in grown))
    gy0, gy1 = min(y0, min(y for _, y in grown)), max(y1, max(y for _, y in grown))
    if (gx1 - gx0 + 1) * (gy1 - gy0 + 1) <= 1.8 * (x1 - x0 + 1) * (y1 - y0 + 1):   # extend, don't flood a busy scene
        x0, x1, y0, y1 = gx0, gx1, gy0, gy1
    pad_x, pad_y = max(1, round((x1 - x0 + 1) * .12)), max(1, round((y1 - y0 + 1) * .12))
    x0, x1 = max(0, x0 - pad_x), min(w - 1, x1 + pad_x)
    y0, y1 = max(0, y0 - pad_y), min(h - 1, y1 + pad_y)
    inside = sum(grid[y][x] for y in range(y0, y1 + 1) for x in range(x0, x1 + 1))
    area = (x1 - x0 + 1) * (y1 - y0 + 1) / (w * h)
    concentration = (inside / total) / max(area, .02)   # 1 = no better than random, higher = focused
    n_in = (x1 - x0 + 1) * (y1 - y0 + 1)
    mean_in = inside / n_in
    mean_out = (total - inside) / max(1, w * h - n_in)
    separation = mean_in / (mean_out + 1e-6)              # big subjects: inside clearly brighter than outside
    conf = max(0.0, min(1.0, max((concentration - 1) / 3, (separation - 2) / 6 if area > .25 else 0.0)))
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


MODEL_PATH = __import__('pathlib').Path(__file__).resolve().parent / 'models' / 'u2netp.onnx'


def _u2net():
    """Salient-object model (U²-Net-P, Apache-2.0), loaded once. None if onnxruntime or the file is missing."""
    if 'u2net' not in _models:
        try:
            import onnxruntime as ort
            opts = ort.SessionOptions()
            opts.log_severity_level = 3
            _models['u2net'] = ort.InferenceSession(str(MODEL_PATH), opts, providers=['CPUExecutionProvider'])
        except Exception:
            _models['u2net'] = None
    return _models['u2net']


def object_map(img):
    """Per-pixel 'this is the main object' probability (0..1), same size as `img`.

    Very wide or tall photos are scanned in overlapping square tiles: squashing a 3:1 panorama into the
    model's 320x320 input makes small subjects (a distant sailboat) vanish."""
    import numpy as np
    from PIL import Image
    sess = _u2net()
    if sess is None:
        return None
    name = sess.get_inputs()[0].name
    mean, std = np.array([.485, .456, .406]), np.array([.229, .224, .225])

    def run(tile):
        x = np.asarray(tile.resize((320, 320), Image.BILINEAR), dtype=np.float32) / 255.0
        x = ((x - mean) / std).transpose(2, 0, 1)[None].astype(np.float32)
        out = sess.run(None, {name: x})[0][0, 0]
        return np.asarray(Image.fromarray(out.astype(np.float32)).resize(tile.size, Image.BILINEAR))

    W, H = img.size
    if max(W, H) / min(W, H) <= 1.6:
        m = run(img)
    else:
        side = min(W, H)
        n = int(np.ceil(max(W, H) / side * .999)) + 1
        m = np.zeros((H, W), dtype=np.float32)
        for i in range(n):
            off = int(round(i * (max(W, H) - side) / (n - 1)))
            box = (off, 0, off + side, H) if W > H else (0, off, W, off + side)
            t = run(img.crop(box))
            if W > H:
                m[:, off:off + side] = np.maximum(m[:, off:off + side], t)
            else:
                m[off:off + side, :] = np.maximum(m[off:off + side, :], t)
    return np.clip(m, 0.0, 1.0)


def objects_from_map(m):
    """Main object(s) from the model's map: (box, parts, confidence) or None.

    Separate objects that are about as strong as the best one are all kept (a breakfast flat-lay:
    bowl, cup and croissant); weak blobs (a rock in the corner of a seascape) are not."""
    import numpy as np
    import cv2
    H, W = m.shape
    if m.max() < .5:
        return None
    mask = (m >= .5).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    comps = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < W * H * .0008:
            continue
        vals = m[lab == i]
        comps.append({'box': [x / W, y / H, w / W, h / H], 'area': area / (W * H),
                      'mean': float(vals.mean()), 'peak': float(vals.max()), 'mass': float(vals.sum())})
    if not comps:
        return None
    comps.sort(key=lambda c: -c['mass'])
    best = comps[0]
    if best['peak'] < .8 or best['mean'] < .6:
        return None
    keep = [c for c in comps if c['mass'] >= best['mass'] * .2 and c['mean'] >= best['mean'] * .9]
    def near(a, b, gap=.04):
        ax, ay, aw, ah = a['box']; bx, by, bw, bh = b['box']
        return max(0, bx - (ax + aw), ax - (bx + bw)) <= gap and max(0, by - (ay + ah), ay - (by + bh)) <= gap
    for c in comps:   # small but equally strong objects touching a kept one belong to the scene's subject (boat by a cliff)
        if c not in keep and c['mean'] >= best['mean'] * .9 and any(near(c, k) for k in keep):
            keep.append(c)
    for c in comps:   # a second, equally crisp upright object far from the first (two hikers at either side of a
        # ridge) is part of the scene's subject too, even though it is much smaller
        x, y, w, h = c['box']
        if (c not in keep and c['mean'] >= best['mean'] and c['peak'] >= .97 and c['mass'] >= best['mass'] * .1
                and h * H >= w * W * 1.5 and c['area'] >= .01):
            keep.append(c)
    for c in comps:   # a small, crisp, compact object (a sailboat on open water) is a subject even beside a big one
        x, y, w, h = c['box']
        # only in panoramas (where tiling makes a big neighbour dominate) and only upright shapes, so wide
        # strips of cloud or horizon never qualify
        panorama = max(W, H) / min(W, H) > 1.6
        upright = h * H >= w * W
        compact = c['area'] / max(w * h, 1e-6) >= .35 and h * H / (w * W) <= 6
        if panorama and upright and c not in keep and c['mean'] >= .85 and c['peak'] >= .97 and compact and c['area'] <= .02:
            keep.append(c)
    def pad(b, k=.06):
        x, y, w, h = b
        x0, y0 = max(0.0, x - w * k), max(0.0, y - h * k)
        x1, y1 = min(1.0, x + w * (1 + k)), min(1.0, y + h * (1 + k))
        return [x0, y0, x1 - x0, y1 - y0]
    parts = [pad(c['box']) for c in sorted(keep, key=lambda c: c['box'][0])]
    x0 = min(p[0] for p in parts); y0 = min(p[1] for p in parts)
    x1 = max(p[0] + p[2] for p in parts); y1 = max(p[1] + p[3] for p in parts)
    covered = sum(c['area'] for c in keep)
    if (x1 - x0) * (y1 - y0) > .8 and covered > .5:
        return None   # the whole photo lights up: a texture or a frame-filling object, no single subject to crop around
    conf = round(min(1.0, best['mean']) * (0.5 if covered > .6 else 1.0), 3)
    return [x0, y0, x1 - x0, y1 - y0], parts, conf


def _accept_people(people, m):
    """Drop person boxes cut off by the photo edge (not a full body) or sitting on a known object
    that isn't person-shaped (the HOG detector fired on a dog's legs)."""
    out = []
    for p in people:
        x, y, w, h = p
        if x <= .01 or y <= .01 or x + w >= .99 or y + h >= .99:
            continue
        out.append(p)
    return out


def _detect(src: str) -> dict:
    img = _open(src)
    if img is None:
        return {'box': CENTRE, 'source': 'assumed', 'confidence': 0.0}
    aspect = round(img.size[0] / img.size[1], 4)
    omap = object_map(img)            # also used to confirm faces
    face = _faces(img, omap)
    if face:
        box, parts = face
        return {'box': [round(v, 4) for v in box], 'source': 'faces', 'confidence': 0.9, 'aspect': aspect,
                'parts': [[round(v, 4) for v in p] for p in parts]}
    # 2. the salient-object model (the standard approach in modern cut-out / smart-crop tools)
    if omap is not None:
        found = objects_from_map(omap)
        if found:
            box, parts, conf = found
            out = {'box': [round(v, 4) for v in box], 'source': 'objects', 'confidence': conf, 'aspect': aspect}
            if len(parts) > 1:
                out['parts'] = [[round(v, 4) for v in p] for p in parts]
            return out
        # 3. nothing stands out as an object: maybe a small person in a big scene
        people = _accept_people(_people(img), omap)
        if people:
            x0 = min(p[0] for p in people); y0 = min(p[1] for p in people)
            x1 = max(p[0] + p[2] for p in people); y1 = max(p[1] + p[3] for p in people)
            return {'box': [round(x0, 4), round(y0, 4), round(x1 - x0, 4), round(y1 - y0, 4)], 'source': 'people',
                    'confidence': 0.7, 'aspect': aspect, 'parts': [[round(v, 4) for v in p] for p in people]}
        return {'box': CENTRE, 'source': 'assumed', 'confidence': 0.0, 'aspect': aspect}
    # fallback without the model: classical colour-contrast saliency
    # two scales: the coarse map keeps big subjects whole, the fine one finds small ones
    # (a runner on a wide road is ~1 px at 96 px). Keep whichever is more confident.
    found = []
    for size in (96, 160):
        grid, w, h = saliency_map(img, size)
        found.append(box_from_map(grid, w, h))
    (b1, c1), (b2, c2) = found
    if _iou(b1, b2) >= .4:      # both scales see the same thing: union keeps every part of it
        x0, y0 = min(b1[0], b2[0]), min(b1[1], b2[1])
        x1, y1 = max(b1[0] + b1[2], b2[0] + b2[2]), max(b1[1] + b1[3], b2[1] + b2[3])
        box, conf = [x0, y0, x1 - x0, y1 - y0], max(c1, c2)
    else:                        # they disagree: trust the more confident one
        box, conf = (b2, c2) if c2 > c1 + .05 else (b1, c1)
    bx, by, bw, bh = box
    if (bh > .95 and bw < .15) or (bw > .95 and bh < .15):
        conf = 0.0   # a thin strip along a whole edge is a gradient or a border, not a subject
    if bw * bh > .8:
        conf = 0.0   # "the whole photo" is texture (grass, fabric) or a frame-filling object: no single subject to crop around
    if conf < .5:
        # colour saliency is unsure (a small person in a big scene matches the scene's colours):
        # try the full-body person detector. Only here: on clear product shots it misfires (a sneaker heel).
        people = _people(img)
        if people:
            x0 = min(p[0] for p in people); y0 = min(p[1] for p in people)
            x1 = max(p[0] + p[2] for p in people); y1 = max(p[1] + p[3] for p in people)
            return {'box': [round(x0, 4), round(y0, 4), round(x1 - x0, 4), round(y1 - y0, 4)], 'source': 'people',
                    'confidence': 0.7, 'aspect': aspect, 'parts': [[round(v, 4) for v in p] for p in people]}
    if conf < .1:   # nothing clearly stands out: keep the centre rather than a random patch
        return {'box': CENTRE, 'source': 'assumed', 'confidence': conf, 'aspect': aspect}
    return {'box': [round(v, 4) for v in box], 'source': 'saliency', 'confidence': conf, 'aspect': aspect}


def reframe(subject: list, image_aspect: float, slot_aspect: float, parts: list | None, avoid: list) -> dict:
    """Like smart_crop, but also keeps the subject out from under `avoid` (copy laid over the photo).

    `avoid` boxes are slot-relative [x, y, w, h] in 0-1. The window may zoom in (down to 62% of the
    largest window) and move on both axes, as a designer would reframe a photo behind text. The subject
    is never cut more than smart_crop would cut it. Returns {crop, kept, under}: `under` is the share of
    the subject still under the copy."""
    base = smart_crop(subject, image_aspect, slot_aspect, parts)
    parts = parts or [subject]
    if not avoid or not (image_aspect > 0 and slot_aspect > 0):
        return {**base, 'under': 0.0}
    tot = sum(p[2] * p[3] for p in parts) or 1.0

    def measure(c):
        cx, cy, cw, ch = c
        kept = under = 0.0
        for px, py, pw, ph in parts:
            ix0, iy0 = max(px, cx), max(py, cy)
            ix1, iy1 = min(px + pw, cx + cw), min(py + ph, cy + ch)
            if ix1 <= ix0 or iy1 <= iy0:
                continue
            kept += (ix1 - ix0) * (iy1 - iy0)
            # the visible part, in slot coordinates
            q = ((ix0 - cx) / cw, (iy0 - cy) / ch, (ix1 - ix0) / cw, (iy1 - iy0) / ch)
            for ax, ay, aw, ah in avoid:
                ox = max(0.0, min(q[0] + q[2], ax + aw) - max(q[0], ax))
                oy = max(0.0, min(q[1] + q[3], ay + ah) - max(q[1], ay))
                under += ox * oy * cw * ch          # back to image units
        return kept / tot, min(1.0, under / tot)
    k0, u0 = measure(base['crop'])
    best = (u0, 0, 0.0, base['crop'], k0)
    if u0 < .02:
        return {**base, 'under': round(u0, 3)}
    bw, bh = base['crop'][2], base['crop'][3]
    for zi, z in enumerate((1.0, .92, .85, .78, .7, .62)):
        cw, ch = bw * z, bh * z
        for i in range(21):
            for j in range(21):
                cx, cy = (1 - cw) * i / 20, (1 - ch) * j / 20
                k, u = measure((cx, cy, cw, ch))
                if k < min(.98, k0) - 1e-6:
                    continue
                d = abs(cx - base['crop'][0]) + abs(cy - base['crop'][1])
                key = (round(u, 2), zi, d)
                if key < best[:3]:
                    best = (round(u, 2), zi, d, [round(cx, 4), round(cy, 4), round(cw, 4), round(ch, 4)], k)
    return {'crop': best[3], 'kept': round(best[4], 3), 'under': round(measure(best[3])[1], 3)}


def _iou(a, b) -> float:
    ix = max(0.0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])) * max(0.0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    u = a[2] * a[3] + b[2] * b[3] - ix
    return ix / u if u > 0 else 0.0


def smart_crop(subject: list, image_aspect: float, slot_aspect: float, parts: list | None = None) -> dict:
    """The part of the photo to show in a slot of another shape: as large as possible (cover fit),
    slid along the free axis to keep as much of the subject as it can, never past the photo's edges.

    `parts` are separate subjects (e.g. each person's face). If they don't all fit, the window keeps
    the most of them it can (by area) instead of centring on the empty space between them.
    Returns image-relative `crop` [x, y, w, h] and `kept`, the share of the subject(s) inside it."""
    parts = parts or [subject]
    if not (image_aspect > 0 and slot_aspect > 0) or not all(map(math.isfinite, (image_aspect, slot_aspect))):
        return {'crop': [0.0, 0.0, 1.0, 1.0], 'kept': 1.0}      # zero-size image or slot: nothing to crop
    wide = image_aspect > slot_aspect
    if wide:
        cw, ch = slot_aspect / image_aspect, 1.0
    else:
        cw, ch = 1.0, image_aspect / slot_aspect
    size = cw if wide else ch
    def covered(pos):
        cx, cy = (pos, 0.0) if wide else (0.0, pos)
        tot = got = 0.0
        for px, py, pw, ph in parts:
            a = pw * ph
            ix = max(0.0, min(px + pw, cx + cw) - max(px, cx)) * max(0.0, min(py + ph, cy + ch) - max(py, cy))
            tot += a; got += ix
        return got / tot if tot > 0 else 1.0
    def sliced(pos):
        """How much of the subject is cut through by the window edge (a face sliced in half looks broken)."""
        cx, cy = (pos, 0.0) if wide else (0.0, pos)
        tot = bad = 0.0
        for px, py, pw, ph in parts:
            a = pw * ph
            ix = max(0.0, min(px + pw, cx + cw) - max(px, cx)) * max(0.0, min(py + ph, cy + ch) - max(py, cy))
            f = ix / a if a > 0 else 1.0
            tot += a
            if .05 < f < .95:
                bad += a * min(f, 1 - f)
        return bad / tot if tot > 0 else 0.0
    sx, sy, sw, sh = subject
    centre = (sx + sw / 2 if wide else sy + sh / 2) - size / 2
    best = min(max(centre, 0.0), 1.0 - size)
    best_kept = covered(best)
    if best_kept < .999:          # not everything fits: keep the most, without slicing through a face or object
        steps = 60
        best_val = best_kept - sliced(best)
        for i in range(steps + 1):
            pos = (1.0 - size) * i / steps
            k = covered(pos)
            v = k - sliced(pos)
            if v > best_val + 1e-6 or (abs(v - best_val) <= 1e-6 and abs(pos - centre) < abs(best - centre)):
                best, best_kept, best_val = pos, k, v
    cx, cy = (best, 0.0) if wide else (0.0, best)
    return {'crop': [round(cx, 4), round(cy, 4), round(cw, 4), round(ch, 4)], 'kept': round(best_kept, 3)}