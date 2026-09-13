# Leakage contract

This contract applies to every future model, baseline, feature pipeline, and
evaluation in this repository.

## Governing rule

For a match occurring at prediction time `t`, every predictive feature must
satisfy:

```text
feature(match_t) = f(matches strictly before t)
```

For historical results, the executable form is:

```text
feature(match_t) = f(matches where result_available_at < t)
```

Information that becomes known at or after kickoff is not available to the
prediction for that match. A convenient column being present in the historical
match table does not make it a legal feature.

## Forbidden predictive inputs

The following must never be inputs for the match being predicted:

- current-match goals or result;
- current-match shots or shots on target;
- current-match cards, corners, or fouls;
- future matches of any team;
- final-season standings or end-of-season aggregates;
- statistics calculated with matches after the prediction timestamp;
- closing betting odds, closing implied probabilities, or market overround;
- any transformation fitted with validation or test-period observations.

Closing odds live only in the logically separate market benchmark table. They
may be compared with model probabilities after predictions are frozen, but they
are not features and may not influence model selection as if they were training
data.

## Time ordering

- Final evaluation must be chronological and walk-forward.
- Random shuffled train/test splitting is forbidden for final evaluation.
- Training windows, decay weights, scalers, encoders, imputers, and feature
  selection must be fitted using information available strictly before each
  evaluation match.
- The canonical table backfills the earliest audited kickoff times from the
  reviewed TFF snapshot. If a trusted kickoff time is missing in any future
  data, matches on the same calendar date are treated conservatively as
  simultaneous and may use only matches from strictly earlier dates.
- An earlier kickoff is not automatically an available result. Because the
  current sources lack final-whistle timestamps, the fixed conservative policy
  is `result_available_at = kickoff_at + 180 minutes`. The lag is a leakage
  guardrail, is not tuned, and may not be shortened using evaluation results.
- Source-confirmed interruptions require an explicit reviewed availability
  override. Başakşehir-Bursaspor on 23 February 2019 anchors its 180-minute lag
  to the official next-day resumption; ineligible administrative rows have no
  result-availability timestamp.
- Dynamic promoted-team prior parameters, including the shrinkage constant,
  must be estimated inside each chronological training boundary. A later
  season or evaluation fold may not influence a prior used earlier in time.
- Any future backfill must retain an `as_of` or ingestion snapshot boundary so
  revised history cannot leak into an earlier prediction replay.

## Evaluation boundary

Predictions must be materialized before their evaluated matches. Walk-forward
fold definitions, training cutoffs, and prediction timestamps must be saved
with evaluation outputs. Market benchmark probabilities are joined only after
model predictions are fixed.

## Enforcement expectations

Future feature code must declare its source columns and lookback boundary.
All repository evaluation code must obtain historical outcomes through
`scripts/evaluation_time.py`; reimplementing a looser local filter is forbidden.
Automated tests must include boundary cases for same-day fixtures, strict
`result_available_at < t` comparisons, interruptions, future rows, late
backfills, and rolling-window shifts. A passing random-split experiment is not
acceptable evidence for production performance.
