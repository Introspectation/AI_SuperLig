# AI SuperLig handoff

Last verified: 2026-09-14 21:40 Europe/Istanbul (18:40 UTC).

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
and commit, push, and update this handoff at every checkpoint. The user
approved merging PR #5 and PR #6 and continuing with Stage 5.

No deployable model or live forecast exists. Stages 3-5 are development
benchmarks only. Market odds remain an external benchmark and must never enter
predictive features or Stage 3-8 selection.

## 2. Current state

- Branch: `agent/stage5-dixon-coles`, from `main` at `8a264b2`.
- Draft PR #7 targets `main`. The design checkpoint `64ff072` passed CI.
- The commit containing this file is the **Stage 5 evaluation checkpoint**; use
  Git for its hash. Its CI result must be verified with `gh pr checks 7`.
- PR #6 (Stage 4) was rebase-merged on 2026-09-14T18:19:06Z and PR #5 (Stage 3A)
  earlier the same day, both with explicit user approval.
- Never merge into `main` without explicit user approval.
- Local Git Bash quirk: `TZ=Europe/Istanbul date` prints UTC. The machine's
  local clock is Istanbul time.

## 3. Completed work

| Stage | State | Result |
| --- | --- | --- |
| 0-2 | Complete, merged | Data audit, canonical data and lineage, leakage boundary |
| 3 / 3A | Complete, merged | Naive baselines; immutable 2026-27 snapshots and freshness gate |
| 4 | Complete, merged | Independent Poisson walk-forward benchmark |
| 5 | Complete on PR #7 | Time-decayed Dixon-Coles with nested decay selection and ablations |
| 6 | Next in roadmap | Dynamic promoted-team prior (needs user go-ahead) |

Development evidence (1,413 matches, 2021-22 through 2024-25):

| Model | Log loss | Brier |
| --- | ---: | ---: |
| `uniform_hda` | 1.098612 | 0.666667 |
| `expanding_league_hda` | 1.060314 | 0.640070 |
| `independent_poisson` (Stage 4) | 1.008672 | 0.600648 |
| `poisson_decay` (ablation) | 0.995139 | 0.591252 |
| `dixon_coles_no_decay` (ablation) | 1.009002 | 0.600808 |
| `dixon_coles_decay` (Stage 5 candidate) | 0.995379 | 0.591547 |

- Candidate versus Stage 4: paired log-loss difference -0.013293, approximate
  95% interval [-0.020865, -0.005720].
- Complexity check: the gain comes from recency decay. The low-score correction
  is not justified on H/D/A metrics. Candidate minus `poisson_decay` is
  +0.000240 [-0.002336, +0.002816], and `rho` alone is +0.000330 versus Stage 4.
- Nested chronological decay selection (`reports/dixon_coles_selection.csv`):
  2021-22 chose 0.0015/day (half-life 462 days); 2022-23, 2023-24, and 2024-25
  chose 0.003/day (231 days). None was at the grid maximum.
- Low-score cells: Dixon-Coles fixes 1-0, 0-1, and 1-1 but overpredicts 0-0
  (0.0756 against observed 0.0651) and draws (0.2563 against 0.2435). Fitted
  `rho` averages -0.091 (range -0.151 to -0.027).
- Files:
  - code: `scripts/run_dixon_coles_evaluation.py`;
  - tests: `tests/test_dixon_coles_fit.py`, `tests/test_dixon_coles_evaluation.py`;
  - report: `reports/DIXON_COLES_REPORT.md`, plus the `dixon_coles_*` CSVs.
- CI runs `python scripts/run_dixon_coles_evaluation.py`, which chains
  foundation, baselines, Poisson, and Dixon-Coles.
- Validation on 14.09.2026 (Windows):
  - the full chain passed in 91 s;
  - Stage 5 CSVs were identical across two runs;
  - `python -m unittest discover -s tests` passed 47 tests;
  - committed Stage 3/4 outputs showed no content diff.

## 4. In-progress work

None uncommitted at this checkpoint. Working-copy `M` flags on generated
reports are CRLF-only; `git diff --exit-code` shows no content change.

## 5. Decisions and invariants

- Stage 4 and Stage 5 specifications are declared in `MODEL_DESIGN.md`; the
  Stage 5 decay selection rule is in `EVALUATION_PROTOCOL.md`. Both were
  committed before Stage 5 metrics existed.
