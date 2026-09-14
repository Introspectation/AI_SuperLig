# Dynamic promoted-team prior evaluation

## Verdict

**GO.** `dixon_coles_promoted_prior` improves log loss on the 415 development
fixtures involving a promoted club (1.000308 vs 1.029932 for `dixon_coles_decay`) without worsening overall log loss (0.986679 vs 0.995379).

Paired log-loss difference against `dixon_coles_decay`: promoted-club fixtures
-0.029623 [-0.061745, +0.002498], all fixtures
-0.008700 [-0.018153, +0.000752] (approximate 95%
intervals treating matches as independent).

Both approximate intervals include zero, so the improvement is not clearly separated from match-level noise.

Uncertainty propagation is not justified on H/D/A metrics: `dixon_coles_promoted_point` scores 0.986625 overall and 1.000126 on promoted-club fixtures.

12 of 12 `k` selections sit at the grid maximum (k = 64); the declared grid is not extended after seeing results.

`k` was selected by the nested chronological rule at each season's Stage 5 decay;
no development season tuned itself, and no final-holdout result or market
probability was used.

## Overall development results

| Model | Matches | Log loss | Brier score | Promoted-club fixture log loss |
| --- | --- | --- | --- | --- |
| independent_poisson | 1413 | 1.008672 | 0.600648 | - |
| poisson_decay | 1413 | 0.995139 | 0.591252 | 1.027245 |
| dixon_coles_decay | 1413 | 0.995379 | 0.591547 | 1.029932 |
| dixon_coles_promoted_prior | 1413 | 0.986679 | 0.587685 | 1.000308 |
| dixon_coles_promoted_point | 1413 | 0.986625 | 0.587663 | 1.000126 |
| poisson_decay_promoted_prior | 1413 | 0.986863 | 0.587326 | 0.999066 |

Promoted-club fixtures: 415 of 1413 development matches involve
a club with no eligible match in the previous season.

## Paired log-loss differences

| Model | Reference | Subset | Mean difference | Approx. 95% interval |
| --- | --- | --- | --- | --- |
| `dixon_coles_promoted_prior` | `dixon_coles_decay` | promoted-club fixtures | -0.029623 | [-0.061745, +0.002498] |
| `dixon_coles_promoted_prior` | `dixon_coles_decay` | all fixtures | -0.008700 | [-0.018153, +0.000752] |
| `dixon_coles_promoted_point` | `dixon_coles_decay` | promoted-club fixtures | -0.029805 | [-0.061817, +0.002207] |
| `dixon_coles_promoted_point` | `dixon_coles_decay` | all fixtures | -0.008754 | [-0.018175, +0.000667] |
| `poisson_decay_promoted_prior` | `dixon_coles_decay` | promoted-club fixtures | -0.030866 | [-0.063453, +0.001721] |
| `poisson_decay_promoted_prior` | `dixon_coles_decay` | all fixtures | -0.008516 | [-0.018341, +0.001309] |
| `poisson_decay_promoted_prior` | `poisson_decay` | promoted-club fixtures | -0.028179 | [-0.059427, +0.003069] |
| `poisson_decay_promoted_prior` | `poisson_decay` | all fixtures | -0.008276 | [-0.017470, +0.000918] |

Negative differences favour the Stage 6 model.

## Nested chronological k selection

| Model | Target season | Decay/day | Tuning matches | Selected k | Tuning log loss | No-prior tuning log loss | At grid maximum |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `dixon_coles_promoted_prior` | 2021-22 | 0.0015 | 726 | 64 | 1.032272 | 1.042066 | yes |
| `dixon_coles_promoted_prior` | 2022-23 | 0.003 | 1106 | 64 | 1.025621 | 1.034542 | yes |
| `dixon_coles_promoted_prior` | 2023-24 | 0.003 | 1419 | 64 | 1.018643 | 1.026893 | yes |
| `dixon_coles_promoted_prior` | 2024-25 | 0.003 | 1798 | 64 | 1.009735 | 1.019389 | yes |
| `dixon_coles_promoted_point` | 2021-22 | 0.0015 | 726 | 64 | 1.032318 | 1.042066 | yes |
| `dixon_coles_promoted_point` | 2022-23 | 0.003 | 1106 | 64 | 1.025724 | 1.034542 | yes |
| `dixon_coles_promoted_point` | 2023-24 | 0.003 | 1419 | 64 | 1.018691 | 1.026893 | yes |
| `dixon_coles_promoted_point` | 2024-25 | 0.003 | 1798 | 64 | 1.009732 | 1.019389 | yes |
| `poisson_decay_promoted_prior` | 2021-22 | 0.0015 | 726 | 64 | 1.034768 | 1.044204 | yes |
| `poisson_decay_promoted_prior` | 2022-23 | 0.003 | 1106 | 64 | 1.026728 | 1.035179 | yes |
| `poisson_decay_promoted_prior` | 2023-24 | 0.003 | 1419 | 64 | 1.019284 | 1.027164 | yes |
| `poisson_decay_promoted_prior` | 2024-25 | 0.003 | 1798 | 64 | 1.010737 | 1.020050 | yes |

## Candidate k grid on promoted-club fixtures (descriptive)

