import json, sys
sys.path.insert(0, r"C:/Users/Ale/AppData/Local/Temp/overlay-families")
import shapely
from shapely import wkt
from exact import *
T = r"C:/Users/Ale/masters/coursework/MCET063 - Tópicos em Testes Automatizados e Verificação de Software (2026-2)/final-project/experiment/runs/e3/triage/"
j = json.load(open(T + "findings.json", encoding="utf-8"))
for f in j["findings"]:
    if f["rule"] != "R10" or "Polygon" not in f["types_sig"].split(" / ")[0] or "Polygon" not in f["types_sig"]: continue
    a, b = wkt.loads(f["a"]), wkt.loads(f["b"])
    if a.geom_type not in ("Polygon", "MultiPolygon"): continue
    rr = json.load(open(T + "reruns/" + f["key_id"] + ".json"))
    grid = rr["images"]["current"]["info"]["grid"]
    I = shapely.intersection(a, b)
    Ig = shapely.intersection(a, b, grid_size=grid)
    print("==", f["key_id"], f["types_sig"], "nverts", len(shapely.get_coordinates(a)), len(shapely.get_coordinates(b)), "valid", a.is_valid, b.is_valid, "grid", grid)
    print("  relate", shapely.relate(a, b), " intersects", shapely.intersects(a, b))
    print("  I  :", I.geom_type, shapely.get_dimensions(I), "area", I.area, "len", I.length, I.wkt[:200])
    print("  Ig :", Ig.geom_type, shapely.get_dimensions(Ig), "area", Ig.area, Ig.wkt[:160])
    # exact area of overlap per component pair
    tot = 0; convex_ok = True
    for pa in shapely.get_parts(a):
        for pb in shapely.get_parts(b):
            A, B = ring_pts(pa), ring_pts(pb)
            if len(pb.interiors) or len(pa.interiors): convex_ok = False
            if pb.convex_hull.equals(pb) and len(B) == len(ring_pts(pb.convex_hull)):
                C = clip_convex(A, B)
            elif pa.convex_hull.equals(pa) and len(A) == len(ring_pts(pa.convex_hull)):
                C = clip_convex(B, A)
            else:
                convex_ok = False; continue
            ar = area2(C) / 2 if len(C) >= 3 else 0
            tot += ar
            if ar: print("   exact pair area", float(ar), "clip verts", len(C))
    print("  exact overlap area", float(tot), "(complete)" if convex_ok else "(partial: non-convex pair skipped)")
    # exact boundary contacts
    pts, ovl = line_line(a, b)
    print("  exact boundary contacts: points", len(pts), "overlaps", len(ovl))
