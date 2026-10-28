import sys
sys.path.insert(0,r'C:/Users/Ale/AppData/Local/Temp/predicate-families')
from exact import *
import shapely
from shapely import wkt
x=wkt.loads('POLYGON ((699313.1 244162.7, 699370.8 244179.0, 699315.8 244199.1, 699305.1 244184.1, 699313.1 244162.7))')
y=wkt.loads('POLYGON ((699317.1 244195.2, 699309.1 244173.4, 699351.3 244184.3, 699317.1 244195.2))')
SA=segs(rings(x))
for p in rings(y)[0][:-1]:
    loc=locate(p,SA)
    # distance-ish to nearest segment via orientation/length
    best=min(((abs(orient(a,b,p))/((b[0]-a[0])**2+(b[1]-a[1])**2)**F(1,2) if False else abs(float(orient(a,b,p)))/(float((b[0]-a[0])**2+(b[1]-a[1])**2)**0.5)),(a,b)) for a,b in SA)
    print([float(c) for c in p],loc,'min dist to A edge %.3e'%best[0])
print('shapely dist', [shapely.distance(shapely.Point(c),x.exterior) for c in y.exterior.coords[:-1]])
print(shapely.relate(x,y), shapely.difference(y,x).area, shapely.contains_properly(x,y))
