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
import json
import math
from pathlib import Path

from .graph import Box, load
from .plan import plan_tier
from .subject import crop_kw, smart_crop, reframe
from .understand import analyze

MIN_TEXT = 12.0
DROP_ORDER = ['decoration', 'legal', 'caption', 'body', 'item', 'price', 'eyebrow', 'repeat', 'subhead', 'badge', 'offer']

# ---------------------------------------------------------------- text measurement
# Advance widths of the fonts the studio loads (tools/make_font_metrics.py), so wrapped text boxes match what the
# browser draws. Unknown fonts fall back to Inter; unknown characters to the font's average width.

_FONTS = json.loads((Path(__file__).with_name('fonts.json')).read_text(encoding='utf-8'))
WRAP_SAFETY = 1.03            # canvases differ a little (kerning, hinting): wrap as if text were 3% wider


def _table(style: dict, family: str | None = None) -> dict:
    fam = _FONTS.get(family or style.get('fontFamily') or 'Inter') or _FONTS['Inter']
    try:
        w = int(float(style.get('fontWeight') or 400))
    except (TypeError, ValueError):
        w = 400
    key = min(fam, key=lambda k: abs(int(k) - w))
    return fam[key]


def _em(text: str, t: dict) -> float:
    avg = t.get('n', .55)
    return sum(t.get(c, avg) for c in text)


def text_width(text: str, fs: float, style: dict) -> float:
    """Width in px. For fonts other than Inter, the wider of that font and Inter: if the web font fails to load,
    the page falls back to Inter, and the text must still fit its box."""
    s = str(text or '')
    em = _em(s, _table(style))
    if (style.get('fontFamily') or 'Inter') != 'Inter':
        em = max(em, _em(s, _table(style, 'Inter')))
    ls = float(style.get('letterSpacing') or 0)
    return (em * fs + ls * len(s)) * WRAP_SAFETY


def char_w(style: dict) -> float:
    """Average glyph width in em (lower-case text)."""
    return text_width('the quick brown fox jumps', 1.0, style) / 25


def wrap_widths(text: str, fs: float, width: float, style: dict) -> list:
    """Greedy word wrap, the same way the renderer wraps (words never split): the width of each line."""
    space = text_width(' ', fs, style)
    out = []
    for para in str(text or '').split('\n'):
        cur = 0.0
        for word in para.split():
            wl = text_width(word, fs, style)
            if cur and cur + space + wl > width + .01:
                out.append(cur)
                cur = wl
            else:
                cur = cur + (space if cur else 0) + wl
        out.append(cur)
    return out or [0.0]


def text_lines(text: str, fs: float, width: float, style: dict) -> int:
    if width <= 0:
        return 99
    return max(1, len(wrap_widths(text, fs, width, style)))


def drawn_size(node: dict) -> float:
    """The font size the renderer will actually use: it shrinks text until the wrapped lines fit the box."""
    st = node.get('style') or {}
    x, y, w, h = node['box']
    size = float(st.get('fontSize') or h * .7)
    lh = float(st.get('lineHeight') or 1.15)
    if w <= 0 or h <= 0:
        return 0.0
    for _ in range(40):
        ws = wrap_widths(node.get('text', ''), size, w, st)
        if len(ws) * size * lh <= h * 1.08 and max(ws) <= w * 1.02 * WRAP_SAFETY:
            break
        size *= .95
    return size


def longest_word(text: str, fs: float, style: dict) -> float:
    return max((text_width(w, fs, style) for w in str(text or '').split()), default=0.0)


# ---------------------------------------------------------------- flow items

def lines_for(n, fs: float, width: float) -> int:
    """Line count of text node n at font size fs wrapped in `width`."""
    return text_lines(n.text, fs, width, n.style)


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
        self.keep_h = False                  # keep the designer's text box height as a minimum (layout kept)
        self.xs = 1.0                        # extra shrink for display-size text (keeps the rest of the message)
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
        if natural <= avail_w + .5 and not getattr(self, 'force_stack', False):
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

    def fs_of(self, n, k: float) -> float:
        """Font size of text node n at scale k: display sizes (over 24 px) can shrink further by xs, down to 24 px."""
        f = n.font_size * k
        floor = getattr(self, 'display_floor', 24.0)
        if self.xs < 1 and f > floor:
            f = max(floor, f * self.xs)
        return max(self.floor_of(n), f)

    def floor_of(self, n) -> float:
        """12 px, raised for text the designer set much bigger than the smallest copy (up to 18 px for 3x and over)."""
        base = getattr(self, 'base_fs', None)
        if not base or self.role in ('logo', 'legal') or n.font_size <= base * 1.2:
            return MIN_TEXT
        return MIN_TEXT * min(1.5, (n.font_size / base) ** .5)

    def display_size(self, k: float) -> float:
        return max((self.fs_of(n, k) for n in self.texts), default=0)

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
            if len(texts) > 1:
                w = avail_w
            else:      # as wide as its box at this scale, or as its words need at the (12 px floored) size
                n0 = texts[0]
                need = text_width(n0.text, self.fs_of(n0, k), n0.style) if '\n' not in (n0.text or '') else \
                    max(text_width(t, self.fs_of(n0, k), n0.style) for t in n0.text.split('\n'))
                w = min(avail_w, max(self.box.w * k, need))
            h = 0.0
            prev = None
            for n in texts:
                fs = self.fs_of(n, k)
                lh = float(n.style.get('lineHeight') or 1.15)
                h += max(lines_for(n, fs, w) * fs * lh, n.box.h * k if self.keep_h else 0)
                if prev is not None:
                    h += max(0.0, n.box.y - prev.box.b) * k
                prev = n
            return w, h
        u = self.uk(k)
        if self.box.w * u > avail_w + .5 and self._stackable():
            return self._stacked(k, avail_w)[:2]
        return self.box.w * u, self.box.h * u

    def _stackable(self) -> bool:
        """Avatar + name, icon + label: a small picture beside text that can go above it on a narrow canvas."""
        imgs = [n for n in self.members if n.type == 'image']
        return self.kind == 'lockup' and len(imgs) == 1 and bool(self.texts) and \
            all(n.box.x >= imgs[0].box.r - 2 for n in self.texts)

    def _stacked(self, k: float, avail_w: float):
        img = next(n for n in self.members if n.type == 'image')
        u = self.uk(k)
        iw = min(img.box.w * u, avail_w)
        ih = img.box.h * iw / max(1.0, img.box.w)
        gap = max(6.0, 10 * u)
        rows = []
        h = ih + gap
        tw = iw
        for n in sorted(self.texts, key=lambda n: n.box.y):
            fs = max(MIN_TEXT, n.font_size * k)
            lh = fs * float(n.style.get('lineHeight') or 1.15)
            nl = text_lines(n.text, fs, avail_w, n.style)
            w_ = min(avail_w, text_width(n.text, fs, n.style))
            rows.append((n, fs, w_, nl * lh))
            h += nl * lh
            tw = max(tw, w_)
        return tw, h, img, iw, ih, gap, rows

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
                fs = self.fs_of(n, k)
                lh = float(n.style.get('lineHeight') or 1.15)
                if prev is not None:
                    cy += max(0.0, n.box.y - prev.box.b) * k
                th = max(lines_for(n, fs, iw) * fs * lh, n.box.h * k if self.keep_h else 0)
                _set(out, n.id, [ax(iw), cy, iw, th], fs=fs)
                if getattr(self, 'force_align', None):
                    out[n.id].setdefault('style', {})['align'] = self.force_align
                cy += th
                prev = n
            return iw, cy - y
        u = self.uk(k)
        if self.box.w * u > w + .5 and self._stackable():
            tw, th, img, iw, ih, gap, rows = self._stacked(k, w)
            centre = self.align == 'center'
            _set(out, img.id, [x + (w - iw) / 2 if centre else x, y, iw, ih],
                 radius=float(img.style.get('radius') or 0) * iw / max(1.0, img.box.w) if img.style.get('radius') else None)
            cy = y + ih + gap
            for n, fs, w_, hh in rows:
                _set(out, n.id, [x + (w - w_) / 2 if centre else x, cy, w_, hh], fs=fs)
                out[n.id].setdefault('style', {})['align'] = 'center' if centre else 'left'   # stacked lines line up
                cy += hh
            return tw, th
        return self.place_uniform(out, ax(self.box.w * u), y, u)

    def place_uniform(self, out: dict, gx: float, y: float, u: float):
        """Every member scaled by u about the group's top-left, which lands at (gx, y)."""
        for n in self.members:
            if n.id in self.dropped:
                continue
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
        self.total = len(self.cards)
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

    def refresh(self):
        self.members = [m for c in self.cards for m in c.members]
        self.orig_cols = min(self.orig_cols, len(self.cards))

    def can_go_captionless(self) -> bool:
        return not self.flex and all(c.texts and any(n.type == 'image' for n in c.members) for c in self.cards)

    def go_captionless(self):
        """Small canvases: keep the photos of the cards (speakers' faces, products) and drop their captions,
        so the cards can shrink below what 12 px captions would allow."""
        for c in self.cards:
            c.dropped |= {n.id for n in c.members if n.type == 'text'}
            c.box = Box.bound([n.box for n in c.members if n.id not in c.dropped])
        self.box = Box.bound([c.box for c in self.cards])
        self.cw = max(c.box.w for c in self.cards)
        self.ch = max(c.box.h for c in self.cards)
        self.captionless = True

    def importance(self) -> float:
        return DROP_ORDER.index('repeat')

    def reflowable(self) -> bool:
        return False

    def _flex_layout(self, k: float, avail_w: float, max_cols: int):
        n = len(self.cards)
        hgap = max(self.gap0 * k, 24 * k, MIN_TEXT)
        vgap = self.gap0 * k
        for c in self.cards:
            c.force_stack = False
        for cols in range(min(n, max_cols), 0, -1):
            colw = (avail_w - hgap * (cols - 1)) / cols
            if cols == 1 or all(c.reflowable() or c._textrow(k, colw)[2] for c in self.cards):
                break
        rows = math.ceil(n / cols)
        cols = math.ceil(n / rows)
        colw = (avail_w - hgap * (cols - 1)) / cols
        if any(not c.reflowable() and not c._textrow(k, colw)[2] for c in self.cards):
            for c in self.cards:                # one row has to stack: all rows stack, so the list stays consistent
                c.force_stack = True
        heights = [max(c.measure(k, colw)[1] for c in self.cards[r * cols:(r + 1) * cols]) for r in range(rows)]
        self._u = k
        self._flex = (colw, hgap, vgap, heights)
        return cols, rows, k, avail_w if cols > 1 else max(c.measure(k, colw)[0] for c in self.cards), \
            sum(heights) + vgap * (rows - 1)

    def layout(self, k: float, avail_w: float):
        n = len(self.cards)
        max_cols = n if self.orig_cols == n else max(self.orig_cols, 2)
        if self.flex and avail_w >= 330 and n >= 3:
            max_cols = max(max_cols, 3)     # a text list on a wide, short banner: three columns before fewer items
        if self.flex:
            return self._flex_layout(k, avail_w, max_cols)
        u = max(c.uk(k) for c in self.cards) * getattr(self, 'squeeze', 1.0)
        if self.max_h:                      # a column of its own: pick the arrangement that shows the cards largest
            floor = max(c.uk(0) for c in self.cards)
            best = None
            for c in range(min(n, max_cols), 0, -1):
                rows = math.ceil(n / c)
                c = math.ceil(n / rows)
                uc = min(u * 1.25, avail_w / (c * self.cw + (c - 1) * self.gap0),
                         self.max_h / (rows * self.ch + (rows - 1) * self.gap0))
                score = uc * (1.0 if c == self.orig_cols else .88) * (.85 if c > 1 and n % c == 1 else 1.0)
                if best is None or score > best[3] + 1e-9:
                    best = (uc, c, rows, score)
            uc, c, rows, _ = best
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
    h = sh.box.h * k + (fs - fs0) * 1.6
    w = max(sh.box.w * k + grow, text_width(lab.text, fs, lab.style) + max(fs * .6, h * .4 + 2))
    return w, h


def _place_pill(out, sh, lab, x: float, y: float, k: float, avail_w: float):
    bw, bh = _pill_size(sh, lab, k, avail_w)
    fs = max(MIN_TEXT, lab.font_size * k)
    _set(out, sh.id, [x, y, bw, bh], radius=min(float(sh.style.get('radius') or 0) * k, bh / 2))
    lh = fs * float(lab.style.get('lineHeight') or 1.15)
    lw = min(bw, max(bw - bh * .4, text_width(lab.text, fs, lab.style)))
    _set(out, lab.id, [x + (bw - lw) / 2, y + (bh - lh) / 2, lw, lh], fs=fs)
    return bw, bh