- One pre-metric amendment was made. Stage 5 uses a 0-40 goal grid because 0-30
  lost more than 1e-9 mass for one declared fit (Besiktas-Pendikspor,
  2023-08-20, decay 0.005, expected home goals 8.83). Stage 4 keeps 0-30.
- The declared candidate (`dixon_coles_decay`) was not replaced after results.
  Choosing between it and `poisson_decay` belongs to the Stage 8 freeze.
- For match time `t`: `feature(match_t) = f(matches strictly before t)` and
  `result_available_at < prediction_time`, obtained only through
  `scripts/evaluation_time.py`. Stage 5 recency weights are anchored at the
  latest kickoff in the available history, and fits are reused only while that
  history is unchanged.
- Final evaluation is chronological and walk-forward. Current-match
  statistics, future matches, final standings, and closing odds are forbidden
  inputs. Materialize predictions before any market join.
- Iterative-fit per-match outputs are published to nine decimals; aggregates
  are computed before rounding. Stage 4 outputs reproduced on Ubuntu CI.
- Selecting or tuning a model after observing 2026-27 outcomes and then calling
  2025-26 untouched evidence would break the selection boundary.

## 6. Failures and suspicious findings

- **Cold start** is still the main weakness, and decay makes it worse:
  - Besiktas-Pendikspor's candidate log loss is 5.66 (Stage 4: 4.83).
  - For fixtures with an unseen club (9 matches), the candidate is +0.0199 worse
    than Stage 4.
  - This is evidence for Stage 6.
- **Per-season grid (descriptive):** in 2021-22 and 2024-25 the in-season
  optimum sits at the grid maximum (0.005/day). In 2022-23, no decay was best in
  season, and the candidate lost +0.0093 to Stage 4. Do not extend or retune the
  grid after seeing this.
- **Live data is stale** (section 7). A merge-triggered acquisition at
  2026-09-14T17:51Z was byte-identical to the active snapshot. Promotion with
  `--required-through 2026-09-13` (TFF-verified) failed closed and wrote nothing.
  The first scheduled 05:30 Istanbul acquisition from `main` (2026-09-15
  02:30 UTC) had not run at last verification.
- In Git Bash on this machine, `grep -c $'\r'` falsely reports CR on every line.
  Use `git ls-files --eol`.

## 7. Live-data state

Active snapshot, unchanged:

- ID: `20260913T192813Z_d208797586a0`
- Raw file: `data/raw/football_data/2026-27__20260913T192813Z__d208797586a0.csv`
- Captured: `2026-09-13T19:28:13Z`
- Coverage: 36 results, 2026-08-14 through 2026-09-07; audit status `REVIEW`

User note (14.09.2026): the open-source data covers seasons through 2025-26 plus
the current season via Football-Data. Refresh only through that source; any
other source needs explicit approval. `captured_at` uses the acquisition
artifact's `created_at`. A live forecast must pass the gate in
`CURRENT_SEASON_DATA.md` and validate its fixture against an official schedule.

## 8. Remaining work (next safe actions)

1. Verify CI on PR #7 for this checkpoint and fix on the branch if it fails.
   Merge only with explicit user approval.
2. When a scheduled acquisition artifact covers the latest TFF-verified
   completed date, promote it as a separate data checkpoint, rerun
   `python scripts/run_dixon_coles_evaluation.py` and the tests, and commit.
3. Stage 6 (dynamic promoted-team prior, `MODEL_DESIGN.md`) needs the user's
   go-ahead. Before coding, declare these and commit them before metrics:
   - the base model (a decayed Stage 5 fit);
   - how historically promoted clubs are identified from training data only;
   - the chronological selection of `k` and the priors.

## 9. Verification

```powershell
git status --short --branch
git log --oneline main..HEAD
gh pr checks 7
python -m unittest discover -s tests
python scripts/run_dixon_coles_evaluation.py
git diff --exit-code -- DATA_CONTRACT.md data/processed reports config/expected_schemas.json
```

Do not rerun network acquisition blindly; follow `CURRENT_SEASON_DATA.md` and
preserve every raw snapshot immutably.

## 10. Permissions and external effects

- Granted and used on 14.09.2026:
  - merge PR #5 and PR #6;
  - inspect and promote the acquisition artifact if coverage passed (refused
    by the gate);
  - Stage 4 and Stage 5 scope.
- Still requires explicit approval:
  - merging PR #7 or any later PR, or force-pushing;
  - publishing predictions, or adding external data sources;
  - the Stage 3B track, Stage 6, or any later modeling stage.
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
