"""E2 pilot and E3 campaign runner (experiment-plan.md, "Experiments" and the crash paragraph).

How to run (from the experiment folder, with the repo's Python):

  E2 pilot (seed 100, plain-int only, 500 pairs per kind, one lane):
    .venv/Scripts/python.exe -s -m tavs.campaign run --campaign e2 --seeds 100 \
        --kinds predicate overlay --n 500 --arms plain-int --lanes 1
  E3 (seeds 101-110, four arms, both kinds; set N from the pilot's throughput):
    .venv/Scripts/python.exe -s -m tavs.campaign run --campaign e3 --seeds 101-110 \
        --kinds predicate overlay --n <N> --lanes 4
  Analysis afterwards:  .venv/Scripts/python.exe -s -m tavs.analysis --campaign e3
  Remove lane containers and volumes (also done at the end of a finished run unless
  --keep-lanes):  .venv/Scripts/python.exe -s -m tavs.campaign down

Layout: runs/<campaign>/campaign.json (the definition, fixed at first start; a restart with
different flags is refused), lane<i>.sqlite (store.py schema plus tables `campaign_pairs` and
`batches`), lane<i>.out (worker stdout/stderr), progress.log (one line per lane every 200 pairs
or 60 s).

Lanes: one PostgreSQL container per lane from compose.lanes.yaml (project `tavs-lanes`, port
54340+i, same image digest as `current`, fsync off). Seeds are assigned to lanes whole and
round-robin (lane i gets seeds[i::lanes]), so the four arms of one (seed, kind, index) always run
in the same lane. A lane processes its seeds in order, each kind, in chunks of --chunk indices.
Per chunk: `evaluate` each pair (function-level crash skipping inside), then one
`batch_join_lane` over the chunk's pairs with their crash lists (R3 (d); a crashing join is
split in halves), then `apply_batch` per pair. The plan's "per-seed" join is therefore run per
chunk of one seed and kind; pairs never mix seeds in a batch.

Resume: a chunk's pairs are stored with their violations and outcomes and committed in one
transaction after the chunk's join; (seed, kind, idx, arm) is UNIQUE in `campaign_pairs`. A
restart regenerates the same pairs (generation depends only on (seed, kind, index)) and skips
stored ones; a killed chunk is redone. A lane lock file holding the worker's PID refuses a
second live worker on the same lane.

Crash cost: crash events are evaluate's outcomes of kind "crash" (each is one backend crash;
`campaign_pairs.crash_events`) plus the index join's crashes (`batches.crashed`, including the
halving steps). Recovery seconds: evaluate's are parsed from db.py's message "server accepting
again after X s"; for a chunk whose join crashed, the join's whole wall time is counted (an
upper bound).
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import traceback
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"
LANES_COMPOSE = ROOT / "compose.lanes.yaml"
LANES_PROJECT = "tavs-lanes"
BASE_PORT = 54340
MAX_LANES = 8                    # services defined in compose.lanes.yaml
LANE_CONTAINER_MB = 300          # assumed per lane container
LANE_PYTHON_MB = 200             # assumed per lane worker process (Shapely, NumPy, psycopg)
HOST_RESERVE_MB = 1024           # left free for the host
PROGRESS_PAIRS = 200
PROGRESS_SECONDS = 60
ARMS_ALL = ["plain-int", "plain-float", "degen-int", "degen-float"]
KINDS_ALL = ["predicate", "overlay"]
_WAIT_RE = re.compile(r"server accepting again after ([0-9.]+) s")

EXTRA_SCHEMA = """
CREATE TABLE IF NOT EXISTS campaign_pairs (
  pair_id INTEGER PRIMARY KEY REFERENCES pairs, seed INTEGER, kind TEXT, idx INTEGER, arm TEXT,
  form TEXT, regime TEXT, tier_predicate TEXT, tier_overlay TEXT, wall_s REAL,
  crash_events INTEGER, crash_wait_s REAL, harness_exception INTEGER,
  UNIQUE (seed, kind, idx, arm));
