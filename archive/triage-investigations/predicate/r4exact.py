import sys,json
sys.path.insert(0,r'C:/Users/Ale/AppData/Local/Temp/predicate-families')
from exact import *
import shapely; from shapely import wkt
j=json.load(open(sys.argv[1]+'/findings.json',encoding='utf-8'))
def overlap_dim(G1,G2):
    S1=segs(rings(G1)); S2=segs(rings(G2)); best=-1; near=[]
    for a,b in S1:
        for c,d in S2:
            o1,o2=orient(a,b,c),orient(a,b,d)
            L=float(((b[0]-a[0])**2+(b[1]-a[1])**2))**0.5
            if o1==0 and o2==0:
                dd=(b[0]-a[0])**2+(b[1]-a[1])**2
                t=sorted([((q[0]-a[0])*(b[0]-a[0])+(q[1]-a[1])*(b[1]-a[1]))/dd for q in (c,d)])
                if max(t[0],0)<min(t[1],1): best=1
            elif min(abs(float(o1)),abs(float(o2)))/L<1e-6:
                near.append(('near-collinear dist %.2e'%(min(abs(float(o1)),abs(float(o2)))/L)))
    return best,near[:3]
for e in j['findings']:
    if e['rule']!='R4': continue
    A=wkt.loads(e['a']); B=wkt.loads(e['b'])
    print(e['key_id'],'exact 1-dim boundary overlap:',overlap_dim(A,B))
