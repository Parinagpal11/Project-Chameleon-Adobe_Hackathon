"""Local HTTP adapter. Requires Pydantic; no FastAPI/Uvicorn dependency."""
import json, mimetypes, argparse, os
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote
from pydantic import ValidationError
from models import (TransformRequest, BatchRequest, InferRequest, LearnEditRequest, LearnProposalRequest,
                    AddRuleRequest, RulePatch, ParseRuleRequest, ProjectSave)
from engine.intent import infer_edit, infer_any
from engine.rules import parse_text
from engine.understand import analyze
from engine.plan import EVAL_SIZES
import service

MAX_BODY = 15_000_000


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

    def send(self, status, body, kind='application/json'):
        if not isinstance(body, bytes):
            body = json.dumps(body).encode()
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def body(self):
        size = int(self.headers.get('Content-Length', '0'))
        if size < 1 or size > MAX_BODY:
            raise ValueError('Request must be between 1 byte and 15 MB.')
        return json.loads(self.rfile.read(size))

    def dispatch(self):
        path = urlparse(self.path)
        q = parse_qs(path.query)
        campaign = q.get('campaign', ['coffee-launch'])[0]
        p, m = path.path, self.command
        try:
            if m == 'GET':
                if p == '/health': return self.send(200, {'status': 'ok'})
                if p == '/rules': return self.send(200, service.get_rules(campaign))
                if p == '/projects': return self.send(200, service.list_projects())
                if p == '/project': return self.send(200, service.get_project(campaign))
                if p == '/benchmark':
                    from benchmark import run_benchmark
                    return self.send(200, run_benchmark())
                if p == '/testset': return self.send(200, {'designs': service.testset_index(), 'sizes': EVAL_SIZES})
                if p.startswith('/testset/'): return self.send(200, service.testset_design(p[9:]))
                if p == '/eval': return self.send(200, service.eval_report())
                if p == '/': file = service.ROOT / 'frontend' / 'index.html'
                elif p == '/xray': file = service.ROOT / 'frontend' / 'xray.html'
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
                return self.send(200, file.read_bytes(), kind)
            if m == 'DELETE':
                if p == '/rules': return self.send(200, service.clear_rules(campaign))
                if p.startswith('/rules/'): return self.send(200, service.delete_rule(campaign, p[7:]))
                if p == '/project': return self.send(200, service.delete_project(campaign))
            if m == 'PATCH' and p.startswith('/rules/'):
                return self.send(200, service.set_enabled(campaign, p[7:], RulePatch.model_validate(self.body()).enabled))
            if m == 'PUT' and p == '/project':
                return self.send(200, service.save_project(campaign, ProjectSave.model_validate(self.body())))
            if m == 'POST':
                data = self.body()
                if p == '/transform': result = service.transform(TransformRequest.model_validate(data))
                elif p == '/transform-batch': result = service.transform_batch(BatchRequest.model_validate(data))
                elif p == '/infer-edit':
                    req = InferRequest.model_validate(data)
                    result = {'proposals': infer_any(req.before, req.after, req.moved_id, req.kind)}
                elif p == '/learn-edit': result = service.learn_edit(LearnEditRequest.model_validate(data))
                elif p == '/learn': result = service.learn_proposal(LearnProposalRequest.model_validate(data))
                elif p == '/rules':
                    req = AddRuleRequest.model_validate(data)
                    r = req.rule
                    result = service.add_rule(req.campaign, r.type, r.params, r.label, r.source, r.evidence)
                elif p == '/analyze':
                    result = service.analyze_request(data)
                elif p == '/adapt':
                    result = service.adapt_request(data)
                elif p == '/convert':
                    result = service.convert_request(data)
                elif p == '/parse-rule':
                    req = ParseRuleRequest.model_validate(data)
                    result = parse_text(req.text, req.roles)
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

    do_GET = do_POST = do_DELETE = do_PATCH = do_PUT = dispatch


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=int(os.environ.get('PORT', 8000)))
    parser.add_argument('--host', default=os.environ.get('HOST', '127.0.0.1'))
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f'Chameleon running at http://{"127.0.0.1" if args.host in ("0.0.0.0", "") else args.host}:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
