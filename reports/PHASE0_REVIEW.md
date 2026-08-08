# Phase 0.1 administrative-result and team-identity review

## Technical summary

**All 31 heuristic match candidates are source-confirmed administrative
results and are excluded from future played-match model fitting.** Twenty-nine
are unplayed 2022-23 forfeits after Hatayspor and Gaziantep withdrew; two are
started-but-abandoned matches later registered as 3-0 forfeits. Raw rows remain
unchanged for lineage.

**All seven team aliases are approved for canonicalization.** Exact date,
opponent, and score joins to TFF fixtures resolve the provider abbreviations;
the Erzurum mapping also has a club-issued name-change statement. No alias is
written back to raw CSVs.

## Every administrative result is ineligible for played-match fitting

| Reviewed status | Rows | Model eligible | Evidence |
| --- | --- | --- | --- |
| abandoned_forfeit | 2 | false | TFF_2023_ISTANBULSPOR_PFDK\|TFF_2025_ADANA_PFDK |
| not_played_forfeit | 29 | false | TFF_2023_WITHDRAWALS |

| Season | Reviewed rows | Not played forfeits | Abandoned forfeits |
| --- | --- | --- | --- |
| 2022-23 | 29 | 29 | 0 |
| 2023-24 | 1 | 0 | 1 |
| 2024-25 | 1 | 0 | 1 |

The machine-readable row decisions are in
`config/match_status_overrides.csv`; the regenerated
`reports/suspected_non_played_matches.csv` includes the heuristic evidence,
reviewed status, eligibility flag, decision, and evidence ID.

## Seven aliases are safe at this project scope

| Raw label | Canonical name | Confidence | Decision | Evidence |
| --- | --- | --- | --- | --- |
| Ad. Demirspor | Adana Demirspor | high | approved_for_canonicalization | TFF_2021_ADANA_MATCH |
| Buyuksehyr | Istanbul Basaksehir | high | approved_for_canonicalization | TFF_2018_WEEK1 |
| Goztep | Goztepe | high | approved_for_canonicalization | TFF_2018_WEEK1 |
| Karagumruk | Fatih Karagumruk | high | approved_for_canonicalization | TFF_2020_WEEK1 |
| Akhisar Belediyespor | Akhisarspor | high | approved_for_canonicalization | TFF_2018_WEEK1 |
| Erzurum BB | Erzurumspor FK | high | approved_for_canonicalization | TFF_2018_WEEK1\|TFF_2020_WEEK1\|ERZURUM_2025_RENAME |
| Gaziantep | Gaziantep FK | high | approved_for_canonicalization | TFF_2019_WEEK1\|TFF_2020_WEEK1 |

These decisions are scoped to the audited Turkish top-flight seasons. They do
not authorize fuzzy matching of unseen clubs, and they do not merge historical
clubs merely because they share a city name.

## Method and robustness

- Candidate detection remained independent of the review config: exact 3-0/0-3
  scores with every audited match-stat field missing.
- The audit now fails if the detected candidate key set differs by even one row
  from the reviewed override key set.
- The combined 2022-23 TFF decisions identify Hatayspor and Gaziantep as the
  withdrawn clubs and register their remaining fixtures as 3-0 forfeits.
- The two abandoned matches have match-specific PFDK decisions.
- Alias evidence uses exact fixture identity, not string similarity alone.

## Limitations and remaining questions

Ordinary rows do not receive match-by-match external verification; their
`played` status is the canonical default after the reviewed exceptions are
removed. The market benchmark regime and conservative same-day ordering rule
remain separate design decisions and do not block score-only baselines.

## Recommended next step

Proceed to chronological evaluation scaffolding and naive score baselines. The
31 reviewed rows must stay in lineage but must fail any model-population test
that expects `model_eligible=true`.

## Evidence sources

- [TFF_2023_WITHDRAWALS: Yonetim Kurulu Kararlari - 10.02.2023 tarihli 55 sayili toplanti](https://www.tff.org/default.aspx?ftxtID=39572&pageID=285); TFF; accessed 2026-08-08.
- [TFF_2023_WITHDRAWAL_CLUBS: Yonetim Kurulu Kararlari - Hatayspor and Gaziantep withdrawal confirmation](https://www.tff.org/default.aspx?ftxtID=39836&pageID=285); TFF; accessed 2026-08-08.
- [TFF_2023_ISTANBULSPOR_PFDK: PFDK Kararlari - 23.12.2023](https://www.tff.org/default.aspx?ftxtID=43023&pageID=246); TFF; accessed 2026-08-08.
- [TFF_2025_ADANA_PFDK: PFDK Kararlari - 13.02.2025](https://www.tff.org/default.aspx?ftxtID=46746&pageID=246); TFF; accessed 2026-08-08.
- [TFF_2021_ADANA_MATCH: Adana Demirspor - Fenerbahce match detail - 15.08.2021](https://www.tff.org/Default.aspx?macId=222919&pageID=29); TFF; accessed 2026-08-08.
- [TFF_2018_WEEK1: 2018-2019 Super Lig week 1 fixture and table](https://www.tff.org/Default.aspx?hafta=1&pageID=1467); TFF; accessed 2026-08-08.
- [TFF_2020_WEEK1: 2020-2021 Super Lig week 1 fixture and table](https://www.tff.org/Default.aspx?hafta=1&pageID=1529); TFF; accessed 2026-08-08.
- [TFF_2019_WEEK1: 2019-2020 Super Lig week 1 fixture and table](https://www.tff.org/Default.aspx?hafta=1&pageID=1501); TFF; accessed 2026-08-08.
- [ERZURUM_2025_RENAME: Club president statement confirming the name change](https://erzurumsporfk.org/2025/09/01/kulup-baskanimiz-ahmet-dalin-tesekkur-mesaji/); Erzurumspor FK; accessed 2026-08-08.