def _names(item, roles: dict) -> list:
    """How a dropped item is named in the reasons: 'cards', or the roles of what it holds."""
    if getattr(item, 'role', '') == 'repeat':
        return ['cards']
    names = [roles.get(n.id) or n.type for n in item.members if roles.get(n.id) not in ('decoration', 'background')]
    names = [('photo' if r in ('hero', 'image') else r) for r in names]
    return list(dict.fromkeys(names)) or [item.role]


def _set_photo(out: dict, node, box):
    """A photo slot: corner radius scales with the slot so a rounded card doesn't turn into a capsule."""
    r = float((node.style or {}).get('radius') or 0)
    k = min(box[2] / max(1.0, node.box.w), box[3] / max(1.0, node.box.h))
    _set(out, node.id, box, radius=r * k if r else None)


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


def _stretchy(it) -> bool:
    """Items that take whatever width a row leaves them: text, and text lists."""
    return it.reflowable() or getattr(it, 'flex', False)


def _row_widths(items, region, k, gap):
    for it in items:
        if isinstance(it, RepeatItem) and not it.flex:
            it.max_h = region.h             # in a row, cards size to the row's height, not to the type scale
    fixed = [it for it in items if not _stretchy(it)]
    flex = [it for it in items if _stretchy(it)]
    fixed_w = sum(it.measure(k, region.w)[0] for it in fixed)
    free = region.w - fixed_w - gap * max(0, len(items) - 1)
    return [free / max(1, len(flex)) if _stretchy(it) else it.measure(k, region.w)[0] for it in items], free, flex


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
    min_flex = max((it.fs_of(n, k) * 5 if hasattr(it, "fs_of") else MIN_TEXT * 5 for it in flex for n in it.texts), default=0)
    if (flex and free / len(flex) < min_flex) or (not flex and free < -.5):
        return False
    return all(it.measure(k, w)[1] <= region.h + .5 for it, w in zip(items, widths)) and _readable(items, k) \
        and _words_fit(items, k, widths)


def _readable(items, k):
    """Cards squeezed to the width can end up with text under 12 px: that is not a fit."""
    return all(it.min_font(k) >= MIN_TEXT - .01 for it in items if isinstance(it, RepeatItem) and not it.flex)


def _words_fit(items, k, widths):
    """A single word wider than its column would make the renderer shrink the whole text: not a fit."""
    for it, w in zip(items, widths):
        if it.reflowable():
            for n in it.texts:
                if longest_word(n.text, it.fs_of(n, k), n.style) > w + .5:
                    return False
    return True


def fits_column(items, region, k, gap):
    if region.w <= 0 or region.h <= 0:
        return False
    total = sum(it.measure(k, region.w)[1] for it in items) + gap * max(0, len(items) - 1)
    return total <= region.h + .5 and all(it.measure(k, region.w)[0] <= region.w + .5 for it in items) \
        and _readable(items, k) and _words_fit(items, k, [region.w] * len(items))


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
    if abs(sx - 1) < 1e-6 and abs(sy - 1) < 1e-6:      # the original size: the design exactly as made
        out = {n['id']: copy.deepcopy(n) for n in design['nodes']}
        res = finish(design, g, a, out, W, H)
        if res['checks']['ok']:
            res['k'] = 1.0
            res['exact'] = True
            return res
    for kt in cands:
        out = _fresh(design)
        placed = []                     # (orig box, item or None, members) of the movable copy groups
        for gr in groups:
            ob = Box.of(gr['box'])
            anchors = gr.get('anchors') or []
            members = [g.by_id[m] for m in gr['members']]
            if gr['id'] in hero_ids:    # photos: the slot follows the canvas edges; the crop keeps the subject
                for n in members:
                    _set_photo(out, n, [ob.x * sx, ob.y * sy, ob.w * sx, ob.h * sy])
                continue
            it = Item(gr, g, roles)
            it.keep_h = True
            ki = kt if (it.reflowable() or it.is_pill() or it.is_label() or it.pills or it.is_text_row()) else u
            if it.reflowable() or it.is_text_row():
                lane = ob.w * min(kt, sx)
                if it.reflowable():      # a word never breaks: the lane is at least as wide as the longest word
                    lane = max(lane, min(W - 2 * mmin, max((longest_word(n.text, max(MIN_TEXT, n.font_size * ki), n.style)
                                                            for n in it.texts), default=0)))
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
        for i, (ob, mem, at_bottom) in enumerate(placed):
            for ob2, mem2, _ in placed[:i]:
                if ob2.b > ob.y + 2:
                    continue
                A, B = _extent(out, mem2), _extent(out, mem)
                if not A or not B or A.r <= B.x or B.r <= A.x:
                    continue
                need = A.b + max(0.0, ob.y - ob2.b) * min(sy, kt) - B.y
                if need > .5:
                    if at_bottom and A.y - need >= 0:
                        _shift(out, mem2, -need)     # bottom-pinned things stay; what's above moves up
                    else:
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
        if copy_region is not None and band and hero_map and nb.inter(hero_map[1]) > 0 and not b.inter(hero_map[0]):
            continue      # nor a band across a photo it didn't cross before
        fs = n.font_size * min(nb.w / max(1.0, b.w), nb.h / max(1.0, b.h)) if n.type == 'text' else None
        _set(out, did, nb.list(), fs=fs)


def subject_boxes(out: dict, a: dict) -> list:
    """Where each photo's subject parts land on the canvas, through the slot and crop chosen for it."""
    res = []
    for nid, sub in a['subjects'].items():
        n = out.get(nid)
        if not n or n.get('hidden') or 'box' not in n or sub.get('source') == 'assumed':
            continue
        x, y, w, h = n['box']
        cx, cy, cw, ch = n.get('crop') or [0, 0, 1, 1]
        pbs = (sub.get('inner') if sub.get('source') == 'whole' else None) or sub.get('parts') or [sub['box']]
        for pb in pbs:
            q = Box(x + (pb[0] - cx) / cw * w, y + (pb[1] - cy) / ch * h, pb[2] / cw * w, pb[3] / ch * h)
            if q.inter(Box(x, y, w, h)) > 0:
                # only the part that is drawn: what the crop cut off cannot be covered by copy
                x0, y0 = max(q.x, x), max(q.y, y)
                res.append((nid, Box(x0, y0, min(q.r, x + w) - x0, min(q.b, y + h) - y0)))
    return res


def _logos_off_subjects(out: dict, a: dict, W: float, H: float, reasons: list, page_bg: str = '#ffffff'):
    """A logo never sits on a face or the product: move it to the photo's (or canvas's) clearest corner."""
    parts = subject_boxes(out, a)
    if not parts:
        return
    roles = {k: v['role'] for k, v in a['roles'].items()}
    for gr in a['groups']:
        if gr['role'] != 'logo':
            continue
        mem = [out[m] for m in gr['members'] if m in out and not out[m].get('hidden') and 'box' in out[m]]
        if not mem:
            continue
        lb = Box.bound([Box.of(m['box']) for m in mem])
        hits = [(pid, q) for pid, q in parts if lb.inter(q) > min(q.area * .03, lb.area * .05)]   # even a corner of the logo on the subject counts
        if not hits:
            continue
        fx, fy, fw, fh = out[hits[0][0]]['box']
        x0, y0 = max(0.0, fx), max(0.0, fy)
        x1, y1 = min(W, fx + fw), min(H, fy + fh)
        pad = max(6.0, min(W, H) * .03)
        others = [Box.of(m['box']) for m in out.values() if not m.get('hidden') and m['type'] in ('text', 'shape')
                  and 'box' in m and m['id'] not in gr['members'] and roles.get(m['id']) not in ('background', 'panel', 'decoration')]
        photo = Box(x0, y0, x1 - x0, y1 - y0)
        spots = [((x0 + pad, y0 + pad), True), ((x1 - pad - lb.w, y0 + pad), True), ((x0 + pad, y1 - pad - lb.h), True), ((x1 - pad - lb.w, y1 - pad - lb.h), True)]
        # no clear corner on the photo: a corner of the page, off the photo, when a text logo can read there
        texts = [m for m in mem if m['type'] == 'text']
        ink = texts[0].get('style', {}).get('color') if texts and len(mem) == 1 else None
        if ink:
            # line up with the copy's left (or right) edge rather than the page edge
            col = [Box.of(m['box']) for m in out.values() if not m.get('hidden') and 'box' in m and m['id'] not in gr['members']
                   and roles.get(m['id']) in ('headline', 'subhead', 'body', 'cta', 'eyebrow') and not Box.of(m['box']).inter(photo)]
            lx = min((c_.x for c_ in col), default=pad)
            rx = max((c_.r for c_ in col), default=W - pad) - lb.w
            spots += [((lx, pad), False), ((rx, pad), False), ((lx, H - pad - lb.h), False), ((rx, H - pad - lb.h), False),
                      ((pad, pad), False), ((W - pad - lb.w, pad), False), ((pad, H - pad - lb.h), False), ((W - pad - lb.w, H - pad - lb.h), False)]
        fills = [(Box.of(m['box']), m.get('style', {}).get('fill')) for m in out.values() if m['type'] == 'shape' and not m.get('hidden')
                 and 'box' in m and m.get('style', {}).get('fill') and roles.get(m['id']) in ('background', 'panel')]
        inks = [m.get('style', {}).get('color') for m in out.values() if m['type'] == 'text' and not m.get('hidden')
                and roles.get(m['id']) in ('headline', 'subhead', 'body') and m.get('style', {}).get('color')]
        for (nx, ny), on_photo in spots:
            cand = Box(nx, ny, lb.w, lb.h)
            if nx < 0 or ny < 0 or cand.r > W or cand.b > H:
                continue
            room = cand if on_photo else Box(cand.x - pad * .5, cand.y - pad * .5, cand.w + pad, cand.h + pad)   # breathing room off the photo
            if any(cand.inter(q) > 0 for _, q in parts) or any(room.inter(o) > 0 for o in others):
                continue
            dark = None
            if not on_photo:
                if cand.inter(photo) > 0 or any(cand.inter(Box.of(m['box'])) > 0 for m in out.values()
                                                if m['type'] == 'image' and not m.get('hidden') and 'box' in m):
                    continue
                under = next((f for b_, f in reversed(fills) if b_.inter(cand) >= cand.area * .99), page_bg)
                if (contrast(ink, under) or 0) < 3:
                    dark = max(inks, key=lambda c_: contrast(c_, under) or 0, default=None)
                    if not dark or (contrast(dark, under) or 0) < 3:
                        continue
            dx, dy = nx - lb.x, ny - lb.y
            for m in mem:
                b = m['box']
                m['box'] = [round(b[0] + dx, 2), round(b[1] + dy, 2), b[2], b[3]]
                if not on_photo and dark and m['type'] == 'text':
                    m.setdefault('style', {})['color'] = dark
            if not on_photo:   # an earlier note said it stays on the photo; it doesn't any more
                reasons[:] = [r for r in reasons if not r.startswith('Logo stays on the photo')]
            reasons.append('Logo moved to a clear corner so it stays off the photo subject.' if on_photo
                           else 'Logo moved off the photo to a clear corner of the page so it stays off the subject.')
            break


