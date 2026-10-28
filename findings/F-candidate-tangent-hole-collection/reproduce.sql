-- Family F (candidate): ST_ForceCollection(a) changes ST_Relate on valid inputs. Key 0f60d799288b.
SELECT substring(postgis_full_version() from 'POSTGIS="([^ "]+)') AS postgis,
       substring(postgis_full_version() from 'GEOS="([^ "]+)') AS geos;
-- expected: the two matrices are equal
SELECT ST_IsValid(a) AND ST_IsValid(b) AS valid, ST_Relate(a, b) AS lone, ST_Relate(ST_ForceCollection(a), b) AS wrapped
FROM (SELECT 'MULTIPOLYGON (((778596 894741, 778576 894719, 778597 894724, 778596 894741)), ((778596 894741, 778604 894748, 778606 894738, 778596 894741), (778596 894741, 778598 894742, 778598 894741, 778596 894741)))'::geometry AS a,
             'MULTIPOLYGON (((778535 894759, 778501 894754, 778462 894786, 778535 894759)))'::geometry AS b) g;
