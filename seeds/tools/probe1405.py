import json,sys,shapely
sys.stdout.reconfigure(encoding="utf-8")
d=json.load(open(sys.argv[1],encoding="utf-8"))
r=[x for x in d["records"] if x["id"]=="geos#1405"][0]
s1=shapely.from_wkt(r["geometries"]["shape1"]); s2=shapely.from_wkt(r["geometries"]["shape2"])
print("areas",s1.area,s2.area,"overlap rel",shapely.relate(s1,s2))
for lab,(a,b) in (("raw",(s1,s2)),("pre",(shapely.normalize(shapely.buffer(s1,0)),shapely.normalize(shapely.buffer(s2,0))))):
    x=shapely.intersection(a,b); y=shapely.intersection(b,a)
    print(lab,"s1∩s2:",shapely.to_wkt(x,rounding_precision=-1)[:400]); print(lab,"s2∩s1:",shapely.to_wkt(y,rounding_precision=-1)[:400])
    print(lab, "equals", shapely.equals(x,y), "len", shapely.length(x), shapely.length(y))
x=shapely.intersection(s1,shapely.set_precision(s2,1e-300)); print("setprec",shapely.to_wkt(x,rounding_precision=-1)[:300])
