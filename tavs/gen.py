"""Seeded pair generators for the 2x2 design (plain/degenerate x integer/float).

Binding specification: experiment-plan.md, section "Generators (2x2, equal pair budgets, seeded)".

Geometries are built in a small internal representation and written to WKT here, so the
emitted text is exactly what was validated:

    ("Point", [pt]) or ("Point", [])            pt = (x, y)
    ("LineString", [pt, ...])
    ("Polygon", [ring, ...])                    rings are open (no repeated closing point)
    ("MultiPoint" | "MultiLineString" | "MultiPolygon" | "GeometryCollection", [child, ...])

Integer arms store Python ints (written without a decimal point); float arms store floats
written with ``repr`` (shortest round-trip form). Every pair is drawn from its own RNG seeded
by (arm, seed, kind, index), so pair i does not depend on how many pairs are requested.
"""

from __future__ import annotations

import hashlib
import math
import random
from collections import Counter
from fractions import Fraction
from typing import Iterable, Iterator, Optional

import numpy as np
import shapely

from .pair import Pair

ARMS = ("plain-int", "plain-float", "degen-int", "degen-float")
KINDS = ("predicate", "overlay")
LO, HI = 0, 2 ** 20                     # coordinate range (plan: [0, 2^20])
EXT_LO, EXT_HI = 10.0, 1000.0           # shape extent in units
RATIO_LO, RATIO_HI = 0.1, 10.0          # scale ratio a:b, log-uniform
P_NEAR = 0.8                            # b's centre inside a's box expanded by half
MAX_BASE_TRIES = 200
MAX_MOVE_TRIES = 5

# Type mix. Ordered (a, b) classes; A/A, L/A and P/A weighted double (plan, literal reading).
PRED_MIX = [("P", "P", 1), ("P", "L", 1), ("P", "A", 2),
            ("L", "P", 1), ("L", "L", 1), ("L", "A", 2),
            ("A", "P", 1), ("A", "L", 1), ("A", "A", 2)]
OVER_MIX = [("A", "A", 1), ("L", "L", 1)]

GEOM_MOVES = ["shared-vertex", "vertex-on-edge", "collinear-overlap", "hole-tangent",
              "sliver-or-spike", "parts-touching", "empty-part", "point-collection"]
PRED_ONLY_MOVES = {"empty-part", "point-collection"}

SINGLE = {"P": "Point", "L": "LineString", "A": "Polygon"}
MULTI = {"P": "MultiPoint", "L": "MultiLineString", "A": "MultiPolygon"}
DIM = {"P": 0, "L": 1, "A": 2}
CLASSES = ("P", "L", "A")

# --------------------------------------------------------------------------------------------
# Resample accounting (process-wide; per kind, since the arms share base draws).

_STATS: dict[str, Counter] = {}


def _stat(kind: str) -> Counter:
    return _STATS.setdefault(kind, Counter())


def resample_stats(reset: bool = False) -> dict:
    """Counts per kind: indices built; invalid base draws resampled (resample_a/_b, shared by
    all arms); move attempts retried for invalid output or not applicable (degen arms);
    indices whose degen arms got no move; regime redraws and fallbacks (float arms); regime mix."""
    out = {k: dict(c) for k, c in sorted(_STATS.items())}
    if reset:
        _STATS.clear()
    return out


# --------------------------------------------------------------------------------------------
# Internal representation helpers.

def is_multi(t: str) -> bool:
    return t.startswith("Multi") or t == "GeometryCollection"


def fmt(v) -> str:
    if isinstance(v, int):
        return str(v)
    if not math.isfinite(v):
        raise ValueError("non-finite coordinate")
    return repr(float(v))


def _pt(p) -> str:
    return f"{fmt(p[0])} {fmt(p[1])}"


def _seq(s, closed=False) -> str:
    pts = list(s) + ([s[0]] if closed and s else [])
    return "(" + ", ".join(_pt(p) for p in pts) + ")"


def _body(g) -> str:
    """WKT body without the type keyword, as used inside MULTI* parts."""
    t, d = g
    if not d:
        return "EMPTY"
    if t == "Point":
        return "(" + _pt(d[0]) + ")"
    if t == "LineString":
        return _seq(d)
    if t == "Polygon":
        return "(" + ", ".join(_seq(r, True) for r in d) + ")"
    raise ValueError(t)


def to_wkt(g) -> str:
    t, d = g
    if t in ("Point", "LineString", "Polygon"):
        b = _body(g)
        return f"{t.upper()} {b}" if b == "EMPTY" else f"{t.upper()} {b}"
    if not d:
        return f"{t.upper()} EMPTY"
    if t == "GeometryCollection":
        return "GEOMETRYCOLLECTION (" + ", ".join(to_wkt(c) for c in d) + ")"
    return f"{t.upper()} (" + ", ".join(_body(c) for c in d) + ")"


def _num(v: float, integral: bool):
    if integral:
        if v != int(v):
            raise ValueError("non-integral coordinate in integer pair")
        return int(v)
    return float(v)


def from_shapely(geom, integral: bool):
    """Shapely geometry -> internal representation (exact coordinates)."""
    t = geom.geom_type
    if t == "Point":
        return ("Point", [] if geom.is_empty else [tuple(_num(v, integral) for v in geom.coords[0][:2])])
    if t in ("LineString", "LinearRing"):
        return ("LineString", [(_num(x, integral), _num(y, integral)) for x, y, *_ in geom.coords])
    if t == "Polygon":
        if geom.is_empty:
            return ("Polygon", [])
        rings = [geom.exterior] + list(geom.interiors)
        return ("Polygon", [[(_num(x, integral), _num(y, integral)) for x, y, *_ in r.coords][:-1]
                            for r in rings])
    return (t, [from_shapely(c, integral) for c in geom.geoms])


