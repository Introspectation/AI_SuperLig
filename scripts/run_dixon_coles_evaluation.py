#!/usr/bin/env python3
"""Run the Stage 5 leakage-safe time-decayed Dixon-Coles walk-forward evaluation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import evaluation_time
import run_baseline_evaluation as baseline
import run_poisson_evaluation as poisson


ROOT = Path(__file__).resolve().parents[1]
PREDICTIONS_OUTPUT = ROOT / "reports" / "dixon_coles_predictions.csv"
METRICS_OUTPUT = ROOT / "reports" / "dixon_coles_metrics.csv"
GRID_METRICS_OUTPUT = ROOT / "reports" / "dixon_coles_grid_metrics.csv"
SELECTION_OUTPUT = ROOT / "reports" / "dixon_coles_selection.csv"
REPORT_OUTPUT = ROOT / "reports" / "DIXON_COLES_REPORT.md"

CANDIDATE_MODEL = "dixon_coles_decay"
DECAY_ONLY_MODEL = "poisson_decay"
RHO_ONLY_MODEL = "dixon_coles_no_decay"
MODEL_ORDER = [CANDIDATE_MODEL, DECAY_ONLY_MODEL, RHO_ONLY_MODEL]
REFERENCE_MODEL = poisson.MODEL_NAME
REPORT_MODEL_ORDER = [
    *baseline.MODEL_ORDER,
    REFERENCE_MODEL,
    DECAY_ONLY_MODEL,
    RHO_ONLY_MODEL,
    CANDIDATE_MODEL,
]
# Declared in MODEL_DESIGN.md before any Stage 5 metric was computed.
DECAY_GRID_PER_DAY = (0.0, 0.0005, 0.001, 0.0015, 0.002, 0.003, 0.005)
GRID_SEASONS = ("2019-20", "2020-21", "2021-22", "2022-23", "2023-24", "2024-25")
TUNING_ONLY_SEASONS = ("2019-20", "2020-21")
LOW_SCORE_CELLS = (("0-0", 0, 0), ("1-0", 1, 0), ("0-1", 0, 1), ("1-1", 1, 1))
# Stage 4's 0-30 grid lost more than 1e-9 mass for one declared fit; see the
# pre-metric amendment in MODEL_DESIGN.md.
SCORE_GRID_MAX_GOALS = 40
PREDICTION_COLUMNS = [
    "match_id",
    "season",
    "prediction_time",
    "model",
    "decay_per_day",
    "available_history_rows",
    "training_rows_used",
    "effective_training_weight",
    "latest_result_available_at",
    "home_team",
    "away_team",
    "home_team_history_matches",
    "away_team_history_matches",
    "expected_home_goals",
    "expected_away_goals",
    "fitted_rho",
    *baseline.PROBABILITY_COLUMNS,
    "p_score_0_0",
    "p_score_1_0",
    "p_score_0_1",
    "p_score_1_1",
    "p_observed_score",
    "actual_home_goals",
    "actual_away_goals",
    "actual_result",
]
GRID_METRIC_COLUMNS = [
    "season",
    "season_role",
    "decay_per_day",
    "matches",
    "log_loss",
    "brier_score",
]
SELECTION_COLUMNS = [
    "target_season",
    "tuning_seasons",
    "tuning_matches",
    "selected_decay_per_day",
    "selected_tuning_log_loss",
    "no_decay_tuning_log_loss",
    "selected_at_grid_maximum",
]

TEAM_STRENGTH_PRECISION = poisson.TEAM_STRENGTH_PRECISION
NEWTON_TOLERANCE = poisson.NEWTON_TOLERANCE
FULL_STEP_THRESHOLD = poisson.FULL_STEP_THRESHOLD
MAX_NEWTON_ITERATIONS = 100
MAX_STEP_HALVINGS = 60
SECONDS_PER_DAY = 86400.0
HOME_VALUES = np.array([1.0, 1.0, 1.0, -1.0])
AWAY_VALUES = np.array([1.0, 0.0, 1.0, -1.0])


class DixonColesError(RuntimeError):
    """The Stage 5 model or its evaluation contract was violated."""


@dataclass(frozen=True)
class FitHistory:
    """Indexed scores and recency ages for one available history."""

    teams: tuple[str, ...]
    home_goals: np.ndarray
    away_goals: np.ndarray
    home_index: np.ndarray
    away_index: np.ndarray
    age_days: np.ndarray
    low_score: np.ndarray
    score_00: np.ndarray
    score_01: np.ndarray
    score_10: np.ndarray
    home_slots: np.ndarray
    away_slots: np.ndarray
    gradient_index: np.ndarray
    poisson_pair_index: np.ndarray
    correction_pair_index: np.ndarray

    @property
    def team_count(self) -> int:
        return len(self.teams)

    @property
    def parameter_count(self) -> int:
        return 3 + 2 * len(self.teams)

    @property
    def rho_index(self) -> int:
        return 2 + 2 * len(self.teams)


def build_fit_history(history: pd.DataFrame) -> FitHistory:
    """Index a history; ages are days before its most recent kickoff."""
    required = {"home_team", "away_team", "home_goals", "away_goals", "_kickoff_utc"}
    missing = required.difference(history.columns)
    if missing:
        raise DixonColesError(f"Dixon-Coles history is missing columns: {sorted(missing)}")
    if history.empty:
        raise DixonColesError("Dixon-Coles needs at least one prior result")
    home_teams = history["home_team"].astype("string")
    away_teams = history["away_team"].astype("string")
    if home_teams.isna().any() or away_teams.isna().any():
        raise DixonColesError("Training rows contain missing team names")
    if home_teams.eq(away_teams).any():
        raise DixonColesError("Training rows contain a team playing itself")
    home_goals = poisson._goal_array(history["home_goals"])
    away_goals = poisson._goal_array(history["away_goals"])
    if home_goals.sum() <= 0 or away_goals.sum() <= 0:
        raise DixonColesError("Dixon-Coles history needs home and away goals")

    kickoff = pd.to_datetime(history["_kickoff_utc"], utc=True, errors="raise")
    age_days = ((kickoff.max() - kickoff).dt.total_seconds() / SECONDS_PER_DAY).to_numpy(
        dtype=float
    )

    teams = tuple(sorted(set(home_teams.tolist()) | set(away_teams.tolist())))
    index = {team: position for position, team in enumerate(teams)}
    home_index = np.array([index[team] for team in home_teams.tolist()], dtype=np.int64)
    away_index = np.array([index[team] for team in away_teams.tolist()], dtype=np.int64)
    n_teams = len(teams)
    n_params = 3 + 2 * n_teams
    rho_index = 2 + 2 * n_teams
    zeros = np.zeros(len(history), dtype=np.int64)
    home_slots = np.column_stack(
        [zeros, zeros + 1, 2 + home_index, 2 + n_teams + away_index]
    )
    away_slots = np.column_stack(
        [zeros, zeros + 1, 2 + away_index, 2 + n_teams + home_index]
    )

    low_score = (home_goals <= 1.0) & (away_goals <= 1.0)
    low_home = home_slots[low_score]
    low_away = away_slots[low_score]
    rho_column = np.full(len(low_home), rho_index, dtype=np.int64)
    poisson_pair_index = np.concatenate(
        [
            (home_slots[:, :, None] * n_params + home_slots[:, None, :]).ravel(),
            (away_slots[:, :, None] * n_params + away_slots[:, None, :]).ravel(),
        ]
    )
    correction_pair_index = np.concatenate(
        [
            (low_home[:, :, None] * n_params + low_away[:, None, :]).ravel(),
            (low_away[:, :, None] * n_params + low_home[:, None, :]).ravel(),
            (low_home * n_params + rho_index).ravel(),
            (rho_index * n_params + low_home).ravel(),
            (low_away * n_params + rho_index).ravel(),
            (rho_index * n_params + low_away).ravel(),
            rho_column * n_params + rho_index,
        ]
    )
    gradient_index = np.concatenate(
        [home_slots.ravel(), away_slots.ravel(), rho_column]
    )
    low_home_goals = home_goals[low_score]
    low_away_goals = away_goals[low_score]
    return FitHistory(
        teams=teams,
        home_goals=home_goals,
        away_goals=away_goals,
        home_index=home_index,
        away_index=away_index,
        age_days=age_days,
        low_score=low_score,
        score_00=(low_home_goals == 0.0) & (low_away_goals == 0.0),
        score_01=(low_home_goals == 0.0) & (low_away_goals == 1.0),
        score_10=(low_home_goals == 1.0) & (low_away_goals == 0.0),
        home_slots=home_slots,
        away_slots=away_slots,
        gradient_index=gradient_index,
        poisson_pair_index=poisson_pair_index,
        correction_pair_index=correction_pair_index,
    )


@dataclass(frozen=True)
class DixonColesFit:
    """Weighted penalized maximum-likelihood strengths plus low-score correction."""

    strengths: poisson.PoissonFit
    rho: float
    decay_per_day: float
    effective_weight: float

    def expected_goals(self, home_team: str, away_team: str) -> tuple[float, float]:
        return self.strengths.expected_goals(home_team, away_team)

    def parameter_vector(self) -> dict[str, Any]:
        return {
            "teams": self.strengths.teams,
            "intercept": self.strengths.intercept,
            "home_advantage": self.strengths.home_advantage,
            "attack": self.strengths.attack,
            "defence": self.strengths.defence,
            "rho": self.rho,
        }


def _linear_predictors(theta: np.ndarray, fh: FitHistory) -> tuple[np.ndarray, np.ndarray]:
    n_teams = fh.team_count
    attack = theta[2 : 2 + n_teams]
    defence = theta[2 + n_teams : 2 + 2 * n_teams]
    eta_home = theta[0] + theta[1] + attack[fh.home_index] - defence[fh.away_index]
    eta_away = theta[0] + attack[fh.away_index] - defence[fh.home_index]
    return eta_home, eta_away


def _low_score_tau(
    home_rate: np.ndarray, away_rate: np.ndarray, rho: float, fh: FitHistory
) -> np.ndarray:
    return np.where(
        fh.score_00,
        1.0 - home_rate * away_rate * rho,
        np.where(
            fh.score_01,
            1.0 + home_rate * rho,
            np.where(fh.score_10, 1.0 + away_rate * rho, 1.0 - rho),
        ),
    )


def _objective(
    theta: np.ndarray, fh: FitHistory, weights: np.ndarray, estimate_rho: bool
) -> float:
    eta_home, eta_away = _linear_predictors(theta, fh)
    with np.errstate(over="ignore", invalid="ignore"):
        home_rate = np.exp(eta_home)
        away_rate = np.exp(eta_away)
        terms = weights * (
            fh.home_goals * eta_home - home_rate + fh.away_goals * eta_away - away_rate
        )
        value = float(terms.sum())
        if estimate_rho:
            tau = _low_score_tau(
                home_rate[fh.low_score], away_rate[fh.low_score], float(theta[-1]), fh
            )
            if not (np.isfinite(tau).all() and (tau > 0.0).all()):
                return -math.inf
            value += float((weights[fh.low_score] * np.log(tau)).sum())
    n_teams = fh.team_count
    strengths = theta[2 : 2 + 2 * n_teams]
    penalty = 0.5 * TEAM_STRENGTH_PRECISION * float((strengths * strengths).sum())
    return value - penalty if math.isfinite(value) else -math.inf


def _gradient_and_information(
    theta: np.ndarray, fh: FitHistory, weights: np.ndarray, estimate_rho: bool
) -> tuple[np.ndarray, np.ndarray]:
    eta_home, eta_away = _linear_predictors(theta, fh)
    home_rate = np.exp(eta_home)
    away_rate = np.exp(eta_away)
    n_params = fh.parameter_count
    n_low = int(fh.low_score.sum())

    grad_home = weights * (fh.home_goals - home_rate)
    grad_away = weights * (fh.away_goals - away_rate)
    info_home = weights * home_rate
    info_away = weights * away_rate
    grad_rho = np.zeros(n_low)
    info_cross = np.zeros(n_low)
    info_home_rho = np.zeros(n_low)
    info_away_rho = np.zeros(n_low)
    info_rho = np.zeros(n_low)

    if estimate_rho and n_low:
        rho = float(theta[-1])
        low_weights = weights[fh.low_score]
        lam = home_rate[fh.low_score]
        mu = away_rate[fh.low_score]
        tau = _low_score_tau(lam, mu, rho, fh)
        if not (np.isfinite(tau).all() and (tau > 0.0).all()):
            raise DixonColesError("Dixon-Coles correction left its valid region")
        tau_sq = tau * tau
        s00, s01, s10 = fh.score_00, fh.score_01, fh.score_10
        s11 = ~(s00 | s01 | s10)
        product = lam * mu
        joint = product * rho

        low_grad_home = np.where(s00, -joint / tau, np.where(s01, lam * rho / tau, 0.0))
        low_grad_away = np.where(s00, -joint / tau, np.where(s10, mu * rho / tau, 0.0))
        low_info_home = np.where(
            s00, joint / tau_sq, np.where(s01, -lam * rho / tau_sq, 0.0)
        )
        low_info_away = np.where(
            s00, joint / tau_sq, np.where(s10, -mu * rho / tau_sq, 0.0)
        )
        grad_rho = low_weights * np.where(
            s00,
            -product / tau,
            np.where(s01, lam / tau, np.where(s10, mu / tau, -1.0 / tau)),
        )
        info_cross = low_weights * np.where(s00, joint / tau_sq, 0.0)
        info_home_rho = low_weights * np.where(
            s00, product / tau_sq, np.where(s01, -lam / tau_sq, 0.0)
        )
        info_away_rho = low_weights * np.where(
            s00, product / tau_sq, np.where(s10, -mu / tau_sq, 0.0)
        )
        info_rho = low_weights * np.where(
            s00,
            product * product / tau_sq,
            np.where(s01, lam * lam / tau_sq, np.where(s10, mu * mu / tau_sq, 0.0)),
        ) + low_weights * np.where(s11, 1.0 / tau_sq, 0.0)

        grad_home = grad_home.copy()
        grad_away = grad_away.copy()
        info_home = info_home.copy()
        info_away = info_away.copy()
        grad_home[fh.low_score] += low_weights * low_grad_home
        grad_away[fh.low_score] += low_weights * low_grad_away
        info_home[fh.low_score] += low_weights * low_info_home
        info_away[fh.low_score] += low_weights * low_info_away

    gradient = np.bincount(
        fh.gradient_index,
        weights=np.concatenate(
            [
                (grad_home[:, None] * HOME_VALUES).ravel(),
                (grad_away[:, None] * AWAY_VALUES).ravel(),
                grad_rho,
            ]
        ),
        minlength=n_params,
    )
    home_outer = np.outer(HOME_VALUES, HOME_VALUES).ravel()
    away_outer = np.outer(AWAY_VALUES, AWAY_VALUES).ravel()
    information = np.bincount(
        fh.poisson_pair_index,
        weights=np.concatenate(
            [
                (info_home[:, None] * home_outer).ravel(),
                (info_away[:, None] * away_outer).ravel(),
            ]
        ),
        minlength=n_params * n_params,
    )
    if estimate_rho and n_low:
        information = information + np.bincount(
            fh.correction_pair_index,
            weights=np.concatenate(
                [
                    (info_cross[:, None] * np.outer(HOME_VALUES, AWAY_VALUES).ravel()).ravel(),
                    (info_cross[:, None] * np.outer(AWAY_VALUES, HOME_VALUES).ravel()).ravel(),
                    (info_home_rho[:, None] * HOME_VALUES).ravel(),
                    (info_home_rho[:, None] * HOME_VALUES).ravel(),
                    (info_away_rho[:, None] * AWAY_VALUES).ravel(),
                    (info_away_rho[:, None] * AWAY_VALUES).ravel(),
                    info_rho,
                ]
            ),
            minlength=n_params * n_params,
        )
    information = information.reshape(n_params, n_params)

    n_teams = fh.team_count
    strength_slice = slice(2, 2 + 2 * n_teams)
    gradient[strength_slice] -= TEAM_STRENGTH_PRECISION * theta[strength_slice]
    diagonal = np.arange(2, 2 + 2 * n_teams)
    information[diagonal, diagonal] += TEAM_STRENGTH_PRECISION
    return gradient, information


def _newton_direction(information: np.ndarray, gradient: np.ndarray) -> np.ndarray:
    try:
        np.linalg.cholesky(information)
        return np.linalg.solve(information, gradient)
    except np.linalg.LinAlgError:
        pass
    damping = 1e-6 * max(float(np.abs(np.diag(information)).max()), 1.0)
    for _ in range(40):
        damped = information + damping * np.eye(len(information))
        try:
            np.linalg.cholesky(damped)
            return np.linalg.solve(damped, gradient)
        except np.linalg.LinAlgError:
            damping *= 10.0
    raise DixonColesError("Dixon-Coles information matrix could not be stabilized")


def _initial_theta(
    fh: FitHistory, weights: np.ndarray, warm_start: dict[str, Any] | None
) -> np.ndarray:
    n_teams = fh.team_count
    theta = np.zeros(fh.parameter_count)
    total_weight = float(weights.sum())
    mean_home = float((weights * fh.home_goals).sum()) / total_weight
    mean_away = float((weights * fh.away_goals).sum()) / total_weight
    theta[0] = math.log(mean_away)
    theta[1] = math.log(mean_home / mean_away)
    if warm_start is None:
        return theta
    theta[0] = float(warm_start["intercept"])
    theta[1] = float(warm_start["home_advantage"])
    previous = {team: position for position, team in enumerate(warm_start["teams"])}
    for position, team in enumerate(fh.teams):
        old = previous.get(team)
        if old is not None:
            theta[2 + position] = float(warm_start["attack"][old])
            theta[2 + n_teams + position] = float(warm_start["defence"][old])
    theta[-1] = float(warm_start["rho"])
    return theta


def fit_dixon_coles(
    fh: FitHistory,
    decay_per_day: float,
    estimate_rho: bool = True,
    warm_start: dict[str, Any] | None = None,
) -> DixonColesFit:
    """Fit weighted attack, defence, home advantage, and optionally rho by Newton steps."""
    if not math.isfinite(decay_per_day) or decay_per_day < 0.0:
        raise DixonColesError("decay_per_day must be finite and non-negative")
    weights = np.exp(-decay_per_day * fh.age_days)
    theta = _initial_theta(fh, weights, warm_start)
    if not estimate_rho:
        theta[-1] = 0.0
    if _objective(theta, fh, weights, estimate_rho) == -math.inf:
        theta = _initial_theta(fh, weights, None)
    active = fh.parameter_count if estimate_rho else fh.parameter_count - 1
    objective = _objective(theta, fh, weights, estimate_rho)

    for _ in range(MAX_NEWTON_ITERATIONS):
        gradient, information = _gradient_and_information(theta, fh, weights, estimate_rho)
        step = np.zeros(fh.parameter_count)
        step[:active] = _newton_direction(
            information[:active, :active], gradient[:active]
        )
        if not np.isfinite(step).all():
            raise DixonColesError("Dixon-Coles Newton step is not finite")
        largest_step = float(np.abs(step).max())
        if largest_step <= FULL_STEP_THRESHOLD:
            candidate = theta + step
            candidate_objective = _objective(candidate, fh, weights, estimate_rho)
            if not math.isfinite(candidate_objective):
                raise DixonColesError("Dixon-Coles converged outside its valid region")
            theta, objective = candidate, candidate_objective
            if largest_step < NEWTON_TOLERANCE:
                return _build_fit(theta, fh, weights, decay_per_day)
            continue

        scale = 1.0
        for _ in range(MAX_STEP_HALVINGS):
            candidate = theta + scale * step
            candidate_objective = _objective(candidate, fh, weights, estimate_rho)
            if math.isfinite(candidate_objective) and candidate_objective >= objective:
                break
            scale *= 0.5
        else:
            raise DixonColesError("Dixon-Coles Newton step did not improve the objective")
        theta, objective = candidate, candidate_objective
    raise DixonColesError("Dixon-Coles fit did not converge")


def _build_fit(
    theta: np.ndarray, fh: FitHistory, weights: np.ndarray, decay_per_day: float
) -> DixonColesFit:
    n_teams = fh.team_count
    strengths = poisson.PoissonFit(
        teams=fh.teams,
        intercept=float(theta[0]),
        home_advantage=float(theta[1]),
        attack=theta[2 : 2 + n_teams].copy(),
        defence=theta[2 + n_teams : 2 + 2 * n_teams].copy(),
        training_rows=len(fh.home_goals),
    )
    return DixonColesFit(
        strengths=strengths,
        rho=float(theta[-1]),
        decay_per_day=decay_per_day,
        effective_weight=float(weights.sum()),
    )


def score_distribution(expected_home: float, expected_away: float, rho: float) -> np.ndarray:
    """Return the renormalized Dixon-Coles score matrix; rows are home goals."""
    matrix = np.outer(
        poisson._poisson_pmf(expected_home, SCORE_GRID_MAX_GOALS),
        poisson._poisson_pmf(expected_away, SCORE_GRID_MAX_GOALS),
    )
    tau = np.array(
        [
            [1.0 - expected_home * expected_away * rho, 1.0 + expected_home * rho],
            [1.0 + expected_away * rho, 1.0 - rho],
        ]
    )
    if not (np.isfinite(tau).all() and (tau > 0.0).all()):
        raise DixonColesError("Dixon-Coles correction is invalid for this fixture")
    matrix[:2, :2] *= tau
    mass = float(matrix.sum())
    if not mass >= poisson.MIN_SCORE_MATRIX_MASS:
        raise DixonColesError("Score matrix truncation lost too much probability")
    return matrix / mass


def build_timeline(matches: pd.DataFrame) -> pd.DataFrame:
    """Parse availability once and attach each row's UTC kickoff for recency ages."""
    timeline = matches.copy()
    timeline["result_available_at"] = pd.to_datetime(
        timeline["result_available_at"], format="ISO8601", utc=True, errors="raise"
    )
    timeline["_kickoff_utc"] = pd.to_datetime(
        [
            baseline._prediction_time(row).tz_convert("UTC")
            for row in matches.itertuples(index=False)
        ],
        utc=True,
    )
    return timeline


