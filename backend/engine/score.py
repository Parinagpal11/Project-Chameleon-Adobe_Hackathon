"""Score stage: rate a resized design against the original, the same way for Chameleon and for the baselines.

score(design, original, analysis, ...) -> {'overall', 'content', 'legibility', 'faithfulness', 'composition',
                                           'subject', 'notes'}, every number 0-100.

  content       how much of the message is still there and not cut off (weighted: headline, button, logo,
                offer and photo count most; legal and decoration least)
  legibility    share of the text that will draw at 12 px or more, undistorted, on a readable background
  faithfulness  the original's reading order, type hierarchy and shapes are kept (stretching distorts shapes)
  composition   no overlaps, nothing off canvas, breathing room at the edges, the canvas is used (no empty bars)
  subject       how much of each photo's subject is visible

The baselines (stretch, centre crop, letterbox) are built as real designs by `baseline_designs` and scored
with the same function, so the comparison is like for like.
"""
from __future__ import annotations

from .graph import Box

WEIGHT = {'headline': 3.0, 'cta': 3.0, 'logo': 2.0, 'offer': 2.0, 'price': 1.5, 'hero': 2.0, 'image': 1.5,
          'subhead': 1.5, 'body': 1.0, 'eyebrow': 1.0, 'badge': 1.0, 'item': 1.0, 'caption': .8, 'legal': .5}
SKIP = ('background', 'decoration', 'panel')
PARTS = {'content': .25, 'legibility': .25, 'faithfulness': .2, 'composition': .2, 'subject': .1}


def _w(role):
    return WEIGHT.get(role, 1.0)


def _pairs_kept(order_a: list, order_b: list) -> float:
    """Share of pairs that keep their relative order (1.0 = same order)."""
    common = [x for x in order_a if x in set(order_b)]
    pos = {x: i for i, x in enumerate(order_b)}
    n = good = 0
    for i in range(len(common)):
        for j in range(i + 1, len(common)):
            n += 1
            good += pos[common[i]] < pos[common[j]]
    return good / n if n else 1.0


def _visual_order(boxes: dict) -> list:
    """Reading order of a laid-out design: rows top to bottom, left to right inside a row (Z pattern)."""
    items = sorted(boxes.items(), key=lambda kv: (kv[1].y, kv[1].x))
    rows: list[list] = []
    for gid, b in items:
        if rows and b.y < max(r[1].cy for r in rows[-1]):
            rows[-1].append((gid, b))
        else:
            rows.append([(gid, b)])
    return [gid for row in rows for gid, _ in sorted(row, key=lambda kv: kv[1].x)]


def used_share(design: dict, a: dict) -> float:
    """Share of the canvas covered by the content's bounding box (or a background element)."""
    roles = {k: v['role'] for k, v in a['roles'].items()}
    W, H = float(design['page']['width']), float(design['page']['height'])
    canvas = Box(0, 0, W, H)
    bs = [Box.of(n['box']) for n in design['nodes'] if n['type'] != 'group' and not n.get('hidden') and 'box' in n
          and roles.get(n['id']) not in SKIP]
    used = Box.bound(bs).inter(canvas) / (W * H) if bs else 0.0
    for n in design['nodes']:
        if roles.get(n['id']) == 'background' and 'box' in n and not n.get('hidden'):
            used = max(used, Box.of(n['box']).inter(canvas) / (W * H))
    return used


