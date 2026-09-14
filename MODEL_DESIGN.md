# Model design decisions

This file records decisions that future modeling code must follow. It does not
implement a predictive model.

## Independent Poisson (Stage 4)

Implemented by `scripts/run_poisson_evaluation.py`; development evidence is in
`reports/POISSON_REPORT.md`. The specification below was fixed before its
development metrics were computed.

```text
log(home_rate) = intercept + home_advantage + attack[home] - defence[away]
log(away_rate) = intercept + attack[away] - defence[home]
```

- Home and away goals are conditionally independent Poisson counts.
- Each prediction time gets its own penalized maximum-likelihood fit (Newton
  steps with step halving) on every eligible on-pitch score available strictly
  before that time. Same-kickoff fixtures share one fit.
- All available history is weighted equally. Recency decay is a Stage 5
  decision.
- Every team attack and defence log-strength has a fixed N(0, 1) penalty;
  intercept and home advantage are unpenalized. The penalty is an
  identifiability device for sparse clubs, not a promoted-team prior, and must
  not be tuned into one.
- A club with no prior eligible result receives strength 0, the penalty centre.
  This is the cold-start behaviour the promoted-team prior must improve on.
- Score probabilities use a 0-30 goal grid per side, require truncation mass of
  at least `1 - 1e-9`, and are renormalized; H/D/A probabilities sum the matrix.
- Official awarded scores, match statistics, market odds, final-holdout
  outcomes, and live rows outside their snapshot boundary are not inputs.

## Dynamic promoted-team prior

The project uses the name **dynamic promoted-team prior** for cold-start
handling. A newly promoted club must not receive an arbitrary fixed safety
multiplier. Its attack and defence strengths start from separately estimated
promoted-team priors and move toward current-season evidence as eligible
top-flight matches are observed.

For an illustrative implementation on the model's latent strength scale:

```text
w(n) = n / (n + k)

attack(n)  = w(n) * observed_attack(n)  + (1 - w(n)) * promoted_attack_prior
defence(n) = w(n) * observed_defence(n) + (1 - w(n)) * promoted_defence_prior
```

`n` counts only `model_eligible=true` top-flight matches whose results were
available before the prediction time under `LEAKAGE_CONTRACT.md`.
`k` controls shrinkage persistence. The formula is the agreed mechanism, not a
license to set `k` or either prior by intuition.

## Estimation rules

- Estimate attack and defence priors separately from historically promoted clubs.
- Select `k` and every prior parameter inside chronological training data only.
- Compare candidate settings by walk-forward validation; never tune on the final
  2026-27 evaluation period.
- Carry wider uncertainty for clubs with little top-flight evidence instead of
  presenting their point estimate as equally certain.
- If a club has recent Super Lig history, compare a time-decayed historical prior
  with the generic promoted-team prior using training-only validation.
- A future second-tier bridge may transfer 1. Lig strength through an empirically
  learned league-strength offset. No 1. Lig data is added in this phase.
- Closing market odds remain forbidden as predictive inputs, including for prior
  construction or tuning.

## Leakage boundary

Every update obeys `LEAKAGE_CONTRACT.md`. For a match at time `t`, the prior and
all observed-strength terms may use only results available strictly before `t`.
An earlier kickoff alone is not proof that a match had finished. Same-date
matches without a trusted kickoff time are treated as simultaneous.
The canonical availability policy is a fixed 180-minute post-kickoff lag with
source-reviewed interruption overrides. Modeling code may not tune or shorten
that guardrail.

## Deferred implementation

The dynamic promoted-team prior belongs after the naive and independent-Poisson
baselines. Its added complexity must earn its place through chronological
out-of-sample performance and calibration, not in-sample fit.
