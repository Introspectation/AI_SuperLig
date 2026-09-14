# AI SuperLig handoff

Last verified: 2026-09-14, about 22:00 Europe/Istanbul.

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
- Merging PR #5, #6, and #7 was approved and done.
- Stage 6 was approved and started.
- A separate data checkpoint that promotes a snapshot is approved once
  Football-Data covers the TFF-verified latest completed date.

No deployable model or live forecast exists. Stages 3-6 are development
benchmarks only. Market odds remain an external benchmark and must never enter
predictive features or Stage 3-8 selection.

## 2. Current state

- Branch: `agent/stage6-promoted-team-prior`, from `main` at `7b1489d`
  (PR #7, Stage 5, rebase-merged 2026-09-14T18:49:02Z after green CI).
- The commit containing this file is the **Stage 6 design checkpoint**: the
  declared promoted-team prior specification and k-selection rule, committed
  before any Stage 6 code or metric. Use Git for its hash.
- Stage 6 implementation has not started. Check for the draft PR with
  `gh pr list --head agent/stage6-promoted-team-prior` and verify its CI.
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
| 6 | Design declared | Dynamic promoted-team prior |

Development evidence (1,413 matches, 2021-22 through 2024-25):

| Model | Log loss | Brier |
| --- | ---: | ---: |
| `uniform_hda` | 1.098612 | 0.666667 |
| `expanding_league_hda` | 1.060314 | 0.640070 |
| `independent_poisson` (Stage 4) | 1.008672 | 0.600648 |
| `poisson_decay` (Stage 5 ablation) | 0.995139 | 0.591252 |
| `dixon_coles_no_decay` (Stage 5 ablation) | 1.009002 | 0.600808 |
| `dixon_coles_decay` (Stage 5 candidate) | 0.995379 | 0.591547 |

- Stage 5 gain comes from recency decay; the low-score correction is not
  justified on H/D/A metrics (candidate minus `poisson_decay` +0.000240
  [-0.002336, +0.002816]).
- Selected decays: 0.0015/day for 2021-22 and 0.003/day for later seasons.
- Reports: `reports/BASELINE_REPORT.md`, `reports/POISSON_REPORT.md`, and
  `reports/DIXON_COLES_REPORT.md`.

## 4. In-progress work: Stage 6 implementation plan

Implement exactly the declared design in `MODEL_DESIGN.md` ("Stage 6
implementation (declared)") and `EVALUATION_PROTOCOL.md` ("Stage 6
chronological prior-strength selection"):

1. Create `scripts/run_promoted_prior_evaluation.py`. It must reuse the Stage 5
   state (timeline, targets, walk-forward contexts, decay selection) without
   refitting twice. Consider refactoring `run_dixon_coles_evaluation` to return
   its contexts, keeping Stage 5 outputs byte-identical.
2. For each season from 2018-19 to 2023-24, run end-of-season base refits for
   each selected decay and `rho` setting, through `evaluation_time`. Compute
   promoted-club offsets against the `S-1` reference level.
3. Apply the blend and Gauss-Hermite uncertainty (5 nodes per log rate, via
   `numpy.polynomial.hermite_e.hermegauss`) for k in {0, 4, 8, 16, 32, 64}.
   `k = 0` must reproduce Stage 5 predictions exactly.
4. Nested k selection per model. Outputs:
   - `reports/promoted_prior_predictions.csv`, `..._metrics.csv`,
     `..._selection.csv`;
   - `reports/PROMOTED_PRIOR_REPORT.md`, with the gate on promoted-club
     fixtures, ablations, and cold-start slices by n and by prior history.
5. Tests:
   - blend math and the `k = 0` equivalence;
   - promoted-status leakage (only `S-1` rows);
   - offsets use only completed earlier seasons;
   - uncertainty mixing sums to one;
   - selection rule and committed-output checks.
6. Chain CI to the new command, then update ROADMAP/README/HANDOFF, commit,
   push, and inspect CI.

## 5. Decisions and invariants

- For match time `t`: `feature(match_t) = f(matches strictly before t)` and
  `result_available_at < prediction_time`, obtained only through
  `scripts/evaluation_time.py`.
- Stage 4-6 specifications are declared in `MODEL_DESIGN.md` and selection
  rules in `EVALUATION_PROTOCOL.md`, each committed before its metrics. Do not
  change a grid, rule, or candidate after seeing results. Record any
  unavoidable pre-metric amendment explicitly; Stage 5's 0-40 goal grid is the
  precedent.
- Final evaluation is chronological and walk-forward. Current-match
  statistics, future matches, final standings, and closing odds are forbidden
  inputs. Materialize predictions before any market join.
- Iterative-fit per-match outputs are published to nine decimals; aggregates
  are computed before rounding. Stage 4 and 5 outputs reproduced on Ubuntu CI.
- Selecting or tuning a model after observing 2026-27 outcomes and then calling
  2025-26 untouched evidence would break the selection boundary.
- On 14.09.2026 the user asked in chat what the models say about Gaziantep
  FK-Fenerbahçe (14.09 20:00). A research forecast was computed as of kickoff
  and not committed or published:
  - the freshness gate failed (snapshot ends 2026-09-07);
  - the fit used 2025-26 results as training data only, and no 2025-26 metric
    was computed;
  - Stage 5 models gave about 20/20/60 for home/draw/away, with 1-2 the most
    likely score.

## 6. Failures and suspicious findings

- **Cold start** is the main weakness, and Stage 5 decay makes it worse:
  - Besiktas-Pendikspor has log loss 5.66.
  - Fixtures with an unseen club are +0.0199 worse versus Stage 4.
  - This is the Stage 6 target.
- **Stage 5 per-season grid (descriptive):** the in-season optimum hit the grid
  maximum in 2021-22 and 2024-25, and no decay was best in 2022-23. Do not
  retune the grid.
- **Live data is stale** (section 7). The merge-triggered acquisition at
  2026-09-14T17:51Z was byte-identical to the active snapshot, and promotion
  through 2026-09-13 failed closed. The first scheduled 05:30 Istanbul run
  (2026-09-15 02:30 UTC) was not yet observed.
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
- Gaziantep FK-Fenerbahçe on 14.09 is part of week 5.

A live forecast must pass the gate in `CURRENT_SEASON_DATA.md` and validate its
fixture against an official schedule.

## 8. Remaining work (next safe actions)

1. Implement Stage 6 per section 4, then commit, push, update the draft PR, and
   inspect CI. Merge only with explicit user approval.
2. After a scheduled acquisition covers the TFF-verified latest completed date,
   promote it as a separate data checkpoint (approved), rerun the full chain
   and tests, and commit.
3. Stage 7 (small-data ML challengers) needs a new user go-ahead.

## 9. Verification

```powershell
git status --short --branch
git log --oneline main..HEAD
gh pr list --state open
python -m unittest discover -s tests
python scripts/run_dixon_coles_evaluation.py
git diff --exit-code -- DATA_CONTRACT.md data/processed reports config/expected_schemas.json
```

Do not rerun network acquisition blindly; follow `CURRENT_SEASON_DATA.md` and
preserve every raw snapshot immutably.

## 10. Permissions and external effects

- Granted on 14.09.2026:
  - merge PR #5, #6, and #7 (all done);
  - inspect and promote acquisition artifacts that pass the coverage gate;
  - Stage 4, 5, and 6 scope.
- Still requires explicit approval:
  - merging the Stage 6 PR or any later PR, or force-pushing;
  - publishing predictions, or adding external data sources;
  - the Stage 3B track, or Stage 7 and later.
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
  freshness status. It needs a user decision. The chat forecast above shows why
  the freshness gate and pre-kickoff timing matter.
- **Market comparison:** an independent review computed de-vig market log loss
  `0.956823` and Brier `0.566425` on the same 1,413 matches. These figures are
  not in a committed report; market comparison belongs to the post-freeze
  benchmark.
- **Returning-club historical prior** and **1. Lig bridge**: deferred in the
  Stage 6 design.
- **Referee effects** (user idea, unapproved): if tested later, prefer a
  leakage-safe hierarchical referee effect and require chronological
  out-of-sample gain.
