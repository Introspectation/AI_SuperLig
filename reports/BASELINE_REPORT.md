# Naive baseline evaluation

## Verdict

**GO.** The first leakage-safe probabilistic baselines produced 1,413
development-period predictions with complete coverage. This is a measured
reference checkpoint, not a deployable 2026-27 model.

`expanding_league_hda` has the lowest development log loss. Its relative log-loss
improvement over `uniform_hda` is 3.49%. No final-holdout result
or market probability was used to reach this statement.

## Overall development results

| Model | Matches | Log loss | Brier score |
| --- | --- | --- | --- |
| uniform_hda | 1413 | 1.098612 | 0.666667 |
| expanding_league_hda | 1413 | 1.060314 | 0.640070 |

Lower is better. Log loss uses natural logarithms; the multiclass Brier
score is the mean sum of squared H/D/A probability errors.

## Results by season

| Season | Model | Matches | Log loss | Brier score |
| --- | --- | --- | --- | --- |
| 2021-22 | uniform_hda | 380 | 1.098612 | 0.666667 |
| 2021-22 | expanding_league_hda | 380 | 1.058153 | 0.638515 |
| 2022-23 | uniform_hda | 313 | 1.098612 | 0.666667 |
| 2022-23 | expanding_league_hda | 313 | 1.065917 | 0.644374 |
| 2023-24 | uniform_hda | 379 | 1.098612 | 0.666667 |
| 2023-24 | expanding_league_hda | 379 | 1.066599 | 0.644249 |
| 2024-25 | uniform_hda | 341 | 1.098612 | 0.666667 |
| 2024-25 | expanding_league_hda | 341 | 1.050594 | 0.633206 |

## Frozen evaluation boundary

- Warm-up history: 2017-18 through 2020-21.
- Development walk-forward: 2021-22 through 2024-25.
- Final holdout: 2025-26, still sealed and absent from predictions/metrics.
- Current season: 2026-27, live-only and absent from development metrics.
- Each prediction uses only `result_available_at < prediction_time` history.
- Same-kickoff fixtures share the same available history.

## Baseline scope

`uniform_hda` assigns one third to every outcome. `expanding_league_hda`
uses only prior league-wide H/D/A frequencies. Neither baseline uses team
identity, match statistics, betting odds, or promoted-team assumptions.
The isolated market benchmark table is not loaded by the evaluator.

## Next roadmap gate

Implement independent Poisson under the same split and metrics. Do not open
the 2025-26 holdout and do not implement the dynamic promoted-team prior yet.
