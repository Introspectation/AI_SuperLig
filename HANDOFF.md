# AI SuperLig handoff

Last verified: 2026-09-14 23:20 Europe/Istanbul (20:20 UTC).

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

**Stop condition at this transfer:** Stages 0-7 are complete. The user approved
merging PR #9 (Stage 7) and asked for this handoff. **Stage 8 is not approved
yet.** Do not start the candidate freeze or touch the 2025-26 holdout without
explicit user go-ahead.

No deployable model or live forecast exists. Stages 3-7 are development
benchmarks only. Market odds remain an external benchmark and must never enter
predictive features or Stage 3-8 selection.

## 2. Current state

- This file is the last commit of PR #9 (`agent/stage7-ml-challengers`). The
  user approved rebase-merging PR #9 into `main` on 14.09.2026 after green CI.
  Verify with `gh pr view 9`; afterwards `main` holds Stages 0-7.
- There is no active feature branch after the merge. Start new work from an
  up-to-date `main` on a short-lived `agent/...` branch.
- Before this commit, PR #9's head `447a0a5` passed both CI runs (about
  5.5 minutes). CI runs `python scripts/run_ml_challenger_evaluation.py` with a
  20-minute timeout.
- No other PR was open at verification.
- Local worktree: generated reports can show CRLF-only `M` flags on Windows;
  `git diff --exit-code` shows no content change. They were reset to the
  committed state before this handoff.
- Local Git Bash quirk: `TZ=Europe/Istanbul date` prints UTC; plain `date` shows
  local Istanbul time.

## 3. Completed work

| Stage | PR | Result |
| --- | --- | --- |
| 0-2 | #1-#3 | Data audit, canonical data and lineage, strict leakage boundary |
| 3 / 3A | #4, #5 | Naive baselines; immutable 2026-27 snapshots and freshness gate |
| 4 | #6 | Independent Poisson, GO |
| 5 | #7 | Time-decayed Dixon-Coles, GO; gain from decay, `rho` not justified |
| 6 | #8 | Dynamic promoted-team prior, GO on point estimates with caveats |
| 7 | #9 | Penalized multinomial logistic challengers, CHARACTERIZED |

Development evidence (1,413 matches, 2021-22 through 2024-25):

| Model | Stage / role | Log loss | Brier |
| --- | --- | ---: | ---: |
| `uniform_hda` | 3 | 1.098612 | 0.666667 |
| `expanding_league_hda` | 3 | 1.060314 | 0.640070 |
| `independent_poisson` | 4 candidate | 1.008672 | 0.600648 |
| `poisson_decay` | 5 ablation | 0.995139 | 0.591252 |
| `dixon_coles_decay` | 5 candidate | 0.995379 | 0.591547 |
| `dixon_coles_promoted_prior` | 6 candidate | 0.986679 | 0.587685 |
| `dixon_coles_promoted_point` | 6 ablation | 0.986625 | 0.587663 |
| `poisson_decay_promoted_prior` | 6 ablation | 0.986863 | 0.587326 |
| `ml_offset_logit` | 7 candidate | 0.986766 | 0.587777 |
| `ml_offset_recalibration` | 7 ablation | 0.986679 | 0.587685 |
| `ml_plain_logit` | 7 ablation | 0.983529 | 0.585562 |

Key findings (full detail in `reports/*_REPORT.md`):

- **Stage 5:** candidate versus Stage 4 -0.013293 [-0.020865, -0.005720]. The
  gain comes from decay; `rho` alone is +0.000330. Selected decays are
  0.0015/day (2021-22) and 0.003/day (later seasons).
- **Stage 6:** versus Stage 5, promoted-club fixtures (415) -0.029623
  [-0.061745, +0.002498] and all fixtures -0.008700 [-0.018153, +0.000752].
  All 12 `k` selections are at the grid maximum (64). Uncertainty propagation
  adds nothing.
- **Stage 7:** the candidate versus Stage 6 is +0.000087 [-0.004291,
  +0.004465]. Recalibration always chose `lambda = inf`. `ml_plain_logit` is
  -0.003150 [-0.010136, +0.003835]: suggestive, not separated from noise, and
  it uses Stage 6 logits as features. The most consistent adjustment signals are
  shots-on-target share and form. Stage 6 slightly underpredicts home wins.
- **Leakage safeguards held at every stage:**
  - tamper tests: future and current-match data cannot change fits or features;
  - nested chronological tuning;
  - `k = 0` and `lambda = inf` reproduce the previous stage exactly;
  - Windows-generated outputs reproduce on Ubuntu CI.

## 4. In-progress work

None. No uncommitted source, config, or documentation changes.

## 5. Decisions and invariants

- For match time `t`: `feature(match_t) = f(matches strictly before t)` and
  `result_available_at < prediction_time`, obtained only through
  `scripts/evaluation_time.py`. Past-match statistics are legal history; a
  match's own statistics never are.
- Stage 4-7 specifications are in `MODEL_DESIGN.md` and selection rules in
  `EVALUATION_PROTOCOL.md`, each committed before its metrics. Stage 5's 0-40
  goal grid is the only pre-metric amendment. Never change a grid, rule,
  feature, or candidate after seeing results.
- Final evaluation is chronological and walk-forward. Random splits,
  current-match statistics, future matches, final standings, and closing odds
  are forbidden. Materialize predictions before any market join.
- Iterative-fit per-match outputs are published to nine decimals; aggregates
  are computed before rounding.
