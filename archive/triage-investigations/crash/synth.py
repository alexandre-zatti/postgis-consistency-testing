import json
from lib import *
D={o['key']:o for o in json.load(open("crash_f.json"))}
# 8 covers findings that did not crash with shapely.covers: replay PostGIS's GEOSRelatePattern(g1,g2,'******FF*')
for k in ['294fa540b9e7','2f21b3671a46','3c65694cb6d0','55126c6f66d3','7938b1290db5','b12ac70d395d','c076a34c36d2','f8fafa8e6c72']:
    o=D[k]; res=[]
    for pr in o['cur']:
        i=form_of(pr)
        res.append((pr, run_form(o,'covers',i,o['a'],o['b']), run_form(o,'relate_pattern',i,o['a'],o['b'],'******FF*')))
    print(k,res)
P1="POLYGON ((0 0, 1 0, 0 1, 0 0))"; P2="POLYGON ((0 0, -1 0, 0 -1, 0 0))"; P2off="POLYGON ((0.1 0, -1 0, 0 -1, 0.1 0))"; P2far="POLYGON ((5 5, 4 5, 5 4, 5 5))"
P2edge="POLYGON ((0.5 0, 0.5 -1, -0.5 -1, 0.5 0))"  # touches P1 at (0.5,0) vertex-on-edge
G=lambda *m: "GEOMETRYCOLLECTION ("+", ".join(m)+")"
S=[
 ("GC(EMPTY,P1,P2) vs far POINT", G("POLYGON EMPTY",P1,P2), "POINT (9 9)"),
 ("GC(EMPTY,P1,P2) vs POINT at shared vertex", G("POLYGON EMPTY",P1,P2), "POINT (0 0)"),
 ("GC(EMPTY,P1,P2) vs POINT(0.2 0.2)", G("POLYGON EMPTY",P1,P2), "POINT (0.2 0.2)"),
 ("GC(P1,P2) no EMPTY vs POINT 0 0", G(P1,P2), "POINT (0 0)"),
 ("GC(P1,P2,EMPTY) EMPTY last", G(P1,P2,"POLYGON EMPTY"), "POINT (0 0)"),
 ("GC(EMPTY,P1,P2off) no touch", G("POLYGON EMPTY",P1,P2off), "POINT (0 0)"),
 ("GC(EMPTY,P1,P2far) no touch", G("POLYGON EMPTY",P1,P2far), "POINT (0 0)"),
 ("GC(EMPTY,P1,P2edge) vertex-on-edge touch, point there", G("POLYGON EMPTY",P1,P2edge), "POINT (0.5 0)"),
 ("GC(EMPTY,P1,P2edge) vs far point", G("POLYGON EMPTY",P1,P2edge), "POINT (9 9)"),
 ("GC(POINT EMPTY,P1,P2)", G("POINT EMPTY",P1,P2), "POINT (0 0)"),
 ("GC(LINESTRING EMPTY,P1,P2)", G("LINESTRING EMPTY",P1,P2), "POINT (0 0)"),
 ("GC(MULTIPOLYGON EMPTY,P1,P2)", G("MULTIPOLYGON EMPTY",P1,P2), "POINT (0 0)"),
 ("GC(P1, MULTIPOLYGON(P2,EMPTY))", G(P1,"MULTIPOLYGON (((0 0, -1 0, 0 -1, 0 0)), EMPTY)"), "POINT (0 0)"),
 ("MULTIPOLYGON(P1,EMPTY,P2) unwrapped", "MULTIPOLYGON (((0 0, 1 0, 0 1, 0 0)), EMPTY, ((0 0, -1 0, 0 -1, 0 0)))", "POINT (0 0)"),
 ("GC(EMPTY, MULTIPOLYGON(P1,P2)) one polygonal element", G("POLYGON EMPTY","MULTIPOLYGON (((0 0, 1 0, 0 1, 0 0)), ((0 0, -1 0, 0 -1, 0 0)))"), "POINT (0 0)"),
 ("1e15 GC(EMPTY,P1,P2) vs point", G("POLYGON EMPTY","POLYGON ((1e15 1e15, 1000000000000001 1e15, 1e15 1000000000000001, 1e15 1e15))","POLYGON ((1e15 1e15, 999999999999999 1e15, 1e15 999999999999999, 1e15 1e15))"), "POINT (1e15 1e15)"),
]
for name,x,y in S:
    print(f"{name}: relate={call('relate',x,y)} | intersects={call('intersects',x,y)} | prepared_intersects={call('intersects',x,y,prepared=True)} | relate(y,x)={call('relate',y,x)}")
