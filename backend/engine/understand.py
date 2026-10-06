"""Understand stage: read a design the way a designer does before resizing it.

analyze(graph) returns a JSON-ready dict:
  layers         background / panels / decoration / content
  roles          per leaf: headline, subhead, eyebrow, body, offer, cta, legal, logo, hero, image, ...
  groups         elements that belong together (text stacks, buttons, lockups, cards)
  grid           margins, shared alignment lines, dominant alignment
  anchors        which page edges each group hugs
  reading_order  groups in the order a reader meets them
  subjects       the part of each photo that must survive a crop
  style          overall structure (overlay, split, stacked, single) and alignment
  notes          the same findings in plain English (shown in the X-ray view)

Everything is deterministic and explainable: thresholds are relative to the page and to
the elements' own sizes, so the same rules work for a 300x250 banner and a 1080x1920 story.
"""
from __future__ import annotations

import re

from .graph import Box, Graph, Node, load
from .subject import find_subject, smart_crop

ROLE_WEIGHT = {
    'headline': 1.0, 'hero': .95, 'cta': .9, 'offer': .85, 'logo': .8, 'subhead': .7, 'photo': .65,
    'image': .6, 'eyebrow': .55, 'badge': .55, 'item': .5, 'body': .5, 'price': .5, 'caption': .45,
    'legal': .4, 'shape': .3, 'panel': .2, 'decoration': .1, 'background': .3,
}
OFFER_RE = re.compile(r'\d+\s?%|[$€£₹]\s?\d|\b\d+\s?(off|free)\b|\boff\b|\bfree\b|\bbogo\b', re.I)
LEGAL_RE = re.compile(r'[©®™*†]|\bterms\b|\bconditions\b|\bapply\b|\bvalid\b|\bexpires?\b|\brestrictions?\b|\btax\b'
                      r'|\bmay change\b|\bsubject to\b|\brequired\b|\bexclud|\bparticipating\b|\bwhile stocks?\b|\bselected\b', re.I)


# ---------------------------------------------------------------- helpers

