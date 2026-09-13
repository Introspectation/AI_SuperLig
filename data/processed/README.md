# Generated data products

Run `python scripts/run_data_foundation.py` to regenerate these files:

- `canonical_matches.csv`: audited match/result history with canonical team
  identities, complete kickoff times, conservative result-availability
  timestamps, status decisions, and raw lineage;
- `market_benchmark.csv`: isolated de-vigged closing probabilities, split into
  primary market-average and secondary single-bookmaker regimes.

`canonical_matches.csv` is historical outcome data, not a pre-match feature
matrix. `market_benchmark.csv` must never be joined into predictive features.
Future history filters must use the strict `result_available_at < prediction`
boundary from `LEAKAGE_CONTRACT.md`.
