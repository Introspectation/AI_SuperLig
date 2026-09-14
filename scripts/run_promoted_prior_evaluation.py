#!/usr/bin/env python3
"""Run the Stage 6 leakage-safe dynamic promoted-team prior walk-forward evaluation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from numpy.polynomial.hermite_e import hermegauss

import evaluation_time
import run_baseline_evaluation as baseline
import run_dixon_coles_evaluation as dc
import run_poisson_evaluation as poisson


ROOT = Path(__file__).resolve().parents[1]
PREDICTIONS_OUTPUT = ROOT / "reports" / "promoted_prior_predictions.csv"
METRICS_OUTPUT = ROOT / "reports" / "promoted_prior_metrics.csv"
GRID_METRICS_OUTPUT = ROOT / "reports" / "promoted_prior_grid_metrics.csv"
SELECTION_OUTPUT = ROOT / "reports" / "promoted_prior_selection.csv"
OFFSETS_OUTPUT = ROOT / "reports" / "promoted_prior_offsets.csv"
REPORT_OUTPUT = ROOT / "reports" / "PROMOTED_PRIOR_REPORT.md"

CANDIDATE_MODEL = "dixon_coles_promoted_prior"
POINT_MODEL = "dixon_coles_promoted_point"
POISSON_MODEL = "poisson_decay_promoted_prior"
MODEL_ORDER = [CANDIDATE_MODEL, POINT_MODEL, POISSON_MODEL]
# Model name -> (estimate_rho, propagate_uncertainty).
MODEL_SPECS = {
    CANDIDATE_MODEL: (True, True),
    POINT_MODEL: (True, False),
    POISSON_MODEL: (False, True),
}
BASE_REFERENCE = {True: dc.CANDIDATE_MODEL, False: dc.DECAY_ONLY_MODEL}
GATE_REFERENCE = dc.CANDIDATE_MODEL
# Declared in MODEL_DESIGN.md before any Stage 6 metric was computed.
K_GRID = (0, 4, 8, 16, 32, 64)
PRIOR_START_SEASON = "2018-19"
_NODES, _WEIGHTS = hermegauss(5)
HERMITE_NODES = tuple(float(node) for node in _NODES)
HERMITE_WEIGHTS = tuple(float(weight) for weight in _WEIGHTS / _WEIGHTS.sum())
PREDICTION_COLUMNS = [
    "match_id",
    "season",
    "prediction_time",
    "model",
    "decay_per_day",
    "prior_k",
    "available_history_rows",
    "latest_result_available_at",
    "home_team",
    "away_team",
    "home_promoted",
    "away_promoted",
    "home_season_matches",
    "away_season_matches",
    "home_prior_weight",
    "away_prior_weight",
    "expected_home_goals",
    "expected_away_goals",
    "home_log_rate_variance",
    "away_log_rate_variance",
    "fitted_rho",
    *baseline.PROBABILITY_COLUMNS,
    "p_observed_score",
    "actual_home_goals",
    "actual_away_goals",
    "actual_result",
]
GRID_METRIC_COLUMNS = [
    "model",
    "season",
    "decay_per_day",
    "prior_k",
    "matches",
    "log_loss",
    "brier_score",
    "promoted_matches",
    "promoted_log_loss",
]
SELECTION_COLUMNS = [
    "model",
    "target_season",
    "decay_per_day",
    "tuning_seasons",
    "tuning_matches",
    "selected_k",
    "selected_tuning_log_loss",
    "no_prior_tuning_log_loss",
    "selected_at_grid_maximum",
]
OFFSET_COLUMNS = [
    "season",
    "decay_per_day",
    "estimate_rho",
    "club",
    "attack_offset",
    "defence_offset",
]


class PromotedPriorError(RuntimeError):
    """The Stage 6 model or its evaluation contract was violated."""


def season_clubs(matches: pd.DataFrame) -> dict[str, frozenset[str]]:
    """Clubs with at least one eligible match in each season."""
    eligible = matches.loc[matches["model_eligible"].astype(bool)]
    return {
        season: frozenset(pd.concat([group["home_team"], group["away_team"]]).tolist())
        for season, group in eligible.groupby("season", sort=False)
    }


def previous_season(season: str, season_order: list[str]) -> str:
    position = season_order.index(season)
    if position == 0:
        raise PromotedPriorError(f"{season} has no previous season for promoted status")
    return season_order[position - 1]


def is_promoted(
    club: str,
    season: str,
    clubs_by_season: dict[str, frozenset[str]],
    season_order: list[str],
) -> bool:
    """A club is promoted when it had no eligible match in the previous season."""
    return club not in clubs_by_season.get(previous_season(season, season_order), frozenset())


def blend(
    observed: float, prior: float, prior_variance: float, n: int, k: int
) -> tuple[float, float, float]:
    """Return blended strength, evidence weight, and remaining prior variance."""
    if n < 0 or k < 0:
        raise PromotedPriorError("n and k must be non-negative")
    if k == 0:
        return observed, 1.0, 0.0
    weight = n / (n + k)
    return weight * observed + (1.0 - weight) * prior, weight, (1.0 - weight) * prior_variance


def mixed_score_distribution(
    log_home: float, log_away: float, var_home: float, var_away: float, rho: float
) -> np.ndarray:
    """Average Dixon-Coles score matrices over normal log-rate uncertainty."""
    if var_home < 0.0 or var_away < 0.0:
        raise PromotedPriorError("Log-rate variances must be non-negative")
    if var_home == 0.0 and var_away == 0.0:
        return dc.score_distribution(math.exp(log_home), math.exp(log_away), rho)

    def points(centre: float, variance: float) -> list[tuple[float, float]]:
        if variance == 0.0:
            return [(centre, 1.0)]
        scale = math.sqrt(variance)
        return [
            (centre + node * scale, weight)
            for node, weight in zip(HERMITE_NODES, HERMITE_WEIGHTS)
        ]

    home_nodes = [(math.exp(value), weight) for value, weight in points(log_home, var_home)]
    away_nodes = [(math.exp(value), weight) for value, weight in points(log_away, var_away)]
    home_pmfs = [poisson._poisson_pmf(rate, dc.SCORE_GRID_MAX_GOALS) for rate, _ in home_nodes]
    away_pmfs = [poisson._poisson_pmf(rate, dc.SCORE_GRID_MAX_GOALS) for rate, _ in away_nodes]
    matrix = np.zeros((dc.SCORE_GRID_MAX_GOALS + 1, dc.SCORE_GRID_MAX_GOALS + 1))
    for (home_rate, home_weight), home_pmf in zip(home_nodes, home_pmfs):
        for (away_rate, away_weight), away_pmf in zip(away_nodes, away_pmfs):
            matrix += (home_weight * away_weight) * _node_matrix(
                home_pmf, away_pmf, home_rate, away_rate, rho
            )
    return matrix / float(matrix.sum())


def _node_matrix(
    home_pmf: np.ndarray,
    away_pmf: np.ndarray,
    expected_home: float,
    expected_away: float,
    rho: float,
) -> np.ndarray:
    """Dixon-Coles matrix from precomputed marginals; mirrors dc.score_distribution."""
    matrix = np.outer(home_pmf, away_pmf)
    tau = np.array(
        [
            [1.0 - expected_home * expected_away * rho, 1.0 + expected_home * rho],
            [1.0 + expected_away * rho, 1.0 - rho],
        ]
    )
    if not (np.isfinite(tau).all() and (tau > 0.0).all()):
        raise PromotedPriorError("Dixon-Coles correction is invalid at an uncertainty node")
    matrix[:2, :2] *= tau
    mass = float(matrix.sum())
    if not mass >= poisson.MIN_SCORE_MATRIX_MASS:
        raise PromotedPriorError("Score matrix truncation lost too much probability")
    return matrix / mass


@dataclass(frozen=True)
class PriorOffsets:
    """Promoted-club strengths relative to the previous-season reference level."""

    season: str
    decay_per_day: float
    estimate_rho: bool
    clubs: tuple[str, ...]
    attack: np.ndarray
    defence: np.ndarray
    latest_result_available_at: pd.Timestamp


def _reference_level(
    fit: dc.DixonColesFit, clubs: frozenset[str]
) -> tuple[float, float]:
    missing = sorted(club for club in clubs if club not in fit.strengths.teams)
    if missing:
        raise PromotedPriorError(f"Reference clubs are missing from the base fit: {missing}")
    strengths = [fit.strengths.team_strength(club) for club in sorted(clubs)]
    return (
        float(np.mean([attack for attack, _ in strengths])),
        float(np.mean([defence for _, defence in strengths])),
    )


def season_end_offsets(
    timeline: pd.DataFrame,
    season: str,
    decay_per_day: float,
    estimate_rho: bool,
    clubs_by_season: dict[str, frozenset[str]],
    season_order: list[str],
) -> PriorOffsets:
    """Refit the base on all results available at the end of `season`."""
    eligible = timeline["model_eligible"].astype(bool)
    season_rows = timeline.loc[eligible & (timeline["season"] == season)]
    if season_rows.empty:
        raise PromotedPriorError(f"{season} has no eligible results for prior offsets")
    cutoff = season_rows["result_available_at"].max() + pd.Timedelta(seconds=1)
    history = evaluation_time.available_history(timeline, cutoff)
    later = season_order[season_order.index(season) + 1 :]
    if history["season"].isin(later).any():
        raise PromotedPriorError("End-of-season history reached a later season")
    fit = dc.fit_dixon_coles(
        dc.build_fit_history(history), decay_per_day, estimate_rho=estimate_rho
    )
    previous = previous_season(season, season_order)
    reference_attack, reference_defence = _reference_level(fit, clubs_by_season[previous])
    promoted = sorted(clubs_by_season[season] - clubs_by_season[previous])
    strengths = [fit.strengths.team_strength(club) for club in promoted]
    return PriorOffsets(
        season=season,
        decay_per_day=decay_per_day,
        estimate_rho=estimate_rho,
        clubs=tuple(promoted),
        attack=np.array([attack - reference_attack for attack, _ in strengths]),
        defence=np.array([defence - reference_defence for _, defence in strengths]),
        latest_result_available_at=pd.Timestamp(history["result_available_at"].max()),
    )


@dataclass(frozen=True)
class Prior:
    attack_offset: float
    defence_offset: float
    attack_variance: float
    defence_variance: float
    offset_count: int
    source_seasons: tuple[str, ...]


def build_prior(
    offsets_by_season: dict[str, PriorOffsets], target_season: str, season_order: list[str]
) -> Prior:
    """Pool offsets from completed seasons between 2018-19 and the season before target."""
    start = season_order.index(PRIOR_START_SEASON)
    end = season_order.index(target_season)
    sources = tuple(season_order[start:end])
    if not sources:
        raise PromotedPriorError(f"No completed prior seasons precede {target_season}")
    attack = np.concatenate([offsets_by_season[season].attack for season in sources])
    defence = np.concatenate([offsets_by_season[season].defence for season in sources])
    if len(attack) < 2:
        raise PromotedPriorError(f"Prior for {target_season} needs at least two offsets")
    return Prior(
        attack_offset=float(attack.mean()),
        defence_offset=float(defence.mean()),
        attack_variance=float(attack.var(ddof=1)),
        defence_variance=float(defence.var(ddof=1)),
        offset_count=len(attack),
        source_seasons=sources,
    )


def _club_terms(
    club: str,
    season: str,
    k: int,
    context: dc.CutoffContext,
    fit: dc.DixonColesFit,
    reference: tuple[float, float],
    prior: Prior,
    clubs_by_season: dict[str, frozenset[str]],
    season_order: list[str],
) -> dict[str, Any]:
    attack, defence = fit.strengths.team_strength(club)
    promoted = is_promoted(club, season, clubs_by_season, season_order)
    n = int(context.season_appearances.get((season, club), 0))
    if not promoted:
        return {
            "promoted": False,
            "n": n,
            "weight": 1.0,
            "attack": attack,
            "defence": defence,
            "attack_variance": 0.0,
            "defence_variance": 0.0,
        }
    attack, weight, attack_variance = blend(
        attack, reference[0] + prior.attack_offset, prior.attack_variance, n, k
    )
    defence, _, defence_variance = blend(
        defence, reference[1] + prior.defence_offset, prior.defence_variance, n, k
    )
    return {
        "promoted": True,
        "n": n,
        "weight": weight,
        "attack": attack,
        "defence": defence,
        "attack_variance": attack_variance,
        "defence_variance": defence_variance,
    }


def _prediction_row(
    match: Any,
    cutoff: pd.Timestamp,
    model: str,
    k: int,
    context: dc.CutoffContext,
    fit: dc.DixonColesFit,
    reference: tuple[float, float],
    prior: Prior,
    clubs_by_season: dict[str, frozenset[str]],
    season_order: list[str],
    matrix_cache: dict[tuple[float, float, float, float], np.ndarray],
) -> dict[str, Any]:
    _, uncertainty = MODEL_SPECS[model]
    if match.home_team == match.away_team:
        raise PromotedPriorError("A fixture needs two different teams")
    home = _club_terms(
        match.home_team, match.season, k, context, fit, reference, prior,
        clubs_by_season, season_order,
    )
    away = _club_terms(
        match.away_team, match.season, k, context, fit, reference, prior,
        clubs_by_season, season_order,
    )
    strengths = fit.strengths
    log_home = strengths.intercept + strengths.home_advantage + home["attack"] - away["defence"]
    log_away = strengths.intercept + away["attack"] - home["defence"]
    var_home = home["attack_variance"] + away["defence_variance"] if uncertainty else 0.0
    var_away = away["attack_variance"] + home["defence_variance"] if uncertainty else 0.0
    cache_key = (log_home, log_away, var_home, var_away)
    matrix = matrix_cache.get(cache_key)
    if matrix is None:
        matrix = mixed_score_distribution(log_home, log_away, var_home, var_away, fit.rho)
        matrix_cache[cache_key] = matrix
    p_home, p_draw, p_away = poisson.hda_probabilities(matrix)
    home_goals = int(match.home_goals)
    away_goals = int(match.away_goals)
    if max(home_goals, away_goals) > dc.SCORE_GRID_MAX_GOALS:
        raise PromotedPriorError("Observed score lies outside the score matrix")
    return {
        "match_id": match.match_id,
        "season": match.season,
        "prediction_time": cutoff.isoformat(),
        "model": model,
        "decay_per_day": fit.decay_per_day,
        "prior_k": k,
        "available_history_rows": context.history_rows,
        "latest_result_available_at": context.latest_result_available_at.isoformat(),
        "home_team": match.home_team,
        "away_team": match.away_team,
        "home_promoted": home["promoted"],
        "away_promoted": away["promoted"],
        "home_season_matches": home["n"],
        "away_season_matches": away["n"],
        "home_prior_weight": home["weight"],
        "away_prior_weight": away["weight"],
        "expected_home_goals": math.exp(log_home),
        "expected_away_goals": math.exp(log_away),
        "home_log_rate_variance": var_home,
        "away_log_rate_variance": var_away,
        "fitted_rho": fit.rho,
        "p_home": p_home,
        "p_draw": p_draw,
        "p_away": p_away,
        "p_observed_score": float(matrix[home_goals, away_goals]),
        "actual_home_goals": home_goals,
        "actual_away_goals": away_goals,
        "actual_result": match.result,
    }


def build_offsets(
    timeline: pd.DataFrame,
    decays: list[float],
    clubs_by_season: dict[str, frozenset[str]],
    season_order: list[str],
) -> dict[tuple[str, float, bool], PriorOffsets]:
    last_source = season_order.index(dc.GRID_SEASONS[-1])
    seasons = season_order[season_order.index(PRIOR_START_SEASON) : last_source]
    return {
        (season, decay, estimate_rho): season_end_offsets(
            timeline, season, decay, estimate_rho, clubs_by_season, season_order
        )
        for season in seasons
        for decay in decays
        for estimate_rho in (True, False)
    }


def build_grid(
    state: dc.Stage5State,
    offsets: dict[tuple[str, float, bool], PriorOffsets],
    clubs_by_season: dict[str, frozenset[str]],
    season_order: list[str],
) -> pd.DataFrame:
    decays = sorted({float(decay) for decay in state.selection["selected_decay_per_day"]})
    priors: dict[tuple[str, float, bool], Prior] = {}
    for season in dc.GRID_SEASONS:
        first_prediction = state.targets.loc[
            state.targets["season"] == season, "_prediction_time"
        ].min()
        for decay in decays:
            for estimate_rho in (True, False):
                by_season = {
                    source: offsets[(source, decay, estimate_rho)]
                    for source in season_order[
                        season_order.index(PRIOR_START_SEASON) : season_order.index(season)
                    ]
                }
                if any(
                    not item.latest_result_available_at < first_prediction
                    for item in by_season.values()
                ):
                    raise PromotedPriorError(
                        f"Prior offsets for {season} used a result unavailable at its first kickoff"
                    )
                priors[(season, decay, estimate_rho)] = build_prior(
                    by_season, season, season_order
                )

    rows: list[dict[str, Any]] = []
    for cutoff, fixtures in state.targets.groupby("_prediction_time", sort=True):
        context = state.contexts[cutoff]
        for decay in decays:
            for estimate_rho in (True, False):
                fit = context.fits[(decay, estimate_rho)]
                references: dict[str, tuple[float, float]] = {}
                for match in fixtures.itertuples(index=False):
                    season = match.season
                    if season not in references:
                        references[season] = _reference_level(
                            fit, clubs_by_season[previous_season(season, season_order)]
                        )
                    prior = priors[(season, decay, estimate_rho)]
                    matrix_cache: dict[tuple[float, float, float, float], np.ndarray] = {}
                    for model, (model_rho, _) in MODEL_SPECS.items():
                        if model_rho != estimate_rho:
                            continue
                        for k in K_GRID:
                            rows.append(
                                _prediction_row(
                                    match, cutoff, model, k, context, fit,
                                    references[season], prior, clubs_by_season, season_order,
                                    matrix_cache,
                                )
                            )
    grid = pd.DataFrame(rows, columns=PREDICTION_COLUMNS)
    expected = len(state.targets) * len(decays) * len(MODEL_ORDER) * len(K_GRID)
    if len(grid) != expected:
        raise PromotedPriorError("Stage 6 grid predictions are incomplete")
    return baseline.add_match_scores(grid)


def summarize_grid(grid_scored: pd.DataFrame) -> pd.DataFrame:
    keys = ["model", "season", "decay_per_day", "prior_k"]
    overall = (
        grid_scored.groupby(keys, sort=True)
        .agg(
            matches=("log_loss", "size"),
            log_loss=("log_loss", "mean"),
            brier_score=("brier_score", "mean"),
        )
        .reset_index()
    )
    promoted_rows = grid_scored.loc[grid_scored["home_promoted"] | grid_scored["away_promoted"]]
    promoted = (
        promoted_rows.groupby(keys, sort=True)
        .agg(promoted_matches=("log_loss", "size"), promoted_log_loss=("log_loss", "mean"))
        .reset_index()
    )
    summary = overall.merge(promoted, on=keys, how="left", validate="one_to_one")
    summary["promoted_matches"] = summary["promoted_matches"].fillna(0).astype(int)
    summary["model"] = pd.Categorical(summary["model"], categories=MODEL_ORDER, ordered=True)
    summary = summary.sort_values(keys, kind="stable").reset_index(drop=True)
    summary["model"] = summary["model"].astype("string")
    return summary[GRID_METRIC_COLUMNS]


def select_k(
    grid_scored: pd.DataFrame,
    decay_by_season: dict[str, float],
    targets: pd.DataFrame,
    timeline: pd.DataFrame,
) -> pd.DataFrame:
    """Apply the nested chronological k-selection rule for every Stage 6 model."""
    availability = pd.to_datetime(
        timeline.set_index("match_id")["result_available_at"], utc=True
    )
    rows: list[dict[str, Any]] = []
    for model in MODEL_ORDER:
        for position in range(len(dc.TUNING_ONLY_SEASONS), len(dc.GRID_SEASONS)):
            season = dc.GRID_SEASONS[position]
            decay = float(decay_by_season[season])
            tuning_seasons = dc.GRID_SEASONS[:position]
            first_prediction = targets.loc[targets["season"] == season, "_prediction_time"].min()
            tuning = grid_scored.loc[
                (grid_scored["model"] == model)
                & (grid_scored["decay_per_day"] == decay)
                & grid_scored["season"].isin(tuning_seasons)
            ]
            if tuning.empty or pd.isna(first_prediction):
                raise PromotedPriorError(f"k selection for {model} {season} has no evidence")
            if not availability.loc[tuning["match_id"].unique()].lt(first_prediction).all():
                raise PromotedPriorError(
                    f"k tuning for {season} used a result unavailable at its first kickoff"
                )
            losses = tuning.groupby("prior_k", sort=True)["log_loss"].agg(["mean", "size"])
            if sorted(losses.index.tolist()) != sorted(K_GRID) or losses["size"].nunique() != 1:
                raise PromotedPriorError(f"k tuning grid for {model} {season} is incomplete")
            selected = min(K_GRID, key=lambda k: (float(losses.loc[k, "mean"]), k))
            rows.append(
                {
                    "model": model,
                    "target_season": season,
                    "decay_per_day": decay,
                    "tuning_seasons": ";".join(tuning_seasons),
                    "tuning_matches": int(losses["size"].iloc[0]),
                    "selected_k": int(selected),
                    "selected_tuning_log_loss": float(losses.loc[selected, "mean"]),
                    "no_prior_tuning_log_loss": float(losses.loc[0, "mean"]),
                    "selected_at_grid_maximum": selected == max(K_GRID),
                }
            )
    return pd.DataFrame(rows, columns=SELECTION_COLUMNS)


def _validate(
    predictions: pd.DataFrame,
    grid_scored: pd.DataFrame,
    development: pd.DataFrame,
    stage5_predictions: pd.DataFrame,
    decay_by_season: dict[str, float],
) -> None:
    if predictions.columns.tolist() != PREDICTION_COLUMNS:
        raise PromotedPriorError("Stage 6 prediction output schema changed")
    expected_ids = development["match_id"].tolist()
    for model in MODEL_ORDER:
        selected = predictions.loc[predictions["model"] == model]
        if sorted(selected["match_id"].tolist()) != sorted(expected_ids):
            raise PromotedPriorError(f"Stage 6 coverage is incomplete for {model}")
    probabilities = predictions[baseline.PROBABILITY_COLUMNS].to_numpy(dtype=float)
    if not (np.isfinite(probabilities).all() and ((probabilities > 0) & (probabilities < 1)).all()):
        raise PromotedPriorError("Stage 6 probabilities must be finite and inside (0, 1)")
    if not (np.abs(probabilities.sum(axis=1) - 1.0) < 1e-12).all():
        raise PromotedPriorError("Stage 6 probabilities do not sum to one")
    prediction_times = pd.to_datetime(predictions["prediction_time"], utc=True, errors="raise")
    latest = pd.to_datetime(predictions["latest_result_available_at"], utc=True, errors="raise")
    if not latest.lt(prediction_times).all():
        raise PromotedPriorError("Stage 6 history crosses the strict time boundary")

    # k = 0 must reproduce the Stage 5 base predictions exactly.
    development_grid = grid_scored.loc[
        (grid_scored["prior_k"] == 0)
        & grid_scored["season"].map(decay_by_season).eq(grid_scored["decay_per_day"])
    ]
    for model, (estimate_rho, _) in MODEL_SPECS.items():
        stage6 = development_grid.loc[development_grid["model"] == model]
        stage5 = stage5_predictions.loc[
            stage5_predictions["model"] == BASE_REFERENCE[estimate_rho]
        ]
        merged = stage6.merge(
            stage5, on="match_id", suffixes=("", "_stage5"), validate="one_to_one"
        )
        if len(merged) != len(expected_ids):
            raise PromotedPriorError(f"k = 0 comparison lost fixtures for {model}")
        for column in baseline.PROBABILITY_COLUMNS:
            if not merged[column].eq(merged[f"{column}_stage5"]).all():
                raise PromotedPriorError(f"k = 0 does not reproduce Stage 5 for {model}")


@dataclass(frozen=True)
class Stage6State:
    """Stage 6 grid predictions and selections reused by later stages."""

    grid_scored: pd.DataFrame
    selection: pd.DataFrame
    decay_by_season: dict[str, float]


def evaluate(
    matches: pd.DataFrame,
    splits: pd.DataFrame,
    state: dc.Stage5State,
    stage5_predictions: pd.DataFrame,
) -> tuple[dict[str, pd.DataFrame], Stage6State]:
    season_order = splits["season"].tolist()
    clubs_by_season = season_clubs(matches)
    decays = sorted({float(decay) for decay in state.selection["selected_decay_per_day"]})
    offsets = build_offsets(state.timeline, decays, clubs_by_season, season_order)
    grid_scored = build_grid(state, offsets, clubs_by_season, season_order)
    decay_by_season = {
        str(season): float(decay)
        for season, decay in zip(
            state.selection["target_season"], state.selection["selected_decay_per_day"]
        )
    }
    selection = select_k(grid_scored, decay_by_season, state.targets, state.timeline)
    choices = selection[["model", "target_season", "decay_per_day", "selected_k"]].rename(
        columns={"target_season": "season", "selected_k": "prior_k"}
    )
    predictions = grid_scored.merge(
        choices, on=["model", "season", "decay_per_day", "prior_k"], validate="many_to_one"
    )[PREDICTION_COLUMNS]
    predictions["model"] = pd.Categorical(
        predictions["model"], categories=MODEL_ORDER, ordered=True
    )
    predictions = predictions.sort_values(
        ["prediction_time", "match_id", "model"], kind="stable"
    ).reset_index(drop=True)
    predictions["model"] = predictions["model"].astype("string")
    development = baseline.development_targets(matches, splits)
    _validate(predictions, grid_scored, development, stage5_predictions, decay_by_season)
    offset_rows = [
        {
            "season": item.season,
            "decay_per_day": item.decay_per_day,
            "estimate_rho": item.estimate_rho,
            "club": club,
            "attack_offset": float(attack),
            "defence_offset": float(defence),
        }
        for item in offsets.values()
        for club, attack, defence in zip(item.clubs, item.attack, item.defence)
    ]
    outputs = {
        "predictions": predictions,
        "metrics": baseline.score_predictions(predictions, MODEL_ORDER),
        "grid_metrics": summarize_grid(grid_scored),
        "selection": selection,
        "offsets": pd.DataFrame(offset_rows, columns=OFFSET_COLUMNS),
    }
    return outputs, Stage6State(grid_scored, selection, decay_by_season)


def run_evaluation(
    matches: pd.DataFrame,
    splits: pd.DataFrame,
    state: dc.Stage5State,
    stage5_predictions: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    return evaluate(matches, splits, state, stage5_predictions)[0]


def run_and_write(
    matches: pd.DataFrame,
    splits: pd.DataFrame,
    state: dc.Stage5State,
    stage5_outputs: dict[str, pd.DataFrame],
) -> tuple[dict[str, pd.DataFrame], Stage6State]:
    outputs, stage6_state = evaluate(matches, splits, state, stage5_outputs["predictions"])
    write_outputs(outputs, stage5_outputs, matches, splits)
    return outputs, stage6_state


def _paired_difference(
    frame: pd.DataFrame, reference: pd.DataFrame, ids: set[str] | None = None
) -> pd.Series:
    merged = frame[["match_id", "log_loss"]].merge(
        reference[["match_id", "log_loss"]],
        on="match_id",
        suffixes=("", "_reference"),
        validate="one_to_one",
    )
    if len(merged) != len(frame):
        raise PromotedPriorError("Paired comparison lost fixtures")
    if ids is not None:
        merged = merged.loc[merged["match_id"].isin(ids)]
    return merged["log_loss"] - merged["log_loss_reference"]


def _n_bucket(n: int) -> str:
    if n == 0:
        return "0"
    if n <= 5:
        return "1-5"
    if n <= 16:
        return "6-16"
    return "17+"


def generate_report(
    outputs: dict[str, pd.DataFrame],
    stage5_outputs: dict[str, pd.DataFrame],
    matches: pd.DataFrame,
    splits: pd.DataFrame,
) -> str:
    season_order = splits["season"].tolist()
    clubs_by_season = season_clubs(matches)
    predictions = outputs["predictions"]
    selection = outputs["selection"]
    grid_metrics = outputs["grid_metrics"]
    offsets = outputs["offsets"]
    poisson_metrics = pd.read_csv(poisson.METRICS_OUTPUT, dtype={"season": "string"})
    all_metrics = pd.concat(
        [poisson_metrics, stage5_outputs["metrics"], outputs["metrics"]], ignore_index=True
    )
    overall = all_metrics.loc[all_metrics["season"] == "ALL"].set_index("model")
    report_models = [poisson.MODEL_NAME, dc.DECAY_ONLY_MODEL, dc.CANDIDATE_MODEL, *MODEL_ORDER]

    scored = baseline.add_match_scores(predictions)
    stage5_scored = baseline.add_match_scores(stage5_outputs["predictions"])
    frames = {model: scored.loc[scored["model"] == model] for model in MODEL_ORDER}
    for model in (dc.DECAY_ONLY_MODEL, dc.CANDIDATE_MODEL):
        frames[model] = stage5_scored.loc[stage5_scored["model"] == model]
    candidate = frames[CANDIDATE_MODEL]
    promoted_mask = candidate["home_promoted"].astype(bool) | candidate["away_promoted"].astype(bool)
    promoted_ids = set(candidate.loc[promoted_mask, "match_id"])

    def promoted_loss(model: str) -> float:
        frame = frames[model]
        return float(frame.loc[frame["match_id"].isin(promoted_ids), "log_loss"].mean())

    candidate_all = float(overall.loc[CANDIDATE_MODEL, "log_loss"])
    reference_all = float(overall.loc[GATE_REFERENCE, "log_loss"])
    candidate_promoted = promoted_loss(CANDIDATE_MODEL)
    reference_promoted = promoted_loss(GATE_REFERENCE)
    gate = candidate_promoted < reference_promoted and candidate_all <= reference_all
    promoted_mean, promoted_low, promoted_high = dc._interval(
        _paired_difference(candidate, frames[GATE_REFERENCE], promoted_ids)
    )
    overall_mean, overall_low, overall_high = dc._interval(
        _paired_difference(candidate, frames[GATE_REFERENCE])
    )
    caveats = []
    if promoted_high >= 0.0 and overall_high >= 0.0:
        caveats.append(
            "Both approximate intervals include zero, so the improvement is not clearly "
            "separated from match-level noise."
        )
    elif promoted_high >= 0.0:
        caveats.append("The promoted-club interval includes zero.")
    elif overall_high >= 0.0:
        caveats.append("The all-fixture interval includes zero.")
    point_all = float(overall.loc[POINT_MODEL, "log_loss"])
    point_promoted = promoted_loss(POINT_MODEL)
    if point_all <= candidate_all and point_promoted <= candidate_promoted:
        caveats.append(
            f"Uncertainty propagation is not justified on H/D/A metrics: `{POINT_MODEL}` "
            f"scores {point_all:.6f} overall and {point_promoted:.6f} on promoted-club fixtures."
        )
    edge_count = int(selection["selected_at_grid_maximum"].astype(bool).sum())
    if edge_count:
        caveats.append(
            f"{edge_count} of {len(selection)} `k` selections sit at the grid maximum "
            f"(k = {max(K_GRID)}); the declared grid is not extended after seeing results."
        )
    verdict = [
        (
            f"**GO.** `{CANDIDATE_MODEL}` improves log loss on the {len(promoted_ids)} development"
            if gate
            else f"**CHARACTERIZED.** `{CANDIDATE_MODEL}` does not pass the declared gate on the"
        ),
        f"fixtures involving a promoted club ({candidate_promoted:.6f} vs {reference_promoted:.6f}"
        f" for `{GATE_REFERENCE}`)"
        + (" without worsening" if gate else "; overall development log loss is")
        + f" overall log loss ({candidate_all:.6f} vs {reference_all:.6f}).",
        "",
        f"Paired log-loss difference against `{GATE_REFERENCE}`: promoted-club fixtures",
        f"{promoted_mean:+.6f} [{promoted_low:+.6f}, {promoted_high:+.6f}], all fixtures",
        f"{overall_mean:+.6f} [{overall_low:+.6f}, {overall_high:+.6f}] (approximate 95%",
        "intervals treating matches as independent).",
        "",
        *[line for caveat in caveats for line in (caveat, "")],
        "`k` was selected by the nested chronological rule at each season's Stage 5 decay;",
        "no development season tuned itself, and no final-holdout result or market",
        "probability was used.",
    ]

    overall_rows = [
        [
            model,
            int(overall.loc[model, "matches"]),
            f"{float(overall.loc[model, 'log_loss']):.6f}",
            f"{float(overall.loc[model, 'brier_score']):.6f}",
            "-" if model == poisson.MODEL_NAME else f"{promoted_loss(model):.6f}",
        ]
        for model in report_models
    ]
    paired_rows = []
    comparisons = [(model, GATE_REFERENCE) for model in MODEL_ORDER] + [
        (POISSON_MODEL, dc.DECAY_ONLY_MODEL)
    ]
    for model, reference in comparisons:
        for label, ids in (("promoted-club fixtures", promoted_ids), ("all fixtures", None)):
            mean, low, high = dc._interval(_paired_difference(frames[model], frames[reference], ids))
            paired_rows.append(
                [f"`{model}`", f"`{reference}`", label, f"{mean:+.6f}", f"[{low:+.6f}, {high:+.6f}]"]
            )

    selection_rows = [
        [
            f"`{row.model}`",
            row.target_season,
            f"{row.decay_per_day:g}",
            int(row.tuning_matches),
            int(row.selected_k),
            f"{row.selected_tuning_log_loss:.6f}",
            f"{row.no_prior_tuning_log_loss:.6f}",
            "yes" if bool(row.selected_at_grid_maximum) else "no",
        ]
        for row in selection.itertuples(index=False)
    ]
    candidate_grid = grid_metrics.loc[grid_metrics["model"] == CANDIDATE_MODEL]
    grid_rows = []
    for (season, decay), group in candidate_grid.groupby(["season", "decay_per_day"], sort=True):
        by_k = group.set_index("prior_k")
        grid_rows.append(
            [
                season,
                f"{decay:g}",
                int(by_k["promoted_matches"].iloc[0]),
                *[f"{float(by_k.loc[k, 'promoted_log_loss']):.4f}" for k in K_GRID],
            ]
        )

    prior_rows = []
    for row in selection.loc[selection["model"] == CANDIDATE_MODEL].itertuples(index=False):
        sources = season_order[
            season_order.index(PRIOR_START_SEASON) : season_order.index(row.target_season)
        ]
        used = offsets.loc[
            offsets["season"].isin(sources)
            & offsets["decay_per_day"].eq(row.decay_per_day)
            & offsets["estimate_rho"].astype(bool)
        ]
        prior_rows.append(
            [
                row.target_season,
                len(used),
                f"{float(used['attack_offset'].mean()):+.3f}",
                f"{float(used['attack_offset'].std(ddof=1)):.3f}",
                f"{float(used['defence_offset'].mean()):+.3f}",
                f"{float(used['defence_offset'].std(ddof=1)):.3f}",
            ]
        )

    promoted_candidate = candidate.loc[promoted_mask].merge(
        frames[GATE_REFERENCE][["match_id", "log_loss"]],
        on="match_id",
        suffixes=("", "_reference"),
        validate="one_to_one",
    )

    def fewest_n(row: Any) -> int:
        counts = []
        if row.home_promoted:
            counts.append(int(row.home_season_matches))
        if row.away_promoted:
            counts.append(int(row.away_season_matches))
        return min(counts)

    def has_earlier_history(row: Any) -> bool:
        season_position = season_order.index(row.season)
        earlier = season_order[: max(season_position - 1, 0)]
        clubs = [
            club
            for club, flag in ((row.home_team, row.home_promoted), (row.away_team, row.away_promoted))
            if flag
        ]
        return any(club in clubs_by_season.get(season, frozenset()) for club in clubs for season in earlier)

    promoted_candidate["n_bucket"] = [
        _n_bucket(fewest_n(row)) for row in promoted_candidate.itertuples(index=False)
    ]
    promoted_candidate["history"] = [
        "earlier top-flight history in data" if has_earlier_history(row) else "no earlier history in data"
        for row in promoted_candidate.itertuples(index=False)
    ]

    def slice_rows(column: str, labels: list[str]) -> list[list[Any]]:
        rows = []
        for label in labels:
            group = promoted_candidate.loc[promoted_candidate[column] == label]
            if group.empty:
                rows.append([label, 0, "-", "-", "-"])
                continue
            rows.append(
                [
                    label,
                    len(group),
                    f"{float(group['log_loss_reference'].mean()):.6f}",
                    f"{float(group['log_loss'].mean()):.6f}",
                    f"{float((group['log_loss'] - group['log_loss_reference']).mean()):+.6f}",
                ]
            )
        return rows

    worst = candidate.sort_values(["log_loss", "match_id"], ascending=[False, True], kind="stable").head(5)
    worst_rows = [
        [
            row.season,
            str(row.prediction_time)[:10],
            f"{row.home_team} - {row.away_team}",
            "home" if row.home_promoted and not row.away_promoted
            else "away" if row.away_promoted and not row.home_promoted
            else "both" if row.home_promoted else "none",
            int(row.prior_k),
            f"{row.expected_home_goals:.2f} - {row.expected_away_goals:.2f}",
            f"{int(row.actual_home_goals)}-{int(row.actual_away_goals)}",
            f"{row.log_loss:.4f}",
        ]
        for row in worst.itertuples(index=False)
    ]

    slice_headers = [
        "Slice",
        "Matches",
        f"`{GATE_REFERENCE}` log loss",
        f"`{CANDIDATE_MODEL}` log loss",
        "Difference",
    ]
    table = baseline._markdown_table
    lines = [
        "# Dynamic promoted-team prior evaluation",
        "",
        "## Verdict",
        "",
        *verdict,
        "",
        "## Overall development results",
        "",
        *table(
            ["Model", "Matches", "Log loss", "Brier score", "Promoted-club fixture log loss"],
            overall_rows,
        ),
        "",
        f"Promoted-club fixtures: {len(promoted_ids)} of {len(candidate)} development matches involve",
        "a club with no eligible match in the previous season.",
        "",
        "## Paired log-loss differences",
        "",
        *table(["Model", "Reference", "Subset", "Mean difference", "Approx. 95% interval"], paired_rows),
        "",
        "Negative differences favour the Stage 6 model.",
        "",
        "## Nested chronological k selection",
        "",
        *table(
            [
                "Model",
                "Target season",
                "Decay/day",
                "Tuning matches",
                "Selected k",
                "Tuning log loss",
                "No-prior tuning log loss",
                "At grid maximum",
            ],
            selection_rows,
        ),
        "",
        "## Candidate k grid on promoted-club fixtures (descriptive)",
        "",
        *table(
            ["Season", "Decay/day", "Promoted matches", *[f"k={k}" for k in K_GRID]],
            grid_rows,
        ),
        "",
        "Log loss on promoted-club fixtures for each declared `k`; this table never",
        "replaces the nested choice.",
        "",
        "## Prior used at each development season",
        "",
        *table(
            [
                "Target season",
                "Offsets",
                "Mean attack offset",
                "Attack SD",
                "Mean defence offset",
                "Defence SD",
            ],
            prior_rows,
        ),
        "",
        "Offsets are candidate-base strengths of previously promoted clubs relative to",
        "the previous-season reference level (`reports/promoted_prior_offsets.csv`).",
        "",
        "## Cold-start slices on promoted-club fixtures",
        "",
        *table(slice_headers, slice_rows("n_bucket", ["0", "1-5", "6-16", "17+"])),
        "",
        "Slices use the fewest current-season matches among promoted clubs in a fixture.",
        "",
        *table(
            slice_headers,
            slice_rows(
                "history",
                ["no earlier history in data", "earlier top-flight history in data"],
            ),
        ),
        "",
        "## Largest single-match candidate losses",
        "",
        *table(
            ["Season", "Kickoff date", "Fixture", "Promoted", "k", "Expected goals", "Score", "H/D/A log loss"],
            worst_rows,
        ),
        "",
        "## Model specification",
        "",
        "The declared specification is in `MODEL_DESIGN.md` (Stage 6 implementation) and",
        "the k-selection rule in `EVALUATION_PROTOCOL.md`. `k = 0` reproduces the Stage 5",
        "base predictions exactly; the evaluator verifies this before writing outputs.",
        "",
        "## Frozen evaluation boundary",
        "",
        "- Tuning-only walk-forward seasons: 2019-20 and 2020-21.",
        "- Development walk-forward: 2021-22 through 2024-25.",
        "- Prior offsets use only completed seasons from 2018-19 before each target season.",
        "- Final holdout: 2025-26, still sealed and absent from fitting, tuning, and metrics.",
        "- Current season: 2026-27, live-only and absent from development metrics.",
        "- The isolated market benchmark table is not loaded by the evaluator.",
        "",
        "## Next roadmap gate",
        "",
        "Stage 7 (small-data ML challengers) requires a new user go-ahead and must use the",
        "same split, metrics, and chronological tuning rules.",
        "",
    ]
    return "\n".join(lines)


def write_outputs(
    outputs: dict[str, pd.DataFrame],
    stage5_outputs: dict[str, pd.DataFrame],
    matches: pd.DataFrame,
    splits: pd.DataFrame,
) -> None:
    PREDICTIONS_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    outputs["predictions"].to_csv(
        PREDICTIONS_OUTPUT, index=False, float_format=poisson.PUBLISHED_FLOAT_FORMAT
    )
    outputs["metrics"].to_csv(METRICS_OUTPUT, index=False, float_format="%.12f")
    outputs["grid_metrics"].to_csv(GRID_METRICS_OUTPUT, index=False, float_format="%.12f")
    outputs["selection"].to_csv(SELECTION_OUTPUT, index=False, float_format="%.12f")
    outputs["offsets"].to_csv(
        OFFSETS_OUTPUT, index=False, float_format=poisson.PUBLISHED_FLOAT_FORMAT
    )
    REPORT_OUTPUT.write_text(
        generate_report(outputs, stage5_outputs, matches, splits), encoding="utf-8"
    )


def main() -> int:
    poisson_status = poisson.main()
    if poisson_status != 0:
        return poisson_status
    splits = baseline.load_split_config()
    matches = baseline.load_matches()
    stage5_outputs, state = dc.run_and_write(matches, splits)
    print("Dixon-Coles evaluation complete.")
    outputs, _ = run_and_write(matches, splits, state, stage5_outputs)
    print(
        "Promoted-team prior evaluation complete: "
        f"{outputs['predictions']['match_id'].nunique()} development matches, "
        f"{len(MODEL_ORDER)} Stage 6 models."
    )
    print(f"Report: {REPORT_OUTPUT}")
    print("Final holdout: SEALED (2025-26)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
