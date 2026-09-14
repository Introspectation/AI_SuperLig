# Time-decayed Dixon-Coles evaluation

## Verdict

**GO.** `dixon_coles_decay` beats `independent_poisson` on development log loss
(0.995379 vs 1.008672) and Brier score
(0.591547 vs 0.600648).

Mean paired log-loss difference against `independent_poisson`: -0.013293
(approximate 95% interval [-0.020865, -0.005720]; the interval excludes zero).
Ablations attribute the change: decay alone -0.013533, low-score
correction alone +0.000330, both together -0.013293.

The low-score correction is not justified on H/D/A metrics:
`poisson_decay` scores 0.995139 log loss and 0.591252
Brier versus the candidate's 0.995379 and 0.591547; the
candidate-minus-`poisson_decay` paired log-loss difference is
+0.000240 ([-0.002336, +0.002816]).
The Stage 5 gain comes from recency decay. The candidate was declared before
results and is not replaced here; the Stage 8 freeze weighs this evidence.

Decay was selected by the nested chronological rule; no development season
tuned itself, and no final-holdout result or market probability was used.

## Overall development results

| Model | Matches | Log loss | Brier score |
| --- | --- | --- | --- |
| uniform_hda | 1413 | 1.098612 | 0.666667 |
| expanding_league_hda | 1413 | 1.060314 | 0.640070 |
| independent_poisson | 1413 | 1.008672 | 0.600648 |
| poisson_decay | 1413 | 0.995139 | 0.591252 |
| dixon_coles_no_decay | 1413 | 1.009002 | 0.600808 |
| dixon_coles_decay | 1413 | 0.995379 | 0.591547 |

Lower is better. All models use the same 1,413 development fixtures and
kickoff prediction times. Aggregates are computed before per-match values
are rounded for publication.

## Paired log-loss difference against `independent_poisson`

| Model | Season | Matches | Mean difference | Approx. 95% interval |
| --- | --- | --- | --- | --- |
| `dixon_coles_decay` | ALL | 1413 | -0.013293 | [-0.020865, -0.005720] |
| `dixon_coles_decay` | 2021-22 | 380 | -0.011755 | [-0.020381, -0.003130] |
| `dixon_coles_decay` | 2022-23 | 313 | +0.009283 | [-0.006113, +0.024678] |
| `dixon_coles_decay` | 2023-24 | 379 | -0.010710 | [-0.026000, +0.004579] |
| `dixon_coles_decay` | 2024-25 | 341 | -0.038598 | [-0.058427, -0.018768] |
| `poisson_decay` | ALL | 1413 | -0.013533 | [-0.020706, -0.006359] |
| `dixon_coles_no_decay` | ALL | 1413 | +0.000330 | [-0.002038, +0.002699] |

Negative differences favour the Stage 5 model. Intervals use a normal
approximation that treats matches as independent and are descriptive.

## Nested chronological decay selection

| Target season | Tuning seasons | Tuning matches | Selected decay/day | Half-life | Tuning log loss | No-decay tuning log loss | At grid maximum |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2021-22 | 2019-20, 2020-21 | 726 | 0.0015 | 462 days | 1.042066 | 1.043480 | no |
| 2022-23 | 2019-20, 2020-21, 2021-22 | 1106 | 0.003 | 231 days | 1.034542 | 1.042303 | no |
| 2023-24 | 2019-20, 2020-21, 2021-22, 2022-23 | 1419 | 0.003 | 231 days | 1.026893 | 1.031055 | no |
| 2024-25 | 2019-20, 2020-21, 2021-22, 2022-23, 2023-24 | 1798 | 0.003 | 231 days | 1.019389 | 1.024350 | no |

Each target season uses the decay with the lowest walk-forward log loss over
earlier grid seasons only. Ties select the smaller decay.

## Walk-forward grid by season (descriptive)

| Season | 0 | 0.0005 | 0.001 | 0.0015 | 0.002 | 0.003 | 0.005 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2019-20 | 1.0495 | 1.0485 | 1.0478 | 1.0473 | 1.0471 | 1.0475 | 1.0500 |
| 2020-21 | 1.0391 | 1.0385 | 1.0382 | 1.0382 | 1.0386 | 1.0400 | 1.0447 |
| 2021-22 | 1.0401 | 1.0350 | 1.0303 | 1.0263 | 1.0230 | 1.0181 | 1.0129 |
| 2022-23 | 0.9913 | 0.9938 | 0.9957 | 0.9971 | 0.9982 | 0.9999 | 1.0032 |
| 2023-24 | 0.9992 | 0.9970 | 0.9949 | 0.9932 | 0.9920 | 0.9913 | 0.9935 |
| 2024-25 | 1.0015 | 0.9908 | 0.9813 | 0.9737 | 0.9682 | 0.9613 | 0.9555 |

H/D/A log loss of the Dixon-Coles fit for each declared decay. 2019-20 and
2020-21 are tuning-only warm-up seasons. This table never replaces the
nested choice above.

## Results by season

