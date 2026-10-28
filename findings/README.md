# Findings: one small reproducer per problem family

Each folder shows one family from [docs/04-results.md](../docs/04-results.md) on the smallest
clear input we have. Each one contains:

- `reproduce.py`: Shapely only (GEOS 3.14.1 inside Shapely 2.2.0). It prints the inputs, the
  results, what the right answer is, and a one-line verdict.
- `reproduce.sql`: the same check in plain PostGIS SQL, for `psql`.
- `expected_output.txt`: what we observed on 2026-10-28, in Shapely and in PostGIS current
  (3.6.4 / GEOS 3.14.1) and development (3.7.0dev / GEOS 3.16.0dev).

Each script names, in a comment, the finding it comes from (its key in
`runs/e3/triage/findings.json`).

| Folder | What you will see | Class |
|---|---|---|
| [A-relateng-crash-empty-polygon](A-relateng-crash-empty-polygon/) | GEOS crashes (segmentation fault) on a collection holding `POLYGON EMPTY` and two polygons touching at a point; without the empty polygon the answer is `FF20F1FF2` | new defect |
| [B-prepared-contains-empty-member](B-prepared-contains-empty-member/) | a triangle "contains" a point on its own edge when the point comes with an empty part, but only on the prepared (cached) path | unreported variant of a known cause |
| [C-relateng-rounding-vs-prepared](C-relateng-rounding-vs-prepared/) | direct and prepared Contains disagree on decimal polygons; an exact check shows the prepared answer is right | known open issue (GEOS #740) |
| [D-relate-not-symmetric-self-noding](D-relate-not-symmetric-self-noding/) | `relate(b, a)` is not the transpose of `relate(a, b)`, on whole-number coordinates | known open issue (GEOS #1558) |
| [F-candidate-tangent-hole-collection](F-candidate-tangent-hole-collection/) | wrapping a valid shape in a collection changes its relationship matrix | candidate |
| [G-precision-effects-not-bugs](G-precision-effects-not-bugs/) | two rounding effects: a sliver overlap returned as a point, and a fixed-grid overlay that invents a 44.6-unit overlap where the true one has length 0 | not bugs |

Family E (one unexplained case) has no folder.

## Safety

- Every `reproduce.py` that can crash runs the crashing call in a child process, so the script
  itself survives and reports the exit code. On Windows, a crash shows as exit code
  3221225477 (0xC0000005); on Linux, as -11 or 139.
- **`A-.../reproduce.sql` crashes the PostgreSQL server process.** Run it only on a throwaway
  container, for example:
  `docker run -d --rm -e POSTGRES_PASSWORD=postgis -p 127.0.0.1:54390:5432 postgis/postgis:18-3.6`.
- The SQL for B runs one query per input on purpose. When all inputs were in one grouped query,
  PostgreSQL reordered the rows and the cached (prepared) shape carried over between inputs,
  which changed the results.

## Notes found while writing these

- **A, which ring start matters.** In the original finding, rotating one polygon's ring so it
  does not start at the touching point avoided the crash (`ring_start_variants.py`). With the
  minimal point query, every ring start crashes. With a disjoint polygon as the other argument,
  only the first member's start matters.
  - **A possible explanation, not verified:** the crashing locator is built when a point being
    located lies on two polygon boundaries. That point can be the query point itself, or the
    first vertex of a ring, which RelateNG tests.
- **B, a second crash (open lead, outside the registered results).** On the unit square
  `POLYGON ((0 0, 1 0, 1 1, 0 1, 0 0))`, prepared Contains against
  `GEOMETRYCOLLECTION (POINT (0.5 0), LINESTRING EMPTY)` crashes Shapely. The same happens with
  `POINT EMPTY`. With `POLYGON EMPTY` it returns True, and the triangle does not crash.
  - This was found by hand on 2026-10-28, not by the campaign.
  - It has not been tested in PostGIS, and its cause is unknown.
