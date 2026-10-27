"""Consistency rules R1-R11 (experiment-plan.md, section "Rules").

`evaluate(target, pair)` gathers values with a few statements and returns violations and
outcomes:

- lone statement: named predicates both ways, `ST_Relate` matrices both ways, wrappers (R4),
  lone pattern calls, input dimension/emptiness/validity;
- R3 prepared shapes, one statement per shape and orientation:
  (b) `SELECT array_agg(ST_P($1,g) ORDER BY o) FROM unnest(ARRAY[$2,$2,$2]) WITH ORDINALITY t(g,o)`
  (c) the same with roles swapped, `ST_P(g,$1)`, for Intersects, Touches, Disjoint, Within and
      Relate-pattern only;
  (d) `batch_index_join(target, pairs)`: one GiST index join per batch (call it once per seed);
- overlay statement: intersections, unions (both orders), fixed-precision overlays, and the
  measures R5-R11 need.

Every predicate rule is checked in both orientations, (a,b) and (b,a); `orientation` records
which. DE-9IM pattern matching is done in Python. A failed statement is retried expression by
expression so that one failing overlay does not hide the others; failures become outcomes.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Optional

import shapely

from .db import Target, classify_error
from .pair import Pair

PREDICATES = ["Contains", "Within", "Covers", "CoveredBy", "Intersects", "Disjoint", "Touches",
              "Equals"]
# R3 reachability from PostGIS 3.6.4 (94d984b) postgis/lwgeom_geos_predicates.c:
# GetPrepGeomCache(fcinfo, g1, g2) receives g1 in Intersects (l.137), Touches (260),
# Disjoint (324), Contains (542), Covers (768), CoveredBy (852; its prepared branch needs
# argnum == 2 at l.853, so it is dead code) and relate_pattern (928); it receives g2 in
# Intersects, Touches, Disjoint, Within (623, g1 = NULL) and relate_pattern. Equals never
# calls the cache. (Overlaps and Crosses also pass both, but are not in the plan's list.)
PREP_ARG1 = ["Contains", "Covers", "CoveredBy", "Intersects", "Disjoint", "Touches"]  # R3 (b)
PREP_ARG2 = ["Intersects", "Touches", "Disjoint", "Within"]                          # R3 (c)
# ST_Disjoint has no index support function (pg_proc.prosupport is '-'), so it cannot be
# served by the GiST index and stays out of the index join.
INDEXED = ["Contains", "Within", "Covers", "CoveredBy", "Intersects", "Touches", "Equals"]
ORIENTATIONS = {"ab": ("a", "b"), "ba": ("b", "a")}


def transpose(m: str) -> str:
    """Transpose a DE-9IM matrix or pattern: swap cells 1<->3, 2<->6, 5<->7 (0-based)."""
    s = list(m)
    for i, j in ((1, 3), (2, 6), (5, 7)):
        s[i], s[j] = s[j], s[i]
    return "".join(s)


def matches(matrix: str, pattern: str) -> bool:
    for m, p in zip(matrix.upper(), pattern.upper()):
        if p == "*":
            continue
        if p == "T":
            if m not in "012":
                return False
        elif p == "F":
            if m != "F":
                return False
        elif m != p:
            return False
    return True


_COVERS = ["T*****FF*", "*T****FF*", "***T**FF*", "****T*FF*"]
PATTERNS: dict[str, list[str]] = {
    "Contains": ["T*****FF*"],
    "Within": ["T*F**F***"],
    "Covers": _COVERS,
    "CoveredBy": [transpose(p) for p in _COVERS],
    "Disjoint": ["FF*FF****"],
    "Touches": ["FT*******", "F**T*****", "F***T****"],
    "Equals": ["T*F**FFF*"],
}
# Intersects is "not FF*FF****". Relate-pattern calls use every distinct pattern above.
REL_PATTERNS: list[str] = sorted({p for ps in PATTERNS.values() for p in ps})


def named_from_matrix(pred: str, matrix: str) -> bool:
    if pred == "Intersects":
        return not matches(matrix, "FF*FF****")
    return any(matches(matrix, p) for p in PATTERNS[pred])


# --------------------------------------------------------------------------------------------
@dataclass
class Violation:
    rule: str
    sub: str
    function: str
    paths: str                      # the two paths/values compared
    orientation: Optional[str]      # ab, ba or None
    tier: str                       # strict | candidate
    magnitude: Optional[float] = None
    band: Optional[str] = None      # logged | triage (measure rules)
    precision_limited: bool = False
    raw: dict = field(default_factory=dict)


@dataclass
class Outcome:
    stage: str                      # lone | prep_b_ab | ... | overlay:<expr> | batch | skip
    kind: str                       # overlay_error | sql_error | timeout | other_error | skipped
    message: str


@dataclass
class Evaluation:
    pair: Pair
    target: str
    violations: list[Violation] = field(default_factory=list)
    outcomes: list[Outcome] = field(default_factory=list)
    rules_run: list[str] = field(default_factory=list)
    seconds: dict[str, float] = field(default_factory=dict)
    info: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------------------------
# Tolerance (plan, "Tolerance")

def band(m: float, measure: str, m_small: float, L: float, M: float) -> Optional[str]:
    scale = L * M if measure == "area" else M
    if m <= max(1e-9 * m_small, 1e-12 * scale):
        return None                 # noise: not a violation
    if m <= max(1e-6 * m_small, 1e-9 * scale):
        return "logged"
    return "triage"


def precision_limited(measure: str, m_small: Optional[float], L: float, M: float) -> bool:
    if m_small is None:
        return False
    scale = L * M if measure == "area" else M
    return 1e-9 * scale >= m_small


def coord_stats(pair: Pair) -> dict:
    """L = largest side of the pair's union box, M = max |coordinate| (from Shapely)."""
    ga, gb = shapely.from_wkt(pair.a), shapely.from_wkt(pair.b)
    coords = [c for c in (shapely.get_coordinates(ga), shapely.get_coordinates(gb)) if len(c)]
    if not coords:
        return {"L": 0.0, "M": 0.0, "types": (ga.geom_type, gb.geom_type)}
    import numpy as np
    xy = np.vstack(coords)
    L = float(max(xy[:, 0].max() - xy[:, 0].min(), xy[:, 1].max() - xy[:, 1].min()))
    M = float(np.abs(xy).max())
    return {"L": L, "M": M, "types": (ga.geom_type, gb.geom_type)}


