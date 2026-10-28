# Family B: prepared Contains is True for a collection of a boundary point plus an empty member.
# Hand-made smaller input (unit triangle, point on its bottom edge); provenance: family B,
# smallest Contains finding 072283bc43b2 (same shape: triangle, GC(POLYGON EMPTY, vertex point)).
import shapely

A = shapely.from_wkt("POLYGON ((0 0, 1 0, 0 1, 0 0))")
CASES = ["GEOMETRYCOLLECTION (POINT (0.5 0), POLYGON EMPTY)",
         "GEOMETRYCOLLECTION (POINT (0.5 0), LINESTRING EMPTY)",
         "POINT (0.5 0)"]
Ap = shapely.from_wkt(A.wkt)
shapely.prepare(Ap)
print("Shapely", shapely.__version__, "GEOS", shapely.geos_version_string)
print("a =", A.wkt)
bad = 0
for w in CASES:
    b = shapely.from_wkt(w)
    un, pr = shapely.contains(A, b), shapely.contains(Ap, b)
    bad += un != pr
    print(f"b = {w}\n  relate(a, b) = {shapely.relate(A, b)}  contains = {un}  prepared contains = {pr}")
print("expected: False everywhere (the point lies on the boundary of a: relate II=F, so a does not contain b)")
print("verdict:", f"BUG reproduced, prepared Contains disagrees in {bad} of {len(CASES)} cases" if bad else "not reproduced")
