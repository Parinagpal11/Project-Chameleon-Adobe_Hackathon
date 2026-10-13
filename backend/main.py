"""Optional FastAPI adapter mirroring local_server.py (not integration-tested; the default server is)."""
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from models import ProjectSave
import service

app = FastAPI(title='Chameleon')


@app.on_event('startup')
def warm_up():
    import threading
    from engine import subject
    service.load_saved_results(); subject.load_saved()
    threading.Thread(target=service.warm_up, daemon=True).start()


def run(fn, *args):
    try:
        return fn(*args)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get('/health')
def health(): return {'status': 'ok'}
@app.get('/example')
def example(name: str = 'snow_cabins'):
    if name not in service.TEMPLATES: raise HTTPException(404, 'Unknown template')
    return FileResponse(service.TEMPLATE_DIR / f'{name}.json')
@app.get('/templates')
def templates(): return [{'id': k, **v} for k, v in service.TEMPLATES.items()]
@app.get('/projects')
def projects(x_chameleon_owner: str = Header('')): return service.list_projects(x_chameleon_owner)
@app.get('/project')
def project(campaign: str): return run(service.get_project, campaign)
@app.put('/project')
def save(req: ProjectSave, campaign: str, x_chameleon_owner: str = Header('')): return run(service.save_project, campaign, req, x_chameleon_owner)
@app.delete('/project')
def drop(campaign: str, x_chameleon_owner: str = Header('')): return run(service.delete_project, campaign, x_chameleon_owner)
@app.post('/analyze')
def analyze(data: dict): return run(service.analyze_request, data)
@app.post('/adapt')
def adapt(data: dict): return run(service.adapt_request, data)
@app.post('/convert')
def convert(data: dict): return run(service.convert_request, data)
@app.get('/testset')
def testset():
    from engine.plan import EVAL_SIZES
    return {'designs': service.testset_index(), 'sizes': EVAL_SIZES}
@app.get('/testset/{design_id}')
def testset_design(design_id: str): return run(service.testset_design, design_id)
@app.get('/eval')
def eval_report(): return run(service.eval_report)
@app.get('/report')
def report(): return FileResponse(service.ROOT / 'frontend' / 'eval.html')
@app.get('/xray')
def xray(): return FileResponse(service.ROOT / 'frontend' / 'xray.html')
@app.get('/how')
def how(): return FileResponse(service.ROOT / 'frontend' / 'how.html')


app.mount('/assets', StaticFiles(directory=service.ROOT / 'frontend'), name='assets')


@app.get('/')
def index(): return FileResponse(service.ROOT / 'frontend' / 'index.html')
