# AI SuperLig handoff

Last verified: 2026-09-14, about 22:45 Europe/Istanbul.

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
- Stage 6 was approved.
- A separate data checkpoint that promotes a snapshot is approved once
  Football-Data covers the TFF-verified latest completed date.

No deployable model or live forecast exists. Stages 3-6 are development
benchmarks only. Market odds remain an external benchmark and must never enter
predictive features or Stage 3-8 selection.

## 2. Current state

- Branch: `agent/stage6-promoted-team-prior`, from `main` at `7b1489d`.
- Draft PR #8 targets `main`. The design checkpoint `250242f` passed CI.
- The commit containing this file is the **Stage 6 evaluation checkpoint**; use
  Git for its hash. Its CI result must be verified with `gh pr checks 8`.
- CI now runs `python scripts/run_promoted_prior_evaluation.py`, which chains
  every stage, with a job timeout of 20 minutes.
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
| 6 | Complete on PR #8 | Dynamic promoted-team prior, nested k selection, ablations |
| 7 | Next in roadmap | Small-data ML challengers (needs user go-ahead) |

Development evidence (1,413 matches, 2021-22 through 2024-25):

| Model | Log loss | Brier | Promoted-club fixtures log loss |
| --- | ---: | ---: | ---: |
| `independent_poisson` (Stage 4) | 1.008672 | 0.600648 | - |
| `poisson_decay` (Stage 5 ablation) | 0.995139 | 0.591252 | 1.027245 |
| `dixon_coles_decay` (Stage 5 candidate) | 0.995379 | 0.591547 | 1.029932 |
| `dixon_coles_promoted_prior` (Stage 6 candidate) | 0.986679 | 0.587685 | 1.000308 |
| `dixon_coles_promoted_point` (no-uncertainty ablation) | 0.986625 | 0.587663 | 1.000126 |
| `poisson_decay_promoted_prior` (`rho = 0` ablation) | 0.986863 | 0.587326 | 0.999066 |

- **Declared gate:** GO on point estimates. Promoted-club fixtures number
  415/1413.
- **Paired differences** versus `dixon_coles_decay`:
  - promoted-club fixtures -0.029623 [-0.061745, +0.002498];
  - all fixtures -0.008700 [-0.018153, +0.000752].
  - **Both approximate intervals include zero.**
- **Every `k` selection** (3 models × 4 seasons) is **k = 64, the grid maximum**.
  The prior therefore dominates promoted clubs for most of a season
  (w = 0.35 after 34 matches). The grid is not extended post hoc.
- **Uncertainty propagation** is not justified on H/D/A metrics; the point
  ablation is marginally better.
- **Slices** (candidate minus Stage 5):
  - fewest current-season matches 1-5: -0.110 (58 fixtures);
  - promoted clubs with no earlier data history: -0.039 (306 fixtures);
  - clubs with earlier history: -0.004 (109 fixtures).
- **Prior offsets** (`reports/promoted_prior_offsets.csv`): promoted-club
  attack is about -0.08 to -0.11 below the previous-season reference (SD about
  0.2), and defence -0.01 to -0.05 (SD about 0.1).
- **Files:**
  - code: `scripts/run_promoted_prior_evaluation.py`;
  - tests: `tests/test_promoted_prior_evaluation.py`;
  - report: `reports/PROMOTED_PRIOR_REPORT.md`, plus the `promoted_prior_*`
    CSVs.
- `run_dixon_coles_evaluation.py` now exposes `evaluate`, `run_and_write`, and
  `Stage5State`, and stores per-season appearance counts. Stage 5 outputs are
  unchanged. `k = 0` is verified to reproduce Stage 5 predictions exactly
  before outputs are written.

## 4. In-progress work

None uncommitted at this checkpoint. Working-copy `M` flags on generated
reports can be CRLF-only; trust `git diff --exit-code`.

## 5. Decisions and invariants

- For match time `t`: `feature(match_t) = f(matches strictly before t)` and
  `result_available_at < prediction_time`, obtained only through
  `scripts/evaluation_time.py`.
