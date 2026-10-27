"""Build seeds/known_bugs.json from the downloaded issue JSON in seeds/raw.

Usage: <venv python> -I build_known_bugs.py <seeds_dir>
Geometries are taken verbatim from issue bodies/comments/tests (only CRLF -> LF);
WKB hex inputs are converted with Shapely and the hex kept in `original`.
"""
import json, os, re, sys
import shapely
from shapely import from_wkt, from_wkb

sys.stdout.reconfigure(encoding="utf-8")
SEEDS = sys.argv[1]
RAW = os.path.join(SEEDS, "raw")

RX = re.compile(r"""(['"])((?:MULTI)?(?:POLYGON|LINESTRING|POINT)\b[^'"]*|GEOMETRYCOLLECTION[^'"]*)\1""", re.I)
FENCE = re.compile(r"```[a-z]*\n(.*?)```", re.S)


def issue(name):
    with open(os.path.join(RAW, name + ".json"), encoding="utf-8") as f:
        return json.load(f)


def comments(name):
    with open(os.path.join(RAW, name + "_c.json"), encoding="utf-8") as f:
        return json.load(f)


def body(name):
    return issue(name)["body"].replace("\r\n", "\n")


def quoted(name):
    return [m.group(2) for m in RX.finditer(body(name))]


def fences(name):
    return [m.group(1).strip() for m in FENCE.finditer(body(name))]


def W(g, n=300):
    if g is None:
        return None
    s = shapely.to_wkt(g, rounding_precision=-1, output_dimension=4)
    return s if len(s) <= n else s[:n] + "...(truncated, %d chars)" % len(s)


def rel(a, b):
    return shapely.relate(a, b)


def area(g):
    return float(shapely.area(g))


def fresh(wkt):
    return from_wkt(wkt)


def prepared(wkt):
    g = from_wkt(wkt)
    shapely.prepare(g)
    return g


def safe(fn):
    try:
        return fn()
    except Exception as e:  # GEOS exceptions are part of the observation
        return "EXCEPTION %s: %s" % (type(e).__name__, e)


records = []


def rec(**kw):
    base = dict(id=None, url=None, title=None, status=None, fixed_in=None, fixed_in_basis=None,
                geometries=None, original=None, operations=[], reported=None, expected=None, notes=None,
                check=None, observed_geos_3_14_1=None, reproduces_in_geos_3_14_1=None)
    base.update(kw)
    records.append(base)
    return base


def gh(name, kind="geos"):
    i = issue(name)
    st = i["state"]
    return dict(url=i["html_url"], title=i["title"], status=st)


# ---------------- GEOS #1022
q = quoted("geos_1022")
r = rec(id="geos#1022", **gh("geos_1022"),
        geometries={"g1": q[0], "g2": q[1], "g3": q[2],
                    "c1_a": "GEOMETRYCOLLECTION (POINT (2 2), LINESTRING (0 0, 1 1))",
                    "c1_b": "LINESTRING ( 2 2, 3 3)"},
        operations=["crosses", "relate"],
        reported="ST_Crosses(g1,g2)=true, ST_Crosses(g1,g3)=false; geosop relate(g1,g2)=212FF0212 (dr-jts comment); "
                 "comment case relate(c1_a,c1_b)=1F10F0102",
        expected="ST_Crosses(g1,g2)=false and ST_Crosses(g1,g3)=false (reporter); maintainer: relate matrix 'very wrong' (dim(Int n Int)=2 is wrong); "
                 "for c1 reporter says dim(Int n Int)=1 is wrong (POINT(2 2) is b's start point)",
        notes="g2 and g3 are the same polygon with a rotated start vertex (order-invariance). dr-jts: old relate mishandles mixed-dimension "
              "GeometryCollections. c1_a/c1_b from comment by cuteDen-ECNU 2024-01-12. Issue still open on GitHub; GEOS 3.13.0 replaced relate with RelateNG.")


def ev1022():
    g = {k: fresh(v) for k, v in r["geometries"].items()}
    c12 = bool(shapely.crosses(g["g1"], g["g2"])); c13 = bool(shapely.crosses(g["g1"], g["g3"]))
    m12 = rel(g["g1"], g["g2"]); m13 = rel(g["g1"], g["g3"]); mc = rel(g["c1_a"], g["c1_b"])
    obs = "crosses(g1,g2)=%s crosses(g1,g3)=%s relate(g1,g2)=%s relate(g1,g3)=%s relate(c1_a,c1_b)=%s" % (c12, c13, m12, m13, mc)
    rep = "yes" if (c12 or m12 == "212FF0212" or mc == "1F10F0102") else "no"
    return obs, rep


r["_ev"] = ev1022