CREATE TABLE IF NOT EXISTS batches (
  batch_id INTEGER PRIMARY KEY, run_id INTEGER, seed INTEGER, kind TEXT, idx_from INTEGER,
  idx_to INTEGER, n_pairs INTEGER, seconds REAL, crashed INTEGER, errors TEXT,
  failed_rows TEXT, gen_seconds REAL);
CREATE TABLE IF NOT EXISTS gen_errors (
  seed INTEGER, kind TEXT, idx INTEGER, message TEXT);
CREATE TABLE IF NOT EXISTS gen_stats (
  run_id INTEGER, seed INTEGER, stats TEXT);
"""


# --------------------------------------------------------------------------------------------
# helpers

def parse_seeds(spec: str) -> list[int]:
    """'100' | '101-110' | '101,103,105-107'."""
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = (int(x) for x in part.split("-", 1))
            out += list(range(lo, hi + 1))
        elif part:
            out.append(int(part))
    if len(set(out)) != len(out):
        raise SystemExit(f"duplicate seeds in {spec!r}")
    return out


def assign(seeds: list[int], lanes: int) -> list[list[int]]:
    return [seeds[i::lanes] for i in range(lanes)]


def available_mb() -> tuple[float, float]:
    """(available, total) physical memory of the host in MB."""
    if os.name != "nt":
        page, total = os.sysconf("SC_PAGE_SIZE"), os.sysconf("SC_PHYS_PAGES")
        try:
            avail = os.sysconf("SC_AVPHYS_PAGES")      # Linux; macOS has no such name
        except (ValueError, OSError):
            avail = total // 2                          # unknown: assume half is free
        return avail * page / 2**20, total * page / 2**20
    class MS(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    m = MS()
    m.dwLength = ctypes.sizeof(MS)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
        raise OSError("GlobalMemoryStatusEx failed")
    return m.ullAvailPhys / 2**20, m.ullTotalPhys / 2**20


def pid_alive(pid: int) -> bool:
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x1000, False, pid)        # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    code = ctypes.c_ulong()
    ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
    k32.CloseHandle(h)
    return bool(ok) and code.value == 259          # STILL_ACTIVE


def compose(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    cmd = ["docker", "compose", "-p", LANES_PROJECT, "-f", str(LANES_COMPOSE), *args]
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=check)


def running_lanes() -> set[int]:
    r = subprocess.run(["docker", "ps", "--filter", f"label=com.docker.compose.project="
                        f"{LANES_PROJECT}", "--format",
                        "{{.Label \"com.docker.compose.service\"}}"],
                       capture_output=True, text=True, check=True)
    return {int(s[4:]) for s in r.stdout.split() if s.startswith("lane")}


def check_digest() -> str:
    """The lane image digest must equal service `current` in compose.yaml."""
    cur = re.search(r"^\s*current:.*?\n\s*<<: \*db\s*\n\s*image:\s*(\S+)",
                    (ROOT / "compose.yaml").read_text(encoding="utf-8"), re.M)
    lane = re.search(r"^\s*image:\s*(\S+)", LANES_COMPOSE.read_text(encoding="utf-8"), re.M)
    if not cur or not lane or cur.group(1) != lane.group(1):
        raise SystemExit(f"lane image {lane and lane.group(1)} differs from current "
                         f"{cur and cur.group(1)}")
    return lane.group(1)


def log_line(path: Path, text: str) -> None:
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(text + "\n")


# --------------------------------------------------------------------------------------------
# worker (one lane, one process)

def open_store(path: Path):
    from .store import Store
    store = Store(path)
    store.db.execute("PRAGMA journal_mode=WAL")
    store.db.execute("PRAGMA synchronous=NORMAL")
    store.db.executescript(EXTRA_SCHEMA)
    return store


def run_lane(cdir: Path, lane: int, seeds: list[int], kinds: list[str], n: int,
             arms: list[str], chunk: int) -> int:
    from . import gen
    from .db import Target
    from .rules import (Evaluation, Outcome, apply_batch, batch_join_lane, crash_list,
                        evaluate, tier)

    lock = cdir / f"lane{lane}.lock"
    if lock.exists():
        try:
            old = int(lock.read_text().strip())
        except ValueError:
            old = -1
        if old > 0 and old != os.getpid() and pid_alive(old):
            print(f"lane {lane}: worker PID {old} is still running; refusing", flush=True)
            return 3
    lock.write_text(str(os.getpid()))
    progress = cdir / "progress.log"
    store = open_store(cdir / f"lane{lane}.sqlite")
    db = store.db
    done = {tuple(r) for r in db.execute("SELECT seed, kind, idx, arm FROM campaign_pairs")}
    planned = {(s, k, i, a) for s in seeds for k in kinds for i in range(n) for a in arms}
    if done - planned:
        print(f"lane {lane}: {len(done - planned)} stored pairs are outside this definition",
              flush=True)
    total = len(planned)
    n_done = len(done & planned)
    # running totals, including earlier sessions
    crashes, crash_s, strict = db.execute(
        "SELECT COALESCE(SUM(crash_events),0), COALESCE(SUM(crash_wait_s),0), "
        "(SELECT COUNT(*) FROM violations WHERE tier='strict') FROM campaign_pairs").fetchone()
    bc, bs = db.execute("SELECT COALESCE(SUM(crashed),0), COALESCE(SUM(CASE WHEN crashed "
                        "THEN seconds ELSE 0 END),0) FROM batches").fetchone()
    crashes, crash_s = crashes + bc, crash_s + bs
    strict_pairs = db.execute("SELECT COUNT(DISTINCT pair_id) FROM violations WHERE "
                              "tier='strict'").fetchone()[0]

    target = Target(f"lane{lane}", port=BASE_PORT + lane)
    run_id = store.start_run("campaign:" + cdir.name, f"lane{lane}", target.version(),
                             {"lane": lane, "port": BASE_PORT + lane, "seeds": seeds,
                              "kinds": kinds, "n": n, "arms": arms, "chunk": chunk,
                              "already_done": n_done})
    t_start = time.perf_counter()
    session_pairs = 0
    last_log = (t_start, n_done)

    def report(final=False):
        nonlocal last_log
        el = time.perf_counter() - t_start
        rate = 3600 * session_pairs / el if el > 0 else 0.0
        log_line(progress, f"{time.strftime('%Y-%m-%d %H:%M:%S')} lane{lane}"
                           f"{' FINAL' if final else ''} done={n_done} remaining={total - n_done}"
                           f" pairs_per_h={rate:.0f} crashes={crashes} crash_s={crash_s:.1f}"
                           f" strict_violations={strict} strict_pairs={strict_pairs}")
        print(f"progress done={n_done} remaining={total - n_done} crashes={crashes}", flush=True)
        last_log = (time.perf_counter(), n_done)

    report()
    try:
        for seed in seeds:
            for kind in kinds:
                for start in range(0, n, chunk):
                    idxs = range(start, min(n, start + chunk))
                    todo_idx = [i for i in idxs
                                if any((seed, kind, i, a) not in done for a in arms)]
                    if not todo_idx:
                        continue
                    g0 = time.perf_counter()
                    pairs = []
                    for i in todo_idx:
                        try:
                            built = gen.build(seed, kind, i)
                        except Exception:  # noqa: BLE001 - recorded, the run continues
                            db.execute("INSERT INTO gen_errors VALUES (?,?,?,?)",
                                       (seed, kind, i, traceback.format_exc()[-2000:]))
                            db.commit()
                            continue
                        pairs += [built[a] for a in arms if (seed, kind, i, a) not in done]
                    gen_s = time.perf_counter() - g0
                    if not pairs:
                        continue
                    # 1. evaluate every pair (function-level crash lists build up per pair)
                    evs, walls, hxs = [], [], []
                    for p in pairs:
                        t0 = time.perf_counter()
                        hx = 0
                        try:
                            ev = evaluate(target, p)
                        except Exception:  # noqa: BLE001 - a harness error, kept as an outcome
                            ev = Evaluation(pair=p, target=target.name)
                            ev.outcomes.append(Outcome("harness", "harness_exception",
                                                       traceback.format_exc()[-2000:]))
                            hx = 1
                        evs.append(ev)
                        walls.append(time.perf_counter() - t0)
                        hxs.append(hx)
                        if time.perf_counter() - last_log[0] >= PROGRESS_SECONDS:
                            report()
                    # 2. R3 (d): one index join over the chunk, excluding crashed functions
                    plan_file = cdir / f"lane{lane}_batch_plan.json"
                    bj = batch_join_lane(target, pairs, [crash_list(ev) for ev in evs],
                                         explain=not plan_file.exists())
                    if bj["plan"] is not None and not plan_file.exists():
                        plan_file.write_text(json.dumps(dict(
                            target=target.name, index_used=bj["index_used"], **bj["plan"]),
                            indent=2, default=str), encoding="utf-8")
                        print(f"lane {lane}: index join plan checked, index used = "
                              f"{bj['index_used']}", flush=True)
                    bout = [o for j in bj["outcomes"] for o in bj["outcomes"][j]]
                    # 3. store the chunk in one transaction
                    db.execute("INSERT INTO batches (run_id, seed, kind, idx_from, idx_to, "
                               "n_pairs, seconds, crashed, errors, failed_rows, gen_seconds) "
                               "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                               (run_id, seed, kind, todo_idx[0], todo_idx[-1], len(pairs),
                                bj["seconds"], bj["crashes"],
                                json.dumps(Counter(f"{o.stage}:{o.kind}" for o in bout)),
                                "[]", gen_s))
                    chunk_crashes, chunk_crash_s = bj["crashes"], (
                        bj["seconds"] if bj["crashes"] else 0.0)
                    chunk_strict = chunk_strict_pairs = stored = 0
                    for j, (p, ev) in enumerate(zip(pairs, evs)):
                        apply_batch(ev, bj["results"].get(j), bj["outcomes"].get(j))
                        ev.seconds["batch_lane_share"] = bj["seconds"] / len(pairs)
                        # crash events of evaluate's own statements (batch crashes are
                        # counted per batch, in `batches.crashed`)
                        ce = [o for o in ev.outcomes
                              if o.kind == "crash" and not o.stage.startswith("batch")]
                        cw = sum(float(m.group(1)) for o in ce
                                 for m in [_WAIT_RE.search(o.message or "")] if m)
                        src = gen.parse_source(p.source or "form=?")
                        try:
                            tp, to = tier(p, "predicate"), tier(p, "overlay")
                        except Exception:  # noqa: BLE001
                            tp = to = "error"
                        db.execute("SAVEPOINT pair")
                        try:
                            pid = store.add(run_id, ev, commit=False)
                            db.execute(
                                "INSERT INTO campaign_pairs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                (pid, seed, kind, p.index, p.arm, src.get("form"),
                                 src.get("regime", "none"), tp, to, walls[j], len(ce), cw,
                                 hxs[j]))
                            db.execute("RELEASE pair")
                        except sqlite3.IntegrityError:
                            db.execute("ROLLBACK TO pair")
                            db.execute("RELEASE pair")
                            print(f"lane {lane}: duplicate {(seed, kind, p.index, p.arm)} "
                                  "not stored", flush=True)
                            continue
                        stored += 1
                        done.add((seed, kind, p.index, p.arm))
                        chunk_crashes += len(ce)
                        chunk_crash_s += cw
                        sv = [v for v in ev.violations if v.tier == "strict"]
                        chunk_strict += len(sv)
                        chunk_strict_pairs += bool(sv)
                    db.commit()
                    n_done += stored
                    session_pairs += stored
                    crashes += chunk_crashes
                    crash_s += chunk_crash_s
                    strict += chunk_strict
                    strict_pairs += chunk_strict_pairs
                    if (n_done - last_log[1] >= PROGRESS_PAIRS
                            or time.perf_counter() - last_log[0] >= PROGRESS_SECONDS):
                        report()
            db.execute("INSERT INTO gen_stats VALUES (?,?,?)",
                       (run_id, seed, json.dumps(gen.resample_stats(), default=str)))
            db.commit()
        report(final=True)
    finally:
        store.finish_run(run_id)
        store.close()
        target.close()
        try:
            if lock.read_text().strip() == str(os.getpid()):
                lock.unlink()
        except OSError:
            pass
    return 0


# --------------------------------------------------------------------------------------------
# orchestrator

def definition(args) -> dict:
    seeds = parse_seeds(args.seeds)
    lanes = min(args.lanes, len(seeds))
    return {"campaign": args.campaign, "seeds": seeds, "kinds": args.kinds, "n": args.n,
            "arms": args.arms, "lanes": lanes, "chunk": args.chunk,
            "assignment": assign(seeds, lanes)}


def wait_lane(lane: int, limit_s: float = 180) -> str:
    from .db import Target
    t = Target(f"lane{lane}", port=BASE_PORT + lane)
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < limit_s:
        r = t.run("SELECT postgis_full_version()")
        if r.ok:
            t.close()
            return r.one()[0]
        time.sleep(2)
    t.close()
    raise SystemExit(f"lane {lane} not ready after {limit_s:.0f} s")


def cmd_run(args) -> int:
    d = definition(args)
    cdir = RUNS / args.campaign
    cdir.mkdir(parents=True, exist_ok=True)
    cfile = cdir / "campaign.json"
    if cfile.exists():
        old = json.loads(cfile.read_text(encoding="utf-8"))
        old_cmp = {k: v for k, v in old.items() if k not in ("created", "digest")}
        if old_cmp != d:
            raise SystemExit(f"{cfile} holds a different definition; refusing.\n"
                             f"stored:    {json.dumps(old_cmp)}\nrequested: {json.dumps(d)}")
        print(f"resuming campaign {args.campaign}")
    digest = check_digest()
    lanes = d["lanes"]
    if lanes > MAX_LANES:
        raise SystemExit(f"at most {MAX_LANES} lanes (compose.lanes.yaml)")

    up = running_lanes()
    new = [i for i in range(lanes) if i not in up]
    avail, total = available_mb()
    per_lane = LANE_CONTAINER_MB + LANE_PYTHON_MB
    need = len(new) * LANE_CONTAINER_MB + lanes * LANE_PYTHON_MB + HOST_RESERVE_MB
    fit = max(0, int((avail - HOST_RESERVE_MB) // per_lane))
    print(f"memory: host available {avail:.0f} MB of {total:.0f} MB; lanes requested {lanes} "
          f"({len(new)} containers to start, {len(up & set(range(lanes)))} already up); "
          f"need about {need:.0f} MB ({LANE_CONTAINER_MB} MB per new container + "
          f"{LANE_PYTHON_MB} MB per worker + {HOST_RESERVE_MB} MB reserve); "
          f"about {fit} lanes fit", flush=True)
    if need > avail:
        raise SystemExit(f"refusing: about {need:.0f} MB needed, {avail:.0f} MB available. "
                         f"Use --lanes {max(1, fit)} or free memory.")
    if not cfile.exists():
        cfile.write_text(json.dumps(dict(d, created=time.strftime("%Y-%m-%d %H:%M:%S"),
                                         digest=digest), indent=2), encoding="utf-8")

    if new:
        r = compose("up", "-d", *[f"lane{i}" for i in new], check=False)
        if r.returncode:
            raise SystemExit(f"docker compose up failed:\n{r.stderr}")
    for i in range(lanes):
        v = wait_lane(i)
        print(f"lane {i} ready on port {BASE_PORT + i}: {v[:60]}...", flush=True)

    log_line(cdir / "progress.log", f"{time.strftime('%Y-%m-%d %H:%M:%S')} start "
             f"lanes={lanes} assignment={d['assignment']} n={d['n']} kinds={d['kinds']} "
             f"arms={d['arms']}")
    procs = []
    for i, seeds in enumerate(d["assignment"]):
        out = open(cdir / f"lane{i}.out", "a", encoding="utf-8")
        cmd = [sys.executable, "-s", "-m", "tavs.campaign", "worker", "--campaign",
               args.campaign, "--lane", str(i), "--lane-seeds", ",".join(map(str, seeds)),
               "--kinds", *d["kinds"], "--n", str(d["n"]), "--arms", *d["arms"],
               "--chunk", str(d["chunk"])]
        procs.append((subprocess.Popen(cmd, cwd=ROOT, stdout=out, stderr=subprocess.STDOUT),
                      out))
        print(f"lane {i}: seeds {seeds}, worker PID {procs[-1][0].pid}", flush=True)
    codes = []
    try:
        for p, out in procs:
            codes.append(p.wait())
            out.close()
    except KeyboardInterrupt:
        for p, _ in procs:
            p.terminate()
        raise
    print(f"workers finished with exit codes {codes}", flush=True)
    print((cdir / "progress.log").read_text(encoding="utf-8").splitlines()[-1])
    if all(c == 0 for c in codes) and not args.keep_lanes:
        cmd_down(args)
    return 0 if all(c == 0 for c in codes) else 1


def cmd_down(_args) -> int:
    r = compose("down", "-v", check=False)
    print(r.stderr.strip() or r.stdout.strip() or "lanes removed")
    return r.returncode


def cmd_worker(args) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    cdir = RUNS / args.campaign
    return run_lane(cdir, args.lane, parse_seeds(args.lane_seeds), args.kinds, args.n,
                    args.arms, args.chunk)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="start or resume a campaign")
    r.add_argument("--campaign", required=True)
    r.add_argument("--seeds", required=True, help="e.g. 100 or 101-110")
    r.add_argument("--kinds", nargs="+", default=KINDS_ALL, choices=KINDS_ALL)
    r.add_argument("--n", type=int, required=True, help="indices per (seed, kind)")
    r.add_argument("--arms", nargs="+", default=ARMS_ALL, choices=ARMS_ALL)
    r.add_argument("--lanes", type=int, default=4)
    r.add_argument("--chunk", type=int, default=25,
                   help="indices per batch index join and per commit (default 25)")
    r.add_argument("--keep-lanes", action="store_true",
                   help="leave the lane containers up after a finished run")
    w = sub.add_parser("worker", help="internal: one lane")
    w.add_argument("--campaign", required=True)
    w.add_argument("--lane", type=int, required=True)
    w.add_argument("--lane-seeds", required=True)
    w.add_argument("--kinds", nargs="+", required=True)
    w.add_argument("--n", type=int, required=True)
    w.add_argument("--arms", nargs="+", required=True)
    w.add_argument("--chunk", type=int, required=True)
    sub.add_parser("down", help="remove the lane containers and their volumes")
    args = ap.parse_args(argv)
    if args.cmd == "run":
        args.arms = [a for a in ARMS_ALL if a in args.arms]
        args.kinds = [k for k in KINDS_ALL if k in args.kinds]
    return {"run": cmd_run, "worker": cmd_worker, "down": cmd_down}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
