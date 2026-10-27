import shapely
a=shapely.from_wkt('POLYGON ((1 1, 0 0.5, 0 0, 1 1))'); b=shapely.from_wkt('POLYGON ((1 1, 0 0.49999999999999994, 0 1, 1 1))')
print(shapely.intersection(a,b).area, shapely.intersection(b,a).area, shapely.union(a,b).area, a.is_valid, b.is_valid)
