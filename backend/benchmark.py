"""Reproducible synthetic benchmark, 24 designs × four held-out target formats.
Training edits use a 1080×1920 Story. No target layout is used to infer rules.
Naive scaling preserves geometry; do not claim it introduces overlap in clean inputs.
"""
import json,random
from pathlib import Path
from models import Design,Canvas
from engine.genome import enrich_design
from engine.intent import infer_edit,bind_rules
from service import compile_design,evaluate,naive_resize
TARGETS=[('square',1080,1080),('landscape',1200,628),('ultrawide',1584,396),('mobile',320,480)]

def corpus():
    rng=random.Random(42)
    base=json.loads((Path(__file__).resolve().parent.parent/'examples/coffee_ad.json').read_text())
    items=[]
    for i in range(24):
        d=Design.model_validate(base)
        for e in d.elements:
            e.id=f'design{i}_{e.id}'
            if e.type=='text' and e.text:e.text += ['',' TODAY',' • LIMITED EDITION'][i%3]
            if e.genome.role=='headline':e.fontSize=48+rng.randrange(32)
        # Two source orderings, two intentional designer preferences: avoid a benchmark
        # that simply rewards a hard-coded conventional CTA order.
        byrole={e.genome.role:e for e in d.elements}
        if i%2:byrole['cta'].y,byrole['offer'].y=byrole['offer'].y,byrole['cta'].y
        if i%4==0:
            from models import Element,Genome
            d.elements.append(Element(id=f'design{i}_legal',type='text',x=90,y=970,width=900,height=35,text='Terms apply. Offer ends 30 September.',fontSize=18,genome=Genome(role='legal',importance=.8,removable=False)))
        # Vary source dimensions with a geometry-preserving rescale.
        d=naive_resize(d,Canvas(width=[1080,1200,1440][i%3],height=[1080,1600][i%2]))
        items.append(enrich_design(d))
    return items

def run_benchmark():
    totals={name:{} for name in ('naive','chameleon_no_memory','chameleon_memory')};rows=[]
    for i,d in enumerate(corpus()):
        _,training,_,_=compile_design(d,Canvas(width=1080,height=1920),[])
        before=training[0]['design'];after=before.model_copy(deep=True)
        roles={e.genome.role:e for e in after.elements};cta=roles['cta'];offer=roles['offer']
        # Demonstrate a changed ordering with one position edit.
        # The lower of the two moves up above the other (always fits inside the canvas).
        desired='BELOW' if cta.y<offer.y else 'ABOVE'
        mover,anchor=(offer,cta) if desired=='BELOW' else (cta,offer)
        mover.y=anchor.y-mover.height-4
        proposals=infer_edit(before,after,mover.id)
        rule=next(p for p in proposals if p['target_role']==anchor.genome.role and p['relation']=='ABOVE')
        # Change element IDs after teaching to test semantic, rather than ID-based transfer.
        unseen=d.model_copy(deep=True)
        for e in unseen.elements:e.id='unseen_'+e.id
        bound,_=bind_rules(unseen,[rule])
        for label,w,h in TARGETS:
            target=Canvas(width=w,height=h)
            _,unlearned,_,_=compile_design(unseen,target,[])
            _,learned,_,_=compile_design(unseen,target,[rule])
            arms={'naive':evaluate(naive_resize(unseen,target),unseen,bound),
                  'chameleon_no_memory':evaluate(unlearned[0]['design'],unseen,bound),
                  'chameleon_memory':evaluate(learned[0]['design'],unseen,bound)}
            for name,c in arms.items():
                for key,value in c['metrics'].items():totals[name][key]=totals[name].get(key,0)+value
            rows.append({'design':i,'format':label,'learned_relation':desired,'metrics':{name:c['metrics'] for name,c in arms.items()}})
    return {'dataset':'Synthetic variations of the included coffee campaign; not independent professional designs.',
            'seed':42,'designs':24,'formats':4,'cases':96,'training_format':'1080×1920 Story',
            'held_out_formats':[label for label,_,_ in TARGETS],
            'method':'One inferred ordering edit per design. Three arms scored against identical intent. IDs change before transfer. No target-format corrections.',
            'limitations':['Synthetic, related designs limit generalization.','Geometric scaling does not create overlaps or out-of-bounds from clean inputs.','Scores and text-fit checks are heuristic; no human aesthetic evaluation.','Only ABOVE/BELOW semantic ordering is learned.'],
            'totals':totals,'rows':rows}
if __name__=='__main__':print(json.dumps(run_benchmark(),indent=2))
