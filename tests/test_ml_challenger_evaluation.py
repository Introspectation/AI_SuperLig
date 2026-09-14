from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import evaluation_time  # noqa: E402
import run_baseline_evaluation as baseline  # noqa: E402
import run_dixon_coles_evaluation as dc  # noqa: E402
import run_ml_challenger_evaluation as ml  # noqa: E402


def _synthetic_multinomial(rows: int, seed: int = 20260914):
    generator = np.random.default_rng(seed)
    features = generator.normal(size=(rows, 2))
    offsets = np.column_stack(
        [generator.normal(0.4, 0.3, rows), generator.normal(0.1, 0.3, rows)]
    )
    true = np.array([[0.2, 0.5, -0.3], [-0.1, -0.4, 0.2]])
    design = ml._design(features, features.mean(axis=0), features.std(axis=0))
    probabilities = ml._probabilities(design, true, offsets)
    labels = np.array(
        [generator.choice(3, p=row) for row in probabilities], dtype=int
    )
    return features, labels, offsets, true


class LogitFitTests(unittest.TestCase):
    def test_fit_recovers_adjustment_coefficients(self) -> None:
        features, labels, offsets, true = _synthetic_multinomial(40000)
        fit = ml.fit_logit(features, labels, offsets, ("a", "b"), True, 1.0)
        np.testing.assert_allclose(fit.coefficients, true, atol=0.05)

    def test_analytic_derivatives_match_finite_differences(self) -> None:
        features, labels, offsets, _ = _synthetic_multinomial(300)
        design = ml._design(features, features.mean(axis=0), features.std(axis=0))
        mask = ml._penalty_mask(3, False)
        coefficients = np.array([[0.1, -0.2, 0.3], [0.05, 0.1, -0.15]])
        gradient, information = ml._gradient_and_information(
            coefficients, design, offsets, labels, 2.0, mask
        )
        step = 1e-6
        numeric_gradient = np.zeros(6)
        numeric_information = np.zeros((6, 6))
        for position in range(6):
            up = coefficients.ravel().copy()
            down = coefficients.ravel().copy()
            up[position] += step
            down[position] -= step
            numeric_gradient[position] = (
                ml._objective(up.reshape(2, 3), design, offsets, labels, 2.0, mask)
                - ml._objective(down.reshape(2, 3), design, offsets, labels, 2.0, mask)
            ) / (2.0 * step)
            gradient_up, _ = ml._gradient_and_information(
                up.reshape(2, 3), design, offsets, labels, 2.0, mask
            )
            gradient_down, _ = ml._gradient_and_information(
                down.reshape(2, 3), design, offsets, labels, 2.0, mask
            )
            numeric_information[:, position] = -(gradient_up - gradient_down) / (2.0 * step)
        self.assertLess(np.abs(gradient - numeric_gradient).max(), 1e-5)
        self.assertLess(np.abs(information - numeric_information).max(), 1e-5)

    def test_infinite_penalty_is_the_declared_null_model(self) -> None:
        features, labels, offsets, _ = _synthetic_multinomial(400)
        base = np.full((len(labels), 3), 1.0 / 3.0)
        offset_fit = ml.fit_logit(features, labels, offsets, ("a", "b"), True, math.inf)
        self.assertTrue(offset_fit.is_null_adjustment)
        np.testing.assert_array_equal(ml.predict_logit(offset_fit, features, offsets, base), base)

        plain = ml.fit_logit(features, labels, offsets, ("a", "b"), False, math.inf)
        predicted = ml.predict_logit(plain, features, offsets, base)
        frequencies = np.bincount(labels, minlength=3) / len(labels)
        np.testing.assert_allclose(predicted, np.tile(frequencies, (len(labels), 1)), atol=1e-9)
        self.assertTrue(np.all(plain.coefficients[:, 1:] == 0.0))

    def test_stronger_penalty_shrinks_adjustments(self) -> None:
        features, labels, offsets, _ = _synthetic_multinomial(800)
        weak = ml.fit_logit(features, labels, offsets, ("a", "b"), True, 1.0)
        strong = ml.fit_logit(features, labels, offsets, ("a", "b"), True, 300.0)
        self.assertLess(np.abs(strong.coefficients).sum(), np.abs(weak.coefficients).sum())
        with self.assertRaises(ml.MLChallengerError):
            ml.fit_logit(features, labels, offsets, ("a", "b"), True, 0.0)


