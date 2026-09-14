# AI SuperLig handoff

Last verified: 2026-09-14 21:15 Europe/Istanbul.

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

User instruction (14.09.2026): continue from the handoff, follow `ROADMAP.md`,
and commit, push, and update this handoff at every checkpoint.

No deployable model or live forecast exists. Stage 4 independent Poisson is a
development benchmark only. Market odds remain an external benchmark and must
never enter predictive features or Stage 3-8 selection.

## 2. Current state

- Branch: `agent/stage4-independent-poisson`, created from `main` at `60f1d9f`.
- The commit containing this file is the Stage 4 checkpoint; use Git for its
  hash rather than a self-referential value.
- Draft PR: from this branch to `main`, opened after this commit was pushed.
  Find it with `gh pr list --head agent/stage4-independent-poisson`.
- CI for this checkpoint must be verified with `gh pr checks`; it was not
  observable when this file was written.
- PR #5 (Stage 3A live snapshots) was rebase-merged into `main` on
  2026-09-14T17:51:14Z with explicit user approval. Post-merge `main` CI
  (run 34877246199) passed.
- Never merge into `main` without explicit user approval.

## 3. Completed work

| Stage | State | Result |
| --- | --- | --- |
| 0 | Complete | Historical and current-season data audit |
| 1 | Complete | Canonical data, immutable lineage, kickoff backfill, isolated market table |
| 2 | Complete | Strict result-availability and leakage boundary |
| 3 | Complete | Uniform and expanding-league H/D/A baselines |
| 3A | Complete, merged | Versioned immutable 2026-27 snapshots and freshness gate |
| 4 | Complete on this branch | Independent Poisson walk-forward benchmark |
| 5 | Next in roadmap | Time-decayed Dixon-Coles |

Stage 4 evidence (`reports/POISSON_REPORT.md`, same 1,413 development matches,
2021-22 through 2024-25):

| Model | Log loss | Brier |
| --- | ---: | ---: |
| `uniform_hda` | 1.098612 | 0.666667 |
| `expanding_league_hda` | 1.060314 | 0.640070 |
| `independent_poisson` | 1.008672 | 0.600648 |

- Paired log-loss difference against `expanding_league_hda`: -0.051642,
  approximate 95% interval [-0.069257, -0.034027] under an independence
  approximation. By season, 2021-22 is the only interval that includes zero.
- Implementation: `scripts/run_poisson_evaluation.py`; tests:
  `tests/test_poisson_evaluation.py`; spec: `MODEL_DESIGN.md`; protocol note:
  `EVALUATION_PROTOCOL.md`. CI now runs `python scripts/run_poisson_evaluation.py`.
- `scripts/run_baseline_evaluation.py` was refactored only to expose
  `development_targets` and `add_match_scores`; baseline predictions and
  metrics are byte-identical, and only the baseline report's next-gate text
  changed.
- Validation on 14.09.2026 (Windows, Python 3.12.4): full pipeline passed in
  44 s, two runs produced identical Poisson outputs, and
  `python -m unittest discover -s tests` passed 32 tests.

## 4. In-progress work

None uncommitted at the checkpoint. `tmp/` is gitignored and holds the
downloaded acquisition artifact `tmp/current-season-34877246106/`.

## 5. Decisions and invariants

- Stage 4 spec, fixed before its metrics were computed: equal-weight history,
  unpenalized intercept and home advantage, fixed untuned N(0, 1) penalty on
  team attack/defence log-strengths, unseen clubs at strength 0, 0-30 goal
  score grid. Do not retune it after seeing results.
- For match time `t`: `feature(match_t) = f(matches strictly before t)` and
  `result_available_at < prediction_time`, obtained only through
  `scripts/evaluation_time.py`.
- Final evaluation is chronological and walk-forward. Current-match
  statistics, future matches, final standings, and closing odds are forbidden
  inputs. Materialize predictions before any market join.
- Published Poisson per-match values use nine decimals because iterative fits
  are reproducible to numerical tolerance, not guaranteed bit-for-bit across
  BLAS/libm builds. Aggregates are computed before rounding.
- Selecting or tuning a model after observing 2026-27 outcomes and then calling
  2025-26 untouched evidence would break the selection boundary.
- Do not set a target such as closing 60-70% of the market gap. An unexpectedly
  extreme gain triggers a leakage audit but is not automatic proof of leakage.

## 6. Failures and suspicious findings

- Cold start is the main Stage 4 weakness. Clubs with 1-3 prior matches can get
  extreme rates: Besiktas-Pendikspor (2023-08-20) was forecast 6.99-0.74
  expected goals and finished 1-1 (log loss 4.83). The 1-33 prior-match bucket
  gains only -0.0064 log loss versus the league baseline. This is evidence for
  Stage 6, not a reason to change Stage 4.