# ---------------- GEOS #1027
q = quoted("geos_1027")
r = rec(id="geos#1027", **gh("geos_1027"),
        geometries={"g1": "GEOMETRYCOLLECTION ( LINESTRING (1 2, 1 1), POINT (0 0))",
                    "g2": " MULTIPOLYGON (((0 0, 3 0, 3 3, 0 3, 0 0)))  ",
                    "g3": " POLYGON ((0 0, 3 0, 3 3, 0 3, 0 0))  "},
        operations=["covers"],
        reported="ST_Covers(g2,g1)=false, ST_Covers(g3,g1)=true; geosop covers(g1? -a GC -b MULTIPOLYGON)=false",
        expected="{true, true} (reporter): g2 covers g1",
        notes="WKT kept with the surrounding spaces as written in the SQL. Note the geosop line in the issue passes -a GC -b MULTIPOLYGON covers "
              "(i.e. covers(GC, MP)), which differs from the SQL order; the SQL ST_Covers(g2,g1) is the stated bug. Issue open on GitHub.")


def ev1027():
    g = {k: fresh(v) for k, v in r["geometries"].items()}
    a = bool(shapely.covers(g["g2"], g["g1"])); b = bool(shapely.covers(g["g3"], g["g1"]))
    gs = bool(shapely.covers(g["g1"], g["g2"]))
    obs = "covers(g2,g1)=%s covers(g3,g1)=%s covers(g1,g2)=%s relate(g2,g1)=%s" % (a, b, gs, rel(g["g2"], g["g1"]))
    return obs, ("yes" if not a else "no")


r["_ev"] = ev1027

# ---------------- GEOS #1033
r = rec(id="geos#1033", **gh("geos_1033"), fixed_in="3.13.0", fixed_in_basis=
        "inferred: maintainer (pramsey 2024-02-12) deferred to RelateNG, released in GEOS 3.13.0 (NEWS); closed 2026-01-07 by dbaston "
        "'contains and containsPrep both return true in current main'; no closing commit",
        geometries={"a": "POLYGON((1 0,0 4,2 2,1 0))", "b": "GEOMETRYCOLLECTION(POINT(2 2),POINT(1 0),LINESTRING(1 2,1 1))"},
        operations=["contains", "contains (prepared)", "covers", "covers (prepared)"],
        reported="contains(a,b)=false; containsPrep(a,b)=true (pramsey: same for covers/coversPrep)",
        expected="contains(a,b)=true (reporter; dbaston confirms both true in main)",
        notes="Prepared vs non-prepared inconsistency.")


def ev1033():
    a = fresh(r["geometries"]["a"]); b = fresh(r["geometries"]["b"]); ap = prepared(r["geometries"]["a"])
    c, cp = bool(shapely.contains(a, b)), bool(shapely.contains(ap, b))
    v, vp = bool(shapely.covers(a, b)), bool(shapely.covers(ap, b))
    return ("contains=%s containsPrep=%s covers=%s coversPrep=%s relate(a,b)=%s" % (c, cp, v, vp, rel(a, b)),
            "yes" if (not c or c != cp or v != vp) else "no")


r["_ev"] = ev1033

# ---------------- GEOS #1053
r = rec(id="geos#1053", **gh("geos_1053"), fixed_in="3.13.0", fixed_in_basis=
        "inferred: dr-jts 2024-05-05 'This result is correctly computed by the RelateNG algorithm'; RelateNG ported in 3.13.0 (NEWS); closed 2024-11-26 without closing commit",
        geometries={"g1": "MULTILINESTRING((2 4, 10 10),(15 10,10 5,5 10))", "g2": "MULTILINESTRING((2 4, 10 10))"},
        operations=["relate"],
        reported="0F1F001F2",
        expected="1F1F00FF2 (dr-jts correction of reporter's 1F1F001F2)",
        notes="Reporter originally expected 1F1F001F2; maintainer corrected to 1F1F00FF2 since A contains B.")


def ev1053():
    g1, g2 = fresh(r["geometries"]["g1"]), fresh(r["geometries"]["g2"])
    m = rel(g1, g2)
    return "relate(g1,g2)=%s relate(g2,g1)=%s" % (m, rel(g2, g1)), ("no" if m == "1F1F00FF2" else ("yes" if m == "0F1F001F2" else "unclear"))


r["_ev"] = ev1053

