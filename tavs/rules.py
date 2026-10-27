"""Consistency rules R1-R12 (experiment-plan.md, section "Rules").

`evaluate(target, pair)` gathers values with a few statements and returns violations and
outcomes:

- lone statement: named predicates both ways, `ST_Relate` matrices both ways, wrappers (R4),
  lone pattern calls (not on EMPTY inputs), input dimension/emptiness/validity, the R3 (c)
  primer choice;
- R3 prepared shapes, one statement per shape and orientation (see `_prep_select`):
  (b) `SELECT array_agg(ST_P($1,g) ORDER BY o) FROM unnest(ARRAY[$2,$2,$2]) WITH ORDINALITY t(g,o)`
  (c) `SELECT array_agg(ST_P(g,$2) ORDER BY o) FROM unnest(ARRAY[primer($1),$1,$1]) ...`
  (d) `batch_index_join(target, pairs)`: one GiST index join per batch (call it once per seed);
- overlay statement: intersections, unions (both orders), fixed-precision overlays, and the
  values R5-R12 need.

Every predicate rule is checked in both orientations, (a,b) and (b,a); `orientation` records
which. DE-9IM pattern matching is done in Python. When a statement fails (error or backend
crash, after the server has recovered), each of its expressions is re-run alone, once: an
expression that fails alone gets its own outcome and the others are compared normally.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import numpy as np
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
# R3 (c) primer: element 1 must differ bytewise from x so that call 2 misses on arg1 and hits
# on arg2. First function in this order whose EWKB differs from x is used.
PRIMERS = ["ST_Reverse", "ST_ForceCollection", "ST_CollectionHomogenize", "ST_Multi"]
# ST_Disjoint has no index support function (pg_proc.prosupport is '-'), so it cannot be
# served by the GiST index and stays out of the index join.
INDEXED = ["Contains", "Within", "Covers", "CoveredBy", "Intersects", "Touches", "Equals"]
ORIENTATIONS = {"ab": ("a", "b"), "ba": ("b", "a")}
R12_POINTS = 32
INT_SPAN = 2 ** 20      # L bound (predicate rules) and M bound (overlay rules) for "int"
INT_MAX = 2 ** 53       # |x| bound for predicate rules
PREDICATE_RULES = {"R1", "R2", "R3", "R4"}   # every other rule is in the overlay family


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
# Shared helpers (also for the campaign runner)

def _geom(g):
    return shapely.from_wkt(g) if isinstance(g, str) else g


def tier_of(a, b, family: str) -> str:
    """Coordinate class of a pair given as WKT or Shapely (plan, "Tier by rule family").
    family "predicate" (R1-R4): 'int' when every coordinate is integral, every |x| < 2^53 and
    L < 2^20 (the side test and orientation determinants use differences bounded by L).
    family "overlay" (R5-R12): additionally M < 2^20 (noding error grows with ulp(M)).
    Otherwise 'float'. Boolean rules are strict on 'int' and candidate on 'float'."""
    if family not in ("predicate", "overlay"):
        raise ValueError(f"unknown rule family {family!r}")
    parts = [shapely.get_coordinates(_geom(g), include_z=False) for g in (a, b)]
    parts = [x for x in parts if len(x)]
    if not parts:
        return "int"
    xy = np.vstack(parts)
    if not np.isfinite(xy).all() or not (xy == np.round(xy)).all():
        return "float"
    if (np.abs(xy) >= INT_MAX).any():
        return "float"
    L = max(xy[:, 0].max() - xy[:, 0].min(), xy[:, 1].max() - xy[:, 1].min())
    if L >= INT_SPAN:
        return "float"
    if family == "overlay" and np.abs(xy).max() >= INT_SPAN:
        return "float"
    return "int"


def tier(pair: Pair, family: str) -> str:
    """`tier_of` on a Pair: 'int' or 'float' for family 'predicate' or 'overlay'."""
    return tier_of(pair.a, pair.b, family)


def rule_family(rule: str) -> str:
    return "predicate" if rule in PREDICATE_RULES else "overlay"


def r12_margin(L: float, M: float, grid: Optional[float] = None) -> float:
    """R12 exclusion margin around the boundaries of a, b, I and U (single place to change).
    Floating results (R12f): max(1e-9*L, 1e-8*M), the worst-case OverlayNG snap displacement
    (tolerance M/1e12, x10 per retry, five tries). Fixed-precision results (R12g): the grid g."""
    if grid is not None:
        return grid
    return max(1e-9 * L, 1e-8 * M)


def r12_seed(pair: Pair) -> int:
    """Deterministic ST_GeneratePoints seed (> 0) from the pair's WKT."""
    h = hashlib.sha256((pair.a + "\x00" + pair.b).encode("utf-8")).digest()
    return int.from_bytes(h[:4], "big") % 2147483646 + 1