def score(design: dict, original: dict, a: dict, distortion: float = 1.0, subject_kept=None,
          allowed_overlaps: set = frozenset(), frame: float = 1.0) -> dict:
    """`frame`: share of the canvas the design actually covers (letterbox leaves empty bars)."""
    from .adapt import drawn_size, contrast, ink, backdrop, MIN_TEXT
    W, H = float(design['page']['width']), float(design['page']['height'])
    canvas = Box(0, 0, W, H)
    roles = {k: v['role'] for k, v in a['roles'].items()}
    out = {n['id']: n for n in design['nodes']}
    leaves = [n for n in original['nodes'] if n['type'] != 'group' and roles.get(n['id']) not in SKIP]
    notes = []

    def shown(nid, readable=True):
        n = out.get(nid)
        if not n or n.get('hidden') or 'box' not in n:
            return 0.0
        b = Box.of(n['box'])
        if b.area <= 0:
            return 0.0
        inside = b.inter(canvas) / b.area
        if n['type'] == 'text':
            if inside < .98:
                return 0.0                     # a cut line of text is lost
            if not readable:
                return 1.0
            size = drawn_size(n)               # and so is text too small to read
            return 1.0 if size >= MIN_TEXT - .01 else (.5 if size >= 9 else 0.0)
        return inside

    # content
    tot = sum(_w(roles.get(n['id'])) for n in leaves) or 1.0
    kept = sum(_w(roles.get(n['id'])) * shown(n['id']) for n in leaves)
    content = kept / tot
    lost = [roles.get(n['id']) or n['id'] for n in leaves if shown(n['id'], False) < .5]
    if lost:
        notes.append('Missing or cut: ' + ', '.join(dict.fromkeys(lost)) + '.')

    # legibility
    texts = [out[n['id']] for n in leaves if n['type'] == 'text' and shown(n['id'], False) > 0 and (n.get('text') or '').strip()]
    readable = tw = 0.0
    small = 0
    for n in texts:
        wgt = _w(roles.get(n['id']))
        tw += wgt
        size_ok = drawn_size(n) >= MIN_TEXT - .01
        c = contrast(ink(n), backdrop(design, n))
        ok = size_ok and (c is None or c >= 2.5) and distortion <= 1.05
        small += not size_ok
        readable += wgt * (1.0 if ok else (0.5 if size_ok and distortion <= 1.3 else 0.0))
    legibility = readable / tw if tw else 1.0
    if small:
        notes.append(f'{small} text{"s" if small > 1 else ""} under 12 px.')
    if distortion > 1.05:
        notes.append(f'Letters and shapes stretched {distortion:.2f}x.')

    # faithfulness: reading order, type hierarchy, shapes
    groups = [gr for gr in a['groups'] if not all(roles.get(m) in SKIP for m in gr['members'])]
    nb = {}
    for gr in groups:
        bs = [Box.of(out[m]['box']) for m in gr['members'] if m in out and shown(m, False) > 0]
        if bs:
            nb[gr['id']] = Box.bound(bs)
    from .understand import reading_order
    # reading order of the copy (photos may move beside or above it; that is a re-flow, not a reshuffle)
    nb = {gid: b for gid, b in nb.items()
          if not any(roles.get(m) in ('hero', 'image') for m in next(gr['members'] for gr in groups if gr['id'] == gid))}
    orig_order = [g for g in a['reading_order'] if g in nb]
    order = _pairs_kept(orig_order, reading_order([{'id': gid, 'box': b} for gid, b in nb.items()]))
    by_size_orig = sorted((n for n in leaves if n['type'] == 'text' and n['id'] in out and shown(n['id'], False) > 0),
                          key=lambda n: -float((n.get('style') or {}).get('fontSize') or 0))
    fs0 = {n['id']: float((n.get('style') or {}).get('fontSize') or 0) for n in by_size_orig}
    fs1 = {n['id']: drawn_size(out[n['id']]) for n in by_size_orig}
    hp = hk = 0
    for i in range(len(by_size_orig)):
        for j in range(i + 1, len(by_size_orig)):
            p, q = by_size_orig[i]['id'], by_size_orig[j]['id']
            if fs0[p] < fs0[q] * 1.15:
                continue                    # about the same size in the original: no order to keep
            hp += 1
            hk += fs1[p] >= fs1[q] * .97    # bigger stays bigger (or equal when both sit at the 12 px floor)
    hierarchy = hk / hp if hp else 1.0
    shapes = max(0.0, 1 - (distortion - 1) / 1.5)       # stretched 1.3x keeps 80%; 2.5x and beyond keeps nothing
    faithfulness = (order + hierarchy) / 2 * shapes
    if order < .9:
        notes.append('Reading order changed.')
    if hierarchy < .9:
        notes.append('Type hierarchy changed.')

    # composition
    vis = [out[n['id']] for n in leaves if shown(n['id'], False) > 0]
    vb = {n['id']: Box.of(n['box']) for n in vis}
    container_of = {t: c_ for c_, ts in a['layers']['containers'].items() for t in ts}
    photo = {i for i in vb if roles.get(i) in ('hero', 'image')}
    ids = list(vb)
    pairs = clash = 0
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            p, q = ids[i], ids[j]
            if container_of.get(p) == q or container_of.get(q) == p or tuple(sorted((p, q))) in allowed_overlaps:
                continue
            if (p in photo and roles.get(q) == 'logo') or (q in photo and roles.get(p) == 'logo'):
                continue
            pairs += 1
            clash += vb[p].inter(vb[q]) > 4
    no_overlap = 1 - (clash / pairs if pairs else 0.0)
    inside = sum(1 for b in vb.values() if b.inter(canvas) >= b.area * .99) / max(1, len(vb))
    edge = .015 * min(W, H)
    roomy = [b for i, b in vb.items() if i not in photo]
    margins = sum(1 for b in roomy if b.x >= edge - .5 and b.y >= edge - .5 and b.r <= W - edge + .5 and b.b <= H - edge + .5) \
        / max(1, len(roomy))
    used = Box.bound(list(vb.values())).inter(canvas) / (W * H) if vb else 0.0
    bg = [n for n in design['nodes'] if roles.get(n['id']) == 'background' and not n.get('hidden') and 'box' in n]
    if bg:
        used = max(used, max(Box.of(n['box']).inter(canvas) for n in bg) / (W * H))
    # the canvas should be used about as fully as the designer used theirs (empty letterbox bars count against)
    target = min(.55, max(.15, a.get('_orig_used', .55) * .85))
    fill = min(1.0, used / target) * (frame if frame < .98 else 1.0)
    composition = (no_overlap + inside + margins + fill) / 4
    if clash:
        notes.append(f'{clash} overlap{"s" if clash > 1 else ""}.')
    if fill < .7:
        notes.append(f'Only {used * 100:.0f}% of the canvas is used.')

    parts = {'content': content, 'legibility': legibility, 'faithfulness': faithfulness, 'composition': composition}
    if subject_kept is not None:
        parts['subject'] = float(subject_kept)
    wsum = sum(PARTS[k] for k in parts)
    overall = sum(PARTS[k] * v for k, v in parts.items()) / wsum
    res = {k: round(v * 100, 1) for k, v in parts.items()}
    res['subject'] = res.get('subject')
    res['overall'] = round(overall * 100, 1)
    res['notes'] = notes
    return res