# ---------------- GEOS #1064
b1064 = body("geos_1064")
ha = re.search(r"Line A: ([0-9A-F]+)", b1064).group(1); hb = re.search(r"Line B: ([0-9A-F]+)", b1064).group(1)
ga, gb = from_wkb(bytes.fromhex(ha)), from_wkb(bytes.fromhex(hb))
r = rec(id="geos#1064", **gh("geos_1064"), fixed_in=None, fixed_in_basis=
        "closed 2024-11-26 without fix; dr-jts 2024-04-08: 'not a bug, but a limitation ... due to numeric rounding'",
        geometries={"A": shapely.to_wkt(ga, rounding_precision=-1), "B": shapely.to_wkt(gb, rounding_precision=-1)},
        original={"format": "WKB hex (as given in issue body)", "A": ha, "B": hb},
        operations=["relate", "relate(A, boundary(B))"],
        reported="relate(A,B) says Int(A) n Bdy(B) has dim 0 (matrix 'F01 FF0 102' as printed: I/B/E rows F 0 1 / F F 0 / 1 0 2), while A vs Boundary(B) "
                 "shows no intersection (F F 1 / F F 0 / 0 F 2). strk XML test (PR #1092/#1093): obtained F01FF0102 on main",
        expected="Consistent answers; XML test issue-geos-gh1064.xml expects FF1FF0102 (GEOS 3.8 result). Maintainer: the 3.12+ Orientation predicate "
                 "reports a proper intersection, so 3.8 is 'wrong' by current technology; not considered a bug",
        notes="WKT converted with Shapely 2.2.0 to_wkt(rounding_precision=-1). The WKT in strk's XML test output "
              "(LINESTRING (16.330791631988802 68.75635661578073, ...)) matches A.")


def ev1064():
    A, B = fresh(r["geometries"]["A"]), fresh(r["geometries"]["B"])
    m, mt = rel(A, B), rel(B, A)
    bd = shapely.boundary(B)
    mb = rel(A, bd)
    inter = bool(shapely.intersects(A, bd))
    transp = "".join(mt[i] for i in (0, 3, 6, 1, 4, 7, 2, 5, 8))
    obs = "relate(A,B)=%s relate(B,A)=%s (transpose consistent=%s) relate(A,boundary(B))=%s intersects(A,boundary(B))=%s" % (m, mt, transp == m, mb, inter)
    incons = (m[1] != "F") != inter
    return obs, ("yes" if incons else "no")


r["_ev"] = ev1064

# ---------------- GEOS #1224
r = rec(id="geos#1224", **gh("geos_1224"), fixed_in="3.13.1", fixed_in_basis=
        "PR #1229 merged 2025-01-17 (merge b6c1b594); NEWS lists GH-1229 under 3.14.0; #1248 calls a 3.13.1 regression 'caused by #1229', so it was also in 3.13.1",
        geometries={"a": "GEOMETRYCOLLECTION(POLYGON EMPTY, POINT EMPTY, LINESTRING(10 10, 10 10))", "b": "POINT(1 1)",
                    "c": "GEOMETRYCOLLECTION(POLYGON EMPTY, POINT EMPTY, LINESTRING(10 10, 10 10), POINT(1 1))",
                    "d": "GEOMETRYCOLLECTION(LINESTRING(10 10, 10 10), POINT(1 1))"},
        operations=["union", "unaryUnion"],
        reported="union(a,b)=GEOMETRYCOLLECTION (POLYGON EMPTY, POINT EMPTY, LINESTRING (10 10, 10 10), POINT (1 1)); "
                 "unaryUnion(c)=GEOMETRYCOLLECTION (POINT (1 1), LINESTRING EMPTY); unaryUnion(d)=GEOMETRYCOLLECTION (POINT (1 1), LINESTRING EMPTY)",
        expected="No empty elements in union results; JTS unary union gives POINT (1 1); dr-jts: ideal unaryUnion(d) is probably "
                 "GEOMETRYCOLLECTION (LINESTRING(10 10, 10 10), POINT (1 1))",
        notes="d is the simpler case from dr-jts comment 2025-01-09. Inputs contain a zero-length LINESTRING, so they are invalid by OGC rules. "
              "Cause: envelope-disjoint union heuristic in Geometry::Union.")


def ev1224():
    g = {k: fresh(v) for k, v in r["geometries"].items()}
    u = shapely.union(g["a"], g["b"]); uc = shapely.union_all(g["c"]); ud = shapely.union_all(g["d"])
    has_empty = lambda x: any(p.is_empty for p in getattr(x, "geoms", [])) or x.is_empty
    obs = "union(a,b)=%s | unaryUnion(c)=%s | unaryUnion(d)=%s" % (W(u, 150), W(uc, 150), W(ud, 150))
    r["reproduces_detail"] = ("partial: union(a,b) no longer contains empty elements (the part PR #1229 fixed); unaryUnion(c) and unaryUnion(d) "
                              "still return a LINESTRING EMPTY element as reported in the issue body/comment")
    return obs, ("yes" if (has_empty(u) or has_empty(uc) or has_empty(ud)) else "no")


r["_ev"] = ev1224

# ---------------- GEOS #1248
r = rec(id="geos#1248", **gh("geos_1248"), fixed_in="3.14.0", fixed_in_basis="PR #1258 merged 2025-04-21 (a0f13d86); NEWS lists GH-1258 under 3.14.0; backport to a 3.13.x release not checked",
        geometries={"g1": "POINT ZM EMPTY"},
        operations=["union"],
        reported="POINT EMPTY (GEOS 3.13.1; GDAL autotest)",
        expected="GDAL test accepts MULTIPOINT ZM EMPTY or POINT ZM EMPTY; maintainers (dr-jts, +1 rouault) chose POINT ZM EMPTY",
        notes="Regression caused by PR #1229 (dr-jts). Coordinate-dimension preservation for EMPTY, not a geometric wrong result.")


