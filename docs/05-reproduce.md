# 5. How to reproduce

There are three levels. Each one needs more setup than the one before. Pick the level that
answers your question.

| Level | What you get | Needs |
|---|---|---|
| 1. See the problems | each problem family shown in seconds | Python + Shapely |
| 2. Recompute every number | all tables in [04-results.md](04-results.md) from the stored data | Python, 2.5 GB disk |
| 3. Rerun the experiments | new runs from scratch, compared with ours | Python, Docker, several GB of RAM |

The experiments ran on Windows 11 with Python 3.14.7 and Docker Desktop. Linux and macOS
should work but were not tested.

## Setup (all levels)

```bash
git clone https://github.com/alexandre-zatti/postgis-consistency-testing.git
cd postgis-consistency-testing
python -m venv .venv
# Windows:      .venv\Scripts\activate
# Linux/macOS:  source .venv/bin/activate
pip install -r requirements.txt
```

Use Python 3.14. The data download script uses `compression.zstd`, which is new in 3.14. All
commands below run from the repository root, with the virtual environment active.

## Level 1: see the problems

```bash
python findings/A-relateng-crash-empty-polygon/reproduce.py
python findings/B-prepared-contains-empty-member/reproduce.py
# ... one folder per family; see findings/README.md
```

Each folder also has the same check as SQL (`reproduce.sql`) and the output we observed
(`expected_output.txt`). **Warning:** the SQL in folder A crashes the PostgreSQL server process.
Run it only on a throwaway container, never on a database you care about.

## Level 2: recompute every number

The main run's raw results are five SQLite databases, 2.1 GB in total. They are too big for Git,
so they are attached to the GitHub release `e3-data-v1` as compressed files (296 MB).

```bash
python scripts/fetch_e3_data.py
```

This uses the GitHub CLI (`gh auth login` first), because the repository is private. As an
alternative, download the six release files in the browser and run
`python scripts/fetch_e3_data.py --from-dir <download folder>`. The script checks every file
against its SHA-256 hash and unpacks it into `runs/e3/`.

Then run:

```bash
python -s -m tavs.analysis --campaign e3     # primary measure and contrasts -> runs/e3/analysis/
python -s -m tavs.posthoc runs/e3            # exploratory: all four contrasts and the breakdown
python -s -m tavs.posthoc_checks runs/e3     # exploratory: harness checks and mechanism splits
python -s -m tavs.families runs/e3           # final family per finding -> runs/e3/triage/families.csv
git status runs/                             # the rewritten files should be unchanged
```

The calibration and pilot results (`runs/e1`, `runs/e2`) are small and already in the
repository.

## Level 3: rerun the experiments

Install Docker, then start the three pinned PostGIS versions. Always use the project name
`tavs`:

```bash
docker compose -p tavs up -d    # current on port 54336, development 54337, old 54335
```

**Calibration (E1).** It took about 80 seconds here. It rewrites `runs/e1/`, so `git diff runs/e1`
shows any difference from our run.

```bash
python -s -m tavs.e1
```

**Pilot (E2).** Use a new campaign name. A campaign whose folder already exists resumes
instead of starting over. The generator is seeded, so your pairs are the same as ours.

```bash
python -s -m tavs.campaign run --campaign e2-rerun --seeds 100 --kinds predicate overlay --n 500 --arms plain-int --lanes 1
python -s -m tavs.analysis --campaign e2-rerun
```

**Main run (E3).** The runner starts its own throwaway databases (`compose.lanes.yaml`, Docker
project `tavs-lanes`, ports 54340 and up). It checks free memory first, and needs about 3.5 GB
for 5 lanes. The awkward arms crash PostgreSQL on purpose. The runner records each crash,
reconnects and continues. A small slice, one seed and 500 indices per kind:

```bash
python -s -m tavs.campaign run --campaign e3-small --seeds 101 --kinds predicate overlay --n 500 --lanes 2
python -s -m tavs.analysis --campaign e3-small
```

The full run took about 2¾ hours on our 14-thread laptop:

```bash
python -s -m tavs.campaign run --campaign e3-rerun --seeds 101-110 --kinds predicate overlay --n 8000 --lanes 5
python -s -m tavs.analysis --campaign e3-rerun
python -s -m tavs.campaign down                # removes the lane containers
```

An interrupted run continues where it stopped if you repeat the same command.

**Triage (E4).** Triage starts its own throwaway containers for crash replays (`tavs-triage-*`)
and removes them at the end. It is the slowest step.

```bash
python -s -m tavs.triage --campaign e3-rerun --cap 400
python -s -m tavs.families runs/e3-rerun
```

`families.py` assigns families by the rules fixed for our findings. On a different run, new kinds
of finding stop it with "unclassified finding", which is the intended behaviour.

**Generator self-check:** `python -s -m tavs.gen_check 200` prints the arms' shape statistics.

**Cleanup:**

```bash
docker compose -p tavs down -v
```

## What to compare

| Output | Our value | File |
|---|---|---|
| Calibration, as pre-registered | 4 of 12 | `runs/e1/summary.md` |
| False alarms on GEOS test pairs | 0 of 964 | `runs/e1/summary.md` |
| Pilot violations | 0 of 1,000 | `runs/e2/` |
| Main run, pairs | 640,000, 0 harness errors | `runs/e3/analysis/summary.txt` |
| Violating pairs per arm | 0 / 29 / 146 / 5,492 | same |
| Crash events | 677 in 176 pairs | same |
| Triage | 400 representatives, all reproduce, 399 unique | `runs/e3_triage_console.txt` |

Timing-dependent numbers (pairs per hour, crash recovery time) will differ on your machine. The
violations should not, because every pair is generated from its seed.
