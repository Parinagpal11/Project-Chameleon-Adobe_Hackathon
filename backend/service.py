"""Application core shared by FastAPI and the lightweight local server."""
import json, os, re, sqlite3, time, uuid
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from engine.genome import enrich_design
from engine.generator import generate_candidates, ordered
from engine.repair import repair_candidate
from engine.scorer import score_candidate
from engine.intent import infer_any, relation
from engine import rules as R

ROOT = Path(__file__).resolve().parent.parent
# Starter templates: graph designs with real photos (examples/templates). The older studio samples stay in
# examples/ for importing, but new campaigns start from these.
TEMPLATE_DIR = Path(__file__).resolve().parent.parent / 'examples' / 'templates'
TEMPLATES = json.loads((TEMPLATE_DIR / 'index.json').read_text()) if (TEMPLATE_DIR / 'index.json').is_file() else {}


def campaign_key(value):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', value or ''):
        raise ValueError('Use 1–80 letters, digits, hyphens or underscores for campaign.')
    return value


SCHEMA = '''
CREATE TABLE IF NOT EXISTS rules (
  id TEXT PRIMARY KEY, campaign TEXT NOT NULL, type TEXT NOT NULL, rule_key TEXT NOT NULL,
  params TEXT NOT NULL, label TEXT NOT NULL, source TEXT NOT NULL, evidence TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1, created REAL NOT NULL, UNIQUE(campaign, rule_key));
CREATE TABLE IF NOT EXISTS projects (
  campaign TEXT PRIMARY KEY, name TEXT NOT NULL, data TEXT NOT NULL, updated REAL NOT NULL);
'''


@contextmanager
def database():
    path = Path(os.environ.get('CHAMELEON_DB', str(ROOT / 'data' / 'campaigns.sqlite3')))
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    try:
        conn.executescript(SCHEMA)
        _migrate_legacy(conn)
        with conn:
            yield conn
    finally:
        conn.close()


def _migrate_legacy(conn):
    """Copy rules from the v1 campaign_rules table (order-only) once, then leave it untouched."""
    has = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='campaign_rules'").fetchone()
    if not has:
        return
    for c, s, t, r, e in conn.execute('SELECT campaign,source_role,target_role,relation,evidence FROM campaign_rules').fetchall():
        try:
            p = R.normalize('order', {'source_role': s, 'target_role': t, 'relation': r})
        except ValueError:
            continue
        conn.execute('INSERT OR IGNORE INTO rules VALUES (?,?,?,?,?,?,?,?,1,?)',
                     (uuid.uuid4().hex[:12], c, 'order', R.key('order', p), json.dumps(p), R.label('order', p), 'edit', e or '{}', time.time()))
    conn.execute('ALTER TABLE campaign_rules RENAME TO campaign_rules_v1_migrated')
    conn.commit()


def _row(row):
    i, t, p, lab, src, ev, en, cr = row
    p = json.loads(p)
    out = {'id': i, 'type': t, 'params': p, 'label': lab, 'source': src, 'evidence': json.loads(ev),
           'enabled': bool(en), 'created': cr}
    if t == 'order':
        out.update(p)  # legacy keys
    return out


def get_rules(campaign):
    campaign_key(campaign)
    with database() as conn:
        rows = conn.execute('SELECT id,type,params,label,source,evidence,enabled,created FROM rules WHERE campaign=? ORDER BY created', (campaign,))
        return [_row(r) for r in rows]


def clear_rules(campaign):
    campaign_key(campaign)
    with database() as conn:
        conn.execute('DELETE FROM rules WHERE campaign=?', (campaign,))
    return {'status': 'cleared', 'campaign': campaign}


def _check_cycles(conn, campaign):
    rows = [json.loads(p) for (p,) in conn.execute("SELECT params FROM rules WHERE campaign=? AND type='order' AND enabled=1", (campaign,))]
    roles = {v for r in rows for v in (r['source_role'], r['target_role'])}
    ordered([SimpleNamespace(id=x) for x in roles],
            [{'source': r['source_role'], 'target': r['target_role'], 'relation': r['relation']} for r in rows])