- Stage 4-6 specifications are in `MODEL_DESIGN.md` and selection rules in
  `EVALUATION_PROTOCOL.md`, each committed before its metrics. Do not change a
  grid, rule, or candidate after seeing results. Stage 5's 0-40 goal grid is the
  only pre-metric amendment.
- Promoted status uses only previous-season membership. Prior offsets use only
  completed seasons (from 2018-19) before the target season, via end-of-season
  refits through `evaluation_time`.
- Stage 8 (candidate freeze) must weigh these findings:
  - Stage 5 `rho` added no H/D/A value;
  - Stage 6 uncertainty added no H/D/A value;
  - Stage 6 gains have intervals that include zero, with k at the grid edge.
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
  - 2025-26 results were used only as training data, and no 2025-26 metric was
    computed;
  - Stage 5 models gave about 20/20/60, with 1-2 the most likely score.

## 6. Failures and suspicious findings

- **Team alias gap in live data:** 2026-27 rows use "Erzurumspor", while
  2018-19 and 2020-21 rows use "Erzurumspor FK". A live fit would treat them as
  different clubs. Review `config/team_aliases.csv` before any live forecast.
  This does not affect development metrics.
- **Cold start:** Stage 5 made sparse-history clubs worse (Besiktas-Pendikspor
  log loss 5.66). Stage 6 removes that match from the top-5 losses.
- **Performance:** CI runtime grew. On 14.09.2026 on Windows, two full-chain
  runs took 319 s and 360 s, and the 61-test suite took 125 s. Stage 5
  walk-forward fitting and the Stage 6 grid dominate. Watch CI duration against
  the 20-minute timeout; profile before adding stages.
- **Live data is stale** (section 7). The merge-triggered acquisition at
  2026-09-14T17:51Z was byte-identical, and promotion through 2026-09-13 failed
  closed. The first scheduled 05:30 Istanbul run (2026-09-15 02:30 UTC) was not
  yet observed.
- In Git Bash here, `grep -c $'\r'` falsely reports CR; use
  `git ls-files --eol`.

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

1. Verify CI on PR #8 for this checkpoint and fix on the branch if it fails.
   Merge only with explicit user approval.
2. After a scheduled acquisition covers the TFF-verified latest completed date,
   promote it as a separate data checkpoint (approved). Rerun
   `python scripts/run_promoted_prior_evaluation.py` and the tests, then commit.
3. Stage 7 (small-data ML challengers) needs a new user go-ahead. Declare
   features, their lookback boundaries, the model family, and the tuning rule
   before any metric.

## 9. Verification

```powershell
git status --short --branch
git log --oneline main..HEAD
gh pr checks 8
python -m unittest discover -s tests
python scripts/run_promoted_prior_evaluation.py
git diff --exit-code -- DATA_CONTRACT.md data/processed reports config/expected_schemas.json
```

Do not rerun network acquisition blindly; follow `CURRENT_SEASON_DATA.md` and
preserve every raw snapshot immutably.

## 10. Permissions and external effects

- Granted on 14.09.2026:
  - merge PR #5, #6, and #7 (all done);
  - promote acquisition artifacts that pass the coverage gate;
  - Stage 4, 5, and 6 scope.
- Still requires explicit approval:
  - merging PR #8 or any later PR, or force-pushing;
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
  freshness status. It needs a user decision; the chat forecast showed why
  pre-kickoff timing and the freshness gate matter.
- **Market comparison:** an independent review computed de-vig market log loss
  `0.956823` and Brier `0.566425` on the same 1,413 matches. These figures are
  not in a committed report; market comparison belongs to the post-freeze
  benchmark.
- **Returning-club historical prior** and **1. Lig bridge**: deferred in the
  Stage 6 design.
- **Wider k grid:** the edge selection suggests stronger shrinkage. Testing it
  would need a new pre-registered design, and development data has already been
  seen.
- **Referee effects** (user idea, unapproved): if tested later, prefer a
  leakage-safe hierarchical referee effect and require chronological
  out-of-sample gain.
