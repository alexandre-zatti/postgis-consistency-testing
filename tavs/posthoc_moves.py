"""Exploratory E3 analysis, defined after the results (2026-11-06): which degenerate moves the
pairs and findings of each triage family carry.

usage: python -s -m tavs.posthoc_moves runs/e3

Reads only stored data (no Docker, no new runs):
- the lane stores (`lane*.sqlite`, opened read-only): every counted violation and every crash,
  rebuilt into triage items and groups exactly as `triage.load_items` does, but loading only the
  pairs that are flagged or crashed;
- `triage/findings.json`: each finding's groups and representatives;
- `triage/families.csv`: each finding's family.

Move per pair, two methods:
- stored: `pairs.moves`, the JSON list of moves the generator applied (`gen.build`), with the
  "(k=...)" suffix of the decimal sliver move removed;
- derived (empty-part only): the token EMPTY in the stored WKT of a or b. The plain generator
  never draws an empty member and no other move creates one, so this is an independent marker.

A pair belongs to a family through the groups of its items: a group takes the families of the
findings its representatives shrank to. A pair can belong to more than one family (for example
a crash and an R3 violation on the same pair). Crashing pairs are included (family A), although
the registered flagged-pair rate excludes crashes.

Writes <campaign>/analysis/moves-by-family.csv and moves-by-family.md, and prints checks.
"""
from __future__ import annotations

import csv
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

from .analysis import counted
from .gen import ARMS, GEOM_MOVES
from .triage import type_sig

FAMILY_ORDER = ["A", "B", "C", "D", "E", "F", "G1", "G2", "G3", "G4"]
DEFECT_FAMILIES = {"A", "B", "C", "D", "E", "F"}
HEADER = ("Exploratory analysis, defined after the results (2026-11-06); not part of the "
          "registered protocol.")


def base_moves(raw: str | None) -> list[str]:
    return [m.split("(")[0] for m in json.loads(raw or "[]")]


def load_items(cdir: Path) -> tuple[list[dict], dict]:
    """Counted violations and crash items, grouped as in triage.load_items; pairs keyed by
    (lane, pair_id) with their stored moves and the derived EMPTY marker."""
    items, pairs = [], {}
    for f in sorted(cdir.glob("lane*.sqlite")):
        db = sqlite3.connect(f"file:{f.as_posix()}?mode=ro", uri=True)
        lane = f.stem
        rows = []
        for (vid, pid, rule, sub, fn, paths, o, tier, mag, band, plim) in db.execute(
                "SELECT violation_id, pair_id, rule, sub, function, paths, orientation, tier, "
                "magnitude, band, precision_limited FROM violations"):
            v = {"rule": rule, "sub": sub, "function": fn, "tier": tier, "magnitude": mag,
                 "band": band, "plim": bool(plim)}
            if counted(v):
                rows.append((pid, f"{lane}:{pid}:v{vid}", rule, sub, fn, paths, o))
        crash_stages = defaultdict(list)
        for pid, stage in db.execute("SELECT pair_id, stage FROM outcomes WHERE kind='crash'"):
            crash_stages[pid].append(stage)
        need = {r[0] for r in rows} | set(crash_stages)
        for pid in need:
            a, b, moves, info, seed, kind, idx, arm = db.execute(
                "SELECT p.a, p.b, p.moves, p.info, c.seed, c.kind, c.idx, c.arm FROM pairs p "
                "LEFT JOIN campaign_pairs c USING (pair_id) WHERE p.pair_id=?", (pid,)).fetchone()
            pairs[(lane, pid)] = {"lane": lane, "pair_id": pid, "a": a, "b": b, "arm": arm,
                                  "seed": seed, "kind": kind, "idx": idx,
                                  "moves": base_moves(moves),
                                  "empty_wkt": "EMPTY" in (a or "").upper()
                                  or "EMPTY" in (b or "").upper(),
                                  "info": json.loads(info or "{}")}
        for pid, item, rule, sub, fn, paths, o in rows:
            items.append({"key": (lane, pid), "item": item, "rule": rule, "sub": sub,
                          "function": fn, "paths": paths, "orientation": o})
        for pid, stages in crash_stages.items():
            fs = set(pairs[(lane, pid)]["info"].get("crashed_functions", []))
            fs |= {"ST_" + s.split(":")[1] for s in stages
                   if s.startswith("batch:") and s.count(":") == 2}
            for fn in sorted(fs) or ["(unattributed)"]:
                items.append({"key": (lane, pid), "item": f"{lane}:{pid}:crash:{fn}",
                              "rule": "crash", "sub": "backend crash", "function": fn,
                              "paths": "", "orientation": None})
        db.close()
    for it in items:
        p = pairs[it["key"]]
        it["group"] = " | ".join(str(x) for x in (
            it["rule"], it["sub"], it["function"], it["paths"], it["orientation"] or "-",
            p["arm"] or "-", type_sig(p["a"], p["b"])))
    return items, pairs


