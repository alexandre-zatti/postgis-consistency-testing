import sys, shapely
fn, a, b = sys.argv[1], shapely.from_wkt(sys.argv[2]), shapely.from_wkt(sys.argv[3])
if fn == "prepared_intersects":
    shapely.prepare(a)
    r = shapely.intersects(a, b)
else:
    r = getattr(shapely, fn)(a, b)
print(r, flush=True)
