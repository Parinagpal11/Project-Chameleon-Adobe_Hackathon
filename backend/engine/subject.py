"""Find the part of a photo that matters, so crops keep it.

Order of preference:
  1. a subject box given in the design (author knows best)
  2. faces, when OpenCV is installed (people are almost always the subject)
  3. spectral-residual saliency (Hou & Zhang, 2007) on a small greyscale copy
  4. centre box fallback (flagged `assumed`)

Pillow is needed for 2–3; numpy makes 3 exact, and without it a gradient-energy map is used.
Returned boxes are image-relative, 0..1: [x, y, w, h].
"""
from __future__ import annotations

import base64
import io
import math
from pathlib import Path

CENTRE = [0.2, 0.2, 0.6, 0.6]


def _open(src: str):
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        if src.startswith('data:'):
            raw = base64.b64decode(src.split(',', 1)[1])
            return Image.open(io.BytesIO(raw)).convert('RGB')
        p = Path(src)
        if p.is_file():
            return Image.open(p).convert('RGB')
    except Exception:
        return None
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


def saliency_map(img, size: int = 64):
    """Return (grid, w, h): a list of rows of floats, larger = more salient."""
    small = img.convert('L').resize((size, max(8, round(size * img.size[1] / img.size[0]))))
    w, h = small.size
    try:
        import numpy as np
        a = np.asarray(small, dtype=float) / 255.0
        f = np.fft.fft2(a)
        log_amp = np.log(np.abs(f) + 1e-8)
        phase = np.angle(f)
        k = np.ones((3, 3)) / 9.0
        pad = np.pad(log_amp, 1, mode='edge')
        avg = sum(pad[i:i + h, j:j + w] * k[i, j] for i in range(3) for j in range(3))
        sal = np.abs(np.fft.ifft2(np.exp(log_amp - avg + 1j * phase))) ** 2
        pad = np.pad(sal, 2, mode='edge')   # smooth
        sal = sum(pad[i:i + h, j:j + w] for i in range(5) for j in range(5)) / 25.0
        return sal.tolist(), w, h
    except ImportError:
        px = list(small.getdata())
        grid = [[0.0] * w for _ in range(h)]
        for y in range(1, h - 1):
            for x in range(1, w - 1):
                gx = px[y * w + x + 1] - px[y * w + x - 1]
                gy = px[(y + 1) * w + x] - px[(y - 1) * w + x]
                grid[y][x] = math.hypot(gx, gy)
        return grid, w, h


def box_from_map(grid, w, h, keep: float = 0.6):
    """Smallest box (by centre-out search on cumulative mass) holding `keep` of the salience."""
    cx_w, cy_w = (w - 1) / 2, (h - 1) / 2
    vals = []
    for y in range(h):
        for x in range(w):
            bias = 1.0 - 0.35 * (((x - cx_w) / w) ** 2 + ((y - cy_w) / h) ** 2) * 4   # mild centre prior
            vals.append(grid[y][x] * max(bias, 0.2))
    total = sum(vals) or 1.0
    # centre of mass
    mx = sum((i % w) * v for i, v in enumerate(vals)) / total
    my = sum((i // w) * v for i, v in enumerate(vals)) / total
    # grow a box around the centre of mass until it holds `keep` of the mass
    rx, ry = 1, 1
    while True:
        x0, x1 = max(0, int(mx - rx)), min(w - 1, int(mx + rx))
        y0, y1 = max(0, int(my - ry)), min(h - 1, int(my + ry))
        mass = sum(vals[y * w + x] for y in range(y0, y1 + 1) for x in range(x0, x1 + 1))
        if mass / total >= keep or (x0 == 0 and x1 == w - 1 and y0 == 0 and y1 == h - 1):
            break
        rx += max(1, w // 32); ry += max(1, h // 32)
    peak = max(vals) / (total / len(vals))
    conf = max(0.0, min(1.0, (peak - 1) / 12))
    return [x0 / w, y0 / h, (x1 - x0 + 1) / w, (y1 - y0 + 1) / h], round(conf, 3)


def find_subject(node) -> dict:
    if node.subject is not None:
        return {'box': node.subject.list(), 'source': 'given', 'confidence': 1.0}
    img = _open(node.src) if node.src else None
    if img is None:
        return {'box': CENTRE, 'source': 'assumed', 'confidence': 0.0}
    face = _faces(img)
    if face:
        return {'box': [round(v, 4) for v in face], 'source': 'faces', 'confidence': 0.9}
    grid, w, h = saliency_map(img)
    box, conf = box_from_map(grid, w, h)
    return {'box': [round(v, 4) for v in box], 'source': 'saliency', 'confidence': conf}
