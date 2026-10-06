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

    def descendants(self, node: Node) -> list[Node]:
        out = []
        for cid in node.children:
            c = self.by_id.get(cid)
            if not c: continue
            out.extend(self.descendants(c) if c.type == 'group' else [c])
        return out

    def to_json(self) -> dict:
        return {'format': FORMAT, 'name': self.name,
                'page': {'width': self.width, 'height': self.height, 'background': self.background},
                'nodes': [n.to_json() for n in sorted(self.nodes, key=lambda n: n.z)],
                **({'meta': self.meta} if self.meta else {})}


# ---------------------------------------------------------------- loading

def is_graph(data: dict) -> bool:
    return isinstance(data, dict) and ('nodes' in data or data.get('format') == FORMAT)


def from_graph_json(data: dict) -> Graph:
    page = data.get('page') or {}
    w, h = float(page.get('width', 0)), float(page.get('height', 0))
    if w <= 0 or h <= 0:
        raise ValueError('page.width and page.height must be positive')
    raw = data.get('nodes') or []
    if not raw:
        raise ValueError('A design needs at least one node')
    nodes: list[Node] = []
    seen = set()
    for i, d in enumerate(raw):
        nid = str(d.get('id') or f'n{i}')
        if nid in seen:
            raise ValueError(f'Duplicate node id: {nid}')
        seen.add(nid)
        t = d.get('type')
        if t not in (*LEAF_TYPES, 'group'):
            raise ValueError(f'Node {nid}: unknown type {t!r}')
        box = Box.of(d['box']) if d.get('box') is not None else Box(0, 0, 0, 0)
        subj = Box.of(d['subject']) if d.get('subject') else None
        nodes.append(Node(id=nid, type=t, box=box, z=int(d.get('z', i)), role=d.get('role'),
                          text=d.get('text'), style=dict(d.get('style') or {}), src=d.get('src'),
                          subject=subj, shape=d.get('shape') or ('rect' if t == 'shape' else None),
                          children=[str(c) for c in d.get('children') or []], meta=dict(d.get('meta') or {})))
    g = Graph(w, h, nodes, background=page.get('background', '#ffffff'), name=data.get('name', ''),
              meta=dict(data.get('meta') or {}))
    _link_groups(g)
    return g


def _link_groups(g: Graph):
    for n in g.groups():
        missing = [c for c in n.children if c not in g.by_id]
        if missing:
            raise ValueError(f'Group {n.id} refers to unknown nodes: {", ".join(missing)}')
        for c in n.children:
            g.by_id[c].parent = n.id
    for n in g.groups():   # group boxes always follow their content
        kids = g.descendants(n)
        if kids:
            n.box = Box.bound(k.box for k in kids)
            n.z = min(k.z for k in kids)


def from_legacy(design: dict) -> Graph:
    """Convert the studio's ad JSON into a graph. Buttons become a group of shape + label."""
    canvas = design['canvas']
    brand = design.get('brand') or {}
    nodes: list[Node] = []
    z = 0
    for e in design['elements']:
        role = (e.get('genome') or {}).get('role')
        box = Box(float(e['x']), float(e['y']), float(e['width']), float(e['height']))
        t = e['type']
        font = brand.get('font', 'Inter')
        if t == 'button':
            nodes.append(Node(f"{e['id']}__bg", 'shape', box, z, shape='rect',
                              style={'fill': brand.get('primary', '#222222'), 'radius': min(box.h / 2, 18)}))
            nodes.append(Node(f"{e['id']}__label", 'text', Box(box.x + box.w * .1, box.y + box.h * .2, box.w * .8, box.h * .6),
                              z + 1, text=e.get('text') or 'Button',
                              style={'fontSize': round(box.h * .36, 1), 'fontWeight': 700, 'fontFamily': font,
                                     'color': '#ffffff', 'align': 'center'}))
            nodes.append(Node(e['id'], 'group', box, z, role=role or 'cta',
                              children=[f"{e['id']}__bg", f"{e['id']}__label"]))
            z += 2
            continue
        if t == 'text' or (t == 'logo' and e.get('text') and not e.get('src')):
            nodes.append(Node(e['id'], 'text', box, z, role=role or ('logo' if t == 'logo' else None),
                              text=e.get('text') or '',
                              style={'fontSize': e.get('fontSize') or round(box.h * .6, 1),
                                     'fontWeight': 800 if role in ('headline', 'logo') else 500,
                                     'fontFamily': font, 'color': brand.get('text', '#111111'),
                                     'align': e.get('align') or 'left'}))
        elif t in ('image', 'logo'):
            nodes.append(Node(e['id'], 'image', box, z, role=role or ('logo' if t == 'logo' else None),
                              src=e.get('src'), meta={'art': e['art']} if e.get('art') else {}))
        else:   # shape / decoration
            nodes.append(Node(e['id'], 'shape', box, z, role=role or ('decoration' if t == 'decoration' else None),
                              shape='ellipse' if t == 'decoration' else 'rect',
                              style={'fill': brand.get('accent', '#cccccc')}))
        z += 1
    g = Graph(float(canvas['width']), float(canvas['height']), nodes,
              background=brand.get('background', '#ffffff'), name=design.get('name', ''))
    _link_groups(g)
    return g


def load(data: dict | Graph) -> Graph:
    if isinstance(data, Graph):
        return data
    if hasattr(data, 'model_dump'):
        data = data.model_dump(exclude_none=True)
    if is_graph(data):
        return from_graph_json(data)
    if isinstance(data, dict) and 'elements' in data and 'canvas' in data:
        return from_legacy(data)
    raise ValueError('Unrecognised design: expected chameleon-graph/1 or the studio ad format')