def _is_point_polygon(types: tuple[str, str]) -> bool:
    pts, polys = {"Point", "MultiPoint"}, {"Polygon", "MultiPolygon"}
    return (types[0] in pts and types[1] in polys) or (types[0] in polys and types[1] in pts)


# --------------------------------------------------------------------------------------------
# SQL helpers

_HEAD = ("WITH g AS MATERIALIZED (SELECT ST_GeomFromText(%(a)s) a, ST_GeomFromText(%(b)s) b), "
         "o AS MATERIALIZED (SELECT {cols} FROM g) ")


def _select(bases: dict[str, str], exprs: dict[str, str]) -> str:
    cols = ", ".join(["a", "b"] + [f"{sql} AS {name}" for name, sql in bases.items()])
    sel = ", ".join(f"{sql} AS {name}" for name, sql in exprs.items())
    return _HEAD.format(cols=cols) + f"SELECT {sel} FROM o"


def _deps(sql: str, bases: dict[str, str]) -> dict[str, str]:
    return {n: s for n, s in bases.items() if re.search(rf"\b{n}\b", sql)}


def run_exprs(target: Target, pair: Pair, bases: dict[str, str], exprs: dict[str, str],
              stage: str, ev: Evaluation) -> dict[str, Any]:
    """Evaluate named expressions in one statement; on failure, one statement per expression
    (with only the bases it needs). Failures are recorded as outcomes; missing values absent."""
    params = {"a": pair.a, "b": pair.b}
    r = target.run(_select(bases, exprs), params)
    ev.seconds[stage] = ev.seconds.get(stage, 0.0) + r.seconds
    if r.ok:
        return dict(zip(exprs, r.one()))
    if r.error == "crash":
        ev.outcomes.append(Outcome(stage, "crash", r.message or ""))
        ev.info["crashed"] = stage
        return {}
    ev.outcomes.append(Outcome(stage, "statement_retry", f"{r.error}; retrying per expression: "
                                               f"{r.message}"))
    values: dict[str, Any] = {}
    failed_msgs: dict[str, str] = {}
    for name, sql in exprs.items():
        rr = target.run(_select(_deps(sql, bases), {name: sql}), params)
        ev.seconds[stage] += rr.seconds
        if rr.error == "crash":
            ev.outcomes.append(Outcome(f"{stage}:{name}", "crash", rr.message or ""))
            ev.info["crashed"] = f"{stage}:{name}"
            return values
        if rr.ok:
            values[name] = rr.one()[0]
        else:
            failed_msgs[name] = f"{rr.error}: {rr.message}"
            ev.outcomes.append(Outcome(f"{stage}:{name}", rr.error, rr.message or ""))
    return values


