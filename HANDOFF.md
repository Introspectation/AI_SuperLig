# AI SuperLig handoff

Last verified: 2026-09-14 21:40 Europe/Istanbul.

This file is the shared operational handoff for coding agents (Claude Code and
Codex alternate on this repository). Treat it as a lead, not ground truth:
recheck the branch, worktree, PR/CI state, current date, and live-data
freshness before changing anything. Update this file in place at each real
checkpoint rather than creating competing handoff files. The user's local
Codex skills `handoff` and `ai-superlig-workflow` (under `~/.codex/skills/`)
define the same checkpoint and handoff conventions.

## 1. Objective and boundary

The project is building leakage-safe probabilistic predictions for the Turkish
Süper Lig. The active live season is **2026-27**. The completed **2025-26**
season remains the sealed final holdout.

User instructions (14.09.2026): continue from the handoff, follow `ROADMAP.md`,
and commit, push, and update this handoff at every checkpoint. After Stage 4
the user approved merging PR #6 and continuing with the next roadmap stage
(Stage 5).

No deployable model or live forecast exists. Stages 3-5 are development
benchmarks only. Market odds remain an external benchmark and must never enter
predictive features or Stage 3-8 selection.

## 2. Current state

- Branch: `agent/stage5-dixon-coles`, created from `main` at `8a264b2`.
- The commit containing this file is the **Stage 5 design checkpoint**: the
  declared design, fit core, and fit unit tests. Use Git for its hash.
- Stage 5 is **in progress**. The walk-forward evaluation loop, nested decay
  selection, outputs, report, and CI wiring are not implemented yet, and no
  Stage 5 development metric has been computed.
- PR #6 (Stage 4) was rebase-merged into `main` on 2026-09-14T18:19:06Z with
  explicit user approval, after both CI runs passed, including the
  cross-platform output reproducibility diff. PR #5 was merged earlier the same
  day.
- Check for an open PR with
  `gh pr list --head agent/stage5-dixon-coles`. Never merge into `main` without
  explicit user approval.

## 3. Completed work

| Stage | State | Result |
| --- | --- | --- |
| 0-2 | Complete | Data audit, canonical data and lineage, leakage boundary |
| 3 | Complete | Uniform and expanding-league H/D/A baselines |
| 3A | Complete, merged | Versioned immutable 2026-27 snapshots and freshness gate |
| 4 | Complete, merged | Independent Poisson walk-forward benchmark |
| 5 | Design and fit core committed | Time-decayed Dixon-Coles |

Stage 4 evidence (`reports/POISSON_REPORT.md`, 1,413 development matches,
2021-22 through 2024-25):

| Model | Log loss | Brier |
| --- | ---: | ---: |
| `uniform_hda` | 1.098612 | 0.666667 |
| `expanding_league_hda` | 1.060314 | 0.640070 |
| `independent_poisson` | 1.008672 | 0.600648 |

Stage 5 so far:

- `MODEL_DESIGN.md` records the declared Dixon-Coles specification and decay
  grid; `EVALUATION_PROTOCOL.md` records the nested chronological decay
  selection rule. Both were committed before any Stage 5 metric existed.
- `scripts/run_dixon_coles_evaluation.py` contains `build_fit_history`,
  `fit_dixon_coles` (weighted penalized Newton with an exact Hessian, joint
  `rho`, optional warm start), and `score_distribution`.
- `tests/test_dixon_coles_fit.py` checks the fit core:
  - zero decay without `rho` reproduces Stage 4 to machine precision;
  - synthetic `rho` is recovered;
  - analytic gradient and information match finite differences;
  - decay down-weights old results;
  - the correction cells are correct;
  - invalid inputs fail.
- Probe on real history (not committed): warm-started fits take about 4 ms
  each, and sampled fitted `rho` ranged from -0.17 to -0.01.

## 4. In-progress work

Implement the Stage 5 evaluation in `scripts/run_dixon_coles_evaluation.py`
exactly as declared:

1. Build a timeline with parsed `result_available_at` and a `_kickoff_utc`
   column (`baseline._prediction_time`). For every eligible fixture from
   2019-20 through 2024-25, in kickoff order, call
   `evaluation_time.available_history`. Reuse fits while the history size is
   unchanged; warm-start each decay chain.
2. Predict every fixture for every grid decay with fitted `rho`, then compute
   per-season grid metrics.
3. For each development season, select the decay by the protocol rule and
   assert that tuning results were available before its first kickoff.
4. Materialize three models over the development fixtures:
   - `dixon_coles_decay`: the selected decay with fitted `rho`;
   - `poisson_decay`: the selected decay with `rho = 0`;
   - `dixon_coles_no_decay`: no decay with fitted `rho`.
5. Write:
   - `reports/dixon_coles_predictions.csv` (9 decimals);
   - `reports/dixon_coles_metrics.csv`;
   - `reports/dixon_coles_grid_metrics.csv`;
   - `reports/dixon_coles_selection.csv`;
   - `reports/DIXON_COLES_REPORT.md`, with the verdict against
     `independent_poisson`, paired intervals, selected decay per season,
     ablations, the per-season grid, the `rho` summary, low-score cell
     calibration, the scoreline diagnostic, the cold-start slice, and the
     largest losses.
6. Chain the command after `run_poisson_evaluation.main()`, and switch CI to
   `python scripts/run_dixon_coles_evaluation.py`. Raise the job timeout only if
   needed.
