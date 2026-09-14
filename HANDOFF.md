# AI SuperLig handoff

Last verified: 2026-09-14, Europe/Istanbul.

This file is the shared operational handoff for coding agents. Treat it as a
lead, not ground truth: recheck the branch, worktree, PR/CI state, current date,
and live-data freshness before changing anything. Update this file in place at
the next real transfer checkpoint rather than creating competing handoff files.

## Objective and boundary

The project is building leakage-safe probabilistic predictions for the Turkish
Süper Lig. The active live season is **2026-27**. The completed **2025-26**
season remains the sealed final holdout.

No deployable model or full score-distribution model exists yet. Do not present
the naive H/D/A baseline as one. Market odds remain an external benchmark and
must never enter predictive features.

## Repository state at transfer

- Branch: `agent/2026-27-live-snapshots`
- Pre-handoff checkpoint: `c0bd440`
- Remote parity was verified before this handoff commit.
- Open PR: [#5 - 2026-27 canli snapshot ve tazelik katmani](https://github.com/Introspectation/AI_SuperLig/pull/5)
- PR state at verification: draft, targeting `main`, all three checks successful.
- The worktree was clean before this handoff was added.
- Never merge into `main` without explicit user approval.

The commit containing this file is the durable handoff checkpoint; use Git for
its final hash rather than copying a self-referential hash into this document.

## Completed work

| Stage | State | Result |
| --- | --- | --- |
| 0 | Complete | Historical and current-season data audit |
| 1 | Complete | Canonical data, immutable lineage, kickoff backfill, isolated market table |
| 2 | Complete | Strict result-availability and leakage boundary |
| 3 | Complete | Uniform and expanding-league H/D/A baselines |
| 3A | Complete | Versioned immutable 2026-27 snapshots and freshness gate |
| 4 | Next in current roadmap | Independent Poisson |

Read `ROADMAP.md`, `EVALUATION_PROTOCOL.md`, `LEAKAGE_CONTRACT.md`, and
`CURRENT_SEASON_DATA.md` before modifying the model or live-data flow.

## Live-data state

Active snapshot:

- ID: `20260913T192813Z_d208797586a0`
- Raw file: `data/raw/football_data/2026-27__20260913T192813Z__d208797586a0.csv`
- Captured: `2026-09-13T19:28:13Z`
- Coverage: 36 results, from 2026-08-14 through 2026-09-07
- Audit status: `REVIEW`

This snapshot is valid immutable evidence but is stale for any prediction that
requires completed results through 2026-09-13. A current forecast must pass the
acquisition-age and coverage-through checks documented in
`CURRENT_SEASON_DATA.md` and must verify its fixture against an official
schedule source.

## Baseline evidence

The chronological development set contains 1,413 matches from 2021-22 through
2024-25. The 2025-26 holdout and 2026-27 live season are absent from these
metrics.

| Model | Log loss | Brier |
| --- | ---: | ---: |
| `uniform_hda` | 1.098612 | 0.666667 |
| `expanding_league_hda` | 1.060314 | 0.640070 |

`expanding_league_hda` knows only league-wide H/D/A frequencies available
before each prediction. It does not know team identity, form, squads, match
statistics, referees, expected goals, or scorelines. See
`reports/BASELINE_REPORT.md`.

An independent review also recomputed the isolated de-vig market benchmark on
the same 1,413 matches:

- Market log loss: `0.956823`
- Market Brier: `0.566425`
- Expanding baseline closes `27.01%` of the uniform-to-market log-loss gap.

These market figures are not yet in a committed generated comparison report.
The percentage is only a descriptive fraction of that measured log-loss gap,
not a fraction of all predictive information.

## Proposed parallel publication decision

The team discussed starting pre-kickoff publication now instead of waiting for
the final Stage 10 runner. The recommended revision is:

- Add a **Stage 3B live baseline publication track** now.
- Keep Stage 4 independent Poisson as the next actual model.
- Let live publication run in parallel with the research ladder.
- Keep Stage 10 as runner hardening/automation, not as the first published
  prediction.

A Stage 3B artifact must be labeled as an H/D/A-only league-frequency baseline.
It should record at least `generated_at`, `data_as_of`, source snapshot ID,
fixture kickoff and timezone, model/version, Git commit, H/D/A probabilities,
and freshness status. There is currently no committed `predictions/` directory
and no pre-kickoff forecast history.

This proposal has not been implemented. Do not claim that ROADMAP.md already
contains it.

## Non-negotiable evaluation rules

For a match at prediction time `t`:

```text
feature(match_t) = f(matches strictly before t)
result_available_at < prediction_time
```

- Final evaluation is chronological/walk-forward; random shuffled final splits
  are forbidden.
- Current-match statistics, future matches, final standings, and closing odds
  are forbidden predictive inputs.
- Materialize model predictions before any market join.
- Publishing a frozen model during 2026-27 does not itself contaminate the
  2025-26 holdout. Selecting or tuning a model after observing 2026-27 outcomes
  and later calling 2025-26 untouched final evidence would break the intended
  selection boundary.
- Do not set an unsupported target that Poisson must close 60-70% of the market
  gap. Measure first. An unexpectedly extreme gain triggers a leakage audit but
  is not automatic proof of leakage.

## Parking lot: referee effects

The user proposed referee-dependent weighting. This is a future research idea,
not an implemented or approved Stage 4 feature.

If tested later, prefer a leakage-safe hierarchical/partial-pooling referee
effect over a fixed multiplier: use only pre-prediction assignments and prior
matches, shrink low-sample referees toward the league mean, account for team and
assignment confounding, and require chronological out-of-sample gain. Cards,
fouls, or penalties may be more defensible first targets than directly changing
match-result probabilities.

## Proposed next checkpoint

Confirm scope with the user, then consider this coherent increment:

1. Revise `ROADMAP.md` to add the parallel Stage 3B publication track.
2. Add market comparison through a separate post-prediction evaluator/report.
3. Define an immutable pre-kickoff prediction contract.
4. Implement the honest H/D/A-only baseline publisher.
5. Refresh/promote 2026-27 data only when freshness and coverage checks pass.
6. Run relevant tests and reproducibility commands.
7. Commit and push the feature branch; inspect GitHub Actions.

Do not fold independent Poisson into the same checkpoint unless the user opens
that scope explicitly.

## Git and public-repository rules

At each successful checkpoint, stage only intended files and use the user's
Europe/Istanbul commit format:

```text
DD.MM.YYYY -> genel yapilan isler

- Birinci somut degisiklik.
- Ikinci somut degisiklik.
- Onemli sinir veya karar.
```

Push the feature branch and inspect CI. Never force-push, silently modify raw
source files, commit secrets, or merge without explicit approval.

## Resume checks

Run these before continuing:

```powershell
git status --short --branch
git log --oneline main..HEAD
gh pr list --state open
python scripts/run_data_foundation.py
python scripts/run_baseline_evaluation.py
```

Do not rerun network acquisition blindly. Follow `CURRENT_SEASON_DATA.md` and
preserve every raw snapshot immutably.
