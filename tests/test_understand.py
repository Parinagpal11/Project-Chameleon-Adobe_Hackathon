"""Engine v2 — design graph, Plan tiers and the Understand stage."""
import base64
import io
import json
import sys
import threading
import time
import unittest
from pathlib import Path
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from engine.graph import load, Box            # noqa: E402
from engine.plan import plan_tier, EVAL_SIZES  # noqa: E402
from engine.understand import analyze          # noqa: E402
from engine import subject                     # noqa: E402

TESTSET = ROOT / 'examples' / 'testset'


def design(name):
    return json.loads((TESTSET / f'{name}.json').read_text())


def by_member(a, node_id):
    return next(g for g in a['groups'] if node_id in g['members'])


class GraphTests(unittest.TestCase):
    def test_loads_graph_and_links_groups(self):
        g = load(design('promo-centered'))
        self.assertEqual((g.width, g.height), (1080, 1080))
        btn = g.by_id['cta']
        self.assertEqual(btn.type, 'group')
        self.assertEqual(g.by_id['cta-bg'].parent, 'cta')
        self.assertEqual(btn.box.list(), g.by_id['cta-bg'].box.list())   # group box follows its content

    def test_loads_studio_format(self):
        g = load(json.loads((ROOT / 'examples' / 'coffee_ad.json').read_text()))
        self.assertEqual(g.by_id['cta'].type, 'group')
        self.assertEqual(g.by_id['cta__label'].text, 'SHOP NOW')
        self.assertEqual(g.by_id['hero'].role, 'hero')

    def test_rejects_bad_designs(self):
        base = {'format': 'chameleon-graph/1', 'page': {'width': 100, 'height': 100}}
        with self.assertRaises(ValueError):
            load({**base, 'nodes': [{'id': 'a', 'type': 'text', 'box': [0, 0, 1, 1]}] * 2})
        with self.assertRaises(ValueError):
            load({**base, 'nodes': [{'id': 'g', 'type': 'group', 'children': ['missing']}]})
        with self.assertRaises(ValueError):
            load({**base, 'nodes': [{'id': 'a', 'type': 'video', 'box': [0, 0, 1, 1]}]})
        with self.assertRaises(ValueError):
            load({'something': 'else'})

    def test_box_maths(self):
        a, b = Box(0, 0, 10, 10), Box(5, 5, 10, 10)
        self.assertEqual(a.inter(b), 25)
        self.assertEqual(a.union(b).list(), [0, 0, 15, 15])
        self.assertTrue(Box(0, 0, 20, 20).contains(a))


class ValidationTests(unittest.TestCase):
    BASE = {'format': 'chameleon-graph/1', 'page': {'width': 100, 'height': 100}}

    def bad(self, design, contains):
        with self.assertRaises(ValueError) as e:
            load(design)
        self.assertIn(contains, str(e.exception))

    def test_bad_inputs_give_clear_errors(self):
        b = self.BASE
        self.bad({**b, 'nodes': [{'id': 'g1', 'type': 'group', 'children': ['g2']},
                                 {'id': 'g2', 'type': 'group', 'children': ['g1']}]}, 'loop')
        self.bad({**b, 'nodes': [{'id': 'g', 'type': 'group', 'children': ['g']}]}, 'itself')
        self.bad({**b, 'nodes': [5]}, 'nodes[0]')
        self.bad({**b, 'nodes': {'a': 1}}, 'nodes must be a list')
        self.bad({'format': 'chameleon-graph/1', 'page': [1, 2], 'nodes': []}, 'page must be an object')
        self.bad({**b, 'nodes': [{'id': 'a', 'type': 'text', 'box': [0, 0, 1]}]}, '[x, y, width, height]')
        self.bad({**b, 'nodes': [{'id': 'a', 'type': 'text', 'box': [0, 0, float('nan'), 1]}]}, 'finite')
        self.bad({**b, 'nodes': [{'id': 'a', 'type': 'text'}]}, 'needs a box')
        self.bad({**b, 'nodes': [{'id': 'a', 'type': 'text', 'box': [0, 0, 1, 1], 'style': {'fontSize': 'big'}}]}, 'fontSize')
        self.bad({**b, 'nodes': [{'id': 'a', 'type': 'text', 'box': [0, 0, 1, 1]}, {'id': 'b', 'type': 'text', 'box': [0, 0, 1, 1]},
                                 {'id': 'g1', 'type': 'group', 'children': ['a']}, {'id': 'g2', 'type': 'group', 'children': ['a']}]}, 'two groups')
        self.bad({'canvas': {'width': 0, 'height': 10}, 'elements': [{'id': 'a', 'type': 'text', 'x': 0, 'y': 0, 'width': 1, 'height': 1}]}, 'positive')
        self.bad({'canvas': {'width': 10, 'height': 10}, 'elements': []}, 'non-empty')
        self.bad({**b, 'nodes': [{'id': 'a', 'type': 'text', 'box': [-1e308, 10, 1e308, 30]}]}, '1,000,000')

    def test_friendly_coercion(self):
        g = load({**self.BASE, 'nodes': [{'id': 'a', 'type': 'text', 'box': ['0', 0, '50px', 10], 'text': 2026,
                                          'style': {'fontWeight': 'bold', 'fontSize': '40px', 'align': 'centre'}}]})
        a = g.by_id['a']
        self.assertEqual((a.font_weight, a.font_size, a.style['align'], a.text, a.box.w), (700, 40.0, 'center', '2026', 50.0))