# --------------------------------------------------------------------------------------------
# Statements

def _lone_exprs() -> dict[str, str]:
    e = {"dim_a": "ST_Dimension(a)", "dim_b": "ST_Dimension(b)",
         "empty_a": "ST_IsEmpty(a)", "empty_b": "ST_IsEmpty(b)",
         "valid_a": "ST_IsValid(a)", "valid_b": "ST_IsValid(b)",
         # R3 (c) needs ST_Reverse(x) to differ bytewise from x
         "revsame_a": "ST_AsEWKB(ST_Reverse(a)) = ST_AsEWKB(a)",
         "revsame_b": "ST_AsEWKB(ST_Reverse(b)) = ST_AsEWKB(b)"}
    for o, (x, y) in ORIENTATIONS.items():
        e[f"rel_{o}"] = f"ST_Relate({x},{y})"
        e[f"wrel1_{o}"] = f"ST_Relate(ST_ForceCollection({x}),{y})"
        e[f"wrel2_{o}"] = f"ST_Relate({x},ST_ForceCollection({y}))"
        for p in PREDICATES:
            e[f"lone_{p}_{o}"] = f"ST_{p}({x},{y})"
            e[f"w1_{p}_{o}"] = f"ST_{p}(ST_ForceCollection({x}),{y})"
            e[f"w2_{p}_{o}"] = f"ST_{p}({x},ST_ForceCollection({y}))"
        for i, pat in enumerate(REL_PATTERNS):
            e[f"pat{i}_{o}"] = f"ST_Relate({x},{y},'{pat}')"
    return e


LONE_EXPRS = _lone_exprs()


def _prep_sql(shape: str) -> tuple[str, list[str]]:
    """R3 (b) prepared arg1: SELECT array_agg(ST_P($1,g) ORDER BY o)
         FROM unnest(ARRAY[$2,$2,$2]) WITH ORDINALITY t(g,o)  ($1 = %(c)s = x, $2 = %(r)s = y)
    R3 (c) prepared arg2: SELECT array_agg(ST_P(g,$2) ORDER BY o)
         FROM unnest(ARRAY[ST_Reverse($1),$1,$1]) WITH ORDINALITY t(g,o)  ($1 = %(r)s = x,
         $2 = %(c)s = y). Call 1 misses and stores both args; call 2 differs bytewise in arg1
         and hits arg2, so y is prepared; call 3 uses the prepared y (lwgeom_cache.c l.124-130:
         the arg1 hit is tested first, so with both args repeating (b) would prepare arg1)."""
    names, cols = [], []
    preds = PREP_ARG1 if shape == "b" else PREP_ARG2
    for p in preds:
        call = f"ST_{p}(%(c)s::geometry, g)" if shape == "b" else f"ST_{p}(g, %(c)s::geometry)"
        cols.append(f"array_agg({call} ORDER BY o)")
        names.append(p)
    for i, pat in enumerate(REL_PATTERNS):
        call = (f"ST_Relate(%(c)s::geometry, g, '{pat}')" if shape == "b"
                else f"ST_Relate(g, %(c)s::geometry, '{pat}')")
        cols.append(f"array_agg({call} ORDER BY o)")
        names.append(f"pat{i}")
    first = "%(r)s::geometry" if shape == "b" else "ST_Reverse(%(r)s::geometry)"
    sql = (f"SELECT {', '.join(cols)} FROM unnest(ARRAY[{first},%(r)s::geometry,"
           f"%(r)s::geometry]) WITH ORDINALITY t(g,o)")
    return sql, names


PREP_SQL = {s: _prep_sql(s) for s in ("b", "c")}


