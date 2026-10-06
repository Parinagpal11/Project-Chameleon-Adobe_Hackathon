"""Start the local Chameleon app from the project folder.

    python run.py              # restarts itself when backend code changes (development)
    python run.py --no-reload  # plain single process (demos, hosting)

Other options (--port, --host) are passed to the server.
"""
import os
import runpy
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / 'backend'


def serve():
    sys.path.insert(0, str(BACKEND))
    runpy.run_path(str(BACKEND / 'local_server.py'), run_name='__main__')


def snapshot():
    return {p: p.stat().st_mtime for p in BACKEND.rglob('*.py')}


def watch(args):
    """Run the server in a child process; restart it when any backend .py file changes."""
    env = dict(os.environ, CHAMELEON_CHILD='1')
    while True:
        child = subprocess.Popen([sys.executable, __file__, '--no-reload', *args], env=env)
        seen = snapshot()
        try:
            while child.poll() is None:
                time.sleep(1)
                if snapshot() != seen:
                    print('\nBackend code changed, restarting…', flush=True)
                    child.terminate()
                    try:
                        child.wait(5)
                    except subprocess.TimeoutExpired:
                        child.kill()
                    break
            else:
                return child.returncode   # the server stopped on its own (e.g. port in use)
        except KeyboardInterrupt:
            child.terminate()
            return 0


if __name__ == '__main__':
    args = sys.argv[1:]
    if '--no-reload' in args:
        sys.argv = [sys.argv[0]] + [a for a in args if a != '--no-reload']
        serve()
    else:
        sys.exit(watch(args) or 0)
