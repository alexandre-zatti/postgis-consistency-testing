"""Check: for line/line R10 and R11 findings, does any segment pair overlap collinearly in
exact arithmetic on the stored doubles? If none does, the true intersection has length 0."""
import json, sys
from fractions import Fraction as F
import shapely

d = json.load(open(sys.argv[1], encoding="utf-8"))
fs = d["findings"] if isinstance(d, dict) else d


def segs(g):
    out = []
    for part in shapely.get_parts(g):
        cs = [(F(x), F(y)) for x, y in shapely.get_coordinates(part)]
        out += list(zip(cs, cs[1:]))
    return out


def cross(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def overlap_len2(s, t):
    (p, q), (r, u) = s, t
    if cross(p, q, r) != 0 or cross(p, q, u) != 0:
        return 0
    ax = 0 if p[0] != q[0] else 1          # project on a non-degenerate axis
    lo1, hi1 = sorted((p[ax], q[ax])); lo2, hi2 = sorted((r[ax], u[ax]))
    return max(0, min(hi1, hi2) - max(lo1, lo2))


for f in fs:
    if f["rule"] not in ("R10", "R11"):
        continue
    a, b = shapely.from_wkt(f["a"]), shapely.from_wkt(f["b"])
    if "Line" not in a.geom_type or "Line" not in b.geom_type:
        continue
    ov = any(overlap_len2(s, t) > 0 for s in segs(a) for t in segs(b))
    fl = shapely.intersection(a, b)
    print(f["rule"], f["function"], "exact collinear overlap:", ov,
          "| float result:", fl.geom_type, round(fl.length, 6))
