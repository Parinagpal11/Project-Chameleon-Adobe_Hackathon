"""Campaign rule vocabulary: validation, labels, binding to a design and checking a layout.

Rule shapes (all keyed by semantic role, never element ID):
  order      {source_role, target_role, relation: ABOVE|BELOW}
  pin        {role, corner: top-left|top-right|bottom-left|bottom-right}
  align      {role, align: left|center|right}          role may be '*' (all content)
  emphasis   {role, weight: 0.5..2.0}                  relative prominence in the layout
  hide_small {role, below: px}                         hide when the format's short side < below
"""
import re

CORNERS = ('top-left', 'top-right', 'bottom-left', 'bottom-right')
ALIGNS = ('left', 'center', 'right')
CONTENT_TYPES = ('text', 'button', 'logo')


def _role(value, allow_all=False):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z_*]{1,40}', value):
        raise ValueError('Rules must name a semantic role such as cta, logo or headline.')
    if value == '*' and not allow_all:
        raise ValueError('This rule needs one specific role.')
    return value


def normalize(rtype, params):
    """Validate params and return a clean copy. Raises ValueError with a readable message."""
    p = dict(params or {})
    if rtype == 'order':
        out = {'source_role': _role(p.get('source_role')), 'target_role': _role(p.get('target_role')),
               'relation': p.get('relation')}
        if out['relation'] not in ('ABOVE', 'BELOW'):
            raise ValueError('Order rules are ABOVE or BELOW.')
        if out['source_role'] == out['target_role']:
            raise ValueError('Choose two different roles.')
        return out
    if rtype == 'pin':
        if p.get('corner') not in CORNERS:
            raise ValueError('Pin to top-left, top-right, bottom-left or bottom-right.')
        return {'role': _role(p.get('role')), 'corner': p['corner']}
    if rtype == 'align':
        if p.get('align') not in ALIGNS:
            raise ValueError('Align left, center or right.')
        return {'role': _role(p.get('role'), True), 'align': p['align']}
    if rtype == 'emphasis':
        try:
            w = float(p.get('weight'))
        except (TypeError, ValueError):
            raise ValueError('Emphasis needs a numeric weight.')
        return {'role': _role(p.get('role')), 'weight': round(min(2.0, max(0.5, w)), 2)}
    if rtype == 'hide_small':
        try:
            below = int(p.get('below'))
        except (TypeError, ValueError):
            raise ValueError('Hide rules need a size in pixels.')
        if not 64 <= below <= 4000:
            raise ValueError('Use a size between 64 and 4000 px.')
        return {'role': _role(p.get('role')), 'below': below}
    raise ValueError(f'Unknown rule type: {rtype}')


def cap(s):
    return s[:1].upper() + s[1:]


def nice(role):
    return {'cta': 'CTA', '*': 'all content'}.get(role, role.replace('_', ' '))


def label(rtype, p):
    if rtype == 'order':
        return f"{nice(p['source_role'])} stays {p['relation'].lower()} {nice(p['target_role'])}"
    if rtype == 'pin':
        return f"{cap(nice(p['role']))} pinned {p['corner'].replace('-', ' ')}"
    if rtype == 'align':
        return f"{cap(nice(p['role']))} aligned {p['align']}"
    if rtype == 'emphasis':
        word = 'larger' if p['weight'] > 1 else 'smaller'
        return f"{cap(nice(p['role']))} {word} (×{p['weight']:g})"
    if rtype == 'hide_small':
        return f"Hide {nice(p['role'])} when the short side is under {p['below']}px"
    return rtype


def key(rtype, p):
    """Rules sharing a key replace each other (latest wins). Order pairs share a key in either direction."""
    if rtype == 'order':
        return 'order:' + '|'.join(sorted((p['source_role'], p['target_role'])))
    return f"{rtype}:{p['role']}"


def as_typed(rule):
    """Accept legacy order dicts {source_role,target_role,relation} as well as typed rules."""
    if 'type' in rule:
        return rule
    return {'type': 'order', 'params': {k: rule[k] for k in ('source_role', 'target_role', 'relation')},
            'enabled': True}


