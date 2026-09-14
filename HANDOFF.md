# AI SuperLig handoff

Last verified: 2026-09-14 22:35 Europe/Istanbul.

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

User instructions and approvals (14.09.2026):

- Continue from the handoff, follow `ROADMAP.md`, and commit, push, and update
  this handoff at every checkpoint.
- Merging PR #5, #6, #7, and #8 was approved and done.
- Stage 7 (ML challengers) was approved and started.
- A separate data checkpoint that promotes a snapshot is approved once
  Football-Data covers the TFF-verified latest completed date.

No deployable model or live forecast exists. Stages 3-7 are development
benchmarks only. Market odds remain an external benchmark and must never enter
predictive features or Stage 3-8 selection.

## 2. Current state

- Branch: `agent/stage7-ml-challengers`, from `main` at `f12778f` (PR #8,
  Stage 6, rebase-merged 2026-09-14T19:33:35Z after green CI).
- The commit containing this file is the **Stage 7 design checkpoint**. It
  holds the declared ML challenger specification and penalty-selection rule,
  committed before any Stage 7 code or metric. Use Git for its hash.
- Stage 7 implementation has not started. Find the draft PR with
  `gh pr list --head agent/stage7-ml-challengers` and verify its CI.
- CI runs `python scripts/run_promoted_prior_evaluation.py` (all stages
  through 6). PR #8's CI took about 3.5 minutes; the job timeout is 20 minutes.
- Never merge into `main` without explicit user approval.
- Local Git Bash quirk: `TZ=Europe/Istanbul date` prints UTC; plain `date` shows
  local Istanbul time.

## 3. Completed work

| Stage | State | Result |
| --- | --- | --- |
| 0-2 | Complete, merged | Data audit, canonical data and lineage, leakage boundary |
| 3 / 3A | Complete, merged | Naive baselines; immutable 2026-27 snapshots and freshness gate |
| 4 | Complete, merged | Independent Poisson walk-forward benchmark |
| 5 | Complete, merged | Time-decayed Dixon-Coles, nested decay selection, ablations |
| 6 | Complete, merged | Dynamic promoted-team prior, nested k selection, ablations |
| 7 | Design declared | Small-data ML challengers |

Development evidence (1,413 matches, 2021-22 through 2024-25):

| Model | Log loss | Brier |
| --- | ---: | ---: |
| `uniform_hda` | 1.098612 | 0.666667 |
| `expanding_league_hda` | 1.060314 | 0.640070 |
| `independent_poisson` (Stage 4) | 1.008672 | 0.600648 |
| `poisson_decay` (Stage 5 ablation) | 0.995139 | 0.591252 |
| `dixon_coles_decay` (Stage 5 candidate) | 0.995379 | 0.591547 |
| `dixon_coles_promoted_prior` (Stage 6 candidate) | 0.986679 | 0.587685 |
| `dixon_coles_promoted_point` (Stage 6 ablation) | 0.986625 | 0.587663 |
| `poisson_decay_promoted_prior` (Stage 6 ablation) | 0.986863 | 0.587326 |

Stage caveats for the Stage 8 freeze:

- **Stage 5:** the gain comes from recency decay; `rho` adds no H/D/A value.
- **Stage 6:** passes its gate on point estimates, but:
  - its paired intervals include zero;
  - all 12 `k` selections are at the grid maximum (64);
  - uncertainty propagation adds no H/D/A value.

Reports: `reports/BASELINE_REPORT.md`, `POISSON_REPORT.md`,
`DIXON_COLES_REPORT.md`, and `PROMOTED_PRIOR_REPORT.md`.

## 4. In-progress work: Stage 7 implementation plan