def _rescue_logo(out: dict, a: dict, g, W: float, H: float, reasons: list):
    """A logo the copy area had no room for goes on the photo instead, small, in a corner clear of the subject
    and of everything else (the brand stays in every size). Ink colour is settled afterwards by the photo
    legibility pass."""
    roles = {k: v['role'] for k, v in a['roles'].items()}
    photos = [Box.of(n['box']) for n in out.values() if n['type'] == 'image' and not n.get('hidden') and 'box' in n
              and roles.get(n['id']) not in ('logo', 'decoration') and n['box'][2] * n['box'][3] >= W * H * .2]
    if not photos:
        return
    parts = [q for _, q in subject_boxes(out, a)]
    k = min(W / g.width, H / g.height)
    for gr in a['groups']:
        if gr['role'] != 'logo' or len(gr['members']) != 1:
            continue
        nid = gr['members'][0]
        n, src = out.get(nid), g.by_id.get(nid)
        if not n or not n.get('hidden') or src is None:
            continue
        if n['type'] == 'text':
            style = dict(n.get('style') or {})
            fs = max(MIN_TEXT * 1.05, float(style.get('fontSize') or 12) * k)
            lw = text_width(n.get('text', ''), fs, style) + 2
            lh = fs * float(style.get('lineHeight') or 1.15)
        else:
            lh = max(14.0, src.box.h * k)
            lw = lh * src.box.w / max(1.0, src.box.h)
        others = [Box.of(m['box']) for m in out.values() if not m.get('hidden') and 'box' in m and m['id'] != nid
                  and m['type'] in ('text', 'shape') and roles.get(m['id']) not in ('background', 'panel', 'decoration')]
        done = False
        for ph in sorted(photos, key=lambda b_: -b_.area):
            pad = max(4.0, min(ph.w, ph.h) * .05)
            if lw + 2 * pad > ph.w * .6 or lh + 2 * pad > ph.h * .3:
                continue
            for x, y in ((ph.x + pad, ph.y + pad), (ph.r - pad - lw, ph.y + pad), (ph.x + pad, ph.b - pad - lh), (ph.r - pad - lw, ph.b - pad - lh)):
                cand = Box(x, y, lw, lh)
                room = Box(x - pad * .5, y - pad * .5, lw + pad, lh + pad)
                if x < 0 or y < 0 or cand.r > W or cand.b > H or any(cand.inter(q) > 0 for q in parts) \
                        or any(room.inter(o) > 0 for o in others):
                    continue
                n['box'] = [round(x, 2), round(y, 2), round(lw, 2), round(lh, 2)]
                n['hidden'] = False
                if n['type'] == 'text':
                    n['style'] = {**(n.get('style') or {}), 'fontSize': round(fs, 2), 'align': 'left'}
                kept = []
                for r in reasons:
                    if r.startswith('Logo dropped') or r.startswith('Logo joins the row'):
                        continue
                    if r.startswith('Dropped to make room:'):     # the logo is back: take it off that list
                        names = [x.strip(' .') for x in r.split(':', 1)[1].split(',')]
                        names = [x for x in names if x and x != 'logo']
                        if not names:
                            continue
                        r = 'Dropped to make room: ' + ', '.join(names) + '.'
                    kept.append(r)
                reasons[:] = kept
                reasons.append('Logo kept on a clear corner of the photo: the copy had no room for it at this size.')
                done = True
                break
            if done:
                break


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
        given = g.by_id[nid].crop
        same_slot = (abs(W - g.width) < .5 and abs(H - g.height) < .5
                     and all(abs(u - v) < .5 for u, v in zip(nb, ob.list())))
        if given and same_slot and sub.get('source') != 'whole':
            # original size, photo where the designer put it: keep their framing
            n['crop'] = list(given)
            crops[nid] = 1.0
            reasons.append('Photo kept as the designer framed it.')
            continue
        c = smart_crop(sub['box'], img_aspect, slot, sub.get('parts'), **crop_kw(sub, scored=True))
        original_size = abs(W - g.width) < .5 and abs(H - g.height) < .5
        if same_slot and not given and sub.get('source') not in ('whole', 'focus'):
            # original size, photo where the designer put it: show it exactly as the design does (centred cover)
            cw, ch = (slot / img_aspect, 1.0) if img_aspect > slot else (1.0, img_aspect / slot)
            crop = [(1 - cw) / 2, (1 - ch) / 2, cw, ch]
            ps = sub.get('parts') or [sub['box']]
            tot = sum(p[2] * p[3] for p in ps) or 1.0
            inside = sum(max(0.0, min(p[0] + p[2], crop[0] + cw) - max(p[0], crop[0])) *
                         max(0.0, min(p[1] + p[3], crop[1] + ch) - max(p[1], crop[1])) for p in ps)
            if inside / tot >= c['kept'] - .02:     # only when it shows the subject as well as the smart crop
                c = {'crop': [round(v, 4) for v in crop], 'kept': inside / tot}
        if nid in a['layers']['background'] and sub.get('source') != 'assumed' and not original_size:
            # copy sits on this photo: reframe so the subject is clear of it
            nbx = Box.of(nb)
            avoid = []
            for m in out.values():
                if m.get('hidden') or m['type'] in ('group', 'image') or m['id'] == nid or 'box' not in m:
                    continue
                if a['roles'].get(m['id'], {}).get('role') in ('background', 'panel', 'decoration'):
                    continue
                q = Box.of(m['box'])
                if q.inter(nbx) > 0:
                    avoid.append([(q.x - nbx.x) / nbx.w, (q.y - nbx.y) / nbx.h, q.w / nbx.w, q.h / nbx.h])
            r = reframe(sub['box'], img_aspect, slot, sub.get('parts'), avoid)
            if r['crop'] != c['crop']:
                reasons.append('Photo reframed so its subject sits clear of the copy.')
            c = r
        n['crop'] = c['crop']
        # scored like the naive resizes: the share of what the ORIGINAL showed of the subject
        # (a designer may have framed only part of it)
        crops[nid] = c['kept'] if sub.get('source') == 'whole' else \
            min(1.0, c['kept'] / max(sub.get('kept') or 1.0, 1e-6))      # 'keep whole' means the whole image
        src = sub.get('source')
        what = {'focus': 'your focus area', 'faces': 'the faces', 'people': 'the people'}.get(src, 'the main subject')
        plural = src in ('faces', 'people')
        if src == 'whole':
            if c['kept'] < .999:
                reasons.append(f"Only {c['kept'] * 100:.0f}% of the photo fits this shape.")
        elif src != 'assumed' and c['kept'] >= .999:
            reasons.append(f"Photo cropped so {what} {'stay' if plural else 'stays'} fully in view.")
        elif src != 'assumed':
            reasons.append(f"Photo cropped around {what}; {c['kept'] * 100:.0f}% of {'them' if plural else 'it'} fits this shape.")
    _rescue_logo(out, a, g, W, H, reasons)
    if not (abs(W - g.width) < .5 and abs(H - g.height) < .5):     # at the original size the designer placed it
        _logos_off_subjects(out, a, W, H, reasons, (design.get('page') or {}).get('background') or '#ffffff')
    nodes = [out[n['id']] for n in design['nodes']]
    if not (abs(W - g.width) < .5 and abs(H - g.height) < .5 and a.get('_pinned_crop')):
        _legible_on_photos(nodes, a, W, H, reasons)       # (a photo the designer framed keeps their colours)
    for n in nodes:      # photos are not repeated per size: the client re-attaches them by id
        if n.get('src'):
            n.pop('src')
            n['srcFrom'] = n['id']
    roles = {k: v['role'] for k, v in a['roles'].items()}
    gone = []
    for n in nodes:     # nothing degenerate or entirely outside the canvas is ever drawn
        if n['type'] == 'group' or n.get('hidden'):
            continue
        x, y, w, h = n['box']
        if not all(map(math.isfinite, n['box'])) or w < .5 or h < .5 or x >= W or y >= H or x + w <= 0 or y + h <= 0:
            n['hidden'] = True
            if roles.get(n['id']) not in ('decoration', 'background', 'panel'):
                gone.append(roles.get(n['id']) or n['type'])
    if gone:
        reasons.append('No room at this size for: ' + ', '.join(dict.fromkeys(gone)) + '.')
    adapted = {'format': 'chameleon-graph/1', 'name': design.get('name', ''),
               'page': {**design['page'], 'width': W, 'height': H}, 'nodes': nodes}
    c = check(adapted, a, crops)
    if not c['ok']:
        bits = []
        if c['small_text']: bits.append(f"{len(c['small_text'])} text under 12 px")
        if c['off_canvas']: bits.append(f"{len(c['off_canvas'])} off canvas")
        if c['overlaps']: bits.append(f"{len(c['overlaps'])} overlap{'s' if len(c['overlaps']) > 1 else ''}")
        if c.get('low_contrast'): bits.append(f"{len(c['low_contrast'])} hard to read on its background")
        reasons.append('This size is too small to fit the content cleanly: ' + ', '.join(bits) + '.')
    return {'design': adapted, 'reasons': reasons, 'checks': c}


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
    # buttons side by side in the design (a primary and a secondary action) move as one row of pills:
    # they stay side by side when the column is wide enough and stack, left-aligned, when it isn't
    def one_pill(gr):
        return gr['kind'] == 'button' and gr['id'] not in rep_of and \
            sum(1 for m in gr['members'] if g.by_id[m].type == 'shape') == 1 and \
            sum(1 for m in gr['members'] if g.by_id[m].type == 'text') == 1
    merged, skip = [], set()
    for i, gr in enumerate(groups):
        if gr['id'] in skip:
            continue
        if one_pill(gr):
            row = [gr]
            for nx in groups[i + 1:]:
                b0, b1 = Box.of(row[-1]['box']), Box.of(nx['box'])
                if one_pill(nx) and min(b0.b, b1.b) - max(b0.y, b1.y) > .5 * min(b0.h, b1.h) and b1.x > b0.r - 1:
                    row.append(nx)
                else:
                    break
            if len(row) > 1:
                skip.update(x['id'] for x in row)
                gr = {**gr, 'members': [m for x in row for m in x['members']],
                      'box': Box.bound([Box.of(x['box']) for x in row]).list(), 'anchors': gr.get('anchors') or []}
        merged.append(gr)
    groups = merged
    items, seen = [], set()
    for gr in groups:
        bid = rep_of.get(gr['id'])
        if bid is None:
            items.append(Item(gr, g, roles))
        elif bid not in seen:
            seen.add(bid)
            blk = next(b for b in a['blocks'] if b['id'] == bid)
            items.append(RepeatItem([by_id[x] for x in blk['groups']], g, roles))
    # an item that sat to the right of another on the same row (a second button) lines up with that one
    # when the flow stacks them; its own position on the old row says nothing about the column's alignment
    for i, it in enumerate(items):
        if isinstance(it, RepeatItem):
            continue
        for prev in items[:i]:
            if isinstance(prev, RepeatItem):
                continue
            ov = min(it.box.b, prev.box.b) - max(it.box.y, prev.box.y)
            if ov > .5 * min(it.box.h, prev.box.h) and it.box.x > prev.box.x:
                it.align = prev.align
                break
    return items


def adapt_one(design: dict, g, a: dict, target: dict, base_overlaps: set = frozenset()) -> dict:
    res = _adapt_one(design, g, a, target, base_overlaps)
    attach_scores(res, design, a)
    return res


def attach_scores(res: dict, original: dict, a: dict):
    """Score Chameleon and the three naive resizes the same way (engine/score.py)."""
    from .score import score, baseline_designs
    W, H = res['width'], res['height']
    allowed = a.get('_base_overlaps', set())
    has_subject = bool(a['subjects'])
    kept_c = res['checks'].get('subject_kept')
    if has_subject and kept_c is None:
        kept_c = 0.0                       # every photo was dropped: its subject is lost
    res['score'] = score(res['design'], original, a, 1.0, kept_c, allowed)
    for name, (d, distortion, frame) in baseline_designs(original, W, H).items():
        kept = res['baselines']['crop']['subject_kept'] if name == 'crop' else (1.0 if has_subject else None)
        res['baselines'].setdefault(name, {})['score'] = score(d, original, a, distortion, kept, allowed, frame)