def walk_forward_targets(matches: pd.DataFrame, splits: pd.DataFrame) -> pd.DataFrame:
    """Return every eligible grid-season fixture ordered by kickoff prediction time."""
    roles = dict(splits.itertuples(index=False, name=None))
    development = tuple(season for season, role in roles.items() if role == "development")
    if development != GRID_SEASONS[len(TUNING_ONLY_SEASONS) :]:
        raise DixonColesError("Stage 5 grid seasons no longer match the development split")
    if any(roles.get(season) != "warmup_history" for season in TUNING_ONLY_SEASONS):
        raise DixonColesError("Stage 5 tuning-only seasons must be warm-up history")

    eligible = matches["model_eligible"].astype(bool)
    targets = matches.loc[eligible & matches["season"].isin(GRID_SEASONS)].copy()
    targets["_prediction_time"] = [
        baseline._prediction_time(row) for row in targets.itertuples(index=False)
    ]
    targets = targets.sort_values(["_prediction_time", "match_id"], kind="stable")
    frozen = baseline.development_targets(matches, splits)["match_id"].tolist()
    selected = targets.loc[targets["season"].isin(development), "match_id"].tolist()
    if selected != frozen:
        raise DixonColesError("Stage 5 development fixtures differ from the frozen set")
    return targets