def _overlap_1d(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


def _words(text):
    return len((text or '').split())


def _lines(t) -> int:
    return max(1, round(t.box.h / (t.font_size * float(t.style.get('lineHeight') or 1.15))))


class _DSU:
    def __init__(self, items):
        self.p = {i: i for i in items}

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


# ---------------------------------------------------------------- 1. layers

def classify_layers(g: Graph) -> dict:
    page = g.page
    pa = page.area
    short = min(g.width, g.height)
    leaves = g.leaves()
    texts = [n for n in leaves if n.type == 'text']
    out = {'background': [], 'panels': [], 'containers': {}, 'decoration': [], 'content': []}
    for n in leaves:
        cover = n.box.inter(page) / pa
        if n.role == 'background' or (n.type != 'text' and cover >= .85):
            out['background'].append(n.id); continue
        if n.role == 'decoration':
            out['decoration'].append(n.id); continue
        if n.type == 'text':
            out['content'].append(n.id); continue
        inside = [t.id for t in texts if t.z > n.z and n.box.contains(t.box, slack=2)]
        thin = min(n.box.w, n.box.h) <= max(2.0, short * .006)
        if n.type == 'shape' and inside and cover <= .25:
            out['containers'][n.id] = inside
            out['content'].append(n.id); continue
        if n.type == 'shape' and cover > .25:
            out['panels'].append(n.id); continue
        if n.type == 'shape' and (thin or cover < .06 or not inside):
            out['decoration'].append(n.id); continue
        out['content'].append(n.id)
    return out


# ---------------------------------------------------------------- 2. roles

CTA_VERBS = {'shop', 'buy', 'get', 'book', 'order', 'start', 'save', 'sign', 'join', 'learn', 'download', 'try',
             'register', 'rsvp', 'subscribe', 'watch', 'read', 'discover', 'explore', 'see', 'view', 'claim',
             'reserve', 'apply', 'contact', 'call', 'donate', 'play', 'install', 'open', 'go', 'continue', 'find',
             'request', 'grab', 'reach', 'visit', 'listen', 'meet', 'check'}
STORE_RE = re.compile(r'app store|google play|play store|microsoft store', re.I)
PRICE_ONLY_RE = re.compile(r'^\s*(from\s+)?[$€£₹]\s?\d[\d.,]*\s*$|^\s*\d[\d.,]*\s?[$€£₹]\s*$', re.I)


def _style_key(t: Node):
    return (round(t.font_size), t.font_weight, str(t.style.get('color', '')).lower())


def _is_text_logo(t: Node, g: Graph, hs: float) -> bool:
    words = _words(t.text)
    txt = (t.text or '').strip()
    caps = txt.upper() == txt and any(c.isalpha() for c in txt)
    near_edge = t.box.y <= g.height * .12 or t.box.b >= g.height * .88
    return (words <= 3 and near_edge and t.font_weight >= 700 and t.font_size <= hs * .6
            and (caps or float(t.style.get('letterSpacing') or 0) > 0))


def infer_roles(g: Graph, layers: dict) -> dict:
    pa = g.width * g.height
    roles: dict[str, dict] = {}
    def put(nid, role, source='inferred', conf=.6): roles[nid] = {'role': role, 'source': source, 'confidence': conf}
    contained = {t: c for c, ts in layers['containers'].items() for t in ts}
    for nid in layers['background']: put(nid, 'background', 'layout', .95)
    for nid in layers['decoration']: put(nid, 'decoration', 'layout', .8)
    for nid in layers['panels']: put(nid, 'panel', 'layout', .8)
    for n in g.leaves():   # author-given roles always win
        if n.role and n.id not in roles:
            put(n.id, n.role, 'given', 1.0)

    texts = [g.by_id[i] for i in layers['content'] if g.by_id[i].type == 'text']
    images = [g.by_id[i] for i in layers['content'] if g.by_id[i].type == 'image']
    def strength(t): return t.font_size * (1 + (t.font_weight - 400) / 1000)
    candidates = [t for t in texts if t.id not in contained and t.id not in roles]
    given_head = next((t for t in texts if roles.get(t.id, {}).get('role') == 'headline'), None)
    if not given_head and candidates:
        top = max(t.font_size for t in candidates)
        wordy = [t for t in candidates if not (OFFER_RE.search(t.text or '') and _words(t.text) <= 4)
                 and not PRICE_ONLY_RE.search(t.text or '') and t.font_size >= top * .25]
        if wordy and len(wordy) < len(candidates):
            candidates = wordy      # "50% OFF" is the offer; the headline is the words around it
    head = given_head or (max(candidates, key=lambda t: (strength(t), -t.box.y)) if candidates else None)
    hs = head.font_size if head else max((t.font_size for t in texts), default=16)
    sizes = sorted(t.font_size for t in texts if t.id not in contained) or [16]
    median = sizes[len(sizes) // 2]
    free_texts = [t for t in texts if t.id not in contained]
    base = max(free_texts, key=lambda t: len(t.text or '')).font_size if free_texts else 16   # body size
    style_count: dict = {}
    for t in texts:
        if t.id not in contained: style_count[_style_key(t)] = style_count.get(_style_key(t), 0) + 1

    # containers first: buttons and badges
    for t in texts:
        if t.id in roles or t.id not in contained: continue
        c = g.by_id[contained[t.id]]
        ratio = c.box.w / max(c.box.h, 1)
        first = ((t.text or '').strip().split() or [''])[0].lower().strip('!.,')
        pill = float(c.style.get('radius') or 0) >= c.box.h / 3
        if first in CTA_VERBS or STORE_RE.search(t.text or ''):
            put(t.id, 'cta', conf=.9)
        elif pill and 1.6 <= ratio <= 12 and _words(t.text) <= 4 and c.box.area / pa <= .06:
            put(t.id, 'cta', conf=.6)
        elif OFFER_RE.search(t.text or '') and _words(t.text) <= 6:
            put(t.id, 'offer', conf=.7)
        else:
            put(t.id, 'badge' if _words(t.text) <= 4 else 'body', conf=.6)

    # captions: text hanging under an image (and lines hanging under those captions)
    captions: list[Node] = []
    for t in sorted(texts, key=lambda n: n.box.y):
        if t.id in roles or t.id in contained or t is head: continue
        tol = max(4.0, g.width * .01)
        for anchor in images + captions:
            below = (anchor.box.x - tol <= t.box.x and t.box.r <= anchor.box.r + tol
                     and 0 <= t.box.y - anchor.box.b <= t.font_size * 1.6 and anchor.box.area / pa <= .2)
            beside = (anchor in images and anchor.box.area / pa <= .04 and 0 <= t.box.x - anchor.box.r <= anchor.box.w * .6
                      and anchor.box.y - tol <= t.box.y and t.box.b <= anchor.box.b + tol)
            if below or beside:
                captions.append(t); break
    for t in captions:
        put(t.id, 'price' if PRICE_ONLY_RE.search(t.text or '') else 'caption', conf=.65)

    for t in texts:
        if t.id in roles: continue
        if t is head:
            put(t.id, 'headline', conf=.9); continue
        fs, words, txt = t.font_size, _words(t.text), t.text or ''
        h_overlap = head is not None and _overlap_1d(t.box.x, t.box.r, head.box.x, head.box.r) >= .3 * min(t.box.w, head.box.w)
        repeated = style_count.get(_style_key(t), 0) >= 3
        if PRICE_ONLY_RE.search(txt):
            put(t.id, 'price', conf=.8)
        elif _is_text_logo(t, g, hs):
            put(t.id, 'logo', conf=.6)
        elif OFFER_RE.search(txt) and words <= 5:
            put(t.id, 'offer', conf=.75)
        elif fs <= min(sizes[-1] * .3, median) and fs <= sizes[0] * 1.05 and t.box.cy > g.height * .7 \
                and (LEGAL_RE.search(txt) or words >= 12):
            put(t.id, 'legal', conf=.7)
        elif repeated:
            put(t.id, 'item', conf=.6)
        elif head and h_overlap and fs <= hs * .5 and words <= 5 and t.box.b <= head.box.y + 2 \
                and head.box.y - t.box.b <= hs * 1.5:
            put(t.id, 'eyebrow', conf=.65)
        elif head and h_overlap and hs * .3 <= fs <= hs * .85 and 0 <= t.box.y - head.box.b <= hs * 1.6 \
                and (_lines(t) == 1 or fs >= hs * .5):
            put(t.id, 'subhead', conf=.7)
        elif fs >= base * 1.5 and words <= 10:
            put(t.id, 'subhead', conf=.55)
        else:
            put(t.id, 'body', conf=.5)

    for nid in layers['content']:
        n = g.by_id[nid]
        if nid in roles: continue
        if n.type == 'shape':   # containers take the role of their text
            inner = [roles.get(t, {}).get('role') for t in layers['containers'].get(nid, [])]
            put(nid, 'cta' if 'cta' in inner else ('badge' if inner else 'shape'), conf=.7); continue
        frac = n.box.area / pa
        near_edge = min(n.box.x, n.box.y, g.width - n.box.r, g.height - n.box.b) <= min(g.width, g.height) * .15
        if frac >= .12:
            put(nid, 'hero', conf=.8)
        elif frac <= .035 and near_edge and n.box.w >= n.box.h * 1.4:
            put(nid, 'logo', conf=.55)
        else:
            put(nid, 'image', conf=.6)
    return roles


# ---------------------------------------------------------------- 3. groups

def _units(g: Graph, layers: dict, roles: dict | None = None) -> list[dict]:
    """Atoms for grouping: explicit groups, containers with their text, then single leaves."""
    pa = g.width * g.height
    content = set(layers['content'])
    taken: set[str] = set()
    units = []
    for grp in g.groups():
        if grp.parent:   # only top-level groups
            continue
        kids = [k.id for k in g.descendants(grp) if k.id in content]
        if not kids or grp.box.area / pa > .85:
            continue
        units.append({'members': kids, 'explicit': grp.id})
        taken.update(kids)
    for c, ts in layers['containers'].items():
        if c in taken: continue
        members = [c] + [t for t in ts if t not in taken]
        units.append({'members': members, 'container': c})
        taken.update(members)
    for nid in layers['content']:
        if nid not in taken:
            units.append({'members': [nid]})
            taken.add(nid)
    for u in units:
        nodes = [g.by_id[m] for m in u['members']]
        u['logo'] = any((roles or {}).get(n.id, {}).get('role') == 'logo' for n in nodes)
        u['box'] = Box.bound(n.box for n in nodes)
        u['textual'] = any(n.type == 'text' for n in nodes)
        u['image'] = all(n.type == 'image' for n in nodes)
        u['fs'] = max((n.font_size for n in nodes if n.type == 'text'), default=u['box'].h * .5)
        u['single_text'] = len(nodes) == 1 and nodes[0].type == 'text'
        u['align'] = nodes[0].style.get('align', 'left') if u['single_text'] else None
    return units


def _between(a: Box, b: Box, others: list[Box]) -> bool:
    """Is any other box sitting in the horizontal corridor between a and b?"""
    left, right = (a, b) if a.x <= b.x else (b, a)
    y0, y1 = max(a.y, b.y), min(a.b, b.b)
    return any(o.x >= left.r - 1 and o.r <= right.x + 1 and _overlap_1d(o.y, o.b, y0, y1) > 0 for o in others)


def _divided(upper: Box, lower: Box, dividers: list[Box]) -> bool:
    """A divider line or panel edge between two stacked boxes means they are separate blocks."""
    x0, x1 = max(upper.x, lower.x), min(upper.r, lower.r)
    return any(d.y >= upper.b - 1 and d.b <= lower.y + 1 and _overlap_1d(d.x, d.r, x0, x1) > 0 for d in dividers)


def _should_join(a: dict, b: dict, g: Graph, others, dividers: list[Box] = ()) -> bool:
    """`others` is a callable returning the boxes of all other units (only needed for row checks)."""
    if a['logo'] or b['logo']:
        return False      # a logo is always its own block: it gets anchored, not re-flowed with copy
    A, B = a['box'], b['box']
    short = min(g.width, g.height)
    pa = g.width * g.height
    tol = max(4.0, g.width * .008)
    if a['textual'] and b['textual']:
        if A.inter(B) > 0:
            return True
        big, small = max(a['fs'], b['fs']), min(a['fs'], b['fs'])
        upper, lower = (A, B) if A.y <= B.y else (B, A)
        vgap = lower.y - upper.b
        aligned = (abs(A.x - B.x) <= tol or abs(A.cx - B.cx) <= tol or abs(A.r - B.r) <= tol
                   or _overlap_1d(A.x, A.r, B.x, B.r) >= .3 * min(A.w, B.w))
        if aligned and -2 <= vgap <= .6 * big + .5 * small + .01 * short and not _divided(upper, lower, dividers):
            return True
        left, right = (A, B) if A.x <= B.x else (B, A)
        hgap = right.x - left.r
        voverlap = _overlap_1d(A.y, A.b, B.y, B.b)
        if voverlap >= .5 * min(A.h, B.h) and -2 <= hgap <= .8 * small + .01 * short:
            return True
        # label ... value rows (menus, spec lists): same size, same line, nothing in between
        lu, ru = (a, b) if A.x <= B.x else (b, a)
        if a['single_text'] and b['single_text'] and abs(a['fs'] - b['fs']) <= .1 * big \
                and lu['align'] == 'left' and ru['align'] == 'right' \
                and voverlap >= .8 * min(A.h, B.h) and hgap > 0 and not _between(A, B, others()):
            return True
        return False
    if a['image'] != b['image'] and (a['textual'] or b['textual']):
        img, txt = (A, B) if a['image'] else (B, A)
        tu = b if a['image'] else a
        left, right = (img, txt) if img.x <= txt.x else (txt, img)
        if img.area / pa <= .04 and _overlap_1d(img.y, img.b, txt.y, txt.b) >= .5 * min(img.h, txt.h) \
                and 0 <= right.x - left.r <= max(img.h, img.w) * .6:
            return True   # logo lockup, avatar + name
        if img.area / pa <= .2 and img.x - tol <= txt.x and txt.r <= img.r + tol \
                and 0 <= txt.y - img.b <= tu['fs'] * 1.6:
            return True   # image with caption underneath
    return False


def find_groups(g: Graph, layers: dict, roles: dict) -> list[dict]:
    units = _units(g, layers, roles)
    dsu = _DSU(range(len(units)))
    boxes = [u['box'] for u in units]
    dividers = [g.by_id[d].box for d in layers['decoration'] if g.by_id[d].type == 'shape'
                and g.by_id[d].box.h <= max(4.0, g.height * .01)]
    for i in range(len(units)):
        for j in range(i + 1, len(units)):
            if units[i].get('explicit') or units[j].get('explicit'):
                continue   # author-made groups are kept as they are
            others = (lambda i=i, j=j: [b for k, b in enumerate(boxes) if k not in (i, j)])
            if _should_join(units[i], units[j], g, others, dividers):
                dsu.union(i, j)
    buckets: dict[int, list[dict]] = {}
    for i, u in enumerate(units):
        buckets.setdefault(dsu.find(i), []).append(u)
    pa = g.width * g.height
    groups = []
    for k, us in sorted(buckets.items(), key=lambda kv: (Box.bound(u['box'] for u in kv[1]).y, kv[0])):
        members = [m for u in us for m in u['members']]
        nodes = [g.by_id[m] for m in members]
        box = Box.bound(n.box for n in nodes)
        mroles = [roles.get(m, {}).get('role', 'image') for m in members]
        types = {n.type for n in nodes}
        has_container = any(m in layers['containers'] for m in members)
        n_text = sum(1 for n in nodes if n.type == 'text')
        imgs = [n for n in nodes if n.type == 'image']
        if has_container and types <= {'shape', 'text'} and n_text <= 2 * max(1, sum(1 for m in members if m in layers['containers'])):
            kind = 'button' if 'cta' in mroles else 'badge'
        elif types == {'image'}:
            kind = 'image'
        elif types <= {'text', 'shape'}:
            common = min(u['box'].b for u in us) - max(u['box'].y for u in us)
            kind = 'text' if n_text == 1 and len(members) == 1 else (
                'row' if len(us) > 1 and common >= .5 * min(u['box'].h for u in us) else 'text-stack')
        elif imgs and all(i.box.area / pa <= .04 for i in imgs):
            kind = 'lockup'
        else:
            kind = 'card'
        if kind == 'card':
            role = max((roles.get(i.id, {}).get('role', 'image') for i in imgs), key=lambda r: ROLE_WEIGHT.get(r, .5))
        else:
            role = max(mroles, key=lambda r: ROLE_WEIGHT.get(r, .5))
        explicit = next((u['explicit'] for u in us if u.get('explicit')), None)
        align = None
        aligns = [n.style.get('align', 'left') for n in nodes if n.type == 'text' and n.id not in
                  {t for ts in layers['containers'].values() for t in ts}]
        if aligns:
            align = max(set(aligns), key=aligns.count)
        groups.append({'id': explicit or f'g{len(groups) + 1}', 'kind': kind, 'members': members,
                       'box': box, 'role': role, 'importance': ROLE_WEIGHT.get(role, .5),
                       'explicit': bool(explicit), 'text_align': align})
    return groups


def find_repeats(g: Graph, groups: list[dict]) -> list[dict]:
    """Groups that repeat a pattern (cards in a row, rows in a list). They should re-flow together."""
    tol = max(4.0, min(g.width, g.height) * .01)
    used, out = set(), []
    for i, a in enumerate(groups):
        if a['id'] in used or a['kind'] in ('button',) and a['role'] == 'cta': continue
        A = a['box']
        same = [b for b in groups if b['kind'] == a['kind'] and b['id'] not in used
                and abs(b['box'].w - A.w) <= max(tol, .1 * A.w) and abs(b['box'].h - A.h) <= max(tol, .1 * A.h)]
        for axis, key in (('row', lambda x: x['box'].y), ('column', lambda x: x['box'].x)):
            line = [b for b in same if abs(key(b) - key(a)) <= tol]
            if len(line) >= 2:
                line.sort(key=lambda x: x['box'].x if axis == 'row' else x['box'].y)
                gaps = [(line[k + 1]['box'].x - line[k]['box'].r) if axis == 'row' else (line[k + 1]['box'].y - line[k]['box'].b)
                        for k in range(len(line) - 1)]
                if min(gaps) >= -1 and max(gaps) - min(gaps) <= max(tol, .15 * max(gaps)):
                    out.append({'axis': axis, 'groups': [x['id'] for x in line], 'gap': round(sum(gaps) / len(gaps), 1),
                                'kind': a['kind']})
                    used.update(x['id'] for x in line)
                    break
    return out


# ---------------------------------------------------------------- 4. grid, anchors, order

def _cluster(values, tol):
    """values: list of (pos, member). Returns clusters as (mean_pos, members)."""
    out = []
    for pos, m in sorted(values):
        if out and pos - out[-1][2] <= tol:
            out[-1][1].append(m); out[-1][2] = pos
            out[-1][0].append(pos)
        else:
            out.append([[pos], [m], pos])
    return [(sum(p) / len(p), ms) for p, ms, _ in out]


def find_grid(g: Graph, layers: dict, groups: list[dict]) -> dict:
    W, H = g.width, g.height
    boxes = [gr['box'] for gr in groups] or [g.page]
    def side(dists, dim):   # nearest non-bleeding content to that edge
        keep = [d for d in dists if d > dim * .01]
        return round(min(keep), 1) if keep else 0.0
    margins = {'left': side([b.x for b in boxes], W), 'top': side([b.y for b in boxes], H),
               'right': side([W - b.r for b in boxes], W), 'bottom': side([H - b.b for b in boxes], H)}
    leaves = [g.by_id[i] for i in layers['content']]
    tol = max(4.0, W * .006)
    lines = []
    in_box = {x for ts in layers['containers'].values() for x in ts}
    def counts(n, kind):   # text only defines the edge it is aligned to; the rest of its box is empty space
        if n.id in in_box: return False      # button labels follow their button
        if n.type != 'text': return True
        return n.style.get('align', 'left') == kind
    for kind, f in (('left', lambda b: b.x), ('center', lambda b: b.cx), ('right', lambda b: b.r)):
        for pos, ms in _cluster([(f(n.box), n.id) for n in leaves if counts(n, kind)], tol):
            if len(set(ms)) >= 2:
                lines.append({'axis': 'x', 'kind': kind, 'pos': round(pos, 1), 'members': sorted(set(ms)),
                              'page_centre': kind == 'center' and abs(pos - W / 2) <= tol})
    tol_y = max(4.0, H * .006)
    for kind, f in (('top', lambda b: b.y), ('middle', lambda b: b.cy), ('bottom', lambda b: b.b)):
        for pos, ms in _cluster([(f(n.box), n.id) for n in leaves], tol_y):
            if len(set(ms)) >= 2:
                lines.append({'axis': 'y', 'kind': kind, 'pos': round(pos, 1), 'members': sorted(set(ms))})
    # dominant text alignment, weighted by amount of text
    votes = {'left': 0.0, 'center': 0.0, 'right': 0.0}
    in_container = {x for ts in layers['containers'].values() for x in ts}
    for n in leaves:
        if n.type == 'text' and n.id not in in_container:
            votes[n.style.get('align', 'left')] = votes.get(n.style.get('align', 'left'), 0) + len(n.text or '') + 1
    total = sum(votes.values())
    best = max(votes, key=votes.get) if total else 'left'
    alignment = best if total and votes[best] / total >= .6 else ('mixed' if total else 'none')
    return {'margins': margins, 'lines': lines, 'alignment': alignment}


def _column(gr: dict, tall: list[dict], W: float) -> tuple[float, float]:
    """The horizontal band a group lives in: the page, or the space beside a tall photo/card."""
    b, tol = gr['box'], W * .01
    x0 = max([v['box'].r for v in tall if v is not gr and v['box'].r <= b.x + tol], default=0.0)
    x1 = min([v['box'].x for v in tall if v is not gr and v['box'].x >= b.r - tol], default=W)
    return x0, x1


def find_blocks(g: Graph, groups: list[dict], repeats: list[dict], dividers: list[Box]) -> list[dict]:
    """Second level of the grouping hierarchy (designers group hierarchically: a headline stack and its
    button form one "copy block"; repeated cards form one row). Groups are nested in exactly one block.

    Cues, as in the layout-grouping literature: proximity, shared alignment edge, same column, and a
    divider line or panel edge breaking a block. Logos, legal lines and photos stay blocks of their own
    because they are anchored, not re-flowed with the copy."""
    W, H = g.width, g.height
    by_id = {gr['id']: gr for gr in groups}
    blocks, used = [], set()
    for r in repeats:
        members = [i for i in r['groups'] if i in by_id]
        if len(members) >= 2:
            blocks.append({'kind': 'repeat', 'groups': members})
            used.update(members)
    alone = {'logo', 'legal', 'hero', 'background', 'decoration'}
    def cornered(gr):   # pinned to a page corner (a date badge top-left): anchored, not part of the copy flow
        a = set(gr.get('anchors', []))
        return bool(a & {'top', 'bottom'}) and bool(a & {'left', 'right'}) and gr['role'] != 'headline' and gr['kind'] != 'button'
    cand = [gr for gr in groups if gr['id'] not in used and gr['role'] not in alone
            and gr['kind'] not in ('image', 'card') and not cornered(gr)]
    dsu = _DSU(range(len(cand)))
    tol = max(4.0, W * .01)
    for i, a in enumerate(cand):
        for j in range(i + 1, len(cand)):
            b = cand[j]
            A, B = a['box'], b['box']
            if a.get('column') != b.get('column'):
                continue
            aligned = (abs(A.x - B.x) <= tol or abs(A.cx - B.cx) <= tol or abs(A.r - B.r) <= tol
                       or _overlap_1d(A.x, A.r, B.x, B.r) >= .3 * min(A.w, B.w))
            upper, lower = (A, B) if A.y <= B.y else (B, A)
            gap = lower.y - upper.b
            if aligned and -2 <= gap <= max(H * .08, 1.2 * min(A.h, B.h)) and not _divided(upper, lower, dividers):
                dsu.union(i, j)
    buckets: dict[int, list[dict]] = {}
    for i, gr in enumerate(cand):
        buckets.setdefault(dsu.find(i), []).append(gr)
    for members in buckets.values():
        if len(members) >= 2:
            blocks.append({'kind': 'copy' if any(m['role'] == 'headline' for m in members) else 'stack',
                           'groups': [m['id'] for m in sorted(members, key=lambda m: m['box'].y)]})
            used.update(m['id'] for m in members)
    for gr in groups:
        if gr['id'] not in used:
            blocks.append({'kind': 'single', 'groups': [gr['id']]})
    order = {gid: i for i, gid in enumerate(gr['id'] for gr in sorted(groups, key=lambda x: (x['box'].y, x['box'].x)))}
    blocks.sort(key=lambda bl: min(order[x] for x in bl['groups']))
    for i, bl in enumerate(blocks):
        bl['id'] = f'b{i + 1}'
        bl['box'] = Box.bound(by_id[x]['box'] for x in bl['groups']).list()
        for x in bl['groups']:
            by_id[x]['block'] = bl['id']
    return blocks


def find_anchors(g: Graph, groups: list[dict], margins: dict) -> None:
    """Which edges each group follows. Groups beside a tall photo are anchored within their column."""
    W, H = g.width, g.height
    tall = [x for x in groups if x['kind'] in ('image', 'card') and x['box'].h >= H * .7]
    cols = {x['id']: _column(x, tall, W) for x in groups}
    for gr in groups:
        b = gr['box']
        x0, x1 = cols[gr['id']]
        cw = x1 - x0
        same = [o['box'] for o in groups if cols[o['id']] == (x0, x1)]
        def side(dists):
            keep = [d for d in dists if d > cw * .01]
            return min(keep) if keep else 0.0
        if (x0, x1) == (0.0, W):
            ml, mr = margins['left'], margins['right']
        else:
            ml, mr = side([o.x - x0 for o in same]), side([x1 - o.r for o in same])
            gr['column'] = [round(x0, 1), round(x1, 1)]
        a = []
        left = b.x - x0 <= ml + W * .04 and b.x - x0 <= cw * .2
        right = x1 - b.r <= mr + W * .04 and x1 - b.r <= cw * .2
        centred = abs(b.cx - (x0 + x1) / 2) <= cw * .03
        if left and right:   # spans margin to margin: its own text alignment says which edge it follows
            if (b.w >= cw * .9 and gr['kind'] in ('image', 'card')) or gr['kind'] == 'row': a += ['left', 'right']
            elif gr.get('text_align') == 'center' or (gr.get('text_align') is None and centred): a.append('center-x')
            elif gr.get('text_align') == 'right': a.append('right')
            else: a.append('left')
        elif left: a.append('left')
        elif right: a.append('right')
        elif centred: a.append('center-x')
        if b.y <= margins['top'] + H * .04 and b.y <= H * .15: a.append('top')
        if H - b.b <= margins['bottom'] + H * .04 and H - b.b <= H * .15: a.append('bottom')
        if abs(b.cy - H / 2) <= H * .02 and 'top' not in a and 'bottom' not in a: a.append('center-y')
        if b.w >= W * .9 and 'fill-x' not in a: a.append('fill-x')
        gr['anchors'] = a


def _cut(items: list[dict], axis: str) -> list[list[dict]] | None:
    """Split items where their projection on `axis` has a gap (recursive XY-cut)."""
    lo, hi = ('y', 'b') if axis == 'y' else ('x', 'r')
    items = sorted(items, key=lambda x: getattr(x['box'], lo))
    parts, cur, reach = [], [items[0]], getattr(items[0]['box'], hi)
    for it in items[1:]:
        start = getattr(it['box'], lo)
        if start >= reach - 1:   # whitespace gap: a new band starts here
            parts.append(cur); cur = [it]
        else:
            cur.append(it)
        reach = max(reach, getattr(it['box'], hi))
    parts.append(cur)
    return parts if len(parts) > 1 else None


def reading_order(groups: list[dict]) -> list[str]:
    """Rows top to bottom; inside a row, columns left to right (XY-cut, like reading a page)."""
    def walk(items):
        if len(items) <= 1:
            return [x['id'] for x in items]
        span = Box.bound(x['box'] for x in items)
        cols = _cut(items, 'x')   # true columns first: each one at least half as tall as the whole
        if cols and all(Box.bound(x['box'] for x in c).h >= .5 * span.h for c in cols):
            return [i for c in cols for i in walk(c)]
        for axis in ('y', 'x'):
            parts = _cut(items, axis)
            if parts:
                return [i for p in parts for i in walk(p)]
        return [x['id'] for x in sorted(items, key=lambda x: (round(x['box'].y), x['box'].x))]
    return walk(list(groups)) if groups else []


def overall_style(g: Graph, layers: dict, groups: list[dict], roles: dict, grid: dict, repeats=()) -> dict:
    bg_images = [i for i in layers['background'] if g.by_id[i].type == 'image']
    text_groups = [x for x in groups if x['kind'] in ('text', 'text-stack', 'row', 'button', 'badge', 'lockup')]
    heroes = [x for x in groups if x['role'] in ('hero', 'photo') or x['kind'] in ('image', 'card') and x['box'].area > g.width * g.height * .12]
    structure = 'single'
    if bg_images and text_groups:
        structure = 'overlay'
    visual = heroes or [x for x in groups if x['kind'] in ('image', 'card') and x['role'] != 'logo']
    if structure == 'single' and visual and text_groups:
        hb = Box.bound(x['box'] for x in visual)
        main = [x for x in text_groups if x['role'] == 'headline'] or [x for x in text_groups if x['role'] != 'logo']
        tb = Box.bound(x['box'] for x in main) if main else None
        if tb is not None:
            if _overlap_1d(hb.x, hb.r, tb.x, tb.r) <= .15 * min(hb.w, tb.w):
                structure = 'split-horizontal'
            elif _overlap_1d(hb.y, hb.b, tb.y, tb.b) <= .15 * min(hb.h, tb.h):
                structure = 'stacked'
            else:
                structure = 'overlap'
    centred = sum(1 for x in text_groups if 'center-x' in x.get('anchors', []))
    # coverage: share of the page covered by content groups (sampled)
    n, hit = 48, 0
    boxes = [x['box'] for x in groups]
    for i in range(n):
        for j in range(n):
            px, py = (i + .5) * g.width / n, (j + .5) * g.height / n
            if any(b.x <= px <= b.r and b.y <= py <= b.b for b in boxes):
                hit += 1
    cover = hit / (n * n)
    return {'structure': structure, 'alignment': grid['alignment'],
            'repeated_cards': any(r['kind'] in ('card', 'image') for r in repeats),
            'centred_groups': centred, 'coverage': round(cover, 3),
            'density': 'airy' if cover < .35 else ('balanced' if cover < .65 else 'dense')}


# ---------------------------------------------------------------- 5. notes

def _notes(g, layers, roles, groups, grid, style, subjects) -> list[str]:
    notes = []
    s = style['structure']
    notes.append({'overlay': 'Text sits over a full-bleed photo.',
                  'split-horizontal': 'Image and text sit side by side.',
                  'stacked': 'Image and text are stacked vertically.',
                  'overlap': 'Image and text overlap.',
                  'single': 'One main content area.'}[s])
    if grid['alignment'] in ('left', 'center', 'right'):
        notes.append(f"Text is mostly {grid['alignment']}-aligned.")
    elif grid['alignment'] == 'mixed':
        notes.append('Text alignment is mixed.')
    m = grid['margins']
    notes.append(f"Margins: left {m['left']:.0f}, top {m['top']:.0f}, right {m['right']:.0f}, bottom {m['bottom']:.0f} px.")
    cols = {tuple(gr['column']) for gr in groups if gr.get('column')}
    for c0, c1 in sorted(cols):
        notes.append(f"Content beside the tall image forms a column at x {c0:.0f}–{c1:.0f}; it is anchored within that column.")
    shared = [l for l in grid['lines'] if l['axis'] == 'x' and len(l['members']) >= 3]
    for l in shared[:3]:
        notes.append(f"{len(l['members'])} elements share a {l['kind']} edge at x={l['pos']:.0f}.")
    grouped: dict[str, int] = {}
    for gr in groups:
        if len(gr['members']) > 1 and gr['kind'] not in ('button', 'badge'):
            names = [roles.get(mm, {}).get('role', mm) for mm in gr['members']]
            names = [x for x in names if x not in ('shape', 'badge')] or names
            line = f"Grouped ({gr['kind']}): {', '.join(dict.fromkeys(names))}"
            grouped[line] = grouped.get(line, 0) + 1
    notes += [f"{line} (×{n})." if n > 1 else f"{line}." for line, n in grouped.items()]
    for gr in groups:
        corner = [a for a in gr['anchors'] if a in ('top', 'bottom', 'left', 'right')]
        if len(corner) == 2 and gr['role'] in ('logo', 'cta', 'legal', 'offer', 'badge'):
            label = {'cta': 'Button', 'logo': 'Logo', 'legal': 'Legal line', 'offer': 'Offer', 'badge': 'Badge'}[gr['role']]
            notes.append(f"{label} is anchored {'-'.join(reversed(corner)) if corner[0] in ('left', 'right') else '-'.join(corner)}.")
    for iid, sub in subjects.items():
        if sub['source'] != 'assumed':
            how = {'given': 'marked in the design', 'faces': 'found by face detection', 'people': 'found by person detection',
                   'objects': 'found by object detection', 'saliency': 'found by saliency'}[sub['source']]
            notes.append(f"Subject of photo “{iid}” {how}.")
    if layers['decoration']:
        notes.append(f"{len(layers['decoration'])} decorative element(s) can move or drop when space is tight.")
    notes.append(f"Content covers {style['coverage'] * 100:.0f}% of the page ({style['density']}).")
    return notes


# ---------------------------------------------------------------- public

def analyze(design, targets: list[dict] | None = None) -> dict:
    g = design if isinstance(design, Graph) else load(design)
    layers = classify_layers(g)
    roles = infer_roles(g, layers)
    groups = find_groups(g, layers, roles)
    grid = find_grid(g, layers, groups)
    find_anchors(g, groups, grid['margins'])
    order = reading_order(groups)
    repeats = find_repeats(g, groups)
    dividers = [g.by_id[d].box for d in layers['decoration'] if g.by_id[d].type == 'shape'
                and g.by_id[d].box.h <= max(4.0, g.height * .01)]
    blocks = find_blocks(g, groups, repeats, dividers)
    style = overall_style(g, layers, groups, roles, grid, repeats)
    subjects = {}
    for n in g.leaves():
        if n.type == 'image' and roles.get(n.id, {}).get('role') not in ('logo', 'decoration'):
            sub = find_subject(n)
            slot = n.box.w / n.box.h if n.box.h else 1.0
            if sub.get('aspect'):
                # detected on the whole photo: choose the crop around the subject
                sub.update(smart_crop(sub['box'], sub['aspect'], slot, sub.get('parts')))
                cx, cy, cw, ch = sub['crop']
            else:
                # given by the designer (relative to the slot as shown) or photo not readable:
                # no crop decision; the renderer keeps its default cover fit
                cx, cy, cw, ch = 0.0, 0.0, 1.0, 1.0
            def to_page(b):   # image-relative box -> inside the shown crop (clipped) -> page coordinates
                bx, by, bw, bh = b
                x0, y0 = max(0.0, (bx - cx) / cw), max(0.0, (by - cy) / ch)
                x1, y1 = min(1.0, (bx + bw - cx) / cw), min(1.0, (by + bh - cy) / ch)
                return Box(n.box.x + x0 * n.box.w, n.box.y + y0 * n.box.h,
                           max(0.0, x1 - x0) * n.box.w, max(0.0, y1 - y0) * n.box.h).list()
            sub['page_box'] = to_page(sub['box'])
            if sub.get('parts'):   # each face separately, only those still visible in the crop
                sub['page_parts'] = [pb for pb in (to_page(pp) for pp in sub['parts']) if pb[2] > 1 and pb[3] > 1]
            subjects[n.id] = sub
    texts = sorted((n for n in g.leaves() if n.type == 'text'), key=lambda n: -n.font_size)
    result = {
        'page': {'width': g.width, 'height': g.height,
                 'orientation': 'square' if .9 <= g.width / g.height <= 1.1 else ('landscape' if g.width > g.height else 'portrait')},
        'layers': {k: v for k, v in layers.items() if k != 'containers'} | {'containers': layers['containers']},
        'roles': roles,
        'groups': [{**gr, 'box': gr['box'].list()} for gr in groups],
        'grid': grid,
        'reading_order': order,
        'repeats': repeats,
        'blocks': blocks,
        'hierarchy': [n.id for n in texts],
        'subjects': subjects,
        'style': style,
    }
    result['notes'] = _notes(g, layers, roles, groups, grid, style, subjects)
    for bl in blocks:
        if bl['kind'] == 'copy':
            roles_in = [next(gr for gr in groups if gr['id'] == x)['role'] for x in bl['groups']]
            result['notes'].append(f"Copy block: {' + '.join(dict.fromkeys(roles_in))} move together.")
    for r in repeats:
        result['notes'].append(f"{len(r['groups'])} matching {r['kind']} groups repeat in a {r['axis']} (gap {r['gap']:.0f} px).")
    if targets:
        from .plan import plan_tier
        result['targets'] = [{**t, **plan_tier(g.width, g.height, t['width'], t['height'])} for t in targets]
    return result
