"""Generator and shrinker self-check: python -m tavs.gen_check [n]"""

from __future__ import annotations

import re
import sys
import time
from collections import Counter

import numpy as np
import shapely

from . import gen
from .gen import ARMS, KINDS, coincidence_stats, generate, generate_all, make_pair, resample_stats
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
    print(f"shapely {shapely.__version__}, GEOS {shapely.geos_version_string}, n={n}, seed=1")
    print("paired design: one base pair per index; plain-int=base, degen-int=base+moves, "
          "plain-float=regime(base), degen-float=regime(base+moves)\n")
    for kind in KINDS:
        resample_stats(reset=True)
        t0 = time.perf_counter()
        rows = list(generate_all(1, n, kind))
        dt = time.perf_counter() - t0
        rs = resample_stats()[kind]
        print(f"#### kind={kind}: {1000 * dt / n:.2f} ms per index (all four arms)")
        print(f"  base resamples (shared by all arms): {(rs.get('resample_a', 0) + rs.get('resample_b', 0)) / (2 * n):.2%} "
              f"of geometries (a {rs.get('resample_a', 0)}, b {rs.get('resample_b', 0)}); "
              f"b centre near a {rs.get('b_near', 0) / n:.3f}")
        mv = {k: v for k, v in rs.items() if k.startswith("move_")}
        print(f"  degen arms: indices without any move {rs.get('degen_no_move', 0)}; move retries/not applicable: "
              + ", ".join(f"{k[5:]}={v}" for k, v in sorted(mv.items())))
        rg = {k: v for k, v in rs.items() if k.startswith("regime")}
        print(f"  float arms: regime retries/fallback/mix: " + ", ".join(f"{k}={v}" for k, v in sorted(rg.items())))
        forms = Counter(gen.parse_source(r["plain-int"].source)["form"] for r in rows)
        per_geom = Counter(f for r in rows for f in gen.parse_source(r["plain-int"].source)["form"].split("/"))
        print("  form mix per geometry: " + ", ".join(f"{k} {v / (2 * n):.3f}" for k, v in sorted(per_geom.items()))
              + "; per pair: " + ", ".join(f"{k} {v}" for k, v in forms.most_common()))
        cls = Counter("/".join("PLA"[int(shapely.get_dimensions(shapely.from_wkt(w)))] for w in (r["plain-int"].a, r["plain-int"].b))
                      for r in rows)
        print("  base classes (by dimension): " + ", ".join(f"{s} {c}" for s, c in sorted(cls.items())))
        moves = Counter(m for r in rows for m in r["degen-int"].moves)
        nmoves = Counter(len(r["degen-int"].moves) for r in rows)
        print("  moves: " + ", ".join(f"{m} {c}" for m, c in moves.most_common())
              + f"; per index {dict(sorted(nmoves.items()))}")

        # determinism and pairing checks
        again = list(generate_all(1, n, kind))
        same = all((r[a].a, r[a].b, r[a].moves, r[a].source) == (s[a].a, s[a].b, s[a].moves, s[a].source)
                   for r, s in zip(rows, again) for a in ARMS)
        short = list(generate_all(1, 50, kind))
        prefix = all(r[a].a == s[a].a and r[a].b == s[a].b for r, s in zip(rows, short) for a in ARMS)
        k = n - 1
        lone = all((make_pair(a, 1, kind, k).a, make_pair(a, 1, kind, k).b) == (rows[k][a].a, rows[k][a].b)
                   for a in ARMS)
        m = min(n, 100)
        via_generate = all(p.a == rows[i][a].a and p.b == rows[i][a].b
                           for a in ARMS for i, p in enumerate(generate(a, 1, m, kind)))
        plain_ok = degen_exact = degen_n = thin_ok = thin_n = thin_same = 0
        for r in rows:
            f = gen.regime_map(r["plain-float"].source)
            mapped = [gen.to_wkt(gen.apply_regime(gen.from_wkt(w, True), f)) for w in (r["plain-int"].a, r["plain-int"].b)]
            plain_ok += mapped == [r["plain-float"].a, r["plain-float"].b]
            src = gen.parse_source(r["degen-float"].source)
            f = gen.regime_map(r["degen-float"].source)
            mi = [gen.apply_regime(gen.from_wkt(w, True), f) for w in (r["degen-int"].a, r["degen-int"].b)]
            fl = [gen.from_wkt(w, False) for w in (r["degen-float"].a, r["degen-float"].b)]
            if "qk" not in src:
                degen_n += 1
                degen_exact += [gen.to_wkt(g) for g in mi] == [gen.to_wkt(g) for g in fl]
            else:
                # regime(degen-int) = degen-float except at the thin feature: the other geometry
                # is identical; the target keeps its structure and differs in at most the
                # 2 (spike) or 1 (sliver) vertices that carry the quantum width (0 when
                # k*ulp(M) equals the mapped integer width, e.g. ulp = 1 above 2^52)
                thin_n += 1
                t = 1 if src["thin_geom"] == "b" else 0
                other_same = gen.to_wkt(mi[1 - t]) == gen.to_wkt(fl[1 - t])
                vi, vf = gen.vertices(mi[t]), gen.vertices(fl[t])
                diff = sum(x != y for x, y in zip(vi, vf))
                limit = 2 if src["thin"] == "spike" else 1
                thin_ok += other_same and len(vi) == len(vf) and diff <= limit
                thin_same += diff == 0
        strip = lambda ms: [x.split("(")[0] for x in ms]
        shared_moves = sum(strip(r["degen-int"].moves) == strip(r["degen-float"].moves) for r in rows)
        reg = lambda src: {k2: v for k2, v in gen.parse_source(src).items() if k2 == "regime" or k2 in gen.REGIME_KEYS}
        same_regime = all(reg(r["plain-float"].source) == reg(r["degen-float"].source) for r in rows)
        print(f"  determinism: rerun {'ok' if same else 'FAIL'}; n=50 prefix {'ok' if prefix else 'FAIL'}; "
              f"lone index {k} {'ok' if lone else 'FAIL'}; generate(arm) = generate_all[arm] (first {m}) "
              f"{'ok' if via_generate else 'FAIL'}")
        print(f"  pairing: plain-float = regime(plain-int) {plain_ok}/{n}; degen-float = regime(degen-int) "
              f"{degen_exact}/{degen_n} (no sliver/spike); equal except the quantum thin feature {thin_ok}/{thin_n} "
              f"(of which {thin_same} identical: quantum = mapped 1 unit); "
              f"degen arms share moves {shared_moves}/{n}; float arms share regime {'ok' if same_regime else 'FAIL'}")
        qs = {k2: v for k2, v in rs.items() if k2.startswith(("thin:", "quantum"))}
        print("  quantum slivers/spikes: " + ", ".join(f"{k2}={v}" for k2, v in sorted(qs.items()))
              + f"  (k retries per thin index {rs.get('quantum_invalid_retry', 0) / max(1, thin_n):.3f})")
        for a in ("plain-float", "degen-float"):
            tr = [r[a] for r in rows if gen.parse_source(r[a].source)["regime"].startswith("translate")]
            def integral(p):
                c = np.concatenate([shapely.get_coordinates(shapely.from_wkt(w)).ravel() for w in (p.a, p.b)])
                return bool(np.all(np.floor(c) == c) and np.all(np.abs(c) < 2 ** 53))
            with_thin = [p for p in tr if "qk" in gen.parse_source(p.source)]
            without = [p for p in tr if "qk" not in gen.parse_source(p.source)]
            print(f"  integrality, {a}, translation regime: all coordinates integral and < 2^53 in "
                  f"{sum(map(integral, without))}/{len(without)} pairs without a quantum feature, "
                  f"{sum(map(integral, with_thin))}/{len(with_thin)} with one")

        print(f"  {'arm':12s} {'coords':6s} {'exact':>6s} {'near1e-9':>8s} {'near4ulp':>8s} "
              f"{'shared':>6s} {'v-on-e':>6s} {'colin':>6s} {'self':>6s} {'touch0':>6s} {'inters':>6s} {'empty':>6s}  ms/pair(cs)")
        for a in ARMS:
            pairs = [r[a] for r in rows]
            t1 = time.perf_counter()
            cs = coincidence_stats(pairs)
            dc = time.perf_counter() - t1
            print(f"  {a:12s} {check_coords(pairs):6s} {cs['any_exact']:6.3f} {cs['near_rel_1e-9']:8.3f} "
                  f"{cs['near_4ulp']:8.3f} {cs['shared_vertex']:6.3f} {cs['vertex_on_edge']:6.3f} "
                  f"{cs['collinear_overlap']:6.3f} {cs['self_touch']:6.3f} {cs['touch_point_only']:6.3f} "
                  f"{cs['intersects']:6.3f} {cs['has_empty_part']:6.3f}  {1000 * dc / n:.2f}")
        for a in ("plain-float", "degen-float"):
            by = {}
            for r in rows:
                by.setdefault(gen.parse_source(r[a].source)["regime"], []).append(r[a])
            print(f"  {a} by regime: " + "; ".join(
                f"{g} (n={len(ps)}) exact {cs['any_exact']:.3f} near1e-9 {cs['near_rel_1e-9']:.3f} near4ulp {cs['near_4ulp']:.3f}"
                for g, ps in sorted(by.items()) for cs in [coincidence_stats(ps)]))
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