def _adapt_one(design: dict, g, a: dict, target: dict, base_overlaps: set = frozenset()) -> dict:
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
            if same and res.get('exact'):
                kept_msg = 'Original size: layout kept as designed.'
            elif same:
                kept_msg = 'Original size: layout kept, with what breaks a rule here fixed (text raised to 12 px, nothing off the canvas).'
            else:
                kept_msg = 'Layout kept: each element stays near the edge it was on, and text re-wraps to fit.'
            reasons = [head, kept_msg]
            if abs(res['k'] - s) / max(s, 1e-6) > .03:
                reasons.append(f"Text set {'larger' if res['k'] > s else 'smaller'} than a plain resize ({res['k'] / s * 100:.0f}%) so it fills the new shape.")
            res['reasons'] = list(dict.fromkeys(reasons + res['reasons']))
            res.pop('k')
            res.pop('exact', None)
            kept = res['checks'].get('subject_kept')
            from .score import _subject_under_copy
            under = _subject_under_copy({n['id']: n for n in res['design']['nodes']}, a) if a['subjects'] else 0.0
            # copy sits on the (new) photo's subject. At the original size the designer may have put it there on
            # purpose (snow_cabins: 36% of the cabins): only more than 40% cover there (a dropped-in photo) re-lays it out
            # (the Studio labels a photo the user dropped in 'your photo': the copy was never placed for it)
            people = any(sub.get('source') in ('faces', 'people') for sub in a['subjects'].values())
            dropped_in = any(((g.by_id[i].meta or {}).get('label') == 'your photo') for i in a['subjects'] if i in g.by_id)
            covered = under > max(.25 if (people or dropped_in or not same) else .4, a.get('_orig_under', 0.0) + .1)
            whole = any(sub.get('source') == 'whole' for sub in a['subjects'].values())
            if ((not same or whole) and kept is not None and kept < (.98 if whole else .9)) or covered:
                # keeping the layout loses most of the photo's subject (a wide scene in a tall story):
                # also try the rebuilt layout and keep whichever scores higher
                alt = reflow_one(design, g, a, W, H, 2)
                alt = _pick_layout(alt, design, g, a, W, H, 2)
                alt.pop('alternatives', None)
                alt['reasons'] = list(dict.fromkeys([head] + alt['reasons']))
                res = _tall_variants(alt, design, g, a, W, H, 2, head, kept_layout=res, kept_last=whole)
                res = _fill_variants(res, design, g, a, W, H, head)
            res.pop('_args', None)
            return {**meta, **res}
    res = reflow_one(design, g, a, W, H, tier)
    res = _pick_layout(res, design, g, a, W, H, tier)
    res['reasons'] = list(dict.fromkeys([head] + res['reasons']))
    if W / H < .8 and not res.get('alternatives'):
        res = _tall_variants(res, design, g, a, W, H, tier, head)
    elif .8 <= W / H < 1.25 and a['style']['structure'] == 'overlay' and a['subjects'] and not res.get('alternatives'):
        cands = [('Copy over the photo', res)]
        alt = reflow_one(design, g, a, W, H, tier, side=True)
        if any('side panel' in r for r in alt['reasons']):
            cands.append(('Photo beside the copy', alt))
        if min(W, H) < 400 and any(gr['role'] == 'logo' for gr in a['groups']) and \
                any(r.startswith('Dropped to make room') for r in res['reasons']):
            cands.append(('Logo on the button row', reflow_one(design, g, a, W, H, tier, logo_by_cta=True)))
        for _, c in cands[1:]:
            c['reasons'] = list(dict.fromkeys([head] + c['reasons']))
        if len(cands) > 1:
            res, _, _ = _best_of(cands, design, a)
    elif tier == 2 and W / H >= 1.25 and a['style']['structure'] == 'overlay' and a['subjects'] and not res.get('alternatives'):
        # a wide canvas: try both the photo full-bleed with the copy over its quiet side, and the photo as a panel
        panel = any('side panel' in r for r in res['reasons'])
        alt = reflow_one(design, g, a, W, H, tier, keep_bleed=True) if panel else reflow_one(design, g, a, W, H, tier, side=True)
        if panel != any('side panel' in r for r in alt['reasons']):
            alt['reasons'] = list(dict.fromkeys([head] + alt['reasons']))
            first = 'Photo beside the copy' if panel else 'Copy over the photo'
            res, _, _ = _best_of([(first, res), ('Copy over the photo' if panel else 'Photo beside the copy', alt)], design, a)
    res = _fill_variants(res, design, g, a, W, H, head)
    for alt in res.get('alternatives', []):
        alt['reasons'] = list(dict.fromkeys([head] + alt['reasons']))
    res.pop('_args', None)
    return {**meta, **res}


FILL_LABEL = {'type': 'Bigger type', 'space': 'Even spacing', 'photo': 'Bigger photo'}


def _fill_variants(res: dict, design: dict, g, a: dict, W: float, H: float, head: str) -> dict:
    """The chosen layout leaves a dead area: also try it with bigger type and with the message spread out,
    score them, keep the best (the rest go under 'Layouts tried')."""
    args = res.get('_args')
    if not args or args.get('fill'):
        return res
    sc = _quick_score(res, design, a)
    panel = any('side panel' in r or 'panel at the' in r for r in res['reasons']) and not args.get('tall')
    empty = any(n.startswith('An empty area') for n in sc.get('notes', []))
    cut = panel and (res['checks'].get('subject_kept') or 1.0) < .9      # the photo panel cuts its subject
    if not (empty or cut):
        return res
    base = {k_: v for k_, v in args.items() if k_ not in ('fill', 'tier')}
    old = res.pop('alternatives', [])
    cands = [(res.get('layout_label') or 'Layout rebuilt', res)]
    fills = ['type', 'space'] if empty else []
    if panel:
        fills.append('photo')
    for f in fills:
        alt = reflow_one(design, g, a, W, H, args['tier'], fill=f, **base)
        alt['reasons'] = list(dict.fromkeys([head] + alt['reasons']))
        same = [n.get('box') for n in alt['design']['nodes']] == [n.get('box') for n in res['design']['nodes']]
        if alt['checks']['ok'] and not same:          # an identical layout is not another option
            cands.append((f"{cands[0][0]} · {FILL_LABEL[f].lower()}" if res.get('layout_label') else FILL_LABEL[f], alt))
    if len(cands) == 1:
        if old:
            res['alternatives'] = old
        return res
    chosen, best, first = _best_of(cands, design, a, .2)
    if chosen is not res:
        chosen['reasons'] = list(dict.fromkeys(chosen['reasons'] + [
            f"{FILL_LABEL[chosen['_args']['fill']]} fills the empty space better."]))
    seen = {lab for lab in (x['label'] for x in chosen.get('alternatives', []))}
    chosen['alternatives'] = chosen.get('alternatives', []) + [x for x in old if x['label'] not in seen and x['design'] is not chosen['design']]
    return chosen


def _best_of(cands: list, design: dict, a: dict, margin: float = 1.0) -> dict:
    """cands: [(label, result)], the first is the default. Score each; a later one wins only if its checks pass
    and it scores more than a point higher. The others are kept as alternatives."""
    scored = [(lab, r, _quick_score(r, design, a)) for lab, r in cands]
    best = scored[0]
    # among the rebuilt variants the best score wins; the default (the designer's own layout, or the rules'
    # first choice) is only replaced when one beats it by more than a point
    rivals = [c for c in scored[1:] if c[1]['checks']['ok']]
    hi = max((c[2]['overall'] for c in rivals), default=None)
    top = next((c for c in rivals if c[2]['overall'] >= hi - .3), None) if rivals else None   # near-ties: the earlier one
    if top is not None and top[2]['overall'] > best[2]['overall'] + margin:
        best = top
    chosen = best[1]
    chosen['layout_label'] = best[0]
    chosen['alternatives'] = [{'label': lab, 'design': r['design'], 'reasons': r['reasons'], 'checks': r['checks'],
                               'score_overall': round(sc['overall'], 1), 'score': sc}
                              for lab, r, sc in scored if r is not chosen and r['checks']['ok']]
    return chosen, best, scored[0]


TALL_LABEL = {None: 'Photo panel', 'frame': 'Photo framed in the middle', 'blur': 'Photo on a blurred fill'}


def _tall_variants(res: dict, design: dict, g, a: dict, W: float, H: float, tier: int, head: str,
                   kept_layout: dict | None = None, kept_last: bool = False) -> dict:
    """A full-bleed photo that had to become a panel on a tall canvas: also try it framed in the middle and on a
    blurred fill of itself, plus (tier 1) the layout as designed; keep the best."""
    cands = []
    if kept_layout is not None:
        cands.append(('Layout kept', kept_layout))
    if any('panel at the' in r for r in res['reasons']):
        cands.append((TALL_LABEL[None], res))
        for mode in ('frame', 'blur'):
            alt = reflow_one(design, g, a, W, H, tier, tall=mode)
            alt['reasons'] = list(dict.fromkeys([head] + alt['reasons']))
            cands.append((TALL_LABEL[mode], alt))
    elif kept_layout is None:
        return res
    else:
        cands.append((res.get('layout_label') or ('Copy moved off the subject' if a['style']['structure'] == 'overlay'
                                                  else 'Layout rebuilt'), res))
    if kept_last and kept_layout is not None:
        # 'keep whole photo': the designer asked for all of it, so the rebuilt layouts come first and the
        # cropped original layout has to clearly beat them
        cands = cands[1:] + cands[:1]
    chosen, best, first = _best_of(cands, design, a, 1.0 if kept_layout is not None else .3)
    if kept_last and kept_layout is not None and chosen is not kept_layout:
        kk = kept_layout['checks'].get('subject_kept') or 0
        chosen['reasons'] = list(dict.fromkeys(chosen['reasons'] + [
            f"Keeping the layout would show only {kk * 100:.0f}% of the photo, and all of it was asked for, so the layout was rebuilt."]))
    elif kept_layout is not None and chosen is not kept_layout:
        kk = kept_layout['checks'].get('subject_kept')
        why = (f"Keeping the layout would show only {kk * 100:.0f}% of the photo's subject"
               if kk is not None and kk < .9 else "Keeping the layout would put the copy on the photo's subject")
        chosen['reasons'] = list(dict.fromkeys(chosen['reasons'] + [
            f"{why}, so the layout was rebuilt."]))
    return chosen


LAYOUT_LABEL = {('photo', 'beside'): 'Photo beside the copy', ('photo', 'above'): 'Photo above the copy',
                ('cards', 'beside'): 'Cards beside the copy', ('cards', 'below'): 'Cards under the copy'}


def _quick_score(res: dict, original: dict, a: dict) -> float:
    from .score import score
    kept = res['checks'].get('subject_kept')
    if a['subjects'] and kept is None:
        kept = 0.0
    return score(res['design'], original, a, 1.0, kept, a.get('_base_overlaps', set()))


def _label_wraps(res: dict, a: dict) -> bool:
    """An eyebrow or tag line broken over two lines ('15-MINUTE / DINNER') reads as a mistake."""
    for n in res['design']['nodes']:
        if n['type'] != 'text' or n.get('hidden') or a['roles'].get(n['id'], {}).get('role') not in ('eyebrow', 'badge'):
            continue
        fs = drawn_size(n)
        if fs and n['box'][3] > fs * float((n.get('style') or {}).get('lineHeight') or 1.15) * 1.6:
            return True
    return False


def _pick_layout(res: dict, design: dict, g, a: dict, W: float, H: float, tier: int) -> dict:
    """Candidate layouts: the rules' choice and the other family (photo beside vs above, cards beside vs under).
    Each is scored; the best is shown and the others are kept as alternatives."""
    lay = res.get('layout') or {}
    aspect = W / H
    tries = []
    if lay.get('photo') and .6 <= aspect <= 2.6:
        tries.append(('photo', 'above' if lay['photo'] == 'beside' else 'beside', {'orient': 'above' if lay['photo'] == 'beside' else 'beside'}))
    if lay.get('cards') and .6 <= aspect <= 2.6:
        tries.append(('cards', 'below' if lay['cards'] == 'beside' else 'beside', {'cards_beside': lay['cards'] == 'below'}))
    if not tries:
        return res
    key = 'photo' if lay.get('photo') else 'cards'
    cands = [(LAYOUT_LABEL[(key, lay[key])], res)]
    for kind, val, kw in tries:
        alt = reflow_one(design, g, a, W, H, tier, **kw)
        if (alt.get('layout') or {}).get(kind) == val:       # the forced family really happened
            cands.append((LAYOUT_LABEL[(kind, val)], alt))
    for i, (lab, r) in enumerate(cands):
        # photo above the copy leaves the copy too little room (text under 12 px, items dropped): a shorter photo
        if (r.get('layout') or {}).get('photo') == 'above' and (not r['checks']['ok'] or r['checks']['dropped']):
            for cap in (.5, .42):
                alt = reflow_one(design, g, a, W, H, tier, orient='above', photo_max=cap)
                if (alt.get('layout') or {}).get('photo') == 'above' and alt['checks']['ok'] and \
                        (not r['checks']['ok'] or len(alt['checks']['dropped']) < len(r['checks']['dropped'])):
                    if i == 0:
                        alt['reasons'] = alt['reasons'] + ['Photo kept shorter so the message fits below it.']
                    cands[i] = (lab, alt)
                    break
            break
    for lab, r in list(cands):
        # photo beside the copy cuts too much of a wide subject: also try a wider photo column
        if (r.get('layout') or {}).get('photo') == 'beside' and (r['checks'].get('subject_kept') or 1) < .75:
            alt = reflow_one(design, g, a, W, H, tier, orient='beside', wide_photo=True)
            if (alt.get('layout') or {}).get('photo') == 'beside' and not _label_wraps(alt, a) and \
                    (alt['checks'].get('subject_kept') or 0) > (r['checks'].get('subject_kept') or 0) + .05:
                cands.append((LAYOUT_LABEL[('photo', 'beside')] + ' · wider photo', alt))
            break
    def lost_key(r):          # the headline or the button gone: not a layout worth offering
        return any(a['roles'].get(i, {}).get('role') in ('headline', 'cta') for i in r['checks'].get('dropped', []))
    cands = cands[:1] + [c for c in cands[1:] if not lost_key(c[1])]
    full = [(lab, r, _quick_score(r, design, a)) for lab, r in cands]
    scored = [(lab, r, sc['overall']) for lab, r, sc in full]
    full_by_id = {id(r): sc for _, r, sc in full}
    best = scored[0]
    for c in scored[1:]:
        if c[1]['checks']['ok'] and c[2] > best[2] + 1.0:
            best = c
    chosen = best[1]
    if best is not scored[0]:
        chosen['reasons'] = chosen['reasons'] + [f"{best[0]} scores higher here ({best[2]:.0f} vs {scored[0][2]:.0f}), so it was chosen."]
    chosen['alternatives'] = [{'label': lab, 'design': r['design'], 'reasons': r['reasons'], 'checks': r['checks'],
                               'score_overall': round(sc, 1), 'score': full_by_id[id(r)]}
                              for lab, r, sc in scored if r is not chosen and r['checks']['ok']]
    chosen['layout_label'] = best[0]
    return chosen


