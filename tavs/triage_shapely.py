"""GEOS-only check for E4 triage, in Shapely 2.2.0 (GEOS 3.14.1). Always run in a subprocess:
some findings crash GEOS itself (the RelateNG empty-ring crash), which would kill the caller.

  python -s -m tavs.triage_shapely <in.json> <out.json>

`in.json` holds {"mode": "check" | "crash", ...}. The result is written to `out.json`; a GEOS
segfault leaves no file and a non-zero exit code, which the caller records as a crash.

mode "check": recompute the violated sub-check with Shapely where an equivalent exists and
return {"applicable", "violated", "band", "detail", "fixed"}; "fixed" repeats an overlay check
with grid_size g (the R11 grid), the fixed-precision evidence for the precision-effect class.
mode "crash": call one Shapely function on (x, y) and return its value (a crash never returns).
"""

from __future__ import annotations

import json
import sys

import shapely

from .rules import LINE_COVER, band, matches, named_from_matrix, transpose

PRED = {"Contains": "contains", "Within": "within", "Covers": "covers",
        "CoveredBy": "covered_by", "Intersects": "intersects", "Disjoint": "disjoint",
        "Touches": "touches", "Equals": "equals"}
# PostGIS SQL function (as in rules.sql_functions / crash lists) -> Shapely function
CRASH_FN = {f"ST_{k}": v for k, v in PRED.items()}
CRASH_FN.update({"ST_Relate(matrix)": "relate", "ST_Relate(pattern)": "relate_pattern",
                 "ST_Intersection": "intersection", "ST_Union": "union",
                 "ST_Difference": "difference", "ST_SymDifference": "symmetric_difference"})


def _orient(a, b, o):
    return (b, a) if o == "ba" else (a, b)


def _parts(g):
    out = []
    for p in shapely.get_parts(g):
        if p.geom_type.startswith("Multi") or p.geom_type == "GeometryCollection":
            out += _parts(p)
        elif not p.is_empty:
            out.append(p)
    return out


def extract(g, dim: int):
    """ST_CollectionExtract(g, dim + 1): the parts of dimension `dim` as a multi geometry."""
    ps = [p for p in _parts(g) if shapely.get_dimensions(p) == dim]
    return {0: shapely.MultiPoint, 1: shapely.MultiLineString, 2: shapely.MultiPolygon}[dim](ps)


def _force_collection(g):
    if g.geom_type == "GeometryCollection":
        return g
    if g.geom_type.startswith("Multi"):
        return shapely.GeometryCollection(list(shapely.get_parts(g)))
    return shapely.GeometryCollection([g])


def _stats(a, b):
    xy = [c for c in (shapely.get_coordinates(a), shapely.get_coordinates(b)) if len(c)]
    if not xy:
        return 0.0, 0.0
    import numpy as np
    xy = np.vstack(xy)
    L = float(max(xy[:, 0].max() - xy[:, 0].min(), xy[:, 1].max() - xy[:, 1].min()))
    return L, float(abs(xy).max())


def _cover_band(cont, part, M):
    """Certified containment as in rules.cover_class: None (covered or noise), logged, triage."""
    if part.is_empty or shapely.covers(cont, part):
        return None
    if shapely.covers(shapely.buffer(cont, 1e-12 * M), part):
        return None
    return "logged" if shapely.covers(shapely.buffer(cont, 1e-9 * M), part) else "triage"


