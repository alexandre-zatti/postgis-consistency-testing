import sys,json,collections
import shapely
from shapely import wkt
j=json.load(open(sys.argv[1]+'/findings.json',encoding='utf-8'))
fn={'Contains':shapely.contains,'Covers':shapely.covers,'Within':shapely.within}
out=collections.Counter(); ex={}
for e in j['findings']:
    if e['rule']!='R3': continue
    A=wkt.loads(e['a']); B=wkt.loads(e['b'])
    emp='EMPTY' in e['a'] or 'EMPTY' in e['b']
    o=e['orientation']; x,y=(A,B) if o=='ab' else (B,A)
    f=fn[e['function']]
    lone=bool(f(x,y))
    x2=shapely.from_wkb(shapely.to_wkb(x)); y2=shapely.from_wkb(shapely.to_wkb(y))
    if 'arg1' in e['sub']: shapely.prepare(x2)
    else: shapely.prepare(y2)
    prep=bool(f(x2,y2))
    rel=shapely.relate(x,y)
    raw=e['rerun']['images']['current']['violations'][0]['raw']
    k=(emp,e['function'],e['sub'],x.geom_type,y.geom_type,'pg lone=%s calls=%s'%(raw['lone'],raw['calls']),'sh lone=%s prep=%s'%(lone,prep))
    out[k]+=1
    ex.setdefault(k,[]).append((e['key_id'],rel,x.is_valid,y.is_valid))
for k,n in sorted(out.items(),key=str): print(n,k,ex[k][:2])
