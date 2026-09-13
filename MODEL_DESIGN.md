# Model design decisions

This file records decisions that future modeling code must follow. It does not
implement a predictive model.

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
