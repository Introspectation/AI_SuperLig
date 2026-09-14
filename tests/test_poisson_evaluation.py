from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_baseline_evaluation as baseline  # noqa: E402
import run_poisson_evaluation as poisson  # noqa: E402


TRUE_INTERCEPT = 0.1
TRUE_HOME_ADVANTAGE = 0.25
TRUE_ATTACK = {"A": 0.3, "B": 0.1, "C": -0.1, "D": -0.3}
TRUE_DEFENCE = {"A": 0.2, "B": 0.0, "C": 0.1, "D": -0.3}
PREDICTIVE_COLUMNS = [
    "match_id",
    "prediction_time",
    "available_history_rows",
    "training_rows_used",
    "latest_result_available_at",
    "home_team_history_matches",
    "away_team_history_matches",
    "expected_home_goals",
    "expected_away_goals",
    "p_home",
    "p_draw",
    "p_away",
]


def _true_expected_goals(home_team: str, away_team: str) -> tuple[float, float]:
    return (
        math.exp(
            TRUE_INTERCEPT
            + TRUE_HOME_ADVANTAGE
            + TRUE_ATTACK[home_team]
            - TRUE_DEFENCE[away_team]
        ),
        math.exp(TRUE_INTERCEPT + TRUE_ATTACK[away_team] - TRUE_DEFENCE[home_team]),
    )


def _synthetic_history(repetitions: int, seed: int = 20260914) -> pd.DataFrame:
    generator = np.random.default_rng(seed)
    rows = []
    for _ in range(repetitions):
        for home_team in TRUE_ATTACK:
            for away_team in TRUE_ATTACK:
                if home_team == away_team:
                    continue
                expected_home, expected_away = _true_expected_goals(home_team, away_team)
                rows.append(
                    {
                        "home_team": home_team,
                        "away_team": away_team,
                        "home_goals": int(generator.poisson(expected_home)),
                        "away_goals": int(generator.poisson(expected_away)),
                    }
                )
    return pd.DataFrame(rows)


class PoissonModelTests(unittest.TestCase):
    def test_fit_recovers_identifiable_rates_from_synthetic_league(self) -> None:
        fit = poisson.fit_independent_poisson(_synthetic_history(repetitions=500))
        self.assertAlmostEqual(fit.home_advantage, TRUE_HOME_ADVANTAGE, delta=0.03)
        for home_team in TRUE_ATTACK:
            for away_team in TRUE_ATTACK:
                if home_team == away_team:
                    continue
                fitted = fit.expected_goals(home_team, away_team)
                expected = _true_expected_goals(home_team, away_team)
                for fitted_rate, true_rate in zip(fitted, expected):
                    self.assertLess(abs(fitted_rate / true_rate - 1.0), 0.05)

    def test_sparse_and_unseen_clubs_stay_finite(self) -> None:
        history = pd.DataFrame(
            {
                "home_team": ["A", "B"],
                "away_team": ["B", "A"],
                "home_goals": [0, 3],
                "away_goals": [2, 0],
            }
        )
        fit = poisson.fit_independent_poisson(history)
        self.assertTrue(np.isfinite(fit.attack).all())
        self.assertTrue(np.isfinite(fit.defence).all())
        self.assertEqual(fit.team_strength("Promoted FC"), (0.0, 0.0))
        expected_home, expected_away = fit.expected_goals("Promoted FC", "A")
        self.assertTrue(math.isfinite(expected_home) and expected_home > 0.0)
        self.assertTrue(math.isfinite(expected_away) and expected_away > 0.0)
        with self.assertRaises(poisson.PoissonEvaluationError):
            fit.expected_goals("A", "A")

    def test_score_matrix_matches_closed_form_for_equal_rates(self) -> None:
        matrix = poisson.score_distribution(1.0, 1.0)
        p_home, p_draw, p_away = poisson.hda_probabilities(matrix)
        closed_form_draw = sum(
            math.exp(-2.0) / math.factorial(goals) ** 2 for goals in range(40)
        )
        self.assertAlmostEqual(p_draw, closed_form_draw, places=12)
        self.assertAlmostEqual(p_home, p_away, places=15)
        self.assertAlmostEqual(p_home + p_draw + p_away, 1.0, places=12)
        self.assertAlmostEqual(float(matrix.sum()), 1.0, places=12)
        self.assertAlmostEqual(float(matrix[1, 0]), math.exp(-2.0), places=12)

    def test_invalid_training_rows_fail_loudly(self) -> None:
        history = pd.DataFrame(
            {
                "home_team": ["A"],
                "away_team": ["B"],
                "home_goals": [1.5],
                "away_goals": [0],
            }
        )
        with self.assertRaises(poisson.PoissonEvaluationError):
            poisson.fit_independent_poisson(history)
        with self.assertRaises(poisson.PoissonEvaluationError):
            poisson.fit_independent_poisson(history.iloc[0:0])


class PoissonLeakageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.splits = baseline.load_split_config()
        cls.matches = baseline.load_matches()
        cls.targets = baseline.development_targets(cls.matches, cls.splits)

    def test_same_kickoff_and_future_results_cannot_change_a_prediction(self) -> None:
        season_targets = self.targets.loc[self.targets["season"] == "2023-24"]
        group_sizes = season_targets.groupby("_prediction_time").size()
        cutoff = group_sizes[group_sizes >= 2].index[0]
        fixtures = self.targets.loc[self.targets["_prediction_time"] == cutoff]
        original = pd.DataFrame(poisson.predict_fixtures(self.matches, cutoff, fixtures))

        tampered = self.matches.copy()
        availability = pd.to_datetime(
            tampered["result_available_at"], format="ISO8601", utc=True
        )
        hidden = availability.ge(cutoff) | tampered["match_id"].isin(fixtures["match_id"])
        self.assertTrue(hidden.sum() > len(fixtures))
        tampered.loc[hidden, ["home_goals", "away_goals"]] = [9, 0]
        tampered.loc[hidden, "result"] = "H"
        replayed = pd.DataFrame(poisson.predict_fixtures(tampered, cutoff, fixtures))

        pd.testing.assert_frame_equal(
            original[PREDICTIVE_COLUMNS], replayed[PREDICTIVE_COLUMNS]
        )
        self.assertTrue(original["prediction_time"].nunique() == 1)
        self.assertTrue(original["available_history_rows"].nunique() == 1)


class PoissonEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.splits = baseline.load_split_config()
        cls.matches = baseline.load_matches()
        cls.predictions = poisson.build_predictions(cls.matches, cls.splits)
        cls.metrics = baseline.score_predictions(cls.predictions, [poisson.MODEL_NAME])

    def test_development_coverage_keeps_holdout_and_live_season_sealed(self) -> None:
        self.assertEqual(
            set(self.predictions["season"]),
            {"2021-22", "2022-23", "2023-24", "2024-25"},
        )
        self.assertEqual(self.predictions["match_id"].nunique(), 1413)
        self.assertEqual(len(self.predictions), 1413)
        self.assertEqual(set(self.predictions["model"]), {poisson.MODEL_NAME})
        self.assertFalse(
            any(
                "market" in column or "odds" in column
                for column in self.predictions.columns
            )
        )

    def test_predictions_are_valid_and_strictly_bounded(self) -> None:
        probabilities = self.predictions[baseline.PROBABILITY_COLUMNS]
        self.assertTrue(probabilities.gt(0.0).all(axis=None))
        self.assertTrue(probabilities.lt(1.0).all(axis=None))
        self.assertTrue(probabilities.sum(axis=1).sub(1.0).abs().lt(1e-12).all())
        prediction_time = pd.to_datetime(self.predictions["prediction_time"], utc=True)
        latest_result = pd.to_datetime(
            self.predictions["latest_result_available_at"], utc=True
        )
        self.assertTrue(latest_result.lt(prediction_time).all())
        self.assertTrue(
            self.predictions["training_rows_used"]
            .eq(self.predictions["available_history_rows"])
            .all()
        )

    def test_metrics_cover_every_development_match(self) -> None:
        overall = self.metrics[self.metrics["season"] == "ALL"].iloc[0]
        self.assertEqual(int(overall.matches), 1413)
        self.assertTrue(self.metrics["matches"].gt(0).all())
        self.assertEqual(len(self.metrics), 5)
        self.assertAlmostEqual(float(overall.log_loss), 1.008671903596, places=9)
        self.assertAlmostEqual(float(overall.brier_score), 0.600647894814, places=9)


if __name__ == "__main__":
    unittest.main()