_POLY = {"Polygon", "MultiPolygon"}
_LINE = {"LineString", "MultiLineString", "LinearRing"}


def pair_precision_limited(ga, gb, L: float, M: float) -> tuple[bool, Optional[float], str]:
    """Pair-level flag (plan, "Tolerance"): 1e-9*L*M >= m_small for areas, 1e-9*M >= m_small
    for lengths. Defined only when both operands are polygonal or both linear (Shapely
    measures); other type combinations have no common measure and are never flagged."""
    ga, gb = _geom(ga), _geom(gb)
    if ga.geom_type in _POLY and gb.geom_type in _POLY:
        m_small, measure = min(ga.area, gb.area), "area"
    elif ga.geom_type in _LINE and gb.geom_type in _LINE:
        m_small, measure = min(ga.length, gb.length), "length"
    else:
        return False, None, "none"
    return precision_limited(measure, m_small, L, M), m_small, measure


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
    band: Optional[str] = None      # logged | triage (measure rules, R7 parts)
    precision_limited: bool = False
    raw: dict = field(default_factory=dict)


@dataclass
class Outcome:
    stage: str                      # lone | lone:<expr> | prep_b_ab | overlay:<expr> | batch...
    kind: str                       # crash | overlay_error | sql_error | timeout | other_error |
    message: str                    # statement_retry | skipped | not_applicable | tier_mismatch


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
    base = {"ga": ga, "gb": gb, "types": (ga.geom_type, gb.geom_type),
            "empty": (bool(ga.is_empty), bool(gb.is_empty))}
    if not coords:
        return dict(base, L=0.0, M=0.0)
    xy = np.vstack(coords)
    L = float(max(xy[:, 0].max() - xy[:, 0].min(), xy[:, 1].max() - xy[:, 1].min()))
    M = float(np.abs(xy).max())
    return dict(base, L=L, M=M)


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


# Functions that only reshape, measure or read geometries; a crash is never blamed on them
# while the expression also calls another function.
_LIGHT = {"ST_GeomFromText", "ST_AsText", "ST_AsEWKB", "ST_ForceCollection",
          "ST_CollectionExtract", "ST_CollectionHomogenize", "ST_Multi", "ST_Reverse",
          "ST_Dimension", "ST_IsEmpty", "ST_X", "ST_Y", "ST_Dump", "ST_DumpPoints",
          "ST_Envelope", "ST_Collect", "ST_Segmentize", "ST_Area", "ST_Length"}


def sql_functions(sql: str) -> set[str]:
    """SQL functions an expression calls, with ST_Relate split into 'ST_Relate(matrix)' and
    'ST_Relate(pattern)' (the pattern form carries a quoted pattern literal)."""
    names = set(re.findall(r"\bST_\w+(?=\()", sql))
    if "ST_Relate" in names:
        names.discard("ST_Relate")
        names.add("ST_Relate(pattern)" if re.search(r"ST_Relate\(.*'[^']*'\s*\)", sql)
                  else "ST_Relate(matrix)")
    return names


def crash_list(ev: Evaluation) -> list[str]:
    """Functions that crashed the server on this pair (each on its own)."""
    return ev.info.setdefault("crashed_functions", [])


