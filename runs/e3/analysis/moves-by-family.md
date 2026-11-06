# Degenerate moves by triage family (E3)

**Exploratory analysis, defined after the results (2026-11-06); not part of the registered protocol.**

Produced by `python -s -m tavs.posthoc_moves runs/e3` from the lane stores, `triage/findings.json` and `triage/families.csv`. Each cell is a count of pairs (or findings) in that row carrying the move; `n` is the row's denominator. Moves are read from the stored `pairs.moves` field; `EMPTY in WKT` is derived from the stored inputs. Pairs reach a family through their triage group; crashing pairs (family A) are included. A pair with two moves counts in both columns.

| level | family | arm | n | EMPTY in WKT | no move | shared vertex | vertex on edge | collinear overlap | hole tangent | sliver/spike | parts touching | **empty part** | point collection |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| all pairs (denominator) | - | plain-int | 160000 | 0 | 160000 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| all pairs (denominator) | - | plain-float | 160000 | 0 | 160000 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| all pairs (denominator) | - | degen-int | 160000 | 21081 | 0 | 53521 | 42026 | 39953 | 20319 | 20288 | 20574 | 22029 | 21256 |
| all pairs (denominator) | - | degen-float | 160000 | 21081 | 0 | 53521 | 42026 | 39953 | 20319 | 20288 | 20574 | 22029 | 21256 |
| pairs | A | degen-int | 87 | 87 | 0 | 0 | 0 | 0 | 0 | 0 | 87 | 87 | 0 |
| pairs | A | degen-float | 89 | 89 | 0 | 0 | 0 | 1 | 0 | 0 | 88 | 89 | 0 |
| pairs | B | degen-int | 144 | 144 | 0 | 36 | 47 | 0 | 0 | 2 | 0 | 144 | 58 |
| pairs | B | degen-float | 114 | 114 | 0 | 36 | 23 | 0 | 0 | 2 | 0 | 114 | 52 |
| pairs | C | degen-float | 21 | 0 | 0 | 1 | 11 | 11 | 3 | 1 | 7 | 0 | 0 |
| pairs | D | degen-int | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| pairs | D | degen-float | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| pairs | E | degen-float | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 1 | 0 | 0 | 0 |
| pairs | F | degen-int | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 1 | 0 | 0 |
| pairs | G1 | plain-float | 6 | 0 | 6 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| pairs | G1 | degen-float | 235 | 0 | 0 | 18 | 53 | 203 | 38 | 22 | 35 | 0 | 0 |
| pairs | G2 | plain-float | 5 | 0 | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| pairs | G2 | degen-float | 375 | 0 | 0 | 94 | 190 | 277 | 0 | 0 | 0 | 0 | 0 |
| pairs | G3 | plain-float | 19 | 0 | 19 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| pairs | G3 | degen-float | 4896 | 0 | 0 | 1552 | 1150 | 4807 | 0 | 0 | 0 | 0 | 0 |
| pairs | G4 | plain-float | 5 | 0 | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| pairs | G4 | degen-float | 2 | 0 | 0 | 0 | 2 | 2 | 0 | 0 | 0 | 0 | 0 |
| R3 pairs (any family) | - | degen-int | 144 | 144 | 0 | 36 | 47 | 0 | 0 | 2 | 0 | 144 | 58 |
| R3 pairs (any family) | - | degen-float | 128 | 114 | 0 | 37 | 33 | 6 | 1 | 3 | 2 | 114 | 52 |
| findings (representatives) | A | degen-int | 124 | 124 | 0 | 0 | 0 | 0 | 0 | 0 | 124 | 124 | 0 |
| findings (representatives) | A | degen-float | 130 | 130 | 0 | 0 | 0 | 4 | 0 | 0 | 126 | 130 | 0 |
| findings (representatives) | B | degen-int | 30 | 30 | 0 | 3 | 4 | 0 | 0 | 1 | 0 | 30 | 22 |
| findings (representatives) | B | degen-float | 28 | 28 | 0 | 3 | 3 | 0 | 0 | 0 | 0 | 28 | 22 |
| findings (representatives) | C | degen-float | 29 | 0 | 0 | 0 | 19 | 9 | 5 | 3 | 6 | 0 | 0 |
| findings (representatives) | D | degen-int | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| findings (representatives) | D | degen-float | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| findings (representatives) | E | degen-float | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 1 | 0 | 0 | 0 |
| findings (representatives) | F | degen-int | 2 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 2 | 0 | 0 |
| findings (representatives) | G1 | plain-float | 3 | 0 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| findings (representatives) | G1 | degen-float | 8 | 0 | 0 | 1 | 1 | 8 | 1 | 0 | 0 | 0 | 0 |
| findings (representatives) | G2 | plain-float | 3 | 0 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| findings (representatives) | G2 | degen-float | 8 | 0 | 0 | 1 | 4 | 7 | 0 | 0 | 0 | 0 | 0 |
| findings (representatives) | G3 | plain-float | 12 | 0 | 12 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| findings (representatives) | G3 | degen-float | 16 | 0 | 0 | 8 | 4 | 16 | 0 | 0 | 0 | 0 | 0 |
| findings (representatives) | G4 | plain-float | 2 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| findings (representatives) | G4 | degen-float | 1 | 0 | 0 | 0 | 1 | 1 | 0 | 0 | 0 | 0 | 0 |

Checks printed by the script:

- items rebuilt from the stores: 11367; groups 326; group sizes identical to `selection.json`: True
- groups mapped to more than one family: 2; groups without a finding: 0; pairs in more than one family: {'G2 + G3': 152, 'G3 + G4': 5, 'G2 + G4': 2}
- flagged or crashing pairs where stored empty-part and EMPTY in WKT disagree: 0 of 5843; over all 640,000 pairs: 1896
- defect-family (A-F) pairs with no empty member: 25 ({'C': 21, 'E': 1, 'F': 1, 'D': 2}); defect-family findings whose representatives have no empty member: 34 ({('D', 'degen-int'): 1, ('C', 'degen-float'): 29, ('D', 'degen-float'): 1, ('E', 'degen-float'): 1, ('F', 'degen-int'): 2})
- findings whose representative had EMPTY but whose shrunk input has none: none
- Findings are counted once per arm they occur in (as in `families.py`); their moves are those of their representatives from that arm. Family B is defined in `families.py` as an R3 finding with EMPTY in the shrunk input, so its empty-member share among findings is 100% by construction.
