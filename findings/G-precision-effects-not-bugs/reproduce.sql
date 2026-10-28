-- Family G: precision effects, not bugs. G1 key d28da70b91e1, G3 key 1a5492238a9a; grid 1e-07.
SELECT substring(postgis_full_version() from 'POSTGIS="([^ "]+)') AS postgis,
       substring(postgis_full_version() from 'GEOS="([^ "]+)') AS geos;
-- G1: relate II = 2, but the intersection collapses to a lower dimension
SELECT ST_Relate(a, b) AS relate, ST_AsText(ST_Intersection(a, b)) AS intersection, ST_Dimension(ST_Intersection(a, b)) AS dim
FROM (SELECT 'MULTIPOLYGON (((385381.9 526823.6, 385377.7 526822.0, 385379.8 526819.9, 385381.9 526823.6)))'::geometry AS a,
             'POLYGON ((385382.9 526823.1, 385381.9 526826.2, 385378.7 526825.2, 385382.9 526823.1))'::geometry AS b) g;
-- G3: floating intersection length 0 (correct for the stored doubles), fixed-grid length > 0
SELECT ST_Length(ST_Intersection(a, b)) AS floating_length, ST_Length(ST_Intersection(a, b, 1e-07)) AS fixed_length,
       ST_AsText(ST_Intersection(a, b, 1e-07)) AS fixed
FROM (SELECT 'MULTILINESTRING ((771384.3 141360.0, 771392.4 141493.5))'::geometry AS a,
             'LINESTRING (771384.3 141360.0, 771387.0 141404.5)'::geometry AS b) g;
