# Turkish Super Lig data audit: 2017-18 through 2025-26

## Answer first

**Verdict: GO-WITH-CONSTRAINTS for proceeding to a score-only Dixon-Coles phase.**
No model is implemented in this phase.

The nine Football-Data snapshots contain 3,088 rows. Date, teams,
full-time goals, and FTR are complete and internally consistent enough for a
score-based MVP. The raw schemas are not concat-compatible: they range from 61
to 131 columns and change odds providers and closing-market coverage over time.
The principal blocker to blind modeling is 31 strong heuristic but
unconfirmed non-played/administrative-result candidates: 29 in 2022-23 and one in each of
2023-24 and 2024-25. They have 3-0/0-3 scores while every audited match-stat
field is missing. They require human confirmation and an explicit include/exclude
decision before model fitting.

Reliable MVP columns are `Date`, `HomeTeam`, `AwayTeam`, `FTHG`, `FTAG`, and
`FTR`. Half-time and match-stat fields are retained as optional historical
outcomes. Closing market-average 1X2 odds are absent before 2019-20, so market
benchmark coverage is not homogeneous across all nine seasons.

## Dataset and grain

Expected grain: one Turkish top-flight scheduled match/result per row. Candidate
key: season + parsed date + normalized home team + normalized away team.
Raw CSV bytes are checksum-locked and never rewritten.

## Source provenance

