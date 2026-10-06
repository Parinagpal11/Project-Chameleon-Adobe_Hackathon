def repair_candidate(c):
    d=c['design']; m=min(d.canvas.width,d.canvas.height)*0.04
    for e in d.elements:
        if e.width<=0 or e.height<=0: continue
        e.width=min(e.width,d.canvas.width-2*m); e.height=min(e.height,d.canvas.height-2*m)
        e.x=min(max(m,e.x),max(m,d.canvas.width-e.width-m))
        e.y=min(max(m,e.y),max(m,d.canvas.height-e.height-m))
    c['repaired']=True
    return c
