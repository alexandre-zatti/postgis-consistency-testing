"""SQLite results store. Default location: runs/tavs.sqlite (gitignored)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .pair import Pair
from .rules import Evaluation

DEFAULT_DIR = Path(__file__).resolve().parent.parent / "runs"

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  run_id INTEGER PRIMARY KEY, experiment TEXT, target TEXT, postgis_full_version TEXT,
  params TEXT, started TEXT, finished TEXT);
CREATE TABLE IF NOT EXISTS pairs (
  pair_id INTEGER PRIMARY KEY, run_id INTEGER REFERENCES runs, a TEXT, b TEXT, coord TEXT,
  kind TEXT, arm TEXT, seed INTEGER, idx INTEGER, moves TEXT, source TEXT,
  rules_run TEXT, info TEXT, seconds TEXT);
CREATE TABLE IF NOT EXISTS violations (
  violation_id INTEGER PRIMARY KEY, pair_id INTEGER REFERENCES pairs, rule TEXT, sub TEXT,
  function TEXT, paths TEXT, orientation TEXT, tier TEXT, magnitude REAL, band TEXT,
  precision_limited INTEGER, raw TEXT);
CREATE TABLE IF NOT EXISTS outcomes (
  outcome_id INTEGER PRIMARY KEY, pair_id INTEGER REFERENCES pairs, stage TEXT, kind TEXT,
  message TEXT);
CREATE INDEX IF NOT EXISTS pairs_run ON pairs(run_id);
CREATE INDEX IF NOT EXISTS viol_pair ON violations(pair_id);
CREATE INDEX IF NOT EXISTS out_pair ON outcomes(pair_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _j(x) -> str:
    return json.dumps(x, default=str, ensure_ascii=False)


class Store:
    def __init__(self, path: Optional[Path] = None):
        path = Path(path) if path else DEFAULT_DIR / "tavs.sqlite"
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)

    def start_run(self, experiment: str, target: str, version: str, params: dict) -> int:
        cur = self.db.execute(
            "INSERT INTO runs (experiment, target, postgis_full_version, params, started) "
            "VALUES (?,?,?,?,?)", (experiment, target, version, _j(params), _now()))
        self.db.commit()
        return cur.lastrowid

    def finish_run(self, run_id: int) -> None:
        self.db.execute("UPDATE runs SET finished=? WHERE run_id=?", (_now(), run_id))
        self.db.commit()

    def add(self, run_id: int, ev: Evaluation, commit: bool = True) -> int:
        p: Pair = ev.pair
        cur = self.db.execute(
            "INSERT INTO pairs (run_id,a,b,coord,kind,arm,seed,idx,moves,source,rules_run,info,"
            "seconds) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (run_id, p.a, p.b, p.coord, p.kind, p.arm, p.seed, p.index, _j(p.moves), p.source,
             _j(ev.rules_run), _j(ev.info), _j(ev.seconds)))
        pid = cur.lastrowid
        self.db.executemany(
            "INSERT INTO violations (pair_id,rule,sub,function,paths,orientation,tier,magnitude,"
            "band,precision_limited,raw) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [(pid, v.rule, v.sub, v.function, v.paths, v.orientation, v.tier, v.magnitude,
              v.band, int(v.precision_limited), _j(v.raw)) for v in ev.violations])
        self.db.executemany(
            "INSERT INTO outcomes (pair_id,stage,kind,message) VALUES (?,?,?,?)",
            [(pid, o.stage, o.kind, o.message) for o in ev.outcomes])
        if commit:
            self.db.commit()
        return pid

    def commit(self) -> None:
        self.db.commit()

    def close(self) -> None:
        self.db.commit()
        self.db.close()
