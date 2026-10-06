"""Design graph: the engine's internal picture of a design.

A design is a page plus a flat list of nodes. Leaf nodes are text, image or shape;
group nodes list their children by id. Paint order is the list order (later = on top)
unless a node sets `z`. Boxes are [x, y, w, h] in page pixels.

Two input formats are accepted:
  * Chameleon graph JSON  ({"format": "chameleon-graph/1", "page": ..., "nodes": [...]})
  * the older Chameleon ad JSON ({"canvas": ..., "elements": [...]}) used by the studio

Everything downstream (understand, plan, solve, score) works on `Graph`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

FORMAT = 'chameleon-graph/1'
LEAF_TYPES = ('text', 'image', 'shape')


@dataclass
class Box:
    x: float
    y: float
    w: float
    h: float

    @property
    def r(self): return self.x + self.w

    @property
    def b(self): return self.y + self.h

    @property
    def cx(self): return self.x + self.w / 2

    @property
    def cy(self): return self.y + self.h / 2

    @property
    def area(self): return max(0.0, self.w) * max(0.0, self.h)

    def inter(self, o: 'Box') -> float:
        w = min(self.r, o.r) - max(self.x, o.x)
        h = min(self.b, o.b) - max(self.y, o.y)
        return w * h if w > 0 and h > 0 else 0.0

    def contains(self, o: 'Box', slack: float = 0.0) -> bool:
        return (o.x >= self.x - slack and o.y >= self.y - slack
                and o.r <= self.r + slack and o.b <= self.b + slack)

    def union(self, o: 'Box') -> 'Box':
        x, y = min(self.x, o.x), min(self.y, o.y)
        return Box(x, y, max(self.r, o.r) - x, max(self.b, o.b) - y)

    def list(self): return [round(self.x, 2), round(self.y, 2), round(self.w, 2), round(self.h, 2)]

    @staticmethod
    def of(seq) -> 'Box':
        x, y, w, h = (float(v) for v in seq)
        return Box(x, y, w, h)

    @staticmethod
    def bound(boxes) -> 'Box':
        boxes = list(boxes)
        out = boxes[0]
        for b in boxes[1:]:
            out = out.union(b)
        return out


@dataclass
class Node:
    id: str
    type: str                     # text | image | shape | group
    box: Box
    z: int = 0
    role: str | None = None       # given by the author; inferred roles live in the analysis
    text: str | None = None
    style: dict[str, Any] = field(default_factory=dict)
    src: str | None = None
    subject: Box | None = None    # region of interest inside an image, in image-relative 0..1 units
    shape: str | None = None      # rect | ellipse | line
    children: list[str] = field(default_factory=list)
    parent: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def font_size(self) -> float:
        return float(self.style.get('fontSize') or max(10.0, self.box.h * .7))

    @property
    def font_weight(self) -> int:
        return int(self.style.get('fontWeight') or 400)

    def to_json(self) -> dict:
        out = {'id': self.id, 'type': self.type, 'box': self.box.list(), 'z': self.z}
        for k in ('role', 'text', 'src', 'shape'):
            v = getattr(self, k)
            if v is not None:
                out[k] = v
        if self.style: out['style'] = self.style
        if self.subject: out['subject'] = self.subject.list()
        if self.children: out['children'] = self.children
        if self.meta: out['meta'] = self.meta
        return out


@dataclass
class Graph:
    width: float
    height: float
    nodes: list[Node]
    background: str = '#ffffff'
    name: str = ''
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.by_id = {n.id: n for n in self.nodes}

    @property
    def page(self) -> Box: return Box(0, 0, self.width, self.height)

    def leaves(self) -> list[Node]:
        return sorted((n for n in self.nodes if n.type in LEAF_TYPES), key=lambda n: n.z)

    def groups(self) -> list[Node]:
        return [n for n in self.nodes if n.type == 'group']

    def descendants(self, node: Node, _seen=None) -> list[Node]:
        seen = _seen if _seen is not None else {node.id}
        out = []
        for cid in node.children:
            c = self.by_id.get(cid)
            if not c or cid in seen: continue
            seen.add(cid)
            out.extend(self.descendants(c, seen) if c.type == 'group' else [c])
        return out

    def to_json(self) -> dict:
        return {'format': FORMAT, 'name': self.name,
                'page': {'width': self.width, 'height': self.height, 'background': self.background},
                'nodes': [n.to_json() for n in sorted(self.nodes, key=lambda n: n.z)],
                **({'meta': self.meta} if self.meta else {})}


# ---------------------------------------------------------------- loading

def is_graph(data: dict) -> bool:
    return isinstance(data, dict) and ('nodes' in data or data.get('format') == FORMAT)


WEIGHTS = {'thin': 100, 'extralight': 200, 'light': 300, 'normal': 400, 'regular': 400, 'medium': 500,
           'semibold': 600, 'bold': 700, 'extrabold': 800, 'black': 900, 'heavy': 900}


def _num(v, what: str) -> float:
    """A finite number, accepting numeric strings like "40" or "40px"."""
    if isinstance(v, bool):
        raise ValueError(f'{what} must be a number')
    if isinstance(v, str):
        s = v.strip().lower().removesuffix('px').strip()
        try:
            v = float(s)
        except ValueError:
            raise ValueError(f'{what} must be a number, got {v!r}') from None
    if not isinstance(v, (int, float)) or not math.isfinite(v):
        raise ValueError(f'{what} must be a finite number')
    return float(v)


def _box(v, what: str) -> Box:
    if not isinstance(v, (list, tuple)) or len(v) != 4:
        raise ValueError(f'{what} must be [x, y, width, height]')
    x, y, w, h = (_num(c, what) for c in v)
    if max(abs(x), abs(y), w, h) > 1e6:
        raise ValueError(f'{what}: values must be within ±1,000,000 px')
    if w < 0 or h < 0:
        raise ValueError(f'{what}: width and height cannot be negative')
    return Box(x, y, w, h)


def _style(raw, nid: str) -> dict:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f'Node {nid}: style must be an object')
    s = dict(raw)
    if 'fontWeight' in s and s['fontWeight'] is not None:
        fw = s['fontWeight']
        if isinstance(fw, str) and fw.strip().lower().replace('-', '').replace(' ', '') in WEIGHTS:
            s['fontWeight'] = WEIGHTS[fw.strip().lower().replace('-', '').replace(' ', '')]
        else:
            s['fontWeight'] = int(max(1, min(1000, _num(fw, f'Node {nid}: fontWeight'))))
    for k in ('fontSize', 'lineHeight', 'letterSpacing', 'radius', 'opacity', 'strokeWidth'):
        if k in s and s[k] is not None:
            s[k] = _num(s[k], f'Node {nid}: {k}')
    if s.get('fontSize') is not None and s['fontSize'] <= 0:
        raise ValueError(f'Node {nid}: fontSize must be positive')
    if s.get('align') not in (None, 'left', 'center', 'right'):
        s['align'] = {'centre': 'center', 'middle': 'center', 'start': 'left', 'end': 'right'}.get(str(s['align']).lower(), 'left')
    return s


def from_graph_json(data: dict) -> Graph:
    page = data.get('page')
    if not isinstance(page, dict):
        raise ValueError('page must be an object with width and height')
    w, h = _num(page.get('width'), 'page.width'), _num(page.get('height'), 'page.height')
    if w <= 0 or h <= 0:
        raise ValueError('page.width and page.height must be positive')
    raw = data.get('nodes')
    if not isinstance(raw, list):
        raise ValueError('nodes must be a list')
    if not raw:
        raise ValueError('A design needs at least one node')
    nodes: list[Node] = []
    seen = set()
    for i, d in enumerate(raw):
        if not isinstance(d, dict):
            raise ValueError(f'nodes[{i}] must be an object')
        nid = str(d.get('id') or f'n{i}')
        if nid in seen:
            raise ValueError(f'Duplicate node id: {nid}')
        seen.add(nid)
        t = d.get('type')
        if t not in (*LEAF_TYPES, 'group'):
            raise ValueError(f'Node {nid}: unknown type {t!r} (use text, image, shape or group)')
        if t != 'group' and d.get('box') is None:
            raise ValueError(f'Node {nid}: needs a box [x, y, width, height]')
        box = _box(d['box'], f'Node {nid}: box') if d.get('box') is not None else Box(0, 0, 0, 0)
        subj = None
        if d.get('subject') is not None:
            subj = _box(d['subject'], f'Node {nid}: subject')
            subj = Box(max(0, min(1, subj.x)), max(0, min(1, subj.y)), max(0, min(1, subj.w)), max(0, min(1, subj.h)))
        kids = d.get('children') or []
        if not isinstance(kids, list):
            raise ValueError(f'Node {nid}: children must be a list of ids')
        text = d.get('text')
        src = d.get('src')
        if src is not None and not isinstance(src, str):
            raise ValueError(f'Node {nid}: src must be a string')
        nodes.append(Node(id=nid, type=t, box=box, z=int(_num(d.get('z', i), f'Node {nid}: z')), role=d.get('role') if isinstance(d.get('role'), str) else None,
                          text=None if text is None else str(text), style=_style(d.get('style'), nid), src=src,
                          subject=subj, shape=d.get('shape') or ('rect' if t == 'shape' else None),
                          children=[str(c) for c in kids], meta=dict(d.get('meta') or {}) if isinstance(d.get('meta'), dict) else {}))
    bg = page.get('background', '#ffffff')
    g = Graph(w, h, nodes, background=bg if isinstance(bg, str) else '#ffffff', name=str(data.get('name') or ''),
              meta=dict(data.get('meta') or {}) if isinstance(data.get('meta'), dict) else {})
    _link_groups(g)
    return g


def _link_groups(g: Graph):
    for n in g.groups():
        missing = [c for c in n.children if c not in g.by_id]
        if missing:
            raise ValueError(f'Group {n.id} refers to unknown nodes: {", ".join(missing)}')
        for c in n.children:
            if c == n.id:
                raise ValueError(f'Group {n.id} cannot contain itself')
            if g.by_id[c].parent and g.by_id[c].parent != n.id:
                raise ValueError(f'Node {c} is in two groups ({g.by_id[c].parent} and {n.id})')
            g.by_id[c].parent = n.id
    for n in g.groups():   # cycles: walking up the parents must end
        seen, cur = set(), n
        while cur.parent:
            if cur.id in seen:
                raise ValueError(f'Groups form a loop around {n.id}')
            seen.add(cur.id)
            cur = g.by_id[cur.parent]
    for n in g.groups():   # group boxes always follow their content
        kids = g.descendants(n)
        if kids:
            n.box = Box.bound(k.box for k in kids)
            n.z = min(k.z for k in kids)


def from_legacy(design: dict) -> Graph:
    """Convert the studio's ad JSON into a graph. Buttons become a group of shape + label."""
    canvas = design.get('canvas')
    if not isinstance(canvas, dict):
        raise ValueError('canvas must be an object with width and height')
    cw, ch = _num(canvas.get('width'), 'canvas.width'), _num(canvas.get('height'), 'canvas.height')
    if cw <= 0 or ch <= 0:
        raise ValueError('canvas.width and canvas.height must be positive')
    elements = design.get('elements')
    if not isinstance(elements, list) or not elements:
        raise ValueError('elements must be a non-empty list')
    brand = design.get('brand') if isinstance(design.get('brand'), dict) else {}
    nodes: list[Node] = []
    z = 0
    for i, e in enumerate(elements):
        if not isinstance(e, dict) or 'id' not in e:
            raise ValueError(f'elements[{i}] must be an object with an id')
        eid = str(e['id'])
        role = (e.get('genome') or {}).get('role') if isinstance(e.get('genome'), dict) else None
        box = _box([e.get('x'), e.get('y'), e.get('width'), e.get('height')], f'Element {eid}')
        t = e.get('type')
        font = brand.get('font', 'Inter')
        if t == 'button':
            nodes.append(Node(f"{eid}__bg", 'shape', box, z, shape='rect',
                              style={'fill': brand.get('primary', '#222222'), 'radius': min(box.h / 2, 18)}))
            nodes.append(Node(f"{eid}__label", 'text', Box(box.x + box.w * .1, box.y + box.h * .2, box.w * .8, box.h * .6),
                              z + 1, text=str(e.get('text') or 'Button'),
                              style={'fontSize': round(box.h * .36, 1) or 1, 'fontWeight': 700, 'fontFamily': font,
                                     'color': '#ffffff', 'align': 'center'}))
            nodes.append(Node(eid, 'group', box, z, role=role or 'cta', children=[f"{eid}__bg", f"{eid}__label"]))
            z += 2
            continue
        if t == 'text' or (t == 'logo' and e.get('text') and not e.get('src')):
            fs = e.get('fontSize')
            nodes.append(Node(eid, 'text', box, z, role=role or ('logo' if t == 'logo' else None),
                              text=str(e.get('text') or ''),
                              style={'fontSize': _num(fs, f'Element {eid}: fontSize') if fs else round(box.h * .6, 1) or 1,
                                     'fontWeight': 800 if role in ('headline', 'logo') else 500,
                                     'fontFamily': font, 'color': brand.get('text', '#111111'),
                                     'align': e.get('align') or 'left'}))
        elif t in ('image', 'logo'):
            nodes.append(Node(eid, 'image', box, z, role=role or ('logo' if t == 'logo' else None),
                              src=e.get('src') if isinstance(e.get('src'), str) else None,
                              meta={'art': e['art']} if e.get('art') else {}))
        elif t in ('shape', 'decoration'):
            nodes.append(Node(eid, 'shape', box, z, role=role or ('decoration' if t == 'decoration' else None),
                              shape='ellipse' if t == 'decoration' else 'rect',
                              style={'fill': brand.get('accent', '#cccccc')}))
        else:
            raise ValueError(f'Element {eid}: unknown type {t!r}')
        z += 1
    ids = [n.id for n in nodes]
    dup = next((x for x in ids if ids.count(x) > 1), None)
    if dup:
        raise ValueError(f'Duplicate element id: {dup}')
    g = Graph(cw, ch, nodes, background=brand.get('background', '#ffffff'), name=str(design.get('name') or ''))
    _link_groups(g)
    return g


def load(data: dict | Graph) -> Graph:
    if isinstance(data, Graph):
        return data
    if hasattr(data, 'model_dump'):
        data = data.model_dump(exclude_none=True)
    if is_graph(data):
        return from_graph_json(data)
    if isinstance(data, dict) and ('elements' in data or 'canvas' in data):
        return from_legacy(data)
    raise ValueError('Unrecognised design: expected chameleon-graph/1 or the studio ad format')