class PlanTests(unittest.TestCase):
    def test_tiers(self):
        self.assertEqual(plan_tier(1080, 1080, 1080, 1350)['tier'], 1)    # same family
        self.assertEqual(plan_tier(1080, 1080, 1200, 1000)['tier'], 1)
        self.assertEqual(plan_tier(1080, 1350, 1600, 900)['tier'], 2)     # orientation flips
        self.assertEqual(plan_tier(1080, 1080, 1080, 1920)['tier'], 2)    # 1.78x taller
        self.assertEqual(plan_tier(1080, 1080, 728, 90)['tier'], 3)       # 8x wider
        self.assertEqual(plan_tier(1200, 628, 160, 600)['tier'], 3)       # tiny short side
        self.assertEqual(plan_tier(1080, 1080, 300, 250)['tier'], 2)      # same shape, far smaller

    def test_every_eval_size_gets_a_reasoned_tier(self):
        for s in EVAL_SIZES:
            p = plan_tier(1080, 1080, s['width'], s['height'])
            self.assertIn(p['tier'], (1, 2, 3))
            self.assertTrue(p['reasons'] and p['strategy'])


class UnderstandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        names = [p.stem for p in TESTSET.glob('*.json') if p.stem != 'index']
        cls.a = {n: analyze(design(n), EVAL_SIZES) for n in names}

    def role(self, name, node):
        return self.a[name]['roles'][node]['role']

    def test_testset_index_matches_files(self):
        index = json.loads((TESTSET / 'index.json').read_text())
        self.assertEqual(sorted(d['id'] for d in index), sorted(self.a))
        self.assertGreaterEqual(len(index), 12)

    def test_headlines_found(self):
        for name in ('promo-centered', 'split-photo-left', 'overlay-fullbleed', 'event-poster', 'product-grid',
                     'webinar-speakers', 'story-stacked', 'dense-menu', 'app-download'):
            self.assertEqual(self.role(name, 'headline'), 'headline', name)

    def test_roles(self):
        self.assertEqual(self.role('promo-centered', 'eyebrow'), 'eyebrow')
        self.assertEqual(self.role('promo-centered', 'subhead'), 'subhead')
        self.assertEqual(self.role('promo-centered', 'logo'), 'logo')            # text wordmark near an edge
        self.assertEqual(self.role('promo-centered', 'cta-label'), 'cta')
        self.assertEqual(self.role('event-poster', 'date'), 'badge')             # a box with text that isn't a button
        self.assertEqual(self.role('event-poster', 'legal'), 'legal')
        self.assertEqual(self.role('event-poster', 'sp1-name'), 'caption')
        self.assertEqual(self.role('product-grid', 'p2-price'), 'price')
        self.assertEqual(self.role('sale-banner', 'legal'), 'legal')
        self.assertEqual(self.role('asymmetric-number', 'offer'), 'offer')
        self.assertEqual(self.role('dense-menu', 'item3'), 'item')
        self.assertEqual(self.role('overlay-fullbleed', 'photo'), 'background')
        self.assertEqual(self.role('split-photo-left', 'photo'), 'hero')
        self.assertEqual(self.role('app-download', 'ios'), 'cta')                # store badge counts as a CTA

    def test_given_roles_win(self):
        a = self.a['overlay-fullbleed']
        self.assertEqual(a['roles']['logo'], {'role': 'logo', 'source': 'given', 'confidence': 1.0})

    def test_groups(self):
        a = self.a['promo-centered']
        self.assertEqual(sorted(by_member(a, 'headline')['members']), ['eyebrow', 'headline', 'subhead'])
        self.assertEqual(by_member(a, 'cta-label')['kind'], 'button')
        a = self.a['product-grid']
        cards = [g for g in a['groups'] if g['kind'] == 'card']
        self.assertEqual(len(cards), 3)
        self.assertEqual(sorted(by_member(a, 'p1')['members']), ['p1', 'p1-name', 'p1-price'])
        a = self.a['quote-card']
        self.assertEqual(by_member(a, 'avatar')['kind'], 'lockup')
        self.assertEqual(sorted(by_member(a, 'avatar')['members']), ['avatar', 'name', 'title'])

    def test_logo_is_its_own_group(self):
        for name in ('coffee_ad', 'sneaker_drop', 'saas_webinar'):
            a = analyze(json.loads((ROOT / 'examples' / f'{name}.json').read_text()))
            self.assertEqual(by_member(a, 'logo')['members'], ['logo'], name)
            self.assertIn('top', by_member(a, 'logo')['anchors'])

    def test_column_anchors_beside_tall_photos(self):
        a = self.a['split-photo-left']
        self.assertIn('left', by_member(a, 'headline')['anchors'])      # left of its column, not the page
        self.assertIn('left', by_member(a, 'cta-bg')['anchors'])
        self.assertEqual(by_member(a, 'headline')['column'], [600.0, 1200.0])
        a = self.a['app-download']
        for node in ('headline', 'ios', 'rating'):
            self.assertIn('left', by_member(a, node)['anchors'], node)

    def test_vertical_anchors_need_the_edge(self):
        a = self.a['split-photo-left']
        self.assertNotIn('bottom', by_member(a, 'cta-bg')['anchors'])   # mid-column button
        self.assertEqual(self.role('split-photo-left', 'body'), 'body')  # two-line copy is body, not subhead
        self.assertEqual(self.role('sale-banner', 'offer'), 'offer')
        self.assertEqual(self.role('sale-banner', 'headline'), 'headline')
        self.assertEqual(self.role('quote-card', 'name'), 'caption')

    def test_dividers_and_rows(self):
        a = self.a['dense-menu']
        self.assertEqual(by_member(a, 'headline')['members'], ['headline'])      # the rule line separates it
        row = by_member(a, 'item2')
        self.assertEqual((row['kind'], sorted(row['members'])), ('row', ['item2', 'price2']))
        self.assertEqual(len(a['repeats'][0]['groups']), 6)
        self.assertEqual(a['repeats'][0]['axis'], 'column')

    def test_text_defines_only_its_aligned_edge(self):
        lines = self.a['dense-menu']['grid']['lines']
        self.assertTrue(any(l['kind'] == 'right' and abs(l['pos'] - 990) < 2 and len(l['members']) >= 6 for l in lines))
        self.assertFalse(any(l['kind'] == 'center' and abs(l['pos'] - 390) < 2 for l in lines))
        self.assertEqual(set(by_member(self.a['dense-menu'], 'item2')['anchors']) & {'left', 'right'}, {'left', 'right'})

    def test_repeats(self):
        rep = self.a['event-poster']['repeats']
        self.assertEqual((rep[0]['axis'], len(rep[0]['groups'])), ('row', 3))
        self.assertAlmostEqual(rep[0]['gap'], 40, delta=1)

    def test_anchors(self):
        a = self.a['overlay-fullbleed']
        self.assertEqual(set(by_member(a, 'logo')['anchors']) & {'left', 'top'}, {'left', 'top'})
        self.assertIn('bottom', by_member(a, 'cta-bg')['anchors'])
        a = self.a['promo-centered']
        self.assertIn('center-x', by_member(a, 'headline')['anchors'])
        self.assertNotIn('left', by_member(a, 'headline')['anchors'])
        self.assertIn('bottom', by_member(a, 'logo')['anchors'])

    def test_grid_and_style(self):
        a = self.a['split-photo-left']
        self.assertEqual(a['style']['structure'], 'split-horizontal')
        self.assertEqual(a['grid']['alignment'], 'left')
        self.assertTrue(any(l['kind'] == 'left' and abs(l['pos'] - 660) < 2 for l in a['grid']['lines']))
        self.assertEqual(self.a['promo-centered']['grid']['alignment'], 'center')
        self.assertEqual(self.a['overlay-fullbleed']['style']['structure'], 'overlay')
        self.assertEqual(self.a['story-stacked']['style']['structure'], 'stacked')
        self.assertEqual(self.a['story-stacked']['grid']['margins']['left'], 70)  # full-bleed photo ignored

    def test_reading_order(self):
        order = self.a['overlay-fullbleed']['reading_order']
        a = self.a['overlay-fullbleed']
        self.assertLess(order.index(by_member(a, 'logo')['id']), order.index(by_member(a, 'headline')['id']))
        self.assertLess(order.index(by_member(a, 'headline')['id']), order.index(by_member(a, 'cta-bg')['id']))

    def test_subjects_and_notes(self):
        a = self.a['split-photo-left']
        self.assertEqual(a['subjects']['photo']['source'], 'given')
        self.assertEqual(a['subjects']['photo']['page_box'], [150.0, 125.6, 300.0, 408.2])
        self.assertTrue(any('side by side' in n for n in a['notes']))
        self.assertNotIn('logo', a['subjects'])

    def test_studio_format_analyzes(self):
        a = analyze(json.loads((ROOT / 'examples' / 'coffee_ad.json').read_text()))
        self.assertEqual(by_member(a, 'cta__label')['kind'], 'button')
        self.assertEqual(a['grid']['alignment'], 'left')

    def test_fast_and_deterministic(self):
        d = design('product-grid')
        t0 = time.perf_counter()
        first = analyze(d, EVAL_SIZES)
        self.assertLess(time.perf_counter() - t0, 0.2)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(analyze(d, EVAL_SIZES), sort_keys=True))


