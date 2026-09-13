# Canonical data contract

This contract is based on the audited Football-Data snapshots and the
reviewed TFF kickoff enrichment. `scripts/build_canonical_data.py` materializes
the match and market tables. It does not create a predictive feature table.

## Canonical match table

Grain: one scheduled league match result per row after explicit resolution
of duplicate keys and non-played/administrative results.

| Field | Status | Type | Source | Rule |
| --- | --- | --- | --- | --- |
| match_id | REQUIRED | string | derived | Stable unique key; collision is a hard failure. |
| season | REQUIRED | string | catalog | `YYYY-YY` label. |
| date | REQUIRED | date | Date | Day-first source parsed to ISO date. |
| kickoff_time | REQUIRED | time | Time / reviewed TFF backfill | Time is interpreted as UK clock after TFF cross-checks; TFF supplies two missing seasons. |
| kickoff_timezone | REQUIRED | string | derived | Europe/Istanbul after timezone-aware conversion. |
| kickoff_time_source | REQUIRED | enum | derived lineage | football_data_europe_london_converted or tff_archive. |
| home_team | REQUIRED | string | HomeTeam | Alias changes require review. |
| away_team | REQUIRED | string | AwayTeam | Must differ from home team. |
| home_goals | REQUIRED | integer | FTHG | Non-negative full-time goals. |
| away_goals | REQUIRED | integer | FTAG | Non-negative full-time goals. |
| result | REQUIRED | enum H/D/A | FTR | Must agree with full-time goals. |
| official_home_goals | OPTIONAL | nullable integer | reviewed TFF decision | Only populated when an official award differs from the on-pitch score. |
| official_away_goals | OPTIONAL | nullable integer | reviewed TFF decision | Only populated when an official award differs from the on-pitch score. |
| official_result | OPTIONAL | nullable enum H/D/A | derived from official goals | Kept separate from the on-pitch score-model target. |
| match_status | REQUIRED | enum | curation/default | played, not_played_forfeit, abandoned_forfeit, or played_then_awarded_forfeit. |
| model_eligible | REQUIRED | boolean | derived from match_status | False for non-played/abandoned exclusions; true for the fully played awarded result. |
| source_provider | REQUIRED | string | lineage | football_data. |
| source_file | REQUIRED | string | lineage | Immutable raw CSV path. |
| source_row | REQUIRED | integer | lineage | One-based raw CSV row including header. |
| tff_match_id | OPTIONAL | nullable string | TFF kickoff snapshot | Present for the two kickoff-backfilled seasons. |
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
`match_status=played` is assigned only after the exact reviewed non-played
override set matches the detected administrative-result set. Those 31
overrides set `model_eligible=false`; raw source scores remain in lineage.
The played Akhisarspor-Besiktas match remains model eligible with its 1-3
on-pitch score; the later official 0-3 award is retained only in the nullable
official-score fields.

## Fields rejected from the MVP match table

- `Div`: constant source code and already represented by dataset scope.
- `HTR`: derivable from half-time goals when those goals exist.
- all 1X2, over/under, and Asian-handicap odds: market data is isolated below.
- bookmaker counts, maxima, and exchange fields: not needed for the first
  closing-probability benchmark.
- rolling form, standings, Elo, attack/defence strength, and every other
  pre-match feature: deferred to a later phase.

## Isolated market benchmark table

This table is separate from matches used to construct predictive features.
It may join to frozen predictions only for external benchmark evaluation.

| Field | Status | Type | Rule |
| --- | --- | --- | --- |
| match_id | REQUIRED | string | Foreign key to canonical match. |
| season | REQUIRED | string | Convenience partition and validation field. |
| benchmark_tier | REQUIRED | enum | primary_market_average or secondary_single_bookmaker. |
| benchmark_regime | REQUIRED | enum | market_average_closing or pinnacle_closing. |
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

Resolved hierarchy: `AvgCH/AvgCD/AvgCA` is the primary closing-market-average
benchmark from 2019-20 onward. Complete `PSCH/PSCD/PSCA` rows form a separate
secondary Pinnacle-closing benchmark for 2017-18 and 2018-19. The two regimes
must never be presented as one homogeneous series without stratification.

## Team aliases

`reports/team_aliases.csv` contains seven source-backed mappings approved for
future canonical materialization. They are never written back to raw CSVs, and
the original source names remain available for lineage.

## Hard validation rules

- required fields are non-null; goals are non-negative integers; result is H/D/A;
- result agrees with full-time goals; home and away teams differ;
- natural match keys and `match_id` values are unique;
- kickoff time is complete after the TFF join and UK-to-Turkey conversion;
- raw checksums and exact ordered schemas match their locks;
- all 31 reviewed administrative results set `model_eligible=false`;
- review config must match the detected candidate set exactly;
- market rows never enter a predictive feature dataset.
