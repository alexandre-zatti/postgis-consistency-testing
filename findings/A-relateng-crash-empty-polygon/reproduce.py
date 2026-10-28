# Family A: GEOS RelateNG crashes on a collection holding POLYGON EMPTY plus two polygons
# that touch at one point. Hand-made minimal input; provenance: family A findings, smallest
# shrunk key 924d7491356c. Each call runs in a child process, so this script survives the crash.
import subprocess, sys, shapely

CHILD = "import sys, shapely\nprint(shapely.relate(shapely.from_wkt(sys.argv[1]), shapely.from_wkt(sys.argv[2])))"
P1, P2 = "POLYGON ((0 0, 1 0, 0 1, 0 0))", "POLYGON ((0 0, -1 0, 0 -1, 0 0))"
P1r, P2r = "POLYGON ((1 0, 0 1, 0 0, 1 0))", "POLYGON ((-1 0, 0 -1, 0 0, -1 0))"  # same rings, start off (0 0)
T = "POLYGON ((2 2, 3 2, 2 3, 2 2))"  # a polygon disjoint from both
CASES = [
    ("with POLYGON EMPTY", f"GEOMETRYCOLLECTION (POLYGON EMPTY, {P1}, {P2})", "POINT (0 0)"),
    ("without the empty member", f"GEOMETRYCOLLECTION ({P1}, {P2})", "POINT (0 0)"),
    ("both rings start off the touch point", f"GEOMETRYCOLLECTION (POLYGON EMPTY, {P1r}, {P2r})", "POINT (0 0)"),
    ("other argument: disjoint polygon", f"GEOMETRYCOLLECTION (POLYGON EMPTY, {P1}, {P2})", T),
    ("same, first ring starts off the touch point", f"GEOMETRYCOLLECTION (POLYGON EMPTY, {P1r}, {P2})", T),
]


def relate(a, b):
    r = subprocess.run([sys.executable, "-s", "-c", CHILD, a, b], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else f"CRASH (exit code {r.returncode}, 0x{r.returncode & 0xFFFFFFFF:X})"


print("Shapely", shapely.__version__, "GEOS", shapely.geos_version_string)
res = {}
for name, a, b in CASES:
    res[name] = relate(a, b)
    print(f"{name}:\n  relate({a}, {b})\n  -> {res[name]}")
print("expected: no crash; the empty member changes nothing, so the first call should equal the second (FF20F1FF2)")
crash = res[CASES[0][0]].startswith("CRASH")
print("verdict:", "BUG reproduced, relate crashes the process" if crash else "not reproduced")
