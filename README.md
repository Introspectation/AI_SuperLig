# AI SuperLig

Research repository for probabilistic prediction of the 2026-27 Turkish Super
Lig. The audited data foundation is complete, and modeling has progressed
through leakage-safe naive baselines to a Stage 4 independent Poisson
development benchmark. No production or live model exists yet.

The current season is not treated as a frozen one-time download. See
`CURRENT_SEASON_DATA.md` for immutable refresh, promotion, and pre-prediction
freshness gates.

## Reproduce the data foundation

Create a Python environment, install the pinned lightweight dependencies, then
run the complete offline pipeline:

```powershell
python -m pip install -r requirements.txt
python scripts/run_data_foundation.py
```

The second command is the single reproducibility command. It verifies immutable
raw-file checksums and locked schemas, regenerates the Phase 0 audit, then
rebuilds the canonical and market tables. Normal builds are offline and fail
loudly if a source snapshot, reviewed discrepancy, or expected schema changes.

Source acquisition is intentionally separate from normal builds. The committed
Football-Data snapshots can be restored by the Phase 0 audit from their
catalogued checksums. The official TFF kickoff snapshot can be recreated only
into an empty raw-data target with:

```powershell
python scripts/bootstrap_tff_kickoffs.py
```

The bootstrap records every source URL, response checksum, and byte count in an
immutable manifest and refuses to overwrite an existing snapshot.

## Phase 0 outputs

- `reports/DATA_AUDIT.md`: answer-first audit and GO/NO-GO decision;
- `reports/current_season_snapshot_audit.csv`: capture age, coverage, and source-revision evidence;
- `reports/schema_by_season.csv`: season-by-column schema matrix;
- `reports/missingness_by_season.csv`: column completeness evidence;
- `reports/teams_by_season.csv`: every distinct source team by season;
- `reports/PHASE0_REVIEW.md`: decisions for administrative results and aliases;
- `DATA_CONTRACT.md`: normalized match and isolated market table contracts;
- `LEAKAGE_CONTRACT.md`: non-negotiable time and feature rules.

Additional CSVs preserve season summaries, odds coverage, approved aliases,
schema changes, source provenance, and reviewed administrative-result rows.
The audit fails if its detected candidate set diverges from the reviewed config.

## Canonical outputs

- `data/processed/canonical_matches.csv`: one traceable match row with kickoff,
  conservative result availability, on-pitch score targets, eligibility, and
  Football-Data lineage;
- `data/processed/market_benchmark.csv`: de-vigged H/D/A closing probabilities,
  kept physically and logically separate from predictive features;
- `reports/CANONICAL_DATA_AUDIT.md`: coverage, exclusions, reviewed source
  conflicts, and the canonical-build verdict;
- `reports/canonical_data_quality_by_season.csv`: per-season eligibility,
  kickoff, and market coverage;
- `reports/tff_kickoff_join_audit.csv`: auditable 2017-19 TFF join evidence;
- `MODEL_DESIGN.md`: deferred design for the dynamic promoted-team prior.

The audited Football-Data kickoff values from 2019-20 onward are interpreted as
UK-clock time after exact summer and winter cross-checks against TFF. The build
converts them from `Europe/London` to `Europe/Istanbul`, including daylight
saving changes. The 2017-18 and 2018-19 gaps are backfilled from committed
official TFF archive snapshots. The primary market benchmark uses closing
market-average odds from 2019-20 onward; the earlier Pinnacle closing odds are
retained as a clearly labelled secondary regime rather than mixed into the
primary benchmark.

Future evaluation code must obtain visible historical outcomes through
`scripts/evaluation_time.py`, which enforces the strict availability boundary
and rejects timezone-naive prediction timestamps.

## Reproduce the first baselines

Run the complete offline foundation and chronological baseline evaluation with:

```powershell
python scripts/run_baseline_evaluation.py
```

This creates per-match development predictions, aggregate metrics, and
`reports/BASELINE_REPORT.md`. The split is frozen in
`config/evaluation_splits.csv`: 2021-22 through 2024-25 are walk-forward
development seasons, while 2025-26 remains a sealed final holdout. See
`EVALUATION_PROTOCOL.md` for metric definitions and leakage rules, and
`ROADMAP.md` for the ordered path to the 2026-27 prediction runner.

## Reproduce the independent Poisson model

Run the foundation, the naive baselines, and the Stage 4 independent Poisson
walk-forward evaluation with:

```powershell
python scripts/run_poisson_evaluation.py
```

This regenerates the baseline outputs, then writes per-match Poisson
predictions, metrics, and `reports/POISSON_REPORT.md` under the same frozen
split. The model specification is recorded in `MODEL_DESIGN.md`.

## Reproduce the time-decayed Dixon-Coles model

Run every earlier stage plus the Stage 5 walk-forward decay grid, nested
chronological decay selection, and ablations with:

```powershell
python scripts/run_dixon_coles_evaluation.py
```

This writes `reports/DIXON_COLES_REPORT.md`, per-match predictions, metrics,
per-season grid metrics, and the decay selection table. The selection rule is
in `EVALUATION_PROTOCOL.md`.

## Reproduce the dynamic promoted-team prior

Run every earlier stage plus the Stage 6 promoted-team prior, its nested `k`
selection, and ablations with:

```powershell
python scripts/run_promoted_prior_evaluation.py
```

This writes `reports/PROMOTED_PRIOR_REPORT.md`, per-match predictions, metrics,
the `k` grid, the `k` selection table, and the prior offsets. CI runs this
command and verifies that every committed output reproduces. The design is in
`MODEL_DESIGN.md`.

Before any future live forecast, run the age-and-coverage gate documented in
`CURRENT_SEASON_DATA.md`. A successful offline build alone does not mean the
upstream current-season source is fresh.

## Git and CI

Work happens on short-lived branches and enters `main` through pull requests.
See `CONTRIBUTING.md` for the branch and commit convention. GitHub Actions
re-runs tests and the complete offline data foundation; deployment/CD is
intentionally absent until the project has a deployable live system.

## Source

The raw inputs are the Turkish league CSVs linked by
[Football-Data](https://www.football-data.co.uk/turkeym.php). Field meanings,
including the distinction between pre-closing odds and `C`-suffixed closing
odds, follow the provider's
[data notes](https://www.football-data.co.uk/notes.txt).

Official kickoff backfill and reviewed administrative results are sourced from
the [Turkish Football Federation](https://www.tff.org/). Exact page URLs and
checksums are preserved in the raw manifest and review-source configuration.
