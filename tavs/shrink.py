"""Geometry-aware greedy shrinker (plan: drop part, drop hole, drop vertex while valid,
round float digits; at most 200 steps; chain recorded).

`max_steps` bounds the number of calls to `still_fails` (each call re-runs the failing rule
through SQL), not only the accepted steps. A candidate is tried only if each geometry that
was valid before stays valid (Shapely), so a shrunk pair stays inside the rule's input domain.
Candidates are tried in order: drop part, drop hole, drop vertex, round; the first accepted
candidate restarts the scan. The search ends when a full scan accepts nothing or the budget
is spent.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Callable, Iterator

import shapely

from .gen import from_wkt, is_multi, map_coords, nvert, seqs, set_seq, to_wkt, vertices
from .pair import Pair


def _drop_part_cands(g, path=()) -> Iterator[tuple[str, object]]:
    t, d = g
    if is_multi(t):
        if len(d) > 1:
            for i in range(len(d)):
                yield f"drop part {path + (i,)}", (t, d[:i] + d[i + 1:])
        for i, c in enumerate(d):
            for desc, nc in _drop_part_cands(c, path + (i,)):
                yield desc, (t, d[:i] + [nc] + d[i + 1:])


def _drop_hole_cands(g, path=()):
    t, d = g
    if t == "Polygon" and len(d) > 1:
        for i in range(1, len(d)):
            yield f"drop hole {path + (i,)}", (t, d[:i] + d[i + 1:])
    elif is_multi(t):
        for i, c in enumerate(d):
            for desc, nc in _drop_hole_cands(c, path + (i,)):
                yield desc, (t, d[:i] + [nc] + d[i + 1:])


def _drop_vertex_cands(g):
    for path, s, closed in seqs(g):
        minimum = 3 if closed else 2
        if len(s) <= minimum:
            continue
        for i in range(len(s)):
            yield f"drop vertex {i} of {path}", set_seq(g, path, s[:i] + s[i + 1:])


def _sig_digits(v: float) -> int:
    if v == 0 or v != v:
        return 1
    m = repr(abs(v)).lower().split("e")[0].replace(".", "").lstrip("0").rstrip("0")
    return max(1, len(m))


def _round_sig(v: float, k: int) -> float:
    if v == 0:
        return 0.0
    return float(f"{v:.{k - 1}e}")


def _max_digits(g) -> int:
    return max((_sig_digits(c) for p in vertices(g) for c in p), default=1)


def _valid(g) -> bool:
    try:
        return shapely.from_wkt(to_wkt(g)).is_valid
    except Exception:
        return False


def shrink(pair: Pair, still_fails: Callable[[Pair], bool],
           max_steps: int = 200) -> tuple[Pair, list[dict]]:
    integral = pair.coord == "int"
    cur = {"a": from_wkt(pair.a, integral), "b": from_wkt(pair.b, integral)}
    was_valid = {k: _valid(v) for k, v in cur.items()}
    chain: list[dict] = []
    calls = 0

    def make(state) -> Pair:
        return dataclasses.replace(pair, a=to_wkt(state["a"]), b=to_wkt(state["b"]),
                                   moves=list(pair.moves))

    def candidates(state):
        for op in (_drop_part_cands, _drop_hole_cands, _drop_vertex_cands):
            for which in ("a", "b"):
                for desc, ng in op(state[which]):
                    yield which, desc, {**state, which: ng}
        if not integral:
            # round both geometries together first (keeps a-b coincidences), then each one
            top = max(_max_digits(state["a"]), _max_digits(state["b"]))
            for k in range(1, top):
                f = lambda p, k=k: (_round_sig(p[0], k), _round_sig(p[1], k))
                yield "ab", f"round to {k} significant digits", \
                    {"a": map_coords(state["a"], f), "b": map_coords(state["b"], f)}
            for which in ("a", "b"):
                for k in range(1, _max_digits(state[which])):
                    f = lambda p, k=k: (_round_sig(p[0], k), _round_sig(p[1], k))
                    yield which, f"round to {k} significant digits", \
                        {**state, which: map_coords(state[which], f)}

    progress = True
    while progress and calls < max_steps:
        progress = False
        seen = {(to_wkt(cur["a"]), to_wkt(cur["b"]))}
        for which, desc, cand in candidates(cur):
            key = (to_wkt(cand["a"]), to_wkt(cand["b"]))
            if key in seen:
                continue
            seen.add(key)
            if any(was_valid[k] and not _valid(cand[k]) for k in ("a", "b")):
                continue
            if calls >= max_steps:
                break
            calls += 1
            p = make(cand)
            if still_fails(p):
                cur = cand
                chain.append({"step": len(chain) + 1, "call": calls, "geom": which, "op": desc,
                              "vertices_a": nvert(cand["a"]), "vertices_b": nvert(cand["b"]),
                              "a": p.a, "b": p.b})
                progress = True
                break
    return make(cur), chain
