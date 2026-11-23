"""E6: replay the wrong-answer families B to F on GEOS built before and at two fixes (PR #1601, #1615).

  .venv/Scripts/python.exe -s -m tavs.replay_fixes                (full replay -> runs/e6-geos-fixes/)
  options: --target LABEL=IMAGE[=COMMIT]  repeatable; replaces the four default targets; without
                                          a commit the GEOS commit-marker check is skipped
           --families B,D                 only these families (of B, C, D, E, F)
           --limit N                      only the first N selected findings (sorted by family, key)
           --keys K1,K2                   only these finding keys
           --out DIR                      output folder (default runs/e6-geos-fixes)

Default targets, in this order (pinned dev image with GEOS rebuilt, docker/geos-rebuild):
  before-b  tavs-geos:before-faaaad0b  faaaad0b  parent of the merge of GEOS PR #1601
  fix-b     tavs-geos:fix-695a1909     695a1909  merge of PR #1601 (fix reported for family B)
  before-d  tavs-geos:before-b6754aa2  b6754aa2  parent of the merge of GEOS PR #1615
  fix-d     tavs-geos:fix-35fa80c9     35fa80c9  merge of PR #1615 (fix for the issue family D
                                                 is consistent with)

Findings: families B, C, D, E and F of runs/e3/triage/families.csv (58 + 29 + 2 + 1 + 2 = 92;
the counts are asserted), with the shrunk pairs and the triage record from
runs/e3/triage/findings.json.

Check per finding and target: the triage's own rerun, `triage.rerun(f, tw, tdir)`, called
unchanged. `rerun` loops over the triage's three image slots (current, dev, old) through
`tw.target(image)`; here `tw` is a stand-in whose every slot is this target's throwaway
container, so each finding is evaluated three times on the same target (slot "current" gives
the status, the other two are repeats; disagreements are reported). `rerun` also runs its
Shapely step (local GEOS, not the target); that result is kept in details.json only.
Status of a slot: "reproduces" when `present_counted` (the recorded (rule, sub, function,
orientation) violation is present and counted, as in the triage's current/dev/old record);
otherwise "crash" when an outcome kind is "crash", "other error" when any outcome kind is not
one of skipped / not_applicable / tier_mismatch (or `rerun` raised), else "not reproduced".

Control: the status on before-b (or on the first target when before-b is not run) against the
triage's recorded `dev` result (present_counted), per family.

The SQL reproducers of families B and D are run per target, one statement at a time.
Containers, verification and image info come from tavs.replay_fix (E5): one throwaway container
per target (label tavs.e6=1, name tavs-e6-<label>-<pid>, `--pull never`), GEOS verification
before and after, removed afterwards. Existing images and containers are never modified.

Outputs: results.csv, reproducers.csv, details.json, summary.md. Exit code 0 when every target
verified and ran, 3 when a verification failed, 1 on an exception.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import re
import shutil
import socket
import sys
import tempfile
import time
import traceback
from collections import Counter
from pathlib import Path
from typing import Optional

from . import replay_fix as rf
from . import triage
from .db import Target

TRIAGE = rf.TRIAGE
FAMILY_COUNTS = {"B": 58, "C": 29, "D": 2, "E": 1, "F": 2}
DEFAULT_TARGETS = [
    ("before-b", "tavs-geos:before-faaaad0b", "faaaad0b0b95e8a0bdb72e2b28416bd1511e7deb"),
    ("fix-b", "tavs-geos:fix-695a1909", "695a19097e4750e689c02f6b4de69bc25a5f70e3"),
    ("before-d", "tavs-geos:before-b6754aa2", "b6754aa2eb591a2bdabfe7f730c1e3c9c71408e5"),
    ("fix-d", "tavs-geos:fix-35fa80c9", "35fa80c99e8db5738f06163082caa49fc7c2ee3d"),
]
REPRODUCERS = {
    "B": rf.ROOT / "findings" / "B-prepared-contains-empty-member" / "reproduce.sql",
    "D": rf.ROOT / "findings" / "D-relate-not-symmetric-self-noding" / "reproduce.sql",
}
EXPECTATION_TEXT = (
    "Expectation fixed before the run: all 58 family B findings reproduce on before-b and none "
    "on fix-b, before-d or fix-d; both family D findings reproduce on before-b, fix-b and "
    "before-d and none on fix-d. Families C, E and F carry no expectation and are reported as "
    "observed.")
# expected "reproduces" (True) or not (False), per family and target label
EXPECTED = {"B": {"before-b": True, "fix-b": False, "before-d": False, "fix-d": False},
            "D": {"before-b": True, "fix-b": True, "before-d": True, "fix-d": False}}
CONTROL_LABEL = "before-b"
STATUSES = ("reproduces", "not reproduced", "crash", "other error")
SLOTS = triage.IMAGES                       # ("current", "dev", "old"): rerun's three slots
BENIGN_OUTCOMES = {"skipped", "not_applicable", "tier_mismatch"}


# --------------------------------------------------------------------------------------------
# inputs

def load_findings(families: list[str], limit: Optional[int], keys: Optional[set]) -> list[dict]:
    with open(TRIAGE / "families.csv", encoding="utf-8", newline="") as fh:
        fam = {r["key"]: r["family"] for r in csv.DictReader(fh)}
    counts = Counter(v for v in fam.values() if v in FAMILY_COUNTS)
    if dict(counts) != FAMILY_COUNTS:
        raise SystemExit(f"families.csv counts {dict(sorted(counts.items()))} differ from the "
                         f"expected {FAMILY_COUNTS}")
    data = json.loads((TRIAGE / "findings.json").read_text(encoding="utf-8"))
    by_key = {f["key_id"]: f for f in data["findings"]}
    wanted = {k for k, v in fam.items() if v in FAMILY_COUNTS}
    missing = sorted(wanted - set(by_key))
    if missing:
        raise SystemExit(f"families B-F keys missing from findings.json: {missing}")
    crash = sorted(k for k in wanted if by_key[k]["rule"] == "crash")
    if crash:
        raise SystemExit(f"families B-F contain crash findings (unexpected): {crash}")
    fs = sorted((dict(by_key[k], family=fam[k]) for k in wanted if fam[k] in families),
                key=lambda f: (f["family"], f["key_id"]))
    if keys:
        unknown = keys - {f["key_id"] for f in fs}
        if unknown:
            raise SystemExit(f"not findings of families {','.join(families)}: {sorted(unknown)}")
        fs = [f for f in fs if f["key_id"] in keys]
    if limit is not None:
        fs = fs[:limit]
    return fs


def statements(path: Path) -> list[dict]:
    """Statements of a reproducer file, each with the comment lines just before it."""
    out, comments, body = [], [], []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("--"):
            if not body:
                comments.append(s[2:].strip())
            continue
        if s:
            body.append(line)
        if s.endswith(";"):
            out.append({"comment": " ".join(comments), "sql": "\n".join(body).rstrip()[:-1]})
            comments, body = [], []
    if "\n".join(body).strip():
        out.append({"comment": " ".join(comments), "sql": "\n".join(body).strip()})
    return out


# --------------------------------------------------------------------------------------------
# container (E5's Throwaway with E6 name and label, and no pulling)

class E6Throwaway(rf.Throwaway):
    def __init__(self, label: str, image: str):
        super().__init__(label, image)
        self.name = f"tavs-e6-{label}-{os.getpid()}"

    def start(self) -> Target:
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        self.port = s.getsockname()[1]
        s.close()
        self.run_cmd = ["docker", "run", "-d", "--rm", "--pull", "never", "--name", self.name,
                        "--label", "tavs.e6=1", "-e", "POSTGRES_PASSWORD=postgis",
                        "--shm-size", "256m", "-p", f"127.0.0.1:{self.port}:5432", self.image,
                        "postgres", "-c", "fsync=off", "-c", "synchronous_commit=off",
                        "-c", "full_page_writes=off"]
        r = rf.sh(self.run_cmd)
        if r.returncode != 0:
            raise RuntimeError(f"docker run failed for {self.image}: {r.stderr.strip()[:500]}")
        self.log.append(f"{rf.now()} started {self.name} from {self.image} on "
                        f"127.0.0.1:{self.port}")
        t = Target(f"e6-{self.label}", port=self.port)
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < rf.READY_S:
            if t.run("SELECT postgis_full_version()").ok:
                break
            t.close_quietly()
            time.sleep(2)
        else:
            raise RuntimeError(f"throwaway {self.name} not ready after {rf.READY_S} s")
        self.target = t
        return t


class OneTarget:
    """Stands in for `triage.Throwaways` inside `triage.rerun`: every image slot is this
    target's container."""

    def __init__(self, t: Target, version: Optional[str]):
        self.t = t
        self.versions = {s: version for s in SLOTS}

    def target(self, image: str) -> Target:
        return self.t


