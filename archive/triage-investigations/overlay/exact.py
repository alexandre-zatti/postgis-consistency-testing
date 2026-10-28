"""Exact (rational) helpers on the double-valued inputs."""
from fractions import Fraction as F
import shapely

def fr(p): return (F(p[0]), F(p[1]))

def orient(a, b, c):
    v = (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])
    return (v > 0) - (v < 0)

def segs(g):
    out = []
    for part in shapely.get_parts(g):
        if part.geom_type in ('Polygon',):
            rings = [part.exterior] + list(part.interiors)
        else:
            rings = [part]
        for r in rings:
            cs = [fr(c) for c in shapely.get_coordinates(r)]
            out += [(cs[i], cs[i+1]) for i in range(len(cs)-1) if cs[i] != cs[i+1]]
    return out

def on_seg(p, a, b):
    return orient(a, b, p) == 0 and min(a[0], b[0]) <= p[0] <= max(a[0], b[0]) and min(a[1], b[1]) <= p[1] <= max(a[1], b[1])

def seg_inter(a, b, c, d):
    """Return ('none'|'point'|'overlap', payload) exactly."""
    o1, o2, o3, o4 = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
    if o1 == o2 == 0:  # collinear lines
        # parametrise on a->b
        ab = (b[0]-a[0], b[1]-a[1]); L2 = ab[0]**2 + ab[1]**2
        t = lambda p: ((p[0]-a[0])*ab[0] + (p[1]-a[1])*ab[1]) / L2
        tc, td = sorted([t(c), t(d)])
        lo, hi = max(F(0), tc), min(F(1), td)
        if lo > hi: return ('none', None)
        P = lambda s: (a[0]+s*ab[0], a[1]+s*ab[1])
        if lo == hi: return ('point', P(lo))
        return ('overlap', (P(lo), P(hi)))
    if o1 != o2 and o3 != o4:
        # proper or endpoint intersection
        den = (b[0]-a[0])*(d[1]-c[1]) - (b[1]-a[1])*(d[0]-c[0])
        s = ((c[0]-a[0])*(d[1]-c[1]) - (c[1]-a[1])*(d[0]-c[0])) / den
        return ('point', (a[0]+s*(b[0]-a[0]), a[1]+s*(b[1]-a[1])))
    for p, (x, y) in ((c, (a, b)), (d, (a, b)), (a, (c, d)), (b, (c, d))):
        if on_seg(p, x, y): return ('point', p)
    return ('none', None)

def line_line(ga, gb):
    pts, ovl = [], []
    for s in segs(ga):
        for t in segs(gb):
            k, v = seg_inter(*s, *t)
            if k == 'point': pts.append(v)
            elif k == 'overlap': ovl.append(v)
    return pts, ovl

def area2(poly):
    s = 0
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]; x2, y2 = poly[(i+1) % n]
        s += x1*y2 - x2*y1
    return s

def clip_convex(subject, clip):
    """Sutherland-Hodgman, exact. clip must be convex, CCW."""
    out = subject
    n = len(clip)
    for i in range(n):
        A, B = clip[i], clip[(i+1) % n]
        inp, out = out, []
        if not inp: break
        for j in range(len(inp)):
            P, Q = inp[j], inp[(j+1) % len(inp)]
            pin, qin = orient(A, B, P) >= 0, orient(A, B, Q) >= 0
            if pin: out.append(P)
            if pin != qin:
                den = (Q[0]-P[0])*(B[1]-A[1]) - (Q[1]-P[1])*(B[0]-A[0])
                s = ((A[0]-P[0])*(B[1]-A[1]) - (A[1]-P[1])*(B[0]-A[0])) / den
                X = (P[0]+s*(Q[0]-P[0]), P[1]+s*(Q[1]-P[1]))
                if X != P and X != Q: out.append(X)
                elif X == Q and not qin: out.append(X)
    return out

def ring_pts(poly):
    cs = [fr(c) for c in shapely.get_coordinates(poly.exterior)][:-1]
    if area2(cs) < 0: cs = cs[::-1]
    return cs
