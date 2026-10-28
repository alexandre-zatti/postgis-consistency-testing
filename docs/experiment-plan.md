# Experiment plan: consistency testing of PostGIS/GEOS spatial operations

Status 2026-10-27: accepted by Alexandre for execution; revised after an independent adversarial
review (decisions at the end). Paper title: *Testing the Consistency of Spatial Operations in
PostGIS Through Property-Based and Differential Testing*. Background: `docs/01-background.md`.
Code and data: this repository (map in `README.md`).

## Constraints

- Course final project (MCET063, assignment PDF in this folder): software artifact, experimental
  evaluation, paper, presentation. Two weeks from 2026-10-27; Alexandre works alone.
- Answerable with zero new bugs. No bug count promised. Upstream reports only with Alexandre's OK.
- Code and data stay local; nothing published without Alexandre's OK.

## Questions

- **RQ1.** Which consistency rules between PostGIS spatial functions (predicates and overlays)
  flag wrong or inconsistent results in current PostGIS/GEOS, on which inputs, and how do the
  flags sort into defects, path inconsistencies and precision effects?
- **RQ2.** Under equal pair budgets, does degenerate-targeted generation flag more than plain
  random generation, separately for integer-grid and floating-point coordinates (2×2)?
- **RQ3.** Sensitivity: of known wrong-result bugs with reproducers, how many do the
  pre-registered rules flag on a version that has the bug, and how many false alarms do the
  rules raise where it is absent?

## Targets