Implement exactly the declared design in `MODEL_DESIGN.md` ("Small-data ML
challengers (Stage 7, declared)") and `EVALUATION_PROTOCOL.md` ("Stage 7
chronological penalty selection"):

1. Create `scripts/run_ml_challenger_evaluation.py`. Reuse the Stage 5 state
   and the Stage 6 grid, which holds Stage 6 candidate probabilities for every
   grid-season fixture at each selected decay and `k`. Expose Stage 6 grid
   state from `run_promoted_prior_evaluation` without changing its outputs.
2. Build features for every eligible fixture from 2019-20 onward at its own
   kickoff:
   - form, shots-on-target share, and rest days from
     `evaluation_time.available_history`;
   - Stage 6 logits and promoted flags.
3. Write the penalized multinomial logistic Newton fit with offsets; a draw is
   the reference class. `lambda = inf` must reproduce Stage 6 exactly for
   offset models.
4. Run walk-forward refits over training-set changes for 2020-21 through
   2024-25, for each lambda and model, then the nested lambda selection.
5. Outputs:
   - `reports/ml_predictions.csv`, `ml_metrics.csv`, `ml_grid_metrics.csv`,
     `ml_selection.csv`;
   - `reports/ML_CHALLENGER_REPORT.md`, with the gate, ablations, calibration
     tables (calibration-in-the-large and 10-bin per-class ECE), and coefficient
     summaries.
6. Tests:
   - fit math, the `inf` equivalence, and feature leakage (future results
     cannot change features);
   - the selection rule and committed-output checks.
7. Chain CI to the new command, profile runtime, update ROADMAP/README/HANDOFF,
   commit, push, and inspect CI.

## 5. Decisions and invariants

- For match time `t`: `feature(match_t) = f(matches strictly before t)` and
  `result_available_at < prediction_time`, obtained only through
  `scripts/evaluation_time.py`. Past-match statistics such as shots on target
  are legal history; a match's own statistics never are.
- Stage 4-7 specifications are in `MODEL_DESIGN.md` and selection rules in
  `EVALUATION_PROTOCOL.md`, each committed before its metrics. Do not change a
  grid, rule, feature, or candidate after seeing results. Stage 5's 0-40 goal
  grid is the only pre-metric amendment so far.
- Final evaluation is chronological and walk-forward. Current-match
  statistics, future matches, final standings, and closing odds are forbidden
  inputs. Materialize predictions before any market join.
- Iterative-fit per-match outputs are published to nine decimals; aggregates
  are computed before rounding.
- Selecting or tuning a model after observing 2026-27 outcomes and then calling
  2025-26 untouched evidence would break the selection boundary.
- On 14.09.2026 the user asked in chat about Gaziantep FK-Fenerbahçe
  (14.09 20:00). A research forecast was computed as of kickoff and not
  committed or published:
  - the freshness gate failed;
  - 2025-26 results were used only as training data;
  - Stage 5 models gave about 20/20/60, with 1-2 the most likely score.

## 6. Failures and suspicious findings

- **Team alias gap in live data:** 2026-27 rows use "Erzurumspor", while
  2018-19 and 2020-21 rows use "Erzurumspor FK". Review
  `config/team_aliases.csv` before any live forecast.
- **Runtime:** a local full chain took 319-360 s on Windows, while CI took about
  3.5 minutes. Stage 7 adds walk-forward logistic refits, so profile and keep CI
  under its timeout.
- **Live data is stale** (section 7). The merge-triggered acquisition at
  2026-09-14T17:51Z was byte-identical, and promotion through 2026-09-13 failed
  closed. The first scheduled 05:30 Istanbul run (2026-09-15 02:30 UTC) was not
  yet observed.
- In Git Bash here, `grep -c $'\r'` falsely reports CR; use
  `git ls-files --eol`. Working-copy `M` flags on generated reports can be
  CRLF-only.

## 7. Live-data state

Active snapshot, unchanged:

- ID: `20260913T192813Z_d208797586a0`
- Raw file: `data/raw/football_data/2026-27__20260913T192813Z__d208797586a0.csv`
- Captured: `2026-09-13T19:28:13Z`
- Coverage: 36 results, 2026-08-14 through 2026-09-07; audit status `REVIEW`

User note: open-source data covers seasons through 2025-26 plus the current
season via Football-Data. Refresh only through that source.

Promotion procedure:

- `captured_at` = the acquisition artifact's `created_at`.
- `--required-through` = the latest completed match date verified on TFF.

A live forecast must pass the gate in `CURRENT_SEASON_DATA.md` and validate its
fixture against an official schedule.

## 8. Remaining work (next safe actions)

1. Implement Stage 7 per section 4, then commit, push, update the draft PR, and
   inspect CI. Merge only with explicit user approval.
2. After a scheduled acquisition covers the TFF-verified latest completed date,
   promote it as a separate data checkpoint (approved), rerun the full chain
   and tests, and commit.
3. Stage 8 (candidate freeze) needs a new user go-ahead. It must freeze code,
   hyperparameters, and the decision rule before the one-time 2025-26 holdout.

## 9. Verification

```powershell
git status --short --branch
git log --oneline main..HEAD
gh pr list --state open
python -m unittest discover -s tests
python scripts/run_promoted_prior_evaluation.py
git diff --exit-code -- DATA_CONTRACT.md data/processed reports config/expected_schemas.json
```

Do not rerun network acquisition blindly; follow `CURRENT_SEASON_DATA.md` and
preserve every raw snapshot immutably.

## 10. Permissions and external effects

- Granted on 14.09.2026:
  - merge PR #5, #6, #7, and #8 (all done);
  - promote acquisition artifacts that pass the coverage gate;
  - Stage 4-7 scope.
- Still requires explicit approval:
  - merging the Stage 7 PR or any later PR, or force-pushing;
  - publishing predictions, or adding external data sources;
  - the Stage 3B track, or Stage 8 and later.
- At each checkpoint, stage only intended files and commit in the
  Europe/Istanbul format below, then push the feature branch and inspect CI:

```text
DD.MM.YYYY -> genel yapilan isler

- Birinci somut degisiklik.
- Ikinci somut degisiklik.
- Onemli sinir veya karar.
```

## 11. Parking lot

- **Stage 3B live baseline publication track** (proposal, not in `ROADMAP.md`):
  honest pre-kickoff forecasts with `generated_at`, `data_as_of`, snapshot ID,
  kickoff and timezone, model and version, Git commit, probabilities, and
  freshness status. It needs a user decision.
- **Market comparison:** an independent review computed de-vig market log loss
  `0.956823` and Brier `0.566425` on the same 1,413 matches. These figures are
  not in a committed report; market comparison belongs to the post-freeze
  benchmark.
- **Returning-club historical prior**, **1. Lig bridge**, **wider Stage 6 k
  grid**: deferred; any of them needs a new pre-registered design.
- **Deferred ML inputs:** tree ensembles, Elo, `HxG/AxG`, referee effects.