def run_named(target: Target, stage: str, ev: Evaluation, build: Callable[[dict], str],
              exprs: dict[str, str], params: Any,
              deps_sql: Callable[[str], str] = lambda sql: "") -> dict[str, Any]:
    """Evaluate named expressions in one statement built by `build(exprs)`.

    Crash list (per pair, `ev.info["crashed_functions"]`): an expression that calls a listed
    function (in its own SQL or in the bases it depends on, `deps_sql`) is not sent; it gets a
    `skipped` outcome "F crashed on this pair". If the statement fails (error, timeout or
    backend crash; `Target.run` has already waited for recovery after a crash), the failure is
    recorded and the remaining expressions are re-run alone, once, again skipping those that
    call a function listed meanwhile. An expression that crashes alone puts its functions on
    the list (the non-light ones it calls itself; else those of its bases; else all)."""
    crashed = crash_list(ev)
    ev.seconds.setdefault(stage, 0.0)

    def funcs(sql):
        return sql_functions(sql) | sql_functions(deps_sql(sql))

    def drop_listed(names):
        keep = {}
        for name in names:
            hit = sorted(funcs(exprs[name]) & set(crashed))
            if hit:
                ev.outcomes.append(Outcome(f"{stage}:{name}", "skipped",
                                           f"{', '.join(hit)} crashed on this pair"))
            else:
                keep[name] = exprs[name]
        return keep

    todo = drop_listed(list(exprs))
    if not todo:
        return {}
    r = target.run(build(todo), params)
    ev.seconds[stage] += r.seconds
    if r.ok:
        return dict(zip(todo, r.one()))
    kind = "crash" if r.error == "crash" else "statement_retry"
    ev.outcomes.append(Outcome(stage, kind, f"{r.error}; re-running the remaining expressions "
                                            f"alone: {r.message}"))
    values: dict[str, Any] = {}
    for name in list(todo):
        if not drop_listed([name]):
            continue
        sql = todo[name]
        rr = target.run(build({name: sql}), params)
        ev.seconds[stage] += rr.seconds
        if rr.ok:
            values[name] = rr.one()[0]
            continue
        ev.outcomes.append(Outcome(f"{stage}:{name}", rr.error, rr.message or ""))
        if rr.error == "crash":
            own = {f for f in sql_functions(sql) if f not in _LIGHT}
            dep = {f for f in sql_functions(deps_sql(sql)) if f not in _LIGHT}
            for f in sorted(own or dep or funcs(sql)):
                if f not in crashed:
                    crashed.append(f)
    return values


def run_exprs(target: Target, pair: Pair, bases: dict[str, str], exprs: dict[str, str],
              stage: str, ev: Evaluation) -> dict[str, Any]:
    """`run_named` over the pair CTE; each expression alone carries only the bases it uses."""
    return run_named(target, stage, ev, lambda ex: _select(
        {n: s for x in ex.values() for n, s in _deps(x, bases).items()}, ex),
        exprs, {"a": pair.a, "b": pair.b},
        deps_sql=lambda sql: " ".join(_deps(sql, bases).values()))


# --------------------------------------------------------------------------------------------
# Statements

def _lone_exprs(with_patterns: bool) -> dict[str, str]:
    e = {"dim_a": "ST_Dimension(a)", "dim_b": "ST_Dimension(b)",
         "empty_a": "ST_IsEmpty(a)", "empty_b": "ST_IsEmpty(b)",
         "valid_a": "ST_IsValid(a)", "valid_b": "ST_IsValid(b)"}
    for x in ("a", "b"):            # R3 (c) primer: first PRIMERS function changing the bytes
        whens = " ".join(f"WHEN ST_AsEWKB({f}({x})) <> ST_AsEWKB({x}) THEN '{f}'"
                         for f in PRIMERS)
        e[f"primer_{x}"] = f"CASE {whens} END"
    for o, (x, y) in ORIENTATIONS.items():
        e[f"rel_{o}"] = f"ST_Relate({x},{y})"
        e[f"wrel1_{o}"] = f"ST_Relate(ST_ForceCollection({x}),{y})"
        e[f"wrel2_{o}"] = f"ST_Relate({x},ST_ForceCollection({y}))"
        for p in PREDICATES:
            e[f"lone_{p}_{o}"] = f"ST_{p}({x},{y})"
            e[f"w1_{p}_{o}"] = f"ST_{p}(ST_ForceCollection({x}),{y})"
            e[f"w2_{p}_{o}"] = f"ST_{p}({x},ST_ForceCollection({y}))"
        if with_patterns:           # pattern calls are never compared on EMPTY inputs
            for i, pat in enumerate(REL_PATTERNS):
                e[f"pat{i}_{o}"] = f"ST_Relate({x},{y},'{pat}')"
    return e