def arm_totals(cdir: Path) -> dict:
    """All pairs per arm: count, stored moves, derived EMPTY marker (one SQL scan per lane)."""
    tot = {arm: Counter() for arm in ARMS}
    for f in sorted(cdir.glob("lane*.sqlite")):
        db = sqlite3.connect(f"file:{f.as_posix()}?mode=ro", uri=True)
        for arm, moves, e, n in db.execute(
                "SELECT c.arm, p.moves, (instr(upper(p.a),'EMPTY')>0 OR instr(upper(p.b),'EMPTY')>0)"
                " AS e, count(*) FROM pairs p JOIN campaign_pairs c USING (pair_id) "
                "GROUP BY c.arm, p.moves, e"):
            ms = set(base_moves(moves))
            t = tot[arm]
            t["n"] += n
            t["empty_wkt"] += n * bool(e)
            t["no_move"] += n * (not ms)
            t["empty_move_xor_wkt"] += n * (("empty-part" in ms) != bool(e))
            for m in ms:
                t[m] += n
        db.close()
    return tot


def tally(objs) -> Counter:
    c = Counter()
    for o in objs:
        c["n"] += 1
        c["empty_wkt"] += o["empty_wkt"]
        c["no_move"] += not o["moves"]
        for m in set(o["moves"]):
            c[m] += 1
    return c