def bind(design, rules):
    """Resolve role-based rules to element IDs for one design.

    Returns a context dict consumed by the generator and evaluator, plus skipped rules with reasons."""
    byrole = {}
    for e in design.elements:
        byrole.setdefault(e.genome.role, []).append(e)
    ctx = {'order': [], 'pin': {}, 'align': {}, 'emphasis': {}, 'hide_small': {}, 'rules': []}
    skipped = []
    for raw in rules:
        r = as_typed(raw)
        if not r.get('enabled', True):
            continue
        t, p = r['type'], r['params']
        if t == 'order':
            s, g = byrole.get(p['source_role'], []), byrole.get(p['target_role'], [])
            if len(s) != 1 or len(g) != 1:
                skipped.append({'rule': raw, 'reason': 'Role missing or ambiguous; rule was not applied.'})
                continue
            b = {'source': s[0].id, 'target': g[0].id, 'relation': p['relation'],
                 'source_role': p['source_role'], 'target_role': p['target_role']}
            ctx['order'].append(b)
            ctx['rules'].append({**r, 'ids': [s[0].id, g[0].id]})
            continue
        if p['role'] == '*':
            targets = [e for e in design.elements if e.type in CONTENT_TYPES]
        else:
            targets = byrole.get(p['role'], [])
        if not targets:
            skipped.append({'rule': raw, 'reason': f"No {nice(p['role'])} in this design; rule was not applied."})
            continue
        for e in targets:
            ctx[t][e.id] = p['corner'] if t == 'pin' else p['align'] if t == 'align' else p['weight'] if t == 'emphasis' else p['below']
        ctx['rules'].append({**r, 'ids': [e.id for e in targets]})
    return ctx, skipped


def _relation(a, b):
    if a.y >= b.y + b.height - 1e-7:
        return 'BELOW'
    if a.y + a.height <= b.y + 1e-7:
        return 'ABOVE'
    return None


def _emphasis_ok(e, weight, design, ctx):
    """Compare the element's size with a reference text element against the expected type-scale ratio."""
    from engine.generator import SCALE
    if e.pinned:  # pinned elements scale their badge size by the weight directly
        return True
    if not e.fontSize:
        return True
    role = e.genome.role if e.genome else 'body'
    refs = [x for x in design.elements if x.id != e.id and not x.hidden and x.width > 0 and x.fontSize
            and x.type in ('text', 'button') and not x.pinned and (x.genome.role if x.genome else 'body') in SCALE]
    if not refs:
        return True
    ref = next((x for x in refs if x.genome.role == 'headline'), refs[0])
    rr = ref.genome.role
    expected = (SCALE.get(role, .4) * weight) / (SCALE.get(rr, .4) * ctx['emphasis'].get(ref.id, 1.0))
    neutral = SCALE.get(role, .4) / (SCALE.get(rr, .4) * ctx['emphasis'].get(ref.id, 1.0))
    actual = e.fontSize / ref.fontSize
    # satisfied when the size moved at least half-way from neutral towards the requested weight
    return actual >= neutral + (expected - neutral) * .5 if weight > 1 else actual <= neutral + (expected - neutral) * .5


def check(design, ctx):
    """Is every bound rule satisfied in this layout? Returns one result per rule."""
    els = {e.id: e for e in design.elements}
    w, h = design.canvas.width, design.canvas.height
    short = min(w, h)
    tol = short * 0.08
    out = []
    for r in ctx['rules']:
        t, p, ids = r['type'], r['params'], r['ids']
        applies, ok = True, True
        if t == 'order':
            a, b = els.get(ids[0]), els.get(ids[1])
            vis = a and b and a.width > 0 and b.width > 0
            ok = bool(vis and _relation(a, b) == p['relation'])
            if a and b and (a.hidden or b.hidden):
                applies, ok = False, True
        elif t == 'hide_small':
            applies = short < p['below']
            ok = all((els[i].hidden or els[i].width == 0) == applies for i in ids if i in els)
        else:
            for i in ids:
                e = els.get(i)
                if not e or e.hidden or e.width == 0:
                    continue
                if t == 'pin':
                    v, hz = p['corner'].split('-')
                    ok &= (e.y <= tol) if v == 'top' else (e.y + e.height >= h - tol)
                    ok &= (e.x <= tol) if hz == 'left' else (e.x + e.width >= w - tol)
                elif t == 'align':
                    ok &= (e.align or 'left') == p['align']
                elif t == 'emphasis':
                    ok &= _emphasis_ok(e, p['weight'], design, ctx)
        out.append({'id': r.get('id'), 'type': t, 'params': p, 'label': r.get('label') or label(t, p),
                    'applies': applies, 'satisfied': bool(ok)})
    return out


# ---------------------------------------------------------------- plain-English rules