- The 2025-26 holdout opens once, only after a committed Stage 8 freeze.
  Selecting or tuning after observing 2026-27 outcomes and then calling
  2025-26 untouched would break the selection boundary.
- On 14.09.2026 the user asked in chat about Gaziantep FK-Fenerbahçe. A
  research forecast was computed as of kickoff and not committed or published:
  - the freshness gate failed;
  - 2025-26 results were used only as training data;
  - Stage 5 models gave about 20/20/60, with 1-2 the most likely score.

## 6. Failures and suspicious findings

- **Stage 8 selection risk:** every development metric above is now known.
  Choosing the best-looking model among many ablations would overfit
  development data. Stage 8 must declare and justify its rule. For example:
  prefer the simplest model whose gains are not separated from noise, or keep
  the last declared candidate. Commit that rule before the holdout.
- **Team alias gap in live data:** 2026-27 rows use "Erzurumspor", while
  2018-19 and 2020-21 rows use "Erzurumspor FK". Review
  `config/team_aliases.csv` before any live forecast. Development metrics are
  unaffected.
- **Runtime:** CI takes about 5.5 minutes. A local Windows full chain took
  775 s (Stage 5 189 s, Stage 6 73 s, Stage 7 372 s), and the 75-test suite
  took 143 s. Profile Stage 7 `walk_forward` before adding stages.
- **Live data is stale** (section 7):
  - The merge-triggered acquisition at 2026-09-14T17:51Z was byte-identical to
    the active snapshot.
  - Promotion with `--required-through 2026-09-13` failed closed and wrote
    nothing.
  - The first scheduled 05:30 Istanbul acquisition from `main` (2026-09-15
    02:30 UTC) had not run at verification.
- In Git Bash here, `grep -c $'\r'` falsely reports CR; use
  `git ls-files --eol`.

## 7. Live-data state

Active snapshot, unchanged:

- ID: `20260913T192813Z_d208797586a0`
- Raw file: `data/raw/football_data/2026-27__20260913T192813Z__d208797586a0.csv`
- Captured: `2026-09-13T19:28:13Z`
- Coverage: 36 results, 2026-08-14 through 2026-09-07; audit status `REVIEW`

TFF (read 14.09 about 20:50) showed week 5 completed on 11-13 September, with
Gaziantep FK-Fenerbahçe scheduled for 14.09 20:00.

User note: open-source data covers seasons through 2025-26 plus the current
season via Football-Data. Refresh only through that source.

Promotion procedure (`CURRENT_SEASON_DATA.md`):

1. Download the scheduled run's artifact into `tmp/`.
2. Promote it:
   - `--captured-at` = the artifact's `created_at`;
   - `--required-through` = the latest completed date verified on TFF;
   - `--artifact-digest` = from `gh api .../runs/RUN_ID/artifacts`.
3. Rerun the full chain and the tests, then commit as a separate data
   checkpoint.

## 8. Remaining work (next safe actions, in order)

1. **Verify the merge:** `gh pr view 9` shows MERGED, and the `main` push CI is
   green. If the merge did not happen, ask the user; do not merge on your own.
2. **Data checkpoint (approved):**
   - after the scheduled acquisition runs, check whether its 2026-27 CSV covers
     the TFF-verified latest completed date;
   - promote it on a new branch from `main`, rerun the chain and tests, commit,
     push, and open a PR;
   - merging that PR still needs approval.
3. **Stage 8 candidate freeze (needs user go-ahead).** First write and commit a
   freeze document:
   - the chosen model and the justification for the selection rule (see
     section 6);
   - how decay, `k`, and `lambda` are chosen for 2025-26, using only seasons
     before it under the existing nested rules;
   - the frozen code commit;
   - the holdout decision rule and the post-prediction market comparison plan.

   Evaluated options only:
   - `dixon_coles_promoted_prior` is the last declared model-based candidate;
   - `dixon_coles_promoted_point` and `poisson_decay_promoted_prior` are simpler
     or near-equal ablations;
   - `ml_plain_logit` is the lowest development log loss but was never a
     declared candidate.

   A time-decayed Poisson with a point prior and no `rho` was never evaluated,
   so it is not an option without a new pre-registered stage.
4. **Before any live forecast:** fix the Erzurumspor alias, pass the freshness
   gate, and decide on the Stage 3B publication track.

## 9. Verification

```powershell
git status --short --branch
git log --oneline -5 origin/main
gh pr list --state all --limit 5
gh run list --branch main --limit 3
gh run list --workflow bootstrap-football-data.yml --limit 3
python -m unittest discover -s tests
python scripts/run_ml_challenger_evaluation.py
git diff --exit-code -- DATA_CONTRACT.md data/processed reports config/expected_schemas.json
```

Do not rerun network acquisition blindly; follow `CURRENT_SEASON_DATA.md` and
preserve every raw snapshot immutably.

## 10. Permissions and external effects

- Granted and used on 14.09.2026:
  - merge PR #5-#9;
  - trigger, inspect, and promote acquisition artifacts that pass the coverage
    gate;
  - Stage 4-7 scope.
- Still requires explicit approval:
  - Stage 8 and any holdout opening;
  - merging any new PR, including the data checkpoint, or force-pushing;
  - publishing predictions, or adding external data sources;
  - the Stage 3B track.
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
  grid**: deferred; each needs a new pre-registered design.
- **Deferred ML inputs:** tree ensembles, Elo, `HxG/AxG`, referee effects.
