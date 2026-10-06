"""Layout generator: places hero imagery and a typographic content stack for any canvas.

Honours campaign rules supplied as a bound context (see engine.rules.bind):
order (topological stacking), pin (corner placement outside the flow), align (horizontal
alignment), emphasis (relative size) and hide_small (format-dependent visibility).
"""
from copy import deepcopy
import math

# Relative type scale by role; the headline sets the base size.
SCALE = {'headline': 1.0, 'offer': .62, 'subtitle': .5, 'body': .36, 'legal': .26, 'cta': .42, 'logo': .4}
MAX_LINES = {'headline': 3, 'offer': 2, 'subtitle': 2, 'body': 4, 'legal': 3, 'cta': 1, 'logo': 1}
CHAR_W = .62     # average glyph width as a fraction of font size (used for logos without text)
LINE_H = 1.14


def char_w(ch):
    """Approximate advance width (fraction of font size) of one glyph in a bold sans such as Inter 800."""
    if ch == ' ':
        return .27
    if ch in 'MW@%':
        return .92
    if ch in 'iIl.,:;!|\'':
        return .3
    if ch.isupper() or ch in '&#':
        return .71
    if ch.isdigit():
        return .63
    return .58


def text_w(text, fs):
    return sum(char_w(c) for c in text) * fs


def ordered(elements, rules):
    ids = {e.id for e in elements}
    edges = {i: set() for i in ids}
    for r in rules:
        a, b = (r['target'], r['source']) if r['relation'] == 'BELOW' else (r['source'], r['target'])
        if a in ids and b in ids:
            edges[b].add(a)
    result = []
    remaining = list(elements)
    while remaining:
        done = {x.id for x in result}
        ready = next((e for e in remaining if not edges[e.id] - done), None)
        if ready is None:
            raise ValueError('Corrections contain a cycle')
        result.append(ready)
        remaining.remove(ready)
    return result


def wrap_count(text, fs, width):
    """Greedy word wrap using per-glyph widths. Returns (lines, widest_line_px)."""
    words = (text or '').split() or ['']
    lines, cur, widest = 1, 0.0, 0.0
    space = char_w(' ') * fs
    for w in words:
        ww = text_w(w, fs)
        if ww > width:
            return 99, ww
        if cur and cur + space + ww > width:
            widest = max(widest, cur)
            lines, cur = lines + 1, ww
        else:
            cur = cur + (space if cur else 0) + ww
    widest = max(widest, cur)
    return lines, widest


def _ctx(rules):
    if isinstance(rules, dict):
        return rules
    return {'order': list(rules), 'pin': {}, 'align': {}, 'emphasis': {}, 'hide_small': {}, 'rules': []}


def generate_candidates(design, w, h, rules=()):
    ctx = _ctx(rules)
    ratio = w / h
    if ratio < .45:
        strategies = ['hero_top', 'stacked', 'hero_small']
    elif ratio < .8:
        strategies = ['hero_top', 'stacked', 'text_left']
    elif ratio > 2.6:
        buttons = {e.id for e in design.elements if e.type == 'button'}
        cta_ordered = any(r['source'] in buttons or r['target'] in buttons for r in ctx['order'])
        # A side-by-side CTA cannot honour an above/below rule that involves it.
        strategies = ['text_right' if cta_ordered else 'banner', 'text_left', 'stacked' if ctx['order'] else 'row']
    else:
        strategies = ['text_left', 'text_right', 'stacked']
    return [_apply(design, w, h, s, ctx) for s in strategies]


def _role(e):
    return e.genome.role if e.genome else 'body'