@dataclass(frozen=True)
class CutoffContext:
    """Every declared fit for one available history."""

    history_rows: int
    latest_result_available_at: pd.Timestamp
    appearances: pd.Series
    fits: dict[tuple[float, bool], DixonColesFit]


def _context_from_history(
    history: pd.DataFrame,
    cutoff: pd.Timestamp,
    warm_starts: dict[tuple[float, bool], dict[str, Any]] | None,
) -> CutoffContext:
    if history.empty:
        raise DixonColesError("A walk-forward prediction has no prior history")
    latest = pd.to_datetime(
        history["result_available_at"], format="ISO8601", utc=True, errors="raise"
    ).max()
    if not latest < cutoff:
        raise DixonColesError("Dixon-Coles history crosses the strict time boundary")
    fh = build_fit_history(history)
    fits: dict[tuple[float, bool], DixonColesFit] = {}
    for decay in DECAY_GRID_PER_DAY:
        for estimate_rho in (True, False):
            key = (decay, estimate_rho)
            warm = None if warm_starts is None else warm_starts.get(key)
            fit = fit_dixon_coles(fh, decay, estimate_rho=estimate_rho, warm_start=warm)
            if warm_starts is not None:
                warm_starts[key] = fit.parameter_vector()
            fits[key] = fit
    return CutoffContext(
        history_rows=len(history),
        latest_result_available_at=latest,
        appearances=poisson._team_appearances(history),
        fits=fits,
    )