def from_wkt(wkt: str, integral: bool):
    return from_shapely(shapely.from_wkt(wkt), integral)


def seqs(g, path=()):
    """Yield (path, seq, closed) for every coordinate sequence; path addresses it."""
    t, d = g
    if t == "Point":
        yield path, d, False
    elif t == "LineString":
        yield path, d, False
    elif t == "Polygon":
        for i, r in enumerate(d):
            yield path + (i,), r, True
    else:
        for i, c in enumerate(d):
            yield from seqs(c, path + (i,))


def set_seq(g, path, new):
    t, d = g
    if t in ("Point", "LineString"):
        assert not path
        return (t, list(new))
    if t == "Polygon":
        rings = [list(r) for r in d]
        rings[path[0]] = list(new)
        return (t, rings)
    kids = list(d)
    kids[path[0]] = set_seq(kids[path[0]], path[1:], new)
    return (t, kids)


def vertices(g) -> list:
    return [p for _, s, _ in seqs(g) for p in s]


def edges(g) -> list:
    out = []
    for _, s, closed in seqs(g):
        n = len(s)
        if n < 2:
            continue
        for i in range(n if closed else n - 1):
            if s[i] != s[(i + 1) % n]:          # skip zero-length edges
                out.append((s[i], s[(i + 1) % n]))
    return out


def leaves(g, path=()):
    """Yield (path, leaf) for every non-collection geometry; path indexes nested children."""
    t, d = g
    if is_multi(t):
        for i, c in enumerate(d):
            yield from leaves(c, path + (i,))
    else:
        yield path, g


def set_leaf(g, path, new):
    if not path:
        return new
    t, d = g
    kids = list(d)
    kids[path[0]] = set_leaf(kids[path[0]], path[1:], new)
    return (t, kids)


def map_coords(g, f):
    t, d = g
    if t in ("Point", "LineString"):
        return (t, [f(p) for p in d])
    if t == "Polygon":
        return (t, [[f(p) for p in r] for r in d])
    return (t, [map_coords(c, f) for c in d])


def nvert(g) -> int:
    return len(vertices(g))


def bbox(gs) -> tuple:
    vs = [p for g in gs for p in vertices(g)]
    xs = [p[0] for p in vs]
    ys = [p[1] for p in vs]
    return min(xs), min(ys), max(xs), max(ys)


# --------------------------------------------------------------------------------------------
# Drawing base shapes.

class Ctx:
    def __init__(self, rng: random.Random, integral: bool, stats: Optional[Counter] = None):
        self.rng = rng
        self.integral = integral
        self.stats = stats if stats is not None else Counter()

    def snap(self, p):
        if self.integral:
            return (int(round(p[0])), int(round(p[1])))
        return (float(p[0]), float(p[1]))

    def loguniform(self, lo, hi):
        return math.exp(self.rng.uniform(math.log(lo), math.log(hi)))


def _ray_radius(shell, c, th):
    """Distance from c along direction th to the first crossing of the closed ring."""
    dx, dy = math.cos(th), math.sin(th)
    best = math.inf
    n = len(shell)
    for i in range(n):
        (x1, y1), (x2, y2) = shell[i], shell[(i + 1) % n]
        ex, ey = x2 - x1, y2 - y1
        den = dx * ey - dy * ex
        if abs(den) < 1e-15:
            continue
        wx, wy = x1 - c[0], y1 - c[1]
        t = (wx * ey - wy * ex) / den
        u = (wx * dy - wy * dx) / den
        if t > 0 and -1e-12 <= u <= 1 + 1e-12:
            best = min(best, t)
    return best


def _dedupe(seq, closed):
    """Drop consecutive repeated points created by snapping (validity is checked later)."""
    out = [p for i, p in enumerate(seq) if i == 0 or p != seq[i - 1]]
    while closed and len(out) > 1 and out[-1] == out[0]:
        out.pop()
    return out


def draw_polygon(cx: Ctx, c, ext):
    """Star-shaped polygon, 3-12 vertices, 0-2 holes scaled 0.3-0.6 about the centre."""
    rng = cx.rng
    n = rng.randint(3, 12)
    R = ext / 2.0
    th0 = rng.uniform(0, 2 * math.pi)
    angs = [th0 + 2 * math.pi * (i + rng.uniform(-0.2, 0.2)) / n for i in range(n)]
    shell = [(c[0] + R * r * math.cos(a), c[1] + R * r * math.sin(a))
             for a, r in ((a, rng.uniform(0.5, 1.0)) for a in angs)]
    rings = [shell]
    h = rng.randint(0, 2)
    if h == 1:
        s = rng.uniform(0.3, 0.6)
        rings.append([(c[0] + s * (x - c[0]), c[1] + s * (y - c[1])) for x, y in shell])
    elif h == 2:
        # Two holes cannot both be the whole shell scaled about the centre (they would nest),
        # so each is the scaled shell restricted to one half-plane sector, closed near c.
        base = rng.uniform(0, 2 * math.pi)
        for j in range(2):
            s = rng.uniform(0.3, 0.6)
            lo, hi = base + j * math.pi + 0.1 * math.pi, base + (j + 1) * math.pi - 0.1 * math.pi
            inner = [lo] + sorted(a for a in ((a - lo) % (2 * math.pi) + lo for a in angs)
                                  if lo < a < hi) + [hi]
            mid = (lo + hi) / 2
            r0 = 0.3 * s * _ray_radius(shell, c, mid)
            ring = [(c[0] + r0 * math.cos(mid), c[1] + r0 * math.sin(mid))]
            for a in inner:
                r = s * _ray_radius(shell, c, a)
                ring.append((c[0] + r * math.cos(a), c[1] + r * math.sin(a)))
            rings.append(ring)
    return ("Polygon", [_dedupe([cx.snap(p) for p in r], True) for r in rings])


