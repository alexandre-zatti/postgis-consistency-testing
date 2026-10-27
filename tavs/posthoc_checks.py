"""Advisor checks on E3: R3 harness checks, R10/R11 mechanism split, four contrasts, post-hoc sensitivity."""
import glob, json, sqlite3, sys
from collections import Counter, defaultdict
from scipy.stats import wilcoxon

camp = sys.argv[1]
SEEDS = None


def gtype(wkt):
    t = (wkt or "").lstrip().split("(")[0].split(" ")[0].upper()
    if "LINE" in t:
        return "L"
    if "POLYGON" in t:
        return "A"
    if "POINT" in t:
        return "P"
    return "G"


def regime(src):
    return next((t.split("=")[1] for t in (src or "").split(";") if t.startswith("regime=")), "?")


def mvset(moves):
    return "+".join(sorted({m.split("(")[0] for m in json.loads(moves or "[]")})) or "-"


r3 = Counter(); r3_moves = Counter(); r3_crashed = 0; r3_elem1 = Counter(); r3_pairs = set()
r11 = defaultdict(Counter); r11_pairs = set(); r10 = defaultdict(Counter); r10_pairs = set()
r10_sub = Counter(); r10_reg = Counter(); r11_reg = Counter()
explain = {}
for f in sorted(glob.glob(f"{camp}/lane*.sqlite")):
    lane = f.split("lane")[-1].split(".")[0]
    pf = f"{camp}/lane{lane}_batch_plan.json"
    try:
        explain[lane] = json.load(open(pf, encoding="utf-8")).get("index_used")
    except OSError:
        explain[lane] = "missing"
    c = sqlite3.connect(f)
    q = ("SELECT v.rule, v.sub, v.function, v.orientation, v.band, v.tier, v.raw, p.pair_id, p.arm, "
         "p.a, p.b, p.moves, p.source, cp.crash_events FROM violations v JOIN pairs p USING(pair_id) "
         "JOIN campaign_pairs cp USING(pair_id)")
    for rule, sub, fn, o, band, tier, raw, pid, arm, a, b, moves, src, ce in c.execute(q):
        key = (lane, pid)
        types = "".join(sorted(gtype(a) + gtype(b)))
        if rule == "R3":
            r3[(arm, fn, sub)] += 1
            r3_moves[(arm, mvset(moves))] += 1
            r3_pairs.add(key)
            if ce:
                r3_crashed += 1
            rw = json.loads(raw or "{}")
            calls, lone = rw.get("calls"), rw.get("lone")
            if calls and lone is not None:
                r3_elem1["elem1==lone" if calls[0] == lone else "elem1!=lone"] += 1
            else:
                r3_elem1["no lone/calls"] += 1
        elif rule == "R11" and band == "triage":
            r11[arm][types] += 1
            r11_pairs.add(key)
            if arm == "degen-float":
                r11_reg[(regime(src), types)] += 1
        elif rule == "R10":
            r10[arm][types] += 1
            r10_pairs.add(key)
            r10_sub[(arm, sub)] += 1
            if arm == "degen-float":
                r10_reg[(regime(src), types)] += 1
    c.close()

print("== EXPLAIN index_used per lane:", explain)
print("== R3 violations by (arm, function, shape):")
for k, v in sorted(r3.items()):
    print("  ", v, k)
print("== R3 by (arm, move set), top 15:")
for k, v in r3_moves.most_common(15):
    print("  ", v, k)
print("== R3 violations on pairs with crash events:", r3_crashed)
print("== R3 element 1 vs lone (flagged rows):", dict(r3_elem1))
print("== R11 triage violations by arm, type pair (A=area L=line P=point):")
for arm, cnt in r11.items():
    print("  ", arm, dict(cnt))
print("== R11 triage degen-float by (regime, types):", dict(r11_reg))
print("== R10 violations by arm, type pair:")
for arm, cnt in r10.items():
    print("  ", arm, dict(cnt))
print("== R10 by (arm, sub):", dict(r10_sub))
print("== R10 degen-float by (regime, types):", dict(r10_reg))
print(f"== pair overlap: R10 pairs {len(r10_pairs)}, R11-triage pairs {len(r11_pairs)}, both {len(r10_pairs & r11_pairs)}")
