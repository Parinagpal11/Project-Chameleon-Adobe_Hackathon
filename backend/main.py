"""Optional FastAPI adapter mirroring local_server.py (not integration-tested; the default server is)."""
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from models import (TransformRequest, BatchRequest, InferRequest, LearnEditRequest, LearnProposalRequest,
                    AddRuleRequest, RulePatch, ParseRuleRequest, ProjectSave)
from engine.intent import infer_any
from engine.rules import parse_text
import service

app = FastAPI(title='Chameleon — Campaign Rule Memory')


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
def example(): return FileResponse(service.ROOT / 'examples' / 'coffee_ad.json')
@app.get('/rules')
def rules(campaign: str = 'coffee-launch'): return run(service.get_rules, campaign)
@app.delete('/rules')
def clear(campaign: str = 'coffee-launch'): return run(service.clear_rules, campaign)
@app.post('/rules')
def add(req: AddRuleRequest): return run(service.add_rule, req.campaign, req.rule.type, req.rule.params, req.rule.label, req.rule.source, req.rule.evidence)
@app.patch('/rules/{rule_id}')
def patch(rule_id: str, req: RulePatch, campaign: str = 'coffee-launch'): return run(service.set_enabled, campaign, rule_id, req.enabled)
@app.delete('/rules/{rule_id}')
def delete(rule_id: str, campaign: str = 'coffee-launch'): return run(service.delete_rule, campaign, rule_id)
@app.post('/transform')
def transform(req: TransformRequest): return run(service.transform, req)
@app.post('/transform-batch')
def batch(req: BatchRequest): return run(service.transform_batch, req)
@app.post('/infer-edit')
def infer(req: InferRequest): return {'proposals': run(infer_any, req.before, req.after, req.moved_id, req.kind)}
@app.post('/learn-edit')
def learn_legacy(req: LearnEditRequest): return run(service.learn_edit, req)
@app.post('/learn')
def learn(req: LearnProposalRequest): return run(service.learn_proposal, req)
@app.post('/parse-rule')
def parse(req: ParseRuleRequest): return parse_text(req.text, req.roles)
@app.get('/projects')
def projects(): return service.list_projects()
@app.get('/project')
def project(campaign: str): return run(service.get_project, campaign)
@app.put('/project')
def save(req: ProjectSave, campaign: str): return run(service.save_project, campaign, req)
@app.delete('/project')
def drop(campaign: str): return run(service.delete_project, campaign)
@app.get('/benchmark')
def benchmark():
    from benchmark import run_benchmark
    return run_benchmark()


app.mount('/assets', StaticFiles(directory=service.ROOT / 'frontend'), name='assets')


@app.get('/')
def index(): return FileResponse(service.ROOT / 'frontend' / 'index.html')