def draw_line(cx: Ctx, c, ext):
    """Simple line, 2-8 vertices: x-monotone chain in a rotated frame."""
    rng = cx.rng
    k = rng.randint(2, 8)
    xs = sorted(rng.uniform(-ext / 2, ext / 2) for _ in range(k))
    ys = [rng.uniform(-ext / 4, ext / 4) for _ in range(k)]
    phi = rng.uniform(0, 2 * math.pi)
    co, si = math.cos(phi), math.sin(phi)
    return ("LineString", _dedupe([cx.snap((c[0] + x * co - y * si, c[1] + x * si + y * co))
                                   for x, y in zip(xs, ys)], False))


def draw_point(cx: Ctx, c, ext):
    rng = cx.rng
    return ("Point", [cx.snap((c[0] + rng.uniform(-ext / 2, ext / 2),
                               c[1] + rng.uniform(-ext / 2, ext / 2)))])


DRAW = {"P": draw_point, "L": draw_line, "A": draw_polygon}


def draw_shape(cx: Ctx, cls: str, form: str, c, ext):
    rng = cx.rng
    if form == "single":
        return DRAW[cls](cx, c, ext)
    k = rng.randint(1, 3)
    pext = max(EXT_LO, ext / k)
    phi = rng.uniform(0, 2 * math.pi)
    u = (math.cos(phi), math.sin(phi))
    cents = [(c[0] + (j - (k - 1) / 2) * 1.15 * pext * u[0],
              c[1] + (j - (k - 1) / 2) * 1.15 * pext * u[1]) for j in range(k)]
    if form == "multi":
        return (MULTI[cls], [DRAW[cls](cx, cc, pext) for cc in cents])
    # collection: one member of the class, the others of any class of lower or equal dimension
    kinds = [cls] + [rng.choice(CLASSES[:DIM[cls] + 1]) for _ in range(k - 1)]
    rng.shuffle(kinds)
    return ("GeometryCollection", [DRAW[q](cx, cc, pext) for q, cc in zip(kinds, cents)])


def _in_range(g, integral):
    for p in vertices(g):
        for v in p:
            if not math.isfinite(v):
                return False
            if integral and not (isinstance(v, int) and LO <= v <= HI):
                return False
            if not integral and not (LO <= v <= HI):
                return False
    return True


def valid(g) -> bool:
    try:
        s = shapely.from_wkt(to_wkt(g))
    except Exception:
        return False
    if not s.is_valid:
        return False
    # lines must be simple (plan: "lines 2-8 vertices, simple")
    for _, leaf in leaves(g):
        if leaf[0] == "LineString" and leaf[1] and not shapely.from_wkt(to_wkt(leaf)).is_simple:
            return False
    return True


# --------------------------------------------------------------------------------------------
# Degenerate moves. Each returns (a, b) or None when not applicable to these types.

def _vec(p, q):
    return (q[0] - p[0], q[1] - p[1])


def _translate(g, d):
    return map_coords(g, lambda p: (p[0] + d[0], p[1] + d[1]))


def _pick_ab(cx, a, b):
    """Random (src, tgt, tgt_is_b)."""
    if cx.rng.random() < 0.5:
        return a, b, True
    return b, a, False


def _put(a, b, new_tgt, tgt_is_b):
    return (a, new_tgt) if tgt_is_b else (new_tgt, b)


def _nonempty_vertices(g):
    return [p for p in vertices(g)]


