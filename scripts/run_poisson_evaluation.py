#!/usr/bin/env python3
"""Run the Stage 4 leakage-safe independent Poisson walk-forward evaluation."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import evaluation_time
import run_baseline_evaluation as baseline


ROOT = Path(__file__).resolve().parents[1]
PREDICTIONS_OUTPUT = ROOT / "reports" / "poisson_predictions.csv"
METRICS_OUTPUT = ROOT / "reports" / "poisson_metrics.csv"
REPORT_OUTPUT = ROOT / "reports" / "POISSON_REPORT.md"

MODEL_NAME = "independent_poisson"
COMPARISON_MODEL = "expanding_league_hda"
REPORT_MODEL_ORDER = [*baseline.MODEL_ORDER, MODEL_NAME]
# Fixed N(0, 1) penalty on every team log-strength. It keeps sparse and unseen
# clubs finite and identifiable; it is declared here, not tuned on evaluation data.
TEAM_STRENGTH_PRECISION = 1.0
MAX_GOALS = 30
MIN_SCORE_MATRIX_MASS = 1.0 - 1e-9
NEWTON_TOLERANCE = 1e-10
FULL_STEP_THRESHOLD = 1e-4
MAX_NEWTON_ITERATIONS = 50
MAX_STEP_HALVINGS = 40
# Iterative fits are reproducible to numerical tolerance rather than bit-for-bit
# across BLAS/libm builds, so per-match fitted values are published rounded.
PUBLISHED_FLOAT_FORMAT = "%.9f"
FULL_SEASON_MATCHES = 34
PREDICTION_COLUMNS = [
    "match_id",
    "season",
    "prediction_time",
    "model",
    "available_history_rows",
    "training_rows_used",
    "latest_result_available_at",
    "home_team",
    "away_team",
    "home_team_history_matches",
    "away_team_history_matches",
    "expected_home_goals",
    "expected_away_goals",
    *baseline.PROBABILITY_COLUMNS,
    "p_observed_score",
    "actual_home_goals",
    "actual_away_goals",
    "actual_result",
]


class PoissonEvaluationError(RuntimeError):
    """The Stage 4 model or its evaluation contract was violated."""


@dataclass(frozen=True)
class PoissonFit:
    """Penalized maximum-likelihood team strengths fitted to one history."""

    teams: tuple[str, ...]
    intercept: float
    home_advantage: float
    attack: np.ndarray
    defence: np.ndarray
    training_rows: int
    _index: dict[str, int] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "_index", {team: position for position, team in enumerate(self.teams)}
        )

    def team_strength(self, team: str) -> tuple[float, float]:
        """Return attack and defence; an unseen club sits at the penalty centre."""
        position = self._index.get(team)
        if position is None:
            return 0.0, 0.0
        return float(self.attack[position]), float(self.defence[position])

    def expected_goals(self, home_team: str, away_team: str) -> tuple[float, float]:
        if home_team == away_team:
            raise PoissonEvaluationError("A fixture needs two different teams")
        home_attack, home_defence = self.team_strength(home_team)
        away_attack, away_defence = self.team_strength(away_team)
        expected_home = math.exp(
            self.intercept + self.home_advantage + home_attack - away_defence
        )
        expected_away = math.exp(self.intercept + away_attack - home_defence)
        return expected_home, expected_away


def _goal_array(values: pd.Series) -> np.ndarray:
    goals = pd.to_numeric(values, errors="raise")
    if goals.isna().any() or goals.lt(0).any() or not goals.eq(goals.round()).all():
        raise PoissonEvaluationError("Training goals must be non-negative integers")
    return goals.to_numpy(dtype=float)


@dataclass(frozen=True)
class _Design:
    goals: np.ndarray
    attackers: np.ndarray
    defenders: np.ndarray
    is_home: np.ndarray
    n_teams: int


def _penalized_log_likelihood(theta: np.ndarray, design: _Design) -> float:
    n_teams = design.n_teams
    attack = theta[2 : 2 + n_teams]
    defence = theta[2 + n_teams :]
    eta = (
        theta[0]
        + theta[1] * design.is_home
        + attack[design.attackers]
        - defence[design.defenders]
    )
    with np.errstate(over="ignore"):
        rate = np.exp(eta)
        value = float((design.goals * eta - rate).sum())
    penalty = 0.5 * TEAM_STRENGTH_PRECISION * float(
        (attack * attack).sum() + (defence * defence).sum()
    )
    return value - penalty


def _gradient_and_information(
    theta: np.ndarray, design: _Design
) -> tuple[np.ndarray, np.ndarray]:
    n_teams = design.n_teams
    attack = theta[2 : 2 + n_teams]
    defence = theta[2 + n_teams :]
    eta = (
        theta[0]
        + theta[1] * design.is_home
        + attack[design.attackers]
        - defence[design.defenders]
    )
    rate = np.exp(eta)
    residual = design.goals - rate
    home_rate = rate * design.is_home

    gradient = np.empty(2 + 2 * n_teams)
    gradient[0] = residual.sum()
    gradient[1] = (residual * design.is_home).sum()
    gradient[2 : 2 + n_teams] = (
        np.bincount(design.attackers, weights=residual, minlength=n_teams)
        - TEAM_STRENGTH_PRECISION * attack
    )
    gradient[2 + n_teams :] = (
        -np.bincount(design.defenders, weights=residual, minlength=n_teams)
        - TEAM_STRENGTH_PRECISION * defence
    )

    attack_rate = np.bincount(design.attackers, weights=rate, minlength=n_teams)
    defence_rate = np.bincount(design.defenders, weights=rate, minlength=n_teams)
    attack_home_rate = np.bincount(design.attackers, weights=home_rate, minlength=n_teams)
    defence_home_rate = np.bincount(design.defenders, weights=home_rate, minlength=n_teams)
    pair_rate = np.bincount(
        design.attackers * n_teams + design.defenders,
        weights=rate,
        minlength=n_teams * n_teams,
    ).reshape(n_teams, n_teams)

    attack_slice = slice(2, 2 + n_teams)
    defence_slice = slice(2 + n_teams, 2 + 2 * n_teams)
    information = np.zeros((2 + 2 * n_teams, 2 + 2 * n_teams))
    information[0, 0] = rate.sum()
    information[0, 1] = information[1, 0] = information[1, 1] = home_rate.sum()
    information[0, attack_slice] = information[attack_slice, 0] = attack_rate
    information[0, defence_slice] = information[defence_slice, 0] = -defence_rate
    information[1, attack_slice] = information[attack_slice, 1] = attack_home_rate
    information[1, defence_slice] = information[defence_slice, 1] = -defence_home_rate
    information[attack_slice, attack_slice] = np.diag(
        attack_rate + TEAM_STRENGTH_PRECISION
    )
    information[defence_slice, defence_slice] = np.diag(
        defence_rate + TEAM_STRENGTH_PRECISION
    )
    information[attack_slice, defence_slice] = -pair_rate
    information[defence_slice, attack_slice] = -pair_rate.T
    return gradient, information


def fit_independent_poisson(history: pd.DataFrame) -> PoissonFit:
    """Fit attack, defence, intercept, and home advantage by penalized Newton steps."""
    required = {"home_team", "away_team", "home_goals", "away_goals"}
    missing = required.difference(history.columns)
    if missing:
        raise PoissonEvaluationError(f"Poisson history is missing columns: {sorted(missing)}")
    if history.empty:
        raise PoissonEvaluationError("Independent Poisson needs at least one prior result")

    home_teams = history["home_team"].astype("string")
    away_teams = history["away_team"].astype("string")
    if home_teams.isna().any() or away_teams.isna().any():
        raise PoissonEvaluationError("Training rows contain missing team names")
    if home_teams.eq(away_teams).any():
        raise PoissonEvaluationError("Training rows contain a team playing itself")
    home_goals = _goal_array(history["home_goals"])
    away_goals = _goal_array(history["away_goals"])
    if home_goals.sum() <= 0 or away_goals.sum() <= 0:
        raise PoissonEvaluationError("Poisson history needs home and away goals")

    teams = tuple(sorted(set(home_teams.tolist()) | set(away_teams.tolist())))
    index = {team: position for position, team in enumerate(teams)}
    home_index = np.array([index[team] for team in home_teams.tolist()], dtype=np.int64)
    away_index = np.array([index[team] for team in away_teams.tolist()], dtype=np.int64)
    n_matches = len(history)
    design = _Design(
        goals=np.concatenate([home_goals, away_goals]),
        attackers=np.concatenate([home_index, away_index]),
        defenders=np.concatenate([away_index, home_index]),
        is_home=np.concatenate([np.ones(n_matches), np.zeros(n_matches)]),
        n_teams=len(teams),
    )

    theta = np.zeros(2 + 2 * len(teams))
    theta[0] = math.log(float(away_goals.mean()))
    theta[1] = math.log(float(home_goals.mean()) / float(away_goals.mean()))
    objective = _penalized_log_likelihood(theta, design)
    for _ in range(MAX_NEWTON_ITERATIONS):
        gradient, information = _gradient_and_information(theta, design)
        step = np.linalg.solve(information, gradient)
        if not np.isfinite(step).all():
            raise PoissonEvaluationError("Poisson Newton step is not finite")
        largest_step = float(np.abs(step).max())
        if largest_step <= FULL_STEP_THRESHOLD:
            theta = theta + step
            objective = _penalized_log_likelihood(theta, design)
            if largest_step < NEWTON_TOLERANCE:
                n_teams = design.n_teams
                return PoissonFit(
                    teams=teams,
                    intercept=float(theta[0]),
                    home_advantage=float(theta[1]),
                    attack=theta[2 : 2 + n_teams].copy(),
                    defence=theta[2 + n_teams :].copy(),
                    training_rows=n_matches,
                )
            continue

        scale = 1.0
        for _ in range(MAX_STEP_HALVINGS):
            candidate = theta + scale * step
            candidate_objective = _penalized_log_likelihood(candidate, design)
            if math.isfinite(candidate_objective) and candidate_objective >= objective:
                break
            scale *= 0.5
        else:
            raise PoissonEvaluationError("Poisson Newton step did not improve the objective")
        theta, objective = candidate, candidate_objective
    raise PoissonEvaluationError("Poisson fit did not converge")


def _poisson_pmf(rate: float, max_goals: int = MAX_GOALS) -> np.ndarray:
    if not math.isfinite(rate) or rate <= 0.0:
        raise PoissonEvaluationError("Expected goals must be finite and positive")
    pmf = np.empty(max_goals + 1)
    pmf[0] = math.exp(-rate)
    for goals in range(1, max_goals + 1):
        pmf[goals] = pmf[goals - 1] * rate / goals
    return pmf


def score_distribution(expected_home: float, expected_away: float) -> np.ndarray:
    """Return the renormalized independent score matrix; rows are home goals."""
    matrix = np.outer(_poisson_pmf(expected_home), _poisson_pmf(expected_away))
    mass = float(matrix.sum())
    if not mass >= MIN_SCORE_MATRIX_MASS:
        raise PoissonEvaluationError("Score matrix truncation lost too much probability")
    return matrix / mass


def hda_probabilities(matrix: np.ndarray) -> tuple[float, float, float]:
    return (
        float(np.tril(matrix, -1).sum()),
        float(np.trace(matrix)),
        float(np.triu(matrix, 1).sum()),
    )


def _team_appearances(history: pd.DataFrame) -> pd.Series:
    return pd.concat([history["home_team"], history["away_team"]]).value_counts()


def predict_fixtures(
    matches: pd.DataFrame, cutoff: pd.Timestamp, fixtures: pd.DataFrame
) -> list[dict[str, Any]]:
    """Fit on results available strictly before `cutoff` and predict its fixtures."""
    history = evaluation_time.available_history(matches, cutoff)
    if history.empty:
        raise PoissonEvaluationError("A development prediction has no prior history")
    latest = pd.to_datetime(
        history["result_available_at"], format="ISO8601", utc=True, errors="raise"
    ).max()
    if not latest < cutoff:
        raise PoissonEvaluationError("Poisson history crosses the strict time boundary")
    fit = fit_independent_poisson(history)
    appearances = _team_appearances(history)

    rows: list[dict[str, Any]] = []
    for match in fixtures.itertuples(index=False):
        expected_home, expected_away = fit.expected_goals(match.home_team, match.away_team)
        matrix = score_distribution(expected_home, expected_away)
        p_home, p_draw, p_away = hda_probabilities(matrix)
        home_goals = int(match.home_goals)
        away_goals = int(match.away_goals)
        if max(home_goals, away_goals) > MAX_GOALS:
            raise PoissonEvaluationError("Observed score lies outside the score matrix")
        rows.append(
            {
                "match_id": match.match_id,
                "season": match.season,
                "prediction_time": cutoff.isoformat(),
                "model": MODEL_NAME,
                "available_history_rows": len(history),
                "training_rows_used": fit.training_rows,
                "latest_result_available_at": latest.isoformat(),
                "home_team": match.home_team,
                "away_team": match.away_team,
                "home_team_history_matches": int(appearances.get(match.home_team, 0)),
                "away_team_history_matches": int(appearances.get(match.away_team, 0)),
                "expected_home_goals": expected_home,
                "expected_away_goals": expected_away,
                "p_home": p_home,
                "p_draw": p_draw,
                "p_away": p_away,
                "p_observed_score": float(matrix[home_goals, away_goals]),
                "actual_home_goals": home_goals,
                "actual_away_goals": away_goals,
                "actual_result": match.result,
            }
        )
    return rows


def build_predictions(matches: pd.DataFrame, splits: pd.DataFrame) -> pd.DataFrame:
    targets = baseline.development_targets(matches, splits)
    # Parse availability once; every cutoff still filters through evaluation_time.
    timeline = matches.copy()
    timeline["result_available_at"] = pd.to_datetime(
        timeline["result_available_at"], format="ISO8601", utc=True, errors="raise"
    )
    rows: list[dict[str, Any]] = []
    for cutoff, fixtures in targets.groupby("_prediction_time", sort=True):
        rows.extend(predict_fixtures(timeline, cutoff, fixtures))
    predictions = pd.DataFrame(rows, columns=PREDICTION_COLUMNS)
    predictions = predictions.sort_values(
        ["prediction_time", "match_id"], kind="stable"
    ).reset_index(drop=True)
    _validate_predictions(predictions, targets, splits)
    return predictions


def _validate_predictions(
    predictions: pd.DataFrame, targets: pd.DataFrame, splits: pd.DataFrame
) -> None:
    if predictions.columns.tolist() != PREDICTION_COLUMNS:
        raise PoissonEvaluationError("Poisson prediction output schema changed")
    if predictions["match_id"].duplicated().any():
        raise PoissonEvaluationError("Duplicate Poisson match predictions")
    if len(predictions) != len(targets) or set(predictions["match_id"]) != set(
        targets["match_id"]
    ):
        raise PoissonEvaluationError("Poisson prediction coverage is incomplete")
    development_seasons = set(splits.loc[splits["role"] == "development", "season"])
    if not set(predictions["season"]).issubset(development_seasons):
        raise PoissonEvaluationError("Poisson predictions left the development split")

    probabilities = predictions[baseline.PROBABILITY_COLUMNS].to_numpy(dtype=float)
    if not np.isfinite(probabilities).all():
        raise PoissonEvaluationError("Poisson probabilities must be finite")
    if not ((probabilities > 0.0) & (probabilities < 1.0)).all():
        raise PoissonEvaluationError("Poisson probabilities must be strictly inside (0, 1)")
    if not (np.abs(probabilities.sum(axis=1) - 1.0) < 1e-12).all():
        raise PoissonEvaluationError("Poisson probabilities do not sum to one")
    expected = predictions[["expected_home_goals", "expected_away_goals"]].to_numpy(
        dtype=float
    )
    if not (np.isfinite(expected).all() and (expected > 0.0).all()):
        raise PoissonEvaluationError("Expected goals must be finite and positive")
    observed_score = predictions["p_observed_score"].to_numpy(dtype=float)
    if not ((observed_score > 0.0) & (observed_score <= 1.0)).all():
        raise PoissonEvaluationError("Observed-score probabilities are invalid")

    home_goals = predictions["actual_home_goals"]
    away_goals = predictions["actual_away_goals"]
    implied = np.select(
        [home_goals.gt(away_goals), home_goals.eq(away_goals)], ["H", "D"], "A"
    )
    if not predictions["actual_result"].eq(pd.Series(implied, index=predictions.index)).all():
        raise PoissonEvaluationError("Actual results disagree with actual goals")
    prediction_times = pd.to_datetime(predictions["prediction_time"], utc=True, errors="raise")
    latest_results = pd.to_datetime(
        predictions["latest_result_available_at"], utc=True, errors="raise"
    )
    if not latest_results.lt(prediction_times).all():
        raise PoissonEvaluationError("Prediction history crosses the strict time boundary")


def load_baseline_outputs(
    predictions: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load the freshly regenerated baseline outputs for the same fixtures."""
    baseline_predictions = pd.read_csv(
        baseline.PREDICTIONS_OUTPUT,
        dtype={
            "match_id": "string",
            "season": "string",
            "prediction_time": "string",
            "model": "string",
            "actual_result": "string",
        },
    )
    baseline_metrics = pd.read_csv(baseline.METRICS_OUTPUT, dtype={"season": "string"})
    expected_times = predictions.set_index("match_id")["prediction_time"].astype(str)
    for model in baseline.MODEL_ORDER:
        selected = baseline_predictions.loc[baseline_predictions["model"] == model]
        selected_times = selected.set_index("match_id")["prediction_time"].astype(str)
        if (
            len(selected) != len(predictions)
            or selected_times.index.duplicated().any()
            or not selected_times.reindex(expected_times.index).eq(expected_times).all()
        ):
            raise PoissonEvaluationError(
                f"Baseline {model} predictions do not match the Poisson fixtures"
            )
    return baseline_predictions, baseline_metrics