def _prep_cols(shape: str, with_patterns: bool) -> dict[str, str]:
    """Column name -> call with g the array element and %(c)s the constant argument."""
    cols = {}
    for p in (PREP_ARG1 if shape == "b" else PREP_ARG2):
        cols[p] = f"ST_{p}(%(c)s::geometry, g)" if shape == "b" else f"ST_{p}(g, %(c)s::geometry)"
    if with_patterns:
        for i, pat in enumerate(REL_PATTERNS):
            cols[f"pat{i}"] = (f"ST_Relate(%(c)s::geometry, g, '{pat}')" if shape == "b"
                               else f"ST_Relate(g, %(c)s::geometry, '{pat}')")
    return cols


def _prep_select(shape: str, primer: Optional[str]) -> Callable[[dict], str]:
    """R3 (b) prepared arg1: SELECT array_agg(ST_P($1,g) ORDER BY o)
         FROM unnest(ARRAY[$2,$2,$2]) WITH ORDINALITY t(g,o)  ($1 = %(c)s = x, $2 = %(r)s = y).
    R3 (c) prepared arg2: SELECT array_agg(ST_P(g,$2) ORDER BY o)
         FROM unnest(ARRAY[primer($1),$1,$1]) WITH ORDINALITY t(g,o)  ($1 = %(r)s = x,
         $2 = %(c)s = y). Call 1 misses and stores both args; call 2 differs bytewise in arg1
         and hits arg2, so y is prepared; call 3 uses the prepared y (lwgeom_cache.c l.124-130
         tests the arg1 hit first, so with both args repeating arg1 would be prepared).
    Element 1 only primes the cache; elements 2-3 are the compared calls."""
    first = "%(r)s::geometry" if shape == "b" else f"{primer}(%(r)s::geometry)"

    def build(cols: dict) -> str:
        sel = ", ".join(f"array_agg({call} ORDER BY o) AS {name}" for name, call in cols.items())
        return (f"SELECT {sel} FROM unnest(ARRAY[{first},%(r)s::geometry,%(r)s::geometry]) "
                f"WITH ORDINALITY t(g,o)")
    return build


def _lowdim_exprs(part: str, t: int, M: float, L: float, prefix: str) -> dict[str, str]:
    """R7 lower-dimensional part checks for one part expression of type t (1 points, 2 lines).
    Per operand s: Covers(s, part); where false, Covers(ST_Buffer(s, 1e-12*M), part) (noise),
    Covers(ST_Buffer(s, 1e-9*M), part) (logged) and a magnitude: exact max point distance for
    point parts, a lower bound for line parts (vertices of ST_Segmentize(part, L/1024))."""
    e1, e2 = repr(1e-12 * M), repr(1e-9 * M)
    seg = part if t == 1 or L <= 0 else f"ST_Segmentize({part}, {L / 1024!r})"
    ex = {f"{prefix}_txt": f"CASE WHEN ST_IsEmpty({part}) THEN NULL "
                           f"ELSE left(ST_AsText({part}),400) END"}
    for s in ("a", "b"):
        miss = f"ST_IsEmpty({part}) OR ST_Covers({s},{part})"
        ex[f"{prefix}_{s}"] = f"CASE WHEN ST_IsEmpty({part}) THEN NULL ELSE ST_Covers({s},{part}) END"
        ex[f"{prefix}_n{s}"] = f"CASE WHEN {miss} THEN NULL ELSE ST_Covers(ST_Buffer({s},{e1}),{part}) END"
        ex[f"{prefix}_l{s}"] = f"CASE WHEN {miss} THEN NULL ELSE ST_Covers(ST_Buffer({s},{e2}),{part}) END"
        ex[f"{prefix}_d{s}"] = (f"CASE WHEN {miss} THEN NULL ELSE (SELECT max(ST_Distance(dp.geom, {s})) "
                                f"FROM ST_DumpPoints({seg}) dp) END")
    return ex


