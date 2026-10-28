-- Family A: RelateNG crash, collection with POLYGON EMPTY plus two polygons touching at (0 0).
-- Hand-made minimal input; provenance: family A, smallest shrunk key 924d7491356c.
-- WARNING: the last query crashes the server backend. Run only on a throwaway container.
SELECT substring(postgis_full_version() from 'POSTGIS="([^ "]+)') AS postgis,
       substring(postgis_full_version() from 'GEOS="([^ "]+)') AS geos;
-- without the empty member: expected FF20F1FF2
SELECT ST_Relate('GEOMETRYCOLLECTION (POLYGON ((0 0, 1 0, 0 1, 0 0)), POLYGON ((0 0, -1 0, 0 -1, 0 0)))',
                 'POINT (0 0)') AS without_empty;
-- with the empty member: expected the same matrix; observed: the backend crashes
SELECT ST_Relate('GEOMETRYCOLLECTION (POLYGON EMPTY, POLYGON ((0 0, 1 0, 0 1, 0 0)), POLYGON ((0 0, -1 0, 0 -1, 0 0)))',
                 'POINT (0 0)') AS with_empty;
