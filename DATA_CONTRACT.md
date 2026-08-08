# Provisional data contract

This is a Phase 0 proposal based on the audited Football-Data snapshots. It
does not create a canonical dataset or any predictive feature table.

## Canonical match table

Grain: one scheduled league match result per row after explicit resolution
of duplicate keys and non-played/administrative results.

| Field | Status | Type | Source | Rule |
| --- | --- | --- | --- | --- |
| match_id | REQUIRED | string | derived | Stable unique key; collision is a hard failure. |
| season | REQUIRED | string | catalog | `YYYY-YY` label. |
| date | REQUIRED | date | Date | Day-first source parsed to ISO date. |
| kickoff_time | OPTIONAL | time | Time | Absent in 2017-18 and 2018-19. |
| home_team | REQUIRED | string | HomeTeam | Alias changes require review. |
| away_team | REQUIRED | string | AwayTeam | Must differ from home team. |
| home_goals | REQUIRED | integer | FTHG | Non-negative full-time goals. |
| away_goals | REQUIRED | integer | FTAG | Non-negative full-time goals. |
| result | REQUIRED | enum H/D/A | FTR | Must agree with full-time goals. |
| home_ht_goals | OPTIONAL | nullable integer | HTHG | Overall 99.00%; weakest season 91.52%. |
| away_ht_goals | OPTIONAL | nullable integer | HTAG | Overall 99.00%; weakest season 91.52%. |
| home_shots | OPTIONAL | nullable integer | HS | Overall 99.00%; weakest season 91.52%. |
| away_shots | OPTIONAL | nullable integer | AS | Overall 99.00%; weakest season 91.52%. |
| home_shots_on_target | OPTIONAL | nullable integer | HST | Overall 99.00%; weakest season 91.52%. |
| away_shots_on_target | OPTIONAL | nullable integer | AST | Overall 99.00%; weakest season 91.52%. |
| home_fouls | OPTIONAL | nullable integer | HF | Overall 99.00%; weakest season 91.52%. |
| away_fouls | OPTIONAL | nullable integer | AF | Overall 99.00%; weakest season 91.52%. |
| home_corners | OPTIONAL | nullable integer | HC | Overall 99.00%; weakest season 91.52%. |
| away_corners | OPTIONAL | nullable integer | AC | Overall 99.00%; weakest season 91.52%. |
| home_yellow_cards | OPTIONAL | nullable integer | HY | Overall 99.00%; weakest season 91.52%. |
| away_yellow_cards | OPTIONAL | nullable integer | AY | Overall 99.00%; weakest season 91.52%. |
| home_red_cards | OPTIONAL | nullable integer | HR | Overall 99.00%; weakest season 91.52%. |
| away_red_cards | OPTIONAL | nullable integer | AR | Overall 98.96%; weakest season 91.52%. |

`match_id` is proposed as a SHA-256 of
`season|date_iso|approved_home_team|approved_away_team`. Inputs are delimited
and UTF-8 encoded. The unhashed components must remain alongside the ID for
auditability. A collision or duplicate natural key is a hard failure.

Optional match statistics are historical outcomes, not pre-match features.
The leakage contract forbids using a match's own optional statistics to
predict that match.

## Fields rejected from the MVP match table

- `Div`: constant source code and already represented by dataset scope.
- `HTR`: derivable from half-time goals when those goals exist.
- all 1X2, over/under, and Asian-handicap odds: market data is isolated below.
- bookmaker counts, maxima, and exchange fields: not needed for the first
  closing-probability benchmark.
- `match_status`: the source has no explicit played/awarded/abandoned field.
  The audit flags 31 candidates, but Phase 0 will not invent status values.
- rolling form, standings, Elo, attack/defence strength, and every other
  pre-match feature: deferred to a later phase.

## Isolated market benchmark table

This table is separate from matches used to construct predictive features.
It may join to frozen predictions only for external benchmark evaluation.

| Field | Status | Type | Rule |
| --- | --- | --- | --- |
| match_id | REQUIRED | string | Foreign key to canonical match. |
| closing_home_odds | REQUIRED | decimal | Decimal odds > 1 when row exists. |
| closing_draw_odds | REQUIRED | decimal | Decimal odds > 1 when row exists. |
| closing_away_odds | REQUIRED | decimal | Decimal odds > 1 when row exists. |
| market_p_home | REQUIRED | float | De-vigged probability in [0, 1]. |
| market_p_draw | REQUIRED | float | De-vigged probability in [0, 1]. |
| market_p_away | REQUIRED | float | De-vigged probability in [0, 1]. |
| market_overround | REQUIRED | float | Sum of raw inverse odds minus 1. |
| odds_source | REQUIRED | string | Exact average/bookmaker and closing status. |

For odds `(o_h, o_d, o_a)`, let `q_i = 1 / o_i`,
`market_overround = q_h + q_d + q_a - 1`, and
`market_p_i = q_i / (q_h + q_d + q_a)`.

Selection hierarchy: use `AvgCH/AvgCD/AvgCA` as the closing market average
where complete (2019-20 onward in the audited schemas). Earlier seasons may
use complete `PSCH/PSCD/PSCA` only as a separately labelled Pinnacle closing
benchmark. Market-average and single-bookmaker rows must not be presented as
one homogeneous series without stratification.

## Team aliases

`reports/team_aliases.csv` contains proposals only. High-confidence mappings
still require one human sign-off before canonical materialization. Review-level
mappings are never applied automatically. Raw names remain available for lineage.

## Hard validation rules

- required fields are non-null; goals are non-negative integers; result is H/D/A;
- result agrees with full-time goals; home and away teams differ;
- natural match keys and `match_id` values are unique;
- raw checksums and exact ordered schemas match their locks;
- non-played/administrative candidates require explicit disposition;
- market rows never enter a predictive feature dataset.
