"""Solve stage: adapt() lays every test-set design out at the 8 evaluation sizes."""
import json, random, sys, threading, time, unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from engine.adapt import adapt, MIN_TEXT          # noqa: E402
from engine.plan import EVAL_SIZES                 # noqa: E402

TESTSET = ROOT / 'examples' / 'testset'
IDS = [d['id'] for d in json.loads((TESTSET / 'index.json').read_text())]


def design(i):
    return json.loads((TESTSET / f'{i}.json').read_text())


def visible(res):
    return {n['id']: n for n in res['design']['nodes'] if n['type'] != 'group' and not n.get('hidden')}


class AdaptTestSet(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = {i: adapt(design(i), EVAL_SIZES) for i in IDS}

    def test_every_size_passes_the_checks(self):
        for i, r in self.out.items():
            self.assertEqual(len(r['results']), 8)
            for res in r['results']:
                c = res['checks']
                where = f"{i} {res['width']:.0f}x{res['height']:.0f}"
                self.assertEqual(c['overlaps'], [], where)
                self.assertEqual(c['off_canvas'], [], where)
                self.assertEqual(c['small_text'], [], where)
                self.assertTrue(c['ok'], where)
                self.assertTrue(res['reasons'][0].startswith(f"Tier {res['tier']}"), where)

    def test_geometry_is_really_inside_and_readable(self):
        """Re-measure the output itself rather than trusting check()."""
        for i, r in self.out.items():
            for res in r['results']:
                W, H = res['width'], res['height']
                for n in visible(res).values():
                    x, y, w, h = n['box']
                    if n['type'] == 'text':
                        self.assertGreaterEqual(n['style']['fontSize'], MIN_TEXT - .01, (i, W, H, n['id']))
                        self.assertTrue(-1 <= x and -1 <= y and x + w <= W + 1 and y + h <= H + 1, (i, W, H, n['id']))
                    self.assertTrue(w > 0 and h > 0, (i, W, H, n['id']))

    def test_headline_and_cta_are_never_dropped(self):
        for i, r in self.out.items():
            roles = {}
            from engine.understand import analyze
            from engine.graph import load
            a = analyze(load(design(i)))
            roles = {k: v['role'] for k, v in a['roles'].items()}
            for res in r['results']:
                vis = visible(res)
                for nid, role in roles.items():
                    if role in ('headline',):
                        self.assertIn(nid, vis, (i, res['width'], res['height'], nid))

    def test_subjects_are_kept(self):
        for i, r in self.out.items():
            for res in r['results']:
                kept = res['checks']['subject_kept']
                if kept is not None:
                    self.assertGreaterEqual(kept, .8, (i, res['width'], res['height']))

    def test_original_size_keeps_the_layout(self):
        for i in IDS:
            d = design(i)
            W, H = d['page']['width'], d['page']['height']
            res = adapt(d, [{'width': W, 'height': H}])['results'][0]
            self.assertEqual(res['tier'], 1)
            self.assertIn('Original size: layout kept as designed.', res['reasons'], i)
            orig = {n['id']: n for n in d['nodes'] if n['type'] != 'group'}
            from engine.understand import analyze
            from engine.graph import load
            labels = {t for ts in analyze(load(d))['layers']['containers'].values() for t in ts}
            for nid, n in visible(res).items():
                if nid in labels:          # button labels are re-centred in their button
                    continue
                ob = orig[nid]['box']
                al = (orig[nid].get('style') or {}).get('align', 'left')
                if orig[nid]['type'] == 'text' and al == 'center':
                    self.assertLess(abs(n['box'][0] + n['box'][2] / 2 - ob[0] - ob[2] / 2), 4, (i, nid))
                elif orig[nid]['type'] == 'text' and al == 'right':
                    self.assertLess(abs(n['box'][0] + n['box'][2] - ob[0] - ob[2]), 4, (i, nid))
                else:
                    self.assertLess(abs(n['box'][0] - ob[0]), 4, (i, nid))
                self.assertLess(abs(n['box'][1] - ob[1]), 30, (i, nid))
                if orig[nid]['type'] == 'text':
                    self.assertAlmostEqual(n['style']['fontSize'], orig[nid]['style']['fontSize'], delta=.5)

    def test_same_family_keeps_anchors(self):
        """1080x1080 -> 1080x1350: the bottom-anchored logo stays at the bottom, centred things stay centred."""
        res = adapt(design('promo-centered'), [{'width': 1080, 'height': 1350}])['results'][0]
        self.assertTrue(any(r.startswith('Layout kept') for r in res['reasons']))
        vis = visible(res)
        x, y, w, h = vis['logo']['box']
        self.assertAlmostEqual(x + w / 2, 540, delta=3)
        self.assertGreater(y, 1350 * .85)
        hx, _, hw, _ = vis['headline']['box']
        self.assertAlmostEqual(hx + hw / 2, 540, delta=3)

    def test_cards_go_beside_copy_on_wide_canvases(self):
        r = {res['width']: res for res in self.out['event-poster']['results']}
        res = r[1200]
        self.assertIn('Cards placed beside the copy for the wider canvas.', res['reasons'])
        vis = visible(res)
        self.assertGreater(vis['sp1']['box'][0], vis['headline']['box'][0] + vis['headline']['box'][2] - 1)
        # cards wrap into a grid or stay a row, but are all shown
        for nid in ('sp1', 'sp2', 'sp3'):
            self.assertIn(nid, vis)

    def test_text_list_reflows_instead_of_shrinking(self):
        """The menu's item ... price rows re-lay out at 300 px wide; prices stay right-aligned with their item."""
        r = {res['width']: res for res in self.out['dense-menu']['results']}
        vis = visible(r[1080])
        self.assertIn('item1', vis)
        ix, iy, iw, ih = vis['item1']['box']; px, py, pw, ph = vis['price1']['box']
        self.assertAlmostEqual(iy, py, delta=2)
        self.assertGreater(px, ix + iw)

    def test_banner_puts_logo_in_the_row(self):
        r = {res['width']: res for res in self.out['product-grid']['results']}
        res = r[728]
        self.assertIn('Logo joins the row so the banner reads left to right.', res['reasons'])
        vis = visible(res)
        lx, ly, lw, lh = vis['logo']['box']
        self.assertLess(lx, 728 * .3)
        self.assertTrue(0 <= ly and ly + lh <= 90)

    def test_light_logo_stays_on_the_photo(self):
        """story-stacked's logo is white, made for the photo: it must never land on the cream copy area."""
        for res in self.out['story-stacked']['results']:
            self.assertEqual(res['checks']['low_contrast'], [], res['width'])
            if 'logo' in visible(res):
                self.assertFalse(any(r.startswith('Logo joins the row') for r in res['reasons']))
            else:
                self.assertTrue(any(r.startswith('Logo dropped') for r in res['reasons']), res['width'])

    def test_drops_are_explained(self):
        from engine.understand import analyze
        from engine.graph import load
        for i, r in self.out.items():
            roles = {k: v['role'] for k, v in analyze(load(design(i)))['roles'].items()}
            for res in r['results']:
                text = ' '.join(res['reasons']).lower()
                for nid in res['checks']['dropped']:
                    role = roles.get(nid, '')
                    if role in ('panel', 'background'):
                        continue
                    name = 'photo' if role in ('hero', 'image') else role
                    self.assertTrue(name in text or 'cards' in text or 'showing' in text or 'logo dropped' in text,
                                    (i, res['width'], res['height'], nid, role, res['reasons']))

    def test_photos_are_cropped_not_stretched_and_src_not_repeated(self):
        for i, r in self.out.items():
            for res in r['results']:
                for n in res['design']['nodes']:
                    self.assertNotIn('src', n)
                    if n.get('crop'):
                        cx, cy, cw, ch = n['crop']
                        self.assertTrue(0 <= cx <= 1 and 0 <= cy <= 1 and 0 < cw <= 1.0001 and 0 < ch <= 1.0001)

    def test_baselines(self):
        res = self.out['promo-centered']['results'][6]       # 728x90
        b = res['baselines']
        self.assertGreater(b['stretch']['distortion'], 5)
        self.assertTrue(b['crop']['cut'])

    def test_deterministic(self):
        a1 = adapt(design('webinar-speakers'), EVAL_SIZES)
        a2 = adapt(design('webinar-speakers'), EVAL_SIZES)
        self.assertEqual(json.dumps(a1, sort_keys=True), json.dumps(a2, sort_keys=True))


class AdaptRobustness(unittest.TestCase):
    def test_legacy_studio_json(self):
        d = json.loads((ROOT / 'examples' / 'coffee_ad.json').read_text())
        out = adapt(d, EVAL_SIZES)
        self.assertEqual(len(out['results']), 8)

    def test_random_designs_never_crash_and_finish_fast(self):
        rnd = random.Random(7)
        words = 'Big summer sale shop now free shipping new arrivals limited time only today'.split()
        for trial in range(40):
            W, H = rnd.choice([(1080, 1080), (1200, 628), (1080, 1920), (300, 250)])
            nodes = []
            for j in range(rnd.randint(1, 14)):
                t = rnd.choice(['text', 'text', 'shape', 'image'])
                w, h = rnd.uniform(20, W * .9), rnd.uniform(10, H * .5)
                box = [rnd.uniform(0, W - w), rnd.uniform(0, H - h), w, h]
                n = {'id': f'n{j}', 'type': t, 'box': box}
                if t == 'text':
                    n['text'] = ' '.join(rnd.choice(words) for _ in range(rnd.randint(1, 9)))
                    n['style'] = {'fontSize': rnd.uniform(8, 120), 'fontWeight': rnd.choice([400, 700, 900])}
                elif t == 'shape':
                    n['shape'] = 'rect'; n['style'] = {'fill': '#333'}
                nodes.append(n)
            d = {'format': 'chameleon-graph/1', 'page': {'width': W, 'height': H}, 'nodes': nodes}
            t0 = time.time()
            out = adapt(d, EVAL_SIZES)
            self.assertLess(time.time() - t0, 5, trial)
            for res in out['results']:
                for n in res['design']['nodes']:
                    if 'box' in n and not n.get('hidden'):
                        self.assertTrue(all(abs(v) < 1e6 for v in n['box']), (trial, n))


class AdaptHTTP(unittest.TestCase):
    def test_endpoint(self):
        from local_server import ThreadingHTTPServer, Handler
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{server.server_port}'
        opener = build_opener(ProxyHandler({}))

        def api(path, data):
            req = Request(base + path, data=json.dumps(data).encode(), method='POST',
                          headers={'Content-Type': 'application/json'})
            with opener.open(req, timeout=20) as r:
                return json.load(r)
        try:
            out = api('/adapt', {'design': design('sale-banner')})
            self.assertEqual(len(out['results']), 8)
            out = api('/adapt', {'design': design('sale-banner'), 'targets': [{'width': 728, 'height': 90}]})
            self.assertEqual(out['results'][0]['tier'], 3)
            for bad in ({'design': design('sale-banner'), 'targets': [{'width': 5, 'height': 5}]},
                        {'design': {'nodes': []}}, {'targets': []}):
                with self.assertRaises(HTTPError) as e:
                    api('/adapt', bad)
                self.assertEqual(e.exception.code, 400, bad)
        finally:
            server.shutdown(); server.server_close()


if __name__ == '__main__':
    unittest.main()
