"""Local HTTP adapter. Requires Pydantic; no FastAPI/Uvicorn dependency."""
import json, mimetypes, argparse, os, gzip
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote
from pydantic import ValidationError
from models import ProjectSave
from engine.plan import EVAL_SIZES
import service

MAX_BODY = 15_000_000


def _plain(o):
    """numpy numbers (from the image code) as plain JSON numbers."""
    if hasattr(o, 'item'):
        return o.item()
    raise TypeError(f'{type(o).__name__} is not JSON serializable')


def _error_text(exc):
    if isinstance(exc, ValidationError):
        first = exc.errors()[0]
        where = '.'.join(str(x) for x in first.get('loc', ()))
        return f"Invalid {where or 'request'}: {first.get('msg')}"
    return str(exc)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        if os.environ.get('CHAMELEON_QUIET'):
            return
        super().log_message(fmt, *args)

    def send(self, status, body, kind='application/json', cache='no-store'):
        if not isinstance(body, bytes):
            body = json.dumps(body, separators=(',', ':'), default=_plain).encode()
        if len(body) > 1400 and 'gzip' in self.headers.get('Accept-Encoding', '') and not kind.startswith(('font/', 'image/')):
            body = gzip.compress(body, 5)
            self.send_response(status)
            self.send_header('Content-Encoding', 'gzip')
            self.send_header('Vary', 'Accept-Encoding')
        else:
            self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', cache)
        self.end_headers()
        if self.command != 'HEAD':      # HEAD gets the headers, never the body
            self.wfile.write(body)

    def body(self):
        size = int(self.headers.get('Content-Length', '0'))
        if size < 1 or size > MAX_BODY:
            raise ValueError('Request must be between 1 byte and 15 MB.')
        return json.loads(self.rfile.read(size))

    def dispatch(self):
        path = urlparse(self.path)
        q = parse_qs(path.query)
        campaign = q.get('campaign', [''])[0]
        owner = self.headers.get('X-Chameleon-Owner', '')
        p = path.path
        m = 'GET' if self.command == 'HEAD' else self.command   # HEAD reads like GET, minus the body
        try:
            if m == 'GET':
                if p == '/health': return self.send(200, {'status': 'ok'})
                if p == '/projects': return self.send(200, service.list_projects(owner))
                if p == '/project': return self.send(200, service.get_project(campaign))
                if p == '/testset': return self.send(200, {'designs': service.testset_index(), 'sizes': EVAL_SIZES})
                if p.startswith('/testset/'): return self.send(200, service.testset_design(p[9:]))
                if p == '/eval': return self.send(200, service.eval_report())
                if p == '/': file = service.ROOT / 'frontend' / 'index.html'
                elif p == '/xray': file = service.ROOT / 'frontend' / 'xray.html'
                elif p == '/how': file = service.ROOT / 'frontend' / 'how.html'
                elif p in ('/report', '/eval/report'): file = service.ROOT / 'frontend' / 'eval.html'
                elif p == '/example':
                    name = q.get('name', [next(iter(service.TEMPLATES), '')])[0]
                    if name not in service.TEMPLATES: return self.send(404, {'detail': 'Unknown template'})
                    file = service.TEMPLATE_DIR / f'{name}.json'
                elif p == '/templates': return self.send(200, [{'id': k, **v} for k, v in service.TEMPLATES.items()])
                elif p.startswith('/assets/'):
                    base = (service.ROOT / 'frontend').resolve()
                    file = (base / unquote(p[8:])).resolve()
                    if not file.is_relative_to(base): return self.send(403, {'detail': 'Forbidden'})
                else: return self.send(404, {'detail': 'Not found'})
                if not file.is_file(): return self.send(404, {'detail': 'Not found'})
                kind = mimetypes.guess_type(file.name)[0] or 'application/octet-stream'
                if kind.startswith('text/') or kind.endswith('javascript'): kind += '; charset=utf-8'
                # fonts never change; pages, scripts and templates are re-checked so an update shows at once
                return self.send(200, file.read_bytes(), kind, 'public, max-age=31536000, immutable' if file.suffix == '.woff2' else 'no-cache')
            if m == 'DELETE':
                if p == '/project': return self.send(200, service.delete_project(campaign, owner))
            if m == 'PUT' and p == '/project':
                return self.send(200, service.save_project(campaign, ProjectSave.model_validate(self.body()), owner))
            if m == 'POST':
                data = self.body()
                if p == '/analyze':
                    result = service.analyze_request(data)
                elif p == '/adapt':
                    result = service.adapt_request(data)
                elif p == '/convert':
                    result = service.convert_request(data)
                else: return self.send(404, {'detail': 'Not found'})
                return self.send(200, result)
            self.send(405, {'detail': 'Method not allowed'})
        except LookupError as exc:
            self.send(404, {'detail': str(exc)})
        except (ValueError, ValidationError) as exc:
            self.send(400, {'detail': _error_text(exc)})
        except Exception:
            import traceback; traceback.print_exc()
            self.send(500, {'detail': 'Unexpected server error; inspect terminal.'})

    do_GET = do_HEAD = do_POST = do_DELETE = do_PUT = dispatch


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=int(os.environ.get('PORT', 8000)))
    parser.add_argument('--host', default=os.environ.get('HOST', '127.0.0.1'))
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    from engine import subject
    service.load_saved_results(); subject.load_saved()       # saved answers and photo readings, ready at once
    import threading; threading.Thread(target=service.warm_up, daemon=True).start()
    print(f'Chameleon running at http://{"127.0.0.1" if args.host in ("0.0.0.0", "") else args.host}:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
