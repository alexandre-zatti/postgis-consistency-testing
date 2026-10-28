import json, sys, math
sys.path.insert(0, r"C:/Users/Ale/AppData/Local/Temp/overlay-families")
import shapely
from shapely import wkt
from exact import *
T = r"C:/Users/Ale/masters/coursework/MCET063 - Tópicos em Testes Automatizados e Verificação de Software (2026-2)/final-project/experiment/runs/e3/triage/"
j = json.load(open(T + "findings.json", encoding="utf-8"))
for f in j["findings"]:
    if f["rule"] != "R10" or "Polygon" not in f["types_sig"]: continue
    a, b = wkt.loads(f["a"]), wkt.loads(f["b"])
    best = None
    for pa in shapely.get_parts(a):
        for pb in shapely.get_parts(b):
            C = clip_convex(ring_pts(pa), ring_pts(pb))
            if len(C) >= 3 and area2(C):
                ar = float(area2(C)) / 2
                L = max(math.hypot(float(C[i][0]-C[i-1][0]), float(C[i][1]-C[i-1][1])) for i in range(len(C)))
                best = (ar, L, 2*ar/L)
    M = max(abs(v) for v in shapely.get_coordinates(shapely.union_all([a, b])).ravel())
    print(f["key_id"], "area %.2e longest edge %.3g max width %.2e  ulp(M) %.2e  dim(I) %d" % (*best, math.ulp(M), shapely.get_dimensions(shapely.intersection(a, b))))