SYNONYMS = {
    'cta': ['call to action', 'shop now', 'cta', 'button', 'buy button'],
    'logo': ['logo', 'brand mark', 'brandmark', 'wordmark'],
    'headline': ['headline', 'heading', 'title', 'tagline'],
    'offer': ['offer', 'discount', 'price', 'deal', 'promo', 'sale'],
    'hero': ['hero', 'image', 'photo', 'product shot', 'picture', 'product'],
    'subtitle': ['subtitle', 'subheading', 'subhead'],
    'body': ['body', 'description', 'copy', 'paragraph'],
    'legal': ['legal', 'disclaimer', 'terms', 'fine print', 'small print'],
}
SMALL_WORDS = {'tiny': 200, 'leaderboard': 200, 'banner': 200, 'banners': 200, 'small': 400, 'mobile': 400,
               'phone': 400, 'narrow': 400, 'compact': 400}


def _find_roles(text, roles):
    """Return roles mentioned in text, ordered by position of first mention."""
    allowed = set(roles) if roles else set(SYNONYMS)
    hits = []
    for role, words in SYNONYMS.items():
        if role not in allowed and roles:
            continue
        for w in sorted(words, key=len, reverse=True):
            m = re.search(r'\b' + re.escape(w) + r's?\b', text)
            if m:
                hits.append((m.start(), role))
                break
    for role in roles or []:
        if role not in SYNONYMS:
            m = re.search(r'\b' + re.escape(role.replace('_', ' ')) + r'\b', text)
            if m:
                hits.append((m.start(), role))
    seen, ordered_roles = set(), []
    for _, r in sorted(hits):
        if r not in seen:
            seen.add(r)
            ordered_roles.append(r)
    return ordered_roles


def _clause(text, roles):
    t = ' ' + text.lower().strip() + ' '
    found = _find_roles(t, roles)
    corner = re.search(r'\b(top|bottom|upper|lower)[\s-]*(left|right)\b', t)
    if corner and found:
        v = 'top' if corner.group(1) in ('top', 'upper') else 'bottom'
        return {'type': 'pin', 'params': {'role': found[0], 'corner': f'{v}-{corner.group(2)}'}}
    if re.search(r'\b(hide|drop|remove|skip)\b', t) and found:
        px = re.search(r'(\d{2,4})\s*(px|pixels)?', t)
        below = int(px.group(1)) if px else next((v for k, v in SMALL_WORDS.items() if re.search(r'\b' + k + r'\b', t)), 400)
        return {'type': 'hide_small', 'params': {'role': found[0], 'below': below}}
    al = re.search(r'\b(center|centre|centered|centred|middle|left|right)\b', t)
    if al and re.search(r'\b(align|aligned|alignment|center|centre|centered|centred|justify|justified)\b', t):
        a = al.group(1)
        a = 'center' if a.startswith('cent') or a == 'middle' else a
        role = found[0] if found else ('*' if re.search(r'\b(all|everything|text|content)\b', t) else None)
        if role:
            return {'type': 'align', 'params': {'role': role, 'align': a}}
    if len(found) >= 2:
        rel = re.search(r'\b(below|under|underneath|beneath|after)\b', t)
        rel2 = re.search(r'\b(above|over|before|on top of)\b', t)
        if rel or rel2:
            first = (rel or rel2).start()
            other = rel2 if rel else rel
            if rel and rel2:
                first = min(rel.start(), rel2.start())
                relation = 'BELOW' if rel.start() == first else 'ABOVE'
            else:
                relation = 'BELOW' if rel else 'ABOVE'
            return {'type': 'order', 'params': {'source_role': found[0], 'target_role': found[1], 'relation': relation}}
    if found and re.search(r'\b(bigger|larger|more prominent|stand out|emphasi[sz]e|never shrink|prominent|bold)\b', t):
        return {'type': 'emphasis', 'params': {'role': found[0], 'weight': 1.5}}
    if found and re.search(r'\b(smaller|less prominent|subtle|de-?emphasi[sz]e|shrink)\b', t):
        return {'type': 'emphasis', 'params': {'role': found[0], 'weight': 0.7}}
    return None


def parse_text(text, roles=()):
    """Deterministic keyword parser. Splits on commas/semicolons/'and'/'.' and returns rule proposals."""
    parts = [p for p in re.split(r'[;,.\n]|\band\b|\bthen\b', text, flags=re.I) if p.strip()]
    rules, unmatched = [], []
    for part in parts:
        r = _clause(part, list(roles))
        if r:
            try:
                r['params'] = normalize(r['type'], r['params'])
            except ValueError:
                unmatched.append(part.strip())
                continue
            r['label'] = label(r['type'], r['params'])
            r['source'] = 'text'
            r['evidence'] = {'text': part.strip()}
            rules.append(r)
        else:
            unmatched.append(part.strip())
    return {'rules': rules, 'unmatched': unmatched}
