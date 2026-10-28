# Family F (candidate): wrapping a valid multipolygon with a hole tangent to its shell in a
# GeometryCollection changes relate. Finding key 0f60d799288b. In PostGIS: ST_ForceCollection(a).
import shapely

a = shapely.from_wkt("MULTIPOLYGON (((778596 894741, 778576 894719, 778597 894724, 778596 894741)), "
                     "((778596 894741, 778604 894748, 778606 894738, 778596 894741), "
                     "(778596 894741, 778598 894742, 778598 894741, 778596 894741)))")
b = shapely.from_wkt("MULTIPOLYGON (((778535 894759, 778501 894754, 778462 894786, 778535 894759)))")
fa = shapely.GeometryCollection(list(shapely.get_parts(a)))  # as tavs/triage_shapely._force_collection
print("Shapely", shapely.__version__, "GEOS", shapely.geos_version_string)
print("a =", a.wkt, "\nb =", b.wkt, "\nvalid:", a.is_valid, b.is_valid)
lone, wrapped = shapely.relate(a, b), shapely.relate(fa, b)
print("relate(a, b)                 =", lone)
print("relate(ForceCollection(a), b) =", wrapped)
print("expected: the same matrix (same point set); a and b are disjoint, so EB should be 1")
print("verdict:", "reproduced, wrapping changes relate (candidate bug)" if lone != wrapped else "not reproduced")