def ev1248():
    g = fresh("POINT ZM EMPTY")
    u = shapely.union(g, g)
    obs = "union=%s has_z=%s has_m=%s" % (W(u), bool(shapely.has_z(u)), bool(shapely.has_m(u)))
    return obs, ("no" if (shapely.has_z(u) and shapely.has_m(u)) else "yes")


r["_ev"] = ev1248

# ---------------- GEOS #1275 / PostGIS #5938
rec(id="geos#1275", **gh("geos_1275"), fixed_in=None, fixed_in_basis="closed 2025-07-05; root cause found in PostGIS (mask not transposed when operands flipped), not GEOS. Milestone 3.13.1 set on the GEOS issue.",
    geometries=None, operations=["relate (pattern)", "prepared relate pattern"],
    reported="ST_Relate(g1,g2,pattern) result depends on prepared-geometry caching state (postgis-devel 2025-07-04, David Smith)",
    expected="Same result regardless of prepared state",
    notes="No geometry in the GEOS issue itself; the scenario's minimal reproducer is the PostGIS regression test recorded under postgis#5938. "
          "Original data (Kansas/Lawrence) in gist e8429f70b74bc97cd2a0a3a6193d5949 (not used). JTS test commit f664e0ff.",
    reproduces_in_geos_3_14_1=None)

r = rec(id="postgis#5938", url="https://trac.osgeo.org/postgis/ticket/5938",
        title="(trac page unreachable: anti-bot wall) ST_Relate(geom,geom,pattern) failure in certain caching situations with RelateNG prepared geometry",
        status="closed", fixed_in="PostGIS 3.5.4 / 3.6.0", fixed_in_basis=
        "commit a4886d85 (2025-07-04, 'Closes #5938'); PostGIS stable-3.5 NEWS lists #5938 under 3.5.4; compare shows 3.6.0 contains the commit",
        geometries={"a1": "LINESTRING (170 290, 205 272)", "a2": "LINESTRING (120 215, 176 197)", "a3": "LINESTRING (170 290, 205 272)",
                    "b": "POLYGON ((100 200, 140 230, 180 310, 280 310, 390 270, 400 210, 320 140, 215 141, 150 170, 100 200))"},
        operations=["relate", "relate_pattern '1FF00F212'", "prepared relate pattern with operands flipped"],
        reported="Pattern result wrong for rows after the first (cache prepares the polygon, operands swapped, mask not transposed)",
        expected="regress/core/tickets_expected: #5938|1FF00F212|t for all three rows",
        notes="Title/status from PostGIS commits a4886d85 and 74d24bc7 (GitHub mirror) because trac returned an anti-bot page. "
              "Geometries from regress/core/tickets.sql in those commits. The defect is in PostGIS's operand handling; GEOS alone is only "
              "checked for the consistency the fix relies on (relate_pattern(a,b,P) == relate_pattern(b,a,transpose(P)), with b prepared).")


def ev5938():
    g = r["geometries"]
    out = []; bad = False
    P = "1FF00F212"; PT = "".join(P[i] for i in (0, 3, 6, 1, 4, 7, 2, 5, 8))
    bp = prepared(g["b"])
    for k in ("a1", "a2", "a3"):
        a = fresh(g[k])
        m = rel(a, fresh(g["b"]))
        p1 = bool(shapely.relate_pattern(a, fresh(g["b"]), P))
        p2 = bool(shapely.relate_pattern(bp, a, PT))
        p3 = bool(shapely.relate_pattern(bp, a, P))  # the buggy (untransposed) call
        out.append("%s: relate=%s pattern=%s prepB_transposed=%s prepB_untransposed=%s" % (k, m, p1, p2, p3))
        bad |= (m != P or not p1 or not p2)
    return "; ".join(out), ("yes" if bad else "no")


r["_ev"] = ev5938

# ---------------- GEOS #1342
q = quoted("geos_1342")
r = rec(id="geos#1342", **gh("geos_1342"), geometries={"wkt1": q[0], "wkt2": q[1]}, operations=["intersection"],
        reported="intersection is invalid: 'Hole lies outside shell[-74.8816300087355 -8.66410020035459]' (GEOS 3.14.1, Shapely 2.1.2); geosop isValid=false",
        expected="valid intersection geometry", notes="dr-jts: 'Fails in JTS too.' Originally shapely#2077.")


def ev1342():
    a, b = fresh(r["geometries"]["wkt1"]), fresh(r["geometries"]["wkt2"])
    x = safe(lambda: shapely.intersection(a, b))
    if isinstance(x, str):
        return x, "unclear"
    return "valid=%s reason=%s result=%s" % (bool(x.is_valid), shapely.is_valid_reason(x), W(x, 200)), ("no" if x.is_valid else "yes")


