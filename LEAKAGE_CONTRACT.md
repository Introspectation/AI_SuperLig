# Leakage contract

This contract applies to every future model, baseline, feature pipeline, and
evaluation in this repository.

## Governing rule

For a match occurring at prediction time `t`, every predictive feature must
satisfy:

```text
feature(match_t) = f(matches strictly before t)
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
- When kickoff time is missing, as in the earliest audited seasons, matches on
  the same calendar date are treated conservatively as simultaneous. Features
  for those matches may use only matches from strictly earlier dates.
- Any future backfill must retain an `as_of` or ingestion snapshot boundary so
  revised history cannot leak into an earlier prediction replay.

## Evaluation boundary

Predictions must be materialized before their evaluated matches. Walk-forward
fold definitions, training cutoffs, and prediction timestamps must be saved
with evaluation outputs. Market benchmark probabilities are joined only after
model predictions are fixed.

## Enforcement expectations

Future feature code must declare its source columns and lookback boundary.
Automated tests must include boundary cases for same-day fixtures, future rows,
late backfills, and rolling-window shifts. A passing random-split experiment is
not acceptable evidence for production performance.
