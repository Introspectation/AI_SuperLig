# Evaluation protocol

This protocol freezes the first modeling-stage time split and scoring rules.
It applies to every baseline and challenger unless a later reviewed change
explicitly replaces it.

## Season roles

| Role | Seasons | Permitted use |
| --- | --- | --- |
| Warm-up history | 2017-18 through 2020-21 | Historical observations available to the first development prediction; 2019-20 and 2020-21 also host Stage 5 walk-forward tuning predictions. |
| Development walk-forward | 2021-22 through 2024-25 | Model development, comparison, and training-only tuning. |
| Final holdout | 2025-26 | Sealed until the candidate model and decision rule are frozen. |
| Live-only current season | 2026-27 | Versioned observations may update a live fit; never development tuning data. |

The machine-readable assignment is `config/evaluation_splits.csv`. The first
baseline command fails if that exact assignment changes unexpectedly. The
2025-26 final holdout is schema-validated but is not scored or used for model
fitting, tuning, or selection by the baseline evaluator.
The in-progress 2026-27 season is also absent from development metrics. Its
versioned snapshots exist only for timestamped live research predictions.

## Walk-forward rule

Every development fixture is predicted at its canonical kickoff timestamp.
Historical outcomes must be obtained through `scripts/evaluation_time.py` and
must satisfy:

```text
result_available_at < prediction_time
```

Fixtures sharing a kickoff timestamp receive predictions from the same history.
Models may expand their history after a result becomes available, but they may
not see the current fixture, an overlapping fixture, a future result, or an
administrative row marked `model_eligible=false`.

## Metrics

- Primary: multiclass natural-log loss over Home/Draw/Away probabilities.
- Secondary: multiclass Brier score, calculated as the sum of the three squared
  probability errors per match and then averaged.
- Lower is better for both metrics.
- Metrics are reported for the complete development period and separately by
  season. Per-match predictions are retained so all aggregates are auditable.

The evaluator requires finite probabilities strictly between zero and one that
sum to one. Probability clipping is not used to hide invalid model output.

## First baselines

- `uniform_hda`: fixed one-third probability for each outcome; uses no training
  observations.
- `expanding_league_hda`: empirical Home/Draw/Away frequencies from every
  eligible result available before the prediction timestamp.

These are reference floors, not deployment candidates. They use no team
identity, match statistics, betting odds, or future information. They remain
the floors for every later challenger.

## Stage 4 independent Poisson

`independent_poisson` is the first team-strength challenger. It is scored on
the same development fixtures, prediction timestamps, and metrics as the
baselines. `scripts/run_poisson_evaluation.py` regenerates the baselines first
and fails if their fixtures or prediction times differ. The specification is
recorded in `MODEL_DESIGN.md`.

Iterative fits are reproducible to numerical tolerance rather than
bit-for-bit across numerical libraries, so per-match fitted values are
published to nine decimals; aggregate metrics are computed before rounding.
The paired interval, calibration-in-the-large table, cold-start slice, and
exact-score diagnostic in `reports/POISSON_REPORT.md` are descriptive evidence,
not selection rules.

## Stage 5 chronological decay selection

Stage 5 selects its recency decay without letting a development season tune
itself:

1. Every eligible fixture from 2019-20 through 2024-25 is predicted at kickoff
   for each declared decay value, using only `result_available_at < t` history.
   2019-20 and 2020-21 serve only as tuning seasons.
2. For development season `S`, the selected decay minimizes mean H/D/A log loss
   over all grid predictions from 2019-20 through the season before `S`. Ties
   select the smaller decay. Every tuning result must be available before the
   first prediction time in `S`.
3. Development metrics for `S` use only that selected decay. The per-season grid
   table in the Stage 5 report is descriptive and never replaces the nested
   choice.

The 2025-26 holdout is not a tuning season.

## Stage 6 chronological prior-strength selection

1. Every eligible fixture from 2019-20 through 2024-25 is predicted for each
   declared `k`, using the Stage 5 fits at the decay selected for the target
   development season.
2. For development season `S`, each Stage 6 model selects the `k` that
   minimizes mean H/D/A log loss over its predictions from 2019-20 through the
   season before `S` at decay `decay_S`. Ties select the smaller `k`; `k = 0`
   means no prior. Every tuning result must be available before the first
   prediction time in `S`.
3. Development metrics for `S` use only that `k`. Promoted-club slices in the
   Stage 6 report are the declared gate subset; all other slices are
   descriptive.

## Market isolation

The evaluator does not load `data/processed/market_benchmark.csv`. Closing odds
remain an external benchmark and may be joined only after model predictions are
materialized and candidate selection is no longer allowed to treat them as
training inputs.
