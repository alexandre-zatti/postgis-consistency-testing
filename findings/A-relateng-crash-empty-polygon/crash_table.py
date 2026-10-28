import subprocess, sys, shapely
W = sys.argv[1]
A = "MULTIPOLYGON (((164484 439560, 164431 439492, 164415 439458, 164484 439560)))"
P1 = "POLYGON ((164444 439544, 164448 439550, 164449 439556, 164444 439544))"
P2 = "POLYGON ((164449 439556, 164451 439558, 164452 439556, 164449 439556))"
P2x = "POLYGON ((164450 439557, 164451 439559, 164452 439557, 164450 439557))"
assert shapely.from_wkt(P1).touches(shapely.from_wkt(P2))
assert shapely.from_wkt(P1).disjoint(shapely.from_wkt(P2x))
V = [
    ("base: A=MULTIPOLYGON, B=GC(POLYGON EMPTY, P1, P2)", A, f"GEOMETRYCOLLECTION (POLYGON EMPTY, {P1}, {P2})"),
    ("drop third member P2", A, f"GEOMETRYCOLLECTION (POLYGON EMPTY, {P1})"),
    ("break the touch (P2 moved off P1)", A, f"GEOMETRYCOLLECTION (POLYGON EMPTY, {P1}, {P2x})"),
    ("POLYGON EMPTY -> POINT EMPTY", A, f"GEOMETRYCOLLECTION (POINT EMPTY, {P1}, {P2})"),
    ("POLYGON EMPTY -> MULTIPOLYGON EMPTY", A, f"GEOMETRYCOLLECTION (MULTIPOLYGON EMPTY, {P1}, {P2})"),
    ("EMPTY member last", A, f"GEOMETRYCOLLECTION ({P1}, {P2}, POLYGON EMPTY)"),
    ("no EMPTY member", A, f"GEOMETRYCOLLECTION ({P1}, {P2})"),
    ("swap argument order (B, A)", f"GEOMETRYCOLLECTION (POLYGON EMPTY, {P1}, {P2})", A),
    ("A as POLYGON", A.replace("MULTIPOLYGON (((", "POLYGON ((").replace(")))", "))"), f"GEOMETRYCOLLECTION (POLYGON EMPTY, {P1}, {P2})"),
]
FNS = ["relate", "intersects", "contains", "covers", "prepared_intersects"]
print("| variant | " + " | ".join(FNS) + " |")
print("|---|" + "---|" * len(FNS))
for name, a, b in V:
    cells = []
    for fn in FNS:
        r = subprocess.run([sys.executable, W + "/crash_one.py", fn, a, b], capture_output=True, text=True)
        if r.returncode == 0:
            cells.append(r.stdout.strip())
        else:
            err = (r.stderr.strip().splitlines() or [""])[-1][:60]
            cells.append(f"exit {r.returncode}" + (f" ({err})" if err else ""))
    print(f"| {name} | " + " | ".join(cells) + " |")
