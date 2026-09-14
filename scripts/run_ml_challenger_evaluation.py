#!/usr/bin/env python3
"""Run the Stage 7 leakage-safe small-data ML challenger walk-forward evaluation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import evaluation_time
import run_baseline_evaluation as baseline
import run_dixon_coles_evaluation as dc
import run_poisson_evaluation as poisson
import run_promoted_prior_evaluation as pp


ROOT = Path(__file__).resolve().parents[1]
PREDICTIONS_OUTPUT = ROOT / "reports" / "ml_predictions.csv"
METRICS_OUTPUT = ROOT / "reports" / "ml_metrics.csv"
GRID_METRICS_OUTPUT = ROOT / "reports" / "ml_grid_metrics.csv"
SELECTION_OUTPUT = ROOT / "reports" / "ml_selection.csv"
COEFFICIENTS_OUTPUT = ROOT / "reports" / "ml_coefficients.csv"
REPORT_OUTPUT = ROOT / "reports" / "ML_CHALLENGER_REPORT.md"

CANDIDATE_MODEL = "ml_offset_logit"
RECALIBRATION_MODEL = "ml_offset_recalibration"
PLAIN_MODEL = "ml_plain_logit"
MODEL_ORDER = [CANDIDATE_MODEL, RECALIBRATION_MODEL, PLAIN_MODEL]
REFERENCE_MODEL = pp.CANDIDATE_MODEL
LOGIT_FEATURES = ("stage6_logit_home_draw", "stage6_logit_away_draw")
CONTEXT_FEATURES = (
    "form_points_diff",
    "sot_share_diff",
    "rest_days_diff",
    "home_promoted",
    "away_promoted",
)
ALL_FEATURES = (*LOGIT_FEATURES, *CONTEXT_FEATURES)
# Model name -> (uses the Stage 6 logit offset, adjustment features).
MODEL_SPECS = {
    CANDIDATE_MODEL: (True, ALL_FEATURES),
    RECALIBRATION_MODEL: (True, LOGIT_FEATURES),
    PLAIN_MODEL: (False, ALL_FEATURES),
}
# Declared in MODEL_DESIGN.md before any Stage 7 metric was computed.
PENALTY_GRID = (1.0, 3.0, 10.0, 30.0, 100.0, 300.0, math.inf)
TRAINING_START_SEASON = "2019-20"
FIRST_PREDICTION_SEASON = "2020-21"
FORM_WINDOW = 5
REST_DAYS_CAP = 14.0
NEWTON_TOLERANCE = 1e-10
FULL_STEP_THRESHOLD = 1e-4
MAX_NEWTON_ITERATIONS = 100
MAX_STEP_HALVINGS = 60
LABELS = {"H": 0, "D": 1, "A": 2}
CALIBRATION_BINS = 10
PREDICTION_COLUMNS = [
    "match_id",
    "season",
    "prediction_time",
    "model",
    "decay_per_day",
    "prior_k",
    "penalty",
    "training_rows",
    "latest_training_result_available_at",
    *ALL_FEATURES,
    *baseline.PROBABILITY_COLUMNS,
    "actual_result",
]
GRID_METRIC_COLUMNS = [
    "model",
    "season",
    "decay_per_day",
    "prior_k",
    "penalty",
    "matches",
    "log_loss",
    "brier_score",
]
SELECTION_COLUMNS = [
    "model",
    "target_season",
    "decay_per_day",
    "prior_k",
    "tuning_seasons",
    "tuning_matches",
    "selected_penalty",
    "selected_tuning_log_loss",
    "no_adjustment_tuning_log_loss",
    "selected_at_grid_minimum",
]
COEFFICIENT_COLUMNS = ["model", "season", "penalty", "outcome", "term", "coefficient"]


class MLChallengerError(RuntimeError):
    """The Stage 7 model or its evaluation contract was violated."""


# ---------------------------------------------------------------- features


def club_context(
    history: pd.DataFrame, club: str, cutoff: pd.Timestamp, mean_points: float
) -> tuple[float, float, float]:
    """Mean points, shots-on-target share, and capped rest days before `cutoff`."""
    rows = history.loc[(history["home_team"] == club) | (history["away_team"] == club)]
    if rows.empty:
        return mean_points, 0.5, REST_DAYS_CAP
    recent = rows.sort_values(["_kickoff_utc", "match_id"], kind="stable").tail(FORM_WINDOW)
    is_home = recent["home_team"].eq(club).to_numpy()
    result = recent["result"].to_numpy()
    won = np.where(is_home, result == "H", result == "A")
    points = np.where(won, 3.0, np.where(result == "D", 1.0, 0.0))

    home_sot = pd.to_numeric(recent["home_shots_on_target"], errors="coerce").to_numpy(dtype=float)
    away_sot = pd.to_numeric(recent["away_shots_on_target"], errors="coerce").to_numpy(dtype=float)
    shots_for = np.where(is_home, home_sot, away_sot)
    shots_against = np.where(is_home, away_sot, home_sot)
    usable = ~(np.isnan(shots_for) | np.isnan(shots_against))
    total = float(shots_for[usable].sum() + shots_against[usable].sum())
    share = float(shots_for[usable].sum()) / total if usable.any() and total > 0.0 else 0.5

    last_kickoff = pd.Timestamp(recent["_kickoff_utc"].iloc[-1])
    rest_days = (cutoff.tz_convert("UTC") - last_kickoff).total_seconds() / 86400.0
    if rest_days <= 0.0:
        raise MLChallengerError("A club's previous match does not precede the prediction")
    return float(points.mean()), share, min(rest_days, REST_DAYS_CAP)


def build_context_features(state: dc.Stage5State) -> pd.DataFrame:
    """Form, shots-on-target, and rest features for every grid-season fixture."""
    rows: list[dict[str, Any]] = []
    for cutoff, fixtures in state.targets.groupby("_prediction_time", sort=True):
        history = evaluation_time.available_history(state.timeline, cutoff)
        if history.empty:
            raise MLChallengerError("A Stage 7 feature has no prior history")
        if not history["result_available_at"].max() < cutoff:
            raise MLChallengerError("Stage 7 feature history crosses the strict time boundary")
        counts = history["result"].value_counts()
        mean_points = (
            3.0 * (int(counts.get("H", 0)) + int(counts.get("A", 0)))
            + 2.0 * int(counts.get("D", 0))
        ) / (2.0 * len(history))
        for match in fixtures.itertuples(index=False):
            home = club_context(history, match.home_team, cutoff, mean_points)
            away = club_context(history, match.away_team, cutoff, mean_points)
            rows.append(
                {
                    "match_id": match.match_id,
                    "form_points_diff": home[0] - away[0],
                    "sot_share_diff": home[1] - away[1],
                    "rest_days_diff": home[2] - away[2],
                }
            )
    return pd.DataFrame(rows)


def feature_table(
    state: dc.Stage5State,
    stage6_state: pp.Stage6State,
    context: pd.DataFrame,
    decay: float,
    k: int,
) -> pd.DataFrame:
    grid = stage6_state.grid_scored
    base = grid.loc[
        (grid["model"] == pp.CANDIDATE_MODEL)
        & (grid["decay_per_day"] == decay)
        & (grid["prior_k"] == k),
        ["match_id", "p_home", "p_draw", "p_away", "home_promoted", "away_promoted"],
    ]
    table = (
        state.targets[["match_id", "season", "result", "model_eligible", "_prediction_time"]]
        .merge(
            state.timeline[["match_id", "result_available_at"]],
            on="match_id",
            validate="one_to_one",
        )
        .merge(base, on="match_id", validate="one_to_one")
        .merge(context, on="match_id", validate="one_to_one")
    )
    if len(table) != len(state.targets):
        raise MLChallengerError("Stage 7 feature table lost fixtures")
    table["stage6_logit_home_draw"] = np.log(table["p_home"] / table["p_draw"])
    table["stage6_logit_away_draw"] = np.log(table["p_away"] / table["p_draw"])
    table["home_promoted"] = table["home_promoted"].astype(float)
    table["away_promoted"] = table["away_promoted"].astype(float)
    if table[list(ALL_FEATURES)].isna().any(axis=None):
        raise MLChallengerError("Stage 7 features contain missing values")
    table = table.loc[table["season"] >= TRAINING_START_SEASON]
    return table.sort_values(["_prediction_time", "match_id"], kind="stable").reset_index(
        drop=True
    )


# ------------------------------------------------------------------- model


@dataclass(frozen=True)
class LogitFit:
    """Penalized multinomial logistic adjustment with draw as the reference class."""

    features: tuple[str, ...]
    uses_offset: bool
    penalty: float
    means: np.ndarray
    scales: np.ndarray
    coefficients: np.ndarray
    training_rows: int

    @property
    def is_null_adjustment(self) -> bool:
        return self.uses_offset and math.isinf(self.penalty)


def _design(features: np.ndarray, means: np.ndarray, scales: np.ndarray) -> np.ndarray:
    return np.column_stack([np.ones(len(features)), (features - means) / scales])


def _probabilities(
    design: np.ndarray, coefficients: np.ndarray, offsets: np.ndarray
) -> np.ndarray:
    adjustment = offsets + design @ coefficients.T
    logits = np.column_stack(
        [adjustment[:, 0], np.zeros(len(design)), adjustment[:, 1]]
    )
    shifted = logits - logits.max(axis=1, keepdims=True)
    exponentiated = np.exp(shifted)
    return exponentiated / exponentiated.sum(axis=1, keepdims=True)


def _penalty_mask(width: int, uses_offset: bool) -> np.ndarray:
    mask = np.ones((2, width))
    if not uses_offset:
        mask[:, 0] = 0.0
    return mask


def _objective(
    coefficients: np.ndarray,
    design: np.ndarray,
    offsets: np.ndarray,
    labels: np.ndarray,
    penalty: float,
    mask: np.ndarray,
) -> float:
    probabilities = _probabilities(design, coefficients, offsets)
    chosen = probabilities[np.arange(len(labels)), labels]
    if not (np.isfinite(chosen).all() and (chosen > 0.0).all()):
        return -math.inf
    return float(np.log(chosen).sum()) - 0.5 * penalty * float(
        (mask * coefficients * coefficients).sum()
    )


def _gradient_and_information(
    coefficients: np.ndarray,
    design: np.ndarray,
    offsets: np.ndarray,
    labels: np.ndarray,
    penalty: float,
    mask: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    probabilities = _probabilities(design, coefficients, offsets)
    home = probabilities[:, 0]
    away = probabilities[:, 2]
    residual_home = (labels == 0).astype(float) - home
    residual_away = (labels == 2).astype(float) - away
    gradient = np.concatenate([design.T @ residual_home, design.T @ residual_away])
    gradient -= penalty * mask.ravel() * coefficients.ravel()
    weight_hh = home * (1.0 - home)
    weight_aa = away * (1.0 - away)
    weight_ha = -home * away
    block_hh = design.T @ (design * weight_hh[:, None])
    block_aa = design.T @ (design * weight_aa[:, None])
    block_ha = design.T @ (design * weight_ha[:, None])
    information = np.block([[block_hh, block_ha], [block_ha.T, block_aa]])
    information[np.diag_indices_from(information)] += penalty * mask.ravel()
    return gradient, information


def fit_logit(
    features: np.ndarray,
    labels: np.ndarray,
    offsets: np.ndarray,
    feature_names: tuple[str, ...],
    uses_offset: bool,
    penalty: float,
    warm_start: np.ndarray | None = None,
) -> LogitFit:
    """Fit penalized adjustment coefficients by Newton steps with step halving."""
    if penalty <= 0.0:
        raise MLChallengerError("Penalty must be positive or infinite")
    rows, width = features.shape
    if rows == 0 or width != len(feature_names):
        raise MLChallengerError("Stage 7 training features have the wrong shape")
    if set(np.unique(labels)) - {0, 1, 2}:
        raise MLChallengerError("Stage 7 labels must be H/D/A codes")
    if not uses_offset:
        offsets = np.zeros_like(offsets)
    means = features.mean(axis=0)
    scales = features.std(axis=0)
    scales = np.where(scales > 0.0, scales, 1.0)
    coefficients = np.zeros((2, width + 1))

    def build(values: np.ndarray) -> LogitFit:
        return LogitFit(
            features=feature_names,
            uses_offset=uses_offset,
            penalty=penalty,
            means=means,
            scales=scales,
            coefficients=values,
            training_rows=rows,
        )

    if uses_offset and math.isinf(penalty):
        return build(coefficients)
    design = _design(features, means, scales)
    mask = _penalty_mask(width + 1, uses_offset)
    active = np.ones((2, width + 1), dtype=bool)
    penalty_value = penalty
    if math.isinf(penalty):
        active[:, 1:] = False
        penalty_value = 0.0
    active_flat = active.ravel()
    if warm_start is not None and warm_start.shape == coefficients.shape:
        coefficients = np.where(active, warm_start, 0.0)
    objective = _objective(coefficients, design, offsets, labels, penalty_value, mask)
    if not math.isfinite(objective):
        coefficients = np.zeros((2, width + 1))
        objective = _objective(coefficients, design, offsets, labels, penalty_value, mask)

    for _ in range(MAX_NEWTON_ITERATIONS):
        gradient, information = _gradient_and_information(
            coefficients, design, offsets, labels, penalty_value, mask
        )
        step = np.zeros(2 * (width + 1))
        step[active_flat] = np.linalg.solve(
            information[np.ix_(active_flat, active_flat)], gradient[active_flat]
        )
        if not np.isfinite(step).all():
            raise MLChallengerError("Stage 7 Newton step is not finite")
        step = step.reshape(2, width + 1)
        largest = float(np.abs(step).max())
        if largest <= FULL_STEP_THRESHOLD:
            coefficients = coefficients + step
            objective = _objective(coefficients, design, offsets, labels, penalty_value, mask)
            if largest < NEWTON_TOLERANCE:
                return build(coefficients)
            continue
        scale = 1.0
        for _ in range(MAX_STEP_HALVINGS):
            candidate = coefficients + scale * step
            candidate_objective = _objective(
                candidate, design, offsets, labels, penalty_value, mask
            )
            if math.isfinite(candidate_objective) and candidate_objective >= objective:
                break
            scale *= 0.5
        else:
            raise MLChallengerError("Stage 7 Newton step did not improve the objective")
        coefficients, objective = candidate, candidate_objective
    raise MLChallengerError("Stage 7 fit did not converge")


def predict_logit(
    fit: LogitFit,
    features: np.ndarray,
    offsets: np.ndarray,
    base_probabilities: np.ndarray,
) -> np.ndarray:
    if fit.is_null_adjustment:
        return base_probabilities.copy()
    design = _design(features, fit.means, fit.scales)
    applied = offsets if fit.uses_offset else np.zeros_like(offsets)
    return _probabilities(design, fit.coefficients, applied)


# ------------------------------------------------------------ walk-forward


def walk_forward(
    table: pd.DataFrame, last_season: str, decay: float, k: int
) -> tuple[list[dict[str, Any]], dict[tuple[str, float, str], LogitFit]]:
    """Refit on each new training set and predict every fixture through `last_season`."""
    seasons = dc.GRID_SEASONS[
        dc.GRID_SEASONS.index(FIRST_PREDICTION_SEASON) : dc.GRID_SEASONS.index(last_season) + 1
    ]
    targets = table.loc[table["season"].isin(seasons)]
    rows: list[dict[str, Any]] = []
    season_fits: dict[tuple[str, float, str], LogitFit] = {}
    warm: dict[tuple[str, float], np.ndarray] = {}
    fits: dict[tuple[str, float], LogitFit] = {}
    previous_size: int | None = None
    latest = None
    for cutoff, fixtures in targets.groupby("_prediction_time", sort=True):
        training = evaluation_time.available_history(table, cutoff)
        if training.empty:
            raise MLChallengerError("A Stage 7 prediction has no training rows")
        if previous_size is not None and len(training) < previous_size:
            raise MLChallengerError("Stage 7 training rows shrank as time advanced")
        if len(training) != previous_size:
            latest = training["result_available_at"].max()
            if not latest < cutoff:
                raise MLChallengerError("Stage 7 training crosses the strict time boundary")
            labels = training["result"].map(LABELS).to_numpy(dtype=int)
            training_offsets = training[list(LOGIT_FEATURES)].to_numpy(dtype=float)
            fits = {}
            for model, (uses_offset, names) in MODEL_SPECS.items():
                features = training[list(names)].to_numpy(dtype=float)
                offsets = training_offsets if uses_offset else np.zeros_like(training_offsets)
                for penalty in PENALTY_GRID:
                    fit = fit_logit(
                        features, labels, offsets, names, uses_offset, penalty,
                        warm.get((model, penalty)),
                    )
                    warm[(model, penalty)] = fit.coefficients
                    fits[(model, penalty)] = fit
            previous_size = len(training)

        fixture_offsets = fixtures[list(LOGIT_FEATURES)].to_numpy(dtype=float)
        base = fixtures[["p_home", "p_draw", "p_away"]].to_numpy(dtype=float)
        season_values = fixtures["season"].tolist()
        for (model, penalty), fit in fits.items():
            _, names = MODEL_SPECS[model]
            probabilities = predict_logit(
                fit, fixtures[list(names)].to_numpy(dtype=float), fixture_offsets, base
            )
            for position, match in enumerate(fixtures.itertuples(index=False)):
                row = {
                    "match_id": match.match_id,
                    "season": match.season,
                    "prediction_time": pd.Timestamp(cutoff).isoformat(),
                    "model": model,
                    "decay_per_day": decay,
                    "prior_k": k,
                    "penalty": penalty,
                    "training_rows": fit.training_rows,
                    "latest_training_result_available_at": pd.Timestamp(latest).isoformat(),
                    "p_home": float(probabilities[position, 0]),
                    "p_draw": float(probabilities[position, 1]),
                    "p_away": float(probabilities[position, 2]),
                    "actual_result": match.result,
                }
                for name in ALL_FEATURES:
                    row[name] = float(getattr(match, name))
                rows.append(row)
            for season in set(season_values):
                season_fits[(model, penalty, season)] = fit
    return rows, season_fits


def select_penalty(
    grid_scored: pd.DataFrame,
    choices: dict[str, tuple[float, int]],
    targets: pd.DataFrame,
    timeline: pd.DataFrame,
) -> pd.DataFrame:
    """Apply the nested chronological penalty rule for every Stage 7 model."""
    availability = pd.to_datetime(
        timeline.set_index("match_id")["result_available_at"], utc=True
    )
    first = dc.GRID_SEASONS.index(FIRST_PREDICTION_SEASON)
    rows: list[dict[str, Any]] = []
    for model in MODEL_ORDER:
        for position in range(len(dc.TUNING_ONLY_SEASONS), len(dc.GRID_SEASONS)):
            season = dc.GRID_SEASONS[position]
            decay, k = choices[season]
            tuning_seasons = dc.GRID_SEASONS[first:position]
            first_prediction = targets.loc[targets["season"] == season, "_prediction_time"].min()
            tuning = grid_scored.loc[
                (grid_scored["model"] == model)
                & (grid_scored["decay_per_day"] == decay)
                & (grid_scored["prior_k"] == k)
                & grid_scored["season"].isin(tuning_seasons)
            ]
            if tuning.empty or pd.isna(first_prediction):
                raise MLChallengerError(f"Penalty selection for {model} {season} has no evidence")
            if not availability.loc[tuning["match_id"].unique()].lt(first_prediction).all():
                raise MLChallengerError(
                    f"Penalty tuning for {season} used a result unavailable at its first kickoff"
                )
            losses = tuning.groupby("penalty", sort=True)["log_loss"].agg(["mean", "size"])
            if sorted(losses.index.tolist()) != sorted(PENALTY_GRID) or losses["size"].nunique() != 1:
                raise MLChallengerError(f"Penalty tuning grid for {model} {season} is incomplete")
            selected = min(
                PENALTY_GRID, key=lambda value: (float(losses.loc[value, "mean"]), -value)
            )
            rows.append(
                {
                    "model": model,
                    "target_season": season,
                    "decay_per_day": decay,
                    "prior_k": k,
                    "tuning_seasons": ";".join(tuning_seasons),
                    "tuning_matches": int(losses["size"].iloc[0]),
                    "selected_penalty": selected,
                    "selected_tuning_log_loss": float(losses.loc[selected, "mean"]),
                    "no_adjustment_tuning_log_loss": float(losses.loc[math.inf, "mean"]),
                    "selected_at_grid_minimum": selected == min(PENALTY_GRID),
                }
            )
    return pd.DataFrame(rows, columns=SELECTION_COLUMNS)


def run_evaluation(
    matches: pd.DataFrame,
    splits: pd.DataFrame,
    state: dc.Stage5State,
    stage6_state: pp.Stage6State,
    stage6_predictions: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    candidate_selection = stage6_state.selection.loc[
        stage6_state.selection["model"] == pp.CANDIDATE_MODEL
    ]
    choices = {
        str(row.target_season): (float(row.decay_per_day), int(row.selected_k))
        for row in candidate_selection.itertuples(index=False)
    }
    context = build_context_features(state)
    combos: dict[tuple[float, int], list[str]] = {}
    for season, combo in choices.items():
        combos.setdefault(combo, []).append(season)

    all_rows: list[dict[str, Any]] = []
    season_fits: dict[tuple[float, int], dict[tuple[str, float, str], LogitFit]] = {}
    for (decay, k), seasons in sorted(combos.items()):
        table = feature_table(state, stage6_state, context, decay, k)
        rows, fits = walk_forward(table, max(seasons), decay, k)
        all_rows.extend(rows)
        season_fits[(decay, k)] = fits
    grid = pd.DataFrame(all_rows, columns=PREDICTION_COLUMNS)
    grid_scored = baseline.add_match_scores(grid)

    selection = select_penalty(grid_scored, choices, state.targets, state.timeline)
    chosen = selection[
        ["model", "target_season", "decay_per_day", "prior_k", "selected_penalty"]
    ].rename(columns={"target_season": "season", "selected_penalty": "penalty"})
    predictions = grid.merge(
        chosen, on=["model", "season", "decay_per_day", "prior_k", "penalty"], validate="many_to_one"
    )[PREDICTION_COLUMNS]
    predictions["model"] = pd.Categorical(predictions["model"], categories=MODEL_ORDER, ordered=True)
    predictions = predictions.sort_values(
        ["prediction_time", "match_id", "model"], kind="stable"
    ).reset_index(drop=True)
    predictions["model"] = predictions["model"].astype("string")
    development = baseline.development_targets(matches, splits)
    _validate(predictions, grid, development, stage6_predictions, choices)

    coefficient_rows = []
    for row in selection.itertuples(index=False):
        fit = season_fits[(row.decay_per_day, row.prior_k)][
            (row.model, row.selected_penalty, row.target_season)
        ]
        terms = ("intercept", *fit.features)
        for outcome, values in (("home_vs_draw", fit.coefficients[0]), ("away_vs_draw", fit.coefficients[1])):
            for term, value in zip(terms, values):
                coefficient_rows.append(
                    {
                        "model": row.model,
                        "season": row.target_season,
                        "penalty": row.selected_penalty,
                        "outcome": outcome,
                        "term": term,
                        "coefficient": float(value),
                    }
                )
    grid_metrics = (
        grid_scored.groupby(["model", "season", "decay_per_day", "prior_k", "penalty"], sort=True)
        .agg(
            matches=("log_loss", "size"),
            log_loss=("log_loss", "mean"),
            brier_score=("brier_score", "mean"),
        )
        .reset_index()[GRID_METRIC_COLUMNS]
    )
    return {
        "predictions": predictions,
        "metrics": baseline.score_predictions(predictions, MODEL_ORDER),
        "grid_metrics": grid_metrics,
        "selection": selection,
        "coefficients": pd.DataFrame(coefficient_rows, columns=COEFFICIENT_COLUMNS),
    }


def _validate(
    predictions: pd.DataFrame,
    grid: pd.DataFrame,
    development: pd.DataFrame,
    stage6_predictions: pd.DataFrame,
    choices: dict[str, tuple[float, int]],
) -> None:
    if predictions.columns.tolist() != PREDICTION_COLUMNS:
        raise MLChallengerError("Stage 7 prediction output schema changed")
    expected = sorted(development["match_id"].tolist())
    for model in MODEL_ORDER:
        if sorted(predictions.loc[predictions["model"] == model, "match_id"].tolist()) != expected:
            raise MLChallengerError(f"Stage 7 coverage is incomplete for {model}")
    probabilities = predictions[baseline.PROBABILITY_COLUMNS].to_numpy(dtype=float)
    if not (np.isfinite(probabilities).all() and ((probabilities > 0) & (probabilities < 1)).all()):
        raise MLChallengerError("Stage 7 probabilities must be finite and inside (0, 1)")
    if not (np.abs(probabilities.sum(axis=1) - 1.0) < 1e-12).all():
        raise MLChallengerError("Stage 7 probabilities do not sum to one")
    prediction_times = pd.to_datetime(predictions["prediction_time"], utc=True, errors="raise")
    latest = pd.to_datetime(
        predictions["latest_training_result_available_at"], utc=True, errors="raise"
    )
    if not latest.lt(prediction_times).all():
        raise MLChallengerError("Stage 7 training crosses the strict time boundary")

    # lambda = inf must reproduce the Stage 6 candidate exactly for offset models.
    stage6 = stage6_predictions.loc[stage6_predictions["model"] == pp.CANDIDATE_MODEL]
    season_decay = {season: combo[0] for season, combo in choices.items()}
    season_k = {season: combo[1] for season, combo in choices.items()}
    for model, (uses_offset, _) in MODEL_SPECS.items():
        if not uses_offset:
            continue
        null = grid.loc[
            (grid["model"] == model)
            & np.isinf(grid["penalty"])
            & grid["season"].isin(list(choices))
        ]
        null = null.loc[
            null["season"].map(season_decay).eq(null["decay_per_day"])
            & null["season"].map(season_k).eq(null["prior_k"])
        ]
        merged = null.merge(stage6, on="match_id", suffixes=("", "_stage6"), validate="one_to_one")
        if len(merged) != len(expected):
            raise MLChallengerError(f"lambda = inf comparison lost fixtures for {model}")
        for column in baseline.PROBABILITY_COLUMNS:
            if not merged[column].eq(merged[f"{column}_stage6"]).all():
                raise MLChallengerError(f"lambda = inf does not reproduce Stage 6 for {model}")


# ------------------------------------------------------------------ report


def expected_calibration_error(frame: pd.DataFrame, column: str, outcome: str) -> float:
    probabilities = frame[column].to_numpy(dtype=float)
    observed = frame["actual_result"].eq(outcome).to_numpy(dtype=float)
    bins = np.minimum((probabilities * CALIBRATION_BINS).astype(int), CALIBRATION_BINS - 1)
    error = 0.0
    for index in range(CALIBRATION_BINS):
        selected = bins == index
        if selected.any():
            error += float(selected.mean()) * abs(
                float(probabilities[selected].mean()) - float(observed[selected].mean())
            )
    return error


def _penalty_label(value: float) -> str:
    return "inf" if math.isinf(value) else f"{value:g}"


def generate_report(
    outputs: dict[str, pd.DataFrame], stage6_outputs: dict[str, pd.DataFrame]
) -> str:
    predictions = outputs["predictions"]
    selection = outputs["selection"]
    grid_metrics = outputs["grid_metrics"]
    coefficients = outputs["coefficients"]
    all_metrics = pd.concat([stage6_outputs["metrics"], outputs["metrics"]], ignore_index=True)
    overall = all_metrics.loc[all_metrics["season"] == "ALL"].set_index("model")
    report_models = [pp.CANDIDATE_MODEL, pp.POINT_MODEL, *MODEL_ORDER]

    scored = baseline.add_match_scores(predictions)
    stage6_scored = baseline.add_match_scores(stage6_outputs["predictions"])
    frames = {model: scored.loc[scored["model"] == model] for model in MODEL_ORDER}
    for model in (pp.CANDIDATE_MODEL, pp.POINT_MODEL):
        frames[model] = stage6_scored.loc[stage6_scored["model"] == model]

    def paired(model: str, season: str | None = None) -> tuple[float, float, float, int]:
        merged = frames[model][["match_id", "season", "log_loss"]].merge(
            frames[REFERENCE_MODEL][["match_id", "log_loss"]],
            on="match_id",
            suffixes=("", "_reference"),
            validate="one_to_one",
        )
        if season is not None:
            merged = merged.loc[merged["season"] == season]
        mean, low, high = dc._interval(merged["log_loss"] - merged["log_loss_reference"])
        return mean, low, high, len(merged)

    candidate_loss = float(overall.loc[CANDIDATE_MODEL, "log_loss"])
    candidate_brier = float(overall.loc[CANDIDATE_MODEL, "brier_score"])
    reference_loss = float(overall.loc[REFERENCE_MODEL, "log_loss"])
    reference_brier = float(overall.loc[REFERENCE_MODEL, "brier_score"])
    mean, low, high, _ = paired(CANDIDATE_MODEL)
    gate = candidate_loss < reference_loss and candidate_brier < reference_brier and high < 0.0
    verdict = [
        (
            f"**GO.** `{CANDIDATE_MODEL}` beats `{REFERENCE_MODEL}` on development log loss"
            if gate
            else f"**CHARACTERIZED.** `{CANDIDATE_MODEL}` does not pass the declared gate against"
        ),
        (
            f"({candidate_loss:.6f} vs {reference_loss:.6f}) and Brier score"
            f" ({candidate_brier:.6f} vs {reference_brier:.6f})."
            if gate
            else f"`{REFERENCE_MODEL}`: log loss {candidate_loss:.6f} vs {reference_loss:.6f},"
            f" Brier {candidate_brier:.6f} vs {reference_brier:.6f}."
        ),
        f"The paired log-loss difference is {mean:+.6f} (approximate 95% interval"
        f" [{low:+.6f}, {high:+.6f}]); the gate requires the interval to exclude zero.",
        "",
    ]
    recalibration_loss = float(overall.loc[RECALIBRATION_MODEL, "log_loss"])
    plain_loss = float(overall.loc[PLAIN_MODEL, "log_loss"])
    verdict += [
        f"Ablations: recalibration only {recalibration_loss:.6f}; plain logistic without the",
        f"Stage 6 offset {plain_loss:.6f}. Penalties were selected by the nested",
        "chronological rule; no development season tuned itself, and no final-holdout",
        "result or market probability was used.",
    ]
    null_selections = int(np.isinf(selection["selected_penalty"]).sum())
    if null_selections:
        verdict += [
            "",
            f"{null_selections} of {len(selection)} penalty selections chose `inf`, meaning no",
            "adjustment (offset models reproduce Stage 6; the plain model predicts class",
            "frequencies).",
        ]

    overall_rows = [
        [
            model,
            int(overall.loc[model, "matches"]),
            f"{float(overall.loc[model, 'log_loss']):.6f}",
            f"{float(overall.loc[model, 'brier_score']):.6f}",
        ]
        for model in report_models
    ]
    paired_rows = []
    for model in MODEL_ORDER:
        seasons = [None] + (
            sorted(predictions["season"].unique()) if model == CANDIDATE_MODEL else []
        )
        for season in seasons:
            value, lower, upper, count = paired(model, season)
            paired_rows.append(
                [f"`{model}`", season or "ALL", count, f"{value:+.6f}", f"[{lower:+.6f}, {upper:+.6f}]"]
            )
    selection_rows = [
        [
            f"`{row.model}`",
            row.target_season,
            f"{row.decay_per_day:g} / {int(row.prior_k)}",
            int(row.tuning_matches),
            _penalty_label(float(row.selected_penalty)),
            f"{row.selected_tuning_log_loss:.6f}",
            f"{row.no_adjustment_tuning_log_loss:.6f}",
        ]
        for row in selection.itertuples(index=False)
    ]
    candidate_grid = grid_metrics.loc[grid_metrics["model"] == CANDIDATE_MODEL]
    grid_rows = []
    for (season, decay, k), group in candidate_grid.groupby(
        ["season", "decay_per_day", "prior_k"], sort=True
    ):
        by_penalty = group.set_index("penalty")
        grid_rows.append(
            [
                season,
                f"{decay:g} / {int(k)}",
                *[f"{float(by_penalty.loc[value, 'log_loss']):.4f}" for value in PENALTY_GRID],
            ]
        )
    calibration_rows = []
    for model in (REFERENCE_MODEL, CANDIDATE_MODEL):
        frame = frames[model]
        calibration_rows.append(
            [
                f"`{model}`",
                *[
                    f"{float(frame[column].mean()):.4f} / {expected_calibration_error(frame, column, outcome):.4f}"
                    for column, outcome in zip(baseline.PROBABILITY_COLUMNS, ("H", "D", "A"))
                ],
            ]
        )
    observed = predictions.loc[predictions["model"] == CANDIDATE_MODEL, "actual_result"].value_counts(
        normalize=True
    )
    calibration_rows.insert(
        0,
        ["observed frequency", *[f"{float(observed.get(outcome, 0.0)):.4f}" for outcome in ("H", "D", "A")]],
    )
    candidate_coefficients = coefficients.loc[coefficients["model"] == CANDIDATE_MODEL]
    coefficient_seasons = sorted(candidate_coefficients["season"].unique())
    coefficient_rows = []
    for term in ("intercept", *ALL_FEATURES):
        values = []
        for season in coefficient_seasons:
            subset = candidate_coefficients.loc[
                (candidate_coefficients["season"] == season) & (candidate_coefficients["term"] == term)
            ].set_index("outcome")["coefficient"]
            values.append(
                f"{float(subset.get('home_vs_draw', 0.0)):+.3f} / {float(subset.get('away_vs_draw', 0.0)):+.3f}"
            )
        coefficient_rows.append([term, *values])

    table = baseline._markdown_table
    lines = [
        "# Small-data ML challenger evaluation",
        "",
        "## Verdict",
        "",
        *verdict,
        "",
        "## Overall development results",
        "",
        *table(["Model", "Matches", "Log loss", "Brier score"], overall_rows),
        "",
        f"## Paired log-loss difference against `{REFERENCE_MODEL}`",
        "",
        *table(["Model", "Season", "Matches", "Mean difference", "Approx. 95% interval"], paired_rows),
        "",
        "Negative differences favour the Stage 7 model. Intervals treat matches as independent.",
        "",
        "## Nested chronological penalty selection",
        "",
        *table(
            [
                "Model",
                "Target season",
                "Stage 5 decay / Stage 6 k",
                "Tuning matches",
                "Selected lambda",
                "Tuning log loss",
                "No-adjustment tuning log loss",
            ],
            selection_rows,
        ),
        "",
        "## Candidate penalty grid by season (descriptive)",
        "",
        *table(
            ["Season", "Decay / k", *[f"lambda={_penalty_label(value)}" for value in PENALTY_GRID]],
            grid_rows,
        ),
        "",
        "## Calibration",
        "",
        *table(["Source", "Home mean / ECE", "Draw mean / ECE", "Away mean / ECE"], calibration_rows),
        "",
        f"ECE uses {CALIBRATION_BINS} equal-width probability bins per outcome and is descriptive.",
        "",
        "## Candidate coefficients (standardized features)",
        "",
        *table(["Term (home / away vs draw)", *coefficient_seasons], coefficient_rows),
        "",
        "Coefficients come from the last fit of each development season at its selected",
        "penalty. They adjust the Stage 6 logits, so zero means no change.",
        "",
        "## Model specification",
        "",
        "The declared specification is in `MODEL_DESIGN.md` (Stage 7) and the penalty",
        "rule in `EVALUATION_PROTOCOL.md`. `lambda = inf` reproduces the Stage 6 candidate",
        "exactly for offset models; the evaluator verifies this before writing outputs.",
        "",
        "## Frozen evaluation boundary",
        "",
        "- Training rows start in 2019-20; tuning predictions start in 2020-21.",
        "- Development walk-forward: 2021-22 through 2024-25.",
        "- Final holdout: 2025-26, still sealed and absent from fitting, tuning, and metrics.",
        "- Current season: 2026-27, live-only and absent from development metrics.",
        "- The isolated market benchmark table is not loaded by the evaluator.",
        "",
        "## Next roadmap gate",
        "",
        "Stage 8 freezes one candidate and its decision rule using development evidence",
        "only. It requires a new user go-ahead; the 2025-26 holdout opens only afterwards.",
        "",
    ]
    return "\n".join(lines)


def write_outputs(
    outputs: dict[str, pd.DataFrame], stage6_outputs: dict[str, pd.DataFrame]
) -> None:
    PREDICTIONS_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    outputs["predictions"].to_csv(
        PREDICTIONS_OUTPUT, index=False, float_format=poisson.PUBLISHED_FLOAT_FORMAT
    )
    outputs["metrics"].to_csv(METRICS_OUTPUT, index=False, float_format="%.12f")
    outputs["grid_metrics"].to_csv(GRID_METRICS_OUTPUT, index=False, float_format="%.12f")
    outputs["selection"].to_csv(SELECTION_OUTPUT, index=False, float_format="%.12f")
    outputs["coefficients"].to_csv(
        COEFFICIENTS_OUTPUT, index=False, float_format=poisson.PUBLISHED_FLOAT_FORMAT
    )
    REPORT_OUTPUT.write_text(generate_report(outputs, stage6_outputs), encoding="utf-8")


def main() -> int:
    poisson_status = poisson.main()
    if poisson_status != 0:
        return poisson_status
    splits = baseline.load_split_config()
    matches = baseline.load_matches()
    stage5_outputs, state = dc.run_and_write(matches, splits)
    print("Dixon-Coles evaluation complete.")
    stage6_outputs, stage6_state = pp.run_and_write(matches, splits, state, stage5_outputs)
    print("Promoted-team prior evaluation complete.")
    outputs = run_evaluation(matches, splits, state, stage6_state, stage6_outputs["predictions"])
    write_outputs(outputs, stage6_outputs)
    print(
        "ML challenger evaluation complete: "
        f"{outputs['predictions']['match_id'].nunique()} development matches, "
        f"{len(MODEL_ORDER)} Stage 7 models."
    )
    print(f"Report: {REPORT_OUTPUT}")
    print("Final holdout: SEALED (2025-26)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