def _paired_rows(merged: pd.DataFrame) -> list[list[Any]]:
    rows: list[list[Any]] = []
    groups = [("ALL", merged)] + [
        (season, merged.loc[merged["season"] == season])
        for season in sorted(merged["season"].unique())
    ]
    for label, group in groups:
        difference = group["log_loss_poisson"] - group["log_loss_comparison"]
        mean = float(difference.mean())
        standard_error = float(difference.std(ddof=1)) / math.sqrt(len(difference))
        rows.append(
            [
                label,
                len(group),
                f"{mean:+.6f}",
                f"[{mean - 1.96 * standard_error:+.6f}, {mean + 1.96 * standard_error:+.6f}]",
                f"{float(group['log_loss_poisson'].lt(group['log_loss_comparison']).mean()):.1%}",
            ]
        )
    return rows


def _history_bucket(matches_seen: int) -> str:
    if matches_seen == 0:
        return "0 (unseen club)"
    if matches_seen < FULL_SEASON_MATCHES:
        return f"1-{FULL_SEASON_MATCHES - 1}"
    return f"{FULL_SEASON_MATCHES}+"


def generate_report(
    predictions: pd.DataFrame,
    metrics: pd.DataFrame,
    baseline_predictions: pd.DataFrame,
    baseline_metrics: pd.DataFrame,
) -> str:
    all_metrics = pd.concat([baseline_metrics, metrics], ignore_index=True)
    overall = all_metrics.loc[all_metrics["season"] == "ALL"].set_index("model")
    poisson_loss = float(overall.loc[MODEL_NAME, "log_loss"])
    poisson_brier = float(overall.loc[MODEL_NAME, "brier_score"])
    comparison_loss = float(overall.loc[COMPARISON_MODEL, "log_loss"])
    comparison_brier = float(overall.loc[COMPARISON_MODEL, "brier_score"])
    uniform_loss = float(overall.loc["uniform_hda", "log_loss"])

    poisson_scored = baseline.add_match_scores(predictions)
    comparison_scored = baseline.add_match_scores(
        baseline_predictions.loc[baseline_predictions["model"] == COMPARISON_MODEL]
    )
    merged = poisson_scored[
        ["match_id", "season", "log_loss", "home_team_history_matches",
         "away_team_history_matches"]
    ].merge(
        comparison_scored[["match_id", "log_loss"]],
        on="match_id",
        suffixes=("_poisson", "_comparison"),
        validate="one_to_one",
    )
    if len(merged) != len(predictions):
        raise PoissonEvaluationError("Paired comparison lost fixtures")
    paired = _paired_rows(merged)
    overall_mean = float((merged["log_loss_poisson"] - merged["log_loss_comparison"]).mean())
    overall_interval = paired[0][3]
    interval_bounds = [float(value) for value in overall_interval.strip("[]").split(",")]
    interval_excludes_zero = interval_bounds[1] < 0.0 or interval_bounds[0] > 0.0

    beats = poisson_loss < comparison_loss and poisson_brier < comparison_brier
    if beats:
        verdict = [
            f"**GO.** `{MODEL_NAME}` beats `{COMPARISON_MODEL}` on development log loss",
            f"({poisson_loss:.6f} vs {comparison_loss:.6f}) and Brier score",
            f"({poisson_brier:.6f} vs {comparison_brier:.6f}).",
        ]
    else:
        verdict = [
            f"**CHARACTERIZED.** `{MODEL_NAME}` does not beat `{COMPARISON_MODEL}` on both",
            f"development log loss ({poisson_loss:.6f} vs {comparison_loss:.6f}) and Brier",
            f"score ({poisson_brier:.6f} vs {comparison_brier:.6f}).",
        ]
    gap_share = (uniform_loss - poisson_loss) / uniform_loss
    verdict += [
        "",
        f"The mean paired log-loss difference against `{COMPARISON_MODEL}` is",
        f"{overall_mean:+.6f} with an approximate 95% interval of {overall_interval}; the",
        "interval " + ("excludes" if interval_excludes_zero else "includes") + " zero.",
        f"Its relative log-loss improvement over `uniform_hda` is {gap_share:.2%}.",
        "No final-holdout result or market probability was used. This is development",
        "evidence for the comparison ladder, not a deployable 2026-27 model.",
    ]

    overall_rows = [
        [
            model,
            int(overall.loc[model, "matches"]),
            f"{float(overall.loc[model, 'log_loss']):.6f}",
            f"{float(overall.loc[model, 'brier_score']):.6f}",
        ]
        for model in REPORT_MODEL_ORDER
    ]
    by_season = all_metrics.loc[all_metrics["season"] != "ALL"]
    season_rows = [
        [
            season,
            model,
            int(row["matches"]),
            f"{float(row['log_loss']):.6f}",
            f"{float(row['brier_score']):.6f}",
        ]
        for season in sorted(by_season["season"].unique())
        for model in REPORT_MODEL_ORDER
        for _, row in by_season.loc[
            (by_season["season"] == season) & (by_season["model"] == model)
        ].iterrows()
    ]

    observed = predictions["actual_result"].value_counts(normalize=True)
    calibration_rows = [
        [
            "observed frequency",
            *[f"{float(observed.get(outcome, 0.0)):.4f}" for outcome in ("H", "D", "A")],
        ]
    ]
    for model in REPORT_MODEL_ORDER:
        source = (
            predictions
            if model == MODEL_NAME
            else baseline_predictions.loc[baseline_predictions["model"] == model]
        )
        calibration_rows.append(
            [
                f"mean `{model}`",
                *[
                    f"{float(source[column].mean()):.4f}"
                    for column in baseline.PROBABILITY_COLUMNS
                ],
            ]
        )
    goals_rows = [
        [
            "home",
            f"{float(predictions['actual_home_goals'].mean()):.4f}",
            f"{float(predictions['expected_home_goals'].mean()):.4f}",
        ],
        [
            "away",
            f"{float(predictions['actual_away_goals'].mean()):.4f}",
            f"{float(predictions['expected_away_goals'].mean()):.4f}",
        ],
    ]

    merged["history_bucket"] = [
        _history_bucket(int(min(home, away)))
        for home, away in zip(
            merged["home_team_history_matches"], merged["away_team_history_matches"]
        )
    ]
    bucket_order = [
        _history_bucket(0),
        _history_bucket(1),
        _history_bucket(FULL_SEASON_MATCHES),
    ]
    bucket_rows = []
    for bucket in bucket_order:
        group = merged.loc[merged["history_bucket"] == bucket]
        if group.empty:
            bucket_rows.append([bucket, 0, "-", "-", "-"])
            continue
        comparison_mean = float(group["log_loss_comparison"].mean())
        poisson_mean = float(group["log_loss_poisson"].mean())
        bucket_rows.append(
            [
                bucket,
                len(group),
                f"{comparison_mean:.6f}",
                f"{poisson_mean:.6f}",
                f"{poisson_mean - comparison_mean:+.6f}",
            ]
        )
    scoreline_loss = float(
        predictions["p_observed_score"].map(lambda value: -math.log(value)).mean()
    )
    worst = poisson_scored.sort_values(
        ["log_loss", "match_id"], ascending=[False, True], kind="stable"
    ).head(5)
    worst_rows = [
        [
            row.season,
            str(row.prediction_time)[:10],
            f"{row.home_team} - {row.away_team}",
            int(min(row.home_team_history_matches, row.away_team_history_matches)),
            f"{row.expected_home_goals:.2f} - {row.expected_away_goals:.2f}",
            f"{int(row.actual_home_goals)}-{int(row.actual_away_goals)}",
            f"{row.log_loss:.4f}",
        ]
        for row in worst.itertuples(index=False)
    ]

    lines = [
        "# Independent Poisson evaluation",
        "",
        "## Verdict",
        "",
        *verdict,
        "",
        "## Overall development results",
        "",
        *baseline._markdown_table(
            ["Model", "Matches", "Log loss", "Brier score"], overall_rows
        ),
        "",
        "Lower is better. Log loss uses natural logarithms; the multiclass Brier",
        "score is the mean sum of squared H/D/A probability errors. Aggregate metrics",
        "are computed before per-match fitted values are rounded for publication.",
        "",
        f"## Paired log-loss difference against `{COMPARISON_MODEL}`",
        "",
        *baseline._markdown_table(
            [
                "Season",
                "Matches",
                "Mean difference",
                "Approx. 95% interval",
                "Poisson lower on match",
            ],
            paired,
        ),
        "",
        "Negative differences favour the Poisson model. Intervals use a normal",
        "approximation that treats matches as independent; they ignore dependence",
        "within match rounds and are descriptive, not a selection rule.",
        "",
        "## Results by season",
        "",
        *baseline._markdown_table(
            ["Season", "Model", "Matches", "Log loss", "Brier score"], season_rows
        ),
        "",
        "## Calibration in the large",
        "",
        *baseline._markdown_table(["Source", "Home", "Draw", "Away"], calibration_rows),
        "",
        *baseline._markdown_table(
            ["Side", "Observed mean goals", "Mean expected goals"], goals_rows
        ),
        "",
        "## Cold-start characterization",
        "",
        "Fixtures are grouped by the fewer prior eligible matches of the two clubs in",
        "the history available at prediction time.",
        "",
        *baseline._markdown_table(
            [
                "Fewest prior matches",
                "Matches",
                f"`{COMPARISON_MODEL}` log loss",
                "Poisson log loss",
                "Difference",
            ],
            bucket_rows,
        ),
        "",
        "This slice is descriptive evidence for the later promoted-team prior. It is",
        "not used to adjust the Stage 4 specification.",
        "",
        "## Largest single-match Poisson losses",
        "",
        *baseline._markdown_table(
            [
                "Season",
                "Kickoff date",
                "Fixture",
                "Fewest prior matches",
                "Expected goals",
                "Score",
                "H/D/A log loss",
            ],
            worst_rows,
        ),
        "",
        "Clubs with very little history can receive extreme rates under the fixed",
        "penalty. These rows document the cold-start failure mode that the Stage 6",
        "promoted-team prior must address; they are not a reason to retune Stage 4.",
        "",
        "## Scoreline diagnostic",
        "",
        f"Mean negative log probability of the observed exact score: {scoreline_loss:.6f}.",
        "This diagnostic prepares the Stage 5 low-score comparison; the primary and",
        "secondary metrics remain H/D/A log loss and Brier score.",
        "",
        "## Model specification",
        "",
        "For every prediction time `t`, one model is fitted by penalized maximum",
        "likelihood to every eligible on-pitch score with `result_available_at < t`:",
        "",
        "```text",
        "home_goals ~ Poisson(exp(intercept + home_advantage + attack[home] - defence[away]))",
        "away_goals ~ Poisson(exp(intercept + attack[away] - defence[home]))",
        "```",
        "",
        "- Home and away goals are conditionally independent given the two rates.",
        "- All available history is weighted equally; recency decay belongs to Stage 5.",
        "- Intercept and home advantage are unpenalized. Every team attack and defence",
        f"  log-strength has a fixed N(0, {1.0 / TEAM_STRENGTH_PRECISION:g}) penalty that keeps sparse clubs",
        "  identifiable; it is not tuned and is not a promoted-team prior.",
        "- A club with no prior eligible result receives strength 0, the penalty centre.",
        f"- Score probabilities use a 0-{MAX_GOALS} goal grid per side and are renormalized",
        "  after a truncation-mass check; H/D/A probabilities sum that matrix.",
        "- Official awarded scores, match statistics, and market odds are not inputs.",
        "",
        "## Frozen evaluation boundary",
        "",
        "- Warm-up history: 2017-18 through 2020-21.",
        "- Development walk-forward: 2021-22 through 2024-25.",
        "- Final holdout: 2025-26, still sealed and absent from fitting and metrics.",
        "- Current season: 2026-27, live-only and absent from development metrics.",
        "- Each fit uses only `evaluation_time.available_history` at the prediction time.",
        "- Same-kickoff fixtures share one fit and the same available history.",
        "- The isolated market benchmark table is not loaded by the evaluator.",
        "",
        "## Next roadmap gate",
        "",
        "Stage 5 adds recency decay and the Dixon-Coles low-score correction under the",
        "same split and metrics, with chronological tuning only. Do not open the",
        "2025-26 holdout and do not implement the promoted-team prior yet.",
        "",
    ]
    return "\n".join(lines)


def write_outputs(
    predictions: pd.DataFrame,
    metrics: pd.DataFrame,
    baseline_predictions: pd.DataFrame,
    baseline_metrics: pd.DataFrame,
) -> None:
    PREDICTIONS_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(PREDICTIONS_OUTPUT, index=False, float_format=PUBLISHED_FLOAT_FORMAT)
    metrics.to_csv(METRICS_OUTPUT, index=False, float_format="%.12f")
    REPORT_OUTPUT.write_text(
        generate_report(predictions, metrics, baseline_predictions, baseline_metrics),
        encoding="utf-8",
    )


def main() -> int:
    baseline_status = baseline.main()
    if baseline_status != 0:
        return baseline_status
    splits = baseline.load_split_config()
    matches = baseline.load_matches()
    predictions = build_predictions(matches, splits)
    metrics = baseline.score_predictions(predictions, [MODEL_NAME])
    baseline_predictions, baseline_metrics = load_baseline_outputs(predictions)
    write_outputs(predictions, metrics, baseline_predictions, baseline_metrics)
    print(f"Poisson evaluation complete: {len(predictions)} development matches.")
    print(f"Report: {REPORT_OUTPUT}")
    print("Final holdout: SEALED (2025-26)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