# --------------------------------------------------------------------------------------------
# replay

def slot_status(slot: dict) -> str:
    if slot.get("present_counted"):
        return "reproduces"
    kinds = set(slot.get("outcomes") or {})
    if "crash" in kinds:
        return "crash"
    if kinds - BENIGN_OUTCOMES:
        return "other error"
    return "not reproduced"


def replay_finding(tw: OneTarget, f: dict, tdir: Path) -> dict:
    try:
        rr = triage.rerun(f, tw, tdir)
    except Exception as exc:  # noqa: BLE001 - recorded as "other error"
        return {"status": "other error", "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc()[-2000:], "rerun": None}
    slots = {s: slot_status(rr["images"][s]) for s in SLOTS}
    return {"status": slots[SLOTS[0]], "slot_status": slots,
            "repeats_agree": len(set(slots.values())) == 1, "error": None, "rerun": rr}


def run_reproducers(t: Target) -> dict:
    out = {}
    for fam, path in REPRODUCERS.items():
        res = []
        for i, st in enumerate(statements(path), 1):
            r = t.run(st["sql"])
            res.append({"n": i, "comment": st["comment"], "sql": st["sql"], "error": r.error,
                        "rows": [list(x) for x in r.rows] if r.ok else None,
                        "message": (r.message or "")[:300] if not r.ok else None})
        out[fam] = res
    return out


def run_target(label: str, image: str, expected: Optional[str], findings: list[dict],
               tdir: Path) -> dict:
    rec = {"label": label, "image": image, "expected_commit": expected, "start": rf.now(),
           "image_info": rf.image_info(image), "findings": {}, "reproducers": None}
    c = E6Throwaway(label, image)
    try:
        t = c.start()
        rec["docker_run"] = " ".join(c.run_cmd)
        rec["container_image_id"] = rf.sh(["docker", "inspect", "--format", "{{.Image}}",
                                           c.name]).stdout.strip()
        rec["verify_before"] = rf.verify(c, expected)
        print(f"[{label}] verify: ok={rec['verify_before']['ok']} "
              f"{rec['verify_before'].get('problems')}", flush=True)
        if not rec["verify_before"]["ok"]:
            rec["skipped"] = "verification failed before the replay"
            return rec
        rec["reproducers"] = run_reproducers(t)
        for fam, res in rec["reproducers"].items():
            print(f"[{label}] reproducer {fam}: " + "; ".join(
                f"{s['n']}={s['error'] or s['rows']}" for s in res), flush=True)
        tw = OneTarget(t, rec["verify_before"].get("postgis_full_version"))
        for i, f in enumerate(findings, 1):
            t0 = time.perf_counter()
            r = replay_finding(tw, f, tdir)
            r["seconds"] = round(time.perf_counter() - t0, 2)
            rec["findings"][f["key_id"]] = r
            if i % 10 == 0 or i == len(findings):
                n = Counter(x["status"] for x in rec["findings"].values())
                print(f"[{label}] {i}/{len(findings)} findings: {dict(n)}", flush=True)
        rec["verify_after"] = rf.verify(c, expected)
        print(f"[{label}] verify after: ok={rec['verify_after']['ok']}", flush=True)
    except Exception as exc:  # noqa: BLE001 - recorded, container still removed
        rec["exception"] = f"{type(exc).__name__}: {exc}"
        print(f"[{label}] exception: {rec['exception']}", flush=True)
    finally:
        c.close()
        rec["containers"] = c.log
        rec["end"] = rf.now()
    return rec


# --------------------------------------------------------------------------------------------
# outputs

def _viol(slot: dict) -> list:
    return [{k: v[k] for k in ("paths", "tier", "magnitude", "raw")}
            for v in slot.get("violations") or []]


def _values(r: dict) -> str:
    if r["rerun"] is None:
        return json.dumps({"error": r["error"]}, ensure_ascii=False)
    s = r["rerun"]["images"][SLOTS[0]]
    return json.dumps({"present_counted": s["present_counted"], "present": s["present"],
                       "violations": _viol(s), "outcomes": s["outcomes"],
                       "outcome_messages": s["outcome_messages"],
                       "repeat_status": r["slot_status"]}, ensure_ascii=False, default=str)


def _raw_same(r: dict, f: dict) -> Optional[bool]:
    if r["rerun"] is None:
        return None
    now_raw = [v["raw"] for v in r["rerun"]["images"][SLOTS[0]].get("violations") or []]
    dev_raw = [v["raw"] for v in f["rerun"]["images"]["dev"].get("violations") or []]
    return json.loads(json.dumps(now_raw, default=str)) == json.loads(json.dumps(dev_raw,
                                                                                  default=str))


def _control_label(recs: list[dict]) -> Optional[str]:
    labels = [r["label"] for r in recs]
    return CONTROL_LABEL if CONTROL_LABEL in labels else (labels[0] if labels else None)


def _rows(r: Optional[list]) -> str:
    return json.dumps(r, ensure_ascii=False, default=str)


def _target_lines(rec: dict) -> list[str]:
    ii = rec["image_info"]
    L = [f"### {rec['label']}", "",
         f"- Image: `{rec['image']}`; id `{ii.get('id')}`; digests {ii.get('repo_digests')}; "
         f"created {ii.get('created')}; label tavs.geos.commit "
         f"{ii.get('label_tavs_geos_commit')}" + (f"; inspect error {ii['error']}"
                                                  if ii.get("error") else ""),
         f"- Container image id: `{rec.get('container_image_id')}`",
         f"- Expected GEOS commit: {rec['expected_commit'] or '(none: commit check skipped)'}",
         f"- Start {rec['start']}, end {rec.get('end')}",
         f"- docker run: `{rec.get('docker_run')}`"]
    for when in ("verify_before", "verify_after"):
        v = rec.get(when)
        if not v:
            continue
        L += [f"- {when}: ok={v.get('ok')} problems={v.get('problems')}",
              f"  - postgis_geos_version: `{v.get('postgis_geos_version')}`",
              f"  - marker /_tavs_geos_commit.txt: {v.get('marker_commit')}; base image marker: "
              f"{v.get('base_geos_marker')}; GEOS version names the commit: "
              f"{v.get('geos_version_names_commit')}",
              f"  - PostGIS library: `{v.get('postgis_library')}`; ldd: "
              f"`{' | '.join(x.strip() for x in (v.get('ldd') or '').splitlines())}`",
              f"  - backend {v.get('backend_pid')} maps: {v.get('mapped_geos_files')}",
              f"  - sha256 (runtime): {v.get('sha256')}",
              f"  - sha256 (build record): {v.get('build_sha256') or '-'}"]
        if when == "verify_before" and v.get("build_record"):
            L += ["  - build record /_tavs_geos_build.txt:", "", "```", v["build_record"],
                  "```", ""]
    for k in ("skipped", "exception"):
        if rec.get(k):
            L.append(f"- {k.upper()}: {rec[k]}")
    return L + [f"- {x}" for x in rec.get("containers", [])] + [""]


def write_outputs(out: Path, meta: dict, findings: list[dict], recs: list[dict]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    fams = sorted({f["family"] for f in findings})
    with open(out / "results.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["key", "family", "rule", "sub", "function", "orientation", "paths", "target",
                    "image", "status", "repeats_agree", "repeat_status", "present_counted",
                    "present", "raw_same_as_triage_dev", "values", "triage_current",
                    "triage_dev", "triage_old", "triage_dev_violations", "seconds"])
        for rec in recs:
            for f in findings:
                r = rec["findings"].get(f["key_id"])
                if r is None:
                    continue
                s = r["rerun"]["images"][SLOTS[0]] if r["rerun"] else {}
                im = f["rerun"]["images"]
                w.writerow([f["key_id"], f["family"], f["rule"], f["sub"], f["function"],
                            f["orientation"], f["paths"], rec["label"], rec["image"],
                            r["status"], r.get("repeats_agree"),
                            json.dumps(r.get("slot_status")), s.get("present_counted"),
                            s.get("present"), _raw_same(r, f), _values(r),
                            im["current"]["present_counted"], im["dev"]["present_counted"],
                            im["old"]["present_counted"],
                            json.dumps(_viol(im["dev"]), ensure_ascii=False, default=str),
                            r["seconds"]])
    with open(out / "reproducers.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["target", "reproducer", "n", "comment", "error", "rows", "message"])
        for rec in recs:
            for fam, res in (rec.get("reproducers") or {}).items():
                for s in res:
                    w.writerow([rec["label"], fam, s["n"], s["comment"], s["error"],
                                _rows(s["rows"]), s["message"]])
    (out / "details.json").write_text(json.dumps({"meta": meta, "targets": recs}, indent=1,
                                                 default=str, ensure_ascii=False),
                                      encoding="utf-8")

    fam_of = {f["key_id"]: f["family"] for f in findings}
    n_fam = Counter(fam_of.values())
    L = ["# E6: families B to F replayed on GEOS before and at the fixes (GEOS PR #1601, #1615)",
         "",
         f"- Command: `{meta['command']}`",
         f"- Working directory: `{meta['cwd']}`",
         f"- Start: {meta['start']}; end: {meta.get('end', '(running or interrupted)')}",
         f"- Repository HEAD: {meta['git_head']}; uncommitted changes in tavs/, docker/, "
         f"scripts/: {meta['git_dirty'] or 'none'}",
         f"- Python {meta['python']}, {meta['platform']}",
         f"- Inputs: {meta['inputs']}",
         f"- Findings: {len(findings)} ({', '.join(f'{k} {n_fam[k]}' for k in fams)}); "
         f"selection: {meta['selection']}",
         f"- Targets: {', '.join(t['label'] + '=' + t['image'] for t in meta['targets'])}",
         "", EXPECTATION_TEXT, "",
         "- Check: `triage.rerun(finding, tw, tdir)` unchanged, with `tw` mapping its three "
         "image slots (current, dev, old) to this target's container: three evaluations per "
         "finding and target. Status from slot `current`: `reproduces` when `present_counted`; "
         "else `crash` when an outcome is `crash`; else `other error` when an outcome kind is "
         f"outside {sorted(BENIGN_OUTCOMES)} or rerun raised; else `not reproduced`.",
         "", "## Status per family and target", "",
         "Cells: reproduces / not reproduced / crash / other error, of the family total.", "",
         "| family | n | " + " | ".join(r["label"] for r in recs) + " |",
         "|---|---|" + "---|" * len(recs)]
    for fam in fams:
        cells = []
        for rec in recs:
            c = Counter(r["status"] for k, r in rec["findings"].items() if fam_of.get(k) == fam)
            done = sum(c.values())
            cells.append(" / ".join(str(c.get(s, 0)) for s in STATUSES) + f" of {n_fam[fam]}"
                         + ("" if done == n_fam[fam] else f" (ran {done})"))
        L.append(f"| {fam} | {n_fam[fam]} | " + " | ".join(cells) + " |")

    ctl = _control_label(recs)
    L += ["", f"## Control: {ctl} against the triage's recorded `dev` result", ""]
    if ctl is None:
        L.append("(no target ran)")
    else:
        crec = next(r for r in recs if r["label"] == ctl)
        if ctl != CONTROL_LABEL:
            L.append(f"({CONTROL_LABEL} was not run; the control uses the first target, {ctl}.)")
            L.append("")
        dis = []
        for fam in fams:
            ks = [f for f in findings if f["family"] == fam and f["key_id"] in crec["findings"]]
            agree = 0
            for f in ks:
                st = crec["findings"][f["key_id"]]["status"]
                dev = f["rerun"]["images"]["dev"]["present_counted"]
                if (st == "reproduces") == bool(dev):
                    agree += 1
                else:
                    dis.append(f"- {f['key_id']} ({fam}): {ctl} {st}; triage dev present_counted="
                               f"{dev}")
            L.append(f"- {fam}: {agree} / {len(ks)} agree (of {n_fam[fam]})")
        L += ["", "Disagreements:" if dis else "Disagreements: none."] + dis
    rep_dis = [f"- {k} ({fam_of[k]}) on {rec['label']}: {r['slot_status']}"
               for rec in recs for k, r in rec["findings"].items()
               if r.get("repeats_agree") is False]
    L += ["", "Repeats within a target (rerun's three slots) disagree: "
          + (f"{len(rep_dis)}" if rep_dis else "none.")] + rep_dis
    pnc = [f"- {k} ({fam_of[k]}) on {rec['label']}: present but not counted"
           for rec in recs for k, r in rec["findings"].items()
           if r["rerun"] and r["rerun"]["images"][SLOTS[0]]["present"]
           and not r["rerun"]["images"][SLOTS[0]]["present_counted"]]
    if pnc:
        L += ["", "Violation present but not counted (status is not `reproduces`):"] + pnc

    L += ["", "## Deviations from the expectation (families B and D)", ""]
    dev_lines = []
    for f in findings:
        exp = EXPECTED.get(f["family"])
        if not exp:
            continue
        for rec in recs:
            r = rec["findings"].get(f["key_id"])
            if r is None or rec["label"] not in exp:
                continue
            want = "reproduces" if exp[rec["label"]] else "not reproduced"
            if r["status"] != want:
                dev_lines.append(f"- {f['key_id']} ({f['family']}) on {rec['label']}: "
                                 f"{r['status']}, expected {want}")
    if not any(rec["label"] in EXPECTED["B"] for rec in recs):
        dev_lines.append("(no target with an expectation was run)")
    L += dev_lines or ["none"]
    L += ["", "## Families C, E, F: findings whose status changes between targets", ""]
    chg = []
    for f in findings:
        if f["family"] in EXPECTED:
            continue
        st = [(rec["label"], rec["findings"][f["key_id"]]["status"]) for rec in recs
              if f["key_id"] in rec["findings"]]
        if len({s for _, s in st}) > 1:
            chg.append(f"- {f['key_id']} ({f['family']} {f['rule']} {f['sub']} / "
                       f"{f['function']}): " + ", ".join(f"{a} {s}" for a, s in st))
    L += chg or ["none"]

    L += ["", "## Reproducers (one statement at a time)", ""]
    for rec in recs:
        for fam, res in (rec.get("reproducers") or {}).items():
            L.append(f"- {rec['label']} {fam}: " + "; ".join(
                f"{s['n']}=" + (f"ERROR {s['error']}" if s["error"] else _rows(s["rows"]))
                for s in res))
    L += ["", "## Targets", ""]
    for rec in recs:
        L += _target_lines(rec)
    if meta.get("full_version"):
        L += ["## postgis_full_version per target", ""]
        L += [f"- {k}: `{v}`" for k, v in meta["full_version"].items()] + [""]
    (out / "summary.md").write_text("\n".join(L) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------------------------

def parse_targets(specs: list[str]) -> list[tuple]:
    out = []
    for spec in specs:
        parts = spec.split("=")
        if len(parts) not in (2, 3) or not parts[1] \
                or not re.fullmatch(r"[a-z0-9][a-z0-9_.-]*", parts[0]):
            raise SystemExit(f"bad --target {spec!r}; use LABEL=IMAGE[=COMMIT]")
        commit = parts[2] if len(parts) == 3 else None
        if commit is not None and not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise SystemExit(f"bad commit in --target {spec!r}; use the full 40-hex SHA")
        out.append((parts[0], parts[1], commit))
    if len({t[0] for t in out}) != len(out):
        raise SystemExit("duplicate --target labels")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--target", action="append", default=[], metavar="LABEL=IMAGE[=COMMIT]")
    ap.add_argument("--families", default=",".join(FAMILY_COUNTS))
    ap.add_argument("--limit", type=int)
    ap.add_argument("--keys")
    ap.add_argument("--out", default=str(rf.ROOT / "runs" / "e6-geos-fixes"))
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    targets = parse_targets(args.target) if args.target else DEFAULT_TARGETS
    families = [x.strip().upper() for x in args.families.split(",") if x.strip()]
    bad = [x for x in families if x not in FAMILY_COUNTS]
    if bad or not families:
        raise SystemExit(f"bad --families {args.families!r}; choose from {list(FAMILY_COUNTS)}")
    keys = set(args.keys.split(",")) if args.keys else None
    findings = load_findings(families, args.limit, keys)
    out = Path(args.out)
    meta = {"command": " ".join([Path(sys.executable).name, "-s", "-m", "tavs.replay_fixes",
                                 *(argv if argv is not None else sys.argv[1:])]),
            "cwd": os.getcwd(), "start": rf.now(), "git_head": rf._git("rev-parse", "HEAD"),
            "git_dirty": rf._git("status", "--porcelain", "--", "tavs", "docker", "scripts")
            .replace("\n", "; "),
            "python": sys.version.split()[0], "platform": platform.platform(),
            "inputs": [str(TRIAGE / "families.csv"), str(TRIAGE / "findings.json"),
                       *(str(p) for p in REPRODUCERS.values())],
            "selection": {"families": families, "limit": args.limit,
                          "keys": sorted(keys) if keys else None},
            "expectation": EXPECTATION_TEXT,
            "targets": [{"label": a, "image": b, "expected_commit": c} for a, b, c in targets]}
    print(f"{len(findings)} findings ({dict(Counter(f['family'] for f in findings))}); targets "
          + ", ".join(f"{a}={b}" for a, b, _ in targets), flush=True)
    tdir = Path(tempfile.mkdtemp(prefix="tavs-e6-"))   # rerun's Shapely step writes tdir/tmp
    recs = []
    try:
        for label, image, expected in targets:
            recs.append(run_target(label, image, expected, findings, tdir))
            write_outputs(out, meta, findings, recs)
    finally:
        shutil.rmtree(tdir, ignore_errors=True)
    meta["end"] = rf.now()
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
