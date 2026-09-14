# Small-data ML challenger evaluation

## Verdict

**CHARACTERIZED.** `ml_offset_logit` does not pass the declared gate against
`dixon_coles_promoted_prior`: log loss 0.986766 vs 0.986679, Brier 0.587777 vs 0.587685.
The paired log-loss difference is +0.000087 (approximate 95% interval [-0.004291, +0.004465]); the gate requires the interval to exclude zero.

Ablations: recalibration only 0.986679; plain logistic without the
Stage 6 offset 0.983529. Penalties were selected by the nested
chronological rule; no development season tuned itself, and no final-holdout
result or market probability was used.

5 of 12 penalty selections chose `inf`, meaning no
adjustment (offset models reproduce Stage 6; the plain model predicts class
frequencies).

## Overall development results

| Model | Matches | Log loss | Brier score |
| --- | --- | --- | --- |
| dixon_coles_promoted_prior | 1413 | 0.986679 | 0.587685 |
| dixon_coles_promoted_point | 1413 | 0.986625 | 0.587663 |
| ml_offset_logit | 1413 | 0.986766 | 0.587777 |
| ml_offset_recalibration | 1413 | 0.986679 | 0.587685 |
| ml_plain_logit | 1413 | 0.983529 | 0.585562 |

## Paired log-loss difference against `dixon_coles_promoted_prior`

| Model | Season | Matches | Mean difference | Approx. 95% interval |
| --- | --- | --- | --- | --- |
| `ml_offset_logit` | ALL | 1413 | +0.000087 | [-0.004291, +0.004465] |
| `ml_offset_logit` | 2021-22 | 380 | +0.000000 | [+0.000000, +0.000000] |
| `ml_offset_logit` | 2022-23 | 313 | -0.001247 | [-0.016056, +0.013562] |
| `ml_offset_logit` | 2023-24 | 379 | -0.000387 | [-0.007980, +0.007205] |
| `ml_offset_logit` | 2024-25 | 341 | +0.001936 | [-0.006654, +0.010527] |
| `ml_offset_recalibration` | ALL | 1413 | +0.000000 | [+0.000000, +0.000000] |
| `ml_plain_logit` | ALL | 1413 | -0.003150 | [-0.010136, +0.003835] |

Negative differences favour the Stage 7 model. Intervals treat matches as independent.

## Nested chronological penalty selection

| Model | Target season | Stage 5 decay / Stage 6 k | Tuning matches | Selected lambda | Tuning log loss | No-adjustment tuning log loss |
| --- | --- | --- | --- | --- | --- | --- |
| `ml_offset_logit` | 2021-22 | 0.0015 / 64 | 420 | inf | 1.030586 | 1.030586 |
| `ml_offset_logit` | 2022-23 | 0.003 / 64 | 800 | 100 | 1.017686 | 1.022178 |
| `ml_offset_logit` | 2023-24 | 0.003 / 64 | 1113 | 300 | 1.010257 | 1.014251 |
| `ml_offset_logit` | 2024-25 | 0.003 / 64 | 1492 | 300 | 1.001554 | 1.004631 |
| `ml_offset_recalibration` | 2021-22 | 0.0015 / 64 | 420 | inf | 1.030586 | 1.030586 |
| `ml_offset_recalibration` | 2022-23 | 0.003 / 64 | 800 | inf | 1.022178 | 1.022178 |
| `ml_offset_recalibration` | 2023-24 | 0.003 / 64 | 1113 | inf | 1.014251 | 1.014251 |
| `ml_offset_recalibration` | 2024-25 | 0.003 / 64 | 1492 | inf | 1.004631 | 1.004631 |
| `ml_plain_logit` | 2021-22 | 0.0015 / 64 | 420 | 100 | 1.043264 | 1.087211 |
| `ml_plain_logit` | 2022-23 | 0.003 / 64 | 800 | 100 | 1.020474 | 1.074469 |
| `ml_plain_logit` | 2023-24 | 0.003 / 64 | 1113 | 100 | 1.014295 | 1.071962 |
| `ml_plain_logit` | 2024-25 | 0.003 / 64 | 1492 | 100 | 1.005896 | 1.070797 |

## Candidate penalty grid by season (descriptive)

