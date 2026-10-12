"""Save the test-set report (GET /eval, the /report page) so a fresh or slow server answers at once.

The saved report carries a fingerprint of the test set and the engine; the server only uses it while that
fingerprint still matches, and otherwise computes a new one. Re-run after changing the engine or the test set.

Run:  python tools/make_eval_report.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import service  # noqa: E402

if __name__ == '__main__':
    service._EVAL_CACHE.clear()
    if service.EVAL_FILE.exists():
        service.EVAL_FILE.unlink()
    report = service.eval_report()
    service.EVAL_FILE.write_text(json.dumps({'stamp': service._eval_stamp(), 'report': report}, separators=(',', ':')))
    s = report['summary']
    print(f"{report['cases']} cases · Chameleon {s['chameleon']['overall']} · crop {s['crop']['overall']} · "
          f"stretch {s['stretch']['overall']} · letterbox {s['letterbox']['overall']} · "
          f"wins {report['wins']} ties {report['ties']} losses {report['losses']} · checks ok {report['checks_ok']}")
