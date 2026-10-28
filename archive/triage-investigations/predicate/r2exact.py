import sys
sys.path.insert(0,r'C:/Users/Ale/AppData/Local/Temp/predicate-families')
from exact import *
from shapely import wkt
# dbd61987613e : locations of b's boundary pieces w.r.t. a
a=wkt.loads('MULTIPOLYGON (((946359.0 598507.0, 946375.0 598527.0, 946363.0 598534.0, 946359.0 598507.0)))')
b=wkt.loads('POLYGON ((946377.3485289358 598545.0969941012, 946377.3485289357 598545.0969941012, 946368.397825941 598530.1008307285, 946377.3485289358 598545.0969941012))')
SA=segs(rings(a)); SB=segs(rings(b))
print('dbd b-boundary pieces in a:', ''.join(sorted(set(pieces_locs(SB,SA)[0]))), 'b vertices:', [locate(p,SA) for p in rings(b)[0][:-1]])
# 5eb8d91024c7: is the line collinear with the hole edge?
P=lambda x,y:(F(x),F(y))
h0,h1=P(898674.5,890139.2),P(898677.1,890137.4); l0,l1=P(898677.1,890137.4),P(898671.9,890141.0)
print('5eb8 orient(hole edge, line end)=',float(orient(h0,h1,l1)), 'orient(line, hole vertex 898674.5 890139.2)=',float(orient(l0,l1,h0)))
# 7d21957b5d7f: line vs polygon-with-hole edges
L=[P(6327538755459650.0,5256115596080508.0),P(6327538755459648.0,5256115596080502.0)]
g=wkt.loads('POLYGON ((6327538755459650.0 5256115596080502.0, 6327538755459648.0 5256115596080504.0, 6327538755459643.0 5256115596080500.0, 6327538755459650.0 5256115596080502.0), (6327538755459648.0 5256115596080504.0, 6327538755459648.0 5256115596080502.0, 6327538755459647.0 5256115596080503.0, 6327538755459648.0 5256115596080504.0))')
for s in segs(rings(g)):
    o1,o2=orient(s[0],s[1],L[0]),orient(s[0],s[1],L[1])
    if o1==0 and o2==0: print('7d21 line collinear with edge',[(float(x),float(y)) for x,y in s])
print('7d21 line pieces in poly:', pieces_locs([tuple(L)],segs(rings(g)))[0])
print('5eb8 line pieces in poly:', pieces_locs([(l0,l1)],segs(rings(wkt.loads('POLYGON ((898678.2 890144.4, 898674.5 890139.2, 898681.3 890126.8, 898678.2 890144.4), (898674.5 890139.2, 898677.1 890137.4, 898676.3 890136.8, 898674.5 890139.2))'))))[0])
