import sys,json
import shapely; from shapely import wkt
j=json.load(open(sys.argv[1]+'/findings.json',encoding='utf-8'))
def T(m): return ''.join(m[i] for i in (0,3,6,1,4,7,2,5,8))
def withfar(g):
    x0,y0,x1,y1=g.bounds; fp=shapely.Point(x1+(x1-x0)*10+1,y1+(y1-y0)*10+1)
    return shapely.GeometryCollection(list(shapely.get_parts(g))+[fp])
for e in j['findings']:
    if e['rule']!='R2': continue
    A=wkt.loads(e['a']); B=wkt.loads(e['b'])
    print(e['key_id'],'ab',shapely.relate(A,B),'T(ba)',T(shapely.relate(B,A)),
          '| ab with A forced self-noding (A+far point):',shapely.relate(withfar(A),B),
          '| T(ba) with B forced:',T(shapely.relate(withfar(B),A)))