def add_rule(campaign, rtype, params, label='', source='manual', evidence=None):
    """Insert or replace (same role / same pair) a rule. Order cycles are rejected and rolled back."""
    campaign_key(campaign)
    p = R.normalize(rtype, params)
    k = R.key(rtype, p)
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('DELETE FROM rules WHERE campaign=? AND rule_key=?', (campaign, k))
        rid = uuid.uuid4().hex[:12]
        conn.execute('INSERT INTO rules VALUES (?,?,?,?,?,?,?,?,1,?)',
                     (rid, campaign, rtype, k, json.dumps(p), label or R.label(rtype, p), source, json.dumps(evidence or {}), time.time()))
        try:
            _check_cycles(conn, campaign)
        except ValueError:
            conn.rollback()
            raise ValueError('That rule contradicts other saved order rules (it would create a loop).')
    return next(r for r in get_rules(campaign) if r['id'] == rid)


def set_enabled(campaign, rule_id, enabled):
    campaign_key(campaign)
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        n = conn.execute('UPDATE rules SET enabled=? WHERE campaign=? AND id=?', (int(enabled), campaign, rule_id)).rowcount
        if not n:
            raise ValueError('Rule not found.')
        try:
            _check_cycles(conn, campaign)
        except ValueError:
            conn.rollback()
            raise ValueError('Turning this on would contradict another order rule.')
    return next(r for r in get_rules(campaign) if r['id'] == rule_id)


def delete_rule(campaign, rule_id):
    campaign_key(campaign)
    with database() as conn:
        n = conn.execute('DELETE FROM rules WHERE campaign=? AND id=?', (campaign, rule_id)).rowcount
    if not n:
        raise ValueError('Rule not found.')
    return {'status': 'deleted', 'id': rule_id}


def learn_edit(req):
    """Legacy: confirm an order proposal from a position edit."""
    proposals = infer_any(req.before, req.after, req.moved_id, 'move')
    chosen = next((p for p in proposals if p['type'] == 'order' and all(p['params'][k] == getattr(req, k) for k in ('source_role', 'target_role', 'relation'))), None)
    if not chosen:
        raise ValueError('The submitted edit does not demonstrate that rule. Move an element to establish a new relationship.')
    add_rule(req.campaign, 'order', chosen['params'], chosen['label'], 'edit', chosen['evidence'])
    return {'learned': chosen, 'all_rules': get_rules(req.campaign)}


def learn_proposal(req):
    """Confirm any proposal. The server re-infers from the edit, so a client cannot save an undemonstrated rule."""
    proposals = infer_any(req.before, req.after, req.moved_id, req.kind)
    want = R.normalize(req.rule_type, req.params)
    chosen = next((p for p in proposals if p['type'] == req.rule_type and p['params'] == want), None)
    if not chosen:
        raise ValueError('The submitted edit does not demonstrate that rule.')
    rule = add_rule(req.campaign, chosen['type'], chosen['params'], chosen['label'], 'edit', chosen['evidence'])
    return {'learned': rule, 'all_rules': get_rules(req.campaign)}


def naive_resize(design, target):
    d = design.model_copy(deep=True)
    sx, sy = target.width / d.canvas.width, target.height / d.canvas.height
    d.canvas = type(d.canvas)(width=target.width, height=target.height)
    for e in d.elements:
        e.x *= sx; e.width *= sx; e.y *= sy; e.height *= sy
        if e.fontSize:
            e.fontSize *= min(sx, sy)
    return d


