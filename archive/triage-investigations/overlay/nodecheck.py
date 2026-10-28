"""Emulate OverlayNG floating noding (MCIndexNoder + IntersectionAdder: exact intersection
point rounded to nearest double) and the FastNodingValidator check, in exact arithmetic.
Approximation of GEOS, not GEOS itself."""
import sys
sys.path.insert(0, r"C:/Users/Ale/AppData/Local/Temp/overlay-families")
from fractions import Fraction as F
from exact import *

def rnd(p): return (F(float(p[0])), F(float(p[1])))

def node_and_validate(ga, gb):
    S = segs(ga) + segs(gb)
    nodes = [set() for _ in S]
    for i in range(len(S)):
        for k in range(i+1, len(S)):
            kind, v = seg_inter(*S[i], *S[k])
            if kind == 'none': continue
            ps = [v] if kind == 'point' else list(v)
            for p in ps:
                q = rnd(p)
                for idx in (i, k):
                    a, b = S[idx]
                    if q != a and q != b: nodes[idx].add(q)
    # split
    pieces = []
    for idx, (a, b) in enumerate(S):
        ab = (b[0]-a[0], b[1]-a[1])
        t = lambda p: (p[0]-a[0])*ab[0] + (p[1]-a[1])*ab[1]
        pts = [a] + sorted(nodes[idx], key=t) + [b]
        pieces += [(pts[j], pts[j+1]) for j in range(len(pts)-1) if pts[j] != pts[j+1]]
    # validate: any intersection that is interior to a piece = invalid noding
    bad = []
    for i in range(len(pieces)):
        for k in range(i+1, len(pieces)):
            (a, b), (c, d) = pieces[i], pieces[k]
            kind, v = seg_inter(a, b, c, d)
            if kind == 'none': continue
            if kind == 'overlap':
                if {a, b} == {c, d}: continue  # identical edges: fine (coincident)
                bad.append(('overlap', i, k)); continue
            if v in (a, b) and v in (c, d): continue
            bad.append(('interior', i, k, (float(v[0]), float(v[1]))))
    return pieces, bad