Source page: [https://www.football-data.co.uk/turkeym.php](https://www.football-data.co.uk/turkeym.php).
Field definitions: [https://www.football-data.co.uk/notes.txt](https://www.football-data.co.uk/notes.txt).
Snapshot date: 2026-08-08.

The first local request was rejected because The local network request returned an access-blocked HTML page instead of CSV. Header validation rejected it and no raw file was promoted.
No mirror or invented substitute entered the audit. The successful acquisition
used direct HTTPS from a GitHub-hosted Ubuntu Actions runner in [this workflow run](https://github.com/Introspectation/AI_SuperLig/actions/runs/31259394478).
Artifact digest: `sha256:dccda407ebb1cb21d211e3a66065ae3acca3f2b8964031027e0b4535c3619e77`. Nine expected season files; artifact-to-workspace SHA-256 equality; per-file hashes locked in raw_sources.csv.
The per-file URLs, byte sizes, and hashes are reproduced in
`raw_file_manifest.csv`.

| Season | Rows | Cols | Teams | Exact dupes | Match dupes | Date fails | Invalid team rows | Score complete | All stats complete | Closing avg complete | Non-played candidates |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2017-18 | 306 | 64 | 18 | 0 | 0 | 0 | 0 | 100.00% | 100.00% | absent | 0 |
| 2018-19 | 306 | 61 | 18 | 0 | 0 | 0 | 0 | 100.00% | 99.67% | absent | 0 |
| 2019-20 | 306 | 105 | 18 | 0 | 0 | 0 | 0 | 100.00% | 100.00% | 100.00% | 0 |
| 2020-21 | 420 | 105 | 21 | 0 | 0 | 0 | 0 | 100.00% | 100.00% | 100.00% | 0 |
| 2021-22 | 380 | 105 | 20 | 0 | 0 | 0 | 0 | 100.00% | 100.00% | 100.00% | 0 |
| 2022-23 | 342 | 105 | 19 | 0 | 0 | 0 | 0 | 100.00% | 91.52% | 91.52% | 29 |
| 2023-24 | 380 | 105 | 20 | 0 | 0 | 0 | 0 | 100.00% | 99.74% | 100.00% | 1 |
| 2024-25 | 342 | 119 | 19 | 0 | 0 | 0 | 0 | 100.00% | 99.71% | 100.00% | 1 |
| 2025-26 | 306 | 131 | 18 | 0 | 0 | 0 | 0 | 100.00% | 100.00% | 100.00% | 0 |

Duplicate counts report excess rows after the first occurrence; affected-row
counts are retained in `season_summary.csv`. Missing/blank teams, same-team rows,
invalid scores, invalid FTR values, and score/FTR mismatches are also in that file.

## Required field coverage

| Season | FTHG | FTAG | FTR | HTHG | HTAG | HS | AS | HST | AST | HF | AF | HC | AC | HY | AY | HR | AR |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2017-18 | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% |
| 2018-19 | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 99.67% |
| 2019-20 | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% |
| 2020-21 | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% |
| 2021-22 | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% |
| 2022-23 | 100.00% | 100.00% | 100.00% | 91.52% | 91.52% | 91.52% | 91.52% | 91.52% | 91.52% | 91.52% | 91.52% | 91.52% | 91.52% | 91.52% | 91.52% | 91.52% | 91.52% |
| 2023-24 | 100.00% | 100.00% | 100.00% | 99.74% | 99.74% | 99.74% | 99.74% | 99.74% | 99.74% | 99.74% | 99.74% | 99.74% | 99.74% | 99.74% | 99.74% | 99.74% | 99.74% |
| 2024-25 | 100.00% | 100.00% | 100.00% | 99.71% | 99.71% | 99.71% | 99.71% | 99.71% | 99.71% | 99.71% | 99.71% | 99.71% | 99.71% | 99.71% | 99.71% | 99.71% | 99.71% |
| 2025-26 | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% |

Shots coverage is 3,057/3,088 (99.00%) overall;
shots-on-target coverage is 3,057/3,088 (99.00%).
The weakest season is 91.52%, driven by the 2022-23
administrative-result candidates rather than scattered ordinary-match missingness.
This is acceptable for optional descriptive outcomes, but not as a REQUIRED MVP
field and never as a current-match predictive input.

## Schema evolution

Columns common to every season (34):

```text
Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR,HS,AS,HST,AST,HF,AF,HC,AC,HY,AY,HR,AR,B365H,B365D,B365A,BWH,BWD,BWA,PSH,PSD,PSA,PSCH,PSCD,PSCA
```

The union contains 179 distinct raw column names. Consecutive
changes are shown below; the complete season-by-union matrix is in
`schema_by_season.csv`.

| Transition | Added | Added columns | Removed | Removed columns |
| --- | --- | --- | --- | --- |
| 2017-18 -> 2018-19 | 0 | none | 3 | LBA\|LBD\|LBH |
| 2018-19 -> 2019-20 | 62 | AHCh\|AHh\|Avg<2.5\|Avg>2.5\|AvgA\|AvgAHA\|AvgAHH\|AvgC<2.5\|AvgC>2.5\|AvgCA\|AvgCAHA\|AvgCAHH\|AvgCD\|AvgCH\|AvgD\|AvgH\|B365<2.5\|B365>2.5\|B365AHA\|B365AHH\|B365C<2.5\|B365C>2.5\|B365CA\|B365CAHA\|B365CAHH\|B365CD\|B365CH\|BWCA\|BWCD\|BWCH\|IWCA\|IWCD\|IWCH\|Max<2.5\|Max>2.5\|MaxA\|MaxAHA\|MaxAHH\|MaxC<2.5\|MaxC>2.5\|MaxCA\|MaxCAHA\|MaxCAHH\|MaxCD\|MaxCH\|MaxD\|MaxH\|P<2.5\|P>2.5\|PAHA\|PAHH\|PC<2.5\|PC>2.5\|PCAHA\|PCAHH\|Time\|VCCA\|VCCD\|VCCH\|WHCA\|WHCD\|WHCH | 18 | Bb1X2\|BbAH\|BbAHh\|BbAv<2.5\|BbAv>2.5\|BbAvA\|BbAvAHA\|BbAvAHH\|BbAvD\|BbAvH\|BbMx<2.5\|BbMx>2.5\|BbMxA\|BbMxAHA\|BbMxAHH\|BbMxD\|BbMxH\|BbOU |
| 2019-20 -> 2020-21 | 0 | none | 0 | none |
| 2020-21 -> 2021-22 | 0 | none | 0 | none |
| 2021-22 -> 2022-23 | 0 | none | 0 | none |
| 2022-23 -> 2023-24 | 0 | none | 0 | none |
| 2023-24 -> 2024-25 | 26 | 1XBA\|1XBCA\|1XBCD\|1XBCH\|1XBD\|1XBH\|BFA\|BFCA\|BFCD\|BFCH\|BFD\|BFE<2.5\|BFE>2.5\|BFEA\|BFEAHA\|BFEAHH\|BFEC<2.5\|BFEC>2.5\|BFECA\|BFECAHA\|BFECAHH\|BFECD\|BFECH\|BFED\|BFEH\|BFH | 12 | IWA\|IWCA\|IWCD\|IWCH\|IWD\|IWH\|VCA\|VCCA\|VCCD\|VCCH\|VCD\|VCH |
| 2024-25 -> 2025-26 | 30 | BFDA\|BFDCA\|BFDCD\|BFDCH\|BFDD\|BFDH\|BMGMA\|BMGMCA\|BMGMCD\|BMGMCH\|BMGMD\|BMGMH\|BVA\|BVCA\|BVCD\|BVCH\|BVD\|BVH\|CLA\|CLCA\|CLCD\|CLCH\|CLD\|CLH\|LBA\|LBCA\|LBCD\|LBCH\|LBD\|LBH | 18 | 1XBA\|1XBCA\|1XBCD\|1XBCH\|1XBD\|1XBH\|BFA\|BFCA\|BFCD\|BFCH\|BFD\|BFH\|WHA\|WHCA\|WHCD\|WHCH\|WHD\|WHH |

Major schema regimes:

- 2017-18 and 2018-19 use legacy BetBrain average/max fields and have no `Time`
  or closing market-average `AvgCH/AvgCD/AvgCA` fields.
- 2019-20 through 2023-24 share a 105-column layout with explicit pre-closing
  (`AvgH/AvgD/AvgA`) and closing (`AvgCH/AvgCD/AvgCA`) averages.
- 2024-25 expands to 119 columns with Betfair/1XBet/exchange fields.
- 2025-26 expands to 131 columns and changes the individual bookmaker roster.

Major missingness (>=5% within a present column):

| Season | Columns >=5% missing | Largest examples |
| --- | --- | --- |
| 2017-18 | 0 | none |
| 2018-19 | 0 | none |
| 2019-20 | 0 | none |
| 2020-21 | 0 | none |
| 2021-22 | 0 | none |
| 2022-23 | 97 | VCA=11.11%, VCD=11.11%, VCH=11.11%, B365AHA=10.53%, B365AHH=10.53%, B365<2.5=9.65%, B365>2.5=9.65%, B365A=9.65%, B365D=9.65%, B365H=9.65%, IWA=8.77%, IWD=8.77% |
| 2023-24 | 6 | IWA=55.53%, IWD=55.53%, IWH=55.53%, IWCA=55.26%, IWCD=55.26%, IWCH=55.26% |
| 2024-25 | 16 | BFEAHA=44.74%, BFEAHH=44.74%, BWCA=40.06%, BWCD=40.06%, BWCH=40.06%, BWA=39.47%, BWD=39.47%, BWH=39.47%, WHA=26.32%, WHCA=26.32%, WHCD=26.32%, WHCH=26.32% |
| 2025-26 | 43 | PSA=56.86%, PSD=56.86%, PSH=56.86%, P<2.5=56.54%, P>2.5=56.54%, PAHA=56.54%, PAHH=56.54%, PC<2.5=55.88%, PC>2.5=55.88%, PCAHA=55.88%, PCAHH=55.88%, PSCA=55.88% |

Meaning/composition cautions:

- Football-Data defines non-`C` odds as pre-closing and `C`-suffixed odds as
  closing. Treating all odds columns as one timestamp would be a semantic error.
- The bookmaker roster changes; even stable `Avg*` names can represent averages
  over different contributing books. Cross-season market comparisons need source
  and regime labels.
- Date meaning is stable, but raw formatting and UTF-8 BOM usage vary by season.
- A full-time 3-0/0-3 score can represent an administrative result in the source
  without an explicit status field. Those rows do not have the same on-pitch
  meaning as ordinary FTHG/FTAG observations.

## Betting-odds audit

| Season | Pre-closing average fields | Coverage | Closing average fields | Coverage | Individual closing sources |
| --- | --- | --- | --- | --- | --- |
| 2017-18 | BbAvH/BbAvD/BbAvA | 100.00% | absent | absent | Pinnacle (99.02%) |
| 2018-19 | BbAvH/BbAvD/BbAvA | 100.00% | absent | absent | Pinnacle (100.00%) |
| 2019-20 | AvgH/AvgD/AvgA | 100.00% | AvgCH/AvgCD/AvgCA | 100.00% | Bet365 (100.00%), Bet&Win (100.00%), Interwetten (100.00%), Pinnacle (100.00%), VC Bet (100.00%), William Hill (100.00%) |
| 2020-21 | AvgH/AvgD/AvgA | 100.00% | AvgCH/AvgCD/AvgCA | 100.00% | Bet365 (100.00%), Bet&Win (100.00%), Interwetten (100.00%), Pinnacle (100.00%), VC Bet (100.00%), William Hill (100.00%) |
| 2021-22 | AvgH/AvgD/AvgA | 100.00% | AvgCH/AvgCD/AvgCA | 100.00% | Bet365 (100.00%), Bet&Win (99.47%), Interwetten (98.95%), Pinnacle (99.74%), VC Bet (99.21%), William Hill (100.00%) |
| 2022-23 | AvgH/AvgD/AvgA | 91.52% | AvgCH/AvgCD/AvgCA | 91.52% | Bet365 (91.52%), Bet&Win (91.52%), Interwetten (91.52%), Pinnacle (91.52%), VC Bet (91.52%), William Hill (91.52%) |
| 2023-24 | AvgH/AvgD/AvgA | 100.00% | AvgCH/AvgCD/AvgCA | 100.00% | Bet365 (100.00%), Bet&Win (97.89%), Interwetten (44.74%), Pinnacle (100.00%), VC Bet (100.00%), William Hill (100.00%) |
| 2024-25 | AvgH/AvgD/AvgA | 100.00% | AvgCH/AvgCD/AvgCA | 100.00% | 1XBet (100.00%), Bet365 (100.00%), Betfair (100.00%), Betfair Exchange (100.00%), Bet&Win (59.94%), Pinnacle (100.00%), William Hill (73.68%) |
| 2025-26 | AvgH/AvgD/AvgA | 100.00% | AvgCH/AvgCD/AvgCA | 100.00% | Bet365 (100.00%), Betfred (99.02%), Betfair Exchange (93.79%), BetMGM (100.00%), BetVictor (99.02%), Bet&Win (100.00%), Coral (69.61%), Ladbrokes (72.22%), Pinnacle (44.12%) |

`AvgH/AvgD/AvgA` are not closing odds. The market benchmark should prefer
`AvgCH/AvgCD/AvgCA` from 2019-20 onward. The first two seasons have Pinnacle
`PSCH/PSCD/PSCA` closing odds but no closing market average; using them creates a
separate single-bookmaker benchmark regime. The full triplet-level evidence is in
`odds_coverage_by_season.csv`. Odds remain outside all predictive feature data.

## Team-name audit

`teams_by_season.csv` lists every distinct raw name, season, and home/away match
count. The source is internally stable for most clubs but uses ASCII
transliterations, abbreviations, truncations, and historical labels.

| Raw name | Proposed canonical | Confidence | Status | Seasons | Reason |
| --- | --- | --- | --- | --- | --- |
| Ad. Demirspor | Adana Demirspor | high | proposed_not_applied | 2021-22\|2022-23\|2023-24\|2024-25 | Unambiguous source abbreviation in the audited seasons. |
| Buyuksehyr | Istanbul Basaksehir | high | proposed_not_applied | 2017-18\|2018-19\|2019-20\|2020-21\|2021-22\|2022-23\|2023-24\|2024-25\|2025-26 | Stable truncated/transliterated source label across all nine seasons. |
| Goztep | Goztepe | high | proposed_not_applied | 2017-18\|2018-19\|2019-20\|2020-21\|2021-22\|2024-25\|2025-26 | Stable one-character truncation of the club name. |
| Karagumruk | Fatih Karagumruk | high | proposed_not_applied | 2020-21\|2021-22\|2022-23\|2023-24\|2025-26 | Unambiguous shortened club name in this league and time range. |
| Akhisar Belediyespor | Akhisarspor | high | proposed_not_applied | 2017-18\|2018-19 | Historical club-name change; no competing Akhisar entity appears. |
| Erzurum BB | Erzurumspor FK | review | human_review_required | 2018-19\|2020-21 | Likely historical abbreviation/name change; old Erzurum entities make automatic merging unsafe. |
| Gaziantep | Gaziantep FK | review | human_review_required | 2019-20\|2020-21\|2021-22\|2022-23\|2023-24\|2024-25\|2025-26 | Likely current club, but the city has had distinct historical clubs. |

No alias is applied automatically in Phase 0. In particular, review-level rows
remain separate until a human decision is recorded.

## Data-quality risks and impact

| Severity | Finding | Evidence | Modeling impact | Required action |
| --- | --- | --- | --- | --- |
| High | Likely non-played/administrative results | 31 rows; 3-0/0-3 with all audited stats missing | Artificial goals bias attack/defence strength and score tails. | Human-confirm and exclude or explicitly model status before fitting. |
| High | Post-match leakage risk | Goals, shots, cards, corners, fouls, and closing odds coexist in raw rows. | Naive feature selection can produce impossible performance. | Enforce LEAKAGE_CONTRACT.md and walk-forward tests. |
| Medium | Odds regime drift | Closing average absent in first two seasons; bookmaker roster changes later. | A single benchmark series would mix unlike sources. | Label source/regime and report benchmark coverage separately. |
| Medium | Missing kickoff time | `Time` absent in 2017-18 and 2018-19. | Same-day strict ordering is unknowable. | Treat same-date matches as simultaneous for leakage boundaries. |
| Medium | Unapproved team aliases | 7 proposed/review mappings. | Bad merges split or combine team histories. | Approve only high-confidence mappings; retain raw lineage. |
| Low | Encoding/header variation | 2018-19 begins with UTF-8 BOM. | Over-strict loaders can reject a valid season. | Decode BOM for parsing; never rewrite raw bytes. |
| Low | Isolated red-card missing value | 2018-19 Bursaspor-Alanyaspor has null AR; all other audited stats are present. | Does not affect score-only Dixon-Coles; unsafe to impute silently. | Keep AR nullable and preserve the source null. |

## Recommended canonical schema

REQUIRED: `match_id`, `season`, `date`, `home_team`, `away_team`,
`home_goals`, `away_goals`, `result`.

OPTIONAL: `kickoff_time`, both half-time goal fields, and all audited shots,
shots-on-target, fouls, corners, yellow-card, and red-card fields. They are
historical outcomes, not current-match features.

REJECTED FROM MVP: `Div`, derivable `HTR`, all odds in the match table,
over/under and handicap markets, bookmaker maxima/counts, unverified
`match_status`, and all rolling/pre-match features. Full types and validation
rules are in `DATA_CONTRACT.md`.

## Explicit unresolved questions

1. Confirm the disposition of all 31 rows in
   `suspected_non_played_matches.csv` before any model is fitted.
2. Approve or reject each team alias proposal, especially `Erzurum BB` and
   `Gaziantep`.
3. Decide whether the closing-market benchmark starts in 2019-20 or uses
   separately labelled Pinnacle closing odds for 2017-18 and 2018-19.
4. Confirm the conservative same-calendar-date ordering rule for seasons without
   kickoff times.
5. Define how newly promoted 2026-27 teams not present in the audit receive
   canonical identities and cold-start handling in a later phase.

## Final decision

**GO-WITH-CONSTRAINTS.** The score-and-result backbone is viable for the next
Dixon-Coles iteration, conditional on resolving non-played candidates and team
aliases. Match statistics are sufficiently complete as optional outcomes but are
not necessary for Dixon-Coles. Market odds are useful as an external benchmark
from 2019-20 onward and must stay logically isolated. Do not proceed to modeling
until the two human-review tables have explicit dispositions.

## Exact columns by season

### 2017-18 (306 rows x 64 columns)

```text
Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR,HS,AS,HST,AST,HF,AF,HC,AC,HY,AY,HR,AR,B365H,B365D,B365A,BWH,BWD,BWA,IWH,IWD,IWA,LBH,LBD,LBA,PSH,PSD,PSA,WHH,WHD,WHA,VCH,VCD,VCA,Bb1X2,BbMxH,BbAvH,BbMxD,BbAvD,BbMxA,BbAvA,BbOU,BbMx>2.5,BbAv>2.5,BbMx<2.5,BbAv<2.5,BbAH,BbAHh,BbMxAHH,BbAvAHH,BbMxAHA,BbAvAHA,PSCH,PSCD,PSCA
```

### 2018-19 (306 rows x 61 columns)

```text
Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR,HS,AS,HST,AST,HF,AF,HC,AC,HY,AY,HR,AR,B365H,B365D,B365A,BWH,BWD,BWA,IWH,IWD,IWA,PSH,PSD,PSA,WHH,WHD,WHA,VCH,VCD,VCA,Bb1X2,BbMxH,BbAvH,BbMxD,BbAvD,BbMxA,BbAvA,BbOU,BbMx>2.5,BbAv>2.5,BbMx<2.5,BbAv<2.5,BbAH,BbAHh,BbMxAHH,BbAvAHH,BbMxAHA,BbAvAHA,PSCH,PSCD,PSCA
```

### 2019-20 (306 rows x 105 columns)

```text
Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR,HS,AS,HST,AST,HF,AF,HC,AC,HY,AY,HR,AR,B365H,B365D,B365A,BWH,BWD,BWA,IWH,IWD,IWA,PSH,PSD,PSA,WHH,WHD,WHA,VCH,VCD,VCA,MaxH,MaxD,MaxA,AvgH,AvgD,AvgA,B365>2.5,B365<2.5,P>2.5,P<2.5,Max>2.5,Max<2.5,Avg>2.5,Avg<2.5,AHh,B365AHH,B365AHA,PAHH,PAHA,MaxAHH,MaxAHA,AvgAHH,AvgAHA,B365CH,B365CD,B365CA,BWCH,BWCD,BWCA,IWCH,IWCD,IWCA,PSCH,PSCD,PSCA,WHCH,WHCD,WHCA,VCCH,VCCD,VCCA,MaxCH,MaxCD,MaxCA,AvgCH,AvgCD,AvgCA,B365C>2.5,B365C<2.5,PC>2.5,PC<2.5,MaxC>2.5,MaxC<2.5,AvgC>2.5,AvgC<2.5,AHCh,B365CAHH,B365CAHA,PCAHH,PCAHA,MaxCAHH,MaxCAHA,AvgCAHH,AvgCAHA
```

### 2020-21 (420 rows x 105 columns)

```text
Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR,HS,AS,HST,AST,HF,AF,HC,AC,HY,AY,HR,AR,B365H,B365D,B365A,BWH,BWD,BWA,IWH,IWD,IWA,PSH,PSD,PSA,WHH,WHD,WHA,VCH,VCD,VCA,MaxH,MaxD,MaxA,AvgH,AvgD,AvgA,B365>2.5,B365<2.5,P>2.5,P<2.5,Max>2.5,Max<2.5,Avg>2.5,Avg<2.5,AHh,B365AHH,B365AHA,PAHH,PAHA,MaxAHH,MaxAHA,AvgAHH,AvgAHA,B365CH,B365CD,B365CA,BWCH,BWCD,BWCA,IWCH,IWCD,IWCA,PSCH,PSCD,PSCA,WHCH,WHCD,WHCA,VCCH,VCCD,VCCA,MaxCH,MaxCD,MaxCA,AvgCH,AvgCD,AvgCA,B365C>2.5,B365C<2.5,PC>2.5,PC<2.5,MaxC>2.5,MaxC<2.5,AvgC>2.5,AvgC<2.5,AHCh,B365CAHH,B365CAHA,PCAHH,PCAHA,MaxCAHH,MaxCAHA,AvgCAHH,AvgCAHA
```

### 2021-22 (380 rows x 105 columns)

```text
Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR,HS,AS,HST,AST,HF,AF,HC,AC,HY,AY,HR,AR,B365H,B365D,B365A,BWH,BWD,BWA,IWH,IWD,IWA,PSH,PSD,PSA,WHH,WHD,WHA,VCH,VCD,VCA,MaxH,MaxD,MaxA,AvgH,AvgD,AvgA,B365>2.5,B365<2.5,P>2.5,P<2.5,Max>2.5,Max<2.5,Avg>2.5,Avg<2.5,AHh,B365AHH,B365AHA,PAHH,PAHA,MaxAHH,MaxAHA,AvgAHH,AvgAHA,B365CH,B365CD,B365CA,BWCH,BWCD,BWCA,IWCH,IWCD,IWCA,PSCH,PSCD,PSCA,WHCH,WHCD,WHCA,VCCH,VCCD,VCCA,MaxCH,MaxCD,MaxCA,AvgCH,AvgCD,AvgCA,B365C>2.5,B365C<2.5,PC>2.5,PC<2.5,MaxC>2.5,MaxC<2.5,AvgC>2.5,AvgC<2.5,AHCh,B365CAHH,B365CAHA,PCAHH,PCAHA,MaxCAHH,MaxCAHA,AvgCAHH,AvgCAHA
```

### 2022-23 (342 rows x 105 columns)

```text
Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR,HS,AS,HST,AST,HF,AF,HC,AC,HY,AY,HR,AR,B365H,B365D,B365A,BWH,BWD,BWA,IWH,IWD,IWA,PSH,PSD,PSA,WHH,WHD,WHA,VCH,VCD,VCA,MaxH,MaxD,MaxA,AvgH,AvgD,AvgA,B365>2.5,B365<2.5,P>2.5,P<2.5,Max>2.5,Max<2.5,Avg>2.5,Avg<2.5,AHh,B365AHH,B365AHA,PAHH,PAHA,MaxAHH,MaxAHA,AvgAHH,AvgAHA,B365CH,B365CD,B365CA,BWCH,BWCD,BWCA,IWCH,IWCD,IWCA,PSCH,PSCD,PSCA,WHCH,WHCD,WHCA,VCCH,VCCD,VCCA,MaxCH,MaxCD,MaxCA,AvgCH,AvgCD,AvgCA,B365C>2.5,B365C<2.5,PC>2.5,PC<2.5,MaxC>2.5,MaxC<2.5,AvgC>2.5,AvgC<2.5,AHCh,B365CAHH,B365CAHA,PCAHH,PCAHA,MaxCAHH,MaxCAHA,AvgCAHH,AvgCAHA
```

### 2023-24 (380 rows x 105 columns)

```text
Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR,HS,AS,HST,AST,HF,AF,HC,AC,HY,AY,HR,AR,B365H,B365D,B365A,BWH,BWD,BWA,IWH,IWD,IWA,PSH,PSD,PSA,WHH,WHD,WHA,VCH,VCD,VCA,MaxH,MaxD,MaxA,AvgH,AvgD,AvgA,B365>2.5,B365<2.5,P>2.5,P<2.5,Max>2.5,Max<2.5,Avg>2.5,Avg<2.5,AHh,B365AHH,B365AHA,PAHH,PAHA,MaxAHH,MaxAHA,AvgAHH,AvgAHA,B365CH,B365CD,B365CA,BWCH,BWCD,BWCA,IWCH,IWCD,IWCA,PSCH,PSCD,PSCA,WHCH,WHCD,WHCA,VCCH,VCCD,VCCA,MaxCH,MaxCD,MaxCA,AvgCH,AvgCD,AvgCA,B365C>2.5,B365C<2.5,PC>2.5,PC<2.5,MaxC>2.5,MaxC<2.5,AvgC>2.5,AvgC<2.5,AHCh,B365CAHH,B365CAHA,PCAHH,PCAHA,MaxCAHH,MaxCAHA,AvgCAHH,AvgCAHA
```

### 2024-25 (342 rows x 119 columns)

```text
Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR,HS,AS,HST,AST,HF,AF,HC,AC,HY,AY,HR,AR,B365H,B365D,B365A,BWH,BWD,BWA,BFH,BFD,BFA,PSH,PSD,PSA,WHH,WHD,WHA,1XBH,1XBD,1XBA,MaxH,MaxD,MaxA,AvgH,AvgD,AvgA,BFEH,BFED,BFEA,B365>2.5,B365<2.5,P>2.5,P<2.5,Max>2.5,Max<2.5,Avg>2.5,Avg<2.5,BFE>2.5,BFE<2.5,AHh,B365AHH,B365AHA,PAHH,PAHA,MaxAHH,MaxAHA,AvgAHH,AvgAHA,BFEAHH,BFEAHA,B365CH,B365CD,B365CA,BWCH,BWCD,BWCA,BFCH,BFCD,BFCA,PSCH,PSCD,PSCA,WHCH,WHCD,WHCA,1XBCH,1XBCD,1XBCA,MaxCH,MaxCD,MaxCA,AvgCH,AvgCD,AvgCA,BFECH,BFECD,BFECA,B365C>2.5,B365C<2.5,PC>2.5,PC<2.5,MaxC>2.5,MaxC<2.5,AvgC>2.5,AvgC<2.5,BFEC>2.5,BFEC<2.5,AHCh,B365CAHH,B365CAHA,PCAHH,PCAHA,MaxCAHH,MaxCAHA,AvgCAHH,AvgCAHA,BFECAHH,BFECAHA
```

### 2025-26 (306 rows x 131 columns)

```text
Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR,HS,AS,HST,AST,HF,AF,HC,AC,HY,AY,HR,AR,B365H,B365D,B365A,BFDH,BFDD,BFDA,BMGMH,BMGMD,BMGMA,BVH,BVD,BVA,BWH,BWD,BWA,CLH,CLD,CLA,LBH,LBD,LBA,PSH,PSD,PSA,MaxH,MaxD,MaxA,AvgH,AvgD,AvgA,BFEH,BFED,BFEA,B365>2.5,B365<2.5,P>2.5,P<2.5,Max>2.5,Max<2.5,Avg>2.5,Avg<2.5,BFE>2.5,BFE<2.5,AHh,B365AHH,B365AHA,PAHH,PAHA,MaxAHH,MaxAHA,AvgAHH,AvgAHA,BFEAHH,BFEAHA,B365CH,B365CD,B365CA,BFDCH,BFDCD,BFDCA,BMGMCH,BMGMCD,BMGMCA,BVCH,BVCD,BVCA,BWCH,BWCD,BWCA,CLCH,CLCD,CLCA,LBCH,LBCD,LBCA,PSCH,PSCD,PSCA,MaxCH,MaxCD,MaxCA,AvgCH,AvgCD,AvgCA,BFECH,BFECD,BFECA,B365C>2.5,B365C<2.5,PC>2.5,PC<2.5,MaxC>2.5,MaxC<2.5,AvgC>2.5,AvgC<2.5,BFEC>2.5,BFEC<2.5,AHCh,B365CAHH,B365CAHA,PCAHH,PCAHA,MaxCAHH,MaxCAHA,AvgCAHH,AvgCAHA,BFECAHH,BFECAHA
```
