# E1 summary (2026-10-27 15:50)

## Pre-registered seeds

**4 of 12 seeds fired as pre-registered** (fired on every 'fires on' image and silent on every 'silent on' image; seeds marked 'to confirm' excluded).

| seed | image | role | expected | expected_fired | as_preregistered | not_expected_fired | other_rules_fired | outcomes |
|---|---|---|---|---|---|---|---|---|
| tangent-hole | current | fire | all of R3,R1 | R3 | NO | - | - | - |
| tangent-hole | dev | fire | all of R3,R1 | R3 | NO | - | - | - |
| tangent-hole | old | silent | all of R3,R1 | - | yes | - | - | - |
| geos#1405 | current | fire | all of R8 | R8 | yes | - | R7,R11 | - |
| geos#1405 | dev | silent | all of R8 | - | yes | - | - | - |
| geos#1383 | current | fire | all of R6 | R6 | yes | - | R5 | - |
| geos#1383 | dev | fire | all of R6 | R6 | yes | - | R5 | - |
| geos#1523 | current | fire | all of R9,R11 | R11 | NO | - | R3 | - |
| geos#1523 | dev | fire | all of R9,R11 | R11 | NO | - | R3 | - |
| geos#1354 | current | fire | all of R10,R9,R11 | R10,R11 | NO | - | R6 | overlay:r7_au:overlay_error;overlay:r8_u:overlay_error;overlay:statement_retry |
| geos#1354 | dev | fire | all of R10,R9,R11 | - | NO | - | - | - |
| geos#1343 | current | fire | all of R9 | - | NO | - | R6,R11 | - |
| geos#1343 | dev | fire | all of R9 | - | NO | - | - | - |
| geos#1344 | current | fire | all of R5,R7,R9 | - | NO | - | R10,R11 | - |
| geos#1344 | dev | fire | all of R5,R7,R9 | - | NO | - | - | - |
| geos#1342 | current | fire | all of R6 | R6 | yes | - | R11 | overlay:r7_ia:overlay_error;overlay:r8_i:overlay_error;overlay:statement_retry |
| geos#1342 | dev | fire | all of R6 | - | NO | - | - | - |
| geos#1540 | current | fire | any of R10,R1 | - | NO | - | R9 | - |
| geos#1540 | dev | fire | any of R10,R1 | - | NO | - | R9 | - |
| geos#1027 | current | to confirm | all of R3,R4 | - | n/a | - | - | - |
| geos#1027 | dev | to confirm | all of R3,R4 | - | n/a | - | - | - |
| geos#1027 | old | to confirm | all of R3,R4 | R3 | n/a | - | - | - |
| geos#1053 | current | silent | all of R10 | - | yes | - | - | R9:not_applicable |
| geos#1053 | old | fire | all of R10 | R10 | yes | - | - | R9:not_applicable |
| geos#1033 | current | silent | all of R3 | - | yes | - | - | - |
| geos#1033 | old | fire | all of R3 | R3 | yes | - | - | - |
| geos#1064 | current | fire | all of R2 | - | NO | - | - | - |
| geos#1064 | old | fire | all of R2 | - | NO | - | R3,R5,R10 | - |

- tangent-hole: NOT as pre-registered
- geos#1405: as pre-registered
- geos#1383: as pre-registered
- geos#1523: NOT as pre-registered
- geos#1354: NOT as pre-registered
- geos#1343: NOT as pre-registered
- geos#1344: NOT as pre-registered
- geos#1342: NOT as pre-registered
- geos#1540: NOT as pre-registered
- geos#1027: to confirm (no verdict)
- geos#1053: as pre-registered
- geos#1033: as pre-registered
- geos#1064: NOT as pre-registered

### Violations per seed and image

