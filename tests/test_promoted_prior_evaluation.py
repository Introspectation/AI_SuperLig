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
import run_dixon_coles_evaluation as dc  # noqa: E402
import run_promoted_prior_evaluation as pp  # noqa: E402


class BlendAndMixtureTests(unittest.TestCase):
    def test_blend_follows_the_declared_formula(self) -> None:
        self.assertEqual(pp.blend(0.4, -0.2, 0.09, n=5, k=0), (0.4, 1.0, 0.0))
        value, weight, variance = pp.blend(0.4, -0.2, 0.09, n=0, k=8)
        self.assertAlmostEqual(value, -0.2, places=15)
        self.assertEqual(weight, 0.0)
        self.assertAlmostEqual(variance, 0.09, places=15)
        value, weight, variance = pp.blend(0.4, -0.2, 0.09, n=8, k=8)
        self.assertAlmostEqual(value, 0.1, places=15)
        self.assertEqual(weight, 0.5)
        self.assertAlmostEqual(variance, 0.045, places=15)
        self.assertEqual(pp.blend(0.4, -0.2, 0.09, n=24, k=8)[1], 0.75)
        with self.assertRaises(pp.PromotedPriorError):
            pp.blend(0.4, -0.2, 0.09, n=-1, k=8)

    def test_zero_variance_mixture_is_exactly_the_point_matrix(self) -> None:
        log_home, log_away = math.log(1.4), math.log(1.1)
        np.testing.assert_array_equal(
            pp.mixed_score_distribution(log_home, log_away, 0.0, 0.0, -0.08),
            dc.score_distribution(math.exp(log_home), math.exp(log_away), -0.08),
        )

    def test_uncertainty_mixture_is_a_valid_wider_distribution(self) -> None:
        log_home, log_away = math.log(1.4), math.log(1.1)
        point = pp.mixed_score_distribution(log_home, log_away, 0.0, 0.0, -0.08)
        mixed = pp.mixed_score_distribution(log_home, log_away, 0.09, 0.04, -0.08)
        self.assertAlmostEqual(float(mixed.sum()), 1.0, places=12)
        self.assertTrue((mixed > 0.0).all())
        goals = np.arange(point.shape[0])

        def home_goal_variance(matrix: np.ndarray) -> float:
            marginal = matrix.sum(axis=1)
            mean = float((goals * marginal).sum())
            return float(((goals - mean) ** 2 * marginal).sum())

        self.assertGreater(home_goal_variance(mixed), home_goal_variance(point))
        self.assertAlmostEqual(sum(pp.HERMITE_WEIGHTS), 1.0, places=15)
        self.assertAlmostEqual(sum(pp.HERMITE_NODES), 0.0, places=12)


class PromotedStatusTests(unittest.TestCase):
    def test_promotion_uses_only_previous_season_membership(self) -> None:
        order = ["2017-18", "2018-19", "2019-20"]
        rows = [
            ("2017-18", "X", "Y", True),
            ("2017-18", "Q", "X", False),
            ("2018-19", "X", "Z", True),
            ("2018-19", "Q", "Z", True),
            ("2019-20", "Z", "W", True),
        ]
        matches = pd.DataFrame(
            rows, columns=["season", "home_team", "away_team", "model_eligible"]
        )
        clubs = pp.season_clubs(matches)
        self.assertTrue(pp.is_promoted("Z", "2018-19", clubs, order))
        self.assertTrue(pp.is_promoted("Q", "2018-19", clubs, order))
        self.assertFalse(pp.is_promoted("X", "2018-19", clubs, order))
        self.assertTrue(pp.is_promoted("W", "2019-20", clubs, order))
        self.assertFalse(pp.is_promoted("Z", "2019-20", clubs, order))

        future = pd.concat(
            [
                matches,
                pd.DataFrame(
                    [("2019-20", "Z", "Y", True)],
                    columns=["season", "home_team", "away_team", "model_eligible"],
                ),
            ]
        )
        self.assertTrue(pp.is_promoted("Z", "2018-19", pp.season_clubs(future), order))
        with self.assertRaises(pp.PromotedPriorError):
            pp.is_promoted("X", "2017-18", clubs, order)


