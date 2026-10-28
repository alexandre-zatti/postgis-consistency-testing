-- Family C: unprepared Contains(b, a) is true, prepared is false (prepared is right: one vertex
-- of a lies about 1e-10 outside b). Finding key 0a0bf9c866ea.
SELECT substring(postgis_full_version() from 'POSTGIS="([^ "]+)') AS postgis,
       substring(postgis_full_version() from 'GEOS="([^ "]+)') AS geos;
-- expected: relate EI and EB not both F, contains false
SELECT ST_Relate(b, a) AS relate_b_a, ST_Contains(b, a) AS contains_b_a
FROM (SELECT 'POLYGON ((699317.1 244195.2, 699309.1 244173.4, 699351.3 244184.3, 699317.1 244195.2))'::geometry AS a,
             'POLYGON ((699313.1 244162.7, 699370.8 244179.0, 699315.8 244199.1, 699305.1 244184.1, 699313.1 244162.7))'::geometry AS b) g;
-- b repeated across rows is prepared from call 2 on; expected {f,f,f}
SELECT array_agg(ST_Contains('POLYGON ((699313.1 244162.7, 699370.8 244179.0, 699315.8 244199.1, 699305.1 244184.1, 699313.1 244162.7))'::geometry, a) ORDER BY o) AS plain_prepared_prepared
FROM unnest(ARRAY['POLYGON ((699317.1 244195.2, 699309.1 244173.4, 699351.3 244184.3, 699317.1 244195.2))'::geometry,
                  'POLYGON ((699317.1 244195.2, 699309.1 244173.4, 699351.3 244184.3, 699317.1 244195.2))'::geometry,
                  'POLYGON ((699317.1 244195.2, 699309.1 244173.4, 699351.3 244184.3, 699317.1 244195.2))'::geometry]) WITH ORDINALITY t(a, o);
