# Evaluation protocol

This protocol freezes the first modeling-stage time split and scoring rules.
It applies to every baseline and challenger unless a later reviewed change
explicitly replaces it.

## Season roles

| Role | Seasons | Permitted use |
| --- | --- | --- |
| Warm-up history | 2017-18 through 2020-21 | Historical observations available to the first development prediction. |
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
identity, match statistics, betting odds, or future information. Independent
Poisson is the next roadmap model after this checkpoint.

## Market isolation

The evaluator does not load `data/processed/market_benchmark.csv`. Closing odds
remain an external benchmark and may be joined only after model predictions are
materialized and candidate selection is no longer allowed to treat them as
training inputs.
