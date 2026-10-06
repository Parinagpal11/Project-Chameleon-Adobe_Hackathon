"""Deterministic, auditable rule induction from a single designer edit.

move   → order (ABOVE/BELOW vs. horizontally overlapping content), pin (dropped in a corner), align
resize → emphasis (relative prominence)
hide   → hide_small (hide this role in formats at least this small)
"""
from collections import Counter
from engine.genome import enrich_design
from engine import rules as R

NON_CONTENT = ('image', 'decoration', 'shape')


def relation(a, b):
    if a.y >= b.y + b.height - 1e-7:
        return 'BELOW'
    if a.y + a.height <= b.y + 1e-7:
        return 'ABOVE'
    return None


def _validate(before, after, moved_id, allowed):
    if before.canvas != after.canvas:
        raise ValueError('Edit within the same canvas before learning.')
    old = {e.id: e for e in before.elements}
    new = {e.id: e for e in after.elements}
    if old.keys() != new.keys() or moved_id not in old:
        raise ValueError('Keep the same elements when teaching an edit.')
    for k in old:
        ex = allowed if k == moved_id else set()
        if old[k].model_dump(exclude=ex) != new[k].model_dump(exclude=ex):
            raise ValueError('Learn one edit at a time; other elements and content must stay unchanged.')


def _corner(e, w, h):
    zx, zy = w * .14, h * .14
    v = 'top' if e.y <= zy else 'bottom' if e.y + e.height >= h - zy else None
    hz = 'left' if e.x <= zx else 'right' if e.x + e.width >= w - zx else None
    return f'{v}-{hz}' if v and hz else None


def _align(e, w):
    cx = e.x + e.width / 2
    if e.width >= w * .8:
        return None
    if abs(cx - w / 2) <= w * .04:
        return 'center'
    if e.x <= w * .12:
        return 'left'
    if e.x + e.width >= w * .88:
        return 'right'
    return None


def _proposal(rtype, params, evidence):
    params = R.normalize(rtype, params)
    out = {'type': rtype, 'params': params, 'label': R.label(rtype, params), 'evidence': evidence, 'source': 'edit'}
    if rtype == 'order':  # legacy keys kept for existing clients and tests
        out.update(params)
    return out


def infer_edit(before, after, moved_id):
    """Legacy entry point: order proposals from a position edit (sorted by gap)."""
    return [p for p in infer_any(before, after, moved_id, 'move') if p['type'] == 'order']


def infer_any(before, after, moved_id, kind='move'):
    allowed = {'move': {'x', 'y'}, 'resize': {'x', 'y', 'width', 'height', 'fontSize'},
               'hide': {'hidden', 'width', 'height'}}[kind]
    _validate(before, after, moved_id, allowed)
    before = enrich_design(before.model_copy(deep=True))
    after = enrich_design(after.model_copy(deep=True))
    old = {e.id: e for e in before.elements}
    new = {e.id: e for e in after.elements}
    a, prev = new[moved_id], old[moved_id]
    w, h = after.canvas.width, after.canvas.height
    canvas = after.canvas.model_dump()
    role = a.genome.role
    counts = Counter(e.genome.role for e in after.elements)

    if kind == 'hide':
        if not a.hidden:
            return []
        return [_proposal('hide_small', {'role': role, 'below': min(w, h) + 1},
                          {'moved_id': moved_id, 'canvas': canvas, 'kind': 'hide'})]

    if prev.width <= 0 or prev.height <= 0 or a.width <= 0 or a.height <= 0:
        raise ValueError('Choose a visible content element.')
    if a.type in NON_CONTENT:
        raise ValueError('This version learns from content elements (text, buttons, logos).')

    if kind == 'resize':
        ratio = ((a.width * a.height) / (prev.width * prev.height)) ** .5
        if abs(ratio - 1) < .08:
            return []
        return [_proposal('emphasis', {'role': role, 'weight': round(ratio, 2)},
                          {'moved_id': moved_id, 'canvas': canvas, 'kind': 'resize', 'ratio': round(ratio, 3)})]

    # kind == 'move'
    if a.x < 0 or a.y < 0 or a.x + a.width > w + 1e-6 or a.y + a.height > h + 1e-6:
        raise ValueError('Keep the edited element inside the canvas.')
    if abs(a.x - prev.x) + abs(a.y - prev.y) < 1:
        return []
    if counts[role] != 1:
        raise ValueError('The moved semantic role must be unique within this design.')
    ev = {'moved_id': moved_id, 'from_y': prev.y, 'to_y': a.y, 'from_x': prev.x, 'to_x': a.x, 'canvas': canvas, 'kind': 'move'}
    out = []
    corner, was_corner = _corner(a, w, h), _corner(prev, w, h)
    if corner and corner != was_corner and (a.pinned != corner):
        out.append(_proposal('pin', {'role': role, 'corner': corner}, ev))

    orders = []
    for b in after.elements:
        if b.id == a.id or b.type in NON_CONTENT or b.width <= 0 or b.height <= 0 or counts[b.genome.role] != 1:
            continue
        overlap = max(0, min(a.x + a.width, b.x + b.width) - max(a.x, b.x))
        if overlap < .2 * min(a.width, b.width):
            continue
        now, was = relation(a, b), relation(prev, old[b.id])
        if now and now != was:
            gap = a.y - (b.y + b.height) if now == 'BELOW' else b.y - (a.y + a.height)
            p = _proposal('order', {'source_role': role, 'target_role': b.genome.role, 'relation': now},
                          {**ev, 'anchor_id': b.id})
            p['previous_relation'] = was or 'OVERLAPPING'
            p['gap'] = round(gap, 2)
            orders.append(p)
    orders.sort(key=lambda r: r['gap'])
    out.extend(orders)

    al, was_al = _align(a, w), _align(prev, w)
    if al and al != was_al and not corner:
        out.append(_proposal('align', {'role': role, 'align': al}, ev))
    return out


def bind_rules(design, rules):
    """Legacy helper: bind order rules only (used by the benchmark)."""
    ctx, skipped = R.bind(design, rules)
    return ctx['order'], skipped