def baseline_designs(original: dict, W: float, H: float) -> dict:
    """The three naive resizes as real designs: stretch (both axes), centre crop (cover), letterbox (contain)."""
    import copy
    W0, H0 = float(original['page']['width']), float(original['page']['height'])

    def build(sx, sy, ox, oy):
        d = copy.deepcopy(original)
        d['page'] = {**d['page'], 'width': W, 'height': H}
        for n in d['nodes']:
            if 'box' in n:
                x, y, w, h = n['box']
                n['box'] = [x * sx + ox, y * sy + oy, w * sx, h * sy]
            st = n.get('style')
            if st and st.get('fontSize'):
                st = n['style'] = dict(st)
                st['fontSize'] = float(st['fontSize']) * min(sx, sy)
            if n.get('src'):
                n.pop('src')
                n['srcFrom'] = n['id']
        return d
    sx, sy = W / W0, H / H0
    k = max(sx, sy)
    f = min(sx, sy)
    return {'stretch': (build(sx, sy, 0, 0), max(sx / sy, sy / sx), 1.0),
            'crop': (build(k, k, (W - W0 * k) / 2, (H - H0 * k) / 2), 1.0, 1.0),
            'letterbox': (build(f, f, (W - W0 * f) / 2, (H - H0 * f) / 2), 1.0, (W0 * f * H0 * f) / (W * H))}
