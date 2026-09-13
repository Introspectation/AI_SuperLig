from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_canonical_data as canonical_build  # noqa: E402
import evaluation_time  # noqa: E402
import run_data_audit as audit  # noqa: E402


class CanonicalDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sources = audit.load_source_catalog()
        manifest = audit.ensure_raw_sources(sources, offline=True)
        cls.frames = audit.read_raw_frames(sources)
        audit.lock_or_validate_schemas(cls.frames, write_schema_lock=False)
        audit.build_evidence(cls.frames, manifest)
        tff, _ = canonical_build.validate_tff_snapshot()
        base = canonical_build.build_base_matches(cls.frames)
        enriched, cls.join_audit = canonical_build.apply_tff_kickoffs(base, tff)
        cls.matches = canonical_build.finalize_matches(enriched)
        cls.market = canonical_build.build_market_benchmark(cls.frames, cls.matches)

    def test_canonical_grain_required_fields_and_kickoffs(self) -> None:
        self.assertEqual(self.matches.columns.tolist(), canonical_build.CANONICAL_COLUMNS)
        self.assertEqual(len(self.matches), 3088)
        self.assertFalse(self.matches["match_id"].duplicated().any())
        self.assertFalse(
            self.matches.duplicated(["season", "date", "home_team", "away_team"]).any()
        )
        self.assertFalse(self.matches["kickoff_time"].isna().any())
        self.assertEqual(
            self.matches["kickoff_time_source"].value_counts().to_dict(),
            {
                "football_data_europe_london_converted": 2476,
                "tff_archive": 612,
            },
        )
        summer = self.matches[
            (self.matches["season"] == "2019-20")
            & (self.matches["home_team"] == "Denizlispor")
            & (self.matches["away_team"] == "Galatasaray")
        ].iloc[0]
        winter = self.matches[
            (self.matches["season"] == "2019-20")
            & (self.matches["home_team"] == "Antalyaspor")
            & (self.matches["away_team"] == "Goztepe")
        ].iloc[0]
        self.assertEqual(summer.kickoff_time, "20:30")
        self.assertEqual(winter.kickoff_time, "13:30")
        self.assertEqual(summer.kickoff_timezone, "Europe/Istanbul")

    def test_statuses_preserve_on_pitch_and_official_results(self) -> None:
        self.assertEqual(int(self.matches["model_eligible"].sum()), 3057)
        self.assertEqual(
            self.matches["match_status"].value_counts().to_dict(),
            {
                "played": 3056,
                "not_played_forfeit": 29,
                "abandoned_forfeit": 2,
                "played_then_awarded_forfeit": 1,
            },
        )
        selected = self.matches[
            (self.matches["season"] == "2018-19")
            & (self.matches["home_team"] == "Akhisarspor")
            & (self.matches["away_team"] == "Besiktas")
        ].iloc[0]
        self.assertEqual((selected.home_goals, selected.away_goals), (1, 3))
        self.assertEqual(
            (selected.official_home_goals, selected.official_away_goals), (0, 3)
        )
        self.assertEqual(selected.official_result, "A")
        self.assertTrue(selected.model_eligible)

    def test_tff_join_is_complete_and_reviewed(self) -> None:
        totals = self.join_audit.sum(numeric_only=True).to_dict()
        self.assertEqual(int(totals["football_data_rows"]), 612)
        self.assertEqual(int(totals["tff_snapshot_rows"]), 612)
        self.assertEqual(int(totals["matched_rows"]), 612)
        self.assertEqual(int(totals["unmatched_rows"]), 0)
        self.assertEqual(int(totals["reviewed_date_mismatches"]), 1)
        self.assertEqual(int(totals["reviewed_score_differences"]), 1)
        self.assertEqual(int(totals["duplicate_canonical_keys"]), 0)

    def test_result_availability_is_conservative_and_source_reviewed(self) -> None:
        self.assertEqual(int(self.matches["result_available_at"].notna().sum()), 3057)
        self.assertEqual(
            self.matches["result_availability_rule"].value_counts().to_dict(),
            {
                "kickoff_plus_180_minutes": 3056,
                "not_model_eligible": 31,
                "reviewed_resumption_plus_180_minutes": 1,
            },
        )
        eligible = self.matches[self.matches["model_eligible"]]
        kickoff_at = pd.to_datetime(
            eligible["date"] + " " + eligible["kickoff_time"],
            format="%Y-%m-%d %H:%M",
        ).dt.tz_localize("Europe/Istanbul")
        available_at = pd.to_datetime(eligible["result_available_at"], utc=True)
        self.assertTrue(available_at.gt(kickoff_at).all())

        resumed = self.matches[
            (self.matches["season"] == "2018-19")
            & (self.matches["home_team"] == "Istanbul Basaksehir")
            & (self.matches["away_team"] == "Bursaspor")
        ].iloc[0]
        self.assertEqual(resumed.date, "2019-02-23")
        self.assertEqual(resumed.kickoff_time, "19:00")
        self.assertEqual(resumed.result_available_at, "2019-02-24T22:00+03:00")

        ordinary = self.matches[
            (self.matches["season"] == "2019-20")
            & (self.matches["home_team"] == "Fenerbahce")
            & (self.matches["away_team"] == "Gaziantep FK")
        ].iloc[0]
        self.assertEqual(ordinary.kickoff_time, "20:00")
        self.assertEqual(ordinary.result_available_at, "2019-08-19T23:00+03:00")
        ordinary_available = pd.Timestamp(ordinary.result_available_at)
        at_boundary = evaluation_time.available_history(
            self.matches, ordinary_available
        )
        after_boundary = evaluation_time.available_history(
            self.matches, ordinary_available + pd.Timedelta(minutes=1)
        )
        self.assertNotIn(ordinary.match_id, set(at_boundary["match_id"]))
        self.assertIn(ordinary.match_id, set(after_boundary["match_id"]))

        before_resumed_result = evaluation_time.available_history(
            self.matches, "2019-02-24T21:59:00+03:00"
        )
        after_resumed_result = evaluation_time.available_history(
            self.matches, "2019-02-24T22:01:00+03:00"
        )
        self.assertNotIn(resumed.match_id, set(before_resumed_result["match_id"]))
        self.assertIn(resumed.match_id, set(after_resumed_result["match_id"]))
        self.assertFalse(after_resumed_result["model_eligible"].eq(False).any())

        leakage_contract = (ROOT / "LEAKAGE_CONTRACT.md").read_text(encoding="utf-8")
        self.assertIn("result_available_at < t", leakage_contract)
        self.assertEqual(
            canonical_build.availability_risk_summary(self.matches),
            {
                "eligible_predictions": 3057,
                "affected_predictions": 1367,
                "unsafe_pair_exposures": 1788,
                "max_unavailable_results": 6,
            },
        )

    def test_history_filter_rejects_naive_prediction_time(self) -> None:
        with self.assertRaises(evaluation_time.TimelineError):
            evaluation_time.available_history(self.matches, "2026-08-01 20:00")

    def test_market_is_isolated_normalized_and_regime_labeled(self) -> None:
        self.assertEqual(self.market.columns.tolist(), canonical_build.MARKET_COLUMNS)
        self.assertEqual(len(self.market), 3054)
        self.assertFalse(self.market["match_id"].duplicated().any())
        self.assertTrue(set(self.market["match_id"]).issubset(set(self.matches["match_id"])))
        probabilities = self.market[["market_p_home", "market_p_draw", "market_p_away"]]
        self.assertTrue(probabilities.sum(axis=1).sub(1.0).abs().lt(1e-12).all())
        self.assertTrue(probabilities.ge(0.0).all(axis=None))
        self.assertTrue(probabilities.le(1.0).all(axis=None))
        self.assertEqual(
            self.market["benchmark_tier"].value_counts().to_dict(),
            {"primary_market_average": 2445, "secondary_single_bookmaker": 609},
        )
        self.assertFalse(any("odds" in column.lower() for column in self.matches.columns))

    def test_dynamic_promoted_team_prior_is_a_deferred_contract(self) -> None:
        design = (ROOT / "MODEL_DESIGN.md").read_text(encoding="utf-8")
        self.assertIn("dynamic promoted-team prior", design)
        self.assertIn("n / (n + k)", design)
        self.assertIn("No 1. Lig data is added in this phase", design)


if __name__ == "__main__":
    unittest.main()