| Role | Image (digest in `compose.yaml`) | Versions confirmed 2026-10-27 |
|---|---|---|
| Current (main target) | `postgis/postgis:18-3.6` | PostgreSQL 18.6, PostGIS 3.6.4 `94d984b`, GEOS 3.14.1 at run time (PostGIS compiled against 3.13.1) |
| Development (triage, #1405 absence) | `postgis/postgis:18-master` | PostgreSQL 18.6, PostGIS 3.7.0dev `3.7.0rc3-1-g4db4d8050`, GEOS 3.16.0dev `283e82726` |
| Old engine (E1 only, half a day) | `postgis/postgis:17-3.5` (frozen) | PostgreSQL 17.5, PostGIS 3.5.2 `dea6d0a`, GEOS 3.9.0 (before RelateNG) |

Version swaps also change PostGIS, so cross-version results serve triage and RQ3 only.
GEOS-only attribution: Shapely 2.2.0 bundles GEOS 3.14.1.

## Rules

Strict = must hold exactly; a reproduced violation is a defect or a path inconsistency.
Candidate = ranked by magnitude and triaged. Boolean rules are strict on integer inputs and
candidate on float inputs. Integer coordinates stay below 2^20, so PostGIS's point-in-polygon
side test (plain double cross product, `liblwgeom/intervaltree.c`) is exact there.

Predicates: Contains, Within, Covers, CoveredBy, Intersects, Disjoint, Touches, Equals, Relate.
Do not pass the boundary-node-rule argument.

| Id | Rule | Tier |
|---|---|---|
| R1 | Named predicate (lone call) = Python match of its pattern set on the `ST_Relate(a,b)` matrix. Contains `T*****FF*`; Within `T*F**F***`; Covers any of `T*****FF*`, `*T****FF*`, `***T**FF*`, `****T*FF*`; CoveredBy the transposes; Intersects not `FF*FF****`; Disjoint `FF*FF****`; Touches any of `FT*******`, `F**T*****`, `F***T****`; Equals `T*F**FFF*` for non-empty inputs only | strict int / candidate float |
| R2 | Logic: Contains ⇒ Covers ⇒ Intersects; Within(a,b) ⇔ Contains(b,a); CoveredBy(a,b) ⇔ Covers(b,a); Intersects, Touches, Equals symmetric; Disjoint ⇔ ¬Intersects; `ST_Relate(b,a)` = transpose of `ST_Relate(a,b)` (swap cells 1↔3, 2↔6, 5↔7, 0-based) | strict int / candidate float |
| R3 | Same predicate across query shapes: (a) lone call; (b) prepared arg1: `SELECT array_agg(ST_P($1,g) ORDER BY o) FROM unnest(ARRAY[$2,$2,$2]) WITH ORDINALITY t(g,o)` (element 1 unprepared, 2–3 prepared); (c) prepared arg2, roles swapped, only where reachable (Intersects, Touches, Disjoint, Within, Relate-pattern); (d) per-seed batch join with a GiST index (`enable_seqscan=off`, plan checked once with `EXPLAIN (ANALYZE, FORMAT JSON)`), EMPTY geometries included; for Relate also `ST_Relate(a,b,pattern)` lone and in (b)/(c) vs the Python match. Pattern calls are not compared on EMPTY inputs (the pattern path has no empty short-circuit; verified: `ST_Relate(poly, 'POINT EMPTY', '******FF*')` true, `ST_Covers` false). Point–polygon pairs take PostGIS's own point-in-polygon code; recorded as a path label | strict int / candidate float |
| R4 | Wrapper: `ST_P(a,b)` = `ST_P(ST_ForceCollection(a), b)` = `ST_P(a, ST_ForceCollection(b))` | strict int / candidate float |
| R5 | Intersects(a,b) ⇔ ¬IsEmpty(Intersection(a,b)); for point–polygon this compares PostGIS point-in-polygon with OverlayNG | strict int / candidate float |
| R6 | ¬IsEmpty(a) ⇒ ¬IsEmpty(Union(a,b)); outputs `ST_IsValid`: strict in fixed-precision mode, candidate in floating mode | strict / candidate |
| R7 | Containment: with I = `ST_CollectionExtract(ST_Intersection(a,b), d)` and U likewise for Union, d the inputs' dimension: measure(`ST_Difference(I,a)`) ≤ ε and measure(`ST_Difference(a,U)`) ≤ ε; lower-dimensional parts of the intersection satisfy `ST_Covers(a,part)` and `ST_Covers(b,part)` (strict int) | candidate |
| R8 | Argument order: measure(`ST_SymDifference(I(a,b), I(b,a))`) ≤ ε, same for Union | candidate |
| R9 | Inclusion–exclusion: abs(measure(U) − measure(a) − measure(b) + measure(I)) ≤ ε | candidate |
| R10 | Dimension: for non-empty intersection, `ST_Dimension` = max of the II, IB, BI, BB cells of `ST_Relate(a,b)`; for non-empty a and b, `ST_Dimension(ST_Union(a,b))` = max(dim a, dim b) | strict int / candidate float |
| R11 | Floating vs fixed precision: abs(area(`ST_Intersection(a,b)`) − area(`ST_Intersection(a,b,g)`)) ≤ ε, same for Union, g = 10^(floor(log10 M) − 12) | candidate |
| R12 | Point sampling (polygon pairs): 32 points from `ST_GeneratePoints(ST_Envelope(ST_Collect(a,b)), 32, seed)`; for every point p farther than 1e-9·L from the boundaries of a, b, I and U: `ST_Intersects(p,I)` = `ST_Intersects(p,a) AND ST_Intersects(p,b)` and `ST_Intersects(p,U)` = `ST_Intersects(p,a) OR ST_Intersects(p,b)`. Independent of overlay areas (point location goes through PostGIS's own point-in-polygon code) | strict |

Amendments 2026-10-27 after E1's first run: R9 on lines only when both inputs are simple
(length counts multiplicity); R7 lower-dimensional parts are candidate, magnitude = max
distance from the part to a and b, noise ≤ 1e-12·M, logged ≤ 1e-9·M, triage above; R3 (b) only
for predicates whose C code passes arg1 to the cache (not Within, Equals), (c) rebuilt as
`unnest(ARRAY[ST_Reverse($1), $1, $1])` because `GetGeomCache` checks the arg1 hit first, only
for predicates passing arg2 (Intersects, Touches, Disjoint, Within, Relate-pattern); Disjoint
has no index support, so it is not in (d); R12 added because R9 shares one noding with the
overlays and can be offset exactly (#1343). The rule set is frozen from the E1 re-run on, for
E2 and E3.

Amendments 2026-10-27 after the independent check of `rules.py` (before the frozen re-run):
R7 lower-dimensional classification certified by buffer containment (noise if
`ST_Covers(ST_Buffer(op, 1e-12·M), part)`, logged at 1e-9·M, triage otherwise; the vertex-only
distance missed a line leaving a non-convex operand between vertices); R3 (c) primer is the
first byte-different of `ST_Reverse`, `ST_ForceCollection`, `ST_CollectionHomogenize`,
`ST_Multi` (point-only first arguments were never tested), and in (b) and (c) elements 2–3
are compared with the lone unprepared result on the same bytes; a failing or crashing
statement is re-run expression by expression once; the precision-limited flag marks every
overlay-rule violation (R5–R12) of the pair, never R1–R4; R2 also checks Contains ⇒ Intersects
directly; rules counts list only rules actually evaluated. Disjoint stays out of (d).

Tier by rule family (reviewer, 2026-10-27): predicate rules R1–R4 are strict when coordinates are
integral, |x| < 2^53 and L < 2^20 (the side test and orientation determinants use differences
bounded by L, so they are exact at any magnitude); overlay rules R5–R12 additionally need
M < 2^20, because noding error grows with ulp(M). R12 runs twice: on the floating results with
margin max(1e-9·L, 1e-8·M), the worst-case snap displacement of OverlayNG
(`OverlayNGRobust.h:71,76`, `.cpp:163-182`: tolerance M/1e12, ×10 per retry, five tries), and on
the fixed-precision results of R11 with margin g.

Amendment after the first frozen E1 run (2026-10-27, before E2): for line/line overlays, R7
and R8 use the certified distance bands (buffer containment at 1e-12·M and 1e-9·M) instead of
length bands. Line noding rounds crossing points, so the leftover of `Difference(a,U)` can be
long while lying within about 1e-13 of U. Example: GEOS XML `TestRelateLL.xml#48`, length
119.7 at distance ≤ 4.2e-14. That run goes to the appendix and E1 is re-run once more. R9
stays on lengths. Yes/no rules on non-integer inputs are candidates with no magnitude, so they
count as triage band in the primary measure and in suite-level detection. Strict plus measured
triage only is reported as a sensitivity line. Precision-limited removes only measured
candidates (R7, R8, R9, R11). Strict violations and yes/no rules (R1–R6, R10, R12) still count
on such pairs, where #1383 shows. E3 runs on 5 lanes (two seeds each). Its N is set from the
E2 throughput.

Rules frozen at experiment commit 23761b7 (2026-10-27). Primary E1 run, `runs/e1/`, 81 s:
4 of 12 seeds fired as pre-registered at rule level. At suite level 7 of 12, or 6 of 12
counting only strict and measured triage. #1027 has no verdict. 0 of 964 GEOS XML pairs give
a strict or triage violation. Appendix runs: `runs/e1-prefreeze/` and `runs/e1-freeze1/`.

E2 (2026-10-27, `runs/e2/`): 1,000 plain-int pairs, 0 strict violations, 0 counted, 0 crashes,
1 R7 in logged; about 57,500 pairs/h on one lane. Gate passed. E3 started the same day:
N = 8,000 per (seed, kind), 640,000 pairs on 5 lanes. The estimate is 4–5 h on a 14-thread
laptop, under the 6 h cap. At 17:27 a low-memory guard stopped the run at about
237,800 of 640,000 pairs (37%): Windows had about 3.2 GB free and vmmemWSL used 4.9 GB.
Results so far are stored and the run resumes without duplicates. The lane containers were
taken down. Restarted at 17:50 on Alexandre's go-ahead; finished 19:24.

E3 results (`runs/e3/analysis/`), all 640,000 pairs, 0 harness errors, 0 duplicates. Violating
pairs per 10k per seed: plain-int 0 in every seed; plain-float 0–2.5; degen-int 5.6–12.5; degen-float
332–363. Degen vs plain within float and float vs int within degen: W = 0, p = 0.0020, Holm 0.0078,
r_rb = 1. The two contrasts with an all-zero arm are reported as counts (146 vs 0, 29 vs 0).
Crashes: 677 events in 176 pairs, about 9% of lane time.

Observation after the results, exploratory: nearly all degen-float R11 triage (9,614 of 9,792
violations) is in line/line pairs with a collinear-overlap move under affine or rotation. The
floating intersection has length 0 and the fixed-grid one about 5 units, because near-collinear
segments cross in floating point and overlap after snapping. Line intersection length is
discontinuous there. The R11 row says area, but the code used length for lines, following the
generic measure line. Reporting is decided with the reviewer; the frozen rules are not changed.

Reporting decisions (after independent review, 2026-10-27; `python -m tavs.posthoc_checks
runs/e3` and `python -m tavs.posthoc runs/e3` reproduce the numbers below):
- The primary is reported as registered. The rule-validity observation becomes an RQ1 result,
  not only a threat: a candidate rule whose flags sort into precision effects answers RQ1. The
  area/length wording is reported as an ambiguity in the frozen text, not a code defect.
- "All-zero arms are reported as counts" is read literally for the registered analysis. The
  reviewer, who wrote it, says it meant both arms zero. As a disclosed secondary, all four
  contrasts are tested with Holm over four: every Holm p = 0.0078 (plain-float vs plain-int:
  9 non-zero seeds, W = 0, p = 0.0039). No conclusion changes. McNemar stays descriptive (pairs
  cluster by cause; the seed is the unit).
- R3 harness checks on E3: all 397 R3 violations are on shapes (b) (286) or (c) (111), none on
  (d); element 1 equals the lone value in all 397 rows; no R3 flag on a pair with crash events;
  each lane's stored plan uses the GiST index (one plan per lane, not per seed). The 160,000
  plain-arm pairs have no R3 flag. The reviewer expected the tangent-hole family; the data say
  otherwise: every degen-int R3 pair (144) and 114 of 128 degen-float R3 pairs carry the
  empty-part move, and one carries hole-tangent. Triage decides the family.
- Mechanism evidence: R11 triage is line/line in all 9,792 degen-float and all 38 plain-float
  violations, all under affine or rotation. R10 is not only lines: 610 degen-float violations,
  375 line/line and 235 polygon/polygon, all affine or rotation, all on the intersection
  dimension half; 152 of the 621 R10 pairs also carry R11 triage. Polygon R10 awaits triage.
- Post-hoc decomposition, exploratory. S1 drops R11 on line/line pairs: degen-float falls from
  5,492 to 747 violating pairs (40–58 per 10k per seed); all four contrasts keep Holm p ≤ 0.016.
  S2 also drops R10: degen-float 139 vs degen-int 146 pairs, float vs int within degen p = 0.36
  (Holm 0.72), plain-float 0. Reading: degeneracy raises the rate under every variant; floating
  coordinates raise only the two precision-sensitive overlay rules, not the yield of the other
  rules. The abstract reports the registered primary, not S1 or S2.
- Triage fix: the crash oracle replayed only the plain call, but most E3 crashes happened in the
  R4 forms with `ST_ForceCollection` on one argument, so 80 crash items read "not reproduced"
  after zero shrink steps. Probes (SQL and Shapely) now include both wrapped forms; those 80
  shrink records were discarded and triage resumed.

E4 triage on E3 (`runs/e3/triage/`, finished 2026-10-27 23:46): 11,367 counted violations and
crash items in 326 groups; 400 representatives (every group has at least one, round-robin; the
cap dropped 202 extra representatives in 154 groups). All 400 reproduced on the current image;
399 unique findings after shrinking and exact dedup. Draft classes: 254 backend crash, 142
present in dev, 3 precision effect. Versions: current GEOS 3.14.1, dev 3.16.0dev, old 3.9.0;
Shapely 2.2.0 bundles 3.14.1. By family (findings): crashes 254, current and dev only, Shapely
crashes on 242; R3 prepared vs lone 82 (58 with a point plus an empty member in a collection),
current and dev only, reproduced in Shapely; R2 5 and R4 5, current and dev only; R10 22, R11
30 and R5 1, present on all three versions. Exact dedup does not merge a family, so findings
count shrunk inputs, not defects; root causes and tracker checks follow below.

Crash family (2026-10-27; scripts in `archive/triage-investigations/crash/`; the EMPTY count in
`findings.json` and the minimal crash were checked separately): all 254 crash findings are one
GEOS defect. `findings.csv` cuts WKT at about 200 characters; the full shrunk inputs in
`findings.json` hold an EMPTY member in all 254. Trigger: a GeometryCollection, as GEOS receives
it, with at least two non-empty polygons whose boundaries share a point and a `POLYGON EMPTY`
anywhere in its tree, on a call path that reaches RelateNG. 146 findings hold the EMPTY inside a
MultiPolygon and crash only under `ST_ForceCollection` (RelatePointLocator counts a MultiPolygon
as one element, so the adjacent-edge locator is built only for a collection); 108 crash on the
plain call. Code path read at dev main a9752091b and tag 3.14.1: `RelatePointLocator.cpp:283-291`
builds `AdjacentEdgeLocator`; `addRings` (`AdjacentEdgeLocator.cpp:113-129`) adds the empty ring;
line 67 loops to `getSize() - 1`, which wraps for size 0. No other unguarded site in
`relateng/`. Tested in Shapely subprocesses: all 748 crashing call forms crash, none after the
EMPTY members are removed; `POINT EMPTY`, `LINESTRING EMPTY` and `MULTIPOLYGON EMPTY` members do
not crash. No debugger trace, so line 67 rests on reading plus these tests. Minimal input,
segfault in Shapely 2.2.0 / GEOS 3.14.1 (rerun separately; without the empty member it returns
FF20F1FF2): `relate(GEOMETRYCOLLECTION (POLYGON EMPTY, POLYGON ((0 0, 1 0, 0 1, 0 0)), POLYGON
((0 0, -1 0, 0 -1, 0 0))), POINT (0 0))`. The 12 findings marked "no crash" in Shapely are replay
gaps, not a second behaviour: PostGIS `ST_Covers` calls `GEOSRelatePattern(..., "******FF*")`
after its own box check, while GEOS `covers` exits on an envelope test (8); the triage helper
replayed 4 `ST_Relate(pattern)` items with a default pattern instead of the crashing one. The dev
image is GEOS 3.16.0dev (3.15.0rc1-41-g283e82726); old GEOS 3.9.0 predates RelateNG (3.13.0).

Overlay families (2026-10-27, exact rational arithmetic on the shrunk doubles,
scripts in `archive/triage-investigations/overlay/`; separately checked that no line/line R10 or R11
finding has an exactly collinear segment overlap, so the true intersection has length 0 in all
of them): no new defect; relate/intersects is exact-correct in every checked case.
- R10 polygon pairs (11): relate II = 2 is correct; the true overlap is a sliver narrower than one
  double step, which overlay returns as a line (10) or point (1), as documented for non-strict
  OverlayNG (`OverlayNG.h:94`, `:167-173`). Closest tracker item GEOS #1383 (open, slivers
  collapsing to lines, maintainer: lower priority); #1354 is a gross error, not this.
- R10 line pairs (11): relate II = 0 is correct; overlay returns lines between two rounded
  crossing points shared by both inputs (9), or after snapping merges near-collinear segments (2).
  GEOS #972 (closed 2023), maintainer: "no promise that the overlay operations are consistent with
  exact spatial predicates".
- R11 line pairs (15 pairs, 30 findings): the earlier reading was half wrong. In 14 pairs the
  floating result (length 0) is correct and the fixed-grid reference is the one that moves: snap
  rounding pulls a segment onto a vertex or crossing within half a cell (`SnapRoundingNoder.h:44-60`).
  In 1 pair the floating result is wrong (all of A, length 4.78) and the grid nearly right; the
  snapping noder adds A's endpoint about 1e-7 from B as a node (path inferred, not observed). So
  R11 on lines mostly flags its own reference: a fixed grid is not ground truth for nearly
  collinear lines. This is the rule-validity result for RQ1.
- R5 (1): the inputs are exactly disjoint (1.94e-11 apart), Intersects = false is correct, and the
  intersection returns all of B, so a snapping fallback must have run (floating noding cannot
  node exactly disjoint segments). Documented in the JTS FAQ (D8) and the GEOS FAQ.
Limits: only the 38 shrunk examples were checked exactly, not the 610 R10 and 9,792 R11
campaign violations; the overlay path is inferred; PostGIS trac could not be searched (bot wall).

Predicate families (2026-10-28, scripts in `archive/triage-investigations/predicate/`;
rerun of the R3, R2 and R4 examples in Shapely and checked tracker states with `gh`):
- R3 with a point plus an empty member (58 findings): prepared Contains returns True, unprepared
  False; the point is on the boundary (`FF20F1FF2`), so False is correct (rerun: True with
  POLYGON EMPTY or LINESTRING EMPTY, False with the bare point). The empty member raises the
  collection's dimension, so `AbstractPreparedPolygonContains` skips its point-only branch and
  finds no segment intersection (`:116-124`, `:182`, `:194-210`). Same root cause as GEOS #1011
  (closed 2024-10-16, fixed by RelateNG on the unprepared path only); nothing found for the
  prepared path. Old GEOS 3.9.0 crashes on all 58 (tabulated from the reruns), so "absent on
  old" means a crash there, not a correct answer.
- R3 on floating polygon pairs (24 findings = 8 pairs × Contains/Covers/Within): RelateNG is wrong
  (`212F01FF2`), prepared is right; GEOS #740, open since 2022-11-23, maintainer attributes it to
  noding robustness (JTS #396). Old: 21 clean, 3 errors.
- R2 (5 pairs): two collection pairs are the RelateNG self-noding decision taken from the first
  argument only (GEOS #1558; PR #1565 "self-node polygons with holes" closed unmerged
  2026-10-20, fix planned in JTS); two line-vs-tangent-hole pairs are the #740 rounding class; one
  needle polygon pair is asymmetric with no mechanism found (rerun: `2F2101212` vs transpose
  `212101212`). Old: 2 clean, 3 errors.
- R4 (4 pairs): one pair, two triangles touching at a vertex with a hole touching the shell there,
  gives an impossible matrix once wrapped (rerun: `FF2FF1212` vs `FF2FFF212`, both inputs
  valid); reading: RelateNG tests only each ring's first vertex (`RelateNG.cpp:619-630`, TODO in
  the code) and the adjacent-edge locator merges sections without polygon identity. No tracker
  item. Three pairs are the #740 rounding class under forced self-noding.

Final classes by family (decision 2026-10-28 after an independent challenge; per-finding
classes in `runs/e3/triage/families.csv`, written by `python -m tavs.families runs/e3`; findings
are shrunk inputs, not defects):

| Family | Findings | Arms | Class |
|---|---|---|---|
| A RelateNG crash, POLYGON EMPTY in a polygon collection | 254 | degen-int, degen-float | new defect; not found in GEOS/JTS GitHub trackers as of 2026-10-28, unreported, unconfirmed |
| B prepared Contains, point plus empty member | 58 | degen-int, degen-float | unreported variant of a known cause on the prepared path (#1011 unprepared, #1008 same function) |
| C RelateNG rounding vs prepared | 29 | degen-float | consistent with open #740 |
| D self-noding decided by first argument | 2 | degen-int, degen-float | consistent with #1558 (PR #1565 unmerged) |
| E needle asymmetry | 1 | degen-float | unresolved, consistent with the #740 class; not counted |
| F tangent-hole collection relate | 2 (1 pair) | degen-int | candidate, mechanism by code reading, possibly related to #1558 |
| G1 R10 polygons, sliver collapse | 11 | degen-float | precision effect (open #1383) |
| G2 R10 lines, lines between rounded crossings | 11 | degen-float | precision effect (#972 maintainer statement) |
| G3 R11 lines, fixed-grid reference moved | 28 | plain-float, degen-float | oracle precision effect |
| G4 snapping fallback returns an input part (R11 pair, R5) | 3 | degen-float | known behaviour class by maintainer statement, not documented |

Independent challenge accepted: A strengthened by reading, since the JTS original loops with a signed `int`
(`AdjacentEdgeLocator.java:59`) and never iterates on an empty ring, so A is a C++ port defect;
the file is unchanged since the 2024-08 port; do not say "since 3.13.0" or call it a PostGIS bug.
B narrowed from "new defect"; F and E downgraded. G is not "documented behaviour" at campaign
scale: every violation group had at least one shrunk representative, all 38 exactly checked
representatives were precision effects, and campaign classes are assigned by group, not checked
per violation; shrinking keeps the violation, not necessarily the mechanism. Never write
"fixed": all 399 reproduce on dev. Shapely is GEOS 3.14.1, not an independent version.
Paper example for D: degen-int pair `27262e8ca8d1`, a wrong answer on integer input.

Secondary measures. Registered (unique findings after dedup per arm): plain-int 0, plain-float
20 (all precision), degen-int 157, degen-float 222. Exploratory (defect families per arm, G and E
excluded, A and B by verified reading, C and D by signature, F by reading): plain-int and
plain-float none; degen-int {A, B, D, F}; degen-float {A, B, C, D}. The robust contrast is plain
(none) vs degenerate (at least four); degen-int vs degen-float is not compared (capped
representatives, uncertain F). Harness notes: Shapely replays of 12 crash findings missed the
PostGIS call path (above); `findings.csv` truncates WKT; `findings.json` keeps the draft classes.

Reproducer notes (2026-10-28, while writing `findings/`, outside the registered results):
for family A's minimal point query every ring start crashes; the ring-start effect shows with a
disjoint polygon as the other argument (first member's start matters), so which start matters
depends on the input. Open lead: prepared Contains of the unit square `POLYGON ((0 0, 1 0, 1 1,
0 1, 0 0))` against `GEOMETRYCOLLECTION (POINT (0.5 0), LINESTRING EMPTY)` (or `POINT EMPTY`)
segfaults Shapely 2.2.0 (rechecked; `POLYGON EMPTY` gives True, the triangle does not crash);
not tested in PostGIS, cause unknown.

Corrections (2026-10-28, from the repository review, rechecked against the stored data; the text
above is kept as written): (1) the suite-level 7 of 12 in the paragraph "Rules frozen at
experiment commit 23761b7" counted #1540, whose only flag
is an R9 triage violation on a precision-limited pair, which does not count. Recomputed by
`tavs/e1_detection.py`: 6 of 12 as pre-registered (5 counting only strict and measured
triage), and 10 of 12 (9) with dev as the absent version for #1342, #1343, #1344 and #1354, which
are correct there; rule level 4 of 12 unchanged; 13 seeds replayed, 12 with a verdict. (2) Arms in
the family table: G1 plain-float 3 / degen-float 8, G2 3 / 8, G3 12 / 16, G4 2 / 1
(`families.csv`). (3) PostGIS trac could not be searched (bot wall); the later search list that
names it is wrong.

Overlay rules (R5–R11) take valid inputs of one dimension: polygon/polygon and line/line
(R5 also point/polygon). Measure = area for polygons, length for lines; points skip R7–R9.
An overlay error is its own outcome, not a violation. R7 and R9 must use Union and Relate as
independent computations, because one overlay can be self-consistently wrong.

**Tolerance**, fixed before E2 and never moved after: L = larger side of the pair's union box,
M = max |coordinate|, m_small = the smaller operand's measure. Areas: noise if
m ≤ max(1e-9·m_small, 1e-12·L·M); logged if ≤ max(1e-6·m_small, 1e-9·L·M); triage above.
Lengths: same with L·M replaced by M. Pairs with 1e-9·L·M ≥ m_small are "precision-limited"
and leave the triage count. The E2 plain-float distribution only confirms the floor sits above
it.

## Generators (2×2, equal pair budgets, seeded)

Arms: plain-int, plain-float, degen-int, degen-float. Coordinates in [0, 2^20]; shape extent
10–1000 units; b's centre inside a's box expanded by half with probability 0.8; scale ratio
a:b log-uniform 0.1–10. Polygons star-shaped, 3–12 vertices, 0–2 holes scaled 0.3–0.6 about
the centre; lines 2–8 vertices, simple; multi types 1–3 parts; collections for predicates only.
Type mix for predicates: all of {P,L,A}², with A/A, L/A, P/A weighted double; overlays A/A and
L/L. Validity checked with Shapely; invalid draws resampled and counted.

Degenerate arm = a plain pair plus one or two moves chosen uniformly: shared vertex (copy);
vertex on an edge (integer: only when gcd(dx,dy) > 1); collinear overlapping edges; hole
tangent to the shell (copy a shell vertex); sliver or spike of width 1 unit (integer) or near
zero (float); multipolygon parts touching at a point; EMPTY parts (predicates only); point-only
collections. Float moves: many significant digits, magnitudes 1e15 and 1e-8, mixed scales.
Each arm reports its observed rate of exact coincidences (shared vertices, 0-dimensional
boundary intersections), so the contrast is measured, not assumed.

Revision 2026-10-27 (reviewer Q1–Q2): paired design. One base pair per (seed, kind, index);
plain-int = base, degen-int = base + shape moves, plain-float = regime(base), degen-float =
regime(base + the same moves). Float regimes are maps applied to both geometries, one per pair:
non-integer affine (full-precision digits), rotation, translation to ~1e15, exact 2^-k scaling
to ~1e-8. Mixed scale is no longer a move (the a:b ratio covers it). Form weights: predicate
pairs single 50%, multi 30%, collection 20%; overlay pairs single 60%, multi 40%. Each arm
also reports the near-coincidence share (within 1e-9 relative or 4 ulp, not exact), the
intended target in the float arms. Violations are also reported by form within arm.
As built: shape moves are applied on the integer grid, then the regime; the translation goes
to an integer offset near 1e15 for predicate pairs and near 2^27 for overlay pairs (at 1e15
OverlayNG's legitimate snap displacement, up to 1e-8·M, exceeds the shapes); in the float
arms slivers and spikes are one coordinate quantum wide, k·ulp(M) with k in {1, 2, 4, 8},
applied after the regime at the int arm's anchor (int arms: 1 unit), so the #1383 trigger
exists in every regime and the magnitude rules are precision-limited there by construction
while the boolean overlay rules stay evaluated (a quantum feature makes a translation pair
non-integral, so the tier is computed per pair, never assumed from the regime; gen_check
5f90a68: 21 of 29 such predicate pairs stay integral, 0 of 35 overlay pairs); plain-float keeps the base pair's chance exact coincidences; the arm contrast for the
near-coincidence target uses the 4-ulp measure, because 1e-9·M is about 1e6 units at 1e15.

Shrinker: drop part, drop hole, drop vertex while valid, round float digits; re-run the failing
rule through SQL at each step; at most 200 steps; chain recorded. Hypothesis is not used:
it stops at the first failing example and cannot shrink an externally supplied input. In the
paper, property-based testing means executable properties, randomised generation, shrinking
and seed replay, in the QuickCheck/Hypothesis tradition.

## Experiments

| Step | What | Gate / output |
|---|---|---|
| E0 Setup | Images pinned, versions recorded (done 2026-10-27); harness: SQL layer, rules, results store | versions recorded |
| E1 Sensitivity (RQ3) | Pre-registered seeds below on the image with the bug and the image without; GEOS XML cases (relate, prepared, overlay; valid, non-curved, same-dimension for overlay rules) on the current image as the false-alarm corpus | per-seed table; "K of N fired as pre-registered"; false alarms after triage |
| E2 Pilot | 1,000 plain-int pairs on the current image | zero strict violations, or each explained, before E3 |
| E3 Campaign (RQ1, RQ2) | 4 arms × 10 seeds (5 minimum) × N pairs on the current image, all rules per pair; N from pilot throughput, total ≤ about 6 h machine time | violating pairs per 10k per seed |
| E4 Triage | Shrink, deduplicate, rerun on dev and old images and in Shapely (GEOS-only); classify | outcome classes; capped at two days |

Dedup key: (rule, function, path pair, type signature of the shrunk pair, `ST_Normalize`d WKTs).
Outcome classes: already fixed upstream; present in dev (new candidate); known open issue;
path inconsistency; precision effect; precision-limited pair; overlay error; backend crash;
not reproducible through PostGIS SQL; harness or generator error.

Crashes (reviewer Q3): one PostgreSQL container per E3 lane; a lost connection is recorded as
"crash in function F", the harness reconnects and re-runs the pair's remaining functions once.
Primary rates exclude crashes; "failing pairs" (violating or crashed) is secondary; each crash
signature is one unique finding. E2 measures crash cost; a Shapely pre-screen (subprocess,
crashing functions only, confirmed in the database on at least 20 pairs) is enabled only if
crashes would take more than about 10% of E3's budget.
As built (2026-10-27): "remaining functions" is applied at function level. Once an expression
crashes on its own, its SQL function is skipped for the rest of the pair, recorded as skipped.
Expression-level retries cost 401.6 s and 115 crashes on the found pair. A crashing batch index
join is split in halves down to the crashing pair, and (pair, predicate) combinations that
already crashed are excluded beforehand.

Seeds fixed 2026-10-27 before any run: E2 pilot seed 100, plain-int, 500 pairs per kind;
E3 seeds 101–110. Seeds below 100 are for development only; seed 1 produced the generator
checks and the crash finding. Primary rates pool both kinds, with equal N per kind; per-kind rates
are descriptive.

E1 reporting (reviewer Q4): the re-run with the frozen rules is primary; the first run goes to
the appendix with each rule change and the seeds that drove it (part of the sensitivity figure
is in-sample). Rule-level "fired as pre-registered" is reported next to suite-level detection
(a strict rule, or a candidate above triage, fires on the version with the bug and no rule
fires on the version without). The pre-registration table is kept as written, with an
"observed on dev" column: #1342, #1343, #1344 and #1354 are correct on 3.16.0dev with no
identified fixing commit, a pre-registration error about the bug's presence, reported as
"correct on 3.16.0dev, cause not identified", and dev then serves as their "absent" version.

Backend crash found 2026-10-27 (generator, degen-int predicate, seed 1, index 507): a
GEOMETRYCOLLECTION with a POLYGON EMPTY member and two point-touching polygons segfaults
`ST_Relate` and `ST_Intersects` on current and dev, not on old; also crashes Shapely 2.2.0
`relate` (GEOS-level). Called new only after: Shapely attribution per function, variant
minimisation, GEOS/JTS tracker search (RelateNG, GeometryCollection, empty, segfault, GH-1229),
and GEOS commits since 3.14.1 touching relateng or noding. Upstream report only with
Alexandre's OK.

Novelty checks done 2026-10-27. Shapely: relate, intersects and prepared intersects (collection
prepared) crash; contains and covers do not. Variants: a POLYGON EMPTY member, point-touching
polygon members and an intersects-type evaluation are all needed. Tracker and commits: nothing
found in GEOS, Shapely, JTS, PostGIS trac or the PostGIS GitHub mirror (searches recorded, all 2026-10-27; later searches could not reach PostGIS Trac, which blocks
automated access, so the final class treats it as not searched). The suspect code is unchanged on main a9752091b and on the 3.13–3.15
branches. Likely cause, read at main a9752091b:
`src/operation/relateng/AdjacentEdgeLocator.cpp`. `addRings` walks into the empty member and
`addRing` stores its empty ring, then `addSections` loops `i < ring->getSize() - 1` on `size_t`,
which wraps for 0 points (JTS uses a signed int; C++-port-only). The file came in with the RelateNG
port (d963c0f0b, 2024-08, GEOS 3.13), which fits 3.9.0 being correct. The locator is built when a
polygon's first vertex lies on two boundaries (`RelatePointLocator.cpp:287-289`). Prediction from
that reading, tested in Shapely: rotating the touching member's ring so it starts off the touch
point (same point set) stops the crash (`FF2FF1212`, false); starting the other member at the
touch point brings it back. No stack trace. Closest related: GEOS #1406 (the same empty-polygon
pattern in `GEOSNode`, fixed in 3.14.2), #1569 (unchecked `getAt`, open). Status: new, with the
cause supported but not traced.

### E1 pre-registered seeds

| Seed | Expected rule(s) | Fires on | Silent on |
|---|---|---|---|
| Tangent hole (JTS/GEOS PR 1565 test 65; issue #1558 deleted) | R3 lone vs prepared Contains/Covers; R1 | current, dev | old. Already observed in PostGIS: lone `ST_Contains(b,a)` false, prepared true, on current and dev; old gives true everywhere |
| GEOS #1405 (intersection order) | R8 | current | dev. Not reproduced in Shapely 3.14.1 with the issue's WKT; needs the post-`set_precision` geometries |
| GEOS #1383 (sliver union empty) | R6 | current, dev | — (open). Confirm binary vs unary union |
| GEOS #1523 (zero-width collinear hole) | R9, R11 (not R7) | current, dev | — (open, unconfirmed by maintainers) |
| GEOS #1354 (overlay returns a point) | R10, R9, R11 | current, dev | — (open) |
| GEOS #1343 (union loses a hole) | R9 | current, dev | — (open). Confirm binary union |
| GEOS #1344 (spurious intersection) | R5, R7, R9 | current, dev | — (open) |
| GEOS #1342 (invalid overlay output) | R6 candidate (floating mode) | current, dev | — (open) |
| GEOS #1540 (relate misses interior–interior; WKT from the EWKB in GEOS #1530) | R10 or R1 vs overlay | current, dev | — (open) |
| GEOS #1027 (Covers after POLYGON→MULTIPOLYGON) | R3 lone vs prepared Covers, R4 | to confirm | — |
| GEOS #1053 (old RelateOp dimension) | R10 | old | current |
| GEOS #1033 (Contains vs prepared Contains) | R3 | old | current |
| GEOS #1064 (relate vs boundary; maintainer: rounding limitation) | R2 | current, old | — (known limitation) |

Dropped: #1022 (Crosses, not reproduced), #1224 (invalid inputs; fixed 3.13.1), #1248 (needs
GEOS 3.13.1), #1355 (an exception, not a wrong result), GEOS #1275 (no geometry), JTS #1222
(maintainer could not reproduce), JTS #1239 (JTS-only). Seed data: `seeds/`.
A seed that the shared GEOS reproduces in Shapely but PostGIS SQL cannot reach is classed
"not reproducible through PostGIS SQL", neither hit nor miss.

## Measures and statistics

Primary: violating pairs per 10k per seed (strict plus candidate above triage; harness errors
and precision-limited pairs removed), at pair level. Four planned contrasts (degenerate vs plain
within each coordinate type; float vs int within each shape class). Because the arms are paired
by seed and index (revision above), the per-seed rates are paired: exact two-sided Wilcoxon
signed-rank over seeds, Holm correction over four, with the matched-pairs rank-biserial
correlation as effect size, and pair-level McNemar counts as a descriptive companion (fuzzer
evaluation practice after Klees et al., CCS 2018). All-zero arms are reported as counts, not tested. Secondary: unique findings after
dedup per arm (counts); rule-level rates (descriptive); outcome classes; E1 table; candidate
magnitude distribution; wall time and pairs per hour per arm.

## Schedule

| Dates | Work |
|---|---|
| Oct 27–29 | E0, E1 |
| Oct 30–31 | Generators, shrinker, E2 |
| Nov 1–2 | E3 |
| Nov 3–4 | E4 |
| Nov 5–7 | Paper (Overleaf `overleaf-postgis-paper/`) |
| Nov 8–10 | Slides (UFFS design kit), buffer |

## Decisions

- 2026-10-27: Alexandre alone, two weeks; plan accepted; Spader full text to be provided by
  Alexandre later; an independent reviewer answers design questions as work
  proceeds.
- 2026-10-27, reviewer review accepted with these changes: R1 compares named predicates with the
  matrix only (the pattern call joins R3); overlay rules gained inclusion–exclusion (R9),
  dimension (R10) and floating vs fixed precision (R11), because the containment rule cannot see
  results that are too small; R3 query shapes fixed from the PostGIS cache code (`ST_CoveredBy`
  never takes its prepared branch: dead code at `lwgeom_geos_predicates.c:852-853` in 3.6.4,
  unchanged in 3.7.0rc3, an observation for the paper); index arm as one batch join per seed;
  integer grid 2^20; tolerance with an absolute floor; dedup key and E1 pre-registration;
  old image kept for E1 only. Changes to the reviewer's list: GEOS #1540 kept (a complete
  reproducer was found in GEOS #1530); wrapper rule R4 added from the reviewer's cheap-rule list.
