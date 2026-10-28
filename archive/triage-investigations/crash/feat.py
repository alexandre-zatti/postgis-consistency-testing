import json, re, collections, shapely
from shapely import wkt
D=json.load(open("crash.json"))
def ringfeat(r):
    cs=list(r.coords)
    rep=any(cs[i]==cs[i+1] for i in range(len(cs)-1))
    from shapely.geometry import Polygon
    area=abs(Polygon(cs).area) if len(cs)>=4 else 0
    return rep, area==0, len(cs)
def feats(w):
    g=wkt.loads(w)
    f=dict(emptymember=False, rep=False, collapsed=False, maxabs=0, npoly=0, types=g.geom_type, ncoord=0)
    def walk(x):
        if x.is_empty and x is not g:
            f['emptymember']=True; return
        if hasattr(x,'geoms'):
            for y in x.geoms: walk(y); return
        if x.geom_type=='Polygon':
            f['npoly']+=1
            for r in [x.exterior,*x.interiors]:
                rep,col,n=ringfeat(r); f['rep']|=rep; f['collapsed']|=col
        cs=shapely.get_coordinates(x)
        f['ncoord']+=len(cs)
        if len(cs): f['maxabs']=max(f['maxabs'],float(abs(cs).max()))
    walk(g)
    return f
rows=[]
for o in D:
    fa,fb=feats(o['a']),feats(o['b'])
    o['fa'],o['fb']=fa,fb
    o['empty']= 'EMPTY' in o['a']+o['b']
    o['mag']=max(fa['maxabs'],fb['maxabs'])
json.dump(D,open("crash_f.json","w"),indent=1)
import math
c=collections.Counter()
for o in D:
    c[(o['empty'], o['fa']['rep'] or o['fb']['rep'], o['fa']['collapsed'] or o['fb']['collapsed'], int(math.log10(o['mag'])) if o['mag']>0 else -1)]+=1
for k,v in sorted(c.items()): print(k,v)
