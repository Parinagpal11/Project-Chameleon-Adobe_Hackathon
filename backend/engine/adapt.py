"""Solve stage: lay a design out again at a new canvas size.

adapt(design, targets) -> {'results': [...]} with, per target:
  design    the adapted design (same node ids, new boxes and font sizes, photo crops, dropped nodes hidden)
  tier      plan tier (1 same family, 2 new orientation, 3 extreme)
  reasons   what was done, in plain English
  checks    overlap / off-canvas / text under 12 px / subject kept
  baselines what plain stretching and centre-cropping would have done (for comparison)

How it works (deterministic, block based):
  1. Understand the original (understand.analyze): photos, groups, blocks, anchors, subjects.
  2. Split the new canvas into regions: a photo region (side by side or stacked, matching the new shape),
     a copy region, and anchored corners for the logo and badges. Full-bleed photos stay full-bleed.
  3. Flow the copy region: blocks keep their internal order and alignment; text re-wraps at the new width.
     Wide, short canvases flow in a row instead of a column.
  4. Fit: shrink type step by step (never under 12 px), then drop the least important pieces
     (decoration, legal, body, eyebrow...) and say so.
  5. Crop every photo around its subject (subject.smart_crop).
"""
from __future__ import annotations

import copy
import math

from .graph import Box, load
from .plan import plan_tier
from .subject import smart_crop
from .understand import analyze

MIN_TEXT = 12.0
DROP_ORDER = ['decoration', 'legal', 'caption', 'body', 'item', 'price', 'eyebrow', 'badge', 'repeat', 'subhead', 'offer']
CHAR_W = {'Inter': .56, 'Poppins': .6, 'Playfair Display': .52, 'Space Grotesk': .57, 'Montserrat': .62,
          'DM Serif Display': .5}


# ---------------------------------------------------------------- text measurement

def char_w(style: dict) -> float:
    w = CHAR_W.get(style.get('fontFamily', 'Inter'), .56)
    w *= 1 + (int(style.get('fontWeight') or 400) - 400) / 2500
    return w