KEY_ROLES = ('headline', 'cta', 'logo', 'offer', 'price')


def reflow_one(design: dict, g, a: dict, W: float, H: float, tier: int, **kw) -> dict:
    """Re-flow at this size. Big type keeps a raised floor (see Item.floor_of) unless that costs the headline,
    the button, the logo, an offer or a price: then the plain 12 px floor is used."""
    res = _reflow_one(design, g, a, W, H, tier, **kw)
    def lost(r):
        return sum(1 for i in r['checks'].get('dropped', []) if a['roles'].get(i, {}).get('role') in KEY_ROLES)
    if lost(res):
        alt = _reflow_one(design, g, a, W, H, tier, hier=False, **kw)
        if lost(alt) < lost(res):
            return alt
    return res


def _reflow_one(design: dict, g, a: dict, W: float, H: float, tier: int, orient=None, cards_beside=None, tall=None,
                side=False, logo_by_cta=False, fill=None, keep_bleed=False, wide_photo=False, photo_max=None,
                hier=True) -> dict:
    """`orient` ('beside'/'above') and `cards_beside` force a layout family; None lets the rules choose.
    `tall` ('frame' / 'blur') changes how a full-bleed photo that must become a panel sits on a tall canvas:
    'frame' puts the photo in the middle with the message above and the button below; 'blur' keeps the panel
    and fills the page behind it with a blurred, darkened copy of the same photo.
    `fill` ('type' / 'space') is for canvases where the copy leaves dead space: 'type' starts the type bigger
    (the fit loop still shrinks it to fit), 'space' opens up the gaps between the lines of the message."""
    args = dict(orient=orient, cards_beside=cards_beside, tall=tall, side=side, logo_by_cta=logo_by_cta, keep_bleed=keep_bleed,
                wide_photo=wide_photo, photo_max=photo_max)
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
            # photos side by side as one series ('Summer or snow?': one photo each): they move as one picture area
            # and are split again in the new slot, so neither gets dropped as a small extra
            rep = next((b for b in a.get('blocks', []) if b['kind'] == 'repeat' and hero and hero['id'] in b['groups']), None)
            mates = [gr for gr in cands if rep and gr is not hero and gr['id'] in rep['groups']
                     and gr['box'][2] * gr['box'][3] >= hero['box'][2] * hero['box'][3] * .6] if hero else []
            if mates and len(mates) <= 2:
                series = sorted([hero] + mates, key=lambda gr: (gr['box'][1], gr['box'][0]))
                hero = {**hero, 'box': Box.bound([Box.of(gr['box']) for gr in series]).list(), '_series': series}
    logo = [gr for gr in a['groups'] if gr['role'] == 'logo']
    legal = [gr for gr in a['groups'] if gr['role'] == 'legal']
    used = {gr['id'] for gr in ([hero] if hero else []) + logo + legal + ((hero or {}).get('_series') or [])}
    copy_groups = [gr for gr in a['groups'] if gr['id'] not in used and gr['role'] != 'background']
    order = {gid: i for i, gid in enumerate(a['reading_order'])}
    copy_groups.sort(key=lambda gr: order.get(gr['id'], 99))

    content = Box(m, m, W - 2 * m, H - 2 * m)
    aspect = W / H
    photo_mode = None
    photo_region = None
    copy_region = content

    if hero:
        hb = Box.of(hero['box'])
        bleed = sum([hb.x <= 1, hb.y <= 1, hb.r >= g.width - 1, hb.b >= g.height - 1]) >= 2
        horizontal = aspect >= 1.25 or (aspect > .8 and a['style']['structure'] == 'split-horizontal')
        if orient is not None:
            horizontal = orient == 'beside'
        photo_mode = 'beside' if horizontal or (tier == 3 and aspect > 3 and orient is None) else 'above'
        if tier == 3 and aspect > 3 and orient is None:
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
                reasons.append('On a banner this wide the photo becomes a small picture at the ' + ('left.' if left else 'right.'))
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
            # size the photo column to its subject: narrower for a tall subject, wider for a wide one
            # (two people, a bowl and a lemon), keeping at least 40% of the width for the copy
            sub = a['subjects'].get(hero['members'][0])
            copy_min = max(W * (.28 if aspect >= 1.6 else .32), min(W * .6, 150.0))   # the copy needs real width, even on small canvases
            if wide_photo:                   # a wide subject on a small canvas: the copy gives up some width (and type size)
                # (never so narrow that an eyebrow or tag line has to break)
                tags = [n for n in g.leaves() if n.type == 'text' and roles.get(n.id) in ('eyebrow', 'badge') and n.text]
                need = max((text_width(n.text, MIN_TEXT, n.style) * 1.04 for n in tags), default=0.0)
                copy_min = max(W * (.28 if aspect >= 1.6 else .36), 110.0, need)
            max_nw = max(W * .2, W - 3 * m - copy_min)
            if sub and sub.get('source') != 'assumed':
                img_aspect = sub.get('aspect') or hb.w / max(1.0, hb.h)
                w0 = photo_region.w
                best = None
                w0 = min(w0, max_nw)
                for i in range(17):
                    nw = W * (.2 + .025 * i)           # 20% ... 60% of the canvas
                    if nw > max_nw + .5:
                        break
                    kept = smart_crop(sub['box'], img_aspect, nw / max(1.0, photo_region.h), sub.get('parts'), **crop_kw(sub))['kept']
                    key = (round(kept / .03), -abs(nw - w0))
                    if best is None or key > best[0]:
                        best = (key, nw)
                nw = best[1] if best else w0
            else:
                nw = min(photo_region.w, max_nw)
            if True:
                if left:
                    photo_region = Box(photo_region.x, photo_region.y, nw, photo_region.h)
                    copy_region = Box(photo_region.r + m, copy_region.y, W - photo_region.r - 2 * m, copy_region.h)
                else:
                    photo_region = Box(photo_region.r - nw, photo_region.y, nw, photo_region.h)
                    copy_region = Box(copy_region.x, copy_region.y, photo_region.x - m - copy_region.x, copy_region.h)
            if a['style']['structure'] != 'split-horizontal':
                reasons.append('Photo and copy placed side by side for the wider shape.')
        else:
            top = not (hb.cy > g.height * .6 and a['style']['structure'] == 'stacked')
            frac = .34 if tier == 3 else min(.55, max(.38, hb.h / g.height if a['style']['structure'] == 'stacked' else .45))
            ph = H * frac
            photo_region = Box(0 if bleed else m, 0 if (bleed and top) else (m if top else H - ph - m),
                               W if bleed else W - 2 * m, ph - (0 if bleed else m))
            if not top and bleed:
                photo_region = Box(0, H - ph, W, ph)
            # size the photo row to its subject too (a spread flat-lay, a group): taller when that keeps more of it,
            # leaving at least 36% of the height for the copy
            sub = a['subjects'].get(hero['members'][0])
            if sub and sub.get('source') != 'assumed' and tier < 3:
                img_aspect = sub.get('aspect') or hb.w / max(1.0, hb.h)
                h0, best = photo_region.h, None
                for i in range(15):
                    nh = H * (.3 + .025 * i)                 # 30% ... 64% of the height
                    if H - nh < H * .36 or (photo_max and nh > H * photo_max + .5):
                        break
                    kept = smart_crop(sub['box'], img_aspect, photo_region.w / max(1.0, nh), sub.get('parts'), **crop_kw(sub))['kept']
                    key = (round(kept / .03), -abs(nh - h0))
                    if best is None or key > best[0]:
                        best = (key, nh)
                if best and abs(best[1] - h0) > 1:
                    nh = best[1] - (0 if bleed else m)
                    photo_region = Box(photo_region.x, photo_region.y if top else photo_region.b - nh, photo_region.w, nh)
            copy_region = Box(m, photo_region.b + m, W - 2 * m, H - photo_region.b - 2 * m) if top else \
                Box(m, m, W - 2 * m, photo_region.y - 2 * m)
            if a['style']['structure'] == 'split-horizontal':
                reasons.append('Photo and copy stacked for the taller shape.')
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
        hsub = a['subjects'].get(hero['members'][0]) if photo_region else None
        if hsub and hsub.get('source') == 'whole' and hsub.get('aspect'):
            # the designer wants all of the photo: the slot takes the photo's own shape, and the copy gets
            # whatever room that frees (never less than its minimum)
            ia = hsub['aspect']
            if photo_mode == 'beside':
                left = photo_region.x < copy_region.x
                cmin = max(W * .32, min(W * .6, 150.0)) if not (tier == 3 and aspect > 3) else W * .4
                nw = min(max(photo_region.h * ia, W * .12), max(W * .12, W - 3 * m - cmin))
                photo_region = Box(photo_region.x if left else photo_region.r - nw, photo_region.y, nw, photo_region.h)
                copy_region = Box(photo_region.r + m, copy_region.y, W - photo_region.r - 2 * m, copy_region.h) if left \
                    else Box(m, copy_region.y, photo_region.x - 2 * m, copy_region.h)
            else:
                top = photo_region.y < copy_region.y
                nh = min(max(photo_region.w / ia, H * .2), H * (.64 if tier < 3 else .5))
                photo_region = Box(photo_region.x, photo_region.y if top else photo_region.b - nh, photo_region.w, nh)
                copy_region = Box(m, photo_region.b + m, W - 2 * m, H - photo_region.b - 2 * m) if top else \
                    Box(m, m, W - 2 * m, photo_region.y - 2 * m)
            pw, ph = photo_region.w, photo_region.h
            fw, fh = (pw, pw / ia) if pw / ph < ia else (ph * ia, ph)
            photo_region = Box(photo_region.x + (pw - fw) / 2, photo_region.y + (ph - fh) / 2, fw, fh)
            reasons.append('All of the photo is shown, as asked.')
        if photo_region and hero.get('_series'):
            # split the picture area again: side by side when that keeps each slot closer to its photo's shape
            series = hero['_series']
            n_ = len(series)
            gap_ = max(4.0, m * .4)
            pa = sum(Box.of(gr['box']).w / max(1.0, Box.of(gr['box']).h) for gr in series) / n_
            side_w = (photo_region.w - gap_ * (n_ - 1)) / n_
            side_h = (photo_region.h - gap_ * (n_ - 1)) / n_
            err = lambda a_: abs(math.log(max(1e-3, a_) / pa))
            across = err(side_w / max(1.0, photo_region.h)) <= err(photo_region.w / max(1.0, side_h))
            for i, gr in enumerate(series):
                slot = Box(photo_region.x + i * (side_w + gap_), photo_region.y, side_w, photo_region.h) if across else \
                    Box(photo_region.x, photo_region.y + i * (side_h + gap_), photo_region.w, side_h)
                for nid in gr['members']:
                    _set_photo(out, g.by_id[nid], slot.list())
            reasons.append(f'The {n_} photos stay together as a set, ' + ('side by side.' if across else 'one above the other.'))
        elif photo_region:
            for nid in hero['members']:
                _set_photo(out, g.by_id[nid], photo_region.list())

    # --- overlay: copy goes where the photo's subject is not
    overlay_parts: list = []        # where the people/objects of a full-bleed photo land on the canvas
    overlay_panel = None
    frame_regions = None            # 'frame': (above the photo, below the photo)
    backdrop = None                 # 'blur': the photo, blurred, behind everything
    if a['style']['structure'] == 'overlay':
        sub = next(iter(a['subjects'].values()), None)
        bg_img = next((out[i] for i in a['layers']['background'] if out[i]['type'] == 'image'), None)
        if sub and bg_img is not None:
            img_aspect = sub.get('aspect') or (g.by_id[bg_img['id']].box.w / max(1, g.by_id[bg_img['id']].box.h))
            c = smart_crop(sub['box'], img_aspect, W / H, sub.get('parts'), **crop_kw(sub))
            bx, by, bw, bh = sub['box']
            cx_ = ((bx + bw / 2) - c['crop'][0]) / c['crop'][2]
            cy_ = ((by + bh / 2) - c['crop'][1]) / c['crop'][3]
            parts = sub.get('parts') or [sub['box']]

            def on_canvas(pb, crop, frame):
                """A subject part (image-relative) as a box on the canvas, through the crop shown in `frame`."""
                return Box(frame.x + (pb[0] - crop[0]) / crop[2] * frame.w, frame.y + (pb[1] - crop[1]) / crop[3] * frame.h,
                           pb[2] / crop[2] * frame.w, pb[3] / crop[3] * frame.h)

            whole = sub.get('source') == 'whole'
            src_ = sub.get('inner_source') if whole else sub.get('source')
            strict = src_ in ('faces', 'people') or sub.get('faces_in_focus')
            tol = .02 if strict else .15     # never even the edge of a face
            cover_parts = (sub.get('inner') or parts) if whole else parts   # 'whole': copy stays off what's in it

            def covers(region):
                """Would copy in `region` sit on a person or object of the full-bleed photo?"""
                return any(region.inter(q) > q.area * tol for q in (on_canvas(pb, c['crop'], Box(0, 0, W, H)) for pb in cover_parts))

            if aspect >= 1.25:
                region = Box(m, m, W * .5 - 1.5 * m, H - 2 * m) if cx_ >= .5 else Box(W * .5 + m * .5, m, W * .5 - 1.5 * m, H - 2 * m)
            else:
                # the copy band: as tall as it can be while it stays off the photo's subject
                for band in ((.6, .54, .48) if tier < 3 else (.7,)):
                    region = Box(m, H * (1 - band), W - 2 * m, H * band - m) if cy_ < .55 else Box(m, m, W - 2 * m, H * band - m)
                    if not covers(region):
                        break
            fits_whole = abs((W / H) / img_aspect - 1) < .04       # the photo's own shape: full-bleed shows all of it
            if whole and fits_whole:
                c = {**c, 'kept': 1.0}
            if not (keep_bleed and not whole) and (side or (whole and not fits_whole) or (c['kept'] < .8 or covers(region)) and (aspect >= 1.25 or aspect < .8)):
                # the subject can't stay whole behind the copy: the photo becomes a panel sized to keep it,
                # and the copy sits beside it on the page background (`side`: try that on a near-square canvas too)
                wide = aspect >= 1.25 or side
                if whole and not side:
                    wide = img_aspect < aspect          # the side with more room for the photo's own shape
                full = W if wide else H
                best = None
                lo = .08 if (wide and W / H > 3) else .22    # extreme banners: a face-shaped thumbnail is allowed
                hi = .6
                if fill == 'photo':
                    lo, hi = max(lo, .28), .45               # the picture as a real part of the layout, not a sliver
                for i in range(20):
                    size = full * (lo + (hi - lo) / 19 * i)   # lo ... 60% of the long side
                    if full - size < full * .38:
                        break
                    slot = (size / H) if wide else (W / size)
                    kept = smart_crop(sub['box'], img_aspect, slot, sub.get('parts'), **crop_kw(sub))['kept']
                    # keep the most subject, then leave the copy the most room ('photo': give the photo the most)
                    key = (round(kept / .03), size if fill == 'photo' else -size)
                    if best is None or key > best[0]:
                        best = (key, size)
                size = best[1]
                if whole:
                    # the designer wants all of the photo: its slot takes the photo's own shape (never cropped);
                    # as big as leaves the copy at least ~38% of the page
                    need = H * img_aspect if wide else W / img_aspect
                    room = (W - 3 * m - max(W * .32, min(W * .6, 150.0))) if wide else H * .68   # copy keeps its minimum
                    size = min(need, full * .62, room)
                    if need <= min(full * .68, room):
                        size = need          # a few pixels more photo beats thin blurred bars beside it
                if wide:
                    right = cx_ >= .5
                    photo_box = Box(W - size, 0, size, H) if right else Box(0, 0, size, H)
                    copy_region = Box(m, m, W - size - 2 * m, H - 2 * m) if right else Box(size + m, m, W - size - 2 * m, H - 2 * m)
                    reasons.append('Photo moved to a side panel on the ' + ('right' if right else 'left') +
                                   ' so its subject stays whole and clear of the copy; copy sits beside it.')
                elif tall == 'frame':
                    # the whole photo in the middle of the page, the message above it and the button below it
                    below_h = max(H * .13, m * 4)            # just enough for the button, with breathing room
                    y0 = round(H - below_h - size)
                    photo_box = Box(0, y0, W, size)
                    frame_regions = (Box(m, m, W - 2 * m, y0 - 2 * m), Box(m, y0 + size + m * .5, W - 2 * m, below_h - m * 1.5))
                    copy_region = frame_regions[0]
                    reasons.append('Photo framed in the middle of the page so every subject stays whole; '
                                   'headline above it, button below it.')
                else:
                    top = cy_ < .55
                    photo_box = Box(0, 0, W, size) if top else Box(0, H - size, W, size)
                    copy_region = Box(m, size + m, W - 2 * m, H - size - 2 * m) if top else Box(m, m, W - 2 * m, H - size - 2 * m)
                    reasons.append('Photo moved to a panel at the ' + ('top' if top else 'bottom') +
                                   ' so its subject stays whole and clear of the copy; copy sits ' + ('below.' if top else 'above.'))
                    if tall == 'blur':
                        backdrop = {'image': bg_img['id'], 'blur': .04, 'dim': .5}
                        reasons.append('The page behind it is the same photo, blurred and darkened, so the story has no empty space.')
                if whole:
                    # fit the whole photo inside its slot; the rest of the slot shows the same photo blurred
                    pw, ph = photo_box.w, photo_box.h
                    fw, fh = (pw, pw / img_aspect) if pw / ph < img_aspect else (ph * img_aspect, ph)
                    shown = Box(photo_box.x + (pw - fw) / 2, photo_box.y + (ph - fh) / 2, fw, fh)
                    if fw < pw - 1 or fh < ph - 1:
                        backdrop = {'image': bg_img['id'], 'blur': .04, 'dim': .5}
                        reasons.append('All of the photo is shown, as asked; the space around it is the same photo, blurred.')
                    else:
                        reasons.append('All of the photo is shown, as asked.')
                    _set(out, bg_img['id'], shown.list())
                else:
                    _set(out, bg_img['id'], photo_box.list())
                overlay_panel = photo_box
            else:
                copy_region = region
                if aspect >= 1.25:
                    reasons.append('Copy placed on the ' + ('left' if cx_ >= .5 else 'right') + ' half, away from the photo subject.')
                else:
                    reasons.append('Copy placed ' + ('below' if cy_ < .55 else 'above') + ' the photo subject.')
                overlay_parts = [on_canvas(pb, c['crop'], Box(0, 0, W, H)) for pb in cover_parts]

    # a photo that leaves no usable room for the copy goes (copy is the message)
    if photo_region is not None and hero and (copy_region.w < max(40.0, W * .2) or copy_region.h < max(14.0, H * .12)):
        for nid in hero['members']:
            out[nid]['hidden'] = True
        photo_region = None
        copy_region = content
        reasons.append('Photo dropped: no room for it beside the copy at this size.')
    copy_region = Box(copy_region.x, copy_region.y, max(1.0, copy_region.w), max(1.0, copy_region.h))
    items = _copy_items(copy_groups, a, g, roles)
    # the smallest copy text sets the 12 px floor; text the designer made much bigger keeps a higher floor,
    # so a headline never ends up the same size as the line under it when everything is squeezed
    copy_fs = [n.font_size for it in items for n in it.texts if roles.get(n.id) not in ('legal', 'logo', 'decoration')]
    for it in items:
        it.base_fs = min(copy_fs) if (copy_fs and hier) else None
    row = copy_region.w / max(1.0, copy_region.h) > 2.6 and copy_region.h < 260 and W / H >= 1.5   # (not on a near-square ad)

    # --- logo: inside the row on banners, otherwise anchored to a corner of the copy.
    # A light-on-dark logo made to sit on the photo stays on the photo (it would vanish on the copy background).
    page_bg = (design.get('page') or {}).get('background', '#ffffff')

    def on_photo_only(gr):
        nodes_ = [g.by_id[x] for x in gr['members']]
        if len(nodes_) != 1 or nodes_[0].type == 'image':
            return False
        n_ = nodes_[0]
        col = n_.style.get('color', '#111') if n_.type == 'text' else n_.style.get('fill')
        c_ = contrast(col, page_bg)
        return c_ is not None and c_ < 2.5

    recolor = []
    for gr in list(logo):
        if not on_photo_only(gr):
            continue
        logo.remove(gr)
        it = Item(gr, g, roles)
        it.align = 'left'
        k_floor = MIN_TEXT / min(n.font_size for n in it.texts) if it.texts else 12 / max(1.0, it.box.h)
        k_logo = max(s, k_floor)
        lw, lh = it.measure(k_logo, W)
        pad = max(6.0, m * .6) if not photo_region or photo_region.w >= 160 else 4.0   # tight on a thumbnail
        if photo_region and photo_region.w * .5 < lw and photo_region.w > 2 * pad:
            # at most half the photo wide; on a small thumbnail it may use the photo's width rather than go under 12 px
            target = photo_region.w * .5 if k_logo * photo_region.w * .5 / lw >= k_floor else photo_region.w - 2 * pad
            k_logo = max(k_floor, k_logo * min(1.0, target / lw))
            lw, lh = it.measure(k_logo, W)
        thumb = photo_region is not None and (photo_region.w < 200 or photo_region.h < 120)   # would sit on the subject
        if photo_region and not (thumb and it.texts) and lw + 2 * pad <= photo_region.w and lh + 2 * pad <= photo_region.h \
                and it.min_font(k_logo) >= MIN_TEXT * .99 \
                or photo_region and not it.texts and lw + 2 * pad <= photo_region.w and lh + 2 * pad <= photo_region.h:
            right = 'right' in (gr.get('anchors') or []) and 'left' not in (gr.get('anchors') or [])
            x = photo_region.r - pad - lw if right else photo_region.x + pad
            it.place(out, x, photo_region.y + pad, lw, k_logo)
            reasons.append('Logo stays on the photo: it is light artwork made for a dark background.')
        elif it.texts and len(gr['members']) == 1:
            recolor.append(gr)          # a text logo: shown in the design's dark ink on the page instead
        else:
            reasons.append('Logo dropped: it is light artwork made for the photo, and there is no room on the photo here.')
    if recolor:
        inks = [n for n in g.leaves() if n.type == 'text' and roles.get(n.id) in ('headline', 'subhead', 'body')]
        dark = min((n.style.get('color') for n in inks if n.style.get('color')), key=lambda c_: -(contrast(c_, page_bg) or 0), default='#111111')
        for gr in recolor:
            nid = gr['members'][0]
            out[nid].setdefault('style', {})['color'] = dark
            logo.append(gr)
        reasons.append('Logo shown in the design\'s dark ink: its light version would vanish on the page here.')
    if row:
        for gr in logo:
            it = Item(gr, g, roles)
            it.align = 'left'
            items.insert(0, it)
        if logo:
            reasons.append('Logo joins the row so the banner reads left to right.')
    late_logo = list(logo) if (logo_by_cta and not row) else []
    for gr in ([] if row or late_logo else logo):
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
        if overlay_parts and any(Box(x, y, lw, lh).inter(q) > 0 for q in overlay_parts):
            # never on a face: try the other side of the top edge
            for nx in (W - m - lw, m, (W - lw) / 2):
                if not any(Box(nx, y, lw, lh).inter(q) > 0 for q in overlay_parts):
                    x = nx
                    reasons.append('Logo moved to the other corner so it stays off the photo subject.')
                    break
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
    dominant = a['grid'].get('alignment') if a['grid'].get('alignment') in ('left', 'center', 'right') else 'left'
    for it in legal_items:
        it.align = dominant              # a small print line follows the column, not its old corner
        it.force_align = dominant

    # --- copy flow with fitting: start from type sized by area (not by the short side), then shrink and drop
    if tier == 1:
        k = s
    else:
        k = min(s * 2.0, max(s, math.sqrt(W * H / (g.width * g.height))))
    if frame_regions is not None:
        k = s * 1.8           # the message gets the whole space above the photo: start big, the fit loop shrinks it
    if fill in ('type', 'photo') and not row:
        k = min(s * 3.2, k * 1.6)
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
    beside_ok = aspect >= 1.15 and (copy_region.w - m) / 2 >= 150      # each column at least 150 px wide
    if not row and hero is None and a['style']['structure'] != 'overlay' and (beside_ok if cards_beside is None else cards_beside):
        split = next((it for it in items if isinstance(it, RepeatItem) and not it.flex), None)

    def columns():
        if frame_regions is not None:
            below = [it for it in allitems if it.role == 'cta' or it in legal_items]
            above = [it for it in allitems if it not in below]
            if above and below and frame_regions[1].h > 20:
                return [(above, copy_region), (below, frame_regions[1])]
            return [(allitems, copy_region)]
        if split is None or split not in allitems:
            return [(allitems, copy_region)]
        cw_ = (copy_region.w - m) / 2
        left = Box(copy_region.x, copy_region.y, cw_, copy_region.h)
        right = Box(copy_region.x + cw_ + m, copy_region.y, copy_region.w - cw_ - m, copy_region.h)
        split.max_h = right.h
        return [([it for it in allitems if it is not split], left), ([split], right)]

    def fit_all(k_, gap_):
        return all(fits(its, reg, k_, gap_) for its, reg in columns())

    def overflow(k_, gap_):
        """How far the stacked copy runs past its area (px): to see whether shrinking the type still helps."""
        return max((sum(it.measure(k_, reg.w)[1] for it in its) + gap_ * max(0, len(its) - 1) - reg.h
                    for its, reg in columns() if its), default=0.0)

    stall, last_ov = 0, None
    for _ in range(300):
        if fit_all(k, gap):
            break
        smallest = min((it.min_font(k) for it in allitems if it.texts), default=99)
        largest = max((it.display_size(k) if hasattr(it, 'display_size') else it.min_font(k) for it in allitems if it.texts), default=0)
        # small lines are lifted to 12 px when drawn: keep shrinking the big type while that lift stays small
        # (up to a third) and the headline stays clearly the biggest thing, before giving up a line of the message
        hd = [it for it in allitems if it.role == 'headline' and it.texts and hasattr(it, 'display_size')]
        head = max((it.display_size(k) for it in hd), default=99)
        droppable = any(it.role not in protected for it in allitems) or \
            any(it.reflowable() and len(it.texts) > 1 and any(roles.get(n.id) not in protected for n in it.texts) for it in allitems)
        keeps_rank = head * .94 >= MIN_TEXT * 1.3 or not droppable   # the headline stays clearly the biggest line
        if not row:
            ov = overflow(k, gap)
            # shrinking no longer helps (what is too tall is already at its 12 px floor, like cards): drop instead
            stall = stall + 1 if last_ov is not None and ov > last_ov - max(1.0, H * .004) else 0
            last_ov = ov
        if keeps_rank and stall < 6 and (smallest > MIN_TEXT * 1.02 or (smallest >= MIN_TEXT * .74 and largest >= MIN_TEXT * 1.6)):
            k *= .94
            gap = max(gap_base * .4, gap * .97)
            continue
        stall, last_ov = 0, None
        # drop the least important piece: a line inside a text stack, or a whole item
        cand = sorted([it for it in allitems if it.role not in protected], key=lambda it: it.importance())
        lines = [(DROP_ORDER.index(roles.get(n.id, 'body')) if roles.get(n.id, 'body') in DROP_ORDER else 99, it, n)
                 for it in allitems if it.reflowable() and len(it.texts) > 1
                 for n in it.texts if roles.get(n.id) not in protected]
        lines.sort(key=lambda r: r[0])
        # before giving up something that carries the message (offer, subhead, badge...), let oversized display
        # text shrink: a 48h or a 50% OFF can be smaller and still be the biggest thing on the canvas
        nexts = ([lines[0][0]] if lines else []) + ([cand[0].importance()] if cand else [])
        nxt = min(nexts) if nexts else 99
        if nxt >= DROP_ORDER.index('body'):
            for it in allitems:
                it.display_floor = 24.0 if min(W, H) >= 400 else (20.0 if min(W, H) >= 200 else 16.0)   # small ads go lower
            disp = [it for it in allitems if it.reflowable() and it.display_size(k) > it.display_floor + .5]
            shrunk = False
            for big in sorted(disp, key=lambda it: -it.display_size(k)):
                before = big.display_size(k)
                big.xs *= .9
                if big.display_size(k) < before - .01:     # (text already at its floor can't shrink further)
                    shrunk = True
                    break
                big.xs /= .9
            if shrunk:
                continue
        if lines and (not cand or lines[0][0] <= cand[0].importance()):
            _, it, n = lines[0]
            it.dropped.add(n.id)
            dropped.append(roles.get(n.id, 'text'))
            if not it.texts:
                allitems.remove(it)          # nothing left of it: it must not keep its place in the flow
            continue
        if cand:
            victim = cand[0]
            if isinstance(victim, RepeatItem) and victim.can_go_captionless() and not getattr(victim, 'captionless', False):
                victim.go_captionless()
                dropped.append('card captions')
                continue
            if isinstance(victim, RepeatItem) and getattr(victim, 'captionless', False) and not victim.flex \
                    and getattr(victim, 'squeeze', 1.0) > .6:
                victim.squeeze = getattr(victim, 'squeeze', 1.0) * .9   # pictures without captions can just get smaller
                continue
            if isinstance(victim, RepeatItem) and len(victim.cards) > 2:
                victim.cards.pop()          # fewer cards before no cards
                victim.refresh()
                continue
            allitems.remove(victim)
            dropped.extend(_names(victim, roles))
            continue
        if k < s * .3:
            break    # nothing left to drop: stop; the checks report what doesn't fit
        k *= .94
    if not fit_all(k, gap):
        # last resort: the headline alone (then the checks say what still doesn't fit)
        keep = [it for it in allitems if it.role == 'headline'] or allitems[:1]
        for it in allitems:
            if it not in keep:
                dropped.extend(_names(it, roles))
        allitems[:] = keep
        for _ in range(60):
            if fit_all(k, gap) or k < s * .2:
                break
            k *= .94
    if fill == 'space' and not row and fit_all(k, gap):
        # open the message up until it fills most of its area (never more than 3x the usual gap)
        def fits_80(g_):
            return all(fits(its, Box(reg.x, reg.y, reg.w, reg.h * .8), k, g_) for its, reg in columns())
        g0 = gap
        while gap < gap_base * 3 and fits_80(gap * 1.1):
            gap *= 1.1
        if gap > g0 * 1.2:
            reasons.append('Space between the lines opened up so the message fills its area.')
    if dropped:
        reasons.append('Dropped to make room: ' + ', '.join(dict.fromkeys(dropped)) + '.')
    if k > s * 1.05:
        reasons.append(f"Text set larger than a plain resize ({k / s * 100:.0f}%) so it reads well at this size.")
    elif k < s * .95:
        reasons.append(f"Text set smaller than a plain resize ({k / s * 100:.0f}%) so everything fits, never under 12 px.")
    reps = [it for it in allitems if isinstance(it, RepeatItem)]
    for it in reps:
        if len(it.cards) < it.total:
            what = 'items' if it.flex else 'cards'
            reasons.append(f"Showing {len(it.cards)} of {it.total} {what} (the rest don't fit at a readable size).")
    region_of = {id(it): reg for its, reg in columns() for it in its}
    if split is not None and split in allitems:
        reasons.append('Cards placed beside the copy for the wider canvas.')
    for it in reps:
        cols, rows, *_ = it.layout(k, region_of[id(it)].w)
        if (cols, rows) != (it.orig_cols, math.ceil(len(it.cards) / max(1, it.orig_cols))):
            what = 'items' if it.flex else 'cards'
            layout = f"{cols} column{'s' if cols > 1 else ''}" if it.flex else f"{rows} row{'s' if rows > 1 else ''} of up to {cols}"
            reasons.append(f"{len(it.cards)} {what} re-arranged in {layout}.")
    valign = 'center'
    if a['style']['structure'] == 'overlay' or any('bottom' in groups[it.id].get('anchors', [])
                                                  for it in items if it.role == 'headline' and it.id in groups):
        valign = 'bottom' if copy_region.cy > H / 2 else 'top'
    if overlay_panel is not None:
        valign = 'center'          # copy beside / under a photo panel: centred in its own area, no dead half
    if row:
        flow_row(allitems, copy_region, k, gap * 1.5, out)
    elif frame_regions is not None:
        cols = columns()
        for its, reg in cols:
            flow_column(its, reg, k, gap, 'center', out)
        # the message didn't need all the room above the photo: give the slack to the photo (more of the
        # picture, less empty page), as long as the photo still spans the full width uncut
        if not whole and len(cols) > 1:
            above, reg = cols[0]
            placed = [Box.of(out[n.id]['box']) for it in above for n in it.members if not out[n.id].get('hidden')]
            pb = Box.of(out[bg_img['id']]['box'])
            if placed:
                used = Box.bound(placed)
                grow = min(reg.h - used.h - 2 * m, W / max(.01, img_aspect) - pb.h)
                if grow > m:
                    pb = Box(pb.x, pb.y - grow, pb.w, pb.h + grow)
                    _set(out, bg_img['id'], pb.list())
                    overlay_panel = pb
                    flow_column(above, Box(reg.x, reg.y, reg.w, reg.h - grow), k, gap, 'center', out)
    else:
        for its, reg in columns():
            flow_column(its, reg, k, gap, valign, out)
    for it in allitems:
        for nid in it.dropped:
            out[nid]['hidden'] = True
    if late_logo:
        # small ads: the logo shares the button's row (button left, logo right) instead of taking a line
        cta_it = next((it for it in allitems if it.role == 'cta'), None)
        cbox = Box.bound([Box.of(out[n.id]['box']) for n in cta_it.members]) if cta_it else None
        for gr in late_logo:
            it = Item(gr, g, roles)
            it.align = 'left'
            k_logo = max(s, 12 / max(1.0, it.box.h))
            lw, lh = it.measure(k_logo, copy_region.w)
            if cbox is not None and lh > cbox.h:
                k_logo *= cbox.h / lh
                lw, lh = it.measure(k_logo, copy_region.w)
            if cbox is None or cbox.r + gap_base * 2 + lw > copy_region.r or it.min_font(k_logo) < MIN_TEXT * .99 and it.texts:
                out_ids = [n.id for n in it.members]
                for nid in out_ids:
                    out[nid]['hidden'] = True
                dropped.extend(_names(it, roles))
                reasons.append('Logo dropped: no room beside the button.')
                continue
            it.place(out, copy_region.r - lw, cbox.cy - lh / 2, lw, k_logo)
            reasons.append('Logo placed on the button row to leave room for the message.')
    if row and legal_items:
        dropped.append('legal')
        reasons.append('Legal line dropped (no room on a banner this short).')

    # --- panels (scrims) follow the copy
    for pid in (a['layers']['panels'] if frame_regions is None else []):
        placed = [Box.of(out[n.id]['box']) for it in allitems for n in it.texts if not out[n.id].get('hidden')]
        if placed and overlay_panel is not None:
            # the photo became a panel: the scrim backs the copy side only, never the photo
            op = overlay_panel
            if op.h >= H - 1:          # side panel
                pb = [0, 0, op.x, H] if op.x > W / 2 - 1 else [op.r, 0, W - op.r, H]
            else:
                pb = [0, 0, W, op.y] if op.y > H / 2 - 1 else [0, op.b, W, H - op.b]
            _set(out, pid, pb)
        elif placed:
            u_ = Box.bound(placed)
            if aspect >= 1.25 and a['style']['structure'] == 'overlay':
                pb = [0, 0, u_.r + m, H] if u_.cx < W / 2 else [u_.x - m, 0, W - u_.x + m, H]
            else:
                pb = [0, max(0, u_.y - m * 1.2), W, H - max(0, u_.y - m * 1.2)] if u_.cy > H / 2 else [0, 0, W, u_.b + m * 1.2]
            _set(out, pid, pb)
    if tier < 3:
        hero_map = (Box.of(hero['box']), photo_region) if hero and photo_region else None
        _decorate(out, g, a, W, H, W / g.width, H / g.height, s, copy_region, hero_map)
    if frame_regions is not None:
        for pid in a['layers']['panels']:
            out[pid]['hidden'] = True        # the copy already sits on the page colour
    res = finish(design, g, a, out, W, H, reasons)
    res['_args'] = {**args, 'fill': fill, 'tier': tier}
    if backdrop:
        res['design'].setdefault('page', {})['backdrop'] = backdrop
        # the copy now sits on the darkened photo, not the page colour: light ink where dark ink would vanish
        _legible_on_photos(res['design']['nodes'], a, W, H, res['reasons'], backdrop)
        res['checks'] = check(res['design'], a, {'_': res['checks']['subject_kept']} if res['checks'].get('subject_kept') is not None else {})
    has_cards = any(isinstance(it, RepeatItem) and not it.flex for it in items)
    res['layout'] = {
        'photo': photo_mode if (hero and photo_region) else None,
        'cards': None if not has_cards or hero else ('beside' if split is not None and split in allitems else 'below'),
    }
    return res


