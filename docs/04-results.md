# 4. Results

The registered numbers below come from files in `runs/` and can be recomputed (see
[05-reproduce.md](05-reproduce.md)). Exploratory analyses decided after seeing the data are
marked as such; their numbers are printed by `python -s -m tavs.posthoc runs/e3` and
`python -s -m tavs.posthoc_checks runs/e3`.

## E1. Calibration (RQ3)

Source: `runs/e1/summary.md` (rule level) and `python -s -m tavs.e1_detection runs/e1` (suite
level). 13 known problems were replayed; 12 have a verdict.

| Measure | Result |
|---|---|
| Rule level: exactly the predicted checks fired on the predicted versions, and stayed silent where predicted | **4 of 12** (GEOS #1405, #1383, #1053, #1033) |
| Suite level: some counted check fired on every version with the bug, and none fired on a version without it | **6 of 12** as pre-registered (5 counting only strict and measured flags); 10 of 12 (9) with the development version as the bug-free version of the four bugs in the note below |
| No verdict | 1 (#1027, marked "to confirm" before the run; it fired only on the old version) |
| False alarms on GEOS's own 964 test pairs | **0** (one measured difference in the *logged* band, below the triage threshold) |

**Note.** Four of the "known" bugs (#1342, #1343, #1344, #1354) give correct results on the
development version, and we could not identify the commit that fixed them. Before the run we had
written that they would still be present. That was our error, and it is reported as such. The
pre-registered count treats their silence on the development version as a miss; the corrected
count treats that version as their bug-free one.

## E2. Pilot

1,000 ordinary whole-number pairs: 0 violations, 0 crashes.

## E3. Main run (RQ2)

Source: `runs/e3/analysis/summary.txt`. 640,000 pairs, 0 harness errors, 0 duplicates.

Flagged pairs per 10,000, per seed. Crashes are not in these rates; they are counted separately:
677 crash events in 176 pairs (87 degen-int, 89 degen-float, none in the ordinary arms).

| Arm | Range over 10 seeds | Total flagged pairs (of 160,000) |
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

**Checks that never fired:** R1, R6, R8, R9 and R12 never fired in the main run, and R7 had no
counted violation. All 397 R3 violations came from the prepared routes; the index-join route
gave none.

**By decimal transformation:** in degen-float, affine (2,381 pairs) and rotation (3,042) produce
almost all flags. Scaling gives 38 and the predicate-pair translation (to about 1e15) 31. The
overlay-pair translation (by a whole number near 2^27) gives 0; it keeps the coordinates whole
(see [02-method.md](02-method.md)).

**What explains the decimal-arm numbers (exploratory).** Nearly all degen-float R11 flags are
line pairs with overlapping collinear edges under affine or rotation transforms. Two segments
that were collinear on the integer grid become *almost* collinear, so they cross at a single point
in exact arithmetic on the stored doubles. The floating-point intersection correctly has length
0. The fixed-grid reference snaps them together and reports a few units of overlap. So R11 mostly
flags its own reference.

| Variant | degen-float | degen-int | plain-float | Conclusion |
|---|---|---|---|---|
| registered (all checks) | 5,492 | 146 | 29 | |
| without R11 on line pairs | 747 | 146 | – | all four contrasts still significant (Holm ≤ 0.016) |
| also without R10 | 139 | 146 | 0 | decimal vs whole number within awkward: p = 0.36, no difference |

Awkward shapes raise the rate in every variant. Decimal coordinates raise mainly the two
precision-sensitive overlay checks. The 139 degen-float pairs still include family C, a known
wrong-answer class that appears only with decimal coordinates (see E4).

## E4. Triage (RQ1)

Source: `runs/e3/triage/` (`findings.json` has the full shrunk inputs, `families.csv` the final
class of each finding). A *finding* is one shrunk example. A *family* is one root cause.

| Family | Findings | Arms | Class |
|---|---|---|---|
| **A** GEOS crash: empty polygon in a collection of touching polygons | 254 | degen-int, degen-float | **new defect** (not found in the GEOS/JTS GitHub trackers as of 2026-10-28; PostGIS's tracker not searched; unreported; not confirmed by maintainers) |
| **B** prepared Contains wrong for a point plus an empty part | 58 | degen-int, degen-float | **unreported variant of a known cause** (GEOS #1011; PR #1008 fixed the same function for collections with multipoints) |
| **C** RelateNG rounding vs prepared predicate | 29 | degen-float | consistent with open GEOS #740 |
| **D** `ST_Relate` not symmetric: self-noding decided by the first argument | 2 | degen-int, degen-float | consistent with GEOS #1558, now deleted (fix PR #1565 closed unmerged) |
| **E** needle polygon asymmetry | 1 | degen-float | unresolved, likely the #740 class; not counted |
| **F** hole touching its shell, inside a collection | 2 (1 pair) | degen-int | candidate, by code reading; possibly related to GEOS #1558 |
| **G1** sliver returned as a line or point in overlay | 11 | plain-float 3, degen-float 8 | rounding effect, not a bug (closest: open GEOS #1383) |
| **G2** overlay lines between rounded crossings | 11 | plain-float 3, degen-float 8 | rounding effect (maintainer statement in GEOS #972) |
| **G3** fixed-grid reference moved | 28 | plain-float 12, degen-float 16 | rounding effect in our reference |
| **G4** snapping fallback returns an input part | 3 | plain-float 2, degen-float 1 | known behaviour class by maintainer statement, not documented |

**A, the crash.** A GeometryCollection holding `POLYGON EMPTY` plus two polygons whose boundaries
share a point makes GEOS crash (segmentation fault) when a predicate reaches RelateNG. In PostGIS
this takes down the database process serving the query.
- **Cause, from reading the code.** In `AdjacentEdgeLocator.cpp` a loop runs to
  `ring->getSize() - 1` on an unsigned integer, which wraps around for an empty ring. The JTS
  original uses a signed integer and does not fail, so this is a translation error in the C++ port
  (2024, GEOS 3.13).
- **Evidence.** In a separate test, all 748 crashing call forms crash in Shapely, and none does
  once the empty members are removed. In the registered triage replay, Shapely crashed on 242 of
  the 254 findings; the other 12 are replay gaps (PostGIS calls GEOS differently for `ST_Covers`
  in 8, and the triage helper used a default pattern for 4 `ST_Relate` items). In the original
  finding, rotating one polygon's ring so it does not start at the touching point avoided the
  crash, which fits the reading. That does not hold in general: for some inputs (such as the
  minimal one below) every ring start crashes, and the refined explanation is not verified. See
  [findings/](../findings/README.md).
- **Wrapping.** 146 of the 254 findings hold the empty polygon inside a MultiPolygon and crash
  only when the input is wrapped with `ST_ForceCollection` (check R4); 108 crash on the plain
  call. This bears on how often real users would meet it.
- **When found.** The crash was first seen during development, before the main run; the main
  run measured how often it occurs.
- **Spread.** It is present on the current and development versions. The old version (3.9.0)
  predates RelateNG.
- **Limits.** There is no debugger trace. PostGIS's own tracker could not be searched, because it
  blocks automated access. Nothing has been reported upstream.
- **Minimal input:** `relate(GEOMETRYCOLLECTION (POLYGON EMPTY, POLYGON ((0 0, 1 0, 0 1, 0 0)),
  POLYGON ((0 0, -1 0, 0 -1, 0 0))), POINT (0 0))`.

**B, prepared Contains.**
- **The problem.** Take a polygon and a collection holding a point on the polygon's border plus
  an empty part. The direct call correctly says "does not contain", but the prepared version says
  "contains".
- **Cause.** The empty part raises the collection's dimension, so the prepared code skips its
  point-only branch.
- **Status.** GEOS #1011 fixed the same cause on the direct path (closed 2024-10-16). GEOS PR #1008
  concerns the same prepared function. We found nothing about this input on the prepared path.
- **Old version.** The old version (3.9.0) crashes on all 58 findings, for a reason we did not
  investigate. It cannot be family A, which needs RelateNG. So "absent there" would be wrong.

**C and D, known issues.**
- **C:** on decimal polygon pairs, RelateNG and the prepared predicate disagree, and the prepared
  one is right (24 findings, check R3). This is consistent with GEOS #740, open since 2022, which
  the maintainer attributes to noding robustness. C also holds five findings of the same rounding
  class from other checks: two line-vs-polygon pairs where a hole touches the shell (R2) and three
  pairs under forced self-noding (R4).
- **D:** `ST_Relate(b, a)` is not the transpose of `ST_Relate(a, b)`, because the new engine
  decides whether to self-node from the first argument only (GEOS #1558; its fix, PR #1565, was
  closed unmerged on 2026-10-20). One of the two D findings has whole-number coordinates, so
  the wrong answer there cannot be blamed on rounding.

**F, candidate.** Two triangles touch at a corner, with a hole touching the shell at that corner.
Wrapping one argument in a collection changes the matrix from `FF2FF1212` to `FF2FFF212`, and both
inputs are valid. A TODO in `RelateNG.cpp` matches. No tracker item matches exactly; it may be
related to GEOS #1558 (the issue behind D, which is also the source of the calibration's
`tangent-hole` case). There is no trace.

**G, rounding effects.**
- **How they were checked.** 38 shrunk overlay examples were checked in exact rational
  arithmetic on the stored doubles: 11 R10 polygon findings, 11 R10 line findings, 15 R11 line
  pairs and 1 R5 finding. They count R11 pairs rather than findings (each pair gives an
  Intersection and a Union finding), which is why 38 does not match G's 53 findings. In every
  case the yes/no answer was exactly right. The overlay differences come from rounding or
  snapping; in one R11 pair (G4) the floating overlay returned a whole input part (length 4.78
  where the true intersection has length 0), with the mechanism inferred, not observed.
- **G3.** In 14 of the 15 R11 line pairs, the floating answer (length 0) is the correct one and
  the fixed grid is wrong. "Correct" refers to the stored doubles: as written in decimal, the
  example segments can be exactly collinear (see [findings/](../findings/README.md)).
- **Caveat.** This was checked on the shrunk examples, not on each of the roughly 10,400
  campaign violations (610 R10 and 9,792 R11). Campaign flags inherit the class of their group,
  and shrinking keeps the violation, not necessarily its mechanism.

**Nothing is "fixed".** All 399 findings still reproduce on the development version.

**Secondary measures:**
- **Unique findings per arm** (registered): plain-int 0, plain-float 20 (all rounding),
  degen-int 157, degen-float 222.
- **Defect families per arm** (exploratory): none for either ordinary arm; {A, B, D, F} for
  degen-int; {A, B, C, D} for degen-float.

## Answers to the questions

- **RQ1.** The path checks (R2, R3, R4) and crash detection found real defects. The overlay
  checks (R5, R10, R11) found no defect, only rounding or snapping effects. In one case (R11 on
  lines) the reference itself was the problem, which is a result about how to design such
  checks. R1, R6, R8, R9 and R12 never fired, R7 never counted, and the index-join route never
  disagreed.
- **RQ2.**
  - Awkward shapes find far more than ordinary ones. Ordinary shapes found no defect family in
    160,000 pairs per arm, and awkward shapes found at least four.
  - Decimal coordinates added mostly rounding flags, plus one known wrong-answer class (C), and
    no new defect.
- **RQ3.** 4 of 12 known bugs were caught exactly as predicted and 6 of 12 by some counted check
  (10 of 12 with the development version as the bug-free version of four bugs it answers
  correctly), with no false alarms on GEOS's test suite.

## Limits

1. **Design of the awkward moves.** The moves were designed from known bug patterns, so the
   comparison shows that targeted generation works, not that random testing is useless.
2. **Calibration is partly in-sample.** The checks were amended after the first calibration
   runs.
3. **The crash cause rests on code reading** plus 748 consistent tests. There is no debugger
   trace and no maintainer confirmation.
4. **Triage was capped** at 400 representatives (202 further picks dropped). Rounding classes
   were checked on 38 shrunk examples.
5. **Crashes are outside the primary rates.** The main finding, the crash, appears in the crash
   counts, not in the flagged-pair rates.
6. **A single machine and a single main target version** were tested. Shapely uses the same GEOS
   3.14.1, so it is not an independent version.
7. **The registered primary includes R11's self-inflicted flags.** It is reported as registered,
   next to the exploratory breakdown.
