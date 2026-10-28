import sys,json
sys.path.insert(0,r'C:/Users/Ale/AppData/Local/Temp/predicate-families')
import shapely; from shapely import wkt
from exact import exact
j=json.load(open(sys.argv[1]+'/findings.json',encoding='utf-8'))
seen=set()
def prep(g):
    g=shapely.from_wkb(shapely.to_wkb(g)); shapely.prepare(g); return g
for e in j['findings']:
    if e['rule']!='R3' or 'EMPTY' in e['a'] or 'EMPTY' in e['b']: continue
    A=wkt.loads(e['a']); B=wkt.loads(e['b'])
    x,y=(A,B) if e['orientation']=='ab' else (B,A)
    if e['function']=='Within': x,y=y,x
    key=(x.wkt,y.wkt)
    r=exact(x,y)
    print(e['key_id'],e['function'],x.geom_type,y.geom_type,'nv=',shapely.get_num_coordinates(x),shapely.get_num_coordinates(y),
      'geos lone C/Cv=',bool(shapely.contains(x,y)),bool(shapely.covers(x,y)),'prep C/Cv=',bool(shapely.contains(prep(x),y)),bool(shapely.covers(prep(x),y)),
      'exact=',r, 'dup' if key in seen else '')
    seen.add(key)
