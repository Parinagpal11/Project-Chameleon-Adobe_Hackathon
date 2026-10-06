"""Browser tests of the X-ray page. Skips unless Playwright + Chromium are installed."""
import base64, io, json, os, sys, tempfile, threading, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / 'backend'))
try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None


@unittest.skipIf(sync_playwright is None, 'Playwright not installed')
class XrayE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ['CHAMELEON_QUIET'] = '1'
        from local_server import ThreadingHTTPServer, Handler
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'
        cls.pw = sync_playwright().start()
        try:
            cls.browser = cls.pw.chromium.launch()
        except Exception as exc:
            cls.pw.stop(); cls.server.shutdown(); raise unittest.SkipTest(f'Chromium unavailable: {exc}')

    @classmethod
    def tearDownClass(cls):
        cls.browser.close(); cls.pw.stop(); cls.server.shutdown(); cls.server.server_close(); cls.tmp.cleanup()

    def open(self, design='overlay-fullbleed', w=1440, h=900):
        page = self.browser.new_page(viewport={'width': w, 'height': h})
        self.errors = []; page.on('pageerror', lambda e: self.errors.append(str(e)))
        page.goto(f'{self.base}/xray#d={design}')
        page.wait_for_selector('.xr-group'); page.wait_for_timeout(300)
        return page

    def test_overlay_panel_and_interactions(self):
        page = self.open('event-poster')
        self.assertNotIn('null', page.inner_text('#xr-meta'))
        groups = page.locator('.xr-group').count()
        self.assertEqual(groups, page.locator('.xr-overlay .grp').count())
        # overlay sits exactly on the canvas
        c = page.locator('#xr-canvas').bounding_box(); o = page.locator('#xr-overlay').bounding_box()
        self.assertAlmostEqual(c['width'], o['width'], delta=1); self.assertAlmostEqual(c['x'], o['x'], delta=1)
        # hovering a group in the list highlights it on the design
        page.hover('.xr-group >> nth=1')
        gid = page.get_attribute('.xr-group >> nth=1', 'data-id')
        self.assertEqual(page.get_attribute('.xr-overlay .grp.on', 'data-id'), gid)
        # toggles switch layers
        page.click('label:has(#xr-l-groups)')
        self.assertEqual(page.locator('.xr-overlay .grp').count(), 0)
        page.click('label:has(#xr-l-groups)')
        self.assertEqual(page.locator('.xr-overlay .grp').count(), groups)
        # tiers for the 8 evaluation sizes
        self.assertEqual(page.locator('.xr-tier').count(), 8)
        # hash change loads another design
        page.evaluate("location.hash = '#d=dense-menu'")
        page.wait_for_function("document.querySelector('#xr-design').value === 'dense-menu' && document.querySelector('#xr-meta').textContent.includes('menu')")
        self.assertEqual(self.errors, [])

    def test_use_your_photo(self):
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest('Pillow not installed')
        img = Image.new('RGB', (900, 1200), (235, 238, 240)); ImageDraw.Draw(img).ellipse((520, 200, 820, 500), fill=(220, 50, 40))
        path = Path(self.tmp.name) / 'photo.png'; img.save(path)
        page = self.open('overlay-fullbleed')
        page.set_input_files('#xr-photo', str(path))
        page.wait_for_selector('.xr-pill.mine')
        self.assertRegex(page.inner_text('.xr-pill.mine'), 'saliency|object detection')
        sub = page.evaluate("XR.S.analysis.subjects.photo")
        x, y, w, h = sub['box']
        self.assertGreater(x + w / 2, .5); self.assertLess(y + h / 2, .5)     # the disc is top-right
        page.select_option('#xr-design', 'promo-centered')
        page.wait_for_function("!document.querySelector('.xr-pill.mine')")
        self.assertEqual(self.errors, [])

    def test_import_errors_keep_state(self):
        page = self.open('quote-card')
        bad = Path(self.tmp.name) / 'studio.json'
        bad.write_text(json.dumps(json.loads((ROOT / 'examples' / 'coffee_ad.json').read_text())))
        page.set_input_files('#xr-file', str(bad))
        page.wait_for_selector('#xr-error:not([hidden])')
        self.assertEqual(page.input_value('#xr-design'), 'quote-card')
        good = Path(self.tmp.name) / 'mine.json'
        good.write_text((ROOT / 'examples' / 'testset' / 'sale-banner.json').read_text())
        page.set_input_files('#xr-file', str(good))
        page.wait_for_function("document.querySelector('#xr-design').value === 'import:mine.json'")

    def test_mobile_has_no_sideways_scroll(self):
        page = self.open('webinar-speakers', 390, 844)
        self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), 391)
        home = self.browser.new_page(viewport={'width': 390, 'height': 844})
        home.goto(self.base + '/'); home.wait_for_timeout(400)
        self.assertLessEqual(home.evaluate("document.querySelector('.home').scrollWidth"), 391)


if __name__ == '__main__':
    unittest.main()
