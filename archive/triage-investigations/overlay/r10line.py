import json, sys
sys.path.insert(0, r"C:/Users/Ale/AppData/Local/Temp/overlay-families")
import shapely, math
from shapely import wkt
from exact import *
T = r"C:/Users/Ale/masters/coursework/MCET063 - Tópicos em Testes Automatizados e Verificação de Software (2026-2)/final-project/experiment/runs/e3/triage/"
j = json.load(open(T + "findings.json", encoding="utf-8"))
rules = sys.argv[1].split(",")
for f in j["findings"]:
    if f["rule"] not in rules: continue
    a, b = wkt.loads(f["a"]), wkt.loads(f["b"])
    if a.geom_type not in ("LineString", "MultiLineString"): continue
    rr = json.load(open(T + "reruns/" + f["key_id"] + ".json"))
    grid = rr["images"]["current"]["info"]["grid"]
    I = shapely.intersection(a, b); Ig = shapely.intersection(a, b, grid_size=grid)
    print("==", f["rule"], f["function"], f["key_id"], f["types_sig"], "nseg", len(segs(a)), len(segs(b)), "grid", grid, "src", f["rep_item"]["source"][:60], f["rep_item"]["arm"])
    print("  relate", shapely.relate(a, b), "intersects", shapely.intersects(a, b))
    print("  I  :", I.geom_type, shapely.get_dimensions(I), "len", I.length, I.wkt[:230])
    print("  Ig :", Ig.geom_type, shapely.get_dimensions(Ig), "len", Ig.length, Ig.wkt[:160])
    if f["function"] == "Union":
        U = shapely.union(a, b); Ug = shapely.union(a, b, grid_size=grid)
        print("  U len", U.length, "Ug len", Ug.length, "a+b", a.length + b.length)
    pts, ovl = line_line(a, b)
    ol = sum(math.hypot(float(q[0]-p[0]), float(q[1]-p[1])) for p, q in ovl)
    print("  EXACT: points", len(pts), [(float(p[0]), float(p[1])) for p in pts][:4], "collinear overlaps", len(ovl), "overlap len", ol)
    # near-collinearity: max distance of b's vertices from a's lines
    for s in segs(a):
        for t in segs(b):
            (p, q), (c, d) = s, t
            L = math.hypot(float(q[0]-p[0]), float(q[1]-p[1]))
            dc = float(abs((q[0]-p[0])*(c[1]-p[1]) - (q[1]-p[1])*(c[0]-p[0]))) / L
            dd = float(abs((q[0]-p[0])*(d[1]-p[1]) - (q[1]-p[1])*(d[0]-p[0]))) / L
            if min(dc, dd) < 1e-3: print("   near-collinear pair: dist of b-ends to a-line", f"{dc:.3e} {dd:.3e}")