class SubjectTests(unittest.TestCase):
    def test_saliency_finds_off_centre_subject(self):
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest('Pillow not installed')
        img = Image.new('RGB', (400, 300), (210, 205, 200))
        ImageDraw.Draw(img).ellipse((270, 60, 370, 160), fill=(200, 30, 40))
        buf = io.BytesIO(); img.save(buf, 'PNG')
        src = 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()
        node = load({'format': 'chameleon-graph/1', 'page': {'width': 400, 'height': 300},
                     'nodes': [{'id': 'p', 'type': 'image', 'box': [0, 0, 400, 300], 'src': src}]}).by_id['p']
        found = subject.find_subject(node)
        self.assertIn(found['source'], ('saliency', 'faces'))
        x, y, w, h = found['box']
        self.assertGreater(x + w / 2, .55)   # the red disc sits right of centre
        self.assertLess(y + h / 2, .6)

    def _uri(self, img):
        buf = io.BytesIO(); img.save(buf, 'PNG')
        return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()

    def test_flat_and_multiple_objects(self):
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest('Pillow not installed')
        for c in ((255, 255, 255), (128, 128, 128), (90, 120, 150)):
            self.assertEqual(subject._detect(self._uri(Image.new('RGB', (300, 200), c)))['source'], 'assumed')
        img = Image.new('RGB', (1200, 600), (240, 240, 240)); d = ImageDraw.Draw(img)
        d.ellipse((100, 200, 300, 400), fill=(200, 30, 30)); d.ellipse((900, 200, 1100, 400), fill=(30, 30, 200))
        x, y, w, h = subject._detect(self._uri(img))['box']
        self.assertLess(x, .1); self.assertGreater(x + w, .9)          # both objects kept
        img = Image.new('RGB', (1000, 1000), (240, 240, 240)); d = ImageDraw.Draw(img)
        d.rectangle((100, 100, 700, 800), fill=(40, 160, 60)); d.ellipse((880, 880, 900, 900), fill=(230, 0, 0))
        x, y, w, h = subject._detect(self._uri(img))['box']
        self.assertLess(x, .15); self.assertGreater(x + w, .65)        # the big object, not the dot

    def test_sky_ground_and_object(self):
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest('Pillow not installed')
        img = Image.new('RGB', (1200, 800)); d = ImageDraw.Draw(img)
        for y in range(800): d.line([(0, y), (1200, y)], fill=(120, 170, 230) if y < 300 else (90, 140, 60))
        d.ellipse((700, 350, 900, 550), fill=(220, 40, 40))
        x, y, w, h = subject._detect(self._uri(img))['box']
        self.assertTrue(x <= 700 / 1200 and x + w >= 900 / 1200 and y <= 350 / 800 and y + h >= 550 / 800)
        self.assertLess(w * h, .25)   # the object, not the whole ground band

    def test_never_reads_local_files(self):
        node = load({'format': 'chameleon-graph/1', 'page': {'width': 10, 'height': 10},
                     'nodes': [{'id': 'p', 'type': 'image', 'box': [0, 0, 10, 10], 'src': str(ROOT / 'previews' / 'v3-home.png')}]}).by_id['p']
        self.assertEqual(subject.find_subject(node)['source'], 'assumed')

    def test_fallback_without_pixels(self):
        node = load({'format': 'chameleon-graph/1', 'page': {'width': 10, 'height': 10},
                     'nodes': [{'id': 'p', 'type': 'image', 'box': [0, 0, 10, 10]}]}).by_id['p']
        self.assertEqual(subject.find_subject(node)['source'], 'assumed')


