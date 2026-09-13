# Canonical data build audit

## Answer first

**GO.** The canonical match table contains all 3,088 audited fixtures,
including 3,057 played-match-eligible rows and 31 source-reviewed
administrative exclusions. Kickoff time is complete for every row after an
exact one-to-one, score-verified TFF backfill of the first two seasons and
timezone-aware Europe/London-to-Europe/Istanbul conversion thereafter.

The isolated market benchmark contains 3,054 rows: 2,445
primary closing-market-average rows from 2019-20 onward and
609 separately labelled Pinnacle-closing rows for 2017-18 and
2018-19. Three eligible 2017-18 matches have no complete Pinnacle triplet
and remain absent from the benchmark rather than being imputed.

No predictive feature, baseline, Poisson model, or Dixon-Coles model is built
in this phase.

## Coverage by season

| Season | Matches | Eligible | Excluded | Kickoff complete | TFF backfill | Market rows | Market coverage | Regime |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2017-18 | 306 | 306 | 0 | 306 | 306 | 303 | 99.02% | pinnacle_closing |
| 2018-19 | 306 | 306 | 0 | 306 | 306 | 306 | 100.00% | pinnacle_closing |
| 2019-20 | 306 | 306 | 0 | 306 | 0 | 306 | 100.00% | market_average_closing |
| 2020-21 | 420 | 420 | 0 | 420 | 0 | 420 | 100.00% | market_average_closing |
| 2021-22 | 380 | 380 | 0 | 380 | 0 | 380 | 100.00% | market_average_closing |
| 2022-23 | 342 | 313 | 29 | 342 | 0 | 313 | 100.00% | market_average_closing |
| 2023-24 | 380 | 379 | 1 | 380 | 0 | 379 | 100.00% | market_average_closing |
| 2024-25 | 342 | 341 | 1 | 342 | 0 | 341 | 100.00% | market_average_closing |
| 2025-26 | 306 | 306 | 0 | 306 | 0 | 306 | 100.00% | market_average_closing |

## TFF kickoff join checks

| Season | Football-Data rows | TFF rows | Matched | Unmatched | Reviewed date differences | Reviewed score differences | Duplicate keys |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2017-18 | 306 | 306 | 306 | 0 | 0 | 0 | 0 |
| 2018-19 | 306 | 306 | 306 | 0 | 1 | 1 | 0 |

TFF names are mapped only through `config/tff_team_aliases.csv`. The build
fails on an unseen TFF label, duplicate canonical key, unmatched fixture, or
score disagreement. The single source-date difference is explicitly reviewed:
Başakşehir-Bursaspor retains its original 23 February prediction timestamp
after the weather suspension and next-day continuation. The played
Akhisarspor-Beşiktaş score remains 1-3 for score modeling while the official
0-3 PFDK result is preserved in separate fields. The immutable
Football-Data CSVs are never rewritten.
Two official 2019-20 TFF weeks lock the summer and winter timezone behavior
so British daylight-saving transitions are not represented as Turkish time.

## Leakage and benchmark boundary

`canonical_matches.csv` contains historical match outcomes, not a feature
matrix. Current-match outcomes remain forbidden predictive inputs under
`LEAKAGE_CONTRACT.md`. `market_benchmark.csv` is a separate table and may be
joined only after model predictions are frozen.
An earlier kickoff is not treated as an available result until the future
evaluation code applies the completion rule in `LEAKAGE_CONTRACT.md`.

## Remaining modeling work

Chronological evaluation scaffolding, naive baselines, independent Poisson,
time-decayed Dixon-Coles, and the dynamic promoted-team prior remain
unimplemented. Their design boundary is recorded in `MODEL_DESIGN.md`.
The conservative result-availability lag must be frozen before evaluation.

## Reviewed source links

- [TFF 2019-20 week 1](https://www.tff.org/Default.aspx?hafta=1&pageID=1501)
  verifies the summer UK-to-Turkey clock difference.
- [TFF 2019-20 week 18](https://www.tff.org/Default.aspx?hafta=18&pageID=1501)
  verifies the winter UK-to-Turkey clock difference.
- Exact acquisition and discrepancy evidence is catalogued in
  `data/raw/tff/kickoff_times_2017-19.manifest.json` and
  `config/kickoff_review_sources.csv`.
