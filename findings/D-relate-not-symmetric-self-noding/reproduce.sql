-- Family D: ST_Relate(b, a) is not the transpose of ST_Relate(a, b). Finding key 27262e8ca8d1.
SELECT substring(postgis_full_version() from 'POSTGIS="([^ "]+)') AS postgis,
       substring(postgis_full_version() from 'GEOS="([^ "]+)') AS geos;
SELECT r_ab, r_ba, transposed_r_ab, r_ba = transposed_r_ab AS symmetric_expected_true
FROM (SELECT r_ab, r_ba, (SELECT string_agg(substr(r_ab, 3 * c + r + 1, 1), '' ORDER BY r, c)
                          FROM generate_series(0, 2) r, generate_series(0, 2) c) AS transposed_r_ab
      FROM (SELECT ST_Relate(a, b) AS r_ab, ST_Relate(b, a) AS r_ba
            FROM (SELECT 'POLYGON ((632510 596465, 632512 596476, 632503 596468, 632510 596465))'::geometry AS a,
                         'GEOMETRYCOLLECTION (POLYGON ((632512 596457, 632523 596483, 632485 596477, 632512 596457), (632510 596469, 632514 596476, 632506 596475, 632510 596469)), POLYGON ((632510 596465, 632512 596476, 632510 596470, 632510 596465)))'::geometry AS b) g) m) x;
