import json, sys
sys.path.insert(0, r"C:/Users/Ale/AppData/Local/Temp/overlay-families")
import shapely
from shapely import wkt
from fractions import Fraction as F
from exact import *
T = r"C:/Users/Ale/masters/coursework/MCET063 - Tópicos em Testes Automatizados e Verificação de Software (2026-2)/final-project/experiment/runs/e3/triage/"
j = json.load(open(T + "findings.json", encoding="utf-8"))
for f in j["findings"]:
    if f["rule"] != "R10" or "Line" not in f["types_sig"]: continue
    a, b = wkt.loads(f["a"]), wkt.loads(f["b"])
    pts, _ = line_line(a, b)
    rp = sorted({(float(p[0]), float(p[1])) for p in pts})
    I = shapely.intersection(a, b)
    ov = sorted({tuple(c) for c in shapely.get_coordinates(I)})
    verts = {tuple(c) for c in shapely.get_coordinates(a)} | {tuple(c) for c in shapely.get_coordinates(b)}
    print(f["key_id"], "exact pts rounded:", len(rp), "| overlay coords:", len(ov), "all overlay coords are rounded exact pts:", set(ov) <= set(rp), "| extra coords that are input vertices:", [c in verts for c in ov if c not in rp])