class AnalyzeHTTPTests(unittest.TestCase):
    def test_endpoints(self):
        from local_server import ThreadingHTTPServer, Handler
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        opener = build_opener(ProxyHandler({}))

        def api(path, data=None):
            req = Request(base + path, data=json.dumps(data).encode() if data is not None else None,
                          method='POST' if data is not None else 'GET', headers={'Content-Type': 'application/json'})
            with opener.open(req, timeout=10) as r:
                return json.load(r)
        try:
            ts = api('/testset')
            self.assertEqual(len(ts['sizes']), 8)
            d = api('/testset/' + ts['designs'][0]['id'])
            out = api('/analyze', {'design': d})
            self.assertEqual(len(out['targets']), 8)
            self.assertIn('groups', out)
            out = api('/analyze', {'design': d, 'targets': [{'name': 'x', 'width': 728, 'height': 90}]})
            self.assertEqual(out['targets'][0]['tier'], 3)
            with self.assertRaises(HTTPError) as e:
                api('/analyze', {'design': {'nodes': []}})
            self.assertEqual(e.exception.code, 400)
            with self.assertRaises(HTTPError) as e:
                api('/testset/../../secret')
            self.assertEqual(e.exception.code, 404)
            for bad in ({'design': {'format': 'chameleon-graph/1', 'page': {'width': 10, 'height': 10},
                                    'nodes': [{'id': 'g', 'type': 'group', 'children': ['g']}]}},
                        {'design': d, 'targets': [1080]}, {'design': d, 'targets': [{'width': None, 'height': 5}]},
                        {'design': {'canvas': {'width': 0, 'height': 5}, 'elements': [{'id': 'a'}]}}):
                with self.assertRaises(HTTPError) as e:
                    api('/analyze', bad)
                self.assertEqual(e.exception.code, 400, bad)
            with self.assertRaises(HTTPError) as e:
                api('/testset/index')
            self.assertEqual(e.exception.code, 404)
            with opener.open(base + '/xray') as r:
                self.assertEqual(r.status, 200)
        finally:
            server.shutdown(); server.server_close(); thread.join()


if __name__ == '__main__':
    unittest.main()
