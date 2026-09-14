# Research roadmap

The project advances through reviewable checkpoints. A later stage may not
weaken the leakage, market-isolation, or final-holdout rules established by an
earlier stage.

| Stage | Status | Deliverable | Gate to advance |
| --- | --- | --- | --- |
| 0. Data audit | Complete | Nine frozen historical seasons plus a versioned current-season audit. | Audited verdict is GO or GO-WITH-CONSTRAINTS. |
| 1. Canonical foundation | Complete | Immutable raw lineage, canonical matches, kickoff times, isolated market benchmark. | Offline deterministic rebuild and CI pass. |
| 2. Leakage boundary | Complete | Result-availability timestamps and strict chronological history helper. | Boundary tests cover overlaps and interruptions. |
| 3. Naive baselines | Complete | Frozen development split, uniform H/D/A, expanding league H/D/A, log loss and Brier reporting. | Complete walk-forward predictions; 2025-26 stays sealed. |
| 3A. Current-season snapshots | Complete | Immutable 2026-27 snapshots with capture time, hash, freshness, and revision checks. | Refresh is reproducible and stale sources are reported rather than treated as current. |
| 4. Independent Poisson | Complete | Team attack/defence plus home advantage, score matrix, H/D/A probabilities. | Beat or clearly characterize naive baselines on development data. |
| 5. Time-decayed Dixon-Coles | Complete | Recency decay and low-score correction under the same evaluation contract. | Chronological tuning only; justify added complexity. |
| 6. Promoted-team prior | Complete | Training-only dynamic promoted-team attack/defence shrinkage. | Improve cold-start behavior without holdout or market leakage. |
| 7. Small-data ML challengers | Planned | Regularized, low-capacity challengers using legal pre-match features only. | Out-of-sample gain and calibration justify complexity. |
| 8. Candidate freeze | Planned | Select model and calibration rule using development evidence. | Code, hyperparameters, and decision rule frozen before holdout. |
| 9. Final benchmark | Locked | One-time 2025-26 holdout evaluation and post-prediction market comparison. | Report performance, calibration, uncertainty, and failure modes. |
| 10. 2026-27 prediction runner | Planned | Reproducible pre-match score distribution and H/D/A prediction command. | Current-season ingestion and monitoring rules pass review. |

## Current boundary

Stages 3 to 6 emit development-period research probabilities only; none is the
final live system. Stage 4 independent Poisson beats both naive baselines
(`reports/POISSON_REPORT.md`). Stage 5 time-decayed Dixon-Coles beats Stage 4,
but its ablations attribute the gain to recency decay; the low-score correction
is not justified on H/D/A metrics (`reports/DIXON_COLES_REPORT.md`). Stage 6's
dynamic promoted-team prior passes its declared cold-start gate on point
estimates. Its approximate intervals include zero, and every `k` selection sits
at the grid maximum (`reports/PROMOTED_PRIOR_REPORT.md`). Stage 7 is next in
order and needs a new user go-ahead.

The final holdout is opened once, only after the Stage 8 candidate freeze. The
market benchmark is never a predictive feature and is not used to tune Stages
3 through 8.
