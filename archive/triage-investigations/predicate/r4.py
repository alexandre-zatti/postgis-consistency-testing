import sys,json
import shapely; from shapely import wkt
from shapely.validation import explain_validity
j=json.load(open(sys.argv[1]+'/findings.json',encoding='utf-8'))
def gc(g): return shapely.GeometryCollection(list(shapely.get_parts(g)))
def withfar(g):
    x0,y0,x1,y1=g.bounds; fp=shapely.Point(x1+(x1-x0)*10+1,y1+(y1-y0)*10+1)
    return shapely.GeometryCollection(list(shapely.get_parts(g))+[fp])
for e in j['findings']:
    if e['rule']!='R4': continue
    A=wkt.loads(e['a']); B=wkt.loads(e['b'])
    v=e['rerun']['images']['current']['violations'][0]
    print('==',e['key_id'],e['sub'],v['raw'] if 'raw' in v else '', 'orient',e['orientation'])
    print('  a:',e['a']); print('  b:',e['b'])
    print('  valid a:',explain_validity(A),'| b:',explain_validity(B))
    wrapA = 'arg1' in e['sub']
    x,y=(A,B) if e['orientation']=='ab' else (B,A)
    print('  relate(x,y)',shapely.relate(x,y),' relate(GC(x),y)' if wrapA else ' relate(x,GC(y))', shapely.relate(gc(x),y) if wrapA else shapely.relate(x,gc(y)),
          ' x forced selfnode',shapely.relate(withfar(x),y))
    print('  relate(y,x)',shapely.relate(y,x),' relate(y,GC(x))',shapely.relate(y,gc(x)))