# ---------------------------------------------------------------- checks and baselines

def _rgb(c):
    c = str(c or '').strip().lstrip('#')
    if len(c) == 3:
        c = ''.join(ch * 2 for ch in c)
    if len(c) != 6:
        return None
    try:
        return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


def contrast(c1, c2) -> float | None:
    """WCAG contrast ratio of two #hex colours (None when either is unknown)."""
    a_, b_ = _rgb(c1), _rgb(c2)
    if a_ is None or b_ is None:
        return None

    def lum(rgb):
        ch = [v / 255 for v in rgb]
        ch = [v / 12.92 if v <= .03928 else ((v + .055) / 1.055) ** 2.4 for v in ch]
        return .2126 * ch[0] + .7152 * ch[1] + .0722 * ch[2]
    l1, l2 = sorted((lum(a_), lum(b_)), reverse=True)
    return (l1 + .05) / (l2 + .05)


def ink(n: dict):
    """The colour a text or a flat logo is drawn in."""
    st = n.get('style') or {}
    return st.get('color', '#111') if n['type'] == 'text' else st.get('fill')


import contextvars
_PHOTOS = contextvars.ContextVar('chameleon_photos', default=None)   # node id -> photo src, for one adapt() call
_PIX: dict = {}                                                      # decoded photos, small, by src