def fit_cutoff(timeline: pd.DataFrame, cutoff: pd.Timestamp) -> CutoffContext:
    """Cold-start every declared fit on results available strictly before `cutoff`."""
    history = evaluation_time.available_history(timeline, cutoff)
    return _context_from_history(history, cutoff, None)


def fit_walk_forward(
    timeline: pd.DataFrame, targets: pd.DataFrame
) -> dict[pd.Timestamp, CutoffContext]:
    """Fit each distinct available history once, in kickoff order, with warm starts."""
    contexts: dict[pd.Timestamp, CutoffContext] = {}
    warm_starts: dict[tuple[float, bool], dict[str, Any]] = {}
    previous_key: tuple[int, pd.Timestamp] | None = None
    previous_context: CutoffContext | None = None
    for cutoff in sorted(targets["_prediction_time"].unique()):
        cutoff = pd.Timestamp(cutoff)
        history = evaluation_time.available_history(timeline, cutoff)
        latest = pd.to_datetime(
            history["result_available_at"], format="ISO8601", utc=True, errors="raise"
        ).max()
        key = (len(history), latest)
        if previous_key is not None and key[0] < previous_key[0]:
            raise DixonColesError("Available history shrank as prediction time advanced")
        if key == previous_key and previous_context is not None:
            contexts[cutoff] = previous_context
            continue
        previous_context = _context_from_history(history, cutoff, warm_starts)
        previous_key = key
        contexts[cutoff] = previous_context
    return contexts