def text_lines(text: str, fs: float, width: float, style: dict) -> int:
    """Greedy word wrap with an average glyph width: good enough to size boxes (the renderer fits exactly)."""
    if width <= 0:
        return 99
    cw = char_w(style) * fs
    ls = float(style.get('letterSpacing') or 0)
    caps = (text or '').upper() == (text or '') and any(c.isalpha() for c in text or '')
    unit = cw * (1.08 if caps else 1) + ls
    lines = 0
    for para in str(text or '').split('\n'):
        cur = 0.0
        lines += 1
        for word in para.split():
            wlen = len(word) * unit
            if cur and cur + unit + wlen > width:
                lines += 1
                cur = wlen
            else:
                cur = cur + (unit if cur else 0) + wlen
            if wlen > width:            # a single word wider than the box
                lines += int(wlen // width)
    return max(1, lines)


def text_width(text: str, fs: float, style: dict) -> float:
    ls = float(style.get('letterSpacing') or 0)
    caps = (text or '').upper() == (text or '') and any(c.isalpha() for c in text or '')
    return len(text or '') * (char_w(style) * fs * (1.08 if caps else 1) + ls)


# ---------------------------------------------------------------- flow items

def lines_for(n, fs: float, width: float) -> int:
    """Line count at font size fs in `width`, calibrated on the original box (how many lines it really had there)."""
    lh = float(n.style.get('lineHeight') or 1.15)
    fs0 = n.font_size
    real = max(1, round(n.box.h / max(1e-6, fs0 * lh)))
    est0 = text_lines(n.text, fs0, n.box.w, n.style)
    est1 = text_lines(n.text, fs, width, n.style)
    return max(1, real + est1 - est0)


class Item:
    """One movable unit of the copy flow: a group (text stack, button, badge, card, lockup, logo...)."""

    def __init__(self, group: dict, g, roles: dict):
        self.g, self.group = g, group
        self.id = group['id']
        self.kind = group['kind']
        self.role = group['role']
        self.members = [g.by_id[m] for m in group['members']]
        self.box = Box.of(group['box'])
        anchors = group.get('anchors') or []
        by_anchor = 'center' if 'center-x' in anchors else \
            ('right' if 'right' in anchors and 'left' not in anchors else 'left')
        self.align = (group.get('text_align') or by_anchor) if self.kind in ('text', 'text-stack') else by_anchor
        self.roles = roles
        self.dropped: set[str] = set()       # member ids hidden to make room
        self.pills = []                      # several buttons in one group (store badges): (shape, label) pairs
        shapes = [n for n in self.members if n.type == 'shape']
        if self.kind in ('button', 'badge') and len(shapes) > 1:
            for sh in shapes:
                lab = next((t for t in self.members if t.type == 'text' and sh.box.contains(t.box, slack=4)), None)
                if lab is None:
                    self.pills = []
                    break
                self.pills.append((sh, lab))
            if len({id(lab) for _, lab in self.pills}) != len(self.pills) or \
                    len(self.pills) * 2 != len([n for n in self.members if n.type in ('shape', 'text')]):
                self.pills = []
        rt = self._row_texts()
        self.spread = len(rt) > 1 and rt[-1].box.r >= self.box.r - 2 and \
            rt[-1].box.x - rt[-2].box.r > max(n.font_size for n in rt) * 2

    @property
    def texts(self):
        return [n for n in self.members if n.type == 'text' and n.id not in self.dropped]

    def _row_texts(self):
        return sorted((n for n in self.members if n.type == 'text'), key=lambda n: n.box.x)

    def is_text_row(self) -> bool:
        """A line of text pieces side by side (menu item ... price): re-laid out, not scaled."""
        return self.kind == 'row' and all(n.type == 'text' for n in self.members) and len(self.members) > 1

    def _textrow(self, k: float, avail_w: float):
        ts = self._row_texts()
        sizes = []
        for n in ts:
            fs = max(MIN_TEXT, n.font_size * k)
            lh = float(n.style.get('lineHeight') or 1.15)
            sizes.append((text_width(n.text, fs, n.style) * 1.04, fs * lh, fs))
        gaps = sum(sz[2] * .8 for sz in sizes[:-1])
        natural = sum(sz[0] for sz in sizes) + gaps
        if natural <= avail_w + .5:
            w = min(avail_w, max(natural, self.box.w * k)) if self.spread else natural
            return w, max(sz[1] for sz in sizes), True, sizes
        sizes = []                           # too narrow: the pieces stack, each wrapping in the width
        for n in ts:
            fs = max(MIN_TEXT, n.font_size * k)
            lh = float(n.style.get('lineHeight') or 1.15)
            nl = text_lines(n.text, fs, avail_w, n.style)
            sizes.append((min(avail_w, text_width(n.text, fs, n.style) * 1.04), nl * fs * lh, fs))
        h = sum(sz[1] for sz in sizes) + sum(sz[2] * .2 for sz in sizes[:-1])
        return max(sz[0] for sz in sizes), h, False, sizes

    def _pillset(self, k: float, avail_w: float):
        sizes = [_pill_size(sh, lab, k, avail_w) for sh, lab in self.pills]
        bs = sorted((sh.box for sh, _ in self.pills), key=lambda b: b.x)
        g0 = [b2.x - b1.r for b1, b2 in zip(bs, bs[1:]) if b2.x > b1.r]
        gap = (min(g0) if g0 else 16) * k
        gap = max(gap, MIN_TEXT * .5)
        rw = sum(w for w, _ in sizes) + gap * (len(sizes) - 1)
        if rw <= avail_w + .5:
            return rw, max(h for _, h in sizes), True, sizes, gap
        return max(w for w, _ in sizes), sum(h for _, h in sizes) + gap * (len(sizes) - 1), False, sizes, gap

    def importance(self) -> float:
        if self.role == 'logo':
            return len(DROP_ORDER) + 2
        order = {r: i for i, r in enumerate(DROP_ORDER)}
        return order.get(self.role, len(DROP_ORDER) + 1)

    def reflowable(self) -> bool:
        return self.kind in ('text', 'text-stack') and self.role != 'logo'

    def is_pill(self) -> bool:
        if self.kind not in ('button', 'badge'):
            return False
        return len([n for n in self.members if n.type == 'shape']) == 1 and bool(self.texts)

    def is_label(self) -> bool:
        """A single line of text that keeps its line (a text logo): sized to its words, not its box."""
        return self.role == 'logo' and len(self.members) == 1 and self.members[0].type == 'text'

    def uk(self, k: float) -> float:
        """Uniform scale for items that keep their inner geometry, never letting their text go under 12 px."""
        fs = [n.font_size for n in self.texts]
        return max(k, MIN_TEXT / min(fs)) if fs else k

    # size this item would take at type scale k inside width `avail_w`
    def measure(self, k: float, avail_w: float):
        if self.is_pill():
            sh = next(n for n in self.members if n.type == 'shape')
            return _pill_size(sh, self.texts[0], k, avail_w)
        if self.pills:
            return self._pillset(k, avail_w)[:2]
        if self.is_text_row():
            return self._textrow(k, avail_w)[:2]
        if self.is_label():
            n = self.members[0]
            fs = max(MIN_TEXT, n.font_size * k)
            return text_width(n.text, fs, n.style) * 1.04, fs * float(n.style.get('lineHeight') or 1.15)
        if self.reflowable():
            texts = sorted(self.texts, key=lambda n: n.box.y)
            if not texts:
                return 0, 0
            w = min(avail_w, max(self.box.w * k, avail_w if len(texts) > 1 or self.box.w * k > avail_w else 0) or avail_w)
            h = 0.0
            prev = None
            for n in texts:
                fs = max(MIN_TEXT, n.font_size * k)
                lh = float(n.style.get('lineHeight') or 1.15)
                h += lines_for(n, fs, w) * fs * lh
                if prev is not None:
                    h += max(0.0, n.box.y - prev.box.b) * k
                prev = n
            return w, h
        u = self.uk(k)
        return self.box.w * u, self.box.h * u

    def min_font(self, k: float) -> float:
        if not self.texts:
            return 99
        if self.reflowable() or self.is_pill() or self.is_label() or self.pills or self.is_text_row():
            return min(n.font_size * k for n in self.texts)
        return min(n.font_size for n in self.texts) * self.uk(k)

    # write node boxes for this item placed at (x, y) with width w at scale k
    def place(self, out: dict, x: float, y: float, w: float, k: float):
        def ax(iw):
            return x if self.align == 'left' else (x + (w - iw) / 2 if self.align == 'center' else x + w - iw)
        if self.is_pill():
            bw, bh = self.measure(k, w)
            _place_pill(out, next(n for n in self.members if n.type == 'shape'), self.texts[0], ax(bw), y, k, w)
            return bw, bh
        if self.pills:
            tw, th, horiz, sizes, gap = self._pillset(k, w)
            px, py = ax(tw), y
            for (sh, lab), (bw, bh) in zip(self.pills, sizes):
                if horiz:
                    _place_pill(out, sh, lab, px, y + (th - bh) / 2, k, w)
                    px += bw + gap
                else:
                    _place_pill(out, sh, lab, ax(bw), py, k, w)
                    py += bh + gap
            return tw, th
        if self.is_text_row():
            tw, th, horiz, sizes = self._textrow(k, w)
            ts = self._row_texts()
            cx, cy = x, y
            for i, (n, (nw, nh, fs)) in enumerate(zip(ts, sizes)):
                if horiz:
                    nx = x + w - nw if (i == len(ts) - 1 and len(ts) > 1 and self.spread) else cx
                    _set(out, n.id, [nx, y + (th - nh) / 2, nw, nh], fs=fs)
                    cx += nw + fs * .8
                else:
                    _set(out, n.id, [x, cy, nw, nh], fs=fs)
                    cy += nh + fs * .2
            return tw, th
        if self.is_label():
            tw, th = self.measure(k, w)
            n = self.members[0]
            _set(out, n.id, [ax(tw), y, tw, th], fs=max(MIN_TEXT, n.font_size * k))
            return tw, th
        if self.reflowable():
            texts = sorted(self.texts, key=lambda n: n.box.y)
            iw, _ = self.measure(k, w)
            cy, prev = y, None
            for n in texts:
                fs = max(MIN_TEXT, n.font_size * k)
                lh = float(n.style.get('lineHeight') or 1.15)
                if prev is not None:
                    cy += max(0.0, n.box.y - prev.box.b) * k
                nl = lines_for(n, fs, iw)
                _set(out, n.id, [ax(iw), cy, iw, nl * fs * lh], fs=fs)
                cy += nl * fs * lh
                prev = n
            return iw, cy - y
        u = self.uk(k)
        return self.place_uniform(out, ax(self.box.w * u), y, u)

    def place_uniform(self, out: dict, gx: float, y: float, u: float):
        """Every member scaled by u about the group's top-left, which lands at (gx, y)."""
        for n in self.members:
            b = n.box
            nb = [gx + (b.x - self.box.x) * u, y + (b.y - self.box.y) * u, b.w * u, b.h * u]
            if n.type == 'text':
                _set(out, n.id, nb, fs=n.font_size * u)
            else:
                _set(out, n.id, nb, radius=float(n.style.get('radius') or 0) * u if n.style.get('radius') else None)
        return self.box.w * u, self.box.h * u


class RepeatItem:
    """Cards in a series (speakers, products) moving as one unit: a row, a grid or a column, whatever fits.

    Cards keep their inner geometry and are scaled together, never with text under 12 px. A single row of cards
    may wrap into a grid; a vertical list may become two columns on a wide canvas."""

    kind = 'repeat'
    role = 'repeat'

    def __init__(self, groups: list[dict], g, roles: dict):
        self.cards = sorted((Item(gr, g, roles) for gr in groups), key=lambda c: (round(c.box.y / 8), c.box.x))
        self.id = 'repeat:' + self.cards[0].id
        self.align = 'center'
        self.dropped: set[str] = set()
        self.members = [m for c in self.cards for m in c.members]
        self.box = Box.bound([c.box for c in self.cards])
        self.cw = max(c.box.w for c in self.cards)
        self.ch = max(c.box.h for c in self.cards)
        first = self.cards[0].box
        self.orig_cols = sum(1 for c in self.cards if abs(c.box.cy - first.cy) < first.h / 2)
        gaps = []
        for a_, b_ in zip(self.cards, self.cards[1:]):
            if b_.box.x > a_.box.r:
                gaps.append(b_.box.x - a_.box.r)
            elif b_.box.y > a_.box.b:
                gaps.append(b_.box.y - a_.box.b)
        self.gap0 = min(gaps) if gaps else self.cw * .08
        self.flex = all(c.is_text_row() or c.reflowable() for c in self.cards)   # text lists re-flow, cards scale
        self.max_h = None                   # set when the cards get a column of their own
        self._u = None

    @property
    def texts(self):
        return [n for c in self.cards for n in c.texts]

    def importance(self) -> float:
        return DROP_ORDER.index('repeat')

    def reflowable(self) -> bool:
        return False

    def _flex_layout(self, k: float, avail_w: float, max_cols: int):
        n = len(self.cards)
        hgap = max(self.gap0 * k, 24 * k, MIN_TEXT)
        vgap = self.gap0 * k
        for cols in range(min(n, max_cols), 0, -1):
            colw = (avail_w - hgap * (cols - 1)) / cols
            if cols == 1 or all(c.reflowable() or c._textrow(k, colw)[2] for c in self.cards):
                break
        rows = math.ceil(n / cols)
        cols = math.ceil(n / rows)
        colw = (avail_w - hgap * (cols - 1)) / cols
        heights = [max(c.measure(k, colw)[1] for c in self.cards[r * cols:(r + 1) * cols]) for r in range(rows)]
        self._u = k
        self._flex = (colw, hgap, vgap, heights)
        return cols, rows, k, avail_w if cols > 1 else max(c.measure(k, colw)[0] for c in self.cards), \
            sum(heights) + vgap * (rows - 1)

    def layout(self, k: float, avail_w: float):
        n = len(self.cards)
        max_cols = n if self.orig_cols == n else max(self.orig_cols, 2)
        if self.flex:
            return self._flex_layout(k, avail_w, max_cols)
        u = max(c.uk(k) for c in self.cards)
        if self.max_h:                      # a column of its own: pick the arrangement that shows the cards largest
            floor = max(c.uk(0) for c in self.cards)
            best = None
            for c in range(min(n, max_cols), 0, -1):
                rows = math.ceil(n / c)
                c = math.ceil(n / rows)
                uc = min(u * 1.25, avail_w / (c * self.cw + (c - 1) * self.gap0),
                         self.max_h / (rows * self.ch + (rows - 1) * self.gap0))
                if best is None or uc > best[0] + 1e-6 or (abs(uc - best[0]) < 1e-6 and c == self.orig_cols):
                    best = (uc, c, rows)
            uc, c, rows = best
            if uc >= floor - 1e-6:
                self._u = uc
                return c, rows, uc, c * self.cw * uc + (c - 1) * self.gap0 * uc, rows * self.ch * uc + (rows - 1) * self.gap0 * uc
        # keep the designer's arrangement when it fits at no less than 3/4 of the type scale
        oc = self.orig_cols
        u_keep = (avail_w + .5) / (oc * self.cw + (oc - 1) * self.gap0)
        if oc > 1 and u_keep >= max(u * .75, max(c.uk(0) for c in self.cards)):
            u = min(u, u_keep)
            rows = math.ceil(n / oc)
            self._u = u
            return oc, rows, u, oc * self.cw * u + (oc - 1) * self.gap0 * u, rows * self.ch * u + (rows - 1) * self.gap0 * u
        cols = 0
        for c in range(min(n, max_cols), 0, -1):
            if c * self.cw * u + (c - 1) * self.gap0 * u <= avail_w + .5:
                cols = c
                break
        if cols == 0:                       # even one card is too wide: shrink to the width (checks flag small text)
            cols, u = 1, avail_w / self.cw
        rows = math.ceil(n / cols)
        cols = math.ceil(n / rows)          # balance the grid: 2 + 2 rather than 3 + 1
        w = cols * self.cw * u + (cols - 1) * self.gap0 * u
        h = rows * self.ch * u + (rows - 1) * self.gap0 * u
        self._u = u
        return cols, rows, u, w, h

    def measure(self, k: float, avail_w: float):
        return self.layout(k, avail_w)[3:]

    def min_font(self, k: float) -> float:
        fs = [n.font_size for n in self.texts]
        if not fs:
            return 99
        return min(fs) * (self._u if self._u is not None else max(c.uk(k) for c in self.cards))

    def place(self, out: dict, x: float, y: float, w: float, k: float):
        cols, rows, u, tw, th = self.layout(k, w)
        if self.flex:
            colw, hgap, vgap, heights = self._flex
            y0 = y
            for r in range(rows):
                for col, c in enumerate(self.cards[r * cols:(r + 1) * cols]):
                    c.place(out, x + col * (colw + hgap), y0, colw if cols > 1 else w, k)
                y0 += heights[r] + vgap
            return tw, th
        step_x, step_y = (self.cw + self.gap0) * u, (self.ch + self.gap0) * u
        for i, c in enumerate(self.cards):
            r, col = divmod(i, cols)
            in_row = min(cols, len(self.cards) - r * cols)
            row_w = in_row * self.cw * u + (in_row - 1) * self.gap0 * u
            x0 = x + (w - row_w) / 2
            c.place_uniform(out, x0 + col * step_x + (self.cw - c.box.w) * u / 2, y + r * step_y, u)
        return tw, th


def _pill_size(sh, lab, k: float, avail_w: float):
    """A button re-sized around its label: padding scales, the label never goes under 12 px."""
    fs0 = lab.font_size * k
    fs = max(MIN_TEXT, fs0)
    grow = text_width(lab.text, fs, lab.style) - text_width(lab.text, fs0, lab.style)   # only when 12 px floor kicks in
    w = max(sh.box.w * k + grow, text_width(lab.text, fs, lab.style) + fs * .6)
    return min(avail_w, w), sh.box.h * k + (fs - fs0) * 1.6


def _place_pill(out, sh, lab, x: float, y: float, k: float, avail_w: float):
    bw, bh = _pill_size(sh, lab, k, avail_w)
    fs = max(MIN_TEXT, lab.font_size * k)
    _set(out, sh.id, [x, y, bw, bh], radius=min(float(sh.style.get('radius') or 0) * k, bh / 2))
    lh = fs * float(lab.style.get('lineHeight') or 1.15)
    _set(out, lab.id, [x + bh * .2, y + (bh - lh) / 2, bw - bh * .4, lh], fs=fs)
    return bw, bh


def _set(out: dict, nid: str, box, fs=None, radius=None):
    n = out[nid]
    n['box'] = [round(v, 2) for v in box]
    n.pop('hidden', None)
    if fs is not None:
        n.setdefault('style', {})['fontSize'] = round(fs, 2)
    if radius is not None:
        n.setdefault('style', {})['radius'] = round(radius, 2)


def _fresh(design: dict) -> dict:
    out = {n['id']: copy.deepcopy(n) for n in design['nodes']}
    for n in out.values():
        if n['type'] != 'group':
            n['hidden'] = True                     # everything is placed explicitly; leftovers stay hidden
    return out


def _extent(out: dict, members) -> Box | None:
    bs = [Box.of(out[n.id]['box']) for n in members if not out[n.id].get('hidden')]
    return Box.bound(bs) if bs else None


def _shift(out: dict, members, dy: float):
    for n in members:
        b = out[n.id]['box']
        out[n.id]['box'] = [b[0], round(b[1] + dy, 2), b[2], b[3]]


# ---------------------------------------------------------------- layout helpers

def flow_column(items, region: Box, k: float, gap: float, valign: str, out: dict):
    sizes = [it.measure(k, region.w) for it in items]
    total = sum(h for _, h in sizes) + gap * max(0, len(items) - 1)
    y = region.y if valign == 'top' else (region.b - total if valign == 'bottom' else region.y + (region.h - total) / 2)
    for it in items:
        _, h = it.place(out, region.x, y, region.w, k)
        y += h + gap
    return total


def _row_widths(items, region, k, gap):
    fixed = [it for it in items if not it.reflowable()]
    flex = [it for it in items if it.reflowable()]
    fixed_w = sum(it.measure(k, region.w)[0] for it in fixed)
    free = region.w - fixed_w - gap * max(0, len(items) - 1)
    return [free / max(1, len(flex)) if it.reflowable() else it.measure(k, region.w)[0] for it in items], free, flex


def flow_row(items, region: Box, k: float, gap: float, out: dict):
    """Left-to-right flow for wide, short regions; the text items share the remaining width."""
    widths, _, _ = _row_widths(items, region, k, gap)
    x = region.x
    total_h = 0.0
    for it, w in zip(items, widths):
        _, h = it.measure(k, w)
        it.place(out, x, region.y + (region.h - h) / 2, w, k)
        total_h = max(total_h, h)
        x += w + gap
    return total_h


def fits_row(items, region, k, gap):
    widths, free, flex = _row_widths(items, region, k, gap)
    min_flex = max((max(MIN_TEXT, n.font_size * k) * 5 for it in flex for n in it.texts), default=0)
    if (flex and free / len(flex) < min_flex) or (not flex and free < -.5):
        return False
    return all(it.measure(k, w)[1] <= region.h + .5 for it, w in zip(items, widths)) and _readable(items, k)


def _readable(items, k):
    """Cards squeezed to the width can end up with text under 12 px: that is not a fit."""
    return all(it.min_font(k) >= MIN_TEXT - .01 for it in items if isinstance(it, RepeatItem))


def fits_column(items, region, k, gap):
    total = sum(it.measure(k, region.w)[1] for it in items) + gap * max(0, len(items) - 1)
    return total <= region.h + .5 and all(it.measure(k, region.w)[0] <= region.w + .5 for it in items) \
        and _readable(items, k)


# ---------------------------------------------------------------- tier 1: keep the layout

def _hero_like(a: dict, g) -> set:
    page = g.width * g.height
    return {gr['id'] for gr in a['groups'] if gr['kind'] == 'image' and len(gr['members']) == 1
            and gr['box'][2] * gr['box'][3] >= page * .08}


def preserve_one(design: dict, g, a: dict, W: float, H: float, base_overlaps: set):
    """Same family of shapes: keep every element where the designer put it, relative to the edges it hugs.

    Text re-wraps in its own lane, photos re-crop around their subject, and elements stacked in a column keep
    their order and spacing (a longer headline pushes what is under it down). Returns None when that can't be
    done cleanly; the caller then re-flows instead."""
    sx, sy = W / g.width, H / g.height
    u = min(sx, sy)
    roles = {k_: v['role'] for k_, v in a['roles'].items()}
    layer_nodes = set(a['layers']['background']) | set(a['layers']['panels']) | set(a['layers']['decoration'])
    hero_ids = _hero_like(a, g)
    mm = [v for v in a['grid']['margins'].values() if v > 1]
    mmin = max(4.0, (min(mm) if mm else 40) * u)
    k_hi = min(math.sqrt(sx * sy), u * 1.15)
    cands = []
    for kt in (k_hi, (k_hi + u) / 2, u, u * .92, u * .85):
        if all(abs(kt - c) > 1e-3 for c in cands):
            cands.append(kt)
    groups = [gr for gr in a['groups'] if not all(m in layer_nodes for m in gr['members'])]
    for kt in cands:
        out = _fresh(design)
        placed = []                     # (orig box, item or None, members) of the movable copy groups
        for gr in groups:
            ob = Box.of(gr['box'])
            anchors = gr.get('anchors') or []
            members = [g.by_id[m] for m in gr['members']]
            if gr['id'] in hero_ids:    # photos: the slot follows the canvas edges; the crop keeps the subject
                for n in members:
                    _set(out, n.id, [ob.x * sx, ob.y * sy, ob.w * sx, ob.h * sy])
                continue
            it = Item(gr, g, roles)
            ki = kt if (it.reflowable() or it.is_pill() or it.is_label() or it.pills or it.is_text_row()) else u
            if it.reflowable() or it.is_text_row():
                lane = ob.w * min(kt, sx)
                w_, h_ = it.measure(ki, lane)
                w_ = lane
            else:
                w_, h_ = it.measure(ki, W - 2 * mmin)
            if 'left' in anchors:
                x = ob.x * sx
            elif 'right' in anchors:
                x = W - (g.width - ob.r) * sx - w_
            else:
                x = ob.cx * sx - w_ / 2
            if 'top' in anchors:
                y = ob.y * sy
            elif 'bottom' in anchors:
                y = H - (g.height - ob.b) * sy - h_
            else:
                y = ob.cy * sy - h_ / 2
            x = min(max(x, 0.0), max(0.0, W - w_))
            it.place(out, x, y, w_, ki)
            placed.append((ob, members, 'bottom' in anchors))
        # a longer text pushes what sits under it down, keeping the original gap
        placed.sort(key=lambda p: p[0].y)
        for i, (ob, mem, _) in enumerate(placed):
            for ob2, mem2, _ in placed[:i]:
                if ob2.b > ob.y + 2:
                    continue
                A, B = _extent(out, mem2), _extent(out, mem)
                if not A or not B or A.r <= B.x or B.r <= A.x:
                    continue
                need = A.b + max(0.0, ob.y - ob2.b) * min(sy, kt) - B.y
                if need > .5:
                    _shift(out, mem, need)
        for nid in a['layers']['background']:
            _set(out, nid, [0, 0, W, H])
        for pid in a['layers']['panels']:
            pb = g.by_id[pid].box
            nb = Box(pb.x * sx, pb.y * sy, pb.w * sx, pb.h * sy)
            inside = [Box.of(out[n.id]['box']) for n in g.leaves() if n.type == 'text' and not out[n.id].get('hidden')
                      and pb.contains(n.box, slack=2)]
            if inside:
                nb = nb.union(Box.bound(inside))
            _set(out, pid, nb.list())
        _decorate(out, g, a, W, H, sx, sy, u, None)
        res = finish(design, g, a, out, W, H)
        c = res['checks']
        c['overlaps'] = [p for p in c['overlaps'] if tuple(sorted(p)) not in base_overlaps]
        c['ok'] = not c['overlaps'] and not c['off_canvas'] and not c['small_text']
        if c['ok'] and not c['dropped']:
            res['k'] = kt
            return res
    return None


def _decorate(out, g, a, W, H, sx, sy, u, copy_region, hero_map=None):
    """Decoration keeps its relative position; a halo behind the photo moves with the photo; divider lines and
    bands span the copy or the page; decorative text and thin bands never cross copy."""
    copy_boxes = [Box.of(n['box']) for n in out.values() if n['type'] == 'text' and not n.get('hidden')]
    for did in a['layers']['decoration']:
        n = g.by_id[did]
        b = n.box
        nb = Box(b.x * sx, b.y * sy, b.w * u, b.h * u)
        band = n.type == 'shape' and b.h <= g.height * .03
        if hero_map and b.inter(hero_map[0]) > b.area * .3:
            ob, hb = hero_map
            hk = min(hb.w / max(1.0, ob.w), hb.h / max(1.0, ob.h))
            nb = Box(hb.cx + (b.x - ob.cx) * hk, hb.cy + (b.y - ob.cy) * hk, b.w * hk, b.h * hk)
        elif band and b.x <= 1 and b.r >= g.width - 1:
            nb = Box(0, b.y * sy, W, max(1.0, b.h * u))
        elif n.type == 'shape' and b.h <= max(4, g.height * .01):
            nb = Box(copy_region.x, b.y * sy, copy_region.w, max(1.0, b.h * u)) if copy_region else \
                Box(b.x * sx, b.y * sy, b.w * sx, max(1.0, b.h * u))
        if (n.type == 'text' or (copy_region is not None and band)) and any(nb.inter(cb) > 0 for cb in copy_boxes):
            continue      # never draw decoration across copy
        _set(out, did, nb.list())


def finish(design: dict, g, a: dict, out: dict, W: float, H: float, reasons: list | None = None):
    """Photo crops around subjects, src handling, checks."""
    reasons = reasons if reasons is not None else []
    crops = {}
    for nid, sub in a['subjects'].items():
        n = out[nid]
        if n.get('hidden'):
            continue
        nb = n['box']
        slot = nb[2] / max(1.0, nb[3])
        ob = g.by_id[nid].box
        img_aspect = sub.get('aspect') or (ob.w / max(1.0, ob.h))
        c = smart_crop(sub['box'], img_aspect, slot, sub.get('parts'))
        n['crop'] = c['crop']
        crops[nid] = c['kept']
        if sub.get('source') != 'assumed' and c['kept'] >= .999:
            reasons.append(f"Photo cropped around its subject ({sub['source']}): 100% kept.")
        elif sub.get('source') != 'assumed':
            reasons.append(f"Photo cropped around its subject: {c['kept'] * 100:.0f}% kept (the rest doesn't fit this shape).")
    nodes = [out[n['id']] for n in design['nodes']]
    for n in nodes:      # photos are not repeated per size: the client re-attaches them by id
        if n.get('src'):
            n.pop('src')
            n['srcFrom'] = n['id']
    adapted = {'format': 'chameleon-graph/1', 'name': design.get('name', ''),
               'page': {**design['page'], 'width': W, 'height': H}, 'nodes': nodes}
    return {'design': adapted, 'reasons': reasons, 'checks': check(adapted, a, crops)}


# ---------------------------------------------------------------- one target

def _copy_items(groups: list[dict], a: dict, g, roles: dict) -> list:
    """Copy groups as flow items, in reading order; cards of a repeat block become one RepeatItem."""
    ids = {gr['id'] for gr in groups}
    by_id = {gr['id']: gr for gr in groups}
    rep_of = {}
    for b in a.get('blocks', []):
        if b['kind'] == 'repeat' and len(b['groups']) > 1 and all(x in ids for x in b['groups']):
            for x in b['groups']:
                rep_of[x] = b['id']
    items, seen = [], set()
    for gr in groups:
        bid = rep_of.get(gr['id'])
        if bid is None:
            items.append(Item(gr, g, roles))
        elif bid not in seen:
            seen.add(bid)
            blk = next(b for b in a['blocks'] if b['id'] == bid)
            items.append(RepeatItem([by_id[x] for x in blk['groups']], g, roles))
    return items


def adapt_one(design: dict, g, a: dict, target: dict, base_overlaps: set = frozenset()) -> dict:
    W, H = float(target['width']), float(target['height'])
    plan = plan_tier(g.width, g.height, W, H)
    tier = plan['tier']
    head = f"Tier {tier} · {plan['tier_name']}: {plan['reasons'][0]}."
    meta = {'name': target.get('name', ''), 'width': W, 'height': H, 'tier': tier, 'tier_name': plan['tier_name'],
            'baselines': baselines(g, a, W, H)}
    if tier == 1:
        res = preserve_one(design, g, a, W, H, base_overlaps)
        if res is not None:
            s = min(W / g.width, H / g.height)
            same = abs(W - g.width) < .5 and abs(H - g.height) < .5
            reasons = [head, 'Original size: layout kept as designed.' if same else
                       'Layout kept: every element stays anchored to the edges it hugs; text re-wraps in its own lane.']
            if abs(res['k'] - s) / max(s, 1e-6) > .03:
                reasons.append(f"Type scaled {res['k'] / s * 100:.0f}% of a plain resize so it fills the new shape.")
            res['reasons'] = list(dict.fromkeys(reasons + res['reasons']))
            res.pop('k')
            return {**meta, **res}
    res = reflow_one(design, g, a, W, H, tier)
    res['reasons'] = list(dict.fromkeys([head] + res['reasons']))
    return {**meta, **res}


def reflow_one(design: dict, g, a: dict, W: float, H: float, tier: int) -> dict:
    s = min(W / g.width, H / g.height)
    reasons: list[str] = []
    out = _fresh(design)
    roles = {k_: v['role'] for k_, v in a['roles'].items()}
    groups = {gr['id']: gr for gr in a['groups']}
    short = min(W, H)
    m0 = sorted(a['grid']['margins'].values())
    mrel = (m0[1] if len(m0) > 1 else 40) / min(g.width, g.height)
    m = max(6.0, min(.09, max(.035, mrel)) * short)
    gap_base = m * .6

    # --- backgrounds
    for nid in a['layers']['background']:
        _set(out, nid, [0, 0, W, H])
    # --- hero photo
    hero = None
    if a['style']['structure'] != 'overlay':
        cands = [gr for gr in a['groups'] if gr['kind'] == 'image' and gr['role'] in ('hero', 'image', 'photo')]
        if cands:
            hero = max(cands, key=lambda gr: gr['box'][2] * gr['box'][3])
            if hero['box'][2] * hero['box'][3] < g.width * g.height * .08:
                hero = None
    logo = [gr for gr in a['groups'] if gr['role'] == 'logo']
    legal = [gr for gr in a['groups'] if gr['role'] == 'legal']
    used = {gr['id'] for gr in ([hero] if hero else []) + logo + legal}
    copy_groups = [gr for gr in a['groups'] if gr['id'] not in used and gr['role'] != 'background']
    order = {gid: i for i, gid in enumerate(a['reading_order'])}
    copy_groups.sort(key=lambda gr: order.get(gr['id'], 99))

    content = Box(m, m, W - 2 * m, H - 2 * m)
    aspect = W / H
    photo_region = None
    copy_region = content

    if hero:
        hb = Box.of(hero['box'])
        bleed = sum([hb.x <= 1, hb.y <= 1, hb.r >= g.width - 1, hb.b >= g.height - 1]) >= 2
        horizontal = aspect >= 1.25 or (aspect > .8 and a['style']['structure'] == 'split-horizontal')
        if tier == 3 and aspect > 3:
            side = min(H - (0 if bleed else 2 * m), W * .25)
            if side < 40:
                reasons.append('Photo dropped: the canvas is too short to show it.')
            else:
                left = hb.cx < g.width / 2
                sub = a['subjects'].get(hero['members'][0])
                ratio = 1.25
                if sub and sub.get('page_box'):     # a thumbnail shaped like its subject keeps all of it
                    sb = sub['page_box']
                    ratio = min(1.6, max(.6, sb[2] / max(1.0, sb[3]) * 1.15))
                tw = side * ratio
                x0 = (0 if bleed else m) if left else W - tw - (0 if bleed else m)
                photo_region = Box(x0, 0 if bleed else m, tw, H if bleed else H - 2 * m)
                copy_region = Box(photo_region.r + m, m, W - photo_region.r - 2 * m, H - 2 * m) if left else \
                    Box(m, m, photo_region.x - 2 * m, H - 2 * m)
                reasons.append('Extreme wide canvas: photo becomes a thumbnail at the ' + ('left.' if left else 'right.'))
        elif horizontal:
            left = hb.cx < g.width / 2
            frac = min(.55, max(.38, hb.w / g.width if a['style']['structure'] == 'split-horizontal' else .45))
            pw = W * frac
            photo_region = Box(0 if (bleed and left) else (m if left else W - pw - (0 if bleed else m)),
                               0 if bleed else m, pw - (0 if bleed else m), H if bleed else H - 2 * m)
            if not left and bleed:
                photo_region = Box(W - pw, 0, pw, H)
            copy_region = Box(photo_region.r + m, m, W - photo_region.r - 2 * m, H - 2 * m) if left else \
                Box(m, m, photo_region.x - 2 * m, H - 2 * m)
            # narrow the photo column until its subject fits whole (the copy column takes the room)
            sub = a['subjects'].get(hero['members'][0])
            if sub and sub.get('source') != 'assumed':
                img_aspect = sub.get('aspect') or hb.w / max(1.0, hb.h)
                for _ in range(12):
                    kept = smart_crop(sub['box'], img_aspect, photo_region.w / max(1.0, photo_region.h), sub.get('parts'))['kept']
                    if kept >= .98 or photo_region.w * .92 < W * .25:
                        break
                    nw = photo_region.w * .92
                    if left:
                        photo_region = Box(photo_region.x, photo_region.y, nw, photo_region.h)
                        copy_region = Box(photo_region.r + m, copy_region.y, W - photo_region.r - 2 * m, copy_region.h)
                    else:
                        photo_region = Box(photo_region.r - nw, photo_region.y, nw, photo_region.h)
                        copy_region = Box(copy_region.x, copy_region.y, photo_region.x - m - copy_region.x, copy_region.h)
            if a['style']['structure'] != 'split-horizontal':
                reasons.append('Photo and copy re-flowed side by side for the wider canvas.')
        else:
            top = not (hb.cy > g.height * .6 and a['style']['structure'] == 'stacked')
            frac = .34 if tier == 3 else min(.55, max(.38, hb.h / g.height if a['style']['structure'] == 'stacked' else .45))
            ph = H * frac
            photo_region = Box(0 if bleed else m, 0 if (bleed and top) else (m if top else H - ph - m),
                               W if bleed else W - 2 * m, ph - (0 if bleed else m))
            if not top and bleed:
                photo_region = Box(0, H - ph, W, ph)
            copy_region = Box(m, photo_region.b + m, W - 2 * m, H - photo_region.b - 2 * m) if top else \
                Box(m, m, W - 2 * m, photo_region.y - 2 * m)
            if a['style']['structure'] == 'split-horizontal':
                reasons.append('Photo and copy re-flowed from side by side to stacked for the taller canvas.')
        if photo_region and not bleed:
            # a cut-out product or a framed photo keeps roughly its own shape: shrink the slot instead of cropping
            ha = hb.w / max(1.0, hb.h)
            ra = photo_region.w / max(1.0, photo_region.h)
            if ra > ha * 1.3:
                nw = photo_region.h * ha * 1.3
                if horizontal and tier != 3 or (tier == 3 and aspect > 3):
                    left_side = photo_region.x < copy_region.x
                    nx = photo_region.x if left_side else photo_region.r - nw
                    if left_side:
                        copy_region = Box(nx + nw + m, copy_region.y, copy_region.r - (nx + nw + m), copy_region.h)
                    else:
                        copy_region = Box(copy_region.x, copy_region.y, nx - m - copy_region.x, copy_region.h)
                    photo_region = Box(nx, photo_region.y, nw, photo_region.h)
                else:
                    photo_region = Box(photo_region.cx - nw / 2, photo_region.y, nw, photo_region.h)
            elif ra < ha / 1.3:
                nh = photo_region.w / ha * 1.3
                photo_region = Box(photo_region.x, photo_region.cy - nh / 2, photo_region.w, nh)
        if photo_region:
            for nid in hero['members']:
                _set(out, nid, photo_region.list())

    # --- overlay: copy goes where the photo's subject is not
    if a['style']['structure'] == 'overlay':
        sub = next(iter(a['subjects'].values()), None)
        bg_img = next((out[i] for i in a['layers']['background'] if out[i]['type'] == 'image'), None)
        if sub and bg_img is not None:
            img_aspect = sub.get('aspect') or (g.by_id[bg_img['id']].box.w / max(1, g.by_id[bg_img['id']].box.h))
            c = smart_crop(sub['box'], img_aspect, W / H, sub.get('parts'))
            bx, by, bw, bh = sub['box']
            cx_ = ((bx + bw / 2) - c['crop'][0]) / c['crop'][2]
            cy_ = ((by + bh / 2) - c['crop'][1]) / c['crop'][3]
            if aspect >= 1.25 and c['kept'] < .8:
                # too wide to keep the subject behind the copy: the photo becomes a side panel shaped like its subject
                ob = g.by_id[bg_img['id']].box
                sa = (bw * ob.w) / max(1.0, bh * ob.h)
                pw = min(W * .5, max(W * .22, H * min(1.6, max(.6, sa * 1.3))))
                right = cx_ >= .5
                photo_box = Box(W - pw, 0, pw, H) if right else Box(0, 0, pw, H)
                _set(out, bg_img['id'], photo_box.list())
                copy_region = Box(m, m, W - pw - 2 * m, H - 2 * m) if right else Box(pw + m, m, W - pw - 2 * m, H - 2 * m)
                reasons.append('Photo moved to a side panel on the ' + ('right' if right else 'left') +
                               ' so its subject stays whole; copy sits beside it.')
            elif aspect < .8 and c['kept'] < .8:
                ob = g.by_id[bg_img['id']].box
                sa = (bw * ob.w) / max(1.0, bh * ob.h)
                ph = min(H * .5, max(H * .22, W / min(1.6, max(.6, sa / 1.3))))
                top = cy_ < .55
                photo_box = Box(0, 0, W, ph) if top else Box(0, H - ph, W, ph)
                _set(out, bg_img['id'], photo_box.list())
                copy_region = Box(m, ph + m, W - 2 * m, H - ph - 2 * m) if top else Box(m, m, W - 2 * m, H - ph - 2 * m)
                reasons.append('Photo moved to a panel at the ' + ('top' if top else 'bottom') +
                               ' so its subject stays whole; copy sits ' + ('below.' if top else 'above.'))
            elif aspect >= 1.25:
                copy_region = Box(m, m, W * .5 - 1.5 * m, H - 2 * m) if cx_ >= .5 else Box(W * .5 + m * .5, m, W * .5 - 1.5 * m, H - 2 * m)
                reasons.append('Copy placed on the ' + ('left' if cx_ >= .5 else 'right') + ' half, away from the photo subject.')
            else:
                band = .48 if tier < 3 else .7
                copy_region = Box(m, H * (1 - band), W - 2 * m, H * band - m) if cy_ < .55 else Box(m, m, W - 2 * m, H * band - m)
                reasons.append('Copy placed ' + ('below' if cy_ < .55 else 'above') + ' the photo subject.')

    items = _copy_items(copy_groups, a, g, roles)
    row = copy_region.w / max(1.0, copy_region.h) > 2.6 and copy_region.h < 260

    # --- logo: inside the row on banners, otherwise anchored to a corner of the copy
    if row:
        for gr in logo:
            it = Item(gr, g, roles)
            it.align = 'left'
            items.insert(0, it)
        if logo:
            reasons.append('Logo joins the row so the banner reads left to right.')
    for gr in ([] if row else logo):
        it = Item(gr, g, roles)
        it.align = 'left'
        k_logo = max(s, 14 / max(1.0, it.box.h)) if tier < 3 else max(s, 12 / max(1.0, it.box.h))
        lw, lh = it.measure(k_logo, copy_region.w)
        if lw > copy_region.w:                 # never wider than the copy column
            k_logo *= copy_region.w / lw
            lw, lh = it.measure(k_logo, copy_region.w)
        anchors = gr.get('anchors', [])
        x = m if 'left' in anchors or ('right' not in anchors and 'center-x' not in anchors) else \
            (W - m - lw if 'right' in anchors else (W - lw) / 2)
        y = m if 'bottom' not in anchors else H - m - lh
        if hero and photo_region and copy_region.w > lw:   # logo lives with the copy, not on the photo
            if 'center-x' in anchors and not ('left' in anchors or 'right' in anchors):
                x = copy_region.x + (copy_region.w - lw) / 2
            else:
                x = copy_region.x if x < W / 2 else copy_region.r - lw
            y = copy_region.b - lh if 'bottom' in anchors else copy_region.y
        x = min(max(x, 0.0), max(0.0, W - lw))
        it.place(out, x, y, lw, k_logo)
        lbox = Box(x, y, lw, lh)
        # shrink the copy region so copy never runs into the logo
        if copy_region.inter(lbox) > 0:
            if lbox.cy < copy_region.cy:
                ny = lbox.b + gap_base
                copy_region = Box(copy_region.x, ny, copy_region.w, copy_region.b - ny)
            else:
                copy_region = Box(copy_region.x, copy_region.y, copy_region.w, lbox.y - gap_base - copy_region.y)
    legal_items = [Item(gr, g, roles) for gr in legal]

    # --- copy flow with fitting: start from type sized by area (not by the short side), then shrink and drop
    if tier == 1:
        k = s
    else:
        k = min(s * 2.0, max(s, math.sqrt(W * H / (g.width * g.height))))
    if row:
        headi = next((it for it in items if it.role == 'headline'), None)
        if headi and headi.texts:
            hs = max(n.font_size for n in headi.texts)
            k = min(s * 2.5 if s * 2.5 > k else k * 2.5, (copy_region.h * .62) / hs)
    gap = gap_base
    dropped: list[str] = []
    fits = fits_row if row else fits_column
    allitems = items + ([] if row else legal_items)
    protected = ('headline', 'cta')
    # wide canvas without a hero photo: cards go beside the copy, like a photo would
    split = None
    if not row and hero is None and a['style']['structure'] != 'overlay' and aspect >= 1.25:
        split = next((it for it in items if isinstance(it, RepeatItem) and not it.flex), None)

    def columns():
        if split is None or split not in allitems:
            return [(allitems, copy_region)]
        cw_ = (copy_region.w - m) / 2
        left = Box(copy_region.x, copy_region.y, cw_, copy_region.h)
        right = Box(copy_region.x + cw_ + m, copy_region.y, copy_region.w - cw_ - m, copy_region.h)
        split.max_h = right.h
        return [([it for it in allitems if it is not split], left), ([split], right)]

    def fit_all(k_, gap_):
        return all(fits(its, reg, k_, gap_) for its, reg in columns())

    for _ in range(300):
        if fit_all(k, gap):
            break
        smallest = min((it.min_font(k) for it in allitems if it.texts), default=99)
        if smallest > MIN_TEXT * 1.02:
            k *= .94
            gap = max(gap_base * .4, gap * .97)
            continue
        # drop the least important piece: a line inside a text stack, or a whole item
        cand = sorted([it for it in allitems if it.role not in protected], key=lambda it: it.importance())
        lines = [(DROP_ORDER.index(roles.get(n.id, 'body')) if roles.get(n.id, 'body') in DROP_ORDER else 99, it, n)
                 for it in allitems if it.reflowable() and len(it.texts) > 1
                 for n in it.texts if roles.get(n.id) not in protected]
        lines.sort(key=lambda r: r[0])
        if lines and (not cand or lines[0][0] <= cand[0].importance()):
            _, it, n = lines[0]
            it.dropped.add(n.id)
            dropped.append(roles.get(n.id, 'text'))
            continue
        if cand:
            victim = cand[0]
            allitems.remove(victim)
            dropped.append('cards' if victim.role == 'repeat' else victim.role)
            continue
        if k < s * .3:
            break    # nothing left to drop: stop; the checks report what doesn't fit
        k *= .94
    if dropped:
        reasons.append('Dropped to make room: ' + ', '.join(dict.fromkeys(dropped)) + '.')
    if abs(k - s) / max(s, 1e-6) > .05:
        reasons.append(f"Type scaled {k / s * 100:.0f}% of a plain resize so it reads well at this size.")
    reps = [it for it in allitems if isinstance(it, RepeatItem)]
    region_of = {id(it): reg for its, reg in columns() for it in its}
    if split is not None and split in allitems:
        reasons.append('Cards placed beside the copy for the wider canvas.')
    for it in reps:
        cols, rows, *_ = it.layout(k, region_of[id(it)].w)
        if (cols, rows) != (it.orig_cols, math.ceil(len(it.cards) / max(1, it.orig_cols))):
            reasons.append(f"{len(it.cards)} cards re-arranged as {rows} row{'s' if rows > 1 else ''} of {cols}.")
    valign = 'center'
    if a['style']['structure'] == 'overlay' or any('bottom' in groups[it.id].get('anchors', [])
                                                  for it in items if it.role == 'headline' and it.id in groups):
        valign = 'bottom' if copy_region.cy > H / 2 else 'top'
    if row:
        flow_row(allitems, copy_region, k, gap * 1.5, out)
    else:
        for its, reg in columns():
            flow_column(its, reg, k, gap, valign, out)
    for it in allitems:
        for nid in it.dropped:
            out[nid]['hidden'] = True
    if row and legal_items:
        dropped.append('legal')
        reasons.append('Legal line dropped (no room on a banner this short).')

    # --- panels (scrims) follow the copy
    for pid in a['layers']['panels']:
        placed = [Box.of(out[n.id]['box']) for it in allitems for n in it.texts if not out[n.id].get('hidden')]
        if placed:
            u_ = Box.bound(placed)
            if aspect >= 1.25 and a['style']['structure'] == 'overlay':
                pb = [0, 0, u_.r + m, H] if u_.cx < W / 2 else [u_.x - m, 0, W - u_.x + m, H]
            else:
                pb = [0, max(0, u_.y - m * 1.2), W, H - max(0, u_.y - m * 1.2)] if u_.cy > H / 2 else [0, 0, W, u_.b + m * 1.2]
            _set(out, pid, pb)
    if tier < 3:
        hero_map = (Box.of(hero['box']), photo_region) if hero and photo_region else None
        _decorate(out, g, a, W, H, W / g.width, H / g.height, s, copy_region, hero_map)
    return finish(design, g, a, out, W, H, reasons)


# ---------------------------------------------------------------- checks and baselines

def check(design: dict, a: dict, crops: dict) -> dict:
    W, H = design['page']['width'], design['page']['height']
    roles = {k: v['role'] for k, v in a['roles'].items()}
    vis = [n for n in design['nodes'] if n['type'] != 'group' and not n.get('hidden')]
    solid = [n for n in vis if roles.get(n['id']) not in ('background', 'panel', 'decoration') and n['type'] in ('text', 'image', 'shape')
             and roles.get(n['id']) not in ('hero', 'image')]
    container_of = {t: c for c, ts in a['layers']['containers'].items() for t in ts}
    overlaps = []
    for i in range(len(solid)):
        for j in range(i + 1, len(solid)):
            p, q = solid[i], solid[j]
            if container_of.get(p['id']) == q['id'] or container_of.get(q['id']) == p['id']:
                continue
            A, B = Box.of(p['box']), Box.of(q['box'])
            if A.inter(B) > 4:
                overlaps.append([p['id'], q['id']])
    off = [n['id'] for n in vis if roles.get(n['id']) not in ('background', 'decoration')
           and (n['box'][0] < -1 or n['box'][1] < -1 or n['box'][0] + n['box'][2] > W + 1 or n['box'][1] + n['box'][3] > H + 1)]
    small = [n['id'] for n in vis if n['type'] == 'text' and float(n.get('style', {}).get('fontSize') or 99) < MIN_TEXT - .01]
    hidden = [n['id'] for n in design['nodes'] if n['type'] != 'group' and n.get('hidden')
              and roles.get(n['id']) not in ('decoration',)]
    kept = min(crops.values()) if crops else None
    return {'overlaps': overlaps, 'off_canvas': off, 'small_text': small, 'dropped': hidden,
            'subject_kept': kept, 'ok': not overlaps and not off and not small}


def baselines(g, a: dict, W: float, H: float) -> dict:
    """What naive resizing does, measured the same way."""
    sx, sy = W / g.width, H / g.height
    stretch = {'distortion': round(max(sx / sy, sy / sx), 3)}
    k = max(sx, sy)                       # centre crop: cover, cut the overflow
    ox, oy = (W - g.width * k) / 2, (H - g.height * k) / 2
    cut = []
    roles = {kk: v['role'] for kk, v in a['roles'].items()}
    for n in g.leaves():
        if roles.get(n.id) in ('background', 'decoration', 'panel'):
            continue
        b = Box(n.box.x * k + ox, n.box.y * k + oy, n.box.w * k, n.box.h * k)
        if b.x < -1 or b.y < -1 or b.r > W + 1 or b.b > H + 1:
            cut.append(n.id)
    sub_kept = None
    for nid, sub in a['subjects'].items():
        pb = Box.of(sub['page_box'])
        b = Box(pb.x * k + ox, pb.y * k + oy, pb.w * k, pb.h * k)
        inside = b.inter(Box(0, 0, W, H)) / max(1.0, b.area)
        sub_kept = inside if sub_kept is None else min(sub_kept, inside)
    fit = min(sx, sy)                      # letterbox: whole design, shrunk, with empty bars
    return {'stretch': stretch,
            'crop': {'scale': round(k, 4), 'offset': [round(ox, 2), round(oy, 2)], 'cut': cut,
                     'subject_kept': None if sub_kept is None else round(sub_kept, 3)},
            'letterbox': {'scale': round(fit, 4), 'empty': round(1 - (g.width * fit * g.height * fit) / (W * H), 3)}}


# ---------------------------------------------------------------- public

def adapt(design: dict, targets: list[dict]) -> dict:
    g = load(design)
    src = g.to_json() if not (isinstance(design, dict) and 'nodes' in design) else design
    a = analyze(g)
    base = check(src, a, {})            # overlaps the designer made on purpose are allowed to stay
    base_overlaps = {tuple(sorted(p)) for p in base['overlaps']}
    return {'source': {'width': g.width, 'height': g.height},
            'analysis_notes': a['notes'],
            'results': [adapt_one(src, g, a, t, base_overlaps) for t in targets]}
