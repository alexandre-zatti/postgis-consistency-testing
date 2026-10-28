# 4. Results

All numbers below come from files in `runs/` and can be recomputed (see
[05-reproduce.md](05-reproduce.md)). Exploratory analyses decided after seeing the data are
marked as such.

## E1. Calibration (RQ3)

Source: `runs/e1/summary.md`.

| Measure | Result |
|---|---|
| Known bugs where exactly the predicted checks fired on the predicted versions, and stayed silent where predicted | **4 of 12** (GEOS #1405, #1383, #1053, #1033) |
| Known bugs flagged by some check on a version with the bug, with no check firing where the bug is absent | 7 of 12 (6 of 12 counting only strict and measured flags) |
| No verdict | 1 (#1027, marked "to confirm" before the run; it fired only on the old version) |
| False alarms on GEOS's own 964 test pairs | **0** (one measured difference in the *logged* band, below the triage threshold) |

**Note.** Four of the "known" bugs (#1342, #1343, #1344, #1354) give correct results on the
development version, and we could not identify the commit that fixed them. Before the run we had
written that they would still be present. That was our error, and it is reported as such.

## E2. Pilot

1,000 ordinary whole-number pairs: 0 violations, 0 crashes.

## E3. Main run (RQ2)

Source: `runs/e3/analysis/summary.txt`. 640,000 pairs, 0 harness errors, 0 duplicates.

Violating pairs per 10,000, per seed:

| Arm | Range over 10 seeds | Total violating pairs (of 160,000) |
|---|---|---|
| plain-int | 0 in every seed | 0 |
| plain-float | 0 – 2.5 | 29 |
| degen-int | 5.6 – 12.5 | 146 |
| degen-float | 332 – 363 | 5,492 |

**Planned contrasts** (exact Wilcoxon over seeds, Holm over 4):

| Contrast | Result |
|---|---|
| awkward vs ordinary, within decimals | p = 0.002, Holm 0.0078, effect size 1 (every seed) |
| decimal vs whole number, within awkward | p = 0.002, Holm 0.0078, effect size 1 |
| awkward vs ordinary, within whole numbers | 146 vs 0 pairs; reported as counts (protocol: an all-zero arm is not tested) |
| decimal vs whole number, within ordinary | 29 vs 0 pairs; reported as counts |

As a disclosed extra, all four contrasts were also tested. Every one gives Holm p = 0.0078, and
no conclusion changes.

**Which checks fire** (pairs with a counted violation):

| Arm | Checks |
|---|---|
| plain-int | none |
| plain-float | R10 11, R11 19 |
| degen-int | R2 1, R3 144, R4 1 |
| degen-float | R2 4, R3 128, R4 5, R5 2, R10 610, R11 4,896 |

**By decimal transformation:** in degen-float, affine (2,381 pairs) and rotation (3,042) produce
almost all flags. Scaling gives 38, far translation 31, and the second translation 0.

**What explains the decimal-arm numbers (exploratory).** Nearly all degen-float R11 flags are
line pairs with overlapping collinear edges under affine or rotation transforms. Two segments
that were collinear on the integer grid become *almost* collinear, so they cross at a single point
in exact arithmetic. The floating-point intersection correctly has length 0. The fixed-grid
reference snaps them together and reports a few units of overlap. So R11 mostly flags its own
reference.

| Variant | degen-float | degen-int | plain-float | Conclusion |
|---|---|---|---|---|
| registered (all checks) | 5,492 | 146 | 29 | |
| without R11 on line pairs | 747 | 146 | – | all four contrasts still significant (Holm ≤ 0.016) |
| also without R10 | 139 | 146 | 0 | decimal vs whole number within awkward: p = 0.36, no difference |

Awkward shapes raise the rate in every variant. Decimal coordinates raise only the two
precision-sensitive overlay checks.

## E4. Triage (RQ1)

Source: `runs/e3/triage/` (`findings.json` has the full shrunk inputs, `families.csv` the final
class of each finding). A *finding* is one shrunk example. A *family* is one root cause.

| Family | Findings | Arms | Class |
|---|---|---|---|
| **A** GEOS crash: empty polygon in a collection of touching polygons | 254 | degen-int, degen-float | **new defect** (not found in the GEOS/JTS GitHub trackers as of 2026-10-28; unreported; not confirmed by maintainers) |
| **B** prepared Contains wrong for a point plus an empty part | 58 | degen-int, degen-float | **unreported variant of a known cause** |
| **C** RelateNG rounding vs prepared predicate | 29 | degen-float | consistent with open GEOS #740 |
| **D** `ST_Relate` not symmetric: self-noding decided by the first argument | 2 | degen-int, degen-float | consistent with GEOS #1558 (fix PR #1565 closed unmerged) |
| **E** needle polygon asymmetry | 1 | degen-float | unresolved, likely the #740 class; not counted |
| **F** hole touching its shell, inside a collection | 2 (1 pair) | degen-int | candidate, by code reading |
| **G1** sliver returned as a line or point in overlay | 11 | degen-float | rounding effect, not a bug (GEOS #1383) |
| **G2** overlay lines between rounded crossings | 11 | degen-float | rounding effect (maintainer statement in GEOS #972) |
| **G3** fixed-grid reference moved | 28 | plain-float, degen-float | rounding effect in our reference |
| **G4** snapping fallback returns an input part | 3 | degen-float | known behaviour class |

**A, the crash.** A GeometryCollection holding `POLYGON EMPTY` plus two polygons whose boundaries
share a point makes GEOS crash (segmentation fault) when a predicate reaches RelateNG. In PostGIS
this takes down the database process serving the query.
- **Cause, from reading the code.** In `AdjacentEdgeLocator.cpp` a loop runs to
  `ring->getSize() - 1` on an unsigned integer, which wraps around for an empty ring. The JTS
  original uses a signed integer and does not fail, so this is a translation error in the C++ port
  (2024, GEOS 3.13).
- **Evidence.** All 748 crashing call forms crash in Shapely, and none does once the empty
  members are removed. In the original finding, rotating one polygon's ring so it does not start
  at the touching point avoided the crash, as the reading predicts. For some inputs (such as
  the minimal one below) every ring start crashes. See
  [findings/](../findings/README.md).
- **Spread.** It is present on the current and development versions. The old version (3.9.0)
  predates RelateNG.
- **Limits.** There is no debugger trace. PostGIS's own tracker could not be searched, because it
  blocks automated access.
- **Minimal input:** `relate(GEOMETRYCOLLECTION (POLYGON EMPTY, POLYGON ((0 0, 1 0, 0 1, 0 0)),
  POLYGON ((0 0, -1 0, 0 -1, 0 0))), POINT (0 0))`.

**B, prepared Contains.**
- **The problem.** Take a polygon and a collection holding a point on the polygon's border plus
  an empty part. The direct call correctly says "does not contain", but the prepared version says
  "contains".
- **Cause.** The empty part raises the collection's dimension, so the prepared code skips its
  point-only branch.
- **Status.** GEOS #1011 fixed the same cause on the direct path (closed 2024-10-16). We found
  nothing about the prepared path.
- **Old version.** The old version crashes on all 58 findings, so "absent there" would be
  wrong.

**C and D, known issues.**
- **C:** on decimal polygon pairs, RelateNG and the prepared predicate disagree, and the prepared
  one is right. This is GEOS #740, open since 2022.
- **D:** `ST_Relate(b, a)` is not the transpose of `ST_Relate(a, b)`, because the new engine
  decides whether to self-node from the first argument only (GEOS #1558; its fix, PR #1565, was
  closed unmerged on 2026-10-20). One of the two D findings has whole-number coordinates, so
  the wrong answer there cannot be blamed on rounding.

**F, candidate.** Two triangles touch at a corner, with a hole touching the shell at that corner.
Wrapping one argument in a collection changes the matrix from `FF2FF1212` to `FF2FFF212`, and both
inputs are valid. A TODO in `RelateNG.cpp` matches, but there is no tracker item and no trace.

**G, rounding effects.**
- **How they were checked.** All 38 shrunk overlay examples were checked in exact rational
  arithmetic. In every case the yes/no answer was exactly right, and the overlay difference
  came from documented rounding.
- **G3.** In 14 of the 15 R11 line pairs, the floating answer (length 0) is the correct one and
  the fixed grid is wrong.
- **Caveat.** This was checked on the shrunk examples, not on each of the 10,000 or so campaign
  flags. Campaign flags inherit the class of their group.

**Nothing is "fixed".** All 399 findings still reproduce on the development version.

**Secondary measures:**
- **Unique findings per arm** (registered): plain-int 0, plain-float 20 (all rounding),
  degen-int 157, degen-float 222.
- **Defect families per arm** (exploratory): none for either ordinary arm; {A, B, D, F} for
  degen-int; {A, B, C, D} for degen-float.

## Answers to the questions

- **RQ1.** The path checks (R2, R3, R4) and crash detection found real defects. The overlay
  checks (R5, R10, R11) found only rounding effects. In one case (R11 on lines) the reference
  itself was the problem, which is a result about how to design such checks.
- **RQ2.**
  - Awkward shapes find far more than ordinary ones. Ordinary shapes found no defect family in
    160,000 pairs per arm, and awkward shapes found at least four.
  - Decimal coordinates added rounding flags, not defects.
- **RQ3.** 4 of 12 known bugs were caught exactly as predicted, 7 of 12 by some check, with no
  false alarms on GEOS's test suite.

## Limits

1. **Design of the awkward moves.** The moves were designed from known bug patterns, so the
   comparison shows that targeted generation works, not that random testing is useless.
2. **Calibration is partly in-sample.** The checks were amended after the first calibration
   runs.
3. **The crash cause rests on code reading** plus 748 consistent tests. There is no debugger
   trace and no maintainer confirmation.
4. **Triage was capped** at 400 representatives. Rounding classes were checked on 38 shrunk
   examples.
5. **A single machine and a single main target version** were tested. Shapely uses the same GEOS
   3.14.1, so it is not an independent version.
6. **The registered primary includes R11's self-inflicted flags.** It is reported as registered,
   next to the exploratory breakdown.
