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

    def test_blocks_nest_groups_like_designers(self):
        def block_roles(name):
            a = self.a[name]; role = {g['id']: g['role'] for g in a['groups']}
            return {b['kind']: sorted(role[x] for x in b['groups']) for b in a['blocks'] if b['kind'] != 'single'}
        self.assertEqual(block_roles('promo-centered'), {'copy': ['cta', 'headline']})
        self.assertEqual(block_roles('split-photo-left'), {'copy': ['cta', 'headline']})
        self.assertEqual(block_roles('product-grid'), {'repeat': ['image', 'image', 'image']})
        eb = block_roles('event-poster')
        self.assertNotIn('badge', eb.get('copy', []))          # corner date badge stays its own block
        for name, a in self.a.items():                           # every group is in exactly one block
            ids = [x for b in a['blocks'] for x in b['groups']]
            self.assertEqual(sorted(ids), sorted(g['id'] for g in a['groups']), name)

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
        self.assertIn(found['source'], ('saliency', 'faces', 'objects'))
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


class RealPhotoTests(unittest.TestCase):
    """Regression set from Pari's manual test round (generated photos, 800 px copies).
    Each is also checked after the browser-style crop to the 1080x1350 slot + JPEG re-save,
    which is exactly what “Use your photo” sends."""
    PHOTOS = ROOT / 'tests' / 'fixtures' / 'photos'

    def detect(self, name, browser_crop):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest('Pillow not installed')
        im = Image.open(self.PHOTOS / name).convert('RGB')
        if browser_crop:
            W, H = im.size; a = 1080 / 1350
            if W / H > a: sw = H * a; im = im.crop(((W - sw) / 2, 0, (W + sw) / 2, H))
            else: sh = W / a; im = im.crop((0, (H - sh) / 2, W, (H + sh) / 2))
        buf = io.BytesIO(); im.save(buf, 'JPEG', quality=88)
        subject._cache.clear()
        return subject._detect('data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode()), im.size

    def covers(self, box, truth, size, need=.85):
        (x, y, w, h), (W, H) = box, size
        tx0, ty0, tx1, ty1 = truth
        ix = max(0, min(x + w, tx1) - max(x, tx0)) * max(0, min(y + h, ty1) - max(y, ty0))
        return ix / ((tx1 - tx0) * (ty1 - ty0)) >= need

    def test_portrait_face(self):
        try:
            import cv2
            if not hasattr(cv2, 'CascadeClassifier'): raise ImportError
        except ImportError:
            self.skipTest('OpenCV 4.x not installed')
        for crop in (False, True):
            r, size = self.detect('portrait-woman.jpg', crop)
            self.assertEqual(r['source'], 'faces')
            x, y, w, h = r['box']
            self.assertGreater(x + w / 2, .55)          # she stands on the right

    def test_black_and_white_and_duotone_portraits(self):
        try:
            import cv2
            from PIL import Image, ImageOps
            if not hasattr(cv2, 'CascadeClassifier'): raise ImportError
        except ImportError:
            self.skipTest('OpenCV 4.x / Pillow not installed')
        w = Image.open(self.PHOTOS / 'portrait-woman.jpg').convert('RGB')
        for im in (ImageOps.grayscale(w).convert('RGB'), ImageOps.colorize(ImageOps.grayscale(w), '#0b1d51', '#a8c8ff')):
            buf = io.BytesIO(); im.save(buf, 'JPEG', quality=88); subject._cache.clear()
            r = subject._detect('data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode())
            self.assertEqual(r['source'], 'faces')

    def test_tent_tight_at_every_slot_shape(self):
        from PIL import Image
        base = Image.open(self.PHOTOS / 'landscape-tent.jpg').convert('RGB')
        for a in (0.8, 600 / 628, 1.0, 1.91):
            W, H = base.size
            im = base.crop(((W - H * a) / 2, 0, (W + H * a) / 2, H)) if W / H > a else base.crop((0, (H - W / a) / 2, W, (H + W / a) / 2))
            buf = io.BytesIO(); im.save(buf, 'JPEG', quality=88); subject._cache.clear()
            r = subject._detect('data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode())
            self.assertIn(r['source'], ('saliency', 'objects'), a)
            self.assertLess(r['box'][2] * r['box'][3], .08, (a, r['box']))

    def test_landscape_tent_is_not_a_face(self):
        for crop in (False, True):
            r, size = self.detect('landscape-tent.jpg', crop)
            self.assertIn(r['source'], ('saliency', 'objects'), crop)
            truth = (.67, .515, .83, .585) if not crop else (.665, .515, .835, .585)
            self.assertTrue(self.covers(r['box'], truth, size), r['box'])
            self.assertLess(r['box'][2] * r['box'][3], .06)   # tight around the small tent

    def test_product_keeps_the_whole_sneaker(self):
        r, size = self.detect('product-sneaker.jpg', False)
        self.assertIn(r['source'], ('saliency', 'objects'))
        self.assertTrue(self.covers(r['box'], (.17, .58, .83, .84), size, need=.97), r['box'])   # shoe incl. white toe (measured on the photo)

    def test_small_runner_in_wide_photo_is_found_and_kept(self):
        try:
            import cv2
            if not hasattr(cv2, 'CascadeClassifier'): raise ImportError
        except ImportError:
            self.skipTest('OpenCV 4.x not installed')
        r, size = self.detect('runner-sunrise.jpg', False)
        self.assertEqual(r['source'], 'people')
        crop = subject.smart_crop(r['box'], r['aspect'], 1080 / 1350, r.get('parts'))   # into a tall slot
        self.assertEqual(crop['kept'], 1.0)
        self.assertLess(crop['crop'][0], .2)                                # slid left, not centred

    def test_two_hikers_far_apart_are_both_subjects(self):
        # snowy ridge: orange hiker at the far left, blue hiker at the far right, tent and dog between.
        # The left hiker is a small blob far from the rest; it used to be dropped as "too small".
        r, size = self.detect('user-hard-snow.jpg', False)
        self.assertEqual(r['source'], 'objects')
        x, y, w, h = r['box']
        self.assertLess(x, .05, r['box'])                 # reaches the orange hiker
        self.assertGreater(x + w, .95, r['box'])          # and the blue one
        self.assertGreaterEqual(len(r.get('parts') or []), 2)

    def test_designer_crop_is_kept_at_the_original_size(self):
        try:
            from PIL import Image  # noqa: F401
        except ImportError:
            self.skipTest('Pillow not installed')
        raw = (self.PHOTOS / 'user-hard-snow.jpg').read_bytes()
        src = 'data:image/jpeg;base64,' + base64.b64encode(raw).decode()
        crop = [.2754, 0, .4492, 1]                         # centred fill of a 16:9 photo in a 4:5 slot
        d = {'format': 'chameleon-graph/1', 'page': {'width': 1080, 'height': 1350},
             'nodes': [{'id': 'photo', 'type': 'image', 'box': [0, 0, 1080, 1350], 'src': src, 'crop': crop},
                       {'id': 'h', 'type': 'text', 'box': [80, 900, 900, 120], 'text': 'Find your quiet place',
                        'style': {'fontSize': 56, 'fontWeight': 800}}]}
        subject._cache.clear()
        sub = analyze(d)['subjects']['photo']
        self.assertEqual(sub['crop'], crop)                 # the designer's framing, not a new smart crop
        self.assertLess(sub['kept'], 1.0)                   # both hikers sit outside the centre
        self.assertEqual(load(d).to_json()['nodes'][0]['crop'], crop)   # survives a load / save round trip

    def test_panorama_slides_to_the_boat(self):
        r, size = self.detect('boat-panorama.jpg', False)
        for slot in (1080 / 1350, 600 / 628, 1.0):
            c = subject.smart_crop(r['box'], r['aspect'], slot, r.get('parts'))
            self.assertEqual(c['kept'], 1.0)
            self.assertGreater(c['crop'][0] + c['crop'][2], .97)          # all the way right

    def test_smart_crop_geometry(self):
        c = subject.smart_crop([.8, .4, .1, .2], 2.0, 1.0)                  # wide photo, square slot
        self.assertEqual(c['crop'][2:], [.5, 1.0]); self.assertEqual(c['crop'][0], .5)   # clamped at the right edge
        self.assertEqual(c['kept'], 1.0)
        c = subject.smart_crop([.4, .05, .2, .1], .5, 1.0)                  # tall photo, square slot
        self.assertEqual(c['crop'][1], 0.0); self.assertEqual(c['crop'][3], .5)
        c = subject.smart_crop([0, 0, 1, 1], 2.0, .5)                       # subject bigger than the window
        self.assertLess(c['kept'], 1.0)

    def test_flat_background(self):
        for crop in (False, True):
            self.assertEqual(self.detect('flat-blue.jpg', crop)[0]['source'], 'assumed')


class PhotoGoldenTests(unittest.TestCase):
    """Every photo Pari has tested, pinned. A change to subject detection must keep all of these.
    (method, number of separate subjects, where the subject's centre must be, image-relative)"""
    GOLDEN = {
        'portrait-woman.jpg':        ('faces', 1, (.55, .85), (.2, .55)),
        'product-sneaker.jpg':       ('objects', 0, (.3, .6), (.6, .8)),
        'landscape-tent.jpg':        ('objects', 0, (.7, .82), (.5, .6)),
        'flat-blue.jpg':             ('assumed', 0, None, None),
        'fashion-street.jpg':        ('faces', 1, (.15, .4), (.08, .32)),
        'latte-overhead.jpg':        ('objects', 0, (.62, .95), (.05, .45)),
        'earbuds-gradient.jpg':      ('objects', 0, (.3, .65), (.6, .88)),
        'two-people-cafe.jpg':       ('faces', 2, None, (.1, .5)),
        'bw-portrait.jpg':           ('faces', 1, (.55, .85), (.15, .55)),
        'runner-sunrise.jpg':        ('people', 1, (.13, .2), (.58, .74)),
        # round 3 (Pari's random photos)
        'three-friends.jpg':         ('faces', 3, None, (.1, .45)),
        'profile-woman.jpg':         ('objects', 0, (.55, .85), None),
        'sunglasses-man.jpg':        ('objects', 0, (.2, .5), (.2, .7)),
        'tokyo-red-coat.jpg':        ('faces', 1, (.55, .7), (.18, .45)),
        'bottle-terrazzo.jpg':       ('objects', 0, (.65, .85), (.35, .7)),
        'dog-studio.jpg':            ('objects', 0, (.15, .45), (.35, .75)),
        'breakfast-flatlay.jpg':     ('objects', 3, None, None),
        'boat-panorama.jpg':         ('objects', 2, (.8, 1.0), None),
    }

    def test_every_tested_photo_keeps_its_result(self):
        try:
            import cv2
            if not hasattr(cv2, 'CascadeClassifier'): raise ImportError
        except ImportError:
            self.skipTest('OpenCV 4.x not installed')
        from PIL import Image
        photos = ROOT / 'tests' / 'fixtures' / 'photos'
        # each photo twice: the committed copy, and re-encoded at its original upload size the way the
        # browser sends it (small pixel differences once flipped a result, so both must hold)
        upload_size = {'two-people-cafe.jpg': (1254, 1254), 'runner-sunrise.jpg': (1672, 941), 'tokyo-red-coat.jpg': (1672, 941),
                       'bottle-terrazzo.jpg': (1254, 1254), 'boat-panorama.jpg': (2172, 724)}
        for name, (source, n_parts, cx_range, cy_range) in self.GOLDEN.items():
          for variant in ('committed', 'upload'):
            with self.subTest(photo=name, variant=variant):
                raw = (photos / name).read_bytes()
                if variant == 'upload':
                    im = Image.open(photos / name).convert('RGB')
                    size = upload_size.get(name, (1122, 1402) if im.height > im.width else (im.width * 1400 // max(im.size), im.height * 1400 // max(im.size)))
                    buf = io.BytesIO(); im.resize(size).save(buf, 'JPEG', quality=88); raw = buf.getvalue()
                subject._cache.clear()
                r = subject._detect('data:image/jpeg;base64,' + base64.b64encode(raw).decode())
                self.assertEqual(r['source'], source)
                self.assertEqual(len(r.get('parts') or []), n_parts)
                x, y, w, h = r['box']
                if cx_range: self.assertTrue(cx_range[0] <= x + w / 2 <= cx_range[1], (x + w / 2, cx_range))
                if cy_range: self.assertTrue(cy_range[0] <= y + h / 2 <= cy_range[1], (y + h / 2, cy_range))
                if name == 'two-people-cafe.jpg':
                    centres = sorted(p[0] + p[2] / 2 for p in r['parts'])
                    self.assertLess(centres[0], .4); self.assertGreater(centres[1], .6)   # one person each side


class PhotoVariantTests(unittest.TestCase):
    """Cases QA found by resizing/cropping Pari's photos: results must not flip."""
    def run_variant(self, name, size=None, crop=None, mirror=False):
        from PIL import Image, ImageOps
        im = Image.open(ROOT / 'tests' / 'fixtures' / 'photos' / name).convert('RGB')
        W, H = im.size
        if crop: im = im.crop((W * crop, H * crop, W * (1 - crop), H * (1 - crop)))
        if size: k = size / max(im.size); im = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
        if mirror: im = ImageOps.mirror(im)
        buf = io.BytesIO(); im.save(buf, 'JPEG', quality=88); subject._cache.clear()
        return subject._detect('data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode())

    def test_no_false_face_on_cropped_terrazzo(self):
        self.assertEqual(self.run_variant('bottle-terrazzo.jpg', crop=.1)['source'], 'objects')

    def test_three_friends_at_every_size(self):
        try:
            import cv2
            if not hasattr(cv2, 'CascadeClassifier'): raise ImportError
        except ImportError:
            self.skipTest('OpenCV 4.x not installed')
        for kw in ({'size': 600}, {'size': 900}, {'mirror': True}, {'crop': .1}):
            r = self.run_variant('three-friends.jpg', **kw)
            self.assertEqual((r['source'], len(r.get('parts') or [])), ('faces', 3), kw)

    def test_textures_have_no_subject(self):
        from PIL import Image
        import random
        random.seed(3)
        im = Image.new('RGB', (600, 600))
        px = im.load()
        for x in range(600):
            for y in range(600):
                v = 90 + (x * 7 + y * 13) % 40 + random.randint(-15, 15)
                px[x, y] = (v, v - 20, v - 40)
        buf = io.BytesIO(); im.save(buf, 'JPEG'); subject._cache.clear()
        self.assertEqual(subject._detect('data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode())['source'], 'assumed')


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