| Season | Decay / k | lambda=1 | lambda=3 | lambda=10 | lambda=30 | lambda=100 | lambda=300 | lambda=inf |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2020-21 | 0.0015 / 64 | 1.0522 | 1.0510 | 1.0477 | 1.0425 | 1.0363 | 1.0326 | 1.0306 |
| 2020-21 | 0.003 / 64 | 1.0556 | 1.0543 | 1.0509 | 1.0455 | 1.0390 | 1.0350 | 1.0321 |
| 2021-22 | 0.0015 / 64 | 0.9947 | 0.9946 | 0.9945 | 0.9948 | 0.9973 | 1.0030 | 1.0193 |
| 2021-22 | 0.003 / 64 | 0.9920 | 0.9919 | 0.9918 | 0.9920 | 0.9941 | 0.9989 | 1.0112 |
| 2022-23 | 0.003 / 64 | 0.9963 | 0.9962 | 0.9957 | 0.9947 | 0.9927 | 0.9908 | 0.9940 |
| 2023-24 | 0.003 / 64 | 0.9829 | 0.9827 | 0.9822 | 0.9810 | 0.9786 | 0.9760 | 0.9764 |
| 2024-25 | 0.003 / 64 | 0.9620 | 0.9619 | 0.9617 | 0.9611 | 0.9593 | 0.9570 | 0.9550 |

## Calibration

| Source | Home mean / ECE | Draw mean / ECE | Away mean / ECE |
| --- | --- | --- | --- |
| observed frequency | 0.4657 | 0.2435 | 0.2909 |
| `dixon_coles_promoted_prior` | 0.4445 / 0.0413 | 0.2570 / 0.0136 | 0.2984 / 0.0337 |
| `ml_offset_logit` | 0.4453 / 0.0289 | 0.2545 / 0.0110 | 0.3002 / 0.0262 |

ECE uses 10 equal-width probability bins per outcome and is descriptive.

## Candidate coefficients (standardized features)

| Term (home / away vs draw) | 2021-22 | 2022-23 | 2023-24 | 2024-25 |
| --- | --- | --- | --- | --- |
| intercept | +0.000 / +0.000 | -0.005 / +0.001 | -0.002 / -0.015 | +0.013 / -0.018 |
| stage6_logit_home_draw | +0.000 / +0.000 | -0.057 / -0.011 | -0.027 / -0.006 | -0.031 / -0.003 |
| stage6_logit_away_draw | +0.000 / +0.000 | +0.076 / -0.011 | +0.017 / +0.002 | -0.006 / +0.010 |
| form_points_diff | +0.000 / +0.000 | +0.070 / -0.032 | +0.044 / -0.029 | +0.040 / -0.016 |
| sot_share_diff | +0.000 / +0.000 | +0.173 / -0.079 | +0.103 / -0.066 | +0.102 / -0.072 |
| rest_days_diff | +0.000 / +0.000 | -0.027 / +0.007 | -0.036 / +0.000 | -0.009 / -0.009 |
| home_promoted | +0.000 / +0.000 | -0.034 / +0.076 | -0.002 / +0.044 | +0.004 / +0.034 |
| away_promoted | +0.000 / +0.000 | +0.012 / +0.044 | +0.021 / +0.005 | +0.014 / +0.001 |

Coefficients come from the last fit of each development season at its selected
penalty. They adjust the Stage 6 logits, so zero means no change.

## Model specification

The declared specification is in `MODEL_DESIGN.md` (Stage 7) and the penalty
rule in `EVALUATION_PROTOCOL.md`. `lambda = inf` reproduces the Stage 6 candidate
exactly for offset models; the evaluator verifies this before writing outputs.

## Frozen evaluation boundary

- Training rows start in 2019-20; tuning predictions start in 2020-21.
- Development walk-forward: 2021-22 through 2024-25.
- Final holdout: 2025-26, still sealed and absent from fitting, tuning, and metrics.
- Current season: 2026-27, live-only and absent from development metrics.
- The isolated market benchmark table is not loaded by the evaluator.

## Next roadmap gate

Stage 8 freezes one candidate and its decision rule using development evidence
only. It requires a new user go-ahead; the 2025-26 holdout opens only afterwards.
