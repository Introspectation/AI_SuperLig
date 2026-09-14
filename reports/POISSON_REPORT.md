# Independent Poisson evaluation

## Verdict

**GO.** `independent_poisson` beats `expanding_league_hda` on development log loss
(1.008672 vs 1.060314) and Brier score
(0.600648 vs 0.640070).

The mean paired log-loss difference against `expanding_league_hda` is
-0.051642 with an approximate 95% interval of [-0.069257, -0.034027]; the
interval excludes zero.
Its relative log-loss improvement over `uniform_hda` is 8.19%.
No final-holdout result or market probability was used. This is development
evidence for the comparison ladder, not a deployable 2026-27 model.

## Overall development results

| Model | Matches | Log loss | Brier score |
| --- | --- | --- | --- |
| uniform_hda | 1413 | 1.098612 | 0.666667 |
| expanding_league_hda | 1413 | 1.060314 | 0.640070 |
| independent_poisson | 1413 | 1.008672 | 0.600648 |

Lower is better. Log loss uses natural logarithms; the multiclass Brier
score is the mean sum of squared H/D/A probability errors. Aggregate metrics
are computed before per-match fitted values are rounded for publication.

## Paired log-loss difference against `expanding_league_hda`

| Season | Matches | Mean difference | Approx. 95% interval | Poisson lower on match |
| --- | --- | --- | --- | --- |
| ALL | 1413 | -0.051642 | [-0.069257, -0.034027] | 54.6% |
| 2021-22 | 380 | -0.020098 | [-0.050975, +0.010780] | 49.7% |
| 2022-23 | 313 | -0.075336 | [-0.114488, -0.036183] | 58.5% |
| 2023-24 | 379 | -0.064597 | [-0.102798, -0.026396] | 56.7% |
| 2024-25 | 341 | -0.050647 | [-0.082902, -0.018392] | 54.0% |

Negative differences favour the Poisson model. Intervals use a normal
approximation that treats matches as independent; they ignore dependence
within match rounds and are descriptive, not a selection rule.

## Results by season

| Season | Model | Matches | Log loss | Brier score |
| --- | --- | --- | --- | --- |
| 2021-22 | uniform_hda | 380 | 1.098612 | 0.666667 |
| 2021-22 | expanding_league_hda | 380 | 1.058153 | 0.638515 |
| 2021-22 | independent_poisson | 380 | 1.038055 | 0.623130 |
| 2022-23 | uniform_hda | 313 | 1.098612 | 0.666667 |
| 2022-23 | expanding_league_hda | 313 | 1.065917 | 0.644374 |
| 2022-23 | independent_poisson | 313 | 0.990581 | 0.587288 |
| 2023-24 | uniform_hda | 379 | 1.098612 | 0.666667 |
| 2023-24 | expanding_league_hda | 379 | 1.066599 | 0.644249 |
| 2023-24 | independent_poisson | 379 | 1.002002 | 0.593079 |
| 2024-25 | uniform_hda | 341 | 1.098612 | 0.666667 |
| 2024-25 | expanding_league_hda | 341 | 1.050594 | 0.633206 |
| 2024-25 | independent_poisson | 341 | 0.999947 | 0.596270 |

## Calibration in the large

| Source | Home | Draw | Away |
| --- | --- | --- | --- |
| observed frequency | 0.4657 | 0.2435 | 0.2909 |
| mean `uniform_hda` | 0.3333 | 0.3333 | 0.3333 |
| mean `expanding_league_hda` | 0.4514 | 0.2602 | 0.2884 |
| mean `independent_poisson` | 0.4581 | 0.2376 | 0.3042 |

| Side | Observed mean goals | Mean expected goals |
| --- | --- | --- |
| home | 1.6292 | 1.5924 |
| away | 1.2590 | 1.2227 |

## Cold-start characterization

Fixtures are grouped by the fewer prior eligible matches of the two clubs in
the history available at prediction time.

| Fewest prior matches | Matches | `expanding_league_hda` log loss | Poisson log loss | Difference |
| --- | --- | --- | --- | --- |
| 0 (unseen club) | 9 | 1.231850 | 1.075214 | -0.156636 |
| 1-33 | 287 | 1.067283 | 1.060871 | -0.006412 |
| 34+ | 1117 | 1.057141 | 0.994724 | -0.062417 |

This slice is descriptive evidence for the later promoted-team prior. It is
not used to adjust the Stage 4 specification.

## Largest single-match Poisson losses

| Season | Kickoff date | Fixture | Fewest prior matches | Expected goals | Score | H/D/A log loss |
| --- | --- | --- | --- | --- | --- | --- |
| 2023-24 | 2023-08-20 | Besiktas - Pendikspor | 1 | 6.99 - 0.74 | 1-1 | 4.8318 |
| 2022-23 | 2022-08-27 | Alanyaspor - Istanbulspor | 3 | 2.93 - 0.33 | 0-1 | 3.7714 |
| 2023-24 | 2023-12-02 | Adana Demirspor - Samsunspor | 13 | 2.32 - 0.60 | 2-3 | 2.5386 |
| 2021-22 | 2021-08-29 | Altay - Fenerbahce | 2 | 2.81 - 0.89 | 0-2 | 2.3927 |
| 2022-23 | 2022-08-14 | Umraniyespor - Antalyaspor | 1 | 3.56 - 1.40 | 0-1 | 2.2353 |

Clubs with very little history can receive extreme rates under the fixed
penalty. These rows document the cold-start failure mode that the Stage 6
promoted-team prior must address; they are not a reason to retune Stage 4.

## Scoreline diagnostic

Mean negative log probability of the observed exact score: 3.005623.
This diagnostic prepares the Stage 5 low-score comparison; the primary and
secondary metrics remain H/D/A log loss and Brier score.

## Model specification

For every prediction time `t`, one model is fitted by penalized maximum
likelihood to every eligible on-pitch score with `result_available_at < t`:

```text
home_goals ~ Poisson(exp(intercept + home_advantage + attack[home] - defence[away]))
away_goals ~ Poisson(exp(intercept + attack[away] - defence[home]))
```

- Home and away goals are conditionally independent given the two rates.
- All available history is weighted equally; recency decay belongs to Stage 5.
- Intercept and home advantage are unpenalized. Every team attack and defence
  log-strength has a fixed N(0, 1) penalty that keeps sparse clubs
  identifiable; it is not tuned and is not a promoted-team prior.
- A club with no prior eligible result receives strength 0, the penalty centre.
- Score probabilities use a 0-30 goal grid per side and are renormalized
  after a truncation-mass check; H/D/A probabilities sum that matrix.
- Official awarded scores, match statistics, and market odds are not inputs.

## Frozen evaluation boundary

- Warm-up history: 2017-18 through 2020-21.
- Development walk-forward: 2021-22 through 2024-25.
- Final holdout: 2025-26, still sealed and absent from fitting and metrics.
- Current season: 2026-27, live-only and absent from development metrics.
- Each fit uses only `evaluation_time.available_history` at the prediction time.
- Same-kickoff fixtures share one fit and the same available history.
- The isolated market benchmark table is not loaded by the evaluator.

## Next roadmap gate

Stage 5 adds recency decay and the Dixon-Coles low-score correction under the
same split and metrics, with chronological tuning only. Do not open the
2025-26 holdout and do not implement the promoted-team prior yet.
