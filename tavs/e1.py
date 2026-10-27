"""E1 sensitivity run (experiment-plan.md, "E1 pre-registered seeds" and "Experiments").

python -m tavs.e1 [--skip-seeds] [--skip-xml] [--xml-limit N]

1. Seeds: writes seeds/e1_preregistration.json (if absent; otherwise reads it), builds pairs from
   seeds/known_bugs.json, runs every applicable rule on each image named for each seed, and
   reports whether the pre-registered rules fired where expected and stayed silent where
   expected, plus other rules that fired.
2. XML false-alarm corpus: GEOS XML test cases on the current image.
Results: runs/tavs.sqlite; summary: runs/e1/summary.md, seeds.csv, xml.csv, batch_plan.json.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

import shapely

from .db import Target
from .pair import Pair
from .rules import (Evaluation, Outcome, apply_batch, batch_join_lane, crash_list, evaluate,
                    tier_of)
from .store import Store

ROOT = Path(__file__).resolve().parent.parent
SEEDS = ROOT / "seeds"
PREREG = SEEDS / "e1_preregistration.json"
OUT = ROOT / "runs" / "e1"
IMAGES = ["current", "dev", "old"]

# Encoding of the plan's E1 table. "pairs" name geometry keys of the known_bugs.json record
# as (a, b). "match": "all" = every expected rule must fire, "any" = at least one.
# "fires_on": null = "to confirm" (run on every image, no verdict).
PREREGISTRATION = {
    "source": "experiment-plan.md, section 'E1 pre-registered seeds' (2026-10-27)",
    "fired_means": "at least one violation of the rule on at least one of the seed's pairs "
                   "(boolean rules: any tier; measure rules: band logged or triage)",
    "silent_means": "none of the seed's expected rules has a violation on that image",
    "seeds": [
        {"seed": "tangent-hole", "record": "geos#1558", "pairs": [["a", "b"]],
         "expected_rules": ["R3", "R1"], "match": "all",
         "detail": "R3 lone vs prepared Contains/Covers; R1",
         "fires_on": ["current", "dev"], "silent_on": ["old"]},
        {"seed": "geos#1405", "record": "geos#1405",
         "pairs": [["shape1", "shape2"], ["pr1499_a", "pr1499_b"]],
         "expected_rules": ["R8"], "match": "all", "detail": "R8 (intersection order)",
         "fires_on": ["current"], "silent_on": ["dev"],
         "note": "plan: needs the post-set_precision geometries, which are not in the seed data; "
                 "raw shapes and the fix PR's example are used"},
        {"seed": "geos#1383", "record": "geos#1383",
         "pairs": [["ex0_1", "ex0_2"], ["ex1_1", "ex1_2"]],
         "expected_rules": ["R6"], "match": "all", "detail": "R6 (sliver union empty), binary union",
         "fires_on": ["current", "dev"], "silent_on": []},
        {"seed": "geos#1523", "record": "geos#1523", "pairs": [["a", "b"]],
         "expected_rules": ["R9", "R11"], "match": "all", "not_expected": ["R7"],
         "detail": "R9, R11 (not R7)", "fires_on": ["current", "dev"], "silent_on": []},
        {"seed": "geos#1354", "record": "geos#1354", "pairs": [["geom_0", "zone"]],
         "expected_rules": ["R10", "R9", "R11"], "match": "all", "detail": "R10, R9, R11",
         "fires_on": ["current", "dev"], "silent_on": []},
        {"seed": "geos#1343", "record": "geos#1343", "pairs": [["poly1", "poly2"]],
         "expected_rules": ["R9"], "match": "all", "detail": "R9 (binary union)",
         "fires_on": ["current", "dev"], "silent_on": []},
        {"seed": "geos#1344", "record": "geos#1344", "pairs": [["poly1", "poly2"]],
         "expected_rules": ["R5", "R7", "R9"], "match": "all", "detail": "R5, R7, R9",
         "fires_on": ["current", "dev"], "silent_on": []},
        {"seed": "geos#1342", "record": "geos#1342", "pairs": [["wkt1", "wkt2"]],
         "expected_rules": ["R6"], "match": "all", "detail": "R6 candidate (floating mode)",
         "fires_on": ["current", "dev"], "silent_on": []},
        {"seed": "geos#1540", "record": "geos#1540", "pairs": [["A", "B"]],
         "expected_rules": ["R10", "R1"], "match": "any", "detail": "R10 or R1 vs overlay",
         "fires_on": ["current", "dev"], "silent_on": []},
        {"seed": "geos#1027", "record": "geos#1027", "pairs": [["g2", "g1"]],
         "expected_rules": ["R3", "R4"], "match": "all",
         "detail": "R3 lone vs prepared Covers, R4", "fires_on": None, "silent_on": []},
        {"seed": "geos#1053", "record": "geos#1053", "pairs": [["g1", "g2"]],
         "expected_rules": ["R10"], "match": "all", "detail": "R10 (old RelateOp dimension)",
         "fires_on": ["old"], "silent_on": ["current"]},
        {"seed": "geos#1033", "record": "geos#1033", "pairs": [["a", "b"]],
         "expected_rules": ["R3"], "match": "all", "detail": "R3 (Contains vs prepared Contains)",
         "fires_on": ["old"], "silent_on": ["current"]},
        {"seed": "geos#1064", "record": "geos#1064", "pairs": [["A", "B"]],
         "expected_rules": ["R2"], "match": "all", "detail": "R2 (known limitation)",
         "fires_on": ["current", "old"], "silent_on": []},
    ],
}

_DIM = {"Point": 0, "MultiPoint": 0, "LineString": 1, "MultiLineString": 1, "LinearRing": 1,
        "Polygon": 2, "MultiPolygon": 2}


def make_pair(a: str, b: str, source: str) -> Pair:
    ga, gb = shapely.from_wkt(a), shapely.from_wkt(b)
    coord = tier_of(ga, gb, "predicate")   # evaluate() applies each rule family's own tier
    da, db = _DIM.get(ga.geom_type), _DIM.get(gb.geom_type)
    kind = "overlay" if da is not None and da == db and da in (1, 2) else "predicate"
    return Pair(a=a, b=b, coord=coord, kind=kind, source=source)


def load_prereg() -> dict:
    if not PREREG.exists():
        PREREG.write_text(json.dumps(PREREGISTRATION, indent=2) + "\n", encoding="utf-8")
    return json.loads(PREREG.read_text(encoding="utf-8"))


def seed_pairs(prereg: dict) -> dict[str, list[Pair]]:
    recs = {r["id"]: r for r in json.loads((SEEDS / "known_bugs.json").read_text(
        encoding="utf-8"))["records"]}
    out = {}
    for s in prereg["seeds"]:
        geoms = recs[s["record"]]["geometries"]
        out[s["seed"]] = [make_pair(geoms[x].strip(), geoms[y].strip(), f"{s['seed']}:{x},{y}")
                          for x, y in s["pairs"]]
    return out


def run_batch(target: Target, store: Store, run_id: int, pairs: list[Pair],
              plan_sink: dict | None = None) -> list[Evaluation]:
    # evaluate first (gives each pair's crash list), then the lane's index join (R3 (d))
    evs = [evaluate(target, p) for p in pairs]
    bj = batch_join_lane(target, pairs, [crash_list(ev) for ev in evs],
                         explain=plan_sink is not None and not plan_sink)
    if plan_sink is not None and not plan_sink and bj["plan"] is not None:
        plan_sink.update(target=target.name, index_used=bj["index_used"], **bj["plan"])
    for i, ev in enumerate(evs):
        apply_batch(ev, bj["results"].get(i), bj["outcomes"].get(i))
        ev.seconds["batch_lane_share"] = bj["seconds"] / max(len(pairs), 1)
        store.add(run_id, ev, commit=False)
    store.commit()
    return evs


def fired_rules(evs: list[Evaluation]) -> dict[str, list[str]]:
    """rule -> list of short descriptions of its violations."""
    out: dict[str, list[str]] = defaultdict(list)
    for ev in evs:
        for v in ev.violations:
            d = f"{v.sub} [{v.function}{', ' + v.orientation if v.orientation else ''}]"
            if v.band:
                d += f" {v.band} " + (f"{v.magnitude:.3g}" if v.magnitude is not None else "n/a")
            if d not in out[v.rule]:
                out[v.rule].append(d)
    return out


# --------------------------------------------------------------------------------------------

def run_seeds(store: Store, plan_sink: dict) -> list[dict]:
    prereg = load_prereg()
    pairs = seed_pairs(prereg)
    rows = []
    targets = {n: Target(n) for n in IMAGES}
    run_ids = {}
    try:
        for s in prereg["seeds"]:
            fires = s["fires_on"]
            images = IMAGES if fires is None else [i for i in IMAGES
                                                   if i in fires or i in s["silent_on"]]
            for img in images:
                t = targets[img]
                if img not in run_ids:
                    run_ids[img] = store.start_run("E1-seeds", img, t.version(),
                                                   {"prereg": str(PREREG.name)})
                evs = run_batch(t, store, run_ids[img], pairs[s["seed"]], plan_sink)
                fr = fired_rules(evs)
                exp = s["expected_rules"]
                hit = [r for r in exp if r in fr]
                role = ("fire" if fires and img in fires else
                        "silent" if img in s["silent_on"] else "to confirm")
                if role == "fire":
                    ok = (len(hit) == len(exp)) if s["match"] == "all" else bool(hit)
                elif role == "silent":
                    ok = not hit
                else:
                    ok = None
                errs = [f"{o.stage}:{o.kind}" for ev in evs for o in ev.outcomes]
                rows.append({
                    "seed": s["seed"], "image": img, "role": role,
                    "expected": ("all of " if s["match"] == "all" else "any of ") + ",".join(exp),
                    "expected_fired": ",".join(hit) or "-",
                    "as_preregistered": {True: "yes", False: "NO", None: "n/a"}[ok],
                    "not_expected_fired": ",".join(r for r in s.get("not_expected", []) if r in fr)
                                          or "-",
                    "other_rules_fired": ",".join(sorted(set(fr) - set(exp), key=_rk)) or "-",
                    "outcomes": ";".join(sorted(set(errs))) or "-",
                    "detail": " | ".join(f"{r}: " + "; ".join(fr[r][:4]) for r in
                                         sorted(fr, key=_rk)) or "-",
                })
                print(f"  {s['seed']:<13} {img:<8} {role:<10} fired={','.join(sorted(fr, key=_rk)) or '-'}",
                      flush=True)
    finally:
        for img, rid in run_ids.items():
            store.finish_run(rid)
        for t in targets.values():
            t.close()
    return rows


def _rk(r: str) -> int:
    return int("".join(ch for ch in r[1:] if ch.isdigit()))


def seed_verdicts(rows: list[dict], prereg: dict) -> tuple[int, int, list[str]]:
    by_seed = defaultdict(list)
    for r in rows:
        by_seed[r["seed"]].append(r)
    k = n = 0
    lines = []
    for s in prereg["seeds"]:
        rs = by_seed[s["seed"]]
        if s["fires_on"] is None:
            lines.append(f"{s['seed']}: to confirm (no verdict)")
            continue
        n += 1
        ok = all(r["as_preregistered"] == "yes" for r in rs if r["role"] in ("fire", "silent"))
        k += ok
        lines.append(f"{s['seed']}: {'as pre-registered' if ok else 'NOT as pre-registered'}")
    return k, n, lines


# --------------------------------------------------------------------------------------------

def xml_cases(limit: int | None = None):
    """Yield (relative file, case number, a, b) and skip reasons from the GEOS XML corpus."""
    base = SEEDS / "geos-xml"
    skips: Counter = Counter()
    found = []
    for f in sorted(base.rglob("*.xml")):
        rel = f.relative_to(base / "tests" / "xmltester" / "tests").as_posix()
        root = ET.parse(f).getroot()
        for n, case in enumerate(root.iter("case"), 1):
            ea, eb = case.find("a"), case.find("b")
            if ea is None or eb is None or not (eb.text or "").strip():
                skips["no b"] += 1
                continue
            if ea.get("file") or eb.get("file"):
                skips["external file"] += 1
                continue
            wkts = []
            for e in (ea, eb):
                txt = " ".join((e.text or "").split())
                if any(k in txt.upper() for k in ("CIRCULAR", "CURVE", "COMPOUND")):
                    wkts = None
                    skips["curve"] += 1
                    break
                try:
                    g = shapely.from_wkt(txt)
                except Exception:  # noqa: BLE001
                    try:
                        g = shapely.from_wkb(bytes.fromhex(txt))
                        txt = shapely.to_wkt(g, rounding_precision=-1)
                    except Exception:  # noqa: BLE001
                        wkts = None
                        skips["unparseable"] += 1
                        break
                if not shapely.is_valid(g):
                    wkts = None
                    skips["invalid (Shapely)"] += 1
                    break
                if g.geom_type == "LinearRing":   # PostGIS WKT has no LINEARRING
                    txt = shapely.to_wkt(shapely.LineString(g.coords), rounding_precision=-1)
                    skips["LINEARRING converted to LINESTRING (kept)"] += 1
                wkts.append(txt)
            if wkts is None:
                continue
            found.append((rel, n, wkts[0], wkts[1]))
            if limit and len(found) >= limit:
                return found, skips
    return found, skips


def run_xml(store: Store, plan_sink: dict, limit: int | None) -> dict:
    cases, skips = xml_cases(limit)
    by_file = defaultdict(list)
    for rel, n, a, b in cases:
        by_file[rel].append(make_pair(a, b, f"{rel}#{n}"))
    t = Target("current")
    rid = store.start_run("E1-xml", "current", t.version(), {"files": len(by_file),
                                                               "cases": len(cases),
                                                               "skips": dict(skips)})
    evs_all = []
    t0 = time.perf_counter()
    try:
        for rel, pairs in by_file.items():
            evs_all += run_batch(t, store, rid, pairs, plan_sink)
            print(f"  {rel}: {len(pairs)} pairs", flush=True)
    finally:
        store.finish_run(rid)
        t.close()
    return {"evs": evs_all, "skips": skips, "seconds": time.perf_counter() - t0, "run_id": rid}


_BAND_RANK = {"-": 0, "logged": 1, "triage": 2}


def xml_summary(res: dict) -> tuple[list[dict], dict]:
    evs = res["evs"]
    rows = []
    per = defaultdict(lambda: Counter())
    for ev in evs:
        f = ev.pair.source.split("#")[0]
        # one pair per (pair, rule): worst tier and band over the rule's violations, and
        # the pair-level precision-limited flag (constant within a rule)
        by_rule: dict = {}
        for v in ev.violations:
            k = by_rule.setdefault(v.rule, {"tier": v.tier, "band": v.band or "-",
                                            "plim": v.precision_limited, "n": 0})
            k["n"] += 1
            if v.tier == "strict":
                k["tier"] = "strict"
            if _BAND_RANK[v.band or "-"] > _BAND_RANK[k["band"]]:
                k["band"] = v.band or "-"
            k["plim"] = k["plim"] or v.precision_limited
        for rule, k in by_rule.items():
            key = (rule, k["tier"], k["band"], k["plim"])
            per[(f,) + key]["pairs"] += 1
            per[(f,) + key]["violations"] += k["n"]
    for (f, rule, tier, bnd, plim), c in sorted(per.items(), key=lambda x: (x[0][0], _rk(x[0][1]))):
        rows.append({"file": f, "rule": rule, "tier": tier, "band": bnd,
                     "precision_limited": plim, "pairs": c["pairs"], "violations": c["violations"]})
    tot = defaultdict(lambda: Counter())
    for r in rows:
        tot[(r["rule"], r["tier"], r["band"], r["precision_limited"])]["pairs"] += r["pairs"]
    outc = Counter(o.kind for ev in evs for o in ev.outcomes)
    secs = [sum(ev.seconds.values()) for ev in evs]
    by_kind = defaultdict(list)
    for ev, s in zip(evs, secs):
        by_kind[ev.pair.kind].append(s)
    timing = {"pairs": len(evs), "mean_ms": 1000 * statistics.mean(secs) if secs else 0,
              "median_ms": 1000 * statistics.median(secs) if secs else 0,
              "by_kind": {k: {"n": len(v), "mean_ms": 1000 * statistics.mean(v),
                              "median_ms": 1000 * statistics.median(v)}
                          for k, v in by_kind.items()},
              "wall_s": res["seconds"]}
    kinds = Counter((ev.pair.kind, ev.pair.coord) for ev in evs)
    return rows, {"totals": tot, "outcomes": outc, "timing": timing, "kinds": kinds}


# --------------------------------------------------------------------------------------------

def _md_table(rows: list[dict], cols: list[str]) -> str:
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        out.append("| " + " | ".join(str(r[c]).replace("|", "/") for c in cols) + " |")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--skip-seeds", action="store_true")
    ap.add_argument("--skip-xml", action="store_true")
    ap.add_argument("--xml-limit", type=int, default=None)
    ap.add_argument("--db", default=None, help="SQLite path (default runs/tavs.sqlite)")
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)
    store = Store(args.db)
    plan_sink: dict = {}
    md = [f"# E1 summary ({time.strftime('%Y-%m-%d %H:%M')})", ""]

    if not args.skip_seeds:
        print("E1 seeds")
        rows = run_seeds(store, plan_sink)
        prereg = load_prereg()
        k, n, lines = seed_verdicts(rows, prereg)
        cols = ["seed", "image", "role", "expected", "expected_fired", "as_preregistered",
                "not_expected_fired", "other_rules_fired", "outcomes"]
        with open(OUT / "seeds.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols + ["detail"])
            w.writeheader()
            w.writerows(rows)
        md += ["## Pre-registered seeds", "", f"**{k} of {n} seeds fired as pre-registered** "
               "(fired on every 'fires on' image and silent on every 'silent on' image; "
               "seeds marked 'to confirm' excluded).", "", _md_table(rows, cols), "",
               *[f"- {x}" for x in lines], "", "### Violations per seed and image", ""]
        md += [f"- {r['seed']} / {r['image']}: {r['detail']}" for r in rows]
        md.append("")

    if not args.skip_xml:
        print("E1 XML corpus (current)")
        res = run_xml(store, plan_sink, args.xml_limit)
        rows, s = xml_summary(res)
        cols = ["file", "rule", "tier", "band", "precision_limited", "pairs", "violations"]
        with open(OUT / "xml.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
        tot_rows = [{"rule": r, "tier": t, "band": b, "precision_limited": p, "pairs": c["pairs"]}
                    for (r, t, b, p), c in sorted(s["totals"].items(), key=lambda x: _rk(x[0][0]))]
        tm = s["timing"]
        md += ["## XML false-alarm corpus (current image)", "",
               f"Pairs evaluated: {tm['pairs']} "
               f"({', '.join(f'{k[0]}/{k[1]}: {v}' for k, v in sorted(s['kinds'].items()))}); "
               f"skipped: {dict(res['skips'])}.", "",
               "Pairs with at least one violation, by rule (before triage):", "",
               _md_table(tot_rows, ["rule", "tier", "band", "precision_limited", "pairs"]) if tot_rows
               else "(none)", "",
               f"Outcomes (errors/skips): {dict(s['outcomes']) or 'none'}.", "",
               f"Time per pair (lone + prepared + overlay statements, excluding the batch join): "
               f"mean {tm['mean_ms']:.1f} ms, median {tm['median_ms']:.1f} ms; "
               + "; ".join(f"{k}: n={v['n']} mean {v['mean_ms']:.1f} ms median {v['median_ms']:.1f} ms"
                           for k, v in tm["by_kind"].items())
               + f". Wall time {tm['wall_s']:.0f} s including batch joins.", "",
               "By file:", "", _md_table(rows, cols) if rows else "(none)", ""]

    if plan_sink:
        (OUT / "batch_plan.json").write_text(json.dumps(plan_sink, indent=2), encoding="utf-8")
        md += [f"Index join plan checked once ({plan_sink.get('target')}): index used = "
               f"{plan_sink.get('index_used')}; see batch_plan.json.", ""]
    text = "\n".join(md)
    (OUT / "summary.md").write_text(text, encoding="utf-8")
    print(text)
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