def build_grid_predictions(
    targets: pd.DataFrame, contexts: dict[pd.Timestamp, CutoffContext]
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for cutoff, fixtures in targets.groupby("_prediction_time", sort=True):
        context = contexts[cutoff]
        for match in fixtures.itertuples(index=False):
            for decay in DECAY_GRID_PER_DAY:
                fit = context.fits[(decay, True)]
                matrix = score_distribution(
                    *fit.expected_goals(match.home_team, match.away_team), fit.rho
                )
                p_home, p_draw, p_away = poisson.hda_probabilities(matrix)
                rows.append(
                    {
                        "match_id": match.match_id,
                        "season": match.season,
                        "decay_per_day": decay,
                        "p_home": p_home,
                        "p_draw": p_draw,
                        "p_away": p_away,
                        "actual_result": match.result,
                    }
                )
    grid = pd.DataFrame(rows)
    if len(grid) != len(targets) * len(DECAY_GRID_PER_DAY):
        raise DixonColesError("Stage 5 grid predictions are incomplete")
    return baseline.add_match_scores(grid)


def summarize_grid(grid_scored: pd.DataFrame, splits: pd.DataFrame) -> pd.DataFrame:
    roles = dict(splits.itertuples(index=False, name=None))
    grouped = (
        grid_scored.groupby(["season", "decay_per_day"], sort=True)
        .agg(
            matches=("log_loss", "size"),
            log_loss=("log_loss", "mean"),
            brier_score=("brier_score", "mean"),
        )
        .reset_index()
    )
    grouped["season_role"] = grouped["season"].map(roles)
    return grouped[GRID_METRIC_COLUMNS]


def select_decays(
    grid_scored: pd.DataFrame, targets: pd.DataFrame, timeline: pd.DataFrame
) -> pd.DataFrame:
    """Apply the nested chronological decay-selection rule to every development season."""
    availability = pd.to_datetime(
        timeline.set_index("match_id")["result_available_at"], utc=True
    )
    rows: list[dict[str, Any]] = []
    for position in range(len(TUNING_ONLY_SEASONS), len(GRID_SEASONS)):
        season = GRID_SEASONS[position]
        tuning_seasons = GRID_SEASONS[:position]
        first_prediction = targets.loc[targets["season"] == season, "_prediction_time"].min()
        tuning = grid_scored.loc[grid_scored["season"].isin(tuning_seasons)]
        if tuning.empty or pd.isna(first_prediction):
            raise DixonColesError(f"Decay selection for {season} has no tuning evidence")
        tuning_ids = tuning["match_id"].unique()
        if not availability.loc[tuning_ids].lt(first_prediction).all():
            raise DixonColesError(
                f"Decay tuning for {season} used a result unavailable at its first kickoff"
            )
        losses = tuning.groupby("decay_per_day", sort=True)["log_loss"].agg(["mean", "size"])
        if sorted(losses.index.tolist()) != sorted(DECAY_GRID_PER_DAY) or (
            losses["size"].nunique() != 1
        ):
            raise DixonColesError(f"Decay tuning grid for {season} is incomplete")
        selected = min(
            DECAY_GRID_PER_DAY, key=lambda decay: (float(losses.loc[decay, "mean"]), decay)
        )
        rows.append(
            {
                "target_season": season,
                "tuning_seasons": ";".join(tuning_seasons),
                "tuning_matches": int(losses["size"].iloc[0]),
                "selected_decay_per_day": selected,
                "selected_tuning_log_loss": float(losses.loc[selected, "mean"]),
                "no_decay_tuning_log_loss": float(losses.loc[0.0, "mean"]),
                "selected_at_grid_maximum": selected == max(DECAY_GRID_PER_DAY),
            }
        )
    return pd.DataFrame(rows, columns=SELECTION_COLUMNS)


def _prediction_row(
    match: Any,
    cutoff: pd.Timestamp,
    model: str,
    context: CutoffContext,
    fit: DixonColesFit,
) -> dict[str, Any]:
    expected_home, expected_away = fit.expected_goals(match.home_team, match.away_team)
    matrix = score_distribution(expected_home, expected_away, fit.rho)
    p_home, p_draw, p_away = poisson.hda_probabilities(matrix)
    home_goals = int(match.home_goals)
    away_goals = int(match.away_goals)
    if max(home_goals, away_goals) > SCORE_GRID_MAX_GOALS:
        raise DixonColesError("Observed score lies outside the score matrix")
    return {
        "match_id": match.match_id,
        "season": match.season,
        "prediction_time": cutoff.isoformat(),
        "model": model,
        "decay_per_day": fit.decay_per_day,
        "available_history_rows": context.history_rows,
        "training_rows_used": fit.strengths.training_rows,
        "effective_training_weight": fit.effective_weight,
        "latest_result_available_at": context.latest_result_available_at.isoformat(),
        "home_team": match.home_team,
        "away_team": match.away_team,
        "home_team_history_matches": int(context.appearances.get(match.home_team, 0)),
        "away_team_history_matches": int(context.appearances.get(match.away_team, 0)),
        "expected_home_goals": expected_home,
        "expected_away_goals": expected_away,
        "fitted_rho": fit.rho,
        "p_home": p_home,
        "p_draw": p_draw,
        "p_away": p_away,
        "p_score_0_0": float(matrix[0, 0]),
        "p_score_1_0": float(matrix[1, 0]),
        "p_score_0_1": float(matrix[0, 1]),
        "p_score_1_1": float(matrix[1, 1]),
        "p_observed_score": float(matrix[home_goals, away_goals]),
        "actual_home_goals": home_goals,
        "actual_away_goals": away_goals,
        "actual_result": match.result,
    }


def build_model_predictions(
    targets: pd.DataFrame,
    contexts: dict[pd.Timestamp, CutoffContext],
    selection: pd.DataFrame,
) -> pd.DataFrame:
    selected = dict(zip(selection["target_season"], selection["selected_decay_per_day"]))
    rows: list[dict[str, Any]] = []
    for cutoff, fixtures in targets.groupby("_prediction_time", sort=True):
        context = contexts[cutoff]
        for match in fixtures.itertuples(index=False):
            if match.season not in selected:
                continue
            decay = float(selected[match.season])
            for model, key in (
                (CANDIDATE_MODEL, (decay, True)),
                (DECAY_ONLY_MODEL, (decay, False)),
                (RHO_ONLY_MODEL, (0.0, True)),
            ):
                rows.append(_prediction_row(match, cutoff, model, context, context.fits[key]))
    predictions = pd.DataFrame(rows, columns=PREDICTION_COLUMNS)
    predictions["model"] = pd.Categorical(
        predictions["model"], categories=MODEL_ORDER, ordered=True
    )
    predictions = predictions.sort_values(
        ["prediction_time", "match_id", "model"], kind="stable"
    ).reset_index(drop=True)
    predictions["model"] = predictions["model"].astype("string")
    return predictions


def _validate_model_predictions(
    predictions: pd.DataFrame, development: pd.DataFrame, selection: pd.DataFrame
) -> None:
    if predictions.columns.tolist() != PREDICTION_COLUMNS:
        raise DixonColesError("Stage 5 prediction output schema changed")
    if predictions.duplicated(["match_id", "model"]).any():
        raise DixonColesError("Duplicate Stage 5 match/model predictions")
    expected_ids = set(development["match_id"])
    for model in MODEL_ORDER:
        selected = predictions.loc[predictions["model"] == model]
        if len(selected) != len(development) or set(selected["match_id"]) != expected_ids:
            raise DixonColesError(f"Stage 5 coverage is incomplete for {model}")
    if not set(predictions["season"]).issubset(set(GRID_SEASONS[len(TUNING_ONLY_SEASONS) :])):
        raise DixonColesError("Stage 5 predictions left the development split")

    probabilities = predictions[baseline.PROBABILITY_COLUMNS].to_numpy(dtype=float)
    if not (np.isfinite(probabilities).all() and ((probabilities > 0) & (probabilities < 1)).all()):
        raise DixonColesError("Stage 5 probabilities must be finite and inside (0, 1)")
    if not (np.abs(probabilities.sum(axis=1) - 1.0) < 1e-12).all():
        raise DixonColesError("Stage 5 probabilities do not sum to one")
    cells = predictions[["p_score_0_0", "p_score_1_0", "p_score_0_1", "p_score_1_1"]]
    if not (cells.gt(0.0).all(axis=None) and predictions["p_observed_score"].gt(0.0).all()):
        raise DixonColesError("Stage 5 score probabilities must be positive")

    selected = dict(zip(selection["target_season"], selection["selected_decay_per_day"]))
    season_decay = predictions["season"].map(selected).astype(float)
    tuned = predictions["model"].isin([CANDIDATE_MODEL, DECAY_ONLY_MODEL])
    if not predictions.loc[tuned, "decay_per_day"].eq(season_decay[tuned]).all():
        raise DixonColesError("A tuned Stage 5 model did not use its selected decay")
    if not predictions.loc[predictions["model"] == RHO_ONLY_MODEL, "decay_per_day"].eq(0.0).all():
        raise DixonColesError("The no-decay ablation used a decay")
    if not predictions.loc[predictions["model"] == DECAY_ONLY_MODEL, "fitted_rho"].eq(0.0).all():
        raise DixonColesError("The decay-only ablation estimated rho")
    prediction_times = pd.to_datetime(predictions["prediction_time"], utc=True, errors="raise")
    latest_results = pd.to_datetime(
        predictions["latest_result_available_at"], utc=True, errors="raise"
    )
    if not latest_results.lt(prediction_times).all():
        raise DixonColesError("Stage 5 history crosses the strict time boundary")


def run_evaluation(matches: pd.DataFrame, splits: pd.DataFrame) -> dict[str, pd.DataFrame]:
    timeline = build_timeline(matches)
    targets = walk_forward_targets(matches, splits)
    contexts = fit_walk_forward(timeline, targets)
    grid_scored = build_grid_predictions(targets, contexts)
    grid_metrics = summarize_grid(grid_scored, splits)
    selection = select_decays(grid_scored, targets, timeline)
    development = baseline.development_targets(matches, splits)
    predictions = build_model_predictions(targets, contexts, selection)
    _validate_model_predictions(predictions, development, selection)
    metrics = baseline.score_predictions(predictions, MODEL_ORDER)
    return {
        "predictions": predictions,
        "metrics": metrics,
        "grid_metrics": grid_metrics,
        "selection": selection,
    }


def load_reference_outputs(predictions: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Load freshly regenerated Stage 3 and Stage 4 outputs for the same fixtures."""
    reference = pd.read_csv(
        poisson.PREDICTIONS_OUTPUT,
        dtype={
            "match_id": "string",
            "season": "string",
            "prediction_time": "string",
            "model": "string",
            "actual_result": "string",
        },
    )
    candidate = predictions.loc[predictions["model"] == CANDIDATE_MODEL]
    expected = candidate.set_index("match_id")["prediction_time"].astype(str)
    observed = reference.set_index("match_id")["prediction_time"].astype(str)
    if (
        len(reference) != len(candidate)
        or observed.index.duplicated().any()
        or not observed.reindex(expected.index).eq(expected).all()
    ):
        raise DixonColesError("Stage 4 reference predictions do not match Stage 5 fixtures")
    return {
        "poisson_predictions": reference,
        "poisson_metrics": pd.read_csv(poisson.METRICS_OUTPUT, dtype={"season": "string"}),
        "baseline_metrics": pd.read_csv(baseline.METRICS_OUTPUT, dtype={"season": "string"}),
    }


def _half_life(decay: float) -> str:
    return "none" if decay == 0.0 else f"{math.log(2.0) / decay:.0f} days"


def _paired(candidate: pd.DataFrame, reference: pd.DataFrame) -> pd.DataFrame:
    merged = candidate[["match_id", "season", "log_loss"]].merge(
        reference[["match_id", "log_loss"]],
        on="match_id",
        suffixes=("_candidate", "_reference"),
        validate="one_to_one",
    )
    if len(merged) != len(candidate):
        raise DixonColesError("Paired comparison lost fixtures")
    merged["difference"] = merged["log_loss_candidate"] - merged["log_loss_reference"]
    return merged


def _interval(difference: pd.Series) -> tuple[float, float, float]:
    mean = float(difference.mean())
    standard_error = float(difference.std(ddof=1)) / math.sqrt(len(difference))
    return mean, mean - 1.96 * standard_error, mean + 1.96 * standard_error


def generate_report(outputs: dict[str, pd.DataFrame], reference: dict[str, pd.DataFrame]) -> str:
    predictions = outputs["predictions"]
    metrics = outputs["metrics"]
    selection = outputs["selection"]
    grid_metrics = outputs["grid_metrics"]
    poisson_predictions = reference["poisson_predictions"]
    all_metrics = pd.concat(
        [reference["baseline_metrics"], reference["poisson_metrics"], metrics],
        ignore_index=True,
    )
    overall = all_metrics.loc[all_metrics["season"] == "ALL"].set_index("model")

    scored = baseline.add_match_scores(predictions)
    reference_scored = baseline.add_match_scores(poisson_predictions)
    by_model = {model: scored.loc[scored["model"] == model] for model in MODEL_ORDER}
    paired = {model: _paired(by_model[model], reference_scored) for model in MODEL_ORDER}

    candidate_loss = float(overall.loc[CANDIDATE_MODEL, "log_loss"])
    candidate_brier = float(overall.loc[CANDIDATE_MODEL, "brier_score"])
    reference_loss = float(overall.loc[REFERENCE_MODEL, "log_loss"])
    reference_brier = float(overall.loc[REFERENCE_MODEL, "brier_score"])
    mean, low, high = _interval(paired[CANDIDATE_MODEL]["difference"])
    beats = candidate_loss < reference_loss and candidate_brier < reference_brier
    if beats:
        verdict = [
            f"**GO.** `{CANDIDATE_MODEL}` beats `{REFERENCE_MODEL}` on development log loss",
            f"({candidate_loss:.6f} vs {reference_loss:.6f}) and Brier score",
            f"({candidate_brier:.6f} vs {reference_brier:.6f}).",
        ]
    else:
        verdict = [
            f"**CHARACTERIZED.** `{CANDIDATE_MODEL}` does not beat `{REFERENCE_MODEL}` on",
            f"both development log loss ({candidate_loss:.6f} vs {reference_loss:.6f}) and",
            f"Brier score ({candidate_brier:.6f} vs {reference_brier:.6f}).",
        ]
    decay_only = float(paired[DECAY_ONLY_MODEL]["difference"].mean())
    rho_only = float(paired[RHO_ONLY_MODEL]["difference"].mean())
    decay_only_loss = float(overall.loc[DECAY_ONLY_MODEL, "log_loss"])
    decay_only_brier = float(overall.loc[DECAY_ONLY_MODEL, "brier_score"])
    increment_mean, increment_low, increment_high = _interval(
        _paired(by_model[CANDIDATE_MODEL], by_model[DECAY_ONLY_MODEL])["difference"]
    )
    increment = [
        f"`{DECAY_ONLY_MODEL}` scores {decay_only_loss:.6f} log loss and {decay_only_brier:.6f}",
        f"Brier versus the candidate's {candidate_loss:.6f} and {candidate_brier:.6f}; the",
        f"candidate-minus-`{DECAY_ONLY_MODEL}` paired log-loss difference is",
        f"{increment_mean:+.6f} ([{increment_low:+.6f}, {increment_high:+.6f}]).",
    ]
    if candidate_loss < decay_only_loss and candidate_brier < decay_only_brier:
        complexity = [
            "The low-score correction adds H/D/A value on top of recency decay:",
            *increment,
        ]
    else:
        complexity = [
            "The low-score correction is not justified on H/D/A metrics:",
            *increment,
            "The Stage 5 gain comes from recency decay. The candidate was declared before",
            "results and is not replaced here; the Stage 8 freeze weighs this evidence.",
        ]
    verdict += [
        "",
        f"Mean paired log-loss difference against `{REFERENCE_MODEL}`: {mean:+.6f}",
        f"(approximate 95% interval [{low:+.6f}, {high:+.6f}]; the interval "
        + ("excludes" if high < 0.0 or low > 0.0 else "includes")
        + " zero).",
        f"Ablations attribute the change: decay alone {decay_only:+.6f}, low-score",
        f"correction alone {rho_only:+.6f}, both together {mean:+.6f}.",
        "",
        *complexity,
        "",
        "Decay was selected by the nested chronological rule; no development season",
        "tuned itself, and no final-holdout result or market probability was used.",
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
    paired_rows = []
    for model in MODEL_ORDER:
        merged = paired[model]
        groups = [("ALL", merged)] + [
            (season, merged.loc[merged["season"] == season])
            for season in sorted(merged["season"].unique())
        ]
        for label, group in groups:
            if model != CANDIDATE_MODEL and label != "ALL":
                continue
            group_mean, group_low, group_high = _interval(group["difference"])
            paired_rows.append(
                [
                    f"`{model}`",
                    label,
                    len(group),
                    f"{group_mean:+.6f}",
                    f"[{group_low:+.6f}, {group_high:+.6f}]",
                ]
            )

    selection_rows = [
        [
            row.target_season,
            row.tuning_seasons.replace(";", ", "),
            int(row.tuning_matches),
            f"{row.selected_decay_per_day:g}",
            _half_life(float(row.selected_decay_per_day)),
            f"{row.selected_tuning_log_loss:.6f}",
            f"{row.no_decay_tuning_log_loss:.6f}",
            "yes" if bool(row.selected_at_grid_maximum) else "no",
        ]
        for row in selection.itertuples(index=False)
    ]
    grid_pivot = grid_metrics.pivot(index="season", columns="decay_per_day", values="log_loss")
    grid_rows = [
        [season, *[f"{float(grid_pivot.loc[season, decay]):.4f}" for decay in DECAY_GRID_PER_DAY]]
        for season in grid_pivot.index
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

    candidate = by_model[CANDIDATE_MODEL]
    home_goals = candidate["actual_home_goals"]
    away_goals = candidate["actual_away_goals"]
    lam = poisson_predictions.set_index("match_id").loc[
        candidate["match_id"], "expected_home_goals"
    ].to_numpy(dtype=float)
    mu = poisson_predictions.set_index("match_id").loc[
        candidate["match_id"], "expected_away_goals"
    ].to_numpy(dtype=float)
    cell_rows = []
    for label, home, away in LOW_SCORE_CELLS:
        independent = np.exp(-(lam + mu)) * lam**home * mu**away / (
            math.factorial(home) * math.factorial(away)
        )
        cell_rows.append(
            [
                label,
                f"{float((home_goals.eq(home) & away_goals.eq(away)).mean()):.4f}",
                f"{float(independent.mean()):.4f}",
                f"{float(candidate[f'p_score_{home}_{away}'].mean()):.4f}",
            ]
        )
    cell_rows.append(
        [
            "draw (any score)",
            f"{float(candidate['actual_result'].eq('D').mean()):.4f}",
            f"{float(poisson_predictions['p_draw'].mean()):.4f}",
            f"{float(candidate['p_draw'].mean()):.4f}",
        ]
    )
    rho_values = candidate["fitted_rho"]
    scoreline_rows = [
        [
            f"`{name}`",
            f"{float(frame['p_observed_score'].map(lambda value: -math.log(value)).mean()):.6f}",
        ]
        for name, frame in [(REFERENCE_MODEL, poisson_predictions)]
        + [(model, by_model[model]) for model in (DECAY_ONLY_MODEL, RHO_ONLY_MODEL, CANDIDATE_MODEL)]
    ]

    merged = paired[CANDIDATE_MODEL].merge(
        candidate[["match_id", "home_team_history_matches", "away_team_history_matches"]],
        on="match_id",
        validate="one_to_one",
    )
    merged["bucket"] = [
        poisson._history_bucket(int(min(home, away)))
        for home, away in zip(
            merged["home_team_history_matches"], merged["away_team_history_matches"]
        )
    ]
    bucket_rows = []
    for bucket in (
        poisson._history_bucket(0),
        poisson._history_bucket(1),
        poisson._history_bucket(poisson.FULL_SEASON_MATCHES),
    ):
        group = merged.loc[merged["bucket"] == bucket]
        if group.empty:
            bucket_rows.append([bucket, 0, "-", "-", "-"])
            continue
        bucket_rows.append(
            [
                bucket,
                len(group),
                f"{float(group['log_loss_reference'].mean()):.6f}",
                f"{float(group['log_loss_candidate'].mean()):.6f}",
                f"{float(group['difference'].mean()):+.6f}",
            ]
        )
    worst = by_model[CANDIDATE_MODEL].sort_values(
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

    table = baseline._markdown_table
    lines = [
        "# Time-decayed Dixon-Coles evaluation",
        "",
        "## Verdict",
        "",
        *verdict,
        "",
        "## Overall development results",
        "",
        *table(["Model", "Matches", "Log loss", "Brier score"], overall_rows),
        "",
        "Lower is better. All models use the same 1,413 development fixtures and",
        "kickoff prediction times. Aggregates are computed before per-match values",
        "are rounded for publication.",
        "",
        f"## Paired log-loss difference against `{REFERENCE_MODEL}`",
        "",
        *table(["Model", "Season", "Matches", "Mean difference", "Approx. 95% interval"], paired_rows),
        "",
        "Negative differences favour the Stage 5 model. Intervals use a normal",
        "approximation that treats matches as independent and are descriptive.",
        "",
        "## Nested chronological decay selection",
        "",
        *table(
            [
                "Target season",
                "Tuning seasons",
                "Tuning matches",
                "Selected decay/day",
                "Half-life",
                "Tuning log loss",
                "No-decay tuning log loss",
                "At grid maximum",
            ],
            selection_rows,
        ),
        "",
        "Each target season uses the decay with the lowest walk-forward log loss over",
        "earlier grid seasons only. Ties select the smaller decay.",
        "",
        "## Walk-forward grid by season (descriptive)",
        "",
        *table(["Season", *[f"{decay:g}" for decay in DECAY_GRID_PER_DAY]], grid_rows),
        "",
        "H/D/A log loss of the Dixon-Coles fit for each declared decay. 2019-20 and",
        "2020-21 are tuning-only warm-up seasons. This table never replaces the",
        "nested choice above.",
        "",
        "## Results by season",
        "",
        *table(["Season", "Model", "Matches", "Log loss", "Brier score"], season_rows),
        "",
        "## Low-score calibration",
        "",
        *table(
            ["Score", "Observed frequency", f"Mean `{REFERENCE_MODEL}`", f"Mean `{CANDIDATE_MODEL}`"],
            cell_rows,
        ),
        "",
        f"Fitted `rho` for `{CANDIDATE_MODEL}` predictions: mean {float(rho_values.mean()):.4f},",
        f"minimum {float(rho_values.min()):.4f}, maximum {float(rho_values.max()):.4f}.",
        "",
        "## Scoreline diagnostic",
        "",
        *table(["Model", "Mean negative log probability of exact score"], scoreline_rows),
        "",
        "Descriptive only; primary and secondary metrics remain H/D/A log loss and Brier.",
        "",
        "## Cold-start characterization",
        "",
        *table(
            [
                "Fewest prior matches",
                "Matches",
                f"`{REFERENCE_MODEL}` log loss",
                f"`{CANDIDATE_MODEL}` log loss",
                "Difference",
            ],
            bucket_rows,
        ),
        "",
        "## Largest single-match candidate losses",
        "",
        *table(
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
        "Sparse-history failures remain evidence for the Stage 6 promoted-team prior.",
        "",
        "## Model specification",
        "",
        "The declared specification is in `MODEL_DESIGN.md`: Stage 4 rates and team",
        "penalty, jointly estimated Dixon-Coles `rho`, exponential recency weights",
        "anchored at the latest kickoff in each available history, and the fixed decay",
        "grid " + ", ".join(f"{decay:g}" for decay in DECAY_GRID_PER_DAY) + " per day.",
        "The selection rule is in `EVALUATION_PROTOCOL.md`.",
        "",
        "## Frozen evaluation boundary",
        "",
        "- Tuning-only walk-forward seasons: 2019-20 and 2020-21.",
        "- Development walk-forward: 2021-22 through 2024-25.",
        "- Final holdout: 2025-26, still sealed and absent from fitting, tuning, and metrics.",
        "- Current season: 2026-27, live-only and absent from development metrics.",
        "- Each fit uses only `evaluation_time.available_history` at the prediction time.",
        "- The isolated market benchmark table is not loaded by the evaluator.",
        "",
        "## Next roadmap gate",
        "",
        "Stage 6 adds the training-only dynamic promoted-team prior under the same split,",
        "metrics, and chronological tuning rules. Do not open the 2025-26 holdout.",
        "",
    ]
    return "\n".join(lines)


def write_outputs(outputs: dict[str, pd.DataFrame], reference: dict[str, pd.DataFrame]) -> None:
    PREDICTIONS_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    outputs["predictions"].to_csv(
        PREDICTIONS_OUTPUT, index=False, float_format=poisson.PUBLISHED_FLOAT_FORMAT
    )
    outputs["metrics"].to_csv(METRICS_OUTPUT, index=False, float_format="%.12f")
    outputs["grid_metrics"].to_csv(GRID_METRICS_OUTPUT, index=False, float_format="%.12f")
    outputs["selection"].to_csv(SELECTION_OUTPUT, index=False, float_format="%.12f")
    REPORT_OUTPUT.write_text(generate_report(outputs, reference), encoding="utf-8")


def main() -> int:
    poisson_status = poisson.main()
    if poisson_status != 0:
        return poisson_status
    splits = baseline.load_split_config()
    matches = baseline.load_matches()
    outputs = run_evaluation(matches, splits)
    reference = load_reference_outputs(outputs["predictions"])
    write_outputs(outputs, reference)
    print(
        "Dixon-Coles evaluation complete: "
        f"{outputs['predictions']['match_id'].nunique()} development matches, "
        f"{len(MODEL_ORDER)} Stage 5 models."
    )
    print(f"Report: {REPORT_OUTPUT}")
    print("Final holdout: SEALED (2025-26)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