def _natural(e, fs, cw):
    """Height and width an element needs at font size fs inside column width cw."""
    role = _role(e)
    if e.type == 'button':
        tw = text_w(e.text or 'SHOP NOW', fs)
        bw = min(cw, tw + fs * 2.4)
        return fs * 2.5, bw, tw + fs * 2.4 <= cw
    if e.type == 'logo' and e.src:
        hgt = fs * 1.6
        aspect = (e.width / e.height) if e.height else 3
        return hgt, min(cw, hgt * aspect), hgt * aspect <= cw * 1.01
    text = e.text or ('LOGO' if e.type == 'logo' else '')
    lines, widest = wrap_count(text, fs, cw)
    ok = lines <= MAX_LINES.get(role, 2)
    return lines * fs * LINE_H, min(cw, widest), ok


def _apply(design, w, h, strategy, ctx):
    d = deepcopy(design)
    d.canvas.width, d.canvas.height = w, h
    short = min(w, h)
    m = short * .06
    gap = short * .03
    for e in d.elements:
        e.hidden = False
        e.pinned = None
        if e.id in ctx['hide_small'] and short < ctx['hide_small'][e.id]:
            e.hidden = True
            e.width = e.height = 0
        elif e.genome.removable:
            e.width = e.height = 0

    visible = [e for e in d.elements if not e.hidden and not e.genome.removable]
    # Pinned elements leave the flow and sit in a canvas corner.
    top_band = bottom_band = 0.0
    for e in visible:
        corner = ctx['pin'].get(e.id)
        if not corner:
            continue
        ph = max(18.0, short * (.09 if e.type == 'logo' else .08)) * ctx['emphasis'].get(e.id, 1.0)
        aspect = (e.width / e.height) if (e.src and e.height) else max(2.2, text_w(e.text or 'LOGO', 1) * .62 * 1.08)
        pw = min((w - 2 * m) * .42, ph * aspect)
        ph = pw / aspect if pw < ph * aspect else ph
        v, hz = corner.split('-')
        e.x = m if hz == 'left' else w - m - pw
        e.y = m if v == 'top' else h - m - ph
        e.width, e.height = pw, ph
        e.fontSize = ph * .62 if e.type != 'image' else e.fontSize
        e.align = hz
        e.pinned = corner
        if v == 'top':
            top_band = max(top_band, ph + gap)
        else:
            bottom_band = max(bottom_band, ph + gap)

    flow = [e for e in visible if not e.pinned]
    heroes = [e for e in flow if e.type == 'image']
    content = [e for e in flow if e.type != 'image' and e.type not in ('shape', 'decoration')]
    content.sort(key=lambda e: (e.y, e.x))
    content = ordered(content, ctx['order'])

    ax, ay, aw, ah = m, m + top_band, w - 2 * m, h - 2 * m - top_band - bottom_band
    x, y, cw, ch = ax, ay, aw, ah
    if heroes:
        if strategy in ('stacked', 'hero_top', 'hero_small'):
            hh = ah * ((.3 if strategy == 'hero_small' else .44) if content else 1)
            hy = ay if strategy in ('hero_top', 'hero_small') else ay + ah - hh
            hx, hw = ax, aw
            ch = ah - hh - gap
            if strategy in ('hero_top', 'hero_small'):
                y = ay + hh + gap
        elif strategy in ('row', 'banner'):
            hw = min(aw * .28, ah * 1.4)
            hh, hy, hx = ah, ay, ax + aw - hw
            cw = aw - hw - gap
        else:
            hw = aw * .46 if w / h < 2.6 else min(aw * .3, ah * 2.4)
            hh, hy = ah, ay
            hx = ax + aw - hw if strategy == 'text_left' else ax
            cw = aw - hw - gap
            if strategy == 'text_right':
                x = ax + hw + gap
        for i, e in enumerate(heroes):
            e.x, e.y = hx, hy + i * hh / len(heroes)
            e.width, e.height = hw, hh / len(heroes) - (gap * .5 if len(heroes) > 1 else 0)

    if content:
        default_align = 'center' if (strategy in ('stacked', 'hero_top', 'hero_small') and w / h < .8) else 'left'
        if strategy == 'row':
            _row(content, ctx, x, y, cw, ch, short)
        elif strategy == 'banner':
            _banner(content, ctx, x, y, cw, ch, short, gap)
        else:
            _stack(content, ctx, x, y, cw, ch, short, default_align)
    return {'strategy': strategy, 'design': d}


