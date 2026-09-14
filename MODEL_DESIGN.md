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

## Time-decayed Dixon-Coles (Stage 5, declared)

Declared on 14.09.2026 before any Stage 5 development metric was computed. Fit
code lives in `scripts/run_dixon_coles_evaluation.py`; development evidence is
in `reports/DIXON_COLES_REPORT.md`.

```text
P(home=x, away=y) = tau(x, y) * Poisson(x; home_rate) * Poisson(y; away_rate)
tau(0,0) = 1 - home_rate * away_rate * rho    tau(0,1) = 1 + home_rate * rho
tau(1,0) = 1 + away_rate * rho                tau(1,1) = 1 - rho
weight(match) = exp(-decay_per_day * days_before_latest_kickoff_in_history)
```

- Rates, the fixed N(0, 1) team-strength penalty, and unseen-club handling are
  unchanged from Stage 4. The score grid is 0-40 goals per side (see the
  amendment below).
- `rho` is estimated jointly with team strengths by weighted penalized maximum
  likelihood in every fit; it is not a tuned hyperparameter. A fit or fixture
  whose correction factors are not strictly positive fails loudly.
- Weights are anchored at the most recent kickoff in the available history, so
  a fit depends only on that history and may be reused by later cutoffs with
  the same history.
- Decay grid per day, with half-life in days: 0 (none), 0.0005 (1386),
  0.001 (693), 0.0015 (462), 0.002 (347), 0.003 (231), 0.005 (139). The grid is
  fixed; a selection at its edge is reported, not extended.
- Decay is selected by the nested chronological rule in
  `EVALUATION_PROTOCOL.md`.
- The candidate is `dixon_coles_decay`. Ablations `poisson_decay` (selected
  decay, `rho = 0`) and `dixon_coles_no_decay` (no decay, fitted `rho`)
  attribute any gain; `independent_poisson` is the Stage 4 reference.
- The promoted-team prior, match statistics, market odds, and the 2025-26
  holdout remain out of scope.

Amendment made before any Stage 5 metric was computed (14.09.2026): the first
full grid run stopped. With the Stage 4 0-30 goal grid, one declared fit lost
more than `1e-9` probability mass: Besiktas-Pendikspor on 2023-08-20, decay
0.005, expected home goals 8.83 against a club with one prior match. The
Dixon-Coles correction itself was valid for that fixture. Stage 5 therefore
uses a 0-40 goal grid per side with the same truncation check. This is a
numerical truncation change chosen without any evaluation result; Stage 4
keeps its 0-30 grid.

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

## Stage 6 implementation (declared)

Declared on 14.09.2026 before any Stage 6 metric was computed. It applies the
agreed blend to Stage 5 base fits. Nothing is refitted for different `k`
values.

For a fixture in season `S` predicted at time `t`:

- **Promoted club:** a club in the fixture with no eligible match in season
  `S-1`. Only completed past-season rows are used. 2017-18 has no predecessor,
  so promoted status is defined from 2018-19 onward.
- **n:** the club's eligible season-`S` matches with `result_available_at < t`.
- **Observed strength:** the club's attack and defence in the Stage 5 base fit
  at `t` (0 for an unseen club).
- **Reference level:** the mean base-fit attack (and, separately, defence) over
  clubs with an eligible match in season `S-1`.
- **Prior offsets:** for every completed season `s'` from 2018-19 up to `S-1`:
  - refit the same base (same decay and `rho` setting) on all results available
    at the end of `s'`;
  - each club promoted into `s'` contributes its attack (defence) minus that
    fit's reference level for `s'`.
- **Prior:** the current reference level plus the mean offset. The prior
  variance is the sample variance (`ddof = 1`) of the offsets; at least two
  offsets are required.
- **Blend:** `w = n / (n + k)` and
  `strength = w * observed + (1 - w) * prior`. `k = 0` disables the prior
  (`w = 1`). Non-promoted clubs are unchanged.
- **Uncertainty:** a promoted club's attack and defence are normal on the
  log-strength scale, centred on the blended value, with variance
  `(1 - w) * prior_variance`.
  - The home log rate variance adds home attack and away defence variances;
    the away log rate variance adds away attack and home defence variances.
  - The score matrix is averaged over a 5-point Gauss-Hermite grid for each
    log rate.
  - Dixon-Coles factors must stay strictly positive at every node.
- **k grid:** 0, 4, 8, 16, 32, 64. `k` is selected per development season by
  the nested rule in `EVALUATION_PROTOCOL.md`, at that season's Stage 5 decay.
- **Models:**
  - candidate `dixon_coles_promoted_prior`: Dixon-Coles decay base, blend, and
    uncertainty;
  - ablation `dixon_coles_promoted_point`: the same without uncertainty;
  - ablation `poisson_decay_promoted_prior`: `rho = 0` base, blend, and
    uncertainty.

  Each model selects its own `k`. The Stage 5 references are
  `dixon_coles_decay` and `poisson_decay`.
- **Gate:** GO requires lower log loss than `dixon_coles_decay` on development
  fixtures involving a promoted club, with overall development log loss no
  worse. Otherwise the result is reported as characterized.
- **Deferred:** a time-decayed historical prior for returning clubs and the
  1. Lig bridge.

Added complexity must earn its place through chronological out-of-sample
performance and calibration, not in-sample fit.
