"""PostGIS targets and connections.

Every statement runs in autocommit with a statement timeout. Database errors never escape:
`Target.run` returns a `Result` whose `error` field carries the classified failure, so a rule
evaluation records an outcome instead of crashing the run.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Optional

import psycopg

# Images pinned by digest in compose.yaml (`docker compose -p tavs`).
TARGETS = {
    "current": {"port": 54336, "image": "postgis/postgis:18-3.6"},
    "dev": {"port": 54337, "image": "postgis/postgis:18-master"},
    "old": {"port": 54335, "image": "postgis/postgis:17-3.5"},
}
HOST = "127.0.0.1"
USER = "postgres"
PASSWORD = "postgis"  # local throwaway containers from compose.yaml
DBNAME = "postgres"
STATEMENT_TIMEOUT_MS = 10_000

# Message fragments that mark a GEOS/overlay failure rather than a SQL or harness failure.
_OVERLAY_MARKERS = ("GEOS", "TopologyException", "AssertionFailed", "IllegalArgument",
                    "found two shells", "lwgeom_", "side location conflict", "non-noded")


# SQLSTATEs/messages of a backend crash or the server's crash recovery.
_CRASH_STATES = {"57P01", "57P02", "57P03"}   # admin_shutdown, crash_shutdown, cannot_connect_now
_CRASH_MARKERS = ("server closed the connection unexpectedly", "terminating connection",
                  "consuming input failed", "connection is lost", "the connection is closed",
                  "recovery mode", "SSL SYSCALL error", "connection to server", "EOF detected")
RECOVERY_WAIT_S = 300


def is_crash(exc: BaseException) -> bool:
    """True when the backend died (our statement crashed it, or another backend's crash made
    the postmaster terminate every connection) rather than returning an SQL error."""
    if getattr(exc, "sqlstate", None) in _CRASH_STATES:
        return True
    if isinstance(exc, psycopg.OperationalError) and any(m in str(exc) for m in _CRASH_MARKERS):
        return True
    return isinstance(exc, (psycopg.InterfaceError,)) and "closed" in str(exc)


def classify_error(exc: BaseException) -> str:
    """Return 'crash', 'timeout', 'overlay_error' (GEOS/liblwgeom geometry failure),
    'sql_error' or 'other_error'."""
    msg = str(exc)
    if is_crash(exc):
        return "crash"
    if isinstance(exc, psycopg.errors.QueryCanceled) or "statement timeout" in msg:
        return "timeout"
    if isinstance(exc, psycopg.Error) and any(m in msg for m in _OVERLAY_MARKERS):
        return "overlay_error"
    if isinstance(exc, psycopg.Error):
        return "sql_error"
    return "other_error"


@dataclass
class Result:
    rows: Optional[list[tuple]] = None
    error: Optional[str] = None       # timeout | overlay_error | sql_error | other_error
    message: Optional[str] = None
    seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return self.error is None

    def one(self) -> Optional[tuple]:
        return self.rows[0] if self.rows else None


class Target:
    """One PostGIS instance. Reconnects after a lost connection."""

    def __init__(self, name: str, timeout_ms: int = STATEMENT_TIMEOUT_MS,
                 port: Optional[int] = None):
        """`name` is a registered target, or any label when `port` is given (e.g. a throwaway
        container for crash probes, which must never run on a shared target)."""
        if port is None and name not in TARGETS:
            raise KeyError(f"unknown target {name!r}; known: {sorted(TARGETS)}")
        self.name = name
        self.port = port if port is not None else TARGETS[name]["port"]
        self.image = TARGETS.get(name, {}).get("image", "unregistered")
        self.timeout_ms = timeout_ms
        self._conn: Optional[psycopg.Connection] = None

    # -- connection -------------------------------------------------------------------------
    def connect(self) -> psycopg.Connection:
        if self._conn is None or self._conn.closed or self._conn.broken:
            self._conn = psycopg.connect(host=HOST, port=self.port, user=USER, password=PASSWORD,
                                         dbname=DBNAME, autocommit=True, connect_timeout=10)
            self._conn.execute(f"SET statement_timeout = {int(self.timeout_ms)}")
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "Target":
        self.connect()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- execution --------------------------------------------------------------------------
    def run(self, sql: str, params: Any = None) -> Result:
        """Execute one statement; return rows or a classified error. Never raises."""
        t0 = time.perf_counter()
        try:
            conn = self.connect()
            cur = conn.execute(sql, params)
            rows = cur.fetchall() if cur.description is not None else []
            return Result(rows=rows, seconds=time.perf_counter() - t0)
        except Exception as exc:  # noqa: BLE001 - every failure becomes an outcome
            kind = classify_error(exc)
            msg = str(exc).strip()[:2000]
            if kind == "crash":
                self.close_quietly()
                waited = self.wait_ready()
                msg = (f"backend crash: {msg} | statement: {sql[:1500]} | params: "
                       f"{str(params)[:1500]} | server accepting again after {waited:.1f} s")
            elif self._conn is not None and (self._conn.closed or self._conn.broken):
                self._conn = None
            return Result(error=kind, message=msg, seconds=time.perf_counter() - t0)

    def close_quietly(self) -> None:
        try:
            if self._conn is not None:
                self._conn.close()
        except Exception:  # noqa: BLE001
            pass
        self._conn = None

    def wait_ready(self, limit_s: float = RECOVERY_WAIT_S) -> float:
        """Poll until the server accepts connections and answers SELECT 1 (after a crash and
        recovery). Returns the seconds waited; returns after `limit_s` even if not ready (the
        next statement then fails with its own outcome instead of the run aborting)."""
        t0 = time.perf_counter()
        time.sleep(0.5)
        while time.perf_counter() - t0 < limit_s:
            try:
                self.connect().execute("SELECT 1")
                return time.perf_counter() - t0
            except Exception:  # noqa: BLE001
                self.close_quietly()
                time.sleep(1.0)
        return time.perf_counter() - t0

    def version(self) -> str:
        r = self.run("SELECT postgis_full_version()")
        return r.one()[0] if r.ok else f"ERROR: {r.message}"
