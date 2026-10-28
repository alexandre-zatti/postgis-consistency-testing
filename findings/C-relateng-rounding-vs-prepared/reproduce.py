# Family C: on float polygons, unprepared Contains/relate (RelateNG) says b contains a;
# prepared Contains says no. Finding key 0a0bf9c866ea (smallest family C finding, unchanged).
from fractions import Fraction
import shapely

a = shapely.from_wkt("POLYGON ((699317.1 244195.2, 699309.1 244173.4, 699351.3 244184.3, 699317.1 244195.2))")
b = shapely.from_wkt("POLYGON ((699313.1 244162.7, 699370.8 244179.0, 699315.8 244199.1, 699305.1 244184.1, 699313.1 244162.7))")
bp = shapely.from_wkt(b.wkt)
shapely.prepare(bp)
print("Shapely", shapely.__version__, "GEOS", shapely.geos_version_string)
print("a =", a.wkt, "\nb =", b.wkt)
un, pr = shapely.contains(b, a), shapely.contains(bp, a)
print("relate(b, a) =", shapely.relate(b, a), " contains(b, a) =", un, " prepared contains(b, a) =", pr)
# exact check on the stored doubles: vertex v of a against edge p->q of b (b is counter-clockwise,
# so a negative cross product means v is strictly outside b)
p, q, v = [tuple(map(Fraction, t)) for t in ((699305.1, 244184.1), (699313.1, 244162.7), (699309.1, 244173.4))]
cross = (q[0] - p[0]) * (v[1] - p[1]) - (q[1] - p[1]) * (v[0] - p[0])
print("exact cross product of a's vertex (699309.1 244173.4) on b's edge:", float(cross), "(< 0: outside b)")
print("expected: contains(b, a) = False, because one vertex of a lies outside b by about 1e-10")
print("verdict:", "BUG reproduced, unprepared (RelateNG) is wrong, prepared is right" if un and not pr and cross < 0 else "not reproduced")
