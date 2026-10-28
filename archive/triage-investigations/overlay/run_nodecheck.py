import json, sys
sys.path.insert(0, r"C:/Users/Ale/AppData/Local/Temp/overlay-families")
from shapely import wkt
from nodecheck import node_and_validate
T = r"C:/Users/Ale/masters/coursework/MCET063 - Tópicos em Testes Automatizados e Verificação de Software (2026-2)/final-project/experiment/runs/e3/triage/"
j = json.load(open(T + "findings.json", encoding="utf-8"))
for f in j["findings"]:
    if f["rule"] not in sys.argv[1].split(","): continue
    a, b = wkt.loads(f["a"]), wkt.loads(f["b"])
    pieces, bad = node_and_validate(a, b)
    print(f["rule"], f["function"], f["key_id"], f["types_sig"], "pieces", len(pieces), "noding", "INVALID" if bad else "valid", bad[:2])
