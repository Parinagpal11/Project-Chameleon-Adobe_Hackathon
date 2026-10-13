"""Application core shared by FastAPI and the lightweight local server."""
import copy, hashlib, json, os, re, sqlite3, threading, time
from collections import OrderedDict
from typing import Any
from contextlib import contextmanager
from pathlib import Path

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
        if 'owner' not in {r[1] for r in conn.execute('PRAGMA table_info(projects)')}:
            conn.execute("ALTER TABLE projects ADD COLUMN owner TEXT NOT NULL DEFAULT ''")
        with conn:
            yield conn
    finally:
        conn.close()


# ------------------------------------------------------------------ projects
# On a shared (hosted) server every browser sends its own random owner id, so each visitor's home page lists
# only their own campaigns. A campaign link still opens for anyone who has it. Campaigns saved before owners
# existed (owner '') show for everyone, which keeps a local install's older campaigns visible.

def owner_key(value):
    value = value or ''
    return value if re.fullmatch(r'[a-zA-Z0-9-]{8,64}', value) else ''


def list_projects(owner=''):
    with database() as conn:
        rows = conn.execute("SELECT campaign,name,updated FROM projects WHERE owner IN (?, '') ORDER BY updated DESC", (owner_key(owner),)).fetchall()
    return [{'campaign': c, 'name': n, 'updated': u} for c, n, u in rows]


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


def save_project(campaign, req, owner=''):
    campaign_key(campaign)
    data = {'design': _valid_design(req.design), 'formats': [f.model_dump() for f in req.formats],
            'assets': req.assets, 'state': req.state}
    with database() as conn:
        row = conn.execute('SELECT owner FROM projects WHERE campaign=?', (campaign,)).fetchone()
        keep = row[0] if row else owner_key(owner)       # a campaign keeps the owner that created it
        conn.execute('INSERT OR REPLACE INTO projects (campaign,name,data,updated,owner) VALUES (?,?,?,?,?)',
                     (campaign, req.name or campaign, json.dumps(data), time.time(), keep))
    return {'status': 'saved', 'campaign': campaign}


def delete_project(campaign, owner=''):
    campaign_key(campaign)
    with database() as conn:
        n = conn.execute("DELETE FROM projects WHERE campaign=? AND owner IN (?, '')", (campaign, owner_key(owner))).rowcount
    if not n:
        raise LookupError('Project not found.')
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
EVAL_FILE = ROOT / 'examples' / 'eval-report.json'


def _eval_stamp():
    """A fingerprint of everything the report depends on: the test-set files and the engine's code and models."""
    h = hashlib.sha1()
    engine = ROOT / 'backend' / 'engine'
    for f in sorted(list(TESTSET.glob('*.json')) + list(engine.glob('*.py')) + list(engine.glob('*.json'))):
        h.update(f.name.encode())
        h.update(f.read_bytes())
    return h.hexdigest()


METHODS = ('chameleon', 'stretch', 'crop', 'letterbox')
DIMS = ('overall', 'content', 'legibility', 'faithfulness', 'composition', 'subject')


def eval_report():
    """Every test-set design at the 8 evaluation sizes, scored for Chameleon and the three naive resizes.

    Cached until a test-set file or the engine changes."""
    from engine.adapt import adapt
    from engine.plan import EVAL_SIZES
    stamp = _eval_stamp()
    if _EVAL_CACHE.get('stamp') == stamp:
        return _EVAL_CACHE['report']
    try:       # saved by tools/make_eval_report.py: a fresh server (or a slow host) answers at once
        saved = json.loads(EVAL_FILE.read_text())
        if saved.get('stamp') == stamp:
            _EVAL_CACHE.update(stamp=stamp, report=saved['report'])
            return saved['report']
    except (OSError, ValueError):
        pass
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
              'wins': int(wins), 'ties': int(ties), 'losses': int(losses),
              'checks_ok': int(sum(bool(r['checks_ok']) for r in rows)), 'designs': designs}
    report = json.loads(json.dumps(report, default=lambda o: o.item() if hasattr(o, 'item') else str(o)))   # plain numbers
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


