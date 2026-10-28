"""E1 detection counts (docs/experiment-plan.md, "E1 reporting"), recomputed from a stored E1 run.

usage: python -s -m tavs.e1_detection runs/e1 [STORE]
STORE defaults to runs/e1/tavs.sqlite; after a rerun of tavs.e1 pass runs/tavs.sqlite. The latest
E1 seed run per image is used.

Rule level: the expected rules fire on every "fire" image and stay silent on every "silent" image
(as in summary.md). Suite level: some counted violation on every "fire" image and none on any
"silent" image, with "counted" as in the E3 analysis (`tavs.analysis.counted`); "measured only"
is its sensitivity variant, which drops the yes/no candidates. Two role sets: as pre-registered,
and with the development image as the bug-free version for the four seeds found correct there.
Seeds marked "to confirm" have no verdict.
"""
import csv
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

from .analysis import counted as counts

DEV_CORRECT = {"geos#1342", "geos#1343", "geos#1344", "geos#1354"}


def counted(rows, measured_only):
    return {rule for rule, tier, band, plim in rows
            if counts({"rule": rule, "tier": tier, "band": band, "plim": plim}, measured_only)}


def main(argv=None) -> int:
    args = argv or sys.argv[1:]
    e1 = Path(args[0])
    store = Path(args[1]) if len(args) > 1 else e1 / "tavs.sqlite"
    db = sqlite3.connect(f"file:{store}?mode=ro", uri=True)
    viol = defaultdict(list)                     # (seed, image) -> [(rule, tier, band, plim)]
    for src, img, *v in db.execute(
            "SELECT p.source, r.target, v.rule, v.tier, v.band, v.precision_limited "
            "FROM violations v JOIN pairs p USING (pair_id) JOIN runs r ON r.run_id = p.run_id "
            "WHERE r.run_id IN (SELECT max(run_id) FROM runs WHERE experiment = 'E1-seeds' "
            "GROUP BY target)"):
        viol[(src.split(":")[0], img)].append(tuple(v))
    rows = list(csv.DictReader((e1 / "seeds.csv").open(encoding="utf-8")))
    seeds = list(dict.fromkeys(r["seed"] for r in rows))
    for rerole in (False, True):
        roles = {(r["seed"], r["image"]): r["role"] for r in rows}
        if rerole:
            roles.update({(s, "dev"): "silent" for s in DEV_CORRECT})
        label = "dev as bug-free for 4 seeds" if rerole else "as pre-registered"
        rule_hits, suite = [], {False: [], True: []}
        for s in seeds:
            imgs = {i: ro for (t, i), ro in roles.items() if t == s}
            if "to confirm" in imgs.values():
                continue
            exp = next(r["expected"] for r in rows if r["seed"] == s)
            want = set(exp.split(" of ")[1].split(","))
            fired = {r["image"]: set(r["expected_fired"].split(",")) - {"-"} for r in rows if r["seed"] == s}
            ok = all((want <= fired[i] if exp.startswith("all") else bool(want & fired[i]))
                     for i, ro in imgs.items() if ro == "fire") and \
                not any(fired[i] for i, ro in imgs.items() if ro == "silent")
            if ok:
                rule_hits.append(s)
            for mo in (False, True):
                got = {i: counted(viol[(s, i)], mo) for i in imgs}
                if all(got[i] for i, ro in imgs.items() if ro == "fire") and \
                        not any(got[i] for i, ro in imgs.items() if ro == "silent"):
                    suite[mo].append(s)
        n = sum("to confirm" not in {ro for (t, _), ro in roles.items() if t == s} for s in seeds)
        print(f"{label}: rule level {len(rule_hits)} of {n} {rule_hits}")
        print(f"  suite level {len(suite[False])} of {n} {suite[False]}")
        print(f"  suite level, measured only {len(suite[True])} of {n} {suite[True]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
