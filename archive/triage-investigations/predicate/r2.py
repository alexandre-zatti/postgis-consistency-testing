import sys,json
import shapely; from shapely import wkt
from shapely.validation import explain_validity
j=json.load(open(sys.argv[1]+'/findings.json',encoding='utf-8'))
def T(m): return ''.join(m[i] for i in (0,3,6,1,4,7,2,5,8))
def prep(g):
    g=shapely.from_wkb(shapely.to_wkb(g)); shapely.prepare(g); return g
for e in j['findings']:
    if e['rule']!='R2': continue
    A=wkt.loads(e['a']); B=wkt.loads(e['b'])
    print('==',e['key_id'], e['rerun']['images']['current']['violations'][0]['raw'], e['rerun']['images']['dev']['violations'][0]['raw'])
    print('  a:',e['a']); print('  b:',e['b'])
    print('  valid a/b:',explain_validity(A),'|',explain_validity(B))
    for p in shapely.get_parts(B) if B.geom_type=='GeometryCollection' else []:
        print('   part',p.geom_type,explain_validity(p))
    ab=shapely.relate(A,B); ba=shapely.relate(B,A)
    print('  shapely relate ab',ab,'T(ba)',T(ba),'| prepared A:',shapely.relate(prep(A),B),'prepared B T:',T(shapely.relate(prep(B),A)))
    print('  boundary inter:', shapely.intersection(A.boundary if A.geom_type!='GeometryCollection' else shapely.boundary(shapely.union_all(A)), B.boundary if B.geom_type!='GeometryCollection' else shapely.boundary(shapely.union_all(B))).wkt[:200])