def _photo_pixels(src):
    if not src:
        return None
    key = hash(src)
    if key not in _PIX:
        from .subject import _open
        _PIX[key] = _open(src)
        if len(_PIX) > 32:
            _PIX.pop(next(iter(_PIX)))
    return _PIX[key]


def _photo_colour(m: dict, box, busy: bool = False):
    """Average colour of photo node m under `box` (canvas coordinates), through the crop it is drawn with.
    None when the photo's pixels are not available (a placeholder, or a path the engine never reads)."""
    src = m.get('src') or (_PHOTOS.get() or {}).get(m.get('srcFrom') or m['id'])
    im = _photo_pixels(src)
    if im is None:
        return None
    iw, ih = im.size
    mx, my, mw, mh = m['box']
    if mw <= 0 or mh <= 0:
        return None
    crop = m.get('crop')
    if not crop:     # drawn as "cover": centred, filling the slot
        a_img, a_slot = iw / ih, mw / mh
        crop = [(1 - a_slot / a_img) / 2, 0, a_slot / a_img, 1] if a_img > a_slot else [0, (1 - a_img / a_slot) / 2, 1, a_img / a_slot]
    cx, cy, cw, ch = crop
    x0, y0 = max(box[0], mx), max(box[1], my)
    x1, y1 = min(box[0] + box[2], mx + mw), min(box[1] + box[3], my + mh)
    if x1 <= x0 or y1 <= y0:
        return None
    u = lambda v: (cx + (v - mx) / mw * cw) * iw
    v_ = lambda v: (cy + (v - my) / mh * ch) * ih
    l, t, r, b = int(max(0, u(x0))), int(max(0, v_(y0))), int(min(iw, u(x1) + 1)), int(min(ih, v_(y1) + 1))
    if r <= l or b <= t:
        return None
    from PIL import ImageStat
    region = im.crop((l, t, r, b))
    if busy:      # how much the photo varies there (luminance spread, 0-255): detail fights small text
        return ImageStat.Stat(region.convert('L')).stddev[0]
    mean = ImageStat.Stat(region).mean
    return '#%02x%02x%02x' % tuple(int(round(c)) for c in mean[:3])