def _k_frames(loss) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    grid_rows, target_rows, availability_rows = [], [], []
    for position, season in enumerate(dc.GRID_SEASONS):
        kickoff = pd.Timestamp(f"{2019 + position}-09-01 20:00", tz="Europe/Istanbul")
        match_id = f"m{position}"
        target_rows.append({"match_id": match_id, "season": season, "_prediction_time": kickoff})
        availability_rows.append(
            {"match_id": match_id, "result_available_at": kickoff + pd.Timedelta(minutes=180)}
        )
        for model in pp.MODEL_ORDER:
            for decay in (0.0015, 0.003):
                for k in pp.K_GRID:
                    grid_rows.append(
                        {
                            "match_id": match_id,
                            "model": model,
                            "season": season,
                            "decay_per_day": decay,
                            "prior_k": k,
                            "log_loss": loss(season, decay, k),
                        }
                    )
    return pd.DataFrame(grid_rows), pd.DataFrame(target_rows), pd.DataFrame(availability_rows)


class KSelectionTests(unittest.TestCase):
    DECAYS = {"2021-22": 0.0015, "2022-23": 0.003, "2023-24": 0.003, "2024-25": 0.003}

    def test_selection_uses_earlier_seasons_at_the_target_decay(self) -> None:
        def loss(season: str, decay: float, k: int) -> float:
            preferred = 4 if decay == 0.0015 else 16
            return 1.0 + abs(k - preferred) / 100.0

        grid, targets, timeline = _k_frames(loss)
        selection = pp.select_k(grid, self.DECAYS, targets, timeline)
        candidate = selection.loc[selection["model"] == pp.CANDIDATE_MODEL]
        self.assertEqual(candidate["selected_k"].tolist(), [4, 16, 16, 16])
        self.assertEqual(candidate["tuning_matches"].tolist(), [2, 3, 4, 5])
        self.assertEqual(len(selection), len(pp.MODEL_ORDER) * 4)

    def test_ties_select_k_zero(self) -> None:
        grid, targets, timeline = _k_frames(lambda season, decay, k: 1.0)
        selection = pp.select_k(grid, self.DECAYS, targets, timeline)
        self.assertTrue(selection["selected_k"].eq(0).all())

    def test_unavailable_tuning_result_fails(self) -> None:
        grid, targets, timeline = _k_frames(lambda season, decay, k: 1.0 + k)
        late = targets.loc[targets["season"] == "2021-22", "_prediction_time"].iloc[0]
        timeline.loc[timeline["match_id"] == "m1", "result_available_at"] = late + pd.Timedelta(
            hours=1
        )
        with self.assertRaises(pp.PromotedPriorError):
            pp.select_k(grid, self.DECAYS, targets, timeline)


class PriorLeakageTests(unittest.TestCase):
    def test_season_end_offsets_ignore_later_seasons(self) -> None:
        splits = baseline.load_split_config()
        matches = baseline.load_matches()
        order = splits["season"].tolist()
        clubs = pp.season_clubs(matches)
        original = pp.season_end_offsets(
            dc.build_timeline(matches), "2020-21", 0.003, True, clubs, order
        )
        tampered = matches.copy()
        later = tampered["season"].isin(order[order.index("2021-22") :])
        tampered.loc[later, ["home_goals", "away_goals"]] = [9, 0]
        tampered.loc[later, "result"] = "H"
        replayed = pp.season_end_offsets(
            dc.build_timeline(tampered), "2020-21", 0.003, True, clubs, order
        )
        self.assertEqual(original.clubs, replayed.clubs)
        np.testing.assert_array_equal(original.attack, replayed.attack)
        np.testing.assert_array_equal(original.defence, replayed.defence)
        first_2021 = dc.walk_forward_targets(matches, splits)
        first_kickoff = first_2021.loc[first_2021["season"] == "2021-22", "_prediction_time"].min()
        self.assertLess(original.latest_result_available_at, first_kickoff)

    def test_prior_pools_only_seasons_before_the_target(self) -> None:
        order = baseline.load_split_config()["season"].tolist()
        stamp = pd.Timestamp("2020-01-01", tz="UTC")
        offsets = {
            season: pp.PriorOffsets(
                season, 0.003, True, (f"{season}-a", f"{season}-b"),
                np.array([value, value + 0.2]), np.array([-value, -value]), stamp,
            )
            for value, season in enumerate(order[order.index("2018-19") : order.index("2024-25")])
        }
        prior = pp.build_prior(offsets, "2021-22", order)
        self.assertEqual(prior.source_seasons, ("2018-19", "2019-20", "2020-21"))
        self.assertEqual(prior.offset_count, 6)
        self.assertAlmostEqual(prior.attack_offset, float(np.mean([0, 0.2, 1, 1.2, 2, 2.2])))
        with self.assertRaises(pp.PromotedPriorError):
            pp.build_prior(offsets, "2018-19", order)


class PromotedPriorOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.predictions = pd.read_csv(
            pp.PREDICTIONS_OUTPUT,
            dtype={
                "match_id": "string",
                "season": "string",
                "model": "string",
                "prediction_time": "string",
                "actual_result": "string",
            },
        )
        cls.metrics = pd.read_csv(pp.METRICS_OUTPUT, dtype={"season": "string"})
        cls.grid = pd.read_csv(pp.GRID_METRICS_OUTPUT, dtype={"season": "string"})
        cls.selection = pd.read_csv(pp.SELECTION_OUTPUT, dtype={"target_season": "string"})

    def test_coverage_keeps_holdout_live_season_and_market_sealed(self) -> None:
        self.assertEqual(set(self.predictions["model"]), set(pp.MODEL_ORDER))
        for model in pp.MODEL_ORDER:
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
        latest = pd.to_datetime(self.predictions["latest_result_available_at"], utc=True)
        self.assertTrue(latest.lt(prediction_time).all())

    def test_models_use_declared_choices(self) -> None:
        choices = self.selection.set_index(["model", "target_season"])
        for row in self.predictions.itertuples(index=False):
            choice = choices.loc[(row.model, row.season)]
            self.assertEqual(int(row.prior_k), int(choice["selected_k"]))
            self.assertEqual(float(row.decay_per_day), float(choice["decay_per_day"]))
        non_promoted = ~self.predictions["home_promoted"] & ~self.predictions["away_promoted"]
        self.assertTrue(self.predictions.loc[non_promoted, "home_log_rate_variance"].eq(0).all())
        self.assertTrue(self.predictions.loc[non_promoted, "home_prior_weight"].eq(1).all())
        point = self.predictions["model"] == pp.POINT_MODEL
        self.assertTrue(self.predictions.loc[point, "home_log_rate_variance"].eq(0).all())
        self.assertTrue(self.predictions.loc[point, "away_log_rate_variance"].eq(0).all())
        poisson_base = self.predictions["model"] == pp.POISSON_MODEL
        self.assertTrue(self.predictions.loc[poisson_base, "fitted_rho"].eq(0).all())

    def test_selection_is_recomputable_from_grid_metrics(self) -> None:
        for row in self.selection.itertuples(index=False):
            tuning_seasons = row.tuning_seasons.split(";")
            self.assertTrue(all(season < row.target_season for season in tuning_seasons))
            tuning = self.grid.loc[
                (self.grid["model"] == row.model)
                & (self.grid["decay_per_day"] == row.decay_per_day)
                & self.grid["season"].isin(tuning_seasons)
            ].copy()
            tuning["weighted"] = tuning["matches"] * tuning["log_loss"]
            summary = tuning.groupby("prior_k")[["weighted", "matches"]].sum()
            losses = summary["weighted"] / summary["matches"]
            self.assertEqual(int(summary["matches"].iloc[0]), int(row.tuning_matches))
            self.assertLess(float(losses.loc[row.selected_k]) - float(losses.min()), 1e-9)

    def test_metrics_match_published_predictions(self) -> None:
        recomputed = baseline.score_predictions(self.predictions, pp.MODEL_ORDER)
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