def _size(e, ctx):
    return SCALE.get(_role(e), .4) * ctx['emphasis'].get(e.id, 1.0)


def _stack(content, ctx, x, y, cw, ch, short, default_align):
    def layout(base):
        total, items, ok = 0.0, [], True
        for e in content:
            fs = max(base * _size(e, ctx), min(12.0, base))  # keep text legible when possible
            hgt, wid, fits = _natural(e, fs, cw)
            ok &= fits
            items.append((e, fs, hgt, wid))
            total += hgt
        spacing = base * .45
        total += spacing * (len(content) - 1)
        return ok and total <= ch * .9, total, items, spacing

    lo, hi = 6.0, max(8.0, min(short * .3, ch * .4, cw * .5) if short < 400 else min(short * .16, ch * .4))
    best = layout(lo)
    for _ in range(26):
        mid = (lo + hi) / 2
        res = layout(mid)
        if res[0]:
            lo, best = mid, res
        else:
            hi = mid
    _, total, items, spacing = best
    if total > ch:  # tiny canvas: compress proportionally rather than overflow or overlap
        k = ch / total * .98
        items = [(e, fs * k, hgt * k, wid * k) for e, fs, hgt, wid in items]
        spacing *= k
        total *= k
    cy = y + max(0.0, (ch - total) / 2)
    for e, fs, hgt, wid in items:
        a = ctx['align'].get(e.id, default_align)
        e.align = a
        e.fontSize = fs if e.type in ('text', 'button', 'logo') else e.fontSize
        bw = wid if e.type in ('button', 'logo') else cw
        e.width, e.height = bw, hgt
        e.x = x if a == 'left' or bw >= cw else (x + cw - bw if a == 'right' else x + (cw - bw) / 2)
        e.y = cy
        cy += hgt + spacing


def _row(content, ctx, x, y, cw, ch, short):
    """Horizontal strip for leaderboard-style banners (ignores vertical order rules by nature)."""
    n = len(content)
    gap = short * .25
    slot = (cw - gap * (n - 1)) / n
    for e in content:
        fs = min(ch * .5 * _size(e, ctx) / .6, ch * .55)
        while fs > 6:
            hgt, wid, ok = _natural(e, fs, slot)
            if ok and hgt <= ch:
                break
            fs *= .92
        hgt, wid, _ = _natural(e, fs, slot)
        e.fontSize = fs
        e.align = 'left'
        e.width, e.height = (wid if e.type in ('button', 'logo') else slot), hgt
        e.x, e.y = x, y + (ch - hgt) / 2
        x += slot + gap


def _banner(content, ctx, x, y, cw, ch, short, gap):
    """Wide banners: text block on the left, the call-to-action button in its own zone on the right."""
    ctas = [e for e in content if e.type == 'button']
    texts = [e for e in content if e.type != 'button']
    if not ctas or not texts:
        return _stack(content, ctx, x, y, cw, ch, short, 'left')
    cta = ctas[0]
    weight = ctx['emphasis'].get(cta.id, 1.0)
    label = cta.text or 'SHOP NOW'
    fs = min(ch * .2 * weight, ch * .3, cw * .3 / (text_w(label, 1) + 2.4))
    bw, bh = text_w(label, fs) + fs * 2.4, fs * 2.5
    cta.fontSize, cta.width, cta.height = fs, bw, bh
    cta.x, cta.y, cta.align = x + cw - bw, y + (ch - bh) / 2, 'center'
    for other in ctas[1:]:
        texts.append(other)
    _stack(texts, ctx, x, y, cw - bw - gap * 2, ch, short, 'left')
