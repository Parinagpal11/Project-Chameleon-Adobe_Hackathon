from models import Design, Genome, Relationship

ROLE_IMPORTANCE = {
    'headline': 1.00, 'hero': 0.95, 'cta': 0.90, 'logo': 0.88,
    'offer': 0.82, 'subtitle': 0.70, 'body': 0.55, 'decoration': 0.20,
}

def infer_role(el):
    if el.genome: return el.genome.role
    if el.type == 'logo': return 'logo'
    if el.type == 'button': return 'cta'
    if el.type == 'image': return 'hero'
    if el.type == 'decoration': return 'decoration'
    if el.type == 'text':
        fs = el.fontSize or 16
        if fs >= 48: return 'headline'
        if fs >= 28: return 'subtitle'
        return 'body'
    return 'body'

def enrich_design(design: Design) -> Design:
    for el in design.elements:
        role = infer_role(el)
        if not el.genome:
            el.genome = Genome(role=role, importance=ROLE_IMPORTANCE.get(role,0.5),
                               removable=(role=='decoration'), scalable=True,
                               reflow=(el.type=='text'), relationships=[])
    ids = {e.genome.role: e.id for e in design.elements if e.genome}
    if 'headline' in ids and 'subtitle' in ids:
        _add_rel(design, ids['headline'], ids['subtitle'], 'ABOVE')
    if 'offer' in ids and 'cta' in ids:
        _add_rel(design, ids['offer'], ids['cta'], 'ABOVE')
    if 'hero' in ids and 'headline' in ids:
        _add_rel(design, ids['headline'], ids['hero'], 'ASSOCIATED_WITH')
    return design

def _add_rel(design, source, target, typ):
    el = next((e for e in design.elements if e.id == source), None)
    if el and el.genome and not any(r.target==target and r.type==typ for r in el.genome.relationships):
        el.genome.relationships.append(Relationship(source=source,target=target,type=typ,strength=0.9))
