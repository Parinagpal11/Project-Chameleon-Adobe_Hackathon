"""Browser end-to-end tests of the v3 studio. Skips unless Playwright + Chromium are installed:
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

    def drag_logo_to_corner(self, page, key='ig-post'):
        page.evaluate(f"App.focusFrame('{key}')"); page.wait_for_timeout(200)
        b = page.evaluate(f"App.elBoxClient('{key}','logo')")
        f = page.evaluate(f"""(()=>{{const l=App.view.layout['{key}'],r=document.getElementById('viewport').getBoundingClientRect(),z=App.view.zoom;
             return {{x:l.x*z+App.view.x+r.left,y:l.y*z+App.view.y+r.top,w:l.w*z,h:l.h*z}}}})()""")
        x, y = b['x'] + b['w'] / 2, b['y'] + b['h'] / 2
        tx, ty = f['x'] + f['w'] - b['w'] / 2 - 8, f['y'] + f['h'] - b['h'] / 2 - 8
        page.mouse.move(x, y); page.mouse.down()
        for i in range(1, 11): page.mouse.move(x + (tx - x) * i / 10, y + (ty - y) * i / 10)
        page.mouse.up(); page.wait_for_selector('#noticed:not([hidden])')

    def test_teach_rule_by_dragging_and_export_zip(self):
        page = self.open()
        self.assertEqual(page.locator('.frame').count(), 6)
        self.drag_logo_to_corner(page)
        self.assertIn('pinned bottom right', page.inner_text('#noticed-options').lower())
        page.click('#noticed-all'); page.wait_for_function('S.rules.length===1')
        cov = page.evaluate('ruleCoverage(S.rules[0])'); self.assertEqual((cov['met'], cov['applies']), (6, 6))
        page.keyboard.press('Control+z'); page.wait_for_function('S.rules.length===0')
        page.keyboard.press('Control+Shift+z'); page.wait_for_function('S.rules.length===1')
        with page.expect_download() as dl: page.click('#export-all')
        z = zipfile.ZipFile(dl.value.path()); pngs = [n for n in z.namelist() if n.endswith('.png')]
        self.assertEqual(len(pngs), 6)
        self.assertIn((728, 90), [struct.unpack('>II', z.read(n)[16:24]) for n in pngs])
        self.assertEqual(self.errors, []); page.close()

    def test_frame_only_tweak_inspector_and_typed_rule(self):
        page = self.open()
        self.drag_logo_to_corner(page)
        page.click('#noticed-one'); page.wait_for_timeout(300)
        self.assertTrue(page.evaluate("!!S.overrides['ig-post'].logo"))
        self.assertEqual(page.locator('.frame-label[data-key="ig-post"] .flag.tw').count(), 1)
        page.evaluate("App.select({key:'feed',id:'cta'})"); page.wait_for_timeout(200)
        page.click('#pane-design [aria-label="Pin top right"]'); page.wait_for_function("S.rules.some(r=>r.type==='pin'&&r.params.role==='cta')")
        page.keyboard.press('Control+k'); page.keyboard.type('hide the offer on small banners'); page.keyboard.press('Enter')
        page.click('#pr-add'); page.wait_for_function("S.rules.some(r=>r.type==='hide_small')")
        self.assertTrue(page.evaluate("display('leaderboard').elements.find(e=>e.id==='offer').hidden"))
        self.assertEqual(self.errors, []); page.close()

    def test_bubbles_frames_drop_and_reopen(self):
        page = self.open()
        page.click('#tab-rules')
        page.evaluate("App.zoomFit()"); page.wait_for_timeout(200)
        bub = page.locator('.bubble:has-text("Pin top-left")').bounding_box()
        t = page.evaluate("App.elBoxClient('ig-story','headline')")
        sx, sy, tx, ty = bub['x'] + 20, bub['y'] + 10, t['x'] + t['w'] / 2, t['y'] + t['h'] / 2
        page.mouse.move(sx, sy); page.mouse.down()
        for i in range(1, 13): page.mouse.move(sx + (tx - sx) * i / 12, sy + (ty - sy) * i / 12)
        page.mouse.up(); page.wait_for_function("S.rules.some(r=>r.type==='pin'&&r.params.role==='headline')")
        page.click('#add-frame-btn'); page.click('.preset[data-key="yt"]'); page.wait_for_function("document.querySelectorAll('.frame').length===7")
        logo = (ROOT / 'previews' / 'v3-home.png').read_bytes()
        page.evaluate("""async (b64)=>{const bin=Uint8Array.from(atob(b64),c=>c.charCodeAt(0));const dt=new DataTransfer();
            dt.items.add(new File([bin],'photo.png',{type:'image/png'}));
            for(const t of ['dragenter','dragover','drop']) window.dispatchEvent(new DragEvent(t,{dataTransfer:dt,clientX:700,clientY:500,bubbles:true,cancelable:true}));}""",
                      base64.b64encode(logo).decode())
        page.wait_for_function("Object.keys(S.assets).length===1")
        page.wait_for_timeout(900)
        page.reload(); page.wait_for_selector('.frame >> nth=6')
        page.wait_for_timeout(500)
        self.assertEqual(page.evaluate("Object.keys(S.assets).length"), 1)
        self.assertTrue(page.evaluate("S.rules.length>=1"))
        self.assertEqual(self.errors, []); page.close()


if __name__ == '__main__':
    unittest.main()
