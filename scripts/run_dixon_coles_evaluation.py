#!/usr/bin/env python3
"""Run the Stage 5 leakage-safe time-decayed Dixon-Coles walk-forward evaluation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

import run_poisson_evaluation as poisson


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
    matrix = np.outer(poisson._poisson_pmf(expected_home), poisson._poisson_pmf(expected_away))
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
