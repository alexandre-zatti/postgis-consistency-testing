"""Campaign analysis (experiment-plan.md, "Measures and statistics").

python -s -m tavs.analysis --campaign <name>

Reads every runs/<campaign>/lane*.sqlite written by tavs/campaign.py and writes
runs/<campaign>/analysis/analysis.json (all numbers) and summary.txt.

Definitions (fixed here, one place to change):
- Harness-error pair: any outcome of kind in HARNESS_KINDS. Removed from every rate.
- Violating pair: see `counted`: strict; or a yes/no-rule (R1-R5, R10) candidate, which has no
  magnitude and counts as in the triage band; or a measured candidate in band "triage".
  Candidates flagged precision-limited never count. Crash outcomes are not violations.
  Sensitivity rates: strict plus measured triage-band candidates only. Unbanded candidates
  from other rules are reported, not counted.
- Rate per (seed, arm): violating pairs per 10k, pooled over kinds with equal weight
  (mean of the per-kind rates; equal to the pooled rate when the kinds have equal N).
- Contrasts, paired by seed: d = rate(first arm) - rate(second arm). Exact two-sided Wilcoxon
  signed-rank (scipy.stats.wilcoxon, method="exact", zero_method="wilcox": seeds with a zero
  difference are dropped and n is the number of non-zero differences; ties among the non-zero
  |d| are flagged because the exact null distribution assumes none). Holm over the four planned
  contrasts with m = 4 fixed (an untested contrast enters with p = 1). Matched-pairs
  rank-biserial r = (T+ - T-) / (T+ + T-) over the same non-zero differences. McNemar counts at
  pair level (same seed, kind, index): b = first arm violating and second not, c = the reverse;
  descriptive only. A contrast where either arm has zero violating pairs in every seed is
  reported as counts and not tested.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import rankdata, wilcoxon

ROOT = Path(__file__).resolve().parent.parent
YESNO_RULES = {"R1", "R2", "R3", "R4", "R5", "R6", "R10"}   # yes/no rules: candidates carry no band
HARNESS_KINDS = {"harness_exception", "other_error", "sql_error"}
ARMS = ["plain-int", "plain-float", "degen-int", "degen-float"]
CONTRASTS = [
    ("degen vs plain within int", "degen-int", "plain-int"),
    ("degen vs plain within float", "degen-float", "plain-float"),
    ("float vs int within plain", "plain-float", "plain-int"),
    ("float vs int within degen", "degen-float", "degen-int"),
]


def load(cdir: Path) -> dict:
    """pair key (seed, kind, idx, arm) -> record; duplicates across or within files counted."""
    pairs: dict = {}
    dups = 0
    batches = []
    files = sorted(cdir.glob("lane*.sqlite"))
    for f in files:
        db = sqlite3.connect(f"file:{f.as_posix()}?mode=ro", uri=True)
        rows = db.execute(
            "SELECT c.pair_id, c.seed, c.kind, c.idx, c.arm, c.form, c.regime, c.tier_predicate,"
            " c.tier_overlay, c.wall_s, c.crash_events, c.crash_wait_s, p.info, p.moves "
            "FROM campaign_pairs c JOIN pairs p USING (pair_id)").fetchall()
        viol = defaultdict(list)
        for pid, rule, sub, fn, tier, mag, band, plim in db.execute(
                "SELECT pair_id, rule, sub, function, tier, magnitude, band, precision_limited "
                "FROM violations"):
            viol[pid].append({"rule": rule, "sub": sub, "function": fn, "tier": tier,
                              "magnitude": mag, "band": band, "plim": bool(plim)})
        outc = defaultdict(list)
        for pid, stage, kind, msg in db.execute(
                "SELECT pair_id, stage, kind, message FROM outcomes"):
            outc[pid].append({"stage": stage, "kind": kind, "message": msg or ""})
        for (pid, seed, kind, idx, arm, form, regime, tp, to, wall, ce, cw, info,
             moves) in rows:
            key = (seed, kind, idx, arm)
            if key in pairs:
                dups += 1
                continue
            info = json.loads(info or "{}")
            pairs[key] = {"lane": f.stem, "seed": seed, "kind": kind, "idx": idx, "arm": arm,
                          "form": form, "regime": regime, "tier_predicate": tp,
                          "tier_overlay": to, "wall_s": wall, "crash_events": ce,
                          "crash_wait_s": cw, "types": info.get("types"),
                          "crashed_functions": info.get("crashed_functions", []),
                          "moves": json.loads(moves or "[]"),
                          "violations": viol[pid], "outcomes": outc[pid]}
        try:
            batches += [dict(zip(("lane", "seed", "kind", "n", "seconds", "crashed", "errors"),
                                 (f.stem,) + r)) for r in db.execute(
                "SELECT seed, kind, n_pairs, seconds, crashed, errors FROM batches")]
        except sqlite3.OperationalError:
            pass
        db.close()
    return {"pairs": pairs, "duplicates": dups, "files": [f.name for f in files],
            "batches": batches}


def counted(v: dict, sensitivity: bool = False) -> bool:
    """Primary: strict; or a candidate from a yes/no rule (no magnitude, counted as in the
    triage band); or a measured candidate in the triage band. Precision-limited removes only
    measured candidates: yes/no overlay rules stay evaluated on such pairs (review, Q1).
    Sensitivity: strict plus measured triage-band only."""
    if v["tier"] == "strict":
        return True
    if v["tier"] != "candidate":
        return False
    if v["band"] == "triage":
        return not v["plim"]
    return not sensitivity and v["rule"] in YESNO_RULES and v["band"] is None


def classify(p: dict) -> None:
    p["harness"] = any(o["kind"] in HARNESS_KINDS for o in p["outcomes"])
    p["violating"] = any(counted(v) for v in p["violations"])
    p["violating_sens"] = any(counted(v, True) for v in p["violations"])
    # unbanded candidates outside YESNO_RULES (not counted anywhere; reported)
    p["other_unbanded"] = any(v["tier"] == "candidate" and v["band"] is None
                              and v["rule"] not in YESNO_RULES for v in p["violations"])
    p["crashed"] = any(o["kind"] == "crash" for o in p["outcomes"])


def per10k(k: int, n: int):
    return None if n == 0 else 1e4 * k / n


def rate_table(pairs: list[dict], seeds, kinds, key: str = "violating") -> dict:
    """{arm: {seed: {"pooled": r, "by_kind": {kind: {"n","k","rate"}}}}}"""
    cnt = defaultdict(lambda: [0, 0])          # (arm, seed, kind) -> [n, k]
    for p in pairs:
        if p["harness"]:
            continue
        c = cnt[(p["arm"], p["seed"], p["kind"])]
        c[0] += 1
        c[1] += p[key]
    out: dict = {}
    for arm in ARMS:
        if not any(a == arm for a, _, _ in cnt):
            continue
        out[arm] = {}
        for s in seeds:
            bk = {k: {"n": cnt[(arm, s, k)][0], "k": cnt[(arm, s, k)][1],
                      "rate": per10k(cnt[(arm, s, k)][1], cnt[(arm, s, k)][0])} for k in kinds}
            rs = [v["rate"] for v in bk.values() if v["rate"] is not None]
            out[arm][s] = {"pooled": float(np.mean(rs)) if len(rs) == len(kinds) else None,
                           "n": sum(v["n"] for v in bk.values()),
                           "k": sum(v["k"] for v in bk.values()), "by_kind": bk}
    return out


def holm(ps: list[float]) -> list[float]:
    m = len(ps)
    order = sorted(range(m), key=lambda i: ps[i])
    adj = [1.0] * m
    run = 0.0
    for r, i in enumerate(order):
        run = max(run, min(1.0, (m - r) * ps[i]))
        adj[i] = run
    return adj


def contrast(rates: dict, pairs_by_key: dict, name: str, x: str, y: str, seeds) -> dict:
    res = {"contrast": name, "first": x, "second": y, "tested": False}
    if x not in rates or y not in rates:
        res["note"] = "arm missing from the campaign"
        res["p"] = None
        return res
    xs = [rates[x][s]["pooled"] for s in seeds]
    ys = [rates[y][s]["pooled"] for s in seeds]
    keep = [i for i in range(len(seeds)) if xs[i] is not None and ys[i] is not None]
    res["seeds"] = [seeds[i] for i in keep]
    res["rates_first"] = [xs[i] for i in keep]
    res["rates_second"] = [ys[i] for i in keep]
    res["counts_first"] = sum(rates[x][s]["k"] for s in seeds)
    res["counts_second"] = sum(rates[y][s]["k"] for s in seeds)
    d = np.array([xs[i] - ys[i] for i in keep], float)
    res["median_diff"] = float(np.median(d)) if len(d) else None
    # McNemar counts over pairs present and non-harness in both arms
    b = c = n_pairs = 0
    for (s, k, i, arm), p in pairs_by_key.items():
        if arm != x:
            continue
        q = pairs_by_key.get((s, k, i, y))
        if q is None or p["harness"] or q["harness"]:
            continue
        n_pairs += 1
        b += p["violating"] and not q["violating"]
        c += q["violating"] and not p["violating"]
    res["mcnemar"] = {"b": b, "c": c, "pairs": n_pairs}
    nz = d[d != 0]
    res["n_nonzero"] = int(len(nz))
    res["n_zero_dropped"] = int(len(d) - len(nz))
    if res["counts_first"] == 0 or res["counts_second"] == 0:
        res["note"] = "an arm has zero violating pairs in every seed: counts only, not tested"
        res["p"] = None
        return res
    if len(nz) == 0:
        res["note"] = "every seed difference is zero: not tested"
        res["p"] = None
        return res
    ranks = rankdata(np.abs(nz))
    tp, tm = float(ranks[nz > 0].sum()), float(ranks[nz < 0].sum())
    res["rank_biserial"] = (tp - tm) / (tp + tm)
    res["ties_in_nonzero_abs_diffs"] = bool(len(set(np.abs(nz))) < len(nz))
    w = wilcoxon([xs[i] for i in keep], [ys[i] for i in keep],
                 zero_method="wilcox", method="exact", alternative="two-sided")
    res.update(tested=True, statistic=float(w.statistic), p=float(w.pvalue))
    return res


def analyse(cdir: Path) -> dict:
    data = load(cdir)
    pairs_by_key = data["pairs"]
    pairs = list(pairs_by_key.values())
    for p in pairs:
        classify(p)
    seeds = sorted({p["seed"] for p in pairs})
    kinds = sorted({p["kind"] for p in pairs})
    arms = [a for a in ARMS if any(p["arm"] == a for p in pairs)]
    cdef = {}
    if (cdir / "campaign.json").exists():
        cdef = json.loads((cdir / "campaign.json").read_text(encoding="utf-8"))
    expected = (len(cdef.get("seeds", [])) * len(cdef.get("kinds", [])) * cdef.get("n", 0)
                * len(cdef.get("arms", []))) if cdef else None

    rates = rate_table(pairs, seeds, kinds)
    cons = [contrast(rates, pairs_by_key, *c, seeds) for c in CONTRASTS]
    adj = holm([c["p"] if c.get("tested") else 1.0 for c in cons])
    for c, a in zip(cons, adj):
        c["p_holm"] = a if c.get("tested") else None

    by_arm = defaultdict(list)
    for p in pairs:
        by_arm[p["arm"]].append(p)
    ok = {a: [p for p in by_arm[a] if not p["harness"]] for a in arms}

    def grouped(key, arms_sel):
        out = {}
        for a in arms_sel:
            g = defaultdict(lambda: [0, 0])
            for p in ok[a]:
                g[p[key]][0] += 1
                g[p[key]][1] += p["violating"]
            out[a] = {str(k): {"n": n, "violating": v, "per10k": per10k(v, n)}
                      for k, (n, v) in sorted(g.items(), key=lambda x: str(x[0]))}
        return out

    rule_rates = {}
    for a in arms:
        r_any, r_cnt = Counter(), Counter()
        for p in ok[a]:
            r_any.update({v["rule"] for v in p["violations"]})
            r_cnt.update({v["rule"] for v in p["violations"] if counted(v)})
        n = len(ok[a])
        rule_rates[a] = {r: {"pairs_any": r_any[r], "pairs_counted": r_cnt[r],
                             "counted_per10k": per10k(r_cnt[r], n)}
                         for r in sorted(r_any, key=lambda s: int("".join(ch for ch in s if ch.isdigit()) or 0))}

    bands = {}
    for a in arms:
        c = Counter()
        for p in ok[a]:
            for v in p["violations"]:
                if v["band"]:
                    c[f"{v['rule']}|{v['band']}|{'plim' if v['plim'] else 'ok'}"] += 1
        bands[a] = dict(sorted(c.items()))

    crash = {"events_in_pairs": sum(p["crash_events"] or 0 for p in pairs),
             "pairs_with_crash": sum(p["crashed"] for p in pairs),
             "recovery_wait_s": sum(p["crash_wait_s"] or 0 for p in pairs),
             "wall_s_of_pairs_with_crash": sum(p["wall_s"] for p in pairs if p["crashed"]),
             "batch_crashes": sum(b["crashed"] for b in data["batches"]),
             "batch_crash_s": sum(b["seconds"] for b in data["batches"] if b["crashed"]),
             "by_arm": {a: sum(p["crashed"] for p in by_arm[a]) for a in arms}}
    sigs = Counter()
    for p in pairs:
        if p["crashed"]:
            t = "/".join(p["types"] or ["?"])
            fs = set(p["crashed_functions"])
            fs |= {"ST_" + o["stage"].split(":")[1] + " (index join)" for o in p["outcomes"]
                   if o["kind"] == "crash" and o["stage"].startswith("batch:")
                   and o["stage"].count(":") == 2}
            for f in sorted(fs) or ["(unattributed)"]:
                sigs[f"{f} | {t}"] += 1
    crash["unique_signatures"] = len(sigs)
    crash["signatures"] = dict(sigs.most_common())
    crash["by_lane"] = {}
    for p in pairs:
        L = crash["by_lane"].setdefault(p["lane"], {"events": 0, "recovery_wait_s": 0.0})
        L["events"] += p["crash_events"] or 0
        L["recovery_wait_s"] += p["crash_wait_s"] or 0
    for b in data["batches"]:
        if b["crashed"]:
            L = crash["by_lane"].setdefault(b["lane"], {"events": 0, "recovery_wait_s": 0.0})
            L["events"] += 1
            L["recovery_wait_s"] += b["seconds"]

    timing = {}
    for a in arms:
        w = [p["wall_s"] for p in by_arm[a]]
        timing[a] = {"pairs": len(w), "wall_s": sum(w),
                     "pairs_per_h": 3600 * len(w) / sum(w) if sum(w) else None,
                     "median_ms": 1000 * float(np.median(w)) if w else None}
    timing["batch_join_s"] = sum(b["seconds"] for b in data["batches"])

    tier_diff = {a: {"pairs": len(by_arm[a]),
                     "differ": sum(p["tier_predicate"] != p["tier_overlay"] for p in by_arm[a])}
                 for a in arms}
    for a in arms:
        t = tier_diff[a]
        t["share"] = t["differ"] / t["pairs"] if t["pairs"] else None

    outcomes = {a: dict(Counter(o["kind"] for p in by_arm[a] for o in p["outcomes"])) for a in arms}
    harness = {a: sum(p["harness"] for p in by_arm[a]) for a in arms}
    unbanded = {a: sum(p["other_unbanded"] for p in ok[a]) for a in arms}
    sens = rate_table(pairs, seeds, kinds, "violating_sens")

    return {
        "campaign": cdir.name, "files": data["files"], "definition": cdef,
        "pairs_loaded": len(pairs), "pairs_expected": expected,
        "duplicate_keys": data["duplicates"], "seeds": seeds, "kinds": kinds, "arms": arms,
        "harness_error_pairs": harness, "definitions": {
            "harness_kinds": sorted(HARNESS_KINDS),
            "violating": "strict; or candidate from a yes/no rule (R1-R5, R10), counted as "
                         "triage; or measured candidate in band triage; candidates flagged "
                         "precision-limited excluded",
            "sensitivity": "strict plus measured triage-band candidates only",
            "pooling": "mean of per-kind rates (equal weight per kind)",
            "wilcoxon": "scipy.stats.wilcoxon exact two-sided, zero_method=wilcox (zeros dropped)",
            "holm": "m = 4 fixed; untested contrasts enter with p = 1"},
        "rates": {a: {str(s): v for s, v in r.items()} for a, r in rates.items()},
        "contrasts": cons,
        "secondary": {
            "rule_rates": rule_rates,
            "by_form": grouped("form", arms),
            "by_regime_float": grouped("regime", [a for a in arms if a.endswith("float")]),
            "band_counts": bands, "crashes": crash, "timing": timing,
            "tier_differs": tier_diff, "outcome_kinds": outcomes,
            "other_unbanded_candidate_pairs": unbanded,
            "sensitivity_strict_plus_measured_triage": {
                a: {str(s): v for s, v in r.items()} for a, r in sens.items()}},
    }


def fmt(x, nd=1):
    return "-" if x is None else (f"{x:.{nd}f}" if isinstance(x, float) else str(x))


def summary(res: dict) -> str:
    L = [f"Campaign {res['campaign']}: {res['pairs_loaded']} pairs loaded "
         f"(expected {res['pairs_expected']}), duplicate keys {res['duplicate_keys']}, "
         f"files {', '.join(res['files'])}",
         f"Harness-error pairs removed: {res['harness_error_pairs']}", "",
         "Primary: violating pairs per 10k, per seed (kinds pooled with equal weight)"]
    for a, r in res["rates"].items():
        L.append(f"  {a:<12} " + "  ".join(f"{s}:{fmt(v['pooled'])} ({v['k']}/{v['n']})"
                                          for s, v in r.items()))
    L.append("  per kind (descriptive):")
    for a, r in res["rates"].items():
        for s, v in r.items():
            L.append(f"    {a:<12} seed {s}: " + ", ".join(
                f"{k} {fmt(b['rate'])} ({b['k']}/{b['n']})" for k, b in v["by_kind"].items()))
    L += ["", "Planned contrasts (paired by seed; exact Wilcoxon, zeros dropped; Holm m=4)",
          f"  {'contrast':<30}{'k1':>5}{'k2':>5}{'n!=0':>6}{'W':>7}{'p':>9}{'p_holm':>9}"
          f"{'r_rb':>7}{'b':>6}{'c':>6}  note"]
    for c in res["contrasts"]:
        m = c.get("mcnemar", {})
        L.append(f"  {c['contrast']:<30}{fmt(c.get('counts_first')):>5}"
                 f"{fmt(c.get('counts_second')):>5}{fmt(c.get('n_nonzero')):>6}"
                 f"{fmt(c.get('statistic')):>7}{fmt(c.get('p'), 4):>9}"
                 f"{fmt(c.get('p_holm'), 4):>9}{fmt(c.get('rank_biserial'), 2):>7}"
                 f"{fmt(m.get('b')):>6}{fmt(m.get('c')):>6}  {c.get('note', '')}"
                 + ("  (ties among |d|)" if c.get("ties_in_nonzero_abs_diffs") else ""))
    s = res["secondary"]
    L += ["", "Rule-level (pairs with a counted violation / any violation):"]
    for a, r in s["rule_rates"].items():
        L.append(f"  {a:<12} " + (", ".join(f"{k} {v['pairs_counted']}/{v['pairs_any']}"
                                            for k, v in r.items()) or "none"))
    L += ["", "By form within arm (violating/n):"]
    for a, r in s["by_form"].items():
        L.append(f"  {a:<12} " + ", ".join(f"{k} {v['violating']}/{v['n']}" for k, v in r.items()))
    L += ["By regime within float arms (violating/n):"]
    for a, r in s["by_regime_float"].items():
        L.append(f"  {a:<12} " + ", ".join(f"{k} {v['violating']}/{v['n']}" for k, v in r.items()))
    L += ["", "Candidate magnitude bands (rule|band|precision-limited: violations):"]
    for a, r in s["band_counts"].items():
        L.append(f"  {a:<12} " + (", ".join(f"{k}: {v}" for k, v in r.items()) or "none"))
    cr = s["crashes"]
    L += ["", f"Crashes: {cr['events_in_pairs']} events in {cr['pairs_with_crash']} pairs "
          f"(by arm {cr['by_arm']}), recovery wait {cr['recovery_wait_s']:.1f} s, wall of "
          f"crashed pairs {cr['wall_s_of_pairs_with_crash']:.1f} s; batch crashes "
          f"{cr['batch_crashes']} ({cr['batch_crash_s']:.1f} s); unique signatures "
          f"{cr['unique_signatures']}"]
    L += [f"  {k}: {v}" for k, v in cr["signatures"].items()]
    L += [f"  by lane: {cr['by_lane']}"]
    L += ["", "Timing (evaluate wall time; batch joins separate):"]
    for a, t in s["timing"].items():
        if a == "batch_join_s":
            L.append(f"  batch joins: {t:.1f} s")
        else:
            L.append(f"  {a:<12} {t['pairs']} pairs, {t['wall_s']:.1f} s, "
                     f"{fmt(t['pairs_per_h'], 0)} pairs/h, median {fmt(t['median_ms'])} ms")
    L += ["", "Predicate tier differs from overlay tier: " + ", ".join(
        f"{a} {t['differ']}/{t['pairs']}" for a, t in s["tier_differs"].items())]
    L += ["Sensitivity (strict + measured triage only), per 10k per seed:"]
    for a, r in s["sensitivity_strict_plus_measured_triage"].items():
        L.append(f"  {a:<12} " + "  ".join(f"{sd}:{fmt(v['pooled'])} ({v['k']}/{v['n']})"
                                          for sd, v in r.items()))
    L += ["Unbanded candidate pairs from rules outside R1-R5/R10 (not counted): "
          + ", ".join(f"{a} {v}" for a, v in s["other_unbanded_candidate_pairs"].items())]
    L += ["Outcome kinds: " + "; ".join(f"{a} {v}" for a, v in s["outcome_kinds"].items())]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--campaign", required=True)
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    cdir = ROOT / "runs" / args.campaign
    res = analyse(cdir)
    out = cdir / "analysis"
    out.mkdir(parents=True, exist_ok=True)
    (out / "analysis.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    text = summary(res)
    (out / "summary.txt").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
