"""E5: replay the family A crash findings on GEOS built just before and at the fix (GEOS PR #1590).

  .venv/Scripts/python.exe -s -m tavs.replay_fix                  (full replay -> runs/e5-geos-fix/)
  options: --target LABEL=IMAGE   repeatable; replaces the three default targets
           --limit N              only the first N family A findings (sorted by key)
           --keys K1,K2           only these finding keys
           --out DIR              output folder (default runs/e5-geos-fix)

Default targets, in this order:
  before  tavs-geos:before-fc3eca90   pinned dev image, GEOS rebuilt at fc3eca90 (parent of the fix)
  fix     tavs-geos:fix-2c8e04fa      pinned dev image, GEOS rebuilt at 2c8e04fa (merge of #1590)
  dev     the pinned dev image itself (compose.yaml `dev`, GEOS 283e8272), as anchor
The two rebuilt images come from docker/geos-rebuild/Dockerfile (scripts/run_e5_geos_fix.ps1).

Family A is read from runs/e3/triage/families.csv (family == "A"); the full shrunk inputs and the
triage's own rerun come from runs/e3/triage/findings.json. The crash check is the triage's
(`triage.rerun` for crash findings): every lone probe of `triage.crash_probes(rep_item)` is sent
with `triage.run_probe` on the shrunk pair, and the finding crashes on a target when any probe's
error is "crash" (`db.classify_error`). Non-crashing probes keep their returned value.
The SQL reproducer findings/A-relateng-crash-empty-polygon/reproduce.sql is also run, one
statement at a time.

One throwaway container per target (label tavs.e5=1, name tavs-e5-<label>-<pid>), started from
the image, used for that target only and removed afterwards. Before and after the findings, each
container is checked: the backend's /proc/<pid>/maps after PostGIS is loaded, `ldd` on the PostGIS
library, SHA-256 of the GEOS libraries PostGIS resolves to and of the ones the backend mapped,
compared with the checksums recorded at build time (/_tavs_geos_build.txt), and the GEOS commit
marker /_tavs_geos_commit.txt against the expected commit. A target that fails the check before
the findings is not replayed. Existing images and containers are never modified.

Outputs: results.csv (one row per finding and target), reproducer.csv, details.json (every
probe, every check) and summary.md. Exit code 0 when every target verified and ran, 3 when a
verification failed, 1 on an exception.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import re
import socket
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Optional

from .db import Target
from .triage import ROOT, crash_probes, run_probe

DEV_IMAGE = ("postgis/postgis@sha256:"
             "620f1f1ffb479ffbda686dbfde113557a9859cdf9de0f86683b0702846915107")
BEFORE_COMMIT = "fc3eca9063096a665700651d6523f56de4dae415"
FIX_COMMIT = "2c8e04faf8235456b417979bcf23271ef34148a7"
DEFAULT_TARGETS = [
    ("before", "tavs-geos:before-fc3eca90", BEFORE_COMMIT),
    ("fix", "tavs-geos:fix-2c8e04fa", FIX_COMMIT),
    ("dev", DEV_IMAGE, None),
]
TRIAGE = ROOT / "runs" / "e3" / "triage"
REPRO_SQL = ROOT / "findings" / "A-relateng-crash-empty-polygon" / "reproduce.sql"
READY_S = 240


def now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S %z")


def sh(cmd: list[str], timeout: float = 120) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)


# --------------------------------------------------------------------------------------------
# inputs

def family_a(limit: Optional[int], keys: Optional[set]) -> list[dict]:
    with open(TRIAGE / "families.csv", encoding="utf-8", newline="") as fh:
        fam = {r["key"]: r["family"] for r in csv.DictReader(fh)}
    data = json.loads((TRIAGE / "findings.json").read_text(encoding="utf-8"))
    fs = sorted((f for f in data["findings"] if fam.get(f["key_id"]) == "A"),
                key=lambda f: f["key_id"])
    if keys:
        missing = keys - {f["key_id"] for f in fs}
        if missing:
            raise SystemExit(f"not family A findings: {sorted(missing)}")
        fs = [f for f in fs if f["key_id"] in keys]
    if limit is not None:
        fs = fs[:limit]
    return fs


def repro_statements() -> list[str]:
    text = "\n".join(line for line in REPRO_SQL.read_text(encoding="utf-8").splitlines()
                     if not line.lstrip().startswith("--"))
    return [s.strip() for s in text.split(";") if s.strip()]


# --------------------------------------------------------------------------------------------
# throwaway container for one target

class Throwaway:
    def __init__(self, label: str, image: str):
        self.label, self.image = label, image
        self.name = f"tavs-e5-{label}-{os.getpid()}"
        self.port: Optional[int] = None
        self.target: Optional[Target] = None
        self.log: list[str] = []
        self.run_cmd: list[str] = []

    def start(self) -> Target:
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        self.port = s.getsockname()[1]
        s.close()
        self.run_cmd = ["docker", "run", "-d", "--rm", "--name", self.name, "--label", "tavs.e5=1",
                        "-e", "POSTGRES_PASSWORD=postgis", "--shm-size", "256m",
                        "-p", f"127.0.0.1:{self.port}:5432", self.image,
                        "postgres", "-c", "fsync=off", "-c", "synchronous_commit=off",
                        "-c", "full_page_writes=off"]
        r = sh(self.run_cmd)
        if r.returncode != 0:
            raise RuntimeError(f"docker run failed for {self.image}: {r.stderr.strip()[:500]}")
        self.log.append(f"{now()} started {self.name} from {self.image} on 127.0.0.1:{self.port}")
        t = Target(f"e5-{self.label}", port=self.port)
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < READY_S:
            if t.run("SELECT postgis_full_version()").ok:
                break
            t.close_quietly()
            time.sleep(2)
        else:
            raise RuntimeError(f"throwaway {self.name} not ready after {READY_S} s")
        self.target = t
        return t

    def exec(self, script: str, user: Optional[str] = None) -> str:
        r = sh(["docker", "exec", *(["-u", user] if user else []), self.name, "sh", "-c", script])
        return (r.stdout + (f"\n[stderr] {r.stderr.strip()}" if r.stderr.strip() else "")
                + (f"\n[rc={r.returncode}]" if r.returncode else "")).strip()

    def close(self) -> None:
        if self.target is not None:
            self.target.close_quietly()
        r = sh(["docker", "rm", "-f", self.name])
        self.log.append(f"{now()} removed {self.name}: rc={r.returncode}")


# --------------------------------------------------------------------------------------------
# verification: which GEOS does PostGIS load in this container?

def _sha_map(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        m = re.match(r"^([0-9a-f]{64})\s+\*?(\S+)$", line.strip())
        if m:
            out[m.group(2)] = m.group(1)
    return out


def verify(c: Throwaway, expected_commit: Optional[str]) -> dict:
    t = c.target
    v: dict = {"time": now()}
    # a fresh backend that has loaded postgis-3.so (any PostGIS call loads it)
    t.close_quietly()
    r = t.run("SELECT postgis_full_version(), postgis_geos_version(), pg_backend_pid(), "
              "(SELECT setting FROM pg_config WHERE name = 'PKGLIBDIR'), "
              "(SELECT probin FROM pg_proc WHERE proname = 'postgis_geos_version' LIMIT 1)")
    if not r.ok:
        v.update(ok=False, problems=[f"version query failed: {r.error}: {r.message}"])
        return v
    full, geos, pid, pkglib, probin = r.one()
    lib = probin.replace("$libdir", pkglib)
    lib = lib if lib.endswith(".so") else lib + ".so"
    v.update(postgis_full_version=full, postgis_geos_version=geos, backend_pid=pid,
             postgis_library=lib)
    # the backend runs as postgres; root in the container lacks CAP_SYS_PTRACE to read its maps
    maps = c.exec(f"grep -i geos /proc/{int(pid)}/maps | awk '{{print $6}}' | sort -u",
                  user="postgres")
    v["maps_raw"] = maps
    v["mapped_geos_files"] = [p for p in maps.splitlines() if p.startswith("/")]
    v["ldd"] = c.exec(f"ldd {lib} | grep -i -E 'geos|not found'")
    resolved = {}
    for line in v["ldd"].splitlines():
        m = re.match(r"^\s*(\S*geos\S*)\s*=>\s*(\S+)", line)
        if m:
            resolved[m.group(1)] = m.group(2)
    v["ldd_resolved"] = resolved
    files = sorted(set(resolved.values()) | set(v["mapped_geos_files"]))
    real = c.exec("for f in " + " ".join(files) + "; do echo \"$f $(readlink -f $f)\"; done") \
        if files else ""
    v["realpath"] = dict(line.split(" ", 1) for line in real.splitlines() if " " in line)
    reals = sorted(set(v["realpath"].values()))
    v["sha256"] = _sha_map(c.exec("sha256sum " + " ".join(reals))) if reals else {}
    v["marker_commit"] = c.exec("cat /_tavs_geos_commit.txt 2>/dev/null || true") or None
    v["build_record"] = c.exec("cat /_tavs_geos_build.txt 2>/dev/null || true") or None
    v["base_geos_marker"] = c.exec("head -1 /_pgis_geos_last_commit.txt 2>/dev/null || true")
    v["build_sha256"] = {}
    if v["build_record"]:
        part = v["build_record"].split("sha256 of the built libraries:", 1)[-1]
        v["build_sha256"] = {Path(k).name: h for k, h in _sha_map(part).items()}

    problems = []
    if "not found" in v["ldd"]:
        problems.append("ldd reports a missing library")
    capi_ldd = next((v["realpath"].get(p) for k, p in resolved.items()
                     if k.startswith("libgeos_c")), None)
    capi_mapped = [v["realpath"].get(p, p) for p in v["mapped_geos_files"]
                   if Path(p).name.startswith("libgeos_c")]
    v["libgeos_c_ldd"], v["libgeos_c_mapped"] = capi_ldd, capi_mapped
    if not capi_ldd:
        problems.append("ldd does not resolve libgeos_c for the PostGIS library")
    if capi_mapped != [capi_ldd]:
        problems.append(f"backend maps libgeos_c {capi_mapped}, ldd resolves {capi_ldd}")
    if len(v["mapped_geos_files"]) != 2:
        problems.append(f"backend maps {len(v['mapped_geos_files'])} GEOS files, expected 2")
    if expected_commit is not None:
        if v["marker_commit"] != expected_commit:
            problems.append(f"marker {v['marker_commit']!r} != expected {expected_commit}")
        if not v["build_sha256"]:
            problems.append("no build record with library checksums")
        for p in v["mapped_geos_files"]:
            rp = v["realpath"].get(p, p)
            want = v["build_sha256"].get(Path(rp).name)
            if v["sha256"].get(rp) != want:
                problems.append(f"{rp}: sha256 {v['sha256'].get(rp)} != build record {want}")
        v["geos_version_names_commit"] = ("g" + expected_commit[:7]) in (geos or "") or \
            ("g" + expected_commit[:7]) in (full or "")
    v["problems"] = problems
    v["ok"] = not problems
    return v


# --------------------------------------------------------------------------------------------
# replay

def replay_finding(t: Target, f: dict) -> dict:
    res = []
    # findings.json keeps a trimmed rep_item; crash_probes needs the function and raw stages
    for q in crash_probes(dict(f["rep_item"], function=f["function"])):
        r = run_probe(t, q, f["a"], f["b"])
        res.append({"probe": q["sql"], "o": q["o"], "error": r.error,
                    "value": r.one()[0] if r.ok else None,
                    "message": (r.message or "")[:300] if not r.ok else None})
    recorded = [(p["probe"], p["o"]) for p in f["rerun"]["images"]["dev"]["probes"]]
    return {"crash": any(p["error"] == "crash" for p in res), "probes": res,
            "probes_match_triage": [(p["probe"], p["o"]) for p in res] == recorded}


def run_repro(t: Target) -> list[dict]:
    out = []
    for i, stmt in enumerate(repro_statements(), 1):
        r = t.run(stmt)
        m = re.search(r"\bAS\s+(\w+)\s*$", stmt, re.I)
        out.append({"n": i, "name": m.group(1) if m else f"statement{i}", "sql": stmt,
                    "error": r.error, "rows": [list(x) for x in r.rows] if r.ok else None,
                    "message": (r.message or "")[:300] if not r.ok else None})
    return out


def image_info(image: str) -> dict:
    r = sh(["docker", "image", "inspect", "--format",
            "{{.Id}}|{{json .RepoDigests}}|{{json .RepoTags}}|{{.Created}}|"
            "{{json .Config}}", image])
    if r.returncode != 0:
        return {"error": r.stderr.strip()[:300]}
    iid, digests, tags, created, config = r.stdout.strip().split("|", 4)
    return {"id": iid, "repo_digests": json.loads(digests), "repo_tags": json.loads(tags),
            "created": created,
            "label_tavs_geos_commit": ((json.loads(config) or {}).get("Labels") or {})
            .get("tavs.geos.commit")}


def run_target(label: str, image: str, expected: Optional[str], findings: list[dict]) -> dict:
    rec = {"label": label, "image": image, "expected_commit": expected, "start": now(),
           "image_info": image_info(image), "findings": {}, "reproducer": None}
    c = Throwaway(label, image)
    try:
        t = c.start()
        rec["docker_run"] = " ".join(c.run_cmd)
        rec["container_image_id"] = sh(["docker", "inspect", "--format", "{{.Image}}",
                                        c.name]).stdout.strip()
        rec["verify_before"] = verify(c, expected)
        print(f"[{label}] verify: ok={rec['verify_before']['ok']} "
              f"{rec['verify_before'].get('problems')}", flush=True)
        if not rec["verify_before"]["ok"]:
            rec["skipped"] = "verification failed before the replay"
            return rec
        rec["reproducer"] = run_repro(t)
        print(f"[{label}] reproducer: " + "; ".join(
            f"{s['name']}={'CRASH' if s['error'] == 'crash' else s['error'] or s['rows']}"
            for s in rec["reproducer"]), flush=True)
        for i, f in enumerate(findings, 1):
            t0 = time.perf_counter()
            r = replay_finding(t, f)
            r["seconds"] = round(time.perf_counter() - t0, 2)
            rec["findings"][f["key_id"]] = r
            if i % 25 == 0 or i == len(findings):
                n = sum(x["crash"] for x in rec["findings"].values())
                print(f"[{label}] {i}/{len(findings)} findings, {n} crashed", flush=True)
        rec["verify_after"] = verify(c, expected)
        print(f"[{label}] verify after: ok={rec['verify_after']['ok']}", flush=True)
    except Exception as exc:  # noqa: BLE001 - recorded, container still removed
        rec["exception"] = f"{type(exc).__name__}: {exc}"
        print(f"[{label}] exception: {rec['exception']}", flush=True)
    finally:
        c.close()
        rec["containers"] = c.log
        rec["end"] = now()
    return rec


# --------------------------------------------------------------------------------------------
# outputs

def _values(r: dict) -> str:
    return json.dumps({p["probe"] + ("" if p["o"] == "ab" else " [ba]"):
                       ("CRASH" if p["error"] == "crash" else
                        f"ERROR:{p['error']}" if p["error"] else p["value"])
                       for p in r["probes"]}, ensure_ascii=False)


def write_outputs(out: Path, meta: dict, findings: list[dict], recs: list[dict]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    tri = {f["key_id"]: f["rerun"]["images"] for f in findings}
    with open(out / "results.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["key", "function", "target", "image", "crash", "probes", "probes_crashed",
                    "probes_other_error", "probes_match_triage", "values", "triage_current_crash",
                    "triage_dev_crash"])
        for rec in recs:
            for f in findings:
                r = rec["findings"].get(f["key_id"])
                if r is None:
                    continue
                errs = Counter(p["error"] for p in r["probes"])
                w.writerow([f["key_id"], f["function"], rec["label"], rec["image"], r["crash"],
                            len(r["probes"]), errs.get("crash", 0),
                            sum(n for k, n in errs.items() if k not in (None, "crash")),
                            r["probes_match_triage"],
                            _values(r), tri[f["key_id"]]["current"]["crash"],
                            tri[f["key_id"]]["dev"]["crash"]])
    with open(out / "reproducer.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["target", "n", "name", "crash", "error", "rows"])
        for rec in recs:
            for s in rec.get("reproducer") or []:
                w.writerow([rec["label"], s["n"], s["name"], s["error"] == "crash", s["error"],
                            json.dumps(s["rows"], ensure_ascii=False)])
    (out / "details.json").write_text(json.dumps({"meta": meta, "targets": recs}, indent=1,
                                                 default=str, ensure_ascii=False),
                                      encoding="utf-8")
    L = ["# E5: family A replay on GEOS before and after the fix (GEOS PR #1590)", "",
         f"- Command: `{meta['command']}`",
         f"- Working directory: `{meta['cwd']}`",
         f"- Start: {meta['start']}; end: {meta.get('end', '(running or interrupted)')}",
         f"- Repository HEAD: {meta['git_head']}; uncommitted changes in tavs/, docker/, scripts/: "
         f"{meta['git_dirty'] or 'none'}",
         f"- Python {meta['python']}, {meta['platform']}",
         f"- Inputs: {meta['inputs']}",
         f"- Findings: {len(findings)} of family A (families.csv family == A); "
         f"selection: {meta['selection']}",
         "- Crash check: `triage.crash_probes(rep_item)` on the shrunk pair through "
         "`triage.run_probe`; a finding crashes when any probe's error is `crash`.",
         "- Image builds: `docker build --progress=plain -t <tag> --build-arg GEOS_COMMIT=<commit> "
         "--build-arg JOBS=6 --build-arg BASE_IMAGE=<dev digest> docker/geos-rebuild` "
         "(scripts/run_e5_geos_fix.ps1; full output in log.txt)", "",
         "## Counts per target", "",
         "| target | image | GEOS marker | verified | findings crashed | probes crashed | "
         "probes other error | reproducer with_empty |",
         "|---|---|---|---|---|---|---|---|"]
    for rec in recs:
        fr = rec["findings"]
        nprobe = sum(len(r["probes"]) for r in fr.values())
        pc = sum(p["error"] == "crash" for r in fr.values() for p in r["probes"])
        po = sum(p["error"] not in (None, "crash") for r in fr.values() for p in r["probes"])
        vb = rec.get("verify_before") or {}
        we = next((s for s in rec.get("reproducer") or [] if s["name"] == "with_empty"), None)
        wes = ("n/a" if we is None else "CRASH" if we["error"] == "crash"
               else we["error"] or json.dumps(we["rows"]))
        L.append(f"| {rec['label']} | `{rec['image']}` | {vb.get('marker_commit') or '-'} | "
                 f"{vb.get('ok')} / after {(rec.get('verify_after') or {}).get('ok')} | "
                 f"{sum(r['crash'] for r in fr.values())} / {len(fr)} (of {len(findings)}) | "
                 f"{pc} / {nprobe} | {po} / {nprobe} | {wes} |")
    L += ["", "Probe lists identical to the triage's recorded probes: " + ", ".join(
        f"{r['label']} {sum(x['probes_match_triage'] for x in r['findings'].values())}"
        f" / {len(r['findings'])}" for r in recs)]
    L += ["", "Anchor agreement with the triage record (crash yes/no per finding):", ""]
    for rec in recs:
        fr = rec["findings"]
        for img in ("dev", "current"):
            agree = sum(fr[k]["crash"] == tri[k][img]["crash"] for k in fr)
            L.append(f"- {rec['label']} vs triage `{img}`: {agree} / {len(fr)} agree")
    L += ["", "## Targets", ""]
    for rec in recs:
        ii = rec["image_info"]
        L += [f"### {rec['label']}", "",
              f"- Image: `{rec['image']}`; id `{ii.get('id')}`; digests {ii.get('repo_digests')}; "
              f"created {ii.get('created')}; label tavs.geos.commit {ii.get('label_tavs_geos_commit')}",
              f"- Container image id: `{rec.get('container_image_id')}`",
              f"- Expected GEOS commit: {rec['expected_commit'] or '(none: anchor)'}",
              f"- Start {rec['start']}, end {rec.get('end')}",
              f"- docker run: `{rec.get('docker_run')}`"]
        for when in ("verify_before", "verify_after"):
            v = rec.get(when)
            if not v:
                continue
            L += [f"- {when}: ok={v.get('ok')} problems={v.get('problems')}",
                  f"  - postgis_geos_version: `{v.get('postgis_geos_version')}`",
                  f"  - marker /_tavs_geos_commit.txt: {v.get('marker_commit')}; base image "
                  f"marker: {v.get('base_geos_marker')}; GEOS version names the commit: "
                  f"{v.get('geos_version_names_commit')}",
                  f"  - PostGIS library: `{v.get('postgis_library')}`; ldd: "
                  f"`{' | '.join(x.strip() for x in (v.get('ldd') or '').splitlines())}`",
                  f"  - backend {v.get('backend_pid')} maps: {v.get('mapped_geos_files')}",
                  f"  - sha256 (runtime): {v.get('sha256')}",
                  f"  - sha256 (build record): {v.get('build_sha256') or '-'}"]
            if when == "verify_before" and v.get("build_record"):
                L += ["  - build record /_tavs_geos_build.txt:", "", "```",
                      v["build_record"], "```", ""]
        for k in ("skipped", "exception"):
            if rec.get(k):
                L.append(f"- {k.upper()}: {rec[k]}")
        L += [f"- {x}" for x in rec.get("containers", [])] + [""]
    if meta.get("full_version"):
        L += ["## postgis_full_version per target", ""]
        L += [f"- {k}: `{v}`" for k, v in meta["full_version"].items()] + [""]
    (out / "summary.md").write_text("\n".join(L) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------------------------

def _git(*args: str) -> str:
    r = sh(["git", "-C", str(ROOT), *args])
    return r.stdout.strip() if r.returncode == 0 else f"(git failed: {r.stderr.strip()[:100]})"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--target", action="append", default=[], metavar="LABEL=IMAGE")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--keys")
    ap.add_argument("--out", default=str(ROOT / "runs" / "e5-geos-fix"))
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    if args.target:
        targets = []
        for spec in args.target:
            label, _, image = spec.partition("=")
            if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]*", label) or not image:
                raise SystemExit(f"bad --target {spec!r}; use LABEL=IMAGE")
            expected = {t[1]: t[2] for t in DEFAULT_TARGETS}.get(image)
            targets.append((label, image, expected))
    else:
        targets = DEFAULT_TARGETS
    keys = set(args.keys.split(",")) if args.keys else None
    findings = family_a(args.limit, keys)
    out = Path(args.out)
    meta = {"command": " ".join([Path(sys.executable).name, "-s", "-m", "tavs.replay_fix",
                                 *(argv if argv is not None else sys.argv[1:])]),
            "cwd": os.getcwd(), "start": now(), "git_head": _git("rev-parse", "HEAD"),
            "git_dirty": _git("status", "--porcelain", "--", "tavs", "docker", "scripts")
            .replace("\n", "; "),
            "python": sys.version.split()[0], "platform": platform.platform(),
            "inputs": [str(TRIAGE / "families.csv"), str(TRIAGE / "findings.json"),
                       str(REPRO_SQL)],
            "selection": {"limit": args.limit, "keys": sorted(keys) if keys else None},
            "targets": [{"label": a, "image": b, "expected_commit": c} for a, b, c in targets]}
    print(f"{len(findings)} family A findings; targets "
          + ", ".join(f"{a}={b}" for a, b, _ in targets), flush=True)
    recs = []
    for label, image, expected in targets:
        recs.append(run_target(label, image, expected, findings))
        write_outputs(out, meta, findings, recs)
    meta["end"] = now()
    meta["full_version"] = {r["label"]: (r.get("verify_before") or {}).get("postgis_full_version")
                            for r in recs}
    write_outputs(out, meta, findings, recs)
    print((out / "summary.md").read_text(encoding="utf-8"), flush=True)
    if any(r.get("exception") for r in recs):
        return 1
    if any(not (r.get("verify_before") or {}).get("ok")
           or not (r.get("verify_after") or {}).get("ok") for r in recs):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