def _r12_expr(seed: int, margin: float, i: str = "i_ab", u: str = "u_ab") -> str:
    """R12 sample: JSON list of points with near-boundary flag and the four point locations.
    I and U are the polygonal extracts of the intersection `i` and union `u` (floating i_ab,
    u_ab for R12f; fixed-precision if_ab, uf_ab for R12g)."""
    m = repr(margin)
    near = " OR ".join(f"ST_DWithin(p, ST_Boundary(ST_CollectionExtract({g},3)), {m})"
                       for g in ("a", "b", i, u))
    return ("(SELECT json_agg(json_build_object('x',ST_X(p),'y',ST_Y(p),'near',near,"
            "'a',ia,'b',ib,'I',ii,'U',iu)) FROM (SELECT p, "
            f"({near}) near, ST_Intersects(p,a) ia, ST_Intersects(p,b) ib, "
            f"ST_Intersects(p,ST_CollectionExtract({i},3)) ii, "
            f"ST_Intersects(p,ST_CollectionExtract({u},3)) iu FROM (SELECT (ST_Dump("
            f"ST_GeneratePoints(ST_Envelope(ST_Collect(a,b)), {R12_POINTS}, {seed}))).geom p) s0) s)")


def _overlay_exprs(d: int, grid: Optional[float], with_r5_only: bool, M: float = 0.0,
                   L: float = 0.0, r12: Optional[int] = None
                   ) -> tuple[dict, dict]:
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
        exprs.update(_lowdim_exprs(f"ST_CollectionExtract(i_ab,{t})", t, M, L, f"lp{t}"))
    if grid is not None:
        exprs.update({"v_ifab": "ST_IsValid(if_ab)", "v_ufab": "ST_IsValid(uf_ab)",
                      "m_ifab": f"{meas}(if_ab)", "m_ufab": f"{meas}(uf_ab)"})
    if d == 2 and r12 is not None:      # r12 = seed; same 32 points for both variants
        exprs["r12f"] = _r12_expr(r12, r12_margin(L, M))
        if grid is not None:
            exprs["r12g"] = _r12_expr(r12, r12_margin(L, M, grid), "if_ab", "uf_ab")
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
    try:
        cs = coord_stats(pair)
    except Exception as exc:  # noqa: BLE001
        ev.outcomes.append(Outcome("parse", "other_error", f"Shapely could not parse: {exc}"))
        return ev
    L, M, types = cs["L"], cs["M"], cs["types"]
    tiers = {f: ("strict" if tier_of(cs["ga"], cs["gb"], f) == "int" else "candidate")
             for f in ("predicate", "overlay")}
    if (pair.coord == "int") != (tiers["predicate"] == "strict"):
        ev.outcomes.append(Outcome("tier", "tier_mismatch",
                                   f"pair.coord={pair.coord!r} but the coordinates give "
                                   f"predicate tier {tiers['predicate']}; the coordinates decide"))
    plim, m_small_s, measure_s = pair_precision_limited(cs["ga"], cs["gb"], L, M)
    pip = _is_point_polygon(types)
    path_label = "point-in-polygon" if pip else None
    any_empty = any(cs["empty"])
    ev.info.update({"L": L, "M": M, "types": types, "tiers": tiers, "precision_limited": plim,
                    "m_small_shapely": m_small_s, "measure": measure_s})

    def V(rule, sub, fn, paths, o, t=None, raw=None, **kw):
        # boolean rules take their family's tier; the precision-limited flag is an
        # overlay-area criterion: R5-R12 only, never R1-R4
        fam = rule_family(rule)
        r = dict(raw or {})
        if path_label:
            r["path_label"] = path_label
        ev.violations.append(Violation(rule, sub, fn, paths, o, t or tiers[fam], raw=r,
                                       precision_limited=plim and fam == "overlay", **kw))

    # ---- lone statement --------------------------------------------------------------------
    lv = run_exprs(target, pair, {}, _lone_exprs(not any_empty), "lone", ev)
    both_nonempty = lv.get("empty_a") is False and lv.get("empty_b") is False
    ev.info.update({k: lv.get(k) for k in ("dim_a", "dim_b", "empty_a", "empty_b", "valid_a",
                                            "valid_b", "rel_ab", "rel_ba", "primer_a",
                                            "primer_b")})

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
        if c is True and i is False:
            V("R2", "Contains=>Intersects", "Contains/Intersects", "lone vs lone", o,
              raw={"Contains": c, "Intersects": i})
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
            stage = f"prep_{shape}_{o}"
            primer = lv.get(f"primer_{x}") if shape == "c" else None
            if shape == "c" and primer is None:
                ev.outcomes.append(Outcome(stage, "skipped",
                                           f"(c) not run: no primer ({', '.join(PRIMERS)}) "
                                           f"changes the bytes of {x}"))
                continue
            # (b): %(c)s = x constant arg1, g = [y, y, y]
            # (c): g = [primer(x), x, x], %(c)s = y constant arg2
            params = {"c": wx, "r": wy} if shape == "b" else {"c": wy, "r": wx}
            vals = run_named(target, stage, ev, _prep_select(shape, primer),
                             _prep_cols(shape, not any_empty), params)
            label = "prepared arg1" if shape == "b" else "prepared arg2"
            if shape == "c":
                ev.info[f"primer_used_{o}"] = primer
            for name, arr in vals.items():
                if arr is None or len(arr) != 3:
                    continue
                if name.startswith("pat"):
                    pat = REL_PATTERNS[int(name[3:])]
                    if mtx is not None:
                        ref, ref_label = matches(mtx, pat), "matrix match"
                    elif shape == "b":
                        ref, ref_label = arr[0], "unprepared first call [1]"
                    else:
                        ev.outcomes.append(Outcome(f"{stage}:{name}", "skipped",
                                                   "no lone matrix to compare with"))
                        continue
                    bad = [k for k in (2, 3) if arr[k - 1] != ref]
                    if bad:
                        V("R3", f"Relate-pattern {label} vs {ref_label}", f"Relate '{pat}'",
                          f"{ref_label} vs {label}[{bad[0]}]", o,
                          raw={"pattern": pat, "matrix": mtx, "calls": list(arr),
                               "shape": shape, "primer": primer})
                    continue
                lone = lv.get(f"lone_{name}_{o}")
                if lone is not None:
                    ref, ref_label = lone, "lone"
                elif shape == "b":
                    ref, ref_label = arr[0], "unprepared first call [1]"
                else:
                    ev.outcomes.append(Outcome(f"{stage}:{name}", "skipped",
                                               "no lone value to compare with"))
                    continue
                bad = [k for k in (2, 3) if arr[k - 1] != ref]
                if bad:
                    V("R3", f"{ref_label} vs {label}", name, f"{ref_label} vs {label}[{bad[0]}]",
                      o, raw={"lone": lone, "calls": list(arr), "shape": shape,
                              "primer": primer})
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
    r12 = r12_seed(pair) if overlay_ok and d == 2 else None
    bases, exprs = _overlay_exprs(d or 0, grid, r5_only, M=M, L=L, r12=r12)
    ov = run_exprs(target, pair, bases, exprs, "overlay", ev)
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
    ev.info.update({"m_small": m_small})

    def MV(rule, sub, fn, paths, mag, raw):
        if mag is None or m_small is None:
            return
        b = band(abs(mag), measure, m_small, L, M)
        if b is not None:
            V(rule, sub, fn, paths, None, t="candidate", magnitude=abs(mag), band=b,
              raw=dict(raw, measure=measure, m_small=m_small, L=L, M=M))

    # R6
    ev.rules_run.append("R6")
    if lv.get("empty_a") is False:
        for k in ("e_uab", "e_uba"):
            if ov.get(k) is True:
                V("R6", "not IsEmpty(a) => not IsEmpty(Union)", "Union",
                  f"IsEmpty(a) vs IsEmpty({'ST_Union(a,b)' if k == 'e_uab' else 'ST_Union(b,a)'})",
                  None, raw={"union": ov.get("t_uab")})
    for k, fn, t in (("v_iab", "Intersection(a,b)", "candidate"),
                     ("v_iba", "Intersection(b,a)", "candidate"),
                     ("v_uab", "Union(a,b)", "candidate"), ("v_uba", "Union(b,a)", "candidate"),
                     ("v_ifab", "Intersection(a,b,g)", "strict"),
                     ("v_ufab", "Union(a,b,g)", "strict")):
        if ov.get(k) is False:
            V("R6", f"IsValid({fn}) {'fixed' if t == 'strict' else 'floating'}", fn,
              "ST_IsValid(output)", None, t=t,
              raw={"grid": grid, "intersection": ov.get("t_iab"), "union": ov.get("t_uab")})

    # R7
    ev.rules_run.append("R7")
    MV("R7", "measure(Difference(I,a))", "Intersection", "I vs a", ov.get("r7_ia"),
       {"value": ov.get("r7_ia")})
    MV("R7", "measure(Difference(a,U))", "Union", "a vs U", ov.get("r7_au"),
       {"value": ov.get("r7_au")})
    for t in (1, 2):
        for v in lowdim_violations(ov, f"lp{t}", t, M, L, failed_stage_prefix="overlay:",
                                   outcomes=ev.outcomes):
            V("R7", v["sub"], "Intersection", v["paths"], None, t="candidate",
              magnitude=v["magnitude"], band=v["band"], raw=v["raw"])

    # R8
    ev.rules_run.append("R8")
    MV("R8", "SymDifference(I(a,b),I(b,a))", "Intersection", "I(a,b) vs I(b,a)",
       ov.get("r8_i"), {"m_iab": ov.get("m_iab"), "m_iba": ov.get("m_iba")})
    MV("R8", "SymDifference(U(a,b),U(b,a))", "Union", "U(a,b) vs U(b,a)",
       ov.get("r8_u"), {"m_uab": ov.get("m_uab"), "m_uba": ov.get("m_uba")})

    # R9
    if d == 1 and not (ov.get("simple_a") is True and ov.get("simple_b") is True):
        ev.outcomes.append(Outcome("R9", "not_applicable",
                                   f"not applicable (non-simple line): simple_a="
                                   f"{ov.get('simple_a')} simple_b={ov.get('simple_b')}"))
    elif None not in (ov.get("m_uab"), m_a, m_b, ov.get("m_iab")):
        ev.rules_run.append("R9")
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
              "ST_Dimension(ST_Intersection) vs ST_Relate cells", None,
              raw={"dim_intersection": ov["dim_iab"], "matrix": mtx,
                   "intersection": ov.get("t_iab")})
    if both_nonempty and ov.get("dim_uab") is not None and da is not None:
        if ov["dim_uab"] != max(da, db_):
            V("R10", "dim(Union) = max(dim a, dim b)", "Union", "ST_Dimension(ST_Union)",
              None, raw={"dim_union": ov["dim_uab"], "union": ov.get("t_uab")})

    # R11
    if grid is not None:
        ev.rules_run.append("R11")
        for fl, fx, fn in (("m_iab", "m_ifab", "Intersection"), ("m_uab", "m_ufab", "Union")):
            if ov.get(fl) is not None and ov.get(fx) is not None:
                MV("R11", f"{fn} floating vs fixed", fn, f"{fn}(a,b) vs {fn}(a,b,g)",
                   ov[fl] - ov[fx], {"floating": ov[fl], "fixed": ov[fx], "grid": grid})

    # R12: point sampling (polygon pairs), strict. R12f on the floating results with margin
    # max(1e-9*L, 1e-8*M); R12g on the fixed-precision results of R11 with margin g (not
    # applicable when M = 0 or g is undefined). Same seed, so the same 32 points.
    if r12 is not None:
        for rule, key_sql, gv in (("R12f", "r12f", None), ("R12g", "r12g", grid)):
            if rule == "R12g" and gv is None:
                ev.outcomes.append(Outcome("R12g", "not_applicable",
                                           "not applicable: M = 0 or grid undefined"))
                continue
            pts = ov.get(key_sql)
            if pts is None:
                continue                # expression failed: its outcome is already recorded
            ev.rules_run.append(rule)
            margin = r12_margin(L, M, gv)
            kept = [p for p in pts if not p["near"]]
            excluded = [[p["x"], p["y"]] for p in pts if p["near"]]
            ev.info[key_sql] = {"seed": r12, "margin": margin, "generated": len(pts),
                                "kept": len(kept), "excluded": len(excluded),
                                "kept_points": [[p["x"], p["y"]] for p in kept],
                                "excluded_points": excluded}
            for key, op, fn in (("I", lambda p: p["a"] and p["b"], "Intersection"),
                                ("U", lambda p: p["a"] or p["b"], "Union")):
                bad = [p for p in kept if p[key] is not None and p["a"] is not None
                       and p["b"] is not None and p[key] != op(p)]
                if bad:
                    V(rule, f"Intersects(p,{key}) = Intersects(p,a) "
                      f"{'AND' if key == 'I' else 'OR'} Intersects(p,b)",
                      fn + ("" if gv is None else " (fixed precision)"),
                      f"point location in {key} vs in a and b", None, t="strict",
                      raw={"points": bad[:32], "n_bad": len(bad), "seed": r12,
                           "margin": margin, "grid": gv, "kept": len(kept),
                           "excluded": len(excluded)})
    return ev


