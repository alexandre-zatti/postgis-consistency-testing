import subprocess, sys

PY = sys.executable
A = "MULTIPOLYGON (((164484 439560, 164431 439492, 164415 439458, 164484 439560)))"
P1 = "POLYGON ((164444 439544, 164448 439550, 164449 439556, 164444 439544))"
P2 = "POLYGON ((164449 439556, 164451 439558, 164452 439556, 164449 439556))"
P2rot = "POLYGON ((164451 439558, 164452 439556, 164449 439556, 164451 439558))"
P1rot = "POLYGON ((164449 439556, 164444 439544, 164448 439550, 164449 439556))"
cases = {
    "base": f"GEOMETRYCOLLECTION (POLYGON EMPTY, {P1}, {P2})",
    "P2 starts off the touch point": f"GEOMETRYCOLLECTION (POLYGON EMPTY, {P1}, {P2rot})",
    "both start off... P1 starts at touch, P2 off": f"GEOMETRYCOLLECTION (POLYGON EMPTY, {P1rot}, {P2rot})",
}
child = (
    "import sys, shapely\n"
    "a = shapely.from_wkt(sys.argv[1]); b = shapely.from_wkt(sys.argv[2])\n"
    "print(shapely.relate(a, b), shapely.intersects(a, b))\n"
)
for name, b in cases.items():
    r = subprocess.run([PY, "-s", "-c", child, A, b], capture_output=True, text=True)
    out = r.stdout.strip() or f"exit {r.returncode}"
    print(f"{name}: {out}")