class ClubContextTests(unittest.TestCase):
    def _history(self) -> pd.DataFrame:
        start = pd.Timestamp("2024-01-01 17:00", tz="UTC")
        rows = [
            ("m1", "A", "B", "H", 5, 2, 0),
            ("m2", "C", "A", "D", 3, 3, 7),
            ("m3", "A", "D", "A", np.nan, 4, 14),
            ("m4", "E", "A", "A", 1, 6, 21),
        ]
        return pd.DataFrame(
            [
                {
                    "match_id": match_id,
                    "home_team": home,
                    "away_team": away,
                    "result": result,
                    "home_shots_on_target": home_sot,
                    "away_shots_on_target": away_sot,
                    "_kickoff_utc": start + pd.Timedelta(days=day),
                }
                for match_id, home, away, result, home_sot, away_sot, day in rows
            ]
        )

    def test_points_shots_share_and_rest_days(self) -> None:
        history = self._history()
        cutoff = pd.Timestamp("2024-01-25 20:00", tz="Europe/Istanbul")
        points, share, rest = ml.club_context(history, "A", cutoff, 1.3)
        self.assertAlmostEqual(points, (3 + 1 + 0 + 3) / 4)
        self.assertAlmostEqual(share, (5 + 3 + 6) / (5 + 3 + 6 + 2 + 3 + 1))
        expected_rest = (cutoff.tz_convert("UTC") - history["_kickoff_utc"].iloc[-1]).total_seconds() / 86400
        self.assertAlmostEqual(rest, expected_rest)
        late = pd.Timestamp("2024-03-01 20:00", tz="Europe/Istanbul")
        self.assertEqual(ml.club_context(history, "A", late, 1.3)[2], ml.REST_DAYS_CAP)
        self.assertEqual(ml.club_context(history, "Unseen", cutoff, 1.3), (1.3, 0.5, ml.REST_DAYS_CAP))


def _penalty_frames(loss) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    grid_rows, target_rows, availability_rows = [], [], []
    for position, season in enumerate(dc.GRID_SEASONS):
        kickoff = pd.Timestamp(f"{2019 + position}-09-01 20:00", tz="Europe/Istanbul")
        match_id = f"m{position}"
        target_rows.append({"match_id": match_id, "season": season, "_prediction_time": kickoff})
        availability_rows.append(
            {"match_id": match_id, "result_available_at": kickoff + pd.Timedelta(minutes=180)}
        )
        if season < ml.FIRST_PREDICTION_SEASON:
            continue
        for model in ml.MODEL_ORDER:
            for decay in (0.0015, 0.003):
                for penalty in ml.PENALTY_GRID:
                    grid_rows.append(
                        {
                            "match_id": match_id,
                            "model": model,
                            "season": season,
                            "decay_per_day": decay,
                            "prior_k": 64,
                            "penalty": penalty,
                            "log_loss": loss(season, decay, penalty),
                        }
                    )
    return pd.DataFrame(grid_rows), pd.DataFrame(target_rows), pd.DataFrame(availability_rows)


class PenaltySelectionTests(unittest.TestCase):
    CHOICES = {
        "2021-22": (0.0015, 64),
        "2022-23": (0.003, 64),
        "2023-24": (0.003, 64),
        "2024-25": (0.003, 64),
    }

    def test_selection_uses_only_earlier_prediction_seasons(self) -> None:
        def loss(season: str, decay: float, penalty: float) -> float:
            preferred = 10.0 if decay == 0.0015 else 100.0
            return 1.0 + (0.5 if math.isinf(penalty) else abs(math.log(penalty / preferred)) / 100.0)

        grid, targets, timeline = _penalty_frames(loss)
        selection = ml.select_penalty(grid, self.CHOICES, targets, timeline)
        candidate = selection.loc[selection["model"] == ml.CANDIDATE_MODEL]
        self.assertEqual(candidate["selected_penalty"].tolist(), [10.0, 100.0, 100.0, 100.0])
        self.assertEqual(candidate["tuning_matches"].tolist(), [1, 2, 3, 4])
        self.assertEqual(candidate["tuning_seasons"].iloc[0], "2020-21")

    def test_ties_select_the_larger_penalty(self) -> None:
        grid, targets, timeline = _penalty_frames(lambda season, decay, penalty: 1.0)
        selection = ml.select_penalty(grid, self.CHOICES, targets, timeline)
        self.assertTrue(np.isinf(selection["selected_penalty"]).all())

    def test_unavailable_tuning_result_fails(self) -> None:
        grid, targets, timeline = _penalty_frames(lambda season, decay, penalty: 1.0)
        late = targets.loc[targets["season"] == "2021-22", "_prediction_time"].iloc[0]
        timeline.loc[timeline["match_id"] == "m1", "result_available_at"] = late + pd.Timedelta(
            hours=1
        )
        with self.assertRaises(ml.MLChallengerError):
            ml.select_penalty(grid, self.CHOICES, targets, timeline)