r["_ev"] = ev1342

# ---------------- GEOS #1343
q = quoted("geos_1343")
r = rec(id="geos#1343", **gh("geos_1343"), geometries={"poly1": q[0], "poly2": q[1]}, operations=["unary_union", "union"],
        reported="union result has no hole ('islands ... get lost'); figure only, no WKT of the result",
        expected="union keeps the hole (non-covered area between the donuts); script check: area(union) <= area(poly1)+area(poly2)",
        notes="pramsey: replicates in JTS OverlayNGRobust. Originally shapely#1633.")


def ev1343():
    a, b = fresh(r["geometries"]["poly1"]), fresh(r["geometries"]["poly2"])
    u = shapely.union_all([a, b]); u2 = shapely.union(a, b)
    holes = lambda g: sum(len(p.interiors) for p in (g.geoms if hasattr(g, "geoms") else [g]))
    s = area(a) + area(b)
    obs = "unary_union: type=%s holes=%d area=%.6f; union: holes=%d area=%.6f; area1+area2=%.6f; valid=%s" % (
        u.geom_type, holes(u), area(u), holes(u2), area(u2), s, bool(u.is_valid))
    return obs, ("yes" if (area(u) > s + 1 or area(u2) > s + 1 or holes(u) == 0) else "no")


r["_ev"] = ev1343

# ---------------- GEOS #1344
q = quoted("geos_1344")
r = rec(id="geos#1344", **gh("geos_1344"), geometries={"poly1": q[0], "poly2": q[1]},
        original={"note": "issue builds polygons from Python coordinate lists; the WKT here is the issue's printed poly1.wkt / poly2.wkt output"},
        operations=["union", "unary_union", "intersection", "difference"],
        reported="union area 127.9311237202268 and union.equals(poly2)=True (unaryUnion same); intersection non-empty ('dodgy'); difference EMPTY",
        expected="union area ~255.86224744 (polygons share an edge); intersection empty",
        notes="mwtoews: normalized inputs give the correct union. pramsey: JTS gives different but also wrong results. Originally shapely#2368.")


def ev1344():
    a, b = fresh(r["geometries"]["poly1"]), fresh(r["geometries"]["poly2"])
    u = shapely.union(a, b); uu = shapely.union_all([a, b]); i = shapely.intersection(a, b); d = shapely.difference(a, b)
    obs = "union area=%.10g unary_union area=%.10g intersection=%s (area %.4g) difference area=%.10g" % (area(u), area(uu), W(i, 120), area(i), area(d))
    return obs, ("yes" if (abs(area(u) - 255.8622) > 1 or area(i) > 1e-6) else "no")


r["_ev"] = ev1344

# ---------------- GEOS #1354
q = quoted("geos_1354")
r = rec(id="geos#1354", **gh("geos_1354"), geometries={"zone": q[0], "geom_0": q[1], "geom_1": q[2]},
        operations=["intersection"],
        reported="geom_0.intersection(zone).geom_type='Point'; zone.intersection(geom_0) also Point",
        expected="Polygon (geom_1, perturbed by ~1e-14..1e-7, gives Polygon)",
        notes="geom_1 is the reporter's nearly identical control geometry. dr-jts: fails in JTS; works with snapping/snap-rounding. Originally shapely#1639.")


def ev1354():
    z, g0, g1 = (fresh(r["geometries"][k]) for k in ("zone", "geom_0", "geom_1"))
    a = shapely.intersection(g0, z); b = shapely.intersection(z, g0); c = shapely.intersection(g1, z)
    obs = "g0∩zone=%s (area %.6g); zone∩g0=%s; g1∩zone=%s (area %.6g)" % (a.geom_type, area(a), b.geom_type, c.geom_type, area(c))
    return obs, ("yes" if (a.geom_type != "Polygon" or b.geom_type != "Polygon") else "no")


r["_ev"] = ev1354

# ---------------- GEOS #1355
q = quoted("geos_1355")
r = rec(id="geos#1355", **gh("geos_1355"), geometries={"buffer_0": q[1], "buffer_1": q[2], "buffer_2": q[3]},
        operations=["unary_union"],
        reported="AssertionFailedException: found two shells in EdgeRing list (GEOS 3.14.1)",
        expected="a polygon (CCW-oriented inputs give a POLYGON)",
        notes="Error rather than wrong result. The issue's geosop GEOMETRYCOLLECTION of the three polygons is equivalent.")


def ev1355():
    gs = [fresh(r["geometries"][k]) for k in ("buffer_0", "buffer_1", "buffer_2")]
    x = safe(lambda: shapely.union_all(gs))
    if isinstance(x, str):
        return x, ("yes" if "two shells" in x else "unclear")
    return "result=%s valid=%s" % (W(x, 200), bool(x.is_valid)), "no"


r["_ev"] = ev1355