| Season | Model | Matches | Log loss | Brier score |
| --- | --- | --- | --- | --- |
| 2021-22 | uniform_hda | 380 | 1.098612 | 0.666667 |
| 2021-22 | expanding_league_hda | 380 | 1.058153 | 0.638515 |
| 2021-22 | independent_poisson | 380 | 1.038055 | 0.623130 |
| 2021-22 | poisson_decay | 380 | 1.024696 | 0.614825 |
| 2021-22 | dixon_coles_no_decay | 380 | 1.040055 | 0.624086 |
| 2021-22 | dixon_coles_decay | 380 | 1.026300 | 0.615836 |
| 2022-23 | uniform_hda | 313 | 1.098612 | 0.666667 |
| 2022-23 | expanding_league_hda | 313 | 1.065917 | 0.644374 |
| 2022-23 | independent_poisson | 313 | 0.990581 | 0.587288 |
| 2022-23 | poisson_decay | 313 | 0.998841 | 0.593345 |
| 2022-23 | dixon_coles_no_decay | 313 | 0.991306 | 0.587501 |
| 2022-23 | dixon_coles_decay | 313 | 0.999864 | 0.593742 |
| 2023-24 | uniform_hda | 379 | 1.098612 | 0.666667 |
| 2023-24 | expanding_league_hda | 379 | 1.066599 | 0.644249 |
| 2023-24 | independent_poisson | 379 | 1.002002 | 0.593079 |
| 2023-24 | poisson_decay | 379 | 0.993417 | 0.586143 |
| 2023-24 | dixon_coles_no_decay | 379 | 0.999247 | 0.591645 |
| 2023-24 | dixon_coles_decay | 379 | 0.991292 | 0.585317 |
| 2024-25 | uniform_hda | 341 | 1.098612 | 0.666667 |
| 2024-25 | expanding_league_hda | 341 | 1.050594 | 0.633206 |
| 2024-25 | independent_poisson | 341 | 0.999947 | 0.596270 |
| 2024-25 | poisson_decay | 341 | 0.960720 | 0.568740 |
| 2024-25 | dixon_coles_no_decay | 341 | 1.001483 | 0.597267 |
| 2024-25 | dixon_coles_decay | 341 | 0.961349 | 0.569389 |

## Low-score calibration

| Score | Observed frequency | Mean `independent_poisson` | Mean `dixon_coles_decay` |
| --- | --- | --- | --- |
| 0-0 | 0.0651 | 0.0645 | 0.0756 |
| 1-0 | 0.0870 | 0.0957 | 0.0859 |
| 0-1 | 0.0665 | 0.0761 | 0.0672 |
| 1-1 | 0.1189 | 0.1100 | 0.1190 |
| draw (any score) | 0.2435 | 0.2376 | 0.2563 |

Fitted `rho` for `dixon_coles_decay` predictions: mean -0.0914,
minimum -0.1513, maximum -0.0271.

## Scoreline diagnostic

| Model | Mean negative log probability of exact score |
| --- | --- |
| `independent_poisson` | 3.005623 |
| `poisson_decay` | 3.002343 |
| `dixon_coles_no_decay` | 3.004885 |
| `dixon_coles_decay` | 3.002127 |

Descriptive only; primary and secondary metrics remain H/D/A log loss and Brier.

## Cold-start characterization

| Fewest prior matches | Matches | `independent_poisson` log loss | `dixon_coles_decay` log loss | Difference |
| --- | --- | --- | --- | --- |
| 0 (unseen club) | 9 | 1.075214 | 1.095132 | +0.019917 |
| 1-33 | 287 | 1.060871 | 1.055015 | -0.005857 |
| 34+ | 1117 | 0.994724 | 0.979253 | -0.015471 |

## Largest single-match candidate losses

| Season | Kickoff date | Fixture | Fewest prior matches | Expected goals | Score | H/D/A log loss |
| --- | --- | --- | --- | --- | --- | --- |
| 2023-24 | 2023-08-20 | Besiktas - Pendikspor | 1 | 7.96 - 0.65 | 1-1 | 5.6590 |
| 2022-23 | 2022-08-27 | Alanyaspor - Istanbulspor | 3 | 3.12 - 0.37 | 0-1 | 3.9499 |
| 2023-24 | 2023-12-02 | Adana Demirspor - Samsunspor | 13 | 2.36 - 0.61 | 2-3 | 2.6503 |
| 2024-25 | 2025-05-25 | Istanbul Basaksehir - Adana Demirspor | 143 | 3.04 - 0.94 | 2-3 | 2.5268 |
| 2022-23 | 2022-11-12 | Fenerbahce - Giresunspor | 50 | 2.38 - 0.70 | 1-2 | 2.4571 |

Sparse-history failures remain evidence for the Stage 6 promoted-team prior.

## Model specification

The declared specification is in `MODEL_DESIGN.md`: Stage 4 rates and team
penalty, jointly estimated Dixon-Coles `rho`, exponential recency weights
anchored at the latest kickoff in each available history, and the fixed decay
grid 0, 0.0005, 0.001, 0.0015, 0.002, 0.003, 0.005 per day.
The selection rule is in `EVALUATION_PROTOCOL.md`.

## Frozen evaluation boundary

- Tuning-only walk-forward seasons: 2019-20 and 2020-21.
- Development walk-forward: 2021-22 through 2024-25.
- Final holdout: 2025-26, still sealed and absent from fitting, tuning, and metrics.
- Current season: 2026-27, live-only and absent from development metrics.
- Each fit uses only `evaluation_time.available_history` at the prediction time.
- The isolated market benchmark table is not loaded by the evaluator.

## Next roadmap gate

Stage 6 adds the training-only dynamic promoted-team prior under the same split,
metrics, and chronological tuning rules. Do not open the 2025-26 holdout.
