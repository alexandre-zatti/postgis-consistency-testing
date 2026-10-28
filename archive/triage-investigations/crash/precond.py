import json, collections, shapely, itertools, math
from shapely import wkt
from lib import FORMS, form_of
D=json.load(open("crash_f.json")); R=json.load(open("run1.json"))
def fc(g):
    if g.geom_type=="GeometryCollection": return g
    if g.geom_type.startswith("Multi"): return shapely.GeometryCollection(list(shapely.get_parts(g)))
    return shapely.GeometryCollection([g])
def elems(g):
    """RelatePointLocator.extractElements: polygonal elements (Polygon or MultiPolygon as a whole)"""
    out=[]
    if g.is_empty: return out
    if g.geom_type in ("Polygon","MultiPolygon"): return [g]
    if g.geom_type=="GeometryCollection":
        for p in g.geoms: out+=elems(p)
    return out
def has_empty_poly(g):
    if g.geom_type=="Polygon": return g.is_empty
    if hasattr(g,'geoms'): return any(has_empty_poly(p) for p in g.geoms)
    return False
def rings(g):
    if g.is_empty: return []
    if g.geom_type=="Polygon": return [g.exterior,*g.interiors]
    if hasattr(g,'geoms'): return [r for p in g.geoms for r in rings(p)]
    return []
def shared_bdy(es):
    # any pair of elements whose boundaries meet
    for e1,e2 in itertools.combinations(es,2):
        if shapely.intersects(e1.boundary,e2.boundary): return True
    return False
cnt=collections.Counter(); feat=collections.Counter(); rows={}
for o in D:
    a0,b0=wkt.loads(o['a']),wkt.loads(o['b'])
    rs=rings(a0)+rings(b0)
    rep=any(any(c[i]==c[i+1] for i in range(len(c)-1)) for c in (list(r.coords) for r in rs))
    col=any(shapely.Polygon(r).area==0 for r in rs)
    nring=[len(r.coords) for r in rs]
    feat[(rep,col)]+=1
    for r in R[o['key']]:
        if not str(r['base']).startswith('CRASH') and not str(r.get('relate','')).startswith('CRASH'): continue
        ori,w=FORMS[r['i']]
        x,y=(a0,b0) if ori=="ab" else (b0,a0)
        if w==1: x=fc(x)
        if w==2: y=fc(y)
        ok=[]
        for g in (x,y):
            es=elems(g)
            ok.append((len(es)>=2, has_empty_poly(g), shared_bdy(es) if len(es)>=2 else False))
        cond=any(all(t) for t in ok)
        cnt[cond]+=1
        rows.setdefault(o['key'],[]).append(cond)
print("ring features (repeated pts, zero-area ring):",feat)
print("crashing forms meeting precondition (>=2 polygonal elems + empty polygon + elems' boundaries meet, same geometry):",cnt)
print("findings with all crashing forms meeting it:",sum(all(v) for v in rows.values()),"of",len(rows))
