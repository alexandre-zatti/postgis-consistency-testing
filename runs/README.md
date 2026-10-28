# Runs

Every run's raw results and summaries, exactly as produced. Nothing here was edited by hand.
Superseded and failed runs are kept, because they document how the checks changed.

| Folder or file | Step | Contents |
|---|---|---|
| `e1/` | E1 calibration, **primary** (checks frozen at commit 23761b7) | `summary.md` (read this first), `seeds.csv` (per known bug), `xml.csv` (GEOS test suite), `tavs.sqlite` (all outcomes), `batch_plan.json` (index-join query plan), `code_commit.txt`, `wall.txt` |
| `e1-freeze1/` | first E1 run with frozen checks (commit 45d9b93), superseded by the line-overlay amendment | same layout |
| `e1-prefreeze/` | last E1 run before the freeze; drove the dated amendments | same layout |
| `e1-first/`, `e1-second-superseded/` | first E1 runs during development | same layout |
| `smoke/` | test run of the campaign runner before E2 (two lanes, seeds 100 and 2, 20 indices per kind) | same layout as `e2/` |
| `e2/` | E2 pilot: 1,000 ordinary whole-number pairs | `campaign.json` (parameters), `lane0.sqlite` (results), `progress.log`, `lane0.out` |
| `e3/` | E3 main run: 640,000 pairs on 5 lanes | `campaign.json`, `progress.log`, `laneN.out`, `laneN_batch_plan.json`; the five `laneN.sqlite` (2.1 GB) are in the GitHub release, fetched by `scripts/fetch_e3_data.py` |
| `e3/analysis/` | E3 analysis | `summary.txt` (read this first), `analysis.json` (every number) |
| `e3/triage/` | E4 triage | `summary.txt`, `selection.json` (groups and representatives), `findings.json` (399 findings, full inputs), `findings.csv` (same, inputs cut at about 200 characters), `families.csv` (final family and class), `shrinks/` (one shrink history per representative), `reruns/` (each finding on three versions and in Shapely) |
| `e3_console.txt` | E3 runner console, first part (stopped by the low-memory guard) | |
| `e3_triage_console_run1.txt` | first triage attempt, with the crash-replay bug | |
| `e3_triage_console.txt` | triage console after the fix | |

## Inside the SQLite files

Each `lane*.sqlite` (and `tavs.sqlite` in the E1 folders) has these main tables:

| Table | One row per |
|---|---|
| `pairs` | generated shape pair (WKT of both shapes, arm, coordinates, moves applied) |
| `campaign_pairs` | (seed, kind, index, arm) done in a campaign, linking to `pairs` |
| `violations` | check that failed on a pair: check code, sub-check, function, tier, magnitude, band |
| `outcomes` | non-violation event: crash, timeout, overlay error, not applicable |

Open them with any SQLite browser, or from Python with `sqlite3`.