def _overlay_exprs(d: int, grid: Optional[float], with_r5_only: bool) -> tuple[dict, dict]:
    bases = {"i_ab": "ST_Intersection(a,b)", "i_ba": "ST_Intersection(b,a)"}
    exprs = {"e_iab": "ST_IsEmpty(i_ab)", "e_iba": "ST_IsEmpty(i_ba)"}
    if with_r5_only:
        return bases, exprs
    ct = 3 if d == 2 else 2
    meas = "ST_Area" if d == 2 else "ST_Length"
    bases.update({"u_ab": "ST_Union(a,b)", "u_ba": "ST_Union(b,a)"})
    if grid is not None:
        bases.update({"if_ab": f"ST_Intersection(a,b,{grid!r})",
                      "uf_ab": f"ST_Union(a,b,{grid!r})"})
    exprs.update({
        "e_uab": "ST_IsEmpty(u_ab)", "e_uba": "ST_IsEmpty(u_ba)",
        "v_iab": "ST_IsValid(i_ab)", "v_iba": "ST_IsValid(i_ba)",
        "v_uab": "ST_IsValid(u_ab)", "v_uba": "ST_IsValid(u_ba)",
        "dim_iab": "ST_Dimension(i_ab)", "dim_uab": "ST_Dimension(u_ab)",
        "t_iab": "left(ST_AsText(i_ab), 400)", "t_uab": "left(ST_AsText(u_ab), 400)",
        "m_a": f"{meas}(a)", "m_b": f"{meas}(b)",
        "m_iab": f"{meas}(i_ab)", "m_iba": f"{meas}(i_ba)",
        "m_uab": f"{meas}(u_ab)", "m_uba": f"{meas}(u_ba)",
        "r7_ia": f"{meas}(ST_Difference(ST_CollectionExtract(i_ab,{ct}), a))",
        "r7_au": f"{meas}(ST_Difference(a, ST_CollectionExtract(u_ab,{ct})))",
        "r8_i": f"{meas}(ST_SymDifference(i_ab, i_ba))",
        "r8_u": f"{meas}(ST_SymDifference(u_ab, u_ba))",
    })
    if d == 1:                      # R9 applies to lines only when both are simple
        exprs.update({"simple_a": "ST_IsSimple(a)", "simple_b": "ST_IsSimple(b)"})
    for t in range(1, ct):          # lower-dimensional parts of the intersection
        part = f"ST_CollectionExtract(i_ab,{t})"
        exprs[f"lp{t}_txt"] = f"CASE WHEN ST_IsEmpty({part}) THEN NULL ELSE left(ST_AsText({part}),400) END"
        exprs[f"lp{t}_a"] = f"CASE WHEN ST_IsEmpty({part}) THEN NULL ELSE ST_Covers(a,{part}) END"
        exprs[f"lp{t}_b"] = f"CASE WHEN ST_IsEmpty({part}) THEN NULL ELSE ST_Covers(b,{part}) END"
        # magnitude: max distance from the part's vertices to a (to b)
        for side in ("a", "b"):
            exprs[f"lp{t}_d{side}"] = (f"(SELECT max(ST_Distance((dp).geom, {side})) "
                                       f"FROM ST_DumpPoints({part}) dp)")
    if grid is not None:
        exprs.update({"v_ifab": "ST_IsValid(if_ab)", "v_ufab": "ST_IsValid(uf_ab)",
                      "m_ifab": f"{meas}(if_ab)", "m_ufab": f"{meas}(uf_ab)"})
    return bases, exprs


# --------------------------------------------------------------------------------------------
# R3 (d): batch index join

class _BatchCrash(Exception):
    pass