# ---------------- GEOS #1383
q = quoted("geos_1383")
r = rec(id="geos#1383", **gh("geos_1383"), geometries={"ex0_1": q[0], "ex0_2": q[1], "ex1_1": q[2], "ex1_2": q[3]},
        operations=["union"],
        reported="union_geom=<POLYGON EMPTY> for both examples",
        expected="non-empty result (union of two non-empty valid polygons should never be empty); JTS OverlayNGRobust gives a MULTILINESTRING (collapse after snapping)",
        notes="Second example added by theroggy 2026-02-10 (in the issue body). dr-jts: lower priority than other OverlayNG failures.")


def ev1383():
    g = {k: fresh(v) for k, v in r["geometries"].items()}
    u0 = shapely.union(g["ex0_1"], g["ex0_2"]); u1 = shapely.union(g["ex1_1"], g["ex1_2"])
    return "ex0 union=%s | ex1 union=%s" % (W(u0, 140), W(u1, 140)), ("yes" if (u0.is_empty or u1.is_empty) else "no")


r["_ev"] = ev1383

# ---------------- GEOS #1405
q = quoted("geos_1405")
r = rec(id="geos#1405", **gh("geos_1405"), fixed_in="3.15.0", fixed_in_basis="PR #1499 merged 2026-08-12 (737737db); NEWS 3.15.0: 'Fix intersection result for slightly overlapping polygons (GH-1499)'; compare: 3.15.0 contains it, 3.14.1 does not",
        geometries={"shape1": q[0], "shape2": q[1],
                    "pr1499_a": "POLYGON ((1 1, 0 0.5, 0 0, 1 1))", "pr1499_b": "POLYGON ((1 1, 0 0.49999999999999994, 0 1, 1 1))"},
        operations=["intersection"],
        reported="intersection(shape1, shape2) wrong (figure 'Wrong behavior'); depends on argument order (GEOS 3.13.1)",
        expected="intersection(shape2, shape1) (figure 'Expected behavior'); order-independent result",
        notes="The reproducer applies buffer(0) then normalize() to both shapes before intersecting; evaluated both raw and with that preprocessing (geometries stored unaltered). Figure only, no result WKT. "
              "pr1499_a/pr1499_b: the fix PR's own simpler example (PR body: before the fix intersection area 0.25 instead of ~0; reproduced there with GEOS 3.13.1). "
              "In Shapely 2.2.0/GEOS 3.14.1 neither case shows order dependence even though the fix is only in 3.15.0; reason not established (possibly 3.13-only behaviour or platform/compiler dependent).")


def ev1405():
    s1, s2 = fresh(r["geometries"]["shape1"]), fresh(r["geometries"]["shape2"])
    out = []; bad = False
    for lab, (a, b) in (("raw", (s1, s2)), ("buffer0+normalize", (shapely.normalize(shapely.buffer(s1, 0)), shapely.normalize(shapely.buffer(s2, 0))))):
        x = shapely.intersection(a, b); y = shapely.intersection(b, a)
        sd = area(shapely.symmetric_difference(x, y))
        out.append("%s: area(s1∩s2)=%.10g area(s2∩s1)=%.10g area(symdiff of the two results)=%.3g" % (lab, area(x), area(y), sd))
        bad |= sd > 1e-9 * max(area(x), area(y), 1e-300)
    pa, pb = fresh(r["geometries"]["pr1499_a"]), fresh(r["geometries"]["pr1499_b"])
    x, y = area(shapely.intersection(pa, pb)), area(shapely.intersection(pb, pa))
    out.append("pr1499: area(a∩b)=%.3g area(b∩a)=%.3g (bug: 0.25)" % (x, y))
    bad |= max(x, y) > 0.01
    return "; ".join(out), ("yes" if bad else "no")


r["_ev"] = ev1405

# ---------------- GEOS #1523
f = fences("geos_1523")
r = rec(id="geos#1523", **gh("geos_1523"), geometries={"a": f[0], "b": f[1]},
        operations=["intersection", "difference"],
        reported="A∩B = POLYGON ((379.694383 3427.1997129264923, 380.736005 3427.1997128766443, 379.777158 3427.199712922531, 379.694383 3427.1997129264923)), area 5.01746e-15; A−B area 11.528085",
        expected="A∩B area ~11.528085; A−B area ~0 (tiny portion of the hole); B−A ~36.571915 (not ~48.1)",
        notes="b WKT spans two lines in the issue (kept with the newline). Fix proposed in open PR #1524. Reproduced by reporter on 3.13.1 and 3.16.0dev 55809ca8d.")


def ev1523():
    a, b = fresh(r["geometries"]["a"]), fresh(r["geometries"]["b"])
    i = shapely.intersection(a, b); d = shapely.difference(a, b); d2 = shapely.difference(b, a)
    obs = "area(A∩B)=%.10g area(A−B)=%.10g area(B−A)=%.10g" % (area(i), area(d), area(d2))
    return obs, ("yes" if abs(area(i) - 11.528085) > 0.01 else "no")