def _lattice_point_on(cx, p, q):
    """A point exactly in the relative interior of segment pq, or None (integer: gcd > 1)."""
    dx, dy = q[0] - p[0], q[1] - p[1]
    g = math.gcd(abs(dx), abs(dy))
    if g <= 1:
        return None
    k = cx.rng.randint(1, g - 1)
    return (p[0] + k * dx // g, p[1] + k * dy // g)


def mv_shared_vertex(cx, a, b, kind):
    src, tgt, tb = _pick_ab(cx, a, b)
    vs, vt = _nonempty_vertices(src), _nonempty_vertices(tgt)
    if not vs or not vt:
        return None
    v, w = cx.rng.choice(vs), cx.rng.choice(vt)
    return _put(a, b, _translate(tgt, _vec(w, v)), tb)


def mv_vertex_on_edge(cx, a, b, kind):
    src, tgt, tb = _pick_ab(cx, a, b)
    es, vt = edges(src), _nonempty_vertices(tgt)
    if not es or not vt:
        src, tgt, tb = tgt, src, not tb
        es, vt = edges(src), _nonempty_vertices(tgt)
        if not es or not vt:
            return None
    es = [e for e in es if math.gcd(abs(e[1][0] - e[0][0]), abs(e[1][1] - e[0][1])) > 1]
    if not es:
        return None
    p, q = cx.rng.choice(es)
    r = _lattice_point_on(cx, p, q)
    w = cx.rng.choice(vt)
    return _put(a, b, _translate(tgt, _vec(w, r)), tb)


def _unit(v):
    n = math.hypot(*v)
    return (v[0] / n, v[1] / n) if n else (1.0, 0.0)


def _replace_leaf_of_class(cx, g, cls, new):
    cands = [(p, leaf) for p, leaf in leaves(g) if leaf[0] == SINGLE[cls] and leaf[1]]
    if not cands:
        return None
    path, _ = cx.rng.choice(cands)
    return set_leaf(g, path, new)


def _leaf_classes(g):
    return {k for _, leaf in leaves(g) if leaf[1] for k, v in SINGLE.items() if v == leaf[0]}


def mv_collinear_overlap(cx, a, b, kind):
    rng = cx.rng
    src, tgt, tb = _pick_ab(cx, a, b)
    if not edges(src) or not (_leaf_classes(tgt) & {"L", "A"}):
        src, tgt, tb = tgt, src, not tb
        if not edges(src) or not (_leaf_classes(tgt) & {"L", "A"}):
            return None
    p, q = rng.choice(edges(src))
    dx, dy = q[0] - p[0], q[1] - p[1]
    g = math.gcd(abs(dx), abs(dy))
    if g == 0:
        return None
    d0 = (dx // g, dy // g)
    j1 = rng.randint(-max(1, g // 2), g - 1)
    j2 = rng.randint(max(j1 + 1, 1), g + max(1, g // 2))
    s = (p[0] + j1 * d0[0], p[1] + j1 * d0[1])
    t = (p[0] + j2 * d0[0], p[1] + j2 * d0[1])
    L = math.dist(s, t)
    n = _unit((-(t[1] - s[1]), t[0] - s[0]))
    side = rng.choice((-1, 1))
    h = L * rng.uniform(0.3, 1.0) * side
    mid = ((s[0] + t[0]) / 2, (s[1] + t[1]) / 2)
    cls = rng.choice(sorted(_leaf_classes(tgt) & {"L", "A"}))
    if cls == "A":
        new = ("Polygon", [[s, t, cx.snap((mid[0] + h * n[0], mid[1] + h * n[1]))]])
    else:
        pts = [s, t]
        dvec = _unit(_vec(s, t))
        for _ in range(rng.randint(0, 2)):
            last = pts[-1]
            ang = rng.uniform(-1.0, 1.0)
            dd = (dvec[0] * math.cos(ang) - dvec[1] * math.sin(ang),
                  dvec[0] * math.sin(ang) + dvec[1] * math.cos(ang))
            pts.append(cx.snap((last[0] + L * dd[0], last[1] + L * dd[1])))
        new = ("LineString", pts)
    out = _replace_leaf_of_class(cx, tgt, cls, new)
    return None if out is None else _put(a, b, out, tb)


def _poly_leaves(g):
    return [(p, leaf) for p, leaf in leaves(g) if leaf[0] == "Polygon" and leaf[1]]


def _pick_poly_target(cx, a, b):
    opts = [(g, isb) for g, isb in ((a, False), (b, True)) if _poly_leaves(g)]
    if not opts:
        return None
    return cx.rng.choice(opts)


def _centre(ring):
    return (sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring))


def mv_hole_tangent(cx, a, b, kind):
    rng = cx.rng
    pick = _pick_poly_target(cx, a, b)
    if pick is None:
        return None
    g, isb = pick
    path, poly = rng.choice(_poly_leaves(g))
    shell = poly[1][0]
    c = _centre(shell)
    v = rng.choice(shell)
    f = rng.uniform(0.3, 0.6)
    base = (v[0] + f * (c[0] - v[0]), v[1] + f * (c[1] - v[1]))
    n = _unit((-(c[1] - v[1]), c[0] - v[0]))
    off = f * math.dist(v, c) * rng.uniform(0.1, 0.3)
    hole = [v, cx.snap((base[0] + off * n[0], base[1] + off * n[1])),
            cx.snap((base[0] - off * n[0], base[1] - off * n[1]))]
    keep = poly[1] if rng.random() < 0.5 else [shell]
    new = ("Polygon", [list(r) for r in keep] + [hole])
    return _put(a, b, set_leaf(g, path, new), isb)


def _signed_area(ring):
    s = 0.0
    n = len(ring)
    for i in range(n):
        s += ring[i][0] * ring[(i + 1) % n][1] - ring[(i + 1) % n][0] * ring[i][1]
    return s / 2


def _lattice_step(direction):
    """Unit lattice vector most aligned with direction."""
    dx, dy = direction
    if abs(dx) >= abs(dy):
        return (1 if dx >= 0 else -1, 0)
    return (0, 1 if dy >= 0 else -1)


def mv_sliver_or_spike(cx, a, b, kind):
    rng = cx.rng
    if rng.random() < 0.5:
        # spike of width w out of a polygon shell edge
        pick = _pick_poly_target(cx, a, b)
        if pick is None:
            return None
        g, isb = pick
        path, poly = rng.choice(_poly_leaves(g))
        shell = list(poly[1][0])
        i = rng.randrange(len(shell))
        p, q = shell[i], shell[(i + 1) % len(shell)]
        e = _unit(_vec(p, q))
        out = (e[1], -e[0]) if _signed_area(shell) > 0 else (-e[1], e[0])
        L = math.dist(p, q) * rng.uniform(0.5, 2.0)
        m = cx.snap(((p[0] + q[0]) / 2, (p[1] + q[1]) / 2))
        st = _lattice_step(e)                       # width 1 unit
        m2 = (m[0] + st[0], m[1] + st[1])
        ap = (int(round(L * out[0])), int(round(L * out[1])))
        spike = [m, (m[0] + ap[0], m[1] + ap[1]), (m2[0] + ap[0], m2[1] + ap[1]), m2]
        shell[i + 1:i + 1] = spike
        new = ("Polygon", [shell] + [list(r) for r in poly[1][1:]])
        ng = set_leaf(g, path, new)
        return (a, ng) if isb else (ng, b)
    # sliver: a thin triangle on an edge of the other geometry replaces a polygon part
    pick = _pick_poly_target(cx, a, b)
    if pick is None:
        return None
    g, isb = pick
    other = a if isb else b
    es = edges(other) or edges(g)
    if not es:
        return None
    p, q = rng.choice(es)
    e = _unit(_vec(p, q))
    nrm = (-e[1], e[0]) if rng.random() < 0.5 else (e[1], -e[0])
    mid = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
    st = _lattice_step(nrm)                         # width about 1 unit
    m = cx.snap(mid)
    r = (m[0] + st[0], m[1] + st[1])
    new = ("Polygon", [[p, q, r]])
    path, _ = rng.choice(_poly_leaves(g))
    ng = set_leaf(g, path, new)
    return (a, ng) if isb else (ng, b)


def _rot(v, ang):
    return (v[0] * math.cos(ang) - v[1] * math.sin(ang), v[0] * math.sin(ang) + v[1] * math.cos(ang))


def mv_parts_touching(cx, a, b, kind):
    rng = cx.rng
    pick = _pick_poly_target(cx, a, b)
    if pick is None:
        return None
    g, isb = pick
    path, poly = rng.choice(_poly_leaves(g))
    shell = poly[1][0]
    c = _centre(shell)
    v = rng.choice(shell)
    o = _unit(_vec(c, v))
    L = math.dist(v, c) * rng.uniform(0.3, 0.8)
    al = math.radians(rng.uniform(15, 35))
    d1, d2 = _rot(o, al), _rot(o, -al)
    tri = ("Polygon", [[v, cx.snap((v[0] + L * d1[0], v[1] + L * d1[1])),
                        cx.snap((v[0] + L * d2[0], v[1] + L * d2[1]))]])
    t = g[0]
    if t == "Polygon":
        ng = ("MultiPolygon", [g, tri])
    elif t == "MultiPolygon":
        ng = (t, list(g[1]) + [tri])
    else:  # collection: add the touching part next to the polygon it touches
        ng = (t, list(g[1]) + [tri])
    return (a, ng) if isb else (ng, b)


def mv_empty_part(cx, a, b, kind):
    if kind != "predicate":
        return None
    rng = cx.rng
    isb = rng.random() < 0.5
    g = b if isb else a
    t, d = g
    if t.startswith("Multi"):
        child = {"MultiPoint": "Point", "MultiLineString": "LineString", "MultiPolygon": "Polygon"}[t]
        kids = list(d)
        kids.insert(rng.randint(0, len(kids)), (child, []))
        ng = (t, kids)
    elif t == "GeometryCollection":
        kids = list(d)
        kids.insert(rng.randint(0, len(kids)), (rng.choice(["Point", "LineString", "Polygon"]), []))
        ng = (t, kids)
    else:
        if rng.random() < 0.5:
            ng = (MULTI[[k for k, v in SINGLE.items() if v == t][0]], [g, (t, [])])
        else:
            ng = ("GeometryCollection", [g, (rng.choice(["Point", "LineString", "Polygon"]), [])])
    return (a, ng) if isb else (ng, b)


def mv_point_collection(cx, a, b, kind):
    if kind != "predicate":
        return None
    rng = cx.rng
    src, tgt, tb = _pick_ab(cx, a, b)
    vs = _nonempty_vertices(src)
    if not vs:
        return None
    es = edges(src)
    pts = []
    for _ in range(rng.randint(1, 3)):
        u = rng.random()
        p = None
        if u < 0.3 and es:
            e = rng.choice(es)
            p = _lattice_point_on(cx, *e)
        if p is None and u < 0.8:
            p = rng.choice(vs)
        if p is None:
            x0, y0, x1, y1 = bbox([src])
            p = cx.snap((rng.uniform(x0, x1), rng.uniform(y0, y1)))
        pts.append(("Point", [p]))
    return _put(a, b, ("GeometryCollection", pts), tb)


MOVE_FN = {
    "shared-vertex": mv_shared_vertex,
    "vertex-on-edge": mv_vertex_on_edge,
    "collinear-overlap": mv_collinear_overlap,
    "hole-tangent": mv_hole_tangent,
    "sliver-or-spike": mv_sliver_or_spike,
    "parts-touching": mv_parts_touching,
    "empty-part": mv_empty_part,
    "point-collection": mv_point_collection,
}


# --------------------------------------------------------------------------------------------
# Float regimes: maps of the plane applied identically to both geometries of a pair.
# Parameters are drawn from the regime stream and the *base* pair only, so plain-float and
# degen-float of one index use the same map. They are recorded in Pair.source, from which
# `regime_map` rebuilds the map.

REGIMES = ("affine", "rotation", "magnitude-1e15", "scale-2^-k")
MAX_REGIME_TRIES = 20


def _draw_regime(rng: random.Random, base_a, base_b) -> dict:
    name = rng.choice(REGIMES)
    x0, y0, x1, y1 = bbox([base_a, base_b])
    if name == "affine":
        # random non-dyadic factor and random full-precision offset
        return {"regime": name, "s": rng.uniform(0.5, 2.0),
                "ox": rng.uniform(-1e6, 1e6), "oy": rng.uniform(-1e6, 1e6)}
    if name == "rotation":
        return {"regime": name, "angle": rng.uniform(0, 2 * math.pi),
                "cx": (x0 + x1) / 2, "cy": (y0 + y1) / 2}
    if name == "magnitude-1e15":
        return {"regime": name, "ox": rng.uniform(1, 9) * 1e15, "oy": rng.uniform(1, 9) * 1e15}
    M = max(abs(x0), abs(y0), abs(x1), abs(y1))
    k = round(math.log2(M / (rng.uniform(1, 9) * 1e-8)))
    return {"regime": name, "k": k}


def _regime_fn(par: dict):
    name = par["regime"]
    if name == "affine":
        s, ox, oy = par["s"], par["ox"], par["oy"]
        return lambda p: (float(p[0]) * s + ox, float(p[1]) * s + oy)
    if name == "rotation":
        co, si = math.cos(par["angle"]), math.sin(par["angle"])
        cx_, cy_ = par["cx"], par["cy"]
        return lambda p: (cx_ + (p[0] - cx_) * co - (p[1] - cy_) * si,
                          cy_ + (p[0] - cx_) * si + (p[1] - cy_) * co)
    if name == "magnitude-1e15":
        ox, oy = par["ox"], par["oy"]
        return lambda p: (float(p[0]) + ox, float(p[1]) + oy)
    if name == "scale-2^-k":
        s = 2.0 ** -int(par["k"])          # exact for the integer base
        return lambda p: (float(p[0]) * s, float(p[1]) * s)
    raise ValueError(name)


def _source(forms, par: Optional[dict]) -> str:
    out = f"form={forms[0]}/{forms[1]}"
    if par is not None:
        out += ";" + ";".join(f"{k}={v if isinstance(v, (str, int)) else repr(v)}"
                              for k, v in par.items())
    return out


def parse_source(source: str) -> dict:
    return dict(kv.split("=", 1) for kv in source.split(";"))


def regime_map(source: str):
    """The plane map recorded in a float pair's source string (None for integer pairs)."""
    d = parse_source(source)
    if "regime" not in d:
        return None
    par = {"regime": d["regime"]}
    for k, v in d.items():
        if k not in ("regime", "form"):
            par[k] = int(v) if k == "k" else float(v)
    return _regime_fn(par)


def apply_regime(g, f):
    return map_coords(g, f)


# --------------------------------------------------------------------------------------------
# Pair generation (paired design).
#
# For each (seed, kind, index) one base pair is drawn; the four arms derive from it:
#   plain-int   = base
#   degen-int   = base + shape moves
#   plain-float = regime(base)
#   degen-float = regime(base + the same shape moves)
# Three RNG streams per index (base, moves, regime) keep these shared across arms.

FORMS = {"predicate": (("single", "multi", "collection"), (0.5, 0.3, 0.2)),
         "overlay": (("single", "multi"), (0.6, 0.4))}


def _rng_for(seed: int, kind: str, index: int, stream: str) -> random.Random:
    h = hashlib.sha256(f"tavs-gen|{seed}|{kind}|{index}|{stream}".encode()).digest()
    return random.Random(int.from_bytes(h[:16], "big"))


def _draw_valid(cx, st, who, cls, form, centre_fn, ext):
    for _ in range(MAX_BASE_TRIES):
        c = centre_fn()
        g = draw_shape(cx, cls, form, c, ext)
        if _in_range(g, cx.integral) and valid(g):
            return g
        st[f"resample_{who}"] += 1
    raise RuntimeError(f"could not draw a valid {cls}/{form} after {MAX_BASE_TRIES} tries")


def _base_pair(cx: Ctx, kind: str, st: Counter):
    rng = cx.rng
    mix = PRED_MIX if kind == "predicate" else OVER_MIX
    ca_, cb_ = rng.choices([(x, y) for x, y, _ in mix], weights=[w for *_, w in mix])[0]
    names, weights = FORMS[kind]
    fa, fb = rng.choices(names, weights=weights)[0], rng.choices(names, weights=weights)[0]
    ea = cx.loguniform(EXT_LO, EXT_HI)
    # ratio a:b log-uniform on [0.1, 10], truncated so that b's extent also stays in [10, 1000]
    rlo, rhi = max(RATIO_LO, ea / EXT_HI), min(RATIO_HI, ea / EXT_LO)
    eb = ea / cx.loguniform(rlo, rhi)

    def centre_in_range(ext):
        m = 1.5 * ext + 40
        return lambda: (rng.uniform(LO + m, HI - m), rng.uniform(LO + m, HI - m))

    a = _draw_valid(cx, st, "a", ca_, fa, centre_in_range(ea), ea)
    mb = 1.5 * eb + 40
    if rng.random() < P_NEAR:
        x0, y0, x1, y1 = bbox([a])
        w, h = x1 - x0, y1 - y0
        bx0, bx1 = x0 - w / 4, x1 + w / 4   # a's box expanded by half (1.5x about its centre)
        by0, by1 = y0 - h / 4, y1 + h / 4

        def cfn():
            return (min(max(rng.uniform(bx0, bx1), LO + mb), HI - mb),
                    min(max(rng.uniform(by0, by1), LO + mb), HI - mb))
        near = True
    else:
        cfn = centre_in_range(eb)
        near = False
    b = _draw_valid(cx, st, "b", cb_, fb, cfn, eb)
    return a, b, near, (fa, fb)


def _apply_moves(cx: Ctx, kind: str, a, b, st: Counter):
    rng = cx.rng
    pool = [m for m in GEOM_MOVES if kind == "predicate" or m not in PRED_ONLY_MOVES]
    want = rng.randint(1, 2)
    order = pool[:]
    rng.shuffle(order)
    chosen = []
    for m in order:
        if len(chosen) >= want:
            break
        for _ in range(MAX_MOVE_TRIES):
            r = MOVE_FN[m](cx, a, b, kind)
            if r is None:
                st[f"move_not_applicable:{m}"] += 1
                break
            na, nb = r
            if _in_range(na, True) and _in_range(nb, True) and valid(na) and valid(nb):
                a, b = na, nb
                chosen.append(m)
                break
            st[f"move_invalid_retry:{m}"] += 1
    return a, b, chosen


def _finite(g) -> bool:
    return all(math.isfinite(v) for p in vertices(g) for v in p)


def build(seed: int, kind: str, index: int) -> dict:
    """The four arm pairs of one index (keys: ARMS); depends only on (seed, kind, index)."""
    if kind not in KINDS:
        raise ValueError(kind)
    st = _stat(kind)
    st["pairs"] += 1
    a, b, near, forms = _base_pair(Ctx(_rng_for(seed, kind, index, "base"), True, st), kind, st)
    st["b_near"] += near
    da, db, moves = _apply_moves(Ctx(_rng_for(seed, kind, index, "moves"), True, st),
                                 kind, a, b, st)
    if not moves:
        st["degen_no_move"] += 1
    rrng = _rng_for(seed, kind, index, "regime")
    for _ in range(MAX_REGIME_TRIES):
        par = _draw_regime(rrng, a, b)
        fl = [apply_regime(g, _regime_fn(par)) for g in (a, b, da, db)]
        if all(_finite(g) and valid(g) for g in fl):
            break
        st[f"regime_retry:{par['regime']}"] += 1
    else:   # exact power-of-two scaling cannot break validity
        st["regime_fallback"] += 1
        par = {"regime": "scale-2^-k", "k": 40}
        fl = [apply_regime(g, _regime_fn(par)) for g in (a, b, da, db)]
    st[f"regime:{par['regime']}"] += 1
    common = dict(kind=kind, seed=seed, index=index)
    return {
        "plain-int": Pair(a=to_wkt(a), b=to_wkt(b), coord="int", arm="plain-int", moves=[],
                          source=_source(forms, None), **common),
        "plain-float": Pair(a=to_wkt(fl[0]), b=to_wkt(fl[1]), coord="float", arm="plain-float",
                            moves=[], source=_source(forms, par), **common),
        "degen-int": Pair(a=to_wkt(da), b=to_wkt(db), coord="int", arm="degen-int",
                          moves=list(moves), source=_source(forms, None), **common),
        "degen-float": Pair(a=to_wkt(fl[2]), b=to_wkt(fl[3]), coord="float", arm="degen-float",
                            moves=list(moves), source=_source(forms, par), **common),
    }


def make_pair(arm: str, seed: int, kind: str, index: int) -> Pair:
    """Pair `index` of arm `arm`; independent of the stream length."""
    if arm not in ARMS:
        raise ValueError(arm)
    return build(seed, kind, index)[arm]


def generate(arm: str, seed: int, n: int, kind: str) -> Iterator[Pair]:
    for i in range(n):
        yield make_pair(arm, seed, kind, i)


def generate_all(seed: int, n: int, kind: str) -> Iterator[dict]:
    """For each index, the four arm pairs together (dict keyed by arm)."""
    for i in range(n):
        yield build(seed, kind, i)


# --------------------------------------------------------------------------------------------
# Coincidence measurement (exact).

def _exact_on_segment(v, p, q) -> bool:
    """v strictly inside segment pq (not an endpoint), exact rational arithmetic."""
    vx, vy, px, py, qx, qy = (Fraction(t) for t in (*v, *p, *q))
    if (qx - px) * (vy - py) - (qy - py) * (vx - px) != 0:
        return False
    dot = (vx - px) * (qx - px) + (vy - py) * (qy - py)
    return 0 < dot < (qx - px) ** 2 + (qy - py) ** 2


def _near_collinear(V, P, Q):
    """Float filter: boolean matrix (len V x len P) where v may be collinear with segment pq."""
    if len(V) == 0 or len(P) == 0:
        return np.zeros((len(V), len(P)), bool)
    ex = (Q[:, 0] - P[:, 0])[None, :]
    ey = (Q[:, 1] - P[:, 1])[None, :]
    wx = V[:, 0][:, None] - P[:, 0][None, :]
    wy = V[:, 1][:, None] - P[:, 1][None, :]
    t1, t2 = ex * wy, ey * wx
    scale = (np.abs(t1) + np.abs(t2) + (np.abs(ex) + np.abs(ey)) * (np.abs(wx) + np.abs(wy))
             + np.abs(V).max(initial=0) * 1e-300)
    return np.abs(t1 - t2) <= 1e-12 * scale


def _vertex_on_edge_any(vs, es) -> bool:
    if not vs or not es:
        return False
    V = np.array(vs, float)
    P = np.array([e[0] for e in es], float)
    Q = np.array([e[1] for e in es], float)
    for i, j in zip(*np.nonzero(_near_collinear(V, P, Q))):
        if _exact_on_segment(vs[i], es[j][0], es[j][1]):
            return True
    return False


def _collinear_overlap_any(ea, eb) -> bool:
    if not ea or not eb:
        return False
    P = np.array([e[0] for e in ea], float)
    Q = np.array([e[1] for e in ea], float)
    S = np.array([e[0] for e in eb], float)
    T = np.array([e[1] for e in eb], float)
    cand = _near_collinear(S, P, Q).T & _near_collinear(T, P, Q).T   # (len ea, len eb)
    for i, j in zip(*np.nonzero(cand)):
        (p, q), (s, t) = ea[i], eb[j]
        px, py, qx, qy, sx, sy, tx, ty = (Fraction(v) for v in (*p, *q, *s, *t))
        ex, ey = qx - px, qy - py
        if ex * (sy - py) - ey * (sx - px) != 0 or ex * (ty - py) - ey * (tx - px) != 0:
            continue
        L2 = ex * ex + ey * ey
        if L2 == 0:
            continue
        u1 = ((sx - px) * ex + (sy - py) * ey) / L2
        u2 = ((tx - px) * ex + (ty - py) * ey) / L2
        lo, hi = max(min(u1, u2), 0), min(max(u1, u2), 1)
        if hi > lo:
            return True
    return False


def _self_touch(g) -> bool:
    """Two rings or parts of the same geometry share a point exactly (vertex-vertex or
    vertex-on-edge): tangent holes, touching parts, coincident collection members."""
    groups = []
    for _, s, closed in seqs(g):
        if not s:
            continue
        n = len(s)
        es = [(s[i], s[(i + 1) % n]) for i in range(n if closed else n - 1)]
        groups.append((s, es))
    for i in range(len(groups)):
        for j in range(len(groups)):
            if i == j:
                continue
            si, _ = groups[i]
            sj, ej = groups[j]
            if set(si) & set(sj):
                return True
            if _vertex_on_edge_any(si, ej):
                return True
    return False


def _strip_empty(g):
    t, d = g
    if is_multi(t):
        kids = [_strip_empty(c) for c in d if c[1]]
        return (t, [k for k in kids if k[1]])
    return g


def _near_dists(vs, other_vs, other_es):
    """Min distance from each vertex of `vs` to a vertex or edge of the other geometry over
    feature pairs that are NOT exact coincidences (equal vertices, vertex exactly inside an
    edge, vertex exactly equal to an edge endpoint). Returns an array, inf where none."""
    if not vs:
        return np.zeros(0)
    V = np.array(vs, float)
    best = np.full(len(vs), np.inf)
    if other_vs:
        W = np.array(other_vs, float)
        D = np.hypot(V[:, None, 0] - W[None, :, 0], V[:, None, 1] - W[None, :, 1])
        D[(V[:, None, 0] == W[None, :, 0]) & (V[:, None, 1] == W[None, :, 1])] = np.inf
        best = np.minimum(best, D.min(axis=1))
    if other_es:
        P = np.array([e[0] for e in other_es], float)
        Q = np.array([e[1] for e in other_es], float)
        ex, ey = (Q - P)[:, 0][None, :], (Q - P)[:, 1][None, :]
        wx, wy = V[:, 0][:, None] - P[:, 0][None, :], V[:, 1][:, None] - P[:, 1][None, :]
        L2 = ex * ex + ey * ey
        t = np.clip((wx * ex + wy * ey) / np.where(L2 > 0, L2, 1), 0, 1)
        D = np.hypot(wx - t * ex, wy - t * ey)
        endpoint = (((V[:, None, 0] == P[None, :, 0]) & (V[:, None, 1] == P[None, :, 1]))
                    | ((V[:, None, 0] == Q[None, :, 0]) & (V[:, None, 1] == Q[None, :, 1])))
        D[endpoint] = np.inf
        for i, j in zip(*np.nonzero(_near_collinear(V, P, Q) & ~endpoint)):
            if _exact_on_segment(vs[i], other_es[j][0], other_es[j][1]):
                D[i, j] = np.inf
        best = np.minimum(best, D.min(axis=1))
    return best


def pair_coincidences(p: Pair) -> dict:
    integral = p.coord == "int"
    ga, gb = from_wkt(p.a, integral), from_wkt(p.b, integral)
    va, vb = vertices(ga), vertices(gb)
    ea, eb = edges(ga), edges(gb)
    shared = bool(set(va) & set(vb))
    on_edge = _vertex_on_edge_any(va, eb) or _vertex_on_edge_any(vb, ea)
    collinear = _collinear_overlap_any(ea, eb)
    selft = _self_touch(ga) or _self_touch(gb)
    has_empty = any(not leaf[1] for g in (ga, gb) for _, leaf in leaves(g))
    # Relate on copies without EMPTY parts (same point sets): GEOS 3.14.1 relate crashes the
    # process on some collections with an EMPTY member (found 2026-10-27, degen-int #507).
    sa, sb = shapely.from_wkt(to_wkt(_strip_empty(ga))), shapely.from_wkt(to_wkt(_strip_empty(gb)))
    m = shapely.relate(sa, sb)
    ii, ib, bi, bb = m[0], m[1], m[3], m[4]
    inter = [c for c in (ii, ib, bi, bb) if c != "F"]
    touch0 = ii == "F" and bool(inter) and max(inter) == "0"
    M = max((abs(v) for q in va + vb for v in q), default=0.0)
    dmin = min(float(np.min(_near_dists(va, vb, eb), initial=np.inf)),
               float(np.min(_near_dists(vb, va, ea), initial=np.inf)))
    return {
        "near_rel_1e-9": dmin <= 1e-9 * M,
        "near_4ulp": dmin <= 4 * math.ulp(M),
        "shared_vertex": shared,
        "vertex_on_edge": on_edge,
        "collinear_overlap": collinear,
        "self_touch": selft,
        "bb_dim0": bb == "0",
        "touch_point_only": touch0,
        "intersects": bool(inter),
        "has_empty_part": has_empty,
        "any_exact": shared or on_edge or collinear or selft,
    }


def coincidence_stats(pairs: Iterable[Pair]) -> dict:
    """Rate of pairs showing each exact coincidence.

    shared_vertex      a vertex of a equals a vertex of b exactly
    vertex_on_edge     a vertex of one lies exactly in the interior of an edge of the other
    collinear_overlap  an edge of a and an edge of b overlap in a segment of positive length
    self_touch         rings/parts within one geometry share a point exactly
    bb_dim0            DE-9IM boundary/boundary cell is 0 (includes proper edge crossings)
    touch_point_only   interiors disjoint and the intersection is 0-dimensional
    any_exact          any of the first four
    near_rel_1e-9      some vertex within 1e-9*M of a vertex/edge of the other geometry,
                       M = max |coordinate| of the pair, exact coincidences excluded
    near_4ulp          the same within 4 ulp(M)
    """
    c = Counter()
    n = 0
    for p in pairs:
        n += 1
        for k, v in pair_coincidences(p).items():
            c[k] += bool(v)
    return {"n": n, **{k: c[k] / n if n else 0.0 for k in
                       ("shared_vertex", "vertex_on_edge", "collinear_overlap", "self_touch",
                        "any_exact", "near_rel_1e-9", "near_4ulp", "bb_dim0", "touch_point_only", "intersects",
                        "has_empty_part")}}


def type_signature(p: Pair) -> str:
    return f"{p.a.split(' ', 1)[0].split('(')[0]}/{p.b.split(' ', 1)[0].split('(')[0]}"
