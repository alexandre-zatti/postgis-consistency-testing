# Family D: relate(b, a) is not the transpose of relate(a, b); b is a collection whose
# members overlap, so the result depends on which argument comes first. Finding key 27262e8ca8d1.
import shapely

a = shapely.from_wkt("POLYGON ((632510 596465, 632512 596476, 632503 596468, 632510 596465))")
b = shapely.from_wkt("GEOMETRYCOLLECTION (POLYGON ((632512 596457, 632523 596483, 632485 596477, 632512 596457), "
                     "(632510 596469, 632514 596476, 632506 596475, 632510 596469)), "
                     "POLYGON ((632510 596465, 632512 596476, 632510 596470, 632510 596465)))")


def transpose(m):
    return "".join(m[3 * c + r] for r in range(3) for c in range(3))


ab, ba = shapely.relate(a, b), shapely.relate(b, a)
print("Shapely", shapely.__version__, "GEOS", shapely.geos_version_string)
print("a =", a.wkt, "\nb =", b.wkt)
print("relate(a, b)            =", ab)
print("relate(b, a)            =", ba)
print("transpose(relate(a, b)) =", transpose(ab))
print("expected: relate(b, a) = transpose(relate(a, b))")
print("verdict:", "BUG reproduced, the matrices are not transposes" if ba != transpose(ab) else "not reproduced")