- Cross-platform reproducibility of the Windows-generated Poisson outputs on
  Ubuntu CI is not yet proven. If CI's output diff fails only in trailing
  digits, reduce published precision rather than loosening the diff check.
- Live data is stale. Acquisition run 34877246106 (merge-triggered,
  2026-09-14T17:51:25Z, artifact digest `sha256:1d5a90a4...eed0`) returned a
  2026-27 CSV byte-identical to the active snapshot. The official TFF fixture
  page, read at about 20:50 on 14.09, showed week 5 completed on 11-13
  September; Gaziantep FK-Fenerbahçe was scheduled for 14.09 20:00. Promotion
  with `--required-through 2026-09-13` failed closed ("candidate ends at
  2026-09-07") and wrote nothing.
- Before PR #5 merged, the scheduled acquisition never ran because GitHub cron
  fires only from the default branch. `main` now carries the 05:30 Istanbul
  schedule; the first scheduled run (2026-09-15 02:30 UTC) is not yet observed.

## 7. Live-data state

Active snapshot, unchanged:

- ID: `20260913T192813Z_d208797586a0`
- Raw file: `data/raw/football_data/2026-27__20260913T192813Z__d208797586a0.csv`
- Captured: `2026-09-13T19:28:13Z`
- Coverage: 36 results, 2026-08-14 through 2026-09-07; audit status `REVIEW`

This snapshot is not sufficient for a forecast that needs results through
2026-09-13. A live forecast must pass the age and coverage gate in
`CURRENT_SEASON_DATA.md` and validate its fixture against an official schedule.
The `captured_at` convention used so far is the acquisition artifact's
`created_at` timestamp.

## 8. Remaining work (next safe actions)

1. Verify CI on the Stage 4 draft PR; fix on this branch if it fails. Merge
   only with explicit user approval.
2. After Football-Data publishes week 5, promote a new snapshot from the
   scheduled acquisition artifact. Independently establish `--required-through`
   from TFF, then run `python scripts/run_poisson_evaluation.py` and the tests
   and commit as a separate data checkpoint.
3. Stage 5 (time-decayed Dixon-Coles) is the next roadmap model. Tune decay and
   low-score correction chronologically on development data only, compare
   against `independent_poisson` under the same split and metrics, and keep the
   promoted-team prior (Stage 6) out of scope.

## 9. Verification

```powershell
git status --short --branch
git log --oneline main..HEAD
gh pr list --state open
gh pr checks <PR>
python scripts/run_poisson_evaluation.py
python -m unittest discover -s tests
git diff --exit-code -- DATA_CONTRACT.md data/processed reports config/expected_schemas.json
```

`run_poisson_evaluation.py` runs the offline foundation, baselines, and Poisson.
Do not rerun network acquisition blindly; follow `CURRENT_SEASON_DATA.md` and
preserve every raw snapshot immutably.

## 10. Permissions and external effects

- Granted and used on 14.09.2026: merge PR #5; inspect and promote the
  acquisition artifact if coverage passed (refused by the gate); Stage 4 scope.
- Still requires explicit approval: merging any later PR, force-pushing,
  publishing predictions, adding external data sources, the Stage 3B track,
  and modeling beyond the next roadmap stage.
- At each checkpoint, stage only intended files and commit in the
  Europe/Istanbul format below, then push the feature branch and inspect CI:

```text
DD.MM.YYYY -> genel yapilan isler

- Birinci somut degisiklik.
- Ikinci somut degisiklik.
- Onemli sinir veya karar.
```

Never force-push, silently modify raw source files, commit secrets, or merge
without explicit approval.

## 11. Parking lot

- **Stage 3B live baseline publication track** (proposal, not implemented and
  not in `ROADMAP.md`): publish honest pre-kickoff H/D/A-only forecasts in
  parallel with the research ladder. An artifact must record `generated_at`,
  `data_as_of`, source snapshot ID, fixture kickoff and timezone, model and
  version, Git commit, probabilities, and freshness status. On 14.09.2026 the
  user chose Stage 4 first; 3B still needs a decision.
- **Market comparison report:** an independent review recomputed the de-vig
  market benchmark on the same 1,413 matches (log loss `0.956823`, Brier
  `0.566425`). It is not in a committed report. Per `ROADMAP.md`, market
  comparison belongs to the post-freeze benchmark and must not steer
  Stages 3-8.
- **Referee effects** (user idea, unapproved): if tested later, prefer a
  leakage-safe hierarchical referee effect over a fixed multiplier. Use only
  pre-prediction assignments, shrink low-sample referees, account for
  confounding, require chronological out-of-sample gain, and consider cards,
  fouls, or penalties as first targets.