def batch_index_join(target: Target, pairs: list[Pair], explain: bool = False) -> dict:
    """Run each indexed predicate as one GiST index join over all `pairs` (both orientations),
    with enable_seqscan=off. Returns {"results": {i: {(P, o): bool}}, "errors": [...],
    "plan": EXPLAIN JSON or None, "index_used": bool or None, "seconds": float}.
    Pairs are identified by their position i in `pairs`; EMPTY geometries are included."""
    import time
    out: dict = {"results": {i: {} for i in range(len(pairs))}, "errors": [], "plan": None,
                 "index_used": None, "seconds": 0.0, "failed_rows": []}
    t0 = time.perf_counter()
    try:
        conn = target.connect()
        conn.execute("DROP TABLE IF EXISTS tavs_bx, tavs_by")
        conn.execute("CREATE TEMP TABLE tavs_bx (id int, a geometry, b geometry)")
        conn.execute("CREATE TEMP TABLE tavs_by (id int, a geometry, b geometry)")
        for i, p in enumerate(pairs):
            try:
                for t in ("tavs_bx", "tavs_by"):
                    conn.execute(f"INSERT INTO {t} VALUES (%s, ST_GeomFromText(%s), "
                                 f"ST_GeomFromText(%s))", (i, p.a, p.b))
            except Exception as exc:  # noqa: BLE001
                out["failed_rows"].append((i, classify_error(exc), str(exc)[:500]))
        conn.execute("CREATE INDEX ON tavs_by USING gist (a)")
        conn.execute("CREATE INDEX ON tavs_by USING gist (b)")
        conn.execute("ANALYZE tavs_bx")
        conn.execute("ANALYZE tavs_by")
        conn.execute("SET enable_seqscan = off")
        try:
            for p in INDEXED:
                for o, (x, y) in ORIENTATIONS.items():
                    q = (f"SELECT x.id FROM tavs_bx x JOIN tavs_by y "
                         f"ON ST_{p}(x.{x}, y.{y}) WHERE x.id = y.id")
                    if explain and out["plan"] is None:
                        plan = conn.execute(f"EXPLAIN (ANALYZE, FORMAT JSON) {q}").fetchone()[0]
                        out["plan"] = {"query": q, "plan": plan}
                        txt = str(plan)
                        out["index_used"] = ("Index Scan" in txt or "Index Only Scan" in txt
                                             or "Bitmap Index Scan" in txt) and "tavs_by" in txt
                    try:
                        hit = {row[0] for row in conn.execute(q).fetchall()}
                    except Exception as exc:  # noqa: BLE001
                        kind = classify_error(exc)
                        out["errors"].append((p, o, kind, f"{str(exc)[:500]} | statement: {q}"))
                        if kind == "crash":
                            raise _BatchCrash() from exc
                        continue
                    for i in out["results"]:
                        out["results"][i][(p, o)] = i in hit
        finally:
            try:
                conn.execute("RESET enable_seqscan")
                conn.execute("DROP TABLE IF EXISTS tavs_bx, tavs_by")
            except Exception:  # noqa: BLE001 - connection lost; temp tables died with it
                pass
    except _BatchCrash:
        out["crashed"] = True
    except Exception as exc:  # noqa: BLE001
        kind = classify_error(exc)
        out["errors"].append(("*", "*", kind, str(exc)[:500]))
        out["crashed"] = kind == "crash"
    if out.get("crashed"):
        # the index join is abandoned for this batch (results kept for joins already done)
        target.close_quietly()
        target.wait_ready()
    failed = {i for i, *_ in out["failed_rows"]}
    for i in failed:
        out["results"][i] = {}
    out["seconds"] = time.perf_counter() - t0
    return out


# --------------------------------------------------------------------------------------------