def _overlay_check(sub, rule, orientation, a, b, grid, payload):
    """One overlay rule (R5-R12) with overlays at grid_size `grid` (None = floating).
    Returns (violated, band, detail)."""
    L, M = _stats(a, b)
    d = int(shapely.get_dimensions(a))
    meas = (lambda g: g.area) if d == 2 else (lambda g: g.length)
    measure = "area" if d == 2 else "length"
    m_small = min(meas(a), meas(b))
    I = shapely.intersection(a, b, grid_size=grid)
    Iba = shapely.intersection(b, a, grid_size=grid)

    def U_():
        return shapely.union(a, b, grid_size=grid)

    def banded(mag):
        bd = band(abs(mag), measure, m_small, L, M)
        return bd == "triage", bd, {"magnitude": abs(mag), "measure": measure,
                                    "m_small": m_small, "L": L, "M": M}

    if rule == "R5":
        x, y = _orient(a, b, orientation)
        i = shapely.intersects(x, y)
        e = shapely.intersection(x, y, grid_size=grid).is_empty
        return i == e, None, {"intersects": bool(i), "intersection_empty": bool(e)}
    if rule == "R6":
        if sub.startswith("not IsEmpty"):
            U, Uba = U_(), shapely.union(b, a, grid_size=grid)
            v = (not a.is_empty) and (U.is_empty or Uba.is_empty)
            return v, None, {"union_empty": U.is_empty, "union_ba_empty": Uba.is_empty}
        fnm = payload["function"]
        op = shapely.intersection if fnm.startswith("Intersection") else shapely.union
        args = (b, a) if "(b,a" in fnm else (a, b)
        g = op(*args, grid_size=payload.get("grid") if fnm.endswith(",g)") else grid)
        return not g.is_valid, None, {"output_valid": bool(g.is_valid)}
    if rule in ("R7", "R8") and d == 1 and not sub.startswith("Covers("):
        U, Uba = U_(), shapely.union(b, a, grid_size=grid)
        names = {"a": a, "i_ab": I, "i_ba": Iba, "u_ab": U, "u_ba": Uba,
                 "ST_CollectionExtract(i_ab,2)": extract(I, 1),
                 "ST_CollectionExtract(i_ba,2)": extract(Iba, 1),
                 "ST_CollectionExtract(u_ab,2)": extract(U, 1),
                 "ST_CollectionExtract(u_ba,2)": extract(Uba, 1)}
        for r, s, _, _, cont, part, _ in LINE_COVER.values():
            if r == rule and s == sub:
                bd = _cover_band(names[cont], names[part], M)
                return bd == "triage", bd, {"method": "certified buffer containment"}
        return None, None, {"note": "line sub-check not found"}
    if rule == "R7":
        if sub.startswith("Covers("):
            s = a if sub.startswith("Covers(a") else b
            t = int(sub.rsplit("type", 1)[1].strip(" )"))
            part = extract(I, t - 1)
            bd = _cover_band(s, part, M)
            return bd == "triage", bd, {"part_empty": part.is_empty}
        ct = d
        if sub == "measure(Difference(I,a))":
            return banded(meas(shapely.difference(extract(I, ct), a, grid_size=grid)))
        U = U_()
        return banded(meas(shapely.difference(a, extract(U, ct), grid_size=grid)))
    if rule == "R8":
        if sub.startswith("SymDifference(I"):
            return banded(meas(shapely.symmetric_difference(I, Iba, grid_size=grid)))
        U, Uba = U_(), shapely.union(b, a, grid_size=grid)
        return banded(meas(shapely.symmetric_difference(U, Uba, grid_size=grid)))
    if rule == "R9":
        U = U_()
        return banded(meas(U) - meas(a) - meas(b) + meas(I))
    if rule == "R10":
        if sub.startswith("dim(Intersection)"):
            if I.is_empty:
                return False, None, {"intersection_empty": True}
            mtx = shapely.relate(a, b)
            exp = max(-1 if c == "F" else int(c) for c in (mtx[0], mtx[1], mtx[3], mtx[4]))
            di = int(shapely.get_dimensions(I))
            return di != exp, None, {"dim_intersection": di, "matrix": mtx}
        U = U_()
        du = int(shapely.get_dimensions(U))
        exp = max(int(shapely.get_dimensions(a)), int(shapely.get_dimensions(b)))
        return du != exp, None, {"dim_union": du}
    if rule == "R11":
        g = payload.get("grid")
        if g is None:
            return None, None, {"note": "no grid"}
        op = shapely.intersection if sub.startswith("Intersection") else shapely.union
        return banded(meas(op(a, b)) - meas(op(a, b, grid_size=g)))
    if rule in ("R12f", "R12g"):
        pts = payload.get("points") or []
        if not pts:
            return None, None, {"note": "no violating points from the PostGIS re-run"}
        key = "I" if "Intersects(p,I)" in sub else "U"
        res = extract(I, 2) if key == "I" else extract(U_(), 2)
        bad = []
        for p in pts:                       # PostGIS raw points: {"x", "y", "a", "b", ...}
            P = shapely.Point(p["x"], p["y"]) if isinstance(p, dict) else shapely.Point(p[0], p[1])
            ia, ib, ir = shapely.intersects(P, a), shapely.intersects(P, b), shapely.intersects(P, res)
            if ir != ((ia and ib) if key == "I" else (ia or ib)):
                bad.append(p)
        return bool(bad), None, {"points_checked": len(pts), "points_bad": len(bad)}
    return None, None, {"note": f"no Shapely check for {rule}"}


