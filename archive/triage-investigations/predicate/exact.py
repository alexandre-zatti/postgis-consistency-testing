# Exact rational evaluation of Covers/Contains(A,B) for polygonal A, polygonal or lineal B.
from fractions import Fraction as F
import shapely
def rings(g):
    out=[]
    for p in shapely.get_parts(g):
        if p.is_empty: continue
        if p.geom_type=='Polygon':
            out.append(list(p.exterior.coords)); out += [list(r.coords) for r in p.interiors]
        else: out.append(list(p.coords))
    return [[(F(x),F(y)) for x,y,*_ in r] for r in out]
def segs(rs):
    return [(r[i],r[i+1]) for r in rs for i in range(len(r)-1) if r[i]!=r[i+1]]
def orient(a,b,c): return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
def onseg(p,a,b):
    return orient(a,b,p)==0 and min(a[0],b[0])<=p[0]<=max(a[0],b[0]) and min(a[1],b[1])<=p[1]<=max(a[1],b[1])
def locate(p,S):  # S = segments of polygonal boundary; 'B','I','E' via even-odd
    for a,b in S:
        if onseg(p,a,b): return 'B'
    c=0
    for a,b in S:
        if (a[1]>p[1])!=(b[1]>p[1]):
            x=a[0]+(p[1]-a[1])*(b[0]-a[0])/(b[1]-a[1])
            if x>p[0]: c+=1
    return 'I' if c%2 else 'E'
def params(a,b,S):
    ts={F(0),F(1)}; proper=False
    d=(b[0]-a[0],b[1]-a[1])
    for c,e in S:
        o1,o2=orient(c,e,a),orient(c,e,b); o3,o4=orient(a,b,c),orient(a,b,e)
        if o1==0 and o2==0:
            dd=d[0]*d[0]+d[1]*d[1]
            for q in (c,e):
                t=((q[0]-a[0])*d[0]+(q[1]-a[1])*d[1])/dd
                if 0<t<1: ts.add(t)
            continue
        if (o1>0)!=(o2>0) or o1==0 or o2==0:
            if ((o3>0)!=(o4>0) or o3==0 or o4==0) and not (o1*o2>0) and not (o3*o4>0):
                den=o1-o2
                t=o1/den
                if 0<=t<=1: ts.add(t)
                if o1!=0 and o2!=0 and o3!=0 and o4!=0: proper=True
    return sorted(ts),proper
def pieces_locs(SB,SA):
    locs=[];prop=False
    for a,b in SB:
        ts,p=params(a,b,SA); prop|=p
        for t in ts: locs.append(locate((a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1])),SA))
        for t0,t1 in zip(ts,ts[1:]):
            t=(t0+t1)/2; locs.append(locate((a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1])),SA))
    return locs,prop
def exact(A,B):
    SA=segs(rings(A)); SB=segs(rings(B))
    lb,propB=pieces_locs(SB,SA)
    covers = 'E' not in lb
    res={'B_boundary_locs_in_A':''.join(sorted(set(lb))),'proper_crossings':propB}
    if shapely.get_dimensions(B)==2:
        la,_=pieces_locs(SA,SB)   # A boundary pieces located w.r.t. B
        res['A_boundary_locs_in_B']=''.join(sorted(set(la)))
        covers = covers and 'I' not in la
        contains=covers
    else:
        contains = covers and 'I' in lb
    res['covers']=covers; res['contains']=contains
    return res