7. Add evaluation and leakage tests, update ROADMAP/README/HANDOFF, commit,
   push, open a draft PR, and inspect CI.

## 5. Decisions and invariants

- For match time `t`: `feature(match_t) = f(matches strictly before t)` and
  `result_available_at < prediction_time`, obtained only through
  `scripts/evaluation_time.py`.
- The Stage 4 and Stage 5 specifications are declared in `MODEL_DESIGN.md`. Do
  not change the grid, the selection rule, or the penalty after seeing Stage 5
  results; report edge selections instead.
- Final evaluation is chronological and walk-forward. Current-match
  statistics, future matches, final standings, and closing odds are forbidden
  inputs. Materialize predictions before any market join.
- Iterative-fit per-match outputs are published to nine decimals; aggregates
  are computed before rounding. PR #6 CI confirmed that Windows-generated
  Stage 4 outputs reproduce on Ubuntu.
- Selecting or tuning a model after observing 2026-27 outcomes and then calling
  2025-26 untouched evidence would break the selection boundary.
- Do not set a target such as closing 60-70% of the market gap. An unexpectedly
  extreme gain triggers a leakage audit but is not automatic proof of leakage.

## 6. Failures and suspicious findings

- Stage 4 cold start: clubs with 1-3 prior matches can receive extreme rates.
  Besiktas-Pendikspor (2023-08-20) was forecast 6.99-0.74 expected goals and
  finished 1-1 (log loss 4.83). This is Stage 6 evidence. Stage 5 must fail
  loudly, not clip, if such rates make a Dixon-Coles correction invalid.
- Live data is stale (section 7). A merge-triggered acquisition at
  2026-09-14T17:51Z returned a 2026-27 CSV byte-identical to the active
  snapshot. Promotion with `--required-through 2026-09-13` (the TFF-verified
  last completed week-5 date) failed closed and wrote nothing.
- The scheduled 05:30 Istanbul acquisition runs only from `main`. Its first
  scheduled run (2026-09-15 02:30 UTC) had not happened at last verification.
- In Git Bash on this machine, `grep -c $'\r'` falsely reports CR on every line.
  Use `git ls-files --eol` to check line endings.

## 7. Live-data state

Active snapshot, unchanged:

- ID: `20260913T192813Z_d208797586a0`
- Raw file: `data/raw/football_data/2026-27__20260913T192813Z__d208797586a0.csv`
- Captured: `2026-09-13T19:28:13Z`
- Coverage: 36 results, 2026-08-14 through 2026-09-07; audit status `REVIEW`

User note (14.09.2026): the open-source data available covers seasons through
2025-26 plus the current season via Football-Data. Refresh only through that
existing source; adding another source needs explicit approval. The
`captured_at` convention is the acquisition artifact's `created_at`. A live
forecast must pass the gate in `CURRENT_SEASON_DATA.md` and validate its
fixture against an official schedule.

## 8. Remaining work (next safe actions)

1. Finish Stage 5 per section 4, then commit, push, open a draft PR, and
   inspect CI. Do not merge without approval.
2. When a scheduled acquisition artifact covers the latest TFF-verified
   completed date, promote it as a separate data checkpoint, rerun the pipeline
   and tests, and commit.
3. After Stage 5, the next roadmap stage is Stage 6, the promoted-team prior.
   It needs the user's go-ahead in the same way.

## 9. Verification

```powershell
git status --short --branch
git log --oneline main..HEAD
gh pr list --state open
python -m unittest discover -s tests
python scripts/run_poisson_evaluation.py
git diff --exit-code -- DATA_CONTRACT.md data/processed reports config/expected_schemas.json
```

Do not rerun network acquisition blindly; follow `CURRENT_SEASON_DATA.md` and
preserve every raw snapshot immutably.

## 10. Permissions and external effects

- Granted and used on 14.09.2026:
  - merge PR #5 and PR #6;
  - inspect and promote the acquisition artifact if coverage passed (refused
    by the gate);
  - Stage 4 scope and Stage 5 scope.
- Still requires explicit approval:
  - merging any later PR, or force-pushing;
  - publishing predictions, or adding external data sources;
  - the Stage 3B track, or any modeling beyond Stage 5.
- At each checkpoint, stage only intended files and commit in the
  Europe/Istanbul format below, then push the feature branch and inspect CI:

```text
DD.MM.YYYY -> genel yapilan isler

- Birinci somut degisiklik.
- Ikinci somut degisiklik.
- Onemli sinir veya karar.
```

## 11. Parking lot

- **Stage 3B live baseline publication track** (proposal, not implemented and
  not in `ROADMAP.md`): publish honest pre-kickoff forecasts in parallel with
  the research ladder. An artifact records `generated_at`, `data_as_of`,
  snapshot ID, kickoff and timezone, model and version, Git commit,
  probabilities, and freshness status. It still needs a user decision.
- **Market comparison:** an independent review computed de-vig market log loss
  `0.956823` and Brier `0.566425` on the same 1,413 matches. These figures are
  not in a committed report. Market comparison belongs to the post-freeze
  benchmark and must not steer Stages 3-8.
- **Referee effects** (user idea, unapproved): if tested later, prefer a
  leakage-safe hierarchical referee effect over a fixed multiplier, and require
  chronological out-of-sample gain.