def check(p: dict) -> dict:
    rule, sub, fn, o = p["rule"], p["sub"], p["function"], p.get("orientation")
    a, b = shapely.from_wkt(p["a"]), shapely.from_wkt(p["b"])
    out = {"applicable": True, "violated": None, "band": None, "detail": {}, "fixed": None,
           "shapely": shapely.__version__, "geos": shapely.geos_version_string}
    x, y = _orient(a, b, o)
    if rule == "R1":
        P = sub.split(" vs ")[0]
        mtx = shapely.relate(x, y)
        got = bool(getattr(shapely, PRED[P])(x, y))
        exp = named_from_matrix(P, mtx)
        out.update(violated=got != exp, detail={"named": got, "matrix": mtx, "matrix_match": exp})
        return out
    if rule == "R2":
        def v(P, o2):
            g1, g2 = _orient(a, b, o2)
            return bool(getattr(shapely, PRED[P])(g1, g2))
        det = {}
        if sub == "Relate transpose":
            r1, r2 = shapely.relate(a, b), shapely.relate(b, a)
            det, bad = {"rel_ab": r1, "rel_ba": r2}, transpose(r1) != r2
        elif sub.endswith(" symmetric"):
            P = sub.split()[0]
            det = {"ab": v(P, "ab"), "ba": v(P, "ba")}
            bad = det["ab"] != det["ba"]
        elif "=>" in sub and "<=>" not in sub:
            P, Q = sub.split("=>")
            det = {P: v(P, o), Q: v(Q, o)}
            bad = det[P] and not det[Q]
        elif sub == "Disjoint<=>not Intersects":
            det = {"Disjoint": v("Disjoint", o), "Intersects": v("Intersects", o)}
            bad = det["Disjoint"] == det["Intersects"]
        else:                                   # P(x,y)<=>Q(y,x)
            P, Q = sub.split("(x,y)<=>")[0], sub.split("<=>")[1].split("(")[0]
            oo = "ba" if o == "ab" else "ab"
            det = {P: v(P, o), Q: v(Q, oo)}
            bad = det[P] != det[Q]
        out.update(violated=bool(bad), detail=det)
        return out
    if rule == "R3":
        if sub == "lone vs index join":
            out.update(applicable=False, detail={"note": "index join is a PostGIS-only path; "
                                                 "GEOS sees the same lone call"})
            return out
        if fn.startswith("Relate '"):
            pat = fn.split("'")[1]
            mtx = shapely.relate(x, y)
            exp = matches(mtx, pat)
            un = bool(shapely.relate_pattern(x, y, pat))
            det = {"matrix": mtx, "matrix_match": exp, "relate_pattern": un}
            if "prepared" in sub:
                xp = shapely.from_wkt(shapely.to_wkt(x))
                shapely.prepare(xp)
                det["relate_pattern_prepared_x"] = bool(shapely.relate_pattern(xp, y, pat))
                det["note"] = "Shapely's relate_pattern may not take GEOS's prepared path"
                out.update(violated=det["relate_pattern_prepared_x"] != exp, detail=det)
            else:
                out.update(violated=un != exp, detail=det)
            return out
        f = getattr(shapely, PRED[fn])
        un = bool(f(x, y))
        if "prepared arg1" in sub:
            xp = shapely.from_wkt(p["a"] if o != "ba" else p["b"])
            shapely.prepare(xp)
            pr = bool(f(xp, y))
            how = "prepare(x); P(x, y)"
        else:                                   # prepared arg2: GEOS prepares the 2nd arg
            yp = shapely.from_wkt(p["b"] if o != "ba" else p["a"])
            shapely.prepare(yp)
            if fn == "Within":
                pr, how = bool(shapely.contains(yp, x)), "prepare(y); Contains(y, x)"
            else:
                pr, how = bool(f(yp, x)), f"prepare(y); {fn}(y, x) (symmetric)"
        out.update(violated=un != pr, detail={"unprepared": un, "prepared": pr, "how": how})
        return out
    if rule == "R4":
        if fn == "Relate":
            base = shapely.relate(x, y)
            w = (shapely.relate(_force_collection(x), y) if "arg1" in sub
                 else shapely.relate(x, _force_collection(y)))
        else:
            f = getattr(shapely, PRED[fn])
            base = bool(f(x, y))
            w = bool(f(_force_collection(x), y) if "arg1" in sub else f(x, _force_collection(y)))
        out.update(violated=base != w, detail={"lone": base, "wrapped": w})
        return out
    # overlay rules
    vio, bd, det = _overlay_check(sub, rule, o, a, b, None, p)
    out.update(violated=vio, band=bd, detail=det, applicable=vio is not None)
    g = p.get("grid")
    if g and rule not in ("R11",):
        try:
            fv, fb, fd = _overlay_check(sub, rule, o, a, b, g, p)
            out["fixed"] = {"grid": g, "violated": fv, "band": fb, "detail": fd}
        except Exception as exc:  # noqa: BLE001
            out["fixed"] = {"grid": g, "error": f"{type(exc).__name__}: {exc}"}
    return out


def crash_call(p: dict) -> dict:
    fn = p["shapely_fn"]
    x, y = shapely.from_wkt(p["x"]), shapely.from_wkt(p["y"])
    if p.get("prepared"):
        shapely.prepare(x)
    if fn == "relate_pattern":
        r = shapely.relate_pattern(x, y, p.get("pattern") or "T*****FF*")
    else:
        r = getattr(shapely, fn)(x, y)
    return {"value": r if isinstance(r, (bool, str)) else (
        bool(r) if fn in PRED.values() else shapely.to_wkt(r)[:200])}


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    src, dst = argv
    with open(src, encoding="utf-8") as fh:
        p = json.load(fh)
    try:
        res = crash_call(p) if p["mode"] == "crash" else check(p)
    except Exception as exc:  # noqa: BLE001 - a Python/GEOS exception is a result, not a crash
        res = {"error": f"{type(exc).__name__}: {exc}"}
    with open(dst, "w", encoding="utf-8") as fh:
        json.dump(res, fh, default=lambda o: bool(o) if hasattr(o, "dtype") else str(o))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
