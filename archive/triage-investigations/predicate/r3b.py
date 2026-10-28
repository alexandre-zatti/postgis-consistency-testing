import sys,json,collections
import shapely
from shapely import wkt
j=json.load(open(sys.argv[1]+'/findings.json',encoding='utf-8'))
def prep(g):
    g=shapely.from_wkb(shapely.to_wkb(g)); shapely.prepare(g); return g
out=collections.Counter(); ex={}
for e in j['findings']:
    if e['rule']!='R3': continue
    if not('EMPTY' in e['a'] or 'EMPTY' in e['b']): continue
    A=wkt.loads(e['a']); B=wkt.loads(e['b'])
    o=e['orientation']; x,y=(A,B) if o=='ab' else (B,A)
    if e['function']=='Within': P,G=y,x   # within(x,y) == contains(y,x), prepared y
    else: P,G=x,y
    pts=shapely.get_parts(G); 
    nonempty=shapely.GeometryCollection([p for p in pts if not p.is_empty])
    pt_only = shapely.MultiPoint([p for p in pts if not p.is_empty]) if len([p for p in pts if not p.is_empty])>1 else [p for p in pts if not p.is_empty][0]
    res=dict(
      lone=bool(shapely.contains(P,G)), prep=bool(shapely.contains(prep(P),G)),
      gc_noempty_lone=bool(shapely.contains(P,nonempty)), gc_noempty_prep=bool(shapely.contains(prep(P),nonempty)),
      pt_lone=bool(shapely.contains(P,pt_only)), pt_prep=bool(shapely.contains(prep(P),pt_only)),
      covers_lone=bool(shapely.covers(P,G)), covers_prep=bool(shapely.covers(prep(P),G)),
      rel=shapely.relate(P,G), ptrel=shapely.relate(P,pt_only),
      emptytype=[p.geom_type for p in pts if p.is_empty][0], dimG=shapely.get_dimensions(G))
    k=tuple(sorted((a,b) for a,b in res.items()))
    out[k]+=1; ex.setdefault(k,e['key_id'])
for k,n in out.items(): print(n,ex[k],dict(k))