def main(argv=None) -> int:
    cdir = Path((argv or sys.argv[1:])[0])
    tdir = cdir / "triage"
    items, pairs = load_items(cdir)
    sel = json.loads((tdir / "selection.json").read_text(encoding="utf-8"))["selection"]
    groups = defaultdict(list)
    for it in items:
        groups[it["group"]].append(it)
    # check: the rebuilt items and groups are those triage selected from
    sizes_ok = {g: len(v) for g, v in groups.items()} == {
        g: v["size"] for g, v in sel["per_group"].items()}
    print(f"items {len(items)} (selection.json {sel['items']}), groups {len(groups)} "
          f"(selection.json {sel['groups']}), group sizes identical: {sizes_ok}")
    if len(items) != sel["items"] or not sizes_ok:
        raise SystemExit("rebuilt items differ from triage selection; stopping")

    fam_of = {r["key"]: r["family"] for r in
              csv.DictReader((tdir / "families.csv").open(encoding="utf-8", newline=""))}
    fs = json.loads((tdir / "findings.json").read_text(encoding="utf-8"))["findings"]
    g_fams = defaultdict(set)
    for f in fs:
        for g in f["groups"]:
            g_fams[g].add(fam_of[f["key_id"]])
    uncovered = [g for g in groups if g not in g_fams]
    mixed = {g: sorted(v) for g, v in g_fams.items() if len(v) > 1}
    print(f"groups without a finding: {len(uncovered)}; groups mapped to more than one family: "
          f"{len(mixed)}")
    for g, v in mixed.items():
        print(f"   {v} <- {g} ({len(groups[g])} items)")

    # pairs per family (via groups)
    pair_fams = defaultdict(set)
    for it in items:
        pair_fams[it["key"]] |= g_fams.get(it["group"], {"(none)"})
    fam_pairs = defaultdict(list)
    for k, fams in pair_fams.items():
        for fam in fams:
            fam_pairs[(fam, pairs[k]["arm"])].append(pairs[k])
    multi = Counter(tuple(sorted(v)) for v in pair_fams.values() if len(v) > 1)
    print("pairs in more than one family:", dict(multi) or "none")

    # findings per family and arm; moves of the representatives from that arm
    items_by_id = {it["item"]: it for it in items}
    fam_findings = defaultdict(list)
    for f in fs:
        fam = fam_of[f["key_id"]]
        for arm in f["arms"]:
            reps = [pairs[items_by_id[r["item"]]["key"]] for r in f["representatives"]
                    if pairs[items_by_id[r["item"]]["key"]]["arm"] == arm]
            fam_findings[(fam, arm)].append({
                "moves": sorted({m for p in reps for m in p["moves"]}),
                "empty_wkt": any(p["empty_wkt"] for p in reps),
                "shrunk_empty": "EMPTY" in (f["a"] + f["b"]).upper(),
                "n_reps": len(reps), "key": f["key_id"]})

    # R3 pairs (independent of families), for the quoted claim
    r3 = defaultdict(list)
    seen = set()
    for it in items:
        if it["rule"] == "R3" and it["key"] not in seen:
            seen.add(it["key"])
            r3[pairs[it["key"]]["arm"]].append(pairs[it["key"]])

    tot = arm_totals(cdir)
    cols = ["level", "family", "arm", "n", "empty_wkt", "no_move"] + GEOM_MOVES
    rows = []
    for arm in ARMS:
        rows.append({"level": "all pairs (denominator)", "family": "-", "arm": arm,
                     **{c: tot[arm][c] for c in cols[3:]}})
    for fam in FAMILY_ORDER + ["(none)"]:
        for arm in ARMS:
            if (fam, arm) in fam_pairs:
                rows.append({"level": "pairs", "family": fam, "arm": arm,
                             **{c: tally(fam_pairs[(fam, arm)])[c] for c in cols[3:]}})
    for arm in ARMS:
        if r3.get(arm):
            rows.append({"level": "R3 pairs (any family)", "family": "-", "arm": arm,
                         **{c: tally(r3[arm])[c] for c in cols[3:]}})
    for fam in FAMILY_ORDER:
        for arm in ARMS:
            if (fam, arm) in fam_findings:
                rows.append({"level": "findings (representatives)", "family": fam, "arm": arm,
                             **{c: tally(fam_findings[(fam, arm)])[c] for c in cols[3:]}})
    adir = cdir / "analysis"
    with (adir / "moves-by-family.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    # defect-family pairs and findings without an empty member
    no_empty_pairs = [(fam, p) for (fam, arm), ps in fam_pairs.items() if fam in DEFECT_FAMILIES
                      for p in ps if not p["empty_wkt"] and "empty-part" not in p["moves"]]
    no_empty_find = [(fam, arm, x) for (fam, arm), xs in fam_findings.items()
                     if fam in DEFECT_FAMILIES for x in xs
                     if not x["empty_wkt"] and "empty-part" not in x["moves"]]
    shrunk_lost = Counter(fam for (fam, arm), xs in fam_findings.items() for x in xs
                          if x["empty_wkt"] and not x["shrunk_empty"])
    disagree = sum(("empty-part" in p["moves"]) != p["empty_wkt"] for p in pairs.values())

    short = {"shared-vertex": "shared vertex", "vertex-on-edge": "vertex on edge",
             "collinear-overlap": "collinear overlap", "hole-tangent": "hole tangent",
             "sliver-or-spike": "sliver/spike", "parts-touching": "parts touching",
             "empty-part": "**empty part**", "point-collection": "point collection"}
    md = [f"# Degenerate moves by triage family (E3)", "", f"**{HEADER}**", "",
          "Produced by `python -s -m tavs.posthoc_moves runs/e3` from the lane stores, "
          "`triage/findings.json` and `triage/families.csv`. Each cell is a count of pairs "
          "(or findings) in that row carrying the move; `n` is the row's denominator. Moves are "
          "read from the stored `pairs.moves` field; `EMPTY in WKT` is derived from the stored "
          "inputs. Pairs reach a family through their triage group; crashing pairs (family A) "
          "are included. A pair with two moves counts in both columns.", "",
          "| level | family | arm | n | EMPTY in WKT | no move | "
          + " | ".join(short[m] for m in GEOM_MOVES) + " |",
          "|---|---|---|---:|---:|---:|" + "---:|" * len(GEOM_MOVES)]
    for r in rows:
        md.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    md += ["", "Checks printed by the script:", "",
           f"- items rebuilt from the stores: {len(items)}; groups {len(groups)}; group sizes "
           f"identical to `selection.json`: {sizes_ok}",
           f"- groups mapped to more than one family: {len(mixed)}; groups without a finding: "
           f"{len(uncovered)}; pairs in more than one family: "
           f"{dict((' + '.join(k), v) for k, v in multi.items()) or 'none'}",
           f"- flagged or crashing pairs where stored empty-part and EMPTY in WKT disagree: "
           f"{disagree} of {len(pairs)}; over all 640,000 pairs: "
           f"{sum(t['empty_move_xor_wkt'] for t in tot.values())}",
           f"- defect-family (A-F) pairs with no empty member: {len(no_empty_pairs)} "
           f"({dict(Counter(f for f, _ in no_empty_pairs))}); defect-family findings whose "
           f"representatives have no empty member: {len(no_empty_find)} "
           f"({dict(Counter((f, a) for f, a, _ in no_empty_find))})",
           f"- findings whose representative had EMPTY but whose shrunk input has none: "
           f"{dict(shrunk_lost) or 'none'}",
           "- Findings are counted once per arm they occur in (as in `families.py`); their moves "
           "are those of their representatives from that arm. Family B is defined in "
           "`families.py` as an R3 finding with EMPTY in the shrunk input, so its empty-member "
           "share among findings is 100% by construction."]
    (adir / "moves-by-family.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md[md.index("Checks printed by the script:"):]))
    print("defect pairs without empty member:",
          [(f, p["arm"], p["seed"], p["kind"], p["idx"], p["moves"]) for f, p in no_empty_pairs][:40])
    print(f"wrote {adir / 'moves-by-family.csv'} and moves-by-family.md ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