class FeatureLeakageTests(unittest.TestCase):
    def test_future_and_current_match_data_cannot_change_features(self) -> None:
        splits = baseline.load_split_config()
        matches = baseline.load_matches()
        targets = dc.walk_forward_targets(matches, splits)
        cutoff = targets.loc[targets["season"] == "2022-23", "_prediction_time"].iloc[40]
        fixture = targets.loc[targets["_prediction_time"] == cutoff].iloc[0]

        def features(frame: pd.DataFrame) -> list[tuple[float, float, float]]:
            history = evaluation_time.available_history(dc.build_timeline(frame), cutoff)
            return [
                ml.club_context(history, club, cutoff, 1.3)
                for club in (fixture["home_team"], fixture["away_team"])
            ]

        original = features(matches)
        tampered = matches.copy()
        availability = pd.to_datetime(tampered["result_available_at"], format="ISO8601", utc=True)
        hidden = availability.ge(cutoff) | tampered["match_id"].eq(fixture["match_id"])
        tampered.loc[hidden, ["home_goals", "away_goals"]] = [9, 0]
        tampered.loc[hidden, "result"] = "H"
        tampered.loc[hidden, ["home_shots_on_target", "away_shots_on_target"]] = [30, 0]
        self.assertEqual(original, features(tampered))


class MLOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.predictions = pd.read_csv(
            ml.PREDICTIONS_OUTPUT,
            dtype={
                "match_id": "string",
                "season": "string",
                "model": "string",
                "prediction_time": "string",
                "actual_result": "string",
            },
        )
        cls.metrics = pd.read_csv(ml.METRICS_OUTPUT, dtype={"season": "string"})
        cls.grid = pd.read_csv(ml.GRID_METRICS_OUTPUT, dtype={"season": "string"})
        cls.selection = pd.read_csv(ml.SELECTION_OUTPUT, dtype={"target_season": "string"})

    def test_coverage_keeps_holdout_live_season_and_market_sealed(self) -> None:
        self.assertEqual(set(self.predictions["model"]), set(ml.MODEL_ORDER))
        for model in ml.MODEL_ORDER:
            selected = self.predictions.loc[self.predictions["model"] == model]
            self.assertEqual(len(selected), 1413)
            self.assertEqual(selected["match_id"].nunique(), 1413)
        self.assertEqual(
            set(self.predictions["season"]), {"2021-22", "2022-23", "2023-24", "2024-25"}
        )
        self.assertFalse(
            any("market" in column or "odds" in column for column in self.predictions.columns)
        )

    def test_published_probabilities_are_valid_and_strictly_bounded(self) -> None:
        probabilities = self.predictions[baseline.PROBABILITY_COLUMNS]
        self.assertTrue(probabilities.gt(0.0).all(axis=None))
        self.assertTrue(probabilities.lt(1.0).all(axis=None))
        self.assertTrue(probabilities.sum(axis=1).sub(1.0).abs().lt(5e-9).all())
        prediction_time = pd.to_datetime(self.predictions["prediction_time"], utc=True)
        latest = pd.to_datetime(self.predictions["latest_training_result_available_at"], utc=True)
        self.assertTrue(latest.lt(prediction_time).all())

    def test_models_use_declared_choices(self) -> None:
        choices = self.selection.set_index(["model", "target_season"])
        merged = self.predictions.merge(
            choices.reset_index().rename(columns={"target_season": "season"}),
            on=["model", "season"],
            suffixes=("", "_selected"),
            validate="many_to_one",
        )
        self.assertEqual(len(merged), len(self.predictions))
        self.assertTrue(merged["penalty"].eq(merged["selected_penalty"]).all())
        self.assertTrue(merged["decay_per_day"].eq(merged["decay_per_day_selected"]).all())
        self.assertTrue(merged["prior_k"].eq(merged["prior_k_selected"]).all())

    def test_selection_is_recomputable_from_grid_metrics(self) -> None:
        for row in self.selection.itertuples(index=False):
            tuning_seasons = row.tuning_seasons.split(";")
            self.assertTrue(all(season < row.target_season for season in tuning_seasons))
            self.assertNotIn("2019-20", tuning_seasons)
            tuning = self.grid.loc[
                (self.grid["model"] == row.model)
                & (self.grid["decay_per_day"] == row.decay_per_day)
                & (self.grid["prior_k"] == row.prior_k)
                & self.grid["season"].isin(tuning_seasons)
            ].copy()
            tuning["weighted"] = tuning["matches"] * tuning["log_loss"]
            summary = tuning.groupby("penalty")[["weighted", "matches"]].sum()
            losses = summary["weighted"] / summary["matches"]
            self.assertEqual(int(summary["matches"].iloc[0]), int(row.tuning_matches))
            self.assertLess(
                float(losses.loc[row.selected_penalty]) - float(losses.min()), 1e-9
            )

    def test_metrics_match_published_predictions(self) -> None:
        recomputed = baseline.score_predictions(self.predictions, ml.MODEL_ORDER)
        merged = recomputed.merge(
            self.metrics, on=["evaluation_role", "season", "model"], suffixes=("", "_published")
        )
        self.assertEqual(len(merged), len(self.metrics))
        self.assertTrue(merged["log_loss"].sub(merged["log_loss_published"]).abs().lt(1e-7).all())
        self.assertTrue(
            merged["brier_score"].sub(merged["brier_score_published"]).abs().lt(1e-7).all()
        )


if __name__ == "__main__":
    unittest.main()
