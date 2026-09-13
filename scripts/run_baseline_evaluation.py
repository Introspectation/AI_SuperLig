#!/usr/bin/env python3
"""Run the audited foundation and leakage-safe naive baseline evaluation."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pandas as pd

import evaluation_time
import run_data_foundation


ROOT = Path(__file__).resolve().parents[1]
CANONICAL_MATCHES = ROOT / "data" / "processed" / "canonical_matches.csv"
SPLIT_CONFIG = ROOT / "config" / "evaluation_splits.csv"
PREDICTIONS_OUTPUT = ROOT / "reports" / "baseline_predictions.csv"
METRICS_OUTPUT = ROOT / "reports" / "baseline_metrics.csv"
REPORT_OUTPUT = ROOT / "reports" / "BASELINE_REPORT.md"

EXPECTED_SPLITS = [
    ("2017-18", "warmup_history"),
    ("2018-19", "warmup_history"),
    ("2019-20", "warmup_history"),
    ("2020-21", "warmup_history"),
    ("2021-22", "development"),
    ("2022-23", "development"),
    ("2023-24", "development"),
    ("2024-25", "development"),
    ("2025-26", "final_holdout"),
]
MODEL_ORDER = ["uniform_hda", "expanding_league_hda"]
PROBABILITY_COLUMNS = ["p_home", "p_draw", "p_away"]
PREDICTION_COLUMNS = [
    "match_id",
    "season",
    "prediction_time",
    "model",
    "available_history_rows",
    "training_rows_used",
    "latest_result_available_at",
    *PROBABILITY_COLUMNS,
    "actual_result",
]
METRIC_COLUMNS = [
    "evaluation_role",
    "season",
    "model",
    "matches",
    "log_loss",
    "brier_score",
]


class BaselineEvaluationError(RuntimeError):
    """The frozen evaluation contract or a baseline invariant was violated."""


def load_split_config() -> pd.DataFrame:
    if not SPLIT_CONFIG.exists():
        raise BaselineEvaluationError("Missing evaluation split config")
    splits = pd.read_csv(SPLIT_CONFIG, dtype="string")
    if splits.columns.tolist() != ["season", "role"]:
        raise BaselineEvaluationError("Evaluation split config schema changed")
    actual = list(splits.itertuples(index=False, name=None))
    if actual != EXPECTED_SPLITS:
        raise BaselineEvaluationError(
            "Evaluation seasons changed; review and update the protocol explicitly"
        )
    return splits


def load_matches() -> pd.DataFrame:
    if not CANONICAL_MATCHES.exists():
        raise BaselineEvaluationError("Canonical matches are missing")
    matches = pd.read_csv(
        CANONICAL_MATCHES,
        dtype={
            "match_id": "string",
            "season": "string",
            "date": "string",
            "kickoff_time": "string",
            "kickoff_timezone": "string",
            "result_available_at": "string",
            "result": "string",
            "model_eligible": "boolean",
        },
    )
    required = {
        "match_id",
        "season",
        "date",
        "kickoff_time",
        "kickoff_timezone",
        "result_available_at",
        "result",
        "model_eligible",
    }
    missing = required.difference(matches.columns)
    if missing:
        raise BaselineEvaluationError(
            f"Canonical data is missing evaluation columns: {sorted(missing)}"
        )
    if matches["match_id"].duplicated().any():
        raise BaselineEvaluationError("Canonical match IDs are not unique")
    if matches["model_eligible"].isna().any():
        raise BaselineEvaluationError("Canonical eligibility contains nulls")
    eligible = matches["model_eligible"].astype(bool)
    if not matches.loc[eligible, "result"].isin(["H", "D", "A"]).all():
        raise BaselineEvaluationError("Eligible matches contain invalid results")
    if set(matches["kickoff_timezone"]) != {"Europe/Istanbul"}:
        raise BaselineEvaluationError("Unexpected canonical kickoff timezone")
    if any("odds" in column.lower() for column in matches.columns):
        raise BaselineEvaluationError("Market odds leaked into canonical match data")
    return matches


def _prediction_time(row: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(f"{row.date} {row.kickoff_time}")
    if timestamp.tzinfo is not None:
        raise BaselineEvaluationError("Canonical kickoff unexpectedly includes a timezone")
    return timestamp.tz_localize(row.kickoff_timezone)


def _probability_row(
    match: Any,
    cutoff: pd.Timestamp,
    model: str,
    probabilities: tuple[float, float, float],
    history_rows: int,
    training_rows: int,
    latest_result: str,
) -> dict[str, Any]:
    return {
        "match_id": match.match_id,
        "season": match.season,
        "prediction_time": cutoff.isoformat(),
        "model": model,
        "available_history_rows": history_rows,
        "training_rows_used": training_rows,
        "latest_result_available_at": latest_result,
        "p_home": probabilities[0],
        "p_draw": probabilities[1],
        "p_away": probabilities[2],
        "actual_result": match.result,
    }


def build_predictions(matches: pd.DataFrame, splits: pd.DataFrame) -> pd.DataFrame:
    canonical_seasons = list(dict.fromkeys(matches["season"].tolist()))
    configured_seasons = splits["season"].tolist()
    if canonical_seasons != configured_seasons:
        raise BaselineEvaluationError("Canonical seasons no longer match the frozen split")

    development_seasons = set(splits.loc[splits["role"] == "development", "season"])
    eligible = matches["model_eligible"].astype(bool)
    targets = matches.loc[eligible & matches["season"].isin(development_seasons)].copy()
    targets["_prediction_time"] = [
        _prediction_time(row) for row in targets.itertuples(index=False)
    ]
    targets = targets.sort_values(["_prediction_time", "match_id"], kind="stable")
    if targets.empty:
        raise BaselineEvaluationError("Development split contains no eligible matches")

    rows: list[dict[str, Any]] = []
    for cutoff, fixtures in targets.groupby("_prediction_time", sort=True):
        history = evaluation_time.available_history(matches, cutoff)
        history_rows = len(history)
        if history_rows == 0:
            raise BaselineEvaluationError("A development prediction has no prior history")
        counts = history["result"].value_counts()
        if not all(int(counts.get(outcome, 0)) > 0 for outcome in ("H", "D", "A")):
            raise BaselineEvaluationError("Historical league-rate baseline has a zero class")
        league_probabilities = tuple(
            float(counts.get(outcome, 0) / history_rows) for outcome in ("H", "D", "A")
        )
        latest = pd.to_datetime(
            history["result_available_at"], format="ISO8601", utc=True, errors="raise"
        ).max()
        latest_result = latest.isoformat()

        for match in fixtures.itertuples(index=False):
            rows.append(
                _probability_row(
                    match,
                    cutoff,
                    "uniform_hda",
                    (1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0),
                    history_rows,
                    0,
                    latest_result,
                )
            )
            rows.append(
                _probability_row(
                    match,
                    cutoff,
                    "expanding_league_hda",
                    league_probabilities,
                    history_rows,
                    history_rows,
                    latest_result,
                )
            )

    predictions = pd.DataFrame(rows, columns=PREDICTION_COLUMNS)
    predictions["model"] = pd.Categorical(
        predictions["model"], categories=MODEL_ORDER, ordered=True
    )
    predictions = predictions.sort_values(
        ["prediction_time", "match_id", "model"], kind="stable"
    ).reset_index(drop=True)
    predictions["model"] = predictions["model"].astype("string")
    _validate_predictions(predictions, targets)
    return predictions


def _validate_predictions(predictions: pd.DataFrame, targets: pd.DataFrame) -> None:
    if predictions.columns.tolist() != PREDICTION_COLUMNS:
        raise BaselineEvaluationError("Prediction output schema changed")
    if predictions.duplicated(["match_id", "model"]).any():
        raise BaselineEvaluationError("Duplicate match/model predictions")
    if len(predictions) != len(targets) * len(MODEL_ORDER):
        raise BaselineEvaluationError("Prediction coverage is incomplete")
    probabilities = predictions[PROBABILITY_COLUMNS]
    if not probabilities.gt(0.0).all(axis=None) or not probabilities.lt(1.0).all(axis=None):
        raise BaselineEvaluationError("Baseline probabilities must be strictly inside (0, 1)")
    if not probabilities.sum(axis=1).sub(1.0).abs().lt(1e-12).all():
        raise BaselineEvaluationError("Baseline probabilities do not sum to one")
    if not predictions["actual_result"].isin(["H", "D", "A"]).all():
        raise BaselineEvaluationError("Prediction targets contain invalid results")
    prediction_times = pd.to_datetime(predictions["prediction_time"], utc=True, errors="raise")
    latest_results = pd.to_datetime(
        predictions["latest_result_available_at"], utc=True, errors="raise"
    )
    if not latest_results.lt(prediction_times).all():
        raise BaselineEvaluationError("Prediction history crosses the strict time boundary")


def score_predictions(predictions: pd.DataFrame) -> pd.DataFrame:
    probability_for_result = {
        "H": predictions["p_home"],
        "D": predictions["p_draw"],
        "A": predictions["p_away"],
    }
    actual_probability = pd.Series(
        [
            float(probability_for_result[result].iloc[index])
            for index, result in enumerate(predictions["actual_result"])
        ],
        index=predictions.index,
        dtype="float64",
    )
    scored = predictions.copy()
    scored["log_loss"] = actual_probability.map(lambda value: -math.log(value))
    scored["brier_score"] = [
        sum(
            (float(row[probability]) - float(result == outcome)) ** 2
            for probability, outcome in zip(PROBABILITY_COLUMNS, ("H", "D", "A"))
        )
        for row, result in zip(scored.to_dict("records"), scored["actual_result"])
    ]

    metric_rows: list[dict[str, Any]] = []
    for model in MODEL_ORDER:
        selected = scored.loc[scored["model"] == model]
        metric_rows.append(_metric_row("ALL", model, selected))
    for season in EXPECTED_SPLITS:
        season_name, role = season
        if role != "development":
            continue
        for model in MODEL_ORDER:
            selected = scored.loc[
                (scored["season"] == season_name) & (scored["model"] == model)
            ]
            metric_rows.append(_metric_row(season_name, model, selected))
    metrics = pd.DataFrame(metric_rows, columns=METRIC_COLUMNS)
    if metrics["matches"].le(0).any():
        raise BaselineEvaluationError("A metric group contains no matches")
    return metrics


def _metric_row(season: str, model: str, selected: pd.DataFrame) -> dict[str, Any]:
    return {
        "evaluation_role": "development",
        "season": season,
        "model": model,
        "matches": len(selected),
        "log_loss": float(selected["log_loss"].mean()),
        "brier_score": float(selected["brier_score"].mean()),
    }


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    return [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
        *["| " + " | ".join(str(value) for value in row) + " |" for row in rows],
    ]


def generate_report(predictions: pd.DataFrame, metrics: pd.DataFrame) -> str:
    overall = metrics.loc[metrics["season"] == "ALL"].set_index("model")
    winner = overall["log_loss"].idxmin()
    uniform_loss = float(overall.loc["uniform_hda", "log_loss"])
    winner_loss = float(overall.loc[winner, "log_loss"])
    improvement = (uniform_loss - winner_loss) / uniform_loss
    development_matches = int(predictions["match_id"].nunique())
    overall_rows = [
        [
            model,
            int(overall.loc[model, "matches"]),
            f"{float(overall.loc[model, 'log_loss']):.6f}",
            f"{float(overall.loc[model, 'brier_score']):.6f}",
        ]
        for model in MODEL_ORDER
    ]
    season_rows = [
        [
            row.season,
            row.model,
            row.matches,
            f"{row.log_loss:.6f}",
            f"{row.brier_score:.6f}",
        ]
        for row in metrics.loc[metrics["season"] != "ALL"].itertuples(index=False)
    ]
    lines = [
        "# Naive baseline evaluation",
        "",
        "## Verdict",
        "",
        f"**GO.** The first leakage-safe probabilistic baselines produced {development_matches:,}",
        "development-period predictions with complete coverage. This is a measured",
        "reference checkpoint, not a deployable 2026-27 model.",
        "",
        f"`{winner}` has the lowest development log loss. Its relative log-loss",
        f"improvement over `uniform_hda` is {improvement:.2%}. No final-holdout result",
        "or market probability was used to reach this statement.",
        "",
        "## Overall development results",
        "",
        *_markdown_table(
            ["Model", "Matches", "Log loss", "Brier score"], overall_rows
        ),
        "",
        "Lower is better. Log loss uses natural logarithms; the multiclass Brier",
        "score is the mean sum of squared H/D/A probability errors.",
        "",
        "## Results by season",
        "",
        *_markdown_table(
            ["Season", "Model", "Matches", "Log loss", "Brier score"], season_rows
        ),
        "",
        "## Frozen evaluation boundary",
        "",
        "- Warm-up history: 2017-18 through 2020-21.",
        "- Development walk-forward: 2021-22 through 2024-25.",
        "- Final holdout: 2025-26, still sealed and absent from predictions/metrics.",
        "- Each prediction uses only `result_available_at < prediction_time` history.",
        "- Same-kickoff fixtures share the same available history.",
        "",
        "## Baseline scope",
        "",
        "`uniform_hda` assigns one third to every outcome. `expanding_league_hda`",
        "uses only prior league-wide H/D/A frequencies. Neither baseline uses team",
        "identity, match statistics, betting odds, or promoted-team assumptions.",
        "The isolated market benchmark table is not loaded by the evaluator.",
        "",
        "## Next roadmap gate",
        "",
        "Implement independent Poisson under the same split and metrics. Do not open",
        "the 2025-26 holdout and do not implement the dynamic promoted-team prior yet.",
        "",
    ]
    return "\n".join(lines)


def write_outputs(predictions: pd.DataFrame, metrics: pd.DataFrame) -> None:
    PREDICTIONS_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(PREDICTIONS_OUTPUT, index=False, float_format="%.12f")
    metrics.to_csv(METRICS_OUTPUT, index=False, float_format="%.12f")
    REPORT_OUTPUT.write_text(generate_report(predictions, metrics), encoding="utf-8")


def main() -> int:
    foundation_status = run_data_foundation.main()
    if foundation_status != 0:
        return foundation_status
    splits = load_split_config()
    matches = load_matches()
    predictions = build_predictions(matches, splits)
    metrics = score_predictions(predictions)
    write_outputs(predictions, metrics)
    print(
        "Baseline evaluation complete: "
        f"{predictions['match_id'].nunique()} development matches, "
        f"{predictions['model'].nunique()} models."
    )
    print(f"Report: {REPORT_OUTPUT}")
    print("Final holdout: SEALED (2025-26)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