def evaluate(target: Target, pair: Pair, batch: Optional[dict] = None) -> Evaluation:
    """Run every applicable rule on one pair. `batch` is this pair's entry from
    `batch_index_join(...)["results"]` (R3 (d)); omit it to skip the index-join path."""
    ev = Evaluation(pair=pair, target=target.name)
    tier = "strict" if pair.coord == "int" else "candidate"
    try:
        cs = coord_stats(pair)
    except Exception as exc:  # noqa: BLE001
        ev.outcomes.append(Outcome("parse", "other_error", f"Shapely could not parse: {exc}"))
        return ev
    L, M, types = cs["L"], cs["M"], cs["types"]
    pip = _is_point_polygon(types)
    path_label = "point-in-polygon" if pip else None
    ev.info.update({"L": L, "M": M, "types": types})

    def V(rule, sub, fn, paths, o, t=tier, raw=None, **kw):
        r = dict(raw or {})
        if path_label:
            r["path_label"] = path_label
        ev.violations.append(Violation(rule, sub, fn, paths, o, t, raw=r, **kw))

    # ---- lone statement --------------------------------------------------------------------
    lv = run_exprs(target, pair, {}, LONE_EXPRS, "lone", ev)
    if ev.info.get("crashed"):
        return ev                   # backend crash: record it and move on to the next pair
    any_empty = bool(lv.get("empty_a")) or bool(lv.get("empty_b"))
    both_nonempty = lv.get("empty_a") is False and lv.get("empty_b") is False
    ev.info.update({k: lv.get(k) for k in ("dim_a", "dim_b", "empty_a", "empty_b",
                                            "valid_a", "valid_b", "rel_ab", "rel_ba")})

    # R1: named predicate (lone) vs Python match on the lone matrix
    ev.rules_run.append("R1")
    for o in ORIENTATIONS:
        mtx = lv.get(f"rel_{o}")
        if mtx is None:
            continue
        for p in PREDICATES:
            if p == "Equals" and not both_nonempty:
                continue
            got = lv.get(f"lone_{p}_{o}")
            if got is None:
                continue
            exp = named_from_matrix(p, mtx)
            if got != exp:
                V("R1", f"{p} vs matrix", p, "lone call vs ST_Relate matrix match", o,
                  raw={"lone": got, "matrix": mtx, "matrix_match": exp})

    # R2: logic
    ev.rules_run.append("R2")

    def g(p, o):
        return lv.get(f"lone_{p}_{o}")

    for o in ORIENTATIONS:
        c, cv, i = g("Contains", o), g("Covers", o), g("Intersects", o)
        if c is True and cv is False:
            V("R2", "Contains=>Covers", "Contains/Covers", "lone vs lone", o,
              raw={"Contains": c, "Covers": cv})
        if cv is True and i is False:
            V("R2", "Covers=>Intersects", "Covers/Intersects", "lone vs lone", o,
              raw={"Covers": cv, "Intersects": i})
        d = g("Disjoint", o)
        if d is not None and i is not None and d == i:
            V("R2", "Disjoint<=>not Intersects", "Disjoint/Intersects", "lone vs lone", o,
              raw={"Disjoint": d, "Intersects": i})
    for p, q in (("Within", "Contains"), ("CoveredBy", "Covers")):
        for o, oo in (("ab", "ba"), ("ba", "ab")):
            x, y = g(p, o), g(q, oo)
            if x is not None and y is not None and x != y:
                V("R2", f"{p}(x,y)<=>{q}(y,x)", f"{p}/{q}", f"{p} {o} vs {q} {oo}", o,
                  raw={p: x, q: y})
    for p in ("Intersects", "Touches", "Equals"):
        x, y = g(p, "ab"), g(p, "ba")
        if x is not None and y is not None and x != y:
            V("R2", f"{p} symmetric", p, "ab vs ba", None, raw={"ab": x, "ba": y})
    if lv.get("rel_ab") and lv.get("rel_ba") and transpose(lv["rel_ab"]) != lv["rel_ba"]:
        V("R2", "Relate transpose", "Relate", "ST_Relate(b,a) vs transpose(ST_Relate(a,b))",
          None, raw={"rel_ab": lv["rel_ab"], "rel_ba": lv["rel_ba"]})

    # R4: wrappers
    ev.rules_run.append("R4")
    for o in ORIENTATIONS:
        for p in PREDICATES + ["Relate"]:
            base = lv.get(f"rel_{o}") if p == "Relate" else lv.get(f"lone_{p}_{o}")
            for w, label in (("1", "ForceCollection(arg1)"), ("2", "ForceCollection(arg2)")):
                k = f"wrel{w}_{o}" if p == "Relate" else f"w{w}_{p}_{o}"
                got = lv.get(k)
                if base is not None and got is not None and got != base:
                    V("R4", label, p, f"lone vs {label}", o, raw={"lone": base, "wrapped": got})

    # R3: lone vs prepared shapes, index join, and pattern calls vs Python match
    ev.rules_run.append("R3")
    for o, (x, y) in ORIENTATIONS.items():
        wx, wy = (pair.a, pair.b) if o == "ab" else (pair.b, pair.a)
        mtx = lv.get(f"rel_{o}")
        # lone pattern calls vs Python match (not on EMPTY inputs)
        if mtx is not None and not any_empty:
            for i, pat in enumerate(REL_PATTERNS):
                got = lv.get(f"pat{i}_{o}")
                if got is not None and got != matches(mtx, pat):
                    V("R3", "Relate-pattern lone vs Python match", f"Relate '{pat}'",
                      "ST_Relate(x,y,pattern) lone vs matrix match", o,
                      raw={"pattern": pat, "call": got, "matrix": mtx})
        for shape in ("b", "c"):
            sql, names = PREP_SQL[shape]
            stage = f"prep_{shape}_{o}"
            if shape == "c" and (lv.get(f"revsame_{x}") is not False
                                 or lv.get(f"empty_{x}") is not False):
                ev.outcomes.append(Outcome(stage, "skipped",
                                           f"(c) not run: ST_Reverse({x}) byte-identical to {x} "
                                           f"or {x} empty (revsame={lv.get(f'revsame_{x}')}, "
                                           f"empty={lv.get(f'empty_{x}')})"))
                continue
            # (b): %(c)s = x constant arg1, g = y repeated
            # (c): g = [ST_Reverse(x), x, x], %(c)s = y constant arg2
            params = {"c": wx, "r": wy} if shape == "b" else {"c": wy, "r": wx}
            r = target.run(sql, params)
            ev.seconds[stage] = r.seconds
            if not r.ok:
                ev.outcomes.append(Outcome(stage, r.error, r.message or ""))
                if r.error == "crash":
                    ev.info["crashed"] = stage
                    return ev
                continue
            label = "prepared arg1" if shape == "b" else "prepared arg2"

            def elem_label(k: int) -> tuple[str, str]:
                if shape == "c" and k == 1:
                    return "orientation check", f"ST_Reverse({x}) lone call [1]"
                return label, f"{label}[{k}]"

            for name, arr in zip(names, r.one()):
                if arr is None:
                    continue
                if name.startswith("pat"):
                    if mtx is None or any_empty:
                        continue
                    pat = REL_PATTERNS[int(name[3:])]
                    exp = matches(mtx, pat)
                    done = set()
                    for k, val in enumerate(arr, 1):
                        sub, path = elem_label(k)
                        if val != exp and sub not in done:
                            done.add(sub)
                            V("R3", f"Relate-pattern {sub} vs Python match",
                              f"Relate '{pat}'", f"matrix match vs {path}", o,
                              raw={"pattern": pat, "matrix": mtx, "calls": list(arr),
                                   "shape": shape})
                    continue
                lone = lv.get(f"lone_{name}_{o}")
                if lone is None:
                    continue
                done = set()
                for k, val in enumerate(arr, 1):
                    sub, path = elem_label(k)
                    if val != lone and sub not in done:
                        done.add(sub)
                        V("R3", f"lone vs {sub}", name, f"lone vs {path}", o,
                          raw={"lone": lone, "calls": list(arr), "shape": shape})
        if batch is not None:
            for p in INDEXED:
                lone, got = lv.get(f"lone_{p}_{o}"), batch.get((p, o))
                if lone is not None and got is not None and lone != got:
                    V("R3", "lone vs index join", p, "lone vs GiST index join", o,
                      raw={"lone": lone, "index_join": got})

    # ---- overlay rules ---------------------------------------------------------------------
    da, db_ = lv.get("dim_a"), lv.get("dim_b")
    valid = lv.get("valid_a") is True and lv.get("valid_b") is True
    overlay_ok = pair.kind == "overlay" and valid and da == db_ and da in (1, 2)
    r5_only = (not overlay_ok) and pip and valid
    if pair.kind == "overlay" and not overlay_ok:
        ev.outcomes.append(Outcome("overlay", "skipped",
                                   f"overlay rules skipped: valid={valid} dims=({da},{db_})"))
    if not (overlay_ok or r5_only):
        return ev
    d = da if overlay_ok else None
    grid = 10.0 ** (math.floor(math.log10(M)) - 12) if (overlay_ok and M > 0) else None
    bases, exprs = _overlay_exprs(d or 0, grid, r5_only)
    ov = run_exprs(target, pair, bases, exprs, "overlay", ev)
    if ev.info.get("crashed"):
        return ev
    ev.info["grid"] = grid

    # R5
    ev.rules_run.append("R5")
    for o, e in (("ab", "e_iab"), ("ba", "e_iba")):
        i, emp = lv.get(f"lone_Intersects_{o}"), ov.get(e)
        if i is not None and emp is not None and i == emp:
            V("R5", "Intersects<=>not IsEmpty(Intersection)", "Intersects/Intersection",
              "lone Intersects vs IsEmpty(ST_Intersection)", o,
              raw={"Intersects": i, "intersection_empty": emp})
    if r5_only:
        return ev

    measure = "area" if d == 2 else "length"
    m_a, m_b = ov.get("m_a"), ov.get("m_b")
    m_small = min(m_a, m_b) if m_a is not None and m_b is not None else None
    plim = precision_limited(measure, m_small, L, M)
    ev.info.update({"m_small": m_small, "precision_limited": plim, "measure": measure})

    def MV(rule, sub, fn, paths, mag, raw):
        if mag is None or m_small is None:
            return
        b = band(abs(mag), measure, m_small, L, M)
        if b is not None:
            V(rule, sub, fn, paths, None, t="candidate", magnitude=abs(mag), band=b,
              precision_limited=plim, raw=dict(raw, measure=measure, m_small=m_small, L=L, M=M))

    # R6
    ev.rules_run.append("R6")
    if lv.get("empty_a") is False:
        for k in ("e_uab", "e_uba"):
            if ov.get(k) is True:
                V("R6", "not IsEmpty(a) => not IsEmpty(Union)", "Union",
                  f"IsEmpty(a) vs IsEmpty({'ST_Union(a,b)' if k == 'e_uab' else 'ST_Union(b,a)'})",
                  None, precision_limited=plim, raw={"union": ov.get("t_uab")})
    for k, fn, t in (("v_iab", "Intersection(a,b)", "candidate"),
                     ("v_iba", "Intersection(b,a)", "candidate"),
                     ("v_uab", "Union(a,b)", "candidate"), ("v_uba", "Union(b,a)", "candidate"),
                     ("v_ifab", "Intersection(a,b,g)", "strict"),
                     ("v_ufab", "Union(a,b,g)", "strict")):
        if ov.get(k) is False:
            V("R6", f"IsValid({fn}) {'fixed' if t == 'strict' else 'floating'}", fn,
              "ST_IsValid(output)", None, t=t, precision_limited=plim,
              raw={"grid": grid, "intersection": ov.get("t_iab"), "union": ov.get("t_uab")})

    # R7
    ev.rules_run.append("R7")
    MV("R7", "measure(Difference(I,a))", "Intersection", "I vs a", ov.get("r7_ia"),
       {"value": ov.get("r7_ia")})
    MV("R7", "measure(Difference(a,U))", "Union", "a vs U", ov.get("r7_au"),
       {"value": ov.get("r7_au")})
    for t in (1, 2):
        txt = ov.get(f"lp{t}_txt")
        for side in ("a", "b"):
            # candidate; magnitude = max distance from the part's vertices to the operand;
            # noise if <= 1e-12*M, logged if <= 1e-9*M, triage above
            cov, dist = ov.get(f"lp{t}_{side}"), ov.get(f"lp{t}_d{side}")
            if cov is False:
                dd = abs(dist) if dist is not None else None
                b = (None if dd is not None and dd <= 1e-12 * M else
                     "logged" if dd is not None and dd <= 1e-9 * M else "triage")
                if b is not None:
                    V("R7", f"Covers({side}, lower-dim part type {t})", "Intersection",
                      f"ST_Covers({side}, part of ST_Intersection)", None, t="candidate",
                      magnitude=dd, band=b, precision_limited=plim,
                      raw={"part": txt, "max_vertex_distance": dist, "M": M})

    # R8
    ev.rules_run.append("R8")
    MV("R8", "SymDifference(I(a,b),I(b,a))", "Intersection", "I(a,b) vs I(b,a)",
       ov.get("r8_i"), {"m_iab": ov.get("m_iab"), "m_iba": ov.get("m_iba")})
    MV("R8", "SymDifference(U(a,b),U(b,a))", "Union", "U(a,b) vs U(b,a)",
       ov.get("r8_u"), {"m_uab": ov.get("m_uab"), "m_uba": ov.get("m_uba")})

    # R9
    ev.rules_run.append("R9")
    r9_ok = True
    if d == 1 and not (ov.get("simple_a") is True and ov.get("simple_b") is True):
        r9_ok = False
        ev.outcomes.append(Outcome("R9", "not_applicable",
                                   f"not applicable (non-simple line): simple_a="
                                   f"{ov.get('simple_a')} simple_b={ov.get('simple_b')}"))
    if r9_ok and None not in (ov.get("m_uab"), m_a, m_b, ov.get("m_iab")):
        mag = ov["m_uab"] - m_a - m_b + ov["m_iab"]
        MV("R9", "m(U)-m(a)-m(b)+m(I)", "Union/Intersection", "U vs a+b-I", mag,
           {"m_U": ov["m_uab"], "m_a": m_a, "m_b": m_b, "m_I": ov["m_iab"]})

    # R10
    ev.rules_run.append("R10")
    mtx = lv.get("rel_ab")
    if mtx and ov.get("e_iab") is False and ov.get("dim_iab") is not None:
        cells = [mtx[k] for k in (0, 1, 3, 4)]
        exp = max(-1 if c == "F" else int(c) for c in cells)
        if ov["dim_iab"] != exp:
            V("R10", "dim(Intersection) = max(II,IB,BI,BB)", "Intersection/Relate",
              "ST_Dimension(ST_Intersection) vs ST_Relate cells", None, precision_limited=plim,
              raw={"dim_intersection": ov["dim_iab"], "matrix": mtx,
                   "intersection": ov.get("t_iab")})
    if both_nonempty and ov.get("dim_uab") is not None and da is not None:
        if ov["dim_uab"] != max(da, db_):
            V("R10", "dim(Union) = max(dim a, dim b)", "Union", "ST_Dimension(ST_Union)",
              None, precision_limited=plim, raw={"dim_union": ov["dim_uab"],
                                                 "union": ov.get("t_uab")})

    # R11
    ev.rules_run.append("R11")
    if grid is not None:
        for fl, fx, fn in (("m_iab", "m_ifab", "Intersection"), ("m_uab", "m_ufab", "Union")):
            if ov.get(fl) is not None and ov.get(fx) is not None:
                MV("R11", f"{fn} floating vs fixed", fn, f"{fn}(a,b) vs {fn}(a,b,g)",
                   ov[fl] - ov[fx], {"floating": ov[fl], "fixed": ov[fx], "grid": grid})
    return ev