def evaluate(design, source, bound, ctx=None):
    """Score a layout. `bound` = order bindings (legacy); `ctx` = full rule context when available."""
    c = score_candidate({'strategy': 'evaluation', 'design': design})
    els = {e.id: e for e in design.elements}
    visible = {i: e for i, e in els.items() if e.width > 0 and e.height > 0}
    required = [e for e in source.elements if not e.genome.removable]
    hidden_by_rule = {i for i, e in els.items() if getattr(e, 'hidden', False)}
    missing = [e.id for e in required if e.id not in visible and e.id not in hidden_by_rule]
    for ident in missing:
        c['violations'].append({'type': 'MISSING_REQUIRED', 'element': ident})
    relation_results = []
    for r in bound:
        a, b = visible.get(r['source']), visible.get(r['target'])
        if r['source'] in hidden_by_rule or r['target'] in hidden_by_rule:
            relation_results.append({**r, 'satisfied': True, 'applies': False})
            continue
        passed = bool(a and b and relation(a, b) == r['relation'])
        relation_results.append({**r, 'satisfied': passed, 'applies': True})
        if not passed:
            c['violations'].append({'type': 'UNSATISFIED_RULE', 'element': r['source']})
    rule_results = R.check(design, ctx) if ctx else []
    other_fail = [r for r in rule_results if r['type'] != 'order' and not r['satisfied']]
    for r in other_fail:
        c['violations'].append({'type': 'UNSATISFIED_RULE', 'rule': r['label']})
    c['score'] = max(0, c['score'] - 25 * len(missing) - 20 * sum(not r['satisfied'] for r in relation_results) - 12 * len(other_fail))
    c['metrics'] = {'overlaps': sum(v['type'] == 'OVERLAP' for v in c['violations']),
                    'out_of_bounds': sum(v['type'] == 'OUT_OF_BOUNDS' for v in c['violations']),
                    'small_text': sum(v['type'] == 'TEXT_TOO_SMALL' for v in c['violations']),
                    'required_total': len(required), 'required_preserved': len(required) - len(missing),
                    'relationships_total': len(bound), 'relationships_preserved': sum(r['satisfied'] for r in relation_results)}
    c['relationship_results'] = relation_results
    c['rule_results'] = rule_results
    return c


def compile_design(design, target, rules):
    source = enrich_design(design.model_copy(deep=True))
    ctx, skipped = R.bind(source, rules)
    bound = ctx['order']
    candidates = []
    for raw in generate_candidates(source, target.width, target.height, ctx):
        repaired = repair_candidate(raw)
        c = evaluate(repaired['design'], source, bound, ctx)
        c['strategy'] = raw['strategy']
        c['explanations'] = []
        for r in c['rule_results']:
            c['explanations'].append({'element': ', '.join(next((x['ids'] for x in ctx['rules'] if x.get('id') == r['id'] and x['type'] == r['type']), [])),
                                      'reason': f"Campaign rule: {r['label']}" + ('' if r['applies'] else ' (not needed at this size)'),
                                      'applied': r['satisfied']})
        for e in c['design'].elements:
            if (e.width == 0 or e.height == 0) and not e.hidden:
                c['explanations'].append({'element': e.id, 'reason': 'Optional decoration suppressed to reserve space for required content.', 'applied': True})
        candidates.append(c)
    candidates.sort(key=lambda c: c['score'], reverse=True)
    baseline = evaluate(naive_resize(source, target), source, bound, ctx)
    baseline['strategy'] = 'naive_resize'
    return source, candidates, baseline, skipped


def serialize(c):
    return {**c, 'design': c['design'].model_dump()}


def transform(req):
    memory = get_rules(req.campaign) if req.use_memory else []
    source, cs, baseline, skipped = compile_design(req.design, req.target, memory)
    return {'campaign': req.campaign, 'design_genome': [{'id': e.id, **e.genome.model_dump()} for e in source.elements],
            'candidates': [serialize(c) for c in cs], 'best': serialize(cs[0]), 'baseline': serialize(baseline),
            'learned_rules': memory, 'skipped_rules': skipped}


def transform_batch(req):
    """Every requested format in one call: the best candidate per format plus all candidates."""
    memory = get_rules(req.campaign) if req.use_memory else []
    out = []
    for t in req.targets:
        source, cs, baseline, skipped = compile_design(req.design, t, memory)
        out.append({'target': t.model_dump(), 'candidates': [serialize(c) for c in cs],
                    'baseline': serialize(baseline), 'skipped_rules': skipped})
    return {'campaign': req.campaign, 'rules': memory, 'formats': out,
            'roles': sorted({e.genome.role for e in enrich_design(req.design.model_copy(deep=True)).elements})}


# ------------------------------------------------------------------ projects

def list_projects():
    with database() as conn:
        rows = conn.execute('SELECT p.campaign,p.name,p.updated,(SELECT COUNT(*) FROM rules r WHERE r.campaign=p.campaign) FROM projects p ORDER BY updated DESC').fetchall()
    return [{'campaign': c, 'name': n, 'updated': u, 'rules': k} for c, n, u, k in rows]


