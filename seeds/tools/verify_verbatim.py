import json, os, sys
seeds = sys.argv[1]; raw = os.path.join(seeds, "raw")
corpus = ""
for f in os.listdir(raw):
    p = os.path.join(raw, f)
    if f.endswith(".json"):
        d = json.load(open(p, encoding="utf-8"))
        for x in (d if isinstance(d, list) else [d]):
            corpus += "\n" + (x.get("body") or "").replace("\r\n", "\n")
    elif f.endswith((".patch", ".txt")):
        corpus += "\n" + open(p, encoding="utf-8").read()
d = json.load(open(os.path.join(seeds, "known_bugs.json"), encoding="utf-8"))
for r in d["records"]:
    for k, w in (r["geometries"] or {}).items():
        if w not in corpus:
            print("NOT VERBATIM", r["id"], k, w[:60])
print("done", len(d["records"]))