def _blend(base: str, over: str, alpha: float) -> str:
    a_, b_ = _rgb(base), _rgb(over)
    if a_ is None or b_ is None:
        return base
    return '#%02x%02x%02x' % tuple(int(round(x * (1 - alpha) + y * alpha)) for x, y in zip(a_, b_))


def backdrop(design: dict, n: dict):
    """Colour behind node n: the topmost visible flat shape under its centre, or the photo's own colour under
    the whole box (with see-through shapes on top of it blended in), else the page. None over a photo whose
    pixels are unknown."""
    x, y, w, h = n['box']
    cx, cy = x + w / 2, y + h / 2
    nodes = [m for m in design['nodes'] if m['type'] != 'group' and not m.get('hidden')]
    idx = next((i for i, m in enumerate(nodes) if m['id'] == n['id']), len(nodes))
    veils = []        # translucent shapes between the text and what is under it
    base = None
    for m in reversed(nodes[:idx]):
        if m['type'] not in ('shape', 'image'):
            continue
        bx, by, bw, bh = m['box']
        if bx <= cx <= bx + bw and by <= cy <= by + bh:
            if m['type'] == 'image':
                base = _photo_colour(m, n['box'])
                if base is None:
                    return None
                break
            st = m.get('style') or {}
            op = float(st.get('opacity', 1) if st.get('opacity') is not None else 1)
            if _rgb(st.get('fill')):
                if op >= .5:
                    base = st.get('fill')
                    break
                veils.append((st.get('fill'), op))
    if base is None:
        page = design.get('page') or {}
        bd = page.get('backdrop')
        img = next((m for m in design['nodes'] if bd and m['id'] == bd.get('image')), None)
        if img is not None:
            # the page is that photo, blurred and darkened (drawn as "cover" over the whole page)
            col = _photo_colour({**img, 'box': [0, 0, page.get('width', 1), page.get('height', 1)], 'crop': None}, n['box'])
            if col is None:
                return None
            base = _blend(col, '#000000', float(bd.get('dim', .5) if bd.get('dim') is not None else .5))
        else:
            base = page.get('background', '#ffffff')
    for fill, op in reversed(veils):
        base = _blend(base, fill, op)
    return base


def _legible_on_photos(nodes: list, a: dict, W: float, H: float, reasons: list, page_backdrop=None):
    """Text sitting straight on a photo (a logo, an eyebrow) that the photo there makes hard to read is set in
    the design's light or dark ink instead, whichever reads better. With `page_backdrop` (the page is the photo,
    blurred and darkened), text on the page counts as text on that photo."""
    roles = {k: v['role'] for k, v in a['roles'].items()}
    d = {'page': {'width': W, 'height': H, **({'backdrop': page_backdrop} if page_backdrop else {})}, 'nodes': nodes}
    texts = [m for m in nodes if m['type'] == 'text' and not m.get('hidden') and (m.get('text') or '').strip()]
    inks = [ink(m) for m in texts if _rgb(ink(m))]
    lum = lambda c: sum(_rgb(c)) / 3
    dark = min(inks + ['#111111'], key=lum)
    dark = dark if lum(dark) < 90 else '#111111'
    light = '#FFFFFF'
    fixed = []
    for m in texts:
        if roles.get(m['id']) in ('decoration', 'panel'):
            continue
        cx, cy = m['box'][0] + m['box'][2] / 2, m['box'][1] + m['box'][3] / 2
        under = next((q for q in reversed(nodes[:nodes.index(m)]) if q['type'] in ('image', 'shape') and not q.get('hidden')
                      and q['box'][0] <= cx <= q['box'][0] + q['box'][2] and q['box'][1] <= cy <= q['box'][1] + q['box'][3]), None)
        if under is None and page_backdrop:
            under = {'type': 'blurred page'}
        elif under is None or under['type'] != 'image':
            continue      # on a flat colour: the designer chose that pairing
        bg = backdrop(d, m)
        c = contrast(ink(m), bg)
        spread = _photo_colour(under, m['box'], busy=True) or 0 if under['type'] == 'image' else 0
        need = 4.5 if spread > 40 else 3.0          # a busy patch of photo needs a stronger contrast
        if c is None or c >= need:
            continue
        best = max((light, dark), key=lambda k: contrast(k, bg) or 0)
        if (contrast(best, bg) or 0) >= max(need * .8, c * 1.3):
            m['style'] = {**(m.get('style') or {}), 'color': best}
            fixed.append((roles.get(m['id']) or 'text', 'light' if best == light else 'dark'))
    for role, tone in dict.fromkeys(fixed):
        reasons.append(f"{role[0].upper() + role[1:]} set in {tone} ink so it reads on the photo here.")


def _contrasts(design: dict, a: dict) -> dict:
    roles = {k: v['role'] for k, v in a['roles'].items()}
    out = {}
    for n in design['nodes']:
        if n['type'] == 'group' or n.get('hidden') or roles.get(n['id']) in ('decoration', 'background', 'panel'):
            continue
        if n['type'] == 'text' or (roles.get(n['id']) == 'logo' and n['type'] == 'shape'):
            out[n['id']] = contrast(ink(n), backdrop(design, n))
    return out


def check(design: dict, a: dict, crops: dict) -> dict:
    W, H = design['page']['width'], design['page']['height']
    roles = {k: v['role'] for k, v in a['roles'].items()}
    allowed = a.get('_base_overlaps', set())
    base_c = a.get('_base_contrast', {})
    vis = [n for n in design['nodes'] if n['type'] != 'group' and not n.get('hidden')]
    solid = [n for n in vis if roles.get(n['id']) not in ('background', 'panel', 'decoration') and n['type'] in ('text', 'image', 'shape')]
    photo = {n['id'] for n in solid if n['type'] == 'image' and roles.get(n['id']) in ('hero', 'image')}
    container_of = {t: c for c, ts in a['layers']['containers'].items() for t in ts}
    overlaps = []
    for i in range(len(solid)):
        for j in range(i + 1, len(solid)):
            p, q = solid[i], solid[j]
            if container_of.get(p['id']) == q['id'] or container_of.get(q['id']) == p['id']:
                continue
            if (p['id'] in photo and roles.get(q['id']) == 'logo') or (q['id'] in photo and roles.get(p['id']) == 'logo'):
                continue      # a logo placed on its photo on purpose
            A, B = Box.of(p['box']), Box.of(q['box'])
            if A.inter(B) > 4 and tuple(sorted((p['id'], q['id']))) not in allowed:
                overlaps.append([p['id'], q['id']])
    off = [n['id'] for n in vis if roles.get(n['id']) not in ('background', 'decoration')
           and (n['box'][0] < -1 or n['box'][1] < -1 or n['box'][0] + n['box'][2] > W + 1 or n['box'][1] + n['box'][3] > H + 1)]
    small = [n['id'] for n in vis if n['type'] == 'text' and n.get('text', '').strip()
             and drawn_size(n) < MIN_TEXT - .01 and roles.get(n['id']) != 'decoration']
    hidden = [n['id'] for n in design['nodes'] if n['type'] != 'group' and n.get('hidden')
              and roles.get(n['id']) not in ('decoration', 'panel')]
    kept = min(crops.values()) if crops else None
    low = []      # text or logo that became hard to read where it now sits (worse than the designer had it)
    for nid, c in _contrasts(design, a).items():
        if c is not None and c < 3 and (base_c.get(nid) is None or c < base_c[nid] * .8):
            low.append(nid)
    return {'overlaps': overlaps, 'off_canvas': off, 'small_text': small, 'low_contrast': low, 'dropped': hidden,
            'subject_kept': kept, 'ok': not overlaps and not off and not small and not low}


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
    src = g.to_json()                   # normalised: ids are strings, sizes are numbers, styles are clean
    _PHOTOS.set({n['id']: n['src'] for n in src['nodes'] if n.get('src')})
    a = analyze(g)
    base = check(src, a, {})            # overlaps the designer made on purpose are allowed to stay
    base_overlaps = {tuple(sorted(p)) for p in base['overlaps']}
    a['_base_overlaps'] = base_overlaps
    a['_base_contrast'] = _contrasts(src, a)
    from .score import used_share, _subject_under_copy
    a['_orig_used'] = used_share(src, a)
    a['_orig_under'] = _subject_under_copy({n['id']: n for n in src['nodes']}, a)
    pinned = any(g.by_id[i].crop for i in a['subjects'] if i in g.by_id)   # the designer framed this photo
    a['_pinned_crop'] = pinned
    if not pinned and any(sub.get('source') not in ('given', 'assumed') for sub in a['subjects'].values()):
        # a photo found by detection (a new photo dropped into the design): the designer never placed copy
        # on THIS subject on purpose, so copy over it is not "as designed"
        a['_orig_under'] = min(a['_orig_under'], .1)
    return {'source': {'width': g.width, 'height': g.height},
            'analysis_notes': a['notes'],
            'roles': {k: v['role'] for k, v in a['roles'].items()},
            'results': [adapt_one(src, g, a, t, base_overlaps) for t in targets]}
