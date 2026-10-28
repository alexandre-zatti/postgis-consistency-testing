import sys, json, shapely
p=json.loads(sys.argv[1])
x,y=shapely.from_wkt(p['x']),shapely.from_wkt(p['y'])
def fc(g):
    if g.geom_type=="GeometryCollection": return g
    if g.geom_type.startswith("Multi"): return shapely.GeometryCollection(list(shapely.get_parts(g)))
    return shapely.GeometryCollection([g])
if p.get('wrap')==1: x=fc(x)
elif p.get('wrap')==2: y=fc(y)
if p.get('prepared'): shapely.prepare(x)
fn=p['fn']
if fn=='relate_pattern': r=shapely.relate_pattern(x,y,p['pattern'])
else: r=getattr(shapely,fn)(x,y)
print(json.dumps(r if isinstance(r,(bool,str)) else str(r)))
