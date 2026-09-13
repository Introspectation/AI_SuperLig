# Research roadmap

The project advances through reviewable checkpoints. A later stage may not
weaken the leakage, market-isolation, or final-holdout rules established by an
earlier stage.

| Stage | Status | Deliverable | Gate to advance |
| --- | --- | --- | --- |
| 0. Data audit | Complete | Nine-season schema, missingness, team-name, result-status, and odds audit. | Audited verdict is GO or GO-WITH-CONSTRAINTS. |
| 1. Canonical foundation | Complete | Immutable raw lineage, canonical matches, kickoff times, isolated market benchmark. | Offline deterministic rebuild and CI pass. |
| 2. Leakage boundary | Complete | Result-availability timestamps and strict chronological history helper. | Boundary tests cover overlaps and interruptions. |
| 3. Naive baselines | Complete | Frozen development split, uniform H/D/A, expanding league H/D/A, log loss and Brier reporting. | Complete walk-forward predictions; 2025-26 stays sealed. |
| 4. Independent Poisson | Next | Team attack/defence plus home advantage, score matrix, H/D/A probabilities. | Beat or clearly characterize naive baselines on development data. |
| 5. Time-decayed Dixon-Coles | Planned | Recency decay and low-score correction under the same evaluation contract. | Chronological tuning only; justify added complexity. |
| 6. Promoted-team prior | Planned | Training-only dynamic promoted-team attack/defence shrinkage. | Improve cold-start behavior without holdout or market leakage. |
| 7. Small-data ML challengers | Planned | Regularized, low-capacity challengers using legal pre-match features only. | Out-of-sample gain and calibration justify complexity. |
| 8. Candidate freeze | Planned | Select model and calibration rule using development evidence. | Code, hyperparameters, and decision rule frozen before holdout. |
| 9. Final benchmark | Locked | One-time 2025-26 holdout evaluation and post-prediction market comparison. | Report performance, calibration, uncertainty, and failure modes. |
| 10. 2026-27 prediction runner | Planned | Reproducible pre-match score distribution and H/D/A prediction command. | Current-season ingestion and monitoring rules pass review. |

## Current boundary

Stage 3 is the first code that emits probabilities. It is a research baseline,
not the final live system. The next implementation must be Stage 4; jumping to
Dixon-Coles, promoted-team adjustments, or ML challengers would erase the
comparison ladder the project was designed to measure.

The final holdout is opened once, only after the Stage 8 candidate freeze. The
market benchmark is never a predictive feature and is not used to tune Stages
3 through 8.
