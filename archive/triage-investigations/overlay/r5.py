import json, sys, math
sys.path.insert(0, r"C:/Users/Ale/AppData/Local/Temp/overlay-families")
import shapely
from shapely import wkt
from exact import *
from nodecheck import node_and_validate
T = r"C:/Users/Ale/masters/coursework/MCET063 - Tópicos em Testes Automatizados e Verificação de Software (2026-2)/final-project/experiment/runs/e3/triage/"
j = json.load(open(T + "findings.json", encoding="utf-8"))
f = [x for x in j["findings"] if x["key_id"] == "49cb0e6036b1"][0]
a, b = wkt.loads(f["a"]), wkt.loads(f["b"])
print(f["a"]); print(f["b"]); print(f["rep_item"]["source"], f["rep_item"]["arm"])
rr = json.load(open(T + "reruns/49cb0e6036b1.json"))
print({k: [v["raw"] for v in rr["images"][k]["violations"]] for k in rr["images"]})
print("shapely key", rr.get("shapely"))
grid = rr["images"]["current"]["info"]["grid"]
I = shapely.intersection(a, b); Ig = shapely.intersection(a, b, grid_size=grid)
print("intersects", shapely.intersects(a, b), "relate", shapely.relate(a, b), "dist", shapely.distance(a, b))
print("I", I.wkt, "\nIg", Ig.wkt)
pts, ovl = line_line(a, b)
print("exact pts", len(pts), "ovl", len(ovl))
for s in segs(a):
    for t in segs(b):
        (p, q), (c, d) = s, t
        # exact min distance between segments (float approx)
        from shapely.geometry import LineString
        ds = LineString([tuple(map(float, p)), tuple(map(float, q))]).distance(LineString([tuple(map(float, c)), tuple(map(float, d))]))
        print("  seg pair dist", ds, "orient c,d wrt a-seg", orient(p, q, c), orient(p, q, d), "orient p,q wrt b-seg", orient(c, d, p), orient(c, d, q))
pieces, bad = node_and_validate(a, b); print("noding emu", bad)
# snapping tolerance in GEOS
M = max(abs(v) for v in shapely.get_coordinates(shapely.union(a, b)).ravel()); print("M", M, "snapTol", M / 1e12)
