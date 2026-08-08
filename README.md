# AI SuperLig

Research repository for probabilistic prediction of the 2026-27 Turkish Super
Lig. The current scope is **Phase 0 and 0.1: source-data audit, contracts, and
source-backed review decisions**. No predictive model is implemented yet.

## Reproduce Phase 0

Create a Python environment, install the pinned lightweight dependencies, then
run the audit:

```powershell
python -m pip install -r requirements.txt
python scripts/run_data_audit.py
```

The second command is the single reproducibility command. It verifies immutable
raw-file checksums and locked schemas before regenerating every report and the
provisional data contract. If a raw file is absent, it attempts the catalogued
Football-Data HTTPS URL and refuses any response whose checksum differs from
the audited snapshot.

## Phase 0 outputs

- `reports/DATA_AUDIT.md`: answer-first audit and GO/NO-GO decision;
- `reports/schema_by_season.csv`: season-by-column schema matrix;
- `reports/missingness_by_season.csv`: column completeness evidence;
- `reports/teams_by_season.csv`: every distinct source team by season;
- `reports/PHASE0_REVIEW.md`: decisions for administrative results and aliases;
- `DATA_CONTRACT.md`: provisional normalized match and isolated market tables;
- `LEAKAGE_CONTRACT.md`: non-negotiable time and feature rules.

Additional CSVs preserve season summaries, odds coverage, approved aliases,
schema changes, source provenance, and reviewed administrative-result rows.
The audit fails if its detected candidate set diverges from the reviewed config.

## Git and CI

Work happens on short-lived branches and enters `main` through pull requests.
See `CONTRIBUTING.md` for the branch and commit convention. GitHub Actions
re-runs tests and the offline audit; deployment/CD is intentionally absent
until the project has a deployable live system.

## Source

The raw inputs are the Turkish league CSVs linked by
[Football-Data](https://www.football-data.co.uk/turkeym.php). Field meanings,
including the distinction between pre-closing odds and `C`-suffixed closing
odds, follow the provider's
[data notes](https://www.football-data.co.uk/notes.txt).
