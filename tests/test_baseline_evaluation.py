from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_baseline_evaluation as baseline  # noqa: E402


class BaselineEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.splits = baseline.load_split_config()
        cls.matches = baseline.load_matches()
        cls.predictions = baseline.build_predictions(cls.matches, cls.splits)
        cls.metrics = baseline.score_predictions(cls.predictions)

    def test_evaluation_split_is_frozen_and_holdout_is_sealed(self) -> None:
        self.assertEqual(
            list(self.splits.itertuples(index=False, name=None)),
            baseline.EXPECTED_SPLITS,
        )
        self.assertEqual(
            set(self.predictions["season"]),
            {"2021-22", "2022-23", "2023-24", "2024-25"},
        )
        self.assertNotIn("2025-26", set(self.predictions["season"]))
        self.assertEqual(self.predictions["match_id"].nunique(), 1413)
        self.assertEqual(len(self.predictions), 2826)

    def test_predictions_are_complete_probabilities_without_market_data(self) -> None:
        self.assertEqual(set(self.predictions["model"]), set(baseline.MODEL_ORDER))
        self.assertFalse(self.predictions.duplicated(["match_id", "model"]).any())
        probabilities = self.predictions[baseline.PROBABILITY_COLUMNS]
        self.assertTrue(probabilities.gt(0.0).all(axis=None))
        self.assertTrue(probabilities.lt(1.0).all(axis=None))
        self.assertTrue(probabilities.sum(axis=1).sub(1.0).abs().lt(1e-12).all())
        self.assertFalse(
            any(
                "market" in column or "odds" in column
                for column in self.predictions.columns
            )
        )

    def test_every_history_boundary_is_strict_and_auditable(self) -> None:
        prediction_time = pd.to_datetime(self.predictions["prediction_time"], utc=True)
        latest_result = pd.to_datetime(
            self.predictions["latest_result_available_at"], utc=True
        )
        self.assertTrue(latest_result.lt(prediction_time).all())
        uniform = self.predictions[self.predictions["model"] == "uniform_hda"]
        expanding = self.predictions[
            self.predictions["model"] == "expanding_league_hda"
        ]
        self.assertTrue(uniform["training_rows_used"].eq(0).all())
        self.assertTrue(
            expanding["training_rows_used"].eq(
                expanding["available_history_rows"]
            ).all()
        )
        self.assertGreaterEqual(int(expanding["available_history_rows"].min()), 1338)

    def test_metrics_cover_every_development_match(self) -> None:
        overall = self.metrics[self.metrics["season"] == "ALL"]
        self.assertEqual(set(overall["model"]), set(baseline.MODEL_ORDER))
        self.assertTrue(overall["matches"].eq(1413).all())
        self.assertTrue(overall["log_loss"].gt(0.0).all())
        self.assertTrue(overall["brier_score"].gt(0.0).all())
        uniform = overall[overall["model"] == "uniform_hda"].iloc[0]
        expanding = overall[
            overall["model"] == "expanding_league_hda"
        ].iloc[0]
        self.assertAlmostEqual(
            float(uniform.log_loss), math_log_one_third(), places=12
        )
        self.assertAlmostEqual(float(expanding.log_loss), 1.060313828507, places=12)
        self.assertAlmostEqual(float(expanding.brier_score), 0.640069777149, places=12)
        self.assertLess(float(expanding.log_loss), float(uniform.log_loss))


def math_log_one_third() -> float:
    import math

    return -math.log(1.0 / 3.0)


if __name__ == "__main__":
    unittest.main()