# The engine is deterministic: the same design and sizes always give the same result, so recent answers are
# kept (by a hash of the request) and a repeat — reopening a campaign, the home page, How it works — is instant.
_RESULTS: 'OrderedDict[str, Any]' = OrderedDict()
_RESULTS_LOCK = threading.Lock()
_RESULTS_MAX = 48


# Answers saved ahead of time for the requests the bundled pages make (home demo, the sample campaign, the
# tour, How it works): a small host answers those at once instead of running the engine for a minute.
# Made by tools/make_caches.py; used only while the engine is unchanged.
SAVED_RESULTS_FILE = ROOT / 'examples' / 'results-cache.json'
_SAVED: dict = {}
_RECORD: dict | None = {} if os.environ.get('CHAMELEON_RECORD') else None


def engine_stamp():
    """A fingerprint of the engine's code, data and models: saved answers are only valid for the same engine."""
    h = hashlib.sha1()
    engine = ROOT / 'backend' / 'engine'
    for f in sorted(list(engine.glob('*.py')) + list(engine.glob('*.json')) + list((engine / 'models').glob('*.onnx'))):
        h.update(f.name.encode())
        h.update(f.read_bytes())
    return h.hexdigest()


def _request_key(kind, data):
    return kind + hashlib.sha1(json.dumps(data, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def load_saved_results():
    try:
        saved = json.loads(SAVED_RESULTS_FILE.read_text())
    except (OSError, ValueError):
        return 0
    if saved.get('stamp') != engine_stamp():
        return 0
    _SAVED.update(saved.get('results') or {})
    return len(_SAVED)


def _remembered(kind, data, compute):
    try:
        key = _request_key(kind, data)
    except (TypeError, ValueError):
        return compute(data)
    if key in _SAVED:
        return copy.deepcopy(_SAVED[key])
    with _RESULTS_LOCK:
        if key in _RESULTS:
            _RESULTS.move_to_end(key)
            return copy.deepcopy(_RESULTS[key])
    result = compute(data)
    result = json.loads(json.dumps(result, default=lambda o: o.item() if hasattr(o, 'item') else str(o)))   # plain numbers
    with _RESULTS_LOCK:
        _RESULTS[key] = copy.deepcopy(result)
        while len(_RESULTS) > _RESULTS_MAX:
            _RESULTS.popitem(last=False)
        if _RECORD is not None:
            _RECORD[key] = copy.deepcopy(result)
    return result


def warm_up():
    """In the background at start-up, at low priority so it never slows a visitor: load the saved answers and
    photo readings, then the photo models (the first run of a new photo would otherwise wait for them)."""
    try:
        os.nice(15)          # Linux: lowers this thread only
    except (AttributeError, OSError):
        pass
    load_saved_results()
    from engine import subject
    subject.load_saved()
    from engine.understand import analyze
    for name in TEMPLATES:
        try:
            analyze(json.loads((TEMPLATE_DIR / f'{name}.json').read_text()), _clean_targets(None)[:1])
        except Exception:
            pass
    try:
        subject._u2net(); subject._yolox()
    except Exception:
        pass


def adapt_request(data):
    return _remembered('adapt', data, _adapt_request)


def analyze_request(data):
    return _remembered('analyze', data, _analyze_request)


def _adapt_request(data):
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


def _analyze_request(data):
    from engine.understand import analyze
    if not isinstance(data, dict) or not isinstance(data.get('design'), dict):
        raise ValueError('Send {"design": {...}, "targets": [...]} (targets optional)')
    design = data['design']
    items = design.get('nodes') if 'nodes' in design else design.get('elements')
    if isinstance(items, list) and len(items) > MAX_NODES:
        raise ValueError(f'Designs are limited to {MAX_NODES} nodes')
    clean = _clean_targets(data.get('targets'))
    try:
        return analyze(design, clean)
    except (KeyError, TypeError) as exc:
        raise ValueError(f'Malformed design: missing or wrong field {exc}')
