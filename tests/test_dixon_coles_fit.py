from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_dixon_coles_evaluation as dc  # noqa: E402
import run_poisson_evaluation as poisson  # noqa: E402


ATTACK = {"A": 0.3, "B": 0.1, "C": -0.1, "D": -0.3}
DEFENCE = {"A": 0.2, "B": 0.0, "C": 0.1, "D": -0.3}
INTERCEPT = 0.1
HOME_ADVANTAGE = 0.25
START = pd.Timestamp("2020-01-01", tz="UTC")


def _rates(home_team: str, away_team: str) -> tuple[float, float]:
    return (
        math.exp(INTERCEPT + HOME_ADVANTAGE + ATTACK[home_team] - DEFENCE[away_team]),
        math.exp(INTERCEPT + ATTACK[away_team] - DEFENCE[home_team]),
    )


def _synthetic_history(repetitions: int, rho: float, seed: int = 20260914) -> pd.DataFrame:
    generator = np.random.default_rng(seed)
    pairs = [(home, away) for home in ATTACK for away in ATTACK if home != away]
    distributions = {pair: dc.score_distribution(*_rates(*pair), rho) for pair in pairs}
    rows = []
    for _ in range(repetitions):
        for pair in pairs:
            matrix = distributions[pair]
            cell = int(generator.choice(matrix.size, p=matrix.ravel()))
            home_goals, away_goals = divmod(cell, matrix.shape[1])
            rows.append(
                {
                    "home_team": pair[0],
                    "away_team": pair[1],
                    "home_goals": home_goals,
                    "away_goals": away_goals,
                    "_kickoff_utc": START + pd.Timedelta(days=len(rows)),
                }
            )
    return pd.DataFrame(rows)


class DixonColesFitTests(unittest.TestCase):
    def test_zero_decay_without_rho_reproduces_stage4(self) -> None:
        history = _synthetic_history(repetitions=40, rho=0.0)
        stage4 = poisson.fit_independent_poisson(history)
        stage5 = dc.fit_dixon_coles(
            dc.build_fit_history(history), 0.0, estimate_rho=False
        )
        self.assertEqual(stage5.rho, 0.0)
        for home_team in ATTACK:
            for away_team in ATTACK:
                if home_team == away_team:
                    continue
                for old, new in zip(
                    stage4.expected_goals(home_team, away_team),
                    stage5.expected_goals(home_team, away_team),
                ):
                    self.assertLess(abs(new / old - 1.0), 1e-9)

    def test_fit_recovers_low_score_dependence(self) -> None:
        history = _synthetic_history(repetitions=800, rho=-0.12)
        fit = dc.fit_dixon_coles(dc.build_fit_history(history), 0.0)
        self.assertAlmostEqual(fit.rho, -0.12, delta=0.05)
        for home_team in ATTACK:
            for away_team in ATTACK:
                if home_team == away_team:
                    continue
                for fitted, true in zip(
                    fit.expected_goals(home_team, away_team),
                    _rates(home_team, away_team),
                ):
                    self.assertLess(abs(fitted / true - 1.0), 0.06)

    def test_analytic_derivatives_match_finite_differences(self) -> None:
        fh = dc.build_fit_history(_synthetic_history(repetitions=20, rho=-0.1))
        generator = np.random.default_rng(7)
        theta = generator.normal(0.0, 0.1, fh.parameter_count)
        theta[-1] = -0.08
        weights = np.exp(-0.002 * fh.age_days)
        gradient, information = dc._gradient_and_information(theta, fh, weights, True)
        step = 1e-6
        numeric_gradient = np.zeros_like(gradient)
        numeric_information = np.zeros_like(information)
        for position in range(len(theta)):
            up = theta.copy()
            down = theta.copy()
            up[position] += step
            down[position] -= step
            numeric_gradient[position] = (
                dc._objective(up, fh, weights, True) - dc._objective(down, fh, weights, True)
            ) / (2.0 * step)
            gradient_up, _ = dc._gradient_and_information(up, fh, weights, True)
            gradient_down, _ = dc._gradient_and_information(down, fh, weights, True)
            numeric_information[:, position] = -(gradient_up - gradient_down) / (2.0 * step)
        self.assertLess(np.abs(gradient - numeric_gradient).max(), 1e-4)
        self.assertLess(np.abs(information - numeric_information).max(), 1e-4)

    def test_decay_downweights_old_results(self) -> None:
        rows = []
        for day in range(0, 200, 2):
            rows.append(("A", "B", 3, 0, day))
            rows.append(("B", "A", 0, 3, day + 1))
        for day in range(800, 1000, 2):
            rows.append(("A", "B", 0, 2, day))
            rows.append(("B", "A", 2, 0, day + 1))
        history = pd.DataFrame(
            [
                {
                    "home_team": home,
                    "away_team": away,
                    "home_goals": home_goals,
                    "away_goals": away_goals,
                    "_kickoff_utc": START + pd.Timedelta(days=day),
                }
                for home, away, home_goals, away_goals, day in rows
            ]
        )
        fh = dc.build_fit_history(history)
        self.assertEqual(float(fh.age_days.min()), 0.0)
        self.assertEqual(float(fh.age_days.max()), 999.0)
        flat = dc.fit_dixon_coles(fh, 0.0, estimate_rho=False)
        decayed = dc.fit_dixon_coles(fh, 0.01, estimate_rho=False)
        self.assertLess(decayed.effective_weight, flat.effective_weight)
        flat_home, _ = flat.expected_goals("A", "B")
        decayed_home, _ = decayed.expected_goals("A", "B")
        self.assertLess(decayed_home, 0.6 * flat_home)

    def test_score_matrix_applies_dixon_coles_cells(self) -> None:
        home_rate, away_rate, rho = 1.3, 1.1, -0.1
        matrix = dc.score_distribution(home_rate, away_rate, rho)
        base = math.exp(-home_rate - away_rate)
        self.assertAlmostEqual(float(matrix.sum()), 1.0, places=12)
        self.assertAlmostEqual(
            float(matrix[0, 0]), base * (1.0 - home_rate * away_rate * rho), places=12
        )
        self.assertAlmostEqual(
            float(matrix[0, 1]), base * away_rate * (1.0 + home_rate * rho), places=12
        )
        self.assertAlmostEqual(
            float(matrix[1, 0]), base * home_rate * (1.0 + away_rate * rho), places=12
        )
        self.assertAlmostEqual(
            float(matrix[1, 1]), base * home_rate * away_rate * (1.0 - rho), places=12
        )
        independent = poisson.score_distribution(home_rate, away_rate)
        size = independent.shape[0]
        self.assertEqual(matrix.shape[0], dc.SCORE_GRID_MAX_GOALS + 1)
        np.testing.assert_allclose(
            dc.score_distribution(home_rate, away_rate, 0.0)[:size, :size],
            independent,
            rtol=0,
            atol=1e-15,
        )

    def test_invalid_inputs_fail_loudly(self) -> None:
        with self.assertRaises(dc.DixonColesError):
            dc.score_distribution(5.0, 5.0, 0.1)
        fh = dc.build_fit_history(_synthetic_history(repetitions=2, rho=0.0))
        with self.assertRaises(dc.DixonColesError):
            dc.fit_dixon_coles(fh, -0.001)
        with self.assertRaises(dc.DixonColesError):
            dc.build_fit_history(pd.DataFrame(columns=["home_team", "away_team"]))


if __name__ == "__main__":
    unittest.main()
