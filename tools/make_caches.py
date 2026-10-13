"""Save what a small host would otherwise compute on its first visits.

1. examples/subjects-cache.json: what photo detection finds in every bundled photo (templates and test set),
   so the photo models never run for them on the server.
2. examples/results-cache.json: the engine's answers to the exact requests the bundled pages make (the home
   demo, each template opened in the Studio, the guided tour, How it works, the Engine room). It is recorded
   by driving those pages in a headless browser (needs Playwright).
3. examples/eval-report.json: the test-set report (same as tools/make_eval_report.py).

Each file carries a fingerprint of the engine; the server ignores a file made by a different engine.
Re-run after changing the engine, the templates or the test set.

Run:  python tools/make_caches.py
"""
import hashlib
import json
import os
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
os.environ['CHAMELEON_RECORD'] = '1'
os.environ.setdefault('CHAMELEON_QUIET', '1')
os.environ['CHAMELEON_DB'] = str(ROOT / 'data' / 'cache-run.sqlite3')

import service  # noqa: E402
from engine import subject  # noqa: E402
from engine.graph import load  # noqa: E402


def photos():
    for f in sorted(list(service.TEMPLATE_DIR.glob('*.json')) + list(service.TESTSET.glob('*.json'))):
        if f.name == 'index.json':
            continue
        d = json.loads(f.read_text())
        if 'nodes' not in d:
            continue
        for n in load(d).leaves():
            if n.type == 'image' and n.src:
                yield n.src


def save_subjects():
    items = {}
    for src in photos():
        key = hashlib.sha1(src.encode('utf-8', 'ignore')).hexdigest()
        if key not in items:
            items[key] = subject._detect(src)
    subject.SAVED_FILE.write_text(json.dumps({'stamp': subject._stamp(), 'items': items},
                                             separators=(',', ':'), default=lambda o: o.item() if hasattr(o, 'item') else str(o)))
    subject._saved.clear()
    subject.load_saved()
    print(f'{len(items)} photo readings saved')


def record_pages():
    from playwright.sync_api import sync_playwright
    from local_server import ThreadingHTTPServer, Handler
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{server.server_port}'
    ready = "document.querySelectorAll('.frame canvas').length >= 6 && !document.body.classList.contains('is-busy')"
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(viewport={'width': 1440, 'height': 900})
            pg.goto(base + '/')
            pg.evaluate("localStorage.setItem('chameleon.tour.v3', '1')")
            pg.reload()
            pg.wait_for_function("document.querySelectorAll('#home-demo .rd-slide').length >= 5", timeout=180000)
            pg.evaluate("document.getElementById('home').scrollTop = 99999")
            pg.wait_for_function("document.querySelector('[data-k=intent] canvas')", timeout=180000)
            for t in service.TEMPLATES:                     # each template opened in the Studio
                pg.goto(base + '/')
                pg.evaluate(f"startTemplate('{t}')")
                pg.wait_for_function(ready, timeout=180000)
            pg.goto(base + '/')                              # the guided tour on the sample (it marks a focus area)
            pg.evaluate("startTemplate('snow_cabins')")
            pg.wait_for_function(ready, timeout=180000)
            pg.evaluate("App.startTour(0)")
            for _ in range(len(pg.evaluate("App.TOUR_STEPS.map(s => s.title)"))):
                pg.wait_for_function("!document.getElementById('tour-next').disabled", timeout=180000)
                pg.click('#tour-next')
            pg.wait_for_function(ready, timeout=180000)
            pg.goto(base + '/how')                           # How it works, for every template in its picker
            pg.wait_for_selector('#score-table .bar', timeout=180000)
            for v in pg.evaluate("[...document.querySelectorAll('#how-design option')].map(o => o.value)"):
                pg.select_option('#how-design', v)
                pg.wait_for_timeout(300)
                pg.wait_for_function("!document.body.classList.contains('loading') && document.querySelector('#score-table .bar')", timeout=180000)
            pg.goto(base + '/xray')                          # the Engine room's first design
            pg.wait_for_selector('.xr-group', timeout=180000)
            b.close()
    finally:
        server.shutdown()
    results = dict(service._RECORD)
    service.SAVED_RESULTS_FILE.write_text(json.dumps({'stamp': service.engine_stamp(), 'results': results}, separators=(',', ':')))
    print(f'{len(results)} answers saved ({service.SAVED_RESULTS_FILE.stat().st_size // 1024} KB)')


def save_report():
    service._EVAL_CACHE.clear()
    if service.EVAL_FILE.exists():
        service.EVAL_FILE.unlink()
    report = service.eval_report()
    service.EVAL_FILE.write_text(json.dumps({'stamp': service._eval_stamp(), 'report': report}, separators=(',', ':')))
    print(f"report saved: {report['cases']} cases, Chameleon {report['summary']['chameleon']['overall']}")


if __name__ == '__main__':
    save_subjects()
    record_pages()
    save_report()
    try:
        Path(os.environ['CHAMELEON_DB']).unlink()
    except OSError:
        pass
