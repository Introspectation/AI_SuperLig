from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_baseline_evaluation as baseline  # noqa: E402
import run_dixon_coles_evaluation as dc  # noqa: E402


def _selection_frames(loss) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    grid_rows, target_rows, availability_rows = [], [], []
    for position, season in enumerate(dc.GRID_SEASONS):
        kickoff = pd.Timestamp(f"{2019 + position}-09-01 20:00", tz="Europe/Istanbul")
        match_id = f"m{position}"
        target_rows.append({"match_id": match_id, "season": season, "_prediction_time": kickoff})
        availability_rows.append(
            {"match_id": match_id, "result_available_at": kickoff + pd.Timedelta(minutes=180)}
        )
        for decay in dc.DECAY_GRID_PER_DAY:
            grid_rows.append(
                {
                    "match_id": match_id,
                    "season": season,
                    "decay_per_day": decay,
                    "log_loss": loss(season, decay),
                }
            )
    return pd.DataFrame(grid_rows), pd.DataFrame(target_rows), pd.DataFrame(availability_rows)


class DecaySelectionTests(unittest.TestCase):
    def test_selection_uses_only_earlier_seasons(self) -> None:
        def loss(season: str, decay: float) -> float:
            if season <= "2021-22":
                return 1.0 + abs(decay - 0.002)
            return 1.0 + 10.0 * abs(decay - 0.005)

        grid, targets, timeline = _selection_frames(loss)
        selection = dc.select_decays(grid, targets, timeline)
        self.assertEqual(
            selection["target_season"].tolist(), ["2021-22", "2022-23", "2023-24", "2024-25"]
        )
        self.assertEqual(
            selection["selected_decay_per_day"].tolist(), [0.002, 0.002, 0.005, 0.005]
        )
        self.assertEqual(selection["tuning_matches"].tolist(), [2, 3, 4, 5])
        self.assertEqual(
            selection["selected_at_grid_maximum"].tolist(), [False, False, True, True]
        )
        self.assertEqual(selection["tuning_seasons"].iloc[0], "2019-20;2020-21")

    def test_ties_select_the_smaller_decay(self) -> None:
        grid, targets, timeline = _selection_frames(lambda season, decay: 1.0)
        selection = dc.select_decays(grid, targets, timeline)
        self.assertTrue(selection["selected_decay_per_day"].eq(0.0).all())

    def test_tuning_result_unavailable_at_target_kickoff_fails(self) -> None:
        grid, targets, timeline = _selection_frames(lambda season, decay: 1.0 + decay)
        late = targets.loc[targets["season"] == "2021-22", "_prediction_time"].iloc[0]
        timeline.loc[timeline["match_id"] == "m1", "result_available_at"] = late + pd.Timedelta(
            hours=1
        )
        with self.assertRaises(dc.DixonColesError):
            dc.select_decays(grid, targets, timeline)


class DixonColesLeakageTests(unittest.TestCase):
    def test_future_and_same_kickoff_results_cannot_change_fits(self) -> None:
        splits = baseline.load_split_config()
        matches = baseline.load_matches()
        targets = dc.walk_forward_targets(matches, splits)
        season_targets = targets.loc[targets["season"] == "2022-23"]
        group_sizes = season_targets.groupby("_prediction_time").size()
        cutoff = group_sizes[group_sizes >= 2].index[3]
        fixture_ids = targets.loc[targets["_prediction_time"] == cutoff, "match_id"]
        original = dc.fit_cutoff(dc.build_timeline(matches), cutoff)

        tampered = matches.copy()
        availability = pd.to_datetime(
            tampered["result_available_at"], format="ISO8601", utc=True
        )
        hidden = availability.ge(cutoff) | tampered["match_id"].isin(fixture_ids)
        self.assertGreater(int(hidden.sum()), len(fixture_ids))
        tampered.loc[hidden, ["home_goals", "away_goals"]] = [9, 0]
        tampered.loc[hidden, "result"] = "H"
        replayed = dc.fit_cutoff(dc.build_timeline(tampered), cutoff)

        self.assertEqual(original.history_rows, replayed.history_rows)
        self.assertEqual(set(original.fits), set(replayed.fits))
        for key, fit in original.fits.items():
            other = replayed.fits[key]
            self.assertEqual(fit.rho, other.rho)
            self.assertEqual(fit.strengths.intercept, other.strengths.intercept)
            self.assertEqual(fit.strengths.home_advantage, other.strengths.home_advantage)
            np.testing.assert_array_equal(fit.strengths.attack, other.strengths.attack)
            np.testing.assert_array_equal(fit.strengths.defence, other.strengths.defence)


class DixonColesOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.predictions = pd.read_csv(
            dc.PREDICTIONS_OUTPUT,
            dtype={
                "match_id": "string",
                "season": "string",
                "model": "string",
                "prediction_time": "string",
                "actual_result": "string",
            },
        )
        cls.metrics = pd.read_csv(dc.METRICS_OUTPUT, dtype={"season": "string"})
        cls.grid = pd.read_csv(dc.GRID_METRICS_OUTPUT, dtype={"season": "string"})
        cls.selection = pd.read_csv(dc.SELECTION_OUTPUT, dtype={"target_season": "string"})

    def test_coverage_keeps_holdout_live_season_and_market_sealed(self) -> None:
        self.assertEqual(set(self.predictions["model"]), set(dc.MODEL_ORDER))
        for model in dc.MODEL_ORDER:
            selected = self.predictions.loc[self.predictions["model"] == model]
            self.assertEqual(len(selected), 1413)
            self.assertEqual(selected["match_id"].nunique(), 1413)
        self.assertEqual(
            set(self.predictions["season"]), {"2021-22", "2022-23", "2023-24", "2024-25"}
        )
        self.assertEqual(set(self.grid["season"]), set(dc.GRID_SEASONS))
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

    def test_models_use_their_declared_decay_and_rho(self) -> None:
        selected = dict(
            zip(self.selection["target_season"], self.selection["selected_decay_per_day"])
        )
        self.assertTrue(set(selected.values()).issubset(set(dc.DECAY_GRID_PER_DAY)))
        tuned = self.predictions["model"].isin([dc.CANDIDATE_MODEL, dc.DECAY_ONLY_MODEL])
        expected = self.predictions.loc[tuned, "season"].map(selected)
        self.assertTrue(self.predictions.loc[tuned, "decay_per_day"].eq(expected).all())
        no_decay = self.predictions["model"] == dc.RHO_ONLY_MODEL
        self.assertTrue(self.predictions.loc[no_decay, "decay_per_day"].eq(0.0).all())
        decay_only = self.predictions["model"] == dc.DECAY_ONLY_MODEL
        self.assertTrue(self.predictions.loc[decay_only, "fitted_rho"].eq(0.0).all())

    def test_selection_is_recomputable_from_grid_metrics(self) -> None:
        for row in self.selection.itertuples(index=False):
            tuning_seasons = row.tuning_seasons.split(";")
            self.assertTrue(all(season < row.target_season for season in tuning_seasons))
            tuning = self.grid.loc[self.grid["season"].isin(tuning_seasons)].copy()
            tuning["weighted"] = tuning["matches"] * tuning["log_loss"]
            summary = tuning.groupby("decay_per_day")[["weighted", "matches"]].sum()
            losses = summary["weighted"] / summary["matches"]
            self.assertEqual(int(summary["matches"].iloc[0]), int(row.tuning_matches))
            self.assertLess(
                float(losses.loc[row.selected_decay_per_day]) - float(losses.min()), 1e-9
            )

    def test_metrics_match_published_predictions(self) -> None:
        recomputed = baseline.score_predictions(self.predictions, dc.MODEL_ORDER)
        merged = recomputed.merge(
            self.metrics, on=["evaluation_role", "season", "model"], suffixes=("", "_published")
        )
        self.assertEqual(len(merged), len(self.metrics))
        self.assertTrue(merged["matches"].eq(merged["matches_published"]).all())
        self.assertTrue(merged["log_loss"].sub(merged["log_loss_published"]).abs().lt(1e-7).all())
        self.assertTrue(
            merged["brier_score"].sub(merged["brier_score_published"]).abs().lt(1e-7).all()
        )


if __name__ == "__main__":
    unittest.main()
