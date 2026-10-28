# Family G: precision effects, not bugs. G1 key d28da70b91e1 (smallest G1 finding),
# G3 key 1a5492238a9a (smallest G3 finding). Grid size 1e-07 as in the triage (R11 grid).
import shapely

W = shapely.from_wkt
print("Shapely", shapely.__version__, "GEOS", shapely.geos_version_string)
# G1: relate says the interiors overlap in 2D, but the overlay sliver collapses below one double step
a = W("MULTIPOLYGON (((385381.9 526823.6, 385377.7 526822.0, 385379.8 526819.9, 385381.9 526823.6)))")
b = W("POLYGON ((385382.9 526823.1, 385381.9 526826.2, 385378.7 526825.2, 385382.9 526823.1))")
m, i = shapely.relate(a, b), shapely.intersection(a, b)
print("G1 a =", a.wkt, "\n   b =", b.wkt)
print("   relate(a, b) =", m, " II =", m[0], "\n   intersection(a, b) =", i.wkt, " dimension =", shapely.get_dimensions(i))
print("   expected for exact arithmetic: dimension = II; here a precision effect gives", m[0], "vs", shapely.get_dimensions(i))
# G3: floating intersection of two almost collinear lines is a point; on a 1e-07 grid they snap onto one line
G = 1e-07
a = W("MULTILINESTRING ((771384.3 141360.0, 771392.4 141493.5))")
b = W("LINESTRING (771384.3 141360.0, 771387.0 141404.5)")
f, g = shapely.intersection(a, b), shapely.intersection(a, b, grid_size=G)
print("G3 a =", a.wkt, "\n   b =", b.wkt)
print("   intersection(a, b)              =", f.wkt, " length =", f.length)
print(f"   intersection(a, b, grid_size={G}) =", g.wkt, " length =", g.length)
print("   expected: floating length 0 is correct for the stored doubles (not exactly collinear); the grid snaps them")
ok = m[0] == "2" and shapely.get_dimensions(i) < 2 and f.length == 0 and g.length > 0
print("verdict:", "both precision effects reproduced (not bugs)" if ok else "not reproduced as stated")