r["_ev"] = ev1523

# ---------------- GEOS #1540 / JTS #1237
bj = body("jts_1237")
hA_trunc = re.search(r"A: ([0-9A-F]+)", bj).group(1); hB = re.search(r"B: ([0-9A-F]+)", bj).group(1)
strk = [c for c in comments("geos_1530") if "-c relate" in c["body"]][0]
hA = re.search(r"-a ([0-9A-F]+)", strk["body"]).group(1); hB2 = re.search(r"-b ([0-9A-F]+)", strk["body"]).group(1)
assert hB2 == hB
gA, gB = from_wkb(bytes.fromhex(hA)), from_wkb(bytes.fromhex(hB))
r = rec(id="geos#1540", **gh("geos_1540"),
        geometries={"A": shapely.to_wkt(gA, rounding_precision=-1), "B": shapely.to_wkt(gB, rounding_precision=-1)},
        original={"format": "EWKB hex, SRID 4258", "A": hA, "B": hB,
                  "A_as_printed_in_jts_1237": hA_trunc,
                  "note": "The A hex in JTS #1237 (and #1236) is truncated (%d hex chars; a 3-point EWKB line needs 122) and does not parse; "
                          "the complete A used here is from strk's geosop command in GEOS #1530 (comment %s), whose B equals JTS #1237's B." % (len(hA_trunc), strk["html_url"])},
        operations=["relate", "crosses", "linemerge+is_simple (context)"],
        reported="relate(A,B)=FF1F00102 (no interior-interior intersection); geosop crosses=false",
        expected="interior-interior intersection present (II not F), per dr-jts in JTS #1236: B crosses A near a vertex of A; IsSimpleOp detects it",
        notes="Upstream JTS #1237 (open). Root cause per dr-jts: RelateOp uses computed intersection points, which round onto B's endpoint. SRID dropped in WKT.")


def ev1540():
    A, B = fresh(r["geometries"]["A"]), fresh(r["geometries"]["B"])
    m = rel(A, B); c = bool(shapely.crosses(A, B))
    lm = shapely.line_merge(shapely.union_all([A, B]) if False else shapely.multilinestrings([A, B]))
    obs = "relate(A,B)=%s crosses=%s relate(B,A)=%s line_merge(A,B) is_simple=%s" % (m, c, rel(B, A), bool(shapely.is_simple(lm)))
    return obs, ("yes" if m[0] == "F" else "no")


r["_ev"] = ev1540

# ---------------- GEOS #1558 (deleted) via PR #1565 test 65
r = rec(id="geos#1558", url="https://github.com/libgeos/geos/issues/1558",
        title="(issue deleted; API returns 404) RelateNG wrong result for polygon with hole touching the shell (per PR #1565 'tangent-hole containment case')",
        status="deleted", fixed_in=None, fixed_in_basis="Fix PR #1565 'fix(relateng): self-node polygons with holes (fixes #1558)' was closed unmerged 2026-10-20; no later commit to src/operation/relateng/RelateGeometry.cpp on main (last 2025-12-16)",
        geometries={"a": "POLYGON ((0 0,4 0,4 4,0 4,0 0),(2 0,1 1,3 1,2 0))", "b": "POLYGON ((0 0,4 0,4 4,0 4,0 0))"},
        original={"source": "https://github.com/libgeos/geos/pull/1565 tests/unit/operation/relateng/RelateNGTest.cpp test<65>"},
        operations=["relate", "contains/within", "covers/coveredBy", "overlaps"],
        reported="Not obtainable (issue body deleted). Surviving comments (dr-jts 2026-10-13/14): 'This is indeed a bug, and exists in JTS as well'; fix is to require self-noding for polygons with holes in RelateGeometry.isSelfNodingRequired",
        expected="From test 65: relate(a,b)=2FF11F2F2, relate(b,a)=212F1FFF2, contains(b,a)=true, within(a,b)=true, covers(b,a)=true, coveredBy(a,b)=true, overlaps(a,b)=false",
        notes="Hole touches the shell at (2 0) (valid polygon). Test expectations were written by the PR author and CI-checked per the PR text; the PR was not merged.")


def ev1558():
    a, b = fresh(r["geometries"]["a"]), fresh(r["geometries"]["b"])
    bp, ap = prepared(r["geometries"]["b"]), prepared(r["geometries"]["a"])
    vals = dict(relate_ab=rel(a, b), relate_ba=rel(b, a), contains_ba=bool(shapely.contains(b, a)), within_ab=bool(shapely.within(a, b)),
                covers_ba=bool(shapely.covers(b, a)), coveredby_ab=bool(shapely.covered_by(a, b)), overlaps_ab=bool(shapely.overlaps(a, b)),
                contains_ba_prep=bool(shapely.contains(bp, a)), covers_ba_prep=bool(shapely.covers(bp, a)), within_ab_prep=bool(shapely.within(ap, b)))
    exp = dict(relate_ab="2FF11F2F2", relate_ba="212F1FFF2", contains_ba=True, within_ab=True, covers_ba=True, coveredby_ab=True, overlaps_ab=False,
               contains_ba_prep=True, covers_ba_prep=True, within_ab_prep=True)
    diff = [k for k in exp if vals[k] != exp[k]]
    return " ".join("%s=%s" % kv for kv in vals.items()) + " | mismatches vs test 65: %s" % (diff or "none"), ("yes" if diff else "no")


