"""Post-hoc (exploratory) E3 analysis: all four contrasts tested, and a decomposition that drops
R11 on line/line pairs (S1) and additionally all R10 (S2). Frozen rules and primary unchanged."""
import json, sys
from collections import Counter
from pathlib import Path
from scipy.stats import wilcoxon
from tavs import analysis as A

cdir = Path(sys.argv[1])
data = A.load(cdir)
pairs = list(data["pairs"].values())
for p in pairs:
    A.classify(p)
seeds = sorted({p["seed"] for p in pairs})
kinds = sorted({p["kind"] for p in pairs})


def is_ll(p):
    t = p.get("types") or []
    return len(t) == 2 and all("Line" in str(x) for x in t)


def keep_s1(p, v):
    return not (v["rule"] == "R11" and is_ll(p))


def keep_s2(p, v):
    return keep_s1(p, v) and v["rule"] != "R10"


for p in pairs:
    p["s1"] = any(A.counted(v) and keep_s1(p, v) for v in p["violations"])
    p["s2"] = any(A.counted(v) and keep_s2(p, v) for v in p["violations"])

print("types sample:", Counter(tuple(p.get("types") or []) for p in pairs).most_common(4))
for key in ("violating", "s1", "s2"):
    rates = A.rate_table(pairs, seeds, kinds, key=key)
    ok = [p for p in pairs if not p["harness"]]
    tot = Counter(p["arm"] for p in ok if p[key])
    print(f"\n== {key}: violating pairs per arm {dict(tot)}")
    for arm in A.ARMS:
        if arm in rates:
            print(f"   {arm}: per-seed per10k", [round(rates[arm][s]["pooled"], 1) for s in seeds])
    ps, rows = [], []
    for name, x, y in A.CONTRASTS:
        xs = [rates[x][s]["pooled"] for s in seeds]
        ys = [rates[y][s]["pooled"] for s in seeds]
        d = [a - b for a, b in zip(xs, ys)]
        nz = [e for e in d if e != 0]
        if nz:
            w = wilcoxon(xs, ys, zero_method="wilcox", method="exact", alternative="two-sided")
            ps.append(float(w.pvalue))
            rk = sorted(range(len(nz)), key=lambda i: abs(nz[i]))
            rows.append((name, x, y, len(nz), float(w.statistic), float(w.pvalue)))
        else:
            ps.append(1.0)
            rows.append((name, x, y, 0, None, None))
    adj = A.holm(ps)
    for (name, x, y, n, W, p), a in zip(rows, adj):
        print(f"   {name}: {x} vs {y}: nonzero seeds {n}, W={W}, p={p}, Holm={a:.4f}")
