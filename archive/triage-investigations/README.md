# Triage investigations (exploratory scripts, kept as provenance)

These are the throwaway scripts used on 2026-10-27 and 2026-10-28 to find the root cause of each
finding family after triage. They are kept so every classification in
[docs/04-results.md](../../docs/04-results.md) can be traced. They are **not** polished tools.
They ran from a scratch folder and contain absolute Windows paths from the original machine. To
rerun one, change the paths at the top of the script to your copy of `runs/e3/triage/`.

| Folder | Question | Key scripts |
|---|---|---|
| `crash/` | Are all 254 crash findings one defect, and what triggers it? | `precond.py`, `precond2.py` (which members are needed), `synth.py`, `synth2.py` (synthetic minimal inputs), `t_forms.py` (call forms), `child.py`, `lib.py` (crash-safe subprocess calls); `crash.json`, `crash_f.json`, `run1.json` are their outputs |
| `predicate/` | Which answer is right in the R2, R3 and R4 findings, and why do the paths disagree? | `exact.py`, `r2exact.py`, `r4exact.py` (exact rational arithmetic), `r3.py`, `r3b.py`, `r3float.py`, `r2force.py`, `old.py` (old-version status) |
| `overlay/` | Are the R5, R10 and R11 flags defects or rounding? | `exact.py`, `nodecheck.py` (exact noding checks), `r10poly.py`, `r10line.py`, `r10mech.py`, `sliver.py`, `r5.py`, `exact_collinear_overlap.py` (no line pair has an exactly collinear overlap) |

The conclusions are summarised in the protocol, [docs/experiment-plan.md](../../docs/experiment-plan.md),
in the sections "Crash family", "Overlay families" and "Predicate families".
