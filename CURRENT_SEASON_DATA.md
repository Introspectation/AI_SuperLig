# Current-season data operations

The 2026-27 season is a live, revisable source rather than a one-time historical
file. Every acquisition is stored under a timestamped, checksum-bearing path.
An older raw file is never edited, replaced, or deleted.

## Current status

The active snapshot was captured on 13 September 2026 but contains 36 results
only through 7 September 2026. This is valid audit evidence and an explicit
freshness warning. It is not sufficient for a forecast that expects matches
completed through 13 September.

## Acquire and promote a refresh

GitHub Actions checks Football-Data every day at 05:30 Europe/Istanbul and can
also be started manually:

```powershell
gh workflow run bootstrap-football-data.yml --ref main
gh run list --workflow bootstrap-football-data.yml --limit 3
gh run watch RUN_ID
gh run download RUN_ID --name football-data-superlig-2017-2027 --dir tmp/current-season
```

Inspect the run's artifact metadata and then promote only if the source covers
the latest completed match date required by the forecast:

```powershell
gh api repos/Introspectation/AI_SuperLig/actions/runs/RUN_ID/artifacts

python scripts/promote_current_season_snapshot.py `
  --input tmp/current-season/data/raw/football_data/2026-27.csv `
  --captured-at 2026-09-14T05:30:00Z `
  --required-through 2026-09-13 `
  --acquisition-run-url https://github.com/Introspectation/AI_SuperLig/actions/runs/RUN_ID `
  --artifact-name football-data-superlig-2017-2027 `
  --artifact-digest sha256:ARTIFACT_DIGEST

python scripts/run_data_foundation.py
```

Promotion fails before writing anything when the response is not a CSV, the
schema changes, match keys duplicate, row/date coverage regresses, or the
candidate does not reach `--required-through`. A successful promotion appends
`config/current_season_snapshots.csv`, writes a new immutable raw file, and
leaves schema-lock changes for explicit review.

The scheduled workflow only creates a short-lived acquisition artifact. It
does not push to `main`; promotion, generated-report review, checkpoint commit,
pull request, and CI remain deliberate maintainer actions.

## Pre-prediction gate

Every live forecast must pass both acquisition-age and result-coverage checks:

```powershell
python scripts/check_current_season_freshness.py `
  --as-of 2026-09-14T20:00:00+03:00 `
  --required-through 2026-09-13 `
  --max-capture-age-hours 24
```

`--as-of` is the prediction time, not kickoff inferred from the raw result
file. `--required-through` is the latest completed league match date that the
operator has independently established. The gate fails closed if the snapshot
was captured after the prediction time, is too old, or ends before that date.

This check does not make Football-Data authoritative for fixtures or guarantee
that every same-day match is present. A future live prediction runner must also
validate the requested fixture against an official schedule source.
