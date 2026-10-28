import json, collections, shapely, itertools
from shapely import wkt
from lib import FORMS
exec(open("precond.py").read().split("cnt=collections.Counter()")[0])
D=json.load(open("crash_f.json"))
import re
def idx(p):
    from lib import form_of; return form_of(p)
cnt=collections.Counter(); kinds=collections.Counter(); ex=[]
for o in D:
    a0,b0=wkt.loads(o['a']),wkt.loads(o['b'])
    crash_i={idx(p) for p in o['cur']}
    allprobes=json.load(open(r"C:/Users/Ale/masters/coursework/MCET063 - Tópicos em Testes Automatizados e Verificação de Software (2026-2)/final-project/experiment/runs/e3/triage/reruns/%s.json"%o['key'],encoding='utf-8'))['images']['current']['probes']
    for p in allprobes:
        i=idx(p['probe'])
        if i in crash_i: continue
        ori,w=FORMS[i]
        x,y=(a0,b0) if ori=="ab" else (b0,a0)
        if w==1: x=fc(x)
        if w==2: y=fc(y)
        cond=any(len(elems(g))>=2 and has_empty_poly(g) and shared_bdy(elems(g)) for g in (x,y))
        cnt[(o['fn'],cond)]+=1
        if cond and len(ex)<6: ex.append((o['key'],p['probe']))
    # kind of shared boundary contact: shared vertex vs vertex-on-edge
    for g in (a0,b0, fc(a0), fc(b0)):
        es=elems(g)
        if len(es)>=2 and has_empty_poly(g):
            for e1,e2 in itertools.combinations(es,2):
                inter=shapely.intersection(e1.boundary,e2.boundary)
                if inter.is_empty: continue
                v1={tuple(c) for c in shapely.get_coordinates(e1)}; v2={tuple(c) for c in shapely.get_coordinates(e2)}
                pts={tuple(c) for c in shapely.get_coordinates(inter)}
                kinds[(inter.geom_type, all(p in v1 and p in v2 for p in pts))]+=1
            break
print("non-crashing PostGIS forms meeting the precondition:"); [print(' ',k,v) for k,v in sorted(cnt.items())]
print(ex)
print("boundary contact kinds (type, all contact points are shared vertices):",kinds)
