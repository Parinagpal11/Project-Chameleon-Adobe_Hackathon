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


def largest_empty(boxes: list, W: float, H: float, n: int = 48) -> float:
    """Share of the canvas taken by the biggest empty rectangle (no photo, text or shape in it), on an n x n grid."""
    occ = [[False] * n for _ in range(n)]
    for b in boxes:
        x0, y0 = max(0, int(b.x / W * n)), max(0, int(b.y / H * n))
        x1, y1 = min(n, int(-(-b.r / W * n // 1))), min(n, int(-(-b.b / H * n // 1)))
        for yy in range(y0, y1):
            row = occ[yy]
            for xx in range(x0, x1):
                row[xx] = True
    best, heights = 0, [0] * n
    for yy in range(n):
        for xx in range(n):
            heights[xx] = 0 if occ[yy][xx] else heights[xx] + 1
        stack = []                                    # largest rectangle in a histogram
        for xx in range(n + 1):
            h = heights[xx] if xx < n else 0
            start = xx
            while stack and stack[-1][1] >= h:
                st, sh = stack.pop()
                best = max(best, sh * (xx - st))
                start = st
            stack.append((start, h))
    return best / (n * n)


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
    """Score one resized design against the original.

    `distortion` and `frame` describe how the design is put on the canvas, which the node data alone can't
    show: a naive stretch draws everything scaled unevenly (distortion = the larger axis ratio), a letterbox
    leaves empty bars (frame = share of the canvas covered). Chameleon's output is drawn 1:1 (photos are
    cropped, never stretched), so it is scored with 1.0 for both.
    `subject_kept` is None only when the original has no photo subject; a dropped photo is 0."""
    from .adapt import drawn_size, contrast, ink, backdrop, MIN_TEXT
    W, H = float(design['page']['width']), float(design['page']['height'])
    canvas = Box(0, 0, W, H)
    roles = {k: v['role'] for k, v in a['roles'].items()}
    out = {n['id']: n for n in design['nodes']}
    leaves = [n for n in original['nodes'] if n['type'] != 'group' and roles.get(n['id']) not in SKIP]
    bg_photos = [n for n in original['nodes'] if n['type'] == 'image' and roles.get(n['id']) == 'background']
    container_of = {t: c_ for c_, ts in a['layers']['containers'].items() for t in ts}
    notes = []
    size_cache = {}

    def dsize(n):
        if n['id'] not in size_cache:
            size_cache[n['id']] = drawn_size(n)
        return size_cache[n['id']]

    def present(n):
        return n is not None and not n.get('hidden') and 'box' in n and n['box'][2] > 0 and n['box'][3] > 0

    solids = {i: Box.of(n['box']) for i, n in out.items() if present(n) and n['type'] in ('text', 'shape')
              and roles.get(i) not in SKIP}

    def buried(n):
        """Text half hidden under another element (not its own button)."""
        b = Box.of(n['box'])
        for j, q in solids.items():
            if j == n['id'] or container_of.get(n['id']) == j or container_of.get(j) == n['id']:
                continue
            if tuple(sorted((n['id'], j))) in allowed_overlaps:
                continue
            if b.inter(q) > b.area * .1:
                return True
        return False

    def low_contrast(n):
        c = contrast(ink(n), backdrop(design, n))
        return c is not None and c < 2.0

    def shown(nid, readable=True):
        n = out.get(nid)
        if not present(n):
            return 0.0
        b = Box.of(n['box'])
        inside = b.inter(canvas) / b.area
        if n['type'] == 'text':
            if inside < .98:
                return 0.0                     # a cut line of text is lost
            if not readable:
                return 1.0
            if low_contrast(n) or buried(n):
                return 0.0                     # so is text you can't see
            size = dsize(n)                    # or too small to read
            return 1.0 if size >= MIN_TEXT - .01 else (.5 if size >= 9 else 0.0)
        return inside

    # content: the message, including the full-bleed photo.
    # Small banners (300x250, 728x90, 160x600) are expected to carry headline, button and logo; dropping a
    # secondary line there (eyebrow, caption, legal, body, extra items) costs half.
    banner = min(W, H) <= 250
    SECONDARY = ('eyebrow', 'caption', 'legal', 'body', 'item', 'price', 'decoration', 'repeat')

    def got(n):
        v = shown(n['id'])
        return max(v, .5) if banner and roles.get(n['id']) in SECONDARY and shown(n['id'], False) < .5 else v
    items = leaves + bg_photos
    tot = sum(_w(roles.get(n['id'])) if n not in bg_photos else 2.0 for n in items)
    kept = sum((_w(roles.get(n['id'])) if n not in bg_photos else 2.0) * got(n) for n in items)
    content = kept / tot if tot else 1.0
    lost = [('photo' if roles.get(n['id']) in ('hero', 'image', 'background') else roles.get(n['id']) or n['id'])
            for n in items if shown(n['id'], False) < .5]
    if lost:
        notes.append('Missing or cut: ' + ', '.join(dict.fromkeys(lost)) + '.')

    # legibility
    orig_texts = [n for n in leaves if n['type'] == 'text' and (n.get('text') or '').strip()]
    texts = [out[n['id']] for n in orig_texts if shown(n['id'], False) > 0]
    readable = 0.0
    small = faint = hidden_under = 0
    if banner:          # a secondary line dropped on a banner is not an unreadable line
        readable += sum(.5 * _w(roles.get(n['id'])) for n in orig_texts
                        if roles.get(n['id']) in SECONDARY and shown(n['id'], False) <= 0)
    for n in texts:
        wgt = _w(roles.get(n['id']))
        size_ok = dsize(n) >= MIN_TEXT - .01
        lc, bu = low_contrast(n), buried(n)
        ok = size_ok and not lc and not bu and distortion <= 1.05
        small += not size_ok
        faint += lc
        hidden_under += bu
        readable += wgt * (1.0 if ok else (0.5 if size_ok and not lc and not bu and distortion <= 1.3 else 0.0))
    tw_all = sum(_w(roles.get(n['id'])) for n in orig_texts)
    legibility = readable / tw_all if tw_all else 1.0          # text that was cut away can't be read either
    if small:
        notes.append(f'{small} text{"s" if small > 1 else ""} under 12 px.')
    if faint:
        notes.append(f'{faint} text{"s" if faint > 1 else ""} hard to read on {"their" if faint > 1 else "its"} background.')
    if hidden_under:
        notes.append(f'{hidden_under} text{"s" if hidden_under > 1 else ""} partly covered.')
    if distortion > 1.05:
        notes.append(f'Letters and shapes stretched {distortion:.2f}x.')

    # faithfulness: reading order, type hierarchy, shapes, scaled by how much of the design is there at all
    groups = [gr for gr in a['groups'] if not all(roles.get(m) in SKIP for m in gr['members'])]
    nb = {}
    for gr in groups:
        bs = [Box.of(out[m]['box']) for m in gr['members'] if m in out and shown(m, False) > 0]
        if bs:
            nb[gr['id']] = Box.bound(bs)
    from .understand import reading_order
    # reading order of the copy (photos may move beside or above it; that is a re-flow, not a reshuffle)
    # (the logo is left out too: on a banner it leads the row by convention)
    copy_nb = {gid: b for gid, b in nb.items()
               if not any(roles.get(m) in ('hero', 'image', 'logo') for m in next(gr['members'] for gr in groups if gr['id'] == gid))}
    orig_order = [g for g in a['reading_order'] if g in copy_nb]
    order = _pairs_kept(orig_order, reading_order([{'id': gid, 'box': b} for gid, b in copy_nb.items()]))
    by_size_orig = sorted((n for n in orig_texts if n['id'] in out and shown(n['id'], False) > 0),
                          key=lambda n: -float((n.get('style') or {}).get('fontSize') or 0))
    fs0 = {n['id']: float((n.get('style') or {}).get('fontSize') or 0) for n in by_size_orig}
    fs1 = {n['id']: dsize(out[n['id']]) for n in by_size_orig}
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
    faithfulness = (order + hierarchy) / 2 * shapes * (1.0 if nb or not groups else 0.0)   # nothing left: nothing kept
    if order < .9:
        notes.append('Reading order changed.')
    if hierarchy < .9:
        notes.append('Type hierarchy changed.')

    # composition
    vis = [out[n['id']] for n in leaves if shown(n['id'], False) > 0]
    vb = {n['id']: Box.of(n['box']) for n in vis}
    photo = {i for i in vb if roles.get(i) in ('hero', 'image')}
    ids = list(vb)
    clash = 0
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            p, q = ids[i], ids[j]
            if container_of.get(p) == q or container_of.get(q) == p or tuple(sorted((p, q))) in allowed_overlaps:
                continue
            if (p in photo and roles.get(q) == 'logo') or (q in photo and roles.get(p) == 'logo'):
                continue
            clash += vb[p].inter(vb[q]) > 4
    no_overlap = max(0.0, 1 - .25 * clash)                     # every overlap costs a quarter
    inside = sum(1 for b in vb.values() if b.inter(canvas) >= b.area * .99) / len(vb) if vb else 1.0
    edge = .015 * min(W, H)
    roomy = [b for i, b in vb.items() if i not in photo]
    margins = sum(1 for b in roomy if b.x >= edge - .5 and b.y >= edge - .5 and b.r <= W - edge + .5 and b.b <= H - edge + .5) \
        / len(roomy) if roomy else 1.0
    used = Box.bound(list(vb.values())).inter(canvas) / (W * H) if vb else 0.0
    bg = [n for n in design['nodes'] if roles.get(n['id']) == 'background' and present(n)]
    if bg:
        used = max(used, max(Box.of(n['box']).inter(canvas) for n in bg) / (W * H))
    # the canvas should be used about as fully as the designer used theirs
    target = min(.55, max(.15, a.get('_orig_used', .55) * .85))
    fill = min(1.0, used / target)
    # copy should not cover the photo subject more than the designer's own layout did
    under = _subject_under_copy(out, a)
    excess = max(0.0, under - a.get('_orig_under', 0.0) - .03)
    faces = any((sub.get('inner_source') if sub.get('source') == 'whole' else sub.get('source')) in ('faces', 'people')
                or sub.get('faces_in_focus') for sub in a['subjects'].values())
    clear = max(0.0, 1 - (6 if faces else 3) * excess)       # copy on a face is worse than on an object
    # presence: the headline, the button and the main photo keep about the weight they had on the original canvas
    W0, H0 = float(original['page']['width']), float(original['page']['height'])
    on = {n['id']: n for n in original['nodes']}
    pres = []
    for role in ('headline', 'cta'):
        ids_ = [n['id'] for n in orig_texts if roles.get(n['id']) == role and shown(n['id'], False) > 0]
        if ids_:
            i = max(ids_, key=lambda x: float((on[x].get('style') or {}).get('fontSize') or 0))
            r0 = float((on[i].get('style') or {}).get('fontSize') or 0) / min(W0, H0)
            r1 = dsize(out[i]) / min(W, H)
            if r0 > 0:
                pres.append(min(1.0, (r1 / r0) / .6))
    photos0 = [n for n in original['nodes'] if n['type'] == 'image' and roles.get(n['id']) in ('hero', 'image')]
    if photos0:
        p0 = max(photos0, key=lambda n: n['box'][2] * n['box'][3])
        n1 = out.get(p0['id'])
        if present(n1):
            a0_ = (p0['box'][2] * p0['box'][3]) / (W0 * H0)
            a1_ = (n1['box'][2] * n1['box'][3]) / (W * H)
            if a0_ > 0:
                pres.append(min(1.0, (a1_ / a0_) ** .5 / .6))
    else:
        # a full-bleed photo that became a panel or a thumbnail: it should still read as the design's picture
        bg0 = [n for n in original['nodes'] if n['type'] == 'image' and roles.get(n['id']) == 'background']
        if bg0:
            p0 = max(bg0, key=lambda n: n['box'][2] * n['box'][3])
            n1 = out.get(p0['id'])
            if present(n1) and p0['box'][2] * p0['box'][3] >= W0 * H0 * .5:
                a1_ = (n1['box'][2] * n1['box'][3]) / (W * H)
                pres.append(min(1.0, a1_ ** .5 / .5))
    presence = sum(pres) / len(pres) if pres else 1.0
    # balance: no big dead area (a thin photo strip with an empty half page, copy pinned to one end of a column)
    occupied = list(vb.values()) + [Box.of(n['box']) for n in design['nodes']
                                    if n['type'] == 'image' and roles.get(n['id']) == 'background' and present(n)]
    if (design.get('page') or {}).get('backdrop'):
        occupied.append(canvas)                      # a blurred photo fill behind everything is not dead space
    empty = largest_empty(occupied, W, H) if occupied else 1.0
    # as airy as the designer's own layout is fine; only dead space beyond that counts
    W0_, H0_ = float(original['page']['width']), float(original['page']['height'])
    occ0 = [Box.of(n['box']) for n in original['nodes'] if n['type'] != 'group' and 'box' in n and not n.get('hidden')
            and roles.get(n['id']) not in ('panel', 'decoration')]
    empty0 = largest_empty(occ0, W0_, H0_) if occ0 else 0.0
    balance = max(0.0, 1 - max(0.0, empty - max(.12, empty0 + .08)) * 3)
    composition = (no_overlap + inside + margins + fill + clear + presence + balance) / 7 * frame   # empty letterbox bars count against
    if presence < .8:
        notes.append('Headline, button or photo much smaller than in the original.')
    if clash:
        notes.append(f'{clash} overlap{"s" if clash > 1 else ""}.')
    if fill < .7:
        notes.append(f'Only {used * 100:.0f}% of the canvas is used.')
    if balance < .9:
        notes.append(f'An empty area covers {empty * 100:.0f}% of the canvas.')
    if frame < .98:
        notes.append(f'Empty bars: the design covers {frame * 100:.0f}% of the canvas.')
    if excess > 0:
        notes.append(f'Copy covers {under * 100:.0f}% of the photo subject.')

    parts = {'content': content, 'legibility': legibility, 'faithfulness': faithfulness, 'composition': composition}
    if subject_kept is not None:
        # losing a bit of the subject's edge is fine; cutting a real part of it (half a person, a bottle's top)
        # is not: below 90% kept the penalty grows faster
        k_ = float(subject_kept)
        parts['subject'] = k_ if k_ >= .9 else max(0.0, k_ - (.9 - k_) * 1.5)
    wsum = sum(PARTS[k] for k in parts)
    overall = sum(PARTS[k] * v for k, v in parts.items()) / wsum
    # the headline and the button carry the message: losing one costs more than its share
    for role, keep in (('headline', .7), ('cta', .85)):
        ids_ = [n['id'] for n in leaves if roles.get(n['id']) == role and n['type'] == 'text']
        if ids_ and max(shown(i) for i in ids_) < .5:
            overall *= keep
            notes.append(f'The {"headline" if role == "headline" else "button"} is lost.')
    res = {k: round(v * 100, 1) for k, v in parts.items()}
    res['subject'] = res.get('subject')
    res['overall'] = round(overall * 100, 1)
    res['notes'] = notes
    return res


def _subject_under_copy(out: dict, a: dict) -> float:
    """Share of the photo subjects' area that has text or a button drawn over it."""
    from .adapt import subject_boxes
    roles = {k: v['role'] for k, v in a['roles'].items()}
    parts = subject_boxes(out, a)
    if not parts:
        return 0.0
    copy_ = [Box.of(n['box']) for n in out.values() if not n.get('hidden') and 'box' in n and n['type'] in ('text', 'shape')
             and roles.get(n['id']) not in ('background', 'panel', 'decoration', 'logo')]
    tot = sum(q.area for _, q in parts) or 1.0
    cov = 0.0
    for _, q in parts:
        cov += min(q.area, sum(q.inter(c) for c in copy_))
    return cov / tot


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
