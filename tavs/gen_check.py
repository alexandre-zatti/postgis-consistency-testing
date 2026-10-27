"""Generator and shrinker self-check: python -m tavs.gen_check [n]"""

from __future__ import annotations

import re
import sys
import time
from collections import Counter

import shapely

from . import gen
from .gen import ARMS, KINDS, coincidence_stats, generate, make_pair, resample_stats, type_signature
from .shrink import shrink

NUM = re.compile(r"-?\d+(?:\.\d*)?(?:[eE][-+]?\d+)?")


def check_coords(pairs) -> str:
    bad = 0
    for p in pairs:
        for w in (p.a, p.b):
            for tok in NUM.findall(w):
                if p.coord == "int":
                    if not re.fullmatch(r"\d+", tok) or not (0 <= int(tok) <= 2 ** 20):
                        bad += 1
                else:
                    if repr(float(tok)) != tok:
                        bad += 1
            # emitted text is exactly what the internal form writes after a Shapely round trip
            if gen.to_wkt(gen.from_wkt(w, p.coord == "int")) != w:
                bad += 1
    return "ok" if bad == 0 else f"FAIL ({bad} bad tokens/round trips)"


def main(n: int = 1000) -> None:
    print(f"shapely {shapely.__version__}, GEOS {shapely.geos_version_string}, n={n}, seed=1\n")
    for kind in KINDS:
        for arm in ARMS:
            resample_stats(reset=True)
            t0 = time.perf_counter()
            pairs = list(generate(arm, 1, n, kind))
            dt = time.perf_counter() - t0
            rs = resample_stats()[f"{arm}/{kind}"]
            draws = rs["pairs"] + rs.get("resample_a", 0) + rs.get("resample_b", 0)
            t1 = time.perf_counter()
            cs = coincidence_stats(pairs)
            dc = time.perf_counter() - t1
            sigs = Counter(type_signature(p) for p in pairs)
            moves = Counter(m for p in pairs for m in p.moves)
            nmoves = Counter(len(p.moves) for p in pairs)
            # determinism
            again = list(generate(arm, 1, n, kind))
            same = all((p.a, p.b, p.moves) == (q.a, q.b, q.moves) for p, q in zip(pairs, again))
            short = list(generate(arm, 1, 50, kind))
            prefix = all((p.a, p.b, p.moves) == (q.a, q.b, q.moves) for p, q in zip(pairs, short))
            k = n - 1
            lone = make_pair(arm, 1, kind, k)
            single = (lone.a, lone.b, lone.moves) == (pairs[k].a, pairs[k].b, pairs[k].moves)
            print(f"== {arm} / {kind}")
            print(f"  generation {1000 * dt / n:.2f} ms/pair; coincidence measure {1000 * dc / n:.2f} ms/pair")
            print(f"  base-geometry resample rate {(draws - rs['pairs']) / (rs['pairs'] * 2):.2%} "
                  f"of geometries (a {rs.get('resample_a', 0)}, b {rs.get('resample_b', 0)}); "
                  f"pair resamples (no move applied) {rs.get('resample_pair_no_move', 0)}; "
                  f"b centre near a {rs.get('b_near', 0) / rs['pairs']:.3f}")
            mv = {k2: v for k2, v in rs.items() if k2.startswith(("move_", "float_"))}
            if mv:
                print("  move retries/not applicable: " + ", ".join(f"{k2.removeprefix('move_')}={v}" for k2, v in sorted(mv.items())))
            cls = Counter("/".join("PLA"[int(shapely.get_dimensions(shapely.from_wkt(w)))] for w in (p.a, p.b))
                          for p in pairs)
            print("  classes (by dimension): " + ", ".join(f"{s} {c}" for s, c in sorted(cls.items())))
            print("  types: " + ", ".join(f"{s} {c}" for s, c in sigs.most_common()))
            if moves:
                print("  moves: " + ", ".join(f"{m} {c}" for m, c in moves.most_common())
                      + f"; per pair {dict(sorted(nmoves.items()))}")
            print("  coincidence rates: " + ", ".join(f"{k2} {v:.3f}" for k2, v in cs.items() if k2 != "n"))
            print(f"  coordinates: {check_coords(pairs)}; determinism: rerun {'ok' if same else 'FAIL'}, "
                  f"n=50 prefix {'ok' if prefix else 'FAIL'}, lone index {k} {'ok' if single else 'FAIL'}")
            print()

    print("== shrinker self-check")
    calls = Counter()

    def fails_vertices(p):
        calls["v"] += 1
        a, b = shapely.from_wkt(p.a), shapely.from_wkt(p.b)
        return shapely.get_num_coordinates(a) > 4 and a.intersects(b)

    for arm, kind in (("degen-int", "predicate"), ("plain-float", "overlay"), ("degen-float", "predicate")):
        for p in generate(arm, 1, 400, kind):
            if fails_vertices(p) and gen.nvert(gen.from_wkt(p.a, p.coord == "int")) >= 12 \
                    and gen.nvert(gen.from_wkt(p.b, p.coord == "int")) >= 6:
                break
        calls.clear()
        before = (gen.nvert(gen.from_wkt(p.a, p.coord == "int")), gen.nvert(gen.from_wkt(p.b, p.coord == "int")))
        small, chain = shrink(p, fails_vertices)
        after = (gen.nvert(gen.from_wkt(small.a, p.coord == "int")), gen.nvert(gen.from_wkt(small.b, p.coord == "int")))
        ok = fails_vertices(small)
        print(f"  [{arm}/{kind} #{p.index}] 'a has >4 vertices and intersects b': vertices a,b {before} -> {after}; "
              f"{len(chain)} accepted steps, {calls['v'] - 1} oracle calls; still fails: {ok}")
        print(f"    ops: {Counter(s['op'].split(' ')[0] + ' ' + s['op'].split(' ')[1] for s in chain)}")
        print(f"    a: {small.a[:160]}")
        print(f"    b: {small.b[:160]}")

    # rounding on a float pair
    for p in generate("plain-float", 1, 200, "overlay"):
        if shapely.from_wkt(p.a).intersects(shapely.from_wkt(p.b)):
            break
    calls.clear()

    def fails_intersects(p):
        calls["v"] += 1
        return shapely.from_wkt(p.a).intersects(shapely.from_wkt(p.b))

    small, chain = shrink(p, fails_intersects)
    print(f"  [plain-float/overlay #{p.index}] 'a intersects b': {len(chain)} steps, {calls['v']} calls; "
          f"ops {Counter(s['op'].split(' ')[0] for s in chain)}")
    print(f"    a: {small.a}")
    print(f"    b: {small.b}")
    budget_calls = Counter()

    def never(p):
        budget_calls["v"] += 1
        return False

    shrink(p, never, max_steps=200)
    print(f"  budget: an oracle that never fails was called {budget_calls['v']} times (cap 200)")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 1000)
