-- Family B: prepared Contains is true for GC(boundary point, empty member); unprepared is false.
-- Hand-made input (unit triangle, point on its bottom edge); provenance: key 072283bc43b2.
-- PostGIS prepares a geometry it sees repeated across rows: call 1 is plain, calls 2-3 prepared.
SELECT substring(postgis_full_version() from 'POSTGIS="([^ "]+)') AS postgis,
       substring(postgis_full_version() from 'GEOS="([^ "]+)') AS geos;
-- relate: expected FF20F1FF2 (II=F, so a does not contain b)
SELECT ST_Relate('POLYGON ((0 0, 1 0, 0 1, 0 0))', 'GEOMETRYCOLLECTION (POINT (0.5 0), POLYGON EMPTY)') AS relate;
-- expected {f,f,f} in each query
SELECT 'GC(POINT, POLYGON EMPTY)' AS b, array_agg(ST_Contains('POLYGON ((0 0, 1 0, 0 1, 0 0))'::geometry, g) ORDER BY o) AS plain_prepared_prepared
FROM unnest(array_fill('GEOMETRYCOLLECTION (POINT (0.5 0), POLYGON EMPTY)'::geometry, ARRAY[3])) WITH ORDINALITY t(g, o);
SELECT 'GC(POINT, LINESTRING EMPTY)' AS b, array_agg(ST_Contains('POLYGON ((0 0, 1 0, 0 1, 0 0))'::geometry, g) ORDER BY o) AS plain_prepared_prepared
FROM unnest(array_fill('GEOMETRYCOLLECTION (POINT (0.5 0), LINESTRING EMPTY)'::geometry, ARRAY[3])) WITH ORDINALITY t(g, o);
SELECT 'POINT' AS b, array_agg(ST_Contains('POLYGON ((0 0, 1 0, 0 1, 0 0))'::geometry, g) ORDER BY o) AS plain_prepared_prepared
FROM unnest(array_fill('POINT (0.5 0)'::geometry, ARRAY[3])) WITH ORDINALITY t(g, o);