def lowdim_violations(vals: dict, prefix: str, t: int, M: float, L: float,
                      failed_stage_prefix: str = "", outcomes: Optional[list] = None
                      ) -> list[dict]:
    """Classify R7 lower-dimensional parts from `_lowdim_exprs` values: per operand where
    Covers is false, noise if the 1e-12*M buffer covers the part, logged if the 1e-9*M
    buffer does, triage otherwise (also triage when a buffer check failed)."""
    out = []
    failed = {o.stage.split(":", 1)[1] for o in (outcomes or [])
              if o.stage.startswith(failed_stage_prefix) and ":" in o.stage}
    for s in ("a", "b"):
        if vals.get(f"{prefix}_{s}") is not False:
            continue
        n, lg = vals.get(f"{prefix}_n{s}"), vals.get(f"{prefix}_l{s}")
        err = [k for k in (f"{prefix}_n{s}", f"{prefix}_l{s}") if k in failed or vals.get(k) is None]
        if n is True:
            continue                    # noise
        if n is False and lg is True:
            b = "logged"
        else:
            b = "triage"
        dist = vals.get(f"{prefix}_d{s}")
        out.append({"sub": f"Covers({s}, lower-dim part type {t})",
                    "paths": f"ST_Covers({s}, part of ST_Intersection)", "band": b,
                    "magnitude": abs(dist) if dist is not None else None,
                    "raw": {"part": vals.get(f"{prefix}_txt"),
                            "magnitude_kind": ("exact max point distance" if t == 1 else
                                               "lower bound: max distance of the vertices of "
                                               "ST_Segmentize(part, L/1024)"),
                            "covers_buffer_1e-12M": n, "covers_buffer_1e-9M": lg,
                            "buffer_check_failed": err or None, "M": M, "L": L}})
    return out
