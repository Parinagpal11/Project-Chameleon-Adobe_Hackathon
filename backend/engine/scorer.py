def _rect(e): return (e.x,e.y,e.x+e.width,e.y+e.height)
def _overlap(a,b):
    ax1,ay1,ax2,ay2=_rect(a); bx1,by1,bx2,by2=_rect(b)
    return max(0,min(ax2,bx2)-max(ax1,bx1))*max(0,min(ay2,by2)-max(ay1,by1))

def score_candidate(c):
    d=c['design']; score=100.0; violations=[]
    visible=[e for e in d.elements if e.width>0 and e.height>0]
    for e in visible:
        if e.x<0 or e.y<0 or e.x+e.width>d.canvas.width or e.y+e.height>d.canvas.height:
            score-=25; violations.append({'type':'OUT_OF_BOUNDS','element':e.id})
        if e.type in ('text','button','logo') and e.fontSize and e.fontSize<12:
            score-=12; violations.append({'type':'TEXT_TOO_SMALL','element':e.id})
    critical=[e for e in visible if e.genome and e.genome.importance>=0.7 and e.type!='image']
    for i in range(len(critical)):
        for j in range(i+1,len(critical)):
            ov=_overlap(critical[i],critical[j])
            if ov>0:
                score-=min(30,ov/3000); violations.append({'type':'OVERLAP','elements':[critical[i].id,critical[j].id]})
    c['score']=round(max(0,min(100,score)),1); c['violations']=violations
    return c
