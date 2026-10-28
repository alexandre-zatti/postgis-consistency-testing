"""Final E4 classes (lead decision 2026-10-28, after investigators and the advisor's challenge;
experiment-plan.md, "Final classes by family"). Writes <campaign>/triage/families.csv, one row per
triage finding, and prints unique findings and defect families per arm.

usage: python -m tavs.families runs/e3
"""
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import shapely

# family -> (class, confidence, tracker references); G* are not defects
FAMILIES = {
    "A": ("new defect: RelateNG crash, POLYGON EMPTY in a polygon collection", "high",
          "none found in GEOS/JTS GitHub 2026-10-28; PostGIS Trac not searched"),
    "B": ("unreported variant of a known cause: prepared Contains, point plus empty member",
          "medium-high", "GEOS #1011 (unprepared path, closed 2024-10-16); GEOS #1008"),
    "C": ("consistent with known open issue: RelateNG rounding vs prepared", "medium",
          "GEOS #740 (open); JTS #396"),
    "D": ("consistent with known open issue: self-noding decided by first argument", "medium",
          "GEOS #1558; PR #1565 closed unmerged 2026-10-20"),
    "E": ("unresolved, consistent with the #740 rounding class (not counted)", "low",
          "GEOS #740"),
    "F": ("candidate: tangent-hole collection relate, mechanism by code reading", "medium",
          "none found; possibly related to GEOS #1558"),
    "G1": ("precision effect: sliver collapse in overlay (R10 polygons)", "high",
           "GEOS #1383 (open)"),
    "G2": ("precision effect: overlay lines between rounded shared crossings (R10 lines)", "high",
           "GEOS #972 maintainer statement"),
    "G3": ("oracle precision effect: the fixed-grid reference moved (R11 lines)", "high",
           "snap rounding by design"),
    "G4": ("known behaviour class: snapping fallback returns an input part", "medium",
           "GEOS #972 maintainer statement; JTS FAQ D8"),
}
R2_KEYS = {"27262e8ca8d1": "D", "c6321394979e": "D", "dbd61987613e": "E"}
R4_KEYS = {"0f60d799288b": "F", "65b990eb05cf": "F"}
SNAP_KEYS = {"4febb7f24404", "44fa4173dd80", "49cb0e6036b1"}
DEFECTS = {"A", "B", "C", "D", "F"}


def family(f: dict) -> str:
    r, k = f["rule"], f["key_id"]
    if r == "crash":
        return "A"
    if r == "R3":
        return "B" if "EMPTY" in f["a"] + f["b"] else "C"
    if r == "R2":
        return R2_KEYS.get(k, "C")
    if r == "R4":
        return R4_KEYS.get(k, "C")
    if k in SNAP_KEYS:
        return "G4"
    if r == "R10":
        return "G1" if "Polygon" in shapely.from_wkt(f["a"]).geom_type else "G2"
    if r == "R11":
        return "G3"
    raise ValueError(f"unclassified finding {k} ({r})")


def main(argv=None) -> int:
    cdir = Path((argv or sys.argv[1:])[0])
    d = json.loads((cdir / "triage" / "findings.json").read_text(encoding="utf-8"))
    fs = d["findings"] if isinstance(d, dict) else d
    rows, per_arm, fam_arm = [], defaultdict(int), defaultdict(set)
    for f in fs:
        fam = family(f)
        cls, conf, refs = FAMILIES[fam]
        rows.append({"key": f["key_id"], "rule": f["rule"], "function": f["function"],
                     "arms": " ".join(sorted(f["arms"])), "family": fam, "class": cls,
                     "confidence": conf, "references": refs})
        for arm in f["arms"]:
            per_arm[(arm, fam in DEFECTS or fam == "E")] += 1
            if fam in DEFECTS:
                fam_arm[arm].add(fam)
    out = cdir / "triage" / "families.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {out} ({len(rows)} findings)")
    for arm in ("plain-int", "plain-float", "degen-int", "degen-float"):
        print(f"{arm}: unique findings {per_arm[(arm, True)] + per_arm[(arm, False)]} "
              f"(non-precision {per_arm[(arm, True)]}); defect families "
              f"{sorted(fam_arm[arm]) or '-'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