def get_project(campaign):
    campaign_key(campaign)
    with database() as conn:
        row = conn.execute('SELECT name,data,updated FROM projects WHERE campaign=?', (campaign,)).fetchone()
    if not row:
        raise LookupError('Project not found.')
    return {'campaign': campaign, 'name': row[0], **json.loads(row[1]), 'updated': row[2]}


def _valid_design(design):
    """A project's design: the graph format (checked by loading it) or the older studio format."""
    from engine.graph import load
    if isinstance(design, dict) and 'nodes' in design:
        nodes = design.get('nodes')
        if isinstance(nodes, list) and len(nodes) > MAX_NODES:
            raise ValueError(f'Designs are limited to {MAX_NODES} nodes')
        load(design)
        return design
    from models import Design
    return Design.model_validate(design).model_dump()


def save_project(campaign, req):
    campaign_key(campaign)
    data = {'design': _valid_design(req.design), 'formats': [f.model_dump() for f in req.formats],
            'assets': req.assets, 'state': req.state}
    with database() as conn:
        conn.execute('INSERT OR REPLACE INTO projects VALUES (?,?,?,?)', (campaign, req.name or campaign, json.dumps(data), time.time()))
    return {'status': 'saved', 'campaign': campaign}


def delete_project(campaign):
    campaign_key(campaign)
    with database() as conn:
        conn.execute('DELETE FROM projects WHERE campaign=?', (campaign,))
        conn.execute('DELETE FROM rules WHERE campaign=?', (campaign,))
    return {'status': 'deleted', 'campaign': campaign}


# ---------------------------------------------------------------- Understand stage (engine v2)

TESTSET = ROOT / 'examples' / 'testset'
MAX_NODES = 300


def testset_index():
    f = TESTSET / 'index.json'
    return json.loads(f.read_text()) if f.is_file() else []


def testset_design(design_id):
    if not re.fullmatch(r'[a-z0-9-]{1,60}', design_id or '') or design_id == 'index':
        raise LookupError('Unknown test design')
    f = TESTSET / f'{design_id}.json'
    if not f.is_file():
        raise LookupError('Unknown test design')
    return json.loads(f.read_text())


_EVAL_CACHE = {}
METHODS = ('chameleon', 'stretch', 'crop', 'letterbox')
DIMS = ('overall', 'content', 'legibility', 'faithfulness', 'composition', 'subject')


def eval_report():
    """Every test-set design at the 8 evaluation sizes, scored for Chameleon and the three naive resizes.

    Cached until a test-set file or the engine changes."""
    from engine.adapt import adapt
    from engine.plan import EVAL_SIZES
    engine = ROOT / 'backend' / 'engine'
    stamp = tuple(sorted((f.name, f.stat().st_mtime) for f in list(TESTSET.glob('*.json')) + list(engine.glob('*.py'))))
    if _EVAL_CACHE.get('stamp') == stamp:
        return _EVAL_CACHE['report']
    designs, rows = [], []
    for meta in testset_index():
        d = testset_design(meta['id'])
        res = adapt(d, EVAL_SIZES)
        out = []
        for r in res['results']:
            entry = {'name': r['name'], 'width': r['width'], 'height': r['height'], 'tier': r['tier'],
                     'chameleon': r['score'], 'checks_ok': r['checks']['ok']}
            for m in METHODS[1:]:
                entry[m] = r['baselines'][m]['score']
            out.append(entry)
            rows.append(entry)
        designs.append({'id': meta['id'], 'name': meta.get('name', meta['id']), 'level': meta.get('level'),
                        'width': d['page']['width'], 'height': d['page']['height'], 'results': out})

    def avg(m, dim):
        vals = [r[m][dim] for r in rows if r[m].get(dim) is not None]
        return round(sum(vals) / len(vals), 1) if vals else None
    summary = {m: {dim: avg(m, dim) for dim in DIMS} for m in METHODS}
    wins = ties = losses = 0
    for r in rows:
        best = max(r[m]['overall'] for m in METHODS[1:])
        c = r['chameleon']['overall']
        wins += c > best + .05
        ties += abs(c - best) <= .05
        losses += c < best - .05
    report = {'cases': len(rows), 'sizes': EVAL_SIZES, 'summary': summary,
              'wins': wins, 'ties': ties, 'losses': losses,
              'checks_ok': sum(r['checks_ok'] for r in rows), 'designs': designs}
    _EVAL_CACHE.update(stamp=stamp, report=report)
    return report


