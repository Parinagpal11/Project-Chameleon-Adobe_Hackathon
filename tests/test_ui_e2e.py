"""Browser end-to-end tests of the Studio (every size laid out by the layout engine). Skips unless Playwright + Chromium are installed:
    pip install playwright && python -m playwright install chromium
"""
import base64, json, os, struct, sys, tempfile, threading, unittest, zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / 'backend'))
try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None


@unittest.skipIf(sync_playwright is None, 'Playwright not installed')
class StudioE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ['CHAMELEON_DB'] = str(Path(cls.tmp.name) / 'db.sqlite3'); os.environ['CHAMELEON_QUIET'] = '1'
        from local_server import ThreadingHTTPServer, Handler
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.pw = sync_playwright().start()
        try:
            cls.browser = cls.pw.chromium.launch()
        except Exception as exc:
            cls.pw.stop(); cls.server.shutdown(); raise unittest.SkipTest(f'Chromium unavailable: {exc}')

    @classmethod
    def tearDownClass(cls):
        cls.browser.close(); cls.pw.stop(); cls.server.shutdown(); cls.server.server_close()
        os.environ.pop('CHAMELEON_DB', None); cls.tmp.cleanup()

    def open(self):
        page = self.browser.new_page(viewport={'width': 1440, 'height': 900}, accept_downloads=True)
        self.errors = []; page.on('pageerror', lambda e: self.errors.append(str(e)))
        page.goto(f'http://127.0.0.1:{self.server.server_port}/')
        page.evaluate("localStorage.setItem('chameleon.tour.v3','1')")
        page.click('#new-sample'); page.wait_for_selector('.frame >> nth=5')
        page.wait_for_timeout(500)
        return page

    def drag(self, page, key, eid, dx, dy):
        page.evaluate(f"App.focusFrame('{key}')"); page.wait_for_timeout(200)
        b = page.evaluate(f"App.elBoxClient('{key}','{eid}')")
        x, y = b['x'] + b['w'] / 2, b['y'] + b['h'] / 2
        page.mouse.move(x, y); page.mouse.down()
        for i in range(1, 11): page.mouse.move(x + dx * i / 10, y + dy * i / 10)
        page.mouse.up(); page.wait_for_timeout(300)

    def test_sample_layout_options_tweak_and_export_zip(self):
        page = self.open()
        self.assertEqual(page.locator('.frame').count(), 6)
        # every size comes from the engine, with a photo and no failed checks
        self.assertTrue(page.evaluate("activeFormats().every(f => chosen(f.key) && chosen(f.key).checks.ok)"))
        self.assertTrue(page.evaluate("activeFormats().every(f => display(f.key).elements.some(e => e.type === 'image' && e.src))"))
        # a size explains itself and offers the other layouts it tried
        page.evaluate("App.select({key:'feed',id:null})"); page.wait_for_timeout(300)
        self.assertIn('Why it looks like this', page.inner_text('#pane-design'))
        n = page.locator('#pane-design .layout-opt').count()
        if n > 1:
            page.locator('#pane-design .layout-opt').nth(1).click(); page.wait_for_function("!!S.choices.feed")
        # dragging the headline changes that size only, and undo puts it back
        self.drag(page, 'ig-post', 'headline', 30, 40)
        self.assertTrue(page.evaluate("!!S.overrides['ig-post'].headline"))
        self.assertFalse(page.evaluate("!!(S.overrides.feed||{}).headline"))
        self.assertEqual(page.locator('.frame-label[data-key="ig-post"] .flag.tw').count(), 1)
        page.keyboard.press('Control+z'); page.wait_for_function("!(S.overrides['ig-post']||{}).headline")
        with page.expect_download() as dl: page.click('#export-all')
        z = zipfile.ZipFile(dl.value.path()); pngs = [n for n in z.namelist() if n.endswith('.png')]
        self.assertEqual(len(pngs), 6)
        self.assertIn((728, 90), [struct.unpack('>II', z.read(n)[16:24]) for n in pngs])
        self.assertEqual(self.errors, []); page.close()

    def settle(self, page):
        page.wait_for_timeout(200)
        page.wait_for_function("!document.body.classList.contains('is-busy')", timeout=30000)

    def test_photo_framing_whole_and_focus(self):
        page = self.open()
        page.evaluate("App.select({key:'feed',id:null})"); page.wait_for_timeout(300)
        page.click('#pane-design [role="radio"]:has-text("Whole photo")')
        page.wait_for_function("photoNode().meta.keepWhole === true"); self.settle(page)
        kept = page.evaluate("activeFormats().map(f => chosen(f.key).checks.subject_kept)")
        self.assertTrue(all(k >= .98 for k in kept), kept)          # the whole photo shows at every size
        page.click('#pane-design [role="radio"]:has-text("Focus area")')
        pick = page.locator('.focus-pick'); pick.scroll_into_view_if_needed(); b = pick.bounding_box()
        x0, y0 = b['x'] + b['width'] * .4, b['y'] + b['height'] * .55
        page.mouse.move(x0, y0); page.mouse.down(); page.mouse.move(x0 + b['width'] * .2, y0 + b['height'] * .25, steps=6); page.mouse.up()
        page.wait_for_function("!!photoNode().meta.focus && !photoNode().meta.keepWhole"); self.settle(page)
        kept = page.evaluate("activeFormats().map(f => [f.key, chosen(f.key).checks.subject_kept, photoNode().meta.focus])")
        self.assertTrue(all((k or 0) >= .9 for _, k, _ in kept), kept)   # the marked area stays in view
        page.click('#pane-design [role="radio"]:has-text("Auto")')
        page.wait_for_function("!photoNode().meta.focus && !photoNode().meta.keepWhole")
        self.assertEqual(self.errors, []); page.close()

    def test_frames_photo_drop_and_reopen(self):
        page = self.open()
        page.click('#add-frame-btn'); page.click('.preset[data-key="yt"]'); page.wait_for_function("document.querySelectorAll('.frame').length===7")
        photo = (ROOT / 'tests' / 'fixtures' / 'photos' / 'user-coral-sandal.jpg').read_bytes()
        page.evaluate("""async (b64)=>{const bin=Uint8Array.from(atob(b64),c=>c.charCodeAt(0));const dt=new DataTransfer();
            dt.items.add(new File([bin],'sandal.jpg',{type:'image/jpeg'}));
            for(const t of ['dragenter','dragover','drop']) window.dispatchEvent(new DragEvent(t,{dataTransfer:dt,clientX:700,clientY:500,bubbles:true,cancelable:true}));}""",
                      base64.b64encode(photo).decode())
        page.wait_for_function("Object.keys(S.assets).length===1")
        page.wait_for_function("photoNode().src.startsWith('asset:') && activeFormats().every(f => chosen(f.key))", timeout=30000)
        page.wait_for_timeout(900)
        page.reload(); page.wait_for_selector('.frame >> nth=6')
        page.wait_for_timeout(500)
        self.assertEqual(page.evaluate("Object.keys(S.assets).length"), 1)
        self.assertTrue(page.evaluate("photoNode().src.startsWith('asset:')"))
        self.assertEqual(self.errors, []); page.close()


if __name__ == '__main__':
    unittest.main()