| Season | Decay/day | Promoted matches | k=0 | k=4 | k=8 | k=16 | k=32 | k=64 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2019-20 | 0.0015 | 96 | 1.0987 | 1.0730 | 1.0663 | 1.0615 | 1.0589 | 1.0581 |
| 2019-20 | 0.003 | 96 | 1.1053 | 1.0790 | 1.0723 | 1.0675 | 1.0650 | 1.0644 |
| 2020-21 | 0.0015 | 114 | 1.0934 | 1.0758 | 1.0710 | 1.0674 | 1.0655 | 1.0651 |
| 2020-21 | 0.003 | 114 | 1.0919 | 1.0742 | 1.0692 | 1.0653 | 1.0631 | 1.0627 |
| 2021-22 | 0.0015 | 108 | 1.0696 | 1.0580 | 1.0539 | 1.0499 | 1.0469 | 1.0450 |
| 2021-22 | 0.003 | 108 | 1.0607 | 1.0493 | 1.0453 | 1.0413 | 1.0383 | 1.0365 |
| 2022-23 | 0.0015 | 97 | 0.9980 | 0.9847 | 0.9828 | 0.9825 | 0.9838 | 0.9859 |
| 2022-23 | 0.003 | 97 | 0.9954 | 0.9800 | 0.9772 | 0.9758 | 0.9757 | 0.9765 |
| 2023-24 | 0.0015 | 108 | 1.0233 | 0.9851 | 0.9810 | 0.9780 | 0.9765 | 0.9761 |
| 2023-24 | 0.003 | 108 | 1.0337 | 0.9918 | 0.9874 | 0.9841 | 0.9822 | 0.9814 |
| 2024-25 | 0.0015 | 102 | 1.0231 | 1.0117 | 1.0087 | 1.0062 | 1.0046 | 1.0041 |
| 2024-25 | 0.003 | 102 | 1.0168 | 1.0046 | 1.0012 | 0.9982 | 0.9963 | 0.9957 |

Log loss on promoted-club fixtures for each declared `k`; this table never
replaces the nested choice.

## Prior used at each development season

| Target season | Offsets | Mean attack offset | Attack SD | Mean defence offset | Defence SD |
| --- | --- | --- | --- | --- | --- |
| 2021-22 | 9 | -0.079 | 0.203 | -0.031 | 0.091 |
| 2022-23 | 12 | -0.078 | 0.212 | -0.011 | 0.102 |
| 2023-24 | 15 | -0.095 | 0.192 | -0.035 | 0.112 |
| 2024-25 | 18 | -0.110 | 0.181 | -0.048 | 0.119 |

Offsets are candidate-base strengths of previously promoted clubs relative to
the previous-season reference level (`reports/promoted_prior_offsets.csv`).

## Cold-start slices on promoted-club fixtures

| Slice | Matches | `dixon_coles_decay` log loss | `dixon_coles_promoted_prior` log loss | Difference |
| --- | --- | --- | --- | --- |
| 0 | 12 | 1.066655 | 1.059038 | -0.007617 |
| 1-5 | 58 | 1.146663 | 1.036852 | -0.109811 |
| 6-16 | 123 | 1.010544 | 1.004911 | -0.005632 |
| 17+ | 222 | 1.008191 | 0.985036 | -0.023155 |

Slices use the fewest current-season matches among promoted clubs in a fixture.

| Slice | Matches | `dixon_coles_decay` log loss | `dixon_coles_promoted_prior` log loss | Difference |
| --- | --- | --- | --- | --- |
| no earlier history in data | 306 | 1.055362 | 1.016484 | -0.038878 |
| earlier top-flight history in data | 109 | 0.958539 | 0.954897 | -0.003642 |

## Largest single-match candidate losses

| Season | Kickoff date | Fixture | Promoted | k | Expected goals | Score | H/D/A log loss |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2024-25 | 2025-05-25 | Istanbul Basaksehir - Adana Demirspor | none | 64 | 3.04 - 0.94 | 2-3 | 2.5268 |
| 2022-23 | 2022-11-12 | Fenerbahce - Giresunspor | none | 64 | 2.38 - 0.70 | 1-2 | 2.4571 |
| 2023-24 | 2023-12-21 | Besiktas - Alanyaspor | none | 64 | 2.46 - 0.86 | 1-3 | 2.2412 |
| 2024-25 | 2025-05-26 | Hatayspor - Fenerbahce | none | 64 | 1.03 - 2.71 | 4-2 | 2.1750 |
| 2024-25 | 2025-04-20 | Fenerbahce - Kayserispor | none | 64 | 3.10 - 0.72 | 3-3 | 2.1624 |

## Model specification

The declared specification is in `MODEL_DESIGN.md` (Stage 6 implementation) and
the k-selection rule in `EVALUATION_PROTOCOL.md`. `k = 0` reproduces the Stage 5
base predictions exactly; the evaluator verifies this before writing outputs.

## Frozen evaluation boundary

- Tuning-only walk-forward seasons: 2019-20 and 2020-21.
- Development walk-forward: 2021-22 through 2024-25.
- Prior offsets use only completed seasons from 2018-19 before each target season.
- Final holdout: 2025-26, still sealed and absent from fitting, tuning, and metrics.
- Current season: 2026-27, live-only and absent from development metrics.
- The isolated market benchmark table is not loaded by the evaluator.

## Next roadmap gate

Stage 7 (small-data ML challengers) requires a new user go-ahead and must use the
same split, metrics, and chronological tuning rules.