def _clean_targets(targets):
    from engine.plan import EVAL_SIZES
    if targets is None:
        return EVAL_SIZES
    if not isinstance(targets, list) or not targets or len(targets) > 30:
        raise ValueError('targets must be a list of 1 to 30 sizes')
    clean = []
    for i, t in enumerate(targets):
        if not isinstance(t, dict):
            raise ValueError(f'targets[{i}] must be an object like {{"width": 1080, "height": 1350}}')
        try:
            w, h = float(t.get('width')), float(t.get('height'))
        except (TypeError, ValueError):
            raise ValueError(f'targets[{i}] needs numeric width and height') from None
        if not (16 <= w <= 8192 and 16 <= h <= 8192):
            raise ValueError('Each target needs width and height between 16 and 8192')
        clean.append({'name': str(t.get('name') or '')[:60], 'width': int(round(w)), 'height': int(round(h))})
    return clean


def adapt_request(data):
    from engine.adapt import adapt
    if not isinstance(data, dict) or not isinstance(data.get('design'), dict):
        raise ValueError('Send {"design": {...}, "targets": [...]} (targets optional)')
    design = data['design']
    items = design.get('nodes') if 'nodes' in design else design.get('elements')
    if isinstance(items, list) and len(items) > MAX_NODES:
        raise ValueError(f'Designs are limited to {MAX_NODES} nodes')
    targets = _clean_targets(data.get('targets'))
    try:
        return adapt(design, targets)
    except (KeyError, TypeError) as exc:
        raise ValueError(f'Malformed design: missing or wrong field {exc}')


def convert_request(data):
    """An older studio design (canvas + elements) as a chameleon-graph/1 design; a graph is returned as is."""
    from engine.graph import load
    if not isinstance(data, dict) or not isinstance(data.get('design'), dict):
        raise ValueError('Send {"design": {...}}')
    design = data['design']
    items = design.get('nodes') if 'nodes' in design else design.get('elements')
    if isinstance(items, list) and len(items) > MAX_NODES:
        raise ValueError(f'Designs are limited to {MAX_NODES} nodes')
    try:
        return {'design': load(design).to_json()}
    except (KeyError, TypeError) as exc:
        raise ValueError(f'Malformed design: missing or wrong field {exc}')


def analyze_request(data):
    from engine.understand import analyze
    from engine.plan import EVAL_SIZES
    if not isinstance(data, dict) or not isinstance(data.get('design'), dict):
        raise ValueError('Send {"design": {...}, "targets": [...]} (targets optional)')
    design = data['design']
    items = design.get('nodes') if 'nodes' in design else design.get('elements')
    if isinstance(items, list) and len(items) > MAX_NODES:
        raise ValueError(f'Designs are limited to {MAX_NODES} nodes')
    targets = data.get('targets')
    if targets is None:
        targets = EVAL_SIZES
    if not isinstance(targets, list) or not targets or len(targets) > 30:
        raise ValueError('targets must be a list of 1 to 30 sizes')
    clean = []
    for i, t in enumerate(targets):
        if not isinstance(t, dict):
            raise ValueError(f'targets[{i}] must be an object like {{"width": 1080, "height": 1350}}')
        try:
            w, h = float(t.get('width')), float(t.get('height'))
        except (TypeError, ValueError):
            raise ValueError(f'targets[{i}] needs numeric width and height') from None
        if not (16 <= w <= 8192 and 16 <= h <= 8192):
            raise ValueError('Each target needs width and height between 16 and 8192')
        clean.append({'name': str(t.get('name') or '')[:60], 'width': int(round(w)), 'height': int(round(h))})
    try:
        return analyze(design, clean)
    except (KeyError, TypeError) as exc:
        raise ValueError(f'Malformed design: missing or wrong field {exc}')