- tangent-hole / current: R3: lone vs prepared arg2 [Within, ab]; lone vs prepared arg1 [Contains, ba]; lone vs prepared arg1 [Covers, ba]
- tangent-hole / dev: R3: lone vs prepared arg2 [Within, ab]; lone vs prepared arg1 [Contains, ba]; lone vs prepared arg1 [Covers, ba]
- tangent-hole / old: -
- geos#1405 / current: R7: measure(Difference(I,a)) [Intersection] triage 0.0913; measure(Difference(I,a)) [Intersection] triage 0.25 | R8: SymDifference(I(a,b),I(b,a)) [Intersection] triage 0.0913; SymDifference(U(a,b),U(b,a)) [Union] triage 0.0913 | R11: Intersection floating vs fixed [Intersection] triage 0.0913; Union floating vs fixed [Union] triage 0.0913; Intersection floating vs fixed [Intersection] triage 0.25; Union floating vs fixed [Union] triage 0.25
- geos#1405 / dev: -
- geos#1383 / current: R5: Intersects<=>not IsEmpty(Intersection) [Intersects/Intersection, ab]; Intersects<=>not IsEmpty(Intersection) [Intersects/Intersection, ba] | R6: not IsEmpty(a) => not IsEmpty(Union) [Union]
- geos#1383 / dev: R5: Intersects<=>not IsEmpty(Intersection) [Intersects/Intersection, ab]; Intersects<=>not IsEmpty(Intersection) [Intersects/Intersection, ba] | R6: not IsEmpty(a) => not IsEmpty(Union) [Union]
- geos#1523 / current: R3: lone vs prepared arg2 [Within, ab]; lone vs prepared arg1 [Contains, ba]; lone vs prepared arg1 [Covers, ba] | R11: Intersection floating vs fixed [Intersection] triage 11.5; Union floating vs fixed [Union] triage 11.5
- geos#1523 / dev: R3: lone vs prepared arg2 [Within, ab]; lone vs prepared arg1 [Contains, ba]; lone vs prepared arg1 [Covers, ba] | R11: Intersection floating vs fixed [Intersection] triage 11.5; Union floating vs fixed [Union] triage 11.5
- geos#1354 / current: R6: IsValid(Union(a,b)) floating [Union(a,b)]; IsValid(Union(b,a)) floating [Union(b,a)] | R10: dim(Intersection) = max(II,IB,BI,BB) [Intersection/Relate] | R11: Intersection floating vs fixed [Intersection] triage 5.79e+03; Union floating vs fixed [Union] triage 5.79e+03
- geos#1354 / dev: -
- geos#1343 / current: R6: IsValid(Intersection(a,b)) floating [Intersection(a,b)]; IsValid(Intersection(b,a)) floating [Intersection(b,a)] | R11: Intersection floating vs fixed [Intersection] triage 453; Union floating vs fixed [Union] triage 453
- geos#1343 / dev: -
- geos#1344 / current: R10: dim(Intersection) = max(II,IB,BI,BB) [Intersection/Relate] | R11: Intersection floating vs fixed [Intersection] triage 128; Union floating vs fixed [Union] triage 128
- geos#1344 / dev: -
- geos#1342 / current: R6: IsValid(Intersection(a,b)) floating [Intersection(a,b)]; IsValid(Intersection(b,a)) floating [Intersection(b,a)] | R11: Intersection floating vs fixed [Intersection] triage 1.48e+04; Union floating vs fixed [Union] triage 1.48e+04
- geos#1342 / dev: -
- geos#1540 / current: R9: m(U)-m(a)-m(b)+m(I) [Union/Intersection] triage 0.00077
- geos#1540 / dev: R9: m(U)-m(a)-m(b)+m(I) [Union/Intersection] triage 0.00077
- geos#1027 / current: -
- geos#1027 / dev: -
- geos#1027 / old: R3: lone vs prepared arg1 [Contains, ab]; lone vs prepared arg1 [Covers, ab]; lone vs prepared arg2 [Within, ba]
- geos#1053 / current: -
- geos#1053 / old: R10: dim(Intersection) = max(II,IB,BI,BB) [Intersection/Relate]
- geos#1033 / current: -
- geos#1033 / old: R3: lone vs prepared arg1 [Contains, ab]; lone vs prepared arg1 [Covers, ab]; lone vs prepared arg2 [Within, ba]
- geos#1064 / current: -
- geos#1064 / old: R3: lone vs prepared arg1 [Intersects, ab]; lone vs prepared arg1 [Disjoint, ab]; lone vs prepared arg2 [Intersects, ab]; lone vs prepared arg2 [Disjoint, ab] | R5: Intersects<=>not IsEmpty(Intersection) [Intersects/Intersection, ab]; Intersects<=>not IsEmpty(Intersection) [Intersects/Intersection, ba] | R10: dim(Intersection) = max(II,IB,BI,BB) [Intersection/Relate]

## XML false-alarm corpus (current image)

Pairs evaluated: 964 (overlay/float: 16, overlay/int: 408, predicate/float: 7, predicate/int: 533); skipped: {'LINEARRING converted to LINESTRING (kept)': 2, 'invalid (Shapely)': 1}.

Pairs with at least one violation, by rule (before triage):

| rule | tier | band | precision_limited | pairs |
|---|---|---|---|---|
| R7 | candidate | triage | False | 1 |

Outcomes (errors/skips): {'skipped': 591, 'not_applicable': 63}.

Time per pair (lone + prepared + overlay statements, excluding the batch join): mean 12.1 ms, median 11.2 ms; overlay: n=424 mean 16.0 ms median 13.0 ms; predicate: n=540 mean 8.9 ms median 8.3 ms. Wall time 20 s including batch joins.

By file:

| file | rule | tier | band | precision_limited | pairs | violations |
|---|---|---|---|---|---|---|
| validate/TestRelateLL.xml | R7 | candidate | triage | False | 1 | 1 |

Index join plan checked once (current): index used = True; see batch_plan.json.