r["_ev"] = ev1558

# ---------------- JTS #1239
q = quoted("jts_1239")
r = rec(id="jts#1239", **gh("jts_1239"), geometries={"a": q[0], "b": q[1]}, operations=["symDifference", "union", "difference"],
        reported="symDifference area -0.031229999995478153, invalid (JTS 1.20); GEOS 3.15.0 and main 7312930: area -0.031229999995477611, invalid (Self-intersection)",
        expected="area 0.03123, valid (areal part of a ⊕ b is a)",
        notes="Found by the reporter's fuzzer (NTS legacy overlay vs OverlayNG with area bounds). Fix proposal: lower bound in OverlayUtil.isResultAreaConsistent for SYMDIFFERENCE.")


def ev1239():
    a, b = fresh(r["geometries"]["a"]), fresh(r["geometries"]["b"])
    s = shapely.symmetric_difference(a, b); u = shapely.union(a, b); d = shapely.difference(a, b)
    obs = "symdiff area=%.17g valid=%s (%s); union area=%.10g; difference area=%.10g" % (area(s), bool(s.is_valid), shapely.is_valid_reason(s), area(u), area(d))
    return obs, ("yes" if (area(s) < 0 or not s.is_valid) else "no")


r["_ev"] = ev1239

# ---------------- JTS #1222
f = fences("jts_1222")
r = rec(id="jts#1222", **gh("jts_1222"), geometries={"polygon": f[0], "neg_buffer": f[1]},
        operations=["difference"],
        reported="difference result with outer-ring vertices moved (rounded to 0.1): " + f[2].replace("\n", " ")[:300] + "...",
        expected="outer ring vertices unchanged (equal to the input polygon's)",
        notes="WKT spans several lines in the issue (kept with newlines). dr-jts could not reproduce in 1.20 or master; result is rounded to one decimal; "
              "reporter uses a PrecisionModel scale 100 in GeoTools. Likely not an OverlayNG defect.")


def ev1222():
    p, nb = fresh(r["geometries"]["polygon"]), fresh(r["geometries"]["neg_buffer"])
    d = shapely.difference(p, nb)
    pin = set(map(tuple, shapely.get_coordinates(p.exterior)))
    ext = d.exterior if d.geom_type == "Polygon" else None
    pout = set(map(tuple, shapely.get_coordinates(ext))) if ext is not None else set()
    moved = pin - pout
    obs = "difference type=%s holes=%s input exterior vertices missing from result exterior=%d of %d" % (
        d.geom_type, len(d.interiors) if ext is not None else None, len(moved), len(pin))
    return obs, ("yes" if moved else "no")


r["_ev"] = ev1222

# ---------------- checks
for r in records:
    ev = r.pop("_ev", None)
    if r["geometries"] is None:
        continue
    chk = {}
    for k, w in r["geometries"].items():
        try:
            g = from_wkt(w)
            chk[k] = {"parses": True, "geom_type": g.geom_type, "is_valid": bool(g.is_valid),
                      "explain_validity": None if g.is_valid else shapely.is_valid_reason(g)}
        except Exception as e:
            chk[k] = {"parses": False, "error": str(e)}
    r["check"] = chk
    if ev:
        obs, rep = ev()
        r["observed_geos_3_14_1"] = obs
        r["reproduces_in_geos_3_14_1"] = rep

out = {"generated_with": {"shapely": shapely.__version__, "geos": shapely.geos_version_string},
       "notes": "Geometry text is verbatim from the cited issue/test (CRLF normalised to LF). WKB/EWKB inputs converted with "
                "shapely.to_wkt(rounding_precision=-1); hex kept in `original`. reproduces_in_geos_3_14_1 is decided by the per-record "
                "rule in seeds/tools/build_known_bugs.py (ev* functions). Raw issue downloads are in seeds/raw.",
       "records": records}
with open(os.path.join(SEEDS, "known_bugs.json"), "w", encoding="utf-8") as fh:
    json.dump(out, fh, indent=2, ensure_ascii=False)
for r in records:
    print(r["id"], "| geoms:", r["geometries"] is not None, "| valid:",
          None if not r["check"] else {k: v.get("is_valid") for k, v in r["check"].items()},
          "| repro:", r["reproduces_in_geos_3_14_1"])
    print("   ", (r["observed_geos_3_14_1"] or "")[:400])
