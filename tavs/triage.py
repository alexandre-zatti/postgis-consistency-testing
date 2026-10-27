"""E4 triage (experiment-plan.md, "Experiments": E4 row, dedup key, outcome classes, crashes).

  .venv/Scripts/python.exe -s -m tavs.triage --campaign e3
  .venv/Scripts/python.exe -s -m tavs.triage --campaign-dir <path>      (any folder with lane*.sqlite)
  options: --k 3 --cap 300 --steps 200 --crash-oracle container|shapely --rules R3,R12f
           --select-only (no Docker; writes selection.json only)

Steps, for one campaign:
1. Select every violation that `analysis.counted()` counts, plus every crash outcome (one item
   per (pair, crashed SQL function)).
2. Pre-group by (rule, sub, function, paths, orientation, arm, type signature of the pair).
   Within a group pick up to K representatives, smallest total vertex count first. Total cap:
   representatives are taken round-robin by rank (every group's first, then every second, ...),
   groups in descending size; what the cap leaves out is reported per group.
3. Shrink each representative with `shrink.shrink` (<= `--steps` oracle calls, chain recorded).
   Violation oracle: `rules.evaluate` on the candidate (plus a one-pair `batch_join_lane` for the
   index-join sub-check) shows a counted violation with the same (rule, sub, function,
   orientation). Crash oracle: one of the lone probes that crashed the original pair still
   crashes (`--crash-oracle container`, default), or the equivalent Shapely call still kills a
   Shapely subprocess (`--crash-oracle shapely`).
4. Deduplicate with the plan's key: (rule, function, path pair, type signature of the shrunk
   pair, ST_Normalize'd WKTs of the shrunk pair).
5. Re-run each unique finding through `evaluate` (crash findings: the probes) on current, dev
   and old, and record whether the same violation appears.
6. GEOS-only check in Shapely 2.2.0 / GEOS 3.14.1 in a subprocess (`tavs.triage_shapely`).
7. Draft an outcome class per finding (marked "draft"; "known open issue" is never set here).
8. Write runs/<campaign>/triage/: findings.json, findings.csv, summary.txt, selection.json,
   shrinks/<rep>.json and reruns/<finding>.json (the last two make a restart skip finished work).

Every SQL statement goes to throwaway containers started from the digests in compose.yaml
(label tavs.triage=1) and removed at the end, never to the shared or lane containers: shrinking
and re-running deliberately send candidate geometries that may crash a backend.
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import hashlib
import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

import shapely

from .analysis import counted
from .db import Target
from .gen import from_wkt, nvert
from .pair import Pair

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
IMAGES = ("current", "dev", "old")
SNAP_NOTE = ("heuristic bound: OverlayNG worst-case snap displacement max(1e-9*L, 1e-8*M) "
             "(plan, R12), times the operands' total boundary length for areas")


# --------------------------------------------------------------------------------------------
# helpers

def _h(s: str, n: int = 12) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:n]


def _sig(g) -> str:
    if g.is_empty:
        return f"{g.geom_type} EMPTY"
    if g.geom_type == "GeometryCollection":
        return "GeometryCollection(" + ",".join(sorted({_sig(m) for m in g.geoms})) + ")"
    return g.geom_type


def type_sig(a: str, b: str) -> str:
    try:
        return _sig(shapely.from_wkt(a)) + " / " + _sig(shapely.from_wkt(b))
    except Exception:  # noqa: BLE001
        return "unparsable"


def _nv(wkt: str) -> int:
    try:
        return nvert(from_wkt(wkt, False))
    except Exception:  # noqa: BLE001
        return 10 ** 9


def _write_json(path: Path, obj) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=1, default=str, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _vdict(v) -> dict:
    return {"rule": v.rule, "sub": v.sub, "function": v.function, "paths": v.paths,
            "orientation": v.orientation, "tier": v.tier, "band": v.band,
            "magnitude": v.magnitude, "plim": bool(v.precision_limited), "raw": v.raw}


# --------------------------------------------------------------------------------------------
# throwaway containers

def image_digests() -> dict:
    text = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    out = {}
    for name in IMAGES:
        m = re.search(rf"^\s*{name}:.*?\n(?:.*\n)*?\s*image:\s*(\S+)", text, re.M)
        if m:
            out[name] = m.group(1)
    return out


class Throwaways:
    """One throwaway PostgreSQL container per image, started on demand, removed by close()."""

    def __init__(self):
        self.digests = image_digests()
        self.started: dict[str, tuple[str, int]] = {}
        self.targets: dict[str, Target] = {}
        self.versions: dict[str, str] = {}
        self.log: list[str] = []

    def target(self, image: str) -> Target:
        if image in self.targets:
            return self.targets[image]
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        name = f"tavs-triage-{image}-{os.getpid()}"
        cmd = ["docker", "run", "-d", "--rm", "--name", name, "--label", "tavs.triage=1",
               "-e", "POSTGRES_PASSWORD=postgis", "--shm-size", "256m",
               "-p", f"127.0.0.1:{port}:5432", self.digests[image],
               "postgres", "-c", "fsync=off", "-c", "synchronous_commit=off",
               "-c", "full_page_writes=off"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"docker run failed for {image}: {r.stderr.strip()[:500]}")
        self.started[image] = (name, port)
        self.log.append(f"started {name} from {self.digests[image]} on 127.0.0.1:{port}")
        t = Target(f"triage-{image}", port=port)
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < 240:
            rr = t.run("SELECT postgis_full_version()")
            if rr.ok:
                self.versions[image] = rr.one()[0]
                break
            t.close_quietly()
            time.sleep(2)
        else:
            raise RuntimeError(f"throwaway {name} not ready after 240 s")
        self.targets[image] = t
        return t

    def close(self) -> None:
        for t in self.targets.values():
            t.close_quietly()
        for image, (name, _) in self.started.items():
            r = subprocess.run(["docker", "rm", "-f", name], capture_output=True, text=True)
            self.log.append(f"removed {name}: rc={r.returncode}")
        self.started.clear()
        self.targets.clear()


# --------------------------------------------------------------------------------------------
# 1. selection

def load_items(cdir: Path, rules: Optional[set] = None) -> list[dict]:
    items = []
    for f in sorted(cdir.glob("lane*.sqlite")):
        db = sqlite3.connect(f"file:{f.as_posix()}?mode=ro", uri=True)
        has_cp = bool(db.execute("SELECT 1 FROM sqlite_master WHERE name='campaign_pairs'")
                      .fetchone())
        cp = ("LEFT JOIN campaign_pairs c USING (pair_id)" if has_cp else "")
        cols = "c.seed, c.kind, c.idx, c.arm" if has_cp else "p.seed, p.kind, p.idx, p.arm"
        pairs = {}
        for row in db.execute(f"SELECT p.pair_id, p.a, p.b, p.coord, {cols}, p.moves, p.source, "
                              f"p.info FROM pairs p {cp}"):
            pid, a, b, coord, seed, kind, idx, arm, moves, source, info = row
            pairs[pid] = {"lane": f.stem, "pair_id": pid, "a": a, "b": b, "coord": coord,
                          "seed": seed, "kind": kind, "idx": idx, "arm": arm,
                          "moves": json.loads(moves or "[]"), "source": source,
                          "info": json.loads(info or "{}")}

        def base(pid):
            p = pairs[pid]
            return {k: p[k] for k in ("lane", "pair_id", "a", "b", "coord", "seed", "kind",
                                      "idx", "arm", "moves", "source")}

        for (vid, pid, rule, sub, fn, paths, o, tier, mag, band, plim, raw) in db.execute(
                "SELECT violation_id, pair_id, rule, sub, function, paths, orientation, tier, "
                "magnitude, band, precision_limited, raw FROM violations"):
            v = {"rule": rule, "sub": sub, "function": fn, "tier": tier, "magnitude": mag,
                 "band": band, "plim": bool(plim)}
            if not counted(v) or (rules and rule not in rules) or pid not in pairs:
                continue
            items.append(dict(base(pid), item=f"{f.stem}:{pid}:v{vid}", rule=rule, sub=sub,
                              function=fn, paths=paths, orientation=o, tier=tier,
                              magnitude=mag, band=band, plim=bool(plim),
                              raw=json.loads(raw or "{}")))
        if rules and "crash" not in rules:
            db.close()
            continue
        crash_stages = defaultdict(list)
        for pid, stage in db.execute("SELECT pair_id, stage FROM outcomes WHERE kind='crash'"):
            crash_stages[pid].append(stage)
        for pid, stages in crash_stages.items():
            if pid not in pairs:
                continue
            fs = set(pairs[pid]["info"].get("crashed_functions", []))
            fs |= {"ST_" + s.split(":")[1] for s in stages
                   if s.startswith("batch:") and s.count(":") == 2}
            for fn in sorted(fs) or ["(unattributed)"]:
                pats = sorted({s.split(":", 1)[1] for s in stages if ":pat" in s
                               or s.startswith("lone:pat")})
                items.append(dict(base(pid), item=f"{f.stem}:{pid}:crash:{fn}", rule="crash",
                                  sub="backend crash", function=fn, paths="", orientation=None,
                                  tier="crash", magnitude=None, band=None, plim=False,
                                  raw={"stages": stages, "pattern_stages": pats}))
        db.close()
    for it in items:
        it["types_sig"] = type_sig(it["a"], it["b"])
        it["vertices"] = _nv(it["a"]) + _nv(it["b"])
        it["group"] = " | ".join(str(x) for x in (it["rule"], it["sub"], it["function"],
                                                   it["paths"], it["orientation"] or "-",
                                                   it["arm"] or "-", it["types_sig"]))
    return items


def select(items: list[dict], k: int, cap: int) -> tuple[list[dict], dict]:
    groups = defaultdict(list)
    for it in items:
        groups[it["group"]].append(it)
    for g in groups.values():
        g.sort(key=lambda x: (x["vertices"], x["item"]))
    order = sorted(groups, key=lambda g: (-len(groups[g]), g))
    reps, chosen = [], defaultdict(int)
    for rank in range(k):
        for g in order:
            if rank < len(groups[g]) and len(reps) < cap:
                reps.append(dict(groups[g][rank], rep=_h(groups[g][rank]["item"]), rank=rank))
                chosen[g] += 1
    info = {"items": len(items), "groups": len(groups), "k": k, "cap": cap,
            "representatives": len(reps),
            "per_group": {g: {"size": len(groups[g]), "representatives": chosen[g],
                              "wanted": min(k, len(groups[g])),
                              "left_out_by_cap": min(k, len(groups[g])) - chosen[g]}
                          for g in order}}
    info["left_out_by_cap"] = {g: v["left_out_by_cap"] for g, v in info["per_group"].items()
                               if v["left_out_by_cap"]}
    return reps, info


def to_pair(it: dict, a: Optional[str] = None, b: Optional[str] = None) -> Pair:
    return Pair(a=a or it["a"], b=b or it["b"], coord=it["coord"] or "float",
                kind=it["kind"] or "predicate", arm=it["arm"], seed=it["seed"],
                index=it["idx"], moves=list(it["moves"] or []), source=it["source"])


# --------------------------------------------------------------------------------------------
# oracles

def eval_pair(target: Target, pair: Pair, index_join: bool):
    from .rules import batch_join_lane, evaluate
    batch = None
    if index_join:
        bj = batch_join_lane(target, [pair])
        batch = bj["results"].get(0)
    ev = evaluate(target, pair, batch)
    if index_join:
        ev.outcomes.extend(bj["outcomes"].get(0, []))
    return ev


def same_violation(ev, it: dict) -> list[dict]:
    return [_vdict(v) for v in ev.violations
            if (v.rule, v.sub, v.function, v.orientation)
            == (it["rule"], it["sub"], it["function"], it["orientation"])]


def violation_oracle(target: Target, it: dict):
    ij = it["sub"] == "lone vs index join"

    def still_fails(p: Pair) -> bool:
        ev = eval_pair(target, p, ij)
        return any(counted(v) for v in same_violation(ev, it))
    return still_fails


def crash_probes(it: dict) -> list[dict]:
    """Lone SQL probes for a crashed function, both orientations, plain and with either
    argument wrapped by ST_ForceCollection (the R4 forms, where most E3 crashes happened)."""
    from .rules import REL_PATTERNS
    fn = it["function"]
    out = []
    for o in ("ab", "ba"):
        x, y = ("a", "b") if o == "ab" else ("b", "a")
        if fn == "ST_Relate(pattern)":
            idx = sorted({int(m) for s in it["raw"].get("pattern_stages", [])
                          for m in re.findall(r"pat(\d+)", s)}) or range(len(REL_PATTERNS))
            for i in idx:
                out.append({"o": o, "fn": fn, "wrap": 0, "pattern": REL_PATTERNS[i],
                            "sql": f"ST_Relate({x},{y},'{REL_PATTERNS[i]}')"})
            continue
        call = "ST_Relate" if fn.startswith("ST_Relate") else fn
        if not re.fullmatch(r"ST_\w+", call):
            continue
        for w, (u, v) in enumerate(((x, y), (f"ST_ForceCollection({x})", y),
                                    (x, f"ST_ForceCollection({y})"))):
            out.append({"o": o, "fn": fn, "wrap": w, "sql": f"{call}({u},{v})"})
    return out


def run_probe(target: Target, pr: dict, a: str, b: str):
    sql = (f"WITH g AS (SELECT ST_GeomFromText(%(a)s) a, ST_GeomFromText(%(b)s) b) "
           f"SELECT ({pr['sql']})::text FROM g")
    return target.run(sql, {"a": a, "b": b})


def shapely_sub(payload: dict, workdir: Path, timeout: float = 120) -> dict:
    """Run tavs.triage_shapely in a subprocess; a GEOS crash is returned as {"crashed": ...}."""
    workdir.mkdir(parents=True, exist_ok=True)
    fd, src = tempfile.mkstemp(suffix=".json", dir=workdir)
    os.close(fd)
    dst = src[:-5] + ".out.json"
    Path(src).write_text(json.dumps(payload), encoding="utf-8")
    try:
        r = subprocess.run([PY, "-s", "-m", "tavs.triage_shapely", src, dst], cwd=ROOT,
                           capture_output=True, text=True, timeout=timeout)
        if r.returncode == 0 and os.path.exists(dst):
            return json.loads(Path(dst).read_text(encoding="utf-8"))
        return {"crashed": True, "returncode": r.returncode,
                "returncode_hex": hex(r.returncode & 0xFFFFFFFF),
                "stderr": r.stderr.strip()[-300:]}
    except subprocess.TimeoutExpired:
        return {"timeout": True}
    finally:
        for p in (src, dst):
            try:
                os.remove(p)
            except OSError:
                pass


def shapely_crash_payloads(it: dict, a: str, b: str) -> list[dict]:
    from .triage_shapely import CRASH_FN
    fn = CRASH_FN.get(it["function"])
    if fn is None:
        return []
    return [{"mode": "crash", "shapely_fn": fn, "o": o, "wrap": w,
             "x": a if o == "ab" else b, "y": b if o == "ab" else a}
            for o in ("ab", "ba") for w in (0, 1, 2)]


# --------------------------------------------------------------------------------------------
# 3. shrink one representative

def shrink_rep(rep: dict, tw: Throwaways, steps: int, crash_oracle: str, tdir: Path) -> dict:
    from .shrink import shrink
    t0 = time.perf_counter()
    pair = to_pair(rep)
    try:
        from_wkt(pair.a, pair.coord == "int")
        from_wkt(pair.b, pair.coord == "int")
    except ValueError:
        pair = dataclasses.replace(pair, coord="float")
    calls = [0]
    rec = {"rep": rep["rep"], "item": rep["item"], "group": rep["group"], "steps": steps,
           "oracle": None, "original_reproduces": None}
    if rep["rule"] == "crash":
        if crash_oracle == "shapely":
            pays = shapely_crash_payloads(rep, pair.a, pair.b)
            live = [p for p in pays if shapely_sub(p, tdir / "tmp").get("crashed")]
            rec["oracle"] = {"kind": "shapely subprocess crash", "probes": live or pays}

            def still_fails(p: Pair) -> bool:
                calls[0] += 1
                for q in live:
                    x, y = (p.a, p.b) if q["o"] == "ab" else (p.b, p.a)
                    if shapely_sub(dict(q, x=x, y=y), tdir / "tmp").get("crashed"):
                        return True
                return False
        else:
            t = tw.target("current")
            probes = crash_probes(rep)
            live = [q for q in probes if run_probe(t, q, pair.a, pair.b).error == "crash"]
            rec["oracle"] = {"kind": "throwaway container: lone probe crashes the backend",
                             "image": tw.digests["current"], "probes": live or probes}

            def still_fails(p: Pair) -> bool:
                calls[0] += 1
                return any(run_probe(t, q, p.a, p.b).error == "crash" for q in live)
        rec["original_reproduces"] = bool(live)
    else:
        t = tw.target("current")
        inner = violation_oracle(t, rep)

        def still_fails(p: Pair) -> bool:
            calls[0] += 1
            return inner(p)
        rec["oracle"] = {"kind": "evaluate on throwaway current: same (rule, sub, function, "
                                 "orientation) counted", "image": tw.digests["current"]}
        rec["original_reproduces"] = still_fails(pair)
    if rec["original_reproduces"]:
        small, chain = shrink(pair, still_fails, max_steps=steps)
    else:
        small, chain = pair, []
    rec.update(shrunk_a=small.a, shrunk_b=small.b, coord=small.coord, chain=chain,
               oracle_calls=calls[0], vertices_before=rep["vertices"],
               vertices_after=_nv(small.a) + _nv(small.b),
               seconds=time.perf_counter() - t0)
    return rec


# --------------------------------------------------------------------------------------------
# 5-7. per finding

def normalize(tw: Throwaways, wkt: str) -> str:
    r = tw.target("current").run("SELECT ST_AsText(ST_Normalize(ST_GeomFromText(%s)))", (wkt,))
    if r.ok:
        return r.one()[0]
    return "UNNORMALIZED " + shapely.to_wkt(shapely.normalize(shapely.from_wkt(wkt)))


def rerun(f: dict, tw: Throwaways, tdir: Path) -> dict:
    out = {"images": {}, "versions": {}}
    pair = to_pair(f["rep_item"], f["a"], f["b"])
    pair = dataclasses.replace(pair, coord=f["coord"])
    for image in IMAGES:
        t0 = time.perf_counter()
        t = tw.target(image)
        out["versions"][image] = tw.versions.get(image)
        if f["rule"] == "crash":
            res = []
            for q in crash_probes(f["rep_item"]):
                x, y = (pair.a, pair.b) if q["o"] == "ab" else (pair.b, pair.a)
                r = run_probe(t, q, pair.a, pair.b)
                res.append({"probe": q["sql"], "o": q["o"], "error": r.error,
                            "value": r.one()[0] if r.ok else None,
                            "message": (r.message or "")[:300] if not r.ok else None})
            out["images"][image] = {"crash": any(r["error"] == "crash" for r in res),
                                    "probes": res, "seconds": time.perf_counter() - t0}
            continue
        ev = eval_pair(t, pair, f["sub"] == "lone vs index join")
        same = same_violation(ev, f)
        fixed_analog = None
        if f["rule"] == "R12f":
            fixed_analog = any(v.rule == "R12g" and v.function.startswith(f["function"])
                               for v in ev.violations)
        elif f["rule"] == "R6" and f["sub"].endswith("floating"):
            fx = f["function"].split("(")[0] + "(a,b,g)"
            fixed_analog = any(v.rule == "R6" and v.function == fx for v in ev.violations)
        out["images"][image] = {
            "present": bool(same), "present_counted": any(counted(v) for v in same),
            "violations": same[:4], "fixed_precision_analog_violated": fixed_analog,
            "outcomes": dict(Counter(o.kind for o in ev.outcomes)),
            "outcome_messages": [f"{o.stage}: {o.kind}: {o.message[:200]}" for o in ev.outcomes
                                 if o.kind not in ("skipped", "not_applicable")][:6],
            "info": {k: ev.info.get(k) for k in ("L", "M", "grid", "tiers", "types",
                                                 "precision_limited", "crashed_functions")},
            "seconds": time.perf_counter() - t0}
    # 6. Shapely (GEOS 3.14.1)
    t0 = time.perf_counter()
    if f["rule"] == "crash":
        res = [dict(p, x=None, y=None, result=shapely_sub(p, tdir / "tmp"))
               for p in shapely_crash_payloads(f["rep_item"], pair.a, pair.b)]
        out["shapely"] = {"applicable": bool(res), "crash": any(r["result"].get("crashed")
                                                                for r in res),
                          "calls": [{"fn": r["shapely_fn"], "o": r["o"], "result": r["result"]}
                                    for r in res]}
    else:
        cur = out["images"]["current"]
        pts = None
        for v in cur.get("violations", []):
            pts = pts or v["raw"].get("points")
        payload = {"mode": "check", "rule": f["rule"], "sub": f["sub"],
                   "function": f["function"], "orientation": f["orientation"],
                   "a": pair.a, "b": pair.b, "points": pts,
                   "grid": (cur.get("info") or {}).get("grid")}
        out["shapely"] = shapely_sub(payload, tdir / "tmp")
    out["shapely_seconds"] = time.perf_counter() - t0
    out["margin_check"] = margin_check(f, out)
    return out


def margin_check(f: dict, rr: dict) -> Optional[dict]:
    from .rules import r12_margin
    cur = rr["images"].get("current") or {}
    vs = cur.get("violations") or []
    info = cur.get("info") or {}
    if not vs or vs[0].get("magnitude") is None or info.get("L") is None:
        return None
    mag, raw = vs[0]["magnitude"], vs[0]["raw"]
    delta = r12_margin(info["L"], info["M"])
    if raw.get("measure") == "area":
        try:
            per = sum(shapely.from_wkt(w).boundary.length for w in (f["a"], f["b"]))
        except Exception:  # noqa: BLE001
            return None
        bound, kind = delta * per, "area"
    elif "magnitude_kind" in raw:          # distances (R7 parts, line cover)
        bound, kind = delta, "distance"
    else:
        return None
    return {"magnitude": mag, "bound": bound, "kind": kind, "within": mag <= bound,
            "note": SNAP_NOTE}


def draft_class(f: dict) -> tuple[str, list[str]]:
    rr = f["rerun"]
    im = rr["images"]
    sh = rr.get("shapely") or {}
    if f["rule"] == "crash":
        ev = [f"current crash={im['current']['crash']}", f"dev crash={im['dev']['crash']}",
              f"old crash={im['old']['crash']}", f"Shapely crash={sh.get('crash')}"]
        if not im["current"]["crash"]:
            return "not reproducible through PostGIS SQL", ev + ["no probe crashes current"]
        return "backend crash", ev
    cur, dev = im["current"], im["dev"]
    harness = {"harness_exception", "other_error", "sql_error"}
    sh_v = None if sh.get("crashed") or sh.get("error") or not sh.get("applicable") \
        else sh.get("violated")
    ev = [f"current present_counted={cur['present_counted']}",
          f"dev present_counted={dev['present_counted']}",
          f"old present_counted={im['old']['present_counted']}",
          f"Shapely applicable={sh.get('applicable')} violated={sh.get('violated')}"
          + (" CRASHED" if sh.get("crashed") else "") + (f" error={sh['error']}"
                                                          if sh.get("error") else "")]
    fx = (sh.get("fixed") or {}).get("violated")
    pg_fx = cur.get("fixed_precision_analog_violated")
    mc = rr.get("margin_check")
    prec = []
    if pg_fx is False:
        prec.append("PostGIS fixed-precision analog clean")
    if sh_v and fx is False:
        prec.append("Shapely fixed-precision (grid g) clean")
    if mc and mc["within"]:
        prec.append(f"magnitude {mc['magnitude']:.3g} within {mc['kind']} snap bound "
                    f"{mc['bound']:.3g}")
    if prec:
        ev.append("precision evidence: " + ", ".join(prec))
    if not f["original_reproduces"]:
        ev.append("original pair did not reproduce on the throwaway current")
    if not cur["present_counted"]:
        if any(k in harness for k in cur["outcomes"]):
            return "harness or generator error", ev + [f"current outcomes {cur['outcomes']}"]
        if sh_v:
            return "not reproducible through PostGIS SQL", ev
        return "harness or generator error", ev + ["not reproduced on current, nor in Shapely"]
    if not dev["present_counted"]:
        if any(k in harness or k == "crash" for k in dev["outcomes"]):
            ev.append(f"dev outcomes {dev['outcomes']} (dev run incomplete)")
        else:
            return "already fixed upstream", ev
    if sh_v is False:
        return "path inconsistency", ev
    if prec:
        return "precision effect", ev
    return "present in dev (new candidate)", ev


# --------------------------------------------------------------------------------------------
# outputs

def _short(s: str, n: int = 160) -> str:
    return s if len(s) <= n else s[:n - 3] + "..."


def write_outputs(tdir: Path, findings: list[dict], sel: dict, meta: dict) -> None:
    _write_json(tdir / "findings.json", {"meta": meta, "selection": sel, "findings": findings})
    with open(tdir / "findings.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["key", "rule", "sub", "function", "arms", "seeds", "raw_violations",
                    "raw_violations_shared", "shrunk_a", "shrunk_b", "current", "dev", "old",
                    "shapely", "draft_class", "class_status"])
        for f in findings:
            im = f["rerun"]["images"]
            sh = f["rerun"].get("shapely") or {}
            if f["rule"] == "crash":
                rep = [str(im[i]["crash"]) for i in IMAGES]
                shs = "crash" if sh.get("crash") else ("n/a" if not sh.get("applicable")
                                                       else "no crash")
            else:
                rep = [str(im[i]["present_counted"]) for i in IMAGES]
                shs = ("crash" if sh.get("crashed") else "n/a" if not sh.get("applicable")
                       else f"violated={sh.get('violated')}")
            w.writerow([f["key_id"], f["rule"], f["sub"], f["function"], ";".join(f["arms"]),
                        ";".join(map(str, f["seeds"])), f["raw_count"], f["raw_shared"],
                        _short(f["a"]), _short(f["b"]), *rep, shs, f["draft_class"], "draft"])
    L = [f"E4 triage of {meta['campaign_dir']}  ({meta['finished']})",
         f"selected items {sel['items']} in {sel['groups']} groups; representatives "
         f"{sel['representatives']} (K={sel['k']}, cap={sel['cap']})",
         f"left out by the cap: {sum(sel['left_out_by_cap'].values())} representatives in "
         f"{len(sel['left_out_by_cap'])} groups"]
    L += [f"  {g}: {n}" for g, n in sel["left_out_by_cap"].items()]
    L += [f"shrinks: {meta['shrinks']}  (reproduced originally: {meta['reproduced']})",
          f"unique findings: {len(findings)}", "", "Draft classes (lead decides):"]
    for c, n in Counter(f["draft_class"] for f in findings).most_common():
        L.append(f"  {c}: {n}")
    L += ["", "Findings:"]
    for f in findings:
        L.append(f"- [{f['key_id']}] {f['rule']} {f['sub']} / {f['function']} "
                 f"({f['types_sig']}), raw {f['raw_count']} (+{f['raw_shared']} shared), "
                 f"arms {','.join(f['arms'])}: draft '{f['draft_class']}'")
        L.append(f"    A = {_short(f['a'], 200)}")
        L.append(f"    B = {_short(f['b'], 200)}")
        L.append(f"    evidence: {'; '.join(f['evidence'])}")
        L.append(f"    seconds: shrink {f['seconds']['shrink']:.1f}, rerun "
                 f"{f['seconds']['rerun']:.1f}")
    L += ["", "Containers:"] + [f"  {x}" for x in meta["containers"]]
    (tdir / "summary.txt").write_text("\n".join(L) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--campaign")
    g.add_argument("--campaign-dir")
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--cap", type=int, default=300)
    ap.add_argument("--steps", type=int, default=200)
    ap.add_argument("--crash-oracle", choices=["container", "shapely"], default="container")
    ap.add_argument("--rules", help="comma list to restrict (e.g. R3,R12f,crash); testing only")
    ap.add_argument("--select-only", action="store_true")
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    cdir = Path(args.campaign_dir) if args.campaign_dir else ROOT / "runs" / args.campaign
    if not any(cdir.glob("lane*.sqlite")):
        raise SystemExit(f"no lane*.sqlite in {cdir}")
    tdir = cdir / "triage"
    for d in (tdir, tdir / "shrinks", tdir / "reruns"):
        d.mkdir(parents=True, exist_ok=True)
    rules = set(args.rules.split(",")) if args.rules else None
    items = load_items(cdir, rules)
    reps, sel = select(items, args.k, args.cap)
    _write_json(tdir / "selection.json", {"selection": sel, "representatives": [
        {k: r[k] for k in ("rep", "item", "group", "rank", "vertices")} for r in reps]})
    print(f"{len(items)} items, {sel['groups']} groups, {len(reps)} representatives", flush=True)
    if args.select_only:
        return 0

    tw = Throwaways()
    t_start = time.perf_counter()
    try:
        recs = {}
        for i, rep in enumerate(reps):
            path = tdir / "shrinks" / f"{rep['rep']}.json"
            if path.exists():
                recs[rep["rep"]] = json.loads(path.read_text(encoding="utf-8"))
                continue
            rec = shrink_rep(rep, tw, args.steps, args.crash_oracle, tdir)
            _write_json(path, rec)
            recs[rep["rep"]] = rec
            print(f"[{i + 1}/{len(reps)}] {rep['group']}: reproduces={rec['original_reproduces']}"
                  f" {rec['vertices_before']}->{rec['vertices_after']} vertices, "
                  f"{len(rec['chain'])} steps, {rec['oracle_calls']} calls, "
                  f"{rec['seconds']:.1f} s", flush=True)

        # 4. dedup
        by_key: dict = {}
        rep_finding = {}
        for rep in reps:
            rec = recs[rep["rep"]]
            na, nb = normalize(tw, rec["shrunk_a"]), normalize(tw, rec["shrunk_b"])
            sig = type_sig(rec["shrunk_a"], rec["shrunk_b"])
            key = [rep["rule"], rep["function"], rep["paths"], sig, na, nb]
            kid = _h(json.dumps(key))
            rep_finding[rep["rep"]] = kid
            f = by_key.setdefault(kid, {
                "key_id": kid, "key": {"rule": rep["rule"], "function": rep["function"],
                                       "paths": rep["paths"], "types_sig": sig,
                                       "a_normalized": na, "b_normalized": nb},
                "rule": rep["rule"], "sub": rep["sub"], "function": rep["function"],
                "paths": rep["paths"], "orientation": rep["orientation"], "types_sig": sig,
                "a": rec["shrunk_a"], "b": rec["shrunk_b"], "coord": rec["coord"],
                "rep_item": rep, "original_reproduces": rec["original_reproduces"],
                "representatives": [], "shrink_seconds": []})
            f["representatives"].append({"rep": rep["rep"], "item": rep["item"],
                                         "group": rep["group"], "chain": rec["chain"],
                                         "oracle": rec["oracle"],
                                         "original_a": rep["a"], "original_b": rep["b"],
                                         "vertices": [rec["vertices_before"],
                                                      rec["vertices_after"]],
                                         "oracle_calls": rec["oracle_calls"]})
            f["shrink_seconds"].append(rec["seconds"])
            f["original_reproduces"] = f["original_reproduces"] or rec["original_reproduces"]

        # raw coverage: a group whose representatives all map to one finding is covered by it
        groups = defaultdict(list)
        for it in items:
            groups[it["group"]].append(it)
        g_find = defaultdict(set)
        for rep in reps:
            g_find[rep["group"]].add(rep_finding[rep["rep"]])
        for f in by_key.values():
            f.update(raw_count=0, raw_shared=0, arms=set(), seeds=set(), groups=[])
        for gname, members in groups.items():
            fs = g_find.get(gname, set())
            for kid in fs:
                f = by_key[kid]
                f["groups"].append(gname)
                f["arms"] |= {str(m["arm"]) for m in members}
                f["seeds"] |= {m["seed"] for m in members}
                if len(fs) == 1:
                    f["raw_count"] += len(members)
                else:
                    f["raw_shared"] += len(members)

        # 5-7
        findings = []
        for kid, f in by_key.items():
            path = tdir / "reruns" / f"{kid}.json"
            if path.exists():
                rr = json.loads(path.read_text(encoding="utf-8"))
            else:
                rr = rerun(f, tw, tdir)
                _write_json(path, rr)
            f["rerun"] = rr
            f["draft_class"], f["evidence"] = draft_class(f)
            f["class_status"] = "draft"
            f["known_open_issue"] = None
            f["seconds"] = {"shrink": sum(f["shrink_seconds"]),
                            "rerun": sum(v.get("seconds", 0) for v in rr["images"].values())
                            + rr.get("shapely_seconds", 0)}
            f["arms"], f["seeds"] = sorted(f["arms"]), sorted(f["seeds"], key=str)
            f["rep_item"] = {k: f["rep_item"][k] for k in ("item", "lane", "pair_id", "seed",
                                                           "kind", "idx", "arm", "coord",
                                                           "moves", "source", "raw")}
            findings.append(f)
            print(f"finding {kid}: {f['rule']} {f['function']} -> {f['draft_class']}",
                  flush=True)
        findings.sort(key=lambda f: (f["rule"], f["function"], f["key_id"]))
        meta = {"campaign_dir": str(cdir), "finished": time.strftime("%Y-%m-%d %H:%M:%S"),
                "args": vars(args), "shrinks": len(recs),
                "reproduced": sum(bool(r["original_reproduces"]) for r in recs.values()),
                "wall_s_this_run": time.perf_counter() - t_start,
                "versions": tw.versions, "digests": tw.digests,
                "shapely": shapely.__version__, "geos": shapely.geos_version_string}
    finally:
        tw.close()
    meta["containers"] = tw.log
    write_outputs(tdir, findings, sel, meta)
    print((tdir / "summary.txt").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
